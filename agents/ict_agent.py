"""
ICT Analysis Agent  —  يحلل السوق بالكامل بمفاهيم ICT
Implements: Market Structure · BOS/CHoCH · Order Blocks ·
            Fair Value Gaps · Liquidity Levels · PD Arrays
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


# ──────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ──────────────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str   # "HH" | "HL" | "LH" | "LL"

@dataclass
class OrderBlock:
    high: float
    low: float
    mid: float
    direction: str   # "BULL" | "BEAR"
    index: int
    broken: bool = False

@dataclass
class FVG:
    high: float
    low: float
    mid: float
    direction: str   # "BULL" | "BEAR"
    index: int
    filled: bool = False

@dataclass
class LiquidityLevel:
    price: float
    kind: str        # "BSL" buy-side  | "SSL" sell-side
    index: int
    swept: bool = False

@dataclass
class ICTAnalysis:
    symbol:        str
    market:        str
    bias:          str           # "BULLISH" | "BEARISH" | "NEUTRAL"
    structure:     str           # "BOS_UP" | "BOS_DOWN" | "CHOCH_UP" | "CHOCH_DOWN" | "RANGING"
    order_blocks:  list[OrderBlock] = field(default_factory=list)
    fvgs:          list[FVG]        = field(default_factory=list)
    liquidity:     list[LiquidityLevel] = field(default_factory=list)
    premium_zone:  float = 0.0
    discount_zone: float = 0.0
    equilibrium:   float = 0.0
    current_price: float = 0.0
    in_premium:    bool  = False
    in_discount:   bool  = False
    setup_score:   int   = 0     # 0-15 (extended)
    # Extended ICT concepts (populated by main.py pipeline)
    pdh_pdl:        object = None   # PDHPDLResult
    po3:            object = None   # PO3Result
    breaker:        object = None   # BreakerResult
    silver_bullet:  object = None   # SilverBulletResult
    displacement:   object = None   # DisplacementResult
    volume_profile: object = None   # VolumeProfileResult
    divergence:     object = None   # DivergenceResult


# ──────────────────────────────────────────────────────────────────
#  SWING DETECTION
# ──────────────────────────────────────────────────────────────────

def detect_swings(df: pd.DataFrame, left: int = 5, right: int = 5) -> list[SwingPoint]:
    swings = []
    highs = df["high"].values
    lows  = df["low"].values

    for i in range(left, len(df) - right):
        is_swing_high = all(highs[i] >= highs[i-j] for j in range(1, left+1)) and \
                        all(highs[i] >= highs[i+j] for j in range(1, right+1))
        is_swing_low  = all(lows[i]  <= lows[i-j]  for j in range(1, left+1)) and \
                        all(lows[i]  <= lows[i+j]   for j in range(1, right+1))
        if is_swing_high:
            swings.append(SwingPoint(i, highs[i], "swing_high"))
        if is_swing_low:
            swings.append(SwingPoint(i, lows[i], "swing_low"))

    return sorted(swings, key=lambda s: s.index)


def classify_structure(swings: list[SwingPoint]) -> tuple[str, str]:
    """
    Returns (structure_label, bias)
    """
    highs = [s for s in swings if s.kind == "swing_high"]
    lows  = [s for s in swings if s.kind == "swing_low"]

    if len(highs) < 2 or len(lows) < 2:
        return "RANGING", "NEUTRAL"

    last_h, prev_h = highs[-1], highs[-2]
    last_l, prev_l = lows[-1],  lows[-2]

    # Bullish structure
    if last_h.price > prev_h.price and last_l.price > prev_l.price:
        return "BOS_UP", "BULLISH"
    # Bearish structure
    if last_h.price < prev_h.price and last_l.price < prev_l.price:
        return "BOS_DOWN", "BEARISH"
    # Change of character
    if last_l.price < prev_l.price and last_h.price > prev_h.price:
        return "CHOCH_UP", "BULLISH"
    if last_h.price < prev_h.price and last_l.price > prev_l.price:
        return "CHOCH_DOWN", "BEARISH"

    return "RANGING", "NEUTRAL"


# ──────────────────────────────────────────────────────────────────
#  ORDER BLOCKS
# ──────────────────────────────────────────────────────────────────

def detect_order_blocks(df: pd.DataFrame, bias: str,
                        lookback: int = 50) -> list[OrderBlock]:
    obs = []
    closes = df["close"].values
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    n = min(len(df), lookback)

    for i in range(2, n - 1):
        # Bullish OB: last bearish candle before a bullish impulse (3+ candles up)
        if bias in ("BULLISH", "NEUTRAL"):
            is_bearish = closes[i] < opens[i]
            impulse_up = all(closes[i+j] > closes[i+j-1] for j in range(1, min(3, n-i)))
            if is_bearish and impulse_up:
                ob = OrderBlock(
                    high=highs[i], low=lows[i],
                    mid=(highs[i]+lows[i])/2,
                    direction="BULL", index=i
                )
                obs.append(ob)

        # Bearish OB: last bullish candle before a bearish impulse
        if bias in ("BEARISH", "NEUTRAL"):
            is_bullish = closes[i] > opens[i]
            impulse_dn = all(closes[i+j] < closes[i+j-1] for j in range(1, min(3, n-i)))
            if is_bullish and impulse_dn:
                ob = OrderBlock(
                    high=highs[i], low=lows[i],
                    mid=(highs[i]+lows[i])/2,
                    direction="BEAR", index=i
                )
                obs.append(ob)

    # Mark broken OBs (price has closed through them)
    last_close = closes[-1]
    for ob in obs:
        if ob.direction == "BULL" and last_close < ob.low:
            ob.broken = True
        if ob.direction == "BEAR" and last_close > ob.high:
            ob.broken = True

    # Return unbroken OBs only, most recent first
    valid = [ob for ob in obs if not ob.broken]
    return sorted(valid, key=lambda x: x.index, reverse=True)[:5]


# ──────────────────────────────────────────────────────────────────
#  FAIR VALUE GAPS (FVG / IFVG)
# ──────────────────────────────────────────────────────────────────

def detect_fvgs(df: pd.DataFrame, bias: str,
                min_gap_pct: float = 0.001) -> list[FVG]:
    fvgs = []
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    n = len(df)

    for i in range(1, n - 1):
        gap_bull = lows[i+1] - highs[i-1]   # Bullish FVG
        gap_bear = lows[i-1] - highs[i+1]   # Bearish FVG
        mid_p    = (highs[i-1] + lows[i-1]) / 2

        if gap_bull > 0 and (gap_bull / mid_p) >= min_gap_pct:
            if bias in ("BULLISH", "NEUTRAL"):
                fvgs.append(FVG(
                    high=lows[i+1], low=highs[i-1],
                    mid=(lows[i+1]+highs[i-1])/2,
                    direction="BULL", index=i
                ))

        if gap_bear > 0 and (gap_bear / mid_p) >= min_gap_pct:
            if bias in ("BEARISH", "NEUTRAL"):
                fvgs.append(FVG(
                    high=lows[i-1], low=highs[i+1],
                    mid=(lows[i-1]+highs[i+1])/2,
                    direction="BEAR", index=i
                ))

    # Mark filled FVGs
    last_close = closes[-1]
    for fvg in fvgs:
        if fvg.direction == "BULL" and last_close < fvg.low:
            fvg.filled = True
        if fvg.direction == "BEAR" and last_close > fvg.high:
            fvg.filled = True

    valid = [f for f in fvgs if not f.filled]
    return sorted(valid, key=lambda x: x.index, reverse=True)[:5]


# ──────────────────────────────────────────────────────────────────
#  LIQUIDITY LEVELS
# ──────────────────────────────────────────────────────────────────

def detect_liquidity(df: pd.DataFrame,
                     tolerance_pct: float = 0.001) -> list[LiquidityLevel]:
    levels = []
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(df)

    # Equal highs (Buy-Side Liquidity above)  &  Equal lows (Sell-Side below)
    for i in range(5, n - 1):
        # Check for equal highs in last 20 bars
        window_h = highs[max(0,i-20):i]
        for h in window_h:
            if abs(highs[i] - h) / h < tolerance_pct:
                levels.append(LiquidityLevel(
                    price=highs[i], kind="BSL", index=i))
                break

        window_l = lows[max(0,i-20):i]
        for l in window_l:
            if abs(lows[i] - l) / l < tolerance_pct:
                levels.append(LiquidityLevel(
                    price=lows[i], kind="SSL", index=i))
                break

    # Add previous day high/low as liquidity
    if n >= 96:  # At least 1 day of 15m data
        prev_day = df.iloc[-97:-1]
        pdh = prev_day["high"].max()
        pdl = prev_day["low"].min()
        levels.append(LiquidityLevel(price=pdh, kind="BSL", index=n-97))
        levels.append(LiquidityLevel(price=pdl, kind="SSL", index=n-97))

    last_close = df["close"].iloc[-1]
    for lv in levels:
        if lv.kind == "BSL" and last_close > lv.price:
            lv.swept = True
        if lv.kind == "SSL" and last_close < lv.price:
            lv.swept = True

    return [lv for lv in levels if not lv.swept]


# ──────────────────────────────────────────────────────────────────
#  PREMIUM / DISCOUNT
# ──────────────────────────────────────────────────────────────────

def calc_pd_arrays(df: pd.DataFrame, lookback: int = 100) -> tuple[float, float, float]:
    """Returns (premium_level, equilibrium, discount_level)"""
    sub     = df.iloc[-lookback:]
    high    = sub["high"].max()
    low     = sub["low"].min()
    eq      = (high + low) / 2
    premium = eq + (high - eq) * 0.5   # 75% level
    discount= low  + (eq  - low) * 0.5  # 25% level
    return premium, eq, discount


# ──────────────────────────────────────────────────────────────────
#  SETUP SCORE  (0-10)
# ──────────────────────────────────────────────────────────────────

def score_setup(analysis: ICTAnalysis) -> int:
    score = 0
    price = analysis.current_price

    # Bias defined (+2)
    if analysis.bias != "NEUTRAL":
        score += 2

    # Structure clear (+2 BOS / +1 CHoCH)
    if "BOS" in analysis.structure:
        score += 2
    elif "CHOCH" in analysis.structure:
        score += 1

    # OB near price (+2)
    for ob in analysis.order_blocks[:2]:
        if ob.low <= price <= ob.high * 1.002:
            score += 2
            break

    # FVG near price (+2)
    for fvg in analysis.fvgs[:2]:
        if fvg.low <= price <= fvg.high * 1.002:
            score += 2
            break

    # Price in discount/premium (+1)
    if analysis.bias == "BULLISH" and analysis.in_discount:
        score += 1
    if analysis.bias == "BEARISH" and analysis.in_premium:
        score += 1

    # Liquidity sweep nearby (+1)
    for lv in analysis.liquidity[:3]:
        diff_pct = abs(lv.price - price) / price
        if diff_pct < 0.005:
            score += 1
            break

    # PO3 Power of 3 (+2 if distribution_bias matches)
    po3 = analysis.po3
    if po3 and po3.score_boost > 0:
        if po3.distribution_bias == analysis.bias:
            score += po3.score_boost

    # Breaker Block confluence (+2)
    breaker = analysis.breaker
    if breaker and breaker.score_boost > 0:
        bb = breaker.best_breaker
        if bb:
            aligned = (analysis.bias == "BULLISH" and bb.direction == "BULL") or \
                      (analysis.bias == "BEARISH" and bb.direction == "BEAR")
            if aligned:
                score += breaker.score_boost

    # Silver Bullet window (+1 active, +3 with setup)
    sb = analysis.silver_bullet
    if sb and sb.active:
        sb_aligned = (sb.direction == "LONG" and analysis.bias == "BULLISH") or \
                     (sb.direction == "SHORT" and analysis.bias == "BEARISH") or \
                     not sb.has_setup
        if sb_aligned:
            score += sb.score_boost

    # Displacement (+1/+2 if aligned with bias)
    disp = analysis.displacement
    if disp and disp.detected:
        dir_match = (disp.direction == "UP" and analysis.bias == "BULLISH") or \
                    (disp.direction == "DOWN" and analysis.bias == "BEARISH")
        if dir_match:
            score += disp.score_boost

    # Divergence (+2 aligned / +1 any)
    div = analysis.divergence
    if div and div.score_boost > 0:
        score += div.score_boost

    return min(score, 15)


# ──────────────────────────────────────────────────────────────────
#  MAIN  ANALYSIS
# ──────────────────────────────────────────────────────────────────

def analyze(symbol: str, market: str,
            df_htf: pd.DataFrame, df_ltf: pd.DataFrame) -> Optional[ICTAnalysis]:
    """
    Full ICT analysis.
    df_htf = 1h candles (bias)
    df_ltf = 15m candles (entry precision)
    """
    if df_htf.empty or df_ltf.empty:
        log_agent("ICTAgent", symbol, "Insufficient data — skipping")
        return None

    # 1. Market structure & bias on HTF
    swings_htf        = detect_swings(df_htf, left=5, right=5)
    structure, bias   = classify_structure(swings_htf)

    # 2. PD Arrays
    premium, eq, discount = calc_pd_arrays(df_htf)

    # 3. Current price
    current_price = float(df_ltf["close"].iloc[-1])

    # 4. In premium / discount?
    in_premium  = current_price >= premium
    in_discount = current_price <= discount

    # 5. OBs & FVGs on LTF
    obs  = detect_order_blocks(df_ltf, bias)
    fvgs = detect_fvgs(df_ltf, bias)

    # 6. Liquidity
    liquidity = detect_liquidity(df_ltf)

    analysis = ICTAnalysis(
        symbol        = symbol,
        market        = market,
        bias          = bias,
        structure     = structure,
        order_blocks  = obs,
        fvgs          = fvgs,
        liquidity     = liquidity,
        premium_zone  = premium,
        discount_zone = discount,
        equilibrium   = eq,
        current_price = current_price,
        in_premium    = in_premium,
        in_discount   = in_discount,
    )

    analysis.setup_score = score_setup(analysis)

    log_agent("ICTAgent", symbol,
              f"Bias={bias} | Struct={structure} | "
              f"OBs={len(obs)} | FVGs={len(fvgs)} | Score={analysis.setup_score}/10")

    return analysis


def get_best_entry_zone(analysis: ICTAnalysis) -> Optional[dict]:
    """
    Returns the best entry zone (OB+FVG confluence preferred).
    """
    if analysis.setup_score < 6:
        return None

    price = analysis.current_price

    # Look for OB+FVG confluence
    for ob in analysis.order_blocks[:3]:
        for fvg in analysis.fvgs[:3]:
            if ob.direction == fvg.direction:
                overlap_high = min(ob.high, fvg.high)
                overlap_low  = max(ob.low,  fvg.low)
                if overlap_low < overlap_high:
                    dist = abs(price - (overlap_high+overlap_low)/2) / price
                    if dist < 0.01:  # within 1% of price
                        return {
                            "type": "OB+FVG",
                            "high": overlap_high,
                            "low":  overlap_low,
                            "mid":  (overlap_high+overlap_low)/2,
                            "direction": ob.direction
                        }

    # Fallback: standalone OB
    for ob in analysis.order_blocks[:2]:
        dist = abs(price - ob.mid) / price
        if dist < 0.008:
            return {
                "type": "OB",
                "high": ob.high,
                "low":  ob.low,
                "mid":  ob.mid,
                "direction": ob.direction
            }

    # Fallback: standalone FVG
    for fvg in analysis.fvgs[:2]:
        dist = abs(price - fvg.mid) / price
        if dist < 0.008:
            return {
                "type": "FVG",
                "high": fvg.high,
                "low":  fvg.low,
                "mid":  fvg.mid,
                "direction": fvg.direction
            }

    return None
