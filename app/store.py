"""data/pins.json is the source of truth, so the map always works even if every API is down.

The Google Sheet is a mirror, written best effort by app/actions.py.
"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from typing import Optional

from . import config
from .models import Pin, now_iso

_LOCK = threading.Lock()


def _read_raw() -> list[dict]:
    if not config.PINS_PATH.exists():
        reset()
    try:
        return json.loads(config.PINS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_raw(rows: list[dict]) -> None:
    tmp = config.PINS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(config.PINS_PATH)


def all_pins() -> list[Pin]:
    out: list[Pin] = []
    for row in _read_raw():
        try:
            out.append(Pin.model_validate(row))
        except Exception as exc:
            print(f"[store] skipping bad pin row: {exc!r}")
    out.sort(key=lambda p: p.created_at, reverse=True)
    return out


def get(pin_id: str) -> Optional[Pin]:
    for p in all_pins():
        if p.id == pin_id:
            return p
    return None


def new_id() -> str:
    return uuid.uuid4().hex[:6]


def add(pin: Pin) -> Pin:
    with _LOCK:
        rows = _read_raw()
        rows.append(pin.model_dump())
        _write_raw(rows)
    return pin


def update(pin_id: str, **fields) -> Optional[Pin]:
    """Patch a pin in place. Returns the updated pin, or None if the id is unknown.

    Unknown field names are a programming error, not user input, so they fail loudly
    instead of being silently dropped into a dict nobody reads again.
    """
    unknown = set(fields) - set(Pin.model_fields)
    if unknown:
        raise ValueError(f"unknown Pin field(s): {sorted(unknown)}")
    with _LOCK:
        rows = _read_raw()
        for i, row in enumerate(rows):
            if row.get("id") != pin_id:
                continue
            row.update({k: v for k, v in fields.items() if v is not None})
            row["updated_at"] = now_iso()
            try:
                pin = Pin.model_validate(row)
            except Exception as exc:
                print(f"[store] update rejected for {pin_id}: {exc!r}")
                return None
            rows[i] = pin.model_dump()
            _write_raw(rows)
            return pin
    return None


def append_update(pin_id: str, entry: dict) -> Optional[Pin]:
    pin = get(pin_id)
    if not pin:
        return None
    return update(pin_id, updates=[*pin.updates, {"at": now_iso(), **entry}])


def reset() -> int:
    """Restore the seeded demo data. Backs the live file for POST /demo/reset."""
    if config.SEED_PATH.exists():
        shutil.copyfile(config.SEED_PATH, config.PINS_PATH)
    else:
        config.PINS_PATH.write_text("[]", encoding="utf-8")
    return len(_read_raw())
