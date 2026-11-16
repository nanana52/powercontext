# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Persistent scope-local evidence DAG and native memory availability propagation."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy import text

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.sources import SourceRef
from powercontext.builtin.sources import validate_scope_id
from powercontext.builtin.runtime.models import GetMemoryEntryRequest


class SourceLifecycleError(ValueError):
    """An invalid lifecycle operation or unavailable evidence reference."""


class SourceLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    revision: StrictInt = Field(gt=0)
    sequence: StrictInt = Field(gt=0)
    available: StrictBool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Lifecycle event values must not be blank")
        return value


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pc_source_lifecycle_nodes (
    scope_id VARCHAR(255) NOT NULL,
    node_id VARCHAR(255) NOT NULL,
    kind VARCHAR(16) NOT NULL,
    reference_json TEXT NOT NULL,
    parents_json TEXT NOT NULL,
    support_policy VARCHAR(8) NOT NULL,
    source_revision INTEGER NOT NULL,
    event_sequence INTEGER NOT NULL,
    last_event_json TEXT NOT NULL,
    available INTEGER NOT NULL,
    PRIMARY KEY (scope_id, node_id)
)
"""


class SourceLifecycleApplication:
    def __init__(self, runtime) -> None:
        self._runtime = runtime
        self._search = runtime._topic_memory_search
        if self._search is not None:
            runtime._topic_memory_search = self._topic_search

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self._runtime, validate_scope_id(scope_id))

    async def _topic_search(self, scope_id: str, query: str, **kwargs):
        assert self._search is not None
        result = await self._search(scope_id, query, **kwargs)
        database = self._runtime._records()._database
        async with database.transaction() as connection:
            await connection.execute(text(_CREATE_TABLE))
            rows = (await connection.execute(
                text("SELECT reference_json FROM pc_source_lifecycle_nodes WHERE scope_id = :scope "
                     "AND kind = 'topic' AND available = 0"), {"scope": scope_id}
            )).all()
        unavailable = {json.loads(row[0])["artifact_id"] for row in rows}
        if not unavailable:
            return result
        return result.model_copy(update={
            "hits": tuple(hit for hit in result.hits if hit.artifact_ref.artifact_id not in unavailable)
        })


class ScopedSourceLifecycle:
    def __init__(self, runtime, scope_id: str) -> None:
        self._runtime = runtime
        self.scope_id = scope_id

    @property
    def _database(self):
        return self._runtime._records()._database

    async def _load(self):
        async with self._database.transaction() as connection:
            await connection.execute(text(_CREATE_TABLE))
            rows = (await connection.execute(
                text("SELECT node_id, kind, reference_json, parents_json, support_policy, "
                     "source_revision, event_sequence, last_event_json, available "
                     "FROM pc_source_lifecycle_nodes WHERE scope_id=:scope ORDER BY node_id"),
                {"scope": self.scope_id},
            )).mappings().all()
        return {str(r['node_id']): {
            'kind': r['kind'], 'reference': json.loads(r['reference_json']),
            'parents': tuple(json.loads(r['parents_json'])), 'policy': r['support_policy'],
            'revision': int(r['source_revision']), 'sequence': int(r['event_sequence']),
            'last_event': json.loads(r['last_event_json']), 'available': bool(r['available']),
        } for r in rows}

    @staticmethod
    def _states(nodes):
        states = {}
        def available(node_id, stack):
            if node_id in states:
                return states[node_id]
            if node_id in stack or node_id not in nodes:
                raise SourceLifecycleError("Invalid or cyclic parent graph")
            node = nodes[node_id]
            if node['kind'] == 'source':
                state = node['available']
            else:
                support = [available(parent, (*stack, node_id)) for parent in node['parents']]
                state = all(support) if node['policy'] == 'all' else any(support)
            states[node_id] = state
            return state
        for node_id in nodes:
            available(node_id, ())
        return states

    async def _persist_states(self, states):
        async with self._database.transaction() as connection:
            for key, available in states.items():
                await connection.execute(text("UPDATE pc_source_lifecycle_nodes SET available=:enabled "
                                              "WHERE scope_id=:scope AND node_id=:node"),
                                         {'enabled': int(available), 'scope': self.scope_id, 'node': key})

    async def _sync_native(self, nodes, states):
        if not any(record['kind'] == 'memory' for record in nodes.values()):
            return
        # The lifecycle record is the durable intent. Reconcile the native memory state
        # on every registration/event, including an event replay after partial failure.
        async with self._runtime._context(self.scope_id) as context:
            service = context.artifacts.memory
            current = await service.head(context.artifacts.memory_artifact_id)
            current_entries = {e.entry_id: e for e in await service.entries(current)}
            for node_id, record in nodes.items():
                if record['kind'] != 'memory':
                    continue
                cite = MemoryCitation.model_validate(record['reference'])
                entry = current_entries.get(cite.entry_id)
                if entry is None or entry.entry_version_id != cite.entry_version_id:
                    raise SourceLifecycleError(f"Memory evidence version changed: {node_id}")
                desired = 'active' if states[node_id] else 'inactive'
                manifest_item = next(
                    (
                        item for item in current.content.manifest.entries
                        if item.entry_id == cite.entry_id
                    ),
                    None,
                )
                if (
                    manifest_item is None
                    or manifest_item.entry_version_id != cite.entry_version_id
                ):
                    raise SourceLifecycleError(
                        f"Memory manifest changed: {node_id}"
                    )
                if manifest_item.state == desired:
                    continue
                if desired == 'active':
                    current = await service.reactivate(current, entries=(entry,), reason='source-lifecycle-restore')
                else:
                    current = await service.forget(current, entries=(entry,), reason='source-lifecycle-withdrawal')
                current_entries = {e.entry_id: e for e in await service.entries(current)}

    async def _reconcile(self):
        nodes = await self._load()
        states = self._states(nodes)
        await self._persist_states(states)
        await self._sync_native(nodes, states)
        return sorted(node for node, state in states.items() if state)

    async def _register(self, node_id, kind, reference, parents, policy, revision=0):
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError('Invalid node identity')
        if kind != 'source':
            if (policy not in ('all', 'any') or not isinstance(parents, (tuple, list)) or
                not parents or any(not isinstance(p, str) or not p.strip() for p in parents) or
                len(set(parents)) != len(parents)):
                raise SourceLifecycleError('Invalid dependency policy or parents')
        else:
            policy, parents = 'all', ()
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._load()
            if any(p == node_id or p not in nodes for p in parents):
                raise SourceLifecycleError('Parent not registered or cyclic dependency')
            value = reference.model_dump(mode='json')
            if node_id in nodes:
                previous = nodes[node_id]
                if any((previous[kind_key] != value_key) for kind_key, value_key in (
                    ('kind', kind), ('reference', value), ('parents', tuple(parents)),
                    ('policy', policy), ('revision', revision),
                )):
                    raise SourceLifecycleError('Node identity already registered with another binding')
                return await self._reconcile()
            try:
                if kind == 'source':
                    assert isinstance(reference, SourceRef)
                    if type(revision) is not int or revision < 1:
                        raise SourceLifecycleError('Source revision must be positive')
                    await self._runtime.records.for_scope(self.scope_id).get_source(
                        reference.source_type, reference.source_id)
                elif kind == 'memory':
                    assert isinstance(reference, MemoryCitation)
                    await self._runtime.memory.for_scope(self.scope_id).get(
                        GetMemoryEntryRequest(citation=reference))
                else:
                    assert isinstance(reference, ArtifactRef)
                    if reference.family != 'topic-memory':
                        raise SourceLifecycleError('Topic reference must be a topic-memory artifact')
                    await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
                        reference.family, reference.artifact_id, reference.revision)
            except SourceLifecycleError:
                raise
            except Exception as error:
                raise SourceLifecycleError('Lifecycle reference is not readable in this scope') from error
            async with self._database.transaction() as connection:
                await connection.execute(text(
                    "INSERT INTO pc_source_lifecycle_nodes (scope_id,node_id,kind,reference_json,parents_json,"
                    "support_policy,source_revision,event_sequence,last_event_json,available) VALUES "
                    "(:scope,:node,:kind,:reference,:parents,:policy,:revision,0,'null',1)"), {
                    'scope': self.scope_id, 'node': node_id, 'kind': kind,
                    'reference': json.dumps(value, sort_keys=True),
                    'parents': json.dumps(list(parents)), 'policy': policy, 'revision': revision,
                })
            return await self._reconcile()

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int):
        if not isinstance(source_ref, SourceRef):
            raise SourceLifecycleError('Invalid Source reference')
        return await self._register(node_id, 'source', source_ref, (), 'all', revision)

    async def register_memory(
        self, node_id: str, citation: MemoryCitation, *, parents: tuple[str, ...], policy: Literal['all','any']
    ):
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError('Invalid Memory citation')
        return await self._register(node_id, 'memory', citation, parents, policy)

    async def register_topic(
        self, node_id: str, reference: ArtifactRef, *, parents: tuple[str, ...], policy: Literal['all','any']
    ):
        if not isinstance(reference, ArtifactRef):
            raise SourceLifecycleError('Invalid Topic reference')
        return await self._register(node_id, 'topic', reference, parents, policy)

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError('Invalid lifecycle event')
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._load()
            previous = nodes.get(event.node_id)
            if previous is None or previous['kind'] != 'source' or previous['revision'] != event.revision:
                raise SourceLifecycleError('Unknown Source or revision mismatch')
            serialized = event.model_dump(mode='json')
            if event.sequence < previous['sequence'] or (
                event.sequence == previous['sequence'] and serialized != previous['last_event']
            ):
                raise SourceLifecycleError('Stale or conflicting Source event')
            if event.sequence > previous['sequence']:
                async with self._database.transaction() as connection:
                    await connection.execute(text(
                        'UPDATE pc_source_lifecycle_nodes SET available=:state, event_sequence=:sequence, '
                        'last_event_json=:event WHERE scope_id=:scope AND node_id=:node'), {
                        'state': int(event.available), 'sequence': event.sequence,
                        'event': json.dumps(serialized, sort_keys=True), 'scope': self.scope_id, 'node': event.node_id,
                    })
            return await self._reconcile()

    async def resolve(self, node_id: str, *, purpose: Literal['audit','generation']):
        if purpose not in ('audit', 'generation'):
            raise SourceLifecycleError('Unknown evidence usage purpose')
        nodes = await self._load()
        if node_id not in nodes:
            raise SourceLifecycleError('Unknown evidence node')
        if purpose == 'generation' and not self._states(nodes)[node_id]:
            raise SourceLifecycleError('Source evidence is currently unavailable for generation')
        node = nodes[node_id]
        kind = node['kind']
        cls = {'source': SourceRef, 'memory': MemoryCitation, 'topic': ArtifactRef}[kind]
        return cls.model_validate(node['reference'])


__all__ = ['SourceLifecycleError', 'SourceLifecycleEvent', 'SourceLifecycleApplication']
