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

D7 — TOKEN-SEED IS THE *ONLY* AUTH PATH (no UI login, no 2FA):
  The auth path is exactly this module + inject-ghl-auth.sh: mint the Firebase
  ID/refresh token from the client's refresh token, then (in-browser) (1) seed
  the Firebase Web SDK User record into IndexedDB, (2) call the SPA's own
  getCurrentUser() (GET /oauth/2/login/current authed by `token-id`) to obtain
  the logged-in object `i`, and (3) write the SPA's six auth COOKIES from `i`
  (cookie `a` = btoa({apiKey,userId,companyId}) is the authoritative logged-in
  signal; without it the SPA throws user_not_logged_in and bounces to login).
  Then navigate STRAIGHT INTO the dashboard. The refresh token ALONE produces a
  logged-in SPA session — NO Sign-in form is rendered, NO password is typed, NO
  two-factor-authentication is ever reached.

  HARD RULE (NO AUTOMATIC UI-LOGIN FALLBACK): the token-seed is the ONLY
  auto-invoked auth path. If seeding fails (no token / revoked token / the
  seeded record does not log the SPA in), the builder MUST STOP and report
  (non-zero exit). It must NEVER auto-open the Sign-in form or a two-factor
  prompt. GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD remain a DOCUMENTED,
  MANUAL-only last resort (operator-initiated, never auto-invoked by this
  module or by inject-ghl-auth.sh). --check reports the available path for the
  operator; it does NOT authorize an automatic UI login.

ROOT-CAUSE NOTE (auth/internal-error — fixed 2026-06-21):
  The Firebase Web SDK User._fromJSON() asserts typeof emailVerified ===
  'boolean' and typeof isAnonymous === 'boolean'. An earlier build omitted both
  fields, so the SDK threw AuthErrorCode.INTERNAL_ERROR the instant it
  rehydrated the seeded record (the SPA bounced back to the login form). The
  record built below now ALWAYS includes emailVerified:false + isAnonymous:false
  (and the full required shape), so the SDK accepts the record and the SPA boots
  authenticated.

AUTH STORAGE SCHEMA (bundle-verified + live network proof, 2026-06-21 pass 2)
-----------------------------------------------------------------------------
TWO storages must be seeded — proven by reading the SPA bundle (/tmp/ghl-spa,
chunk.DOYVEcZH.js) and by a live token-only network replay:

(A) COOKIES — the SPA's authoritative "logged-in" signal (NOT httpOnly, NOT a
    Set-Cookie; every one is written/read via document.cookie). The bundle's
    `An` getter/setter is verbatim:
       set: a="/"; i=(e===null?-1:1)*31536e3; n=fp(hostname);
            s=n?`domain=${n};`:""; o=n?"secure":"";
            cookie `a`  = btoa(JSON.stringify({apiKey,userId,companyId}))
            cookie `access-token-v1`     = e.jwt
            cookie `refresh-token-v1`    = e.refreshJwt
            cookie `access-token-v2`     = e.authToken
            cookie `refresh-token-v2`    = e.refreshToken
            cookie `custom-firebase-token` = e.firebaseToken
       get: reads cookie `a` -> JSON.parse(atob(a)); if absent it THROWS
            "user_not_logged_in". Cl(): if(!t?.apiKey) throw "Not authenticated".
    => Without cookie `a`, the SPA bounces straight to the login form. This is
       exactly why the earlier IndexedDB-only seed FAILED (03-login-attempt.png).
    Cookie attributes replicate the setter verbatim: path=/; Max-Age=31536000;
    domain=<registrable host> (only when resolvable); `secure` (only when domain
    set). All six cookies are JS-readable (NOT httpOnly).

(B) FIREBASE IndexedDB — needed so the generic-API interceptor's
    `token-id = await firebase.auth().currentUser.getIdToken()` resolves on every
    data XHR. The SPA itself boots Firebase from the `custom-firebase-token`
    cookie via `signInWithCustomToken(token)`. We ALSO write the full Firebase
    Web SDK User record so getIdToken() works immediately on first paint:
  IndexedDB database : firebaseLocalStorageDb   (Firebase Web SDK persistence DB)
    object store     : firebaseLocalStorage     (keyPath = "fbase_key")
      entry.fbase_key  = "firebase:authUser:AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE:[DEFAULT]"
      entry.value      = full User JSON: uid, emailVerified:false,
        isAnonymous:false, providerData:[], stsTokenManager{refreshToken,
        accessToken,expirationTime}, createdAt/lastLoginAt (epoch-ms strings),
        apiKey, appName="[DEFAULT]".

THE LOGGED-IN OBJECT `i` (source of every cookie value) is fetched IN-BROWSER by
the SPA's own getCurrentUser():
    GET https://backend.leadconnectorhq.com/oauth/2/login/current
    headers: {channel:"APP", source:"WEB_USER", version:"2021-07-28",
              device-id:<uuid>, token-id:<minted id_token>}
  LIVE-PROVEN 200 returning exactly {token, jwt, refreshJwt, apiKey, authToken,
  refreshToken, userId, companyId, name, role, type, permissions}. token-id alone
  authenticates (bare token-id from securetoken => 200). Done in-browser because
  Cloudflare's bot-check WAF (error 1010) blocks bare non-browser requests;
  inside the agent-browser the Cloudflare clearance + browser UA are automatic.

localStorage (origin): deviceId, proxyLoginCount, debug_sentry, locale  (NO
  auth token there; auth state is the cookies above + Firebase IndexedDB).

CREDENTIAL MODEL (CLIENT KEYS ONLY — never the operator's keys on a client box)
-------------------------------------------------------------------------------
Primary (silent, unattended): a refresh token resolved from, in order:
    GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN  (canonical)
    CAF_FIREBASE_REFRESH_TOKEN          (alias)
    GHL_FIREBASE_REFRESH_TOKEN          (legacy)
  grabbed by the Convert and Flow / Scale-44 Token Grabber Chrome extension
  (44-convert-and-flow-operator/tools/chrome-extension/) from the client's OWN
  logged-in browser, then stored in ~/.openclaw/secrets/.env.

MANUAL last resort (NEVER auto-invoked — operator only): GHL_AGENCY_EMAIL /
  GHL_AGENCY_PASSWORD (or older GHL_EMAIL / GHL_PASSWORD). These exist ONLY so a
  human operator can, by hand, recover when the refresh token cannot be
  re-grabbed. Neither this module nor inject-ghl-auth.sh ever drives the Sign-in
  form automatically. There is NO automatic UI-login / two-factor fallback.

USAGE
-----
  python3 seed-ghl-auth.py --print-seed        # mint token, print JSON seed to stdout
  python3 seed-ghl-auth.py --print-seed --out /tmp/<session>/ghl-auth-seed.json
  python3 seed-ghl-auth.py --check             # only report which auth path is available
Exit codes: 0 = seed minted; 2 = no usable refresh token (STOP — do NOT auto-open
the login form; operator must supply a fresh token); 3 = refresh token present
but REVOKED/expired (STOP — re-grab via the Token Grabber). A non-zero exit means
the builder STOPS and reports; it NEVER triggers an automatic UI login.
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

# IndexedDB target (Firebase JS SDK source: indexed_db.ts + persistence DB name,
# persistence_user_manager.ts _persistenceKeyName key format).
IDB_DATABASE = "firebaseLocalStorageDb"
IDB_STORE = "firebaseLocalStorage"
IDB_KEYPATH = "fbase_key"
# Firebase Web SDK default app name. _persistenceKeyName() builds the key as
# firebase:authUser:<apiKey>:<appName>; appName is "[DEFAULT]" unless
# initializeApp() is called with a custom name (GHL/LeadConnector does not).
DEFAULT_APP_NAME = "[DEFAULT]"
# The fbase_key string for the [DEFAULT] Firebase app — CONFIRMED verbatim from
# the Firebase JS SDK source (_persistenceKeyName) + the live IndexedDB store
# read by the Token Grabber. Overridable via --fbase-key.
DEFAULT_FBASE_KEY = f"firebase:authUser:{FIREBASE_API_KEY}:{DEFAULT_APP_NAME}"

# ── SPA COOKIE CONTRACT (verbatim from chunk.DOYVEcZH.js `An` setter) ──────────
# The SPA writes these six cookies; the `An` getter reads them back. Cookie `a`
# is base64(JSON.stringify({apiKey,userId,companyId})) and is the authoritative
# "logged-in" signal — its absence throws user_not_logged_in. The token cookies
# overlay jwt/refreshJwt/authToken/refreshToken/firebaseToken onto that object.
# Setter attributes (verbatim): path="/"; Max-Age=31536000 (=31536e3);
# domain=<registrable host> only when resolvable; `secure` only when domain set.
COOKIE_MAX_AGE = 31536000  # seconds (= 31536e3 in the bundle; 1 year)
COOKIE_PATH = "/"
# Maps the login/current response field -> the SPA cookie name (An setter order).
COOKIE_TOKEN_MAP = {
    "jwt": "access-token-v1",
    "refreshJwt": "refresh-token-v1",
    "authToken": "access-token-v2",
    "refreshToken": "refresh-token-v2",
    "firebaseToken": "custom-firebase-token",  # = the response's `token` field
}
COOKIE_A_NAME = "a"

# ── getCurrentUser() — the SPA's own login/current call (in-browser STEP 2) ────
# GET /oauth/2/login/current authed by `token-id:<id_token>` returns the logged-
# in object `i`. Done IN the agent-browser (Cloudflare bot-check WAF — error 1010
# — blocks bare non-browser requests; inside the browser the clearance + UA are
# automatic). Static headers are verbatim from the bundle ($t).
LOGIN_CURRENT_HOST = "backend.leadconnectorhq.com"
LOGIN_CURRENT_PATH = "/oauth/2/login/current"
GHL_STATIC_HEADERS = {
    "channel": "APP",
    "source": "WEB_USER",
    "version": "2021-07-28",
}

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
    authenticated. `fbase_key` is the IndexedDB key; `value` is the COMPLETE
    Firebase Web SDK User JSON in the EXACT shape User._fromJSON() expects.

    CRITICAL (root cause of the old auth/internal-error): emailVerified and
    isAnonymous are asserted by the SDK as `typeof === 'boolean'`. Omitting them
    threw INTERNAL_ERROR on rehydrate and bounced the SPA to the login form.
    Both are now always present (false). providerData is [] (correct for a
    custom-token sign-in). createdAt/lastLoginAt are epoch-ms STRINGS (the SDK
    asserts string|undefined — never raw numbers).
    """
    id_token = resp.get("id_token") or resp.get("access_token") or ""
    refresh_token = resp.get("refresh_token") or ""
    user_id = resp.get("user_id") or resp.get("localId") or ""
    expires_in = int(resp.get("expires_in", "3600") or 3600)
    now_ms = int(time.time() * 1000)
    expiration_ms = int((time.time() + expires_in) * 1000)

    if not id_token:
        raise RuntimeError("securetoken response had no id_token")
    if not refresh_token:
        # Without a refreshToken the SDK cannot silently renew the id_token; the
        # seed would die at the first ~hourly refresh. Refuse rather than ship a
        # half-record (the securetoken refresh-grant always returns one).
        raise RuntimeError("securetoken response had no refresh_token")
    if not user_id:
        raise RuntimeError("securetoken response had no user_id (uid)")

    # The Firebase Web SDK User record, EXACT shape (User._fromJSON +
    # StsTokenManager.fromJSON). This single record, written to IndexedDB, logs
    # the SPA in — confirmed: the id_token validates directly via the backend's
    # `token-id` header. This is a CUSTOM-AUTH user (sign_in_provider=custom):
    # email/displayName/photoURL genuinely do not exist for this user, so they
    # are OMITTED (not set to null) — the SDK asserts string|undefined for them.
    value = {
        "uid": user_id,
        # email/displayName/photoURL/phoneNumber/tenantId deliberately OMITTED
        # (undefined) — a custom-token user has none; setting null would fail
        # the SDK's string|undefined assertion.
        "emailVerified": False,    # REQUIRED boolean (SDK asserts typeof===boolean)
        "isAnonymous": False,      # REQUIRED boolean (SDK asserts typeof===boolean)
        "providerData": [],        # custom sign-in -> empty array (Array.isArray ok)
        "stsTokenManager": {
            "refreshToken": refresh_token,
            "accessToken": id_token,
            "expirationTime": expiration_ms,  # epoch MILLISECONDS
        },
        # epoch-ms STRINGS (SDK asserts string|undefined, never numbers).
        "createdAt": str(now_ms),
        "lastLoginAt": str(now_ms),
        "apiKey": FIREBASE_API_KEY,
        "appName": DEFAULT_APP_NAME,
    }

    return {
        # (B) Firebase Web SDK persistence record. accessToken is the freshly
        # minted id_token so firebase.auth().currentUser.getIdToken() resolves on
        # first paint (before any silent refresh). The SPA also boots Firebase
        # from the custom-firebase-token cookie via signInWithCustomToken().
        "indexeddb": {
            "database": IDB_DATABASE,
            "store": IDB_STORE,
            "keyPath": IDB_KEYPATH,
            "entry": {
                "fbase_key": fbase_key,
                "value": value,
            },
        },
        # (STEP 2) The SPA's own getCurrentUser() call. The browser-side injector
        # runs THIS fetch (Cloudflare bot-check blocks bare non-browser requests),
        # takes the returned object `i`, and writes the cookies from it. Authed by
        # the `token-id` header = the minted id_token (live-proven 200; token-id
        # ALONE authenticates — no Bearer, no cookie, no 2FA).
        "login_current": {
            "method": "GET",
            "url": f"https://{LOGIN_CURRENT_HOST}{LOGIN_CURRENT_PATH}",
            "headers": {
                **GHL_STATIC_HEADERS,
                "token-id": id_token,
                # device-id is added in-browser (SPA reads it from getDeviceId /
                # localStorage; the injector supplies a stable uuid if absent).
            },
            # The returned object `i` field -> SPA cookie name. cookie `a` is
            # built from i.{apiKey,userId,companyId}; cookie custom-firebase-token
            # is i.token (the firebase custom token), NOT the id_token.
            "response_to_cookies": COOKIE_TOKEN_MAP,
        },
        # (A) The SPA cookie contract — the authoritative logged-in signal. The
        # injector populates the VALUES from the login_current response `i` and
        # writes them with these EXACT attributes (verbatim `An` setter). Cookie
        # `a` = btoa(JSON.stringify({apiKey,userId,companyId})). All are
        # JS-readable (NOT httpOnly); NO server Set-Cookie authenticates the SPA.
        "cookies": {
            "a_name": COOKIE_A_NAME,
            "a_shape": ["apiKey", "userId", "companyId"],  # exact key ORDER
            "token_map": COOKIE_TOKEN_MAP,
            "attrs": {
                "path": COOKIE_PATH,
                "maxAge": COOKIE_MAX_AGE,
                # domain/secure resolved in-browser from window.location.hostname
                # exactly as the `An` setter does (fp(hostname) -> registrable
                # domain; secure only when a domain is set).
            },
        },
        # Raw header set a pre-rehydrate XHR could use (token-id is load-bearing;
        # Authorization:Bearer alone returns 401 — token-id alone returns 200).
        "headers": {
            "token-id": id_token,
            **GHL_STATIC_HEADERS,
        },
        "meta": {
            "expirationTime": expiration_ms,
            "minted_at": int(time.time()),
            "uid": user_id,
            "id_token": id_token,            # minted Firebase id_token (token-id)
            "app_token_required": False,     # AUTH_FLOW.appTokenExchange: not needed
            "session_cookie_required": False,
            "note": "Seed Firebase IndexedDB + fetch /oauth/2/login/current (in "
                    "browser, token-id header) + write the six SPA cookies from "
                    "the response BEFORE navigating to the builder. cookie `a` is "
                    "mandatory (its absence => user_not_logged_in => login bounce). "
                    "The refresh token alone logs the SPA in (no UI login, no "
                    "2FA). id_token is short-lived (~60 min); re-run this module "
                    "or let the SDK auto-renew from refreshToken on a 401.",
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
        # The token-seed is the ONLY automatic auth path. Manual creds, if
        # present, are reported for the operator's awareness ONLY — they are
        # NOT an auto-invokable fallback. No refresh token => builder STOPS.
        has_manual = bool(os.environ.get("GHL_AGENCY_EMAIL") or os.environ.get("GHL_EMAIL"))
        print(json.dumps({
            "auth_path": "none",
            "manual_login_creds_present": has_manual,
            "note": "No refresh token. Token-seed is the ONLY auto auth path; the "
                    "builder MUST STOP. Manual GHL_AGENCY_EMAIL/PASSWORD login is "
                    "operator-only and never auto-invoked.",
        }))
        return 2

    if not token:
        sys.stderr.write(
            "No Firebase refresh token set (checked "
            + ", ".join(REFRESH_ENV_VARS)
            + "). STOP: the token-seed is the ONLY automatic auth path — do NOT "
            "auto-open the Sign-in form or any two-factor prompt. The operator "
            "must supply a fresh refresh token (re-grab via the Convert and Flow "
            "Token Grabber Chrome extension). GHL_AGENCY_EMAIL/PASSWORD is a "
            "MANUAL last resort only, never auto-invoked.\n"
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
