"""
memory/knowledge_base.py  —  BO Commander Persistent Knowledge Base  v2.0
=========================================================================
SQLite-backed memory for the multi-agent system:

  • Incidents   — every detected problem, timestamp, severity, resolution
  • Remediations — what fixed each type of problem
  • Server history — server state over time
  • AI memory   — conversation context + learned patterns
  • Playbooks   — known fix procedures per error pattern

Database: ~/.bo_commander/knowledge.db  (auto-created on first use)
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("KnowledgeBase")


# ─────────────────────────────────────────────────────────────────────────────
#  DB location
# ─────────────────────────────────────────────────────────────────────────────
def _db_path() -> Path:
    home = Path.home() / ".bo_commander"
    home.mkdir(exist_ok=True)
    return home / "knowledge.db"


# ─────────────────────────────────────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    severity    TEXT    NOT NULL DEFAULT 'warning',
    message     TEXT    NOT NULL,
    resolved    INTEGER NOT NULL DEFAULT 0,
    resolved_ts TEXT,
    resolution  TEXT,
    server      TEXT,
    extra_json  TEXT
);

CREATE TABLE IF NOT EXISTS remediations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    problem     TEXT    NOT NULL,
    fix_applied TEXT    NOT NULL,
    success     INTEGER NOT NULL DEFAULT 1,
    duration_s  REAL,
    extra_json  TEXT
);

CREATE TABLE IF NOT EXISTS server_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    server_name TEXT    NOT NULL,
    server_id   TEXT,
    status      TEXT    NOT NULL,
    cpu_pct     REAL,
    mem_pct     REAL,
    failures    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    session_id  TEXT,
    tags        TEXT
);

CREATE TABLE IF NOT EXISTS playbooks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    category    TEXT    NOT NULL,
    trigger     TEXT    NOT NULL,
    steps_json  TEXT    NOT NULL,
    success_count INTEGER DEFAULT 0,
    fail_count    INTEGER DEFAULT 0,
    last_used   TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_ts       ON incidents(ts);
CREATE INDEX IF NOT EXISTS idx_incidents_cat      ON incidents(category);
CREATE INDEX IF NOT EXISTS idx_server_history_ts  ON server_history(ts);
CREATE INDEX IF NOT EXISTS idx_ai_memory_session  ON ai_memory(session_id);
"""

# Built-in remediation playbooks
_DEFAULT_PLAYBOOKS = [
    {
        "name":     "cms_down",
        "category": "server",
        "trigger":  "CMS not responding|Central Management Server stopped",
        "steps":    [
            "Check port 6400 with: check port 6400",
            "Check Windows service: sc query BOEXI40CMS",
            "Read CMS log: show bo log",
            "Restart CMS service: sc start BOEXI40CMS",
            "Verify BO connection: system health"
        ]
    },
    {
        "name":     "tomcat_down",
        "category": "tomcat",
        "trigger":  "port 8080 closed|Tomcat not responding|CMC unreachable",
        "steps":    [
            "Check port 8080: check port 8080",
            "Read Tomcat log: show tomcat log",
            "Clear cache: clear cache",
            "Restart Tomcat: restart tomcat",
            "Verify: check port 8080"
        ]
    },
    {
        "name":     "failed_schedules",
        "category": "reports",
        "trigger":  "failed instances|schedule failure|report failed",
        "steps":    [
            "List failures: show failed reports",
            "Check server health: system health",
            "Check logs: show bo log",
            "Retry: retry failed",
            "Verify: show failed reports"
        ]
    },
    {
        "name":     "disk_full",
        "category": "disk",
        "trigger":  "disk.*9[0-9]%|disk critical|out of space",
        "steps":    [
            "Check disk: disk space",
            "Purge old instances (30 days): delete old instances",
            "Clear Tomcat cache: clear cache",
            "Check disk again: disk space"
        ]
    },
    {
        "name":     "high_memory",
        "category": "memory",
        "trigger":  "RAM.*8[0-9]%|high memory|java heap",
        "steps":    [
            "Check system: system health",
            "Check Java heap: show bo log",
            "Restart APS service if needed",
            "Purge old instances: delete old instances"
        ]
    },
    {
        "name":     "login_failure",
        "category": "auth",
        "trigger":  "authentication failed|login failed|FWB 00003",
        "steps":    [
            "Check CMS status: check port 6400",
            "Verify credentials in .env",
            "Check CMS log: show bo log",
            "Restart CMS service if needed"
        ]
    },
]


class KnowledgeBase:
    """
    Thread-safe persistent knowledge base using SQLite.

    Usage:
        from memory.knowledge_base import kb
        kb.record_incident("server", "CMS stopped", severity="critical")
        history = kb.get_incidents(hours=24)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._db   = str(_db_path())
        self._init_db()
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._lock:
                conn = self._conn()
                conn.executescript(_SCHEMA)
                conn.commit()
                # Insert default playbooks if missing
                for pb in _DEFAULT_PLAYBOOKS:
                    conn.execute(
                        "INSERT OR IGNORE INTO playbooks "
                        "(name, category, trigger, steps_json) VALUES (?,?,?,?)",
                        (pb["name"], pb["category"], pb["trigger"],
                         json.dumps(pb["steps"]))
                    )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"KB init error: {e}")

    # ── Incidents ─────────────────────────────────────────────────────────────

    def record_incident(self, category: str, message: str,
                        severity: str = "warning", server: str = "",
                        extra: dict = None) -> int:
        """Record a detected incident. Returns new incident ID."""
        try:
            with self._lock:
                conn = self._conn()
                cur = conn.execute(
                    "INSERT INTO incidents (ts, category, severity, message, server, extra_json) "
                    "VALUES (?,?,?,?,?,?)",
                    (datetime.now().isoformat(), category, severity, message,
                     server, json.dumps(extra or {}))
                )
                incident_id = cur.lastrowid
                conn.commit()
                conn.close()
                return incident_id
        except Exception as e:
            logger.error(f"record_incident: {e}")
            return -1

    def resolve_incident(self, incident_id: int, resolution: str):
        """Mark incident as resolved."""
        try:
            with self._lock:
                conn = self._conn()
                conn.execute(
                    "UPDATE incidents SET resolved=1, resolved_ts=?, resolution=? WHERE id=?",
                    (datetime.now().isoformat(), resolution, incident_id)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"resolve_incident: {e}")

    def get_incidents(self, hours: int = 24, category: str = None,
                      unresolved_only: bool = False) -> List[Dict]:
        """Get incidents from the last N hours."""
        try:
            since = (datetime.now() - timedelta(hours=hours)).isoformat()
            query = "SELECT * FROM incidents WHERE ts > ?"
            params: list = [since]
            if category:
                query += " AND category=?"
                params.append(category)
            if unresolved_only:
                query += " AND resolved=0"
            query += " ORDER BY ts DESC LIMIT 200"
            with self._lock:
                conn = self._conn()
                rows = [dict(r) for r in conn.execute(query, params).fetchall()]
                conn.close()
            return rows
        except Exception as e:
            logger.error(f"get_incidents: {e}")
            return []

    def get_incident_summary(self) -> Dict:
        """Quick stats: counts by severity and category."""
        try:
            with self._lock:
                conn = self._conn()
                since = (datetime.now() - timedelta(hours=24)).isoformat()
                rows = conn.execute(
                    "SELECT category, severity, COUNT(*) as cnt "
                    "FROM incidents WHERE ts > ? GROUP BY category, severity",
                    (since,)
                ).fetchall()
                conn.close()
            summary = {}
            for r in rows:
                summary.setdefault(r["category"], {})[r["severity"]] = r["cnt"]
            return summary
        except Exception as e:
            logger.error(f"get_incident_summary: {e}")
            return {}

    # ── Remediations ──────────────────────────────────────────────────────────

    def record_remediation(self, category: str, problem: str,
                           fix_applied: str = "", success: bool = True,
                           duration_s: float = 0.0):
        try:
            with self._lock:
                conn = self._conn()
                conn.execute(
                    "INSERT INTO remediations (ts, category, problem, fix_applied, success, duration_s) "
                    "VALUES (?,?,?,?,?,?)",
                    (datetime.now().isoformat(), category, problem,
                     fix_applied, int(success), duration_s)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"record_remediation: {e}")

    def get_remediations(self, category: str = None, limit: int = 50) -> List[Dict]:
        try:
            query  = "SELECT * FROM remediations"
            params: list = []
            if category:
                query += " WHERE category=?"
                params.append(category)
            query += " ORDER BY ts DESC LIMIT ?"
            params.append(limit)
            with self._lock:
                conn = self._conn()
                rows = [dict(r) for r in conn.execute(query, params).fetchall()]
                conn.close()
            return rows
        except Exception as e:
            logger.error(f"get_remediations: {e}")
            return []

    # ── Server history ────────────────────────────────────────────────────────

    def record_server_state(self, server_name: str, status: str,
                            server_id: str = "", cpu: float = 0,
                            mem: float = 0, failures: int = 0):
        try:
            with self._lock:
                conn = self._conn()
                conn.execute(
                    "INSERT INTO server_history "
                    "(ts, server_name, server_id, status, cpu_pct, mem_pct, failures) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (datetime.now().isoformat(), server_name, server_id,
                     status, cpu, mem, failures)
                )
                conn.commit()
                # Keep only last 10000 rows
                conn.execute(
                    "DELETE FROM server_history WHERE id NOT IN "
                    "(SELECT id FROM server_history ORDER BY ts DESC LIMIT 10000)"
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"record_server_state: {e}")

    def get_server_history(self, server_name: str = None,
                           hours: int = 24) -> List[Dict]:
        try:
            since  = (datetime.now() - timedelta(hours=hours)).isoformat()
            query  = "SELECT * FROM server_history WHERE ts > ?"
            params: list = [since]
            if server_name:
                query += " AND server_name LIKE ?"
                params.append(f"%{server_name}%")
            query += " ORDER BY ts DESC LIMIT 500"
            with self._lock:
                conn = self._conn()
                rows = [dict(r) for r in conn.execute(query, params).fetchall()]
                conn.close()
            return rows
        except Exception as e:
            logger.error(f"get_server_history: {e}")
            return []

    # ── AI Memory / Conversation context ─────────────────────────────────────

    def save_message(self, role: str, content: str,
                     session_id: str = None, tags: str = ""):
        try:
            sid = session_id or self._session_id
            with self._lock:
                conn = self._conn()
                conn.execute(
                    "INSERT INTO ai_memory (ts, role, content, session_id, tags) "
                    "VALUES (?,?,?,?,?)",
                    (datetime.now().isoformat(), role, content, sid, tags)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"save_message: {e}")

    def get_conversation(self, session_id: str = None,
                         limit: int = 20) -> List[Dict]:
        try:
            sid = session_id or self._session_id
            with self._lock:
                conn = self._conn()
                rows = [dict(r) for r in conn.execute(
                    "SELECT role, content FROM ai_memory WHERE session_id=? "
                    "ORDER BY ts DESC LIMIT ?",
                    (sid, limit)
                ).fetchall()]
                conn.close()
            rows.reverse()  # chronological order
            return rows
        except Exception as e:
            logger.error(f"get_conversation: {e}")
            return []

    # ── Playbooks ─────────────────────────────────────────────────────────────

    def get_playbook(self, category: str = None,
                     trigger_text: str = None) -> Optional[Dict]:
        """Find the best matching playbook."""
        try:
            with self._lock:
                conn = self._conn()
                if trigger_text:
                    rows = [dict(r) for r in conn.execute(
                        "SELECT * FROM playbooks", ()
                    ).fetchall()]
                    conn.close()
                    import re
                    for pb in rows:
                        if re.search(pb["trigger"], trigger_text, re.IGNORECASE):
                            pb["steps"] = json.loads(pb["steps_json"])
                            return pb
                    return None
                if category:
                    row = conn.execute(
                        "SELECT * FROM playbooks WHERE category=? ORDER BY success_count DESC LIMIT 1",
                        (category,)
                    ).fetchone()
                    conn.close()
                    if row:
                        pb = dict(row)
                        pb["steps"] = json.loads(pb["steps_json"])
                        return pb
                conn.close()
                return None
        except Exception as e:
            logger.error(f"get_playbook: {e}")
            return None

    def get_all_playbooks(self) -> List[Dict]:
        try:
            with self._lock:
                conn = self._conn()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM playbooks ORDER BY category, name"
                ).fetchall()]
                conn.close()
            for pb in rows:
                pb["steps"] = json.loads(pb["steps_json"])
            return rows
        except Exception as e:
            logger.error(f"get_all_playbooks: {e}")
            return []

    def update_playbook_stats(self, name: str, success: bool):
        col = "success_count" if success else "fail_count"
        try:
            with self._lock:
                conn = self._conn()
                conn.execute(
                    f"UPDATE playbooks SET {col}={col}+1, last_used=? WHERE name=?",
                    (datetime.now().isoformat(), name)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"update_playbook_stats: {e}")

    # ── Context summary for AI ────────────────────────────────────────────────

    def get_ai_context(self) -> str:
        """Build a compact context string for the AI prompt."""
        try:
            summary = self.get_incident_summary()
            recent  = self.get_incidents(hours=2, unresolved_only=True)
            parts   = []
            if summary:
                parts.append(f"Incidents (24h): {json.dumps(summary)}")
            if recent:
                parts.append(f"Active issues ({len(recent)}): " +
                             ", ".join(r["message"][:60] for r in recent[:3]))
            return " | ".join(parts) if parts else ""
        except Exception:
            return ""

    def get_stats(self) -> Dict:
        """Overall DB stats."""
        try:
            with self._lock:
                conn = self._conn()
                stats = {
                    "incidents":     conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
                    "remediations":  conn.execute("SELECT COUNT(*) FROM remediations").fetchone()[0],
                    "server_events": conn.execute("SELECT COUNT(*) FROM server_history").fetchone()[0],
                    "ai_messages":   conn.execute("SELECT COUNT(*) FROM ai_memory").fetchone()[0],
                    "playbooks":     conn.execute("SELECT COUNT(*) FROM playbooks").fetchone()[0],
                    "db_path":       self._db,
                }
                conn.close()
            return stats
        except Exception as e:
            logger.error(f"get_stats: {e}")
            return {}


# ─────────────────────────────────────────────────────────────────────────────
#  Singleton
# ─────────────────────────────────────────────────────────────────────────────
kb = KnowledgeBase()
