"""Weekly report generator for FlowMemo.

Generates a structured weekly report from tasks, decisions, and risks.
Respects PowerContext-retrieved user preferences for section ordering.
All data is traceable to source notes — nothing is fabricated.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


DEFAULT_ORDER = ["risk", "done", "in_progress", "decisions", "next_week"]

SECTION_LABELS = {
    "risk": "风险",
    "done": "已完成",
    "in_progress": "进行中 / 待办",
    "decisions": "决策",
    "next_week": "下周计划",
}


def parse_preferred_order(memory_content: str) -> list[str]:
    """Extract section order from user preference memory.

    Example: '先写风险，再写已完成，最后写下周计划' → ['risk', 'done', 'next_week']
    """
    if not memory_content:
        return DEFAULT_ORDER[:]

    keyword_map = [
        ("风险", "risk"),
        ("已完成", "done"),
        ("完成", "done"),
        ("进行中", "in_progress"),
        ("待办", "in_progress"),
        ("决策", "decisions"),
        ("决定", "decisions"),
        ("下周", "next_week"),
        ("计划", "next_week"),
    ]

    order = []
    for keyword, section in keyword_map:
        if keyword in memory_content and section not in order:
            order.append(section)

    for s in DEFAULT_ORDER:
        if s not in order:
            order.append(s)

    return order


def format_source(note_title: Optional[str], note_id: Optional[str]) -> str:
    if note_title:
        return f"（来源：{note_title}）"
    if note_id:
        return f"（来源：{note_id}）"
    return ""


def generate_report(
    notes: list[dict],
    tasks: list[dict],
    decisions: list[dict],
    risks: list[dict],
    memory_content: str = "",
    recalled_count: int = 0,
) -> str:
    """Generate a Markdown weekly report.

    - Does NOT fabricate completed items.
    - Each item references its source note.
    - Section order follows memory preference if available.
    """
    order = parse_preferred_order(memory_content)

    done_tasks = [t for t in tasks if t.get("status") == "done"]
    pending_tasks = [t for t in tasks if t.get("status") != "done"]
    note_map = {n["id"]: n.get("title", n["id"]) for n in notes}

    header_stats = f"基于 {len(notes)} 条记录、{len(tasks)} 个任务、{recalled_count} 条已召回记忆"

    lines = [f"# 周报", f"", f"> {header_stats}", ""]

    if memory_content:
        lines.append(f"📌 **记忆偏好已应用**：{memory_content[:100]}")
        lines.append("")

    section_renderers = {
        "risk": lambda: _render_risks(risks, note_map),
        "done": lambda: _render_done(done_tasks, note_map),
        "in_progress": lambda: _render_pending(pending_tasks, note_map),
        "decisions": lambda: _render_decisions(decisions, note_map),
        "next_week": lambda: _render_next_week(pending_tasks, note_map),
    }

    for section_key in order:
        renderer = section_renderers.get(section_key)
        if renderer:
            content = renderer()
            if content:
                lines.append(content)
                lines.append("")

    today = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"---")
    lines.append(f"*生成日期：{today}*")

    return "\n".join(lines)


def _render_risks(risks: list[dict], note_map: dict) -> str:
    if not risks:
        return "## 风险\n\n暂无已识别风险。"
    lines = ["## 风险"]
    for r in risks:
        src = format_source(note_map.get(r.get("note_id")), r.get("note_id"))
        lines.append(f"- {r['content']}{src}")
    return "\n".join(lines)


def _render_done(tasks: list[dict], note_map: dict) -> str:
    if not tasks:
        return "## 已完成\n\n暂无已完成事项（不编造）。"
    lines = ["## 已完成"]
    for t in tasks:
        assignee = f"{t['assignee']}：" if t.get("assignee") else ""
        src = format_source(note_map.get(t.get("note_id")), t.get("note_id"))
        lines.append(f"- {assignee}{t['title']}{src}")
    return "\n".join(lines)


def _render_pending(tasks: list[dict], note_map: dict) -> str:
    if not tasks:
        return ""
    lines = ["## 进行中 / 待办"]
    for t in tasks:
        assignee = f"{t['assignee']}：" if t.get("assignee") else ""
        due = f"，截止 {t['due_date']}" if t.get("due_date") and t["due_date"] != "待确认" else ""
        src = format_source(note_map.get(t.get("note_id")), t.get("note_id"))
        lines.append(f"- {assignee}{t['title']}{due}{src}")
    return "\n".join(lines)


def _render_decisions(decisions: list[dict], note_map: dict) -> str:
    if not decisions:
        return ""
    lines = ["## 决策"]
    for d in decisions:
        src = format_source(note_map.get(d.get("note_id")), d.get("note_id"))
        lines.append(f"- {d['content']}{src}")
    return "\n".join(lines)


def _render_next_week(pending_tasks: list[dict], note_map: dict) -> str:
    if not pending_tasks:
        return "## 下周计划\n\n暂无待办事项。"
    lines = ["## 下周计划"]
    for t in pending_tasks:
        assignee = f"{t['assignee']}：" if t.get("assignee") else ""
        status_note = "（待确认）" if t.get("due_date") == "待确认" else ""
        lines.append(f"- {assignee}{t['title']}{status_note}")
    return "\n".join(lines)
