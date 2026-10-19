"""Morning brief: pins near you, status changes on your issues, and civic dates.

Civic neutrality: election content is dates and logistics only, from official sources.
This file never mentions a candidate, a party, or a position.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, store
from .geo import km_between, neighborhood
from .models import BriefItem, Pin

# Default home point for the demo user: Valencia and 20th, in the Mission.
HOME_LAT = float(config.DEMO_CITY and 37.75878)
HOME_LNG = -122.42095
NEAR_KM = 1.2

# Static card. California general election logistics, from official state sources.
CIVIC_DATES: list[dict] = [
    {
        "text": ("Today, October 19, is the last day to register online for the November 3, 2026 "
                 "California general election. After today you can still use same day conditional "
                 "registration in person at your county elections office or any vote center."),
        "url": "https://registertovote.ca.gov/",
    },
    {
        "text": "The California general election is Tuesday, November 3, 2026. Polls are open 7am to 8pm.",
        "url": "https://www.sos.ca.gov/elections/upcoming-elections",
    },
]

ACTIVE = ("routing", "routed", "reported", "needs_human")


def _near(pin: Pin, lat: float, lng: float) -> bool:
    return km_between(lat, lng, pin.lat, pin.lng) <= NEAR_KM


def build(lat: float = HOME_LAT, lng: float = HOME_LNG, reporter: str = "") -> dict:
    pins = store.all_pins()
    nearby = [p for p in pins if _near(p, lat, lng)]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds")

    items: list[BriefItem] = []

    # Emergencies are never digested. They are told to call 911 at the moment they are dropped.
    fresh = [p for p in nearby
             if p.created_at >= cutoff and p.status in ACTIVE and not p.emergency]
    for p in fresh[:5]:
        where = p.address_hint or f"{p.lat:.4f}, {p.lng:.4f}"
        items.append(BriefItem(kind="new_pin", pin_id=p.id, url=p.channel_url,
                               text=f"New {p.category.replace('_', ' ')} pin at {where}: {p.note}"))

    mine = [p for p in nearby if not p.emergency and (not reporter or p.reporter == reporter)]
    for p in mine:
        if p.status in ("acknowledged", "resolved") and p.updated_at >= cutoff:
            where = p.address_hint or f"{p.lat:.4f}, {p.lng:.4f}"
            verb = "was acknowledged by" if p.status == "acknowledged" else "was marked resolved by"
            items.append(BriefItem(kind="status_change", pin_id=p.id, url=p.channel_url,
                                   text=f"Your {p.category.replace('_', ' ')} pin at {where} "
                                        f"{verb} {p.agency or 'the agency'}."))

    for card in CIVIC_DATES:
        items.append(BriefItem(kind="civic_date", text=card["text"], url=card["url"]))

    counts = {
        "nearby_total": len(nearby),
        "open": sum(1 for p in nearby if p.status in ACTIVE),
        "acknowledged": sum(1 for p in nearby if p.status == "acknowledged"),
        "resolved": sum(1 for p in nearby if p.status == "resolved"),
        "needs_human": sum(1 for p in nearby if p.status == "needs_human"),
    }
    area = neighborhood(lat, lng)
    return {
        "area": area,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
        "items": [i.model_dump() for i in items],
        "markdown": to_markdown(area, counts, items),
    }


def to_markdown(area: str, counts: dict, items: list[BriefItem]) -> str:
    lines = [
        f"*Morning brief for {area}*",
        (f"{counts['open']} open, {counts['acknowledged']} acknowledged, "
         f"{counts['resolved']} resolved, {counts['needs_human']} need a human."),
    ]
    new_pins = [i for i in items if i.kind == "new_pin"]
    changes = [i for i in items if i.kind == "status_change"]
    civic = [i for i in items if i.kind == "civic_date"]
    if new_pins:
        lines += ["", "*New on your blocks*"] + [f"- {i.text}" for i in new_pins]
    if changes:
        lines += ["", "*Status changes on your issues*"] + [f"- {i.text}" for i in changes]
    if civic:
        lines += ["", "*Civic dates*"] + [f"- {i.text} <{i.url}|official source>" for i in civic]
    lines += ["", "Drafts are ready for your review. The agent never sends anything on its own."]
    return "\n".join(lines)
