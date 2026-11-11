"""Contest: exact character positions and budget after formatting/citations."""
from powercontext.builtin.runtime.source_evidence import OriginalSourceCandidate, select_original_evidence
from powercontext.sources import SourceRef


def test_evidence_span_multibyte_and_budget():
    source = OriginalSourceCandidate(SourceRef(source_type='content', source_id='doc-1'),
                                     '背景。' * 70 + '2026年营业收入达到100亿元。' + '附注。' * 40)
    result = select_original_evidence('2026 营业收入', (source,), scope_id='alpha', max_bytes=512)
    assert result.content_bytes <= 512
    assert result.spans
    for ref, start, end in result.spans:
        assert source.text[start:end] in result.content
        assert ref.source_id == 'doc-1'
    assert 'Citation:' in result.content


def test_tiny_budget_and_no_overlap():
    source = OriginalSourceCandidate(SourceRef(source_type='content', source_id='x'), 'abc revenue ' * 70)
    empty = select_original_evidence('revenue', (source,), scope_id='alpha', max_bytes=64)
    assert empty.content == '' and empty.spans == ()
    result = select_original_evidence('revenue', (source,), scope_id='alpha', max_bytes=800)
    assert len(result.spans) <= 2
    assert result.content_bytes == len(result.content.encode('utf-8'))
