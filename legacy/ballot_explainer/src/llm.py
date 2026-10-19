"""Thin OpenAI-compatible chat client (whatever open model the event credits cover).

Uses plain httpx against {OPENAI_COMPATIBLE_BASE_URL}/chat/completions so any
OpenAI-compatible provider works. TODO(cline): swap to the `openai` SDK if preferred.
"""
from __future__ import annotations

import json

import httpx

from . import config


def chat_json(system: str, user: str, timeout: float = 60.0) -> dict:
    if not config.have(config.OPENAI_COMPATIBLE_BASE_URL, config.OPENAI_COMPATIBLE_API_KEY, config.MODEL):
        raise RuntimeError("Set OPENAI_COMPATIBLE_BASE_URL / OPENAI_COMPATIBLE_API_KEY / MODEL in .env")
    r = httpx.post(
        config.OPENAI_COMPATIBLE_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_COMPATIBLE_API_KEY}"},
        json={
            "model": config.MODEL,
            "temperature": 0,
            # Not every OpenAI-compatible server supports response_format; drop it if yours 400s.
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])
