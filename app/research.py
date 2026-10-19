"""Parallel: agency lookup, duplicate check, and the ongoing Monitor.

Verified against parallel-web 1.3.5 in .venv:
  Parallel(api_key=...).search(objective=..., search_queries=[...], mode=..., timeout=...)
      -> SearchResult(.results[].{url,title,excerpts})
  Parallel(...).monitor.create(type="event_stream", frequency=..., settings={...},
      processor="lite", webhook={...}, metadata={str: str}) -> Monitor(.monitor_id)

Every call is cached by input hash. With DEMO_MODE=1 the cache is served first.
Nothing here ever raises into the pipeline: on failure it returns empty results.
"""
from __future__ import annotations

from typing import Any

from . import cache, config, domains

# Kept as a re-export so existing callers and tests keep working. The authoritative copy
# now lives in the civic_311 domain pack.
from .domains.civic_311 import CATEGORY_QUERIES  # noqa: F401

def _client():
    from parallel import Parallel  # pip install parallel-web

    return Parallel(api_key=config.PARALLEL_API_KEY)


def _flatten(result: Any) -> list[dict]:
    rows: list[dict] = []
    for r in getattr(result, "results", []) or []:
        excerpts = list(getattr(r, "excerpts", None) or [])
        rows.append({
            "title": (getattr(r, "title", "") or getattr(r, "url", ""))[:200],
            "url": getattr(r, "url", ""),
            "excerpt": " ".join(excerpts)[:600],
        })
    return [r for r in rows if r["url"]]


def _search(namespace: str, objective: str, queries: list[str], max_chars: int = 4000) -> list[dict]:
    payload = {"objective": objective, "queries": queries, "mode": config.PARALLEL_SEARCH_MODE}
    cached = cache.get(namespace, payload)
    if cached is not None and (config.DEMO_MODE or not config.PARALLEL_API_KEY):
        return list(cached)
    if not config.PARALLEL_API_KEY:
        return list(cached or [])
    try:
        result = _client().search(
            objective=objective,
            search_queries=queries,
            mode=config.PARALLEL_SEARCH_MODE,
            max_chars_total=max_chars,
            timeout=config.SEARCH_TIMEOUT,
        )
        rows = _flatten(result)
        if rows:
            cache.put(namespace, payload, rows)
        return rows
    except Exception as exc:
        print(f"[parallel] {namespace} failed: {exc!r}")
        return list(cached or [])


def agency_query(category: str, domain: str | None = None) -> tuple[str, list[str]]:
    """Single source of truth for the agency cache key, shared with scripts/warm_cache.py.

    Keyed on category alone, deliberately. The free text note and the address are excluded
    so every report in a category shares one cache entry, which is what makes DEMO_MODE
    instant and the stage run identical every time.
    """
    return domains.get(domain).research_queries(category)


def find_agency(category: str, domain: str | None = None) -> list[dict]:
    """Who is responsible and how do you report it, with citations."""
    objective, queries = agency_query(category, domain)
    return _search("parallel_agency", objective, queries)


def dedupe_query(category: str, address_hint: str,
                 domain: str | None = None) -> tuple[str, list[str]]:
    """Single source of truth for the dedupe cache key, shared with scripts/warm_cache.py."""
    return domains.get(domain).dedupe_queries(category, address_hint or config.DEMO_CITY)


def check_already_reported(category: str, address_hint: str,
                           domain: str | None = None) -> list[dict]:
    """Is this already known: existing reports, outage maps, recent local news."""
    objective, queries = dedupe_query(category, address_hint, domain)
    return _search("parallel_dedupe", objective, queries, max_chars=2500)


def create_monitor(pin_id: str, category: str, address_hint: str) -> str:
    """One event_stream Monitor keeps watching an open issue. Returns monitor_id or ''."""
    if not (config.PARALLEL_API_KEY and config.PARALLEL_MONITOR_WEBHOOK_URL):
        return ""
    where = address_hint or config.DEMO_CITY
    try:
        monitor = _client().monitor.create(
            type="event_stream",
            frequency="1d",
            processor="lite",
            settings={"query": (
                f"New official updates, repair schedules, outage notices or local news about a "
                f"{category.replace('_', ' ')} issue near {where} in {config.DEMO_CITY}."
            )},
            webhook={"url": config.PARALLEL_MONITOR_WEBHOOK_URL,
                     "event_types": ["monitor.event.detected"]},
            metadata={"pin_id": pin_id, "category": category},
            timeout=config.SEARCH_TIMEOUT,
        )
        return getattr(monitor, "monitor_id", "") or ""
    except Exception as exc:
        print(f"[parallel] monitor.create failed: {exc!r}")
        return ""


def monitor_event_text(payload: dict) -> tuple[str, str]:
    """Turn a monitor.event.detected webhook into (pin_id, text). Best effort, never raises."""
    data = payload.get("data") or {}
    pin_id = str((data.get("metadata") or {}).get("pin_id", ""))
    lines: list[str] = []
    try:
        res = _client().monitor.events(data["monitor_id"],
                                       event_group_id=data["event"]["event_group_id"])
        for ev in getattr(res, "events", []) or []:
            out = getattr(ev, "output", None)
            if out is not None:
                lines.append(str(getattr(out, "content", out))[:300])
    except Exception as exc:
        print(f"[parallel] monitor.events failed: {exc!r}")
    if not lines:
        fallback = (data.get("event") or {}).get("title") or "New activity detected for this issue."
        lines = [str(fallback)[:300]]
    return pin_id, " ".join(lines)
