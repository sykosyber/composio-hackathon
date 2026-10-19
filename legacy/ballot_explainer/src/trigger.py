"""Trigger: Composio Gmail webhook + manual Run button + Parallel Monitor webhook. stdlib only.

    python -m src.trigger           # http://127.0.0.1:8000  (Run button)

Routes
  GET  /                    Run button page (manual fallback - USE THIS ON STAGE)
  POST /run                 run pipeline (cache mode unless MODE=live)
  POST /webhooks/composio   Composio trigger delivery (GMAIL_NEW_GMAIL_MESSAGE)
  POST /webhooks/parallel   Parallel Monitor delivery (monitor.event.detected) -> Slack DM

Composio docs (verified 2026-10-19):
  Triggers overview:  https://docs.composio.dev/docs/triggers
     !! Gmail is a POLLING trigger: up to ~15 min latency on Composio-managed auth. Do not rely on it live.
  Create trigger:     https://docs.composio.dev/docs/setting-up-triggers/creating-triggers
  Receive events:     https://docs.composio.dev/docs/setting-up-triggers/subscribing-to-events
     local forwarding:  composio dev triggers listen --forward "http://localhost:8000/webhooks/composio"
  Full example:       https://docs.composio.dev/examples/email-triggered-agent
     composio.triggers.parse(body=..., headers=..., verify_secret=SECRET) -> {"raw_payload", "payload"}
"""
from __future__ import annotations

import io
import json
import threading
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import config, pipeline

KEYWORDS = ("ballot", "election", "vote", "voter")
PAGE = """<!doctype html><meta charset=utf-8><title>Your Ballot, Explained</title>
<style>body{font:16px system-ui;max-width:860px;margin:40px auto}button{font-size:22px;padding:14px 28px}
pre{background:#111;color:#0f0;padding:16px;white-space:pre-wrap;min-height:300px}</style>
<h1>Your Ballot, Explained</h1><p>Altruistic Agent - Pillar 1. Nonpartisan, cited, human-in-the-loop.</p>
<label><input type=checkbox id=inj checked> show guardrail demo</label>
<p><button onclick="go()">Run</button></p><pre id=o></pre>
<script>async function go(){o.textContent='running...';const r=await fetch('/run?inject='+(inj.checked?1:0),{method:'POST'});o.textContent=await r.text()}</script>"""


def _run_capture(**kw) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            pipeline.run(**kw)
        except Exception as e:
            print(f"ERROR: {e!r}")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, text: str, ctype: str = "text/plain; charset=utf-8"):
        b = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._reply(200, PAGE, "text/html; charset=utf-8") if self.path == "/" else self._reply(404, "not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if self.path.startswith("/run"):
            return self._reply(200, _run_capture(inject="inject=1" in self.path))
        if self.path == "/webhooks/composio":
            return self._composio(body)
        if self.path == "/webhooks/parallel":
            return self._parallel(body)
        self._reply(404, "not found")

    def _composio(self, body: bytes):
        from composio import Composio

        try:
            parsed = Composio(api_key=config.COMPOSIO_API_KEY).triggers.parse(
                body=body, headers=dict(self.headers), verify_secret=config.COMPOSIO_WEBHOOK_SECRET)
        except Exception:
            return self._reply(401, "invalid webhook")
        ev = parsed["payload"]
        if ev.get("trigger_slug") != "GMAIL_NEW_GMAIL_MESSAGE":
            return self._reply(200, "ignored")
        # TODO(cline): confirm Gmail payload field names via composio.triggers.get_type("GMAIL_NEW_GMAIL_MESSAGE").payload
        p = ev.get("payload") or {}
        email = {"subject": p.get("subject", ""), "body": p.get("message_text") or p.get("preview", {}).get("body", "")}
        if not any(k in (email["subject"] + email["body"]).lower() for k in KEYWORDS):
            return self._reply(200, "not an election email")
        threading.Thread(target=lambda: print(_run_capture(email=email, push=True)), daemon=True).start()
        self._reply(200, "pipeline started")

    def _parallel(self, body: bytes):
        from . import monitor, outputs

        # TODO(cline): verify Parallel webhook signature - https://docs.parallel.ai/resources/webhook-setup
        msg = monitor.handle_webhook(json.loads(body or b"{}"))
        if msg:
            outputs.slack_self_dm(msg)
        self._reply(200, "ok")


def serve(host: str = "127.0.0.1", port: int = 8000):
    print(f"Run button: http://{host}:{port}/   (MODE={config.MODE})")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
