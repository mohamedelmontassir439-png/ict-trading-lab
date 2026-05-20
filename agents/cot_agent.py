"""
COT Agent  —  Commitment of Traders sentiment filter
Uses net positioning data (commercial vs non-commercial).
COT data updates weekly (Tuesdays); fetched from CFTC public CSV.
Falls back to NEUTRAL if data is unavailable.
"""
import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent

# CFTC bulk download (most recent year)
CFTC_URL = "https://www.cftc.gov/sites/default/files/files/dea/history/fut_fin_txt_{year}.zip"

# Map our symbols to CFTC market names (partial match)
COT_MARKET_MAP = {
    "EURUSD=X": "EURO FX",
    "GBP/USD":  "BRITISH POUND",
    "GC=F":     "GOLD",
    "BTCUSDT":  "BITCOIN",
}

_cot_cache: dict = {}   # symbol → {timestamp, signal}


def get_cot_signal(symbol: str) -> str:
    """
    Returns "BULLISH", "BEARISH", or "NEUTRAL".
    Caches result for 24h to avoid hammering CFTC.
    """
    global _cot_cache

    cached = _cot_cache.get(symbol)
    if cached:
        age = (datetime.utcnow() - cached["ts"]).total_seconds()
        if age < 86400:
            return cached["signal"]

    market_name = COT_MARKET_MAP.get(symbol)
    if not market_name:
        return "NEUTRAL"

    try:
        year = datetime.utcnow().year
        url  = CFTC_URL.format(year=year)
        df   = pd.read_csv(url, compression="zip", low_memory=False)

        # Filter for our market
        mask = df["Market and Exchange Names"].str.contains(market_name, case=False, na=False)
        sub  = df[mask].copy()
        if sub.empty:
            return "NEUTRAL"

        sub = sub.sort_values("As of Date in Form YYYY-MM-DD", ascending=False)
        latest = sub.iloc[0]

        net_non_comm = (float(latest.get("NonComm_Positions_Long_All", 0))
                        - float(latest.get("NonComm_Positions_Short_All", 0)))
        net_comm     = (float(latest.get("Comm_Positions_Long_All", 0))
                        - float(latest.get("Comm_Positions_Short_All", 0)))

        # Non-commercial (speculators) net long → bullish; net short → bearish
        if net_non_comm > 0 and net_comm < 0:
            signal = "BULLISH"
        elif net_non_comm < 0 and net_comm > 0:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        _cot_cache[symbol] = {"ts": datetime.utcnow(), "signal": signal}
        log_agent("COTAgent", symbol,
                  f"Net non-comm={net_non_comm:+,.0f} | signal={signal}")
        return signal

    except Exception as e:
        log_agent("COTAgent", symbol, f"COT fetch failed: {e} — defaulting NEUTRAL")
        return "NEUTRAL"


def cot_filter(cot_signal: str, ict_bias: str) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Blocks trade if COT strongly contradicts ICT bias.
    """
    if cot_signal == "NEUTRAL":
        return True, "COT neutral — no block"
    if cot_signal == ict_bias:
        return True, f"COT confirms {ict_bias}"
    return False, f"COT {cot_signal} contradicts ICT {ict_bias} — skip"
