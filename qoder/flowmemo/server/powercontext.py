"""PowerContext HTTP client for FlowMemo.

Real HTTP integration — no mocking. All calls are server-side only.
API reference: https://powercontext.oceanbase.io/en/docs/develop/api-quickstart/

Endpoints used:
  GET  /health/live
  POST /v1/scopes
  POST /v1/memory/remember
  POST /v1/context/prepare
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional

import httpx


class PowerContextClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: float = 15.0):
        self.base_url = (base_url or os.environ.get("POWERCONTEXT_URL", "")).rstrip("/")
        self.token = token or os.environ.get("POWERCONTEXT_TOKEN", "")
        self.timeout = timeout
        self._scope_cache: dict[str, str] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def health_check(self) -> dict:
        if not self.is_configured:
            return {"status": "not_configured", "message": "PowerContext URL not set"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/health/live", headers=self._headers())
                if resp.status_code == 200:
                    return {"status": "connected", "url": self.base_url}
                return {"status": "error", "code": resp.status_code}
        except httpx.ConnectError:
            return {"status": "disconnected", "message": "Cannot reach PowerContext service"}
        except httpx.TimeoutException:
            return {"status": "timeout", "message": "PowerContext service timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_or_create_scope(self, visitor_id: str) -> dict:
        if not self.is_configured:
            return {"error": "not_configured"}
        if visitor_id in self._scope_cache:
            return {"scope_id": self._scope_cache[visitor_id]}
        nonce = uuid.uuid4().hex[:12]
        payload = {
            "title": f"FlowMemo visitor {visitor_id[:8]}",
            "summary": "Weekly report workspace memory scope",
            "idempotency_key": f"flowmemo-{visitor_id[:8]}-{nonce}",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/v1/scopes", json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    data = resp.json()
                    scope_id = data.get("scope_id", "")
                    if scope_id:
                        self._scope_cache[visitor_id] = scope_id
                        return {"scope_id": scope_id, "raw": data}
                    return {"error": "no_scope_id", "raw": data}
                return {"error": f"HTTP {resp.status_code}", "raw": resp.text[:500]}
        except Exception as e:
            return {"error": str(e)}

    async def remember(self, scope_id: str, kind: str, text: str, reason: str = "") -> dict:
        if not self.is_configured:
            return {"error": "not_configured"}
        payload = {
            "scope_id": scope_id,
            "kind": kind,
            "text": text,
            "reason": reason or "User-saved preference via FlowMemo workspace",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/v1/memory/remember", json=payload, headers=self._headers())
                data = resp.json() if resp.status_code == 200 else {}
                success = resp.status_code == 200 and isinstance(data.get("records"), list) and len(data.get("records", [])) > 0
                return {
                    "success": success,
                    "status_code": resp.status_code,
                    "records": data.get("records", []),
                    "raw": data,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def prepare(self, scope_id: str, query: str, max_bytes: int = 4000) -> dict:
        if not self.is_configured:
            return {"error": "not_configured"}
        payload = {
            "scope_id": scope_id,
            "query": query,
            "max_bytes": max_bytes,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/v1/context/prepare", json=payload, headers=self._headers())
                data = resp.json() if resp.status_code == 200 else {}
                return {
                    "status": data.get("status", "unknown"),
                    "content": data.get("content", ""),
                    "raw": data,
                    "status_code": resp.status_code,
                }
        except Exception as e:
            return {"status": "error", "content": "", "error": str(e)}


_client: Optional[PowerContextClient] = None


def get_client() -> PowerContextClient:
    global _client
    if _client is None:
        _client = PowerContextClient()
    return _client
