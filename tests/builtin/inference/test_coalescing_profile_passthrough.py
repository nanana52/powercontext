from __future__ import annotations
import asyncio
from powercontext.builtin.inference import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel


def test_wrapper_exposes_profile_without_reinterpreting_provider_metadata():
    async def run():
        class Provider:
            profile = object()
            def __init__(self): self.calls = []
            async def embed(self, texts):
                self.calls.append(tuple(texts))
                return EmbeddingResult(vectors=tuple((float(len(t)),) for t in texts),
                                       usage=InferenceUsage(requests=1, input_tokens=9))
        base = Provider()
        wrapped = CoalescingEmbeddingModel(base, coalesce_ms=0)
        assert wrapped.profile is base.profile
        result = await wrapped.embed(('alpha', 'beta', 'alpha'))
        assert result.vectors == ((5.0,), (4.0,), (5.0,))
        assert result.usage.requests == 1 and result.usage.input_tokens == 9
        cached = await wrapped.embed(('alpha',))
        assert cached.vectors == ((5.0,),) and cached.usage.requests == 0
        assert base.calls == [('alpha', 'beta')]
    asyncio.run(run())
