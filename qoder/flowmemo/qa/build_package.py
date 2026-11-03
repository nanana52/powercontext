#!/usr/bin/env python3
"""Rebuild the submission package and write its checksum outside the archive.

A checksum stored inside the archive it describes is self-referential, so the
digest goes to `<archive>.sha256` next to it.

Usage: python qa/build_package.py
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path

import zipfile

BASE = Path(__file__).resolve().parents[1]
# `evidence/` is kept: it holds the desensitized live-acceptance record, which
# is submission proof rather than scratch output. Secrets never reach it — the
# harness masks scope ids and never writes a sessionId or token.
SKIP_DIRS = {"__pycache__", "data"}
SKIP_SUFFIX = (".pyc", ".bak")
ARCHIVE = BASE / "flowmemo-submission.zip"
# The sidecar of the *previous* build must not ride inside the new archive: its
# digest describes a package that no longer exists, so shipping it would be a
# stale proof that contradicts the checksum the submission actually advertises.
SIDECAR = Path(str(ARCHIVE) + ".sha256")


def collect() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(BASE):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path in (ARCHIVE, SIDECAR) or name.endswith(SKIP_SUFFIX) or ".qoder.site" in name:
                continue
            files.append(path)
    return sorted(files)


def main() -> int:
    files = collect()
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(BASE.parent).as_posix())
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    SIDECAR.write_text(f"{digest}  {ARCHIVE.name}\n", encoding="utf-8")
    print(f"entries={len(files)} bytes={ARCHIVE.stat().st_size} sha256={digest}")
    print(f"checksum written to {SIDECAR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
