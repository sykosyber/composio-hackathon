# Liner API: where it fits, and where it does not

Researched 2026-10-19 against the live docs at liner.com/developers. Assessment only, no
code written, nothing added to `requirements.txt`. This is a post-hackathon question.

## What Liner actually offers

Four product lines, flat rate per call rather than per token.

| API | Endpoint | Price / 1K | Returns |
|---|---|---|---|
| Web Search | `POST /api/v1/tools/search/web` | **$1** | ranked results: `title, url, hostname, description, date`, up to 20 |
| Scholar Search | `POST /api/v1/tools/search/scholar` | **$0.30** | same plus `citationCount, authors, journal` |
| Quick Answer Agent | `POST /api/v1/agents/quick-answer` | $3 | ~200 char answer, up to 3 references, SSE or `stream:false` |
| Search Agent | `POST /api/v1/agents/search` | $20 | iterative web/academic search, answer with citations |
| Deep Research Agent | `POST /api/v1/agents/deep-research` | $200 | long-form report with source citations |

Raw HTTP with an `x-api-key` header. No Python SDK, which for us is a plus: it is four lines
of `httpx` and no new dependency to vendor.

Relevant request options on Web Search: `date_range` (`past_day` through `past_year`),
`country_code`, `lang`, `max_results`.

## The honest fit assessment

**Liner Web Search and Parallel Search solve the same problem for us.** Both return ranked
URLs with snippets, which is exactly what the no-source-no-claim guardrail consumes. So the
first question is not "where does Liner fit" but "does it replace Parallel, sit alongside
it, or neither."

For this project the answer is **neither, for now**, and then **alongside, for two specific
things Parallel does not do well.**

### Why it does not replace Parallel

Parallel is a required sponsor technology. Swapping it out is not on the table, and I would
not recommend it even if it were: our Search integration works, is cached, and is wired to
the guardrail. Replacing a working citation source an hour before code freeze would be
reckless, and post-hackathon the switching cost buys nothing we do not already have.

Liner's pricing page advertises Web Search at $1/1K against "Parallel Base $4/1K." That is a
real four-fold difference at volume, but at our volume it is the difference between cents and
cents. Cost is not the deciding factor here, capability is.

### Where Liner genuinely adds something

**1. Scholar Search for the gardening pillar.** The strongest fit, and it is not close. At
$0.30 per 1,000 calls it is the cheapest thing in the entire stack, and it returns
`citationCount, authors, journal`. The gardening pillar needs exactly this: what grows here,
in what soil, when to plant, how to identify a pest. That is horticultural and extension
science literature, not general web content. General web search on "why are my tomato leaves
curling" returns content farms. Scholar search returns papers with citation counts we can
threshold on.

This matters because of our own guardrail. "No source, no claim" currently means a `.gov`
domain. For growing advice there is no equivalent official domain, and a citation count plus
a journal name is a defensible substitute signal. Liner gives us that for almost nothing.

**2. `date_range` for the already-reported check.** Our duplicate check currently asks
Parallel whether an issue near a location has been reported recently, and "recently" is a
word in a prompt. Liner takes `date_range: "past_week"` as a parameter. For a dedupe check,
recency is the entire question, and a hard filter beats asking a model to respect a date
expressed in prose.

**3. Scholar Search for charity vetting, with a serious caveat.** Academic literature on
nonprofit effectiveness exists, and `citationCount` is a real quality signal. The caveat:
our charity guardrail says the agent reports verifiable facts and never ranks by
effectiveness. Introducing an API that surfaces effectiveness research is exactly the kind of
thing that quietly becomes a ranking feature. If we use Scholar here it is for context a
human reads, never as an input to an ordering. I would want that written into the pack
before any code is merged.

### Where it does not fit

**The Agent APIs are the wrong shape for us.** Quick Answer returns a ~200 character answer
with up to 3 references. Our pipeline already has an open-weight model doing synthesis, and
the architecture depends on us controlling that step: we validate the JSON with Pydantic, we
strip invented citations with `enforce_sources`, we fall back to rules on failure. An API
that returns a pre-written answer removes that control and puts a second, unvalidated model
in the loop. Deep Research at $200/1K is for a different product entirely.

The retrieval-only endpoints are the right fit precisely because they do not generate. The
docs say so themselves: "maximum control with your own LLM or RAG pipeline."

## How it would slot into the substrate

The domain pack work on `vision/civic-substrate` already created the seam. A pack declares
its research queries; it does not yet declare its *provider*. The natural extension is one
more field:

```python
class DomainPack(Protocol):
    search_provider: str   # "parallel" | "liner_web" | "liner_scholar"
```

`research._search()` dispatches on it and normalizes both into our existing
`{title, url, excerpt}` shape. Liner's `description` maps to `excerpt`, everything else maps
one to one. Nothing downstream changes, because the guardrail and the LLM prompt only ever
see the normalized shape.

Estimated work: about half a day, most of it the normalizer and its tests, not the HTTP call.

## Recommendation

**Do not touch this before the demo.** It is ~1:50 PM, freeze is 2:45. This adds a network
dependency and an API key to a pipeline that currently works. There is no version of this
that improves today's three minutes.

**Post-hackathon, adopt it narrowly:**

1. Liner Scholar Search as the research provider for the gardening pack. Clear win, cheapest
   call in the stack, and it answers a verification problem we otherwise have no answer for.
2. Liner Web Search with `date_range` for the duplicate check, as an A/B against Parallel
   rather than a replacement.
3. Keep Parallel for agency routing. It works, it is integrated, the relationship is real.
4. Skip the Agent APIs entirely. They duplicate a step we deliberately own.

**Open question for Mateo:** the Scholar-for-charity-vetting idea is the one I am least sure
about. It is genuinely useful and it sits one small step from the ranking behavior we
promised never to build. Better to decide that deliberately than to discover we drifted into
it.

**Unverified:** I could not confirm whether Liner offers free trial credits or what the
rate limits are. The pricing page describes a prepaid credit system and links a separate
rate limits page I did not read. Worth checking before committing to it.
