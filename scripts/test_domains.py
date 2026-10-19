#!/usr/bin/env python3
"""Prove the domain seam holds.

    .venv/bin/python scripts/test_domains.py

The real assertion of Phase 1: a second domain pack runs through the same pipeline with
no `if domain ==` branch anywhere in `app/`. If this needs a special case to pass, the
abstraction is wrong and should be reworked rather than patched.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import domains, pipeline, store  # noqa: E402
from app.models import Pin, RoutingCard, Source, now_iso  # noqa: E402

passed, failed = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def no_domain_branches() -> None:
    """Static guard: `app/` must never branch on a domain slug."""
    offenders = []
    for path in (Path(__file__).resolve().parent.parent / "app").rglob("*.py"):
        if path.parent.name == "domains":
            continue  # packs are allowed to know their own identity
        text = path.read_text()
        for slug in domains.all_slugs():
            if f'== "{slug}"' in text or f"== '{slug}'" in text:
                offenders.append(f"{path.name} branches on {slug}")
    check("no domain branching inside app/", not offenders, "; ".join(offenders))


def run_pack(slug: str, note: str, expect_category: str) -> None:
    pack = domains.get(slug)
    check(f"[{slug}] pack resolves", pack.slug == slug)
    check(f"[{slug}] classifies note", pack.classify(note) == expect_category,
          f"got {pack.classify(note)}")

    objective, queries = pack.research_queries(expect_category)
    check(f"[{slug}] research query is non empty", bool(objective) and bool(queries))

    # Same objective in, same objective out. The cache key depends on it.
    again, _ = pack.research_queries(expect_category)
    check(f"[{slug}] research query is deterministic", objective == again)

    stamp = now_iso()
    pin_id = f"dom-{slug}"
    store.add(Pin(id=pin_id, created_at=stamp, updated_at=stamp, lat=37.7599,
                  lng=-122.4148, note=note, domain=slug, status="routing"))
    result = pipeline.run(pin_id)
    check(f"[{slug}] pipeline completes", result is not None)
    check(f"[{slug}] reaches a terminal status",
          result is not None and result.status != "routing",
          result.status if result else "none")
    check(f"[{slug}] category is from this pack's vocabulary",
          result is not None and result.category in pack.categories,
          result.category if result else "none")
    check(f"[{slug}] trace was recorded", result is not None and len(result.trace) >= 5)


def main() -> int:
    print("static: seam integrity")
    no_domain_branches()
    check("two packs registered", len(domains.all_slugs()) >= 2, str(domains.all_slugs()))

    print("packs: 311 (reference)")
    run_pack("civic_311", "Streetlight out at Valencia and 18th, very dark at night.", "streetlight")

    print("packs: garden (fixture, deliberately different)")
    run_pack("garden", "The tomato bed needs watering, the soil is bone dry.", "watering")

    print("packs: verification gates differ per domain")
    bare = RoutingCard(agency="Dolores Community Garden")
    ok_garden, _ = domains.get("garden").verify(bare)
    ok_311, reason_311 = domains.get("civic_311").verify(bare)
    check("garden accepts a named garden with no gov citation", ok_garden)
    check("311 rejects the same card for lacking a cited URL", not ok_311, reason_311)

    cited = RoutingCard(
        agency="SFPUC", channel="SF 311", channel_url="https://www.sf.gov/report-problem-streetlight",
        sources=[Source(title="SF", url="https://www.sf.gov/report-problem-streetlight")])
    ok_cited, reason_cited = domains.get("civic_311").verify(cited)
    check("311 accepts a properly cited card", ok_cited, reason_cited)

    print("packs: action lists differ per domain")
    kinds_311 = [a.kind for a in domains.get("civic_311").actions(None, True)]
    kinds_garden = [a.kind for a in domains.get("garden").actions(None, True)]
    check("311 drafts an email", "gmail_draft" in kinds_311)
    check("garden does not email an authority", "gmail_draft" not in kinds_garden)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
