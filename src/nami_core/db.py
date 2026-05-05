"""Database connection pool for Nami Core.

Uses psycopg3 for PostgreSQL access. Connection details
are loaded from /etc/nami-harness/postgres_password.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

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
