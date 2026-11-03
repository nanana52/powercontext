#!/usr/bin/env python3
"""Non-destructive submission readiness audit; advisory, not official judging."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]

# The published page must be byte-identical to the source we ship, otherwise a
# reviewer testing the live site is not testing the submitted code.
def live_check() -> tuple[bool, bool]:
    ok = True
    submission = (BASE / "docs/SUBMISSION.md").read_text(encoding="utf-8")
    url = re.search(r"https?://[^\s)>`]+", submission)
    if not url:
        print("FAIL live: no site URL in docs/SUBMISSION.md")
        return False, False
    origin = url.group(0).rstrip("/")
    headers = {"Origin": origin, "Referer": origin + "/", "Cache-Control": "no-store"}

    def get(path: str) -> bytes:
        req = urllib.request.Request(origin + path, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read()

    html = get("/index.html").decode("utf-8", "replace")
    marker = re.search(r"js/app\.js\?v=([\w-]+)", html)
    local_html = (BASE / "dist/index.html").read_text(encoding="utf-8")
    local_marker = re.search(r"js/app\.js\?v=([\w-]+)", local_html)
    same_marker = bool(marker and marker.group(1) == (local_marker and local_marker.group(1)))
    print(f"{'PASS' if same_marker else 'FAIL'} live: app.js version marker {marker and marker.group(1)!r} == source {local_marker and local_marker.group(1)!r}")
    ok &= same_marker

    remote_ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))
    source_ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', local_html))
    missing = source_ids - remote_ids
    print(f"{'PASS' if not missing else 'FAIL'} live: all {len(source_ids)} source element ids published (missing={sorted(missing)})")
    ok &= not missing

    js = get(f"/js/app.js?v={marker.group(1) if marker else ''}")
    local_js = (BASE / "dist/js/app.js").read_bytes()
    same_js = hashlib.sha256(js).hexdigest() == hashlib.sha256(local_js).hexdigest()
    print(f"{'PASS' if same_js else 'FAIL'} live: app.js sha256 matches source ({len(js)} bytes served)")
    ok &= same_js

    pc_ready = False
    try:
        health = json.loads(get("/functions/v1/app/health").decode("utf-8"))
        pc = health.get("powercontext", {})
        pc_ready = pc.get("health", {}).get("status") == "ready"
        ready = pc_ready
        verdict = "PASS" if ready else "BLOCKED"
        print(f"{verdict} live: function /health responds; PowerContext reachable={pc.get('reachable')} upstream={pc.get('upstream_status')}")
        print("NOTE memory cases require PowerContext; run qa/live_acceptance.py for them.")
    except Exception as exc:
        print(f"FAIL live: function /health did not respond: {type(exc).__name__}")
        ok = False
    return ok, pc_ready


REQUIRED = ["README.md", "AGENT_TASK.md", "PROJECT_SPEC.md", "fixtures/demo_notes.json"]
DOCS = ["docs/RUNBOOK.md", "docs/DEMO_STEPS.md", "docs/SUBMISSION.md", "docs/QODER_DEV_LOG.md"]


def check(live: bool = False, pc_ready: bool = False):
    ok = True
    for item in REQUIRED:
        exists = (BASE / item).is_file()
        print(f"{'PASS' if exists else 'FAIL'} required: {item}")
        ok &= exists
    for item in DOCS:
        exists = (BASE / item).is_file()
        print(f"{'PASS' if exists else 'TODO'} deliverable: {item}")
        ok &= exists
    app_files = [p for p in BASE.rglob("*") if p.is_file() and p.suffix in {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte"} and "node_modules" not in p.parts]
    print(f"{'PASS' if app_files else 'TODO'} Qoder-authored application source candidates: {len(app_files)}")
    ok &= bool(app_files)
    try:
        branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True, stderr=subprocess.DEVNULL).strip()
        print(f"{'PASS' if branch == '2026-competition-ecosystem' else 'CHECK'} competition branch: {branch}")
        ok &= branch == "2026-competition-ecosystem"
    except Exception:
        print("CHECK repository branch: unavailable")
        ok = False
    submission = BASE / "docs/SUBMISSION.md"
    if submission.exists():
        s = submission.read_text(encoding="utf-8")
        sha = re.search(r"\b[a-fA-F0-9]{40}\b", s)
        site = re.search(r"https?://[^\s)>`]+", s)
        print(f"{'PASS' if sha else 'TODO'} full SHA in submission")
        site_state = "PASS" if (site and live) else ("CHECK" if site else "TODO")
        print(f"{site_state} site URL public test")
        ok &= bool(sha and site)
    if ok:
        if live and pc_ready:
            print("READINESS=LIVE_ARTIFACTS_MATCH_SOURCE_AND_POWERCONTEXT_READY (memory proof: qa/live_acceptance.py)")
        else:
            print("READINESS=LOCALLY_READY_REQUIRES_REAL_SITE_AND_POWERCONTEXT_VERIFICATION")
    else:
        print("READINESS=INCOMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="verify the published artifacts match this source tree")
    args = parser.parse_args()
    pc_ready = False
    if args.live:
        live_ok, pc_ready = live_check()
        if not live_ok:
            raise SystemExit(1)
    raise SystemExit(check(args.live, pc_ready))
