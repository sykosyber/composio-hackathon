"""The domain seam.

Four things vary between civic domains. Everything else in `app/` is shared infrastructure
and must not know which domain it is running.

A DomainPack supplies:
  categories        the vocabulary of issue types
  rules             regex -> category, the LLM-free classifier fallback
  research_queries  what to ask Parallel, and the cache key that comes with it
  verify            the no-source-no-claim gate, which differs per domain
  actions           which Composio calls to make, in order

Anything that does not vary by domain belongs in `app/`, not here. That includes the
tracer, the cache, the LLM retry and validation, the privacy scrub, the timeout wrapper
and the local-first store.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..models import RoutingCard


@dataclass(frozen=True)
class ActionSpec:
    """One Composio call the pipeline should make for this item.

    The pipeline executes these by verified slug. A domain pack declares intent, it does
    not get to invent tool slugs or bypass the shared timeout and tracing.
    """

    step: str                       # trace label, for example "ledger"
    tool: str                       # trace tool label, for example "composio-sheets"
    kind: str                       # "sheet_append" | "gmail_draft" | "slack_post"
    payload: dict[str, Any] = field(default_factory=dict)
    # Skip this action unless the item passed verification. Drafting a report to an
    # agency we could not verify would violate no source, no claim.
    requires_verified: bool = False


@runtime_checkable
class DomainPack(Protocol):
    """Implemented by each civic domain. See `civic_311.py` for the reference pack."""

    slug: str
    label: str
    categories: tuple[str, ...]
    default_category: str

    def classify(self, note: str) -> str:
        """Rule-based category guess. Must never raise and must never call the network."""
        ...

    def severity(self, note: str) -> str:
        """Rule-based severity guess. Must never raise and must never call the network."""
        ...

    def research_queries(self, category: str) -> tuple[str, list[str]]:
        """Return (objective, search_queries) for the Parallel agency lookup.

        This doubles as the cache key, so it must be a pure function of its arguments.
        Including free text here would give every item its own cache entry and make
        DEMO_MODE useless.
        """
        ...

    def dedupe_queries(self, category: str, where: str) -> tuple[str, list[str]]:
        """Return (objective, search_queries) for the already-known check."""
        ...

    def verify(self, card: RoutingCard) -> tuple[bool, str]:
        """The no-source-no-claim gate. Return (verified, reason_if_not).

        Every domain needs this, but each decides what counts as sufficient evidence.
        311 needs a cited official reporting URL. Charity vetting would need a
        registration record. A garden task needs nothing external at all.
        """
        ...

    def actions(self, item: Any, verified: bool) -> list[ActionSpec]:
        """Which Composio calls to make for this item, in order."""
        ...


def match_rules(note: str, rules: list[tuple[str, str]], default: str) -> str:
    """Shared regex matcher. First match wins, so order the rules deliberately."""
    low = (note or "").lower()
    for pattern, value in rules:
        if re.search(pattern, low):
            return value
    return default
