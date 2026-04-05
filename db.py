import sqlite3
from contextlib import contextmanager
from typing import Generator

from config import DB_PATH


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                payer_id    INTEGER NOT NULL,
                amount      REAL    NOT NULL,
                description TEXT    NOT NULL,
                mode        TEXT    NOT NULL DEFAULT 'shared',
                personal_pct REAL   NOT NULL DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_expense(
    payer_id: int,
    amount: float,
    description: str,
    mode: str = "shared",
    personal_pct: float = 0.0,
) -> int:
    """Insert expense and return its id."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (payer_id, amount, description, mode, personal_pct)"
            " VALUES (?, ?, ?, ?, ?)",
            (payer_id, amount, description, mode, personal_pct),
        )
        return cur.lastrowid  # type: ignore[return-value]


def get_expenses() -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM expenses ORDER BY created_at"
        ).fetchall()


def get_recent_expenses(n: int = 10) -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM expenses ORDER BY created_at DESC LIMIT ?", (n,)
        ).fetchall()


def delete_last_expense() -> sqlite3.Row | None:
    """Delete the most recent expense and return it (or None if empty)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM expenses ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            conn.execute("DELETE FROM expenses WHERE id = ?", (row["id"],))
        return row


def clear_all() -> int:
    """Delete all expenses and return how many were deleted."""
    with _conn() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM expenses")
        count: int = cur.fetchone()[0]
        conn.execute("DELETE FROM expenses")
        return count
