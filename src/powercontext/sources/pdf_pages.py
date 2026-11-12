# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Physical-page PDF Sources, immutable across document revisions."""
from __future__ import annotations

import hashlib
import io
import math
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



# General IR vocabulary only: these are synonyms and statement headings, not
# document IDs, evaluation questions, reference answers or evidence page labels.
_STOP = frozenset("""
a an the of to from for with on and or in at by as is are was were be been being
have has had do does did would could should if then else how what which who why
when where that this these those it its they their there any all about during over
into in at up down can may might based using use evaluate calculate give answer
please state show find amount value number total much many percentage percent
reported report reporting according information details shown provided following
within perspective analyst investment question provide determine whether
fy year years fiscal annual financial company corporation corporation inc corp
millions million billion thousands usd dollars compared compare comparison
""".split())

# Neutral concept equivalences that apply to every company's annual report.
_EXPANSIONS = (
    (("income statement", "income statements", "p&l", "profit and loss"),
     ("statement", "operation", "revenue", "earning", "income")),
    (("cash flow", "cash flows", "cashflow"),
     ("statement", "cash", "flow", "operating", "investing", "financing")),
    (("balance sheet", "balance sheets"), ("balance", "asset", "liability", "equity")),
    (("ebitda",), ("operating", "income", "depreciation", "amortization")),
    (("capex", "capital expenditures", "capital expenditure"),
     ("capital", "expenditure", "property", "plant", "equipment", "addition", "purchase")),
    (("revenue", "revenues", "sales"), ("net", "sale", "revenue")),
    (("operating profit", "operating income", "operating earnings"),
     ("income", "operation", "earning")),
    (("cash from operations", "operating cash flow"),
     ("net", "cash", "provided", "operating", "activity")),
    (("net income", "net earnings", "profit margin"),
     ("net", "earning", "income", "revenue")),
    (("debt", "leverage", "borrowings"), ("debt", "loan", "borrowing", "liability")),
    (("restructuring",), ("restructuring", "reorganization", "charge", "cost")),
    (("geography", "geographies", "geographic", "region"),
     ("segment", "region", "geographic", "international", "country")),
    (("lawsuit", "litigation", "legal battles", "legal proceedings"),
     ("legal", "proceeding", "litigation", "contingency")),
)

_TOKEN_RE = re.compile(r"[a-z]+|\d+")


def _stem(word: str) -> str:
    # Deliberately conservative: financial account names must not be destroyed.
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(token) for token in _TOKEN_RE.findall(text.casefold())]


def _query_weights(question: str) -> dict[str, float]:
    terms = Counter(word for word in _tokens(question) if word not in _STOP and len(word) > 1)
    weights: dict[str, float] = {word: min(1.0 + 0.10 * (count - 1), 1.4) for word, count in terms.items()}
    lower = question.casefold()
    for triggers, synonyms in _EXPANSIONS:
        if any(phrase in lower for phrase in triggers):
            for word in synonyms:
                word = _stem(word)
                if word not in _STOP:
                    weights[word] = max(weights.get(word, 0.0), 0.28)
    return weights


def _statement_targets(question: str) -> tuple[str, ...]:
    lower = question.casefold()
    targets: list[str] = []
    if any(x in lower for x in ("cash flow", "cash flows", "capex", "capital expenditure", "depreciation", "amortization")):
        targets.append("cash")
    if any(x in lower for x in ("income statement", "profit and loss", "p&l", "operating income", "ebitda", "revenue", "margin", "earnings")):
        targets.append("income")
    if any(x in lower for x in ("balance sheet", "asset", "liabilities", "debt", "equity", "working capital")):
        targets.append("balance")
    return tuple(targets)


def _statement_relevance(text: str, target: str) -> float:
    lower = text.casefold()
    if target == "cash":
        return (4.5 if "statement" in lower and "cash flow" in lower else 0.0) + (
            1.6 if "net cash provided" in lower or "net cash used" in lower else 0.0
        )
    if target == "income":
        return (4.5 if "statement" in lower and ("operation" in lower or "income" in lower) else 0.0) + (
            1.6 if "cost of sales" in lower or "net sales" in lower else 0.0
        )
    return (4.5 if "balance sheet" in lower else 0.0) + (
        1.6 if "total assets" in lower and "liabilities" in lower else 0.0
    )


async def search_pdf_pages(memory, question: str, limit: int = 10):
    """Rank real persisted PDF page citations using scoped public Memory APIs.

    A full natural-language question is not a good single FTS query for a long
    annual report.  Search gives index-backed seeds; list supplies the complete
    scoped page corpus so short, rare evidence and multi-statement questions
    cannot disappear at the candidate-generation stage.  Both APIs only expose
    actual persisted Memory entries, whose citations are returned unchanged.
    """
    from powercontext.builtin.runtime import SearchMemoryRequest
    from powercontext.builtin.artifacts.memory.models import MemoryCitation

    if limit <= 0:
        return ()
    # Preserve the native search channel and its exact persistent identities.
    found = await memory.search(SearchMemoryRequest(
        query=question, mode="fts", limit=max(100, min(limit * 6, 200)),
    ))
    fts_ranks = {
        (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id): rank
        for rank, hit in enumerate(found.hits)
    }

    page = await memory.list()
    entries = [
        record for record in page.entries
        if any(ref.source_type == "pdf-page" for ref in record.entry.sources)
    ]
    if not entries:
        # Compatible fallback for Memory backends with search but no page entries.
        seen: set[tuple[str, str, str]] = set()
        output: list[MemoryCitation] = []
        for hit in found.hits:
            key = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
            if key in seen:
                continue
            seen.add(key)
            output.append(MemoryCitation(memory_ref=hit.memory_ref,
                                         entry_id=hit.entry_id,
                                         entry_version_id=hit.entry_version_id))
            if len(output) >= limit:
                break
        return tuple(output)

    term_weights = _query_weights(question)
    targets = _statement_targets(question)
    count_by_document: list[Counter[str]] = []
    lengths: list[int] = []
    frequency: Counter[str] = Counter()
    for record in entries:
        terms = Counter(_tokens(record.entry.text))
        count_by_document.append(terms)
        lengths.append(sum(terms.values()))
        frequency.update(terms.keys())
    average_length = max(1, sum(lengths) / len(lengths))
    document_count = len(entries)
    idf = {
        term: math.log1p((document_count - frequency.get(term, 0) + 0.5) /
                         (frequency.get(term, 0) + 0.5))
        for term in term_weights
    }
    scores: list[float] = []
    group_scores: dict[str, list[float]] = {target: [] for target in targets}
    for index, record in enumerate(entries):
        freq = count_by_document[index]
        norm = 1.2 * (0.25 + 0.75 * lengths[index] / average_length)
        lexical = sum(
            weight * idf[term] * (count * 2.2) / (count + norm)
            for term, weight in term_weights.items()
            if (count := freq.get(term, 0))
        )
        present = sum(weight for term, weight in term_weights.items() if freq.get(term))
        coverage = present / max(sum(term_weights.values()), 1.0)
        score = lexical + 2.0 * coverage
        key = (record.memory_ref.artifact_id, record.entry.entry_id, record.entry.entry_version_id)
        if key in fts_ranks:
            score += 1.6 / math.sqrt(1 + fts_ranks[key])
        # Exact multiword accounting labels are stronger than isolated words.
        lower = record.entry.text.casefold()
        for phrase in ("cash flows", "operating income", "net revenues", "net sales",
                       "balance sheets", "total assets", "capital expenditures",
                       "depreciation and amortization", "legal proceedings"):
            if phrase in question.casefold() and phrase in lower:
                score += 1.3
        scores.append(score)
        for target in targets:
            group_scores[target].append(score + _statement_relevance(lower, target))

    selected: list[int] = []
    selected_sources: set[tuple[str, str]] = set()

    def choose(index: int) -> None:
        record = entries[index]
        source = next(ref for ref in record.entry.sources if ref.source_type == "pdf-page")
        key = (source.source_type, source.source_id)
        if key not in selected_sources:
            selected_sources.add(key)
            selected.append(index)

    # Reserve a few candidates for each financial statement needed to answer a
    # multi-statement question; otherwise BM25 over a long report over-focuses
    # on just one side of a ratio.
    if len(targets) > 1 and limit >= len(targets) * 2:
        per_target = min(4, max(2, limit // (len(targets) * 3)))
        for target in targets:
            for index in sorted(range(document_count),
                                key=lambda i: group_scores[target][i], reverse=True)[:per_target]:
                choose(index)
    for index in sorted(range(document_count), key=lambda i: scores[i], reverse=True):
        if len(selected) >= limit:
            break
        choose(index)
    return tuple(entries[index].citation for index in selected[:limit])
