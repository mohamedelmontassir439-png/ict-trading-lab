"""
Displacement Agent  —  detects institutional displacement candles
Strong impulsive moves (2+ large-body candles) signal real institutional participation.
A Displacement + CISD (Change in State of Delivery) confirms the setup direction.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class DisplacementResult:
    detected:     bool
    direction:    str    # "UP" | "DOWN" | ""
    strength:     float  # total_range / ATR
    candle_count: int
    score_boost:  int
    bars_ago:     int


def analyze_displacement(symbol: str, df: pd.DataFrame,
                         current_price: float) -> DisplacementResult:
    """
    Looks back 20 bars for the most recent displacement event.
    Displacement = 2+ consecutive large-body candles (body > 60% of range, range > 1×ATR).
    """
    _default = DisplacementResult(False, "", 0.0, 0, 0, 0)

    if df is None or df.empty or len(df) < 20:
        return _default

    closes = df["close"].values
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    n      = len(df)

    # ATR(14)
    tr_list = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i]  - closes[i-1]))
        tr_list.append(tr)
    atr = float(np.mean(tr_list[-14:])) if len(tr_list) >= 14 else float(np.mean(tr_list))

    if atr <= 0:
        return _default

    lookback = min(20, n - 1)

    for start in range(n - 2, n - lookback - 1, -1):
        # Try to find a displacement run starting at 'start'
        run_dir = None
        run_len = 0
        run_range = 0.0
        i = start

        while i < n:
            body = abs(closes[i] - opens[i])
            rng  = highs[i] - lows[i]
            if rng < atr * 0.5:
                break

            is_bull = closes[i] > opens[i]
            is_bear = closes[i] < opens[i]

            # Body must be at least 50% of the candle range
            if body < rng * 0.50:
                break

            candle_dir = "UP" if is_bull else ("DOWN" if is_bear else None)
            if candle_dir is None:
                break

            if run_dir is None:
                run_dir = candle_dir
            elif candle_dir != run_dir:
                break

            run_len   += 1
            run_range += rng
            i += 1

        if run_len >= 2 and run_dir and run_range >= atr * 1.5:
            strength = run_range / atr
            score_boost = 2 if strength >= 3.0 else 1
            bars_ago = n - 1 - start

            result = DisplacementResult(
                detected=True, direction=run_dir,
                strength=round(strength, 2), candle_count=run_len,
                score_boost=score_boost, bars_ago=bars_ago,
            )
            log_agent("DisplacementAgent", symbol,
                      f"{run_dir} displacement | {run_len} candles | "
                      f"strength={strength:.1f}×ATR | {bars_ago} bars ago | +{score_boost}pts")
            return result

    return _default
