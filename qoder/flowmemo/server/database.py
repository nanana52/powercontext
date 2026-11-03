"""SQLite database layer for FlowMemo.

Manages projects, notes, tasks, decisions, risks, and visitor sessions.
Each visitor gets an isolated session with its own data scope.
"""
from __future__ import annotations

import aiosqlite
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

DB_PATH = os.environ.get("FLOWMEMO_DB", str(Path(__file__).resolve().parent.parent / "data" / "flowmemo.db"))


async def _ensure_dir():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


async def get_db() -> aiosqlite.Connection:
    await _ensure_dir()
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS visitors (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (visitor_id) REFERENCES visitors(id)
            );
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'user',
                note_date TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                note_id TEXT,
                title TEXT NOT NULL,
                assignee TEXT DEFAULT '',
                due_date TEXT DEFAULT '',
                priority TEXT DEFAULT '中',
                status TEXT DEFAULT 'pending',
                source_line INTEGER,
                created_at REAL NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                note_id TEXT,
                content TEXT NOT NULL,
                source_line INTEGER,
                created_at REAL NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );
            CREATE TABLE IF NOT EXISTS risks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                note_id TEXT,
                content TEXT NOT NULL,
                source_line INTEGER,
                created_at REAL NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );
            CREATE TABLE IF NOT EXISTS memory_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                endpoint TEXT,
                request_body TEXT,
                response_body TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (visitor_id) REFERENCES visitors(id)
            );
        """)
        await db.commit()
    finally:
        await db.close()


async def get_or_create_visitor(visitor_id: Optional[str] = None) -> str:
    if visitor_id is None:
        visitor_id = str(uuid.uuid4())
    db = await get_db()
    try:
        now = time.time()
        existing = await db.execute("SELECT id FROM visitors WHERE id = ?", (visitor_id,))
        if await existing.fetchone():
            await db.execute("UPDATE visitors SET last_seen = ? WHERE id = ?", (now, visitor_id))
        else:
            await db.execute("INSERT INTO visitors (id, created_at, last_seen) VALUES (?, ?, ?)",
                             (visitor_id, now, now))
        await db.commit()
        return visitor_id
    finally:
        await db.close()


async def create_project(visitor_id: str, name: str) -> dict:
    project_id = str(uuid.uuid4())[:8]
    now = time.time()
    db = await get_db()
    try:
        await db.execute("INSERT INTO projects (id, visitor_id, name, created_at) VALUES (?, ?, ?, ?)",
                         (project_id, visitor_id, name, now))
        await db.commit()
        return {"id": project_id, "name": name, "created_at": now}
    finally:
        await db.close()


async def list_projects(visitor_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, created_at FROM projects WHERE visitor_id = ? ORDER BY created_at DESC",
            (visitor_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_project(visitor_id: str, project_id: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, created_at FROM projects WHERE id = ? AND visitor_id = ?",
            (project_id, visitor_id))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def add_note(project_id: str, title: str, content: str, source: str = "user", note_date: str = None) -> dict:
    note_id = str(uuid.uuid4())[:8]
    now = time.time()
    db = await get_db()
    try:
        existing = await db.execute("SELECT id FROM notes WHERE project_id = ? AND title = ?",
                                    (project_id, title))
        if await existing.fetchone():
            cursor = await db.execute("SELECT id, title, content, source, note_date, created_at FROM notes WHERE project_id = ? AND title = ?",
                                      (project_id, title))
            row = await cursor.fetchone()
            return dict(row)
        await db.execute(
            "INSERT INTO notes (id, project_id, title, content, source, note_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (note_id, project_id, title, content, source, note_date, now))
        await db.commit()
        return {"id": note_id, "title": title, "content": content, "source": source, "note_date": note_date, "created_at": now}
    finally:
        await db.close()


async def list_notes(project_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, content, source, note_date, created_at FROM notes WHERE project_id = ? ORDER BY created_at",
            (project_id,))
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def delete_note(note_id: str, project_id: str) -> bool:
    db = await get_db()
    try:
        await db.execute("DELETE FROM tasks WHERE note_id = ? AND project_id = ?", (note_id, project_id))
        await db.execute("DELETE FROM decisions WHERE note_id = ? AND project_id = ?", (note_id, project_id))
        await db.execute("DELETE FROM risks WHERE note_id = ? AND project_id = ?", (note_id, project_id))
        cursor = await db.execute("DELETE FROM notes WHERE id = ? AND project_id = ?", (note_id, project_id))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def add_task(project_id: str, note_id: str, title: str, assignee: str = "", due_date: str = "",
                   priority: str = "中", source_line: int = None) -> dict:
    db = await get_db()
    try:
        existing = await db.execute(
            "SELECT id FROM tasks WHERE project_id = ? AND note_id = ? AND title = ?",
            (project_id, note_id, title))
        if await existing.fetchone():
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND note_id = ? AND title = ?",
                (project_id, note_id, title))
            return dict(await cursor.fetchone())
        task_id = str(uuid.uuid4())[:8]
        now = time.time()
        await db.execute(
            "INSERT INTO tasks (id, project_id, note_id, title, assignee, due_date, priority, status, source_line, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (task_id, project_id, note_id, title, assignee, due_date, priority, source_line, now))
        await db.commit()
        return {"id": task_id, "project_id": project_id, "note_id": note_id, "title": title,
                "assignee": assignee, "due_date": due_date, "priority": priority, "status": "pending",
                "source_line": source_line, "created_at": now}
    finally:
        await db.close()


async def list_tasks(project_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT t.*, n.title as note_title FROM tasks t LEFT JOIN notes n ON t.note_id = n.id WHERE t.project_id = ? ORDER BY t.created_at",
            (project_id,))
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def update_task(task_id: str, project_id: str, **kwargs) -> Optional[dict]:
    allowed = {"title", "assignee", "due_date", "priority", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return None
    db = await get_db()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id, project_id]
        await db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ? AND project_id = ?", values)
        await db.commit()
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def add_decision(project_id: str, note_id: str, content: str, source_line: int = None) -> dict:
    db = await get_db()
    try:
        existing = await db.execute(
            "SELECT id FROM decisions WHERE project_id = ? AND note_id = ? AND content = ?",
            (project_id, note_id, content))
        if await existing.fetchone():
            cursor = await db.execute(
                "SELECT * FROM decisions WHERE project_id = ? AND note_id = ? AND content = ?",
                (project_id, note_id, content))
            return dict(await cursor.fetchone())
        decision_id = str(uuid.uuid4())[:8]
        now = time.time()
        await db.execute(
            "INSERT INTO decisions (id, project_id, note_id, content, source_line, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (decision_id, project_id, note_id, content, source_line, now))
        await db.commit()
        return {"id": decision_id, "project_id": project_id, "note_id": note_id,
                "content": content, "source_line": source_line, "created_at": now}
    finally:
        await db.close()


async def list_decisions(project_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT d.*, n.title as note_title FROM decisions d LEFT JOIN notes n ON d.note_id = n.id WHERE d.project_id = ? ORDER BY d.created_at",
            (project_id,))
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def add_risk(project_id: str, note_id: str, content: str, source_line: int = None) -> dict:
    db = await get_db()
    try:
        existing = await db.execute(
            "SELECT id FROM risks WHERE project_id = ? AND note_id = ? AND content = ?",
            (project_id, note_id, content))
        if await existing.fetchone():
            cursor = await db.execute(
                "SELECT * FROM risks WHERE project_id = ? AND note_id = ? AND content = ?",
                (project_id, note_id, content))
            return dict(await cursor.fetchone())
        risk_id = str(uuid.uuid4())[:8]
        now = time.time()
        await db.execute(
            "INSERT INTO risks (id, project_id, note_id, content, source_line, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (risk_id, project_id, note_id, content, source_line, now))
        await db.commit()
        return {"id": risk_id, "project_id": project_id, "note_id": note_id,
                "content": content, "source_line": source_line, "created_at": now}
    finally:
        await db.close()


async def list_risks(project_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT r.*, n.title as note_title FROM risks r LEFT JOIN notes n ON r.note_id = n.id WHERE r.project_id = ? ORDER BY r.created_at",
            (project_id,))
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def log_memory_action(visitor_id: str, action: str, endpoint: str, request_body: Any, response_body: Any, success: bool):
    db = await get_db()
    try:
        now = time.time()
        await db.execute(
            "INSERT INTO memory_log (visitor_id, action, endpoint, request_body, response_body, success, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (visitor_id, action, endpoint,
             json.dumps(request_body, ensure_ascii=False, default=str) if request_body else None,
             json.dumps(response_body, ensure_ascii=False, default=str) if response_body else None,
             1 if success else 0, now))
        await db.commit()
    finally:
        await db.close()


async def get_memory_log(visitor_id: str, limit: int = 10) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, action, endpoint, request_body, response_body, success, created_at FROM memory_log WHERE visitor_id = ? ORDER BY created_at DESC LIMIT ?",
            (visitor_id, limit))
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def get_stats(project_id: str) -> dict:
    db = await get_db()
    try:
        notes_count = await (await db.execute("SELECT COUNT(*) FROM notes WHERE project_id = ?", (project_id,))).fetchone()
        tasks = await (await db.execute("SELECT COUNT(*), SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) FROM tasks WHERE project_id = ?", (project_id,))).fetchone()
        risks_count = await (await db.execute("SELECT COUNT(*) FROM risks WHERE project_id = ?", (project_id,))).fetchone()
        return {
            "notes": notes_count[0] if notes_count[0] else 0,
            "tasks": tasks[0] if tasks[0] else 0,
            "done": tasks[1] if tasks[1] else 0,
            "risks": risks_count[0] if risks_count[0] else 0,
        }
    finally:
        await db.close()
