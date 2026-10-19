# Altruistic Agent — Pillar 1: **Your Ballot, Explained**

A personal agent that notices your ballot arrived, researches every race on it **with citations**, strips out anything biased or unsourced, and puts what you need into your Google Doc, your calendar, and a **draft** invite to friends. It never recommends a candidate or a vote.

> Built for the Cline × Composio × Parallel hackathon, Mon Oct 19 2026 (11:00–4:30 PT).
> Composio is the eyes and hands. Parallel is the cited research and the ongoing watch. Cline built it.

**Why:** in local races, non-voters most often say they couldn't find information on the candidates or what the office does ([CJUR, Cutler & Matthews](https://cjur.uwinnipeg.ca/index.php/cjur/article/download/389/182/761); [Horizon Research NZ poll](https://www.pressreader.com/new-zealand/the-post-1022/20221111/281543704902631)). The fix isn't an agent that tells you how to vote. It's one that makes the first step cheap and keeps everything traceable to the official source.

---

## DEMO_SOURCE

**Contra Costa County (Walnut Creek), November 3, 2026 General Election. These are OFFICIAL county pages, fetched 2026-10-19:**

| What | URL |
|---|---|
| Election page (deadlines, early voting, drop boxes, polling places) | https://www.contracostavote.gov/election/november-3-2026-general-election/ |
| Official candidate list (8/14/26) | https://www.contracostavote.gov/wp-content/uploads/8-14-26_candidatelist_summary_final.pdf |
| Measure T (City Treasurer appointive?) | https://www.contracostavote.gov/m9012-en-2/ |
| Measure U (Senior housing rezoning near BART) | https://www.contracostavote.gov/m9013-en/ |
| Positions up for election | https://www.contracostavote.gov/wp-content/uploads/26Nov03_PositionsUpForElection.pdf |

The seed cache `cache/contra_costa_walnut_creek_2026-11-03.json` has 4 real Walnut Creek items:
- **City Council** (vote for 2): Cherise Marie Khaund, Brendan Moran. Two candidates for two seats, so it's uncontested.
- **City Treasurer** (vote for 1): Ronald Cassano, the incumbent and the only candidate.
- **Measure T**: whether the treasurer becomes appointed. Official arguments **for and against** were both filed.
- **Measure U**: senior-housing rezoning of a 2.4-acre site. An argument **for** was filed, and the guide says **no argument against was filed**. The guardrail states that outright and doesn't invent one.

Caveats: the seed is hand-built from those pages in the Parallel result shape, not a live Parallel response. Candidate ballot designations and stated priorities are blank until a live Task run fills them in. The full ballot for a given address also includes state and federal races, props, school board, and Measure W in the Acalanes area. The demo sticks to the city-level items.

Real dates from the county page: **registration deadline is today, 10/19** (same-day conditional registration in person after that). The last day to request a VBM ballot is 10/27. Regional early voting at 111 N Wiget Ln, Walnut Creek runs Oct 30 and Nov 2 from 11 to 6, and Oct 31 from 9 to 3. Election Day is Nov 3, polls 7am to 8pm, and drop boxes close at 8:00pm sharp.

---

## Architecture: a deterministic pipeline with agentic steps inside

In 3.5 hours, reliability beats autonomy, so every step runs in the same order every time. Each step is cached, and models only handle the fuzzy parts.

```
 [0] TRIGGER   Composio GMAIL_NEW_GMAIL_MESSAGE webhook  ──or──  Run button (stage default)
       │       src/trigger.py
 [1] EXTRACT   model reads email → county/city/election          (agentic, JSON-validated)
       │       Parallel Extract → official election page/sample ballot (JS + PDF ok)
       │       model → contest list (schemas/ballot_extraction.schema.json)
       │       src/extract.py
 [2] RESEARCH  Parallel Task, ONE RUN PER CONTEST, concurrent (asyncio)
       │       output_schema = schemas/contest.schema.json | schemas/measure.schema.json
       │       → content + basis[] (per-field citations, reasoning, confidence)
       │       src/research.py   (every result written to cache/)
 [3] GUARDRAIL drop fields with 0 citations · redact recommendation/loaded language ·
       │       measures need both official arguments accounted for (else HELD BACK) ·
       │       optional 2nd model pass flags subtler bias
       │       src/guardrails.py  (deterministic, no keys needed)
 [4] OUTPUTS   Composio session.execute:
       │         GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN  "Your Ballot, Explained" (every claim linked)
       │         GOOGLECALENDAR_CREATE_EVENT          deadlines (send_updates="none")
       │         GMAIL_CREATE_EMAIL_DRAFT             invite friends: DRAFT ONLY, human hits send
       │       src/outputs.py
 [5] MONITOR   Parallel Monitor per race (event_stream, daily) → webhook → Slack DM to yourself
               src/monitor.py + POST /webhooks/parallel
```

**Hard guardrail:** the agent explains, sources, and shows all sides. It never recommends. Nothing goes to another person without a human clicking send.

### What's ready and what's stubbed

| Piece | State |
|---|---|
| `scripts/run_demo.py`: full pipeline from cache, prints every stage | **Ready**, runs with no keys |
| `src/guardrails.py`: citation drop, loaded-language redaction, both-sides rule | **Ready**, deterministic |
| `src/outputs.render_markdown`: the Doc content with linked citations | **Ready**, writes `out/your_ballot_explained.md` |
| `src/trigger.py`: Run button UI at `:8000`, `/run`, webhook routes | **Ready** for Run; webhook routes are written but untested live |
| `schemas/*.json`: Parallel Task output schemas | **Ready**, follow Parallel's rules (all required, `additionalProperties:false`, nullable optional fields, no min/max/format) |
| `src/research.py`: `AsyncParallel.task_run.create/result` | Written against SDK 1.3.5 signatures; **not run with a real key** |
| `src/extract.py`: `client.extract(urls, objective)` + model calls | Written; **not run live**. County→URL map is TODO |
| `src/outputs.py`: Composio `session.execute(...)` calls | Written with slugs/params from Composio toolkit docs; **response parsing (doc URL) is TODO** |
| `src/monitor.py`: `client.monitor.create/events` | Written; webhook signature verification is TODO |
| `scripts/connect_accounts.py`: Connect Links + Gmail trigger | Written from Composio's email-triggered-agent example; needs a key |

Grep `TODO(cline)` for the exact gaps.

---

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate     # Composio needs Python 3.11+
pip install -r requirements.txt
cp .env.example .env                                   # fill keys (see below)

python scripts/run_demo.py                             # cache-only, guardrail demo on
python -m src.trigger                                  # Run button → http://127.0.0.1:8000

# once keys are in:
python scripts/connect_accounts.py                     # OAuth Gmail/Docs/Calendar/Slack BEFORE kickoff
MODE=live python scripts/run_demo.py --live "Measure T"         # 1 contest live, rest cached
MODE=live python scripts/run_demo.py --live "Measure T" --push  # + Doc, Calendar, Gmail DRAFT
```

## Env vars (`.env.example`)

| Var | Needed for | Where |
|---|---|---|
| `COMPOSIO_API_KEY` | Steps 0 and 4 | dashboard.composio.dev → Settings → API keys |
| `COMPOSIO_USER_ID` | session scope | any stable id, default `mateo-demo` |
| `COMPOSIO_TRIGGER_ID`, `COMPOSIO_WEBHOOK_SECRET` | Gmail trigger | printed by `connect_accounts.py --trigger URL` |
| `PARALLEL_API_KEY` | Steps 1, 2, 5 | platform.parallel.ai |
| `PARALLEL_PROCESSOR` | Step 2 | `base` default; `lite` is faster, `core` goes deeper |
| `PARALLEL_MONITOR_WEBHOOK_URL` | Step 5 | public tunnel → `/webhooks/parallel` |
| `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY`, `MODEL` | Step 1 + optional bias pass | whatever open model the event credits cover |
| `SLACK_WEBHOOK_URL` *(optional)* or `SLACK_DM_CHANNEL` | Step 5 alerts | posts to **your own** DM only |
| `DEMO_COUNTY` | cache file | `contra_costa_walnut_creek_2026-11-03` |
| `DEMO_INVITE_TO` | Gmail draft "To" | a test address; it's a draft and never sent |
| `MODE` | `cache` (stage-safe) or `live` | |

## Verified API references (2026-10-19)

- **Parallel**, `pip install parallel-web`, `from parallel import Parallel, AsyncParallel`
  - Task: https://docs.parallel.ai/task-api/task-quickstart · schema rules: https://docs.parallel.ai/task-api/guides/specify-a-task · basis: https://docs.parallel.ai/task-api/guides/access-research-basis
  - Extract (`/v1/extract`): https://docs.parallel.ai/extract/extract-quickstart
  - Monitor: https://docs.parallel.ai/monitor-api/monitor-quickstart
- **Composio**, `pip install composio` (**not** the legacy `composio-core`), `from composio import Composio`
  - Sessions: https://docs.composio.dev/docs/quickstart (`composio.create(user_id=...)`, `session.execute(slug, arguments=...)`, `session.authorize(toolkit)`)
  - Triggers: https://docs.composio.dev/docs/triggers. **Gmail is a polling trigger with up to ~15 min latency**, so the Run button is the stage path.
  - Email-triggered agent example: https://docs.composio.dev/examples/email-triggered-agent
  - Tool slugs: https://docs.composio.dev/toolkits/googledocs, /googlecalendar, /gmail, /slack

---

## Build timeline (today)

| Time (PT) | Do |
|---|---|
| **before 11:45** | Keys in `.env`. Test Gmail account. `scripts/connect_accounts.py` for Gmail/Docs/Calendar/Slack. `python scripts/run_demo.py` works. |
| 11:45–12:30 | Model call + Composio session + one Parallel call end to end (`--live "Measure T"`) |
| 12:30–1:45 | Extract + Task fan-out with schemas. **Cache every result.** Fill in candidate priorities. |
| 1:45–2:30 | `--push`: Doc, Calendar, Gmail draft. Parse the doc URL into the draft. Gmail trigger (nice-to-have). |
| 2:30–2:50 | Guardrail polish + one Monitor → Slack DM |
| 2:50–3:15 | **Freeze code.** README, push to GitHub (open source required), record backup video of `run_demo.py` + Run button |

## 3-minute demo script

See [DEMO.md](DEMO.md).

## Roadmap (one slide)

The same pipeline works for **Pillar 2, charity vetting** (Parallel checks registration and financials, guardrail drops anything uncited) and **Pillar 3, community gardens** (find plots, keep watering rotas in Calendar, Monitor for grant deadlines). One person's explainer can become a neighborhood guide.

## License

MIT
