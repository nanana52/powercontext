"""Note parser: extracts tasks, decisions, and risks from meeting notes.

Rules:
- Line-based parsing with normalized full-width colons
- `待办：` → task, `决定：` → decision, `风险：` → risk
- Tasks: extract assignee (Chinese name), due date (YYYY-MM-DD), priority (高/中/低)
- No guessing — unparseable fields go to "待确认"
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_line(line: str) -> str:
    """Normalize full-width colons and whitespace."""
    return line.strip().replace("：", ":").replace("　", " ")


def parse_assignee(text: str) -> str:
    """Extract Chinese name as assignee from text like '小周在 ... 前'."""
    m = re.search(r'([\u4e00-\u9fff]{2,3})(?:\s*在)', text)
    if m:
        return m.group(1)
    m = re.search(r'([\u4e00-\u9fff]{2,3})', text)
    if m:
        return m.group(1)
    return ""


def parse_due_date(text: str) -> str:
    """Extract YYYY-MM-DD date from text."""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    return m.group(1) if m else ""


def parse_priority(text: str) -> str:
    """Extract priority: 高/中/低."""
    if "优先级高" in text or "高" in text:
        return "高"
    if "优先级低" in text or "低" in text:
        return "低"
    if "优先级中" in text or "中" in text:
        return "中"
    return "待确认"


def parse_task_title(text: str) -> str:
    """Extract the core task description, removing assignee/date/priority metadata."""
    title = text
    title = re.sub(r'^.*?在\s*\d{4}-\d{2}-\d{2}\s*前\s*', '', title)
    title = re.sub(r'，?优先级[高中低待确认]', '', title)
    title = title.strip().rstrip('。，,')
    if not title:
        title = text.strip()
    return title


def parse_note_content(content: str, note_id: str) -> dict:
    """Parse a note's content into structured items.

    Returns:
        {
            "tasks": [{"title", "assignee", "due_date", "priority", "source_line"}],
            "decisions": [{"content", "source_line"}],
            "risks": [{"content", "source_line"}],
        }
    """
    tasks = []
    decisions = []
    risks = []

    lines = content.splitlines()
    for i, raw_line in enumerate(lines, start=1):
        line = normalize_line(raw_line)
        if not line:
            continue

        if line.startswith("待办:"):
            body = line[len("待办:"):].strip()
            if not body:
                continue
            assignee = parse_assignee(body)
            due_date = parse_due_date(body)
            priority = parse_priority(body)
            title = parse_task_title(body)
            tasks.append({
                "title": title,
                "assignee": assignee if assignee else "待确认",
                "due_date": due_date if due_date else "待确认",
                "priority": priority,
                "source_line": i,
            })

        elif line.startswith("决定:"):
            body = line[len("决定:"):].strip()
            if body:
                decisions.append({"content": body, "source_line": i})

        elif line.startswith("风险:"):
            body = line[len("风险:"):].strip()
            if body:
                risks.append({"content": body, "source_line": i})

    return {"tasks": tasks, "decisions": decisions, "risks": risks}
