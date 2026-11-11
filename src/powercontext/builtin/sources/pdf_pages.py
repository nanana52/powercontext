# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0 (the "License");
"""One durable Source per *physical* page of a financial report PDF.

Pages without extractable text are retained and explicitly marked as needing
OCR, rather than disappearing and shifting all downstream page citations.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections import Counter
from typing import Annotated

from pydantic import BaseModel, Field

from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

PDF_PAGE_SOURCE_NAME = "pdf-page"
NonEmpty = Annotated[str, Field(min_length=1)]


class PdfPageCapture(BaseModel):
    document_id: NonEmpty
    pdf_digest: NonEmpty
    page_number: Annotated[int, Field(ge=1)]
    total_pages: Annotated[int, Field(ge=1)]
    text: str
    requires_ocr: bool = False


class PdfPageSource(Source):
    document_id: str
    pdf_digest: str
    page_number: int
    total_pages: int
    text: str
    requires_ocr: bool = False


def pdf_page_source_id(document_id: str, page_number: int) -> str:
    if not document_id.strip() or page_number < 1:
        raise ValueError("document_id and one-based page number are required")
    return hashlib.sha256(f"{document_id}\0{page_number}".encode("utf-8")).hexdigest()


class PdfPageSourceAdapter:
    name = PDF_PAGE_SOURCE_NAME
    input_class = PdfPageCapture
    source_class = PdfPageSource

    async def resolve(self, value: PdfPageCapture, /) -> PdfPageSource:
        return PdfPageSource(
            name=pdf_page_source_id(value.document_id, value.page_number),
            materialization=SourceMaterialization.CAPTURED,
            **value.model_dump(),
        )

    async def read(self, source: PdfPageSource, /) -> PdfPageCapture:
        return PdfPageCapture.model_validate(source.model_dump(include=set(PdfPageCapture.model_fields)))


class PdfPageTextProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PdfPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PdfPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.name,
            content=source.text or f"[Page {source.page_number}: text layer unavailable, OCR required]",
            metadata={
                "document_id": source.document_id,
                "pdf_digest": source.pdf_digest,
                "page_number": source.page_number,
                "total_pages": source.total_pages,
                "requires_ocr": source.requires_ocr,
            },
        )


def parse_pdf_pages(document_id: str, pdf_data: bytes, /) -> tuple[PdfPageCapture, ...]:
    """Extract every physical page using pypdf (optional ``pdf`` dependency)."""

    if not document_id.strip() or not isinstance(pdf_data, bytes) or not pdf_data:
        raise ValueError("PDF identity and nonempty bytes are required")
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("Install pypdf to enable financial-report PDF ingestion") from error
    reader = PdfReader(io.BytesIO(pdf_data), strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF cannot be ingested without authorization")
    digest = hashlib.sha256(pdf_data).hexdigest()
    pages = []
    total = len(reader.pages)
    if not total:
        raise ValueError("PDF has no physical pages")
    for number, page in enumerate(reader.pages, start=1):
        # Layout mode retains many table column breaks; fallback avoids silently
        # losing ordinary text on PDF versions unsupported by layout extraction.
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError, KeyError):
            text = page.extract_text() or ""
        pages.append(PdfPageCapture(
            document_id=document_id,
            pdf_digest=digest,
            page_number=number,
            total_pages=total,
            text=text,
            requires_ocr=not bool(text.strip()),
        ))
    return tuple(pages)


def pdf_query_tokens(text: str) -> tuple[str, ...]:
    lower = text.casefold()
    words = re.findall(r"[a-z0-9][a-z0-9_.%-]*|[\u3400-\u9fff]+", lower)
    result: list[str] = []
    for word in words:
        if "\u3400" <= word[0] <= "\u9fff" and len(word) > 1:
            result.extend(word[i:i+2] for i in range(len(word)-1))
        else:
            result.append(word)
    return tuple(result)


def rank_pdf_pages(query: str, pages: tuple[PdfPageSource, ...], /, *, limit: int = 5) -> tuple[PdfPageSource, ...]:
    """Lexical page ranking preserving distinct physical page identity."""
    terms = Counter(pdf_query_tokens(query))
    if not terms or limit < 1:
        return ()
    scored: list[tuple[float, PdfPageSource]] = []
    for page in pages:
        if page.requires_ocr:
            continue
        words = Counter(pdf_query_tokens(page.text))
        matched = sum(min(count, words[term]) for term, count in terms.items())
        coverage = sum(1 for term in terms if words[term])
        if coverage:
            score = (coverage / len(terms)) * 2 + matched / (len(words) + 10) ** .5
            scored.append((score, page))
    scored.sort(key=lambda item: (-item[0], item[1].document_id, item[1].page_number))
    return tuple(page for _, page in scored[:limit])


PDF_PAGE_SOURCE_ADAPTER = PdfPageSourceAdapter()
PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(PDF_PAGE_SOURCE_ADAPTER, projections=(PdfPageTextProjection(),))

__all__ = [
    "PDF_PAGE_SOURCE_NAME", "PDF_PAGE_SOURCE_ADAPTER", "PDF_PAGE_SOURCE_DEFINITION",
    "PdfPageCapture", "PdfPageSource", "parse_pdf_pages", "pdf_page_source_id", "rank_pdf_pages",
]
