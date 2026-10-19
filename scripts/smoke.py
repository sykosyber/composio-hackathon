#!/usr/bin/env python3
"""Smoke test the whole app against a running server. No keys required.

    .venv/bin/python -m uvicorn app.main:app --port 8000 &
    .venv/bin/python scripts/smoke.py

Checks the guardrails, the pipeline, both webhooks, the brief and the reset path.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import guardrails, llm  # noqa: E402
from app.geo import address_hint  # noqa: E402

BASE = "http://127.0.0.1:8000"
passed, failed = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def main() -> int:
    print("unit: guardrails and geo")
    check("emergency detected", guardrails.is_emergency("there is a gas leak on the corner"))
    check("non emergency passes", not guardrails.is_emergency("streetlight is out"))
    check("email scrubbed", "@" not in guardrails.scrub("call bob@example.com please"))
    check("phone scrubbed", "555" not in guardrails.scrub("ring 415-555-0199 anytime"))
    check("geocode names intersection",
          address_hint(37.76150, -122.42180) == "Valencia St and 18th St")
    check("rule classifier", llm.rule_category("streetlight out, very dark") == "streetlight")
    check("rule severity", llm.rule_severity("exposed wire, very unsafe") == "high")

    print("api: reset and list")
    client = httpx.Client(base_url=BASE, timeout=20)
    seeded = client.post("/demo/reset").json()["pins"]
    check("reset restores seeds", seeded >= 8, f"got {seeded}")
    pins = client.get("/pins").json()
    check("pins listed", len(pins) == seeded)
    check("seed statuses varied", {p["status"] for p in pins} >= {"acknowledged", "resolved",
                                                                  "needs_human"})

    print("api: pipeline on a new pin")
    created = client.post("/pins", json={
        "lat": 37.7615, "lng": -122.4218, "reporter": "mateo",
        "note": "Streetlight out at Valencia and 18th, very dark at night. reach me at 415-555-0199",
    }).json()
    check("pin returns immediately", created["status"] == "routing")
    check("personal data stripped", "555" not in created["note"])
    pin = {}
    for _ in range(20):
        time.sleep(0.4)
        pin = client.get(f"/pins/{created['id']}").json()
        if pin["status"] != "routing":
            break
    check("pipeline finished", pin["status"] != "routing", pin["status"])
    check("category classified", pin["category"] == "streetlight")
    check("agent trace recorded", len(pin["trace"]) >= 8, str(len(pin["trace"])))
    check("draft subject tagged", pin["draft_subject"].startswith(f"[PIN-{created['id']}]"))
    check("no unsourced claim",
          bool(pin["agency"]) or pin["status"] == "needs_human")

    print("api: emergency path")
    emergency = client.post("/pins", json={
        "lat": 37.765, "lng": -122.4196, "reporter": "dana",
        "note": "Strong gas leak smell near the corner store",
    }).json()
    time.sleep(1.5)
    emergency = client.get(f"/pins/{emergency['id']}").json()
    check("emergency flagged", emergency["emergency"] is True)
    check("emergency not routed", emergency["status"] == "needs_human")
    check("emergency says call 911", "911" in emergency["summary"])

    print("api: webhooks")
    reply = client.post("/webhooks/composio", json={"payload": {
        "subject": "Re: [PIN-seed03] sidewalk request",
        "sender": "311@sfgov.org",
        "message_text": "We opened service request 24-118.",
    }}).json()
    check("gmail reply matched", reply.get("matched") is True, str(reply))
    check("pin acknowledged", client.get("/pins/seed03").json()["status"] == "acknowledged")

    monitor = client.post("/webhooks/parallel", json={
        "type": "monitor.event.detected",
        "data": {"monitor_id": "m1", "metadata": {"pin_id": "seed07"},
                 "event": {"event_group_id": "g1", "title": "Crew scheduled"}},
    }).json()
    check("monitor event attached", monitor.get("matched") is True)
    check("update stored", len(client.get("/pins/seed07").json()["updates"]) >= 1)

    print("api: morning brief")
    brief = client.get("/brief").json()
    text = brief["markdown"]
    check("brief has an area", bool(brief["area"]))
    check("brief lists civic dates", "November 3, 2026" in text)
    check("brief has registration deadline", "register online" in text)
    check("brief stays neutral",
          not any(w in text.lower() for w in ("vote for", "candidate", "endorse")))
    check("brief has status changes", "acknowledged" in text.lower())

    client.post("/demo/reset")
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
