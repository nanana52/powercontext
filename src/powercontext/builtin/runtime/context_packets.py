# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Versioned, self-checking incremental transfer for prepared Agent context.

Every frame contains enough metadata to reject missing, mixed or corrupt packets.
A delta's only external input is the prior serialized frame result; no database,
index or hidden shared memory is required for reconstruction.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from powercontext.builtin.runtime.models import PreparedContext

PACKET_SCHEMA = "powercontext.prepared-context.packet.v1"


class PreparedContextPacket(BaseModel):
    """One bounded UTF-8 payload fragment and its reconstruction metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["powercontext.prepared-context.packet.v1"] = Field(default=PACKET_SCHEMA, alias="schema")
    kind: Literal["full", "delta"]
    base_digest: str | None
    result_digest: str
    index: int = Field(ge=0)
    total: int = Field(ge=1)
    body: str


def serialize_prepared_context(value: PreparedContext) -> str:
    """Canonical wire encoding that preserves content and exact citations."""

    return json.dumps(value.model_dump(mode="json", by_alias=True), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _delta(previous: str, current: str) -> str:
    """Encode prefix/middle/suffix as a small source-bound, deterministic diff."""

    common_prefix = 0
    common_max = min(len(previous), len(current))
    while common_prefix < common_max and previous[common_prefix] == current[common_prefix]:
        common_prefix += 1
    common_suffix = 0
    while (
        common_suffix < common_max - common_prefix
        and previous[len(previous) - common_suffix - 1] == current[len(current) - common_suffix - 1]
    ):
        common_suffix += 1
    operations: list[list[object]] = []
    if common_prefix:
        operations.append(["copy", 0, common_prefix])
    middle = current[common_prefix : len(current) - common_suffix if common_suffix else len(current)]
    if middle:
        operations.append(["text", middle])
    if common_suffix:
        operations.append(["copy", len(previous) - common_suffix, len(previous)])
    return json.dumps(operations, ensure_ascii=False, separators=(",", ":"))


def _utf8_chunks(text: str, max_payload_bytes: int) -> tuple[str, ...]:
    if max_payload_bytes < 16:
        raise ValueError("max_payload_bytes must be at least 16")  # noqa: TRY003
    chunks: list[str] = []
    part: list[str] = []
    count = 0
    for char in text:
        size = len(char.encode("utf-8"))
        if part and count + size > max_payload_bytes:
            chunks.append("".join(part))
            part.clear()
            count = 0
        part.append(char)
        count += size
    if part or not chunks:
        chunks.append("".join(part))
    return tuple(chunks)


def pack_prepared_context(
    result: PreparedContext,
    /,
    *,
    previous_serialized: str | None = None,
    max_payload_bytes: int = 2048,
) -> tuple[PreparedContextPacket, ...]:
    """Choose smaller full or delta transfer and split its payload into frames."""

    current = serialize_prepared_context(result)
    full = _assemble("full", None, _digest(current), current, max_payload_bytes)
    if previous_serialized is None:
        return full
    # Do not trust arbitrary caller-provided base content, even if it hashes.
    PreparedContext.model_validate_json(previous_serialized)
    delta = _assemble("delta", _digest(previous_serialized), _digest(current), _delta(previous_serialized, current), max_payload_bytes)
    full_size = sum(len(packet.model_dump_json(by_alias=True).encode("utf-8")) for packet in full)
    delta_size = sum(len(packet.model_dump_json(by_alias=True).encode("utf-8")) for packet in delta)
    return delta if delta_size < full_size else full


def _assemble(kind: Literal["full", "delta"], base: str | None, result: str, body: str, size: int) -> tuple[PreparedContextPacket, ...]:
    chunks = _utf8_chunks(body, size)
    return tuple(
        PreparedContextPacket(
            kind=kind,
            base_digest=base,
            result_digest=result,
            index=index,
            total=len(chunks),
            body=part,
        )
        for index, part in enumerate(chunks)
    )


def rebuild_prepared_context(
    packets: tuple[PreparedContextPacket, ...],
    /,
    *,
    previous_serialized: str | None = None,
) -> tuple[PreparedContext, str]:
    """Reconstruct a prepared result and its serialized state using wire inputs only."""

    if not packets:
        raise ValueError("packet transfer is empty")  # noqa: TRY003
    first = packets[0]
    if len(packets) != first.total or set(packet.index for packet in packets) != set(range(first.total)):
        raise ValueError("transfer packets are missing or duplicated")  # noqa: TRY003
    for packet in packets:
        if (
            packet.schema_version != first.schema_version
            or packet.kind != first.kind
            or packet.base_digest != first.base_digest
            or packet.result_digest != first.result_digest
            or packet.total != first.total
        ):
            raise ValueError("transfer contains packets from different results")  # noqa: TRY003
    payload = "".join(packet.body for packet in sorted(packets, key=lambda packet: packet.index))
    if first.kind == "full":
        if first.base_digest is not None:
            raise ValueError("full transfer may not carry a base digest")  # noqa: TRY003
        serialized = payload
    else:
        if previous_serialized is None or _digest(previous_serialized) != first.base_digest:
            raise ValueError("missing or incorrect prior serialized state")  # noqa: TRY003
        PreparedContext.model_validate_json(previous_serialized)
        operations = json.loads(payload)
        if not isinstance(operations, list) or not operations:
            raise ValueError("delta operations are missing")  # noqa: TRY003
        pieces: list[str] = []
        for op in operations:
            if not isinstance(op, list):
                raise ValueError("malformed delta operation")  # noqa: TRY003
            if len(op) == 2 and op[0] == "text" and isinstance(op[1], str):
                pieces.append(op[1])
            elif (
                len(op) == 3
                and op[0] == "copy"
                and all(type(value) is int for value in op[1:])
                and 0 <= op[1] < op[2] <= len(previous_serialized)
            ):
                pieces.append(previous_serialized[op[1] : op[2]])
            else:
                raise ValueError("invalid delta operation")  # noqa: TRY003
        serialized = "".join(pieces)
    if _digest(serialized) != first.result_digest:
        raise ValueError("reconstructed context digest mismatch")  # noqa: TRY003
    result = PreparedContext.model_validate_json(serialized)
    if serialize_prepared_context(result) != serialized:
        raise ValueError("noncanonical prepared context")  # noqa: TRY003
    return result, serialized


__all__ = [
    "PACKET_SCHEMA",
    "PreparedContextPacket",
    "serialize_prepared_context",
    "pack_prepared_context",
    "rebuild_prepared_context",
]
