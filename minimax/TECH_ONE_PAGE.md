# One-page technical design

**Purpose:** SDD-SHIP-2026 fixes a small shipping price boundary defect
while demonstrating context selection and resumable development state.

### Interfaces and data flow
`bash minimax/run.sh` -> Python `sdd.run` -> embedded **seekdb SQL**
(import/version active spec, code and tests; SELECT returns actual sources) ->
task-specific prompt -> **MiniMax-M2.5 real HTTP API** -> model-suggested
old/new source code line -> validated one-line patch -> unchanged Python unit
tests -> **PowerContext 1.4.1 Server** write Memory -> restart Server ->
read same Scope and reuse real previous task state.

- seekdb: embedded `pylibseekdb` runtime, MySQL-compatible `test.sdd_docs`.
  Four source documents; digest, kind, path and actual content are stored.
  Query is executed before prompt construction. `specs/archived_policy.md`
  is explicitly excluded from active imports.
- PowerContext: local HTTP, SQLite persistence in `.local/powercontext`,
  explicit `/v1/memory/remember`, `/v1/memory/search`, `/v1/context/prepare`.
  Scoped real memory is read after Server process restart and inserted into
  the resumed task context saved to evidence.
- MiniMax: `MINIMAX_API_KEY` from environment only, POST to official
  text chatcompletion_v2 endpoint; logs user task, actual fetched
  context, model response and applied diff, excluding private reasoning.
- Tests: `tests.test_target` fails before due only to boundary assertions;
  `tests.test_regression` passes before and after; all pass after edit.
- Spec version experiment: reimport same source key with additional
  `SPEC-SHIP-006` note, select SQL again and verify updated text; restore
  authoritative spec afterward.

### Limitations
The complete evidence is generated only by a **real successful run**.
No provider keys, simulated MiniMax edits, fabricated passing logs, or
unverified screenshots are included in this submission starter.
The first run depends on Internet package downloads, actual API eligibility,
and a compatible Linux runtime for embedded seekdb.
