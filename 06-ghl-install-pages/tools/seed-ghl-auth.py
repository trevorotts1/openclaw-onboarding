#!/usr/bin/env python3
"""seed-ghl-auth.py — Mint a fresh GoHighLevel / Convert and Flow Firebase ID
token from the client's refresh token and emit a browser auth-seed payload that
makes an agent-browser (or Playwright) session start ALREADY LOGGED IN — no
password typing, no two-factor-authentication friction.

WHY THIS EXISTS
---------------
GoHighLevel has NO public or internal API for building Funnels / Websites / Pages
(confirmed by audit). The page builder is a browser-only surface. To drive that
browser silently we must seed a valid logged-in session BEFORE navigating to the
builder. GoHighLevel stores its Firebase auth in the browser's IndexedDB (NOT
localStorage — corrected by the 2026-06-21 live-capture pass). This module:

  1. Reuses the EXACT same Firebase refresh-token -> ID-token exchange that
     Skill 44 already performs in
     44-convert-and-flow-operator/.../internal/transport.py
     (same securetoken endpoint, same hardcoded FIREBASE_API_KEY, same
     grant_type, same env-resolution order). It does NOT import or alter
     Skill 44 — it re-implements the read-only exchange so Skill 44's engine is
     untouched (non-breaking, per GOAL §4.2.3).
  2. Captures the FULL securetoken response (id_token, refresh_token,
     expires_in, user_id) — transport.py only keeps id_token; the browser seed
     needs all four.
  3. Emits a JSON seed payload describing exactly what to write into the
     browser's IndexedDB so the session is authenticated.

This module NEVER opens a browser itself and NEVER logs in with a password. It
only mints the token and prints the seed contract. The browser-side write is
done by inject_ghl_auth.sh (agent-browser eval) or the Playwright fallback.

AUTH STORAGE SCHEMA (live-captured 2026-06-21, app.convertandflow.com)
----------------------------------------------------------------------
IndexedDB database : firebaseLocalStorageDb
  object store     : firebaseLocalStorage   (keyPath = "fbase_key")
    entry.fbase_key                            <- key, e.g. "firebase:authUser:<apiKey>:[DEFAULT]"
    entry.value.stsTokenManager.refreshToken   <- Firebase REFRESH token
    entry.value.stsTokenManager.accessToken    <- Firebase ID token (short-lived JWT)
    entry.value.stsTokenManager.expirationTime <- epoch millis when accessToken expires
    entry.value.uid                            <- user id
localStorage (origin): deviceId, proxyLoginCount, debug_sentry, locale  (NO token)

CREDENTIAL MODEL (CLIENT KEYS ONLY — never the operator's keys on a client box)
-------------------------------------------------------------------------------
Primary (silent, unattended): a refresh token resolved from, in order:
    GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN  (canonical)
    CAF_FIREBASE_REFRESH_TOKEN          (alias)
    GHL_FIREBASE_REFRESH_TOKEN          (legacy)
  grabbed by the Convert and Flow / Scale-44 Token Grabber Chrome extension
  (44-convert-and-flow-operator/tools/chrome-extension/) from the client's OWN
  logged-in browser, then stored in ~/.openclaw/secrets/.env.

Fallback (attended, may hit two-factor authentication): scripted login form with
    GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD   (real var names on this fleet)
    GHL_EMAIL / GHL_PASSWORD                 (older spec names — also accepted)
  See A1 in ghl-install-pages-full.md. Two-factor authentication PAUSES for a
  human; it is never bypassed.

USAGE
-----
  python3 seed-ghl-auth.py --print-seed        # mint token, print JSON seed to stdout
  python3 seed-ghl-auth.py --print-seed --out /tmp/<session>/ghl-auth-seed.json
  python3 seed-ghl-auth.py --check             # only report which auth path is available
Exit codes: 0 = seed minted; 2 = no usable refresh token (fall back to login form);
3 = refresh token present but REVOKED/expired (re-grab via Token Grabber).
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

# PRESERVED EXACTLY from Skill 44 transport.py — same key, same endpoint.
# This is the GoHighLevel/Convert-and-Flow Firebase web API key (hardcoded in
# transport.py; verified accepted by Google in the live-capture pass). It is NOT
# a secret and NOT an env var.
FIREBASE_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
FIREBASE_TOKEN_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

# Env-resolution order — IDENTICAL to transport.py _resolve_refresh_token().
REFRESH_ENV_VARS = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "CAF_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
)

# IndexedDB target (live-captured 2026-06-21).
IDB_DATABASE = "firebaseLocalStorageDb"
IDB_STORE = "firebaseLocalStorage"
IDB_KEYPATH = "fbase_key"
# The fbase_key string for the [DEFAULT] Firebase app. The exact value still
# needs a logged-in capture to confirm verbatim (gate #27 residual); this is the
# documented Firebase web SDK convention and is overridable via --fbase-key.
DEFAULT_FBASE_KEY = f"firebase:authUser:{FIREBASE_API_KEY}:[DEFAULT]"

_CTX = ssl.create_default_context()


def _resolve_refresh_token() -> tuple[str, str]:
    """Return (token, env_var_name) for the first non-empty refresh-token var,
    or ("", "") if none set. Same precedence as Skill 44 transport.py."""
    for name in REFRESH_ENV_VARS:
        val = os.environ.get(name, "").strip()
        if val:
            return val, name
    return "", ""


def _exchange(refresh_token: str) -> dict:
    """Exchange a Firebase refresh token for a fresh ID token.

    PRESERVED EXACTLY from transport.py: URL, params, grant_type, timeout=10.
    DIFFERENCE: transport.py returns only id_token; we return the FULL response
    (id_token, refresh_token, expires_in, user_id) because the browser seed
    needs all four to populate stsTokenManager + uid.

    Raises RuntimeError with the Google error code on failure (e.g.
    INVALID_REFRESH_TOKEN when the token has been revoked).
    """
    body = f"grant_type=refresh_token&refresh_token={refresh_token}"
    req = urllib.request.Request(
        FIREBASE_TOKEN_URL,
        data=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            detail = str(e.code)
        raise RuntimeError(f"securetoken exchange failed: HTTP {e.code} {detail}") from e
    except Exception as e:  # network/timeout
        raise RuntimeError(f"securetoken exchange failed: {e}") from e


def build_seed(resp: dict, fbase_key: str) -> dict:
    """Build the browser auth-seed payload from a securetoken response.

    The seed describes the IndexedDB entry to write so the GoHighLevel SPA boots
    authenticated. `fbase_key` is the IndexedDB key; the value mirrors the
    Firebase web SDK's persisted user shape (only the fields GoHighLevel reads).
    """
    id_token = resp.get("id_token") or resp.get("access_token") or ""
    refresh_token = resp.get("refresh_token") or ""
    user_id = resp.get("user_id") or ""
    expires_in = int(resp.get("expires_in", "3600") or 3600)
    expiration_ms = int((time.time() + expires_in) * 1000)

    if not id_token:
        raise RuntimeError("securetoken response had no id_token")

    return {
        "indexeddb": {
            "database": IDB_DATABASE,
            "store": IDB_STORE,
            "keyPath": IDB_KEYPATH,
            "entry": {
                "fbase_key": fbase_key,
                "value": {
                    "uid": user_id,
                    "stsTokenManager": {
                        "refreshToken": refresh_token,
                        "accessToken": id_token,
                        "expirationTime": expiration_ms,
                    },
                    # Minimal extra fields the SDK tolerates; GoHighLevel reads
                    # uid + stsTokenManager. Kept conservative on purpose.
                    "apiKey": FIREBASE_API_KEY,
                    "appName": "[DEFAULT]",
                },
            },
        },
        # GoHighLevel also sends the ID token as a `token-id:` header (NOT Bearer)
        # with `version: 2021-07-28` on its internal API. Provided so a caller can
        # set --headers for any XHR that fires before the SDK rehydrates.
        "headers": {
            "token-id": id_token,
            "version": "2021-07-28",
        },
        "meta": {
            "expirationTime": expiration_ms,
            "minted_at": int(time.time()),
            "note": "Seed into IndexedDB BEFORE navigating to the builder. "
                    "ID token is short-lived (~50-60 min); auto-refresh on 401 "
                    "by re-running this module.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Mint GoHighLevel Firebase ID token + browser auth seed")
    ap.add_argument("--print-seed", action="store_true", help="Mint token and print JSON seed to stdout")
    ap.add_argument("--check", action="store_true", help="Only report which auth path is available")
    ap.add_argument("--out", help="Also write the seed JSON to this file path")
    ap.add_argument("--fbase-key", default=DEFAULT_FBASE_KEY,
                    help="IndexedDB fbase_key value (default: Firebase [DEFAULT] app convention)")
    args = ap.parse_args()

    token, env_name = _resolve_refresh_token()

    if args.check:
        if token:
            print(json.dumps({"auth_path": "refresh-token", "env_var": env_name, "len": len(token)}))
            return 0
        has_login = bool(os.environ.get("GHL_AGENCY_EMAIL") or os.environ.get("GHL_EMAIL"))
        print(json.dumps({"auth_path": "login-form" if has_login else "none",
                          "fallback_creds_present": has_login}))
        return 0 if has_login else 2

    if not token:
        sys.stderr.write(
            "No Firebase refresh token set (checked "
            + ", ".join(REFRESH_ENV_VARS)
            + "). Fall back to the GHL_AGENCY_EMAIL/GHL_AGENCY_PASSWORD login form "
            "(A1 in ghl-install-pages-full.md). Two-factor authentication may pause for a human.\n"
        )
        return 2

    try:
        resp = _exchange(token)
    except RuntimeError as e:
        msg = str(e)
        sys.stderr.write(msg + "\n")
        if "INVALID_REFRESH_TOKEN" in msg or "TOKEN_EXPIRED" in msg or "USER_DISABLED" in msg:
            sys.stderr.write(
                "Refresh token is REVOKED/expired. Re-grab it via the Convert and Flow "
                "Token Grabber Chrome extension (44-convert-and-flow-operator/tools/chrome-extension/) "
                "from the CLIENT's own logged-in browser and update ~/.openclaw/secrets/.env.\n"
            )
            return 3
        return 2

    seed = build_seed(resp, args.fbase_key)
    out = json.dumps(seed, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            f.write(out)
        # Lock down — it contains live tokens.
        try:
            os.chmod(args.out, 0o600)
        except OSError:
            pass
    if args.print_seed or not args.out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
