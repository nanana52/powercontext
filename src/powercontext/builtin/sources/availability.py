# Copyright (c) 2026 OceanBase. Licensed under the Apache License, Version 2.0.
"""Durable scoped Source availability transitions, never generation evidence.

A transition is a new Source journal entry. Existing evidence, immutable artifact
revisions and historical citations are not overwritten or deleted. Replaying the
journal after a restart derives the same availability state.
"""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from powercontext.artifacts import ArtifactLineage
from powercontext.sources import AdapterSourceDefinition, SourceRef
from powercontext.sources.models import Source, SourceMaterialization

SOURCE_AVAILABILITY_EVENT_NAME = "source-availability-event"


class SourceAvailabilityChange(BaseModel):
    change_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    available: bool


class SourceAvailabilityEvent(Source):
    target_source_type: str
    target_source_id: str
    available: bool


class SourceAvailabilityAdapter:
    name = SOURCE_AVAILABILITY_EVENT_NAME
    input_class = SourceAvailabilityChange
    source_class = SourceAvailabilityEvent

    async def resolve(self, value: SourceAvailabilityChange, /) -> SourceAvailabilityEvent:
        SourceRef(source_type=value.source_type, source_id=value.source_id)
        return SourceAvailabilityEvent(
            name=value.change_id,
            materialization=SourceMaterialization.CAPTURED,
            target_source_type=value.source_type,
            target_source_id=value.source_id,
            available=value.available,
        )

    async def read(self, source: SourceAvailabilityEvent, /) -> SourceAvailabilityChange:
        return SourceAvailabilityChange(
            change_id=source.name,
            source_type=source.target_source_type,
            source_id=source.target_source_id,
            available=source.available,
        )


def availability_from_entries(entries: Iterable[object]) -> dict[tuple[str, str], bool]:
    """Fold append-only transitions in stable journal order."""
    states: dict[tuple[str, str], bool] = {}
    for entry in sorted(entries, key=lambda item: item.position):
        source = entry.source
        if isinstance(source, SourceAvailabilityEvent):
            key = (source.target_source_type, source.target_source_id)
            states[key] = source.available
    return states


def lineage_has_available_source(
    lineage: ArtifactLineage | None,
    states: dict[tuple[str, str], bool],
) -> bool:
    """An artifact is available when it retains at least one live direct Source.

    Unattributed explicit artifacts remain visible. A withdrawn supporting
    Source never becomes a valid citation simply because a hit exists in an
    index; the last supporting Source disappearing hides its descendants.
    """
    if lineage is None or not lineage.sources:
        return True
    return any(states.get((ref.source_type, ref.source_id), True) for ref in lineage.sources)


SOURCE_AVAILABILITY_ADAPTER = SourceAvailabilityAdapter()
SOURCE_AVAILABILITY_DEFINITION = AdapterSourceDefinition(SOURCE_AVAILABILITY_ADAPTER)

__all__ = [
    "SOURCE_AVAILABILITY_EVENT_NAME", "SourceAvailabilityChange", "SourceAvailabilityEvent",
    "SOURCE_AVAILABILITY_ADAPTER", "SOURCE_AVAILABILITY_DEFINITION", "availability_from_entries",
    "lineage_has_available_source",
]
