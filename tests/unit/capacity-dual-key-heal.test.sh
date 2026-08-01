#!/usr/bin/env bash
# tests/unit/capacity-dual-key-heal.test.sh — WS-8 dual-key heal (incident 2026-08-01)
#
# THE INCIDENT THIS LOCKS DOWN:
#   Both concurrency keys were set to 500 out-of-band on an operator box:
#       agents.defaults.maxConcurrent            = 500   ← cap on ALL agent runs
#       agents.defaults.subagents.maxConcurrent  = 500   ← cap on subagent fanout
#   scripts/capacity-monitor.sh reconciled ONLY the subagents key. Its 15-minute
#   tick healed that key 500 -> 12, logged success, and left the TOP-LEVEL key at
#   500 — managed by NOTHING — for five days. 500 concurrent runs on a 12-core box
#   exhausted RAM, thrashed swap, and made every response crawl. Repeated manual
#   fixes "did not stick" because the healer was blind to the key that mattered.
#   The script ships to every box, so the blind spot was fleet-wide.
#
# Checks:
#   W1   the writer actually reconciles agents.defaults.maxConcurrent (static
#        regression guard against silently reverting to a single-key writer)
#   W2   install.sh no longer hard-overwrites subagents.maxConcurrent to 100
#        (the "100 everywhere" half of WS-8; it also RE-CLOBBERED healed values)
#
#   A1   both keys at 500 -> BOTH become the computed safe value
#   A2   a timestamped backup of openclaw.json is created
#   A3   the profile records BOTH previous values (previousMaxConcurrent +
#        previousDefaultsMaxConcurrent) and the computed value
#
#   B1   both keys already in sync -> config is NOT rewritten (byte-identical)
#   B2   ...and no backup is produced for a no-op tick
#
#   C1   THE EXACT INCIDENT: defaults=500 while subagents is ALREADY safe ->
#        still heals. Under the old single-key test this read as "in sync" and
#        the box was never healed.
#
#   D1   defaults key ABSENT -> subagents still heals
#   D2   ...and the absent key is NOT created. AgentDefaultsSchema is .strict(),
#        so injecting the key on a runtime that predates it would make the
#        runtime reject the box's ENTIRE config.
#
#   E1   a runaway OC_CAP_* override (the deliberate-raise escape hatch, kept on
#        purpose) emits a loud WARN instead of passing silently
#   E2   ...and still exits 0 — the WARN informs, it does not clamp or fail
#
# Fully offline: no gateway, no network, no writes outside a temp HOME.
# Exit 0 = all checks pass. Exit 1 = a regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MON_SH="$REPO_ROOT/scripts/capacity-monitor.sh"
INSTALL_SH="$REPO_ROOT/install.sh"
PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== capacity-dual-key-heal.test.sh (WS-8 / incident 2026-08-01) ==="
echo ""

[ -f "$MON_SH" ]     || { echo "FAIL: scripts/capacity-monitor.sh not found at $MON_SH"; exit 1; }
[ -f "$INSTALL_SH" ] || { echo "FAIL: install.sh not found at $INSTALL_SH"; exit 1; }

# SAFETY: capacity-monitor.sh prefers /data/.openclaw over $HOME/.openclaw and
# that choice cannot be overridden by env. On a VPS this test could therefore
# rewrite the REAL config, so refuse to run the write cases there.
DATA_ROOT_PRESENT=0
[ -d /data/.openclaw ] && DATA_ROOT_PRESENT=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Pin the computed value so assertions are hardware-independent:
#   safe = max(MIN_AGENTS, min(MAX_AGENTS, ...)) — with both at 6, safe == 6
#   on every box regardless of cores/RAM.
SAFE_PIN=6

mk_root() {  # $1=name  $2=config json  -> echoes the temp HOME
    local home="$TMP/$1"
    mkdir -p "$home/.openclaw"
    printf '%s\n' "$2" > "$home/.openclaw/openclaw.json"
    printf '%s\n' "$home"
}

run_mon() {  # $1=temp HOME ; remaining args = extra env assignments
    local home="$1"; shift
    env -i PATH="$PATH" HOME="$home" \
        OC_CAP_MIN_AGENTS="$SAFE_PIN" OC_CAP_MAX_AGENTS="$SAFE_PIN" \
        "$@" bash "$MON_SH" 2>&1
}

cfgv() {  # $1=config path  $2=python expr over cfg
    python3 -c "import json,sys; cfg=json.load(open('$1')); print($2)" 2>/dev/null
}

backups() {  # $1=openclaw root -> count of capacity backups
    find "$1" -maxdepth 1 -name 'openclaw.json.bak.capacity.*' 2>/dev/null | wc -l | tr -d ' '
}

BOTH_500='{"agents":{"defaults":{"maxConcurrent":500,"subagents":{"maxConcurrent":500,"maxSpawnDepth":4}},"list":[{"name":"main"}]},"tools":{"exec":{}}}'

# ===========================================================================
# W — static wiring guards
# ===========================================================================
echo "--- W: writer wiring (static) ---"

if grep -q 'defaults\["maxConcurrent"\] = safe' "$MON_SH"; then
    pass "W1 writer assigns agents.defaults.maxConcurrent (dual-key heal wired)"
else
    fail "W1 writer never assigns defaults[\"maxConcurrent\"] — reverted to the single-key writer that left 500 unhealed for 5 days"
fi

if grep -q "sub\['maxConcurrent'\] = max(100, prev_concurrent)" "$INSTALL_SH"; then
    fail "W2 install.sh still hard-overwrites subagents.maxConcurrent to 100 (the WS-8 '100 everywhere' bug; it also re-clobbers healed values)"
else
    pass "W2 install.sh no longer hard-overwrites subagents.maxConcurrent to 100"
fi
echo ""

if [ "$DATA_ROOT_PRESENT" = "1" ]; then
    echo "--- A/B/C/D/E: SKIPPED — /data/.openclaw exists on this host ---"
    echo "    capacity-monitor.sh would target the REAL config, not the fixture."
    echo ""
    echo "=== RESULT: $PASS passed, $FAIL failed (write cases skipped) ==="
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
fi

# ===========================================================================
# A — both keys at 500 (the config as found on the box)
# ===========================================================================
echo "--- A: both keys at 500 -> both heal ---"

H="$(mk_root a "$BOTH_500")"
CFG="$H/.openclaw/openclaw.json"
OUT="$(run_mon "$H")"; RC=$?

DEF="$(cfgv "$CFG" "cfg['agents']['defaults']['maxConcurrent']")"
SUB="$(cfgv "$CFG" "cfg['agents']['defaults']['subagents']['maxConcurrent']")"
if [ "$DEF" = "$SAFE_PIN" ] && [ "$SUB" = "$SAFE_PIN" ]; then
    pass "A1 both keys healed 500 -> $SAFE_PIN (defaults=$DEF, subagents=$SUB)"
else
    fail "A1 keys NOT both healed: defaults.maxConcurrent=$DEF subagents.maxConcurrent=$SUB (want $SAFE_PIN/$SAFE_PIN) rc=$RC"
fi

if [ "$(backups "$H/.openclaw")" -ge 1 ]; then
    pass "A2 timestamped backup of openclaw.json created before the write"
else
    fail "A2 no openclaw.json.bak.capacity.* backup written"
fi

PROF="$H/.openclaw/.capacity-profile.json"
if [ -f "$PROF" ]; then
    PSUB="$(cfgv "$PROF" "cfg['previousMaxConcurrent']")"
    PDEF="$(cfgv "$PROF" "cfg['previousDefaultsMaxConcurrent']")"
    PNOW="$(cfgv "$PROF" "cfg['maxConcurrentAgents']")"
    if [ "$PSUB" = "500" ] && [ "$PDEF" = "500" ] && [ "$PNOW" = "$SAFE_PIN" ]; then
        pass "A3 profile records BOTH previous values (previousMaxConcurrent=500, previousDefaultsMaxConcurrent=500) and maxConcurrentAgents=$SAFE_PIN"
    else
        fail "A3 profile fields wrong: previousMaxConcurrent=$PSUB previousDefaultsMaxConcurrent=$PDEF maxConcurrentAgents=$PNOW"
    fi
else
    fail "A3 .capacity-profile.json not written"
fi

if echo "$OUT" | grep -q "HEAL" && echo "$OUT" | grep -q "defaults.maxConcurrent 500 -> $SAFE_PIN" \
   && echo "$OUT" | grep -q "subagents.maxConcurrent 500 -> $SAFE_PIN"; then
    pass "A4 HEAL log names BOTH keys and BOTH previous values"
else
    fail "A4 HEAL log does not name both keys: $(echo "$OUT" | grep -i heal | head -1)"
fi
echo ""

# ===========================================================================
# B — already in sync: no rewrite
# ===========================================================================
echo "--- B: in-sync config -> no rewrite ---"

IN_SYNC="{\"agents\":{\"defaults\":{\"maxConcurrent\":$SAFE_PIN,\"subagents\":{\"maxConcurrent\":$SAFE_PIN}}}}"
H="$(mk_root b "$IN_SYNC")"
CFG="$H/.openclaw/openclaw.json"
BEFORE="$(cat "$CFG")"
OUT="$(run_mon "$H")"

if [ "$BEFORE" = "$(cat "$CFG")" ]; then
    pass "B1 in-sync config left byte-identical (no pointless rewrite)"
else
    fail "B1 rewrote a config that was already in sync"
fi
if [ "$(backups "$H/.openclaw")" = "0" ]; then
    pass "B2 no backup churn on a no-op tick"
else
    fail "B2 produced a backup for a no-op tick"
fi
echo ""

# ===========================================================================
# C — THE EXACT INCIDENT: subagents already safe, defaults still 500
# ===========================================================================
echo "--- C: defaults=500 while subagents is already safe (the incident) ---"

INCIDENT="{\"agents\":{\"defaults\":{\"maxConcurrent\":500,\"subagents\":{\"maxConcurrent\":$SAFE_PIN}}}}"
H="$(mk_root c "$INCIDENT")"
CFG="$H/.openclaw/openclaw.json"
OUT="$(run_mon "$H")"

DEF="$(cfgv "$CFG" "cfg['agents']['defaults']['maxConcurrent']")"
SUB="$(cfgv "$CFG" "cfg['agents']['defaults']['subagents']['maxConcurrent']")"
if [ "$DEF" = "$SAFE_PIN" ]; then
    pass "C1 defaults.maxConcurrent healed 500 -> $SAFE_PIN even though subagents was already in sync"
else
    fail "C1 THE INCIDENT REPRODUCES: defaults.maxConcurrent still $DEF — a subagents-only 'in sync' check leaves the top-level cap at 500"
fi
if [ "$SUB" = "$SAFE_PIN" ]; then
    pass "C2 already-safe subagents key preserved at $SAFE_PIN"
else
    fail "C2 disturbed the already-safe subagents key: $SUB"
fi
if [ "$(backups "$H/.openclaw")" -ge 1 ]; then
    pass "C3 backup written for the defaults-only heal"
else
    fail "C3 healed the config without a backup"
fi
echo ""

# ===========================================================================
# D — defaults key absent: heal subagents, never CREATE the strict key
# ===========================================================================
echo "--- D: defaults key absent (.strict() safety) ---"

ABSENT='{"agents":{"defaults":{"subagents":{"maxConcurrent":500}}}}'
H="$(mk_root d "$ABSENT")"
CFG="$H/.openclaw/openclaw.json"
OUT="$(run_mon "$H")"

SUB="$(cfgv "$CFG" "cfg['agents']['defaults']['subagents']['maxConcurrent']")"
HAS="$(cfgv "$CFG" "'maxConcurrent' in cfg['agents']['defaults']")"
if [ "$SUB" = "$SAFE_PIN" ]; then
    pass "D1 subagents.maxConcurrent healed 500 -> $SAFE_PIN with the top-level key absent"
else
    fail "D1 subagents.maxConcurrent = $SUB (want $SAFE_PIN)"
fi
if [ "$HAS" = "False" ]; then
    pass "D2 absent agents.defaults.maxConcurrent NOT created (AgentDefaultsSchema is .strict() — an unknown key rejects the whole config)"
else
    fail "D2 CREATED agents.defaults.maxConcurrent on a config that lacked it — a runtime predating the key would reject this box's ENTIRE config"
fi
echo ""

# ===========================================================================
# E — runaway override warns loudly but stays an escape hatch
# ===========================================================================
echo "--- E: runaway OC_CAP_* override -> loud WARN, still exit 0 ---"

H="$(mk_root e "$BOTH_500")"
OUT="$(env -i PATH="$PATH" HOME="$H" \
        OC_CAP_MIN_AGENTS=200 OC_CAP_MAX_AGENTS=200 \
        bash "$MON_SH" 2>&1)"
RC=$?

if echo "$OUT" | grep -q "RUNAWAY CAP"; then
    pass "E1 a cap above min(cores*4, 64) emits a loud WARN (500-for-5-days can no longer sit silent)"
else
    fail "E1 no RUNAWAY CAP warning for a computed cap of 200: $(echo "$OUT" | tail -2)"
fi
if [ "$RC" = "0" ]; then
    pass "E2 exit 0 preserved — the WARN informs, it does not clamp or fail the deliberate-raise path"
else
    fail "E2 exit code changed to $RC — the OC_CAP_* escape hatch must stay usable"
fi
echo ""

# ===========================================================================
echo "=== RESULT: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
