"""Deterministic pin pipeline with LLM steps inside it. Same order every time.

  0 guardrail  emergency check (skips everything and says call 911)
  1 geocode    coarse address hint from coordinates, offline table
  2 research   Parallel Search: responsible agency + official reporting channel, cited
  3 dedupe     Parallel Search: is this already known
  4 route      open-source LLM produces the routing card, validated by Pydantic
  5 verify     no source, no claim
  6 ledger     Composio Google Sheets append (mirror, best effort)
  7 draft      Composio Gmail DRAFT, never sent
  8 notify     Composio Slack post to the neighborhood channel
  9 watch      Parallel Monitor on the open issue

Every external call has a timeout and a fallback, so the map never stalls.
"""
from __future__ import annotations

from . import actions, guardrails, llm, research, store
from .geo import address_hint
from .models import Pin
from .trace import Tracer


def _save(pin_id: str, tracer: Tracer, **fields) -> Pin | None:
    return store.update(pin_id, trace=[s.model_dump() for s in tracer.steps], **fields)


def run(pin_id: str) -> Pin | None:
    """Run the pipeline. Never raises: a pin must never be left stuck in `routing`."""
    try:
        return _run(pin_id)
    except Exception as exc:
        # Last resort. Any unhandled failure still leaves the pin in a terminal, honest state
        # rather than an endless spinner on the map.
        print(f"[pipeline] unhandled failure on {pin_id}: {exc!r}")
        return store.update(
            pin_id,
            status="needs_human",
            needs_human_reason="Routing failed, a human should take a look",
        )


def _run(pin_id: str) -> Pin | None:
    pin = store.get(pin_id)
    if pin is None:
        print(f"[pipeline] unknown pin {pin_id}")
        return None
    tracer = Tracer(pin_id)

    # 0 Emergencies are not routed.
    with tracer.step("guardrail", "local-rules") as box:
        emergency = guardrails.is_emergency(pin.note)
        box["detail"] = "emergency detected" if emergency else "no emergency signals"
    if emergency:
        return _save(pin_id, tracer, status="needs_human", emergency=True,
                     summary=guardrails.EMERGENCY_MESSAGE,
                     needs_human_reason="Possible emergency, call 911")

    # 1 Coarse location label. Offline, so it always works.
    with tracer.step("geocode", "local-table") as box:
        hint = pin.address_hint or address_hint(pin.lat, pin.lng)
        box["detail"] = hint
    _save(pin_id, tracer, address_hint=hint)

    # 2 Who is responsible, with citations.
    guess = llm.rule_category(pin.note)
    with tracer.step("research", "parallel-search") as box:
        agency_hits = research.find_agency(guess)
        box["ok"] = bool(agency_hits)
        box["detail"] = f"{len(agency_hits)} cited results"

    # 3 Already known?
    with tracer.step("dedupe", "parallel-search") as box:
        dedupe_hits = research.check_already_reported(guess, hint)
        box["detail"] = f"{len(dedupe_hits)} results"

    snippets = (agency_hits + dedupe_hits)[:8]
    dedupe_hint = " | ".join(f"{h['title']}: {h.get('excerpt', '')[:160]}" for h in dedupe_hits[:3])

    # 4 Routing card from the open-source model, validated.
    with tracer.step("route", "llm-json") as box:
        card, origin = llm.route(pin_id, pin.note, hint, pin.lat, pin.lng, snippets, dedupe_hint)
        box["ok"] = origin != "fallback"
        box["detail"] = f"{origin}: {card.category}/{card.severity}"

    # 5 No source, no claim.
    with tracer.step("verify", "guardrails") as box:
        card = guardrails.enforce_sources(card, {s["url"] for s in snippets})
        verified, reason = guardrails.verify_card(card)
        box["ok"] = verified
        box["detail"] = "cited agency and channel" if verified else reason

    status = "routed" if verified else "needs_human"
    pin = _save(
        pin_id, tracer,
        category=card.category, severity=card.severity, summary=card.summary,
        agency=card.agency, channel=card.channel, channel_url=card.channel_url,
        already_reported=card.already_reported,
        sources=[s.model_dump() for s in card.sources],
        draft_subject=card.draft_subject, draft_body=card.draft_body,
        status=status, needs_human_reason="" if verified else reason,
    ) or pin

    # 6 Shared ledger mirror. Failure is logged, never fatal.
    with tracer.step("ledger", "composio-sheets") as box:
        out = actions.append_to_sheet(pin)
        box["ok"] = out.ok
        box["detail"] = "row appended" if out.ok else out.detail

    # 7 Gmail DRAFT. Never sent.
    draft_id = ""
    if verified:
        with tracer.step("draft", "composio-gmail") as box:
            out = actions.create_draft(pin)
            box["ok"] = out.ok
            box["detail"] = f"draft {out.detail}" if out.ok else out.detail
            draft_id = out.detail if out.ok else ""
    else:
        tracer.record("draft", "composio-gmail", 0, True, "skipped, agency not verified")

    # 8 Tell the neighbors.
    slack_ts = ""
    with tracer.step("notify", "composio-slack") as box:
        out = actions.post_to_slack(actions.pin_slack_message(pin))
        box["ok"] = out.ok
        box["detail"] = f"posted {out.detail}" if out.ok else out.detail
        slack_ts = out.detail if out.ok else ""

    # 9 Keep watching.
    with tracer.step("watch", "parallel-monitor") as box:
        monitor_id = research.create_monitor(pin_id, card.category, hint)
        box["ok"] = bool(monitor_id)
        box["detail"] = monitor_id or "monitor skipped, no webhook url configured"

    final_status = "reported" if (verified and draft_id) else status
    return _save(pin_id, tracer, draft_id=draft_id, slack_ts=slack_ts,
                 monitor_id=monitor_id, status=final_status)
