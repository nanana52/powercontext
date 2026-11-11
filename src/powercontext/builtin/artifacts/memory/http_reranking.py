# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Batch HTTP score adapter for the existing identity-preserving Memory rerank port.

Wire protocol v1:
  POST {"query": str, "candidates": [{"id": "1", "text": "..."}, ...]}
  200  {"scores": [{"id": "1", "score": 0.85}, ...]}

Every candidate id must appear exactly once in each response. The id is an opaque
rank label, not an Artifact id; the Runtime keeps authoritative hit identities.
"""

from __future__ import annotations

import asyncio
import json
from typing import Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from powercontext.builtin.artifacts.memory.reranking import (
    MemoryRerankDecision,
    MemoryRerankText,
    _validate_bounds,
)
from powercontext.builtin.inference import InferenceUsage
from powercontext.builtin.inference.errors import (
    InferenceConfigurationError,
    InferenceTimeoutError,
    InferenceUnavailableError,
    InvalidInferenceOutputError,
)

HTTP_SCORE_RERANK_POLICY = "powercontext.memory.rerank.http-score.v1"


class HttpScoreRerankConfig(BaseModel):
    """Client-owned HTTP scoring endpoint and operation bounds."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    endpoint: str = Field(repr=False)
    api_key: SecretStr | None = Field(default=None, repr=False)
    batch_size: int = Field(default=16, ge=1, le=256, strict=True)
    timeout_seconds: float = Field(default=30.0, gt=0, allow_inf_nan=False)
    max_request_bytes: int = Field(default=65_536, ge=256, strict=True)

    @model_validator(mode="after")
    def validate_endpoint(self) -> Self:
        try:
            url = httpx.URL(self.endpoint)
        except (TypeError, ValueError) as error:
            raise ValueError("HTTP reranker requires an absolute HTTP endpoint") from error  # noqa: TRY003
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.fragment
            or any(c.isspace() for c in self.endpoint)
        ):
            raise ValueError("HTTP reranker requires a valid endpoint without embedded credentials")  # noqa: TRY003
        return self


class _Score(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    score: float = Field(allow_inf_nan=False)


class _ScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: tuple[_Score, ...]


class HttpScoreMemoryReranker:
    """Score a coarse pool in bounded batches, then rank globally and stably.

    Pass this instance to ``open_builtin_runtime(memory_reranker=...)``. Search
    and prepare keep their existing authorization and citation semantics.
    """

    supports_atomic_memory = True
    policy_id = HTTP_SCORE_RERANK_POLICY

    def __init__(self, config: HttpScoreRerankConfig, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client

    async def rerank(self, query: str, candidates: tuple[MemoryRerankText, ...], limit: int, /) -> MemoryRerankDecision:
        _validate_bounds(len(candidates), limit)
        scores: list[float] = []
        requests = 0
        headers = {"Content-Type": "application/json"}
        if self._config.api_key is not None:
            headers["Authorization"] = f"Bearer {self._config.api_key.get_secret_value()}"

        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                for start in range(0, len(candidates), self._config.batch_size):
                    batch = candidates[start : start + self._config.batch_size]
                    entries = [{"id": str(start + index + 1), "text": item.text} for index, item in enumerate(batch)]
                    payload = json.dumps({"query": query, "candidates": entries}, ensure_ascii=False).encode("utf-8")
                    if len(payload) > self._config.max_request_bytes:
                        raise InferenceConfigurationError("HTTP rerank batch exceeds max_request_bytes")
                    requests += 1
                    response = await self._client.post(
                        self._config.endpoint,
                        content=payload,
                        headers=headers,
                        timeout=self._config.timeout_seconds,
                        follow_redirects=False,
                    )
                    response.raise_for_status()
                    result = _ScoreResponse.model_validate(response.json())
                    expected = {item["id"] for item in entries}
                    observed: dict[str, float] = {}
                    for item in result.scores:
                        if item.id not in expected or item.id in observed:
                            raise ValueError("score response contains unknown or duplicate candidate id")  # noqa: TRY003
                        observed[item.id] = item.score
                    if set(observed) != expected:
                        raise ValueError("score response omits one or more candidates")  # noqa: TRY003
                    scores.extend(observed[item["id"]] for item in entries)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise InferenceTimeoutError("memory.rerank", self._config.timeout_seconds) from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {408, 504}:
                raise InferenceTimeoutError("memory.rerank", self._config.timeout_seconds) from error
            if error.response.status_code in {409, 425, 429} or error.response.status_code >= 500:
                raise InferenceUnavailableError("memory.rerank") from error
            raise InferenceConfigurationError("HTTP rerank endpoint rejected request") from error
        except (httpx.RequestError, OSError) as error:
            raise InferenceUnavailableError("memory.rerank") from error
        except (ValueError, TypeError) as error:
            raise InvalidInferenceOutputError("memory.rerank", "invalid scoring response") from error

        ranks = tuple(sorted(range(1, len(candidates) + 1), key=lambda rank: (-scores[rank - 1], rank))[:limit])
        return MemoryRerankDecision(selected_ranks=ranks, usage=InferenceUsage(requests=requests))


__all__ = ["HTTP_SCORE_RERANK_POLICY", "HttpScoreMemoryReranker", "HttpScoreRerankConfig"]
