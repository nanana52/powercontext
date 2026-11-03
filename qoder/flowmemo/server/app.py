"""FlowMemo main server — FastAPI application.

Serves the static frontend and provides all API endpoints for:
- Visitor session management
- Project CRUD
- Note import/parsing
- Task management
- PowerContext memory operations
- Weekly report generation
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from .parser import parse_note_content
from .powercontext import get_client
from .report import generate_report

app = FastAPI(title="FlowMemo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

SESSION_COOKIE = "fm_sid"
SESSION_TTL = 86400 * 7
_sessions: dict[str, dict] = {}


def _get_session_id(request: Request) -> str:
    sid = request.cookies.get(SESSION_COOKIE)
    if sid and sid in _sessions:
        _sessions[sid]["last_seen"] = time.time()
        return sid
    sid = secrets.token_hex(16)
    _sessions[sid] = {"created": time.time(), "last_seen": time.time()}
    return sid


@app.on_event("startup")
async def startup():
    await db.init_db()


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "FlowMemo"}


# ── Visitor & Session ──

@app.post("/api/session")
async def create_session(request: Request, response: Response):
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    response.set_cookie(SESSION_COOKIE, sid, max_age=SESSION_TTL, httponly=True, samesite="lax")
    return {"visitor_id": visitor_id, "session_id": sid}


# ── Projects ──

@app.get("/api/projects")
async def list_projects(request: Request):
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    projects = await db.list_projects(visitor_id)
    if not projects:
        default = await db.create_project(visitor_id, "默认项目")
        projects = [default]
    return {"projects": projects}


@app.post("/api/projects")
async def create_project(request: Request):
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    body = await request.json()
    name = body.get("name", "未命名项目").strip()
    if not name:
        raise HTTPException(400, "项目名称不能为空")
    project = await db.create_project(visitor_id, name)
    return project


# ── Notes ──

@app.get("/api/projects/{project_id}/notes")
async def list_notes(project_id: str, request: Request):
    notes = await db.list_notes(project_id)
    return {"notes": notes}


@app.post("/api/projects/{project_id}/notes")
async def add_note(project_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "").strip()
    content = body.get("content", "").strip()
    if not title or not content:
        raise HTTPException(400, "标题和内容不能为空")
    note = await db.add_note(project_id, title, content, source="user")
    parsed = parse_note_content(content, note["id"])
    tasks_created = []
    for t in parsed["tasks"]:
        task = await db.add_task(project_id, note["id"], t["title"],
                                 t["assignee"], t["due_date"], t["priority"], t["source_line"])
        tasks_created.append(task)
    for d in parsed["decisions"]:
        await db.add_decision(project_id, note["id"], d["content"], d["source_line"])
    for r in parsed["risks"]:
        await db.add_risk(project_id, note["id"], r["content"], r["source_line"])
    return {"note": note, "tasks_created": len(tasks_created),
            "decisions_created": len(parsed["decisions"]),
            "risks_created": len(parsed["risks"])}


@app.post("/api/projects/{project_id}/notes/import-fixture")
async def import_fixture(project_id: str, request: Request):
    fixture_path = FIXTURES_DIR / "demo_notes.json"
    if not fixture_path.exists():
        raise HTTPException(404, "演示文件不存在")
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    imported = []
    total_tasks = 0
    total_decisions = 0
    total_risks = 0
    for note_data in data.get("notes", []):
        note = await db.add_note(project_id, note_data["title"], note_data["content"],
                                 source="fixture", note_date=note_data.get("date"))
        parsed = parse_note_content(note_data["content"], note_data["id"])
        for t in parsed["tasks"]:
            await db.add_task(project_id, note["id"], t["title"],
                              t["assignee"], t["due_date"], t["priority"], t["source_line"])
            total_tasks += 1
        for d in parsed["decisions"]:
            await db.add_decision(project_id, note["id"], d["content"], d["source_line"])
            total_decisions += 1
        for r in parsed["risks"]:
            await db.add_risk(project_id, note["id"], r["content"], r["source_line"])
            total_risks += 1
        imported.append(note)
    return {"imported": len(imported), "tasks": total_tasks,
            "decisions": total_decisions, "risks": total_risks}


@app.delete("/api/projects/{project_id}/notes/{note_id}")
async def delete_note(project_id: str, note_id: str):
    ok = await db.delete_note(note_id, project_id)
    if not ok:
        raise HTTPException(404, "记录不存在")
    return {"deleted": True}


# ── Tasks ──

@app.get("/api/projects/{project_id}/tasks")
async def list_tasks(project_id: str):
    tasks = await db.list_tasks(project_id)
    return {"tasks": tasks}


@app.patch("/api/projects/{project_id}/tasks/{task_id}")
async def update_task(project_id: str, task_id: str, request: Request):
    body = await request.json()
    task = await db.update_task(task_id, project_id, **body)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


# ── Decisions & Risks ──

@app.get("/api/projects/{project_id}/decisions")
async def list_decisions(project_id: str):
    return {"decisions": await db.list_decisions(project_id)}


@app.get("/api/projects/{project_id}/risks")
async def list_risks(project_id: str):
    return {"risks": await db.list_risks(project_id)}


# ── Stats ──

@app.get("/api/projects/{project_id}/stats")
async def get_stats(project_id: str):
    return await db.get_stats(project_id)


# ── PowerContext Memory ──

@app.get("/api/memory/status")
async def memory_status(request: Request):
    client = get_client()
    health = await client.health_check()
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    memory_logs = await db.get_memory_log(visitor_id, limit=5)
    sanitized_logs = []
    for log in memory_logs:
        sanitized_logs.append({
            "action": log["action"],
            "endpoint": log["endpoint"],
            "success": bool(log["success"]),
            "created_at": log["created_at"],
        })
    return {
        "configured": client.is_configured,
        "health": health,
        "recent_logs": sanitized_logs,
    }


@app.post("/api/memory/save")
async def save_preference(request: Request):
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(400, "偏好内容不能为空")
    client = get_client()
    if not client.is_configured:
        await db.log_memory_action(visitor_id, "save", "none", {"text": text[:50]}, None, False)
        return {"success": False, "error": "PowerContext 未配置，无法保存记忆到远程服务", "configured": False}
    scope_result = await client.get_or_create_scope(visitor_id)
    if "error" in scope_result:
        await db.log_memory_action(visitor_id, "save_scope", "/v1/scopes", {"visitor": visitor_id[:8]}, scope_result, False)
        return {"success": False, "error": f"Scope 创建失败: {scope_result['error']}", "configured": True}
    scope_id = scope_result["scope_id"]
    remember_result = await client.remember(scope_id, "decision", text, "User-saved weekly report preference via FlowMemo")
    await db.log_memory_action(
        visitor_id, "remember", "/v1/memory/remember",
        {"scope_id": scope_id[:8] + "...", "kind": "decision", "text": text[:80]},
        {"success": remember_result["success"], "records_count": len(remember_result.get("records", []))},
        remember_result["success"]
    )
    return {
        "success": remember_result["success"],
        "records": remember_result.get("records", []),
        "scope_id_prefix": scope_id[:8] + "...",
        "configured": True,
    }


@app.post("/api/memory/recall")
async def recall_memory(request: Request):
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    body = await request.json()
    query = body.get("query", "周报偏好").strip()
    client = get_client()
    if not client.is_configured:
        await db.log_memory_action(visitor_id, "recall", "none", {"query": query}, None, False)
        return {"success": False, "content": "", "status": "not_configured", "configured": False}
    scope_result = await client.get_or_create_scope(visitor_id)
    if "error" in scope_result:
        return {"success": False, "content": "", "status": "no_scope", "error": scope_result["error"]}
    scope_id = scope_result["scope_id"]
    prepare_result = await client.prepare(scope_id, query)
    await db.log_memory_action(
        visitor_id, "prepare", "/v1/context/prepare",
        {"scope_id": scope_id[:8] + "...", "query": query},
        {"status": prepare_result.get("status"), "content_length": len(prepare_result.get("content", ""))},
        prepare_result.get("status") == "ready"
    )
    return {
        "success": prepare_result.get("status") == "ready",
        "status": prepare_result.get("status", "unknown"),
        "content": prepare_result.get("content", ""),
        "configured": True,
    }


# ── Weekly Report ──

@app.post("/api/projects/{project_id}/report")
async def generate_weekly_report(project_id: str, request: Request):
    sid = _get_session_id(request)
    visitor_id = await db.get_or_create_visitor(sid)
    notes = await db.list_notes(project_id)
    tasks = await db.list_tasks(project_id)
    decisions = await db.list_decisions(project_id)
    risks = await db.list_risks(project_id)
    memory_content = ""
    recalled_count = 0
    client = get_client()
    if client.is_configured:
        scope_result = await client.get_or_create_scope(visitor_id)
        if "scope_id" in scope_result:
            prepare_result = await client.prepare(scope_result["scope_id"], "周报偏好 写作顺序")
            if prepare_result.get("status") == "ready" and prepare_result.get("content"):
                memory_content = prepare_result["content"]
                recalled_count = 1
    report = generate_report(notes, tasks, decisions, risks, memory_content, recalled_count)
    return {
        "report": report,
        "stats": {
            "notes": len(notes),
            "tasks": len(tasks),
            "done": sum(1 for t in tasks if t.get("status") == "done"),
            "risks": len(risks),
            "decisions": len(decisions),
            "recalled_memories": recalled_count,
        },
        "memory_applied": bool(memory_content),
    }


# ── Static files ──

@app.get("/static/{path:path}")
async def serve_static(path: str):
    file_path = STATIC_DIR / path
    if file_path.is_file():
        return FileResponse(file_path)
    raise HTTPException(404, "File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8900)
