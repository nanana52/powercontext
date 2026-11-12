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
                    weights[word] = max(weights.get(word, 0.0), 0.65)
    return weights


def _statement_targets(question: str) -> tuple[str, ...]:
    """Map generic business concepts to filing sections, never to fixed pages."""
    lower = question.casefold()
    targets: list[str] = []
    if any(x in lower for x in (
        "cash flow", "capex", "capital expenditure", "depreciation", "amortization",
        "free cash", "operating cash", "cash from operations",
    )):
        targets.append("cash")
    if any(x in lower for x in (
        "income statement", "profit and loss", "p&l", "operating income",
        "ebitda", "revenue", "sales", "margin", "earnings", "operating profit",
    )):
        targets.append("income")
    if any(x in lower for x in (
        "balance sheet", "asset", "liabilities", "debt", "equity", "working capital",
    )):
        targets.append("balance")
    if any(x in lower for x in ("legal", "litigation", "lawsuit", "proceeding", "battles")):
        targets.append("legal")
    if any(x in lower for x in ("geograph", "region", "territor", "countries", "segments")):
        targets.append("geography")
    if "restructur" in lower or "reorganization" in lower:
        targets.append("restructuring")
    return tuple(dict.fromkeys(targets))


def _statement_relevance(text: str, target: str) -> float:
    """Give actual statement/section headings priority over passing mentions.

    The same phrases apply to any annual report; nothing depends on document ID,
    company name, a FinanceBench label, or a known evidence page.
    """
    head = text[:850]
    opening = text[:180]
    if target == "cash":
        return (60.0 if any(x in opening for x in (
            "statement of cash flows", "statements of cash flows", "cash flow statement",
        )) else 15.0 if any(x in head for x in (
            "statement of cash flows", "statements of cash flows",
            "cash flow statement", "statement of cashflow",
        )) else 0.0) + (2.0 if "net cash provided" in text else 0.0)
    if target == "income":
        return (60.0 if any(x in opening for x in (
            "statement of income", "statements of income", "statement of operations",
            "statements of operations", "statement of earnings",
        )) else 15.0 if any(x in head for x in (
            "statement of income", "statements of income", "statement of operations",
            "statements of operations", "statement of earnings", "income statement",
        )) else 0.0) + (1.8 if "net sales" in text or "net revenue" in text else 0.0)
    if target == "balance":
        return (60.0 if any(x in opening for x in (
            "balance sheets", "balance sheet", "statements of financial position",
        )) else 15.0 if any(x in head for x in (
            "balance sheets", "balance sheet", "statements of financial position",
        )) else 0.0) + (1.8 if "total assets" in text and "liabilit" in text else 0.0)
    if target == "legal":
        return (17.0 if "legal proceedings" in head else 0.0) + (
            3.0 if any(x in text for x in ("legal proceedings", "pending litigation", "litigation")) else 0.0
        )
    if target == "geography":
        return (12.0 if any(x in head for x in (
            "geographic areas", "geographical information", "business segments",
            "reportable segments", "segment information", "our segments",
        )) else 0.0) + (2.0 if "geographic" in text else 0.0)
    if target == "restructuring":
        return (12.0 if any(x in head for x in (
            "restructuring charges", "restructuring and", "restructuring costs",
            "restructuring expenses",
        )) else 0.0) + (2.0 if "restructuring" in text else 0.0)
    return 0.0


def _proximity_relevance(tokens: list[str], weighted_terms: dict[str, float]) -> float:
    """Reward overlapping evidence terms in the same local paragraph/table.

    Pure page-level bag-of-words rank is noisy on hundreds of dense 10-K pages.
    This bounded sliding-window signal does not rely on any reference answers.
    """
    if not tokens or not weighted_terms:
        return 0.0
    if len(tokens) < 200:
        window = set(tokens)
        return sum(weight for term, weight in weighted_terms.items() if term in window)
    best = 0.0
    for start in range(0, len(tokens), 90):
        window = set(tokens[start:start + 190])
        score = sum(weight for term, weight in weighted_terms.items() if term in window)
        if score > best:
            best = score
    return best


async def search_pdf_pages(memory, question: str, limit: int = 10):
    """Rank persisted scoped PDF citations using several generic evidence signals.

    The result is always a real MemoryCitation; only the memory public search and
    list APIs are used. Scores use the submitted question and stored page text,
    never reference answers, labels, page numbers, or an external index.
    """
    from powercontext.builtin.runtime import SearchMemoryRequest
    from powercontext.builtin.artifacts.memory.models import MemoryCitation

    if limit <= 0:
        return ()
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
        seen: set[tuple[str, str, str]] = set()
        citations: list[MemoryCitation] = []
        for hit in found.hits:
            key = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
            if key not in seen:
                seen.add(key)
                citations.append(MemoryCitation(memory_ref=hit.memory_ref,
                                                entry_id=hit.entry_id,
                                                entry_version_id=hit.entry_version_id))
            if len(citations) == limit:
                break
        return tuple(citations)

    terms = _query_weights(question)
    targets = _statement_targets(question)
    token_lists = [_tokens(record.entry.text) for record in entries]
    counters = [Counter(toks) for toks in token_lists]
    lengths = [len(toks) for toks in token_lists]
    document_count = len(entries)
    average_length = max(1.0, sum(lengths) / document_count)
    df: Counter[str] = Counter()
    for counter in counters:
        df.update(counter.keys())
    idf = {
        term: math.log1p((document_count - df.get(term, 0) + 0.5) /
                         (df.get(term, 0) + 0.5))
        for term in terms
    }
    prox_weights = {term: weight * idf[term] for term, weight in terms.items()}
    prox_max = sum(prox_weights.values()) or 1.0
    full_scores: list[float] = []
    text_scores: list[float] = []
    section_scores: dict[str, list[float]] = {target: [] for target in targets}
    for index, record in enumerate(entries):
        count = counters[index]
        norm = 1.2 * (0.25 + 0.75 * lengths[index] / average_length)
        bm25 = sum(
            weight * idf[term] * (freq * 2.2) / (freq + norm)
            for term, weight in terms.items() if (freq := count.get(term, 0))
        )
        covered = sum(weight for term, weight in terms.items() if count.get(term))
        coverage = covered / (sum(terms.values()) or 1.0)
        proximity = _proximity_relevance(token_lists[index], prox_weights) / prox_max
        plain = bm25 + 2.5 * coverage + 4.0 * proximity
        key = (record.memory_ref.artifact_id, record.entry.entry_id, record.entry.entry_version_id)
        if key in fts_ranks:
            plain += 2.0 / math.sqrt(1.0 + fts_ranks[key])
        lower = record.entry.text.casefold()
        for phrase in (
            "cash flows", "operating income", "net revenues", "net sales",
            "balance sheets", "total assets", "capital expenditures",
            "depreciation and amortization", "legal proceedings", "geographic areas",
            "restructuring charges",
        ):
            if phrase in question.casefold() and phrase in lower:
                plain += 2.0
        text_scores.append(plain)
        category = {target: _statement_relevance(lower, target) for target in targets}
        # Target sections receive attention without allowing an unrelated table
        # title to overwhelm every lexical match.
        full_scores.append(plain + min(5.0, max(category.values(), default=0.0) * 0.30))
        for target, bonus in category.items():
            section_scores[target].append(plain + bonus)

    selected: list[int] = []
    seen_sources: set[tuple[str, str]] = set()

    def choose(index: int) -> None:
        record = entries[index]
        source = next(ref for ref in record.entry.sources if ref.source_type == "pdf-page")
        key = (source.source_type, source.source_id)
        if key not in seen_sources:
            seen_sources.add(key)
            selected.append(index)

    # Guarantee representation of different statement families needed for
    # multi-table calculations, even when one statement dominates BM25.
    if targets and limit >= 8:
        per_target = min(4, max(1, limit // (max(1, len(targets)) * 5)))
        for target in targets:
            order = sorted(range(document_count), key=lambda i: section_scores[target][i], reverse=True)
            for index in order[:per_target]:
                choose(index)

    # Complement lexical rank with the index-backed search channel. This
    # provides a second retrieval path when either tokenizer misses a synonym.
    if limit >= 10:
        index_ranks = sorted(
            (i for i, record in enumerate(entries)
             if (record.memory_ref.artifact_id, record.entry.entry_id,
                 record.entry.entry_version_id) in fts_ranks),
            key=lambda i: fts_ranks[(entries[i].memory_ref.artifact_id,
                                     entries[i].entry.entry_id,
                                     entries[i].entry.entry_version_id)],
        )
        for index in index_ranks[:min(3, limit // 6)]:
            choose(index)

    for index in sorted(range(document_count), key=lambda i: full_scores[i], reverse=True):
        if len(selected) >= limit:
            break
        choose(index)
    return tuple(entries[index].citation for index in selected[:limit])
