"""Pydantic mirrors of the Parallel Task result shape + our pipeline objects.

Parallel result shape (verified): output.content + output.basis[FieldBasis{field, citations[{url, excerpts}], reasoning, confidence}]
Docs: https://docs.parallel.ai/task-api/guides/access-research-basis
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    url: str
    excerpts: Optional[list[str]] = None


class FieldBasis(BaseModel):
    field: str
    citations: list[Citation] = Field(default_factory=list)
    reasoning: str = ""
    confidence: Optional[str] = None


class TaskOutput(BaseModel):
    type: Literal["json", "text"] = "json"
    content: dict[str, Any]
    basis: list[FieldBasis] = Field(default_factory=list)


class ContestRef(BaseModel):
    kind: Literal["contest", "measure"]
    name: str
    jurisdiction: str
    source_url: str


class Extraction(BaseModel):
    county: str
    city: Optional[str]
    election_name: str
    election_date: str
    official_election_url: str
    contests: list[ContestRef]


class ResearchResult(BaseModel):
    kind: Literal["contest", "measure"]
    run_id: Optional[str] = None
    output: TaskOutput


class GuardrailFinding(BaseModel):
    contest: str
    field: str
    rule: Literal["no_citation", "loaded_language", "missing_side", "llm_flag"]
    detail: str
    action: Literal["dropped", "redacted", "held_back", "annotated"]


class CleanEntry(BaseModel):
    name: str
    kind: Literal["contest", "measure"]
    content: dict[str, Any]
    citations: dict[str, list[str]]  # field -> urls
    held_back: bool = False


class Deadline(BaseModel):
    date: str
    title: str
    source_url: str
    start: Optional[str] = None
    end: Optional[str] = None
    extra_source_url: Optional[str] = None
