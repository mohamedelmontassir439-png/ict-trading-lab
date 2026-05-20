"""
PDH/PDL Agent  —  Previous Day High / Low analysis
Detects if today's price has swept PDH or PDL, and derives bias hint.
"""
import pandas as pd
from dataclasses import dataclass
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class PDHPDLResult:
    pdh:           float
    pdl:           float
    pdh_swept:     bool
    pdl_swept:     bool
    bias_hint:     str    # "BULLISH" | "BEARISH" | "NEUTRAL"
    pdh_dist_pct:  float
    pdl_dist_pct:  float


def analyze_pdh_pdl(symbol: str, df_daily: pd.DataFrame,
                    df_ltf: pd.DataFrame, current_price: float) -> PDHPDLResult:
    """
    Uses yesterday's daily candle for PDH/PDL.
    Checks if LTF has swept those levels today.
    """
    _default = PDHPDLResult(0, 0, False, False, "NEUTRAL", 0, 0)

    if df_daily is None or df_daily.empty or len(df_daily) < 2:
        return _default
    if df_ltf is None or df_ltf.empty:
        return _default

    prev_day = df_daily.iloc[-2]
    pdh = float(prev_day["high"])
    pdl = float(prev_day["low"])

    if pdh <= 0 or pdl <= 0:
        return _default

    # Check if today's LTF price reached PDH / PDL
    today_high = float(df_ltf["high"].max())
    today_low  = float(df_ltf["low"].min())

    pdh_swept = today_high >= pdh
    pdl_swept = today_low  <= pdl

    # Bias hint: if swept PDH → bearish (liquidity grabbed above, expect sell)
    # if swept PDL → bullish (stop-hunt below, expect buy)
    if pdh_swept and not pdl_swept:
        bias_hint = "BEARISH"
    elif pdl_swept and not pdh_swept:
        bias_hint = "BULLISH"
    else:
        bias_hint = "NEUTRAL"

    pdh_dist_pct = abs(current_price - pdh) / pdh * 100
    pdl_dist_pct = abs(current_price - pdl) / pdl * 100

    result = PDHPDLResult(
        pdh=round(pdh, 6), pdl=round(pdl, 6),
        pdh_swept=pdh_swept, pdl_swept=pdl_swept,
        bias_hint=bias_hint,
        pdh_dist_pct=round(pdh_dist_pct, 3),
        pdl_dist_pct=round(pdl_dist_pct, 3),
    )

    log_agent("PDHPDLAgent", symbol,
              f"PDH={pdh:.5f}{'✓' if pdh_swept else ''} "
              f"PDL={pdl:.5f}{'✓' if pdl_swept else ''} | hint={bias_hint}")
    return result
