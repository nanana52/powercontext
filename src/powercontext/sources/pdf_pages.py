# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Physical-page PDF Sources, immutable across document revisions."""
from __future__ import annotations

import hashlib
import io
import re
from collections import Counter

from pydantic import BaseModel

from powercontext.sources import AdapterSourceDefinition, TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization


class PDFDocumentInput(BaseModel):
    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    if not value.document_id.strip() or not value.content.startswith(b"%PDF-"):
        raise ValueError("invalid PDF document")
    from pypdf import PdfReader
    digest = hashlib.sha256(value.content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(value.content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("encrypted PDF requires a password")
        total = len(reader.pages)
        if total <= 0:
            raise ValueError("PDF has no pages")
        rows = []
        for number, page in enumerate(reader.pages, start=1):
            # pypdf's plain extraction preserves high-quality text and table digits.
            text = page.extract_text(extraction_mode="plain") or ""
            rows.append(PDFPageInput(document_id=value.document_id, document_sha256=digest,
                                     page_number=number, text=text))
        return tuple(rows)
    except Exception as error:
        raise ValueError("PDF could not be fully parsed") from error


class _PDFPageAdapter:
    name = "pdf-page"
    input_class = PDFPageInput
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        if not value.document_id.strip() or value.page_number < 1 or not re.fullmatch(r"[a-f0-9]{64}", value.document_sha256):
            raise ValueError("invalid page identity")
        # Digest of tuple makes identity safe for arbitrary-length document IDs.
        key = f"{value.document_id}\0{value.document_sha256}\0{value.page_number}".encode()
        name = f"pdf:{hashlib.sha256(key).hexdigest()}"
        return PDFPageSource(name=name, materialization=SourceMaterialization.CAPTURED, **value.model_dump())

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput.model_validate(source.model_dump(include=set(PDFPageInput.model_fields)))


class _PDFPageProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(source_type="pdf-page", source_id=source.name,
                            content=f"{source.document_id}\n{source.text}",
                            metadata={"document_id": source.document_id,
                                      "document_sha256": source.document_sha256,
                                      "page_number": source.page_number})


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(_PDFPageAdapter(), projections=(_PDFPageProjection(),))


async def search_pdf_pages(memory, question: str, limit: int = 10):
    """Return actual scoped Memory citations; never synthesize a page hit."""
    from powercontext.builtin.runtime import SearchMemoryRequest
    from powercontext.builtin.artifacts.memory.models import MemoryCitation
    if limit <= 0:
        return ()
    # Database-backed search is authoritative; lexical re-ranking can be added
    # without losing the exact stored citation identity.
    result = await memory.search(SearchMemoryRequest(query=question, mode="fts", limit=max(limit * 5, 100)))
    seen = set()
    citations = []
    for hit in result.hits:
        key = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
        if key not in seen:
            seen.add(key)
            citations.append(MemoryCitation(memory_ref=hit.memory_ref, entry_id=hit.entry_id,
                                            entry_version_id=hit.entry_version_id))
            if len(citations) >= limit:
                break
    return tuple(citations)
