# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import asyncio
import csv

import pytest

from powercontext.builtin.sources import (
    BUILTIN_SOURCE_REGISTRY,
    CSV_ROW_SOURCE_ADAPTER,
    CSV_ROW_SOURCE_NAME,
    parse_csv_rows,
)
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY


def test_csv_multiline_quoted_fields_and_stable_source_id() -> None:
    raw = 'id,label,notes\r\nα,"quoted, value","line 1\r\nline 2"\r\nβ,last,done\r\n'
    captures = parse_csv_rows("invoice-2026", raw, "id")
    assert len(captures) == 2
    assert captures[0].values == ("α", "quoted, value", "line 1\r\nline 2")
    assert captures[0].raw_record == 'α,"quoted, value","line 1\r\nline 2"\r\n'
    assert captures[0].raw_header == 'id,label,notes\r\n'

    async def scenario():
        source = await BUILTIN_SOURCE_REGISTRY.resolve(captures[0])
        row = await CSV_ROW_SOURCE_ADAPTER.read(source)
        assert row == captures[0]
        assert (await CSV_ROW_SOURCE_ADAPTER.resolve(captures[0])).name == source.name
        assert (await CSV_ROW_SOURCE_ADAPTER.resolve(captures[0].model_copy(update={"document_id": "different"}))).name != source.name
        projection = BUILTIN_SOURCE_REGISTRY.project(source, TEXT_EVIDENCE_PROJECTION_KEY)
        assert projection["source_type"] == CSV_ROW_SOURCE_NAME
        assert projection["metadata"]["values"] == list(captures[0].values)
        assert "line 1\r\nline 2" in projection["content"]

    asyncio.run(scenario())


@pytest.mark.parametrize("raw", [
    'id,body\n1,yes\n1,no\n',
    'id,body\n,no\n',
    'id,body\n1,2,3\n',
    'id,body\n"unterminated,x',
    'name,body\nJohn,ok\n',
    'id,id\n1,2\n',
])
def test_csv_rejects_ambiguous_or_malformed_input(raw):
    with pytest.raises((ValueError, csv.Error)):
        parse_csv_rows("doc", raw, "id")


def test_csv_persistence_codec_round_trip_uses_registered_definition() -> None:
    """Exercise the real repository codec without requiring a database service."""

    pytest.importorskip("aiosqlite")  # requires the repository's full builtin dependencies
    from powercontext.builtin.persistence.sources import SourceRepository

    async def scenario():
        capture = parse_csv_rows("d2", 'id,value\r\nx,"a,b"\r\n', "id")[0]
        source = await CSV_ROW_SOURCE_ADAPTER.resolve(capture)
        reference, encoded = SourceRepository(BUILTIN_SOURCE_REGISTRY)._encode(source)
        fresh_repository = SourceRepository(BUILTIN_SOURCE_REGISTRY)
        restored = fresh_repository.decode_source({
            "source_type": reference.source_type,
            "source_id": reference.source_id,
            "payload": encoded,
            "journal_position": 4,
        })
        assert restored.value == source
        assert await fresh_repository.read_value(restored.value) == capture
        assert restored.journal_position == 4

    asyncio.run(scenario())
