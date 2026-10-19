#!/usr/bin/env python3
"""Generate data/pins.seed.json: 9 realistic SF pins clustered in the Mission.

    .venv/bin/python scripts/seed.py

Timestamps are relative to now so the morning brief always has fresh material.
Run this before the demo, then POST /demo/reset restores exactly this state.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.geo import address_hint  # noqa: E402
from app.models import Pin  # noqa: E402

# Every URL below returned HTTP 200 on 2026-10-19 (re-verified 2:25 PM PT).
SF311 = {"title": "311 Customer Service Center | SF.gov", "url": "https://www.sf.gov/departments--311-customer-service-center"}
PW = {"title": "San Francisco Public Works", "url": "https://sf.gov/departments/public-works"}
MTA = {"title": "SFMTA customer service", "url": "https://www.sfmta.com/contact-us"}
POTHOLE = {"title": "Report pothole and street issues | SF.gov", "url": "https://www.sf.gov/report-pothole-and-street-issues"}
DUMPING = {"title": "Report illegal dumping activity | SF.gov", "url": "https://www.sf.gov/report-illegal-dumping"}
SIDEWALK = {"title": "Report curb and sidewalk problems | SF.gov", "url": "https://www.sf.gov/report-curb-and-sidewalk-problems"}
GRAFFITI = {"title": "Report graffiti issues | SF.gov", "url": "https://www.sf.gov/report-graffiti-issues"}
WATER = {"title": "Report flooding, water leaks, sewer backup, or odor issues | SF.gov",
         "url": "https://www.sf.gov/report-flooding-water-leaks-sewer-backup-or-odor-issues"}
TREE = {"title": "Report a damaged or fallen tree | SF.gov", "url": "https://www.sf.gov/report-damaged-or-fallen-tree"}
VEHICLE = {"title": "Report an abandoned vehicle | SF.gov", "url": "https://www.sf.gov/report-abandoned-vehicle"}


def hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat(timespec="seconds")


SEEDS = [
    # Bryant and 17th, well away from the live demo pin at Valencia and 18th.
    dict(lat=37.76330, lng=-122.41060, age=26, reporter="mateo", status="reported",
         note="White van with two flat tires has not moved from this corner in over a week.",
         category="parking", severity="low", already_reported="unknown",
         agency="SFMTA", channel="SF 311 abandoned vehicle report",
         channel_url=VEHICLE["url"], sources=[VEHICLE, MTA]),
    dict(lat=37.75234, lng=-122.42062, age=50, reporter="mateo", status="acknowledged",
         note="Deep pothole in the right lane, bikes are swerving around it.",
         category="road_pothole", severity="high", already_reported="yes",
         agency="San Francisco Public Works", channel="SF 311 web form",
         channel_url=POTHOLE["url"], sources=[POTHOLE, PW]),
    dict(lat=37.76503, lng=-122.42194, age=40, reporter="priya", status="acknowledged",
         note="Mattress and two broken chairs dumped on the corner since Friday.",
         category="illegal_dumping", severity="medium", already_reported="yes",
         agency="San Francisco Public Works", channel="SF 311 illegal dumping report",
         channel_url=DUMPING["url"], sources=[DUMPING, PW]),
    dict(lat=37.75824, lng=-122.42393, age=14, reporter="dana", status="routed",
         note="Sidewalk slab lifted by tree roots, hard to pass with a wheelchair.",
         category="sidewalk_accessibility", severity="high", already_reported="unknown",
         agency="San Francisco Public Works", channel="SF 311 web form",
         channel_url=SIDEWALK["url"], sources=[SIDEWALK, PW]),
    dict(lat=37.76500, lng=-122.41966, age=8, reporter="neighbor", status="routed",
         note="Bus shelter glass panel shattered, glass on the bench.",
         category="transit_stop", severity="medium", already_reported="unknown",
         agency="SFMTA", channel="SFMTA customer service",
         channel_url=MTA["url"], sources=[MTA, SF311]),
    dict(lat=37.75540, lng=-122.41296, age=96, reporter="priya", status="resolved",
         note="Graffiti tags across the whole roll up door of the corner shop.",
         category="graffiti", severity="low", already_reported="unknown",
         agency="San Francisco Public Works", channel="SF 311 graffiti removal",
         channel_url=GRAFFITI["url"], sources=[GRAFFITI, PW]),
    dict(lat=37.75850, lng=-122.40720, age=20, reporter="mateo", status="reported",
         note="Water pooling at the catch basin all week, looks like a blocked drain.",
         category="water_sewer", severity="medium", already_reported="likely",
         agency="San Francisco Public Utilities Commission", channel="SF 311 web form",
         channel_url=WATER["url"], sources=[WATER]),
    dict(lat=37.76030, lng=-122.41280, age=5, reporter="dana", status="routed",
         note="Large tree limb cracked and hanging low over the sidewalk.",
         category="tree", severity="high", already_reported="unknown",
         agency="San Francisco Public Works", channel="SF 311 tree report",
         channel_url=TREE["url"], sources=[TREE, PW]),
    dict(lat=37.76117, lng=-122.42623, age=11, reporter="neighbor", status="needs_human",
         note="Loud generator running overnight behind the building, unclear who owns it.",
         category="noise", severity="low", already_reported="unknown",
         agency="", channel="", channel_url="", sources=[SF311],
         needs_human_reason="Couldn't verify the right agency"),
]


def build() -> list[dict]:
    rows: list[dict] = []
    for i, s in enumerate(SEEDS):
        pin_id = f"seed{i:02d}"
        created = hours_ago(s["age"])
        updated = hours_ago(max(0.5, s["age"] / 3))
        where = address_hint(s["lat"], s["lng"])
        label = s["category"].replace("_", " ")
        done = s["status"] in ("reported", "acknowledged", "resolved")
        pin = Pin(
            id=pin_id, created_at=created, updated_at=updated,
            lat=s["lat"], lng=s["lng"], address_hint=where,
            note=s["note"], category=s["category"], severity=s["severity"],
            agency=s["agency"], channel=s["channel"], channel_url=s["channel_url"],
            already_reported=s["already_reported"], status=s["status"], sources=s["sources"],
            draft_id=f"draft-{pin_id}" if done else "",
            reporter=s["reporter"], seed=True,
            summary=f"{label.capitalize()} reported at {where}.",
            needs_human_reason=s.get("needs_human_reason", ""),
            draft_subject=f"[PIN-{pin_id}] {label.capitalize()} at {where}",
            draft_body=f"Hello,\n\nA neighbor reported the following at {where}:\n\n"
                       f"{s['note']}\n\nThank you.",
            trace=[{"step": "seed", "tool": "seed-script", "ms": 0, "ok": True,
                    "detail": "pre-warmed demo pin"}],
        )
        if s["status"] in ("acknowledged", "resolved"):
            pin.updates = [{"at": updated, "kind": "agency_reply",
                            "from": "SF 311 Customer Service",
                            "text": f"Service request opened for [PIN-{pin_id}]."}]
        rows.append(pin.model_dump())
    return rows


if __name__ == "__main__":
    rows = build()
    blob = json.dumps(rows, indent=2, ensure_ascii=False)
    config.SEED_PATH.write_text(blob)
    config.PINS_PATH.write_text(blob)
    print(f"wrote {len(rows)} seeded pins to {config.SEED_PATH} and {config.PINS_PATH}")
