"""Pillar 0: neighborhood issue reporting through a city 311 service.

This is the reference domain pack. The logic here was previously spread across
`app/models.py`, `app/llm.py`, `app/research.py` and `app/guardrails.py`. Behavior is
unchanged, which `scripts/smoke.py` verifies.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .. import config
from ..models import RoutingCard
from .base import ActionSpec, match_rules

CATEGORIES: tuple[str, ...] = (
    "streetlight", "road_pothole", "sidewalk_accessibility", "graffiti",
    "illegal_dumping", "tree", "transit_stop", "water_sewer", "noise", "parking", "other",
)

# First match wins, so order is deliberate: specific before general.
RULES: list[tuple[str, str]] = [
    (r"street ?light|lamp ?post|light (is )?out|dark at night", "streetlight"),
    (r"pothole|road (is )?crack|pavement|sinkhole", "road_pothole"),
    (r"sidewalk|curb ?ramp|wheelchair|accessib|tripping", "sidewalk_accessibility"),
    (r"graffiti|tag(ged|ging)?\b|spray ?paint", "graffiti"),
    (r"dumping|mattress|couch|trash pile|debris|abandoned (sofa|furniture)", "illegal_dumping"),
    (r"tree|branch|limb|canopy|root", "tree"),
    (r"bus (stop|shelter)|muni|transit|bart|shelter glass", "transit_stop"),
    (r"water|sewer|hydrant|leak|flood|drain|catch basin", "water_sewer"),
    (r"noise|loud|music|alarm", "noise"),
    (r"parking|blocked driveway|double ?park|abandoned (car|vehicle)", "parking"),
]

SEVERITY_RULES: list[tuple[str, str]] = [
    (r"danger|unsafe|hazard|exposed wire|live wire|deep|injur|"
     r"blocking the (whole )?sidewalk|flood", "high"),
    (r"minor|small|cosmetic|faded|slight", "low"),
]

CATEGORY_QUERIES: dict[str, list[str]] = {
    "streetlight": ["San Francisco report streetlight outage 311", "SFPUC streetlight repair report"],
    "road_pothole": ["San Francisco report pothole 311 SF Public Works",
                     "SF Public Works street repair request"],
    "sidewalk_accessibility": ["San Francisco report damaged sidewalk 311 Public Works",
                               "San Francisco curb ramp accessibility request"],
    "graffiti": ["San Francisco report graffiti 311 Public Works", "SF graffiti removal request"],
    "illegal_dumping": ["San Francisco report illegal dumping 311 Recology",
                        "SF bulky item pickup request"],
    "tree": ["San Francisco report street tree problem 311 Public Works urban forestry",
             "SF StreetTreeSF maintenance request"],
    "transit_stop": ["San Francisco Muni bus shelter damage report SFMTA",
                     "SFMTA report transit stop problem"],
    "water_sewer": ["San Francisco report water leak sewer SFPUC",
                    "SFPUC report flooding clogged drain"],
    "noise": ["San Francisco noise complaint 311 report", "SF noise ordinance complaint who to call"],
    "parking": ["San Francisco report blocked driveway abandoned vehicle SFMTA 311",
                "SFMTA parking enforcement request"],
    "other": ["San Francisco 311 report a problem city services", "SF 311 service request categories"],
}

TRUSTED_SUFFIXES = (".gov", ".ca.gov", ".org", ".us", ".com")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


class Civic311Pack:
    slug = "civic_311"
    label = "Neighborhood issues"
    categories = CATEGORIES
    default_category = "other"

    def classify(self, note: str) -> str:
        return match_rules(note, RULES, self.default_category)

    def severity(self, note: str) -> str:
        return match_rules(note, SEVERITY_RULES, "medium")

    def research_queries(self, category: str) -> tuple[str, list[str]]:
        objective = (
            f"Identify the exact {config.DEMO_CITY} city agency responsible for this issue and "
            f"the official reporting channel with its URL. Issue category: {category}. "
            "Prefer official city government pages such as sf.gov and 311."
        )
        return objective, CATEGORY_QUERIES.get(category, CATEGORY_QUERIES["other"])

    def dedupe_queries(self, category: str, where: str) -> tuple[str, list[str]]:
        where = where or config.DEMO_CITY
        label = category.replace("_", " ")
        objective = (
            f"Find out whether a {label} problem near {where} in {config.DEMO_CITY} has already "
            "been reported recently, for example in 311 open data, an outage map, or local news."
        )
        return objective, [
            f"{where} {label} 311 report {config.DEMO_CITY}",
            f"{config.DEMO_CITY} {label} near {where} news recent",
        ]

    def verify(self, card: RoutingCard) -> tuple[bool, str]:
        """No source, no claim. An agency and a reporting URL both need a citation."""
        if not card.agency.strip():
            return False, "Couldn't verify the right agency"
        if not card.channel_url.strip():
            return False, "Couldn't verify a reporting channel"
        host = _host(card.channel_url)
        if not host or not host.endswith(TRUSTED_SUFFIXES):
            return False, "Couldn't verify a reporting channel on an official domain"
        cited = {_host(s.url) for s in card.sources if s.url}
        if not cited:
            return False, "Couldn't verify the right agency, no citation returned"
        if host not in cited:
            return False, "Reporting link was not backed by any cited source"
        return True, ""

    def actions(self, item: Any, verified: bool) -> list[ActionSpec]:  # noqa: ARG002
        # item and verified are part of the DomainPack contract. This pack's action list
        # is static; the pipeline applies `requires_verified` itself.
        return [
            ActionSpec(step="ledger", tool="composio-sheets", kind="sheet_append"),
            # Draft only, and only when the agency is verified. The agent never sends.
            ActionSpec(step="draft", tool="composio-gmail", kind="gmail_draft",
                       requires_verified=True),
            ActionSpec(step="notify", tool="composio-slack", kind="slack_post"),
        ]


PACK = Civic311Pack()
