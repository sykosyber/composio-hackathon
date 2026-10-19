"""Step timing + logging. Each pipeline step is logged to the console and shown in the UI."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from .models import TraceStep


class Tracer:
    def __init__(self, pin_id: str) -> None:
        self.pin_id = pin_id
        self.steps: list[TraceStep] = []

    @contextmanager
    def step(self, step: str, tool: str) -> Iterator[dict]:
        started = time.perf_counter()
        box: dict = {"ok": True, "detail": ""}
        try:
            yield box
        except Exception as exc:
            box["ok"] = False
            box["detail"] = f"{type(exc).__name__}: {exc}"[:200]
            raise
        finally:
            ms = int((time.perf_counter() - started) * 1000)
            rec = TraceStep(step=step, tool=tool, ms=ms, ok=bool(box["ok"]), detail=str(box["detail"])[:200])
            self.steps.append(rec)
            flag = "ok " if rec.ok else "FAIL"
            print(f"[{self.pin_id}] {flag} {step:<14} {tool:<18} {ms:>5}ms {rec.detail}")

    def record(self, step: str, tool: str, ms: int, ok: bool, detail: str = "") -> None:
        rec = TraceStep(step=step, tool=tool, ms=ms, ok=ok, detail=detail[:200])
        self.steps.append(rec)
        print(f"[{self.pin_id}] {'ok ' if ok else 'FAIL'} {step:<14} {tool:<18} {ms:>5}ms {rec.detail}")
