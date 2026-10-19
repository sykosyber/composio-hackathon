"""TypeSafe Jev: fast typed decisions with calibrated confidence (~100ms per call).

Used where a pipeline needs a decision, not prose:
  triage(note)        -> emergency probability + issue category, before any search
  classify_reply(txt) -> what an agency reply means: acknowledged / resolved / needs_info / rejected

Every call has a short timeout and returns None on failure, so callers fall back to rules.
Results are cached like Parallel and LLM calls, so DEMO_MODE runs are identical.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from . import cache
from .models import CATEGORIES

TIMEOUT_S = float(os.getenv("TYPESAFE_TIMEOUT", "5"))
EMERGENCY_THRESHOLD = float(os.getenv("JEV_EMERGENCY_THRESHOLD", "0.5"))
CATEGORY_MIN_CONFIDENCE = float(os.getenv("JEV_CATEGORY_MIN_CONFIDENCE", "0.6"))
REPLY_MIN_CONFIDENCE = float(os.getenv("JEV_REPLY_MIN_CONFIDENCE", "0.7"))

EMERGENCY_Q = ("Does this describe immediate danger to people (fire, gas leak, injury, medical emergency, "
               "crime in progress) that needs 911 now?")
REPLY_LABELS = {
    "acknowledged": "Request received, opened, or a crew assigned, but not fixed yet",
    "resolved": "The issue has been fixed, completed, or closed",
    "needs_info": "They ask the reporter for more information or a different channel",
    "rejected": "Wrong agency, duplicate, or they will not handle it",
}

_client = None


def available() -> bool:
    return bool(os.getenv("TYPESAFE_API_KEY", "").strip())


def _get_client():
    global _client
    if _client is None:
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        _client = TypeSafeClient(api_key=os.getenv("TYPESAFE_API_KEY", "").strip(),
                                 timeout=TIMEOUT_S, retry=RetryPolicy(max_retries=0))
    return _client


@dataclass
class Triage:
    emergency_p: float
    category: str
    category_confidence: float


@dataclass
class ReplyVerdict:
    label: str
    confidence: float


def triage(note: str) -> Optional[Triage]:
    """Emergency probability and category for a pin note, in one Jev call."""
    if not available():
        return None
    payload = {"note": note, "v": 1}
    hit = cache.get("jev_triage", payload)
    if hit is not None:
        return Triage(**hit)
    try:
        from typesafe_sdk import Choice, Noul

        r = _get_client().system_one(state=note, questions={
            "emergency": Noul(instructions=EMERGENCY_Q),
            "category": Choice(instructions="Which kind of neighborhood issue is this?",
                               criteria={c: None for c in CATEGORIES}),
        })
        out = Triage(emergency_p=float(r.nouls["emergency"].noul), category=r.choices["category"].choice,
                     category_confidence=float(r.choices["category"].confidence))
    except Exception as exc:  # never fail the pipeline on Jev
        print(f"[jev] triage failed: {exc!r}")
        return None
    cache.put("jev_triage", payload, out.__dict__)
    return out


def classify_reply(text: str) -> Optional[ReplyVerdict]:
    """What an agency's email reply says about the issue."""
    if not available() or not text.strip():
        return None
    payload = {"reply": text[:2000], "v": 1}
    hit = cache.get("jev_reply", payload)
    if hit is not None:
        return ReplyVerdict(**hit)
    try:
        from typesafe_sdk import Choice

        r = _get_client().system_one(state=text[:2000], questions={
            "reply": Choice(instructions="What does this agency email say about the reported neighborhood issue?",
                            criteria=REPLY_LABELS),
        })
        out = ReplyVerdict(label=r.choices["reply"].choice, confidence=float(r.choices["reply"].confidence))
    except Exception as exc:
        print(f"[jev] reply classification failed: {exc!r}")
        return None
    cache.put("jev_reply", payload, out.__dict__)
    return out
