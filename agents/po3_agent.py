"""
Power of 3 Agent  —  Accumulation → Manipulation → Distribution
Asian range sets accumulation. London sweep = manipulation.
NY move = distribution (opposite of manipulation direction).
"""
import pandas as pd
from dataclasses import dataclass
from datetime import time as dtime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class PO3Result:
    phase:              str    # "Accumulation" | "Manipulation" | "Distribution" | "Unknown"
    asian_high:         float
    asian_low:          float
    manipulation_dir:   str    # "UP" | "DOWN" | "NONE"
    distribution_bias:  str    # "BULLISH" | "BEARISH" | "NEUTRAL"
    score_boost:        int


def analyze_po3(symbol: str, df_ltf: pd.DataFrame) -> PO3Result:
    """
    Requires LTF DataFrame with UTC timezone index (15m or 5m candles).
    """
    _default = PO3Result("Unknown", 0, 0, "NONE", "NEUTRAL", 0)

    if df_ltf is None or df_ltf.empty:
        return _default

    if df_ltf.index.tzinfo is None:
        return _default

    # Extract today's candles by UTC session
    today_idx = df_ltf.index.normalize()
    latest_date = today_idx[-1]
    today_df = df_ltf[today_idx == latest_date]

    def session_bars(df, start_h, start_m, end_h, end_m):
        s = dtime(start_h, start_m)
        e = dtime(end_h, end_m)
        return df[[s <= t.time() <= e for t in df.index]]

    asian_bars   = session_bars(today_df, 0, 0, 3, 0)
    london_bars  = session_bars(today_df, 7, 0, 10, 0)

    if asian_bars.empty:
        return _default

    asian_high = float(asian_bars["high"].max())
    asian_low  = float(asian_bars["low"].min())
    asian_range = asian_high - asian_low

    if asian_range <= 0:
        return _default

    # Determine current phase
    now_utc = df_ltf.index[-1].time()
    if dtime(0, 0) <= now_utc <= dtime(3, 0):
        phase = "Accumulation"
    elif dtime(7, 0) <= now_utc <= dtime(10, 0):
        phase = "Manipulation"
    else:
        phase = "Distribution"

    # Detect manipulation direction from London session
    if london_bars.empty:
        manipulation_dir = "NONE"
        distribution_bias = "NEUTRAL"
        score_boost = 0
    else:
        london_high = float(london_bars["high"].max())
        london_low  = float(london_bars["low"].min())

        swept_above = london_high > asian_high
        swept_below = london_low  < asian_low

        if swept_above and not swept_below:
            # London swept above Asian → expect NY to reverse DOWN
            manipulation_dir  = "UP"
            distribution_bias = "BEARISH"
            score_boost = 2
        elif swept_below and not swept_above:
            # London swept below Asian → expect NY to reverse UP
            manipulation_dir  = "DOWN"
            distribution_bias = "BULLISH"
            score_boost = 2
        elif swept_above and swept_below:
            manipulation_dir  = "BOTH"
            distribution_bias = "NEUTRAL"
            score_boost = 0
        else:
            manipulation_dir  = "NONE"
            distribution_bias = "NEUTRAL"
            score_boost = 0

    result = PO3Result(
        phase=phase,
        asian_high=round(asian_high, 6),
        asian_low=round(asian_low, 6),
        manipulation_dir=manipulation_dir,
        distribution_bias=distribution_bias,
        score_boost=score_boost,
    )

    log_agent("PO3Agent", symbol,
              f"Phase={phase} | Asian=[{asian_low:.5f}-{asian_high:.5f}] | "
              f"Manip={manipulation_dir} | Bias={distribution_bias} | +{score_boost}pts")
    return result
