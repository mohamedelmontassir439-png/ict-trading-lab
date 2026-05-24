"""
ICT Analysis Agent — محرك تحليل ICT الكامل
يطبّق منهجية مايكل هودلستون (Inner Circle Trader) بدقة:

  ✦ Market Structure: HH/HL/LH/LL + BOS + CHoCH (MSS)
  ✦ Displacement Candles: شموع الزخم القوي التي تخلق FVG
  ✦ Order Blocks: آخر شمعة عكسية قبل Displacement مُتحقَّق منها
  ✦ Fair Value Gaps: فجوات ناتجة عن Displacement فقط
  ✦ Liquidity Sweep: اصطياد BSL/SSL قبل الانعكاس
  ✦ OTE (Optimal Trade Entry): مناطق 61.8%–78.6% فيبوناتشي
  ✦ Market Maker Model (AMD): تراكم → تلاعب → توزيع
  ✦ Session Levels: مستويات الجلسات (NY / London / Asian)
  ✦ Premium/Discount arrays مع EQ50
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import log_agent


# ══════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SwingPoint:
    index: int
    price: float
    kind:  str   # "HH" | "HL" | "LH" | "LL" | "swing_high" | "swing_low"
    confirmed: bool = False

@dataclass
class DisplacementCandle:
    index:      int
    direction:  str     # "BULL" | "BEAR"
    body_pct:   float   # حجم الجسم كنسبة من السعر
    creates_fvg: bool

@dataclass
class OrderBlock:
    high:  float
    low:   float
    mid:   float
    direction:             str    # "BULL" | "BEAR"
    index:                 int
    displacement_verified: bool  = False
    broken:                bool  = False
    mitigated_50:          bool  = False   # وصل السعر لـ 50% من الـ OB
    ote_entry:             float = 0.0    # أفضل نقطة دخول داخل OB

@dataclass
class FVG:
    high:  float
    low:   float
    mid:   float
    direction:             str    # "BULL" | "BEAR"
    index:                 int
    filled:                bool  = False
    displacement_verified: bool  = False
    fill_pct:              float = 0.0    # نسبة الامتلاء 0-100

@dataclass
class LiquidityLevel:
    price:       float
    kind:        str    # "BSL" | "SSL"
    index:       int
    swept:       bool = False
    sweep_index: int  = -1   # الشمعة التي اصطادت السيولة

@dataclass
class OTEZone:
    high:       float    # مستوى 61.8%
    low:        float    # مستوى 78.6%
    fib_705:    float    # مستوى 70.5% (أفضل دخول)
    direction:  str      # "BULL" | "BEAR"
    swing_high: float
    swing_low:  float

@dataclass
class SessionLevel:
    price: float
    kind:  str    # "NY_HIGH" | "NY_LOW" | "LON_HIGH" | "LON_LOW" | "ASIA_HIGH" | "ASIA_LOW"
    swept: bool = False

@dataclass
class MarketMakerModel:
    """AMD: Accumulation → Manipulation → Distribution"""
    phase:              str    # "ACCUMULATION" | "MANIPULATION" | "DISTRIBUTION" | "UNKNOWN"
    manipulation_dir:   str    # اتجاه التلاعب (ضد الاتجاه الحقيقي)
    distribution_dir:   str    # الاتجاه الحقيقي
    liquidity_swept:    bool
    displacement_found: bool
    confidence:         int    # 0-10

@dataclass
class ICTAnalysis:
    symbol:        str
    market:        str
    bias:          str           # "BULLISH" | "BEARISH" | "NEUTRAL"
    structure:     str           # "BOS_UP" | "BOS_DOWN" | "CHOCH_UP" | "CHOCH_DOWN" | "RANGING"
    order_blocks:  list[OrderBlock]   = field(default_factory=list)
    fvgs:          list[FVG]          = field(default_factory=list)
    liquidity:     list[LiquidityLevel] = field(default_factory=list)
    ote_zone:      Optional[OTEZone]  = None
    session_levels: list[SessionLevel] = field(default_factory=list)
    mm_model:      Optional[MarketMakerModel] = None
    premium_zone:  float = 0.0
    discount_zone: float = 0.0
    equilibrium:   float = 0.0
    current_price: float = 0.0
    in_premium:    bool  = False
    in_discount:   bool  = False
    setup_score:   int   = 0
    # Extended agents (populated by main.py pipeline)
    pdh_pdl:        object = None
    po3:            object = None
    breaker:        object = None
    silver_bullet:  object = None
    displacement:   object = None
    volume_profile: object = None
    divergence:     object = None


# ══════════════════════════════════════════════════════════════════════
#  1. SWING DETECTION  —  الكشف عن القيعان والقمم
# ══════════════════════════════════════════════════════════════════════

def detect_swings(df: pd.DataFrame, left: int = 5, right: int = 5) -> list[SwingPoint]:
    """
    اكتشف swing highs و swing lows بدقة.
    يستخدم left/right bars للتأكيد (لا تسرّع قبل اكتمال right bars).
    """
    swings = []
    highs  = df["high"].values
    lows   = df["low"].values
    n      = len(df)

    for i in range(left, n - right):
        # Swing High
        if (all(highs[i] > highs[i-j] for j in range(1, left+1)) and
                all(highs[i] > highs[i+j] for j in range(1, right+1))):
            swings.append(SwingPoint(i, highs[i], "swing_high", confirmed=True))

        # Swing Low
        if (all(lows[i] < lows[i-j]  for j in range(1, left+1)) and
                all(lows[i] < lows[i+j]  for j in range(1, right+1))):
            swings.append(SwingPoint(i, lows[i],  "swing_low",  confirmed=True))

    return sorted(swings, key=lambda s: s.index)


def classify_swings(swings: list[SwingPoint]) -> list[SwingPoint]:
    """
    صنّف swing points إلى HH / HL / LH / LL.
    هذا هو المبدأ الأساسي لـ ICT Market Structure.
    """
    highs = [s for s in swings if s.kind in ("swing_high", "HH", "LH")]
    lows  = [s for s in swings if s.kind in ("swing_low",  "HL", "LL")]

    for i, h in enumerate(highs):
        if i == 0:
            h.kind = "swing_high"
        elif h.price > highs[i-1].price:
            h.kind = "HH"   # Higher High
        else:
            h.kind = "LH"   # Lower High

    for i, l in enumerate(lows):
        if i == 0:
            l.kind = "swing_low"
        elif l.price > lows[i-1].price:
            l.kind = "HL"   # Higher Low
        else:
            l.kind = "LL"   # Lower Low

    return sorted(highs + lows, key=lambda s: s.index)


def classify_structure(swings: list[SwingPoint]) -> tuple[str, str]:
    """
    Returns (structure_label, bias).
    يستخدم HH/HL/LH/LL لتحديد هيكل السوق بدقة ICT.
    """
    highs = [s for s in swings if s.kind in ("swing_high", "HH", "LH")]
    lows  = [s for s in swings if s.kind in ("swing_low",  "HL", "LL")]

    if len(highs) < 2 or len(lows) < 2:
        return "RANGING", "NEUTRAL"

    last_h, prev_h = highs[-1], highs[-2]
    last_l, prev_l = lows[-1],  lows[-2]

    # BOS صعود: HH + HL
    if last_h.price > prev_h.price and last_l.price > prev_l.price:
        return "BOS_UP", "BULLISH"
    # BOS هبوط: LH + LL
    if last_h.price < prev_h.price and last_l.price < prev_l.price:
        return "BOS_DOWN", "BEARISH"
    # CHoCH (تغيير الشخصية): كسر عكسي
    if last_l.price < prev_l.price and last_h.price > prev_h.price:
        return "CHOCH_UP", "BULLISH"
    if last_h.price < prev_h.price and last_l.price > prev_l.price:
        return "CHOCH_DOWN", "BEARISH"

    return "RANGING", "NEUTRAL"


# ══════════════════════════════════════════════════════════════════════
#  2. DISPLACEMENT CANDLES  —  شموع الإزاحة القوية
# ══════════════════════════════════════════════════════════════════════

def detect_displacement_candles(df: pd.DataFrame,
                                 body_ratio: float = 2.0,
                                 lookback: int = 20) -> list[DisplacementCandle]:
    """
    شمعة Displacement = شمعة بجسم كبير (≥ body_ratio × متوسط الأجسام)
    تخلق FVG (فجوة قيمة عادلة).

    ICT: الـ Displacement هو الدليل على وجود أموال ذكية (Smart Money).
    """
    closes = df["close"].values
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    n      = len(df)

    bodies     = np.abs(closes - opens)
    avg_bodies = pd.Series(bodies).rolling(lookback, min_periods=3).mean().values

    result = []
    for i in range(1, n - 1):
        if avg_bodies[i] <= 0:
            continue
        ratio = bodies[i] / avg_bodies[i]
        if ratio < body_ratio:
            continue

        is_bull = closes[i] > opens[i]
        direction = "BULL" if is_bull else "BEAR"

        # هل تخلق FVG؟
        if is_bull:
            fvg = lows[i+1] - highs[i-1] > 0
        else:
            fvg = lows[i-1] - highs[i+1] > 0

        body_pct = bodies[i] / closes[i] if closes[i] > 0 else 0

        result.append(DisplacementCandle(
            index       = i,
            direction   = direction,
            body_pct    = body_pct,
            creates_fvg = fvg,
        ))

    return result


# ══════════════════════════════════════════════════════════════════════
#  3. ORDER BLOCKS  —  مناطق تجميع أوامر الأموال الذكية
# ══════════════════════════════════════════════════════════════════════

def detect_order_blocks(df: pd.DataFrame, bias: str,
                        lookback: int = 100) -> list[OrderBlock]:
    """
    OB القواعد الحقيقية لـ ICT:
    1. آخر شمعة عكسية قبل شمعة Displacement
    2. يجب أن يكون اتجاه Displacement متوافقاً مع الـ bias
    3. OB غير مُخترَق (لم يُغلق السعر خلفه)
    4. يُحسب OTE entry = 50% من OB (منتصف القضبان)
    """
    df_r = df.iloc[-lookback:].copy() if len(df) > lookback else df.copy()
    displacements = detect_displacement_candles(df_r, body_ratio=1.8)

    closes = df_r["close"].values
    opens  = df_r["open"].values
    highs  = df_r["high"].values
    lows   = df_r["low"].values
    n      = len(df_r)

    obs = []
    used_indices = set()

    for disp in displacements:
        i = disp.index
        if i < 1 or i >= n - 1:
            continue

        if disp.direction == "BULL" and bias in ("BULLISH", "NEUTRAL"):
            # Bullish OB: آخر شمعة هابطة قبل Displacement صاعد
            for j in range(i - 1, max(i - 10, 0), -1):
                if j in used_indices:
                    continue
                if closes[j] < opens[j]:   # شمعة هابطة = Bullish OB
                    ob = OrderBlock(
                        high  = highs[j],
                        low   = lows[j],
                        mid   = (highs[j] + lows[j]) / 2,
                        direction = "BULL",
                        index = j,
                        displacement_verified = True,
                        ote_entry = lows[j] + (highs[j] - lows[j]) * 0.5,  # 50% OTE
                    )
                    obs.append(ob)
                    used_indices.add(j)
                    break

        elif disp.direction == "BEAR" and bias in ("BEARISH", "NEUTRAL"):
            # Bearish OB: آخر شمعة صاعدة قبل Displacement هابط
            for j in range(i - 1, max(i - 10, 0), -1):
                if j in used_indices:
                    continue
                if closes[j] > opens[j]:   # شمعة صاعدة = Bearish OB
                    ob = OrderBlock(
                        high  = highs[j],
                        low   = lows[j],
                        mid   = (highs[j] + lows[j]) / 2,
                        direction = "BEAR",
                        index = j,
                        displacement_verified = True,
                        ote_entry = highs[j] - (highs[j] - lows[j]) * 0.5,
                    )
                    obs.append(ob)
                    used_indices.add(j)
                    break

    # تصفية OBs المكسورة والمُخففة
    last_close = closes[-1]
    for ob in obs:
        if ob.direction == "BULL":
            if last_close < ob.low:
                ob.broken = True
            elif last_close < ob.mid:
                ob.mitigated_50 = True
        else:
            if last_close > ob.high:
                ob.broken = True
            elif last_close > ob.mid:
                ob.mitigated_50 = True

    valid = [ob for ob in obs if not ob.broken]
    return sorted(valid, key=lambda x: x.index, reverse=True)[:5]


# ══════════════════════════════════════════════════════════════════════
#  4. FAIR VALUE GAPS  —  فجوات القيمة العادلة
# ══════════════════════════════════════════════════════════════════════

def detect_fvgs(df: pd.DataFrame, bias: str,
                min_gap_pct: float = 0.001, lookback: int = 200) -> list[FVG]:
    """
    FVG القواعد ICT الحقيقية:
    - الفجوة بين high[i-1] و low[i+1] للصاعد
    - الفجوة بين low[i-1] و high[i+1] للهابط
    - يُفضَّل أن تكون ناتجة عن Displacement
    - تُحسب نسبة الامتلاء (إذا تجاوز 50% → أقل جودة)
    """
    df_r = df.iloc[-lookback:].copy() if len(df) > lookback else df.copy()
    displacements = detect_displacement_candles(df_r, body_ratio=1.5)
    disp_indices  = {d.index for d in displacements}

    highs  = df_r["high"].values
    lows   = df_r["low"].values
    closes = df_r["close"].values
    n      = len(df_r)

    last_close = closes[-1]
    fvgs = []

    for i in range(1, n - 1):
        mid_p = (highs[i-1] + lows[i-1]) / 2 if highs[i-1] > 0 else 1

        # Bullish FVG
        gap_bull = lows[i+1] - highs[i-1]
        if gap_bull > 0 and (gap_bull / mid_p) >= min_gap_pct:
            if bias in ("BULLISH", "NEUTRAL"):
                fill_amount = max(0, last_close - lows[i+1])
                fill_pct    = min(100, fill_amount / gap_bull * 100) if gap_bull > 0 else 0
                filled      = last_close < highs[i-1]   # كُسرت الفجوة للأسفل
                fvgs.append(FVG(
                    high  = lows[i+1],
                    low   = highs[i-1],
                    mid   = (lows[i+1] + highs[i-1]) / 2,
                    direction = "BULL",
                    index = i,
                    filled = filled,
                    displacement_verified = (i in disp_indices),
                    fill_pct = fill_pct,
                ))

        # Bearish FVG
        gap_bear = lows[i-1] - highs[i+1]
        if gap_bear > 0 and (gap_bear / mid_p) >= min_gap_pct:
            if bias in ("BEARISH", "NEUTRAL"):
                fill_amount = max(0, highs[i+1] - last_close)
                fill_pct    = min(100, fill_amount / gap_bear * 100) if gap_bear > 0 else 0
                filled      = last_close > lows[i-1]
                fvgs.append(FVG(
                    high  = lows[i-1],
                    low   = highs[i+1],
                    mid   = (lows[i-1] + highs[i+1]) / 2,
                    direction = "BEAR",
                    index = i,
                    filled = filled,
                    displacement_verified = (i in disp_indices),
                    fill_pct = fill_pct,
                ))

    # فقط FVGs غير مُملوءة بالكامل
    valid = [f for f in fvgs if not f.filled and f.fill_pct < 80]
    return sorted(valid, key=lambda x: x.index, reverse=True)[:6]


# ══════════════════════════════════════════════════════════════════════
#  5. LIQUIDITY DETECTION  —  مستويات السيولة
# ══════════════════════════════════════════════════════════════════════

def detect_liquidity(df: pd.DataFrame,
                     tolerance_pct: float = 0.0012) -> list[LiquidityLevel]:
    """
    BSL (Buy-Side Liquidity): قمم متساوية فوق السعر — stops المتداولين البائعين
    SSL (Sell-Side Liquidity): قيعان متساوية تحت السعر — stops المتداولين الشارين

    ICT: السعر دائماً يذهب لاصطياد السيولة قبل الانعكاس.
    """
    highs     = df["high"].values
    lows      = df["low"].values
    closes    = df["close"].values
    n         = len(df)
    levels    = []
    seen_bsl  = set()
    seen_ssl  = set()

    for i in range(5, n - 1):
        # BSL: قمة تساوي قمة سابقة
        window_h = highs[max(0, i-30):i]
        for j, h in enumerate(window_h):
            if abs(highs[i] - h) / h < tolerance_pct and highs[i] not in seen_bsl:
                seen_bsl.add(round(highs[i], 1))
                levels.append(LiquidityLevel(
                    price = highs[i],
                    kind  = "BSL",
                    index = i,
                ))
                break

        # SSL: قاع يساوي قاعاً سابقاً
        window_l = lows[max(0, i-30):i]
        for j, l in enumerate(window_l):
            if abs(lows[i] - l) / l < tolerance_pct and lows[i] not in seen_ssl:
                seen_ssl.add(round(lows[i], 1))
                levels.append(LiquidityLevel(
                    price = lows[i],
                    kind  = "SSL",
                    index = i,
                ))
                break

    # اكتشاف الـ sweeps: هل اصطاد السعر السيولة؟
    last_h   = highs[-1]
    last_l   = lows[-1]
    last_cls = closes[-1]
    for lv in levels:
        if lv.kind == "BSL" and last_h >= lv.price and last_cls < lv.price:
            lv.swept = True
            lv.sweep_index = n - 1
        if lv.kind == "SSL" and last_l <= lv.price and last_cls > lv.price:
            lv.swept = True
            lv.sweep_index = n - 1

    # أبقِ فقط المستويات غير المُصطادة
    return [lv for lv in levels if not lv.swept]


# ══════════════════════════════════════════════════════════════════════
#  6. OTE ZONE  —  Optimal Trade Entry (فيبوناتشي ICT)
# ══════════════════════════════════════════════════════════════════════

def detect_ote_zone(swings: list[SwingPoint], bias: str) -> Optional[OTEZone]:
    """
    OTE = Optimal Trade Entry
    نطاق 61.8% – 78.6% من آخر swing رئيسي.

    للصاعد: نحسب من swing_low إلى swing_high → ندخل عند retracement 61.8%-78.6%
    للهابط: نحسب من swing_high إلى swing_low → ندخل عند retracement 61.8%-78.6%
    """
    highs = [s for s in swings if s.kind in ("HH", "LH", "swing_high")]
    lows  = [s for s in swings if s.kind in ("HL", "LL", "swing_low")]

    if len(highs) < 1 or len(lows) < 1:
        return None

    if bias == "BULLISH":
        # أحدث swing_low كقاع الـ swing، أحدث swing_high كقمة
        sl = min(lows, key=lambda s: s.price)
        sh = max(highs, key=lambda s: s.price)
        if sh.index <= sl.index:
            return None
        rng   = sh.price - sl.price
        if rng <= 0:
            return None
        ote_h = sh.price - rng * 0.618    # 61.8% retracement
        ote_l = sh.price - rng * 0.786    # 78.6% retracement
        fib705= sh.price - rng * 0.705    # 70.5% = أفضل دخول
        return OTEZone(high=ote_h, low=ote_l, fib_705=fib705,
                       direction="BULL",
                       swing_high=sh.price, swing_low=sl.price)

    elif bias == "BEARISH":
        sh = max(highs, key=lambda s: s.price)
        sl = min(lows,  key=lambda s: s.price)
        if sl.index <= sh.index:
            return None
        rng   = sh.price - sl.price
        if rng <= 0:
            return None
        ote_l = sl.price + rng * 0.618
        ote_h = sl.price + rng * 0.786
        fib705= sl.price + rng * 0.705
        return OTEZone(high=ote_h, low=ote_l, fib_705=fib705,
                       direction="BEAR",
                       swing_high=sh.price, swing_low=sl.price)

    return None


# ══════════════════════════════════════════════════════════════════════
#  7. SESSION LEVELS  —  مستويات الجلسات
# ══════════════════════════════════════════════════════════════════════

def detect_session_levels(df: pd.DataFrame) -> list[SessionLevel]:
    """
    استخرج High/Low لجلسات آسيا ولندن ونيويورك.
    ICT: هذه المستويات هي أهم مناطق السيولة اليومية.

    توقيت UTC:
      Asia:   00:00 – 03:00
      London: 07:00 – 10:00
      NY:     13:30 – 16:00
    """
    from datetime import time as dtime
    levels = []

    if df.empty or not hasattr(df.index, "time"):
        return levels

    try:
        df_copy = df.copy()
        if df_copy.index.tzinfo is None:
            df_copy.index = df_copy.index.tz_localize("UTC")

        session_defs = {
            "ASIA":   (dtime(0, 0),  dtime(3, 0)),
            "LON":    (dtime(7, 0),  dtime(10, 0)),
            "NY":     (dtime(13, 30),dtime(16, 0)),
        }

        for name, (s, e) in session_defs.items():
            mask = df_copy.index.map(
                lambda t: s <= t.time() <= e
            )
            session_df = df_copy[mask]
            if session_df.empty:
                continue
            high = float(session_df["high"].max())
            low  = float(session_df["low"].min())
            last_cls = float(df_copy["close"].iloc[-1])
            levels.append(SessionLevel(
                price = high,
                kind  = f"{name}_HIGH",
                swept = last_cls > high,
            ))
            levels.append(SessionLevel(
                price = low,
                kind  = f"{name}_LOW",
                swept = last_cls < low,
            ))
    except Exception:
        pass

    return [lv for lv in levels if not lv.swept]


# ══════════════════════════════════════════════════════════════════════
#  8. MARKET MAKER MODEL  —  AMD
# ══════════════════════════════════════════════════════════════════════

def detect_market_maker_model(
    df:          pd.DataFrame,
    swings:      list[SwingPoint],
    liquidity:   list[LiquidityLevel],
    bias:        str,
    current_price: float,
) -> MarketMakerModel:
    """
    Market Maker Model = AMD:
    A - Accumulation: تراكم (الآسيوية غالباً)
    M - Manipulation: تلاعب — يأخذ السيولة بالاتجاه الخاطئ
    D - Distribution: توزيع — التحرك الحقيقي

    نكتشف:
    1. هل تم اصطياد سيولة مهمة (liquidity sweep)؟
    2. هل تبعه Displacement في الاتجاه الصحيح؟
    3. ما هي المرحلة الحالية؟
    """
    displacements = detect_displacement_candles(df, body_ratio=2.0)
    swings_c      = classify_swings(swings)
    highs = [s for s in swings_c if s.kind in ("HH", "LH", "swing_high")]
    lows  = [s for s in swings_c if s.kind in ("HL", "LL", "swing_low")]

    # فحص Liquidity Sweep قريب (آخر 30 شمعة)
    n = len(df)
    recent_sweep_bull = any(
        lv.swept and lv.kind == "SSL"
        for lv in liquidity
    )
    recent_sweep_bear = any(
        lv.swept and lv.kind == "BSL"
        for lv in liquidity
    )

    # فحص Displacement بعد sweep
    last_disps = [d for d in displacements if d.index > n - 30]
    bull_disp  = any(d.direction == "BULL" and d.creates_fvg for d in last_disps)
    bear_disp  = any(d.direction == "BEAR" and d.creates_fvg for d in last_disps)

    # تقييم المرحلة
    if bias == "BULLISH":
        liquidity_swept  = recent_sweep_bull
        displacement_ok  = bull_disp
        manip_dir        = "DOWN"   # التلاعب كان بالهبوط لاصطياد SSL
        dist_dir         = "UP"
    elif bias == "BEARISH":
        liquidity_swept  = recent_sweep_bear
        displacement_ok  = bear_disp
        manip_dir        = "UP"
        dist_dir         = "DOWN"
    else:
        return MarketMakerModel("UNKNOWN", "", "", False, False, 0)

    confidence = 0
    if liquidity_swept:
        confidence += 4
    if displacement_ok:
        confidence += 4
    if bias != "NEUTRAL":
        confidence += 2

    if confidence >= 7:
        phase = "DISTRIBUTION"
    elif liquidity_swept:
        phase = "MANIPULATION"
    else:
        phase = "ACCUMULATION"

    return MarketMakerModel(
        phase              = phase,
        manipulation_dir   = manip_dir,
        distribution_dir   = dist_dir,
        liquidity_swept    = liquidity_swept,
        displacement_found = displacement_ok,
        confidence         = confidence,
    )


# ══════════════════════════════════════════════════════════════════════
#  9. PREMIUM / DISCOUNT ARRAYS
# ══════════════════════════════════════════════════════════════════════

def calc_pd_arrays(df: pd.DataFrame, lookback: int = 100) -> tuple[float, float, float]:
    """
    Premium/Discount/Equilibrium من آخر swing رئيسي.
    ICT: الشراء في Discount (< 50%)، البيع في Premium (> 50%).
    """
    sub  = df.iloc[-lookback:]
    high = float(sub["high"].max())
    low  = float(sub["low"].min())
    eq   = (high + low) / 2
    # ICT levels: 25% = Discount Deep, 50% = EQ, 75% = Premium
    premium  = low + (high - low) * 0.75   # 75% = Premium
    discount = low + (high - low) * 0.25   # 25% = Discount Deep
    return premium, eq, discount


# ══════════════════════════════════════════════════════════════════════
#  10. SETUP SCORE  —  تقييم الإعداد (0-15)
# ══════════════════════════════════════════════════════════════════════

def score_setup(analysis: "ICTAnalysis") -> int:
    score = 0
    price = analysis.current_price

    # ── هيكل السوق واضح (+2 BOS / +1 CHoCH) ──
    if analysis.bias != "NEUTRAL":
        score += 2
    if "BOS" in analysis.structure:
        score += 2
    elif "CHOCH" in analysis.structure:
        score += 1

    # ── OB مُتحقَّق من Displacement بالقرب من السعر (+3) ──
    for ob in analysis.order_blocks[:3]:
        buf = ob.high * 0.005   # 0.5%
        in_ob = (ob.low - buf) <= price <= (ob.high + buf)
        if in_ob:
            score += 3 if ob.displacement_verified else 2
            break

    # ── FVG مُتحقَّق من Displacement بالقرب (+2) ──
    for fvg in analysis.fvgs[:3]:
        buf = fvg.high * 0.005
        in_fvg = (fvg.low - buf) <= price <= (fvg.high + buf)
        if in_fvg:
            score += 2 if fvg.displacement_verified else 1
            break

    # ── السعر في OTE (Fibonacci 61.8-78.6%) (+2) ──
    ote = analysis.ote_zone
    if ote:
        if ote.direction == "BULL" and ote.low <= price <= ote.high:
            score += 2
        elif ote.direction == "BEAR" and ote.low <= price <= ote.high:
            score += 2

    # ── Market Maker Model Phase (+2) ──
    mm = analysis.mm_model
    if mm and mm.confidence >= 6:
        score += 2
    elif mm and mm.confidence >= 4:
        score += 1

    # ── السعر في Discount (BULL) أو Premium (BEAR) (+1) ──
    if analysis.bias == "BULLISH" and analysis.in_discount:
        score += 1
    if analysis.bias == "BEARISH" and analysis.in_premium:
        score += 1

    # ── Extended agents (populated externally) ──
    po3 = analysis.po3
    if po3 and hasattr(po3, "score_boost") and po3.score_boost > 0:
        if hasattr(po3, "distribution_bias") and po3.distribution_bias == analysis.bias:
            score += po3.score_boost

    breaker = analysis.breaker
    if breaker and hasattr(breaker, "score_boost") and breaker.score_boost > 0:
        bb = getattr(breaker, "best_breaker", None)
        if bb:
            aligned = ((analysis.bias == "BULLISH" and bb.direction == "BULL") or
                       (analysis.bias == "BEARISH" and bb.direction == "BEAR"))
            if aligned:
                score += breaker.score_boost

    sb = analysis.silver_bullet
    if sb and hasattr(sb, "active") and sb.active:
        sb_aligned = ((getattr(sb, "direction", "") == "LONG"  and analysis.bias == "BULLISH") or
                      (getattr(sb, "direction", "") == "SHORT" and analysis.bias == "BEARISH") or
                      not getattr(sb, "has_setup", True))
        if sb_aligned:
            score += getattr(sb, "score_boost", 0)

    disp = analysis.displacement
    if disp and hasattr(disp, "detected") and disp.detected:
        dir_match = ((getattr(disp, "direction", "") == "UP"   and analysis.bias == "BULLISH") or
                     (getattr(disp, "direction", "") == "DOWN" and analysis.bias == "BEARISH"))
        if dir_match:
            score += getattr(disp, "score_boost", 0)

    div = analysis.divergence
    if div and hasattr(div, "score_boost") and div.score_boost > 0:
        score += div.score_boost

    return min(score, 15)


# ══════════════════════════════════════════════════════════════════════
#  11. MAIN ANALYSIS PIPELINE
# ══════════════════════════════════════════════════════════════════════

def analyze(symbol: str, market: str,
            df_htf: pd.DataFrame, df_ltf: pd.DataFrame) -> Optional[ICTAnalysis]:
    """
    خط التحليل الكامل:
    1. هيكل السوق على HTF (4h) → bias
    2. OBs و FVGs على LTF (15m) مع Displacement verification
    3. OTE zone (Fibonacci)
    4. Liquidity levels
    5. Session levels
    6. Market Maker Model (AMD)
    7. Premium/Discount
    """
    if df_htf.empty or df_ltf.empty:
        log_agent("ICTAgent", symbol, "Insufficient data")
        return None

    # ── 1. Swing detection & structure on HTF ──────────────────────
    swings_htf  = detect_swings(df_htf, left=5, right=5)
    swings_htf  = classify_swings(swings_htf)
    structure, bias = classify_structure(swings_htf)

    # ── 2. Premium/Discount/EQ ─────────────────────────────────────
    premium, eq, discount = calc_pd_arrays(df_htf)

    # ── 3. Current price (from LTF last close) ─────────────────────
    current_price = float(df_ltf["close"].iloc[-1])
    in_premium    = current_price >= premium
    in_discount   = current_price <= discount

    # ── 4. OBs & FVGs on LTF ──────────────────────────────────────
    obs  = detect_order_blocks(df_ltf, bias, lookback=100)
    fvgs = detect_fvgs(df_ltf, bias, lookback=200)

    # ── 5. Liquidity on LTF ───────────────────────────────────────
    liquidity = detect_liquidity(df_ltf)

    # ── 6. OTE Zone ────────────────────────────────────────────────
    swings_ltf = detect_swings(df_ltf, left=3, right=3)
    swings_ltf = classify_swings(swings_ltf)
    ote_zone   = detect_ote_zone(swings_ltf, bias)

    # ── 7. Session levels ──────────────────────────────────────────
    session_lvls = detect_session_levels(df_ltf)

    # ── 8. Market Maker Model ──────────────────────────────────────
    mm_model = detect_market_maker_model(
        df_ltf, swings_ltf, liquidity, bias, current_price
    )

    analysis = ICTAnalysis(
        symbol         = symbol,
        market         = market,
        bias           = bias,
        structure      = structure,
        order_blocks   = obs,
        fvgs           = fvgs,
        liquidity      = liquidity,
        ote_zone       = ote_zone,
        session_levels = session_lvls,
        mm_model       = mm_model,
        premium_zone   = premium,
        discount_zone  = discount,
        equilibrium    = eq,
        current_price  = current_price,
        in_premium     = in_premium,
        in_discount    = in_discount,
    )

    analysis.setup_score = score_setup(analysis)

    log_agent("ICTAgent", symbol,
              f"Bias={bias}({structure}) OBs={len(obs)}(d={sum(1 for o in obs if o.displacement_verified)}) "
              f"FVGs={len(fvgs)}(d={sum(1 for f in fvgs if f.displacement_verified)}) "
              f"OTE={'YES' if ote_zone else 'NO'} AMD={mm_model.phase}({mm_model.confidence}/10) "
              f"Score={analysis.setup_score}/15")

    return analysis


# ══════════════════════════════════════════════════════════════════════
#  12. BEST ENTRY ZONE
# ══════════════════════════════════════════════════════════════════════

def get_best_entry_zone(analysis: "ICTAnalysis") -> Optional[dict]:
    """
    أفضل نقطة دخول حسب منهجية ICT:

    الأولوية:
    1. OB + FVG مع Displacement (confluence + displacement)
    2. OB + FVG بدون Displacement (confluence فقط)
    3. OB مُتحقَّق مع FVG قريبة (proximity)
    4. رفض إذا لم تكتمل الشروط

    شروط إضافية:
    - السعر يجب أن يكون داخل المنطقة (لا فوق/تحتها)
    - يُفضَّل أن يكون في نطاق OTE (61.8-78.6%)
    - يُفضَّل بعد Liquidity Sweep
    """
    if analysis.setup_score < 6:
        return None

    price = analysis.current_price
    ote   = analysis.ote_zone
    mm    = analysis.mm_model

    best_zone = None
    best_score = -1

    for ob in analysis.order_blocks[:5]:
        for fvg in analysis.fvgs[:5]:
            if ob.direction != fvg.direction:
                continue

            # احسب المنطقة المشتركة أو المتقاربة
            overlap_h = min(ob.high, fvg.high)
            overlap_l = max(ob.low,  fvg.low)
            have_overlap = overlap_l < overlap_h

            proximity = abs(ob.mid - fvg.mid) / max(ob.mid, fvg.mid)
            have_proximity = proximity < 0.015   # 1.5%

            if not (have_overlap or have_proximity):
                continue

            if have_overlap:
                zone_h = overlap_h
                zone_l = overlap_l
            else:
                zone_h = max(ob.high, fvg.high)
                zone_l = min(ob.low,  fvg.low)

            # تحقق من موقع السعر
            buf = zone_l * 0.003   # 0.3% tolerance

            if ob.direction == "BULL":
                in_zone = (price >= zone_l - buf) and (price <= zone_h)
            else:
                in_zone = (price <= zone_h + buf) and (price >= zone_l)

            if not in_zone:
                continue

            # احسب نقاط الجودة
            quality = 0
            if ob.displacement_verified:   quality += 3
            if fvg.displacement_verified:  quality += 2
            if have_overlap:               quality += 2
            if ote and (ote.low <= price <= ote.high):  quality += 2
            if mm and mm.liquidity_swept:  quality += 2
            if not ob.mitigated_50:        quality += 1

            if quality > best_score:
                best_score = quality
                best_zone  = {
                    "type":      "OB+FVG",
                    "high":      zone_h,
                    "low":       zone_l,
                    "mid":       (zone_h + zone_l) / 2,
                    "direction": ob.direction,
                    "quality":   quality,
                    "displacement_verified": ob.displacement_verified or fvg.displacement_verified,
                    "ote_aligned": bool(ote and ote.low <= price <= ote.high),
                    "liquidity_swept": bool(mm and mm.liquidity_swept),
                }

    return best_zone
