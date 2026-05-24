"""
Prop Firm Guard — قواعد FUNDEDHIVE الصارمة
يحمي الحساب من انتهاك قواعد الـ Prop Firm.

القواعد المنفَّذة:
  1. حد الخسارة اليومية (Daily Loss Limit)       — 5% افتراضي
  2. حد الخسارة الإجمالية (Max Drawdown)         — 10% افتراضي
  3. حد الهدف الربحي (يسجّل فقط — لا يوقف)
  4. حد حجم الصفقة (Max Lot per Trade)
  5. إغلاق الصفقات قبل نهاية الأسبوع (اختياري)
  6. نافذة حظر الأخبار (اختياري، معطّل افتراضياً)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Optional

log = logging.getLogger(__name__)

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


# ══════════════════════════════════════════════════════════════════════
#  نتيجة الفحص
# ══════════════════════════════════════════════════════════════════════

class GuardResult:
    def __init__(self, allowed: bool, reason: str, severity: str = "INFO"):
        self.allowed  = allowed
        self.reason   = reason
        self.severity = severity   # "INFO" | "WARNING" | "BLOCK"

    def __bool__(self):
        return self.allowed

    def __repr__(self):
        s = "OK" if self.allowed else "BLOCK"
        return f"GuardResult({s}: {self.reason})"


# ══════════════════════════════════════════════════════════════════════
#  فحوصات FUNDEDHIVE
# ══════════════════════════════════════════════════════════════════════

def check_daily_loss(current_balance: float, day_start_balance: float) -> GuardResult:
    """
    اليوم بدأ بـ day_start_balance.
    إذا انخفض الرصيد عن الحد المسموح → حظر.
    FUNDEDHIVE: 5% من رصيد بداية اليوم.
    """
    initial  = config.PROPFIRM_INITIAL_BALANCE
    limit    = config.PROPFIRM_MAX_DAILY_LOSS_PCT

    # FUNDEDHIVE: Daily loss = من رصيد بداية اليوم (static per day)
    max_loss_usd   = day_start_balance * limit
    current_loss   = day_start_balance - current_balance
    loss_pct       = current_loss / day_start_balance if day_start_balance > 0 else 0

    if current_loss >= max_loss_usd:
        return GuardResult(
            False,
            f"حد الخسارة اليومية: -{current_loss:.2f}$ "
            f"({loss_pct:.1%}) ≥ حد {limit:.0%} — الحساب متوقف اليوم",
            "BLOCK"
        )

    remaining = max_loss_usd - current_loss
    if loss_pct >= limit * 0.7:   # تحذير عند 70% من الحد
        return GuardResult(
            True,
            f"تحذير خسارة يومية: {loss_pct:.1%} (المتبقي: {remaining:.2f}$)",
            "WARNING"
        )

    return GuardResult(True, f"خسارة يومية: {loss_pct:.1%} | متبقٍ: {remaining:.2f}$")


def check_max_drawdown(current_balance: float) -> GuardResult:
    """
    FUNDEDHIVE: الـ drawdown يُقاس من الرصيد الابتدائي (static).
    Max 10%.
    """
    initial     = config.PROPFIRM_INITIAL_BALANCE
    limit       = config.PROPFIRM_MAX_DRAWDOWN_PCT
    drawdown    = (initial - current_balance) / initial if initial > 0 else 0
    max_dd_usd  = initial * limit

    if drawdown >= limit:
        return GuardResult(
            False,
            f"حد الـ Drawdown: -{drawdown:.1%} من الرصيد الابتدائي "
            f"({initial - current_balance:.2f}$) — الحساب مُلغى",
            "BLOCK"
        )

    if drawdown >= limit * 0.8:
        return GuardResult(
            True,
            f"تحذير Drawdown: {drawdown:.1%} — اقترب من الحد ({limit:.0%})",
            "WARNING"
        )

    return GuardResult(True, f"Drawdown: {drawdown:.1%} / {limit:.0%}")


def check_lot_size(lot_size: float) -> GuardResult:
    """تأكد أن حجم الصفقة لا يتجاوز الحد المسموح."""
    max_lot = config.PROPFIRM_MAX_LOT_PER_TRADE
    if lot_size > max_lot:
        return GuardResult(
            False,
            f"حجم الصفقة {lot_size:.2f} > الحد {max_lot:.2f} lot — رُفضت",
            "BLOCK"
        )
    return GuardResult(True, f"Lot size OK: {lot_size:.2f} / {max_lot:.2f}")


def check_weekend_close() -> GuardResult:
    """
    FUNDEDHIVE: يجب إغلاق الصفقات قبل نهاية الأسبوع (الجمعة 21:50 UTC تقريباً).
    إذا كان الوقت في نافذة الإغلاق → أعد GuardResult مع is_weekend_close=True.
    """
    if not config.PROPFIRM_CLOSE_ON_WEEKEND:
        return GuardResult(True, "Weekend close معطّل")

    now = datetime.now(timezone.utc)
    # الجمعة = weekday 4, السبت = 5, الأحد = 6
    if now.weekday() == 4 and now.time() >= dtime(21, 45):
        return GuardResult(False, "نافذة الإغلاق الأسبوعية (الجمعة 21:45+)", "BLOCK")
    if now.weekday() in (5, 6):
        return GuardResult(False, "السوق مغلق في عطلة نهاية الأسبوع", "BLOCK")

    # تحذير قبل 15 دقيقة من الجمعة 21:45
    if now.weekday() == 4 and now.time() >= dtime(21, 30):
        return GuardResult(True, "⚠️ تبقّى أقل من 15 دقيقة قبل إغلاق الأسبوع", "WARNING")

    return GuardResult(True, "OK")


def check_news_window() -> GuardResult:
    """
    حظر التداول قبل/بعد الأخبار الكبرى.
    يعتمد على PROPFIRM_NO_NEWS_WINDOW_MIN (دقائق).
    0 = معطّل.
    التطبيق الكامل يحتاج مصدر بيانات أخبار — هنا نُطبَّق الإطار فقط.
    """
    minutes = config.PROPFIRM_NO_NEWS_WINDOW_MIN
    if minutes <= 0:
        return GuardResult(True, "فلتر الأخبار معطّل")

    # TODO: ربط بمصدر أخبار حقيقي (Forex Factory API أو Investing.com)
    # حالياً: القاعدة تُسجَّل ولا تُطبَّق تلقائياً
    return GuardResult(True, f"فلتر الأخبار ({minutes} min) — بدون مصدر بيانات")


def check_profit_target(current_balance: float) -> GuardResult:
    """سجّل تقدّم الهدف الربحي (لا يوقف التداول)."""
    initial = config.PROPFIRM_INITIAL_BALANCE
    target  = config.PROPFIRM_PROFIT_TARGET_PCT
    profit  = (current_balance - initial) / initial if initial > 0 else 0

    if profit >= target:
        return GuardResult(
            True,
            f"🎯 تم تحقيق هدف الربح {profit:.1%} ≥ {target:.0%} — "
            f"يمكنك طلب السحب أو الترقية",
            "INFO"
        )
    remaining = (initial * (1 + target)) - current_balance
    return GuardResult(True, f"هدف الربح: {profit:.1%} / {target:.0%} | متبقٍ: {remaining:.2f}$")


# ══════════════════════════════════════════════════════════════════════
#  الفحص الشامل — استدعه قبل كل صفقة
# ══════════════════════════════════════════════════════════════════════

def run_all_checks(
    current_balance:   float,
    day_start_balance: float,
    lot_size:          float = 0.0,
    skip_lot_check:    bool  = False,
) -> tuple[bool, str]:
    """
    نفّذ كل فحوصات FUNDEDHIVE.
    إرجاع: (مسموح, سبب)
    """
    checks = [
        check_weekend_close(),
        check_max_drawdown(current_balance),
        check_daily_loss(current_balance, day_start_balance),
    ]
    if not skip_lot_check and lot_size > 0:
        checks.append(check_lot_size(lot_size))

    blocked = [c for c in checks if not c.allowed]
    if blocked:
        reasons = " | ".join(c.reason for c in blocked)
        log.warning(f"PropFirmGuard BLOCKED: {reasons}")
        return False, reasons

    warnings = [c for c in checks if c.severity == "WARNING"]
    for w in warnings:
        log.warning(f"PropFirmGuard WARNING: {w.reason}")

    # سجّل تقدّم الهدف
    target_check = check_profit_target(current_balance)
    if target_check.severity == "INFO" and "🎯" in target_check.reason:
        log.info(f"PropFirmGuard: {target_check.reason}")

    return True, "جميع فحوصات FUNDEDHIVE اجتازت"


# ══════════════════════════════════════════════════════════════════════
#  رصيد بداية اليوم — يُخزَّن في DB أو ملف مؤقت
# ══════════════════════════════════════════════════════════════════════

_day_start_file = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    ".day_start_balance"
)


def get_or_init_day_start_balance(current_balance: float) -> float:
    """
    إرجاع رصيد بداية اليوم.
    إذا بدأ يوم جديد → حدّث الملف.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if os.path.exists(_day_start_file):
            with open(_day_start_file) as f:
                parts = f.read().strip().split(",")
            if parts[0] == today:
                return float(parts[1])
    except Exception:
        pass

    # يوم جديد أو أول تشغيل
    with open(_day_start_file, "w") as f:
        f.write(f"{today},{current_balance:.4f}")
    log.info(f"PropFirmGuard: رصيد بداية اليوم = {current_balance:.2f}$")
    return current_balance
