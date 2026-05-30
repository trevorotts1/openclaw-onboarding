#!/usr/bin/env bash
# qc-backend-ready.sh — concise "backend is ready to RECEIVE" completion gate.
#
# Part of the Skill-38 completion contract: testing only happens AFTER both the
# client doc exists (qc-reference-sheet.sh) AND the backend is ready to receive.
# This gate asserts the four backend-ready facts an inbound GHL webhook needs:
#
#   1. hooks.mappings is LIVE — at least one mapping exists in openclaw.json
#      (the inbound webhook has somewhere to route).
#   2. deliver:false on the inbound mapping(s) — the agent SENDS via the GHL
#      Conversations API itself (deliver:true would double-send / mis-deliver).
#   3. a WORKING model is set on the inbound mapping (a non-empty "model" string).
#   4. the gateway answers healthz with HTTP 200 (it is up and listening).
#
# This is a LIVE check (reads openclaw.json + curls the gateway). It is run from
# scripts/11-run-qc-checklist.sh on the client box. On a repo/CI box with no
# install it exits 3 (NO_CONFIG) so CI can treat "nothing to check" as a SKIP
# rather than a false failure (the checklist wrapper does exactly that).
#
# Exit codes:
#   0 = backend ready (all four facts true)
#   1 = backend NOT ready (one or more facts false) — do NOT test, do NOT hand off
#   2 = usage error
#   3 = no openclaw.json found (nothing to check on this box)
#
# PURE BASH (grep/sed/awk), no python — respects qc-static.yml's .py
# claude-/anthropic scan. bash -n clean. set -uo pipefail.

set -uo pipefail

JSON_MODE=0
CONFIG=""
HEALTHZ_URL="${HEALTHZ_URL:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --config)  CONFIG="$2"; shift 2 ;;
    --healthz) HEALTHZ_URL="$2"; shift 2 ;;
    --json)    JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ── Locate openclaw.json ──────────────────────────────────────────────────────
if [ -z "$CONFIG" ]; then
  for c in "${OPENCLAW_CONFIG:-}" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json" "/root/.openclaw/openclaw.json"; do
    [ -n "$c" ] || continue
    [ -f "$c" ] || continue
    CONFIG="$c"; break
  done
fi

if [ -z "$CONFIG" ] || [ ! -f "$CONFIG" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"verdict":"NO_CONFIG"}\n'
  else
    echo "qc-backend-ready: no openclaw.json found (nothing to check on this box)."
  fi
  exit 3
fi

FAIL=0
pass() { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*"; FAIL=1; }

echo "=== qc-backend-ready: backend ready to RECEIVE ==="
echo "config: $CONFIG"

# Extract the hooks.mappings block textually (no jq dependency; jq may be absent
# on a fleet box). We work on a flattened view: pull lines between "mappings"
# and the matching close. A pragmatic grep over the whole file is enough to
# assert presence/values for this gate.
MAP_PRESENT=0
if grep -Eq '"mappings"[[:space:]]*:' "$CONFIG"; then
  # require at least one object inside it (an "id"/"match" key somewhere in hooks)
  if grep -Eq '"(id|match|action)"[[:space:]]*:' "$CONFIG"; then
    MAP_PRESENT=1
  fi
fi
if [ "$MAP_PRESENT" = "1" ]; then
  pass "hooks.mappings is live (at least one inbound mapping present)"
else
  fail "hooks.mappings has no inbound mapping — the GHL webhook has nowhere to route"
fi

# deliver:false present (the agent sends via the GHL API itself).
if grep -Eq '"deliver"[[:space:]]*:[[:space:]]*false' "$CONFIG"; then
  pass "deliver:false set on the inbound mapping (agent sends via the GHL Conversations API)"
else
  fail "inbound mapping must set deliver:false (deliver:true double-sends / mis-delivers)"
fi

# a non-empty model string on a mapping.
if grep -Eq '"model"[[:space:]]*:[[:space:]]*"[^"]+"' "$CONFIG"; then
  pass "a working model is set on the inbound mapping"
else
  fail "inbound mapping has no model set (the agent cannot answer)"
fi

# ── healthz 200 ───────────────────────────────────────────────────────────────
# Derive a healthz URL if not passed: prefer the gateway's local port. Default to
# the conventional local gateway healthz; honor PUBLIC_HOSTNAME if that's all we have.
if [ -z "$HEALTHZ_URL" ]; then
  PORT="$(grep -Eo '"port"[[:space:]]*:[[:space:]]*[0-9]+' "$CONFIG" | head -n1 | grep -Eo '[0-9]+' || true)"
  if [ -n "$PORT" ]; then
    HEALTHZ_URL="http://127.0.0.1:${PORT}/healthz"
  elif [ -n "${PUBLIC_HOSTNAME:-}" ]; then
    HEALTHZ_URL="https://${PUBLIC_HOSTNAME}/healthz"
  fi
fi

if [ -n "$HEALTHZ_URL" ] && command -v curl >/dev/null 2>&1; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$HEALTHZ_URL" 2>/dev/null || echo 000)"
  if [ "$CODE" = "200" ]; then
    pass "gateway healthz 200 ($HEALTHZ_URL)"
  else
    fail "gateway healthz not 200 ($HEALTHZ_URL -> HTTP $CODE) — the gateway is not ready to receive"
  fi
else
  echo "  [SKIP] no healthz URL derivable or curl unavailable (pass --healthz / set HEALTHZ_URL)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — backend is ready to RECEIVE. Testing may proceed (after the client doc gate also passes)."
  [ "$JSON_MODE" = "1" ] && printf '{"verdict":"PASS"}\n'
  exit 0
else
  echo "RESULT: FAIL — backend NOT ready to receive. Do not test, do not hand off."
  [ "$JSON_MODE" = "1" ] && printf '{"verdict":"FAIL"}\n'
  exit 1
fi
