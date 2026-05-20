"""
Breaker Block Agent  —  Failed Order Blocks that flip direction
A Bearish OB that price breaks through becomes a Bullish Breaker (support on retest).
A Bullish OB that price breaks through becomes a Bearish Breaker (resistance on retest).
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class BreakerBlock:
    high:      float
    low:       float
    mid:       float
    direction: str    # "BULL" | "BEAR"  (direction of the BREAKER, not original OB)
    age_bars:  int
    strength:  float  # how far price broke through, normalized


@dataclass
class BreakerResult:
    breakers:      List[BreakerBlock] = field(default_factory=list)
    best_breaker:  Optional[BreakerBlock] = None
    score_boost:   int = 0


def analyze_breakers(symbol: str, df: pd.DataFrame,
                     bias: str, current_price: float) -> BreakerResult:
    """
    Scan the last 150 bars for failed OBs near current price.
    A failed OB = an order block that price later broke through decisively.
    That broken OB becomes a Breaker Block in the opposite direction.
    """
    _default = BreakerResult()

    if df is None or df.empty or len(df) < 20:
        return _default

    closes = df["close"].values
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    n      = min(len(df), 150)

    breakers = []

    for i in range(2, n - 5):
        # Identify potential OB candle
        is_bear_candle = closes[i] < opens[i]
        is_bull_candle = closes[i] > opens[i]

        # Bullish OB: bearish candle followed by impulse up
        if is_bear_candle:
            impulse = sum(1 for j in range(1, min(4, n-i)) if closes[i+j] > closes[i+j-1])
            if impulse >= 2:
                ob_high = highs[i]
                ob_low  = lows[i]
                # Check if price later broke BELOW this OB (making it a failed bullish OB → bearish breaker)
                future = closes[i+3:]
                if len(future) > 0 and np.any(future < ob_low):
                    # This was a bullish OB that failed → bearish breaker
                    dist = abs(current_price - (ob_high + ob_low) / 2) / current_price
                    if dist < 0.015:  # within 1.5% of price
                        bb = BreakerBlock(
                            high=round(ob_high, 6), low=round(ob_low, 6),
                            mid=round((ob_high + ob_low) / 2, 6),
                            direction="BEAR",
                            age_bars=n - i,
                            strength=round(dist, 5),
                        )
                        breakers.append(bb)

        # Bearish OB: bullish candle followed by impulse down
        if is_bull_candle:
            impulse = sum(1 for j in range(1, min(4, n-i)) if closes[i+j] < closes[i+j-1])
            if impulse >= 2:
                ob_high = highs[i]
                ob_low  = lows[i]
                # Check if price later broke ABOVE this OB (failed bearish OB → bullish breaker)
                future = closes[i+3:]
                if len(future) > 0 and np.any(future > ob_high):
                    dist = abs(current_price - (ob_high + ob_low) / 2) / current_price
                    if dist < 0.015:
                        bb = BreakerBlock(
                            high=round(ob_high, 6), low=round(ob_low, 6),
                            mid=round((ob_high + ob_low) / 2, 6),
                            direction="BULL",
                            age_bars=n - i,
                            strength=round(dist, 5),
                        )
                        breakers.append(bb)

    # Keep only breakers aligned with bias, sorted by proximity
    aligned = [b for b in breakers
               if (bias in ("BULLISH", "NEUTRAL") and b.direction == "BULL")
               or (bias in ("BEARISH", "NEUTRAL") and b.direction == "BEAR")]
    aligned.sort(key=lambda b: b.strength)

    best = aligned[0] if aligned else None
    score_boost = 2 if best else 0

    result = BreakerResult(breakers=aligned[:3], best_breaker=best,
                           score_boost=score_boost)

    if best:
        log_agent("BreakerAgent", symbol,
                  f"Breaker {best.direction} [{best.low:.5f}-{best.high:.5f}] "
                  f"age={best.age_bars}bars | +{score_boost}pts")
    return result
