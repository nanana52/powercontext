# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""CSV row Sources with stable document/key identities and exact raw-line readback.

The source identity excludes physical row number. Equal re-imports are idempotent;
changed payloads for an existing immutable Source raise the repository's conflict.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

CSV_ROW_SOURCE_NAME = "csv-row"
NonEmpty = Annotated[str, Field(min_length=1)]


class CsvRowCapture(BaseModel):
    """One row parsed from a document, retaining input order and original bytes-as-text."""

    document_id: NonEmpty
    primary_key_column: NonEmpty
    primary_key: NonEmpty
    columns: tuple[str, ...]
    values: tuple[str, ...]
    raw_header: str
    raw_record: str

    @model_validator(mode="after")
    def validate_row(self) -> "CsvRowCapture":
        if (
            not self.document_id.strip()
            or not self.primary_key_column.strip()
            or not self.primary_key.strip()
            or not self.columns
            or len(self.columns) != len(self.values)
            or self.columns.count(self.primary_key_column) != 1
            or self.values[self.columns.index(self.primary_key_column)] != self.primary_key
        ):
            raise ValueError("invalid CSV row identity or column shape")  # noqa: TRY003
        return self


class CsvRowSource(Source):
    document_id: str
    primary_key_column: str
    primary_key: str
    columns: tuple[str, ...]
    values: tuple[str, ...]
    raw_header: str
    raw_record: str


def csv_row_source_id(document_id: str, primary_key: str) -> str:
    """Derive an unambiguous, stable Source ID independent of row order."""

    identity = json.dumps([document_id, primary_key], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class CsvRowSourceAdapter:
    input_class = CsvRowCapture
    source_class = CsvRowSource
    name = CSV_ROW_SOURCE_NAME

    async def resolve(self, value: CsvRowCapture, /) -> CsvRowSource:
        return CsvRowSource(
            name=csv_row_source_id(value.document_id, value.primary_key),
            materialization=SourceMaterialization.CAPTURED,
            **value.model_dump(),
        )

    async def read(self, source: CsvRowSource, /) -> CsvRowCapture:
        return CsvRowCapture.model_validate(source.model_dump(include=set(CsvRowCapture.model_fields)))


class CsvRowTextEvidenceProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CsvRowSource
    output_class = TextEvidence

    def project(self, source: CsvRowSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.name,
            content="\n".join(f"{name}: {value}" for name, value in zip(source.columns, source.values, strict=True)),
            metadata={
                "document_id": source.document_id,
                "primary_key_column": source.primary_key_column,
                "primary_key": source.primary_key,
                "columns": list(source.columns),
                "values": list(source.values),
                "raw_header": source.raw_header,
                "raw_record": source.raw_record,
            },
        )


def parse_csv_rows(document_id: str, csv_text: str, primary_key_column: str, /) -> tuple[CsvRowCapture, ...]:
    """Parse one CSV text, rejecting malformed rows before returning any capture.

    ``newline=''`` and StringIO tell preserve CRLF, multiline quoted fields and
    exact CSV physical row text for later evidence. No file system access occurs.
    """

    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must be nonempty")  # noqa: TRY003
    if not isinstance(primary_key_column, str) or not primary_key_column.strip():
        raise ValueError("primary_key_column must be nonempty")  # noqa: TRY003
    if not isinstance(csv_text, str):
        raise TypeError("csv_text must be decoded UTF-8 text")  # noqa: TRY003

    stream = io.StringIO(csv_text, newline="")
    reader = csv.reader(stream, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("CSV must contain a header") from None  # noqa: TRY003
    header_end = stream.tell()
    if not header or primary_key_column not in header or header.count(primary_key_column) != 1:
        raise ValueError("CSV must have exactly one matching primary key column")  # noqa: TRY003
    if any(not column.strip() for column in header):
        raise ValueError("CSV headers cannot be empty")  # noqa: TRY003
    header_text = csv_text[:header_end]
    records: list[CsvRowCapture] = []
    observed: set[str] = set()
    last = header_end
    for row in reader:
        finish = stream.tell()
        if len(row) != len(header):
            raise ValueError("CSV row width differs from header")  # noqa: TRY003
        key = row[header.index(primary_key_column)]
        if not key.strip() or key in observed:
            raise ValueError("CSV primary keys must be nonempty and unique per document")  # noqa: TRY003
        observed.add(key)
        records.append(
            CsvRowCapture(
                document_id=document_id,
                primary_key_column=primary_key_column,
                primary_key=key,
                columns=tuple(header),
                values=tuple(row),
                raw_header=header_text,
                raw_record=csv_text[last:finish],
            )
        )
        last = finish
    return tuple(records)


CSV_ROW_SOURCE_ADAPTER = CsvRowSourceAdapter()
CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSV_ROW_SOURCE_ADAPTER,
    projections=(CsvRowTextEvidenceProjection(),),
)

__all__ = [
    "CSV_ROW_SOURCE_ADAPTER",
    "CSV_ROW_SOURCE_DEFINITION",
    "CSV_ROW_SOURCE_NAME",
    "CsvRowCapture",
    "CsvRowSource",
    "parse_csv_rows",
    "csv_row_source_id",
]
