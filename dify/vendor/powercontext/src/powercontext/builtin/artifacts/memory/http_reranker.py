# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""HTTP score-based Memory reranker using opaque original candidate ranks."""
from __future__ import annotations

import math
from urllib.parse import urlparse

import httpx

from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision, _validate_bounds
from powercontext.builtin.inference import InferenceUsage


class HTTPMemoryReranker:
    policy_id = "powercontext.memory.rerank.http-score.v1"

    def __init__(self, endpoint: str, *, client: httpx.AsyncClient | None = None,
                 batch_size: int = 32, timeout: float = 30.0) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("HTTP reranker endpoint must be an HTTP(S) URL")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if not isinstance(timeout, (float, int)) or timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("timeout must be positive and finite")
        self.endpoint = endpoint
        self._client = client
        self.batch_size = batch_size
        self.timeout = timeout

    async def rerank(self, query: str, candidates: tuple, limit: int, /) -> MemoryRerankDecision:
        _validate_bounds(len(candidates), limit)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be nonempty")
        scored: dict[int, float] = {}
        owned_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        requests = 0
        try:
            for offset in range(0, len(candidates), self.batch_size):
                rows = list(enumerate(candidates[offset:offset + self.batch_size], start=offset + 1))
                body = {"query": query, "candidates": [
                    {"rank": rank, "text": hit.text} for rank, hit in rows
                ]}
                response = await client.post(self.endpoint, json=body, timeout=self.timeout)
                requests += 1
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as error:
                    raise ValueError("HTTP reranker did not return valid JSON") from error
                if not isinstance(payload, dict) or set(payload) != {"scores"} or not isinstance(payload["scores"], list):
                    raise ValueError("HTTP reranker response must have only a scores array")
                seen: set[int] = set()
                expected = {rank for rank, _ in rows}
                for item in payload["scores"]:
                    if not isinstance(item, dict) or set(item) != {"rank", "score"}:
                        raise ValueError("invalid score fields")
                    rank, score = item["rank"], item["score"]
                    if (type(rank) is not int or rank not in expected or rank in seen
                            or type(score) not in (float, int) or not math.isfinite(score)):
                        raise ValueError("invalid or duplicated candidate score")
                    seen.add(rank)
                    scored[rank] = float(score)
                if seen != expected:
                    raise ValueError("HTTP reranker omitted candidate ranks")
            ranks = tuple(sorted(scored, key=lambda rank: (-scored[rank], rank))[:limit])
            return MemoryRerankDecision(selected_ranks=ranks, usage=InferenceUsage(requests=requests))
        finally:
            if owned_client:
                await client.aclose()
