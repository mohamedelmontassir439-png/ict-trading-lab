"""
cTrader Open API Agent — تنفيذ الصفقات الحقيقية على حساب FUNDEDHIVE
يعمل على بروتوكول TCP مع cTrader Open API v2 (Spotware).

متطلبات:
    pip install ctrader-open-api

بيانات الاعتماد المطلوبة (في .env):
    CTRADER_CLIENT_ID      — من https://openapi.ctrader.com/
    CTRADER_CLIENT_SECRET
    CTRADER_ACCOUNT_ID     — رقم حساب FUNDEDHIVE
    CTRADER_ACCESS_TOKEN   — OAuth2 access token
"""
from __future__ import annotations

import sys, os, threading, logging, time
from typing import Optional

log = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

# ── Try importing ctrader-open-api (Twisted-based) ──────────────────
try:
    from twisted.internet import reactor, ssl
    from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (
        ProtoOAPayloadType,
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq,
        ProtoOAAccountAuthReq,
        ProtoOANewOrderReq,
        ProtoOAAmendPositionSLTPReq,
        ProtoOAClosePositionReq,
        ProtoOAReconcileReq,
        ProtoOATraderReq,
        ProtoOASymbolsListReq,
        ProtoOAErrorRes,
    )
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAOrderType,
        ProtoOATradeSide,
    )
    _CT_AVAILABLE = True
except ImportError:
    _CT_AVAILABLE = False
    log.warning(
        "ctrader-open-api غير مثبّت — شغّل: pip install ctrader-open-api\n"
        "التداول الحقيقي معطّل حتى يتم التثبيت."
    )


# ══════════════════════════════════════════════════════════════════════
#  CTraderAgent — wrapper متزامن فوق Twisted
# ══════════════════════════════════════════════════════════════════════

class CTraderAgent:
    """
    واجهة متزامنة (blocking) لـ cTrader Open API.
    تشغّل Twisted reactor في خيط خلفي daemon.
    جميع التوابع العامة آمنة للاستخدام من أي خيط.
    """

    # مهلة انتظار الرد من الخادم (ثواني)
    _TIMEOUT = 15

    def __init__(self):
        if not _CT_AVAILABLE:
            raise RuntimeError("ctrader-open-api غير مثبّت — pip install ctrader-open-api")

        self._client: Optional[Client] = None
        self._lock    = threading.Lock()
        self._pending: dict[str, dict] = {}   # client_msg_id → {event, result}
        self._counter = 1

        # حالة الاتصال
        self._app_authed  = threading.Event()
        self._acct_authed = threading.Event()

        # بيانات الأدوات المالية: اسم → (symbol_id, lot_size, digits, pip_size)
        self._symbols: dict[str, dict] = {}
        self._symbols_loaded = threading.Event()

        # تشغيل Twisted في خيط منفصل
        self._reactor_thread = threading.Thread(
            target=self._start_reactor, daemon=True, name="cTrader-Reactor"
        )
        self._reactor_thread.start()

    # ──────────────────────────────────────────
    #  Reactor bootstrap
    # ──────────────────────────────────────────

    def _start_reactor(self):
        endpoint = (
            EndPoints.PROTOBUF_DEMO_HOST if config.CTRADER_DEMO
            else EndPoints.PROTOBUF_LIVE_HOST
        )
        port = (
            EndPoints.PROTOBUF_DEMO_PORT if config.CTRADER_DEMO
            else EndPoints.PROTOBUF_LIVE_PORT
        )

        factory = TcpProtocol.ClientFactory()
        factory.setConnectionMadeCallback(self._on_connected)
        factory.setConnectionLostCallback(self._on_disconnected)
        factory.setMessageReceivedCallback(self._on_message)

        if config.CTRADER_DEMO:
            reactor.connectTCP(endpoint, port, factory)
        else:
            ctx = ssl.ClientContextFactory()
            reactor.connectSSL(endpoint, port, factory, ctx)

        reactor.run(installSignalHandlers=False)

    # ──────────────────────────────────────────
    #  Twisted callbacks
    # ──────────────────────────────────────────

    def _on_connected(self, client: "Client"):
        self._client = client
        log.info("cTrader: متصل — جارٍ المصادقة...")

        req = ProtoOAApplicationAuthReq()
        req.clientId     = config.CTRADER_CLIENT_ID
        req.clientSecret = config.CTRADER_CLIENT_SECRET
        client.send(req)

    def _on_disconnected(self, client: "Client", reason):
        log.warning(f"cTrader: انقطع الاتصال — {reason}")
        self._app_authed.clear()
        self._acct_authed.clear()
        self._symbols_loaded.clear()

    def _on_message(self, client: "Client", message):
        try:
            ptype  = message.payloadType
            msg_id = message.clientMsgId   # string; may be empty

            # — App auth OK
            if ptype == ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES:
                self._app_authed.set()
                log.info("cTrader: تم التحقق من التطبيق")
                req = ProtoOAAccountAuthReq()
                req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID
                req.accessToken         = config.CTRADER_ACCESS_TOKEN
                client.send(req)

            # — Account auth OK
            elif ptype == ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES:
                self._acct_authed.set()
                log.info("cTrader: تم التحقق من الحساب — جارٍ تحميل الأدوات...")
                req = ProtoOASymbolsListReq()
                req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID
                req.includeArchivedSymbols = False
                client.send(req)

            # — Symbols list
            elif ptype == ProtoOAPayloadType.PROTO_OA_SYMBOLS_LIST_RES:
                msg = Protobuf.extract(message)
                for sym in msg.symbol:
                    self._symbols[sym.symbolName] = {
                        "id":       sym.symbolId,
                        "digits":   sym.digits,
                        "pipSize":  sym.pipSize if hasattr(sym, "pipSize") else 0.00001,
                    }
                self._symbols_loaded.set()
                log.info(f"cTrader: {len(self._symbols)} أداة مالية محمّلة")

            # — Error
            elif ptype == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
                msg = Protobuf.extract(message)
                log.error(f"cTrader خطأ: {msg.errorCode} — {msg.description}")
                if msg_id and msg_id in self._pending:
                    entry = self._pending.pop(msg_id)
                    entry["error"] = f"{msg.errorCode}: {msg.description}"
                    entry["event"].set()

            # — أي رد آخر (execution event، trader info، reconcile ...)
            elif msg_id and msg_id in self._pending:
                entry = self._pending.pop(msg_id)
                entry["result"] = Protobuf.extract(message)
                entry["event"].set()

        except Exception as exc:
            log.error(f"cTrader _on_message خطأ: {exc}", exc_info=True)

    # ──────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────

    def _next_id(self) -> str:
        with self._lock:
            mid = str(self._counter)
            self._counter += 1
            return mid

    def _send_wait(self, proto_msg, timeout: int = _TIMEOUT) -> Optional[object]:
        """أرسل رسالة protobuf وانتظر الرد (متزامن)."""
        msg_id = self._next_id()
        event  = threading.Event()
        self._pending[msg_id] = {"event": event, "result": None, "error": None}

        def _do():
            self._client.send(proto_msg, clientMsgId=msg_id)

        reactor.callFromThread(_do)

        if not event.wait(timeout=timeout):
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"cTrader: لم يرد الخادم خلال {timeout}s")

        entry = self._pending.pop(msg_id, {})
        if entry.get("error"):
            raise RuntimeError(f"cTrader: {entry['error']}")
        return entry.get("result")

    def _require_ready(self):
        """تأكد من اكتمال المصادقة قبل أي عملية."""
        if not self._acct_authed.wait(timeout=30):
            raise RuntimeError("cTrader: لم تكتمل مصادقة الحساب")
        if not self._symbols_loaded.wait(timeout=30):
            raise RuntimeError("cTrader: لم تكتمل قائمة الأدوات المالية")

    def _resolve_symbol(self, our_symbol: str) -> dict:
        """حوّل رمز النظام (مثل '^NDX') إلى بيانات cTrader."""
        ct_name = config.CTRADER_SYMBOL_MAP.get(our_symbol, our_symbol)
        info    = self._symbols.get(ct_name)
        if not info:
            # محاولة ثانية بدون حساسية الحالة
            for k, v in self._symbols.items():
                if k.upper() == ct_name.upper():
                    return v
            raise KeyError(
                f"الرمز '{ct_name}' غير موجود في قائمة الأدوات. "
                f"تحقق من CT_SYMBOL_US30/US100/US500 في .env"
            )
        return info

    def _calc_volume(self, symbol_info: dict, entry: float,
                     sl: float, risk_usd: float) -> int:
        """
        احسب حجم الصفقة بوحدات cTrader.
        cTrader: volume = lots * 100  (1 lot = 100 units internally)
        نبدأ بـ lots ثم نضرب في 100.
        """
        risk_pts  = abs(entry - sl)
        if risk_pts <= 0:
            raise ValueError("المسافة بين الدخول ووقف الخسارة = 0")

        # قيمة النقطة (pip) لكل lot واحد — يُعدَّل حسب الأداة
        # للمؤشرات: عادةً 1 نقطة = 1 USD/lot
        # يُعدَّل إذا كانت قيمة النقطة مختلفة عند FUNDEDHIVE
        point_value_per_lot = float(os.getenv("CT_POINT_VALUE_PER_LOT", "1.0"))

        lots = risk_usd / (risk_pts * point_value_per_lot)
        lots = min(lots, config.PROPFIRM_MAX_LOT_PER_TRADE)

        # تقريب لأدنى وحدة (0.01 lot = 1 unit في بعض الـ brokers)
        lots = round(lots, 2)
        volume_units = int(lots * 100)   # cTrader internal

        if volume_units < 1:
            raise ValueError(f"الحجم المحسوب أصغر من الحد الأدنى (lots={lots:.4f})")

        return volume_units

    # ──────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────

    def connect(self, timeout: int = 30) -> bool:
        """
        انتظر حتى يكتمل الاتصال والمصادقة.
        استدعها مرة واحدة عند بدء التشغيل.
        """
        try:
            self._require_ready()
            return True
        except RuntimeError as e:
            log.error(f"cTrader connect failed: {e}")
            return False

    def open_position(
        self,
        symbol:    str,
        direction: str,     # "LONG" | "SHORT"
        entry:     float,
        sl:        float,
        tp:        float,
        risk_usd:  float,
    ) -> Optional[int]:
        """
        افتح صفقة سوق.
        إرجاع: positionId (int) أو None عند الفشل.
        """
        try:
            self._require_ready()
            sym_info = self._resolve_symbol(symbol)
            volume   = self._calc_volume(sym_info, entry, sl, risk_usd)

            req = ProtoOANewOrderReq()
            req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID
            req.symbolId   = sym_info["id"]
            req.orderType  = ProtoOAOrderType.MARKET
            req.tradeSide  = (ProtoOATradeSide.BUY if direction == "LONG"
                              else ProtoOATradeSide.SELL)
            req.volume     = volume
            req.stopLoss   = round(sl, sym_info["digits"])
            req.takeProfit = round(tp, sym_info["digits"])

            result = self._send_wait(req)
            if result and hasattr(result, "position"):
                pos_id = result.position.positionId
                log.info(
                    f"cTrader: صفقة مفتوحة #{pos_id} {direction} {symbol} "
                    f"vol={volume} SL={sl:.5f} TP={tp:.5f}"
                )
                return pos_id

            log.error(f"cTrader open_position: رد غير متوقع — {result}")
            return None

        except Exception as exc:
            log.error(f"cTrader open_position خطأ: {exc}", exc_info=True)
            return None

    def close_position(self, position_id: int, volume: int = 0) -> bool:
        """
        أغلق صفقة مفتوحة.
        volume=0 → إغلاق كامل (الافتراضي).
        """
        try:
            self._require_ready()

            req = ProtoOAClosePositionReq()
            req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID
            req.positionId = position_id
            # إذا volume=0 → نرسل 1 لأن الحقل مطلوب؛ cTrader سيُغلق الكامل
            req.volume = volume if volume > 0 else 1

            result = self._send_wait(req)
            if result:
                log.info(f"cTrader: صفقة #{position_id} مُغلقة")
                return True
            return False

        except Exception as exc:
            log.error(f"cTrader close_position خطأ: {exc}", exc_info=True)
            return False

    def modify_sl_tp(self, position_id: int, sl: float, tp: float) -> bool:
        """عدّل وقف الخسارة والهدف لصفقة مفتوحة."""
        try:
            self._require_ready()

            req = ProtoOAAmendPositionSLTPReq()
            req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID
            req.positionId = position_id
            req.stopLoss   = sl
            req.takeProfit = tp

            result = self._send_wait(req)
            if result:
                log.info(f"cTrader: #{position_id} SL={sl:.5f} TP={tp:.5f} مُعدَّل")
                return True
            return False

        except Exception as exc:
            log.error(f"cTrader modify_sl_tp خطأ: {exc}", exc_info=True)
            return False

    def move_to_breakeven(self, position_id: int, entry: float, tp: float) -> bool:
        """نقّل وقف الخسارة إلى نقطة التعادل."""
        return self.modify_sl_tp(position_id, sl=entry, tp=tp)

    def get_account_info(self) -> Optional[dict]:
        """استرجع رصيد الحساب والملكية والهامش."""
        try:
            self._require_ready()

            req = ProtoOATraderReq()
            req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID

            result = self._send_wait(req)
            if result and hasattr(result, "trader"):
                t = result.trader
                return {
                    "balance":      t.balance / 100.0,   # cTrader stores in cents
                    "equity":       t.balance / 100.0,
                    "currency":     t.depositAsset.name if hasattr(t, "depositAsset") else "USD",
                }
            return None

        except Exception as exc:
            log.error(f"cTrader get_account_info خطأ: {exc}", exc_info=True)
            return None

    def get_open_positions(self) -> list[dict]:
        """استرجع جميع الصفقات المفتوحة."""
        try:
            self._require_ready()

            req = ProtoOAReconcileReq()
            req.ctidTraderAccountId = config.CTRADER_ACCOUNT_ID

            result = self._send_wait(req)
            positions = []
            if result and hasattr(result, "position"):
                for pos in result.position:
                    sym_name = self._id_to_name(pos.tradeData.symbolId)
                    positions.append({
                        "position_id": pos.positionId,
                        "symbol_id":   pos.tradeData.symbolId,
                        "symbol":      sym_name,
                        "direction":   "LONG" if pos.tradeData.tradeSide == ProtoOATradeSide.BUY else "SHORT",
                        "volume":      pos.tradeData.volume,
                        "entry":       pos.price,
                        "sl":          pos.stopLoss,
                        "tp":          pos.takeProfit,
                        "swap":        pos.swap / 100.0,
                        "commission":  pos.commission / 100.0 if hasattr(pos, "commission") else 0.0,
                    })
            return positions

        except Exception as exc:
            log.error(f"cTrader get_open_positions خطأ: {exc}", exc_info=True)
            return []

    def _id_to_name(self, symbol_id: int) -> str:
        for name, info in self._symbols.items():
            if info["id"] == symbol_id:
                return name
        return str(symbol_id)

    def is_ready(self) -> bool:
        return self._acct_authed.is_set() and self._symbols_loaded.is_set()


# ══════════════════════════════════════════════════════════════════════
#  Singleton — استخدم هذا في executor_agent
# ══════════════════════════════════════════════════════════════════════

_agent: Optional[CTraderAgent] = None
_agent_lock = threading.Lock()


def get_ctrader_agent() -> Optional[CTraderAgent]:
    """
    إرجاع مثيل CTraderAgent (singleton).
    None إذا LIVE_MODE=false أو المكتبة غير مثبتة.
    """
    global _agent
    if not config.LIVE_MODE:
        return None
    if not _CT_AVAILABLE:
        return None

    with _agent_lock:
        if _agent is None:
            if not all([
                config.CTRADER_CLIENT_ID,
                config.CTRADER_CLIENT_SECRET,
                config.CTRADER_ACCOUNT_ID,
                config.CTRADER_ACCESS_TOKEN,
            ]):
                log.error(
                    "cTrader: بيانات الاعتماد ناقصة في .env\n"
                    "تأكد من ضبط: CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, "
                    "CTRADER_ACCOUNT_ID, CTRADER_ACCESS_TOKEN"
                )
                return None
            try:
                _agent = CTraderAgent()
                log.info("cTrader: جارٍ الاتصال...")
                # لا ننتظر هنا — الاتصال يحدث في الخلفية
            except Exception as exc:
                log.error(f"cTrader init error: {exc}")
                _agent = None

    return _agent
