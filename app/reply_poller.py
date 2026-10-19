"""Agency reply watcher: polls Gmail through Composio for [PIN-<id>] replies.

Composio consumer (ck_) keys have no trigger API, and Composio's Gmail trigger polls with
minutes of lag anyway. So every GMAIL_POLL_S seconds we run GMAIL_FETCH_EMAILS for replies
(not our own drafts or sent mail) and hand each new match to the same acknowledge path the
/webhooks/composio route uses.
"""
from __future__ import annotations

import html
import os
import re
import threading
from typing import Callable

from . import actions, guardrails, store

POLL_S = float(os.getenv("GMAIL_POLL_S", "8"))
QUERY = os.getenv("GMAIL_REPLY_QUERY", "subject:PIN newer_than:2d -in:drafts -in:sent -from:me")
PIN_TAG = re.compile(r"\[PIN-([A-Za-z0-9_-]{1,40})\]", re.I)
QUOTE_HEADER = re.compile(r"\s*(?:On\s.{0,120}?\swrote:|-{2,}\s*Original Message|From:\s.{0,80}?Sent:)", re.I | re.S)
DONE = {"acknowledged", "resolved", "emergency"}

_seen: set[str] = set()
_thread: threading.Thread | None = None


def _reply_text(msg: dict) -> str:
    """The agency's new words only: no quoted history, no HTML entities, no email addresses."""
    preview = msg.get("preview") if isinstance(msg.get("preview"), dict) else {}
    text = html.unescape(str(msg.get("messageText") or preview.get("body") or ""))
    # Gmail previews arrive as one line, so cut at the quote header wherever it appears.
    text = QUOTE_HEADER.split(text, maxsplit=1)[0]
    keep = []
    for line in text.splitlines():
        if line.startswith(">"):
            break
        keep.append(line)
    return guardrails.scrub(" ".join(" ".join(keep).split()))


def poll_once(on_reply: Callable[[str, str, str], dict]) -> list[dict]:
    out = actions.execute("GMAIL_FETCH_EMAILS", {"query": QUERY, "max_results": 10,
                                                 "include_payload": True, "verbose": False, "user_id": "me"})
    if not out.ok:
        return []
    results = []
    for msg in (out.data or {}).get("data", out.data or {}).get("messages") or []:
        mid = msg.get("messageId")
        if not mid or mid in _seen:
            continue
        _seen.add(mid)
        m = PIN_TAG.search(str(msg.get("subject") or ""))
        if not m:
            continue
        pin_id = m.group(1).lower()
        pin = store.get(pin_id)
        if pin is None or pin.status in DONE:
            continue
        results.append(on_reply(pin_id, str(msg.get("sender") or "the agency"), _reply_text(msg)))
    return results


def _loop(on_reply: Callable[[str, str, str], dict]) -> None:
    print(f"[reply-poller] watching Gmail every {POLL_S:.0f}s: {QUERY}")
    while True:
        try:
            for r in poll_once(on_reply):
                print(f"[reply-poller] {r}")
        except Exception as exc:  # never die; next tick retries
            print(f"[reply-poller] poll failed: {exc!r}")
        threading.Event().wait(POLL_S)


def start(on_reply: Callable[[str, str, str], dict]) -> bool:
    """Start the background poller once. No-op without a Composio key or with GMAIL_POLL_S=0."""
    global _thread
    if _thread is not None or not actions.available() or POLL_S <= 0:
        return _thread is not None
    _thread = threading.Thread(target=_loop, args=(on_reply,), name="reply-poller", daemon=True)
    _thread.start()
    return True
