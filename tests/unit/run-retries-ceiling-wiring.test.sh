#!/usr/bin/env bash
# tests/unit/run-retries-ceiling-wiring.test.sh — FLEET-FIX Area 3 / C.2–C.4 (AUD-24)
#
# Proves the `agents.defaults.runRetries` ceiling wiring:
#
#   W1   install.sh actually references runRetries         (grep > 0; was 0 on main)
#   W2   install.sh invokes scripts/wire-run-retries.sh
#   W3   the REAL Step 0.3b block, executed under install.sh's REAL `set -euo
#        pipefail`, survives the MISS path (bundle without the script). This is a
#        regression guard for a bug that shipped in this branch's first draft:
#        SCRIPTS_DIR is defined LATER in install.sh than this block, so naming it
#        here is an UNBOUND VARIABLE that aborts the ENTIRE install at Step 0.
#   W3b  Step 0.3b must not name $SCRIPTS_DIR in code at all
#   W3c  HIT path: the real block seeds the config end-to-end
#
#   S1   fresh config on a SUPPORTED runtime → all four keys seeded (24/8/32/160)
#   S2   SET-IF-ABSENT: a pre-existing operator value is NEVER overwritten
#   S3   SET-IF-ABSENT is per-subkey: absent siblings fill, present ones survive
#   S4   idempotent: a second run overwrites nothing and reports PRESERVED
#   S5   no collateral damage to sibling config or per-agent runRetries overrides
#
#   N1   runtime WITHOUT the key → CEILING_NOT_SUPPORTED@<version>, config untouched
#   N2   runtime dir missing     → CEILING_NOT_SUPPORTED (fail-CLOSED, no blind write)
#   N2b  runtime with no dist/   → CEILING_NOT_SUPPORTED@<version> (fail-CLOSED)
#
#   H1   HAZARD .strict(): ONLY the four permitted keys are ever written. One
#        stray key and the runtime rejects the box's WHOLE config.
#   H2   HAZARD .refine(max >= min): a default fill must never turn a VALID
#        operator config INVALID. Operator min=200 + our default max=160 fill is
#        160 >= 200 == FALSE → the max fill must be DROPPED, not written.
#   H2b  mirror case: operator max=20 + our default min=32 fill → min fill dropped
#   H3   non-object runRetries (e.g. an int) is left untouched, never coerced
#
# Both H hazards are REAL, not theoretical — verified against the installed
# runtime's own AgentRunRetriesConfigSchema, which REJECTS both shapes.
#
# Exit 0 = all checks pass. Exit 1 = a regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
WIRE_SH="$REPO_ROOT/scripts/wire-run-retries.sh"
PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== run-retries-ceiling-wiring.test.sh (AUD-24 / C.2–C.4) ==="
echo ""

[ -f "$INSTALL_SH" ] || { echo "FAIL: install.sh not found at $INSTALL_SH"; exit 1; }
[ -f "$WIRE_SH" ]    || { echo "FAIL: scripts/wire-run-retries.sh not found at $WIRE_SH"; exit 1; }

# ---------------------------------------------------------------------------
# Fixtures: fake openclaw runtime packages.
# dist/ filenames are content-hashed in the real package, so the grep must walk
# the tree — the fixtures use arbitrary names on purpose to prove that.
# ---------------------------------------------------------------------------
mk_runtime() {  # $1=dir  $2=version  $3=supported(yes/no)
    local dir="$1" ver="$2" supported="$3"
    mkdir -p "$dir/dist"
    printf '{"name":"openclaw","version":"%s"}\n' "$ver" > "$dir/package.json"
    if [ "$supported" = "yes" ]; then
        # Mirrors the real 2026.6.11 schema doc strings + resolver constants.
        cat > "$dir/dist/runtime-schema-ZZfixture.js" <<'JS'
const d = {
  "agents.defaults.runRetries": "Outer run loop retry iteration boundaries for the embedded OpenClaw runner to prevent infinite execution loops during failure recovery.",
  "agents.defaults.runRetries.base": "Base number of run retry iterations (default: 24).",
  "agents.defaults.runRetries.perProfile": "Additional run retry iterations per fallback profile candidate (default: 8).",
  "agents.defaults.runRetries.min": "Minimum (default: 32).",
  "agents.defaults.runRetries.max": "Maximum (default: 160)."
};
JS
    else
        # A runtime that predates the key: schema exists, runRetries does not.
        cat > "$dir/dist/runtime-schema-ZZfixture.js" <<'JS'
const d = {
  "agents.defaults.subagents.maxConcurrent": "Max concurrent subagents.",
  "agents.defaults.bootstrapMaxChars": "Bootstrap char cap."
};
JS
    fi
}

SUPPORTED_RT="$TMP/rt-supported"
UNSUPPORTED_RT="$TMP/rt-unsupported"
mk_runtime "$SUPPORTED_RT"   "2026.6.11" yes
mk_runtime "$UNSUPPORTED_RT" "2026.5.22" no

# Sanity-check the fixtures themselves, so a broken fixture can't fake a pass.
grep -rq "runRetries" "$SUPPORTED_RT/dist"   || { echo "FAIL: supported fixture lacks runRetries"; exit 1; }
grep -rq "runRetries" "$UNSUPPORTED_RT/dist" && { echo "FAIL: unsupported fixture leaks runRetries"; exit 1; }

run_wire() {  # $1=config path  $2=runtime dir ("" = unresolvable)
    OC_JSON="$1" OC_RUNTIME_DIR="$2" PATH="$TMP/emptybin:$PATH" bash "$WIRE_SH" 2>&1
}

# An empty bin dir shadows nothing, but for N2 we must also make sure a real
# openclaw on the operator's PATH cannot rescue an "unresolvable" runtime.
mkdir -p "$TMP/emptybin"

jqv() {  # $1=config  $2=python expr over cfg
    python3 -c "import json,sys; cfg=json.load(open('$1')); print($2)" 2>/dev/null
}

# ===========================================================================
# W — install.sh wiring (the literal acceptance grep)
# ===========================================================================
echo "--- W: install.sh wiring ---"
HITS="$(grep -c "runRetries" "$INSTALL_SH" || true)"
if [ "${HITS:-0}" -gt 0 ]; then
    pass "W1 grep -c runRetries install.sh = $HITS (> 0; was 0 on main)"
else
    fail "W1 grep -c runRetries install.sh = 0 — the ceiling is still unwired"
fi

if grep -q "scripts/wire-run-retries.sh" "$INSTALL_SH"; then
    pass "W2 install.sh invokes scripts/wire-run-retries.sh"
else
    fail "W2 install.sh does not invoke scripts/wire-run-retries.sh"
fi

# W3 — the Step 0.3b block must survive install.sh's REAL shell flags (`set -euo
# pipefail`, line 97) on the MISS path, where the bundled script is not at the
# primary location and the fallback chain is actually evaluated.
#
# REGRESSION GUARD: SCRIPTS_DIR is defined ~line 3146, LATER than this block
# (~2784). Referencing it here is an UNBOUND VARIABLE under `set -u` and aborts
# the ENTIRE install at Step 0. Extract the real block and execute it.
#   $1 = install.sh path the block should think it lives at ("shim")
#   $2 = openclaw.json path
# SCRIPTS_DIR is intentionally NEVER set — mirroring reality at this point in install.sh.
mk_block() {
    local shim="$1" ocjson="$2" out="$TMP/block-$3.sh"
    {
        echo 'set -euo pipefail'
        echo 'step(){ :; }; success(){ echo "  ✓ $1"; }; note(){ echo "  ℹ️  $1"; }'
        echo 'warn(){ echo "  ⚠️  $1"; }; error(){ echo "  ✗ $1"; }; backup_config_file(){ :; }'
        echo "BASH_SOURCE_SHIM=\"$shim\""
        echo 'ONBOARDING_DIR="/nonexistent/onboarding"'
        echo "LOG_FILE=\"$TMP/block.log\""
        echo "OCJSON=\"$ocjson\""
        sed -n '/^# 0\.3b — runRetries ceiling/,/^# 0\.4 — Model selection/p' "$INSTALL_SH" \
            | sed '$d' \
            | sed 's|\${BASH_SOURCE\[0\]}|$BASH_SOURCE_SHIM|g'
        echo 'echo "BLOCK_REACHED_END"'
    } > "$out"
    printf '%s\n' "$out"
}

# W3 — MISS path: the bundled script is nowhere to be found, so the fallback
# chain IS evaluated. This is the exact path that an unbound $SCRIPTS_DIR kills.
echo '{"agents":{"defaults":{}}}' > "$TMP/w3.json"
# A real dir (so dirname/cd resolves, as it always does for a real BASH_SOURCE[0])
# that simply has NO scripts/wire-run-retries.sh — an older bundle.
mkdir -p "$TMP/fakerepo"
B_MISS="$(mk_block "$TMP/fakerepo/install.sh" "$TMP/w3.json" miss)"
if W3OUT="$(OC_RUNTIME_DIR="$SUPPORTED_RT" bash "$B_MISS" 2>&1)" && echo "$W3OUT" | grep -q "BLOCK_REACHED_END"; then
    pass "W3 Step 0.3b survives \`set -euo pipefail\` on the MISS path (fallback evaluated, no unbound-variable abort)"
else
    pass_fail_msg="$(echo "${W3OUT:-}" | grep -i 'unbound\|not found' | head -1)"
    fail "W3 Step 0.3b ABORTS the install under set -u on the miss path: ${pass_fail_msg:-<no output>}"
fi

# W3c — HIT path: the block finds the real script and actually seeds the config.
echo '{"agents":{"defaults":{}}}' > "$TMP/w3c.json"
B_HIT="$(mk_block "$REPO_ROOT/install.sh" "$TMP/w3c.json" hit)"
W3COUT="$(OC_RUNTIME_DIR="$SUPPORTED_RT" bash "$B_HIT" 2>&1)"
W3CB="$(jqv "$TMP/w3c.json" "cfg['agents']['defaults']['runRetries']['base']")"
if echo "$W3COUT" | grep -q "BLOCK_REACHED_END" && [ "$W3CB" = "24" ]; then
    pass "W3c Step 0.3b HIT path: the real install.sh block seeds runRetries.base=24 end-to-end"
else
    fail "W3c Step 0.3b HIT path did not seed (base=$W3CB): $(echo "$W3COUT" | tail -2)"
fi

if sed -n '/^# 0\.3b — runRetries ceiling/,/^# 0\.4 — Model selection/p' "$INSTALL_SH" \
     | grep -v '^[[:space:]]*#' | grep -q 'SCRIPTS_DIR'; then
    fail "W3b Step 0.3b references \$SCRIPTS_DIR, which install.sh does not define until LATER — unbound under set -u"
else
    pass "W3b Step 0.3b does not reference \$SCRIPTS_DIR (defined later in install.sh; would be unbound here)"
fi
echo ""

# ===========================================================================
# S — supported runtime: seeding + set-if-absent
# ===========================================================================
echo "--- S: supported runtime (seed + set-if-absent) ---"

# S1 — fresh config
CFG="$TMP/s1.json"
echo '{"agents":{"defaults":{}}}' > "$CFG"
OUT="$(run_wire "$CFG" "$SUPPORTED_RT")"
if echo "$OUT" | grep -q "RUNRETRIES_STATUS=SEEDED"; then
    B="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['base']")"
    P="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['perProfile']")"
    M="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['min']")"
    X="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['max']")"
    if [ "$B" = "24" ] && [ "$P" = "8" ] && [ "$M" = "32" ] && [ "$X" = "160" ]; then
        pass "S1 fresh install seeds runRetries base=24 perProfile=8 min=32 max=160"
    else
        fail "S1 seeded wrong values: base=$B perProfile=$P min=$M max=$X"
    fi
else
    fail "S1 fresh install did not seed (status: $(echo "$OUT" | grep RUNRETRIES_STATUS || echo none))"
fi

# S2 — pre-existing value must NOT be overwritten (the core set-if-absent claim)
CFG="$TMP/s2.json"
echo '{"agents":{"defaults":{"runRetries":{"base":99,"perProfile":7,"min":50,"max":140}}}}' > "$CFG"
OUT="$(run_wire "$CFG" "$SUPPORTED_RT")"
B="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['base']")"
P="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['perProfile']")"
M="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['min']")"
X="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['max']")"
if [ "$B" = "99" ] && [ "$P" = "7" ] && [ "$M" = "50" ] && [ "$X" = "140" ]; then
    pass "S2 SET-IF-ABSENT: pre-existing 99/7/50/140 preserved verbatim (not overwritten)"
else
    fail "S2 OVERWROTE an operator value: base=$B perProfile=$P min=$M max=$X (expected 99/7/50/140)"
fi
if echo "$OUT" | grep -q "RUNRETRIES_STATUS=PRESERVED"; then
    pass "S2b status reports PRESERVED"
else
    fail "S2b expected PRESERVED, got: $(echo "$OUT" | grep RUNRETRIES_STATUS || echo none)"
fi

# S3 — per-subkey: operator set only `base`; siblings must fill, base must survive
CFG="$TMP/s3.json"
echo '{"agents":{"defaults":{"runRetries":{"base":99}}}}' > "$CFG"
run_wire "$CFG" "$SUPPORTED_RT" >/dev/null
B="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['base']")"
P="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['perProfile']")"
if [ "$B" = "99" ] && [ "$P" = "8" ]; then
    pass "S3 per-subkey: operator base=99 survives, absent perProfile filled to 8"
else
    fail "S3 per-subkey failed: base=$B (want 99), perProfile=$P (want 8)"
fi

# S4 — idempotency
CFG="$TMP/s4.json"
echo '{"agents":{"defaults":{}}}' > "$CFG"
run_wire "$CFG" "$SUPPORTED_RT" >/dev/null
SNAP="$(cat "$CFG")"
OUT="$(run_wire "$CFG" "$SUPPORTED_RT")"
if [ "$SNAP" = "$(cat "$CFG")" ] && echo "$OUT" | grep -q "RUNRETRIES_STATUS=PRESERVED"; then
    pass "S4 idempotent: second run changes nothing, reports PRESERVED"
else
    fail "S4 not idempotent: config drifted on re-run"
fi

# S5 — untouched siblings: the seeder must not disturb the rest of the config
CFG="$TMP/s5.json"
echo '{"agents":{"defaults":{"subagents":{"maxConcurrent":100}},"list":[{"name":"main","runRetries":{"base":77}}]},"tools":{"exec":{}}}' > "$CFG"
run_wire "$CFG" "$SUPPORTED_RT" >/dev/null
MC="$(jqv "$CFG" "cfg['agents']['defaults']['subagents']['maxConcurrent']")"
PA="$(jqv "$CFG" "cfg['agents']['list'][0]['runRetries']['base']")"
if [ "$MC" = "100" ] && [ "$PA" = "77" ]; then
    pass "S5 sibling config intact (subagents.maxConcurrent=100, per-agent runRetries.base=77 untouched)"
else
    fail "S5 collateral damage: maxConcurrent=$MC (want 100), per-agent base=$PA (want 77)"
fi
echo ""

# ===========================================================================
# N — unsupported runtime: CEILING_NOT_SUPPORTED@<version>
# ===========================================================================
echo "--- N: unsupported runtime (skip + report) ---"

# N1 — runtime lacks the key
CFG="$TMP/n1.json"
echo '{"agents":{"defaults":{}}}' > "$CFG"
BEFORE="$(cat "$CFG")"
OUT="$(run_wire "$CFG" "$UNSUPPORTED_RT")"
if echo "$OUT" | grep -q "RUNRETRIES_STATUS=CEILING_NOT_SUPPORTED@2026.5.22"; then
    pass "N1 reports CEILING_NOT_SUPPORTED@2026.5.22 (version tag = the runtime actually grepped)"
else
    fail "N1 expected CEILING_NOT_SUPPORTED@2026.5.22, got: $(echo "$OUT" | grep RUNRETRIES_STATUS || echo none)"
fi
if [ "$BEFORE" = "$(cat "$CFG")" ]; then
    pass "N1b config NOT written on an unsupported runtime (no unknown key = no rejected config)"
else
    fail "N1b WROTE runRetries to a box whose runtime cannot parse it — strict schema would reject the whole config"
fi

# N2 — runtime dir does not exist at all → must FAIL CLOSED, never blind-write
CFG="$TMP/n2.json"
echo '{"agents":{"defaults":{}}}' > "$CFG"
BEFORE="$(cat "$CFG")"
OUT="$(run_wire "$CFG" "$TMP/does-not-exist")"
if echo "$OUT" | grep -q "RUNRETRIES_STATUS=CEILING_NOT_SUPPORTED@" && [ "$BEFORE" = "$(cat "$CFG")" ]; then
    pass "N2 nonexistent runtime dir → CEILING_NOT_SUPPORTED, config untouched (fail-CLOSED)"
else
    fail "N2 fail-OPEN: nonexistent runtime dir did not skip cleanly (status: $(echo "$OUT" | grep RUNRETRIES_STATUS || echo none))"
fi

# N2b — runtime dir exists but has NO dist/ (broken/partial install) → fail closed
CFG="$TMP/n2b.json"
echo '{"agents":{"defaults":{}}}' > "$CFG"
BEFORE="$(cat "$CFG")"
NODIST="$TMP/rt-nodist"
mkdir -p "$NODIST"
printf '{"name":"openclaw","version":"2026.4.0"}\n' > "$NODIST/package.json"
OUT="$(run_wire "$CFG" "$NODIST")"
if echo "$OUT" | grep -q "RUNRETRIES_STATUS=CEILING_NOT_SUPPORTED@2026.4.0" && [ "$BEFORE" = "$(cat "$CFG")" ]; then
    pass "N2b runtime with no dist/ → CEILING_NOT_SUPPORTED@2026.4.0, config untouched (fail-CLOSED)"
else
    fail "N2b fail-OPEN: unreadable dist did not skip cleanly (status: $(echo "$OUT" | grep RUNRETRIES_STATUS || echo none))"
fi
echo ""

# ===========================================================================
# H — the two real schema hazards
# ===========================================================================
echo "--- H: schema hazards (.strict() and .refine(max>=min)) ---"

# H1 — .strict(): exactly the four permitted keys, never a fifth
CFG="$TMP/h1.json"
echo '{"agents":{"defaults":{}}}' > "$CFG"
run_wire "$CFG" "$SUPPORTED_RT" >/dev/null
KEYS="$(jqv "$CFG" "','.join(sorted(cfg['agents']['defaults']['runRetries'].keys()))")"
if [ "$KEYS" = "base,max,min,perProfile" ]; then
    pass "H1 .strict(): exactly the 4 permitted keys written ($KEYS) — no extra key to reject the config"
else
    fail "H1 .strict() VIOLATION: wrote keys [$KEYS], expected exactly base,max,min,perProfile"
fi

# H2 — .refine(max >= min): operator min=200, our default max=160 would be INVALID.
#      The max fill MUST be dropped. Writing it would reject the box's whole config.
CFG="$TMP/h2.json"
echo '{"agents":{"defaults":{"runRetries":{"min":200}}}}' > "$CFG"
run_wire "$CFG" "$SUPPORTED_RT" >/dev/null
M="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['min']")"
HAS_MAX="$(jqv "$CFG" "'max' in cfg['agents']['defaults']['runRetries']")"
VALID="$(python3 -c "
import json
b=json.load(open('$CFG'))['agents']['defaults']['runRetries']
print('OK' if not('min' in b and 'max' in b and b['max']<b['min']) else 'INVALID')")"
if [ "$M" = "200" ] && [ "$HAS_MAX" = "False" ] && [ "$VALID" = "OK" ]; then
    pass "H2 .refine(): operator min=200 kept; conflicting max=160 fill DROPPED → config stays schema-VALID"
else
    fail "H2 .refine() VIOLATION: min=$M has_max=$HAS_MAX validity=$VALID — a naive fill just invalidated a valid config"
fi

# H2b — mirror case: operator max=20, our default min=32 would violate. min fill must drop.
CFG="$TMP/h2b.json"
echo '{"agents":{"defaults":{"runRetries":{"max":20}}}}' > "$CFG"
run_wire "$CFG" "$SUPPORTED_RT" >/dev/null
X="$(jqv "$CFG" "cfg['agents']['defaults']['runRetries']['max']")"
VALID="$(python3 -c "
import json
b=json.load(open('$CFG'))['agents']['defaults']['runRetries']
print('OK' if not('min' in b and 'max' in b and b['max']<b['min']) else 'INVALID')")"
if [ "$X" = "20" ] && [ "$VALID" = "OK" ]; then
    pass "H2b .refine(): operator max=20 kept; conflicting min=32 fill dropped → still VALID"
else
    fail "H2b .refine() VIOLATION: max=$X validity=$VALID"
fi

# H3 — non-object runRetries must never be coerced
CFG="$TMP/h3.json"
echo '{"agents":{"defaults":{"runRetries":42}}}' > "$CFG"
BEFORE="$(cat "$CFG")"
OUT="$(run_wire "$CFG" "$SUPPORTED_RT")"
if echo "$OUT" | grep -q "RUNRETRIES_STATUS=CONFLICT_SKIPPED" && [ "$BEFORE" = "$(cat "$CFG")" ]; then
    pass "H3 non-object runRetries (int 42) left untouched, reports CONFLICT_SKIPPED"
else
    fail "H3 coerced or clobbered a non-object runRetries"
fi
echo ""

# ===========================================================================
echo "=== RESULT: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
