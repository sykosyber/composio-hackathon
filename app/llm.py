"""Open-source model behind an OpenAI-compatible endpoint.

Reuses the httpx approach from the legacy ballot explainer and adds: timeout, one retry on
parse failure, response caching, and a rule-based classifier fallback so the pipeline never
stalls when the model is unreachable.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from . import cache, config, domains
from .models import CATEGORIES, RoutingCard, Source

SYSTEM = """You are a civic issue router for San Francisco. You read one neighborhood report and
return ONE JSON object. Rules:
- Use ONLY the research snippets provided for agency, channel and channel_url. Never invent a URL.
- If the snippets do not support an agency or a reporting URL, leave those fields as empty strings.
- sources must be a subset of the provided snippets, copied exactly.
- Never recommend candidates or political positions.
- draft_body is a short, polite, factual report: what, where, since when if known. No personal data.
Return JSON with exactly these keys: category, severity, summary, agency, channel, channel_url,
already_reported, sources, draft_subject, draft_body."""

def rule_category(note: str, domain: str | None = None) -> str:
    """Rule-based classifier fallback, delegated to the domain pack."""
    return domains.get(domain).classify(note)


def rule_severity(note: str, domain: str | None = None) -> str:
    """Rule-based severity fallback, delegated to the domain pack."""
    return domains.get(domain).severity(note)


def _chat(system: str, user: str) -> str:
    if not config.have(config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL):
        raise RuntimeError("LLM_BASE_URL / LLM_API_KEY / LLM_MODEL are not set")
    resp = httpx.post(
        config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json={
            "model": config.LLM_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=config.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)  # some open models wrap JSON in prose
        if not match:
            raise
        return json.loads(match.group(0))


def _coerce(data: dict) -> RoutingCard:
    if data.get("category") not in CATEGORIES:
        data["category"] = "other"
    if data.get("severity") not in ("low", "medium", "high"):
        data["severity"] = "medium"
    if data.get("already_reported") not in ("yes", "likely", "unknown"):
        data["already_reported"] = "unknown"
    clean: list[dict] = []
    for s in data.get("sources") or []:
        if isinstance(s, dict) and s.get("url"):
            clean.append({"title": str(s.get("title") or s["url"])[:200], "url": str(s["url"])})
    data["sources"] = clean
    return RoutingCard.model_validate(data)


def _retag(subject: str, pin_id: str, card: RoutingCard, address_hint: str) -> str:
    """Guarantee the [PIN-<id>] tag so the Gmail reply trigger can match the thread."""
    tag = f"[PIN-{pin_id}]"
    body = re.sub(r"^\[PIN-[^\]]*\]\s*", "", (subject or "").strip())
    if not body:
        body = f"{card.category.replace('_', ' ').capitalize()} at {address_hint or 'reported location'}"
    return f"{tag} {body}"[:200]


def fallback_card(pin_id: str, note: str, address_hint: str, snippets: list[dict]) -> RoutingCard:
    """Rule-based card used when the model is down or returns unusable JSON."""
    category = rule_category(note)
    label = category.replace("_", " ")
    where = address_hint or "the reported location"
    return RoutingCard(
        category=category,  # type: ignore[arg-type]
        severity=rule_severity(note),  # type: ignore[arg-type]
        summary=f"Reported {label} at {where}.",
        agency="",
        channel="",
        channel_url="",
        already_reported="unknown",
        sources=[Source(title=str(s.get("title") or s.get("url")), url=str(s.get("url")))
                 for s in snippets if s.get("url")][:4],
        draft_subject=f"[PIN-{pin_id}] {label.capitalize()} at {where}",
        draft_body=(f"Hello,\n\nA neighbor reported the following issue at {where} "
                    f"({label}):\n\n{note}\n\nCould you confirm the correct queue for this report?"
                    "\n\nThank you."),
    )


def route(pin_id: str, note: str, address_hint: str, lat: float, lng: float,
          snippets: list[dict], dedupe_hint: str = "") -> tuple[RoutingCard, str]:
    """Return (card, source_label). source_label is cache | llm | fallback."""
    payload = {"note": note, "hint": address_hint, "snips": snippets, "dedupe": dedupe_hint,
               "model": config.LLM_MODEL}
    cached = cache.get("llm_route", payload)
    if cached is not None:
        try:
            card = _coerce(dict(cached))
            card.draft_subject = _retag(card.draft_subject, pin_id, card, address_hint)
            return card, "cache"
        except Exception:
            pass

    user = (
        f"Report id: PIN-{pin_id}\nNote: {note}\nApproximate location: "
        f"{address_hint or 'unknown'} (lat {lat:.5f}, lng {lng:.5f}), {config.DEMO_CITY}.\n\n"
        "Research snippets (the ONLY allowed source of agency and channel_url):\n"
        f"{json.dumps(snippets, indent=2)[:6000]}\n\n"
        f"Duplicate check notes: {dedupe_hint or 'none'}\n\n"
        f"draft_subject MUST start with [PIN-{pin_id}]."
    )
    last: Optional[Exception] = None
    for _ in range(2):  # one retry on parse failure
        try:
            card = _coerce(_parse(_chat(SYSTEM, user)))
            card.draft_subject = _retag(card.draft_subject, pin_id, card, address_hint)
            cache.put("llm_route", payload, card.model_dump())
            return card, "llm"
        except Exception as exc:
            last = exc
    print(f"[llm] falling back to rules: {last!r}")
    return fallback_card(pin_id, note, address_hint, snippets), "fallback"
