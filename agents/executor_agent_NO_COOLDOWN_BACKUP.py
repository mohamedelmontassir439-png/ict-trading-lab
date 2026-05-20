"""
Executor Agent  —  ينفذ ويغلق الصفقات الورقية (FIXED VERSION)

Bug fixes vs v1 original:
  1. Balance no longer decremented on open (was double-deducting on close)
  2. PnL on TP/SL exit uses the limit price (TP or SL), not current price
  3. Breakeven actually moves SL to entry (was log-only)
  4. New BE status when stopped at breakeven after 1R reached
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from database import models
from agents.data_agent import get_current_price


def open_trade(signal: dict, reason: str) -> int:
    """Open a paper trade. Returns trade_id.
    Balance is NOT touched on open — it only moves on close (by realized pnl).
    """
    trade_id = models.open_trade(
        symbol     = signal["symbol"],
        market     = signal["market"],
        direction  = signal["direction"],
        entry      = signal["entry"],
        sl         = signal["sl"],
        tp         = signal["tp"],
        lot        = signal["lot_size"],
        risk_usd   = signal["risk_usd"],
        kill_zone  = signal["kill_zone"],
        setup_type = signal["setup_type"],
        bias       = signal["bias"],
        reason     = reason,
    )

    models.log_agent("Executor", signal["symbol"],
                     f"OPENED #{trade_id} {signal['direction']} "
                     f"@ {signal['entry']} | SL={signal['sl']} TP={signal['tp']}")
    return trade_id


def check_and_close_trades():
    """
    Called every cycle.
    Checks if any open trade hit SL or TP.
    Also implements Breakeven at 1R: SL is moved to entry once 1R reached.
    """
    open_trades = models.get_open_trades()
    if not open_trades:
        return

    for trade in open_trades:
        symbol    = trade["symbol"]
        market    = trade["market"]
        direction = trade["direction"]
        entry     = trade["entry_price"]
        sl        = trade["sl_price"]
        tp        = trade["tp_price"]
        lot       = trade["lot_size"]
        risk_usd  = trade["risk_usd"]
        be_moved  = bool(trade.get("be_moved", 0))
        trade_id  = trade["id"]

        current = get_current_price(symbol, market)
        if current == 0:
            continue

        # Use the ORIGINAL sl_distance (from entry), not the moved SL,
        # so that "1R" target stays fixed regardless of BE adjustment
        sl_distance_now = abs(entry - sl)

        if direction == "LONG":
            hit_sl = current <= sl
            hit_tp = current >= tp
            at_1r  = (not be_moved) and (current >= entry + sl_distance_now)
        else:  # SHORT
            hit_sl = current >= sl
            hit_tp = current <= tp
            at_1r  = (not be_moved) and (current <= entry - sl_distance_now)

        # Close on TP — pnl computed from TP, not current
        if hit_tp:
            tp_distance = abs(tp - entry)
            pnl = tp_distance * lot   # always positive (we hit TP)
            rr  = pnl / risk_usd if risk_usd > 0 else 0
            _close(trade_id, "WIN", pnl, rr)

        # Close on SL — if BE already moved, this is a Break-Even exit
        elif hit_sl:
            if be_moved:
                _close(trade_id, "BE", 0.0, 0.0)
            else:
                _close(trade_id, "LOSS", -risk_usd, -1.0)

        # Move SL to breakeven at 1R
        elif at_1r:
            models.move_sl_to_be(trade_id, entry)
            models.log_agent("Executor", symbol,
                             f"#{trade_id} reached 1R — SL moved to BE @ {entry:.5f}")


def _close(trade_id: int, status: str, pnl: float, rr: float):
    """Close a trade and update account by REALIZED pnl only."""
    pnl = round(pnl, 4)
    rr  = round(rr, 2)

    models.close_trade(trade_id, status, pnl, rr)

    account = models.get_account()
    new_balance   = account["balance"]   + pnl
    new_total_pnl = account["total_pnl"] + pnl
    win_c  = account["win_count"]  + (1 if status == "WIN"  else 0)
    loss_c = account["loss_count"] + (1 if status == "LOSS" else 0)

    models.update_account(
        balance    = round(new_balance, 4),
        equity     = round(new_balance, 4),
        total_pnl  = round(new_total_pnl, 4),
        win_count  = win_c,
        loss_count = loss_c,
    )
    models.log_agent("Executor", "SYSTEM",
                     f"CLOSED #{trade_id} → {status} | PnL=${pnl:+.2f} | RR={rr:.2f}")
