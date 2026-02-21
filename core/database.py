"""
core/database.py — All database logic.

Performance design
------------------
1. WAL mode + persistent connection pool
   SQLite in WAL (Write-Ahead Log) mode allows concurrent reads while a write
   is in progress. We keep a small pool of pre-opened connections instead of
   opening/closing one per query.

2. Thread executor for all DB calls
   SQLite is synchronous. Running it directly in the async event loop blocks
   discord.py from processing heartbeats, messages, and interactions.
   Every public function here is async and offloads work to a thread pool
   via asyncio.to_thread(), keeping the event loop free.

3. TTL cache for read-heavy queries
   Leaderboards and server-stats don't change on every call. We cache their
   results for a configurable number of seconds and serve the cached version
   instantly, only hitting the DB when the cache expires.

4. Single-query server stats
   All five server-stat aggregates run in one SQL query instead of five.

5. Batched nightly notifications
   Streak-loss messages are sent concurrently with asyncio.gather(), not
   serially one by one.
"""

import asyncio
import datetime
import logging
import os
import queue
import sqlite3
import threading
import time
from typing import Optional

from core.config import config

log = logging.getLogger("SF-BOT.db")


# ══════════════════════════════════════════════════════════════════════════════
#  Connection pool
# ══════════════════════════════════════════════════════════════════════════════

_POOL_SIZE = 4  # tune to your server's CPU count; 4 is plenty for a Discord bot


class _ConnectionPool:
    """
    Thread-safe pool of persistent SQLite connections.
    Each connection is configured once (WAL, foreign keys, busy timeout)
    and reused across queries instead of being opened/closed every time.
    """

    def __init__(self, db_path: str, size: int) -> None:
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=size)
        for _ in range(size):
            conn = self._make_connection(db_path)
            self._pool.put(conn)

    @staticmethod
    def _make_connection(db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL mode: readers don't block writers and vice-versa
        conn.execute("PRAGMA journal_mode=WAL")
        # How long to wait for a lock before raising (ms)
        conn.execute("PRAGMA busy_timeout=5000")
        # Keep pages in memory between queries
        conn.execute("PRAGMA cache_size=-8000")  # ~8 MB
        conn.execute("PRAGMA synchronous=NORMAL")  # safe + faster than FULL
        return conn

    def acquire(self) -> sqlite3.Connection:
        return self._pool.get()

    def release(self, conn: sqlite3.Connection) -> None:
        self._pool.put(conn)

    class _Ctx:
        def __init__(self, pool: "_ConnectionPool") -> None:
            self._pool = pool
            self._conn: Optional[sqlite3.Connection] = None

        def __enter__(self) -> sqlite3.Connection:
            self._conn = self._pool.acquire()
            return self._conn

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            if self._conn:
                if exc_type:
                    self._conn.rollback()
                else:
                    self._conn.commit()
                self._pool.release(self._conn)

    def ctx(self) -> "_Ctx":
        return self._Ctx(self)


_pool: Optional[_ConnectionPool] = None


def _get_pool() -> _ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _pool


# ══════════════════════════════════════════════════════════════════════════════
#  TTL cache
# ══════════════════════════════════════════════════════════════════════════════


class _TTLCache:
    """
    Dead-simple in-memory cache with per-key TTL.
    Thread-safe via a lock. Serves stale reads instantly; DB only hit on expiry.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[object, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[bool, object]:
        with self._lock:
            entry = self._store.get(key)
            if entry and time.monotonic() < entry[1]:
                return True, entry[0]
            return False, None

    def set(self, key: str, value: object, ttl: float) -> None:
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._store.pop(k, None)


_cache = _TTLCache()

# Cache TTLs (seconds) — tune freely
_TTL_LEADERBOARD = 60  # leaderboards refresh every minute
_TTL_SERVER_STATS = 120  # server stats refresh every 2 minutes
_TTL_TOP_STREAK = 30  # #1 streak check refreshes every 30s


# ══════════════════════════════════════════════════════════════════════════════
#  Schema & init
# ══════════════════════════════════════════════════════════════════════════════


def _init_schema(conn: sqlite3.Connection) -> None:
    # Step 1 — create table (no-op if already exists)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_streaks (
            user_id             INTEGER PRIMARY KEY,
            username            TEXT    NOT NULL,
            streak_days         INTEGER NOT NULL DEFAULT 0,
            best_streak         INTEGER NOT NULL DEFAULT 0,
            last_post_date      TEXT,
            score               INTEGER NOT NULL DEFAULT 0,
            weekly_score        INTEGER NOT NULL DEFAULT 0,
            monthly_score       INTEGER NOT NULL DEFAULT 0,
            week_start_date     TEXT,
            month_start_date    TEXT
        )
    """)

    # Step 2 — migrations BEFORE indexes
    # Columns must exist before they can be indexed.
    # This is what fixes the crash on existing databases.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(user_streaks)")}
    migrations = {
        "score": "INTEGER NOT NULL DEFAULT 0",
        "best_streak": "INTEGER NOT NULL DEFAULT 0",
        "weekly_score": "INTEGER NOT NULL DEFAULT 0",
        "monthly_score": "INTEGER NOT NULL DEFAULT 0",
        "week_start_date": "TEXT",
        "month_start_date": "TEXT",
    }
    for col, definition in migrations.items():
        if col not in existing:
            conn.execute(
                f"ALTER TABLE user_streaks ADD COLUMN {col} {definition}"
            )
            log.info("Migration: added column '%s'.", col)

    # Step 3 — indexes (IF NOT EXISTS makes these safe to run every startup)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_score       ON user_streaks(score)       WHERE score > 0"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_streak_days ON user_streaks(streak_days) WHERE streak_days > 0"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_weekly      ON user_streaks(week_start_date,  weekly_score)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_monthly     ON user_streaks(month_start_date, monthly_score)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_last_post   ON user_streaks(last_post_date)"
    )

    conn.commit()


def init_db() -> None:
    global _pool
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    # Create pool — also runs schema init on first connection
    _pool = _ConnectionPool(config.DB_PATH, _POOL_SIZE)
    with _pool.ctx() as conn:
        _init_schema(conn)
    log.info(
        "Database ready → %s  (pool=%d, WAL mode)", config.DB_PATH, _POOL_SIZE
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Period helpers
# ══════════════════════════════════════════════════════════════════════════════


def _week_start() -> str:
    today = datetime.date.today()
    return (today - datetime.timedelta(days=today.weekday())).isoformat()


def _month_start() -> str:
    return datetime.date.today().replace(day=1).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
#  Async wrappers — everything the cogs call
# ══════════════════════════════════════════════════════════════════════════════
#
# Pattern: define a plain sync function (_fn), then wrap it with
# asyncio.to_thread() so it runs in a thread pool and never blocks the loop.

# ── record_post ───────────────────────────────────────────────────────────────


def _record_post_sync(
    user_id: int, username: str
) -> tuple[int, int, bool, int | None]:
    today = datetime.date.today()
    today_str = today.isoformat()
    week_start = _week_start()
    month_start = _month_start()

    with _get_pool().ctx() as conn:
        row = conn.execute(
            """
            SELECT streak_days, best_streak, last_post_date, score,
                   weekly_score, monthly_score, week_start_date, month_start_date
            FROM user_streaks WHERE user_id = ?
        """,
            (user_id,),
        ).fetchone()

        if row:
            streak_days = row["streak_days"]
            best_streak = row["best_streak"]
            score = row["score"]
            last_post = row["last_post_date"]
            weekly_score = row["weekly_score"]
            monthly_score = row["monthly_score"]
            prev_week = row["week_start_date"]
            prev_month = row["month_start_date"]

            if last_post == today_str:
                return streak_days, score, True, None

            if last_post:
                delta = (today - datetime.date.fromisoformat(last_post)).days
                streak_days = streak_days + 1 if delta == 1 else 1
            else:
                streak_days = 1

            new_score = score + config.POINTS_PER_POST
            new_best_streak = max(best_streak, streak_days)
            new_weekly = (
                config.POINTS_PER_POST
                if prev_week != week_start
                else weekly_score + config.POINTS_PER_POST
            )
            new_monthly = (
                config.POINTS_PER_POST
                if prev_month != month_start
                else monthly_score + config.POINTS_PER_POST
            )
        else:
            streak_days = 1
            new_best_streak = 1
            new_score = config.POINTS_PER_POST
            new_weekly = config.POINTS_PER_POST
            new_monthly = config.POINTS_PER_POST

        milestone = streak_days if streak_days in config.MILESTONES else None

        conn.execute(
            """
            INSERT INTO user_streaks
                (user_id, username, streak_days, best_streak, last_post_date,
                 score, weekly_score, monthly_score, week_start_date, month_start_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username         = excluded.username,
                streak_days      = excluded.streak_days,
                best_streak      = excluded.best_streak,
                last_post_date   = excluded.last_post_date,
                score            = excluded.score,
                weekly_score     = excluded.weekly_score,
                monthly_score    = excluded.monthly_score,
                week_start_date  = excluded.week_start_date,
                month_start_date = excluded.month_start_date
        """,
            (
                user_id,
                username,
                streak_days,
                new_best_streak,
                today_str,
                new_score,
                new_weekly,
                new_monthly,
                week_start,
                month_start,
            ),
        )

    # Invalidate caches affected by this write
    _cache.invalidate(
        "leaderboard_alltime",
        "leaderboard_streak",
        "leaderboard_weekly",
        "leaderboard_monthly",
        "server_stats",
        "top_streak",
    )

    return streak_days, new_score, False, milestone


async def record_post(
    user_id: int, username: str
) -> tuple[int, int, bool, int | None]:
    return await asyncio.to_thread(_record_post_sync, user_id, username)


# ── get_user ──────────────────────────────────────────────────────────────────


def _get_user_sync(user_id: int) -> Optional[sqlite3.Row]:
    with _get_pool().ctx() as conn:
        return conn.execute(
            """
            SELECT streak_days, best_streak, last_post_date, score,
                   weekly_score, monthly_score
            FROM user_streaks WHERE user_id = ?
        """,
            (user_id,),
        ).fetchone()


async def get_user(user_id: int) -> Optional[sqlite3.Row]:
    return await asyncio.to_thread(_get_user_sync, user_id)


# ── leaderboards (cached) ─────────────────────────────────────────────────────


def _leaderboard_alltime_sync(limit: int) -> list:
    hit, data = _cache.get("leaderboard_alltime")
    if hit:
        return data
    with _get_pool().ctx() as conn:
        rows = conn.execute(
            """
            SELECT username, score, streak_days, best_streak
            FROM user_streaks WHERE score > 0
            ORDER BY score DESC LIMIT ?
        """,
            (limit,),
        ).fetchall()
    result = [dict(r) for r in rows]
    _cache.set("leaderboard_alltime", result, _TTL_LEADERBOARD)
    return result


async def get_leaderboard_alltime(limit: int = 10) -> list:
    return await asyncio.to_thread(_leaderboard_alltime_sync, limit)


def _leaderboard_streak_sync(limit: int) -> list:
    hit, data = _cache.get("leaderboard_streak")
    if hit:
        return data
    with _get_pool().ctx() as conn:
        rows = conn.execute(
            """
            SELECT username, streak_days, score, best_streak
            FROM user_streaks WHERE streak_days > 0
            ORDER BY streak_days DESC LIMIT ?
        """,
            (limit,),
        ).fetchall()
    result = [dict(r) for r in rows]
    _cache.set("leaderboard_streak", result, _TTL_LEADERBOARD)
    return result


async def get_leaderboard_streak(limit: int = 10) -> list:
    return await asyncio.to_thread(_leaderboard_streak_sync, limit)


def _leaderboard_weekly_sync(limit: int) -> list:
    hit, data = _cache.get("leaderboard_weekly")
    if hit:
        return data
    with _get_pool().ctx() as conn:
        rows = conn.execute(
            """
            SELECT username, weekly_score, streak_days
            FROM user_streaks
            WHERE week_start_date = ? AND weekly_score > 0
            ORDER BY weekly_score DESC LIMIT ?
        """,
            (_week_start(), limit),
        ).fetchall()
    result = [dict(r) for r in rows]
    _cache.set("leaderboard_weekly", result, _TTL_LEADERBOARD)
    return result


async def get_leaderboard_weekly(limit: int = 10) -> list:
    return await asyncio.to_thread(_leaderboard_weekly_sync, limit)


def _leaderboard_monthly_sync(limit: int) -> list:
    hit, data = _cache.get("leaderboard_monthly")
    if hit:
        return data
    with _get_pool().ctx() as conn:
        rows = conn.execute(
            """
            SELECT username, monthly_score, streak_days
            FROM user_streaks
            WHERE month_start_date = ? AND monthly_score > 0
            ORDER BY monthly_score DESC LIMIT ?
        """,
            (_month_start(), limit),
        ).fetchall()
    result = [dict(r) for r in rows]
    _cache.set("leaderboard_monthly", result, _TTL_LEADERBOARD)
    return result


async def get_leaderboard_monthly(limit: int = 10) -> list:
    return await asyncio.to_thread(_leaderboard_monthly_sync, limit)


# ── server stats (single query, cached) ───────────────────────────────────────


def _server_stats_sync() -> dict:
    hit, data = _cache.get("server_stats")
    if hit:
        return data

    today_str = datetime.date.today().isoformat()
    with _get_pool().ctx() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                                          AS total_users,
                SUM(CASE WHEN streak_days > 0 THEN 1 ELSE 0 END) AS active_streakers,
                MAX(streak_days)                                  AS highest_streak,
                SUM(CASE WHEN last_post_date = ? THEN 1 ELSE 0 END) AS posted_today,
                COALESCE(SUM(score), 0)                           AS total_score
            FROM user_streaks
        """,
            (today_str,),
        ).fetchone()

    total_users = row["total_users"] or 0
    active_streakers = row["active_streakers"] or 0
    highest_streak = row["highest_streak"] or 0
    posted_today = row["posted_today"] or 0
    total_checkins = int((row["total_score"] or 0) / config.POINTS_PER_POST)
    consistency = round(
        (posted_today / total_users * 100) if total_users else 0
    )

    result = {
        "total_checkins": total_checkins,
        "active_streakers": active_streakers,
        "highest_streak": highest_streak,
        "consistency_pct": consistency,
    }
    _cache.set("server_stats", result, _TTL_SERVER_STATS)
    return result


async def get_server_stats() -> dict:
    return await asyncio.to_thread(_server_stats_sync)


# ── top streak user (cached) ──────────────────────────────────────────────────


def _top_streak_user_sync() -> Optional[dict]:
    hit, data = _cache.get("top_streak")
    if hit:
        return data
    with _get_pool().ctx() as conn:
        row = conn.execute("""
            SELECT user_id, username, streak_days
            FROM user_streaks WHERE streak_days > 0
            ORDER BY streak_days DESC LIMIT 1
        """).fetchone()
    result = dict(row) if row else None
    _cache.set("top_streak", result, _TTL_TOP_STREAK)
    return result


async def get_top_streak_user() -> Optional[dict]:
    return await asyncio.to_thread(_top_streak_user_sync)


# ── nightly expiry ────────────────────────────────────────────────────────────


def _expire_old_streaks_sync() -> list[tuple[int, str, int]]:
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    with _get_pool().ctx() as conn:
        victims = conn.execute(
            """
            SELECT user_id, username, streak_days
            FROM user_streaks WHERE last_post_date < ? AND streak_days > 0
        """,
            (yesterday,),
        ).fetchall()
        conn.execute(
            """
            UPDATE user_streaks SET streak_days = 0
            WHERE last_post_date < ? AND streak_days > 0
        """,
            (yesterday,),
        )
    _cache.invalidate("leaderboard_streak", "server_stats", "top_streak")
    return [(r["user_id"], r["username"], r["streak_days"]) for r in victims]


async def expire_old_streaks() -> list[tuple[int, str, int]]:
    return await asyncio.to_thread(_expire_old_streaks_sync)


# ── admin ─────────────────────────────────────────────────────────────────────


def _admin_set_score_sync(user_id: int, username: str, new_score: int) -> None:
    with _get_pool().ctx() as conn:
        conn.execute(
            """
            INSERT INTO user_streaks (user_id, username, score) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, score = excluded.score
        """,
            (user_id, username, new_score),
        )
    _cache.invalidate("leaderboard_alltime", "server_stats")


async def admin_set_score(user_id: int, username: str, new_score: int) -> None:
    await asyncio.to_thread(_admin_set_score_sync, user_id, username, new_score)


def _admin_add_score_sync(user_id: int, username: str, points: int) -> int:
    with _get_pool().ctx() as conn:
        row = conn.execute(
            "SELECT score FROM user_streaks WHERE user_id = ?", (user_id,)
        ).fetchone()
        new_score = (row["score"] if row else 0) + points
        conn.execute(
            """
            INSERT INTO user_streaks (user_id, username, score) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, score = excluded.score
        """,
            (user_id, username, new_score),
        )
    _cache.invalidate("leaderboard_alltime", "server_stats")
    return new_score


async def admin_add_score(user_id: int, username: str, points: int) -> int:
    return await asyncio.to_thread(
        _admin_add_score_sync, user_id, username, points
    )


def _admin_reset_score_sync(user_id: int) -> None:
    with _get_pool().ctx() as conn:
        conn.execute(
            "UPDATE user_streaks SET score = 0 WHERE user_id = ?", (user_id,)
        )
    _cache.invalidate("leaderboard_alltime", "server_stats")


async def admin_reset_score(user_id: int) -> None:
    await asyncio.to_thread(_admin_reset_score_sync, user_id)


def _admin_reset_streak_sync(user_id: int) -> None:
    with _get_pool().ctx() as conn:
        conn.execute(
            "UPDATE user_streaks SET streak_days = 0 WHERE user_id = ?",
            (user_id,),
        )
    _cache.invalidate("leaderboard_streak", "top_streak", "server_stats")


async def admin_reset_streak(user_id: int) -> None:
    await asyncio.to_thread(_admin_reset_streak_sync, user_id)
