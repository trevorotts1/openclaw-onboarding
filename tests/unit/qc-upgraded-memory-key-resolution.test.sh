#!/usr/bin/env bash
# tests/unit/qc-upgraded-memory-key-resolution.test.sh
#
# REGRESSION GUARD — Skill 31 Layer 4 credential resolution.
#
# THE FALSE FAIL THIS CLOSES (proven live 2026-07-21 on a client box):
#   31-upgraded-memory-system/qc-upgraded-memory-system.sh asserted
#       [ -n "$GEMINI_API_KEY" ] || [ -n "$GOOGLE_API_KEY" ]
#   which reads ONLY the script's own shell env. That env is empty in the
#   NON-INTERACTIVE shell the install/QC harness runs under, while the key is
#   configured where the gateway actually reads it: openclaw.json's env block.
#   A fully-configured box therefore reported "Layer 4 ... FAIL" and the whole
#   Skill 31 QC exited 1 — a reported defect that did not exist.
#
# WHAT THIS FILE PROVES (hermetic; fixture HOMEs in a tempdir, no box touched):
#   T1  key present ONLY in openclaw.json env.vars.<NAME>  -> PASS
#   T2  key present ONLY in openclaw.json env.<NAME> (flat) -> PASS
#   T3  key present ONLY in the process env                 -> PASS (unchanged)
#   T4  key absent EVERYWHERE                               -> still FAIL
#       (the gate must not have been softened into a no-op)
#   T5  no key VALUE is ever printed, logged, or echoed — a unique sentinel
#       value placed in the fixture config must appear nowhere in the output.
#
# Exit 0 = pass. Exit 1 = the Layer 4 gate regressed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QC="$REPO_ROOT/31-upgraded-memory-system/qc-upgraded-memory-system.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-upgraded-memory-key-resolution.test.sh ==="
echo ""

if [ ! -f "$QC" ]; then
  echo "  FAIL: $QC not found"
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Writes a fixture openclaw.json into $1/.openclaw/. $2 = python literal for
# the "env" object. Values are obvious non-credentials.
make_home() {
  local home="$1" env_json="$2"
  mkdir -p "$home/.openclaw"
  python3 -c '
import json, sys
json.dump({"env": json.loads(sys.argv[2])}, open(sys.argv[1], "w"), indent=2)
' "$home/.openclaw/openclaw.json" "$env_json"
}

# Runs the QC script in a scrubbed non-interactive shell (env -i), i.e. exactly
# the condition that produced the false fail, and echoes the Layer 4 verdict.
# Extra NAME=VALUE pairs may be passed after the home dir.
layer4_verdict() {
  local home="$1"; shift
  env -i HOME="$home" PATH="/usr/bin:/bin" "$@" /bin/bash "$QC" 2>&1 \
    | grep -a "Layer 4: Gemini Embedding 2 configured" \
    | sed -e 's/\x1b\[[0-9;]*m//g' \
    | grep -oE '(PASS|FAIL)' | head -1
}

# ── T1: key only in openclaw.json env.vars.<NAME> (the canonical shape) ──────
make_home "$TMP/t1" '{"vars": {"GOOGLE_API_KEY": "fixture-placeholder-not-a-credential"}}'
V1="$(layer4_verdict "$TMP/t1")"
[ "$V1" = "PASS" ] \
  && pass "T1 key in openclaw.json env.vars.GOOGLE_API_KEY -> Layer 4 PASS" \
  || fail "T1 key in openclaw.json env.vars.GOOGLE_API_KEY -> expected PASS, got '${V1:-<no verdict line>}'"

# ── T2: key only in openclaw.json env.<NAME> (flat shape) ───────────────────
make_home "$TMP/t2" '{"GEMINI_API_KEY": "fixture-placeholder-not-a-credential"}'
V2="$(layer4_verdict "$TMP/t2")"
[ "$V2" = "PASS" ] \
  && pass "T2 key in openclaw.json env.GEMINI_API_KEY (flat) -> Layer 4 PASS" \
  || fail "T2 key in openclaw.json env.GEMINI_API_KEY (flat) -> expected PASS, got '${V2:-<no verdict line>}'"

# ── T3: key only in the process env (pre-existing path must not regress) ────
make_home "$TMP/t3" '{"vars": {}}'
V3="$(layer4_verdict "$TMP/t3" GOOGLE_API_KEY=fixture-placeholder-not-a-credential)"
[ "$V3" = "PASS" ] \
  && pass "T3 key in the process env -> Layer 4 PASS (unchanged behavior)" \
  || fail "T3 key in the process env -> expected PASS, got '${V3:-<no verdict line>}'"

# ── T4: absent EVERYWHERE must STILL FAIL (the gate is not a no-op) ─────────
make_home "$TMP/t4" '{"vars": {}}'
V4="$(layer4_verdict "$TMP/t4")"
[ "$V4" = "FAIL" ] \
  && pass "T4 no key anywhere -> Layer 4 still FAILS (real defect still caught)" \
  || fail "T4 no key anywhere -> expected FAIL, got '${V4:-<no verdict line>}' (gate softened!)"

# ── T5: the key VALUE never reaches any output stream ───────────────────────
SENTINEL="ZZ-QC31-SENTINEL-$$-ZZ"
make_home "$TMP/t5" "{\"vars\": {\"GOOGLE_API_KEY\": \"$SENTINEL\"}}"
T5_OUT="$(env -i HOME="$TMP/t5" PATH="/usr/bin:/bin" /bin/bash "$QC" 2>&1)"
if printf '%s' "$T5_OUT" | grep -qa "$SENTINEL"; then
  fail "T5 the configured key VALUE leaked into QC output"
else
  pass "T5 no key value printed/logged (presence check only)"
fi

echo ""
echo "  Result: $PASS passed | $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "qc-upgraded-memory-key-resolution.test.sh: FAILED"
  exit 1
fi
echo "qc-upgraded-memory-key-resolution.test.sh: PASSED"
exit 0
