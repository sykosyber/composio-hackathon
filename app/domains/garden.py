"""Pillar 2 (stub): community and urban gardening.

This pack exists to prove the domain seam with a second, deliberately different example.
It is NOT a shipped feature. It is a fixture: if the pipeline can run this without a single
`if domain ==` branch, the abstraction holds. If it cannot, the seam is wrong.

What makes it a useful test is precisely that it disagrees with the 311 pack:

  - It has no "agency" and no official reporting URL, so `verify` cannot be a citation
    check on a .gov domain. A garden task is verified by having a named garden, not by a
    government source.
  - It never drafts an email to an authority. Its actions are a shared calendar and a
    channel post to the people who actually tend the plot.
  - The thing being routed is a request for help, not a complaint about a defect.

That disagreement is the point. See docs/PHASE1_SUBSTRATE.md, "Risks".
"""
from __future__ import annotations

from typing import Any

from ..models import RoutingCard
from .base import ActionSpec, match_rules

CATEGORIES: tuple[str, ...] = (
    "watering", "weeding", "planting", "harvest_surplus", "repair", "plot_request", "other",
)

RULES: list[tuple[str, str]] = [
    (r"water|irrigat|dry|drought|hose", "watering"),
    (r"weed|overgrown|bindweed|clear the bed", "weeding"),
    (r"plant|seedling|transplant|sow|seed", "planting"),
    (r"harvest|surplus|too many|giving away|glut", "harvest_surplus"),
    (r"fence|gate|bed|shed|tool|broken|repair", "repair"),
    (r"plot|waitlist|join|space available|new member", "plot_request"),
]

SEVERITY_RULES: list[tuple[str, str]] = [
    (r"urgent|dying|wilting|today|heat ?wave", "high"),
    (r"whenever|no rush|sometime", "low"),
]


class GardenPack:
    slug = "garden"
    label = "Community gardens"
    categories = CATEGORIES
    default_category = "other"

    def classify(self, note: str) -> str:
        return match_rules(note, RULES, self.default_category)

    def severity(self, note: str) -> str:
        return match_rules(note, SEVERITY_RULES, "medium")

    def research_queries(self, category: str) -> tuple[str, list[str]]:
        label = category.replace("_", " ")
        objective = (
            f"Find local community gardening guidance for {label} in this region: growing "
            "calendars, local extension service advice, and nearby community gardens."
        )
        return objective, [f"community garden {label} guidance local extension service"]

    def dedupe_queries(self, category: str, where: str) -> tuple[str, list[str]]:  # noqa: ARG002
        # category is part of the contract but irrelevant here: the duplicate check for a
        # garden is about place, not about what kind of task it is.
        objective = f"Find community gardens and shared growing space near {where}."
        return objective, [f"community garden near {where}"]

    def verify(self, card: RoutingCard) -> tuple[bool, str]:
        """A garden task needs a named garden, not a government citation.

        Deliberately different from the 311 gate. This is the assertion that the seam
        does not assume every domain verifies against an official source.
        """
        if not card.agency.strip():
            return False, "Couldn't identify which garden this belongs to"
        return True, ""

    def actions(self, item: Any, verified: bool) -> list[ActionSpec]:  # noqa: ARG002
        # No Gmail draft. Nobody writes to an authority about a watering rota.
        return [
            ActionSpec(step="ledger", tool="composio-sheets", kind="sheet_append"),
            ActionSpec(step="notify", tool="composio-slack", kind="slack_post"),
        ]


PACK = GardenPack()
