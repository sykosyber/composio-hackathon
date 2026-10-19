# 3-minute demo: Your Ballot, Explained

**Demo county:** Contra Costa County, CA, for Walnut Creek voters.
**Official source on screen:** https://www.contracostavote.gov/election/november-3-2026-general-election/
**Measures:** https://www.contracostavote.gov/m9012-en-2/ (T) · https://www.contracostavote.gov/m9013-en/ (U)

**Setup on screen:** browser tab 1 is the Run button (`python -m src.trigger` → http://127.0.0.1:8000). Tab 2 is the official county page. Tab 3 is the Google Doc, tab 4 is Google Calendar, tab 5 is Gmail Drafts. Keep a terminal ready for the `run_demo.py` backup and the video in case Wi-Fi dies.

| Time | Say / do |
|---|---|
| **0:00 Hook** | "Today, October 19th, is the last day to register to vote online in California. Election Day is 15 days out. Who here knows who's running for their water board? Or what their city treasurer actually does?" |
| **0:20 Problem** | "In local races, the number one reason non-voters give is they couldn't find information on candidates or what the office does. The information exists. It's buried in PDFs on county sites." |
| **0:40 Live run** | Show the county ballot email landing in the test inbox ("Composio watches Gmail"). Click **Run**. Narrate the stages as they print: *Extract* finds Walnut Creek and pulls the official county page with Parallel Extract. *Research* fans out one Parallel Task per race; Measure T runs live and the rest come from cache. Then open the **Doc** (every line has a citation link), then **Calendar** (registration today, early voting Oct 30 to Nov 2 at 111 N Wiget Ln, Election Day 7 to 8), then **Gmail Drafts** (the invite is a draft; "I hit send, not the agent"). |
| **2:00 Trust moment** | Point at the GUARDRAIL lines: "Watch this. I planted a biased sentence, 'honestly, this is a no-brainer', and the guardrail redacted it. A field with zero citations got dropped. And for Measure U, the county says *no argument against was filed*. Instead of inventing an opposing view, the guide says exactly that." |
| **2:30 Sponsors** | "Composio is the eyes and hands: Gmail trigger, Docs, Calendar, the draft. Parallel is the cited research, and with Monitor it re-checks every race daily and DMs me on Slack when something changes. Cline wrote most of this in three hours." |
| **2:45 Vision** | "One person's explainer becomes a neighborhood guide. Same pipeline next for charity vetting and community gardens. It never tells you how to vote. It makes the first step cheap." |

**If something breaks:** `python scripts/run_demo.py` runs entirely from cache, then play the backup video. Never run every contest live on stage, because Task latency can be minutes.
