"""
Executor Agent — ينفذ ويغلق الصفقات.

ثلاثة أوضاع (BROKER في .env):
  paper    → ورقي (بدون بروكر)
  ctrader  → حقيقي عبر cTrader Open API + فحوصات FUNDEDHIVE
  mt5      → MetaTrader 5 (Demo أو Live)

في وضع Live (ctrader/mt5):
  - فحوصات PropFirm Guard تسبق كل دخول
  - الـ DB يُسجَّل مع broker_pos_id للمزامنة
"""
from __future__ import annotations

import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from database import models
from agents.data_agent import get_current_price

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  فتح صفقة
# ══════════════════════════════════════════════════════════════════════

def open_trade(signal: dict, reason: str, grade: str = "C") -> int:
    """
    افتح صفقة حسب BROKER المختار.
    إرجاع: trade_id في قاعدة البيانات المحلية.
    """
    broker = config.BROKER
    if broker == "ctrader":
        return _open_live(signal, reason, grade)
    if broker == "mt5":
        return _open_mt5(signal, reason, grade)
    return _open_paper(signal, reason, grade)


def _open_paper(signal: dict, reason: str, grade: str) -> int:
    """فتح صفقة ورقية (بدون بروكر)."""
    trade_id = models.open_trade(
        symbol     = signal["symbol"],
        market     = signal["market"],
        direction  = signal["direction"],
        entry      = signal["entry"],
        sl         = signal["sl"],
        tp         = signal["tp"],
        lot        = signal["lot_size"],
        risk_usd   = signal["risk_usd"],
        kill_zone  = signal["kill_zone"],
        setup_type = signal["setup_type"],
        bias       = signal["bias"],
        reason     = reason,
        grade      = grade,
    )
    models.log_agent(
        "Executor", signal["symbol"],
        f"[PAPER] OPENED #{trade_id} {signal['direction']} "
        f"@ {signal['entry']} | SL={signal['sl']} TP={signal['tp']}"
    )
    return trade_id


def _open_live(signal: dict, reason: str, grade: str) -> int:
    """فتح صفقة حقيقية عبر cTrader + فحوصات FUNDEDHIVE."""
    from agents.ctrader_agent import get_ctrader_agent
    from agents.propfirm_guard import run_all_checks, get_or_init_day_start_balance

    # ── 1. فحوصات Prop Firm ──────────────────────────────────────────
    account     = models.get_account()
    balance     = float(account["balance"])
    day_balance = get_or_init_day_start_balance(balance)

    allowed, reason_guard = run_all_checks(
        current_balance   = balance,
        day_start_balance = day_balance,
        lot_size          = signal.get("lot_size", 0),
    )
    if not allowed:
        log.warning(f"Executor LIVE: PropFirm block — {reason_guard}")
        models.log_agent("Executor", signal["symbol"],
                         f"LIVE BLOCKED (PropFirm): {reason_guard}")
        raise RuntimeError(f"PropFirm guard blocked: {reason_guard}")

    # ── 2. إرسال الأمر لـ cTrader ────────────────────────────────────
    agent = get_ctrader_agent()
    if not agent:
        log.error("Executor LIVE: cTrader agent غير متاح — تحقق من الاعتمادات")
        raise RuntimeError("cTrader agent unavailable")

    if not agent.is_ready():
        log.warning("Executor LIVE: cTrader لم يكتمل اتصاله بعد — انتظر...")
        import time as _t
        _t.sleep(5)
        if not agent.is_ready():
            raise RuntimeError("cTrader not ready after 5s wait")

    position_id = agent.open_position(
        symbol    = signal["symbol"],
        direction = signal["direction"],
        entry     = signal["entry"],
        sl        = signal["sl"],
        tp        = signal["tp"],
        risk_usd  = signal["risk_usd"],
    )
    if position_id is None:
        raise RuntimeError("cTrader open_position أعاد None — تحقق من السجلات")

    # ── 3. تسجيل في قاعدة البيانات ────────────────────────────────────
    trade_id = models.open_trade(
        symbol      = signal["symbol"],
        market      = signal["market"],
        direction   = signal["direction"],
        entry       = signal["entry"],
        sl          = signal["sl"],
        tp          = signal["tp"],
        lot         = signal["lot_size"],
        risk_usd    = signal["risk_usd"],
        kill_zone   = signal["kill_zone"],
        setup_type  = signal["setup_type"],
        bias        = signal["bias"],
        reason      = reason,
        grade       = grade,
        ct_pos_id   = position_id,
    )
    models.log_agent(
        "Executor", signal["symbol"],
        f"[LIVE] OPENED #{trade_id} ct_pos={position_id} {signal['direction']} "
        f"@ {signal['entry']} | SL={signal['sl']} TP={signal['tp']}"
    )
    log.info(
        f"[LIVE] Trade #{trade_id} (cTrader pos #{position_id}) "
        f"{signal['direction']} {signal['symbol']} opened"
    )
    return trade_id


# ══════════════════════════════════════════════════════════════════════
#  فحص وإغلاق الصفقات
# ══════════════════════════════════════════════════════════════════════

def check_and_close_trades():
    """
    يُستدعى كل دورة.
    - paper:   يفحص السعر محلياً ويُغلق عند TP/SL.
    - ctrader: يزامن مع cTrader ثم يُحدّث DB.
    - mt5:     يزامن مع MT5 ثم يُحدّث DB.
    """
    broker = config.BROKER
    if broker == "ctrader":
        _sync_live_trades()
    elif broker == "mt5":
        _sync_mt5_trades()
    else:
        _check_paper_trades()


# ──────────────────────────────────────────
#  Paper trade checking (كالسابق)
# ──────────────────────────────────────────

def _check_paper_trades():
    open_trades = models.get_open_trades()
    if not open_trades:
        return

    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)

    for trade in list(open_trades):
        # إغلاق الصفقات العالقة أكثر من 48 ساعة
        try:
            opened_at = datetime.fromisoformat(trade.get("opened_at") or "")
            if (now_utc - opened_at) > timedelta(hours=48):
                models.log_agent("Executor", trade["symbol"],
                                 f"#{trade['id']} stuck OPEN >48h — force-closing")
                _close_paper(trade["id"], "LOSS", -trade["risk_usd"], -1.0)
                open_trades = [t for t in open_trades if t["id"] != trade["id"]]
        except Exception:
            pass

    for trade in open_trades:
        symbol    = trade["symbol"]
        market    = trade["market"]
        direction = trade["direction"]
        entry     = trade["entry_price"]
        sl        = trade["sl_price"]
        tp        = trade["tp_price"]
        lot       = trade["lot_size"]
        risk_usd  = trade["risk_usd"]
        be_moved  = bool(trade.get("be_moved", 0))
        trade_id  = trade["id"]

        current = get_current_price(symbol, market)
        if current == 0:
            continue

        sl_distance = abs(entry - sl)

        if direction == "LONG":
            hit_sl = current <= sl
            hit_tp = current >= tp
            at_1r  = (not be_moved) and (current >= entry + sl_distance)
        else:
            hit_sl = current >= sl
            hit_tp = current <= tp
            at_1r  = (not be_moved) and (current <= entry - sl_distance)

        if hit_tp:
            tp_dist = abs(tp - entry)
            pnl = tp_dist * lot
            rr  = pnl / risk_usd if risk_usd > 0 else 0
            _close_paper(trade_id, "WIN", pnl, rr)

        elif hit_sl:
            if be_moved:
                _close_paper(trade_id, "BE", 0.0, 0.0)
            else:
                _close_paper(trade_id, "LOSS", -risk_usd, -1.0)

        elif at_1r:
            models.move_sl_to_be(trade_id, entry)
            models.log_agent("Executor", symbol,
                             f"#{trade_id} reached 1R — SL moved to BE @ {entry:.5f}")


def _close_paper(trade_id: int, status: str, pnl: float, rr: float):
    pnl = round(pnl, 4)
    rr  = round(rr,  2)
    models.close_trade(trade_id, status, pnl, rr)
    account        = models.get_account()
    new_balance    = account["balance"]   + pnl
    new_total_pnl  = account["total_pnl"] + pnl
    win_c  = account["win_count"]  + (1 if status == "WIN"  else 0)
    loss_c = account["loss_count"] + (1 if status == "LOSS" else 0)
    models.update_account(
        balance   = round(new_balance, 4),
        equity    = round(new_balance, 4),
        total_pnl = round(new_total_pnl, 4),
        win_count = win_c,
        loss_count= loss_c,
    )
    models.log_agent("Executor", "SYSTEM",
                     f"[PAPER] CLOSED #{trade_id} → {status} | PnL=${pnl:+.2f}")


# ──────────────────────────────────────────
#  Live trade sync with cTrader
# ──────────────────────────────────────────

def _sync_live_trades():
    """
    مزامنة حالة الصفقات مع cTrader:
    1. اجلب الصفقات المفتوحة من cTrader.
    2. للصفقات المفتوحة في DB ولكن مُغلقة في cTrader → سجّل النتيجة.
    3. تحقق من BE (1R) وعدّل SL إذا لزم.
    """
    from agents.ctrader_agent import get_ctrader_agent
    from agents.propfirm_guard import run_all_checks, get_or_init_day_start_balance

    agent = get_ctrader_agent()
    if not agent or not agent.is_ready():
        # إذا cTrader غير متاح — استخدم الفحص المحلي كاحتياط
        log.warning("Executor LIVE: cTrader غير متاح — استخدام الفحص المحلي")
        _check_paper_trades()
        return

    # ── جلب الصفقات المفتوحة من DB ────────────────────────────────
    db_open = models.get_open_trades()
    if not db_open:
        return

    # ── جلب الصفقات الحقيقية من cTrader ───────────────────────────
    try:
        ct_positions = agent.get_open_positions()
        ct_ids = {p["position_id"] for p in ct_positions}
        ct_map  = {p["position_id"]: p for p in ct_positions}
    except Exception as exc:
        log.error(f"Executor LIVE: فشل جلب الصفقات من cTrader: {exc}")
        return

    for trade in db_open:
        trade_id  = trade["id"]
        ct_pos_id = trade.get("ct_pos_id")
        direction = trade["direction"]
        entry     = trade["entry_price"]
        sl        = trade["sl_price"]
        tp        = trade["tp_price"]
        lot       = trade["lot_size"]
        risk_usd  = trade["risk_usd"]
        be_moved  = bool(trade.get("be_moved", 0))

        # ── الصفقة مُغلقة في cTrader (TP/SL/يدوي) ──────────────────
        if ct_pos_id and ct_pos_id not in ct_ids:
            # الصفقة أُغلقت على cTrader — احسب PnL تقريبياً من آخر سعر
            current = get_current_price(trade["symbol"], trade["market"])
            if current == 0:
                continue

            if direction == "LONG":
                pnl = (current - entry) * lot
            else:
                pnl = (entry - current) * lot

            if pnl > 0:
                rr     = pnl / risk_usd if risk_usd > 0 else 0
                status = "WIN"
            elif abs(pnl) < 0.5:
                rr     = 0.0
                status = "BE"
            else:
                rr     = -1.0
                status = "LOSS"
                pnl    = -risk_usd   # استخدم المخاطرة المحددة كخسارة

            _close_live(trade_id, status, round(pnl, 4), round(rr, 2))
            continue

        # ── الصفقة لا تزال مفتوحة — تحقق من BE ──────────────────────
        if ct_pos_id and ct_pos_id in ct_map:
            ct_pos = ct_map[ct_pos_id]
            current = ct_pos.get("entry", 0)   # السعر الحالي غير متاح مباشرة هنا
            current = get_current_price(trade["symbol"], trade["market"])
            if current == 0:
                continue

            sl_distance = abs(entry - sl)

            if direction == "LONG":
                at_1r = (not be_moved) and sl_distance > 0 and (current >= entry + sl_distance)
            else:
                at_1r = (not be_moved) and sl_distance > 0 and (current <= entry - sl_distance)

            if at_1r:
                # نقل SL لـ BE على cTrader
                moved = agent.move_to_breakeven(ct_pos_id, entry, tp)
                if moved:
                    models.move_sl_to_be(trade_id, entry)
                    log.info(
                        f"[LIVE] #{trade_id} ct_pos#{ct_pos_id} "
                        f"reached 1R — SL moved to BE @ {entry:.5f}"
                    )

    # ── فحص PropFirm بعد مزامنة الأرصدة ──────────────────────────
    try:
        account     = models.get_account()
        balance     = float(account["balance"])
        day_balance = get_or_init_day_start_balance(balance)
        allowed, reason_guard = run_all_checks(balance, day_balance, skip_lot_check=True)
        if not allowed:
            log.warning(f"[LIVE] PropFirm alert post-sync: {reason_guard}")
    except Exception as exc:
        log.error(f"PropFirm check error: {exc}")


def _close_live(trade_id: int, status: str, pnl: float, rr: float):
    """أغلق صفقة في DB وحدّث الرصيد (Live)."""
    pnl = round(pnl, 4)
    rr  = round(rr,  2)
    models.close_trade(trade_id, status, pnl, rr)
    account        = models.get_account()
    new_balance    = account["balance"]   + pnl
    new_total_pnl  = account["total_pnl"] + pnl
    win_c  = account["win_count"]  + (1 if status == "WIN"  else 0)
    loss_c = account["loss_count"] + (1 if status == "LOSS" else 0)
    models.update_account(
        balance    = round(new_balance, 4),
        equity     = round(new_balance, 4),
        total_pnl  = round(new_total_pnl, 4),
        win_count  = win_c,
        loss_count = loss_c,
    )
    models.log_agent("Executor", "SYSTEM",
                     f"[LIVE] CLOSED #{trade_id} → {status} | PnL=${pnl:+.2f}")
    log.info(f"[LIVE] Trade #{trade_id} closed → {status} PnL={pnl:+.2f}$")


# ══════════════════════════════════════════════════════════════════════
#  MT5 execution
# ══════════════════════════════════════════════════════════════════════

def _open_mt5(signal: dict, reason: str, grade: str) -> int:
    """فتح صفقة عبر MT5 + فحوصات PropFirm."""
    from agents.mt5_agent import get_mt5_agent
    from agents.propfirm_guard import run_all_checks, get_or_init_day_start_balance

    # ── 1. فحوصات PropFirm ──────────────────────────────────────────
    account     = models.get_account()
    balance     = float(account["balance"])
    day_balance = get_or_init_day_start_balance(balance)

    allowed, reason_guard = run_all_checks(
        current_balance   = balance,
        day_start_balance = day_balance,
        lot_size          = signal.get("lot_size", 0),
    )
    if not allowed:
        log.warning(f"Executor MT5: PropFirm block — {reason_guard}")
        models.log_agent("Executor", signal["symbol"],
                         f"MT5 BLOCKED (PropFirm): {reason_guard}")
        raise RuntimeError(f"PropFirm guard blocked: {reason_guard}")

    # ── 2. إرسال الأمر لـ MT5 ────────────────────────────────────────
    agent = get_mt5_agent()
    if not agent:
        raise RuntimeError("MT5 agent غير متاح — تحقق من MT5_LOGIN/PASSWORD/SERVER")

    if not agent.is_ready():
        import time as _t
        _t.sleep(3)
        if not agent.is_ready():
            raise RuntimeError("MT5 not ready after 3s wait")

    ticket = agent.open_position(
        symbol    = signal["symbol"],
        direction = signal["direction"],
        entry     = signal["entry"],
        sl        = signal["sl"],
        tp        = signal["tp"],
        risk_usd  = signal["risk_usd"],
    )
    if ticket is None:
        raise RuntimeError("MT5 open_position أعاد None — تحقق من السجلات")

    # ── 3. تسجيل في قاعدة البيانات ────────────────────────────────────
    trade_id = models.open_trade(
        symbol      = signal["symbol"],
        market      = signal["market"],
        direction   = signal["direction"],
        entry       = signal["entry"],
        sl          = signal["sl"],
        tp          = signal["tp"],
        lot         = signal["lot_size"],
        risk_usd    = signal["risk_usd"],
        kill_zone   = signal["kill_zone"],
        setup_type  = signal["setup_type"],
        bias        = signal["bias"],
        reason      = reason,
        grade       = grade,
        ct_pos_id   = ticket,     # نستخدم ct_pos_id لتخزين MT5 ticket
    )
    models.log_agent(
        "Executor", signal["symbol"],
        f"[MT5] OPENED #{trade_id} ticket={ticket} {signal['direction']} "
        f"@ {signal['entry']} | SL={signal['sl']} TP={signal['tp']}"
    )
    log.info(
        f"[MT5] Trade #{trade_id} (ticket #{ticket}) "
        f"{signal['direction']} {signal['symbol']} opened"
    )
    return trade_id


def _sync_mt5_trades():
    """
    مزامنة حالة الصفقات مع MT5:
    1. اجلب الصفقات المفتوحة من MT5.
    2. للصفقات المفتوحة في DB ولكن مُغلقة في MT5 → سجّل النتيجة.
    3. تحقق من BE (1R) وعدّل SL إذا لزم.
    """
    from agents.mt5_agent import get_mt5_agent
    from agents.propfirm_guard import run_all_checks, get_or_init_day_start_balance

    agent = get_mt5_agent()
    if not agent or not agent.is_ready():
        log.warning("Executor MT5: غير متاح — استخدام الفحص المحلي")
        _check_paper_trades()
        return

    db_open = models.get_open_trades()
    if not db_open:
        # مزامنة رصيد الحساب فقط
        try:
            info = agent.get_account_info()
            if info:
                acc = models.get_account()
                models.update_account(
                    balance    = info["balance"],
                    equity     = info["equity"],
                    total_pnl  = acc["total_pnl"],
                    win_count  = acc["win_count"],
                    loss_count = acc["loss_count"],
                )
        except Exception:
            pass
        return

    try:
        mt5_positions = agent.get_open_positions()
        mt5_tickets   = {p["ticket"] for p in mt5_positions}
    except Exception as exc:
        log.error(f"Executor MT5: فشل جلب الصفقات: {exc}")
        return

    for trade in db_open:
        trade_id  = trade["id"]
        ticket    = trade.get("ct_pos_id")    # نستخدم ct_pos_id كـ MT5 ticket
        direction = trade["direction"]
        entry     = trade["entry_price"]
        sl        = trade["sl_price"]
        tp        = trade["tp_price"]
        lot       = trade["lot_size"]
        risk_usd  = trade["risk_usd"]
        be_moved  = bool(trade.get("be_moved", 0))

        # ── الصفقة مُغلقة في MT5 ─────────────────────────────────────
        if ticket and ticket not in mt5_tickets:
            current = agent.get_current_price(trade["symbol"])
            if current == 0:
                current = get_current_price(trade["symbol"], trade["market"])
            if current == 0:
                continue

            pnl = (current - entry) * lot if direction == "LONG" else (entry - current) * lot

            if pnl > 0:
                rr     = pnl / risk_usd if risk_usd > 0 else 0
                status = "WIN"
            elif abs(pnl) < 0.5:
                rr = 0.0; status = "BE"
            else:
                rr = -1.0; status = "LOSS"; pnl = -risk_usd

            _close_live(trade_id, status, round(pnl, 4), round(rr, 2))
            continue

        # ── الصفقة لا تزال مفتوحة — تحقق من BE ──────────────────────
        if ticket and ticket in mt5_tickets:
            current = agent.get_current_price(trade["symbol"])
            if current == 0:
                continue

            sl_distance = abs(entry - sl)
            if direction == "LONG":
                at_1r = (not be_moved) and sl_distance > 0 and current >= entry + sl_distance
            else:
                at_1r = (not be_moved) and sl_distance > 0 and current <= entry - sl_distance

            if at_1r:
                moved = agent.move_to_breakeven(ticket, entry, tp)
                if moved:
                    models.move_sl_to_be(trade_id, entry)
                    log.info(f"[MT5] #{trade_id} ticket#{ticket} → SL moved to BE @ {entry:.5f}")

    # ── مزامنة رصيد الحساب ────────────────────────────────────────
    try:
        info = agent.get_account_info()
        if info:
            acc = models.get_account()
            models.update_account(
                balance    = info["balance"],
                equity     = info["equity"],
                total_pnl  = acc["total_pnl"],
                win_count  = acc["win_count"],
                loss_count = acc["loss_count"],
            )
    except Exception as exc:
        log.error(f"MT5 account sync error: {exc}")

    # ── فحص PropFirm ────────────────────────────────────────────────
    try:
        info = agent.get_account_info()
        if info:
            day_balance = get_or_init_day_start_balance(info["balance"])
            allowed, reason_guard = run_all_checks(
                info["balance"], day_balance, skip_lot_check=True)
            if not allowed:
                log.warning(f"[MT5] PropFirm alert: {reason_guard}")
    except Exception as exc:
        log.error(f"PropFirm check error: {exc}")


# ══════════════════════════════════════════════════════════════════════
#  إغلاق تلقائي قبل الأسبوع (PropFirm Weekend Rule)
# ══════════════════════════════════════════════════════════════════════

def close_all_for_weekend():
    """
    يُستدعى من scheduler عند اقتراب نهاية الأسبوع.
    يُغلق كل الصفقات المفتوحة على البروكر المختار.
    """
    if not config.PROPFIRM_CLOSE_ON_WEEKEND:
        return

    broker = config.BROKER

    if broker == "ctrader":
        from agents.ctrader_agent import get_ctrader_agent
        agent = get_ctrader_agent()
        if not agent or not agent.is_ready():
            log.warning("close_all_for_weekend: cTrader غير متاح")
            return
        open_trades = models.get_open_trades()
        for trade in open_trades:
            ct_pos_id = trade.get("ct_pos_id")
            if ct_pos_id:
                agent.close_position(ct_pos_id)
                log.info(f"Weekend close: صفقة #{trade['id']} ct_pos#{ct_pos_id} مُغلقة")

    elif broker == "mt5":
        from agents.mt5_agent import get_mt5_agent
        agent = get_mt5_agent()
        if not agent or not agent.is_ready():
            log.warning("close_all_for_weekend: MT5 غير متاح")
            return
        open_trades = models.get_open_trades()
        for trade in open_trades:
            ticket = trade.get("ct_pos_id")
            if ticket:
                agent.close_position(ticket)
                log.info(f"Weekend close: صفقة #{trade['id']} ticket#{ticket} مُغلقة")
