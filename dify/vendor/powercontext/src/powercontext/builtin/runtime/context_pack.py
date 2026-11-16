# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Deterministic, independently verifiable context packs and prefix deltas."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"


class ContextPackError(ValueError):
    """Malformed context-pack protocol or invalid delta reconstruction."""


def _json(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _encode(items: tuple[bytes, ...]) -> list[str]:
    return [base64.b64encode(item).decode("ascii") for item in items]


def _decode(items: object) -> tuple[bytes, ...]:
    if not isinstance(items, list):
        raise ContextPackError("items must be an array")
    result = []
    for item in items:
        if not isinstance(item, str):
            raise ContextPackError("chunk must be a Base64 string")
        try:
            raw = base64.b64decode(item, validate=True)
            if base64.b64encode(raw).decode("ascii") != item:
                raise ValueError("noncanonical base64")
            raw.decode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise ContextPackError("chunk must contain canonical Base64 of UTF-8 text") from error
        result.append(raw)
    return tuple(result)


def _check_digest(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ContextPackError("invalid SHA-256 digest")
    return value


def _load(data: bytes, fields: set[str], schema: str) -> dict:
    if not isinstance(data, bytes):
        raise ContextPackError("wire value must be bytes")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ContextPackError("wire must be UTF-8 JSON") from error
    if not isinstance(payload, dict) or set(payload) != fields or payload.get("schema") != schema:
        raise ContextPackError("wrong context pack schema or fields")
    return payload


@dataclass(frozen=True, slots=True)
class ContextPack:
    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        if not isinstance(items, tuple) or any(not isinstance(chunk, bytes) for chunk in items):
            raise ContextPackError("items must be a tuple of bytes")
        for chunk in items:
            try:
                chunk.decode("utf-8")
            except UnicodeError as error:
                raise ContextPackError("chunk must be valid UTF-8") from error
        encoded = _encode(items)
        digest = "sha256:" + hashlib.sha256(_json({"schema": PACK_SCHEMA, "items": encoded})).hexdigest()
        payload = {"schema": PACK_SCHEMA, "items": encoded, "digest": digest, "byte_count": 0}
        n = 0
        for _ in range(10):
            payload["byte_count"] = n
            new = len(_json(payload))
            if new == n:
                return cls(items, digest, n)
            n = new
        raise ContextPackError("cannot stabilize byte count")

    @classmethod
    def from_content(cls, content: str, *, chunk_bytes: int = 512) -> ContextPack:
        if type(chunk_bytes) is not int or chunk_bytes < 1 or not isinstance(content, str):
            raise ContextPackError("chunk_bytes must be a positive integer")
        # Prefer line boundaries to stabilize unchanged blocks across turns.
        chunks: list[bytes] = []
        current = b""
        for line in content.splitlines(keepends=True):
            encoded = line.encode("utf-8")
            if len(encoded) > chunk_bytes:
                if current:
                    chunks.append(current)
                    current = b""
                # Split oversized lines only at code-point boundaries.
                part = b""
                for char in line:
                    char_bytes = char.encode("utf-8")
                    if len(char_bytes) > chunk_bytes:
                        raise ContextPackError("chunk limit cannot fit UTF-8 code point")
                    if len(part) + len(char_bytes) > chunk_bytes:
                        chunks.append(part)
                        part = b""
                    part += char_bytes
                current = part
            elif len(current) + len(encoded) > chunk_bytes:
                if current:
                    chunks.append(current)
                current = encoded
            else:
                current += encoded
        if current:
            chunks.append(current)
        return cls.build(tuple(chunks))

    def to_bytes(self) -> bytes:
        return _json({"schema": PACK_SCHEMA, "items": _encode(self.items),
                      "digest": self.digest, "byte_count": self.byte_count})

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPack:
        payload = _load(data, {"schema", "items", "digest", "byte_count"}, PACK_SCHEMA)
        _check_digest(payload["digest"])
        if type(payload["byte_count"]) is not int or payload["byte_count"] < 0:
            raise ContextPackError("byte_count must be nonnegative integer")
        pack = cls.build(_decode(payload["items"]))
        if pack.digest != payload["digest"] or pack.byte_count != payload["byte_count"]:
            raise ContextPackError("pack digest or byte_count mismatch")
        return pack


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        n = 0
        for left, right in zip(base.items, target.items):
            if left != right:
                break
            n += 1
        return cls(base.digest, target.digest, n, target.items[n:])

    def to_bytes(self) -> bytes:
        return _json({"schema": DELTA_SCHEMA, "base_digest": self.base_digest,
                      "target_digest": self.target_digest, "prefix_items": self.prefix_items,
                      "appended": _encode(self.appended)})

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPackDelta:
        payload = _load(data, {"schema", "base_digest", "target_digest", "prefix_items", "appended"}, DELTA_SCHEMA)
        base_digest = _check_digest(payload["base_digest"])
        target_digest = _check_digest(payload["target_digest"])
        n = payload["prefix_items"]
        if type(n) is not int or n < 0:
            raise ContextPackError("invalid prefix_items")
        return cls(base_digest, target_digest, n, _decode(payload["appended"]))


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("invalid base or delta")
    if base.digest != delta.base_digest:
        raise ContextPackError("base digest mismatch")
    if type(delta.prefix_items) is not int or not 0 <= delta.prefix_items <= len(base.items):
        raise ContextPackError("invalid prefix_items")
    result = ContextPack.build((*base.items[:delta.prefix_items], *delta.appended))
    if result.digest != delta.target_digest:
        raise ContextPackError("target digest mismatch")
    return result


__all__ = ["ContextPack", "ContextPackDelta", "ContextPackError", "apply_context_pack_delta"]
