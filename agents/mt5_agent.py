"""
MT5 Agent — تنفيذ الصفقات عبر MetaTrader 5 (حساب Demo أو Live)
يعمل على Windows فقط (MetaTrader5 package).

الوظائف الرئيسية:
  - connect()         → الاتصال بالمنصة وتسجيل الدخول
  - open_position()   → فتح صفقة بـ SL/TP
  - close_position()  → إغلاق صفقة بالـ ticket_id
  - modify_sl_tp()    → تعديل SL/TP
  - move_to_breakeven() → نقل SL إلى نقطة الدخول
  - get_account_info()  → معلومات الحساب
  - get_open_positions() → قائمة الصفقات المفتوحة
  - get_current_price()  → السعر الحالي من MT5 مباشرة
"""
from __future__ import annotations

import logging
import sys
import os
import threading
import time as _time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

log = logging.getLogger(__name__)

_mt5_lock = threading.Lock()
_mt5_instance: "MT5Agent | None" = None


# ══════════════════════════════════════════════════════════════════════
#  MT5 Agent Class
# ══════════════════════════════════════════════════════════════════════

class MT5Agent:
    """
    واجهة متزامنة لـ MetaTrader5.
    كل العمليات تتم على الـ thread الذي يستدعيها (MT5 thread-safe).
    """

    def __init__(self):
        self._ready     = False
        self._mt5       = None          # module reference
        self._login     = config.MT5_LOGIN
        self._password  = config.MT5_PASSWORD
        self._server    = config.MT5_SERVER
        self._symbol_map = config.MT5_SYMBOL_MAP

    # ─────────────────────────────────────────────────────────
    #  اتصال وإعداد
    # ─────────────────────────────────────────────────────────

    def connect(self, timeout: int = 30) -> bool:
        """
        يُشغّل MetaTrader5 ويُسجّل الدخول.
        يُعيد True عند النجاح.
        """
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            log.error("MT5Agent: حزمة MetaTrader5 غير مثبّتة — pip install MetaTrader5")
            return False

        with _mt5_lock:
            # تهيئة المنصة
            if not self._mt5.initialize():
                err = self._mt5.last_error()
                log.error(f"MT5Agent: initialize() فشل → {err}")
                return False

            # تسجيل الدخول
            if self._login and self._password and self._server:
                ok = self._mt5.login(
                    login    = int(self._login),
                    password = str(self._password),
                    server   = str(self._server),
                    timeout  = timeout * 1000,
                )
                if not ok:
                    err = self._mt5.last_error()
                    log.error(f"MT5Agent: login() فشل → {err}")
                    self._mt5.shutdown()
                    return False
            else:
                log.warning("MT5Agent: لا توجد بيانات تسجيل دخول — سيُستخدم الحساب المفتوح حالياً")

            info = self._mt5.account_info()
            if info is None:
                log.error("MT5Agent: account_info() → None بعد الاتصال")
                return False

            self._ready = True
            log.info(
                f"MT5Agent: متصل → حساب #{info.login} | "
                f"Broker: {info.company} | Balance: {info.balance:.2f} {info.currency}"
            )
            return True

    def is_ready(self) -> bool:
        if not self._ready or self._mt5 is None:
            return False
        try:
            return self._mt5.account_info() is not None
        except Exception:
            return False

    def disconnect(self):
        if self._mt5:
            with _mt5_lock:
                self._mt5.shutdown()
                self._ready = False
            log.info("MT5Agent: اتصال مُغلق")

    # ─────────────────────────────────────────────────────────
    #  السعر الحالي (من MT5 مباشرة — أسرع من yfinance)
    # ─────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float:
        """يُعيد آخر سعر Ask (للشراء) أو Bid (للبيع) من MT5."""
        mt5_sym = self._resolve_symbol(symbol)
        if not mt5_sym or not self._ready:
            return 0.0
        try:
            with _mt5_lock:
                tick = self._mt5.symbol_info_tick(mt5_sym)
            if tick is None:
                return 0.0
            return (tick.ask + tick.bid) / 2.0
        except Exception as e:
            log.warning(f"MT5Agent: get_current_price({symbol}) → {e}")
            return 0.0

    # ─────────────────────────────────────────────────────────
    #  فتح صفقة
    # ─────────────────────────────────────────────────────────

    def open_position(
        self,
        symbol:    str,
        direction: str,      # "LONG" | "SHORT"
        entry:     float,
        sl:        float,
        tp:        float,
        risk_usd:  float,
    ) -> int | None:
        """
        فتح صفقة Market Order.
        يُعيد ticket_id عند النجاح، أو None عند الفشل.
        """
        if not self.is_ready():
            log.error("MT5Agent: open_position — غير متصل")
            return None

        mt5_sym = self._resolve_symbol(symbol)
        if not mt5_sym:
            log.error(f"MT5Agent: رمز غير موجود في خريطة MT5: {symbol}")
            return None

        mt5 = self._mt5

        # ── تأكد من توفر الرمز ──────────────────────────────
        with _mt5_lock:
            if not mt5.symbol_select(mt5_sym, True):
                log.error(f"MT5Agent: symbol_select({mt5_sym}) فشل")
                return None
            _time.sleep(0.1)   # انتظر تحميل بيانات الرمز

            sym_info = mt5.symbol_info(mt5_sym)
            if sym_info is None:
                log.error(f"MT5Agent: symbol_info({mt5_sym}) → None")
                return None

            tick = mt5.symbol_info_tick(mt5_sym)
            if tick is None:
                log.error(f"MT5Agent: symbol_info_tick({mt5_sym}) → None")
                return None

        # ── حساب حجم اللوت ─────────────────────────────────
        lot = self._calc_lot_size(sym_info, sl, entry, risk_usd, direction)
        if lot <= 0:
            log.error(f"MT5Agent: حجم اللوت غير صالح: {lot}")
            return None

        # ── نوع الأمر ────────────────────────────────────────
        order_type = mt5.ORDER_TYPE_BUY if direction == "LONG" else mt5.ORDER_TYPE_SELL
        price      = tick.ask            if direction == "LONG" else tick.bid

        # ── بناء الطلب ───────────────────────────────────────
        request = {
            "action":        mt5.TRADE_ACTION_DEAL,
            "symbol":        mt5_sym,
            "volume":        lot,
            "type":          order_type,
            "price":         price,
            "sl":            sl,
            "tp":            tp,
            "deviation":     20,          # max slippage in points
            "magic":         config.MT5_MAGIC_NUMBER,
            "comment":       f"ICT-Lab {direction[:1]}",
            "type_time":     mt5.ORDER_TIME_GTC,
            "type_filling":  self._get_filling_mode(sym_info),
        }

        with _mt5_lock:
            result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            log.error(f"MT5Agent: order_send → None | {err}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(
                f"MT5Agent: order_send فشل | retcode={result.retcode} "
                f"({result.comment}) | symbol={mt5_sym} lot={lot}"
            )
            return None

        ticket = result.order
        log.info(
            f"MT5Agent: صفقة مفتوحة ✓ ticket={ticket} | "
            f"{direction} {mt5_sym} @ {price:.5f} | "
            f"SL={sl:.5f} TP={tp:.5f} | Lot={lot} | Risk=${risk_usd:.2f}"
        )
        return ticket

    # ─────────────────────────────────────────────────────────
    #  إغلاق صفقة
    # ─────────────────────────────────────────────────────────

    def close_position(self, ticket: int, volume: float = 0) -> bool:
        """
        إغلاق صفقة بالـ ticket.
        volume=0 → إغلاق كامل.
        """
        if not self.is_ready():
            return False

        mt5 = self._mt5

        with _mt5_lock:
            positions = mt5.positions_get(ticket=ticket)

        if not positions:
            log.warning(f"MT5Agent: close_position — ticket {ticket} غير موجود")
            return False

        pos = positions[0]
        mt5_sym = pos.symbol
        close_volume = volume if volume > 0 else pos.volume

        with _mt5_lock:
            tick = mt5.symbol_info_tick(mt5_sym)
            if tick is None:
                return False

        # عكس اتجاه الصفقة للإغلاق
        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price      = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price      = tick.ask

        with _mt5_lock:
            sym_info = mt5.symbol_info(mt5_sym)

        request = {
            "action":        mt5.TRADE_ACTION_DEAL,
            "symbol":        mt5_sym,
            "volume":        close_volume,
            "type":          order_type,
            "position":      ticket,
            "price":         price,
            "deviation":     20,
            "magic":         config.MT5_MAGIC_NUMBER,
            "comment":       "ICT-Lab close",
            "type_time":     mt5.ORDER_TIME_GTC,
            "type_filling":  self._get_filling_mode(sym_info) if sym_info else mt5.ORDER_FILLING_IOC,
        }

        with _mt5_lock:
            result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = mt5.last_error() if result is None else result.comment
            log.error(f"MT5Agent: close_position({ticket}) فشل → {err}")
            return False

        log.info(f"MT5Agent: صفقة مُغلقة ✓ ticket={ticket}")
        return True

    # ─────────────────────────────────────────────────────────
    #  تعديل SL/TP
    # ─────────────────────────────────────────────────────────

    def modify_sl_tp(self, ticket: int, sl: float, tp: float) -> bool:
        if not self.is_ready():
            return False

        mt5 = self._mt5
        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl":       sl,
            "tp":       tp,
        }
        with _mt5_lock:
            result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = mt5.last_error() if result is None else result.comment
            log.error(f"MT5Agent: modify_sl_tp({ticket}) فشل → {err}")
            return False

        log.info(f"MT5Agent: SL/TP معدّل ✓ ticket={ticket} | SL={sl:.5f} TP={tp:.5f}")
        return True

    def move_to_breakeven(self, ticket: int, entry: float, tp: float) -> bool:
        """نقل SL إلى نقطة الدخول (Breakeven)."""
        return self.modify_sl_tp(ticket, sl=entry, tp=tp)

    # ─────────────────────────────────────────────────────────
    #  معلومات الحساب
    # ─────────────────────────────────────────────────────────

    def get_account_info(self) -> dict | None:
        if not self.is_ready():
            return None
        try:
            with _mt5_lock:
                info = self._mt5.account_info()
            if info is None:
                return None
            return {
                "balance":      info.balance,
                "equity":       info.equity,
                "margin":       info.margin,
                "free_margin":  info.margin_free,
                "profit":       info.profit,
                "currency":     info.currency,
                "leverage":     info.leverage,
                "login":        info.login,
                "server":       info.server,
                "company":      info.company,
            }
        except Exception as e:
            log.error(f"MT5Agent: get_account_info → {e}")
            return None

    # ─────────────────────────────────────────────────────────
    #  الصفقات المفتوحة
    # ─────────────────────────────────────────────────────────

    def get_open_positions(self) -> list[dict]:
        if not self.is_ready():
            return []
        try:
            with _mt5_lock:
                positions = self._mt5.positions_get()
            if positions is None:
                return []

            result = []
            for pos in positions:
                direction = "LONG" if pos.type == self._mt5.ORDER_TYPE_BUY else "SHORT"
                result.append({
                    "ticket":     pos.ticket,
                    "position_id": pos.ticket,    # alias للتوافق مع executor
                    "symbol":     pos.symbol,
                    "direction":  direction,
                    "volume":     pos.volume,
                    "entry":      pos.price_open,
                    "sl":         pos.sl,
                    "tp":         pos.tp,
                    "profit":     pos.profit,
                    "magic":      pos.magic,
                    "comment":    pos.comment,
                    "time":       pos.time,
                })
            return result
        except Exception as e:
            log.error(f"MT5Agent: get_open_positions → {e}")
            return []

    # ─────────────────────────────────────────────────────────
    #  Helpers خاصة
    # ─────────────────────────────────────────────────────────

    def _resolve_symbol(self, symbol: str) -> str | None:
        """يُحوّل رمز yfinance (^DJI) إلى رمز MT5 (US30Cash مثلاً)."""
        return self._symbol_map.get(symbol, symbol)

    def _calc_lot_size(
        self,
        sym_info,
        sl:         float,
        entry:      float,
        risk_usd:   float,
        direction:  str,
    ) -> float:
        """
        يحسب حجم اللوت بناءً على المخاطرة بالدولار.
        lot = risk_usd / (sl_distance_in_points × point_value_per_lot)
        """
        try:
            point       = sym_info.point or 1e-5
            tick_value  = sym_info.trade_tick_value   # قيمة tick واحد بعملة الحساب
            tick_size   = sym_info.trade_tick_size or point

            # قيمة النقطة الواحدة لكل لوت
            point_value_per_lot = (tick_value / tick_size) * point

            if point_value_per_lot <= 0:
                log.warning(f"MT5Agent: point_value_per_lot صفر → استخدام config")
                point_value_per_lot = config.CT_POINT_VALUE_PER_LOT * point

            sl_distance = abs(entry - sl)
            if sl_distance <= 0:
                return 0.0

            sl_in_points = sl_distance / point
            raw_lot      = risk_usd / (sl_in_points * point_value_per_lot)

            # تقريب لـ lot step
            lot_step = sym_info.volume_step or 0.01
            lot_min  = sym_info.volume_min  or 0.01
            lot_max  = min(sym_info.volume_max or 100.0, config.PROPFIRM_MAX_LOT_PER_TRADE)

            lot = round(raw_lot / lot_step) * lot_step
            lot = max(lot_min, min(lot_max, lot))
            lot = round(lot, 8)
            return lot

        except Exception as e:
            log.error(f"MT5Agent: _calc_lot_size → {e}")
            return 0.0

    def _get_filling_mode(self, sym_info) -> int:
        """يُحدد نوع التعبئة المدعوم من الوسيط."""
        mt5 = self._mt5
        filling_type = sym_info.filling_mode if sym_info else 0
        # ORDER_FILLING_FOK = 1, ORDER_FILLING_IOC = 2, ORDER_FILLING_RETURN = 4
        if filling_type & mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        if filling_type & mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN


# ══════════════════════════════════════════════════════════════════════
#  Singleton
# ══════════════════════════════════════════════════════════════════════

def get_mt5_agent() -> MT5Agent | None:
    """
    يُعيد المثيل الوحيد لـ MT5Agent.
    يُعيد None إذا كان BROKER != "mt5".
    """
    global _mt5_instance

    if config.BROKER != "mt5":
        return None

    if _mt5_instance is not None:
        return _mt5_instance

    agent = MT5Agent()
    if not agent.connect():
        log.error("MT5Agent: فشل الاتصال الأولي")
        return None

    _mt5_instance = agent
    return agent
