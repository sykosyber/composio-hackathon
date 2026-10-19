# Phase 1: extract the civic substrate

Status: planned, not built. Do not start before the hackathon demo is done.

This is a pure refactor. No new product surface, no new user-visible behavior. The point is
to make pillars 2 to 4 cheap to add, and to prove it by moving the existing 311 pillar onto
the new seams without changing what it does.

## Done when

1. The 311 pillar is expressed as a **domain pack** and nothing in `app/` imports anything
   311-specific.
2. `scripts/smoke.py` passes all 29 checks unchanged. That is the regression test for this
   whole refactor.
3. A second, deliberately trivial domain pack exists (a stub garden pack with two categories
   and no real research) and the pipeline runs it end to end without a single `if domain ==`
   branch.

If step 3 requires special-casing, the seam is in the wrong place and the refactor failed.

## The seam

Four things vary per domain. Everything else is shared.

```python
# app/domains/base.py
class DomainPack(Protocol):
    slug: str                      # "civic_311", "garden", "charity"
    categories: tuple[str, ...]    # replaces the hardcoded Category literal
    rules: list[tuple[str, str]]   # regex -> category, the LLM-free fallback

    def research_queries(self, category: str) -> tuple[str, list[str]]: ...
    def verify(self, card: Card) -> tuple[bool, str]: ...   # the no-source-no-claim gate
    def actions(self, item: Item) -> list[ActionSpec]: ...  # which Composio calls, in order
```

Mapping from today's code:

| Today | Moves to |
|---|---|
| `models.CATEGORIES`, `Category` | `DomainPack.categories` |
| `llm._RULES` | `DomainPack.rules` |
| `research.CATEGORY_QUERIES`, `agency_query`, `dedupe_query` | `DomainPack.research_queries` |
| `guardrails.verify_card`, `OFFICIAL_HINTS` | `DomainPack.verify` |
| the hardcoded step 6/7/8 block in `pipeline.run` | `DomainPack.actions` |

What explicitly does **not** move, because it is already universal:

- `trace.Tracer`, the timing and the agent trace
- `cache`, the hash-keyed store and `DEMO_MODE`
- `llm._chat`, `_parse`, `_coerce`, the retry and the validation
- `guardrails.scrub`, `is_emergency`, `enforce_sources`
- `actions.execute`, the timeout wrapper and the slug-based execution
- `store`, the local-first JSON source of truth

## Ordering, smallest reversible steps

Each step keeps `scripts/smoke.py` green. Commit after each.

1. **Generalize the item model.** `Pin` becomes `Item` with a `domain` field and a `card`
   dict. Keep a `Pin` alias so nothing breaks. No behavior change.
2. **Extract the query pack.** Move `CATEGORY_QUERIES` and the two query builders into
   `app/domains/civic_311.py`. `research.py` takes a pack as an argument.
3. **Extract the rules and categories.** Same move for `llm._RULES` and `CATEGORIES`.
4. **Extract verification.** `guardrails.verify_card` becomes `pack.verify`. The generic
   parts, `enforce_sources` and `url_is_plausible`, stay in `guardrails`.
5. **Extract the action list.** Steps 6 to 8 of the pipeline become a list of `ActionSpec`
   the pack returns, executed by a generic loop that already has the timeout and tracing.
6. **Add the stub garden pack.** Prove the seam. Delete it afterwards or keep it as a fixture.

## Risks

- **Over-abstracting on one example.** We have exactly one real domain. Designing a general
  plugin system from a sample size of one usually produces the wrong abstraction. Mitigation:
  step 6 exists specifically to get a second example in before the seams harden, and the stub
  is intentionally cheap to throw away.
- **The multi-user problem is not solved by this refactor.** Domain packs do not give us
  auth, permissions, or a shared database. Gardens and giving circles need those. This phase
  makes the domain logic pluggable, nothing more. Do not let it masquerade as progress on
  identity.
- **The card shape may not generalize.** `RoutingCard` has `agency` and `channel_url` because
  routing is a lookup problem. A garden rota is a scheduling problem and a giving plan is an
  allocation problem. Those may not be cards at all. If the second pack fights the card shape,
  that is real signal, not an inconvenience to work around.

## Explicitly out of scope

Auth, a real database, a real geocoder, any new pillar, any UI change. Those are separate
pieces of work with their own risk. This phase touches only the domain seam.
