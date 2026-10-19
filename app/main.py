"""Altruistic Agent API. FastAPI serves both the JSON API and the static Leaflet map.

  GET  /pins                 all pins
  POST /pins                 create a pin, run the pipeline in the background, return immediately
  GET  /pins/{id}            one pin with its routing card and agent trace
  GET  /brief                morning brief as JSON and markdown
  POST /brief/send           post the brief to Slack via Composio
  POST /webhooks/composio    Gmail trigger, matches [PIN-<id>] and flips status to acknowledged
  POST /webhooks/parallel    Parallel Monitor events, attached to the matching pin
  POST /demo/reset           restore seeded data
  POST /demo/simulate_reply/{id}  stage-safe stand-in for the Gmail trigger
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import actions, brief as brief_mod, config, guardrails, pipeline, reply_poller, research, store
from .models import Pin, PinCreate, now_iso

app = FastAPI(title="Altruistic Agent", version="1.0.0")

# Matches generated ids (hex) and seeded ids (seed00). Kept loose on purpose.
PIN_TAG = re.compile(r"\[PIN-([0-9a-z]{4,16})\]", re.I)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "demo_mode": config.DEMO_MODE,
        "pins": len(store.all_pins()),
        "composio": bool(config.COMPOSIO_API_KEY),
        "parallel": bool(config.PARALLEL_API_KEY),
        "llm": bool(config.LLM_BASE_URL and config.LLM_MODEL),
    }


@app.get("/pins")
def list_pins() -> list[dict]:
    return [p.model_dump() for p in store.all_pins()]


@app.post("/pins")
def create_pin(body: PinCreate, background: BackgroundTasks) -> dict:
    note = guardrails.scrub(body.note)  # privacy: strip personal info before storing
    if not note:
        raise HTTPException(status_code=400, detail="note is required")
    pin_id = store.new_id()
    stamp = now_iso()
    pin = Pin(
        id=pin_id, created_at=stamp, updated_at=stamp,
        lat=body.lat, lng=body.lng, note=note,
        reporter=guardrails.scrub(body.reporter)[:40] or "neighbor",
        status="routing",
    )
    store.add(pin)
    background.add_task(pipeline.run, pin_id)  # the map never waits on the pipeline
    return pin.model_dump()


@app.get("/pins/{pin_id}")
def get_pin(pin_id: str) -> dict:
    pin = store.get(pin_id)
    if pin is None:
        raise HTTPException(status_code=404, detail="pin not found")
    return pin.model_dump()


@app.get("/brief")
def get_brief(lat: float = brief_mod.HOME_LAT, lng: float = brief_mod.HOME_LNG,
              reporter: str = "") -> dict:
    return brief_mod.build(lat, lng, reporter)


@app.post("/brief/send")
def send_brief(lat: float = brief_mod.HOME_LAT, lng: float = brief_mod.HOME_LNG,
               reporter: str = "") -> dict:
    data = brief_mod.build(lat, lng, reporter)
    out = actions.post_to_slack(data["markdown"])
    return {"sent": out.ok, "detail": out.detail, "markdown": data["markdown"]}


def _acknowledge(pin_id: str, who: str, excerpt: str) -> dict:
    pin = store.get(pin_id)
    if pin is None:
        return {"matched": False, "reason": f"no pin {pin_id}"}
    store.append_update(pin_id, {"kind": "agency_reply", "from": who, "text": excerpt[:400]})
    updated = store.update(pin_id, status="acknowledged")
    if updated:
        actions.post_to_slack(
            f"*Update on `PIN-{pin_id}`*: {updated.agency or who} replied. "
            f"Status is now *acknowledged*.\n> {excerpt[:240]}",
            thread_ts=updated.slack_ts,
        )
    return {"matched": True, "pin_id": pin_id, "status": "acknowledged"}


@app.on_event("startup")
def _start_reply_poller() -> None:
    """Real agency replies: poll Gmail via Composio for [PIN-<id>] replies (no tunnel or trigger needed)."""
    reply_poller.start(_acknowledge)


@app.post("/webhooks/composio")
async def composio_webhook(request: Request) -> JSONResponse:
    """Gmail trigger. Matches the reply to a pin by the [PIN-<id>] tag in the subject."""
    raw = await request.body()
    payload: dict[str, Any] = {}
    if config.COMPOSIO_API_KEY and config.COMPOSIO_WEBHOOK_SECRET:
        try:
            from composio import Composio

            parsed = Composio(api_key=config.COMPOSIO_API_KEY).triggers.parse(
                body=raw, headers=dict(request.headers),
                verify_secret=config.COMPOSIO_WEBHOOK_SECRET)
            payload = parsed.get("payload") or {}
        except Exception as exc:
            print(f"[webhook] composio verify failed: {exc!r}")
            return JSONResponse({"ok": False, "detail": "invalid signature"}, status_code=401)
    else:
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}

    inner = payload.get("payload") or payload.get("data") or payload
    subject = str(inner.get("subject") or "")
    sender = str(inner.get("sender") or inner.get("from") or "an agency")
    text = str(inner.get("message_text") or inner.get("snippet") or inner.get("preview") or "")
    match = PIN_TAG.search(subject) or PIN_TAG.search(text)
    if not match:
        return JSONResponse({"ok": True, "matched": False, "detail": "no PIN tag"})
    return JSONResponse({"ok": True, **_acknowledge(match.group(1).lower(), sender, text)})


@app.post("/demo/simulate_reply/{pin_id}")
def simulate_reply(pin_id: str) -> dict:
    """Stage-safe stand-in: Gmail triggers poll and can lag by minutes."""
    return _acknowledge(pin_id, "SF 311 Customer Service",
                        f"Thank you for your report [PIN-{pin_id}]. A service request has been "
                        "opened and assigned to the responsible crew.")


@app.post("/webhooks/parallel")
async def parallel_webhook(request: Request) -> dict:
    """Parallel Monitor events, attached to the matching pin as updates."""
    try:
        payload = json.loads(await request.body() or b"{}")
    except Exception:
        return {"ok": False, "detail": "bad json"}
    pin_id, text = research.monitor_event_text(payload)
    if not pin_id or store.get(pin_id) is None:
        return {"ok": True, "matched": False}
    store.append_update(pin_id, {"kind": "monitor", "text": text})
    return {"ok": True, "matched": True, "pin_id": pin_id}


@app.post("/demo/reset")
def demo_reset() -> dict:
    return {"ok": True, "pins": store.reset()}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(config.WEB_DIR)), name="static")
