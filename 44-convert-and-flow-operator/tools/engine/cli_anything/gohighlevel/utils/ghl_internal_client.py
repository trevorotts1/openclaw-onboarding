"""GoHighLevel internal API client for workflow creation.

Uses Firebase JWT auth against backend.leadconnectorhq.com.
Adapted from ghl-superspeed-v3-main/lib/engine.py (2026-03-25).

EXPERIMENTAL: Gated behind --experimental flag in CLI.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from cli_anything.gohighlevel.utils.safety_gate import check_write, SafetyRefused
from cli_anything.gohighlevel.internal.adapter import InternalAdapter
from cli_anything.gohighlevel.internal.adapter_types import AdapterResult, AdapterError
from cli_anything.gohighlevel.internal.transport import InternalTransport
from cli_anything.gohighlevel.internal.endpoints import BASE_URL as _BASE_URL

BASE_URL = _BASE_URL
FIREBASE_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
CTX = ssl.create_default_context()

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Keys to strip from GET responses before PUT (avoids validation errors)
STRIP_KEYS = frozenset([
    "_id", "id", "__v", "createdAt", "updatedAt", "companyId", "locationId",
    "companyAge", "creationSource", "originType", "deleted",
    "isTriggerBucketMigrated", "permissionMeta",
])


class TokenManager:
    """Firebase refresh token management with auto-refresh.

    Token sources (in priority order):
    1. Cached token (if < 50 minutes old)
    2. Firebase refresh token (from GHL_FIREBASE_REFRESH_TOKEN env var)
    3. Direct Firebase token (from GHL_FIREBASE_TOKEN env var)
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._token_time: float = 0

    def get_token(self) -> str:
        """Get a valid Firebase JWT token."""
        # 1. Check if current token is still fresh (< 50 min)
        if self._token and (time.time() - self._token_time) < 3000:
            return self._token

        # 2. Try Firebase refresh token
        refresh_token = os.environ.get("GHL_FIREBASE_REFRESH_TOKEN", "").strip()
        if refresh_token:
            token = self._refresh_firebase(refresh_token)
            if token:
                self._token = token
                self._token_time = time.time()
                return token
            print(
                "Error: Firebase refresh token is set but token refresh failed.\n"
                "The refresh token may be revoked or expired.\n"
                "Get a new one from the GHL Chrome extension.",
                file=sys.stderr,
            )
            sys.exit(1)

        # 3. Try direct Firebase token from env
        token = os.environ.get("GHL_FIREBASE_TOKEN", "").strip()
        if token:
            self._token = token
            self._token_time = time.time()
            return token

        print(
            "Error: No Firebase token available for internal API.\n"
            "Set GHL_FIREBASE_REFRESH_TOKEN (preferred) or GHL_FIREBASE_TOKEN.\n"
            "Get the refresh token from the GHL Chrome extension.",
            file=sys.stderr,
        )
        sys.exit(1)

    def force_refresh(self) -> str:
        """Force token refresh (called on 401)."""
        self._token = None
        self._token_time = 0
        return self.get_token()

    def _refresh_firebase(self, refresh_token: str) -> Optional[str]:
        """Exchange Firebase refresh token for a fresh ID token."""
        try:
            body = f"grant_type=refresh_token&refresh_token={refresh_token}"
            req = urllib.request.Request(
                f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
                data=body.encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
                data = json.loads(r.read())
                return data.get("id_token", "")
        except Exception:
            return None


class InternalGHLClient:
    """GHL internal API client (backend.leadconnectorhq.com).

    Uses Firebase JWT auth with token-id header (NOT Authorization: Bearer).
    """

    def __init__(self, token_mgr: TokenManager, location_id: str):
        self.token_mgr = token_mgr
        self.location_id = location_id
        self._call_count = 0
        # The InternalAdapter is the single isolation point for all internal API
        # calls.  It composes transport + endpoints + contract + guards + degrade.
        # The shim's request() method delegates to it for write calls; legacy
        # direct urllib calls are preserved for backward compat.
        self._adapter = InternalAdapter(location_id=location_id, transport=InternalTransport())

    @property
    def call_count(self) -> int:
        # Include adapter transport call count for unified tracking
        adapter_count = getattr(self._adapter.transport, "call_count", 0) if hasattr(self, "_adapter") else 0
        return self._call_count + adapter_count

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        workflow_name: str = "",
    ) -> Optional[dict]:
        """Make an API request.

        Delegates to InternalAdapter.transport so that tests can mock
        transport.request without touching the legacy urllib path.
        All write methods are checked by the safety gate before any
        network call is made.
        """
        url = f"{BASE_URL}{path}"
        try:
            check_write(method, url, body, location_id=self.location_id, workflow_name=workflow_name)
        except SafetyRefused as exc:
            print(f"SAFETY GATE: {exc}", file=sys.stderr)
            sys.exit(1)

        # Delegate to the adapter's transport (mockable; auto-refresh on 401)
        try:
            result = self._adapter.transport.request(method, path, body)
        except AdapterError as exc:
            # AdapterError (e.g. NO_TOKEN) — surface as SystemExit for CLI compat
            print(f"Error: {exc.message}", file=sys.stderr)
            sys.exit(1)
        return result

    def _do_request(
        self, method: str, path: str, body: dict | None, token: str
    ) -> Optional[dict]:
        self._call_count += 1
        safe_token = token.encode("ascii", "ignore").decode("ascii").strip()
        headers = {
            "token-id": safe_token,
            "channel": "APP",
            "source": "WEB_USER",
            "version": "2021-07-28",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": CHROME_UA,
        }
        url = f"{BASE_URL}{path}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
                text = resp.read().decode()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None  # Signal retry
            error_body = e.read().decode() if e.fp else ""
            return {"_error": True, "code": e.code, "message": error_body[:200]}
        except Exception as ex:
            return {"_error": True, "message": str(ex)}

    def get_workflow(self, wf_id: str) -> "AdapterResult":
        """Get a workflow by ID via the InternalAdapter (read-only).

        Returns AdapterResult. Supports .get(key) for backward compat with
        callers that treat the result as a dict (delegates to result.data).
        """
        return self._adapter.get_workflow(wf_id)

    def put_workflow(self, wf_id: str, body: dict) -> "AdapterResult":
        """PUT a workflow body via the InternalAdapter (write-gated)."""
        return self._adapter.put_workflow(wf_id, body)

    def put_trigger(self, tr_id: str, body: dict) -> "AdapterResult":
        """PUT a trigger body via the InternalAdapter (write-gated)."""
        return self._adapter.put_trigger(tr_id, body)

    def create_location_tag(self, tag: str, workflow_name: str = "") -> bool:
        """Create a tag at location level (required before using in triggers)."""
        result = self.request(
            "POST", f"/workflow/{self.location_id}/tags/create", {"tag": tag},
            workflow_name=workflow_name,
        )
        return bool(result and not result.get("_error"))

    # ── Agency operations (sub-account + user provisioning) ───────────────────

    def create_location(self, body: dict) -> "AdapterResult":
        """Create a sub-account (location) via the InternalAdapter (write-gated).

        body.companyId must be the FIRESTORE document id of the agency (not the
        relationNumber).  The location whitelist is skipped for create (no id
        exists yet); the approval gate still applies.
        """
        return self._adapter.create_location(body)

    def create_user(self, body: dict) -> "AdapterResult":
        """Add a user via the InternalAdapter (write-gated).

        Required body fields: companyId (FIRESTORE id), firstName, lastName,
        email, password, type, role, locationIds.  The whitelist is checked
        against locationIds[0].
        """
        return self._adapter.create_user(body)
