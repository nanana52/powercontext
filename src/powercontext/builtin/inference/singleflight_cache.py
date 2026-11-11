# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0 (the "License");
"""Scoped bounded embedding cache with cross-call single-flight coalescing.

Only successful vectors enter the cache. A waiter cannot cancel the shared
provider call; the provider receives one batch for concurrent misses. Usage
is reported by a wrapped delegate at the *actual* network boundary.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import Iterator

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel, embed_query

_EMBEDDING_SCOPE: ContextVar[str] = ContextVar("powercontext_embedding_scope", default="")


@contextmanager
def bind_embedding_scope(scope_id: str) -> Iterator[None]:
    """Partition all text and in-flight results by the authorized scope."""

    token = _EMBEDDING_SCOPE.set(scope_id)
    try:
        yield
    finally:
        _EMBEDDING_SCOPE.reset(token)


class SingleFlightEmbeddingModel:
    """Ordered batch embeddings, bounded LRU/TTL and cancellation-isolated misses.

    ``delegate`` should be the *usage-reporting* model. Each real provider
    invocation is then measured once, even if fifty callers share its result.
    """

    def __init__(
        self,
        delegate: EmbeddingModel,
        *,
        max_entries: int = 512,
        ttl_seconds: float = 300,
        batch_size: int = 64,
    ) -> None:
        if max_entries < 1 or ttl_seconds <= 0 or batch_size < 1:
            raise ValueError("cache size, TTL and batch size must be positive")
        self._delegate = delegate
        self.profile = delegate.profile
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._batch_size = batch_size
        self._lock = asyncio.Lock()
        self._cache: OrderedDict[tuple[str, str, str], tuple[float, tuple[float, ...]]] = OrderedDict()
        self._pending: dict[tuple[str, str, str], asyncio.Future[tuple[float, ...]]] = {}
        self._queues: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        self._dispatching: dict[tuple[str, str], asyncio.Task[None]] = {}

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return await self._get(texts, mode="document")

    async def embed_query(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return await self._get(texts, mode="query")

    async def _get(self, texts: tuple[str, ...], *, mode: str) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))
        scope = _EMBEDDING_SCOPE.get()
        # Outside a validated Runtime Scope there is no safe tenant cache key.
        # Preserve direct model semantics rather than mixing unknown callers.
        if not scope:
            return await (embed_query(self._delegate, texts) if mode == "query"
                          else self._delegate.embed(texts))
        group = (scope, mode)
        loop = asyncio.get_running_loop()
        now = monotonic()
        futures: list[asyncio.Future[tuple[float, ...]]] = []
        async with self._lock:
            for value in texts:
                key = (scope, mode, value)
                cached = self._cache.get(key)
                if cached is not None:
                    if cached[0] > now:
                        self._cache.move_to_end(key)
                        ready: asyncio.Future[tuple[float, ...]] = loop.create_future()
                        ready.set_result(cached[1])
                        futures.append(ready)
                        continue
                    self._cache.pop(key, None)
                future = self._pending.get(key)
                if future is None:
                    future = loop.create_future()
                    # Task cancellation must not leak an unobserved exception.
                    future.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
                    self._pending[key] = future
                    self._queues.setdefault(group, []).append(key)
                futures.append(future)
            if self._queues.get(group) and group not in self._dispatching:
                self._dispatching[group] = asyncio.create_task(self._dispatch(group))
        vectors = await asyncio.gather(*(asyncio.shield(future) for future in futures))
        return EmbeddingResult(vectors=tuple(vectors), usage=InferenceUsage(requests=0))

    async def _dispatch(self, group: tuple[str, str]) -> None:
        # Give concurrently scheduled callers one event-loop turn to join.
        await asyncio.sleep(0)
        async with self._lock:
            queue = self._queues.get(group, [])
            batch = queue[:self._batch_size]
            del queue[:len(batch)]
            if not queue:
                self._queues.pop(group, None)
            # A second dispatcher is scheduled once this one completes.
        try:
            if not batch:
                return
            texts = tuple(key[2] for key in batch)
            result = (
                await embed_query(self._delegate, texts)
                if group[1] == "query"
                else await self._delegate.embed(texts)
            )
            if len(result.vectors) != len(batch):
                raise ValueError("embedding provider returned a mismatched vector count")
            # Reject nonfinite/invalid dimensions before making anything visible.
            from math import isfinite
            for vec in result.vectors:
                if len(vec) != self.profile.dimension or not all(isfinite(x) for x in vec):
                    raise ValueError("embedding provider returned an invalid vector")
            async with self._lock:
                for key, vec in zip(batch, result.vectors, strict=True):
                    copied = tuple(float(x) for x in vec)
                    self._cache[key] = (monotonic() + self._ttl, copied)
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._max_entries:
                        self._cache.popitem(last=False)
                    self._pending.pop(key).set_result(copied)
        except BaseException as error:
            async with self._lock:
                for key in batch:
                    future = self._pending.pop(key, None)
                    if future is not None and not future.done():
                        future.set_exception(error)
        finally:
            async with self._lock:
                self._dispatching.pop(group, None)
                if self._queues.get(group):
                    self._dispatching[group] = asyncio.create_task(self._dispatch(group))


__all__ = ["SingleFlightEmbeddingModel", "bind_embedding_scope"]
