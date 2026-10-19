"""Step 2: Parallel Task fan-out, one run per contest/measure, JSON schema output + per-field citations.

Docs (verified 2026-10-19):
- Quickstart: https://docs.parallel.ai/task-api/task-quickstart
    client.task_run.create(input=..., task_spec={...}, processor="base") -> TaskRun(run_id)
    client.task_run.result(run_id, api_timeout=3600) -> TaskRunResult(.output.content, .output.basis)
- JSON schema rules: https://docs.parallel.ai/task-api/guides/specify-a-task
    root must be object; ALL properties required; additionalProperties:false; optional => ["type","null"];
    no format/min*/max*/pattern; depth <= 5; <= 100 properties; spec+input <= 25,000 chars.
- Research basis: https://docs.parallel.ai/task-api/guides/access-research-basis
- Processors (lite/base/core/pro/ultra): https://docs.parallel.ai/task-api/guides/choose-a-processor
- Task Groups (alternative to asyncio fan-out): https://docs.parallel.ai/task-api/group-api

STAGE RULE: never run all contests live. Run ONE live (DEMO_LIVE_CONTEST), load the rest from cache.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from . import cache, config
from .models import ContestRef, ResearchResult


def _schema(kind: str) -> dict:
    return json.loads((config.SCHEMAS_DIR / f"{kind}.schema.json").read_text())


def task_spec(kind: str) -> dict:
    return {"output_schema": {"type": "json", "json_schema": _schema(kind)}}


def task_input(ref: ContestRef, county: str, city: str | None, election: str) -> str:
    return (
        f"{ref.kind.upper()}: {ref.name}\nJurisdiction: {ref.jurisdiction}\n"
        f"Election: {election}, {city + ', ' if city else ''}{county} County, California.\n"
        f"Official source to start from: {ref.source_url}\n"
        "Prefer official county/city/state election sources. Be strictly nonpartisan: describe, attribute, never recommend."
    )


def _to_dict(output: Any) -> dict:
    # SDK objects are pydantic models; model_dump() gives {type, content, basis[...]}
    return output.model_dump() if hasattr(output, "model_dump") else dict(output)


async def research_one(ref: ContestRef, county: str, city: str | None, election: str) -> ResearchResult:
    from parallel import AsyncParallel  # pip install parallel-web

    client = AsyncParallel(api_key=config.PARALLEL_API_KEY)
    run = await client.task_run.create(
        input=task_input(ref, county, city, election),
        task_spec=task_spec(ref.kind),
        processor=config.PARALLEL_PROCESSOR,
        metadata={"contest": ref.name[:200]},
    )
    result = await client.task_run.result(run.run_id, api_timeout=900)
    rr = ResearchResult(kind=ref.kind, run_id=run.run_id, output=_to_dict(result.output))
    cache.put_research(ref.name, rr.model_dump())  # cache EVERY result
    return rr


async def research_all(refs: list[ContestRef], county: str, city: str | None, election: str,
                       live_names: set[str] | None = None) -> dict[str, ResearchResult]:
    """Fan out. Names in live_names hit Parallel (when MODE=live); everything else loads from cache."""
    cached = cache.load().get("research", {})
    out: dict[str, ResearchResult] = {}
    live = [r for r in refs if config.MODE == "live" and (live_names is None or r.name in live_names)]
    for r in refs:
        if r not in live and r.name in cached:
            out[r.name] = ResearchResult.model_validate(cached[r.name])
    if live:
        results = await asyncio.gather(*(research_one(r, county, city, election) for r in live), return_exceptions=True)
        for r, res in zip(live, results):
            if isinstance(res, Exception):
                print(f"  ! live research failed for {r.name}: {res!r}; falling back to cache")
                if r.name in cached:
                    out[r.name] = ResearchResult.model_validate(cached[r.name])
            else:
                out[r.name] = res
    return out
