# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Cross-call embedding coalescing, cancellation-safe singleflight and bounded LRU."""
from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from dataclasses import dataclass

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage


@dataclass(frozen=True)
class _Completed:
    vector: tuple[float, ...]
    batch_id: object | None
    usage: InferenceUsage | None


class CoalescingEmbeddingModel:
    def __init__(self, model, *, max_batch_size: int = 64,
                 coalesce_ms: float = 5.0, cache_size: int = 1024):
        if type(max_batch_size) is not int or max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be nonnegative")
        if type(coalesce_ms) not in (int, float) or coalesce_ms < 0 or not math.isfinite(coalesce_ms):
            raise ValueError("coalesce_ms must be a finite nonnegative number")
        self._model = model
        self.profile = model.profile
        self.max_batch_size = max_batch_size
        self.coalesce_ms = float(coalesce_ms)
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple[str, str], tuple[float, ...]] = OrderedDict()
        self._pending: dict[tuple[str, str], asyncio.Future[_Completed]] = {}
        self._queue: list[tuple[str, str]] = []
        self._dispatching = False
        self._lock = asyncio.Lock()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return await self._get(tuple(texts), "document")

    async def embed_query(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        # Symmetric providers use one shared cache; query-specific providers
        # cannot share vectors computed with the document encoder.
        mode = "query" if callable(getattr(self._model, "embed_query", None)) else "document"
        return await self._get(tuple(texts), mode)

    async def _get(self, texts: tuple[str, ...], mode: str) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))
        loop = asyncio.get_running_loop()
        futures: list[asyncio.Future[_Completed]] = []
        async with self._lock:
            for text in texts:
                key = (mode, text)
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    future = loop.create_future()
                    future.set_result(_Completed(cached, None, None))
                else:
                    future = self._pending.get(key)
                    if future is None:
                        future = loop.create_future()
                        # Canceled callers cannot cancel a shared future.
                        future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
                        self._pending[key] = future
                        self._queue.append(key)
                futures.append(future)
            if self._queue and not self._dispatching:
                self._dispatching = True
                asyncio.create_task(self._dispatch())
        result = await asyncio.gather(*(asyncio.shield(fut) for fut in futures))
        seen: set[object] = set()
        requests = 0
        inputs: int | None = None
        outputs: int | None = None
        for value in result:
            if value.batch_id is None or value.batch_id in seen:
                continue
            seen.add(value.batch_id)
            usage = value.usage
            if usage is None:
                continue
            requests += usage.requests
            if usage.input_tokens is not None:
                inputs = (inputs or 0) + usage.input_tokens
            if usage.output_tokens is not None:
                outputs = (outputs or 0) + usage.output_tokens
        return EmbeddingResult(vectors=tuple(item.vector for item in result),
                               usage=InferenceUsage(requests=requests, input_tokens=inputs, output_tokens=outputs))

    async def _dispatch(self) -> None:
        # One scheduler per wrapper, and a single batch window for concurrent callers.
        await asyncio.sleep(self.coalesce_ms / 1000 if self.coalesce_ms > 0 else 0)
        try:
            while True:
                async with self._lock:
                    if not self._queue:
                        break
                    mode = self._queue[0][0]
                    batch = [key for key in self._queue if key[0] == mode][:self.max_batch_size]
                    selected = set(batch)
                    self._queue = [key for key in self._queue if key not in selected]
                unique = tuple(key[1] for key in batch)
                batch_id = object()
                try:
                    if batch[0][0] == "query" and callable(getattr(self._model, "embed_query", None)):
                        answer = await self._model.embed_query(unique)
                    else:
                        answer = await self._model.embed(unique)
                    if len(answer.vectors) != len(batch):
                        raise ValueError("Embedding provider returned the wrong number of vectors")
                    vectors = [tuple(float(x) for x in vector) for vector in answer.vectors]
                    if any(len(v) != self.profile.dimension or not all(math.isfinite(x) for x in v) for v in vectors):
                        raise ValueError("Embedding provider returned invalid vectors")
                    async with self._lock:
                        for key, vector in zip(batch, vectors, strict=True):
                            if self.cache_size:
                                self._cache[key] = vector
                                self._cache.move_to_end(key)
                                while len(self._cache) > self.cache_size:
                                    self._cache.popitem(last=False)
                            future = self._pending.pop(key, None)
                            if future is not None and not future.done():
                                future.set_result(_Completed(vector, batch_id, answer.usage))
                except BaseException as error:
                    async with self._lock:
                        for key in batch:
                            future = self._pending.pop(key, None)
                            if future is not None and not future.done():
                                future.set_exception(error)
        finally:
            async with self._lock:
                self._dispatching = False
                if self._queue:
                    self._dispatching = True
                    asyncio.create_task(self._dispatch())


__all__ = ["CoalescingEmbeddingModel"]
