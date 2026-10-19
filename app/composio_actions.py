"""Composio actions for the pin pipeline: Google Sheet mirror, Gmail DRAFT, Slack posts.

Rules:
- Every call has a hard 15s timeout and returns None/False on any failure. The pipeline never stalls on us.
- Gmail is DRAFT ONLY. Nothing here can send email. A human reviews the draft and clicks send.
- The Sheet gets only note, coordinates, routing fields, and a display name. Emails/phones are scrubbed.

Tool slugs and argument schemas are recorded in docs/composio_slugs.md (verified against the live API).

Transport (picked from the key type):
- `ck_...` consumer key: Composio MCP at https://connect.composio.dev/mcp (header x-consumer-api-key),
  calling COMPOSIO_MULTI_EXECUTE_TOOL with one explicit slug + arguments. The model never picks tools.
- `ak_...` project key: Python SDK, composio.tools.execute(slug, arguments, user_id=COMPOSIO_USER_ID).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.models import Pin

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
log = logging.getLogger("composio_actions")

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY", "")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "mateo-demo")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")            # spreadsheet id, or the full Sheet URL
if "/d/" in SHEET_ID:
    SHEET_ID = SHEET_ID.split("/d/", 1)[1].split("/", 1)[0]
SHEET_TAB = os.getenv("GOOGLE_SHEET_TAB", "Sheet1")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")         # e.g. "#mission-neighbors" or a C... id
DRAFT_TO = os.getenv("AGENCY_DRAFT_TO", "")            # demo stand-in for the agency inbox. Never a real agency.
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")
TIMEOUT_S = 15
MCP_URL = os.getenv("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp")
USE_MCP = COMPOSIO_API_KEY.startswith("ck_")

SLUGS = {
    "sheet_append": "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND",
    "sheet_update": "GOOGLESHEETS_VALUES_UPDATE",
    "gmail_draft": "GMAIL_CREATE_EMAIL_DRAFT",
    "slack_send": "SLACK_SEND_MESSAGE",
}

SHEET_COLUMNS = ["id", "created_at", "updated_at", "lat", "lng", "address_hint", "note", "category", "severity",
                 "agency", "channel", "channel_url", "already_reported", "status", "sources", "draft_id", "slack_ts"]
_ROWS_FILE = ROOT / "data" / "sheet_rows.json"   # pin id -> sheet row number, so re-syncs update in place
_rows_lock = threading.Lock()

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="composio")
_client = None


# ---------- core ----------

def _composio():
    global _client
    if _client is None:
        from composio import Composio
        _client = Composio(api_key=COMPOSIO_API_KEY, timeout=TIMEOUT_S, max_retries=0)
    return _client


def _mcp_call(name: str, arguments: dict[str, Any]) -> dict:
    """One JSON-RPC tools/call against the Composio MCP server. Returns the parsed tool result JSON."""
    import httpx

    r = httpx.post(MCP_URL, timeout=TIMEOUT_S, headers={
        "x-consumer-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }, json={"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": "tools/call",
             "params": {"name": name, "arguments": arguments}})
    r.raise_for_status()
    msg = None
    for line in r.text.splitlines():  # streamable HTTP answers as SSE: "data: {...}"
        if line.startswith("data:"):
            msg = json.loads(line[5:])
    if msg is None:
        msg = r.json()
    if msg.get("error"):
        raise RuntimeError(f"mcp error: {msg['error']}")
    content = (msg.get("result") or {}).get("content") or []
    return json.loads(content[0]["text"]) if content else {}


def _mcp_execute(slug: str, arguments: dict[str, Any]) -> dict:
    """Execute exactly one named tool via COMPOSIO_MULTI_EXECUTE_TOOL, normalized to {successful, data, error}."""
    out = _mcp_call("COMPOSIO_MULTI_EXECUTE_TOOL", {
        "tools": [{"tool_slug": slug, "arguments": arguments}],
        "thought": f"Altruistic Agent pipeline step {slug}", "current_step": slug, "sync_response_to_workbench": False,
    })
    results = ((out.get("data") or {}).get("results")) or []
    if not out.get("successful") or not results:
        return {"successful": False, "error": out.get("error") or out}
    resp = results[0].get("response") or {}
    return {"successful": bool(resp.get("successful")), "data": resp.get("data") or {}, "error": resp.get("error")}


def _execute(slug: str, arguments: dict[str, Any]) -> dict | None:
    """Run one Composio tool with a hard timeout. Returns the tool's `data` dict, or None on failure."""
    if not COMPOSIO_API_KEY:
        log.warning("composio %s skipped: COMPOSIO_API_KEY not set", slug)
        return None
    t0 = time.perf_counter()

    def call():
        if USE_MCP:
            return _mcp_execute(slug, arguments)
        return _composio().tools.execute(slug, arguments, user_id=COMPOSIO_USER_ID,
                                         dangerously_skip_version_check=True)
    try:
        res = _pool.submit(call).result(timeout=TIMEOUT_S)
    except FutTimeout:
        log.error("composio %s timed out after %ss", slug, TIMEOUT_S)
        return None
    except Exception as e:  # noqa: BLE001 - any SDK/network error is a soft failure
        log.error("composio %s failed: %r", slug, e)
        return None
    ms = int((time.perf_counter() - t0) * 1000)
    res = res if isinstance(res, dict) else getattr(res, "model_dump", lambda: dict(res))()
    if not res.get("successful", res.get("successfull", False)):
        log.error("composio %s unsuccessful in %dms: %s", slug, ms, res.get("error"))
        return None
    log.info("composio %s ok in %dms", slug, ms)
    return res.get("data") or {}


def _dig(d: Any, *paths: str) -> Any:
    """First non-empty value among dotted paths, e.g. _dig(data, 'ts', 'message.ts')."""
    for p in paths:
        cur = d
        for k in p.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur not in (None, ""):
            return cur
    return None


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


def scrub(text: str | None) -> str:
    return _PHONE.sub("[phone removed]", _EMAIL.sub("[email removed]", text or ""))


# ---------- Google Sheet mirror ----------

def _row(pin: Pin) -> list[str]:
    c = pin.card
    vals = {
        "id": pin.id, "created_at": pin.created_at, "updated_at": pin.updated_at,
        "lat": f"{pin.lat:.6f}", "lng": f"{pin.lng:.6f}", "address_hint": pin.address_hint or "",
        "note": scrub(pin.note), "status": pin.status, "draft_id": pin.draft_id or "", "slack_ts": pin.slack_ts or "",
        "category": c.category if c else "", "severity": c.severity if c else "",
        "agency": (c.agency or "") if c else "", "channel": (c.channel or "") if c else "",
        "channel_url": (c.channel_url or "") if c else "", "already_reported": c.already_reported if c else "",
        "sources": json.dumps([s.model_dump() for s in c.sources]) if c else "[]",
    }
    return [str(vals[k]) for k in SHEET_COLUMNS]


def _load_rows() -> dict[str, int]:
    try:
        return json.loads(_ROWS_FILE.read_text())
    except Exception:
        return {}


def _save_rows(rows: dict[str, int]) -> None:
    _ROWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ROWS_FILE.write_text(json.dumps(rows, indent=1))


def _ensure_header() -> bool:
    with _rows_lock:
        rows = _load_rows()
        if rows.get("__header__"):
            return True
    data = _execute(SLUGS["sheet_update"], {
        "spreadsheet_id": SHEET_ID, "range": f"{SHEET_TAB}!A1", "value_input_option": "RAW",
        "values": [SHEET_COLUMNS],
    })
    if data is None:
        return False
    with _rows_lock:
        rows = _load_rows()
        rows["__header__"] = 1
        _save_rows(rows)
    return True


def sheet_upsert(pin: Pin) -> bool:
    """Append the pin as a row, or update its existing row. True on success."""
    if not SHEET_ID:
        log.warning("sheet_upsert skipped: GOOGLE_SHEET_ID not set")
        return False
    _ensure_header()
    row = _row(pin)
    with _rows_lock:
        existing = _load_rows().get(pin.id)
    if existing:
        data = _execute(SLUGS["sheet_update"], {
            "spreadsheet_id": SHEET_ID, "range": f"{SHEET_TAB}!A{existing}", "value_input_option": "RAW",
            "values": [row],
        })
        return data is not None
    data = _execute(SLUGS["sheet_append"], {
        "spreadsheetId": SHEET_ID, "range": f"{SHEET_TAB}!A1", "valueInputOption": "RAW",
        "insertDataOption": "INSERT_ROWS", "values": [row],
    })
    if data is None:
        return False
    rng = _dig(data, "updates.updatedRange", "updatedRange", "response_data.updates.updatedRange") or ""
    m = re.search(r"!A(\d+)", rng)
    if m:
        with _rows_lock:
            rows = _load_rows()
            rows[pin.id] = int(m.group(1))
            _save_rows(rows)
    return True


# ---------- Gmail DRAFT (never send) ----------

def _draft_subject(pin: Pin) -> str:
    subj = (pin.card.draft_subject if pin.card else "") or f"Neighborhood report: {pin.note[:60]}"
    tag = f"[PIN-{pin.id}]"
    return subj if tag in subj else f"{tag} {subj}"


def _draft_body(pin: Pin) -> str:
    c = pin.card
    body = (c.draft_body if c else "") or f"Hello,\n\nI'd like to report: {pin.note}\n\nThank you."
    loc = pin.address_hint or f"{pin.lat:.5f}, {pin.lng:.5f}"
    map_link = f"https://www.openstreetmap.org/?mlat={pin.lat:.6f}&mlon={pin.lng:.6f}#map=18/{pin.lat:.6f}/{pin.lng:.6f}"
    extra = [f"\n\nLocation: {loc}\nMap: {map_link}"]
    if c and c.channel_url:
        extra.append(f"Official reporting channel: {c.channel_url}")
    extra.append("\n(Drafted by Altruistic Agent for a neighbor to review and send. Please keep the "
                 f"[PIN-{pin.id}] tag in your reply so we can track it.)")
    return scrub(body) + "\n".join(extra)


def gmail_draft(pin: Pin) -> str | None:
    """Create a Gmail DRAFT for the agency report. Returns the draft id. Never sends."""
    args = {"subject": _draft_subject(pin), "body": _draft_body(pin), "is_html": False}
    if DRAFT_TO:
        args["recipient_email"] = DRAFT_TO
    data = _execute(SLUGS["gmail_draft"], args)
    if data is None:
        return None
    return _dig(data, "id", "draft_id", "response_data.id", "draft.id") or "draft-created"


# ---------- Slack ----------

STATUS_WORDS = {"routing": "routing", "routed": "agency found", "reported": "draft ready, waiting on a human to send",
                "acknowledged": "agency replied", "resolved": "resolved", "needs_human": "needs a human",
                "emergency": "emergency"}


def pin_slack_text(pin: Pin) -> str:
    c = pin.card
    where = pin.address_hint or f"{pin.lat:.5f}, {pin.lng:.5f}"
    cat = c.category.replace("_", " ") if c else "new issue"
    lines = [f"**:round_pushpin: New pin: {cat}** at {where}", f"> {scrub(pin.note)}"]
    if c and c.agency:
        how = f" via [{c.channel or 'official channel'}]({c.channel_url})" if c.channel_url else ""
        lines.append(f"**Who fixes it:** {c.agency}{how}")
    elif pin.status == "needs_human":
        lines.append("**Who fixes it:** couldn't verify the right agency. Can a neighbor help?")
    if c and c.already_reported in ("yes", "likely"):
        lines.append(f"_Looks like this may already be reported ({c.already_reported})._")
    lines.append(f"**Status:** {STATUS_WORDS.get(pin.status, pin.status)}  |  [Open on the map]({PUBLIC_URL}/?pin={pin.id})")
    return "\n".join(lines)


def slack_post(text: str) -> str | None:
    """Post a message to the neighborhood channel. Returns the message ts."""
    if not SLACK_CHANNEL:
        log.warning("slack_post skipped: SLACK_CHANNEL not set")
        return None
    data = _execute(SLUGS["slack_send"], {"channel": SLACK_CHANNEL, "markdown_text": text})
    if data is None:
        return None
    return _dig(data, "ts", "message.ts", "response_data.ts") or "posted"


def slack_post_pin(pin: Pin) -> str | None:
    return slack_post(pin_slack_text(pin))
