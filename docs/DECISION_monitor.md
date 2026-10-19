# Decision: cut the Parallel Monitor from the demo

Date: 2026-10-19, ~1:45 PM PT, 60 minutes to code freeze.
Decision: **cut it, keep the code.** This reverses my verbal position 20 minutes ago.

## What changed my mind

I argued earlier that the Monitor was "about 2 minutes of work" and worth attempting. I had
not checked two things. Both are disqualifying on their own.

**1. There is no tunnel binary available.** `which cloudflared ngrok` returns nothing. The
Monitor only delivers through a webhook to a publicly reachable URL, so making it fire means
installing and authenticating a tunnel first. That is not 2 minutes, and it is 2 minutes I
would be spending on the install, not on the feature.

**2. A monitor only reports NEW activity after it is created.** From the Parallel docs, and
noted in our own earlier code: a monitor runs once at creation and then on its schedule, and
it only tracks updates it has not seen before. Our frequency is `1d`.

Point 2 is the real killer, and it is a product problem rather than a plumbing one. Even with
a working tunnel, the most likely outcome on stage is a monitor that is created successfully
and then **reports nothing**, because nothing new has happened on the public web about a
streetlight at Valencia and 18th in the 90 seconds since we pinned it. I would be adding a
live network dependency to buy a panel that correctly says "no updates yet."

That is the worst trade in a demo: real risk, no visible payoff.

## What we lose, honestly

Parallel's sponsor surface drops from three features to two: Search for the agency lookup and
Search for the duplicate check. We lose the "ongoing watch" story as a live artifact.

I think this is survivable because Parallel is still genuinely load-bearing rather than
decorative. The no-source-no-claim guardrail is wired directly to Parallel's results: if
Search returns nothing citable, the pin goes to `needs_human` and the UI says we could not
verify the agency. That is a stronger demonstration of Parallel mattering than a monitor
panel showing zero events. Search is doing work the product cannot function without.

## What we keep

All of the Monitor code stays in the repo and stays honest:

- `research.create_monitor()` guards on `PARALLEL_MONITOR_WEBHOOK_URL` and returns `""`
  when it is unset, so the pipeline records `watch: skipped, no webhook url configured`
  in the agent trace rather than failing.
- `POST /webhooks/parallel` is implemented and covered by the smoke suite, which posts a
  synthetic `monitor.event.detected` payload and asserts it attaches to the right pin.
- `research.monitor_event_text()` parses the real payload shape.

So the capability is built and tested, it is just not switched on. If a judge asks, the
truthful answer is: the integration is written and covered by tests, we did not enable it
because a daily-frequency monitor has nothing new to report inside a 3 minute demo, and we
would rather show two Parallel calls that are doing real work than three where one is empty.

## Cut order, revisited

The original cut order was Monitor, then the reply trigger, then the Sheet mirror. The reply
trigger is no longer a candidate: it has been replaced by an 8 second Gmail poller that works
and is more reliable on stage than the upstream trigger, which polls and can lag minutes. So
the remaining cut order if we slip further is: Sheet mirror last, and nothing before it.

## Reversal condition

If a tunnel turns out to be already running on the demo machine, this takes about 5 minutes
to switch on, and the only change is setting `PARALLEL_MONITOR_WEBHOOK_URL`. Even then I
would not put it in the 3 minute script. It belongs in the "what runs after the demo" slide.
