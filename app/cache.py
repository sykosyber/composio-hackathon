"""Hash-keyed JSON cache in data/cache/.

Every Parallel and LLM response is cached by a hash of its input. With DEMO_MODE=1 the
cache is served first, so the live demo is fast and identical on every run.
Extends the simple cache from the legacy ballot explainer.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from . import config


def key(namespace: str, payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(blob.encode()).hexdigest()[:20]
    return f"{namespace}_{digest}"


def get(namespace: str, payload: Any) -> Optional[Any]:
    path = config.CACHE_DIR / f"{key(namespace, payload)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())["value"]
    except Exception:
        return None


def put(namespace: str, payload: Any, value: Any) -> None:
    path = config.CACHE_DIR / f"{key(namespace, payload)}.json"
    try:
        path.write_text(
            json.dumps({"namespace": namespace, "input": payload, "value": value},
                       indent=2, ensure_ascii=False, default=str)
        )
    except Exception as exc:  # cache is best effort, never fail the pipeline
        print(f"[cache] write failed for {namespace}: {exc!r}")
