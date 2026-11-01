from __future__ import annotations

import time
from pathlib import Path

from dashboard.persistence import filing_to_dict, filing_from_dict
from dashboard.session import SessionData
from store.db import Database


class SessionRepository:
    """会话读写：session + filing 两张表，filing.snapshot 存完整 JSON 快照。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, session: SessionData) -> None:
        with self.db.write_lock:
            conn = self.db.conn
            conn.execute(
                "INSERT INTO session (id, company_name, stock_code, status, created_at) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET company_name=excluded.company_name, stock_code=excluded.stock_code,"
                " status=excluded.status, created_at=excluded.created_at",
                (session.session_id, session.company_name, session.stock_code, "done", session.created_at),
            )
            for filing in session.filings:
                conn.execute(
                    "INSERT INTO filing (id, session_id, report_type, period, pages, status, parsed_at, created_at, snapshot)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(id) DO UPDATE SET session_id=excluded.session_id, period=excluded.period,"
                    " pages=excluded.pages, status=excluded.status, snapshot=excluded.snapshot",
                    (
                        filing.filing_id,
                        session.session_id,
                        "annual",
                        filing.period,
                        filing.pages,
                        "done",
                        session.created_at,
                        session.created_at,
                        _dumps(filing),
                    ),
                )
            conn.commit()

    def load(self, session_id: str) -> SessionData | None:
        conn = self.db.conn
        row = conn.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        filings = conn.execute(
            "SELECT snapshot FROM filing WHERE session_id = ? AND snapshot IS NOT NULL ORDER BY period",
            (session_id,),
        ).fetchall()
        return SessionData(
            session_id=row["id"],
            company_name=row["company_name"] or "",
            stock_code=row["stock_code"] or "",
            created_at=row["created_at"] or "",
            filings=[filing_from_dict(_loads(item["snapshot"])) for item in filings],
        )

    def load_all(self) -> list[SessionData]:
        rows = self.db.conn.execute("SELECT id FROM session ORDER BY created_at").fetchall()
        sessions = []
        for row in rows:
            session = self.load(row["id"])
            if session is not None:
                sessions.append(session)
        return sessions

    def delete(self, session_id: str) -> bool:
        conn = self.db.conn
        cursor = conn.execute("DELETE FROM session WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0

    def count_filings(self, session_id: str) -> int:
        row = self.db.conn.execute(
            "SELECT COUNT(*) AS n FROM filing WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row["n"]) if row else 0


def cleanup_temp_files(tmp_dir: Path, max_age_seconds: int = 24 * 3600) -> list[str]:
    """删除超过保留期的上传原件；返回被删除的文件名。"""
    removed: list[str] = []
    if not tmp_dir.exists():
        return removed
    now = time.time()
    for path in tmp_dir.glob("*.pdf"):
        try:
            if now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
                removed.append(path.name)
        except OSError:
            continue
    return removed


def _dumps(filing) -> str:
    import json

    return json.dumps(filing_to_dict(filing), ensure_ascii=False)


def _loads(text: str):
    import json

    return json.loads(text)
