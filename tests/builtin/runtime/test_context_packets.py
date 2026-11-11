# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import pytest

from powercontext.builtin.runtime.context_packets import (
    PreparedContextPacket,
    pack_prepared_context,
    rebuild_prepared_context,
)
from powercontext.builtin.runtime.models import PreparedContext


def _context(content: str) -> PreparedContext:
    return PreparedContext(status="ready", content=content, content_bytes=len(content.encode("utf-8")))


def test_full_and_delta_preserve_citations_and_reduce_wire_bytes() -> None:
    before = _context("# 引用\n[Source: memory/revision-9]\n" + "原始证据-quoted;" * 150)
    after = _context("# 引用\n[Source: memory/revision-9]\n" + "原始证据-quoted;" * 149 + "新事实 😊")
    full = pack_prepared_context(before, max_payload_bytes=128)
    restored, prior_serialized = rebuild_prepared_context(full)
    assert restored == before
    delta = pack_prepared_context(after, previous_serialized=prior_serialized, max_payload_bytes=128)
    assert delta[0].kind == "delta"
    rebuilt, new_serialized = rebuild_prepared_context(delta, previous_serialized=prior_serialized)
    assert rebuilt == after
    assert "[Source: memory/revision-9]" in rebuilt.content
    assert sum(len(p.model_dump_json(by_alias=True)) for p in delta) < sum(
        len(p.model_dump_json(by_alias=True)) for p in pack_prepared_context(after, max_payload_bytes=128)
    )


def test_missing_frame_wrong_base_corruption_and_reordered_frames() -> None:
    before = _context("source citation old " * 100)
    after = _context("source citation old " * 99 + "new evidence")
    _, base = rebuild_prepared_context(pack_prepared_context(before, max_payload_bytes=60))
    packets = pack_prepared_context(after, previous_serialized=base, max_payload_bytes=60)
    assert rebuild_prepared_context(tuple(reversed(packets)), previous_serialized=base)[0] == after
    with pytest.raises(ValueError):
        rebuild_prepared_context(packets, previous_serialized="wrong")
    with pytest.raises(ValueError):
        rebuild_prepared_context(packets[:-1], previous_serialized=base)
    tampered = list(packets)
    tampered[0] = tampered[0].model_copy(update={"body": tampered[0].body + "x"})
    with pytest.raises((ValueError, __import__('json').JSONDecodeError)):
        rebuild_prepared_context(tuple(tampered), previous_serialized=base)


def test_empty_context_roundtrip_and_serialize_packets_as_json() -> None:
    empty = PreparedContext(status="empty", content=None, content_bytes=0)
    packet = pack_prepared_context(empty)[0]
    reconstructed = PreparedContextPacket.model_validate_json(packet.model_dump_json(by_alias=True))
    assert rebuild_prepared_context((reconstructed,))[0] == empty
