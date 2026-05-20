"""
Orchestrator Agent  —  Gemini Edition (FREE) — v2 BUGFIX

Fixes the "Object of type bool is not JSON serializable" error
that was caused by numpy.bool_ values from pandas/numpy operations
in the ICT analysis (in_premium, in_discount).

Uses the Google Gen AI SDK via agents.gemini_client.

Required: GEMINI_API_KEY (env or config).
Install: py -m pip install google-genai
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from database.models import get_account, get_open_trades, log_agent
from agents.ict_agent import ICTAnalysis
from agents.gemini_client import generate_json_response

ICT_SYSTEM_PROMPT = """
You are an expert ICT (Inner Circle Trader) trading analyst with 10+ years of experience.
You think EXACTLY like Michael Huddleston — the founder of ICT.

Your role: analyze market data and decide whether to enter a trade or skip it.

ICT RULES YOU STRICTLY FOLLOW:
1. Never trade against the HTF bias (Daily/4H structure)
2. Only enter during Kill Zones (London 07-10 UTC, NY 13:30-16 UTC, Asia 00-03 UTC)
3. Require minimum 1:2 RR — prefer 1:3
4. Look for confluence: OB + FVG + Liquidity sweep before entry
5. Never trade into strong resistance/support without a liquidity sweep first
6. Prefer discount zone for longs, premium zone for shorts
7. Protect capital above all — if setup score < 6, SKIP
8. One loss is better than two — if daily loss > 2%, stop trading
9. The best trade is sometimes no trade

When the JSON payload includes a "specialist_council" object, you MUST treat it as advisory votes
from sub-agents (liquidity, regime, execution, portfolio risk). If council_score is low (<5) or
specialists flag DANGEROUS / POOR / BLOCK, lean heavily toward SKIP unless ICT confluence is exceptional.

RESPONSE FORMAT — always respond with valid JSON only:
{
  "decision": "ENTER" | "SKIP",
  "reason": "concise ICT explanation (2-3 sentences)",
  "confidence": 1-10,
  "key_level": 0.0,
  "warning": "optional risk note"
}
""".strip()


def ai_decide(
    analysis: ICTAnalysis,
    signal: dict,
    kill_zone: str,
    council: Optional[dict[str, Any]] = None,
) -> dict:
    """
    Sends analysis to Gemini and gets a GO/NO-GO decision.
    Returns dict with decision, reason, confidence.
    """
    account = get_account()
    open_trades = get_open_trades()

    context: dict[str, Any] = {
        "symbol": str(analysis.symbol),
        "market": str(analysis.market),
        "current_price": float(analysis.current_price),
        "bias": str(analysis.bias),
        "structure": str(analysis.structure),
        "kill_zone": str(kill_zone),
        "in_premium": bool(analysis.in_premium),
        "in_discount": bool(analysis.in_discount),
        "equilibrium": round(float(analysis.equilibrium), 5),
        "setup_score": int(analysis.setup_score),
        "order_blocks": [
            {"high": float(ob.high), "low": float(ob.low),
             "dir": str(ob.direction)} for ob in analysis.order_blocks[:3]
        ],
        "fvgs": [
            {"high": float(f.high), "low": float(f.low),
             "dir": str(f.direction)} for f in analysis.fvgs[:3]
        ],
        "liquidity": [
            {"price": float(lv.price), "kind": str(lv.kind)}
            for lv in analysis.liquidity[:5]
        ],
        "proposed_signal": {
            "direction": str(signal.get("direction", "")),
            "entry": float(signal.get("entry") or 0),
            "sl": float(signal.get("sl") or 0),
            "tp": float(signal.get("tp") or 0),
            "setup_type": str(signal.get("setup_type", "")),
            "risk_usd": float(signal.get("risk_usd") or 0),
        },
        "account": {
            "balance": round(float(account["balance"]), 2),
            "total_pnl": round(float(account["total_pnl"]), 2),
            "win_rate": _calc_winrate(account),
            "open_trades": int(len(open_trades)),
        },
    }
    if council:
        context["specialist_council"] = council

    user_msg = (
        f"{ICT_SYSTEM_PROMPT}\n\n"
        f"Analyze this setup and decide: ENTER or SKIP?\n\n"
        f"```json\n{json.dumps(context, indent=2, default=str)}\n```"
    )

    result = generate_json_response(
        user_msg, temperature=0.3, max_output_tokens=500,
    )
    if not result:
        log_agent("Orchestrator", analysis.symbol,
                  "AI unavailable: Gemini not configured or parse error")
        return _fallback(analysis)

    try:
        log_agent("Orchestrator", analysis.symbol,
                  f"AI Decision: {result.get('decision')} | "
                  f"Confidence: {result.get('confidence')}/10 | "
                  f"{str(result.get('reason', ''))[:80]}")
        return result
    except Exception as e:
        log_agent("Orchestrator", analysis.symbol, f"AI Error: {e}")
        return _fallback(analysis)


def _fallback(analysis: ICTAnalysis) -> dict:
    """Rule-based fallback when AI unavailable."""
    if analysis.setup_score >= 7:
        return {"decision": "ENTER", "reason": "Rule-based fallback (AI unavailable)",
                "confidence": int(analysis.setup_score)}
    return {"decision": "SKIP", "reason": "AI unavailable — skipping to be safe",
            "confidence": 0}


def _calc_winrate(account: dict) -> float:
    total = account["win_count"] + account["loss_count"]
    if total == 0:
        return 0.0
    return round(account["win_count"] / total * 100, 1)
