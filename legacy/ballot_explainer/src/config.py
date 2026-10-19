"""Env + paths. Loaded once; every module imports from here."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCHEMAS_DIR = ROOT / "schemas"
CACHE_DIR = ROOT / "cache"
OUT_DIR = ROOT / "out"

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY", "")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "mateo-demo")
COMPOSIO_WEBHOOK_SECRET = os.getenv("COMPOSIO_WEBHOOK_SECRET", "")
COMPOSIO_TRIGGER_ID = os.getenv("COMPOSIO_TRIGGER_ID", "")

PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY", "")
PARALLEL_PROCESSOR = os.getenv("PARALLEL_PROCESSOR", "base")
PARALLEL_MONITOR_WEBHOOK_URL = os.getenv("PARALLEL_MONITOR_WEBHOOK_URL", "")

OPENAI_COMPATIBLE_BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "")
OPENAI_COMPATIBLE_API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
MODEL = os.getenv("MODEL", "")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_DM_CHANNEL = os.getenv("SLACK_DM_CHANNEL", "")

DEMO_COUNTY = os.getenv("DEMO_COUNTY", "contra_costa_walnut_creek_2026-11-03")
DEMO_INVITE_TO = os.getenv("DEMO_INVITE_TO", "")  # address for the Gmail DRAFT; never auto-sent

# "cache" = read cache only (stage-safe). "live" = call APIs, write results back to cache.
MODE = os.getenv("MODE", "cache")


def cache_path(county: str | None = None) -> Path:
    return CACHE_DIR / f"{county or DEMO_COUNTY}.json"


def have(*keys: str) -> bool:
    return all(bool(k) for k in keys)
