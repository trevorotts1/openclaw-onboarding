#!/usr/bin/env bash
# lib-ceo-consent.sh — Shared owner-consent reader for the CEO intent-gate.
#
# THE SINGLE SHARED CONSENT FLAG (goal doc line 142: "a single shared flag read
# consistently by all three layers"). This file is the SHELL-side reader. The
# Command Center server reads the SAME sidecar via src/lib/consent.ts. The hard
# tool-deny (Layer 1) and the QC state-gate (Layer 4) both consult this one flag.
#
# Sidecar location (resolved in priority order — first existing parent wins):
#   1. $CEO_CONSENT_FILE                       (explicit override, tests/CI)
#   2. /data/.openclaw/state/ceo-consent.json  (VPS / Docker)
#   3. $HOME/.openclaw/state/ceo-consent.json  (Mac / bare-metal)
#
# Sidecar shape (written ONLY by scripts/grant-ceo-consent.sh):
#   {
#     "granted":     true,
#     "scope":       "task:<uuid>" | "session:<id>" | "until:<iso8601>" | "global",
#     "granted_at":  "<iso8601>",
#     "granted_by":  "owner",
#     "phrase":      "<the literal owner consent text>"
#   }
#
# HARDENING (goal doc line 91 "Consent-flag write path must be hardened"):
#   - The sidecar lives OUTSIDE any agent-writable workspace. Combined with the
#     Layer-1 `write`/`edit` tool-deny, the CEO agent physically cannot author
#     its own consent. Only the owner-invoked grant script writes it.
#   - Consent is SCOPED and auto-expires. An `until:<iso>` scope past its instant
#     is treated as ABSENT. A `task:`/`session:` scope only matches when the
#     caller passes the same id. A bare `global` scope is honored but is the
#     widest grant and should be time-boxed by the operator.
#
# API (source this file, then call):
#   ceo_consent_file                 -> prints the resolved sidecar path
#   ceo_consent_active [scope_id]    -> exit 0 if consent is active (optionally
#                                       for a given task/session id), else exit 1
#
# No external deps beyond python3 (already required by the onboarding scripts).

# Resolve the sidecar path. Honors an explicit override, else picks the platform
# state dir whose PARENT (~/.openclaw or /data/.openclaw) exists.
ceo_consent_file() {
  if [ -n "${CEO_CONSENT_FILE:-}" ]; then
    printf '%s\n' "$CEO_CONSENT_FILE"
    return 0
  fi
  if [ -d /data/.openclaw ]; then
    printf '%s\n' "/data/.openclaw/state/ceo-consent.json"
    return 0
  fi
  printf '%s\n' "$HOME/.openclaw/state/ceo-consent.json"
}

# ceo_consent_active [scope_id]
#   Returns 0 (active/allow) when a valid, unexpired consent record matches.
#   Returns 1 (absent/deny) otherwise — including malformed/missing files.
#   scope_id (optional): the task id or session id the current action belongs to.
#     - task:<id>    matches only when scope_id == <id>
#     - session:<id> matches only when scope_id == <id>
#     - until:<iso>  matches any action while now < <iso>
#     - global       matches any action (widest; operator time-boxes externally)
ceo_consent_active() {
  local _scope_id="${1:-}"
  local _file
  _file="$(ceo_consent_file)"
  [ -f "$_file" ] || return 1

  CEO_CONSENT_PATH="$_file" CEO_CONSENT_SCOPE_ID="$_scope_id" python3 - <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone

path = os.environ["CEO_CONSENT_PATH"]
scope_id = os.environ.get("CEO_CONSENT_SCOPE_ID", "") or ""

try:
    with open(path) as fh:
        rec = json.load(fh)
except Exception:
    sys.exit(1)  # unreadable/malformed -> treat as NO consent (fail closed)

if not isinstance(rec, dict) or rec.get("granted") is not True:
    sys.exit(1)

scope = rec.get("scope")
if not isinstance(scope, str) or not scope:
    sys.exit(1)


def _parse_iso(s: str):
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


now = datetime.now(timezone.utc)

if scope == "global":
    sys.exit(0)

if scope.startswith("until:"):
    until = _parse_iso(scope[len("until:"):])
    if until is None:
        sys.exit(1)
    sys.exit(0 if now < until else 1)

if scope.startswith("task:"):
    want = scope[len("task:"):].strip()
    sys.exit(0 if scope_id and scope_id == want else 1)

if scope.startswith("session:"):
    want = scope[len("session:"):].strip()
    sys.exit(0 if scope_id and scope_id == want else 1)

# Unknown scope form -> fail closed.
sys.exit(1)
PYEOF
}
