"""
Divergence Agent  —  RSI and MACD divergence detection
Bullish divergence: price makes lower low, indicator makes higher low → reversal up.
Bearish divergence: price makes higher high, indicator makes lower high → reversal down.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class DivergenceResult:
    bullish_rsi:  bool
    bearish_rsi:  bool
    bullish_macd: bool
    bearish_macd: bool
    rsi_value:    float
    macd_hist:    float
    score_boost:  int


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    rsi_vals = [50.0] * period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
        rsi_vals.append(100 - 100 / (1 + rs))

    return np.array(rsi_vals)


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    k = 2 / (period + 1)
    out = np.zeros(len(arr))
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = arr[i] * k + out[i-1] * (1 - k)
    return out


def _macd_hist(closes: np.ndarray, fast=12, slow=26, signal=9) -> np.ndarray:
    if len(closes) < slow + signal:
        return np.zeros(len(closes))
    ema_fast   = _ema(closes, fast)
    ema_slow   = _ema(closes, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    return macd_line - signal_line


def analyze_divergence(symbol: str, df: pd.DataFrame, bias: str) -> DivergenceResult:
    _default = DivergenceResult(False, False, False, False, 50.0, 0.0, 0)

    if df is None or df.empty or len(df) < 40:
        return _default

    closes = df["close"].values.astype(float)
    lows   = df["low"].values.astype(float)
    highs  = df["high"].values.astype(float)

    rsi_vals  = _rsi(closes)
    macd_vals = _macd_hist(closes)

    # Use last 30 bars for divergence scan
    scan = 30
    c_slice = closes[-scan:]
    l_slice = lows[-scan:]
    h_slice = highs[-scan:]
    r_slice = rsi_vals[-scan:]
    m_slice = macd_vals[-scan:]

    def find_lows_idx(arr, n=3):
        idxs = []
        for i in range(1, len(arr) - 1):
            if arr[i] <= arr[i-1] and arr[i] <= arr[i+1]:
                idxs.append(i)
        return idxs[-n:] if len(idxs) >= n else idxs

    def find_highs_idx(arr, n=3):
        idxs = []
        for i in range(1, len(arr) - 1):
            if arr[i] >= arr[i-1] and arr[i] >= arr[i+1]:
                idxs.append(i)
        return idxs[-n:] if len(idxs) >= n else idxs

    price_lows  = find_lows_idx(l_slice)
    price_highs = find_highs_idx(h_slice)

    bullish_rsi = bearish_rsi = False
    bullish_macd = bearish_macd = False

    # Bullish divergence: price lower low, RSI higher low
    if len(price_lows) >= 2:
        p1, p2 = price_lows[-2], price_lows[-1]
        if l_slice[p2] < l_slice[p1] and r_slice[p2] > r_slice[p1]:
            bullish_rsi = True
        if l_slice[p2] < l_slice[p1] and m_slice[p2] > m_slice[p1]:
            bullish_macd = True

    # Bearish divergence: price higher high, indicator lower high
    if len(price_highs) >= 2:
        p1, p2 = price_highs[-2], price_highs[-1]
        if h_slice[p2] > h_slice[p1] and r_slice[p2] < r_slice[p1]:
            bearish_rsi = True
        if h_slice[p2] > h_slice[p1] and m_slice[p2] < m_slice[p1]:
            bearish_macd = True

    rsi_now  = float(rsi_vals[-1])
    macd_now = float(macd_vals[-1])

    # Score: +2 if divergence aligns with bias, +1 for any divergence
    bull_div = bullish_rsi or bullish_macd
    bear_div = bearish_rsi or bearish_macd

    if (bias == "BULLISH" and bull_div) or (bias == "BEARISH" and bear_div):
        score_boost = 2
    elif bull_div or bear_div:
        score_boost = 1
    else:
        score_boost = 0

    result = DivergenceResult(
        bullish_rsi=bullish_rsi, bearish_rsi=bearish_rsi,
        bullish_macd=bullish_macd, bearish_macd=bearish_macd,
        rsi_value=round(rsi_now, 2), macd_hist=round(macd_now, 6),
        score_boost=score_boost,
    )

    if score_boost > 0:
        div_type = ("Bullish" if bull_div else "Bearish")
        log_agent("DivergenceAgent", symbol,
                  f"{div_type} divergence | RSI={rsi_now:.1f} MACD={macd_now:.5f} | "
                  f"+{score_boost}pts")
    return result
