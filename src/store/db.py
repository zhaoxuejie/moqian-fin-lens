from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from store.migrations import MIGRATIONS, SCHEMA_VERSION_DDL


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Database:
    """SQLite 访问层：建库、迁移、连接管理。

    v1.0 单实例（ADR-003 / ADR-004）。解析任务在独立线程里写库，
    因此每个线程持有自己的连接（WAL 支持一写多读），写操作再加进程内锁。
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.write_lock = threading.RLock()
        self._closed = False
        self._main = self._new_connection()

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("database closed")
        if threading.current_thread() is threading.main_thread():
            return self._main
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._new_connection()
            self._local.conn = conn
        return conn

    def migrate(self) -> int:
        """幂等迁移：返回本次实际应用的版本数。"""
        conn = self._main
        conn.execute(SCHEMA_VERSION_DDL)
        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_version")}
        applied_now = 0
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, _now()),
            )
            conn.commit()
            applied_now += 1
        return applied_now

    def table_names(self) -> list[str]:
        rows = self._main.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    def schema_versions(self) -> list[int]:
        rows = self._main.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        return [row["version"] for row in rows]

    def close(self) -> None:
        self._closed = True
        self._main.close()
