#!/usr/bin/env python3
"""Real PowerContext HTTP memory-write + prepare smoke test.

Run only with a real PowerContext Server. No mock, no third-party packages.
Source: https://powercontext.oceanbase.io/en/docs/develop/api-quickstart/
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class HttpClient:
    def __init__(self, url: str, token: str | None, timeout: float = 15):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as err:
            # Avoid printing token or private server response content.
            raise RuntimeError(f"PowerContext {path}: HTTP {err.code}") from None
        except URLError as err:
            raise RuntimeError(f"PowerContext {path}: connection unavailable ({type(err.reason).__name__})") from None


def execute(client: HttpClient, text: str) -> dict:
    client.call("GET", "/health/live")
    nonce = uuid4().hex[:12]
    scope = client.call("POST", "/v1/scopes", {
        "title": "FlowMemo QA sample", "summary": "Fictional weekly-report memory round-trip",
        "idempotency_key": "flowmemo-qa-" + nonce,
    })
    scope_id = scope.get("scope_id")
    if not isinstance(scope_id, str) or not scope_id:
        raise RuntimeError("PowerContext /v1/scopes did not return scope_id")
    remembered = client.call("POST", "/v1/memory/remember", {
        "scope_id": scope_id,
        "kind": "decision",
        "text": text,
        "reason": "User-approved QA sample preference; synthetic fixture",
    })
    records = remembered.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("PowerContext write did not return real memory records")
    prepared = client.call("POST", "/v1/context/prepare", {
        "scope_id": scope_id,
        "query": "riskfirst",
        "max_bytes": 4000,
    })
    content = prepared.get("content") or ""
    status = prepared.get("status")
    recalled = status == "ready" and bool(content) and ("风险" in content or "风险优先" in content)
    result = {
        "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "real_http_calls": ["GET /health/live", "POST /v1/scopes", "POST /v1/memory/remember", "POST /v1/context/prepare"],
        "write_records": len(records),
        "prepare_status": status,
        "recall_contains_risk_preference": recalled,
        "data": "synthetic", "secret_value_printed": False,
    }
    if not recalled:
        raise RuntimeError(f"PowerContext write succeeded but memory recall was not ready (status={status!r}). Inspect indexing/configuration and retry with diagnostics; never claim PASS.")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Real PowerContext memory roundtrip, no mocking")
    ap.add_argument("--url", default=os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--output", help="Optional sanitized JSON evidence output path")
    args = ap.parse_args()
    text = "FlowMemo riskfirst 周报偏好：先写风险，再写已完成事项，最后写下周计划，需引用来源。"
    try:
        result = execute(HttpClient(args.url, os.getenv("POWERCONTEXT_TOKEN")), text)
    except (RuntimeError, ValueError, TimeoutError) as e:
        print("POWERCONTEXT_REAL_ROUNDTRIP_FAIL:", e)
        return 1
    print("POWERCONTEXT_REAL_ROUNDTRIP_PASS")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"SANITIZED_EVIDENCE_SAVED={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
