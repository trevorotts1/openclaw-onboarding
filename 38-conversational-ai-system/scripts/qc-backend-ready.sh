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
#   3. no BLANK model override on the inbound mapping(s). A `model` key is
#      OPTIONAL on a hooks.mappings entry — the effective model is the ROUTING
#      AGENT's own (agents.entries / agents.list / agents.defaults), which
#      24-self-test-hook.sh resolves in its section (b). This gate never greps
#      the whole config for "some model somewhere" and never claims a working
#      model is set on the mapping.
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

# ── THE hook-mapping contract ──────────────────────────────────────────────────
# One authoritative predicate, sourced from scripts/lib-hook-mapping-contract.sh,
# evaluated PER MAPPING ID. This used to be a whole-file grep for `"model": "..."`
# and `"deliver": false`, which PASSED the exact mapping 24-self-test-hook.sh
# refused whenever some other key in the file happened to carry a model (G-04).
# Both gates now call the same predicate and print the same MAPCONTRACT lines,
# so they cannot reach different verdicts on the same config (G-05).
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-hook-mapping-contract.sh"

CONTRACT_OUT="$(hook_mapping_contract_eval "$CONFIG")"

# Machine-comparable report. 24-self-test-hook.sh prints these same four line
# kinds from the same function; the fixture matrix diffs them.
printf '%s\n' "$CONTRACT_OUT" | grep -E '^(MAPCONTRACT|MAPENABLED|MAPSELECT|GATEVERDICT)\|' || true

# reason_seen <token> — true when any mapping reports exactly this reason.
reason_seen() {
  printf '%s\n' "$CONTRACT_OUT" \
    | awk -F'|' -v pat="$1" '$1=="MAPCONTRACT" && index("," $4 ",", "," pat ",") > 0 { f=1 } END { exit f ? 0 : 1 }'
}

MAP_COUNT="$(printf '%s\n' "$CONTRACT_OUT" | grep -c '^MAPCONTRACT|' || true)"
if [ "${MAP_COUNT:-0}" -gt 0 ]; then
  pass "hooks.mappings is live (${MAP_COUNT} inbound mapping(s) parsed and evaluated per id)"
else
  fail "hooks.mappings has no inbound mapping — the GHL webhook has nowhere to route"
fi

# Per-mapping detail. The here-doc keeps the loop in THIS shell so `fail` sets
# FAIL; a `| while` would run it in a subshell and lose the flag.
while IFS='|' read -r _tag _id _verdict _reasons; do
  [ "$_tag" = "MAPCONTRACT" ] || continue
  [ -n "$_id" ] || continue
  if [ "$_verdict" = "OK" ]; then
    pass "mapping '$_id': valid inbound mapping (exact key set, directives, action=agent, deliver:false, agentId bound)"
  else
    fail "mapping '$_id': ${_reasons}"
  fi
done <<EOF
$CONTRACT_OUT
EOF

# deliver:false — the double-send guard, now read from the parsed mapping.
if reason_seen "deliver-not-false" || reason_seen "missing-key:deliver"; then
  fail "inbound mapping must set deliver:false (deliver:true double-sends / mis-delivers)"
else
  pass "deliver:false set on every inbound mapping (agent sends via the GHL Conversations API)"
fi

# model override, read from the parsed mapping per id (never a whole-file grep).
# `model` is OPTIONAL on a hooks.mappings entry (evidence E-PBB017-MODEL-KEY:
# OpenClaw's HookMappingSchema has it .optional() and mergeAction falls back to
# baseAgent.model), so a mapping with no `model` is valid and the real writer
# emits exactly that. What is refused is a PRESENT-but-BLANK override. The
# effective model is NOT on the mapping and is NOT checked here: the self-test's
# section (b) resolves it from the routing agent.
if reason_seen "blank-model-override"; then
  fail "inbound mapping carries a blank model override (drop the key, or set it non-empty)"
else
  pass "no blank model override on any inbound mapping (model is optional here; the effective model is the agent's own, resolved by the self-test)"
fi

# hooks.enabled must be true or nothing routes at all.
case "$(printf '%s\n' "$CONTRACT_OUT" | grep '^MAPENABLED|' | head -n1 | cut -d'|' -f2)" in
  true)  pass "hooks.enabled is true" ;;
  false) fail "hooks.enabled is false" ;;
  *)     fail "hooks.enabled is not set" ;;
esac

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
