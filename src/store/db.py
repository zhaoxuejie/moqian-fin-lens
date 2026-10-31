from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from store.migrations import MIGRATIONS, SCHEMA_VERSION_DDL


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Database:
    """SQLite 访问层：建库、迁移、连接管理。

    v1.0 单实例单写队列（ADR-003 / ADR-004），因此这里不做连接池。
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def migrate(self) -> int:
        """幂等迁移：返回本次实际应用的版本数。"""
        conn = self._conn
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
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    def schema_versions(self) -> list[int]:
        rows = self._conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        return [row["version"] for row in rows]

    def close(self) -> None:
        self._conn.close()
