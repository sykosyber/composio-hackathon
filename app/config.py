"""Env + paths for Altruistic Agent. Loaded once; every module imports from here.

Reused from the legacy ballot explainer (legacy/ballot_explainer/src/config.py) and
re-pointed at the neighborhood pin-and-route product.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
WEB_DIR = ROOT / "web"
PINS_PATH = DATA_DIR / "pins.json"
SEED_PATH = DATA_DIR / "pins.seed.json"

DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---- Composio ----
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY", "")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "mateo-demo")
COMPOSIO_WEBHOOK_SECRET = os.getenv("COMPOSIO_WEBHOOK_SECRET", "")
COMPOSIO_TRIGGER_ID = os.getenv("COMPOSIO_TRIGGER_ID", "")
SHEET_ID = os.getenv("SHEET_ID", "")
SHEET_RANGE = os.getenv("SHEET_RANGE", "Pins!A:Q")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")
AGENCY_DRAFT_TO = os.getenv("AGENCY_DRAFT_TO", "")

# ---- Parallel ----
PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY", "")
PARALLEL_SEARCH_MODE = os.getenv("PARALLEL_SEARCH_MODE", "fast")
PARALLEL_MONITOR_WEBHOOK_URL = os.getenv("PARALLEL_MONITOR_WEBHOOK_URL", "")

# ---- LLM: open-source model behind an OpenAI-compatible endpoint ----
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

# ---- Demo ----
# 1 = serve cached Parallel/LLM results first so the stage demo is fast and identical every run.
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"
DEMO_CITY = os.getenv("DEMO_CITY", "San Francisco")

# ---- Timeouts (seconds). Every external call gets one. ----
SEARCH_TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "15"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
COMPOSIO_TIMEOUT = float(os.getenv("COMPOSIO_TIMEOUT", "15"))


def have(*keys: str) -> bool:
    return all(bool(k) for k in keys)
