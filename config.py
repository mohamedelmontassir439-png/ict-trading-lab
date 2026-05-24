import os
from datetime import time

# ─────────────────────────────────────────────
#  API KEYS
# ─────────────────────────────────────────────
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY",    "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# ─────────────────────────────────────────────
#  BROKER SELECTOR
#  "paper"   → ورقي (بدون بروكر)
#  "ctrader" → cTrader Open API (Live/FUNDEDHIVE)
#  "mt5"     → MetaTrader5 (Demo أو Live)
# ─────────────────────────────────────────────
BROKER    = os.getenv("BROKER", "paper").lower().strip()
LIVE_MODE = BROKER != "paper"     # أي بروكر حقيقي يُفعّل LIVE_MODE

# ─────────────────────────────────────────────
#  MT5 — MetaTrader 5
# ─────────────────────────────────────────────
MT5_LOGIN        = os.getenv("MT5_LOGIN",    "").strip()
MT5_PASSWORD     = os.getenv("MT5_PASSWORD", "").strip()
MT5_SERVER       = os.getenv("MT5_SERVER",   "").strip()
MT5_DEMO         = os.getenv("MT5_DEMO", "true").lower() in ("1", "true", "yes")
MT5_MAGIC_NUMBER = int(os.getenv("MT5_MAGIC", "123456"))

# رموز MT5 حسب الوسيط (عدّل حسب وسيطك)
MT5_SYMBOL_MAP = {
    "^DJI":  os.getenv("MT5_SYMBOL_US30",  "US30"),
    "^NDX":  os.getenv("MT5_SYMBOL_US100", "NAS100"),
    "^GSPC": os.getenv("MT5_SYMBOL_US500", "US500"),
}

# قيمة النقطة لكل لوت (USD) — يُستخدم كـ fallback إذا لم يرد من MT5
CT_POINT_VALUE_PER_LOT = float(os.getenv("CT_POINT_VALUE_PER_LOT", "1.0"))

# ─────────────────────────────────────────────
#  cTrader Open API
#  Get credentials: https://openapi.ctrader.com/
# ─────────────────────────────────────────────
CTRADER_CLIENT_ID      = os.getenv("CTRADER_CLIENT_ID",     "").strip()
CTRADER_CLIENT_SECRET  = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
CTRADER_ACCOUNT_ID     = int(os.getenv("CTRADER_ACCOUNT_ID", "0"))
CTRADER_ACCESS_TOKEN   = os.getenv("CTRADER_ACCESS_TOKEN",  "").strip()
CTRADER_DEMO           = os.getenv("CTRADER_DEMO", "false").lower() in ("1", "true", "yes")

# Symbol names as they appear in your cTrader broker (ask FUNDEDHIVE support if unsure)
CTRADER_SYMBOL_MAP = {
    "^DJI":  os.getenv("CT_SYMBOL_US30",  "US30"),
    "^NDX":  os.getenv("CT_SYMBOL_US100", "NAS100"),
    "^GSPC": os.getenv("CT_SYMBOL_US500", "US500"),
}

# ─────────────────────────────────────────────
#  PROP FIRM RULES — FUNDEDHIVE
#  Adjust to match your exact plan rules.
# ─────────────────────────────────────────────
PROPFIRM_INITIAL_BALANCE       = float(os.getenv("PROPFIRM_INITIAL_BALANCE",    "10000"))
PROPFIRM_MAX_DAILY_LOSS_PCT    = float(os.getenv("PROPFIRM_MAX_DAILY_LOSS_PCT",  "0.05"))   # 5%
PROPFIRM_MAX_DRAWDOWN_PCT      = float(os.getenv("PROPFIRM_MAX_DRAWDOWN_PCT",   "0.10"))   # 10%
PROPFIRM_PROFIT_TARGET_PCT     = float(os.getenv("PROPFIRM_PROFIT_TARGET_PCT",  "0.10"))   # 10%
PROPFIRM_MIN_TRADING_DAYS      = int(os.getenv("PROPFIRM_MIN_TRADING_DAYS",     "5"))
PROPFIRM_MAX_LOT_PER_TRADE     = float(os.getenv("PROPFIRM_MAX_LOT_PER_TRADE",  "5.0"))
PROPFIRM_CLOSE_ON_WEEKEND      = os.getenv("PROPFIRM_CLOSE_ON_WEEKEND", "true").lower() in ("1", "true", "yes")
PROPFIRM_NO_NEWS_WINDOW_MIN    = int(os.getenv("PROPFIRM_NO_NEWS_WINDOW_MIN",   "0"))      # 0 = disabled

# ─────────────────────────────────────────────
#  VIRTUAL ACCOUNT  —  حساب ورقي
# ─────────────────────────────────────────────
INITIAL_CAPITAL    = 10_000.00   # $10,000 افتراضي
RISK_PER_TRADE     = 0.01        # 1% لكل صفقة = $100
MAX_DAILY_LOSS     = 0.03        # 3% خسارة يومية قصوى
MAX_CONCURRENT     = 3           # أقصى عدد صفقات مفتوحة
MIN_RR_RATIO       = 2.0         # نسبة مخاطرة/مكافأة دنيا 1:2
TARGET_RR_RATIO    = 3.0         # هدف 1:3

# ─────────────────────────────────────────────
#  MARKETS  —  الأسواق  (Forex/Indices only)
# ─────────────────────────────────────────────
CRYPTO_PAIRS = []   # Crypto removed — indices only
FOREX_PAIRS  = ["^DJI", "^NDX", "^GSPC"]
FOREX_NAMES  = {
    "^DJI":  "US30",
    "^NDX":  "US100",
    "^GSPC": "US500",
}


def display_symbol(yf_ticker: str) -> str:
    """Human-readable symbol for logs/UI (yfinance ticker -> alias)."""
    return FOREX_NAMES.get(yf_ticker, yf_ticker)


# ─────────────────────────────────────────────
#  TIMEFRAMES  —  الإطارات الزمنية  (1m → 4h)
# ─────────────────────────────────────────────
HTF_INTERVAL   = "4h"    # Bias & trend (highest)
MTF_INTERVAL   = "1h"    # Structure confirmation
LTF_INTERVAL   = "15m"   # Entry precision
ENTRY_INTERVAL = "1m"    # Ultra-precise entry trigger

# ─────────────────────────────────────────────
#  ICT KILL ZONES  (UTC)  —  مناطق الصيد
# ─────────────────────────────────────────────
KILL_ZONES = {
    "Asian":   {"start": time(0,  0), "end": time(3,  0)},
    "London":  {"start": time(7,  0), "end": time(10, 0)},
    "NewYork": {"start": time(13, 30), "end": time(16, 0)},
}

# ─────────────────────────────────────────────
#  SYSTEM SETTINGS
# ─────────────────────────────────────────────
CHECK_INTERVAL_MINUTES = 15
DB_PATH                = "database/trading_lab.db"
LOG_PATH               = "logs/trading.log"
DASHBOARD_PORT         = int(os.getenv("PORT", 8000))
MODEL                  = "claude-sonnet-4-20250514"

# ─────────────────────────────────────────────
#  AI  —  Gemini + multi-agent council
# ─────────────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
ENABLE_AI_COUNCIL = os.getenv("ENABLE_AI_COUNCIL", "true").lower() in ("1", "true", "yes")
COUNCIL_HARD_VETO = os.getenv("COUNCIL_HARD_VETO", "true").lower() in ("1", "true", "yes")
COUNCIL_STRICTER_THRESHOLD = os.getenv("COUNCIL_STRICTER_THRESHOLD", "true").lower() in (
    "1", "true", "yes",
)
AI_ENTER_MIN_CONFIDENCE = int(os.getenv("AI_ENTER_MIN_CONFIDENCE", "6"))
