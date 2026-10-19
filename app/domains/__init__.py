"""Domain pack registry.

Adding a civic pillar should mean adding one module here and nothing else. If a new pack
requires changes inside `app/`, the seam is in the wrong place.
"""
from __future__ import annotations

from .base import ActionSpec, DomainPack, match_rules
from .civic_311 import PACK as CIVIC_311
from .garden import PACK as GARDEN

DEFAULT_DOMAIN = CIVIC_311.slug

_PACKS: dict[str, DomainPack] = {
    CIVIC_311.slug: CIVIC_311,
    GARDEN.slug: GARDEN,
}


def get(slug: str | None = None) -> DomainPack:
    """Return a pack by slug, falling back to the default domain."""
    return _PACKS.get(slug or DEFAULT_DOMAIN, _PACKS[DEFAULT_DOMAIN])


def all_slugs() -> tuple[str, ...]:
    return tuple(_PACKS)


def all_categories() -> tuple[str, ...]:
    """Every category across every pack, for validation at the storage boundary."""
    seen: list[str] = []
    for pack in _PACKS.values():
        for category in pack.categories:
            if category not in seen:
                seen.append(category)
    return tuple(seen)


__all__ = ["ActionSpec", "DomainPack", "match_rules", "get", "all_slugs",
           "all_categories", "DEFAULT_DOMAIN", "CIVIC_311", "GARDEN"]
