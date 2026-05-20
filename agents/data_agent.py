"""
Data Agent  —  يجلب بيانات حقيقية من Binance و yfinance
"""
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from database.models import log_agent

BINANCE_BASE = "https://api.binance.com/api/v3"

INTERVAL_MAP = {
    "5m": "15m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"
}

YFINANCE_INTERVAL = {
    "5m": "15m", "15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"
}
YFINANCE_PERIOD = {
    "5m": "5d", "15m": "60d", "1h": "60d", "4h": "60d", "1d": "1y"
}


def _normalize_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance columns (including MultiIndex) to lowercase OHLCV names."""
    if df.empty:
        return df
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [str(t[0]).lower() for t in out.columns]
    else:
        out.columns = [str(c).lower() for c in out.columns]
    return out


# ──────────────────────────────────────────────────────────────────
#  CRYPTO  (Binance public API  —  لا يحتاج API key)
# ──────────────────────────────────────────────────────────────────

def fetch_crypto(symbol: str, interval: str = "15m", limit: int = 200) -> pd.DataFrame:
    """Returns OHLCV DataFrame for a Binance crypto pair."""
    url = f"{BINANCE_BASE}/klines"
    params = {"symbol": symbol, "interval": INTERVAL_MAP[interval], "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        raw = r.json()
        df = pd.DataFrame(raw, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","qav","trades","tbav","tqav","ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df.set_index("open_time", inplace=True)
        log_agent("DataAgent", symbol, f"Fetched {len(df)} candles [{interval}]")
        return df[["open","high","low","close","volume"]]
    except Exception as e:
        log_agent("DataAgent", symbol, f"ERROR crypto fetch: {e}")
        return pd.DataFrame()


def get_crypto_price(symbol: str) -> float:
    """Current price from Binance ticker."""
    try:
        r = requests.get(f"{BINANCE_BASE}/ticker/price",
                         params={"symbol": symbol}, timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────
#  FOREX / GOLD  (yfinance)
# ──────────────────────────────────────────────────────────────────

def fetch_forex(ticker: str, interval: str = "15m") -> pd.DataFrame:
    """Returns OHLCV DataFrame for a yfinance ticker (EURUSD=X, GC=F …)"""
    try:
        period   = YFINANCE_PERIOD.get(interval, "60d")
        yf_int   = YFINANCE_INTERVAL.get(interval, "15m")
        df = yf.download(ticker, period=period, interval=yf_int,
                         progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError("Empty data")
        df = _normalize_yfinance_columns(df)
        if "volume" not in df.columns:
            df["volume"] = 0.0
        df.index = df.index.tz_localize("UTC") if df.index.tzinfo is None \
                   else df.index.tz_convert("UTC")
        name = config.FOREX_NAMES.get(ticker, ticker)
        log_agent("DataAgent", name, f"Fetched {len(df)} candles [{interval}]")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        name = config.FOREX_NAMES.get(ticker, ticker)
        log_agent("DataAgent", name, f"ERROR forex fetch: {e}")
        return pd.DataFrame()


def get_forex_price(ticker: str) -> float:
    """Last price via yfinance; several fallbacks for indices (^GSPC) where 1m may be empty."""
    attempts = (
        ("1d", "1m"),
        ("5d", "5m"),
        ("5d", "15m"),
        ("10d", "1h"),
        ("60d", "1d"),
    )
    for period, interval in attempts:
        try:
            data = yf.download(
                ticker, period=period, interval=interval,
                progress=False, auto_adjust=True,
            )
            if data.empty:
                continue
            data = _normalize_yfinance_columns(data)
            if "close" not in data.columns:
                continue
            val = float(data["close"].iloc[-1])
            if val > 0:
                return val
        except Exception:
            continue
    return 0.0


# ──────────────────────────────────────────────────────────────────
#  UNIFIED API
# ──────────────────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, market: str, interval: str = "15m",
                limit: int = 200) -> pd.DataFrame:
    if market == "crypto":
        return fetch_crypto(symbol, interval, limit)
    else:
        return fetch_forex(symbol, interval)


def get_current_price(symbol: str, market: str) -> float:
    if market == "crypto":
        return get_crypto_price(symbol)
    else:
        return get_forex_price(symbol)


def is_kill_zone() -> tuple[bool, str]:
    """Returns (True, zone_name) if we are currently in an ICT kill zone."""
    now_utc = datetime.now(timezone.utc).time().replace(second=0, microsecond=0)
    for name, zone in config.KILL_ZONES.items():
        if zone["start"] <= now_utc <= zone["end"]:
            return True, name
    return False, ""


def get_all_symbols():
    """Returns list of (symbol, market) tuples."""
    symbols = []
    for s in config.CRYPTO_PAIRS:
        symbols.append((s, "crypto"))
    for s in config.FOREX_PAIRS:
        symbols.append((s, "forex"))
    return symbols


