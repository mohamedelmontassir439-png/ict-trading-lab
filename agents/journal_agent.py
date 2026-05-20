"""
Journal Agent  —  يتتبع الإحصائيات ويولد تقارير الأداء
"""
from datetime import datetime, date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import (get_account, get_all_trades,
                              upsert_daily_stats, get_conn)


def update_daily_stats():
    today = date.today().isoformat()
    conn  = get_conn()
    rows  = conn.execute("""
        SELECT * FROM trades
        WHERE date(opened_at) = ? OR date(closed_at) = ?
    """, (today, today)).fetchall()
    conn.close()

    trades = [dict(r) for r in rows]
    closed = [t for t in trades if t["status"] in ("WIN","LOSS","BE")]

    wins   = sum(1 for t in closed if t["status"] == "WIN")
    losses = sum(1 for t in closed if t["status"] == "LOSS")
    pnl    = sum(t["pnl"] for t in closed)
    max_dd = min((t["pnl"] for t in closed), default=0.0)

    upsert_daily_stats(today, len(closed), wins, losses, pnl, max_dd)


def get_performance_report() -> dict:
    account = get_account()
    trades  = get_all_trades(500)
    closed  = [t for t in trades if t["status"] in ("WIN","LOSS","BE")]

    if not closed:
        return {
            "balance":      account["balance"],
            "total_pnl":    0,
            "pnl_pct":      0,
            "win_rate":     0,
            "total_trades": 0,
            "wins":         0,
            "losses":       0,
            "avg_win":      0,
            "avg_loss":     0,
            "profit_factor": 0,
            "best_trade":   0,
            "worst_trade":  0,
            "expectancy":   0,
            "open_trades":  len([t for t in trades if t["status"] == "OPEN"]),
        }

    wins   = [t for t in closed if t["status"] == "WIN"]
    losses = [t for t in closed if t["status"] == "LOSS"]

    total_win  = sum(t["pnl"] for t in wins)   or 0
    total_loss = abs(sum(t["pnl"] for t in losses)) or 1

    avg_win  = total_win  / len(wins)   if wins   else 0
    avg_loss = total_loss / len(losses) if losses else 0

    win_rate = len(wins) / len(closed) if closed else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return {
        "balance":        round(account["balance"], 2),
        "total_pnl":      round(account["total_pnl"], 2),
        "pnl_pct": round(account["total_pnl"] / 10000 * 100, 2) if "total_pnl" in account else 0 if "total_pnl" in account else 0,
        "win_rate":       round(win_rate * 100, 1),
        "total_trades":   len(closed),
        "wins":           len(wins),
        "losses":         len(losses),
        "avg_win":        round(avg_win, 2),
        "avg_loss":       round(avg_loss, 2),
        "profit_factor":  round(total_win / total_loss, 2),
        "best_trade":     round(max((t["pnl"] for t in wins),   default=0), 2),
        "worst_trade":    round(min((t["pnl"] for t in losses), default=0), 2),
        "expectancy":     round(expectancy, 2),
        "open_trades":    len([t for t in trades if t["status"] == "OPEN"]),
    }


def get_daily_breakdown(days: int = 30) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT date, trades, wins, losses, pnl
        FROM daily_stats
        ORDER BY date DESC LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def print_report():
    r = get_performance_report()
    print("\n" + "═"*50)
    print("  📊  ICT TRADING LAB — PERFORMANCE REPORT")
    print("═"*50)
    print(f"  Balance:        ${r['balance']:,.2f}")
    print(f"  Total P&L:      ${r['total_pnl']:+,.2f}  ({r['pnl_pct']:+.2f}%)")
    print(f"  Win Rate:       {r['win_rate']}%")
    print(f"  Total Trades:   {r['total_trades']}  ({r['wins']}W / {r['losses']}L)")
    print(f"  Avg Win:        ${r['avg_win']:.2f}")
    print(f"  Avg Loss:       ${r['avg_loss']:.2f}")
    print(f"  Profit Factor:  {r['profit_factor']:.2f}")
    print(f"  Expectancy:     ${r['expectancy']:.2f} / trade")
    print(f"  Best Trade:     ${r['best_trade']:.2f}")
    print(f"  Worst Trade:    ${r['worst_trade']:.2f}")
    print(f"  Open Now:       {r['open_trades']}")
    print("═"*50 + "\n")




