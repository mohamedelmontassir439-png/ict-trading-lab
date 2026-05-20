"""
Silver Bullet Agent  —  ICT Silver Bullet strategy
Three precision windows where FVG entries have highest accuracy.
"""
import pandas as pd
from dataclasses import dataclass
from datetime import time as dtime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


SILVER_BULLET_WINDOWS = {
    "London_SB": (dtime(3, 0),  dtime(4, 0)),
    "AM_SB":     (dtime(10, 0), dtime(11, 0)),
    "PM_SB":     (dtime(14, 0), dtime(15, 0)),
}


@dataclass
class SilverBulletResult:
    active:       bool
    has_setup:    bool
    window_name:  str
    direction:    str    # "LONG" | "SHORT" | ""
    fvg_high:     float
    fvg_low:      float
    fvg_mid:      float
    score_boost:  int


def analyze_silver_bullet(symbol: str, df: pd.DataFrame,
                          bias: str, current_price: float) -> SilverBulletResult:
    """
    Checks if we're in a Silver Bullet window and if a fresh FVG formed
    in that window aligned with bias.
    """
    _default = SilverBulletResult(False, False, "", "", 0, 0, 0, 0)

    if df is None or df.empty or len(df) < 5:
        return _default

    if df.index.tzinfo is None:
        return _default

    now_time = df.index[-1].time()

    # Check if inside a Silver Bullet window
    active_window = None
    for name, (start, end) in SILVER_BULLET_WINDOWS.items():
        if start <= now_time <= end:
            active_window = name
            break

    if not active_window:
        return SilverBulletResult(False, False, "", "", 0, 0, 0, 0)

    # Look for fresh FVG formed in the last 10 bars (within the window)
    win_start, win_end = SILVER_BULLET_WINDOWS[active_window]
    window_bars = df[[win_start <= t.time() <= win_end for t in df.index]]

    if len(window_bars) < 3:
        return SilverBulletResult(True, False, active_window, "", 0, 0, 0, 1)

    highs  = window_bars["high"].values
    lows   = window_bars["low"].values

    best_fvg = None
    best_dir = ""

    for i in range(1, len(window_bars) - 1):
        # Bullish FVG
        gap = lows[i+1] - highs[i-1]
        if gap > 0 and bias in ("BULLISH", "NEUTRAL"):
            mid_ref = (highs[i-1] + lows[i-1]) / 2
            if mid_ref > 0 and gap / mid_ref >= 0.0005:
                dist = abs(current_price - (highs[i-1] + lows[i+1]) / 2) / current_price
                if dist < 0.005:
                    best_fvg = (lows[i+1], highs[i-1])
                    best_dir = "LONG"
                    break

        # Bearish FVG
        gap = lows[i-1] - highs[i+1]
        if gap > 0 and bias in ("BEARISH", "NEUTRAL"):
            mid_ref = (highs[i-1] + lows[i-1]) / 2
            if mid_ref > 0 and gap / mid_ref >= 0.0005:
                dist = abs(current_price - (lows[i-1] + highs[i+1]) / 2) / current_price
                if dist < 0.005:
                    best_fvg = (lows[i-1], highs[i+1])
                    best_dir = "SHORT"
                    break

    if best_fvg:
        fvg_high = max(best_fvg)
        fvg_low  = min(best_fvg)
        fvg_mid  = (fvg_high + fvg_low) / 2
        result = SilverBulletResult(
            active=True, has_setup=True,
            window_name=active_window, direction=best_dir,
            fvg_high=round(fvg_high, 6), fvg_low=round(fvg_low, 6),
            fvg_mid=round(fvg_mid, 6), score_boost=3,
        )
        log_agent("SilverBulletAgent", symbol,
                  f"Window={active_window} | {best_dir} FVG [{fvg_low:.5f}-{fvg_high:.5f}] | +3pts")
    else:
        result = SilverBulletResult(
            active=True, has_setup=False,
            window_name=active_window, direction="",
            fvg_high=0, fvg_low=0, fvg_mid=0, score_boost=1,
        )
        log_agent("SilverBulletAgent", symbol,
                  f"Window={active_window} active, no FVG setup | +1pt")

    return result
