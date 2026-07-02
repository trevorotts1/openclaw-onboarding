#!/usr/bin/env bash
# inject-ghl-auth.sh — Seed a logged-in GoHighLevel session into an agent-browser
# session, so the builder starts authenticated WITHOUT typing a password and
# WITHOUT ever reaching two-factor authentication. The client's Firebase refresh
# token ALONE produces a logged-in SPA session.
#
# This is the BROWSER-SIDE half of D7 and is the ONLY auth path it drives. The
# TOKEN-SIDE half is seed-ghl-auth.py (mints the Firebase ID token from the
# client's refresh token and emits the seed contract). Order:
#
#   1. python3 seed-ghl-auth.py --print-seed --out /tmp/<session>/ghl-auth-seed.json
#   2. inject-ghl-auth.sh <session-name> /tmp/<session>/ghl-auth-seed.json --pre-open
#   3. (this script: seeds Firebase IndexedDB -> fetches /oauth/2/login/current
#      in-page (token-id header) -> writes the six SPA cookies from the response
#      -> activates via $store.dispatch('auth/get') + $router.push — NO page reload)
#   4. snapshot -> confirm dashboard (NOT the login form).
#
# BOUNDED MID-BUILD 401 RECOVERY (P2-1, final-review Point 1 fix 1): the id_token
# seed-ghl-auth.py mints is short-lived (~60min). A long build that crosses that
# window while the Firebase Web SDK's silent renew is blocked (network blip) used
# to abort hard on the FIRST 401/user_not_logged_in-class failure. This script now
# retries EXACTLY ONCE: on a detected 401/user_not_logged_in-class failure during
# or right after injection/activation, it re-runs `seed-ghl-auth.py --print-seed`
# ONE time, re-seeds with the fresh token, and re-verifies. Only a SECOND
# consecutive failure (or a re-mint that itself hits seed-ghl-auth.py's own
# exit-2/exit-3 STOP doctrine) falls through to the hard STOP below. This is
# strictly a re-mint-and-reseed of the SAME token-only path — it NEVER opens the
# Sign-in form and NEVER triggers two-factor. See _seed_and_activate_once /
# _looks_like_401_class / the retry driver near the bottom of this file.
#
# WHY BOTH COOKIES *AND* INDEXEDDB (bundle-verified chunk.DOYVEcZH.js):
#   * COOKIES are the SPA's authoritative logged-in signal. The `An` getter reads
#     cookie `a` (= btoa(JSON.stringify({apiKey,userId,companyId}))) and THROWS
#     "user_not_logged_in" if it is absent; Cl() throws "Not authenticated" with
#     no apiKey. An earlier IndexedDB-ONLY seed therefore bounced to the login
#     form (03-login-attempt.png). We MUST set cookie `a` + the five token
#     cookies (access-token-v1/v2, refresh-token-v1/v2, custom-firebase-token).
#   * FIREBASE IndexedDB is needed so the generic-API interceptor's
#     `token-id = await firebase.auth().currentUser.getIdToken()` resolves on data
#     XHRs (the SPA also boots Firebase from the custom-firebase-token cookie via
#     signInWithCustomToken()).
#   The cookie VALUES come from the SPA's own getCurrentUser():
#     GET /oauth/2/login/current  headers{channel,source,version,device-id,token-id}
#   run IN this browser (Cloudflare's bot-check WAF — error 1010 — blocks bare
#   non-browser requests; inside agent-browser the clearance + UA are automatic).
#   It returns {token, jwt, refreshJwt, apiKey, authToken, refreshToken, userId,
#   companyId} — live-proven 200, token-id alone authenticates, no 2FA.
#
# HARD RULE — NO AUTOMATIC UI-LOGIN / 2FA FALLBACK:
#   This script NEVER drives the Sign-in form and NEVER triggers two-factor. If
#   any step fails (mint/login-current/cookie-write/verify) — including after the
#   ONE bounded re-mint+re-seed above — it exits NON-ZERO and the builder MUST
#   STOP and report. A revoked/expired token => operator re-grabs a fresh refresh
#   token (Token Grabber); it does NOT cause an automatic UI login.
#   GHL_AGENCY_EMAIL/PASSWORD is a documented MANUAL last resort only.
#
# PRIMARY ENGINE: agent-browser (Vercel Labs), headless, isolated --session.
# It must already have navigated to the GoHighLevel origin once (so cookies bind
# to the right origin + the Firebase IndexedDB exists) — pass --pre-open here.
#
# agent-browser's own `state save/load` also captures cookies + IndexedDB; once a
# real logged-in session has been state-saved, prefer `--state <file>` for the
# verbatim cookie set. This script is the path when all we have is a freshly
# minted token (no prior saved state).
set -euo pipefail

# ── D6: HARD HEADLESS GUARD ──────────────────────────────────────────────────
# HEADLESS-ONLY — never open a visible window; taking over a screen is forbidden
# (esp. client boxes). A live run once opened a VISIBLE Chromium window because
# agent-browser inherited a headed config / env: agent-browser is headless by
# default, but an AGENT_BROWSER_HEADED env var OR a {"headed": true} config file
# silently forces a headed window. We close that door three ways, on EVERY
# invocation, dev OR client:
#   1. Strip the inherited env       -> unset AGENT_BROWSER_HEADED
#   2. Force headless on the CLI     -> AB() wrapper appends `--headed false`,
#      which the agent-browser docs define as the explicit override that also
#      disables "headed": true from a config file.
#   3. Refuse to proceed if headed could still be on (assert below).
# `--headed false` is a documented hard override (agent-browser 0.27.0): it
# disables a config-file "headed": true. There is NO code path here that may
# open a headed window.
unset AGENT_BROWSER_HEADED 2>/dev/null || true
export AGENT_BROWSER_HEADED=false   # belt: any child that re-reads env sees false

# Guard/assert: if a headed signal survived our strip, ABORT — never risk a
# visible window. AGENT_BROWSER_HEADED must be exactly "false" (we just set it);
# anything truthy means our strip failed and we refuse.
case "${AGENT_BROWSER_HEADED:-false}" in
  ""|0|false|False|FALSE|no|off) : ;;  # headless — OK
  *) echo "REFUSE: AGENT_BROWSER_HEADED='${AGENT_BROWSER_HEADED}' would open a VISIBLE window. Headless is mandatory (D6). Aborting." >&2; exit 75 ;;
esac

# ── SINGLETON POOLED BROWSER — route ALL agent-browser calls through the gateway
# (browser_manager.sh). It re-uses the D6 guard above VERBATIM and owns AB_BIN +
# the lock-asserting AB() wrapper, the box-wide lock (lock=1), the lease, the
# per-call + per-session TTL, the pool ceiling, the circuit-breaker, and the
# GUARANTEED `trap _bm_teardown EXIT INT TERM HUP`. This closes the orphan gap:
# the 4 non-zero aborts below (the REFUSE/exit 1 sites) now ALWAYS fire teardown
# via the inherited EXIT trap. Sourcing must NOT clobber our set -euo pipefail
# (the manager deliberately does NOT set -e at source time). [verified live
# damage 2026-06-23: 22 orphan *.engine, 357M — no teardown existed in 06.]
# shellcheck source=browser_manager.sh
source "$(dirname "$0")/browser_manager.sh"

TOOLS_DIR="$(dirname "$0")"
SESSION="${1:-}"
SEED_FILE="${2:-}"
ORIGIN="${GHL_AGENCY_URL:-https://app.convertandflow.com}"
PRE_OPEN=0
[ "${3:-}" = "--pre-open" ] && PRE_OPEN=1

if [ -z "$SESSION" ] || [ -z "$SEED_FILE" ]; then
  echo "usage: inject-ghl-auth.sh <session-name> <seed.json> [--pre-open]" >&2
  exit 64
fi
[ -f "$SEED_FILE" ] || { echo "seed file not found: $SEED_FILE" >&2; exit 66; }
[ -x "$AB_BIN" ] || { echo "agent-browser not found (Skill 03 must be installed)" >&2; exit 69; }

# ── P2-4: AGENT-BROWSER VERSION-PIN GUARD (fail loud on drift) ─────────────────
# Every gate selector (tools/gates.json), the `eval` JSON-encoding the injector
# relies on, the auto-inlined-iframe snapshot shape, and the `--headed false`
# override semantics were captured/proven against ONE pinned agent-browser
# version. A silent upgrade can change CLI flags / eval encoding / snapshot shape
# and break this seed+activate flow in ways that LOOK like an auth failure
# (login bounce) but are really an engine drift. We FAIL LOUD on drift here —
# before opening the browser — rather than mis-diagnose it downstream. Override
# (operator-acknowledged) with GHL_AB_ALLOW_VERSION_DRIFT=1; re-pin with
# GHL_AB_PINNED_VERSION after a deliberate re-capture.
#
# SINGLE-SOURCE (P3-3, final-review Point 1 fix 3): the pin value used to be a
# bare inline "0.27.0" default HERE, independent of gates.json — a second place
# that could drift from the gate registry / from browser_manager.py's own
# assert_agent_browser_version() (which already reads gates.json). Precedence now
# mirrors browser_manager.py::_read_pinned_agent_browser_version() exactly, so
# the shell and Python sides share ONE source of truth:
#   1. GHL_AB_PINNED_VERSION env var (operator override after a deliberate
#      re-capture) — unchanged, highest precedence.
#   2. gates.json::agent_browser_version_pin.pinned_version (the single source
#      of record).
#   3. Hard-coded fallback "0.27.0" — ONLY if gates.json is missing/unreadable
#      (matches gates.json at ship time; python3 is already a hard dependency of
#      this flow, see the ACTIVATE_TARGET_JSON encoding below).
if [ -n "${GHL_AB_PINNED_VERSION:-}" ]; then
  : # operator override — highest precedence, nothing to resolve.
else
  GATES_JSON_PATH="$TOOLS_DIR/gates.json"
  GHL_AB_PINNED_VERSION="$(python3 - "$GATES_JSON_PATH" <<'PY' 2>/dev/null
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    v = data.get("agent_browser_version_pin", {}).get("pinned_version", "")
    print(v.strip() if isinstance(v, str) and v.strip() else "0.27.0")
except Exception:
    print("0.27.0")
PY
)"
  [ -n "$GHL_AB_PINNED_VERSION" ] || GHL_AB_PINNED_VERSION="0.27.0"
fi
AB_VERSION_RAW="$("$AB_BIN" --version 2>/dev/null | head -n1 | tr -d '[:space:]' || true)"
# Extract a semver token (e.g. 0.27.0) from whatever the CLI prints.
AB_VERSION="$(printf '%s' "$AB_VERSION_RAW" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"
if [ -z "$AB_VERSION" ]; then
  if [ "${GHL_AB_ALLOW_VERSION_DRIFT:-0}" = "1" ]; then
    echo "WARN: could not read agent-browser version (raw: '${AB_VERSION_RAW}'); GHL_AB_ALLOW_VERSION_DRIFT=1 — proceeding unpinned (risk acknowledged)." >&2
  else
    echo "REFUSE: could not determine agent-browser version (raw: '${AB_VERSION_RAW}'). This seed/activate flow is PINNED to ${GHL_AB_PINNED_VERSION}; an unverifiable engine cannot be trusted. Set GHL_AB_ALLOW_VERSION_DRIFT=1 to override (operator-acknowledged). STOP." >&2
    exit 70
  fi
elif [ "$AB_VERSION" != "$GHL_AB_PINNED_VERSION" ]; then
  if [ "${GHL_AB_ALLOW_VERSION_DRIFT:-0}" = "1" ]; then
    echo "WARN: agent-browser ${AB_VERSION} != pinned ${GHL_AB_PINNED_VERSION}; GHL_AB_ALLOW_VERSION_DRIFT=1 — proceeding despite drift (risk acknowledged)." >&2
  else
    echo "REFUSE: agent-browser version drift — found ${AB_VERSION}, pinned ${GHL_AB_PINNED_VERSION}. The gates.json selectors + eval/snapshot semantics were captured against ${GHL_AB_PINNED_VERSION}; an unverified upgrade can silently break seed/activate (login bounce). Re-pin via GHL_AB_PINNED_VERSION after re-capturing, or set GHL_AB_ALLOW_VERSION_DRIFT=1 to override. STOP." >&2
    exit 70
  fi
fi

# SINGLETON SESSION: the canonical name is the gateway's single source of truth.
# Validate the caller's $1 matches it (else exit 64 via bm_assert_session) so no
# per-iteration session name (the verified 22-distinct-name leak) can slip in.
# AB_SESSION_OVERRIDE=1 is the only escape and is recorded in the lease.
bm_assert_session "$SESSION"
SESSION="$(bm_session_name)"

# Acquire the box-wide lock, write the lease, start the TTL self-kill timer, open
# the canonical session, and INSTALL the EXIT/INT/TERM/HUP teardown trap — BEFORE
# the first open. Every exit below (including the non-zero REFUSE aborts) now
# guarantees teardown (close + state clear) through this trap.
bm_ensure

# ── P3-4: SESSION-SCOPED TEMPDIR + CHAINED CLEANUP TRAP (final-review Point 1
# fix 4) ─────────────────────────────────────────────────────────────────────
# Anything THIS script writes to disk (the bounded re-mint's fresh seed file, the
# per-attempt stderr diagnostics used to classify a 401/user_not_logged_in
# failure) goes under a `mktemp -d` session tempdir instead of a caller-chosen
# /tmp path that is not guaranteed to be swept. The explicit --out override on
# seed-ghl-auth.py itself still works unchanged for external callers (Step 1 in
# the header above) — this only hardens the seed file THIS script mints
# internally during the bounded 401 recovery retry.
#
# CRITICAL — DO NOT clobber bm_ensure's teardown trap: bm_ensure (just above)
# already installed `trap _bm_teardown EXIT INT TERM HUP` — the guaranteed
# browser-session close/state-clear that closes the 22-orphan-engine leak this
# file documents at the top. A naive `trap 'rm -rf ...' EXIT` here would REPLACE
# that trap and silently reintroduce the orphan leak. Instead we install a
# combined teardown that does our rm -rf FIRST, then explicitly calls the same
# _bm_teardown the gateway guarantees, so neither cleanup is ever skipped.
GHL_INJECT_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/ghl-inject-auth.XXXXXX")"
_ghl_inject_teardown() {
  rm -rf "$GHL_INJECT_TMPDIR" 2>/dev/null || true
  _bm_teardown
}
trap _ghl_inject_teardown EXIT INT TERM HUP

# Ensure the origin is open + the SPA is MOUNTED before we seed: activation drives
# the SPA's own store + router (#app.__vue_app__), which only exists once the app
# bundle has booted. The page will bounce to /login (no valid session yet) — that
# is expected; we only need #app mounted so $store/$router are reachable.
# (AB() forces --headed false — D6 headless guard; never a visible window.)
if [ "$PRE_OPEN" = "1" ]; then
  AB --session "$SESSION" open "$ORIGIN/" >/dev/null
  # Poll for the Vue app mount (up to ~12s) instead of a flat sleep.
  for _i in 1 2 3 4 5 6 7 8; do
    MOUNTED="$(AB --session "$SESSION" eval "!!(document.querySelector('#app')&&document.querySelector('#app').__vue_app__)" 2>/dev/null || echo false)"
    case "$MOUNTED" in *true*) break ;; esac
    AB --session "$SESSION" wait 1500 >/dev/null || true
  done
fi

# Build the injector JS. It (1) seeds the Firebase IndexedDB record, (2) fetches
# /oauth/2/login/current IN this browser (token-id header) to get the logged-in
# object `i`, and (3) writes the SPA's six auth cookies from `i` using the
# verbatim `An` setter template (cookie `a` = btoa({apiKey,userId,companyId}) is
# the authoritative logged-in signal). Reads the seed from window.__GHL_SEED__ to
# avoid shell-escaping a large JSON blob.
read -r -d '' INJECT_JS <<'JS' || true
(async () => {
  const seed = __SEED__;
  const { database, store, keyPath, entry } = seed.indexeddb;

  // ── (B) FAIL LOUD before writing the Firebase record ──────────────────────
  // The Firebase Web SDK User._fromJSON() asserts typeof emailVerified==='boolean'
  // and typeof isAnonymous==='boolean', and needs uid + a stsTokenManager with
  // refreshToken + accessToken. A record missing these throws auth/internal-error
  // on rehydrate. We refuse to seed a record that would not log in.
  const v = entry && entry.value || {};
  const missing = [];
  if (!v.uid) missing.push("uid");
  if (typeof v.emailVerified !== "boolean") missing.push("emailVerified(boolean)");
  if (typeof v.isAnonymous !== "boolean") missing.push("isAnonymous(boolean)");
  if (!v.stsTokenManager || !v.stsTokenManager.refreshToken) missing.push("stsTokenManager.refreshToken");
  if (!v.stsTokenManager || !v.stsTokenManager.accessToken) missing.push("stsTokenManager.accessToken");
  if (missing.length) throw new Error("SEED-INVALID: missing/badtype " + missing.join(","));

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(database);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(store)) db.createObjectStore(store, { keyPath });
      };
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = (e) => reject(e.target.error);
    });
  }
  let db = await openDb();
  if (!db.objectStoreNames.contains(store)) {
    const ver = db.version + 1; db.close();
    db = await new Promise((resolve, reject) => {
      const req = indexedDB.open(database, ver);
      req.onupgradeneeded = (e) => { const d = e.target.result; if (!d.objectStoreNames.contains(store)) d.createObjectStore(store, { keyPath }); };
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = (e) => reject(e.target.error);
    });
  }
  await new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(entry);
    tx.oncomplete = () => resolve();
    tx.onerror = (e) => reject(e.target.error);
  });
  const got = await new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const r = tx.objectStore(store).get(entry.fbase_key);
    r.onsuccess = () => resolve(r.result);
    r.onerror = (e) => reject(e.target.error);
  });
  db.close();
  if (!got || !got.value || !got.value.stsTokenManager ||
      got.value.stsTokenManager.accessToken !== entry.value.stsTokenManager.accessToken) {
    throw new Error("SEED-READBACK-FAILED: firebase record did not persist for " + entry.fbase_key);
  }

  // ── (STEP 2) getCurrentUser() — the SPA's own login/current call ──────────
  // Authed by token-id (the minted id_token). Done HERE because Cloudflare's
  // bot-check (error 1010) blocks bare non-browser requests; the agent-browser
  // carries the clearance + a real UA automatically. NOTE: credentials are
  // OMITTED — exactly like the SPA's own axios. The GHL backend's CORS does NOT
  // allow credentialed cross-origin requests, so credentials:"include" makes the
  // browser block it ("Failed to fetch"); credentials:"omit" returns 200.
  const lc = seed.login_current;
  // Stable device-id (SPA reads getDeviceId/localStorage; supply one if absent).
  let deviceId = "";
  try { deviceId = localStorage.getItem("deviceId") || ""; } catch (e) {}
  if (!deviceId) {
    deviceId = (crypto && crypto.randomUUID) ? crypto.randomUUID()
      : ("dev-" + Date.now() + "-" + Math.random().toString(16).slice(2));
    try { localStorage.setItem("deviceId", deviceId); } catch (e) {}
  }
  const lcHeaders = Object.assign({}, lc.headers, { "device-id": deviceId });

  // ── LAYER-2 HARDENING: bounded retry around the login/current fetch ─────────
  // ROOT CAUSE of the intermittent Layer-2 failure (proven by the 2026-06-21
  // run: 3 injects bounced to login, the 4th — after a settle — succeeded; the
  // minted id_token was byte-perfect every time). The in-browser GET
  // /oauth/2/login/current is a SINGLE-SHOT fetch that races against (a)
  // Cloudflare's bot-check (error 1010) interstitial / a transient 5xx, and (b)
  // the SPA's network stack still warming up right after open — either of which
  // yields a non-200 OR a 200 whose body is a challenge/partial JSON that
  // .json() coerces into an object with a present-but-WRONG apiKey. The old
  // guard `if (!i.apiKey)` accepted any non-empty string, so a bad apiKey landed
  // in cookie `a` and the SPA's own auth/get then rejected it -> login bounce.
  // FIX (token-only, no login/2FA): retry up to 4 attempts with exponential
  // backoff + jitter; treat anything that isn't a clean authoritative 200 as
  // retryable; only fail loud after the budget is exhausted. The authoritative
  // shape is asserted: apiKey must be a non-trivial key (>= 8 chars), userId
  // must be present. This does NOT change the auth MODEL — same token-id header,
  // same endpoint, same credentials:"omit" — it only makes the one transient
  // network step reliable.
  const LC_MAX_ATTEMPTS = 4;
  function jitter(ms) { return Math.round(ms * (0.7 + Math.random() * 0.6)); }
  function looksAuthoritative(o) {
    return !!(o && typeof o.apiKey === "string" && o.apiKey.length >= 8 &&
              typeof o.userId === "string" && o.userId.length >= 8);
  }
  let i = null, lastErr = "";
  for (let attempt = 1; attempt <= LC_MAX_ATTEMPTS; attempt++) {
    try {
      const resp = await fetch(lc.url, { method: lc.method || "GET", headers: lcHeaders, mode: "cors", credentials: "omit" });
      if (resp.status !== 200) {
        const body = (await resp.text()).slice(0, 200);
        // 401/403/1010 = bot-check/clearance not yet warm; 5xx/429 = transient.
        // All retryable here (the token itself is valid — Layer 1 verified it).
        lastErr = "LOGIN-CURRENT-" + resp.status + ": " + body;
      } else {
        const cand = await resp.json();
        if (looksAuthoritative(cand)) { i = cand; break; }
        // 200 but body is a challenge/partial — present apiKey is garbage.
        lastErr = "LOGIN-CURRENT-NONAUTH: keys=" + Object.keys(cand || {}).join(",") +
                  " apiKeyLen=" + ((cand && cand.apiKey && cand.apiKey.length) || 0);
      }
    } catch (e) {
      // Network/CORS/parse error -> retryable.
      lastErr = "LOGIN-CURRENT-FETCH: " + (e && e.message || e);
    }
    if (attempt < LC_MAX_ATTEMPTS) {
      await new Promise(r => setTimeout(r, jitter(400 * Math.pow(2, attempt - 1)))); // ~400/800/1600ms +/- jitter
    }
  }
  if (!i) {
    throw new Error("LOGIN-CURRENT-FAILED after " + LC_MAX_ATTEMPTS + " attempts: " + lastErr);
  }

  // ── (A) Write the six SPA cookies from `i` — VERBATIM `An` setter template ──
  // From chunk.DOYVEcZH.js:
  //   a="/"; i=(e===null?-1:1)*31536e3; n=fp(hostname); s=n?`domain=${n};`:"";
  //   o=n?"secure":""; cookie a=btoa(JSON.stringify({apiKey,userId,companyId}));
  //   access-token-v1=jwt; refresh-token-v1=refreshJwt; access-token-v2=authToken;
  //   refresh-token-v2=refreshToken; custom-firebase-token=firebaseToken(=i.token)
  const ckA = seed.cookies;
  const path = (ckA.attrs && ckA.attrs.path) || "/";
  const maxAge = (ckA.attrs && ckA.attrs.maxAge) || 31536000;
  // fp(hostname): registrable domain (last two labels) — the SPA only sets the
  // domain attribute when this resolves, and only then adds `secure`.
  function registrableDomain(host) {
    if (!host || /^[0-9.]+$/.test(host) || host === "localhost") return "";
    const parts = host.split(".");
    if (parts.length < 2) return "";
    return parts.slice(-2).join(".");
  }
  const dom = registrableDomain(window.location.hostname);
  const domStr = dom ? ("domain=" + dom + ";") : "";
  const secStr = dom ? "secure" : "";
  function setCookie(name, value) {
    document.cookie = name + "=" + (value == null ? "" : value) + ";" + domStr + "path=" + path + ";Max-Age=" + maxAge + ";" + secStr + ";";
  }
  // cookie `a` — authoritative logged-in signal. Exact key ORDER per a_shape.
  const aObj = {};
  for (const k of ckA.a_shape) aObj[k] = (i[k] != null ? i[k] : "");
  setCookie(ckA.a_name, btoa(JSON.stringify(aObj)));
  // The five token cookies. firebaseToken := i.token (the firebase custom token).
  const responseFields = { jwt: i.jwt, refreshJwt: i.refreshJwt, authToken: i.authToken, refreshToken: i.refreshToken, firebaseToken: i.token };
  for (const [field, cookieName] of Object.entries(ckA.token_map)) {
    setCookie(cookieName, responseFields[field] != null ? responseFields[field] : "");
  }

  // Read cookie `a` back and confirm it decodes to an object carrying apiKey —
  // never report "seeded" if the SPA's logged-in signal did not land.
  function getCookie(n) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)"));
    return m ? m[1] : null;
  }
  const rawA = getCookie(ckA.a_name);
  let decoded = null;
  try { decoded = rawA ? JSON.parse(atob(rawA)) : null; } catch (e) {}
  if (!decoded || !decoded.apiKey) {
    throw new Error("COOKIE-A-READBACK-FAILED: cookie `a` missing/undecodable (the SPA would throw user_not_logged_in)");
  }
  return "seeded:" + entry.fbase_key + "|cookie-a:apiKey=" + String(decoded.apiKey).slice(0, 6) + "...|userId=" + decoded.userId;
})()
JS

# The injector reads the seed as a live JS OBJECT (not a JSON string), so it can
# access seed.indexeddb / seed.login_current / seed.cookies directly. We stage
# the object on window first, then substitute __SEED__ -> window.__GHL_SEED__.
INJECT_JS="${INJECT_JS/__SEED__/window.__GHL_SEED__}"

# ── DO NOT RELOAD ─────────────────────────────────────────────────────────────
# A full page reload re-runs the agency whitelabel boot gate (the "[redirectIIFE]
# post-ready check" IIFE), which calls firebase signOut() and WIPES the seeded
# Firebase IndexedDB record before it is used, then bounces to /login?logout=true.
# PROVEN: seed + reload => login bounce; seed + in-app router nav => logged in.
# So instead we activate the session through the SPA's OWN store + router (exactly
# what a real login does): commit auth/get (reads the seeded cookies) + user/get,
# then $router.push() to the post-login surface. No full navigation, so the boot
# IIFE never re-runs. The injector already verified cookie `a` decodes; here we
# confirm the store accepts it (auth/get returns a user) and land on the app.
# NEVER `reload` after seeding, including on the bounded re-mint retry below —
# re-seeding reuses this SAME session via eval only, never a navigate/open/reload.
ACTIVATE_TARGET="${GHL_ACTIVATE_PATH:-/}"
# Pre-encode the target path as a JS/JSON string literal, then plain-interpolate
# it below (same SAFE pattern as window.__GHL_SEED__ = ${GHL_SEED_JSON}). NOTE:
# macOS ships /bin/bash 3.2.57 which has NO ${VAR@Q} operator (bad substitution),
# so @Q must not be used here. python3 is already a hard dependency of this flow.
ACTIVATE_TARGET_JSON="$(printf '%s' "$ACTIVATE_TARGET" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"

read -r -d '' ACTIVATE_JS <<'AJS' || true
(async () => {
  // ── LAYER-2 HARDENING: bounded retry around store/router activation ─────────
  // ROOT CAUSE of ACTIVATE-BOUNCED-TO-LOGIN (the intermittent failure seen
  // 2026-06-21): activation fired before the SPA's auth store had finished
  // booting / re-reading the freshly written cookies. `store.dispatch('auth/get')`
  // then resolved against a not-yet-warm store (or the just-set cookies were not
  // yet visible to its cookie layer) and the router redirected to /login. A
  // single 800ms settle was sometimes too short (3 fails) and sometimes enough
  // (the 4th attempt, after a longer manual wait, succeeded). FIX (token-only,
  // no login/2FA): poll for store+router readiness, then retry auth/get +
  // router.push up to 4 times with exponential backoff + jitter, and only
  // declare success once we are verifiably NOT on the login form AND auth/get
  // returned a real user. Fail loud only after the budget is exhausted. Same
  // SPA APIs, same cookies — no auth-model change.
  const ACT_MAX_ATTEMPTS = 4;
  function jitter(ms) { return Math.round(ms * (0.7 + Math.random() * 0.6)); }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // Wait (up to ~8s) for #app -> __vue_app__ -> $store + $router to all exist;
  // activation has no meaning until the SPA store is mounted.
  let store = null, router = null;
  for (let w = 0; w < 16; w++) {
    const el = document.querySelector('#app');
    const gp = el && el.__vue_app__ && el.__vue_app__.config && el.__vue_app__.config.globalProperties;
    if (gp && gp.$store && gp.$router) { store = gp.$store; router = gp.$router; break; }
    await sleep(500);
  }
  if (!store || !router) throw new Error("ACTIVATE-NO-STORE-ROUTER: SPA store/router never mounted (open the GHL origin first / --pre-open)");

  let user = null, lastErr = "";
  for (let attempt = 1; attempt <= ACT_MAX_ATTEMPTS; attempt++) {
    // auth/get reads the seeded cookie `a` (+ token cookies). A transient reject
    // here (store not warm / cookies not yet visible) is RETRYABLE — it does NOT
    // mean the token is bad (Layer 1 minted it fresh + verified).
    try {
      user = await store.dispatch('auth/get');
    } catch (e) {
      user = null; lastErr = "AUTHGET-REJECT: " + (e && e.message || e);
    }
    if (user && user.apiKey && user.userId) {
      try { await store.dispatch('user/get'); } catch (e) { /* non-fatal: some accounts gate user/get */ }
      try { await router.push({ path: window.__GHL_ACTIVATE_TARGET__ || '/' }); } catch (e) { /* router may redirect; verified below */ }
      await sleep(900);
      const hasPwd = !!document.querySelector('input[type=password]');
      const onLogin = /[?&]logout=true/.test(location.href) || /\/login(\b|$)/.test(location.pathname) || hasPwd;
      if (!onLogin) {
        return "activated:userId=" + user.userId + "|href=" + location.href + "|attempt=" + attempt;
      }
      // auth/get returned a user but we still landed on login — the seed had not
      // fully settled; re-seed-read on the next attempt.
      lastErr = "BOUNCED-TO-LOGIN: href=" + location.href + " hasPwd=" + hasPwd;
    } else if (!lastErr) {
      lastErr = "AUTHGET-NOUSER";
    }
    if (attempt < ACT_MAX_ATTEMPTS) {
      await sleep(jitter(600 * Math.pow(2, attempt - 1))); // ~600/1200/2400ms +/- jitter, lets the store warm
    }
  }
  throw new Error("ACTIVATE-FAILED after " + ACT_MAX_ATTEMPTS + " attempts: " + lastErr);
})()
AJS

# ── STAGE + INJECT + ACTIVATE, as reusable functions (P2-1 hardening) ─────────
# The original one-shot script inlined this as straight-line code. It is now
# wrapped in functions ONLY so the bounded re-mint retry below can re-run the
# exact same seed+activate sequence a second time (with a freshly minted seed)
# without duplicating the JS payloads above. Nothing about WHAT is sent to the
# browser changes — same eval calls, same heredoc JS, same no-reload discipline.

# _stage_and_inject <seed-file>
#   Sets INJECT_RESULT ("seeded:..." on success) and INJECT_ERR (stderr
#   diagnostic text, always). Returns 0 on a confirmed "seeded:" result, 1
#   otherwise (including a nonzero eval exit).
_stage_and_inject() {
  local seed_file="$1"
  local err_file="$GHL_INJECT_TMPDIR/inject-stderr.log"
  : > "$err_file"

  export GHL_SEED_JSON="$(cat "$seed_file")"

  if ! AB --session "$SESSION" eval --stdin <<EOF >/dev/null 2>"$err_file"
window.__GHL_SEED__ = ${GHL_SEED_JSON};
EOF
  then
    INJECT_ERR="$(cat "$err_file" 2>/dev/null || true)"
    INJECT_RESULT=""
    return 1
  fi

  local result
  if ! result="$(AB --session "$SESSION" eval --stdin <<EOF 2>"$err_file"
${INJECT_JS}
EOF
)"; then
    INJECT_ERR="$(cat "$err_file" 2>/dev/null || true)"
    INJECT_RESULT="$result"
    return 1
  fi
  INJECT_ERR="$(cat "$err_file" 2>/dev/null || true)"

  # agent-browser 0.27.0 `eval` returns the JS return value JSON-ENCODED, so a
  # string result arrives wrapped in literal double quotes. Strip a single layer
  # of surrounding double quotes (+ trailing CR) before matching.
  result="${result%$'\r'}"
  result="${result#\"}"
  result="${result%\"}"
  INJECT_RESULT="$result"
  case "$INJECT_RESULT" in
    seeded:*) return 0 ;;
    *) return 1 ;;
  esac
}

# _stage_and_activate
#   Uses the already-computed ACTIVATE_TARGET_JSON (global, seed-independent).
#   Sets ACTIVATE_RESULT ("activated:..." on success) and ACTIVATE_ERR (stderr
#   diagnostic text, always). Returns 0 on a confirmed "activated:" result, 1
#   otherwise.
_stage_and_activate() {
  local err_file="$GHL_INJECT_TMPDIR/activate-stderr.log"
  : > "$err_file"

  if ! AB --session "$SESSION" eval --stdin <<EOF >/dev/null 2>"$err_file"
window.__GHL_ACTIVATE_TARGET__ = ${ACTIVATE_TARGET_JSON};
EOF
  then
    ACTIVATE_ERR="$(cat "$err_file" 2>/dev/null || true)"
    ACTIVATE_RESULT=""
    return 1
  fi

  local aresult
  if ! aresult="$(AB --session "$SESSION" eval --stdin <<EOF 2>"$err_file"
${ACTIVATE_JS}
EOF
)"; then
    ACTIVATE_ERR="$(cat "$err_file" 2>/dev/null || true)"
    ACTIVATE_RESULT="$aresult"
    return 1
  fi
  ACTIVATE_ERR="$(cat "$err_file" 2>/dev/null || true)"

  aresult="${aresult%$'\r'}"
  aresult="${aresult#\"}"
  aresult="${aresult%\"}"
  ACTIVATE_RESULT="$aresult"
  case "$ACTIVATE_RESULT" in
    activated:*) return 0 ;;
    *) return 1 ;;
  esac
}

# _seed_and_activate_once <seed-file>
#   The full seed+activate sequence against ONE seed file. Returns 0 only if
#   BOTH steps confirmed. This is called twice at most: once with the original
#   seed, and — ONLY on a detected 401/user_not_logged_in-class failure — once
#   more with a freshly re-minted seed (never a third time; see the driver).
_seed_and_activate_once() {
  local seed_file="$1"
  _stage_and_inject "$seed_file" || return 1
  _stage_and_activate || return 1
  return 0
}

# _looks_like_401_class <diagnostic-text>
#   Classifies a failure as "re-mintable" — i.e. the token-id the browser is
#   holding was rejected as unauthenticated (401-class) rather than the seed
#   being structurally malformed, the SPA never mounting, or some other
#   non-token failure a re-mint cannot fix. Matched ONLY against the specific
#   error signatures the JS above already throws (LOGIN-CURRENT-401/403/
#   NONAUTH, the explicit "user_not_logged_in" doc string on a cookie-`a`
#   readback failure, and the activation-side BOUNCED-TO-LOGIN / AUTHGET-*
#   signatures). Deliberately does NOT match SEED-INVALID, SEED-READBACK-FAILED,
#   or ACTIVATE-NO-STORE-ROUTER — those are not token problems and a re-mint
#   would not fix them (re-minting would just burn the one bounded retry on a
#   failure mode it cannot recover).
_looks_like_401_class() {
  case "$1" in
    *LOGIN-CURRENT-401*|*LOGIN-CURRENT-403*|*LOGIN-CURRENT-NONAUTH*|*user_not_logged_in*|*COOKIE-A-READBACK-FAILED*|*BOUNCED-TO-LOGIN*|*AUTHGET-REJECT*|*AUTHGET-NOUSER*|*"Not authenticated"*)
      return 0 ;;
    *)
      return 1 ;;
  esac
}

# ── THE RETRY DRIVER (P2-1) ────────────────────────────────────────────────────
# 1st attempt with the seed file the caller passed in. On failure, classify: if
# (and ONLY if) the failure signature is 401/user_not_logged_in-class AND no
# re-mint has been attempted yet this run, do ONE bounded re-mint (re-run
# seed-ghl-auth.py --print-seed into the session tempdir) + ONE re-seed attempt.
# Any other outcome — a non-401-class failure, OR a second consecutive failure
# after the re-mint, OR the re-mint itself hitting seed-ghl-auth.py's own
# exit-2/exit-3 STOP doctrine — falls through to a hard STOP. There is NO third
# attempt and NO UI-login/2FA path; this is strictly "re-mint the same
# token-only seed once, then STOP" per D7.
CURRENT_SEED_FILE="$SEED_FILE"
REMINT_ATTEMPTED=0

if ! _seed_and_activate_once "$CURRENT_SEED_FILE"; then
  DIAG="${INJECT_ERR:-}${INJECT_RESULT:-}${ACTIVATE_ERR:-}${ACTIVATE_RESULT:-}"

  if [ "$REMINT_ATTEMPTED" = "0" ] && _looks_like_401_class "$DIAG"; then
    REMINT_ATTEMPTED=1
    echo "WARN: detected a 401/user_not_logged_in-class auth failure (id_token likely crossed its ~60min window while the SDK's silent renew was blocked). D7 token-only doctrine: attempting ONE bounded re-mint + re-seed on the SAME session before any hard STOP. No UI-login/2FA path exists or will be added." >&2

    REMINT_SEED_FILE="$GHL_INJECT_TMPDIR/ghl-auth-reseed.json"
    # Capture seed-ghl-auth.py's REAL exit code (2=no token, 3=revoked/expired) —
    # NOT the negated status `if ! cmd` would give — so its own STOP doctrine
    # propagates faithfully. Bracket with set +e/-e rather than `if !`.
    set +e
    python3 "$TOOLS_DIR/seed-ghl-auth.py" --print-seed --out "$REMINT_SEED_FILE"
    REMINT_RC=$?
    set -e
    if [ "$REMINT_RC" != "0" ]; then
      echo "REFUSE: bounded re-mint failed — seed-ghl-auth.py's own STOP doctrine applies (exit 2 = no usable refresh token; exit 3 = refresh token present but revoked/expired, re-grab via the Token Grabber). Token-seed remains the ONLY auth path; do NOT open the Sign-in form. STOP." >&2
      exit "$REMINT_RC"
    fi

    CURRENT_SEED_FILE="$REMINT_SEED_FILE"
    if ! _seed_and_activate_once "$CURRENT_SEED_FILE"; then
      RETRY_DIAG="${INJECT_ERR:-}${INJECT_RESULT:-}${ACTIVATE_ERR:-}${ACTIVATE_RESULT:-}"
      echo "REFUSE: auth failed AGAIN after the one bounded re-mint + re-seed (no loop — D7 token-only doctrine). Token-seed is the ONLY auth path; do NOT open the Sign-in form or trigger two-factor. Re-grab a fresh refresh token (Token Grabber) and retry. STOP." >&2
      echo "         diagnostic: ${RETRY_DIAG:0:400}" >&2
      exit 3
    fi
  else
    echo "REFUSE: auth seed failed (Firebase IndexedDB / login-current fetch / cookie write / activation) and does not match a recoverable 401/user_not_logged_in signature (or a re-mint was already attempted this run). Token-seed is the ONLY auth path. Do NOT open the Sign-in form. Re-grab a fresh refresh token (Token Grabber) and retry. STOP." >&2
    echo "         diagnostic: ${DIAG:0:400}" >&2
    exit 1
  fi
fi

echo "$INJECT_RESULT"
echo "$ACTIVATE_RESULT"

# Caller may now snapshot and confirm the app surface (NOT the login form). See A1.3.
# Every agent-browser call carries --headed false (D6). HARD RULE: if the SPA ever
# shows the Sign-in form (token revoked), the builder STOPS and reports — it MUST
# NOT auto-fill the form or trigger two-factor. The operator re-grabs a fresh
# refresh token and retries this token-seed path (this script already attempts
# ONE bounded re-mint+re-seed internally before giving up — see the retry driver
# above). NEVER `reload` after seeding — that re-runs the boot gate and logs the
# seeded session out.
echo "NEXT: agent-browser --headed false --session ${SESSION} snapshot -i  # expect the app (NOT login). Navigate via the SPA's own router (\$router.push) — do NOT reload."
