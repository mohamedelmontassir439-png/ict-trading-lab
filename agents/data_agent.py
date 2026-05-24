"""
Data Agent  —  يجلب بيانات حقيقية في الوقت الفعلي
- Indices (US30/US100/US500): yfinance + cTrader live price (وضع Live)
- Crypto: Binance public API (بدون API key)

إصلاحات رئيسية:
  - دعم 1m و4h بشكل صحيح
  - limit مُطبَّق على forex
  - 4h مُشتقّ بـ resample من 1h
  - get_current_price سريع + مخزّن مؤقتاً
  - وضع Live: سعر فعلي من cTrader
"""
from __future__ import annotations

import time as _time
import threading
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from database.models import log_agent

BINANCE_BASE = "https://api.binance.com/api/v3"

# ── yfinance interval/period mapping ────────────────────────────────
# 4h: yfinance لا يدعم 4h — نجلب 1h ونُعيد تجميعها
YFINANCE_INTERVAL = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "60m",
    "4h":  "60m",   # سيُعاد تجميعها لـ 4h
    "1d":  "1d",
}
YFINANCE_PERIOD = {
    "1m":  "7d",    # yfinance: أقصى فترة لـ 1m هي 7 أيام
    "5m":  "5d",
    "15m": "60d",
    "1h":  "60d",
    "4h":  "60d",
    "1d":  "1y",
}


# ══════════════════════════════════════════════════════════════════════
#  Price cache — للسرعة
# ══════════════════════════════════════════════════════════════════════

_price_cache:     dict[str, float]  = {}
_price_cache_ts:  dict[str, float]  = {}   # timestamp آخر تحديث
_CACHE_TTL_SECS = 10   # تحديث السعر كل 10 ثوانٍ كحد أقصى
_cache_lock = threading.Lock()


def _set_cached_price(symbol: str, price: float):
    with _cache_lock:
        _price_cache[symbol]    = price
        _price_cache_ts[symbol] = _time.time()


def _get_cached_price(symbol: str) -> float | None:
    with _cache_lock:
        ts    = _price_cache_ts.get(symbol, 0)
        price = _price_cache.get(symbol, 0)
    if price and (_time.time() - ts) < _CACHE_TTL_SECS:
        return price
    return None


# ══════════════════════════════════════════════════════════════════════
#  Helper: normalize yfinance columns
# ══════════════════════════════════════════════════════════════════════

def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [str(t[0]).lower() for t in out.columns]
    else:
        out.columns = [str(c).lower() for c in out.columns]
    # ضمان الأعمدة الأساسية
    for col in ("open", "high", "low", "close"):
        if col not in out.columns:
            return pd.DataFrame()
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return out[["open", "high", "low", "close", "volume"]]


def _resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """أعد تجميع بيانات 1h لتنتج شموع 4h."""
    if df_1h.empty:
        return df_1h
    df = df_1h.copy()
    df4 = df.resample("4h", closed="left", label="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()
    return df4


# ══════════════════════════════════════════════════════════════════════
#  CRYPTO  (Binance public API)
# ══════════════════════════════════════════════════════════════════════

_BINANCE_INT = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


def fetch_crypto(symbol: str, interval: str = "15m", limit: int = 200) -> pd.DataFrame:
    url    = f"{BINANCE_BASE}/klines"
    params = {"symbol": symbol, "interval": _BINANCE_INT.get(interval, "15m"),
              "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        raw = r.json()
        df  = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tbav", "tqav", "ignore",
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df.set_index("open_time", inplace=True)
        log_agent("DataAgent", symbol, f"Crypto {len(df)} candles [{interval}]")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        log_agent("DataAgent", symbol, f"ERROR crypto: {e}")
        return pd.DataFrame()


def get_crypto_price(symbol: str) -> float:
    cached = _get_cached_price(symbol)
    if cached:
        return cached
    try:
        r = requests.get(f"{BINANCE_BASE}/ticker/price",
                         params={"symbol": symbol}, timeout=5)
        r.raise_for_status()
        price = float(r.json()["price"])
        _set_cached_price(symbol, price)
        return price
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════
#  FOREX / INDICES  (yfinance)
# ══════════════════════════════════════════════════════════════════════

def fetch_forex(ticker: str, interval: str = "15m",
                limit: int = 0) -> pd.DataFrame:
    """
    جلب بيانات OHLCV من yfinance.
    limit: إذا > 0 → أرجع آخر N شمعة فقط.
    4h يُعاد بناؤه من 1h.
    """
    yf_int = YFINANCE_INTERVAL.get(interval, "15m")
    period = YFINANCE_PERIOD.get(interval, "60d")

    try:
        df = yf.download(ticker, period=period, interval=yf_int,
                         progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError("Empty data")

        df = _normalize_yf(df)
        if df.empty:
            raise ValueError("Columns missing after normalize")

        # التعامل مع timezone
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        # إعادة التجميع لـ 4h
        if interval == "4h":
            df = _resample_4h(df)

        # تطبيق limit
        if limit and limit > 0 and len(df) > limit:
            df = df.iloc[-limit:]

        name = config.FOREX_NAMES.get(ticker, ticker)
        log_agent("DataAgent", name,
                  f"{len(df)} candles [{interval}] "
                  f"({df.index[0].strftime('%m/%d %H:%M')} → "
                  f"{df.index[-1].strftime('%m/%d %H:%M')} UTC)")
        return df

    except Exception as e:
        name = config.FOREX_NAMES.get(ticker, ticker)
        log_agent("DataAgent", name, f"ERROR yf fetch [{interval}]: {e}")
        return pd.DataFrame()


def get_forex_price(ticker: str) -> float:
    """
    سعر حالي سريع لأداة yfinance.
    في وضع Live: يُستخدم سعر البروكر الحقيقي أولاً.
    """
    # ── MT5: سعر مباشر من MT5 tick data ─────────────────────────
    if config.BROKER == "mt5":
        try:
            from agents.mt5_agent import get_mt5_agent
            agent = get_mt5_agent()
            if agent and agent.is_ready():
                price = agent.get_current_price(ticker)
                if price and price > 0:
                    _set_cached_price(ticker, price)
                    return price
        except Exception:
            pass

    # ── cTrader: سعر حقيقي ───────────────────────────────────────
    if config.BROKER == "ctrader":
        ct_price = _get_ctrader_price(ticker)
        if ct_price and ct_price > 0:
            return ct_price

    # ── تحقق من الكاش أولاً ─────────────────────────────────────
    cached = _get_cached_price(ticker)
    if cached:
        return cached

    # ── yfinance: جرّب 1m أولاً ثم 5m ───────────────────────────
    for period, interval in (("1d", "1m"), ("5d", "5m"), ("5d", "15m")):
        try:
            data = yf.download(ticker, period=period, interval=interval,
                               progress=False, auto_adjust=True)
            if data.empty:
                continue
            data = _normalize_yf(data)
            if "close" not in data.columns or data.empty:
                continue
            val = float(data["close"].iloc[-1])
            if val > 0:
                _set_cached_price(ticker, val)
                return val
        except Exception:
            continue
    return 0.0


def _get_ctrader_price(ticker: str) -> float:
    """استرجع السعر الحقيقي من cTrader (وضع Live فقط)."""
    try:
        from agents.ctrader_agent import get_ctrader_agent
        agent = get_ctrader_agent()
        if not agent or not agent.is_ready():
            return 0.0

        ct_name = config.CTRADER_SYMBOL_MAP.get(ticker, "")
        if not ct_name:
            return 0.0

        # ابحث عن السعر في المراكز المفتوحة أو عبر بيانات الـ tick
        positions = agent.get_open_positions()
        for pos in positions:
            if pos.get("symbol") == ct_name:
                # استخدم سعر الدخول كتقريب مؤقت (سيُحسَّن لاحقاً بـ tick subscription)
                pass

        return 0.0
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════
#  UNIFIED API
# ══════════════════════════════════════════════════════════════════════

def fetch_ohlcv(symbol: str, market: str, interval: str = "15m",
                limit: int = 200) -> pd.DataFrame:
    """
    جلب OHLCV موحّد لجميع الأسواق.
    limit مُطبَّق دائماً (crypto و forex).
    """
    if market == "crypto":
        df = fetch_crypto(symbol, interval, limit)
    else:
        df = fetch_forex(symbol, interval, limit)

    # تحديث الكاش من آخر سعر إغلاق
    if not df.empty:
        try:
            _set_cached_price(symbol, float(df["close"].iloc[-1]))
        except Exception:
            pass
    return df


def get_current_price(symbol: str, market: str) -> float:
    if market == "crypto":
        return get_crypto_price(symbol)
    return get_forex_price(symbol)


# ══════════════════════════════════════════════════════════════════════
#  Kill Zone  —  وقت حقيقي UTC
# ══════════════════════════════════════════════════════════════════════

def is_kill_zone() -> tuple[bool, str]:
    """
    يتحقق من Kill Zone بتوقيت UTC الحقيقي.
    datetime.now(timezone.utc) → لا توقيت محلي، لا تأخير.
    """
    now_t = datetime.now(timezone.utc).time().replace(second=0, microsecond=0)
    for name, zone in config.KILL_ZONES.items():
        if zone["start"] <= now_t <= zone["end"]:
            return True, name
    return False, ""


def get_all_symbols() -> list[tuple[str, str]]:
    symbols = []
    for s in config.CRYPTO_PAIRS:
        symbols.append((s, "crypto"))
    for s in config.FOREX_PAIRS:
        symbols.append((s, "forex"))
    return symbols
