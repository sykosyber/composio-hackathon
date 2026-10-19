# 3 minute demo script

Before you start:

```bash
.venv/bin/python scripts/seed.py
.venv/bin/python scripts/warm_cache.py
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Open `http://localhost:8000`, the Slack channel, the Google Sheet, and Gmail drafts in tabs.
Press **Reset demo** right before you go on.

| Time | Do | Say |
|---|---|---|
| 0:00 | Map with 9 seeded pins in the Mission. | "Every pin is something a neighbor noticed. Green is acknowledged, orange needs a human." |
| 0:20 | Click Valencia and 18th, type "Streetlight out at Valencia and 18th, very dark at night." Hit Drop pin. | "One line. That is all the user does." |
| 0:30 | The pin appears instantly as `routing`. | "The map never waits on the network. Local JSON is the source of truth." |
| 0:40 | Routing card fills in. Point at the agency, the channel, the cited links. | "Parallel found who owns this and the real reporting URL, with citations. No source, no claim: if Parallel cannot back it up, we say we could not verify it instead of guessing." |
| 1:05 | Point at the agent trace. | "Every step, every tool, every millisecond. Parallel did the research, Composio did the actions." |
| 1:20 | Switch to the Sheet, then Gmail drafts, then Slack. | "Composio wrote the shared ledger row, prepared the report email, and told the neighborhood. The draft is a draft. The agent has no send button. A human clicks send." |
| 1:50 | Click **Simulate agency reply**. Pin turns green. | "When the agency replies, a Composio Gmail trigger matches the PIN tag in the subject and flips the status. Gmail triggers poll, so on stage I am firing the same code path by hand." |
| 2:10 | Click **Send brief to Slack**. | "Every morning: what is new on your blocks, what moved on your issues, and civic dates. Today is the last day to register online for the November 3 election. Dates and logistics only, never a recommendation." |
| 2:40 | Show the README and the repo. | "Open source, MIT, deterministic pipeline, every external call has a timeout and a fallback. Built with Cline." |

## If something breaks

- Network down: `DEMO_MODE=1` already serves everything from the committed cache. Nothing changes.
- A pin goes `needs_human`: that is the guardrail working. Say so, it is a feature.
- Server died: restart it, then **Reset demo**. Seeded state returns in a second.
