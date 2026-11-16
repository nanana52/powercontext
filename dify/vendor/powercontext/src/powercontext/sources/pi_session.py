# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Lossless selected-branch Pi v3 session capture with durable connector checkpoints."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from powercontext.sources import AdapterSourceDefinition, TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence
from powercontext.sources.connectors import ConnectorRunCompletion, ConnectorRunStatus
from powercontext.sources.models import Source, SourceMaterialization


class PiSessionInput(BaseModel):
    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


class PiEventSource(Source):
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


def _source_id(session: str, event: str) -> str:
    if not session or not event:
        raise ValueError("event and session ID must be nonblank")
    packed = json.dumps([session, event], ensure_ascii=False, separators=(",", ":")).encode()
    return "pi:" + hashlib.sha256(packed).hexdigest()


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    pieces = []
    for part in value:
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text" and isinstance(part.get("text"), str):
            pieces.append(part["text"])
        elif kind == "toolCall":
            arguments = json.dumps(part.get("arguments", {}), sort_keys=True,
                                   ensure_ascii=False, separators=(",", ":"))
            pieces.append(f"[tool_call {part.get('name', '')} {part.get('id', '')}] {arguments}")
    return "\n".join(pieces)


def _event(session_id: str, row: dict) -> PiEventInput | None:
    kind = row.get("type")
    if kind in ("compaction", "branch_summary"):
        role, content = kind, row.get("summary") or ""
    elif kind == "custom_message":
        role, content = "custom", _text(row.get("content"))
    elif kind == "message":
        msg = row.get("message")
        if not isinstance(msg, dict):
            return None
        role = msg.get("role")
        if not isinstance(role, str):
            return None
        if role == "toolResult":
            value = _text(msg.get("content"))
            content = f"[tool_result {msg.get('toolName', '')} {msg.get('toolCallId', '')}] {value}" if value else ""
        elif role == "bashExecution":
            cmd = msg.get("command") or ""
            output = msg.get("output") or ""
            content = ("$ " + cmd + ("\n" + output if output else "")) if cmd else ""
        else:
            content = _text(msg.get("content"))
    else:
        return None
    if not isinstance(content, str) or not content:
        return None
    return PiEventInput(session_id=session_id, event_id=row["id"], parent_id=row.get("parentId"),
                        event_type=kind, role=role, content=f"{role}: {content}", record=row)


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    try:
        lines = [line for line in value.content.decode("utf-8-sig").splitlines() if line.strip()]
        rows = [json.loads(line) for line in lines]
    except (UnicodeError, ValueError) as error:
        raise ValueError("invalid Pi v3 session JSONL") from error
    if not rows or not isinstance(rows[0], dict) or rows[0].get("type") != "session" or type(rows[0].get("version")) is not int or rows[0]["version"] != 3 or not isinstance(rows[0].get("id"), str) or not rows[0]["id"].strip():
        raise ValueError("missing or invalid Pi v3 session header")
    session_id = rows[0]["id"]
    nodes: dict[str, dict] = {}
    last = None
    for row in rows[1:]:
        if not isinstance(row, dict):
            raise ValueError("invalid Pi event object")
        id_ = row.get("id")
        parent = row.get("parentId")
        if not isinstance(id_, str) or not id_.strip() or id_ in nodes:
            raise ValueError("duplicate or invalid Pi event ID")
        if parent is not None and (not isinstance(parent, str) or parent not in nodes):
            raise ValueError("missing or forward Pi parent")
        nodes[id_] = row
        last = id_
    if not nodes:
        if value.leaf_id is not None:
            raise ValueError("Pi session has no requested leaf")
        return ()
    target = value.leaf_id if value.leaf_id is not None else last
    if target not in nodes:
        raise ValueError("requested Pi leaf does not exist")
    chain = []
    visited = set()
    while target is not None:
        if target in visited:
            raise ValueError("Pi session parent cycle")
        visited.add(target)
        row = nodes[target]
        chain.append(row)
        target = row.get("parentId")
    out = []
    for row in reversed(chain):
        item = _event(session_id, row)
        if item is not None:
            out.append(item)
    return tuple(out)


class _PiAdapter:
    name = "pi-event"
    input_class = PiEventInput
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        return PiEventSource(name=_source_id(value.session_id, value.event_id),
                             materialization=SourceMaterialization.CAPTURED, **value.model_dump())

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput.model_validate(source.model_dump(include=set(PiEventInput.model_fields)))


class _PiProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(source_type="pi-event", source_id=source.name, content=source.content,
                            metadata={"session_id": source.session_id, "event_id": source.event_id,
                                      "parent_id": source.parent_id, "event_type": source.event_type,
                                      "role": source.role})


PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(_PiAdapter(), projections=(_PiProjection(),))


class PiSessionConnector:
    name = "pi-session-history"
    version = "1"
    source_definitions = frozenset({"pi-event"})

    def __init__(self, path: str | Path, leaf_id: str | None = None):
        self.path = Path(path)
        self.leaf_id = leaf_id

    async def run(self, session, /) -> ConnectorRunCompletion:
        events = parse_pi_session(PiSessionInput(content=self.path.read_bytes(), leaf_id=self.leaf_id))
        previous = session.checkpoint
        if previous is None:
            prior: dict[str, str] = {}
        elif (isinstance(previous, dict) and set(previous) == {"digests"}
              and isinstance(previous["digests"], dict)
              and all(isinstance(k, str) and isinstance(v, str) for k, v in previous["digests"].items())):
            prior = dict(previous["digests"])
        else:
            raise ValueError("invalid Pi connector checkpoint")
        updated = dict(prior)
        # Reject mutation of any imported event before submitting any new events.
        new = []
        for event in events:
            identity = _source_id(event.session_id, event.event_id)
            raw = json.dumps(event.record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(raw).hexdigest()
            if identity in prior:
                if prior[identity] != digest:
                    raise ValueError("previously imported Pi event was edited")
            else:
                updated[identity] = digest
                new.append(event)
        for event in new:
            await session.submit(_source_id(event.session_id, event.event_id), "pi-event", event)
        return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint={"digests": updated})


__all__ = ["PiSessionInput", "PiEventInput", "parse_pi_session", "PI_EVENT_SOURCE_DEFINITION", "PiSessionConnector"]
