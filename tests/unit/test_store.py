from store.db import Database

EXPECTED_TABLES = [
    "anomaly",
    "cell",
    "check_result",
    "entry",
    "export_record",
    "filing",
    "job",
    "metric",
    "schema_version",
    "session",
]


def test_migrate_is_idempotent(tmp_path):
    db = Database(tmp_path / "app.db")
    try:
        assert db.migrate() == 1
        assert db.migrate() == 0
        assert db.schema_versions() == [1]
    finally:
        db.close()


def test_all_tables_exist(tmp_path):
    db = Database(tmp_path / "app.db")
    try:
        db.migrate()
        names = db.table_names()
        for table in EXPECTED_TABLES:
            assert table in names
    finally:
        db.close()


def test_pragmas_are_enabled(tmp_path):
    db = Database(tmp_path / "app.db")
    try:
        db.migrate()
        journal_mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = db.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert str(journal_mode).lower() == "wal"
        assert foreign_keys == 1
    finally:
        db.close()


def test_delete_session_cascades_to_filings(tmp_path):
    db = Database(tmp_path / "app.db")
    try:
        db.migrate()
        conn = db.conn
        conn.execute("INSERT INTO session (id, created_at) VALUES ('s1', '2026-01-01')")
        conn.execute("INSERT INTO filing (id, session_id, created_at) VALUES ('f1', 's1', '2026-01-01')")
        conn.commit()

        conn.execute("DELETE FROM session WHERE id = 's1'")
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM filing").fetchone()[0] == 0
    finally:
        db.close()


def test_in_memory_database_is_supported():
    db = Database(":memory:")
    try:
        assert db.migrate() == 1
        assert "entry" in db.table_names()
    finally:
        db.close()
