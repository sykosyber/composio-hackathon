"""Create (or reuse) the Composio GMAIL_NEW_GMAIL_MESSAGE trigger for the demo user, and print its payload schema.

    .venv/Scripts/python scripts/setup_gmail_trigger.py

Gmail triggers poll; we ask for the shortest interval Composio allows so agency replies show up fast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import composio_actions as ca  # noqa: E402

SLUG = "GMAIL_NEW_GMAIL_MESSAGE"


def main() -> int:
    c = ca._composio()
    t = c.triggers.get_type(SLUG)
    print("config schema:", json.dumps(getattr(t, "config", None), indent=1)[:1500])
    print("payload schema keys:", list((getattr(t, "payload", None) or {}).get("properties", {}).keys()))
    active = c.triggers.list_active(trigger_names=[SLUG])
    items = getattr(active, "items", []) or []
    if items:
        print("already active:", [getattr(i, "id", i) for i in items])
        return 0
    cfg = {"interval": 1, "labelIds": "INBOX", "userId": "me"}
    props = ((getattr(t, "config", None) or {}).get("properties") or {})
    cfg = {k: v for k, v in cfg.items() if k in props} or None
    res = c.triggers.create(SLUG, user_id=ca.COMPOSIO_USER_ID, trigger_config=cfg)
    print("created trigger:", getattr(res, "trigger_id", res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
