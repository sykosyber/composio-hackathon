# Contract requests (Claude lane -> Cline, relayed by Mateo)

Requests for changes in files the Claude lane does not own. Each item is small and copy-pasteable.

## 1. Wire webhooks and the Gmail listener in `app/main.py`

`app/webhooks.py` exposes plain functions; the routes stay Cline's.

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from app import webhooks

@app.post("/webhooks/composio")
async def composio_webhook(request: Request):
    code, body = webhooks.handle_composio(await request.body(), request.headers)
    return JSONResponse(body, status_code=code)

@app.post("/webhooks/parallel")
async def parallel_webhook(request: Request):
    code, body = webhooks.handle_parallel(await request.body(), request.headers)
    return JSONResponse(body, status_code=code)

@app.on_event("startup")          # or lifespan
def _start_listeners():
    webhooks.start_gmail_listener()   # polls Gmail via Composio every 8s for [PIN-id] replies; no-op without a key
```

- `POST /webhooks/composio` also accepts `{"simulate": true, "pin_id": "..."}` when `DEMO_MODE=1`
  (used by the UI's "Simulate agency reply" button at `/?demo=1`; this is the cut-order fallback for the reply trigger).

## 2. Brief routes

```python
from app.brief import build_brief
from app import composio_actions as ca

@app.get("/brief")
def brief():
    return build_brief(load_pins())

@app.post("/brief/send")
def brief_send():
    b = build_brief(load_pins())
    ts = ca.slack_post(b["markdown"])
    return {"ok": ts is not None, "ts": ts}
```

## 3. Static files

`web/` holds `index.html`, `app.js`, `style.css`, `fixtures.json`. Mount it last so API routes win:
`app.mount("/", StaticFiles(directory="web", html=True), name="web")`

## 4. Parallel Monitor metadata

When creating the monitor, set `metadata={"pin_ids": "s01,s05,<id>"}` (comma-separated, strings only).
`handle_parallel` reads pin ids from the monitor's metadata fetched from Parallel, not from the webhook body.

## 5. `/demo/reset`

Restore `data/pins.json` from `data/seed_pins.json` (9 seeded Mission pins). Also delete `data/sheet_rows.json`
so the Sheet mirror re-appends rows.

## 6. requirements.txt

Add `tzdata` (Windows has no system tz database; code falls back to fixed PDT without it).

## 7. New env vars (add to `.env.example`)

```
GOOGLE_SHEET_ID=          # id from the community ledger Sheet URL
GOOGLE_SHEET_TAB=Sheet1
SLACK_CHANNEL=            # channel id, e.g. C0CAABPUP1T (#all-neighborhood)
GMAIL_POLL_S=8
AGENCY_DRAFT_TO=          # demo stand-in for the agency inbox (second test Gmail). Never a real agency.
PUBLIC_URL=http://localhost:8000
BRIEF_HOME_LAT=37.7599
BRIEF_HOME_LNG=-122.4183
```
