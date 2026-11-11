# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Lossless row-level CSV evidence with stable document/key identities."""
from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote

from pydantic import BaseModel

from powercontext.sources import AdapterSourceDefinition, TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization


class CSVDocumentInput(BaseModel):
    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    if not isinstance(document_id, str) or not document_id or document_id != document_id.strip():
        raise ValueError("document_id must be nonblank without outer whitespace")
    if not isinstance(primary_key_value, str) or not primary_key_value.strip():
        raise ValueError("primary_key_value must not be blank")
    identity = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(identity) > 256:
        raise ValueError("CSV row Source ID exceeds 256 characters")
    return identity


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    if not isinstance(value.document_id, str) or not value.document_id or value.document_id != value.document_id.strip():
        raise ValueError("invalid document_id")
    if not isinstance(value.primary_key, str) or not value.primary_key.strip():
        raise ValueError("invalid primary_key")
    try:
        text = value.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if not header or len(set(header)) != len(header) or any(not col.strip() for col in header):
            raise ValueError("invalid CSV header")
        if value.primary_key not in header:
            raise ValueError("primary key does not match CSV header")
        idx = header.index(value.primary_key)
        result = []
        seen = set()
        for values in reader:
            if not values:  # truly empty physical record, not a blank field
                continue
            if len(values) != len(header):
                raise ValueError("CSV row width mismatch")
            key = values[idx]
            if not key.strip() or key in seen:
                raise ValueError("duplicate or empty CSV primary key")
            csv_row_source_id(value.document_id, key)  # validate bounded identity atomically
            seen.add(key)
            result.append(CSVRowInput(
                document_id=value.document_id, primary_key=value.primary_key,
                primary_key_value=key, columns=tuple(header), values=tuple(values),
            ))
        return tuple(result)
    except (UnicodeError, csv.Error, StopIteration) as error:
        raise ValueError("malformed or incomplete CSV document") from error


class _CSVRowAdapter:
    name = "csv-row"
    input_class = CSVRowInput
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        name = csv_row_source_id(value.document_id, value.primary_key_value)
        if (len(value.columns) != len(value.values) or len(set(value.columns)) != len(value.columns)
                or value.primary_key not in value.columns
                or value.values[value.columns.index(value.primary_key)] != value.primary_key_value):
            raise ValueError("invalid CSV row shape")
        return CSVRowSource(name=name, source_id=name, materialization=SourceMaterialization.CAPTURED,
                            **value.model_dump())

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput.model_validate(source.model_dump(include=set(CSVRowInput.model_fields)))


class _CSVRowProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        fields = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(source_type="csv-row", source_id=source.source_id,
                            content=json.dumps(fields, ensure_ascii=False, separators=(",", ":")),
                            metadata={"document_id": source.document_id, "primary_key": source.primary_key,
                                      "primary_key_value": source.primary_key_value,
                                      "columns": list(source.columns), "row": fields})


CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(_CSVRowAdapter(), projections=(_CSVRowProjection(),))
