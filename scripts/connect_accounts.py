#!/usr/bin/env python3
"""One-time setup BEFORE kickoff (venue Wi-Fi + OAuth = pain). Needs COMPOSIO_API_KEY.

1. Prints a Connect Link per toolkit; open each and approve with the TEST Google account + Slack.
2. Optionally (--trigger URL) registers the project webhook + creates the GMAIL_NEW_GMAIL_MESSAGE trigger.
   Pattern from https://docs.composio.dev/examples/email-triggered-agent

  python scripts/connect_accounts.py
  python scripts/connect_accounts.py --trigger https://<tunnel>/webhooks/composio
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from composio import Composio  # noqa: E402

from src import config  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--trigger", metavar="WEBHOOK_URL")
ap.add_argument("--toolkits", default="gmail,googledocs,googlecalendar,slack")
a = ap.parse_args()

composio = Composio(api_key=config.COMPOSIO_API_KEY)
session = composio.create(user_id=config.COMPOSIO_USER_ID, toolkits=a.toolkits.split(","))
accounts = {}
for tk in a.toolkits.split(","):
    req = session.authorize(tk)
    print(f"Connect {tk}: {req.redirect_url}", flush=True)
    accounts[tk] = req.wait_for_connection()
    print(f"  connected {tk}: {accounts[tk].id}")

if a.trigger:
    sub = composio.triggers.set_webhook_subscription(webhook_url=a.trigger, version="V3")
    trig = composio.triggers.create(slug="GMAIL_NEW_GMAIL_MESSAGE", user_id=config.COMPOSIO_USER_ID,
                                    connected_account_id=accounts["gmail"].id, trigger_config={})
    print("Add to .env:")
    print(f"COMPOSIO_TRIGGER_ID={trig.trigger_id}")
    print(f"COMPOSIO_WEBHOOK_SECRET={sub['secret']}")
    print("Reminder: Gmail is a polling trigger (up to ~15 min). Use the Run button on stage.")
