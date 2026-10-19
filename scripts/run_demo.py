#!/usr/bin/env python3
"""Stage-safe demo. Loads the cache and prints every pipeline stage. No API keys needed in default mode.

  python scripts/run_demo.py                     # cache only, guardrail demo on
  python scripts/run_demo.py --no-inject         # clean run
  MODE=live python scripts/run_demo.py --live "Measure T"   # research ONE contest live, rest cached
  python scripts/run_demo.py --push              # also create Doc/Calendar/Gmail DRAFT via Composio
  python scripts/run_demo.py --monitors          # also create Parallel monitors
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pipeline  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--no-inject", action="store_true", help="skip the synthetic biased sentences")
ap.add_argument("--live", action="append", default=None, help="contest name to research live (repeatable)")
ap.add_argument("--push", action="store_true", help="write Doc/Calendar/Gmail draft via Composio")
ap.add_argument("--monitors", action="store_true", help="create Parallel monitors")
a = ap.parse_args()

res = pipeline.run(live_contests=set(a.live) if a.live else set(), inject=not a.no_inject,
                   push=a.push, monitors=a.monitors)
print(f"\nDone. Open {res['markdown_path']}")
