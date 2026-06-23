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
#   any step fails (mint/login-current/cookie-write/verify) it exits NON-ZERO and
#   the builder MUST STOP and report. A revoked/expired token => operator
#   re-grabs a fresh refresh token (Token Grabber); it does NOT cause an automatic
#   UI login. GHL_AGENCY_EMAIL/PASSWORD is a documented MANUAL last resort only.
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

# SINGLETON SESSION: the canonical name is the gateway's single source of truth.
# Validate the caller's $1 matches it (else exit 64 via bm_assert_session) so no
# per-iteration session name (the verified 22-distinct-name leak) can slip in.
# AB_SESSION_OVERRIDE=1 is the only escape and is recorded in the lease.
bm_assert_session "$SESSION"
SESSION="$(bm_session_name)"

# Acquire the box-wide lock, write the lease, start the TTL self-kill timer, open
# the canonical session, and INSTALL the EXIT/INT/TERM/HUP teardown trap — BEFORE
# the first open. Every exit below (including the 4 non-zero REFUSE aborts) now
# guarantees teardown (close + state clear) through this trap.
bm_ensure

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
export GHL_SEED_JSON="$(cat "$SEED_FILE")"

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

# Stage the seed object on window first (small eval), then run the injector.
AB --session "$SESSION" eval --stdin <<EOF >/dev/null
window.__GHL_SEED__ = ${GHL_SEED_JSON};
EOF

# Run the injector. If the JS throws (invalid seed / login-current failure /
# cookie-write failure) the eval exits non-zero and `set -e` aborts this script —
# the builder STOPS and reports. There is NO automatic fall-back to the UI login
# form / two-factor here.
if ! RESULT="$(AB --session "$SESSION" eval --stdin <<EOF
${INJECT_JS}
EOF
)"; then
  echo "REFUSE: auth seed failed (Firebase IndexedDB / login-current fetch / cookie write). Token-seed is the ONLY auth path. Do NOT open the Sign-in form. Re-grab a fresh refresh token (Token Grabber) and retry. STOP." >&2
  exit 1
fi

# Guard: the injector returns "seeded:<key>" on success and throws otherwise.
# agent-browser 0.27.0 `eval` returns the JS return value JSON-ENCODED, so a
# string result arrives wrapped in literal double quotes
# (e.g. `"seeded:firebase:authUser:...:[DEFAULT]"`). Strip a single layer of
# surrounding double quotes before matching so a SUCCESSFUL seed is not wrongly
# REFUSEd. (Trailing CR/whitespace is also trimmed.)
RESULT="${RESULT%$'\r'}"
RESULT="${RESULT#\"}"
RESULT="${RESULT%\"}"
case "$RESULT" in
  seeded:*) : ;;
  *) echo "REFUSE: seed did not confirm (got: '${RESULT}'). Token-seed is the ONLY auth path — do NOT auto-open the login form. STOP." >&2; exit 1 ;;
esac

echo "$RESULT"

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
ACTIVATE_TARGET="${GHL_ACTIVATE_PATH:-/}"
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

AB --session "$SESSION" eval --stdin <<EOF >/dev/null
window.__GHL_ACTIVATE_TARGET__ = ${ACTIVATE_TARGET@Q};
EOF

if ! ARESULT="$(AB --session "$SESSION" eval --stdin <<EOF
${ACTIVATE_JS}
EOF
)"; then
  echo "REFUSE: session activation failed (store/router rejected the seeded auth). Token-seed is the ONLY auth path — do NOT open the Sign-in form. Re-grab a fresh refresh token (Token Grabber) and retry. STOP." >&2
  exit 1
fi
ARESULT="${ARESULT%$'\r'}"; ARESULT="${ARESULT#\"}"; ARESULT="${ARESULT%\"}"
case "$ARESULT" in
  activated:*) echo "$ARESULT" ;;
  *) echo "REFUSE: activation did not confirm (got: '${ARESULT}'). The SPA still rejected the seeded session — do NOT auto-open the login form. STOP + report." >&2; exit 1 ;;
esac

# Caller may now snapshot and confirm the app surface (NOT the login form). See A1.3.
# Every agent-browser call carries --headed false (D6). HARD RULE: if the SPA ever
# shows the Sign-in form (token revoked), the builder STOPS and reports — it MUST
# NOT auto-fill the form or trigger two-factor. The operator re-grabs a fresh
# refresh token and retries this token-seed path. NEVER `reload` after seeding —
# that re-runs the boot gate and logs the seeded session out.
echo "NEXT: agent-browser --headed false --session ${SESSION} snapshot -i  # expect the app (NOT login). Navigate via the SPA's own router (\$router.push) — do NOT reload."
