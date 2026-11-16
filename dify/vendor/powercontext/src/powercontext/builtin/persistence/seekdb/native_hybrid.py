# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.
"""Single-statement native seekdb FTS + ANN Memory candidate retrieval.

The current Memory head is validated by the service; the returned revision is
anchored to that validated head rather than stale projection row revisions.
"""
from __future__ import annotations

from sqlalchemy import bindparam, text
from pyobvector import VECTOR

from powercontext.builtin.artifacts.memory import (
    CapabilityNotSupportedError, MemorySearchChannels, MemorySearchRequest,
)
from powercontext.builtin.artifacts.memory.canonical import validate_embedding
from powercontext.builtin.persistence.memory_index import memory_channel_hits
from powercontext.builtin.persistence.tags import memory_tag_sql, memory_tag_parameters


def _tag_sql(alias: str, has_filter: bool) -> str:
    return memory_tag_sql(alias) if has_filter else ''


async def seekdb_hybrid_channels(connection, scope_id: str, request: MemorySearchRequest, vector_index):
    """Return ordered FTS and ANN channels from exactly one candidate SQL.

    Tag filtering and per-channel candidate LIMIT execute on the database side;
    no application-side text/vector matching is used.
    """
    if request.query_vector is None or request.embedding_profile != vector_index.profile:
        raise CapabilityNotSupportedError('embedding-profile')
    # Match existing capability and current-head guarantees. These are metadata
    # validation queries, not candidate retrieval SQL.
    if not await vector_index.vector_complete(connection, scope_id, request.memories, vector_index.profile):
        raise CapabilityNotSupportedError('vector')

    has_tags = request.tag_filter is not None
    fts_tags = _tag_sql('f', has_tags)
    vector_tags = _tag_sql('m', has_tags)
    ann = '' if has_tags else ' APPROXIMATE'
    # The vector CTE deliberately keeps the ANN scan on the vector table. Joining
    # current-head rows before the ANN top-k can prevent the VECTOR INDEX scan.
    sql = f"""
    WITH fts_candidates AS (
        SELECT f.memory_artifact_id, f.head_revision, f.entry_id, f.entry_version_id,
               v.text, MATCH(f.searchable_text) AGAINST (:fts_query) AS metric
        FROM pc_memory_entry_heads AS f FORCE INDEX (ix_pc_memory_entry_heads_fts)
        JOIN pc_memory_entry_versions AS v
          ON v.scope_id = f.scope_id
         AND v.memory_artifact_id = f.memory_artifact_id
         AND v.entry_version_id = f.entry_version_id
        WHERE f.scope_id = :scope_id
          AND f.memory_artifact_id IN :memory_artifact_ids
          AND MATCH(f.searchable_text) AGAINST (:fts_query)
          {fts_tags}
        ORDER BY metric DESC, f.memory_artifact_id, f.entry_id, f.entry_version_id
        LIMIT :candidate_limit
    ),
    vector_candidates AS (
        SELECT m.memory_artifact_id, m.head_revision, m.entry_id, m.entry_version_id,
               v.text, l2_distance(m.embedding, :query_vector) AS metric
        FROM pc_memory_vector_entries AS m
        JOIN pc_memory_entry_versions AS v
          ON v.scope_id = m.scope_id
         AND v.memory_artifact_id = m.memory_artifact_id
         AND v.entry_version_id = m.entry_version_id
        WHERE m.scope_id = :scope_id
          AND m.memory_artifact_id IN :memory_artifact_ids
          {vector_tags}
        ORDER BY l2_distance(m.embedding, :query_vector){ann}
        LIMIT :candidate_limit
    )
    SELECT streams.channel, streams.memory_artifact_id, streams.head_revision,
           streams.entry_id, streams.entry_version_id, streams.text, streams.distance
    FROM (
        SELECT 0 AS channel_ord, 'fts' AS channel, f.memory_artifact_id, f.head_revision,
               f.entry_id, f.entry_version_id, f.text, NULL AS distance,
               -f.metric AS sort_metric
        FROM fts_candidates AS f
        UNION ALL
        SELECT 1 AS channel_ord, 'vector' AS channel, m.memory_artifact_id, m.head_revision,
               m.entry_id, m.entry_version_id, m.text, m.metric AS distance,
               m.metric AS sort_metric
        FROM vector_candidates AS m
    ) AS streams
    ORDER BY streams.channel_ord, streams.sort_metric,
             streams.memory_artifact_id, streams.entry_id, streams.entry_version_id
    """
    statement = text(sql).bindparams(
        bindparam('memory_artifact_ids', expanding=True),
        bindparam('query_vector', type_=VECTOR(vector_index.profile.dimension)),
    )
    if has_tags:
        statement = statement.bindparams(
            bindparam('tag_keys', expanding=True), bindparam('tag_hashes', expanding=True)
        )
    params = {
        'scope_id': scope_id,
        'memory_artifact_ids': tuple(memory.artifact_id for memory in request.memories),
        'fts_query': request.analyzed_query,
        'query_vector': validate_embedding(request.query_vector, dimension=vector_index.profile.dimension),
        'candidate_limit': request.candidate_limit,
        **memory_tag_parameters(request.tag_filter),
    }
    rows = tuple((await connection.execute(statement, params)).mappings())
    return MemorySearchChannels(
        fts=memory_channel_hits((row for row in rows if row['channel'] == 'fts'), request.memories),
        vector=memory_channel_hits((row for row in rows if row['channel'] == 'vector'), request.memories),
    )
