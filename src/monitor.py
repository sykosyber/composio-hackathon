"""Step 5: Parallel Monitor per race -> webhook -> Slack DM. Makes it a "runs every day" personal agent.

Docs (verified 2026-10-19): https://docs.parallel.ai/monitor-api/monitor-quickstart
  client.monitor.create(type="event_stream", frequency="1d", processor="lite",
                        settings={"query": ..., "advanced_settings": {"source_policy": {"include_domains": [...]}}},
                        webhook={"url": ..., "event_types": ["monitor.event.detected"]},
                        metadata={...})            # metadata values must be strings
  Webhook payload: {"type": "monitor.event.detected", "data": {"monitor_id", "event": {"event_group_id"}, "metadata"}}
  Then: client.monitor.events(monitor_id, event_group_id=...) -> .events[].output.content / .basis
  Webhook verification: https://docs.parallel.ai/resources/webhook-setup  (TODO(cline): verify signature)
  Cancel unused monitors after the demo: client.monitor.cancel(monitor_id)
NOTE: monitor runs once immediately at creation, then on schedule. It only tracks NEW updates.
"""
from __future__ import annotations

from . import config

OFFICIAL_DOMAINS = ["contracostavote.gov", "walnut-creek.org", "sos.ca.gov"]


def monitor_query(name: str, city: str | None, county: str) -> str:
    return (f"Official or news updates about the {name} on the November 3, 2026 ballot in "
            f"{city + ', ' if city else ''}{county} County, California: candidate changes, withdrawals, "
            "forums, new official voter-guide information, or deadline changes")


def create_monitors(names: list[str], city: str | None, county: str, webhook_url: str | None = None) -> list[str]:
    from parallel import Parallel

    client = Parallel(api_key=config.PARALLEL_API_KEY)
    ids = []
    for n in names:
        m = client.monitor.create(
            type="event_stream", frequency="1d", processor="lite",
            settings={"query": monitor_query(n, city, county)},
            # Optional, stricter: settings["advanced_settings"] = {"source_policy": {"include_domains": OFFICIAL_DOMAINS}}
            webhook={"url": webhook_url or config.PARALLEL_MONITOR_WEBHOOK_URL, "event_types": ["monitor.event.detected"]},
            metadata={"contest": n[:200]},
        )
        ids.append(m.monitor_id)
    return ids


def handle_webhook(payload: dict) -> str | None:
    """Turn a monitor.event.detected webhook into a Slack DM line. Returns the message (or None)."""
    if payload.get("type") != "monitor.event.detected":
        return None
    from parallel import Parallel

    data = payload["data"]
    client = Parallel(api_key=config.PARALLEL_API_KEY)
    res = client.monitor.events(data["monitor_id"], event_group_id=data["event"]["event_group_id"])
    contest = (data.get("metadata") or {}).get("contest", "a race on your ballot")
    lines = [f"*Ballot update - {contest}*"]
    for ev in res.events:
        out = ev.output
        urls = [c.url for b in (out.basis or []) for c in (b.citations or [])][:2]
        lines.append(f"- {out.content}  " + " ".join(f"<{u}|source>" for u in urls))
    return "\n".join(lines)
