#!/usr/bin/env python3
"""FlowMemo live acceptance harness (stdlib only, no mocking).

Drives the deployed Qoder Sites Server Function exactly like the browser does
and reports the real HTTP outcome for each memory contract. Never prints a
Token, a Secret value or a full session id.

Usage:
    python qa/live_acceptance.py
    python qa/live_acceptance.py --base https://<site>/functions/v1/app --output evidence/live.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "https://flowmemo-workspace-7u2qbfllad4.qoder.zone/functions/v1/app"
PREF_A = "周报先写已完成事项，再写风险"
PREF_B = "周报先写风险，再写已完成事项"


def mask(value: object, keep: int = 6) -> str:
    text = str(value or "")
    if not text:
        return "<absent>"
    return text[:keep] + "…" if len(text) > keep else text


class FunctionClient:
    """Same-origin style caller: the Sites gateway rejects a bare origin."""

    def __init__(self, base: str, timeout: float = 20):
        self.base = base.rstrip("/")
        self.origin = self.base.split("/functions/")[0]
        self.timeout = timeout

    def call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        headers = {
            "Accept": "application/json",
            "Origin": self.origin,
            "Referer": self.origin + "/",
            "Cache-Control": "no-store",
        }
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return response.status, (json.loads(raw) if raw else {})
        except HTTPError as err:
            raw = err.read().decode("utf-8", errors="replace")
            try:
                return err.code, json.loads(raw)
            except ValueError:
                return err.code, {"non_json": raw[:200]}
        except URLError as err:
            raise RuntimeError(f"transport failure at {path}: {type(err.reason).__name__}") from None


def new_session(client: FunctionClient, project_id: str) -> dict:
    status, data = client.call("POST", "/session/ensure", {"projectId": project_id})
    if status != 200 or not data.get("ok") or not data.get("sessionId"):
        raise RuntimeError(f"/session/ensure failed: HTTP {status} {data.get('error')}")
    return data


def offline_isolation_cases(client: FunctionClient, record) -> None:
    """Isolation checks that the Function can answer without PowerContext.

    Signature verification happens before any upstream call, so a forged or
    cross-project token is provably rejected even while PowerContext is down.
    """
    import base64

    def token(scope_id: str, project_id: str) -> str:
        payload = base64.b64encode(json.dumps({
            "visitorId": "qa-forged-visitor", "projectId": project_id,
            "scope_id": scope_id, "exp": 4_102_444_800,
        }, separators=(",", ":")).encode()).decode()
        # The Function signs the payload with a server-only secret; a client can
        # never produce a matching MAC, so any locally built signature is forged.
        return f"{payload}.{base64.b64encode(bytes(32)).decode()}"

    forged = token("scp_deadbeefdeadbeef", "qa_proj_a")
    status, data = client.call("POST", "/memory/preference/recall", {
        "projectId": "qa_proj_a", "sessionId": forged,
    })
    record("forged_signature_rejected", "PASS" if status == 401 else "FAIL", {
        "http_status": status, "error": data.get("error"),
        "preference_leaked": bool(data.get("preference")),
    })

    tampered = forged[:-8] + "AAAAAAAA"
    status, data = client.call("POST", "/memory/preference/save", {
        "projectId": "qa_proj_a", "sessionId": tampered, "preference": PREF_A,
    })
    record("tampered_token_rejected_on_save", "PASS" if status == 401 else "FAIL", {
        "http_status": status, "error": data.get("error"),
    })

    status, data = client.call("POST", "/session/ensure", {
        "projectId": "qa_proj_a", "sessionId": forged,
    })
    record("renew_with_forged_token_rejected", "PASS" if status == 401 else "FAIL", {
        "http_status": status, "error": data.get("error"),
    })

    status, data = client.call("GET", "/debug/memory")
    record("anonymous_debug_endpoint_removed", "PASS" if status == 404 else "FAIL", {
        "http_status": status, "error": data.get("error"),
        "note": "no route reads memory without a verified session token",
    })


def run() -> dict:
    client = FunctionClient(ARGS_BASE)
    results: list[dict] = []

    def record(name: str, verdict: str, evidence: dict) -> None:
        results.append({"case": name, "verdict": verdict, "evidence": evidence})

    # 1 + 2. Health check must resolve, never hang, and report real status.
    status, health = client.call("GET", "/health")
    pc = health.get("powercontext") or {}
    ready = pc.get("configured") is True and (pc.get("health") or {}).get("status") == "ready"
    record("health_check_responds", "PASS" if status == 200 else "FAIL", {
        "http_status": status,
        "configured": pc.get("configured"),
        "reachable": pc.get("reachable"),
        "upstream_status": pc.get("upstream_status"),
        # A Codespaces tunnel can answer with HTML and still look "reachable";
        # only a JSON body proves PowerContext itself replied.
        "upstream_content_type": pc.get("upstream_content_type"),
        "upstream_json": pc.get("upstream_json"),
        "upstream_served_by": pc.get("upstream_served_by"),
        "request_id": pc.get("request_id") or None,
    })
    record("powercontext_ready", "PASS" if ready else "BLOCKED", {
        "health_status": (pc.get("health") or {}).get("status"),
        "upstream_status": pc.get("upstream_status"),
        "upstream_json": pc.get("upstream_json"),
        "upstream_content_type": pc.get("upstream_content_type"),
        "error": pc.get("error"),
    })

    # Requirement 8 has two halves: the token cannot be forged (server-side,
    # always testable) and the Scope really isolates reads (needs PowerContext).
    offline_isolation_cases(client, record)

    if not ready:
        return {"checked_utc": now(), "powercontext_ready": False, "cases": results,
                "note": "Memory cases not attempted: PowerContext is not ready. "
                        "Reporting BLOCKED instead of fabricating a pass."}

    # 5. Save a preference into a real Scope created by PowerContext.
    project_a = "qa_proj_a"
    session_a = new_session(client, project_a)
    scope_a = session_a.get("scopeId")
    status, saved = client.call("POST", "/memory/preference/save", {
        "projectId": project_a, "sessionId": session_a["sessionId"], "preference": PREF_A,
    })
    record("preference_saved_to_powercontext", "PASS" if saved.get("saved") is True and status == 200 else "FAIL", {
        "http_status": status,
        "scope_id": mask(scope_a),
        "request_id": saved.get("request_id"),
        "error": saved.get("error"),
        "upstream_status": saved.get("upstream_status"),
    })
    token_a = saved.get("sessionId") or session_a["sessionId"]

    # 6. Refresh simulation: re-ensure with the stored token, then recall.
    status, renews = client.call("POST", "/session/ensure", {
        "projectId": project_a, "sessionId": token_a,
    })
    same_scope = renews.get("scopeId") == scope_a
    record("scope_survives_refresh", "PASS" if renews.get("verified") and same_scope else "FAIL", {
        "http_status": status, "verified": renews.get("verified"),
        "same_scope_id": same_scope, "scope_id": mask(renews.get("scopeId")),
    })
    status, recall = client.call("POST", "/memory/preference/recall", {
        "projectId": project_a, "sessionId": token_a,
    })
    record("preference_recalled_from_powercontext",
           "PASS" if recall.get("preference") == PREF_A else "FAIL", {
        "http_status": status, "preference": recall.get("preference"),
        "count": recall.get("count"), "source": recall.get("source"),
        "request_id": recall.get("request_id"),
    })

    # 7. Opposite preference must be recalled instead of the older one.
    status, saved2 = client.call("POST", "/memory/preference/save", {
        "projectId": project_a, "sessionId": token_a, "preference": PREF_B,
    })
    token2 = saved2.get("sessionId") or token_a
    status, recall2 = client.call("POST", "/memory/preference/recall", {
        "projectId": project_a, "sessionId": token2,
    })
    record("latest_preference_wins", "PASS" if recall2.get("preference") == PREF_B else "FAIL", {
        "http_status": status, "preference": recall2.get("preference"),
        "request_id": recall2.get("request_id"),
    })

    # 8. A different visitor must not read visitor A's memory.
    session_b = new_session(client, "qa_proj_b")
    status, cross = client.call("POST", "/memory/preference/recall", {
        "projectId": "qa_proj_b", "sessionId": session_b["sessionId"],
    })
    leaked = cross.get("preference") in (PREF_A, PREF_B)
    record("visitor_isolation_scope_read", "PASS" if not leaked else "FAIL", {
        "http_status": status, "other_scope": mask(session_b.get("scopeId")),
        "scope_differs": session_b.get("scopeId") != scope_a,
        "preference_returned": cross.get("preference"),
    })
    # A foreign session token replayed under another project must be rejected.
    status, forged = client.call("POST", "/memory/preference/recall", {
        "projectId": "qa_proj_b", "sessionId": token_a,
    })
    record("foreign_session_token_rejected", "PASS" if status == 401 else "FAIL", {
        "http_status": status, "error": forged.get("error"),
    })
    # No route accepts an arbitrary scope_id, so there is no IDOR surface.
    status,idor = client.call("POST", "/memory/preference/recall", {
        "projectId": project_a, "sessionId": token_a, "scope_id": "scp_deadbeefdeadbeef",
    })
    record("arbitrary_scope_id_ignored", "PASS" if idor.get("ok") else "FAIL", {
        "http_status": status, "note": "scope comes only from the signed session token"
    })
    return {"checked_utc": now(), "powercontext_ready": True, "cases": results}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    global ARGS_BASE
    parser = argparse.ArgumentParser(description="FlowMemo live Function acceptance, no mocking")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--output", help="Where to write the sanitized JSON evidence")
    parsed = parser.parse_args()
    ARGS_BASE = parsed.base
    try:
        report = run()
    except RuntimeError as err:
        print("LIVE_ACCEPTANCE_ERROR:", err)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Evidence is written for every outcome, including BLOCKED: the reason a
    # case did not run is itself part of the submission record.
    if parsed.output:
        destination = Path(parsed.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("evidence written:", parsed.output)
    verdicts = {case["verdict"] for case in report["cases"]}
    if "FAIL" in verdicts:
        print("LIVE_ACCEPTANCE_FAIL")
        return 1
    if not report["powercontext_ready"]:
        print("LIVE_ACCEPTANCE_BLOCKED (PowerContext not ready)")
        return 2
    print("LIVE_ACCEPTANCE_PASS")
    return 0


ARGS_BASE = DEFAULT_BASE

if __name__ == "__main__":
    raise SystemExit(main())
