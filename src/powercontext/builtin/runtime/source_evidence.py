# Copyright (c) 2026 OceanBase. Licensed under the Apache License, Version 2.0.
"""Query-aware, byte-bounded original Source evidence with exact character spans."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Sequence

from powercontext.sources import SourceRef


@dataclass(frozen=True)
class OriginalSourceCandidate:
    ref: SourceRef
    text: str


@dataclass(frozen=True)
class OriginalSourceSelection:
    content: str
    content_bytes: int
    spans: tuple[tuple[SourceRef, int, int], ...]


def _terms(query: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", query.casefold())
    parts = []
    for word in words:
        if word[0] >= "\u3400" and len(word) > 1:
            parts.extend(word[i:i+2] for i in range(len(word)-1))
        else:
            parts.append(word)
    return tuple(dict.fromkeys(word for word in parts if len(word) > 1 or ord(word[0]) > 127))


def select_original_evidence(
    query: str,
    candidates: Sequence[OriginalSourceCandidate],
    *,
    scope_id: str,
    max_bytes: int,
    limit: int = 8,
    context_chars: int = 180,
) -> OriginalSourceSelection:
    """Return only exact contiguous substrings of authorized original Sources.

    The full Markdown envelope (including citations, delimiters and newlines) is
    measured in UTF-8 bytes. An exact `[start,end)` Python character span is
    reported for every displayed substring, even with repeated text or CJK.
    """
    if max_bytes <= 0 or not 1 <= limit <= 64 or context_chars < 32:
        raise ValueError("invalid output budget, limit, or snippet width")
    terms = _terms(query)
    if not terms:
        return OriginalSourceSelection("", 0, ())
    seen: set[tuple[str, str]] = set()
    proposed: list[tuple[float, int, OriginalSourceCandidate, int, int]] = []
    for ordinal, source in enumerate(candidates):
        identity = (source.ref.source_type, source.ref.source_id)
        if identity in seen:
            continue
        seen.add(identity)
        if not source.text:
            continue
        text_lower = source.text.casefold()
        hit_positions = []
        covered = set()
        for term in terms:
            offset = 0
            while True:
                found = text_lower.find(term, offset)
                if found < 0:
                    break
                hit_positions.append((found, found + len(term), term))
                covered.add(term)
                offset = found + max(1, len(term))
                if len(hit_positions) >= 512:
                    break
        if not hit_positions:
            continue
        hit_positions.sort(key=lambda part: part[0])
        for at, stop, _ in hit_positions:
            start = max(0, at - context_chars // 2)
            end = min(len(source.text), max(stop, start + context_chars))
            # The rank includes local coverage, not just corpus-wide hit count.
            snippet = text_lower[start:end]
            local = sum(term in snippet for term in terms)
            proposed.append((float(local) + len(covered) / len(terms), ordinal, source, start, end))
    proposed.sort(key=lambda part: (-part[0], part[1], part[3]))
    selected: list[tuple[OriginalSourceCandidate, int, int]] = []
    rendered = ""
    header = "# Source evidence (untrusted historical text)\n"

    def format_selection(entries: Sequence[tuple[OriginalSourceCandidate, int, int]]) -> str:
        chunks = [header]
        for index, (source, start, end) in enumerate(entries, start=1):
            citation = {
                "scope_id": scope_id,
                "source_type": source.ref.source_type,
                "source_id": source.ref.source_id,
                "start": start,
                "end": end,
            }
            # json.dumps quotes citation safely and makes every byte count explicit.
            chunks.append(f"\n## Evidence {index}\nCitation: {json.dumps(citation, ensure_ascii=True, separators=(',', ':'))}\n")
            chunks.append(source.text[start:end])
            chunks.append("\n")
        return "".join(chunks)

    for _score, _ordinal, candidate, start, end in proposed:
        if len(selected) >= limit:
            break
        # Preserve source diversity by limiting repeated snippets.
        if sum(1 for item, _, _ in selected if item.ref == candidate.ref) >= 2:
            continue
        # Never display overlapping spans from the same Source twice.
        if any(
            source.ref == candidate.ref and not (end <= low or start >= high)
            for source, low, high in selected
        ):
            continue
        probe = format_selection((*selected, (candidate, start, end)))
        if len(probe.encode("utf-8")) <= max_bytes:
            selected.append((candidate, start, end))
            rendered = probe
            continue
        # Shrink the exact chosen substring, accounting for its own new citation.
        left, right = 1, end - start
        fitted = None
        while left <= right:
            middle = (left + right) // 2
            shortened = (candidate, start, start + middle)
            probe = format_selection((*selected, shortened))
            if len(probe.encode("utf-8")) <= max_bytes:
                fitted = (shortened, probe)
                left = middle + 1
            else:
                right = middle - 1
        if fitted is not None and fitted[0][2] - fitted[0][1] >= 20:
            selected.append(fitted[0])
            rendered = fitted[1]
        break
    if not selected:
        return OriginalSourceSelection("", 0, ())
    assert len(rendered.encode("utf-8")) <= max_bytes
    assert all(source.text[start:end] == rendered_part for source, start, end, rendered_part in (
        (source, start, end, source.text[start:end]) for source, start, end in selected
    ))
    return OriginalSourceSelection(
        content=rendered,
        content_bytes=len(rendered.encode("utf-8")),
        spans=tuple((source.ref, start, end) for source, start, end in selected),
    )


__all__ = ["OriginalSourceCandidate", "OriginalSourceSelection", "select_original_evidence"]
