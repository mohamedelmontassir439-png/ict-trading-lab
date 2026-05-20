"""
AI Specialist Council — multiple expert perspectives in ONE Gemini JSON call.

Virtual sub-agents (same model, structured output):
  • liquidity_specialist — sweeps, stop-hunts, fragile highs/lows
  • regime_specialist      — TREND / RANGE / CHOP + conviction
  • execution_specialist — spread/slippage/session realism (crypto vs index)
  • risk_specialist       — portfolio heat, overtrading, RR sanity
  • synthesis             — hard_veto, council_score, actionable summary

Use ENABLE_AI_COUNCIL in config; hard_veto skips the main orchestrator to save latency/cost.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from agents.gemini_client import generate_json_response
from agents.ict_agent import ICTAnalysis
from database.models import get_open_trades, log_agent

_log = logging.getLogger(__name__)

COUNCIL_PROMPT = """
You are a panel of four independent trading specialists PLUS a chairperson who synthesizes.
All judgments must be grounded ONLY in the JSON facts provided (no invented news).

Output ONE JSON object with EXACTLY these keys:
{
  "liquidity_specialist": {
    "score": <int 1-10>,
    "verdict": "CLEAN" | "MIXED" | "DANGEROUS",
    "note": "<one sentence>"
  },
  "regime_specialist": {
    "label": "TREND" | "RANGE" | "CHOP",
    "confidence": <int 1-10>,
    "note": "<one sentence>"
  },
  "execution_specialist": {
    "score": <int 1-10>,
    "verdict": "OK" | "CAUTION" | "POOR",
    "note": "<one sentence about session/liquidity for this market type>"
  },
  "risk_specialist": {
    "score": <int 1-10>,
    "verdict": "OK" | "ELEVATED" | "BLOCK",
    "note": "<one sentence about heat, size, or correlation>"
  },
  "synthesis": {
    "hard_veto": <true|false>,
    "council_score": <int 1-10 weighted blend of specialists>,
    "summary": "<2 sentences max>"
  }
}

Rules:
- hard_veto=true ONLY if execution_specialist.verdict is POOR, OR risk_specialist.verdict is BLOCK,
  OR liquidity_specialist.verdict is DANGEROUS with score<=3, OR regime is CHOP with confidence>=8.
- council_score should reflect overall trade quality (higher = more aligned).
- Be conservative: paper system must not overtrade marginal setups.
""".strip()


def _digest(df: pd.DataFrame, label: str) -> dict[str, Any]:
    if df is None or df.empty or len(df) < 3:
        return {"label": label, "bars": 0}
    c = df["close"].astype(float)
    hi = df["high"].astype(float)
    lo = df["low"].astype(float)
    n = min(24, len(c))
    move = float((c.iloc[-1] / c.iloc[-n] - 1.0) * 100.0)
    tail = min(14, len(hi))
    rng_series = (hi - lo) / c.replace(0, 1e-12)
    avg_rng = float(rng_series.iloc[-tail:].mean() * 100.0)
    return {
        "label": label,
        "bars": int(len(df)),
        "last_close": round(float(c.iloc[-1]), 6),
        "pct_move_last_bars": round(move, 4),
        "avg_hl_range_pct": round(avg_rng, 4),
    }


def run_specialist_council(
    analysis: ICTAnalysis,
    signal: dict[str, Any],
    kill_zone: str,
    df_htf: pd.DataFrame,
    df_ltf: pd.DataFrame,
) -> dict[str, Any]:
    """
    Returns specialist dict; on failure returns safe neutral object (no veto).
    """
    if not getattr(config, "ENABLE_AI_COUNCIL", True):
        return _neutral_council("Council disabled in config")

    sym = config.display_symbol(analysis.symbol) if analysis.market == "forex" else analysis.symbol
    open_n = len(get_open_trades())

    payload = {
        "display_symbol": sym,
        "raw_symbol": analysis.symbol,
        "market": analysis.market,
        "kill_zone": kill_zone,
        "ict": {
            "bias": analysis.bias,
            "structure": analysis.structure,
            "setup_score": int(analysis.setup_score),
            "in_premium": bool(analysis.in_premium),
            "in_discount": bool(analysis.in_discount),
            "equilibrium": round(float(analysis.equilibrium), 6),
            "current_price": round(float(analysis.current_price), 6),
            "ob_count": len(analysis.order_blocks),
            "fvg_count": len(analysis.fvgs),
            "liq_levels": len(analysis.liquidity),
        },
        "proposed_signal": {
            "direction": signal.get("direction"),
            "entry": float(signal.get("entry") or 0),
            "sl": float(signal.get("sl") or 0),
            "tp": float(signal.get("tp") or 0),
            "risk_usd": float(signal.get("risk_usd") or 0),
            "setup_type": signal.get("setup_type"),
        },
        "portfolio": {"open_trades": open_n, "max_concurrent": config.MAX_CONCURRENT},
        "bars_digest": {
            "htf": _digest(df_htf, "HTF"),
            "ltf": _digest(df_ltf, "LTF"),
        },
    }

    prompt = (
        f"{COUNCIL_PROMPT}\n\n"
        "FACTS (JSON):\n```json\n"
        f"{json.dumps(payload, indent=2, default=str)}\n```"
    )

    result = generate_json_response(
        prompt, temperature=0.2, max_output_tokens=900,
    )
    if not result or "synthesis" not in result:
        _log.info("Council returned empty; using neutral pass-through")
        return _neutral_council("Council parse/unavailable")

    syn = result.get("synthesis") or {}
    log_agent(
        "Council",
        analysis.symbol,
        f"score={syn.get('council_score', '?')} veto={syn.get('hard_veto')} | "
        f"{str(syn.get('summary', ''))[:100]}",
    )
    return result


def _neutral_council(note: str) -> dict[str, Any]:
    return {
        "liquidity_specialist": {"score": 6, "verdict": "MIXED", "note": note},
        "regime_specialist": {"label": "RANGE", "confidence": 5, "note": note},
        "execution_specialist": {"score": 6, "verdict": "OK", "note": note},
        "risk_specialist": {"score": 6, "verdict": "OK", "note": note},
        "synthesis": {
            "hard_veto": False,
            "council_score": 6,
            "summary": note,
        },
    }


def council_minutes(council: dict[str, Any]) -> str:
    """One-line for logs / orchestrator context."""
    syn = council.get("synthesis") or {}
    return (
        f"L={council.get('liquidity_specialist', {}).get('verdict')} "
        f"R={council.get('regime_specialist', {}).get('label')} "
        f"X={council.get('execution_specialist', {}).get('verdict')} "
        f"RS={council.get('risk_specialist', {}).get('verdict')} "
        f"blend={syn.get('council_score')}"
    )
