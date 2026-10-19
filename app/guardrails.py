"""Non-negotiable guardrails. Say these out loud in the demo.

1. Emergencies are not routed. Immediate danger skips the pipeline and shows "Call 911 now."
2. No source, no claim. Agency / channel_url without a citation means status needs_human.
3. Privacy. Only the note, coordinates and a reporter display name are stored, and personal
   data is stripped from the note before anything is written to the shared Sheet.
4. Draft, never send. Enforced in app/actions.py: we only ever create Gmail drafts.
5. Civic neutrality. Election content is dates and logistics only, from official sources.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import RoutingCard

EMERGENCY_PATTERNS = (
    r"\bfire\b", r"\bsmoke\b", r"gas leak", r"smell(s|ing)? (of )?gas", r"explosion",
    r"\binjur(y|ed|ies)\b", r"\bbleeding\b", r"unconscious", r"not breathing",
    r"\bassault\b", r"\bgun\b", r"\bshoot(ing|er)\b", r"\bstabb", r"break ?in in progress",
    r"crime in progress", r"\bactive (shooter|threat)\b", r"downed (power )?line",
    r"live wire", r"someone is trapped", r"\bdrowning\b", r"medical emergency",
)
EMERGENCY_MESSAGE = (
    "Call 911 now. This report describes a possible emergency, so the agent did not route it. "
    "After you are safe, drop a follow up pin for any non urgent damage."
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
# Apartment/unit numbers are personal detail; the pin coordinates are enough.
_UNIT = re.compile(r"\b(apt\.?|apartment|unit|suite|ste\.?)\s*#?\s*[\w-]+", re.I)

# channel_url must point at an official or reputable civic domain.
TRUSTED_SUFFIXES = (".gov", ".ca.gov", ".org", ".us", ".com")
OFFICIAL_HINTS = ("sf.gov", "sfgov.org", "311", ".gov", "sfmta.com", "sfpuc", "sfwater.org",
                  "bart.gov", "recpark")


def is_emergency(note: str) -> bool:
    low = note.lower()
    return any(re.search(p, low) for p in EMERGENCY_PATTERNS)


def scrub(text: str) -> str:
    """Strip personal info before anything is stored or mirrored to the Sheet."""
    out = _EMAIL.sub("[email removed]", text or "")
    out = _PHONE.sub("[phone removed]", out)
    out = _SSN.sub("[id removed]", out)
    out = _UNIT.sub("[unit removed]", out)
    return re.sub(r"\s+", " ", out).strip()[:500]


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def url_is_plausible(url: str) -> bool:
    host = _host(url)
    return bool(host) and host.endswith(TRUSTED_SUFFIXES)


def verify_card(card: RoutingCard, domain: str | None = None) -> tuple[bool, str]:
    """No source, no claim. Returns (verified, reason_if_not).

    Each domain decides what counts as sufficient evidence, so the gate itself lives in
    the domain pack. What does not vary, and therefore stays here, is `enforce_sources`:
    a citation the model invented is never acceptable in any domain.
    """
    from . import domains

    return domains.get(domain).verify(card)


def enforce_sources(card: RoutingCard, allowed_urls: set[str]) -> RoutingCard:
    """Drop any citation the model invented. Only URLs Parallel actually returned survive."""
    card.sources = [s for s in card.sources if s.url in allowed_urls][:5]
    if card.channel_url and card.channel_url not in allowed_urls:
        kept = {_host(u) for u in allowed_urls}
        if _host(card.channel_url) not in kept:
            card.channel_url = ""
    return card
