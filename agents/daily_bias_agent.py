"""
Daily Bias Agent  —  EMA20/EMA50 trend filter on daily candles
Provides a higher-timeframe trend bias to filter LTF entries.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


@dataclass
class DailyBiasResult:
    bias:     str    # "BULLISH" | "BEARISH" | "NEUTRAL"
    ema20:    float
    ema50:    float
    price:    float
    score:    int    # 0-3 alignment score


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    k = 2 / (period + 1)
    out = np.zeros(len(arr))
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = arr[i] * k + out[i-1] * (1 - k)
    return out


def get_daily_bias(symbol: str, df_daily: pd.DataFrame) -> DailyBiasResult:
    """
    Bias logic:
    - Price > EMA20 > EMA50 → BULLISH (strong)
    - Price < EMA20 < EMA50 → BEARISH (strong)
    - EMA20 > EMA50 but price below → weakly bullish → NEUTRAL
    - else NEUTRAL
    """
    _default = DailyBiasResult("NEUTRAL", 0, 0, 0, 0)

    if df_daily is None or df_daily.empty or len(df_daily) < 50:
        return _default

    closes = df_daily["close"].values.astype(float)
    ema20_arr = _ema(closes, 20)
    ema50_arr = _ema(closes, 50)

    price  = float(closes[-1])
    ema20  = float(ema20_arr[-1])
    ema50  = float(ema50_arr[-1])

    score = 0
    if price > ema20: score += 1
    if ema20 > ema50: score += 1
    if price > ema50: score += 1

    if score == 3:
        bias = "BULLISH"
    elif score == 0:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    result = DailyBiasResult(
        bias=bias, ema20=round(ema20, 5), ema50=round(ema50, 5),
        price=round(price, 5), score=score,
    )
    log_agent("DailyBiasAgent", symbol,
              f"Bias={bias} | Price={price:.5f} EMA20={ema20:.5f} EMA50={ema50:.5f} | score={score}/3")
    return result


def daily_bias_filter(daily_bias: DailyBiasResult, ict_bias: str,
                      setup_score: int) -> tuple[bool, str]:
    """
    Block trade if daily bias strongly contradicts ICT bias and score < 8.
    """
    if daily_bias.bias == "NEUTRAL":
        return True, "Daily bias neutral — no block"
    if daily_bias.bias == ict_bias:
        return True, f"Daily bias confirms {ict_bias}"
    if setup_score >= 8:
        return True, f"High score ({setup_score}) overrides daily bias conflict"
    return False, (f"Daily {daily_bias.bias} contradicts ICT {ict_bias} "
                   f"(score={setup_score} < 8) — skip")
