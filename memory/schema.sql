-- ============================================================================
-- bo_commander_memory.db  —  BO Commander Persistent Knowledge Base
-- SQLite schema reference.  Applied automatically by knowledge_base.py.
-- ============================================================================

-- ── INCIDENTS ─────────────────────────────────────────────────────────────
-- Every health issue detected or auto-fixed by any agent.
CREATE TABLE IF NOT EXISTS incidents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,           -- ISO timestamp
    kind        TEXT    NOT NULL,           -- issue type e.g. 'failed_report'
    object      TEXT    DEFAULT '',         -- affected object name / ID
    detail      TEXT    DEFAULT '',         -- detailed description
    severity    TEXT    DEFAULT 'ERROR',    -- CRITICAL | ERROR | WARNING | RESOLVED
    resolved    INTEGER DEFAULT 0,          -- 0=open, 1=resolved
    fix_used    TEXT    DEFAULT '',         -- which fix action was applied
    source      TEXT    DEFAULT 'agent'     -- 'agent' | 'user' | 'scheduler'
);
CREATE INDEX IF NOT EXISTS idx_incidents_ts   ON incidents(ts   DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_kind ON incidents(kind);

-- ── AI CONVERSATION CONTEXT ───────────────────────────────────────────────
-- Full MultiBOT chat history for persistent AI memory.
CREATE TABLE IF NOT EXISTS ai_context (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    role        TEXT    NOT NULL,           -- 'user' | 'assistant'
    content     TEXT    NOT NULL,
    session_id  TEXT    DEFAULT 'default'   -- for multi-session support
);
CREATE INDEX IF NOT EXISTS idx_ai_ts ON ai_context(ts DESC);

-- ── REMEDIATION PLAYBOOKS ─────────────────────────────────────────────────
-- Known fix procedures keyed by issue type.
-- Pre-seeded with 5 common BO issues, editable by user.
CREATE TABLE IF NOT EXISTS playbooks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_type    TEXT    NOT NULL UNIQUE,
    title         TEXT    NOT NULL,
    steps         TEXT    NOT NULL,         -- JSON: ["step1", "step2", ...]
    success_count INTEGER DEFAULT 0,        -- how many times fix succeeded
    created_ts    TEXT    NOT NULL,
    updated_ts    TEXT    NOT NULL
);

-- ── SERVER SNAPSHOTS ──────────────────────────────────────────────────────
-- Periodic server state for trend analysis and anomaly detection.
CREATE TABLE IF NOT EXISTS server_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL,
    server_id    TEXT    NOT NULL,
    server_name  TEXT    NOT NULL,
    status       TEXT    NOT NULL,          -- 'Running' | 'Stopped' | ...
    failures     INTEGER DEFAULT 0,
    cpu_pct      REAL    DEFAULT 0,
    mem_mb       REAL    DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_snap_ts   ON server_snapshots(ts DESC);
CREATE INDEX IF NOT EXISTS idx_snap_name ON server_snapshots(server_name);

-- ── AUTOMATION LOG ────────────────────────────────────────────────────────
-- Every action taken by the automation engine / scheduler.
CREATE TABLE IF NOT EXISTS automation_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    trigger TEXT    NOT NULL,               -- 'auto_heal' | 'scheduler' | 'rule'
    action  TEXT    NOT NULL,
    target  TEXT    DEFAULT '',
    result  TEXT    DEFAULT '',
    success INTEGER DEFAULT 0
);
