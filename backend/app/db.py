"""Conexão PostgreSQL + migrador SQL simples (tabela schema_migrations)."""
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool  # type: ignore

from . import config

_lock = threading.Lock()
_pool: Optional[ConnectionPool] = None
_embedded = None
_uri: Optional[str] = None


def database_uri() -> str:
    """DATABASE_URL explícita, ou PostgreSQL 16 embutido (pgserver) em dev/test."""
    global _embedded, _uri
    if _uri:
        return _uri
    if config.DATABASE_URL:
        _uri = config.DATABASE_URL
    else:
        import pgserver  # dependência só de desenvolvimento
        config.PGDATA_DIR.mkdir(parents=True, exist_ok=True)
        _embedded = pgserver.get_server(str(config.PGDATA_DIR), cleanup_mode=None)
        _uri = _embedded.get_uri()
    return _uri


def pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ConnectionPool(database_uri(), min_size=1, max_size=10,
                                   kwargs={"row_factory": dict_row, "autocommit": False}, open=True)
    return _pool


@contextmanager
def tx():
    with pool().connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def q(sql: str, params: Any = None) -> list:
    with tx() as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if cur.description else []


def q1(sql: str, params: Any = None) -> Optional[dict]:
    rows = q(sql, params)
    return rows[0] if rows else None


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def migrate(conn: Optional[psycopg.Connection] = None) -> list:
    applied = []
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        done = {r["name"] for r in c.execute("SELECT name FROM schema_migrations").fetchall()}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            c.execute(f.read_text(encoding="utf-8"))
            c.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (f.name,))
            applied.append(f.name)
    return applied


def reset_schema() -> None:
    """Somente test/dev: apaga e recria o schema public."""
    assert config.ENV in ("dev", "test"), "reset_schema bloqueado fora de dev/test"
    with tx() as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
