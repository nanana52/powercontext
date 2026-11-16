from __future__ import annotations
import asyncio
from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, RememberMemoryRequest, open_builtin_runtime
from powercontext.builtin.scope import ScopeDraft

class Provider:
    profile=EmbeddingProfile(profile_id="runtime-opt-in",model="offline",dimension=2)
    def __init__(self):self.calls=[]
    async def embed(self,texts):
        self.calls.append(tuple(texts))
        return EmbeddingResult(vectors=tuple((1.0,0.0) for _ in texts),usage=InferenceUsage(requests=1))

def test_runtime_preserves_unwrapped_model_and_honors_explicit_coalescing():
    async def run():
        for wrapped,expected in [(False,2),(True,1)]:
            base=Provider()
            model=CoalescingEmbeddingModel(base,coalesce_ms=0) if wrapped else base
            async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig()),embedding_model=model) as runtime:
                for i in range(2):
                    scope=await runtime.scopes.create(ScopeDraft(title="Scope",summary="compatibility",idempotency_key=str(i)))
                    await runtime.memory.for_scope(scope.scope_id).remember(RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact",text="same text"),)))
            assert len(base.calls)==expected,(wrapped,base.calls)
    asyncio.run(run())
