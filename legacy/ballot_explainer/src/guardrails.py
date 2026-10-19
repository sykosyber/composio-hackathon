"""Step 3: guardrail pass. Fully local + deterministic (the LLM check is an optional second pass).

Rules
1. no_citation      Any claim field whose basis has zero citations is DROPPED.
2. loaded_language  Sentences with recommendation / loaded wording in agent-authored text are REDACTED.
3. missing_side     A measure must have both official arguments accounted for. 'filed' or 'none_filed'
                    is fine (we say so explicitly); 'not_found' on either side => the measure is HELD BACK.
4. llm_flag         (optional, MODE=live + model configured) second model call flags subtler bias.

Hard rule for the whole product: the agent never recommends candidates or positions.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from . import config
from .models import CleanEntry, GuardrailFinding, ResearchResult

# Identity/structural fields that are not claims; never dropped for lack of citation.
STRUCTURAL = {"contest_name", "measure_id", "jurisdiction", "official_source_url"}

# Text the agent itself wrote (as opposed to attributed summaries of official arguments).
AUTHORED = {
    "contest": ["what_the_office_controls", "neutral_summary"],
    "measure": ["plain_language_summary", "yes_means", "no_means", "fiscal_impact"],
}

LOADED_PATTERNS = [
    r"\bvote (yes|no)\b", r"\byou should\b", r"\bshould (support|oppose|vote)\b", r"\bwe (recommend|endorse)\b",
    r"\b(best|better|stronger|weaker|worst) (choice|candidate|option)\b", r"\bno[- ]brainer\b",
    r"\bmust vote\b", r"\b(clearly|obviously|definitely|honestly|undeniably)\b",
    r"\b(disastrous|reckless|radical|extreme|corrupt|dangerous|failed|wasteful)\b",
    r"\bevery (caring|good|smart|responsible) \w+\b",
]
LOADED_RE = re.compile("|".join(LOADED_PATTERNS), re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _cited_fields(basis: list[dict]) -> dict[str, list[str]]:
    """field -> citation urls. List elements ('candidates.0') roll up to their parent."""
    out: dict[str, list[str]] = {}
    for b in basis:
        urls = [c["url"] for c in b.get("citations") or [] if c.get("url")]
        top = b["field"].split(".")[0]
        out.setdefault(top, [])
        out[top].extend(u for u in urls if u not in out[top])
    return out


def _scrub(text: str) -> tuple[str, list[str]]:
    kept, hits = [], []
    for s in SENTENCE_RE.split(text.strip()):
        m = LOADED_RE.search(s)
        (hits.append(f"{m.group(0)!r} in: {s}") if m else kept.append(s))
    return " ".join(kept), hits


def check(name: str, rr: ResearchResult, use_llm: bool | None = None) -> tuple[CleanEntry, list[GuardrailFinding]]:
    content: dict[str, Any] = copy.deepcopy(rr.output.content)
    basis = [b.model_dump() for b in rr.output.basis]
    cites = _cited_fields(basis)
    findings: list[GuardrailFinding] = []
    held = False

    # Rule 1: drop uncited claims
    for field in list(content):
        if field in STRUCTURAL or content[field] in (None, [], ""):
            continue
        if not cites.get(field):
            findings.append(GuardrailFinding(contest=name, field=field, rule="no_citation",
                                             detail="0 citations in Parallel basis", action="dropped"))
            content.pop(field)

    # Rule 2: loaded / recommendation language in agent-authored text
    for field in AUTHORED[rr.kind]:
        if isinstance(content.get(field), str):
            cleaned, hits = _scrub(content[field])
            for h in hits:
                findings.append(GuardrailFinding(contest=name, field=field, rule="loaded_language", detail=h, action="redacted"))
            content[field] = cleaned
    if rr.kind == "contest":
        for c in content.get("candidates", []):
            pri = []
            for p in c.get("stated_priorities", []):
                if LOADED_RE.search(p) and not p.lower().startswith(("says", "states", "said")):
                    findings.append(GuardrailFinding(contest=name, field=f"candidates[{c['name']}].stated_priorities",
                                                     rule="loaded_language", detail=p, action="redacted"))
                else:
                    pri.append(p)
            c["stated_priorities"] = pri

    # Rule 3: measures need both sides accounted for
    if rr.kind == "measure":
        for side, label in (("argument_for", "in favor"), ("argument_against", "against")):
            arg = content.get(side) or {"status": "not_found"}
            if arg.get("status") == "not_found":
                held = True
                findings.append(GuardrailFinding(contest=name, field=side, rule="missing_side",
                                                 detail=f"argument {label} not located", action="held_back"))
            elif arg.get("status") == "none_filed":
                arg["summary"] = f"The official voter guide says no argument {label} was filed."
                findings.append(GuardrailFinding(contest=name, field=side, rule="missing_side",
                                                 detail=f"no argument {label} filed (stated explicitly)", action="annotated"))

    # Rule 4: optional LLM second pass
    if use_llm if use_llm is not None else (config.MODE == "live" and config.MODEL):
        findings += llm_bias_pass(name, content)

    return CleanEntry(name=name, kind=rr.kind, content=content, citations=cites, held_back=held), findings


def llm_bias_pass(name: str, content: dict) -> list[GuardrailFinding]:
    """Second model call: flag recommendation or loaded language the regex missed. Flags only; never rewrites."""
    from . import llm

    try:
        out = llm.chat_json(
            "You audit nonpartisan voter-guide text. Flag any sentence that recommends a vote, praises or "
            'criticizes a candidate/side, or uses loaded language. Return {"flags":[{"field":str,"sentence":str,"why":str}]}. '
            "Return an empty list if clean.",
            str(content),
        )
    except Exception as e:  # never block the demo on the auditor
        print(f"  ! llm bias pass skipped: {e!r}")
        return []
    return [GuardrailFinding(contest=name, field=f.get("field", "?"), rule="llm_flag",
                             detail=f"{f.get('sentence','')} ({f.get('why','')})", action="annotated")
            for f in out.get("flags", [])]
