"""InternalTransport — Firebase exchange + raw HTTP + refresh-on-401.

PRESERVED EXACTLY from ghl_internal_client.py (verified 2026-03-25):
- Firebase exchange URL / params / timeout
- Token cache freshness window: (time.time() - _token_time) < 3000 (50 min)
- force_refresh() clears cache and re-fetches
- request() retry-once on auth failure (None return from _do_request)
- _do_request headers: token-id, channel, source, JSON content-type, CHROME_UA
- ASCII-safe token scrub
- call_count per _do_request

ADDITIVE CHANGES (no happy-path behavior change):
- Env canon: GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN -> CAF_FIREBASE_REFRESH_TOKEN
  -> GHL_FIREBASE_REFRESH_TOKEN (legacy); same pattern for direct-token vars.
- sys.exit() replaced with AdapterError raise so probe/agent callers can
  catch rather than die.  CLI top-level command catches and exits 1 for
  identical interactive UX.
- 429 recognition: returned as AdapterResult(ok=False, http_code=429) with
  X-RateLimit-Daily-Reset header passthrough (caller surfaces, never retries).
- get_token() retries the Firebase securetoken EXCHANGE exactly once on a
  transient None result (exchange-failed) before raising TOKEN_REFRESH_FAILED.
  This is disjoint from the request()-level 401/403 retry: this covers the
  one-time refresh failure observed live, NOT an HTTP auth rejection.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from cli_anything.gohighlevel.internal.adapter_types import AdapterError

# ── Constants — moved from ghl_internal_client.py ───────────────────────────
FIREBASE_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
FIREBASE_TOKEN_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_CTX = ssl.create_default_context()


# ── Token env lookup (canonical -> alias -> legacy) ──────────────────────────

def _resolve_refresh_token() -> str:
    """Return the Firebase refresh token from env, first non-empty wins.

    Order (PRD §7 + adapter-design §6 env canon):
      1. GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN  (canonical)
      2. CAF_FIREBASE_REFRESH_TOKEN          (alias)
      3. GHL_FIREBASE_REFRESH_TOKEN          (legacy — keep for migration)
    """
    for var in (
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
        "CAF_FIREBASE_REFRESH_TOKEN",
        "GHL_FIREBASE_REFRESH_TOKEN",
    ):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


def _resolve_direct_token() -> str:
    """Return a direct Firebase ID token from env (fallback to refresh-token path).

    Order: GOHIGHLEVEL_FIREBASE_TOKEN -> GHL_FIREBASE_TOKEN.
    """
    for var in ("GOHIGHLEVEL_FIREBASE_TOKEN", "GHL_FIREBASE_TOKEN"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


# ── InternalTransport ─────────────────────────────────────────────────────────

class InternalTransport:
    """Firebase JWT auth + raw HTTP against backend.leadconnectorhq.com.

    Behavior is byte-identical to the original InternalGHLClient on the happy
    path.  The only functional change: sys.exit(1) is replaced with
    AdapterError so non-CLI callers (probe, agent) can handle auth failure
    without dying.
    """

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_time: float = 0
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    # ── Token management (PRESERVED EXACTLY) ─────────────────────────────────

    def get_token(self) -> str:
        """Get a valid Firebase JWT token.

        Cache window: < 3000 seconds (50 min) — DO NOT CHANGE.
        Raises AdapterError instead of sys.exit(1) so non-CLI callers survive.
        """
        if self._token and (time.time() - self._token_time) < 3000:
            return self._token

        refresh_token = _resolve_refresh_token()
        if refresh_token:
            token = self._refresh_firebase(refresh_token)
            if not token:
                # RETRY-ONCE on a transient Firebase token-refresh failure.
                # The securetoken exchange occasionally returns None as a
                # ONE-TIME transient (observed live) and succeeds on the very
                # next call.  Retry the exchange EXACTLY ONCE before surfacing
                # TOKEN_REFRESH_FAILED so we don't nudge the owner to re-grab a
                # token that is actually still valid.  This is one retry — not a
                # loop — and it ONLY covers the None (exchange-failed) case; a
                # successful exchange is never re-attempted, and downstream HTTP
                # errors (400/429/etc.) never reach this path.
                token = self._refresh_firebase(refresh_token)
            if token:
                self._token = token
                self._token_time = time.time()
                return token
            # Refresh token present but exchange failed TWICE (transient retry
            # exhausted) — now surface the persistent error / nudge a re-grab.
            raise AdapterError(
                "TOKEN_REFRESH_FAILED",
                "Firebase refresh token is set but token refresh failed. "
                "The refresh token may be revoked or expired. "
                "Get a new one from the Convert and Flow Token Grabber.",
            )

        direct = _resolve_direct_token()
        if direct:
            self._token = direct
            self._token_time = time.time()
            return direct

        raise AdapterError(
            "NO_TOKEN",
            "No Firebase token available for internal API. "
            "Set GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (preferred) or "
            "GOHIGHLEVEL_FIREBASE_TOKEN. "
            "Get the refresh token from the Convert and Flow Token Grabber.",
        )

    def force_refresh(self) -> str:
        """Force token refresh (called on 401 — PRESERVED EXACTLY)."""
        self._token = None
        self._token_time = 0
        return self.get_token()

    def _refresh_firebase(self, refresh_token: str) -> Optional[str]:
        """Exchange Firebase refresh token for a fresh ID token.

        PRESERVED EXACTLY: URL, params, grant_type, timeout=10, id_token key.
        """
        try:
            body = f"grant_type=refresh_token&refresh_token={refresh_token}"
            req = urllib.request.Request(
                FIREBASE_TOKEN_URL,
                data=body.encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, context=_CTX, timeout=10) as r:
                data = json.loads(r.read())
                return data.get("id_token", "")
        except Exception:
            return None

    # ── HTTP request (PRESERVED EXACTLY, additive 429 recognition) ───────────

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Optional[dict]:
        """Send a request.  Returns response dict, None on auth failure, or
        a dict with _error/http_code on other errors.

        Auth retry: if _do_request returns None (401/403), force_refresh and
        retry ONCE.  This is the months-long-persistence guarantee — do not
        add a second retry.
        """
        from cli_anything.gohighlevel.internal.endpoints import BASE_URL as _BASE_URL
        token = self.get_token()
        result = self._do_request(method, path, body, token)

        if result is None:  # auth failure signal
            token = self.force_refresh()
            result = self._do_request(method, path, body, token)

        return result

    def _do_request(
        self,
        method: str,
        path: str,
        body: dict | None,
        token: str,
    ) -> Optional[dict]:
        """Raw HTTP call.  Returns None on 401/403 (triggers retry), dict otherwise.

        PRESERVED EXACTLY: headers, ASCII scrub, 30s timeout, call_count.
        ADDITIVE: 429 recognized explicitly, reset header passed through.
        """
        from cli_anything.gohighlevel.internal.endpoints import BASE_URL as _BASE_URL
        self._call_count += 1
        safe_token = token.encode("ascii", "ignore").decode("ascii").strip()
        headers = {
            "token-id": safe_token,
            "channel": "APP",
            "source": "WEB_USER",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": CHROME_UA,
        }
        url = f"{_BASE_URL}{path}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=_CTX, timeout=30) as resp:
                text = resp.read().decode()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None  # signal for retry
            if e.code == 429:
                # Additive: surface 429 + reset header; caller never retries a 429
                reset_header = ""
                try:
                    reset_header = e.headers.get("X-RateLimit-Daily-Reset", "")
                except Exception:
                    pass
                return {
                    "_error": True,
                    "http_code": 429,
                    "code": 429,
                    "message": "Rate limit exceeded",
                    "rate_limit_reset": reset_header,
                }
            error_body = e.read().decode() if e.fp else ""
            return {"_error": True, "http_code": e.code, "code": e.code, "message": error_body[:200]}
        except Exception as ex:
            return {"_error": True, "http_code": None, "message": str(ex)}
