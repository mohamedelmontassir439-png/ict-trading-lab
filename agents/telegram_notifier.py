"""
Telegram Notifier  —  إشعارات Telegram (اختياري)
Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment to enable.
"""
import os
import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _send(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass


def notify_trade_opened(trade_id: int, signal: dict, reason: str):
    _send(
        f"🟢 <b>TRADE OPENED #{trade_id}</b>\n"
        f"{signal.get('direction')} {signal.get('symbol')}\n"
        f"Entry: {signal.get('entry')} | SL: {signal.get('sl')} | TP: {signal.get('tp')}\n"
        f"Risk: ${signal.get('risk_usd', 0):.2f} | Grade: {signal.get('grade', 'C')}\n"
        f"<i>{reason[:200]}</i>"
    )


def notify_trade_closed(trade_id: int, status: str, symbol: str,
                        pnl: float, rr: float, new_balance: float):
    icon = "✅" if status == "WIN" else ("⚠️" if status == "BE" else "❌")
    _send(
        f"{icon} <b>TRADE CLOSED #{trade_id} — {status}</b>\n"
        f"{symbol} | PnL: ${pnl:+.2f} | RR: {rr:.2f}R\n"
        f"Balance: ${new_balance:,.2f}"
    )


def notify_breakeven_armed(trade_id: int, symbol: str, be_price: float):
    _send(
        f"🔒 <b>Breakeven Armed #{trade_id}</b>\n"
        f"{symbol} | SL moved to {be_price:.5f}"
    )
