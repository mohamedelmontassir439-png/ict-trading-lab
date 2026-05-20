import os
from datetime import time

# ─────────────────────────────────────────────
#  API KEYS  —  use environment variables only
#  Orchestrator uses Gemini: set GEMINI_API_KEY
#  (https://aistudio.google.com/apikey)
#  Optional Anthropic (backup agent only): ANTHROPIC_API_KEY
# ─────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

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
#  MARKETS  —  الأسواق
# ─────────────────────────────────────────────
CRYPTO_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
# yfinance tickers when market is "forex" (indices/FX/metals use yfinance)
FOREX_PAIRS = ["^DJI", "^NDX", "^GSPC"]
FOREX_NAMES = {
    "EURUSD=X": "EURUSD",
    "GC=F": "XAUUSD",
    "^DJI": "US30",
    "^NDX": "US100",
    "^GSPC": "US500",
}


def display_symbol(yf_ticker: str) -> str:
    """Human-readable symbol for logs/UI (yfinance ticker -> alias)."""
    return FOREX_NAMES.get(yf_ticker, yf_ticker)


# ─────────────────────────────────────────────
#  TIMEFRAMES  —  الإطارات الزمنية
# ─────────────────────────────────────────────
HTF_INTERVAL   = "1h"    # Bias
MTF_INTERVAL   = "15m"   # Structure
LTF_INTERVAL   = "5m"    # Entry precision

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
DASHBOARD_PORT         = 5000
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
