"""
Orchestrator Agent  —  يستخدم Claude API لتنسيق جميع الـ Sub-Agents
هو العقل المدبر — يقرر متى يدخل ومتى يبقى خارج السوق
"""
import json
import requests
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from database.models import get_account, get_open_trades, log_agent
from agents.ict_agent import ICTAnalysis

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


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

RESPONSE FORMAT — always respond with valid JSON only:
{
  "decision": "ENTER" | "SKIP",
  "reason": "concise ICT explanation (2-3 sentences)",
  "confidence": 1-10,
  "key_level": 0.0,
  "warning": "optional risk note"
}
""".strip()


def ai_decide(analysis: ICTAnalysis, signal: dict,
              kill_zone: str) -> dict:
    """
    Sends analysis to Claude and gets a GO/NO-GO decision.
    Returns dict with decision, reason, confidence.
    """
    account     = get_account()
    open_trades = get_open_trades()

    context = {
        "symbol":        analysis.symbol,
        "market":        analysis.market,
        "current_price": analysis.current_price,
        "bias":          analysis.bias,
        "structure":     analysis.structure,
        "kill_zone":     kill_zone,
        "in_premium":    bool(analysis.in_premium),
        "in_discount":   bool(analysis.in_discount),
        "equilibrium":   round(analysis.equilibrium, 5),
        "setup_score":   analysis.setup_score,
        "order_blocks": [
            {"high": ob.high, "low": ob.low,
             "dir": ob.direction} for ob in analysis.order_blocks[:3]
        ],
        "fvgs": [
            {"high": f.high, "low": f.low,
             "dir": f.direction} for f in analysis.fvgs[:3]
        ],
        "liquidity": [
            {"price": lv.price, "kind": lv.kind}
            for lv in analysis.liquidity[:5]
        ],
        "proposed_signal": {
            "direction":  signal.get("direction"),
            "entry":      signal.get("entry"),
            "sl":         signal.get("sl"),
            "tp":         signal.get("tp"),
            "setup_type": signal.get("setup_type"),
            "risk_usd":   signal.get("risk_usd"),
        },
        "account": {
            "balance":    round(account["balance"], 2),
            "total_pnl":  round(account["total_pnl"], 2),
            "win_rate":   _calc_winrate(account),
            "open_trades": len(open_trades),
        }
    }

    user_msg = (
        f"Analyze this setup and decide: ENTER or SKIP?\n\n"
        f"```json\n{json.dumps(context, indent=2)}\n```"
    )

    try:
        headers = {
            "x-api-key":         config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        body = {
            "model":      config.MODEL,
            "max_tokens": 500,
            "system":     ICT_SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": user_msg}],
        }
        r = requests.post(ANTHROPIC_URL, headers=headers,
                          json=body, timeout=30)
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()

        # Strip possible markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        log_agent("Orchestrator", analysis.symbol,
                  f"AI Decision: {result.get('decision')} | "
                  f"Confidence: {result.get('confidence')}/10 | "
                  f"{result.get('reason', '')[:80]}")
        return result

    except Exception as e:
        log_agent("Orchestrator", analysis.symbol, f"AI Error: {e}")
        # Fallback: use rule-based decision
        if analysis.setup_score >= 7:
            return {"decision": "ENTER", "reason": "Rule-based fallback (AI unavailable)",
                    "confidence": analysis.setup_score}
        return {"decision": "SKIP",  "reason": "AI unavailable — skipping to be safe",
                "confidence": 0}


def _calc_winrate(account: dict) -> float:
    total = account["win_count"] + account["loss_count"]
    if total == 0:
        return 0.0
    return round(account["win_count"] / total * 100, 1)





