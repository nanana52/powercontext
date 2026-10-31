## What this PR contains

Native C++ seekdb competition branch implementing and extending existing SQL engine functionality:

- AI function behavior (prompt, complete, embedding, rerank and provider handling).
- Local file SQL support for CSV, JSONL/JSON, bounded Parquet decoding, `glob()`.
- Native SQL aggregate/WHERE/JOIN through seekdb's own execution engine.
- CSV type inference, duplicate header handling, `DESCRIBE SELECT * FROM read_*`.
- `COPY` export/import, header and NULL text options.
- File access session opt-in shim and `secure_file_priv` checks.

## Evidence

- Compiled native seekdb binary, with 42/42 isolated local SQL checks passing on port 2891 (`FILE_OFFICIAL_COMPAT_SQL_PASS`).
- 10/10 isolated session security checks passing on port 2890 (`FILE_SQL_SECURITY_PASS`).
- Native parser/C++ regression tests for all these incremental patches.
- Test traces and full source snapshot in the PowerContext competition evidence repo at commit `6303fde6`.

## Known limitations (important)

- Current File SQL implementation rewrites to bounded `JSON_TABLE` values (~2 MiB); this is **not a true streaming scan** and lacks engine-level rescan/projection pushdown.
- `enable_file_sql` is an SQL per-session compatibility shim, **not** a registered OceanBase/seekdb system variable.
- **Asynchronous AI Generated Columns are not implemented** (native DDL, persistent job definitions, change stream, backfill/retry, idempotency).
- AI model/provider functionality needs full official mock-service verification; local smoke alone does not prove all hidden scenarios.
- Local test success does not imply all competition scoring criteria pass.

This is submitted for incremental upstream feedback. There are no external SQL execution engines in this implementation.
