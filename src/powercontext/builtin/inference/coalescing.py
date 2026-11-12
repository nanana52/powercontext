# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Cancellation-safe cross-call embeddings with concurrent independent batches.

Every distinct text has one pending Future until its provider batch resolves.
The batch scheduler is separate from provider work: a blocked batch must not
hold up unrelated requests.  Successful vectors alone enter the LRU cache.
"""
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
        if type(max_batch_size) is not int or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a nonnegative integer")
        if type(coalesce_ms) not in (int, float) or not math.isfinite(coalesce_ms) or coalesce_ms < 0:
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
        self._workers: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    async def embed(self, texts, /) -> EmbeddingResult:
        return await self._get(tuple(texts), "document")

    async def embed_query(self, texts, /) -> EmbeddingResult:
        # Asymmetric embedding providers produce different query/document vectors.
        mode = "query" if callable(getattr(self._model, "embed_query", None)) else "document"
        return await self._get(tuple(texts), mode)

    async def _get(self, texts: tuple[str, ...], mode: str) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))
        loop = asyncio.get_running_loop()
        pending: list[asyncio.Future[_Completed]] = []
        async with self._lock:
            for text in texts:
                key = (mode, text)
                vector = self._cache.get(key)
                if vector is not None:
                    self._cache.move_to_end(key)
                    future: asyncio.Future[_Completed] = loop.create_future()
                    future.set_result(_Completed(vector, None, None))
                else:
                    future = self._pending.get(key)
                    if future is None:
                        future = loop.create_future()
                        # An abandoned/cancelled caller must not leak an unobserved error.
                        future.add_done_callback(self._consume_unobserved_error)
                        self._pending[key] = future
                        self._queue.append(key)
                pending.append(future)
            if self._queue and not self._dispatching:
                self._dispatching = True
                self._start_task(self._dispatch())

        # Shield each shared Future. Cancellation affects only this caller.
        completed = await asyncio.gather(*(asyncio.shield(fut) for fut in pending))
        counted: set[object] = set()
        requests = 0
        input_tokens: int | None = None
        output_tokens: int | None = None
        for item in completed:
            if item.batch_id is None or item.batch_id in counted:
                continue
            counted.add(item.batch_id)
            if item.usage is None:
                continue
            requests += item.usage.requests
            if item.usage.input_tokens is not None:
                input_tokens = (input_tokens or 0) + item.usage.input_tokens
            if item.usage.output_tokens is not None:
                output_tokens = (output_tokens or 0) + item.usage.output_tokens
        return EmbeddingResult(
            vectors=tuple(item.vector for item in completed),
            usage=InferenceUsage(
                requests=requests, input_tokens=input_tokens, output_tokens=output_tokens,
            ),
        )

    @staticmethod
    def _consume_unobserved_error(future: asyncio.Future[_Completed]) -> None:
        if not future.cancelled():
            future.exception()

    def _start_task(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._workers.add(task)
        task.add_done_callback(self._workers.discard)
        task.add_done_callback(self._consume_unobserved_task_error)

    @staticmethod
    def _consume_unobserved_task_error(task: asyncio.Task[None]) -> None:
        # Provider failures are delivered to shared futures; internal dispatcher
        # errors must also be observed rather than logged on a GC cycle.
        if not task.cancelled():
            task.exception()

    async def _dispatch(self) -> None:
        """Dispatch one queue snapshot per coalescing window.

        All bounded, mode-specific batches from the same snapshot start
        together. New keys receive a fresh window; duplicates continue to
        join their existing in-flight Futures.
        """
        undispatched: set[tuple[str, str]] = set()
        try:
            while True:
                # sleep(0) still yields one turn to concurrent callers.
                await asyncio.sleep(self.coalesce_ms / 1000)
                async with self._lock:
                    if not self._queue:
                        return
                    queued = self._queue
                    self._queue = []

                undispatched = set(queued)
                by_mode: dict[str, list[tuple[str, str]]] = {}
                for key in queued:
                    by_mode.setdefault(key[0], []).append(key)
                for keys in by_mode.values():
                    for start in range(0, len(keys), self.max_batch_size):
                        batch = keys[start:start + self.max_batch_size]
                        self._start_task(self._run_batch(batch))
                        undispatched.difference_update(batch)
                undispatched.clear()
        except BaseException as error:
            # A dispatcher failure must not leave any queued caller stranded.
            # Already-started batches remain owned by their provider workers.
            async with self._lock:
                for key in (*undispatched, *self._queue):
                    future = self._pending.pop(key, None)
                    if future is not None and not future.done():
                        future.set_exception(error)
                self._queue.clear()
            if isinstance(error, asyncio.CancelledError):
                raise
        finally:
            async with self._lock:
                self._dispatching = False
                if self._queue:
                    self._dispatching = True
                    self._start_task(self._dispatch())

    async def _run_batch(self, batch: list[tuple[str, str]]) -> None:
        unique = tuple(key[1] for key in batch)
        batch_id = object()
        try:
            if batch[0][0] == "query" and callable(getattr(self._model, "embed_query", None)):
                answer = await self._model.embed_query(unique)
            else:
                answer = await self._model.embed(unique)
            if len(answer.vectors) != len(batch):
                raise ValueError("Embedding provider returned an unexpected vector count")
            vectors = tuple(tuple(float(x) for x in vector) for vector in answer.vectors)
            if any(
                len(vector) != self.profile.dimension or not all(math.isfinite(x) for x in vector)
                for vector in vectors
            ):
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


__all__ = ["CoalescingEmbeddingModel"]
