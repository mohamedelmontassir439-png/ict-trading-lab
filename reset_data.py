"""Wipe paper-trading DB and log. Run: py reset_data.py"""
import os
import sqlite3

import config
from database.models import init_db


def main() -> None:
    db = config.DB_PATH
    log_path = config.LOG_PATH

    init_db()

    if os.path.isfile(db):
        conn = sqlite3.connect(db, timeout=10)
        try:
            conn.execute("DELETE FROM agent_logs")
            conn.execute("DELETE FROM daily_stats")
            conn.execute("DELETE FROM trades")
            conn.execute(
                "UPDATE account SET balance=10000, equity=10000, total_pnl=0, "
                "win_count=0, loss_count=0, updated_at=datetime('now') WHERE id=1"
            )
            conn.commit()
        finally:
            conn.close()
        print(f"Wiped database: {db}")
    else:
        print(f"No database file at {db} (will be created on next start)")

    if os.path.isfile(log_path):
        try:
            os.remove(log_path)
            print(f"Removed log: {log_path}")
        except OSError as e:
            print(f"Could not remove log (close app / editors using it): {e}")
            try:
                open(log_path, "w", encoding="utf-8").close()
                print(f"Truncated log: {log_path}")
            except OSError as e2:
                print(f"Truncate failed: {e2}")


if __name__ == "__main__":
    main()
