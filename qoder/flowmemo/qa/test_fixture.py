#!/usr/bin/env python3
"""Checks that the synthetic reference fixture is internally self-consistent.
This is NOT an application test or evidence of PowerContext integration.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / 'fixtures/demo_notes.json').read_text(encoding='utf-8'))
assert data['fixture'] == 'fictional_work_demo'
assert len(data['notes']) == data['expected']['notes']
lines = [line.strip() for entry in data['notes'] for line in entry['content'].splitlines()]
for label, key in [('待办', 'tasks'), ('决定', 'decisions'), ('风险', 'risks')]:
    actual = sum(line.startswith(label + '：') for line in lines)
    expected = data['expected'][key]
    assert actual == expected, f'{label}: {actual} != {expected}'
assert len(set(n['id'] for n in data['notes'])) == len(data['notes'])
print('FIXTURE_CONTRACT_PASS notes=2 tasks=4 decisions=2 risks=2')
