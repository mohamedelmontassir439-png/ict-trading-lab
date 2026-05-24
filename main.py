"""
main.py  —  نقطة الانطلاق الرئيسية
شغّل: py main.py
Dashboard: http://localhost:5000
"""
import os
import time
import threading
import logging
import sys
from datetime import datetime, timezone, time as dtime

import config

_log_dir = os.path.dirname(os.path.abspath(config.LOG_PATH))
if _log_dir:
    os.makedirs(_log_dir, exist_ok=True)

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# ── Project imports ───────────────────────────
from database.models import init_db
from agents.data_agent       import (fetch_ohlcv, is_kill_zone,
                                      get_all_symbols, get_current_price)
from agents.ict_agent        import analyze, get_best_entry_zone
from agents.risk_agent       import build_trade_signal, risk_of_ruin_check
from agents.executor_agent   import open_trade, check_and_close_trades
from agents.orchestrator     import ai_decide
from agents.ai_council       import run_specialist_council, council_minutes
from agents.journal_agent    import update_daily_stats, print_report

# ── New ICT concept agents ────────────────────
from agents.pdh_pdl_agent        import analyze_pdh_pdl
from agents.po3_agent            import analyze_po3
from agents.breaker_block_agent  import analyze_breakers
from agents.silver_bullet_agent  import analyze_silver_bullet
from agents.displacement_agent   import analyze_displacement
from agents.volume_profile_agent import analyze_volume_profile
from agents.divergence_agent     import analyze_divergence
from agents.cot_agent            import get_cot_signal, cot_filter
from agents.daily_bias_agent     import get_daily_bias, daily_bias_filter

from dashboard.app import run_dashboard


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════

def _grade_trade(score: int) -> str:
    if score >= 9:
        return "A"
    if score >= 7:
        return "B"
    return "C"


# ══════════════════════════════════════════════
#  MAIN TRADING LOOP
# ══════════════════════════════════════════════

def trading_cycle():
    log.info("═" * 55)
    log.info(f"  CYCLE START  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("═" * 55)

    # ── Risk of Ruin guard (global) ──
    ruin_ok, ruin_reason = risk_of_ruin_check()
    if not ruin_ok:
        log.warning(f"  RISK OF RUIN: {ruin_reason}")
        check_and_close_trades()
        update_daily_stats()
        return

    # ── Step 1: Monitor open trades ──
    try:
        check_and_close_trades()
    except Exception as e:
        log.error(f"Executor error: {e}")

    # ── Step 2: Kill Zone check ──
    in_kz, kz_name = is_kill_zone()
    if not in_kz:
        log.info("  Not in Kill Zone — monitoring only")
        update_daily_stats()
        return

    log.info(f"  Kill Zone ACTIVE: {kz_name}")

    # ── Step 3: Analyze each symbol ──
    for symbol, market in get_all_symbols():
        try:
            _analyze_symbol(symbol, market, kz_name)
        except Exception as e:
            lab = config.display_symbol(symbol) if market == "forex" else symbol
            log.error(f"Error on {lab}: {e}", exc_info=True)

    # ── Step 4: Update journal ──
    update_daily_stats()
    try:
        print_report()
    except Exception as e:
        log.warning(f"Report print error (non-critical): {e}")


def _analyze_symbol(symbol: str, market: str, kz_name: str):
    label = config.display_symbol(symbol) if market == "forex" else symbol
    log.info(f"    {label} [{market}]")

    # ── Session filters ──────────────────────────────────────────────
    if kz_name == "Asian":
        log.info(f"    {label}: skipping Asian session (indices only trade London/NY)")
        return

    # Judas Swing: skip first 15 min of NY (13:30-13:45 UTC is manipulation)
    now_utc = datetime.now(timezone.utc)
    now_t   = now_utc.time()
    if kz_name == "NewYork" and now_t < dtime(13, 45):
        log.info(f"    {label}: NY Judas Swing window (13:30-13:45) — wait")
        return

    # ── Fetch OHLCV — 4 timeframes (1m → 4h) ───────────────────────
    df_htf   = fetch_ohlcv(symbol, market, config.HTF_INTERVAL,   limit=200)  # 4h  — bias
    df_mtf   = fetch_ohlcv(symbol, market, config.MTF_INTERVAL,   limit=200)  # 1h  — structure
    df_ltf   = fetch_ohlcv(symbol, market, config.LTF_INTERVAL,   limit=200)  # 15m — entry zone
    df_entry = fetch_ohlcv(symbol, market, config.ENTRY_INTERVAL, limit=100)  # 1m  — trigger
    df_daily = fetch_ohlcv(symbol, market, "1d", limit=60)

    if df_htf.empty or df_ltf.empty:
        log.warning(f"    {label}: no data")
        return

    # ── Core ICT analysis (HTF bias + LTF entry) ─────────────────────
    analysis = analyze(symbol, market, df_htf, df_ltf)
    if not analysis:
        return

    current_price = analysis.current_price
    bias          = analysis.bias

    # ── MTF (1h) structure confirmation ──────────────────────────────
    if not df_mtf.empty:
        try:
            from agents.ict_agent import detect_swings, classify_structure
            mtf_struct, mtf_bias = classify_structure(detect_swings(df_mtf))
            log.info(f"    MTF(1h): Struct={mtf_struct} Bias={mtf_bias}")
            # If MTF contradicts HTF bias, lower confidence
            if mtf_bias not in (bias, "NEUTRAL"):
                log.info(f"    MTF conflict: HTF={bias} vs 1h={mtf_bias}")
        except Exception:
            pass

    log.info(f"    Bias={bias} | Struct={analysis.structure} | "
             f"Score={analysis.setup_score}/15 | Price={current_price:.5f} "
             f"[4h→1h→15m→1m]")

    # ── Extended ICT concept agents ──────────────────────────────────
    try:
        analysis.pdh_pdl = analyze_pdh_pdl(symbol, df_daily, df_ltf, current_price)
    except Exception:
        pass

    try:
        analysis.po3 = analyze_po3(symbol, df_entry if not df_entry.empty else df_ltf)
    except Exception:
        pass

    try:
        analysis.breaker = analyze_breakers(symbol, df_ltf, bias, current_price)
    except Exception:
        pass

    try:
        # Silver Bullet uses 1m for precise FVG detection in its windows
        _sb_df = df_entry if not df_entry.empty else df_ltf
        analysis.silver_bullet = analyze_silver_bullet(symbol, _sb_df, bias, current_price)
    except Exception:
        pass

    try:
        # Displacement is clearest on 1m
        _disp_df = df_entry if not df_entry.empty else df_ltf
        analysis.displacement = analyze_displacement(symbol, _disp_df, current_price)
    except Exception:
        pass

    try:
        analysis.volume_profile = analyze_volume_profile(symbol, df_ltf, current_price)
    except Exception:
        pass

    try:
        analysis.divergence = analyze_divergence(symbol, df_ltf, bias)
    except Exception:
        pass

    # Recompute score after all agents populated
    from agents.ict_agent import score_setup
    analysis.setup_score = score_setup(analysis)

    log.info(f"    Extended Score={analysis.setup_score}/15")

    # ── PDH/PDL alignment log ────────────────────────────────────────
    if analysis.pdh_pdl and (analysis.pdh_pdl.pdh_swept or analysis.pdh_pdl.pdl_swept):
        pp = analysis.pdh_pdl
        log.info(f"    PDH/PDL: PDH={pp.pdh:.5f}{'(swept)' if pp.pdh_swept else ''} "
                 f"PDL={pp.pdl:.5f}{'(swept)' if pp.pdl_swept else ''} hint={pp.bias_hint}")

    # ── PO3 log ──────────────────────────────────────────────────────
    if analysis.po3 and analysis.po3.phase != "Unknown":
        po3 = analysis.po3
        log.info(f"    PO3: Phase={po3.phase} | Manip={po3.manipulation_dir} | "
                 f"Dist={po3.distribution_bias}")

    # ── Score gate ───────────────────────────────────────────────────
    if analysis.setup_score < 6:
        log.info(f"    Score too low ({analysis.setup_score}/15) — skip")
        return

    # ── Daily bias filter ────────────────────────────────────────────
    try:
        daily_bias_result = get_daily_bias(symbol, df_daily)
        db_ok, db_reason = daily_bias_filter(daily_bias_result, bias, analysis.setup_score)
        if not db_ok:
            log.info(f"    Daily bias block: {db_reason}")
            return
        log.info(f"    Daily bias: {daily_bias_result.bias} | {db_reason}")
    except Exception as e:
        log.warning(f"    Daily bias error (non-critical): {e}")

    # ── Get best entry zone ──────────────────────────────────────────
    entry_zone = get_best_entry_zone(analysis)
    if not entry_zone:
        log.info(f"    No valid entry zone found")
        return

    log.info(f"    Entry Zone: {entry_zone['type']} "
             f"[{entry_zone['low']:.5f} – {entry_zone['high']:.5f}]")

    # ── Build risk signal ────────────────────────────────────────────
    signal = build_trade_signal(analysis, entry_zone, kz_name)
    if not signal:
        log.info(f"    Risk check failed — no signal")
        return

    # ── COT filter ───────────────────────────────────────────────────
    try:
        cot_signal = get_cot_signal(symbol)
        cot_ok, cot_reason = cot_filter(cot_signal, bias)
        if not cot_ok:
            log.info(f"    COT block: {cot_reason}")
            return
        if cot_signal != "NEUTRAL":
            log.info(f"    COT: {cot_reason}")
    except Exception as e:
        log.warning(f"    COT error (non-critical): {e}")

    # ── NY Opening Range override (13:45-14:15) ───────────────────────
    if kz_name == "NewYork" and df_ltf is not None and not df_ltf.empty:
        try:
            or_bars = df_ltf[[
                dtime(13, 30) <= t.time() <= dtime(13, 45)
                for t in df_ltf.index
            ]] if df_ltf.index.tzinfo else df_ltf.iloc[:0]
            if not or_bars.empty:
                or_high = float(or_bars["high"].max())
                or_low  = float(or_bars["low"].min())
                log.info(f"    NY OR: [{or_low:.5f} – {or_high:.5f}]")
        except Exception:
            pass

    # ── Trade grading ────────────────────────────────────────────────
    grade = _grade_trade(analysis.setup_score)
    signal["grade"] = grade

    # ── Multi-specialist AI council (Grade A only — conserve Gemini quota) ──
    council = None
    if getattr(config, "ENABLE_AI_COUNCIL", True) and grade == "A":
        try:
            time.sleep(2)   # 2s gap to respect 10 RPM free-tier limit
            council = run_specialist_council(analysis, signal, kz_name, df_htf, df_ltf)
            syn = council.get("synthesis") or {}
            if getattr(config, "COUNCIL_HARD_VETO", True) and syn.get("hard_veto"):
                log.info(f"    Specialist council HARD VETO — {str(syn.get('summary',''))[:200]}")
                return
            log.info(f"    Council: {council_minutes(council)} | {str(syn.get('summary',''))[:120]}")
        except Exception as e:
            log.warning(f"    Council error (non-critical): {e}")

    # ── AI Decision (Grade A/B only — Grade C uses rule-based fallback) ──
    if grade == "C":
        from agents.orchestrator import _fallback
        ai = _fallback(analysis)
    else:
        ai = ai_decide(analysis, signal, kz_name, council=council)
    decision   = ai.get("decision", "SKIP")
    reason     = ai.get("reason", "")
    confidence = ai.get("confidence", 0)

    log.info(f"    AI: {decision} | Confidence={confidence}/10 | Grade={grade}")
    log.info(f"         {reason}")

    thresh = int(getattr(config, "AI_ENTER_MIN_CONFIDENCE", 6))
    if (
        getattr(config, "COUNCIL_STRICTER_THRESHOLD", True)
        and council
        and int((council.get("synthesis") or {}).get("council_score") or 10) < 6
    ):
        thresh = max(thresh, 7)

    if decision == "ENTER" and confidence >= thresh:
        trade_id = open_trade(signal, reason, grade=grade)
        log.info(f"    Trade OPENED #{trade_id} — "
                 f"{signal['direction']} {label} @ {signal['entry']} [Grade {grade}]")
    else:
        if decision == "ENTER":
            log.info(f"    Trade SKIPPED (need confidence >= {thresh}, got {confidence})")
        else:
            log.info(f"    Trade SKIPPED")


# ══════════════════════════════════════════════
#  SCHEDULER
# ══════════════════════════════════════════════

def scheduler():
    log.info("ICT Trading Lab STARTED")
    log.info(f"    Capital: ${config.INITIAL_CAPITAL:,.0f}")
    _fx = [config.display_symbol(s) for s in config.FOREX_PAIRS]
    log.info(f"    Markets: {_fx}  (indices only — crypto removed)")
    log.info(f"    Filter : OB+FVG confluence only")
    log.info(f"    Interval: every {config.CHECK_INTERVAL_MINUTES} minutes")
    log.info(f"    AI council: {'ON' if getattr(config, 'ENABLE_AI_COUNCIL', True) else 'OFF'}")
    log.info("─" * 55)

    while True:
        try:
            trading_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)

        interval_secs = config.CHECK_INTERVAL_MINUTES * 60
        log.info(f"  Next cycle in {config.CHECK_INTERVAL_MINUTES} minutes...")
        time.sleep(interval_secs)


# ══════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════

def _acquire_lock():
    import atexit
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".trading_lock")
    if os.path.exists(lock_path):
        try:
            with open(lock_path) as f:
                old_pid = int(f.read().strip())
            import psutil
            if psutil.pid_exists(old_pid):
                log.error(f"Another instance is already running (PID {old_pid}). Exiting.")
                sys.exit(1)
        except Exception:
            pass
    with open(lock_path, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(lock_path) and os.remove(lock_path))


if __name__ == "__main__":
    try:
        import psutil
        _acquire_lock()
    except ImportError:
        log.warning("psutil not installed — cannot prevent duplicate instances")

    init_db()
    log.info("Database initialized")

    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    log.info(f"Dashboard running -> http://localhost:{config.DASHBOARD_PORT}")

    # Keepalive: ping own dashboard every 10 min to prevent Render free-tier sleep
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if render_url:
        import requests as _req
        def _keepalive():
            while True:
                try:
                    _req.get(render_url, timeout=10)
                except Exception:
                    pass
                time.sleep(600)
        threading.Thread(target=_keepalive, daemon=True).start()
        log.info(f"Keepalive active -> {render_url}")

    scheduler()
