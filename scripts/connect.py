#!/usr/bin/env python3
"""One time setup. Connect Gmail, Google Sheets and Slack, and register the Gmail trigger.

    .venv/bin/python scripts/connect.py
    .venv/bin/python scripts/connect.py --trigger https://<tunnel>/webhooks/composio

Composio SDK 0.28 surface, verified against the installed package:
    Composio(api_key=...).sessions.create(user_id=..., toolkits=[...])
    session.authorize(toolkit) -> request with .redirect_url and .wait_for_connection()
Gmail is a polling trigger, so replies can take minutes to arrive. The demo uses
POST /demo/simulate_reply/{id} on stage and the real trigger when it lands.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from composio import Composio  # noqa: E402

from app import actions, config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", metavar="WEBHOOK_URL",
                        help="public URL ending in /webhooks/composio")
    parser.add_argument("--toolkits", default=",".join(actions.TOOLKITS))
    args = parser.parse_args()

    if not config.COMPOSIO_API_KEY:
        print("Set COMPOSIO_API_KEY in .env first.")
        return 1

    toolkits = [t.strip() for t in args.toolkits.split(",") if t.strip()]
    composio = Composio(api_key=config.COMPOSIO_API_KEY)
    session = composio.sessions.create(user_id=config.COMPOSIO_USER_ID, toolkits=toolkits)

    accounts = {}
    for toolkit in toolkits:
        request = session.authorize(toolkit)
        print(f"Connect {toolkit}: {request.redirect_url}", flush=True)
        accounts[toolkit] = request.wait_for_connection(timeout=1200)
        print(f"  connected {toolkit}: {accounts[toolkit].id}")

    if args.trigger:
        subscription = composio.triggers.set_webhook_subscription(
            webhook_url=args.trigger, version="V3")
        trigger = composio.triggers.create(
            slug="GMAIL_NEW_GMAIL_MESSAGE",
            user_id=config.COMPOSIO_USER_ID,
            connected_account_id=accounts["gmail"].id,
            trigger_config={},
        )
        print("\nAdd these to .env:")
        print(f"COMPOSIO_TRIGGER_ID={trigger.trigger_id}")
        print(f"COMPOSIO_WEBHOOK_SECRET={subscription['secret']}")
        print("Gmail is a polling trigger, so a reply can take a few minutes to arrive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
