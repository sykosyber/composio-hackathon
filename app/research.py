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

from . import cache, config

CATEGORY_QUERIES: dict[str, list[str]] = {
    "streetlight": ["San Francisco report streetlight outage 311", "SFPUC streetlight repair report"],
    "road_pothole": ["San Francisco report pothole 311 SF Public Works", "SF Public Works street repair request"],
    "sidewalk_accessibility": ["San Francisco report damaged sidewalk 311 Public Works",
                               "San Francisco curb ramp accessibility request"],
    "graffiti": ["San Francisco report graffiti 311 Public Works", "SF graffiti removal request"],
    "illegal_dumping": ["San Francisco report illegal dumping 311 Recology", "SF bulky item pickup request"],
    "tree": ["San Francisco report street tree problem 311 Public Works urban forestry",
             "SF StreetTreeSF maintenance request"],
    "transit_stop": ["San Francisco Muni bus shelter damage report SFMTA", "SFMTA report transit stop problem"],
    "water_sewer": ["San Francisco report water leak sewer SFPUC", "SFPUC report flooding clogged drain"],
    "noise": ["San Francisco noise complaint 311 report", "SF noise ordinance complaint who to call"],
    "parking": ["San Francisco report blocked driveway abandoned vehicle SFMTA 311",
                "SFMTA parking enforcement request"],
    "other": ["San Francisco 311 report a problem city services", "SF 311 service request categories"],
}


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


def agency_query(category: str, note: str, address_hint: str) -> tuple[str, list[str]]:
    """Single source of truth for the agency cache key, shared with scripts/warm_cache.py.

    The objective deliberately excludes the free text note so that every report in a
    category shares one cache entry. That is what makes DEMO_MODE instant.
    """
    objective = (
        f"Identify the exact {config.DEMO_CITY} city agency responsible for this issue and the "
        f"official reporting channel with its URL. Issue category: {category}. "
        "Prefer official city government pages such as sf.gov and 311."
    )
    return objective, CATEGORY_QUERIES.get(category, CATEGORY_QUERIES["other"])


def find_agency(category: str, note: str, address_hint: str) -> list[dict]:
    """Who is responsible and how do you report it, with citations."""
    objective, queries = agency_query(category, note, address_hint)
    return _search("parallel_agency", objective, queries)


def dedupe_query(category: str, address_hint: str) -> tuple[str, list[str]]:
    """Single source of truth for the dedupe cache key, shared with scripts/warm_cache.py."""
    where = address_hint or config.DEMO_CITY
    label = category.replace("_", " ")
    objective = (
        f"Find out whether a {label} problem near {where} in {config.DEMO_CITY} has already been "
        "reported recently, for example in 311 open data, an outage map, or local news."
    )
    return objective, [
        f"{where} {label} 311 report {config.DEMO_CITY}",
        f"{config.DEMO_CITY} {label} near {where} news recent",
    ]


def check_already_reported(category: str, address_hint: str) -> list[dict]:
    """Is this already known: existing reports, outage maps, recent local news."""
    objective, queries = dedupe_query(category, address_hint)
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
