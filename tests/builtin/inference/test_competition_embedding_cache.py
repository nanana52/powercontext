"""Contest: concurrency, cancellation, provider failure and scoped vector keys."""
import asyncio

import pytest

from powercontext.builtin.artifacts.memory.models import EmbeddingProfile
from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.singleflight_cache import (
    SingleFlightEmbeddingModel, bind_embedding_scope,
)


class FakeEmbedder:
    profile = EmbeddingProfile(profile_id='p', model='fake', dimension=2)

    def __init__(self):
        self.calls = []
        self.fail_once = False

    async def embed(self, texts):
        self.calls.append(('document', texts))
        await asyncio.sleep(.025)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError('provider unavailable')
        return EmbeddingResult(vectors=tuple((float(len(t)), 1.0) for t in texts), usage=InferenceUsage(requests=1))

    async def embed_query(self, texts):
        self.calls.append(('query', texts))
        await asyncio.sleep(.025)
        return EmbeddingResult(vectors=tuple((float(len(t)), 2.0) for t in texts), usage=InferenceUsage(requests=1))


def test_singleflight_order_and_cache():
    asyncio.run(_test_singleflight_order_and_cache())


async def _test_singleflight_order_and_cache():
    provider = FakeEmbedder()
    cache = SingleFlightEmbeddingModel(provider)
    with bind_embedding_scope('tenant-a'):
        first, second = await asyncio.gather(cache.embed(('one', 'two', 'one')), cache.embed(('two', 'one')))
        assert first.vectors == ((3., 1.), (3., 1.), (3., 1.))
        assert second.vectors == ((3., 1.), (3., 1.))
        assert provider.calls == [('document', ('one', 'two'))]
        cached = await cache.embed(('two',))
        assert cached.usage.requests == 0
    assert len(provider.calls) == 1


def test_query_and_scope_are_isolated():
    asyncio.run(_test_query_and_scope_are_isolated())


async def _test_query_and_scope_are_isolated():
    provider = FakeEmbedder()
    cache = SingleFlightEmbeddingModel(provider)
    with bind_embedding_scope('tenant-a'):
        assert (await cache.embed_query(('x',))).vectors == ((1., 2.),)
        assert (await cache.embed(('x',))).vectors == ((1., 1.),)
    with bind_embedding_scope('tenant-b'):
        await cache.embed(('x',))
    assert len(provider.calls) == 3


def test_waiter_cancel_does_not_cancel_shared_provider():
    asyncio.run(_test_waiter_cancel_does_not_cancel_shared_provider())


async def _test_waiter_cancel_does_not_cancel_shared_provider():
    provider = FakeEmbedder()
    cache = SingleFlightEmbeddingModel(provider)
    with bind_embedding_scope('tenant-a'):
        waiter = asyncio.create_task(cache.embed(('shared',)))
        survivor = asyncio.create_task(cache.embed(('shared',)))
        await asyncio.sleep(.005)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert (await survivor).vectors == ((6., 1.),)
    assert len(provider.calls) == 1


def test_failure_not_cached_and_ttl_expiry():
    asyncio.run(_test_failure_not_cached_and_ttl_expiry())


async def _test_failure_not_cached_and_ttl_expiry():
    provider = FakeEmbedder()
    provider.fail_once = True
    cache = SingleFlightEmbeddingModel(provider, ttl_seconds=.02)
    with bind_embedding_scope('tenant-a'):
        with pytest.raises(RuntimeError):
            await cache.embed(('retry',))
        assert (await cache.embed(('retry',))).vectors == ((5., 1.),)
        await asyncio.sleep(.03)
        await cache.embed(('retry',))
    assert len(provider.calls) == 3
