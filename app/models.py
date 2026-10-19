"""Pin + routing card schemas. Pydantic validates every LLM output before it touches storage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Category is a plain string, not a Literal, because the vocabulary is owned by the domain
# pack rather than by this module. Validation happens at the pipeline boundary against the
# pack's own `categories`, which is the only place that knows which domain is running.
# Hardcoding the 311 vocabulary here made a second domain impossible to add.
Category = str
CATEGORIES: tuple[str, ...] = (
    "streetlight",
    "road_pothole",
    "sidewalk_accessibility",
    "graffiti",
    "illegal_dumping",
    "tree",
    "transit_stop",
    "water_sewer",
    "noise",
    "parking",
    "other",
)

Severity = Literal["low", "medium", "high"]
Status = Literal["routing", "routed", "reported", "acknowledged", "resolved", "needs_human"]
AlreadyReported = Literal["yes", "likely", "unknown"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Source(BaseModel):
    title: str
    url: str


class TraceStep(BaseModel):
    """One pipeline step, shown in the UI as the agent trace. Judges see which sponsor did what."""

    step: str
    tool: str
    ms: int
    ok: bool
    detail: str = ""


class RoutingCard(BaseModel):
    """Validated LLM output. No source, no claim: agency/channel_url need a citation."""

    category: Category = "other"
    severity: Severity = "medium"
    summary: str = ""
    agency: str = ""
    channel: str = ""
    channel_url: str = ""
    already_reported: AlreadyReported = "unknown"
    sources: list[Source] = Field(default_factory=list)
    draft_subject: str = ""
    draft_body: str = ""


class PinCreate(BaseModel):
    lat: float
    lng: float
    note: str
    reporter: str = "neighbor"


class Pin(BaseModel):
    """Field order here is also the Google Sheet column order."""

    id: str
    created_at: str
    updated_at: str
    lat: float
    lng: float
    address_hint: str = ""
    note: str = ""
    category: Category = "other"
    severity: Severity = "medium"
    agency: str = ""
    channel: str = ""
    channel_url: str = ""
    already_reported: AlreadyReported = "unknown"
    status: Status = "routing"
    sources: list[Source] = Field(default_factory=list)
    draft_id: str = ""
    slack_ts: str = ""

    # Not Sheet columns: demo + UI extras.
    # Which domain pack routed this item. Defaults to the 311 pillar so every pin written
    # before domain packs existed still loads and behaves identically.
    domain: str = "civic_311"
    reporter: str = "neighbor"
    seed: bool = False
    summary: str = ""
    emergency: bool = False
    trace: list[TraceStep] = Field(default_factory=list)
    updates: list[dict[str, Any]] = Field(default_factory=list)
    draft_subject: str = ""
    draft_body: str = ""
    needs_human_reason: str = ""
    monitor_id: str = ""


SHEET_COLUMNS: tuple[str, ...] = (
    "id",
    "created_at",
    "updated_at",
    "lat",
    "lng",
    "address_hint",
    "note",
    "category",
    "severity",
    "agency",
    "channel",
    "channel_url",
    "already_reported",
    "status",
    "sources",
    "draft_id",
    "slack_ts",
)


class BriefItem(BaseModel):
    kind: Literal["new_pin", "status_change", "civic_date"]
    text: str
    pin_id: Optional[str] = None
    url: str = ""
