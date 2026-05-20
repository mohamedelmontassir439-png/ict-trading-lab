import sqlite3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db_dir = os.path.dirname(os.path.abspath(config.DB_PATH))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = get_conn()
    c = conn.cursor()

    # ── Account state ──────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS account (
            id            INTEGER PRIMARY KEY,
            balance       REAL    DEFAULT 10000.0,
            equity        REAL    DEFAULT 10000.0,
            total_pnl     REAL    DEFAULT 0.0,
            win_count     INTEGER DEFAULT 0,
            loss_count    INTEGER DEFAULT 0,
            updated_at    TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO account (id, updated_at) VALUES (1, ?)",
              (_utc_now_iso(),))

    # ── Open / closed trades ──────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT,
            market        TEXT,    -- crypto / forex
            direction     TEXT,    -- LONG / SHORT
            entry_price   REAL,
            sl_price      REAL,
            tp_price      REAL,
            lot_size      REAL,
            risk_usd      REAL,
            status        TEXT    DEFAULT 'OPEN',   -- OPEN / WIN / LOSS / BE
            pnl           REAL    DEFAULT 0.0,
            rr_achieved   REAL,
            kill_zone     TEXT,
            setup_type    TEXT,    -- OB / FVG / OB+FVG
            bias          TEXT,    -- BULLISH / BEARISH
            reason        TEXT,    -- AI explanation
            opened_at     TEXT,
            closed_at     TEXT
        )
    """)

    # Migration: add be_moved column if missing (v1 fix)
    cols = [r["name"] for r in c.execute("PRAGMA table_info(trades)").fetchall()]
    if "be_moved" not in cols:
        c.execute("ALTER TABLE trades ADD COLUMN be_moved INTEGER DEFAULT 0")

    # ── Daily stats ───────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date          TEXT PRIMARY KEY,
            trades        INTEGER DEFAULT 0,
            wins          INTEGER DEFAULT 0,
            losses        INTEGER DEFAULT 0,
            pnl           REAL    DEFAULT 0.0,
            max_dd        REAL    DEFAULT 0.0
        )
    """)

    # ── Agent logs ────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            agent         TEXT,
            symbol        TEXT,
            message       TEXT,
            logged_at     TEXT
        )
    """)

    conn.commit()
    conn.close()


# ── Helpers ───────────────────────────────────────

def get_account():
    conn = get_conn()
    row = conn.execute("SELECT * FROM account WHERE id=1").fetchone()
    conn.close()
    return dict(row)


def update_account(balance, equity, total_pnl, win_count, loss_count):
    conn = get_conn()
    conn.execute("""
        UPDATE account SET balance=?, equity=?, total_pnl=?,
        win_count=?, loss_count=?, updated_at=? WHERE id=1
    """, (balance, equity, total_pnl, win_count, loss_count,
          _utc_now_iso()))
    conn.commit()
    conn.close()


def open_trade(symbol, market, direction, entry, sl, tp,
               lot, risk_usd, kill_zone, setup_type, bias, reason):
    conn = get_conn()
    conn.execute("""
        INSERT INTO trades
        (symbol,market,direction,entry_price,sl_price,tp_price,
         lot_size,risk_usd,kill_zone,setup_type,bias,reason,opened_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (symbol, market, direction, entry, sl, tp,
          lot, risk_usd, kill_zone, setup_type, bias, reason,
          _utc_now_iso()))
    trade_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return trade_id


def close_trade(trade_id, status, pnl, rr_achieved):
    conn = get_conn()
    conn.execute("""
        UPDATE trades SET status=?, pnl=?, rr_achieved=?, closed_at=?
        WHERE id=?
    """, (status, pnl, rr_achieved, _utc_now_iso(), trade_id))
    conn.commit()
    conn.close()


def move_sl_to_be(trade_id: int, entry_price: float):
    """Move SL to entry price and mark be_moved=1."""
    conn = get_conn()
    conn.execute("""
        UPDATE trades SET sl_price=?, be_moved=1
        WHERE id=?
    """, (entry_price, trade_id))
    conn.commit()
    conn.close()


def get_open_trades():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE status='OPEN'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_trades(limit=200):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_agent(agent, symbol, message):
    conn = get_conn()
    conn.execute(
        "INSERT INTO agent_logs (agent,symbol,message,logged_at) VALUES (?,?,?,?)",
        (agent, symbol, message, _utc_now_iso()))
    conn.commit()
    conn.close()


def upsert_daily_stats(date_str, trades, wins, losses, pnl, max_dd):
    conn = get_conn()
    conn.execute("""
        INSERT INTO daily_stats (date,trades,wins,losses,pnl,max_dd)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
            trades=excluded.trades, wins=excluded.wins,
            losses=excluded.losses, pnl=excluded.pnl, max_dd=excluded.max_dd
    """, (date_str, trades, wins, losses, pnl, max_dd))
    conn.commit()
    conn.close()
