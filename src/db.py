"""SQLite storage for check results and prompts."""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Default DB path: ./data/aicheck.db (relative to cwd)
def _get_db_path() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    if url:
        return url
    Path("data").mkdir(exist_ok=True)
    return "data/aicheck.db"


def _connection() -> sqlite3.Connection:
    path = _get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = _connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                detected_language TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                assessment_json TEXT,
                file_name TEXT
            );
            CREATE TABLE IF NOT EXISTS check_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                file_path TEXT NOT NULL,
                file_name TEXT,
                detected_language TEXT,
                risk_level TEXT,
                result_id INTEGER REFERENCES check_results(id),
                error_message TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def insert_check_result(
    detected_language: str,
    risk_level: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    assessment: dict,
    file_name: str | None = None,
) -> int:
    """Insert a check result and return its id."""
    conn = _connection()
    try:
        cur = conn.execute(
            """INSERT INTO check_results (
                created_at, detected_language, risk_level,
                prompt_tokens, completion_tokens, total_tokens,
                assessment_json, file_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat() + "Z",
                detected_language,
                risk_level,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                json.dumps(assessment, ensure_ascii=False),
                file_name,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def create_task(file_path: str, file_name: str | None = None) -> int:
    """Create a pending check task. Returns task id. Caller must save file to file_path."""
    conn = _connection()
    try:
        now = datetime.utcnow().isoformat() + "Z"
        cur = conn.execute(
            """INSERT INTO check_tasks (created_at, status, file_path, file_name)
               VALUES (?, 'pending', ?, ?)""",
            (now, file_path, file_name or ""),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def claim_next_pending_task() -> int | None:
    """Atomically claim one pending task (set status to in_progress). Returns task id or None."""
    conn = _connection()
    try:
        row = conn.execute(
            "SELECT id FROM check_tasks WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        task_id = row["id"]
        cur = conn.execute(
            "UPDATE check_tasks SET status = 'in_progress', updated_at = ? WHERE id = ? AND status = 'pending'",
            (datetime.utcnow().isoformat() + "Z", task_id),
        )
        conn.commit()
        if cur.rowcount != 1:
            return None
        return task_id
    finally:
        conn.close()


def get_task(task_id: int) -> dict[str, Any] | None:
    """Get task by id."""
    conn = _connection()
    try:
        row = conn.execute("SELECT * FROM check_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_task_completed(
    task_id: int,
    result_id: int,
    detected_language: str,
    risk_level: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    """Mark task as completed and link to check_results."""
    conn = _connection()
    now = datetime.utcnow().isoformat() + "Z"
    try:
        conn.execute(
            """UPDATE check_tasks SET status = 'completed', result_id = ?,
               detected_language = ?, risk_level = ?, prompt_tokens = ?, completion_tokens = ?, total_tokens = ?, updated_at = ?
               WHERE id = ?""",
            (result_id, detected_language, risk_level, prompt_tokens, completion_tokens, total_tokens, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_task_error(task_id: int, error_message: str) -> None:
    """Mark task as error."""
    conn = _connection()
    now = datetime.utcnow().isoformat() + "Z"
    try:
        conn.execute(
            "UPDATE check_tasks SET status = 'error', error_message = ?, updated_at = ? WHERE id = ?",
            (error_message[:2000] if error_message else "", now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_tasks(limit: int = 100, status_filter: str | None = None) -> list[dict[str, Any]]:
    """List check tasks (all or by status). Most recent first."""
    conn = _connection()
    try:
        if status_filter:
            rows = conn.execute(
                """SELECT id, created_at, status, file_name, detected_language, risk_level,
                          result_id, error_message, total_tokens, updated_at
                   FROM check_tasks WHERE status = ? ORDER BY id DESC LIMIT ?""",
                (status_filter, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, created_at, status, file_name, detected_language, risk_level,
                          result_id, error_message, total_tokens, updated_at
                   FROM check_tasks ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_check_results(limit: int = 100) -> list[dict[str, Any]]:
    """List recent check results (id, created_at, language, risk, tokens)."""
    conn = _connection()
    try:
        rows = conn.execute(
            """SELECT id, created_at, detected_language, risk_level,
                      prompt_tokens, completion_tokens, total_tokens, file_name
               FROM check_results ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_check_result(result_id: int) -> dict[str, Any] | None:
    """Get full check result by id (including assessment_json)."""
    conn = _connection()
    try:
        row = conn.execute(
            "SELECT * FROM check_results WHERE id = ?", (result_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("assessment_json"):
            d["assessment"] = json.loads(d["assessment_json"])
        return d
    finally:
        conn.close()


def get_prompts() -> dict[str, str] | None:
    """Get prompts from DB. Returns None if no prompts stored (use fallback)."""
    conn = _connection()
    try:
        rows = conn.execute(
            "SELECT key, content FROM prompts"
        ).fetchall()
        if not rows:
            return None
        return {r["key"]: r["content"] for r in rows}
    finally:
        conn.close()


def set_prompts(system_message: str, user_message_template: str) -> None:
    """Upsert system_message and user_message_template in prompts table."""
    conn = _connection()
    now = datetime.utcnow().isoformat() + "Z"
    try:
        conn.execute(
            """INSERT INTO prompts (key, content, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at""",
            ("system_message", system_message, now),
        )
        conn.execute(
            """INSERT INTO prompts (key, content, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at""",
            ("user_message_template", user_message_template, now),
        )
        conn.commit()
    finally:
        conn.close()


def seed_prompts_if_empty(system_message: str, user_message_template: str) -> None:
    """If prompts table is empty, insert default prompts."""
    if get_prompts() is not None:
        return
    set_prompts(system_message, user_message_template)


def get_stats() -> dict[str, Any]:
    """Aggregate stats: total checks, total tokens, counts by language."""
    conn = _connection()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_tokens), 0) AS tokens FROM check_results"
        ).fetchone()
        by_lang = conn.execute(
            """SELECT detected_language AS lang, COUNT(*) AS count
               FROM check_results GROUP BY detected_language"""
        ).fetchall()
        return {
            "total_checks": total["n"] or 0,
            "total_tokens": total["tokens"] or 0,
            "by_language": {r["lang"]: r["count"] for r in by_lang},
        }
    finally:
        conn.close()
