# SeekDB 2026 — verified submission and development remainder

## Snapshot
- User's fork (pushed): https://github.com/nanana52/seekdb
- Branch: `2026-competition-ai-functions`
- Previously verified SQL: 42/42 File SQL local checks; 10/10 security local checks.
- User's PowerContext evidence backup: https://github.com/nanana52/powercontext (branch `2026-competition-ecosystem`).
- Verified native source commit before this finalization script: `053002e`.
- One-shot script produces an upstream PR, if GitHub allows the account to create one.
- The user still needs to enter the actual repository URL/PR or branch+commit in the **competition platform**; this script cannot authenticate to that separate website.

## Additional package content
`ob_file_stream_reader.h`: separate C++14 bounded-memory file-reader primitive.
It supports:
- CSV with multiline quoted fields, duplicated headers, CRLF and UTF-8 validation;
- Flat JSONL validation;
- fixed-size batches and rescan;
- file identity change checks and root-constrained canonical paths;
- >5 MiB fixture with 80,000 data rows, exceeding the previous 2 MiB in-memory limit.

This source module is a *prototype* stored as competition evidence, NOT connected
to the engine's FileScan operator. **Do not claim it implements streaming SQL.**

`verify_ai_mock_2891.py`: optional actual SQL mock HTTP test on existing
isolated port 2891; reports real results without hiding failures.

## Still NOT finished (not solved by this package)
1. **FileScan physical SQL operator**: optimizer plan generation, `open()`,
   `get_next_row/batch`, `rescan()`, projection pushdown and file identity
   consistency across planning and execution. Required for the file topic's
   streaming rule; current parser JSON_TABLE path is not compliant.
2. **Registered `enable_file_sql` system variable**, security integration
   and full hidden test compatibility; current compatibility shim is not
   a real registered sysvar.
3. **AI Generated Column (50 points)**: grammar and DDL resolver,
   durable schema metadata with dependencies, async change stream plugin,
   committed-order invalidation, background model requests, retries,
   pending/failed statuses, idempotent restart recovery and safety.
4. **AI Functions**: the official Mock AI Service protocol test, provider
   cases and real cross-row batching need independent proof.
5. **Competition platform submission**: GitHub PR is not the same as
   submitting required repository/branch/SHA fields to the contest portal.

This package is honest about remaining work and will not report 160/160
or claim unimplemented features passed.
