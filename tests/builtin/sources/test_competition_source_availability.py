"""Source event replay, last transition wins, direct dependency withdrawal."""
import asyncio
from types import SimpleNamespace

from powercontext.artifacts import ArtifactLineage
from powercontext.sources import SourceRef
from powercontext.builtin.sources.availability import (
    SourceAvailabilityAdapter, SourceAvailabilityChange,
    availability_from_entries, lineage_has_available_source,
)


def test_availability_event_replay_and_recovery():
    adapter = SourceAvailabilityAdapter()
    original = SourceRef(source_type="content", source_id="source-x")
    first = asyncio.run(adapter.resolve(SourceAvailabilityChange(
        change_id="change-1", source_type="content", source_id="source-x", available=False,
    )))
    second = asyncio.run(adapter.resolve(SourceAvailabilityChange(
        change_id="change-2", source_type="content", source_id="source-x", available=True,
    )))
    entries = (
        SimpleNamespace(position=2, source=second),
        SimpleNamespace(position=1, source=first),
    )
    assert availability_from_entries(entries)[("content", "source-x")]
    lineage = ArtifactLineage(sources=(original,))
    assert lineage_has_available_source(lineage, availability_from_entries(entries))
    assert not lineage_has_available_source(lineage, availability_from_entries((entries[1],)))


def test_shared_lineage_retains_available_support():
    a = SourceRef(source_type="content", source_id="a")
    b = SourceRef(source_type="content", source_id="b")
    lineage = ArtifactLineage(sources=(a, b))
    assert lineage_has_available_source(lineage, {("content", "a"): False})
    assert not lineage_has_available_source(lineage, {
        ("content", "a"): False, ("content", "b"): False,
    })
    assert lineage_has_available_source(ArtifactLineage(), {
        ("content", "a"): False, ("content", "b"): False,
    })
