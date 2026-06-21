#!/usr/bin/env bash
# inject-ghl-auth.sh — Seed a logged-in GoHighLevel session into an agent-browser
# session's IndexedDB, so the builder starts authenticated without typing a
# password or hitting two-factor authentication.
#
# This is the BROWSER-SIDE half of D7. The TOKEN-SIDE half is seed-ghl-auth.py
# (mints the Firebase ID token from the client's refresh token). Order:
#
#   1. python3 seed-ghl-auth.py --print-seed --out /tmp/<session>/ghl-auth-seed.json
#   2. inject-ghl-auth.sh <session-name> /tmp/<session>/ghl-auth-seed.json
#   3. agent-browser --session <session-name> reload   (SPA rehydrates from IndexedDB)
#   4. snapshot -> confirm dashboard (NOT the login form). If login form -> seed
#      failed (token revoked) -> fall back to the login path (A1).
#
# PRIMARY ENGINE: agent-browser (Vercel Labs), headless, isolated --session.
# It must already have navigated to the GoHighLevel origin once (so the origin's
# IndexedDB exists) — pass --pre-open to do that here.
#
# WHY IndexedDB and not localStorage: the 2026-06-21 live-capture pass proved
# GoHighLevel stores Firebase auth in IndexedDB database `firebaseLocalStorageDb`,
# object store `firebaseLocalStorage` (keyPath `fbase_key`). localStorage holds
# NO token. Writing localStorage would NOT log the session in.
#
# agent-browser's own `state save/load` also captures IndexedDB; once a real
# logged-in session has been state-saved, prefer `--state <file>` for the
# verbatim post-login cookie set. This script is the path when all we have is a
# freshly minted token (no prior saved state).
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

AB_BIN="$(command -v agent-browser || echo "$HOME/.npm-global/bin/agent-browser")"

# Guard/assert: if a headed signal survived our strip, ABORT — never risk a
# visible window. AGENT_BROWSER_HEADED must be exactly "false" (we just set it);
# anything truthy means our strip failed and we refuse.
case "${AGENT_BROWSER_HEADED:-false}" in
  ""|0|false|False|FALSE|no|off) : ;;  # headless — OK
  *) echo "REFUSE: AGENT_BROWSER_HEADED='${AGENT_BROWSER_HEADED}' would open a VISIBLE window. Headless is mandatory (D6). Aborting." >&2; exit 75 ;;
esac

# AB() — the ONLY way agent-browser is invoked in this script. Forces
# `--headed false` on every call so no inherited config/env can open a window.
AB() { command "$AB_BIN" --headed false "$@"; }

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

# Ensure the origin's IndexedDB exists before we write to it.
# (AB() forces --headed false — D6 headless guard; never a visible window.)
if [ "$PRE_OPEN" = "1" ]; then
  AB --session "$SESSION" open "$ORIGIN/" >/dev/null
  AB --session "$SESSION" wait 1500 >/dev/null || true
fi

# Build the injector JS. It opens (or creates) the database, ensures the object
# store with the correct keyPath exists, and puts the entry. Reads the seed from
# an env var to avoid shell-escaping a large JSON blob.
export GHL_SEED_JSON="$(cat "$SEED_FILE")"

read -r -d '' INJECT_JS <<'JS' || true
(async () => {
  const seed = JSON.parse(__SEED__);
  const { database, store, keyPath, entry } = seed.indexeddb;

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(database);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(store)) {
          db.createObjectStore(store, { keyPath });
        }
      };
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = (e) => reject(e.target.error);
    });
  }

  let db = await openDb();
  // If the store is missing (fresh DB created by the SDK without our store),
  // bump the version to add it.
  if (!db.objectStoreNames.contains(store)) {
    const v = db.version + 1;
    db.close();
    db = await new Promise((resolve, reject) => {
      const req = indexedDB.open(database, v);
      req.onupgradeneeded = (e) => {
        const d = e.target.result;
        if (!d.objectStoreNames.contains(store)) d.createObjectStore(store, { keyPath });
      };
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
  db.close();
  return "seeded:" + entry.fbase_key;
})()
JS

# Substitute the seed JSON as a JS string literal (JSON is valid JS for a string
# via JSON.parse of a quoted blob). We pass it through window for safety.
INJECT_JS="${INJECT_JS/__SEED__/JSON.stringify(window.__GHL_SEED__)}"

# Stage the seed object on window first (small eval), then run the injector.
AB --session "$SESSION" eval --stdin <<EOF >/dev/null
window.__GHL_SEED__ = ${GHL_SEED_JSON};
EOF

RESULT="$(AB --session "$SESSION" eval --stdin <<EOF
${INJECT_JS}
EOF
)"

echo "$RESULT"

# Reload so the SPA rehydrates from the seeded IndexedDB.
AB --session "$SESSION" reload >/dev/null
AB --session "$SESSION" wait 2000 >/dev/null || true

# Caller must snapshot and confirm dashboard (NOT login form). See A1.3.
# NOTE: the snapshot below ALSO carries --headed false (D6) — every agent-browser
# call in this flow is headless; never let the next step open a visible window.
echo "NEXT: agent-browser --headed false --session ${SESSION} snapshot -i  # expect dashboard, not the Sign in form"
