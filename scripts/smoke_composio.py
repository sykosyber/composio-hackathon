"""Smoke test for app/composio_actions.py against a fake pin. Creates a real Sheet row, a Gmail DRAFT, a Slack post.

    .venv/Scripts/python scripts/smoke_composio.py            # all four actions
    .venv/Scripts/python scripts/smoke_composio.py --check    # only verify key, connected accounts, and slugs

Never sends email: gmail_draft creates a draft only.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")

from app import composio_actions as ca  # noqa: E402
from app.models import Pin, RoutingCard, Source  # noqa: E402


def check() -> bool:
    ok = True
    print("transport:", "MCP (consumer key)" if ca.USE_MCP else "SDK (project key)")
    try:
        if ca.USE_MCP:
            out = ca._mcp_call("COMPOSIO_MANAGE_CONNECTIONS",
                               {"toolkits": [{"name": n, "action": "list"} for n in ("gmail", "googlesheets", "slack")]})
            have = {k: v.get("status") for k, v in ((out.get("data") or {}).get("results") or {}).items()}
            schemas = ca._mcp_call("COMPOSIO_GET_TOOL_SCHEMAS", {"tool_slugs": list(ca.SLUGS.values())})
            missing = (schemas.get("data") or {}).get("not_found") or []
        else:
            c = ca._composio()
            have = {a.toolkit.slug.lower(): a.status.lower() for a in c.connected_accounts.list(user_ids=[ca.COMPOSIO_USER_ID]).items}
            missing = []
            for slug in ca.SLUGS.values():
                try:
                    c.tools.get_raw_composio_tool_by_slug(slug)
                except Exception:  # noqa: BLE001
                    missing.append(slug)
    except Exception as e:  # noqa: BLE001
        print("check failed:", e)
        return False
    print("connected accounts:", have)
    for tk in ("gmail", "googlesheets", "slack"):
        if str(have.get(tk)).lower() != "active":
            print(f"  MISSING: {tk} is not connected")
            ok = False
    for name, slug in ca.SLUGS.items():
        print(f"  slug {'MISSING' if slug in missing else 'ok'}: {name} -> {slug}")
    ok = ok and not missing
    print("env:", {k: bool(v) for k, v in {"GOOGLE_SHEET_ID": ca.SHEET_ID, "SLACK_CHANNEL": ca.SLACK_CHANNEL,
                                           "AGENCY_DRAFT_TO": ca.DRAFT_TO}.items()})
    return ok


def fake_pin() -> Pin:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    pid = f"smoke{int(time.time()) % 100000}"
    return Pin(
        id=pid, created_at=now, updated_at=now, lat=37.76147, lng=-122.42183, address_hint="Valencia St and 18th St",
        note="SMOKE TEST: streetlight out at Valencia and 18th. Call me at 415-555-0100.", reporter="smoke",
        status="reported",
        card=RoutingCard(
            category="streetlight", severity="medium", summary="Smoke test pin.", agency="SFPUC (smoke test)",
            channel="SF311", channel_url="https://www.sf.gov/report-problem-streetlight", already_reported="unknown",
            sources=[Source(title="Report a problem with a streetlight | SF.gov", url="https://www.sf.gov/report-problem-streetlight")],
            draft_subject=f"[PIN-{pid}] SMOKE TEST streetlight", draft_body="Hello,\n\nThis is a smoke test draft. Do not send.\n"),
    )


def main() -> int:
    if not check():
        print("\nCHECK FAILED")
        if "--check" in sys.argv:
            return 1
    if "--check" in sys.argv:
        return 0
    pin = fake_pin()
    results = {}
    for name, fn in (("sheet_upsert", ca.sheet_upsert), ("gmail_draft", ca.gmail_draft), ("slack_post_pin", ca.slack_post_pin)):
        t0 = time.perf_counter()
        out = fn(pin)
        results[name] = out
        print(f"{name:15s} -> {out!r}  ({int((time.perf_counter() - t0) * 1000)}ms)")
    pin.status = "acknowledged"
    results["sheet_update"] = ca.sheet_upsert(pin)
    print(f"{'sheet_update':15s} -> {results['sheet_update']!r}")
    ok = all(v not in (None, False) for v in results.values())
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
