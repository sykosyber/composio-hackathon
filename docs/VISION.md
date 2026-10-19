# Altruistic Agent: the wider vision

Status: design only. Nothing in this document is built. The shipped product is pillar 0, the
neighborhood pin and route agent. This file describes where it goes next and, just as
importantly, what we deliberately will not do.

## The thesis

Civic participation fails for the same four reasons across every domain:

1. **Information overload.** The facts exist but are scattered, stale, and badly organized.
2. **Time cost.** The first step is expensive enough that most people never take it.
3. **Low trust.** Fear of scams, partisan manipulation, or wasted effort.
4. **Isolation.** People act alone when the thing that sustains participation is other people.

So the agent has exactly two jobs:

- **Lower the cost of the first step.**
- **Connect people to each other.**

It does not replace human participation. A system that donates for you, gardens for you, or
votes for you has solved the wrong problem. Success is measured in human connections formed,
not tasks the agent completed.

## What is already built, and what it proves

The pin and route agent is pillar 0. It is worth being precise about what generalizes, because
the next pillars should reuse it rather than re-scaffold.

| Already generic | Lives in | Reusable as is |
|---|---|---|
| Deterministic pipeline with timed, traced steps | `app/pipeline.py`, `app/trace.py` | Yes. The step list changes, the engine does not. |
| Cited research with a no-source-no-claim gate | `app/research.py`, `app/guardrails.py` | Yes. This is the trust mechanism for all pillars. |
| Hash-keyed cache with a demo mode | `app/cache.py` | Yes |
| Validated LLM output with a rule-based fallback | `app/llm.py` | Yes |
| Composio actions by verified slug | `app/actions.py` | Yes. Drafts, ledger rows, channel posts recur everywhere. |
| Local-first store, external systems as mirrors | `app/store.py` | Yes |
| Privacy scrubbing before anything is shared | `app/guardrails.py` | Yes |

| Currently 311-specific | Lives in | Needs generalizing |
|---|---|---|
| The 11 issue categories | `app/models.py` | Becomes one vocabulary among several |
| Per-category search queries | `app/research.py` `CATEGORY_QUERIES` | Becomes a per-domain query pack |
| The routing card shape | `app/models.py` `RoutingCard` | Becomes one card type among several |
| SF intersections and neighborhoods | `app/geo.py` | Needs a real geocoder beyond the demo city |

The honest summary: roughly two thirds of the code is already a general civic substrate that
happens to have one domain plugged into it. That is the thing worth building on.

## The shared substrate

One **civic profile** feeding a **local knowledge graph**, so the agent can answer a single
question well: *here is one small thing you can do this week.*

```
civic profile  (values, location, time available, money available, skills, languages)
      |
      v
local knowledge graph
  nodes:  orgs, gardens, races, pins, people, needs, events
  edges:  serves, needs, located-near, decided-by, member-of, surplus-to
      |
      +--> pillar 0  neighborhood pins      (built)
      +--> pillar 1  charity allocation     (design)
      +--> pillar 2  community gardening    (design)
      +--> pillar 3  local elections        (design, deliberately narrow)
```

The profile stays local and minimal. Giving, location, and civic data are among the most
sensitive categories of personal information a person has. The profile is a local file the
user can read and delete, not a server-side record.

## Pillar 1: charity allocation

**Barriers:** choice paralysis, trust gaps, mismatch between small gifts and felt impact,
local groups invisible next to national brands.

**Individual**
- Values interview that turns "I care about X" into a written giving plan with a budget split
- Vetting assistant: registration status, financials, red flags, before any gift
- Impact receipts: translate published reports into "what your $50 likely did"
- Time-giving: match skills and schedule to volunteer openings, for people with little money

**Community**
- Giving circles: the agent runs logistics (proposals, voting, tracking) so neighbors decide together
- Local needs map surfacing small mutual aid groups and food pantries
- Coordination so the quiet needs do not lose to the visible ones

**Maps onto existing code:** this is the pin pipeline with a different card. The vetting step
is `find_agency` pointed at IRS Pub 78, Form 990 data, and state charity registries. The
no-source-no-claim gate becomes: no registration record, no recommendation. The giving plan is
a Google Doc via Composio. The circle vote is a Slack poll.

**New hard guardrail:** the agent never ranks charities by "effectiveness" using its own
judgment. It reports verifiable facts (registration status, program expense ratio, who says
what about them, with citations) and the human allocates. Ranking is a values question wearing
a math costume.

## Pillar 2: community and urban gardening

**Barriers:** plot access and waitlists, unclear land permissions, knowledge gaps, volunteer
burnout, social friction for newcomers.

**Individual**
- Hyperlocal growing coach: planting calendars, pest diagnosis from a photo, watering reminders
- Finds plots, community gardens, and shared-yard arrangements nearby
- Low-commitment entry: "you have 2 hours Saturday, here is a garden that needs help"

**Community**
- Shared task boards and watering rotas that balance load and catch burnout early
- Harvest redistribution: route surplus to food banks and neighbors
- Garden as hub: gardens are where neighbors actually meet, so civic info flows through them
- Grant and permit help for groups trying to secure land

**Maps onto existing code:** the map and pins already exist. A garden is a pin with a
different card and a recurring schedule. Rotas are Google Calendar via Composio. Burnout
detection is a counting problem over the task board, not an LLM problem: if one person has
taken more than half the slots for three weeks, say so.

**This is the bridge.** Gardens are the only pillar where people physically meet. That makes
them the natural distribution point for the others. A garden rota reminder is also the right
place to mention that registration closes Monday.

## Pillar 3: local elections

Research points at information as the main barrier. Municipal voters have less information
than in other elections, and what exists is poorly organized. One New Zealand poll found about
a third of non-voters had no idea who the candidates were.

Sources:
[Cutler and Matthews, CJUR](https://cjur.uwinnipeg.ca/index.php/cjur/article/download/389/182/761),
[Horizon Research poll, NZ local elections](https://www.pressreader.com/new-zealand/the-post-1022/20221111/281543704902631)

**Individual**
- Your ballot explained: every race and measure in plain language, what the office controls,
  sourced candidate statements
- Deadlines and logistics: registration, mail ballot tracking, drop boxes, transit to polling places
- Measure translator: what a bond or ordinance would change, with arguments from each side

**Community**
- Candidate forum summaries and resident question collection
- Nonpartisan turnout support for low-turnout neighborhoods: reminders, rides, multilingual guides
- Year-round link between votes and outcomes, so the next election feels concrete

**Hard guardrail, non-negotiable:** the agent never recommends candidates or positions. It
explains, sources, and presents all sides. **Any candidate matching feature is a serious
liability and erodes the trust the entire system depends on.** This is not a tuning parameter.

Note on history: an earlier version of this repo was a ballot explainer. It is in `legacy/`.
If this pillar is revived, revive the idea, not that code. The current product deliberately
ships only dates and logistics.

## Cross-cutting design principles

- **Strengths-based.** Start from what the person and the neighborhood already have, not deficits.
- **Self-determination.** The agent proposes, the human decides. No nudging toward specific
  charities, gardens, or votes.
- **Relationship over automation.** Measure connections formed, not tasks completed.
- **Equity by default.** Multilingual, low-bandwidth, SMS and voice access. Designed with the
  people least likely to engage, not retrofitted for them.
- **Privacy.** Giving, location, and civic data stay local and minimal.

These are not decoration. Each one kills features that would otherwise be tempting: the
recommendation engine, the engagement streak, the leaderboard, the "neighbors like you also
donated to" row.

## What would have to be true

Honest preconditions. None of this is more than a document until these are addressed.

1. **A real geocoder.** `app/geo.py` is a 16-entry lookup table for one city. Every pillar
   needs real addresses.
2. **Identity and multi-user.** There is one fixed demo user today. Giving circles and rotas
   are inherently multi-user, which means auth, permissions, and a real database.
3. **A durable store.** `data/pins.json` is correct for a demo and wrong for shared community
   data.
4. **Verifiable data sources per pillar.** Charity vetting needs IRS and state registry
   access. Elections need official county feeds. Without those the no-source-no-claim gate
   just refuses everything, which is safe but useless.
5. **Actual community partners.** A garden rota with no garden is a to-do app. This is the
   precondition most likely to be skipped and most likely to sink the project.

## Sequencing

Deliberately ordered by trust earned, not by technical ease.

| Phase | Build | Why this order |
|---|---|---|
| 0 | Pin and route agent | Shipped. Proves the pipeline and the citation gate. |
| 1 | Extract the substrate: domain packs, card types, profile | Pure refactor, no new product surface, makes everything after it cheap |
| 2 | Gardens | Highest connection value, lowest trust risk, and it is the bridge to the others |
| 3 | Charity vetting, facts only, no ranking | Reuses the citation gate directly. High trust risk, so it goes after the engine is proven. |
| 4 | Elections, dates and logistics only | Highest trust risk, narrowest scope, most constrained |

Charity ranking and candidate matching never ship.

## Open questions

1. Is the garden pillar really the bridge, or is that a story we like more than users would?
2. Does a giving circle need real money movement to be useful, or is "decide together, each
   person gives on their own" enough? The second is dramatically simpler and avoids becoming
   a payments company.
3. Who is the first real community partner? Phase 2 should not start without one.
