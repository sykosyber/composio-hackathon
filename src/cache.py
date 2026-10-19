"""JSON cache. Every live result is written here so the stage demo never waits on an API."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config


def load(county: str | None = None) -> dict[str, Any]:
    p = config.cache_path(county)
    if not p.exists():
        raise FileNotFoundError(f"No cache at {p}. Run in MODE=live once, or copy the seed.")
    return json.loads(p.read_text())


def save(data: dict[str, Any], county: str | None = None) -> Path:
    p = config.cache_path(county)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return p


def put_research(name: str, result: dict[str, Any], county: str | None = None) -> None:
    data = load(county)
    data.setdefault("research", {})[name] = result
    save(data, county)
