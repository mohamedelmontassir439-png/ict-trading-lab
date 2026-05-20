"""
Risk Agent  —  builds validated trade signals (entry / SL / TP / size).
"""
from __future__ import annotations

import sys
import os
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from database.models import get_account, get_open_trades
from agents.ict_agent import ICTAnalysis


def risk_of_ruin_check() -> tuple[bool, str]:
    """
    Dynamic guard: pause trading if drawdown >= 10%, warn at >= 5%.
    Returns (allowed, reason).
    """
    from database.models import log_agent
    account = get_account()
    balance = float(account["balance"])
    initial = float(config.INITIAL_CAPITAL)
    if initial <= 0:
        return True, "OK"
    drawdown_pct = (initial - balance) / initial
    if drawdown_pct >= 0.10:
        return False, (f"Risk of Ruin: drawdown {drawdown_pct:.1%} >= 10% — "
                       f"trading paused until manual review")
    if drawdown_pct >= 0.05:
        log_agent("RiskAgent", "SYSTEM",
                  f"Drawdown warning {drawdown_pct:.1%} >= 5% — risk halved")
    return True, "OK"


def build_trade_signal(
    analysis: ICTAnalysis,
    entry_zone: dict[str, Any],
    kill_zone: str,
) -> Optional[dict[str, Any]]:
    """
    Turn ICT analysis + entry zone into an executor-ready signal dict.
    Returns None if risk checks fail or geometry is invalid.
    """
    from database.models import log_agent as _log_agent

    if analysis.bias not in ("BULLISH", "BEARISH"):
        _log_agent("RiskAgent", analysis.symbol, f"SKIP: bias={analysis.bias}")
        return None

    zdir = entry_zone.get("direction")
    if analysis.bias == "BULLISH" and zdir != "BULL":
        _log_agent("RiskAgent", analysis.symbol, f"SKIP: BULL bias but zone_dir={zdir}")
        return None
    if analysis.bias == "BEARISH" and zdir != "BEAR":
        _log_agent("RiskAgent", analysis.symbol, f"SKIP: BEAR bias but zone_dir={zdir}")
        return None

    open_count = len(get_open_trades())
    if open_count >= config.MAX_CONCURRENT:
        _log_agent("RiskAgent", analysis.symbol,
                   f"SKIP: MAX_CONCURRENT reached ({open_count}/{config.MAX_CONCURRENT} open)")
        return None

    account = get_account()
    balance = float(account["balance"])
    risk_usd = round(balance * config.RISK_PER_TRADE, 2)
    if risk_usd <= 0:
        _log_agent("RiskAgent", analysis.symbol, f"SKIP: risk_usd={risk_usd} <= 0")
        return None

    direction = "LONG" if analysis.bias == "BULLISH" else "SHORT"
    entry = float(entry_zone["mid"])
    low = float(entry_zone["low"])
    high = float(entry_zone["high"])
    buf = max(abs(entry) * 0.0005, 1e-12)

    if direction == "LONG":
        sl = low - buf
        if sl >= entry:
            sl = entry - max(abs(entry) * 0.002, 1e-8)
        risk_per_unit = entry - sl
        if risk_per_unit <= 0:
            return None
        tp = entry + risk_per_unit * config.TARGET_RR_RATIO
        reward_per_unit = tp - entry
    else:
        sl = high + buf
        if sl <= entry:
            sl = entry + max(abs(entry) * 0.002, 1e-8)
        risk_per_unit = sl - entry
        if risk_per_unit <= 0:
            return None
        tp = entry - risk_per_unit * config.TARGET_RR_RATIO
        reward_per_unit = entry - tp

    rr = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0
    if rr < config.MIN_RR_RATIO - 1e-6:
        return None

    lot_size = risk_usd / risk_per_unit

    return {
        "symbol": analysis.symbol,
        "market": analysis.market,
        "direction": direction,
        "entry": round(entry, 8),
        "sl": round(sl, 8),
        "tp": round(tp, 8),
        "lot_size": round(lot_size, 8),
        "risk_usd": risk_usd,
        "kill_zone": kill_zone,
        "setup_type": str(entry_zone.get("type", "ICT")),
        "bias": analysis.bias,
    }
