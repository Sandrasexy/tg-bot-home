import datetime
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

_DB_URL = os.environ["DATABASE_URL"]


@contextmanager
def _cursor():
    conn = psycopg2.connect(_DB_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id           SERIAL PRIMARY KEY,
                payer_id     BIGINT NOT NULL,
                amount       REAL   NOT NULL,
                description  TEXT   NOT NULL,
                mode         TEXT   NOT NULL DEFAULT 'shared',
                personal_pct REAL   NOT NULL DEFAULT 0,
                purchase_date DATE  NOT NULL DEFAULT CURRENT_DATE,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def add_expense(
    payer_id: int,
    amount: float,
    description: str,
    mode: str = "shared",
    personal_pct: float = 0.0,
    purchase_date: str | None = None,
) -> int:
    date_val = purchase_date or datetime.date.today().isoformat()
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO expenses (payer_id, amount, description, mode, personal_pct, purchase_date)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (payer_id, amount, description, mode, personal_pct, date_val),
        )
        return cur.fetchone()["id"]  # type: ignore[index]


def get_expenses() -> list:
    with _cursor() as cur:
        cur.execute("SELECT * FROM expenses ORDER BY purchase_date, created_at")
        return cur.fetchall()


def get_recent_expenses(n: int = 10) -> list:
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM expenses ORDER BY purchase_date DESC, created_at DESC LIMIT %s", (n,)
        )
        return cur.fetchall()


def delete_last_expense() -> dict | None:
    with _cursor() as cur:
        cur.execute("SELECT * FROM expenses ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM expenses WHERE id = %s", (row["id"],))
        return row


def clear_all() -> int:
    with _cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM expenses")
        count: int = cur.fetchone()["count"]  # type: ignore[index]
        cur.execute("DELETE FROM expenses")
        return count
