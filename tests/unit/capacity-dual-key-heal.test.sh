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

# A4 — DID IT ACTUALLY WRITE? (mutation-hardened 2026-08-02)
#
# This check used to assert the HEAL LOG STRING and nothing else, so it could
# not tell "logged a heal" from "performed a heal". Under a mutation that
# deleted the atomic os.replace() the log line was still printed and A4 stayed
# GREEN while the config on disk was untouched. A test that passes either way is
# worthless, so A4 now asserts the PERSISTED CONFIG: both keys re-read from
# disk, and no surviving 500 anywhere in the file. The log WORDING moved to A5,
# which is deliberately not load-bearing.
A4_DEF="$(cfgv "$CFG" "cfg['agents']['defaults']['maxConcurrent']")"
A4_SUB="$(cfgv "$CFG" "cfg['agents']['defaults']['subagents']['maxConcurrent']")"
A4_STALE="$(cfgv "$CFG" "500 in (cfg['agents']['defaults']['maxConcurrent'], cfg['agents']['defaults']['subagents']['maxConcurrent'])")"
if [ "$A4_DEF" = "$SAFE_PIN" ] && [ "$A4_SUB" = "$SAFE_PIN" ] && [ "$A4_STALE" = "False" ]; then
    pass "A4 the heal was PERFORMED, not just logged — both keys persisted to disk at $SAFE_PIN, no 500 survives"
else
    fail "A4 config on disk does not reflect the heal: defaults=$A4_DEF subagents=$A4_SUB stale500=$A4_STALE — the writer logged a heal it did not perform"
fi

if echo "$OUT" | grep -q "HEAL" && echo "$OUT" | grep -q "defaults.maxConcurrent 500 -> $SAFE_PIN" \
   && echo "$OUT" | grep -q "subagents.maxConcurrent 500 -> $SAFE_PIN"; then
    pass "A5 HEAL log names BOTH keys and BOTH previous values (reporting only — A4 is the proof)"
else
    fail "A5 HEAL log does not name both keys: $(echo "$OUT" | grep -i heal | head -1)"
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
# F — the guard must be REACHABLE THROUGH ITS OWN DOCUMENTED KNOB
#
# E1 only ever passed because it sets OC_CAP_MIN_AGENTS=200 — a FLOOR, and a
# knob the rationale never mentions. The documented raise knob is
# OC_CAP_MAX_AGENTS, and it is a CLAMP: raising it cannot push `safe` above
# cores*CORES_MULT, while the guard fires above cores*4. So on a 12-core box
# OC_CAP_MAX_AGENTS=500 produced safe=14 and ZERO warnings, and even
# OC_CAP_RAM_PER_AGENT_GB=0.01 only reached 24 — still silent. The guard read as
# protection while protecting nothing through the path operators are told to use.
# ===========================================================================
echo "--- F: RUNAWAY guard reachable through the DOCUMENTED override ---"

H="$(mk_root f "$BOTH_500")"
OUT="$(env -i PATH="$PATH" HOME="$H" OC_CAP_MAX_AGENTS=500 OC_CAP_DRY_RUN=1 bash "$MON_SH" 2>&1)"
RC=$?
if echo "$OUT" | grep -q "RUNAWAY CAP"; then
    pass "F1 OC_CAP_MAX_AGENTS=500 alone trips RUNAWAY CAP (the documented knob now reaches the guard)"
else
    fail "F1 OC_CAP_MAX_AGENTS=500 produced NO warning — the guard is unreachable through its own documented override: $(echo "$OUT" | tail -2)"
fi
if [ "$RC" = "0" ]; then
    pass "F2 exit 0 preserved for the documented-override warn path"
else
    fail "F2 exit code changed to $RC"
fi

# No override at all -> the platform default (12 Mac / 8 VPS) must NEVER warn,
# or the guard becomes noise on every tick of every small box and gets ignored.
H="$(mk_root f2 "{\"agents\":{\"defaults\":{\"maxConcurrent\":2,\"subagents\":{\"maxConcurrent\":2}}}}")"
OUT="$(env -i PATH="$PATH" HOME="$H" OC_CAP_DRY_RUN=1 bash "$MON_SH" 2>&1)"
if echo "$OUT" | grep -q "RUNAWAY CAP"; then
    fail "F3 platform-default MAX_AGENTS warned — a guard that cries wolf every tick will be ignored: $(echo "$OUT" | grep RUNAWAY | head -1)"
else
    pass "F3 no override, healthy config -> no RUNAWAY warning (guard stays credible)"
fi
echo ""

# ===========================================================================
# G — warn on the value FOUND IN CONFIG, which is what actually happened
#
# The 2026-08-01 incident was NOT a computed value: it was a hand-written
# maxConcurrent: 500 in openclaw.json. The computed value was a healthy 12
# throughout, so a computed-value guard would have said nothing about the very
# config that crushed the box for five days.
# ===========================================================================
echo "--- G: absurd value FOUND in config warns (the real incident shape) ---"

H="$(mk_root g "$BOTH_500")"
OUT="$(env -i PATH="$PATH" HOME="$H" OC_CAP_DRY_RUN=1 bash "$MON_SH" 2>&1)"
RC=$?
if echo "$OUT" | grep -q "ABSURD CAP IN CONFIG"; then
    pass "G1 a hand-written 500 in openclaw.json warns with ZERO OC_CAP_* overrides set"
else
    fail "G1 config holding 500 produced no warning — the monitor still watches only what it COMPUTES, not what it FINDS: $(echo "$OUT" | tail -2)"
fi
if echo "$OUT" | grep -q "agents.defaults.maxConcurrent=500" && echo "$OUT" | grep -q "subagents.maxConcurrent=500"; then
    pass "G2 the warning names BOTH offending keys and their found values"
else
    fail "G2 warning does not name both found keys: $(echo "$OUT" | grep ABSURD | head -1)"
fi
if [ "$RC" = "0" ]; then
    pass "G3 exit 0 preserved (the tick still heals; the warn is additive)"
else
    fail "G3 exit code changed to $RC"
fi

# Fires on the healing tick too, not only in dry-run: something wrote that value
# out-of-band and will likely write it again, so the event must be surfaced even
# when this tick repairs it.
H="$(mk_root g2 "$BOTH_500")"
OUT="$(run_mon "$H")"
if echo "$OUT" | grep -q "ABSURD CAP IN CONFIG"; then
    pass "G4 warning fires on the HEALING tick as well (the writer that put it there is still out there)"
else
    fail "G4 no warning on the healing tick — an out-of-band 500 heals silently and nobody learns it happened"
fi

# And a healthy config must stay completely quiet.
H="$(mk_root g3 "{\"agents\":{\"defaults\":{\"maxConcurrent\":$SAFE_PIN,\"subagents\":{\"maxConcurrent\":$SAFE_PIN}}}}")"
OUT="$(run_mon "$H")"
if echo "$OUT" | grep -qE "ABSURD CAP IN CONFIG"; then
    fail "G5 healthy in-sync config produced an ABSURD warning: $(echo "$OUT" | grep ABSURD | head -1)"
else
    pass "G5 healthy config produces no ABSURD warning (no false positives)"
fi
echo ""

# ===========================================================================
echo "=== RESULT: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
