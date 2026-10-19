"""Morning brief: what changed on your blocks, plus civic dates.

build_brief(pins) -> {"markdown": str, "items": [...]}. Pure function, no network, so GET /brief never stalls.
Civic content is dates and logistics only, from official sources. It never recommends candidates or positions.
"""
from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.models import Pin

try:
    TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # Windows without tzdata: PDT is correct through Nov 1, 2026
    TZ = timezone(timedelta(hours=-7), "PDT")
HOME = (float(os.getenv("BRIEF_HOME_LAT", "37.7599")), float(os.getenv("BRIEF_HOME_LNG", "-122.4183")))
RADIUS_M = float(os.getenv("BRIEF_RADIUS_M", "1500"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")

ELECTION_DAY = date(2026, 11, 3)
ONLINE_REG_DEADLINE = date(2026, 10, 19)
SRC_ELECTION = "https://www.sos.ca.gov/elections/upcoming-elections/general-election-november-3-2026"
SRC_REGISTER = "https://registertovote.ca.gov/"
SRC_SAME_DAY = "https://www.sos.ca.gov/elections/voter-registration/same-day-reg"

OPEN = {"routing", "routed", "reported", "acknowledged", "needs_human"}
LABEL = {"routed": "agency found", "reported": "draft ready", "acknowledged": "agency replied",
         "resolved": "resolved", "needs_human": "needs a human", "routing": "routing", "emergency": "emergency"}


def _ts(iso: str | None) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=TZ)
    except Exception:
        return None


def _dist_m(lat: float, lng: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (HOME[0], HOME[1], lat, lng))
    a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def _where(p: Pin) -> str:
    return p.address_hint or f"{p.lat:.4f}, {p.lng:.4f}"


def _cat(p: Pin) -> str:
    cat = p.card.category.replace("_", " ") if p.card else "other"
    return "issue" if cat == "other" else cat


def civic_items(today: date) -> list[dict[str, Any]]:
    days = (ELECTION_DAY - today).days
    items = []
    if days >= 0:
        items.append({"type": "civic", "text": f"California general election is Tuesday, Nov 3, 2026"
                      f"{' (today)' if days == 0 else f' ({days} days away)'}.", "url": SRC_ELECTION})
    if today < ONLINE_REG_DEADLINE:
        items.append({"type": "civic", "text": "Last day to register to vote online is Monday, Oct 19.", "url": SRC_REGISTER})
    elif today == ONLINE_REG_DEADLINE:
        items.append({"type": "civic", "text": "Today, Oct 19, is the last day to register to vote online.", "url": SRC_REGISTER})
    if today <= ELECTION_DAY:
        items.append({"type": "civic", "text": "Missed online registration? Same-day conditional voter registration is "
                      "available at county elections offices and vote centers through Election Day.", "url": SRC_SAME_DAY})
    return items


def build_brief(pins: list[Pin], now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    since = datetime.combine(now.date() - timedelta(days=1), datetime.min.time(), TZ)  # since yesterday 00:00
    near = [p for p in pins if _dist_m(p.lat, p.lng) <= RADIUS_M and p.status != "emergency"]

    def recent(p: Pin, field: str) -> bool:
        t = _ts(getattr(p, field))
        return bool(t and t >= since)

    new = sorted([p for p in near if recent(p, "created_at") and p.status != "needs_human"], key=lambda p: p.created_at, reverse=True)
    new_ids = {p.id for p in new}
    changed = sorted([p for p in near if p.id not in new_ids and recent(p, "updated_at")
                      and p.status in ("acknowledged", "resolved", "reported", "routed")],
                     key=lambda p: p.updated_at, reverse=True)
    help_needed = [p for p in near if p.status == "needs_human"]
    open_count = sum(p.status in OPEN for p in near)
    resolved_count = sum(p.status == "resolved" for p in near)

    items: list[dict[str, Any]] = []
    for p in changed:
        last = p.updates[-1] if p.updates else LABEL.get(p.status, p.status)
        items.append({"type": "status_change", "pin_id": p.id, "status": p.status,
                      "text": f"{_cat(p).capitalize()} at {_where(p)}: {last}"})
    for p in new:
        agency = f" Routed to {p.card.agency}." if p.card and p.card.agency else ""
        items.append({"type": "new_pin", "pin_id": p.id, "status": p.status,
                      "text": f"New {_cat(p)} at {_where(p)}: \"{p.note.rstrip('.')}\".{agency}"})
    for p in help_needed:
        items.append({"type": "needs_human", "pin_id": p.id, "status": p.status,
                      "text": f"{_cat(p).capitalize()} at {_where(p)}: couldn't verify the right agency. Can you help?"})
    civic = civic_items(now.date())
    items += civic

    md = [f"**Good morning, Mission.** Your neighborhood brief for {now.strftime('%A, %b')} {now.day}.",
          f"{open_count} open pins near you, {resolved_count} resolved.", ""]
    if changed:
        md += ["**Updates on your blocks**"] + [f"- {i['text']} {_link_id(i)}" for i in items if i["type"] == "status_change"] + [""]
    if new:
        md += ["**New since yesterday**"] + [f"- {i['text']} {_link_id(i)}" for i in items if i["type"] == "new_pin"] + [""]
    if help_needed:
        md += ["**Needs a neighbor**"] + [f"- {i['text']} {_link_id(i)}" for i in items if i["type"] == "needs_human"] + [""]
    if not (changed or new or help_needed):
        md += ["Quiet night on your blocks. Nothing new since yesterday.", ""]
    md += ["**Civic dates** (nonpartisan, official sources)"] + [f"- {i['text']} [source]({i['url']})" for i in civic]
    return {"markdown": "\n".join(md).strip() + "\n", "items": items, "generated_at": now.isoformat()}


def _link_id(item: dict[str, Any]) -> str:
    return f"[open]({PUBLIC_URL}/?pin={item['pin_id']})"
