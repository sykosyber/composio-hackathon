"""Composio actions: Google Sheets mirror, Gmail DRAFT, Slack post.

We never let a model pick tools. The pipeline executes specific slugs that were verified
against the live Composio tool schemas on 2026-10-19:

  GMAIL_CREATE_EMAIL_DRAFT                 recipient_email, subject, body, is_html, user_id
  GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND  spreadsheetId, range, valueInputOption, values[[...]]
  SLACK_SEND_MESSAGE                       channel, markdown_text

Transport, picked from the key type:
- `ck_...` consumer key: Composio MCP at https://connect.composio.dev/mcp (header x-consumer-api-key),
  COMPOSIO_MULTI_EXECUTE_TOOL with one fixed slug + arguments. Verified live 2026-10-19 12:43.
- project key: SDK, Composio().sessions.create(user_id=..., toolkits=[...]) then session.execute(slug, arguments={...}).

Every function here is best effort: it returns an Outcome and never raises into the
pipeline, so a dead Sheet or Slack never stalls the demo.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Optional

from . import config
from .models import Pin

TOOLKITS = ["gmail", "googlesheets", "slack"]

_session: Any = None
_session_lock = threading.Lock()


@dataclass
class Outcome:
    ok: bool
    detail: str = ""
    data: Optional[dict] = None


def available() -> bool:
    return bool(config.COMPOSIO_API_KEY)


def session() -> Any:
    """One cached tool-router session for the fixed demo user."""
    global _session
    with _session_lock:
        if _session is None:
            from composio import Composio

            composio = Composio(api_key=config.COMPOSIO_API_KEY)
            _session = composio.sessions.create(user_id=config.COMPOSIO_USER_ID, toolkits=TOOLKITS)
        return _session


MCP_URL = "https://connect.composio.dev/mcp"


def _use_mcp() -> bool:
    return config.COMPOSIO_API_KEY.startswith("ck_")


def mcp_call(name: str, arguments: dict) -> dict:
    """One JSON-RPC tools/call against the Composio MCP server. Returns the parsed tool result."""
    import httpx

    r = httpx.post(MCP_URL, timeout=config.COMPOSIO_TIMEOUT, headers={
        "x-consumer-api-key": config.COMPOSIO_API_KEY, "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
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


def _mcp_execute(slug: str, arguments: dict) -> dict:
    """Run exactly one named tool, normalized to {successful, data, error} like the SDK."""
    out = mcp_call("COMPOSIO_MULTI_EXECUTE_TOOL", {
        "tools": [{"tool_slug": slug, "arguments": arguments}],
        "thought": f"Blockwise pipeline step {slug}", "current_step": slug,
    })
    results = (out.get("data") or {}).get("results") or []
    if not results:
        return {"successful": False, "error": out.get("error") or "no result", "data": {}}
    resp = results[0].get("response") or {}
    return {"successful": bool(resp.get("successful")), "data": resp.get("data") or {},
            "error": resp.get("error") or results[0].get("error")}


def _unwrap(resp: Any) -> dict:
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    if isinstance(resp, dict):
        return resp
    return {"result": str(resp)}


def execute(slug: str, arguments: dict) -> Outcome:
    """Execute one verified tool slug with a timeout and never raise."""
    if not available():
        return Outcome(False, "COMPOSIO_API_KEY not set")
    box: dict = {}

    def _call() -> None:
        try:
            if _use_mcp():
                box["data"] = _mcp_execute(slug, arguments)
            else:
                box["data"] = _unwrap(session().execute(slug, arguments=arguments))
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"[:300]

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=config.COMPOSIO_TIMEOUT)
    if thread.is_alive():
        return Outcome(False, f"{slug} timed out after {config.COMPOSIO_TIMEOUT:.0f}s")
    if "error" in box:
        print(f"[composio] {slug} failed: {box['error']}")
        return Outcome(False, box["error"])
    data = box.get("data") or {}
    if data.get("successful") is False:
        return Outcome(False, str(data.get("error") or "tool reported failure")[:200], data)
    return Outcome(True, "", data)


def _dig(data: Any, *keys: str) -> str:
    """Pull the first matching key out of a nested Composio response."""
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k in keys:
                if cur.get(k):
                    return str(cur[k])
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return ""


# ---------------- Google Sheets: shared community ledger (mirror) ----------------

def sheet_row(pin: Pin) -> list[str]:
    """Pin schema order. Only the note, coordinates and routing data. No personal info."""
    return [
        pin.id, pin.created_at, pin.updated_at, f"{pin.lat:.6f}", f"{pin.lng:.6f}",
        pin.address_hint, pin.note, pin.category, pin.severity, pin.agency, pin.channel,
        pin.channel_url, pin.already_reported, pin.status,
        json.dumps([s.model_dump() for s in pin.sources], ensure_ascii=False),
        pin.draft_id, pin.slack_ts,
    ]


def append_to_sheet(pin: Pin) -> Outcome:
    """Mirror the pin into the shared Google Sheet. If this fails we log it and continue."""
    if not config.SHEET_ID:
        return Outcome(False, "SHEET_ID not set, local ledger only")
    return execute("GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND", {
        "spreadsheetId": config.SHEET_ID,
        "range": config.SHEET_RANGE,
        "valueInputOption": "RAW",
        "insertDataOption": "INSERT_ROWS",
        "majorDimension": "ROWS",
        "values": [sheet_row(pin)],
    })


# ---------------- Gmail: DRAFT only, never send ----------------

def create_draft(pin: Pin) -> Outcome:
    """Create a Gmail DRAFT addressed to the agency. The human reviews and hits send.

    The agent has no send capability in this pipeline by design.
    """
    args: dict[str, Any] = {
        "subject": pin.draft_subject[:200],
        "body": pin.draft_body,
        "is_html": False,
        "user_id": "me",
    }
    if config.AGENCY_DRAFT_TO:
        args["recipient_email"] = config.AGENCY_DRAFT_TO
    out = execute("GMAIL_CREATE_EMAIL_DRAFT", args)
    if out.ok:
        out.detail = _dig(out.data, "draft_id", "id")
    return out


def find_reply(pin_id: str) -> Outcome:
    """Poll Gmail for a reply carrying the [PIN-<id>] tag. Backs the simulate-reply path."""
    return execute("GMAIL_FETCH_EMAILS", {
        "query": f'subject:"[PIN-{pin_id}]"',
        "max_results": 5,
        "user_id": "me",
    })


# ---------------- Slack: the neighborhood channel ----------------

def post_to_slack(markdown_text: str, thread_ts: str = "") -> Outcome:
    if not config.SLACK_CHANNEL:
        return Outcome(False, "SLACK_CHANNEL not set")
    args: dict[str, Any] = {"channel": config.SLACK_CHANNEL, "markdown_text": markdown_text}
    if thread_ts:
        args["thread_ts"] = thread_ts
    out = execute("SLACK_SEND_MESSAGE", args)
    if out.ok:
        out.detail = _dig(out.data, "ts", "message_ts")
    return out


def pin_slack_message(pin: Pin) -> str:
    label = pin.category.replace("_", " ").capitalize()
    where = pin.address_hint or f"{pin.lat:.4f}, {pin.lng:.4f}"
    lines = [
        f"**Blockwise: new pin** · {label} at {where} ({pin.severity})",
        f"> {pin.note}",
    ]
    if pin.status == "needs_human":
        lines.append(f"**Needs a human.** {pin.needs_human_reason}. No source, no claim, so nothing was guessed.")
    else:
        link = f" · [report form]({pin.channel_url})" if pin.channel_url else ""
        lines.append(f"**Who fixes it:** {pin.agency} via {pin.channel}{link}")
        lines.append(f"**Already reported:** {pin.already_reported}")
    if pin.sources:
        cites = " · ".join(f"[{s.title[:40].replace('[', '(').replace(']', ')')}]({s.url})" for s in pin.sources[:3])
        lines.append(f"**Sources:** {cites}")
    lines.append(f"Draft email ready for review. Nothing was sent. `PIN-{pin.id}`")
    return "\n".join(lines)
