SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

# 版本 1：v1.0 的基础表（对应 docs/architecture.md §5）
# 说明：`check` 与 `export` 在 SQLite 中是关键字，表名取 check_result / export_record，
# 语义与架构文档一致，字段不变。
MIGRATION_001 = """
CREATE TABLE IF NOT EXISTS session (
    id           TEXT PRIMARY KEY,
    company_name TEXT,
    stock_code   TEXT,
    status       TEXT NOT NULL DEFAULT 'created',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filing (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    report_type   TEXT,
    period        TEXT,
    pages         INTEGER,
    status        TEXT NOT NULL DEFAULT 'queued',
    error_code    TEXT,
    audit_opinion TEXT,
    parsed_at     TEXT,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES session (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cell (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id  TEXT NOT NULL,
    page       INTEGER NOT NULL,
    table_kind TEXT,
    row_no     INTEGER,
    col_no     INTEGER,
    text       TEXT NOT NULL,
    bbox       TEXT,
    FOREIGN KEY (filing_id) REFERENCES filing (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entry (
    id             TEXT PRIMARY KEY,
    filing_id      TEXT NOT NULL,
    account_code   TEXT NOT NULL,
    value          REAL,
    unit           TEXT,
    page           INTEGER,
    snippet        TEXT,
    confidence     REAL,
    source         TEXT NOT NULL,
    missing_reason TEXT,
    FOREIGN KEY (filing_id) REFERENCES filing (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metric (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id      TEXT NOT NULL,
    code           TEXT NOT NULL,
    value          REAL,
    unit           TEXT,
    formula        TEXT,
    missing_reason TEXT,
    UNIQUE (filing_id, code),
    FOREIGN KEY (filing_id) REFERENCES filing (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS check_result (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id TEXT NOT NULL,
    rule      TEXT NOT NULL,
    passed    INTEGER NOT NULL,
    diff      REAL,
    detail    TEXT,
    FOREIGN KEY (filing_id) REFERENCES filing (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anomaly (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    rule_code  TEXT NOT NULL,
    title      TEXT NOT NULL,
    text       TEXT NOT NULL,
    evidence   TEXT,
    page_refs  TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES session (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS job (
    id         TEXT PRIMARY KEY,
    filing_id  TEXT NOT NULL,
    state      TEXT NOT NULL,
    progress   REAL NOT NULL DEFAULT 0,
    stage      TEXT,
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (filing_id) REFERENCES filing (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS export_record (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind       TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    FOREIGN KEY (session_id) REFERENCES session (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_filing_session ON filing (session_id);
CREATE INDEX IF NOT EXISTS idx_entry_filing   ON entry (filing_id);
CREATE INDEX IF NOT EXISTS idx_metric_filing  ON metric (filing_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_session ON anomaly (session_id);
CREATE INDEX IF NOT EXISTS idx_job_state      ON job (state);
"""

MIGRATIONS: list[tuple[int, str]] = [
    (1, MIGRATION_001),
]
