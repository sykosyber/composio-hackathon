#!/usr/bin/env python3
"""Pre-warm data/cache/ so DEMO_MODE=1 gives a fast, identical run on stage.

    .venv/bin/python scripts/warm_cache.py            # seed from official SF pages
    .venv/bin/python scripts/warm_cache.py --live     # call Parallel per category and cache

Without --live this writes cache entries built from official City and County of San
Francisco pages, so the demo still shows a cited routing card if the venue network dies.
Every URL below was verified on 2026-10-19.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import cache, config, llm, research  # noqa: E402

SF311 = {"title": "311 Customer Service Center | SF.gov",
         "url": "https://www.sf.gov/departments--311-customer-service-center",
         "excerpt": "SF 311 is the city's single point of contact for non emergency service "
                    "requests. Call 311, use the web forms, or use the SF311 mobile app."}

# category -> cited results, official sources only
OFFICIAL: dict[str, list[dict]] = {
    "streetlight": [
        {"title": "Report a problem with a streetlight | SF.gov",
         "url": "https://www.sf.gov/report-problem-streetlight",
         "excerpt": "Report a streetlight that is out, flickering or damaged. The San Francisco "
                    "Public Utilities Commission maintains most city streetlights and SF 311 "
                    "routes the request."}, SF311],
    "road_pothole": [
        {"title": "Report pothole and street issues | SF.gov",
         "url": "https://www.sf.gov/report-pothole-and-street-issues",
         "excerpt": "San Francisco Public Works repairs potholes on city maintained streets. "
                    "Report potholes and street defects through SF 311."}, SF311],
    "sidewalk_accessibility": [
        {"title": "Report curb and sidewalk problems | SF.gov",
         "url": "https://www.sf.gov/report-curb-and-sidewalk-problems",
         "excerpt": "Report broken, uplifted or obstructed sidewalks and damaged curb ramps. "
                    "San Francisco Public Works inspects sidewalk defects."}, SF311],
    "graffiti": [
        {"title": "Report graffiti issues | SF.gov",
         "url": "https://www.sf.gov/report-graffiti-issues",
         "excerpt": "Report graffiti on public or private property. San Francisco Public Works "
                    "removes graffiti from public property."}, SF311],
    "illegal_dumping": [
        {"title": "Report illegal dumping activity | SF.gov",
         "url": "https://www.sf.gov/report-illegal-dumping-activity",
         "excerpt": "Report illegally dumped items on streets and sidewalks. San Francisco "
                    "Public Works collects the material."},
        {"title": "Request street or sidewalk cleaning | SF.gov",
         "url": "https://www.sf.gov/request-street-or-sidewalk-cleaning",
         "excerpt": "Request cleaning of a street or sidewalk through SF 311."}],
    "tree": [
        {"title": "Report a damaged or fallen tree | SF.gov",
         "url": "https://www.sf.gov/report-damaged-or-fallen-tree",
         "excerpt": "San Francisco Public Works urban forestry maintains street trees. Report "
                    "hanging limbs, fallen branches or tree damage. Hazardous limbs are "
                    "treated as urgent."}, SF311],
    "transit_stop": [
        {"title": "Enforcement Requests | SFMTA",
         "url": "https://www.sfmta.com/services/enforcement-requests",
         "excerpt": "The San Francisco Municipal Transportation Agency operates Muni and "
                    "maintains transit stops and shelters."}, SF311],
    "water_sewer": [
        {"title": "Report flooding, water leaks, sewer backup, or odor issues | SF.gov",
         "url": "https://www.sf.gov/report-flooding-water-leaks-sewer-backup-or-odor-issues/",
         "excerpt": "The San Francisco Public Utilities Commission handles water main breaks, "
                    "sewer backups, clogged catch basins and street flooding."}, SF311],
    "parking": [
        {"title": "Report blocked driveway or illegal parking | SF.gov",
         "url": "https://www.sf.gov/report-blocked-driveway-or-illegal-parking",
         "excerpt": "SFMTA parking enforcement responds to blocked driveways and illegal "
                    "parking. Abandoned vehicles are reported separately."}, SF311],
    "noise": [SF311],
    "other": [SF311],
}

AGENCY: dict[str, tuple[str, str]] = {
    "streetlight": ("San Francisco Public Utilities Commission", "SF 311 web form or the SF311 app"),
    "road_pothole": ("San Francisco Public Works", "SF 311 web form or the SF311 app"),
    "sidewalk_accessibility": ("San Francisco Public Works", "SF 311 web form"),
    "graffiti": ("San Francisco Public Works", "SF 311 graffiti report form"),
    "illegal_dumping": ("San Francisco Public Works", "SF 311 illegal dumping report"),
    "tree": ("San Francisco Public Works urban forestry", "SF 311 street tree request"),
    "transit_stop": ("SFMTA", "SFMTA enforcement and service request"),
    "water_sewer": ("San Francisco Public Utilities Commission", "SF 311 web form"),
    "parking": ("SFMTA parking enforcement", "SF 311 web form"),
    "noise": ("", ""),  # intentionally unverified: shows the needs_human guardrail on stage
    "other": ("", ""),
}

# The exact demo pin, so step 4 is a cache hit on stage.
DEMO_NOTE = "Streetlight out at Valencia and 18th, very dark at night."
DEMO_HINT = "Valencia St and 18th St"


def warm_search(live: bool) -> None:
    """Cache one agency lookup and one duplicate check per category."""
    for category, hits in OFFICIAL.items():
        if live and config.PARALLEL_API_KEY:
            got = research.find_agency(category)
            research.check_already_reported(category, DEMO_HINT)
            print(f"  live {category}: {len(got)} results")
            continue
        objective, queries = research.agency_query(category)
        cache.put("parallel_agency",
                  {"objective": objective, "queries": queries,
                   "mode": config.PARALLEL_SEARCH_MODE}, hits)
        print(f"  cached parallel_agency/{category}: {len(hits)} sources")


def warm_route() -> None:
    """Cache the routing card for the exact pin dropped during the demo."""
    category = "streetlight"
    snippets = OFFICIAL[category]
    agency, channel = AGENCY[category]
    card = {
        "category": category,
        "severity": "medium",
        "summary": f"A streetlight is out at {DEMO_HINT}, leaving the crosswalk dark at night.",
        "agency": agency,
        "channel": channel,
        "channel_url": snippets[0]["url"],
        "already_reported": "unknown",
        "sources": [{"title": s["title"], "url": s["url"]} for s in snippets],
        "draft_subject": f"[PIN-x] Streetlight out at {DEMO_HINT}",
        "draft_body": (
            f"Hello,\n\nA neighbor reported that a streetlight is out at {DEMO_HINT} in "
            "San Francisco. The crosswalk is very dark at night, which is a safety concern for "
            "people walking.\n\nCould you confirm the service request and the expected repair "
            "window?\n\nThank you."
        ),
    }
    # The dedupe hint must match what the pipeline builds, so the key lines up.
    dedupe_objective, dedupe_queries = research.dedupe_query(category, DEMO_HINT)
    dedupe_hits = cache.get("parallel_dedupe", {
        "objective": dedupe_objective, "queries": dedupe_queries,
        "mode": config.PARALLEL_SEARCH_MODE,
    }) or []
    snips = (snippets + list(dedupe_hits))[:8]
    dedupe_hint = " | ".join(f"{h['title']}: {h.get('excerpt', '')[:160]}" for h in dedupe_hits[:3])
    payload = {"note": DEMO_NOTE, "hint": DEMO_HINT, "snips": snips,
               "dedupe": dedupe_hint, "model": config.LLM_MODEL}
    cache.put("llm_route", payload, card)
    print(f"  cached llm_route for the demo pin ({len(card['sources'])} sources)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="call Parallel once per category and cache the real results")
    args = parser.parse_args()
    if args.live and not config.PARALLEL_API_KEY:
        print("PARALLEL_API_KEY is not set, falling back to the official seed cache.")
        args.live = False

    print(f"warming {config.CACHE_DIR}")
    warm_search(args.live)
    warm_route()
    files = len(list(config.CACHE_DIR.glob("*.json")))
    print(f"done, {files} cache files. Sanity check: "
          f"{llm.rule_category(DEMO_NOTE)} / {llm.rule_severity(DEMO_NOTE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
