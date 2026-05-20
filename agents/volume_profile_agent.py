"""
Volume Profile Agent  —  POC / VAH / VAL analysis
Builds a volume histogram (or equal-weight proxy) over recent candles.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class VolumeProfileResult:
    poc:           float   # Point of Control
    vah:           float   # Value Area High (70% of volume)
    val:           float   # Value Area Low  (70% of volume)
    in_value_area: bool
    above_poc:     bool
    poc_dist_pct:  float
    score_boost:   int


def analyze_volume_profile(symbol: str, df: pd.DataFrame,
                           current_price: float, bins: int = 100) -> VolumeProfileResult:
    """
    Builds a price-volume histogram over the last 200 candles.
    Falls back to tick-count (equal weight per candle) if volume=0.
    """
    _default = VolumeProfileResult(0, 0, 0, False, False, 0, 0)

    if df is None or df.empty or len(df) < 20:
        return _default

    sub = df.iloc[-200:]
    highs  = sub["high"].values
    lows   = sub["low"].values
    vols   = sub["volume"].values

    price_min = float(lows.min())
    price_max = float(highs.max())
    if price_max <= price_min:
        return _default

    use_equal_weight = float(vols.sum()) < 1.0

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    hist = np.zeros(bins)

    for i in range(len(sub)):
        lo, hi = lows[i], highs[i]
        vol = 1.0 if use_equal_weight else vols[i]
        if vol <= 0:
            vol = 1.0

        lo_bin = max(0, np.searchsorted(bin_edges, lo, side="left") - 1)
        hi_bin = min(bins - 1, np.searchsorted(bin_edges, hi, side="right") - 1)

        if lo_bin > hi_bin:
            continue

        span = hi_bin - lo_bin + 1
        hist[lo_bin:hi_bin+1] += vol / span

    # POC = bin with highest volume
    poc_bin = int(np.argmax(hist))
    poc = float((bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2)

    # Value Area: expand from POC until 70% of total volume is included
    total_vol = hist.sum()
    target    = total_vol * 0.70

    lo_idx = poc_bin
    hi_idx = poc_bin
    accumulated = hist[poc_bin]

    while accumulated < target:
        can_go_up   = hi_idx + 1 < bins
        can_go_down = lo_idx - 1 >= 0

        if not can_go_up and not can_go_down:
            break

        add_up   = hist[hi_idx + 1] if can_go_up   else -1
        add_down = hist[lo_idx - 1] if can_go_down else -1

        if add_up >= add_down:
            hi_idx += 1
            accumulated += add_up
        else:
            lo_idx -= 1
            accumulated += add_down

    vah = float(bin_edges[hi_idx + 1])
    val = float(bin_edges[lo_idx])

    in_value_area = val <= current_price <= vah
    above_poc     = current_price > poc
    poc_dist_pct  = abs(current_price - poc) / poc * 100 if poc > 0 else 0

    # Score: +1 if price is near POC (within 0.3%) — confluence zone
    score_boost = 1 if poc_dist_pct < 0.3 else 0

    result = VolumeProfileResult(
        poc=round(poc, 6), vah=round(vah, 6), val=round(val, 6),
        in_value_area=in_value_area, above_poc=above_poc,
        poc_dist_pct=round(poc_dist_pct, 3), score_boost=score_boost,
    )

    log_agent("VolProfileAgent", symbol,
              f"POC={poc:.5f} VAH={vah:.5f} VAL={val:.5f} | "
              f"in_VA={in_value_area} | dist={poc_dist_pct:.2f}% | +{score_boost}pts")
    return result
