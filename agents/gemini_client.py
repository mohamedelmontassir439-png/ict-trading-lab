"""
Shared Google Gen AI client + JSON generation for all agents (orchestrator, council, etc.).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

_log = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
    _GENAI_IMPORT_OK = True
except ImportError:
    _GENAI_IMPORT_OK = False
    genai = None  # type: ignore
    types = None  # type: ignore
    _log.warning("google-genai not installed. Run: py -m pip install google-genai")

_client: Optional[Any] = None


def get_genai_client():
    """Returns a configured Client or None if unavailable."""
    global _client
    if not _GENAI_IMPORT_OK:
        return None
    key = (config.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key:
        return None
    if _client is None:
        _client = genai.Client(api_key=key)
    return _client


def gemini_model_name() -> str:
    return getattr(config, "GEMINI_MODEL", "gemini-2.5-flash-lite")


def generate_json_response(
    prompt: str,
    *,
    temperature: float = 0.25,
    max_output_tokens: int = 900,
) -> dict[str, Any]:
    """
    One-shot JSON object from Gemini. Returns {} on total failure.
    """
    client = get_genai_client()
    if client is None or types is None:
        return {}

    try:
        response = client.models.generate_content(
            model=gemini_model_name(),
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
            ),
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rstrip("`").strip()
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log.warning("Gemini JSON generation failed: %s", e)
        return {}


def strip_code_fence_json(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    return text
