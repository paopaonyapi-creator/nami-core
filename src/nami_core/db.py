"""Database connection pool for Nami Core.

Uses psycopg3 for PostgreSQL access. Connection details
are loaded from /etc/nami-harness/postgres_password.

Also provides async SQLite pool for audit/analytics DBs.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger("nami_core.db")

from .secrets import get_db_connection_string


def get_connection(dbname: str = "glodbyproza"):
    """Get a raw psycopg connection to the specified database.

    Caller is responsible for closing the connection.
    """
    try:
        import psycopg
    except ImportError:
        raise ImportError("psycopg is required for database access. Install with: pip install psycopg[binary]")

    conn_string = get_db_connection_string(dbname)
    return psycopg.connect(conn_string)


@contextmanager
def db_session(dbname: str = "glodbyproza") -> Generator:
    """Context manager that yields a connection and auto-commits/closes.

    Usage:
        with db_session("glodbyproza") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print(cur.fetchone())
    """
    conn = get_connection(dbname)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── SQLite async pool ──

SQLITE_DB_PATH = os.environ.get("NAMI_DB_PATH", "/tmp/nami_audit.db")
_sqlite_pool: Any = None


async def get_sqlite_pool() -> Any:
    """Get or create the async SQLite connection pool."""
    global _sqlite_pool
    if _sqlite_pool is not None:
        return _sqlite_pool

    try:
        import aiosqlite

        _sqlite_pool = await aiosqlite.connect(SQLITE_DB_PATH)
        _sqlite_pool.row_factory = aiosqlite.Row
        await _sqlite_pool.execute("PRAGMA journal_mode=WAL")
        await _sqlite_pool.execute("PRAGMA busy_timeout=5000")
        logger.info("SQLite pool connected: %s", SQLITE_DB_PATH)
        return _sqlite_pool
    except ImportError:
        logger.warning("aiosqlite not available, falling back to sync sqlite3")
        return None
    except Exception as exc:
        logger.warning("SQLite pool failed: %s", exc)
        return None


async def sqlite_execute(query: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    pool = await get_sqlite_pool()
    if pool is None:
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    async with pool.execute(query, params) as cur:
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def sqlite_execute_write(query: str, params: tuple = ()) -> None:
    """Execute a write query (INSERT/UPDATE/DELETE)."""
    pool = await get_sqlite_pool()
    if pool is None:
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.execute(query, params)
        conn.commit()
        conn.close()
        return

    await pool.execute(query, params)
    await pool.commit()


async def sqlite_close() -> None:
    """Close the SQLite pool."""
    global _sqlite_pool
    if _sqlite_pool:
        try:
            await _sqlite_pool.close()
        except Exception:
            pass
        _sqlite_pool = None


def sqlite_stats() -> dict[str, Any]:
    """Get SQLite pool statistics."""
    return {
        "db_path": SQLITE_DB_PATH,
        "connected": _sqlite_pool is not None,
        "backend": "aiosqlite" if _sqlite_pool is not None else "sqlite3",
    }
