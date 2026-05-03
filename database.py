import sqlite3
from datetime import datetime, timedelta
from typing import Optional


class Database:
    def __init__(self, db_path: str = "vpn_bot.db"):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id          INTEGER PRIMARY KEY,
                    username    TEXT,
                    full_name   TEXT,
                    joined_at   TEXT,
                    sub_until   TEXT
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    plan_id     TEXT,
                    price       INTEGER,
                    status      TEXT DEFAULT 'pending',
                    created_at  TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            """)

    # ── Users ──────────────────────────────────────────
    def add_user(self, user_id: int, username: str, full_name: str):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO users (id, username, full_name, joined_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, full_name, datetime.now().isoformat()))
            conn.execute("""
                UPDATE users SET username=?, full_name=? WHERE id=?
            """, (username, full_name, user_id))

    def get_user(self, user_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("sub_until"):
                sub_until = datetime.fromisoformat(data["sub_until"])
                days_left = (sub_until - datetime.now()).days
                data["sub_days_left"] = max(0, days_left)
            else:
                data["sub_days_left"] = 0
            return data

    def set_user_subscription(self, user_id: int, days: int):
        sub_until = (datetime.now() + timedelta(days=days)).isoformat()
        with self._conn() as conn:
            conn.execute("UPDATE users SET sub_until=? WHERE id=?",
                         (sub_until, user_id))

    def get_all_users(self) -> list:
        with self._conn() as conn:
            return [dict(r) for r in
                    conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()]

    # ── Orders ─────────────────────────────────────────
    def create_order(self, user_id: int, plan_id: str, price: int) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO orders (user_id, plan_id, price, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
            """, (user_id, plan_id, price, datetime.now().isoformat()))
            return cur.lastrowid

    def get_order(self, order_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return dict(row) if row else None

    def get_user_orders(self, user_id: int) -> list:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
                (user_id,)
            ).fetchall()]

    def get_pending_orders(self) -> list:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM orders WHERE status='pending' ORDER BY created_at DESC"
            ).fetchall()]

    def update_order_status(self, order_id: int, status: str):
        with self._conn() as conn:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

    # ── Stats ───────────────────────────────────────────
    def get_stats(self) -> dict:
        with self._conn() as conn:
            total_users   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_orders  = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            pending       = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
            delivered     = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status='delivered'").fetchone()[0]
            return {
                "total_users": total_users,
                "total_orders": total_orders,
                "pending_orders": pending,
                "delivered_orders": delivered,
            }
