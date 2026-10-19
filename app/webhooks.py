"""Inbound events: agency replies (Composio Gmail trigger) and Parallel Monitor updates.

Agency reply flow: the human sends the [PIN-<id>] draft, the agency replies in the same thread, Composio's
GMAIL_NEW_GMAIL_MESSAGE trigger fires, we match the tag in the subject, flip the pin to `acknowledged`,
append an update, and tell the neighborhood on Slack.

Two ways to receive the Gmail trigger (use either):
- start_gmail_listener(): Composio realtime subscription. No public URL needed. Best for the live demo.
- handle_composio(body, headers): for POST /webhooks/composio when a tunnel URL is configured in Composio.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from app import composio_actions as ca
from app.models import Pin
from app.store import get_pin, save_pin

log = logging.getLogger("webhooks")
try:
    TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # Windows without tzdata: PDT is correct through Nov 1, 2026
    TZ = timezone(timedelta(hours=-7), "PDT")
PIN_TAG = re.compile(r"\[PIN-([A-Za-z0-9_-]{1,40})\]")
GMAIL_TRIGGER = "GMAIL_NEW_GMAIL_MESSAGE"
ALLOW_SIMULATE = os.getenv("DEMO_MODE", "0") == "1" or os.getenv("ALLOW_SIMULATE_REPLY", "0") == "1"
ACKABLE = {"routing", "routed", "reported", "needs_human"}

_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webhooks")


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _clip(s: str, n: int = 160) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 3] + "..."


# ---------- agency reply ----------

def acknowledge(pin_id: str, snippet: str = "", via: str = "Gmail") -> Pin | None:
    """Flip a pin to acknowledged, record the reply, notify Slack. Idempotent per status."""
    with _lock:
        pin = get_pin(pin_id)
        if pin is None:
            log.warning("reply for unknown pin %s", pin_id)
            return None
        if pin.status not in ACKABLE:
            log.info("pin %s already %s, ignoring reply", pin_id, pin.status)
            return pin
        who = pin.card.agency if pin.card and pin.card.agency else "The agency"
        pin.status = "acknowledged"
        pin.updated_at = _now()
        pin.updates.append(f"{who} replied ({via}): {_clip(ca.scrub(snippet)) or 'request received.'}")
        save_pin(pin)
    log.info("pin %s acknowledged via %s", pin_id, via)
    # Side effects off the request path; each has its own 15s timeout.
    where = pin.address_hint or f"{pin.lat:.5f}, {pin.lng:.5f}"
    _pool.submit(ca.slack_post, f"**:white_check_mark: Agency replied** on the {pin.card.category.replace('_', ' ') if pin.card else 'pin'} "
                                f"at {where}.\n> {_clip(ca.scrub(snippet), 200) or 'Request received.'}\n"
                                f"[Open on the map]({ca.PUBLIC_URL}/?pin={pin.id})")
    _pool.submit(ca.sheet_upsert, pin)
    return pin


def _gmail_fields(payload: Mapping[str, Any]) -> dict[str, str]:
    p = dict(payload or {})
    preview = p.get("preview") if isinstance(p.get("preview"), dict) else {}
    return {
        "subject": str(p.get("subject") or preview.get("subject") or ""),
        "text": str(p.get("message_text") or p.get("messageText") or preview.get("body") or p.get("snippet") or ""),
        "sender": str(p.get("sender") or p.get("from") or ""),
        "thread_id": str(p.get("thread_id") or p.get("threadId") or ""),
    }


def _reply_text(text: str) -> str:
    """Drop quoted history so the update shows only the agency's new words."""
    keep = []
    for line in (text or "").splitlines():
        if line.startswith(">") or re.match(r"^On .+wrote:\s*$", line.strip()):
            break
        keep.append(line)
    return "\n".join(keep).strip() or text


def handle_gmail_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Handle one normalized Composio trigger event (from webhook or realtime subscription)."""
    slug = str(event.get("trigger_slug") or "").upper()
    if slug and slug != GMAIL_TRIGGER:
        return {"ok": True, "ignored": f"trigger {slug}"}
    f = _gmail_fields(event.get("payload") or {})
    m = PIN_TAG.search(f["subject"])
    if not m:
        return {"ok": True, "ignored": "no [PIN-id] tag"}
    pin = acknowledge(m.group(1), _reply_text(f["text"]))
    return {"ok": pin is not None, "pin_id": m.group(1), "status": pin.status if pin else None}


def handle_composio(body: bytes, headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    """POST /webhooks/composio. Returns (http_status, json). Also accepts {"simulate": true, "pin_id": ...} in DEMO_MODE."""
    try:
        raw = json.loads(body or b"{}")
    except ValueError:
        return 400, {"ok": False, "error": "invalid json"}
    if isinstance(raw, dict) and raw.get("simulate"):
        if not ALLOW_SIMULATE:
            return 403, {"ok": False, "error": "simulate disabled (set DEMO_MODE=1)"}
        pin = acknowledge(str(raw.get("pin_id", "")), raw.get("text") or "Thanks for the report. A crew has been scheduled.",
                          via="simulated reply")
        return (200 if pin else 404), {"ok": pin is not None, "pin_id": raw.get("pin_id")}
    try:
        from composio import Composio
        secret = os.getenv("COMPOSIO_WEBHOOK_SECRET", "")
        kw = {"verify_secret": secret} if secret else {}
        parsed = Composio(api_key=ca.COMPOSIO_API_KEY).triggers.parse(body=body, headers=dict(headers), **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("composio webhook rejected: %r", e)
        return 401, {"ok": False, "error": "invalid webhook"}
    return 200, handle_gmail_event(parsed["payload"])


_subscription = None


def start_gmail_listener() -> bool:
    """Subscribe to Composio trigger events over its realtime channel (no tunnel needed). Call once at startup.

    Requires a GMAIL_NEW_GMAIL_MESSAGE trigger instance for COMPOSIO_USER_ID (scripts/setup_gmail_trigger.py).
    """
    global _subscription
    if _subscription is not None or not ca.COMPOSIO_API_KEY:
        return _subscription is not None

    def run():
        global _subscription
        try:
            sub = ca._composio().triggers.subscribe(timeout=15)

            @sub.handle(trigger_slug=GMAIL_TRIGGER)
            def _on_gmail(event):  # noqa: ANN001
                try:
                    log.info("gmail trigger: %s", handle_gmail_event(event))
                except Exception as e:  # noqa: BLE001
                    log.error("gmail trigger handler failed: %r", e)

            _subscription = sub
            log.info("Composio Gmail trigger listener connected")
            sub.wait_forever()
        except Exception as e:  # noqa: BLE001
            log.error("Composio trigger listener failed: %r", e)
            _subscription = None

    threading.Thread(target=run, name="composio-triggers", daemon=True).start()
    return True


# ---------- Parallel Monitor ----------

def _parallel_client():
    from parallel import Parallel
    return Parallel(api_key=os.getenv("PARALLEL_API_KEY", ""), timeout=15, max_retries=0)


def handle_parallel(body: bytes, headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    """POST /webhooks/parallel. Fetches the detected events from Parallel and attaches them to the pin.

    The pin id comes from the monitor's own metadata (fetched from Parallel), not from the request body,
    so a forged webhook can't write arbitrary text onto pins.
    """
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return 400, {"ok": False, "error": "invalid json"}
    if payload.get("type") != "monitor.event.detected":
        return 200, {"ok": True, "ignored": payload.get("type")}
    data = payload.get("data") or {}
    monitor_id = data.get("monitor_id")
    group_id = (data.get("event") or {}).get("event_group_id")
    if not monitor_id:
        return 400, {"ok": False, "error": "missing monitor_id"}
    try:
        client = _parallel_client()
        monitor = client.monitor.retrieve(monitor_id)
        meta = getattr(monitor, "metadata", None) or {}
        res = client.monitor.events(monitor_id, event_group_id=group_id) if group_id else client.monitor.events(monitor_id, limit=3)
    except Exception as e:  # noqa: BLE001
        log.error("parallel monitor fetch failed: %r", e)
        return 200, {"ok": False, "error": "fetch failed"}

    lines = []
    for ev in (getattr(res, "events", None) or [])[:3]:
        out = getattr(ev, "output", None)
        content = getattr(out, "content", "")
        text = content if isinstance(content, str) else json.dumps(content)[:300]
        urls = [c.url for b in (getattr(out, "basis", None) or []) for c in (getattr(b, "citations", None) or [])][:1]
        lines.append(f"Parallel monitor: {_clip(text, 220)}" + (f" (source: {urls[0]})" if urls else ""))
    if not lines:
        return 200, {"ok": True, "events": 0}

    pin_ids = [p for p in str(meta.get("pin_ids") or meta.get("pin_id") or "").split(",") if p]
    touched = []
    with _lock:
        for pid in pin_ids:
            pin = get_pin(pid)
            if pin is None:
                continue
            pin.updates.extend(lines)
            pin.updated_at = _now()
            save_pin(pin)
            touched.append(pid)
    _pool.submit(ca.slack_post, "**:mag: Neighborhood watch (Parallel Monitor)**\n" + "\n".join(f"- {l}" for l in lines))
    return 200, {"ok": True, "events": len(lines), "pins": touched}
