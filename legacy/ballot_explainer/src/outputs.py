"""Step 4: outputs via Composio. Nothing is ever auto-sent to another person.

- Google Doc  "Your Ballot, Explained"  (GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN: title, markdown_text)
- Google Calendar deadlines             (GOOGLECALENDAR_CREATE_EVENT: summary, start_datetime/end_datetime or
                                          start_date/end_date, timezone, description, send_updates="none")
- Gmail DRAFT inviting friends          (GMAIL_CREATE_EMAIL_DRAFT: recipient_email, subject, body)  <- draft only
- Slack: posts only to the user's OWN DM (SLACK_SEND_MESSAGE: channel, markdown_text) or SLACK_WEBHOOK_URL.

Slugs + params verified 2026-10-19 on https://docs.composio.dev/toolkits/{googledocs,googlecalendar,gmail,slack}
Session API: https://docs.composio.dev/docs/quickstart  ->  composio.create(user_id=...) ; session.execute(slug, arguments=...)
Package is `composio` (NOT legacy `composio-core`).
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx

from . import config
from .models import CleanEntry, Deadline

DOC_TITLE = "Your Ballot, Explained"
TZ = "America/Los_Angeles"


# ---------- rendering (ready, local) ----------

def _link(urls: list[str]) -> str:
    return " ".join(f"[[{i+1}]]({u})" for i, u in enumerate(urls[:3]))


def render_markdown(entries: list[CleanEntry], deadlines: list[Deadline], drop_boxes: list[dict],
                    county: str, city: str | None, election_url: str) -> str:
    L = [f"# {DOC_TITLE}", f"**{city + ', ' if city else ''}{county} County - November 3, 2026 General Election**", "",
         "> Nonpartisan. Every claim links to its source. This guide never recommends a candidate or a vote.",
         f"> Official source: {election_url}", "", "## Key dates"]
    for d in deadlines:
        t = f" {d.start}-{d.end}" if d.start else ""
        L.append(f"- **{d.date}{t}** - {d.title} ([source]({d.source_url}))")
    L += ["", "## Drop boxes near you (open 24/7 until Nov 3, 8:00 pm)"] + [f"- {b['name']}, {b['address']}" for b in drop_boxes]
    for e in entries:
        c, cite = e.content, e.citations
        L += ["", f"## {c.get('contest_name') or c.get('measure_id') or e.name}"]
        if e.held_back:
            L.append("_Held back: we could not verify both official arguments for this measure yet._")
            continue
        if e.kind == "contest":
            if "what_the_office_controls" in c:
                L.append(f"**What this office does:** {c['what_the_office_controls']} {_link(cite.get('what_the_office_controls', []))}")
            L.append(f"**Vote for:** {c.get('vote_for')}  |  **Contested:** {'yes' if c.get('is_contested') else 'no'}")
            for cand in c.get("candidates", []):
                extra = f" - {cand['ballot_designation']}" if cand.get("ballot_designation") else ""
                L.append(f"- **{cand['name']}**{extra}")
                L += [f"  - {p}" for p in cand.get("stated_priorities", [])]
            if c.get("neutral_summary"):
                L.append(f"\n{c['neutral_summary']} {_link(cite.get('neutral_summary', []))}")
        else:
            L.append(f"> {c.get('ballot_question','')}")
            for k, label in (("plain_language_summary", "In plain language"), ("yes_means", "A YES vote means"),
                             ("no_means", "A NO vote means"), ("fiscal_impact", "Cost"), ("vote_threshold", "To pass")):
                if c.get(k):
                    L.append(f"**{label}:** {c[k]} {_link(cite.get(k, []))}")
            for k, label in (("argument_for", "Supporters"), ("argument_against", "Opponents")):
                a = c.get(k) or {}
                if a.get("summary"):
                    by = f" _(signed by {', '.join(a['signers'][:3])})_" if a.get("signers") else ""
                    L.append(f"**{label}:** {a['summary']}{by} {_link(cite.get(k, []))}")
            L.append(f"[Full text, impartial analysis, and arguments]({c.get('official_source_url','')})")
    # blank line after every block so Google Docs / Markdown render separate paragraphs
    spaced = []
    for line in L:
        spaced.append(line)
        if line.startswith(("**", "> ", "[Full", "_Held")):
            spaced.append("")
    return "\n".join(spaced) + "\n"


def invite_text(doc_url: str | None, county: str, city: str | None) -> tuple[str, str]:
    subj = "Quick nonpartisan guide to our Nov 3 ballot"
    body = (f"Hey! I put together a plain-language, nonpartisan guide to what's on the {city or county} ballot, "
            f"with links to the official county sources for every claim.\n\n{doc_url or '[doc link]'}\n\n"
            "Drop boxes close Nov 3 at 8pm. No recommendations in it, just what each race and measure does.")
    return subj, body


# ---------- Composio (stubbed until COMPOSIO_API_KEY + connected accounts) ----------

def _session():
    from composio import Composio

    composio = Composio(api_key=config.COMPOSIO_API_KEY)
    # Restrict to the four toolkits we use; accounts must be connected beforehand (scripts/connect_accounts.py).
    return composio.create(user_id=config.COMPOSIO_USER_ID,
                           toolkits=["googledocs", "googlecalendar", "gmail", "slack"])


def _ok(resp) -> dict:
    # TODO(cline): confirm response shape of session.execute (ToolRouterSessionExecuteResponse) on first live call
    d = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    return d


def create_doc(markdown: str) -> dict:
    s = _session()
    return _ok(s.execute("GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN", arguments={"title": DOC_TITLE, "markdown_text": markdown}))


def add_calendar(deadlines: list[Deadline]) -> list[dict]:
    s = _session()
    out = []
    for d in deadlines:
        args = {"summary": f"Vote: {d.title}"[:250], "description": f"Source: {d.source_url}",
                "timezone": TZ, "calendar_id": "primary", "send_updates": "none", "create_meeting_room": False}
        if d.start and d.end:
            args |= {"start_datetime": f"{d.date}T{d.start}:00", "end_datetime": f"{d.date}T{d.end}:00"}
        else:
            nxt = (date.fromisoformat(d.date) + timedelta(days=1)).isoformat()
            args |= {"start_date": d.date, "end_date": nxt}  # all-day, end exclusive
        out.append(_ok(s.execute("GOOGLECALENDAR_CREATE_EVENT", arguments=args)))
    return out


def create_invite_draft(doc_url: str | None, county: str, city: str | None, to: str | None = None) -> dict:
    """Gmail DRAFT only. The human reviews and hits send. Say this out loud in the demo."""
    subj, body = invite_text(doc_url, county, city)
    args = {"subject": subj, "body": body}
    if to or config.DEMO_INVITE_TO:
        args["recipient_email"] = to or config.DEMO_INVITE_TO
    return _ok(_session().execute("GMAIL_CREATE_EMAIL_DRAFT", arguments=args))


def slack_self_dm(markdown_text: str) -> dict:
    """Post to the user's OWN DM / incoming webhook only (monitor alerts, invite text to forward)."""
    if config.SLACK_WEBHOOK_URL:
        r = httpx.post(config.SLACK_WEBHOOK_URL, json={"text": markdown_text}, timeout=15)
        return {"status": r.status_code}
    if not config.SLACK_DM_CHANNEL:
        raise RuntimeError("Set SLACK_WEBHOOK_URL or SLACK_DM_CHANNEL (a D... id from SLACK_OPEN_DM)")
    return _ok(_session().execute("SLACK_SEND_MESSAGE", arguments={"channel": config.SLACK_DM_CHANNEL,
                                                                  "markdown_text": markdown_text}))
