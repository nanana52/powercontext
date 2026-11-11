"""Source contract: hybrid native candidates must share exactly one execute."""
from pathlib import Path


def test_atomic_seekdb_hybrid_uses_one_statement_with_scoped_native_indices():
    root = Path(__file__).resolve().parents[3]
    code = (root / 'src/powercontext/builtin/persistence/oceanbase/atomic_memory_index.py').read_text()
    start = code.index('    async def _channels(')
    end = code.index('\n\n__all__', start)
    body = code[start:end]
    assert body.count('await connection.execute(') == 1
    assert 'WITH ' in body and ' UNION ALL ' in body
    assert 'MATCH(searchable_text) AGAINST' in body
    assert 'APPROXIMATE ' in body
    assert body.count('scope_id = :scope_id') >= 2
    assert 'profile_fingerprint = :profile' in body
