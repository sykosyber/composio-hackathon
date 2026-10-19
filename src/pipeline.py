"""Deterministic pipeline with agentic steps inside it. Same order every run; each step is cached.

trigger -> 1 extract -> 2 research fan-out -> 3 guardrails -> 4 outputs -> 5 monitors
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from . import cache, config, extract, guardrails, outputs, research
from .models import Deadline, ResearchResult

Log = Callable[[str], None]


def _apply_injections(results: dict[str, ResearchResult], inj: dict) -> None:
    """Demo-only: append the SYNTHETIC biased sentences so the guardrail visibly catches them."""
    for name, edits in inj.items():
        if name.startswith("_") or name not in results:
            continue
        c = results[name].output.content
        for k, v in edits.items():
            field = k.removesuffix("_append")
            if isinstance(c.get(field), str):
                c[field] = c[field] + v


def run(email: dict | None = None, *, live_contests: set[str] | None = None, inject: bool = False,
        push: bool = False, monitors: bool = False, log: Log = print) -> dict[str, Any]:
    data = cache.load()
    email = email or data["trigger_email"]
    log(f"[0] TRIGGER   email: {email.get('subject','')!r}   (MODE={config.MODE})")

    ex = extract.extract_ballot(email)
    log(f"[1] EXTRACT   {ex.city}, {ex.county} County - {ex.election_name}")
    log(f"              source: {ex.official_election_url}")
    for c in ex.contests:
        log(f"              - {c.kind:7s} {c.name}")

    results = asyncio.run(research.research_all(ex.contests, ex.county, ex.city, ex.election_name, live_contests))
    log(f"[2] RESEARCH  {len(results)} Parallel Task results "
        f"({sum(1 for r in results.values() if r.run_id)} live, {sum(1 for r in results.values() if not r.run_id)} cached)")
    if inject:
        _apply_injections(results, data.get("_demo_injections", {}))
        log("              (demo: injected 2 synthetic biased sentences)")

    entries, findings = [], []
    for c in ex.contests:
        if c.name in results:
            e, f = guardrails.check(c.name, results[c.name])
            entries.append(e)
            findings += f
    log(f"[3] GUARDRAIL {len(findings)} findings")
    for f in findings:
        log(f"              {f.action.upper():9s} {f.rule:15s} {f.contest} :: {f.field} :: {f.detail[:110]}")

    deadlines = [Deadline.model_validate(d) for d in data.get("deadlines", [])]
    md = outputs.render_markdown(entries, deadlines, data.get("drop_boxes_walnut_creek", []),
                                 ex.county, ex.city, ex.official_election_url)
    out_md = config.OUT_DIR / "your_ballot_explained.md"
    out_md.write_text(md)
    log(f"[4] OUTPUTS   doc rendered -> {out_md.relative_to(config.ROOT)} ({len(md)} chars)")
    doc = cal = draft = None
    if push:
        doc = outputs.create_doc(md)
        log(f"              Google Doc created: {json.dumps(doc)[:200]}")
        cal = outputs.add_calendar(deadlines)
        log(f"              Calendar: {len(cal)} events")
        # TODO(cline): pull the doc URL out of `doc` once the response shape is confirmed
        draft = outputs.create_invite_draft(None, ex.county, ex.city)
        log("              Gmail DRAFT created (not sent - human hits send)")
    else:
        log(f"              (push=False) would create Doc + {len(deadlines)} calendar events + 1 Gmail DRAFT")
        subj, body = outputs.invite_text(None, ex.county, ex.city)
        log(f"              invite draft preview: {subj!r}")

    mons = []
    names = [e.name for e in entries if not e.held_back]
    if monitors:
        from . import monitor
        mons = monitor.create_monitors(names, ex.city, ex.county)
        log(f"[5] MONITOR   {len(mons)} Parallel monitors created (daily) -> webhook -> Slack DM")
    else:
        log(f"[5] MONITOR   (monitors=False) would create {len(names)} daily Parallel monitors -> webhook -> Slack DM")

    return {"extraction": ex.model_dump(), "entries": [e.model_dump() for e in entries],
            "findings": [f.model_dump() for f in findings], "markdown_path": str(out_md),
            "doc": doc, "calendar": cal, "draft": draft, "monitors": mons}
