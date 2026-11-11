# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Functional HTTP wire tests for the score reranker, without real credentials."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx
import pytest
from pydantic import SecretStr

from powercontext.builtin.artifacts.memory import HttpScoreMemoryReranker, HttpScoreRerankConfig
from powercontext.builtin.inference.errors import InvalidInferenceOutputError, InferenceUnavailableError


@dataclass(frozen=True)
class Candidate:
    text: str


def test_batches_global_sort_identity_and_request_count() -> None:
    calls = []

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer dummy-key"
        data = json.loads(request.content)
        calls.append(data)
        return httpx.Response(200, json={"scores": [
            {"id": item["id"], "score": {"a": 0.5, "b": 0.9, "c": 0.9, "d": -1}[item["text"]]}
            for item in reversed(data["candidates"])
        ]})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
            reranker = HttpScoreMemoryReranker(
                HttpScoreRerankConfig(
                    endpoint="https://ranker.example/api/score",
                    api_key=SecretStr("dummy-key"),
                    batch_size=2,
                ), client,
            )
            result = await reranker.rerank("query", tuple(Candidate(t) for t in "abcd"), 3)
            assert result.selected_ranks == (2, 3, 1)
            assert result.usage.requests == 2
            assert [[item["id"] for item in call["candidates"]] for call in calls] == [["1", "2"], ["3", "4"]]

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [
    {"scores": [{"id": "1", "score": 1.0}]},  # missing one
    {"scores": [{"id": "1", "score": 1.0}, {"id": "1", "score": 2.0}]},  # duplicate
    {"scores": [{"id": "1", "score": 1.0}, {"id": "9", "score": 2.0}]},  # invented
    {"scores": [{"id": "1", "score": float("nan")}, {"id": "2", "score": 0.5}]},
    {"scores": [{"id": "1", "score": "1"}, {"id": "2", "score": 0.5}]},
])
def test_invalid_response_rejected(bad) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=bad))) as client:
            reranker = HttpScoreMemoryReranker(HttpScoreRerankConfig(endpoint="http://localhost/score"), client)
            with pytest.raises(InvalidInferenceOutputError):
                await reranker.rerank("q", (Candidate("a"), Candidate("b")), 1)

    asyncio.run(scenario())


def test_http_provider_error_is_visible() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _req: httpx.Response(503))) as client:
            reranker = HttpScoreMemoryReranker(HttpScoreRerankConfig(endpoint="http://localhost/score"), client)
            with pytest.raises(InferenceUnavailableError):
                await reranker.rerank("q", (Candidate("a"),), 1)

    asyncio.run(scenario())
