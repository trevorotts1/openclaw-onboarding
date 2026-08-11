#!/usr/bin/env bash
# tests/unit/fleet-standards-plugins-allow-sovereignty.test.sh
#
# CI guard: proves the fix/loop-fault-class-20260811 (UNIT U8) resolution of
# the two-writer plugins.allow contradiction between scripts/apply-fleet-
# standards.sh (the ENUMERATOR) and scripts/repair-model-sovereignty.sh (the
# STRIPPER).
#
# THE DEFECT THIS GUARDS AGAINST: apply-fleet-standards.sh's plugins.allow
# enumerator used to compute the UNION of every currently-installed plugin id
# (bundled + non-bundled) and assign it wholesale, unconditionally re-adding
# "anthropic" every run because the plugin is installed on the box.
# repair-model-sovereignty.sh then strips "anthropic" from plugins.allow on
# every run (a hardcoded, by-name strip -- see that script's
# _strip_provider_and_plugins(), ~lines 324-362). Two writers, one key,
# contradictory intent: measured as a permanent oscillation of 2 config
# mutations + 1-2 SIGUSR1 gateway restarts per roll chain, killing every
# in-flight agent run mid-task.
#
# THE FIX under test (scripts/apply-fleet-standards.sh, the "DYNAMIC
# plugins.allow" block):
#   Part 1 -- config/plugins-sovereignty-denylist.json is the ONE shared,
#             authoritative "must never appear in plugins.allow" list.
#   Part 2 -- the enumerator subtracts that deny-set from the union BEFORE
#             assignment, so it stops re-adding what the stripper removes.
#   Part 3 -- read-compare-write: only assigns cfg["plugins"]["allow"] when
#             the computed value (sorted) actually DIFFERS from what is
#             already there. A converged box therefore makes NO second write.
#
# Assertion groups:
#   (1) DENY_SET_EXCLUDED       -- enumeration includes a denied id
#                                  ("anthropic") -> the written plugins.allow
#                                  EXCLUDES it. THE ASSERTION THAT MATTERS
#                                  MOST -- this is the oscillation fix itself.
#   (2) NO_COLLATERAL_PRUNING   -- non-bundled / path-loaded / config-origin
#                                  ids present in the SAME enumeration ARE
#                                  preserved (only the deny-set is removed --
#                                  this is the 2026-08-05 fleet-roll-blocker
#                                  UNION behavior, which the deny-set
#                                  subtraction must not silently re-break).
#   (3) CONVERGENCE_SILENCE     -- running the block twice against an
#                                  already-converged config produces NO
#                                  second write (no "plugins.allow set to"
#                                  message on the 2nd run; cfg unchanged).
#   (4) FAIL_OPEN_NO_ENUMERATION -- plugin enumeration unavailable -> nothing
#                                  written AT ALL (cfg byte-for-byte
#                                  unchanged), matching the PRE-EXISTING
#                                  fail-open contract, untouched by this fix.
#   (5) DENYLIST_MISSING_OR_UNREADABLE -- the deny-list file is unresolved
#                                  (5a) or present but unparseable (5b) ->
#                                  falls back to the CURRENT (pre-fix)
#                                  behavior (denied id NOT subtracted), warns
#                                  on stderr, and does NOT crash (exit 0).
#                                  [5c, bonus] a deny-list whose
#                                  deny_plugin_ids is not a list -> same
#                                  fallback + warning, same no-crash.
#
# The plugins.allow block is extracted LIVE out of the shipped script
# (between its own two-anchor comments), never pasted as a frozen copy, so
# this test tracks the real source. It is exec()'d inside a minimal python
# driver against temp fixture cfg/plugins-list/deny-list files -- the whole
# roll (deep-merge, WhatsApp ban, CEO tool-gate, AGENTS.md injection, model-
# sovereignty repair, `openclaw config validate`, etc.) NEVER runs. No real
# openclaw.json, no live gateway, is touched.
#
# Run: bash tests/unit/fleet-standards-plugins-allow-sovereignty.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$REPO_ROOT/scripts/apply-fleet-standards.sh"
REAL_DENYLIST="$REPO_ROOT/config/plugins-sovereignty-denylist.json"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== fleet-standards-plugins-allow-sovereignty.test.sh ==="
echo ""

if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
  echo "FATAL: scripts/apply-fleet-standards.sh not found at $SCRIPT_UNDER_TEST" >&2
  exit 1
fi
if [[ ! -f "$REAL_DENYLIST" ]]; then
  echo "FATAL: config/plugins-sovereignty-denylist.json not found at $REAL_DENYLIST" >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/fleet-standards-plugins-allow.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Extract the "DYNAMIC plugins.allow" block LIVE out of the shipped script,
# bounded by its own start anchor (the block's own header comment) and the
# NEXT section's anchor (the GOAL-4 baseline comment that follows it) --
# never anchored to this fix's own added text, so a revert of the fix still
# extracts something and assertion (1) fails for the RIGHT reason instead of
# silently no-oping on an empty extraction.
#
# grep -nE (not awk -v with a regex variable) locates the anchor line
# numbers: this repo's em-dash-heavy comments were observed to silently
# fail to match via `awk -v pat=... '$0 ~ pat'` on this host's awk even
# though the identical ERE matches fine via `grep -E` -- sed -n a,bp on the
# grep-derived line numbers sidesteps that entirely (no regex re-evaluation
# of the em-dash content inside awk/sed).
# ---------------------------------------------------------------------------
START_MARKER='DYNAMIC plugins\.allow — vetted-bundled-only plugin gate \(box-specific\)'
END_MARKER='DEFECT 1 \(v13\.1\.3\) — schema-version-aware no-refusal baseline\.'

start_count="$(grep -cE "$START_MARKER" "$SCRIPT_UNDER_TEST")"
end_count="$(grep -cE "$END_MARKER" "$SCRIPT_UNDER_TEST")"

if [[ "$start_count" -ne 1 ]]; then
  echo "FATAL: start anchor ('DYNAMIC plugins.allow — vetted-bundled-only...') matched $start_count time(s) in $SCRIPT_UNDER_TEST, expected exactly 1 -- cannot extract unambiguously. STOPPING (per binding instructions: locate-and-verify every anchor; if not found exactly once, stop and report)." >&2
  exit 1
fi
if [[ "$end_count" -ne 1 ]]; then
  echo "FATAL: end anchor ('DEFECT 1 (v13.1.3) — schema-version-aware...') matched $end_count time(s) in $SCRIPT_UNDER_TEST, expected exactly 1 -- cannot extract unambiguously. STOPPING." >&2
  exit 1
fi

start_line="$(grep -nE "$START_MARKER" "$SCRIPT_UNDER_TEST" | head -1 | cut -d: -f1)"
end_line="$(grep -nE "$END_MARKER" "$SCRIPT_UNDER_TEST" | head -1 | cut -d: -f1)"

if [[ -z "$start_line" || -z "$end_line" || "$end_line" -le "$start_line" ]]; then
  echo "FATAL: anchor line numbers unusable (start=$start_line end=$end_line)" >&2
  exit 1
fi

BLOCK="$TMP/plugins-allow-block.py"
sed -n "$((start_line + 1)),$((end_line - 1))p" "$SCRIPT_UNDER_TEST" > "$BLOCK"

if [[ ! -s "$BLOCK" ]]; then
  fail "0: extraction produced an empty block -- anchors matched but nothing between them"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi

if ! python3 -m py_compile "$BLOCK" 2>"$TMP/pycompile.err"; then
  fail "0: extracted plugins.allow block fails python3 -m py_compile: $(cat "$TMP/pycompile.err")"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
else
  pass "0: extracted plugins.allow block (lines $((start_line + 1))-$((end_line - 1)) of $(basename "$SCRIPT_UNDER_TEST")) compiles clean"
fi

# ---------------------------------------------------------------------------
# Minimal python driver: loads a fixture cfg dict, exec()'s the extracted
# block against it (same globals: json/os/sys/Path, exactly what the block
# itself imports/uses in the real script), then dumps the resulting cfg.
# ---------------------------------------------------------------------------
DRIVER="$TMP/driver.py"
cat > "$DRIVER" <<'EOF'
import json, os, sys
from pathlib import Path

cfg_path = os.environ["TEST_CFG_PATH"]
block_path = os.environ["TEST_BLOCK_PATH"]
out_path = os.environ["TEST_OUT_PATH"]

with open(cfg_path) as f:
    cfg = json.loads(f.read())

with open(block_path) as f:
    _code = f.read()

exec(compile(_code, block_path, "exec"))

with open(out_path, "w") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
EOF

# allow_of.py CFG_JSON -- prints the plugins.allow list, one id per line, or
# the literal "MISSING" if plugins.allow is absent. Line-based output keeps
# the bash-side assertions simple (grep -qx / wc -l) without re-implementing
# JSON parsing in bash.
ALLOW_OF="$TMP/allow_of.py"
cat > "$ALLOW_OF" <<'EOF'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
plugins = d.get("plugins")
allow = plugins.get("allow") if isinstance(plugins, dict) else None
if allow is None:
    print("MISSING")
else:
    for x in allow:
        print(x)
EOF

# cfg_equal.py A_JSON B_JSON -- prints EQUAL or DIFFERENT (structural, not
# byte, comparison -- indentation/key-order-independent).
CFG_EQUAL="$TMP/cfg_equal.py"
cat > "$CFG_EQUAL" <<'EOF'
import json, sys
with open(sys.argv[1]) as f:
    a = json.load(f)
with open(sys.argv[2]) as f:
    b = json.load(f)
print("EQUAL" if a == b else "DIFFERENT")
EOF

# run_block CFG_IN OUT_JSON LOG PLUGINS_JSON ENUM_OK DENYLIST
#   Runs the extracted block once via the driver, with the given env. Returns
#   the driver's exit code. DENYLIST="" reproduces what the real bash caller
#   exports when none of its 5 candidate paths resolved (FLEET_DENYLIST_FILE
#   present but empty) -- the exact "unresolved" case, not an unset var.
run_block() {
  local cfg_in="$1" out_json="$2" log="$3" plugins_json="$4" enum_ok="$5" denylist="$6"
  (
    export FLEET_PLUGINS_ENUM_OK="$enum_ok"
    export FLEET_PLUGINS_JSON_FILE="$plugins_json"
    export FLEET_DENYLIST_FILE="$denylist"
    export TEST_CFG_PATH="$cfg_in"
    export TEST_BLOCK_PATH="$BLOCK"
    export TEST_OUT_PATH="$out_json"
    python3 "$DRIVER"
  ) >"$log" 2>&1
  return $?
}

# ---------------------------------------------------------------------------
# Shared fixture: a plugin enumeration containing the denied id ("anthropic",
# origin=bundled) ALONGSIDE a non-denied bundled id, a config-origin id
# (mirrors ceo-routing-doctrine, the real regression that forced the
# UNION-not-replacement fix on 2026-08-05), and a global-origin id (mirrors
# a path-loaded / npm-installed plugin). Used by cases (1), (2), (3).
# ---------------------------------------------------------------------------
FIXTURE_PLUGINS_JSON="$TMP/plugins-list.json"
cat > "$FIXTURE_PLUGINS_JSON" <<'EOF'
{"plugins": [
  {"id": "anthropic", "origin": "bundled"},
  {"id": "moonshot", "origin": "bundled"},
  {"id": "ceo-routing-doctrine", "origin": "config"},
  {"id": "perplexity", "origin": "global"}
]}
EOF

# ---------------------------------------------------------------------------
# (1)/(2) DENY_SET_EXCLUDED + NO_COLLATERAL_PRUNING -- one run, several
#     assertions against its single result (same grouping style as the
#     existing qc-assert-config-write-chown.test.sh house pattern).
# ---------------------------------------------------------------------------
echo "--- (1)/(2) DENY_SET_EXCLUDED + NO_COLLATERAL_PRUNING: one enumeration, denied id excluded, everything else preserved ---"

CFG1="$TMP/cfg1-in.json"
printf '{"plugins": {"allow": ["stale-old-id"]}}' > "$CFG1"
OUT1="$TMP/cfg1-out.json"
LOG1="$TMP/log1.txt"

run_block "$CFG1" "$OUT1" "$LOG1" "$FIXTURE_PLUGINS_JSON" "1" "$REAL_DENYLIST"
rc1=$?

if [[ "$rc1" -eq 0 ]]; then
  pass "1a: run against a live enumeration containing the denied id exits 0 (no crash)"
else
  fail "1a: run exited $rc1 (expected 0). Log:
$(cat "$LOG1")"
fi

allow1="$(python3 "$ALLOW_OF" "$OUT1" 2>/dev/null)"

if ! printf '%s\n' "$allow1" | grep -qx 'anthropic'; then
  pass "1b: THE OSCILLATION FIX -- 'anthropic' is EXCLUDED from the written plugins.allow"
else
  fail "1b: CRITICAL -- 'anthropic' is present in plugins.allow; the enumerator is re-adding what repair-model-sovereignty.sh strips -- the oscillation is NOT fixed. allow=[$allow1]"
fi

if grep -q "excluded 1 sovereignty-denied id(s)" "$LOG1" && grep -q "anthropic" "$LOG1"; then
  pass "1c: log names the exclusion and the excluded id (anthropic)"
else
  fail "1c: expected a log line naming 1 excluded sovereignty-denied id (anthropic). Log:
$(cat "$LOG1")"
fi

if printf '%s\n' "$allow1" | grep -qx 'moonshot'; then
  pass "2a: NO_COLLATERAL_PRUNING -- a non-denied BUNDLED id (moonshot) is preserved"
else
  fail "2a: moonshot (non-denied, bundled) missing from plugins.allow. allow=[$allow1]"
fi

if printf '%s\n' "$allow1" | grep -qx 'ceo-routing-doctrine'; then
  pass "2b: NO_COLLATERAL_PRUNING -- a CONFIG-origin (non-bundled) id (ceo-routing-doctrine) is preserved -- the 2026-08-05 fleet-roll-blocker fix stays intact"
else
  fail "2b: CRITICAL REGRESSION -- ceo-routing-doctrine (config-origin, non-bundled) missing from plugins.allow; this is the exact fleet-roll-blocker the 2026-08-05 UNION fix closed. allow=[$allow1]"
fi

if printf '%s\n' "$allow1" | grep -qx 'perplexity'; then
  pass "2c: NO_COLLATERAL_PRUNING -- a GLOBAL-origin (non-bundled, path/npm-loaded) id (perplexity) is preserved"
else
  fail "2c: perplexity (global-origin, non-bundled) missing from plugins.allow. allow=[$allow1]"
fi

allow1_count="$(printf '%s\n' "$allow1" | grep -c '.' || true)"
if [[ "${allow1_count:-0}" -eq 3 ]]; then
  pass "2d: plugins.allow has exactly 3 ids (4 enumerated - 1 denied), nothing extra"
else
  fail "2d: expected exactly 3 ids in plugins.allow, got ${allow1_count:-0}: [$allow1]"
fi

if grep -q "plugins.allow set to" "$LOG1"; then
  pass "1d: a write occurred this run (existing allow was stale, not converged)"
else
  fail "1d: expected a 'plugins.allow set to' write message on a stale-input run. Log:
$(cat "$LOG1")"
fi

# ---------------------------------------------------------------------------
# (3) CONVERGENCE_SILENCE -- feed the run-1 RESULT back in as the starting
#     cfg (already converged) and run again with the SAME enumeration. No
#     second write.
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) CONVERGENCE_SILENCE: running twice against an already-converged config -> NO second write ---"

CFG3="$TMP/cfg3-in.json"
cp "$OUT1" "$CFG3"
OUT3="$TMP/cfg3-out.json"
LOG3="$TMP/log3.txt"

run_block "$CFG3" "$OUT3" "$LOG3" "$FIXTURE_PLUGINS_JSON" "1" "$REAL_DENYLIST"
rc3=$?

if [[ "$rc3" -eq 0 ]]; then
  pass "3a: second run (against a converged config) exits 0"
else
  fail "3a: second run exited $rc3 (expected 0). Log:
$(cat "$LOG3")"
fi

if grep -q "already converged" "$LOG3"; then
  pass "3b: log reports plugins.allow already converged -- no write"
else
  fail "3b: expected an 'already converged' log line on the second run. Log:
$(cat "$LOG3")"
fi

if grep -q "plugins.allow set to" "$LOG3"; then
  fail "3c: CRITICAL -- a 'plugins.allow set to' WRITE message appeared on the second (converged) run -- the read-compare-write is not suppressing the no-op write. This is the exact class of bug (an unconditional write on an unchanged value) that produces a SIGUSR1 restart on every roll of an already-clean box."
else
  pass "3c: no 'plugins.allow set to' write message on the second (converged) run"
fi

eq3="$(python3 "$CFG_EQUAL" "$CFG3" "$OUT3" 2>/dev/null)"
if [[ "$eq3" == "EQUAL" ]]; then
  pass "3d: resulting cfg is structurally UNCHANGED by the second (converged) run"
else
  fail "3d: cfg changed on the second (converged) run (expected EQUAL, got $eq3)"
fi

# ---------------------------------------------------------------------------
# (4) FAIL_OPEN_NO_ENUMERATION -- plugin enumeration unavailable -> NOTHING
#     written at all. This is the PRE-EXISTING fail-open contract; must stay
#     intact after Parts 1-3 of this fix.
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) FAIL_OPEN_NO_ENUMERATION: enumeration unavailable -> nothing written at all ---"

CFG4="$TMP/cfg4-in.json"
printf '{"plugins": {"allow": ["untouched-existing-id"]}, "channels": {"telegram": {"mediaMaxMb": 50}}}' > "$CFG4"
OUT4="$TMP/cfg4-out.json"
LOG4="$TMP/log4.txt"

run_block "$CFG4" "$OUT4" "$LOG4" "" "0" "$REAL_DENYLIST"
rc4=$?

if [[ "$rc4" -eq 0 ]]; then
  pass "4a: run with enumeration unavailable exits 0 (no crash)"
else
  fail "4a: run exited $rc4 (expected 0). Log:
$(cat "$LOG4")"
fi

eq4="$(python3 "$CFG_EQUAL" "$CFG4" "$OUT4" 2>/dev/null)"
if [[ "$eq4" == "EQUAL" ]]; then
  pass "4b: cfg is structurally UNCHANGED -- nothing written at all when enumeration is unavailable"
else
  fail "4b: cfg CHANGED with enumeration unavailable (expected EQUAL, got $eq4) -- fail-open contract broken"
fi

if grep -q "plugins.allow enumeration unavailable this run" "$LOG4"; then
  pass "4c: log reports enumeration unavailable"
else
  fail "4c: expected a 'plugins.allow enumeration unavailable this run' log line. Log:
$(cat "$LOG4")"
fi

# ---------------------------------------------------------------------------
# (5) DENYLIST_MISSING_OR_UNREADABLE -- falls back to CURRENT (pre-fix)
#     behavior with a warning, never crashes.
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) DENYLIST_MISSING_OR_UNREADABLE: fallback to pre-fix behavior, warns, never crashes ---"

# (5a) unresolved (empty string -- what the real bash caller exports when
#      none of its 5 candidate paths matched).
CFG5A="$TMP/cfg5a-in.json"
printf '{}' > "$CFG5A"
OUT5A="$TMP/cfg5a-out.json"
LOG5A="$TMP/log5a.txt"

run_block "$CFG5A" "$OUT5A" "$LOG5A" "$FIXTURE_PLUGINS_JSON" "1" ""
rc5a=$?

if [[ "$rc5a" -eq 0 ]]; then
  pass "5a-i: unresolved deny-list path -> exits 0 (no crash)"
else
  fail "5a-i: unresolved deny-list path exited $rc5a (expected 0). Log:
$(cat "$LOG5A")"
fi

allow5a="$(python3 "$ALLOW_OF" "$OUT5A" 2>/dev/null)"
if printf '%s\n' "$allow5a" | grep -qx 'anthropic'; then
  pass "5a-ii: with the deny-list unresolved, plugins.allow falls back to the PRE-FIX behavior ('anthropic' included, nothing subtracted)"
else
  fail "5a-ii: expected 'anthropic' present in plugins.allow when the deny-list is unresolved (pre-fix fallback). allow=[$allow5a]"
fi

if grep -qi "WARNING" "$LOG5A" && grep -q "not found in any delivered location" "$LOG5A"; then
  pass "5a-iii: a WARNING is logged when the deny-list file is unresolved"
else
  fail "5a-iii: expected a WARNING about the unresolved deny-list file. Log:
$(cat "$LOG5A")"
fi

# (5b) present but unparseable (malformed JSON).
BAD_DENYLIST="$TMP/bad-denylist.json"
printf '{ this is not valid json' > "$BAD_DENYLIST"
CFG5B="$TMP/cfg5b-in.json"
printf '{}' > "$CFG5B"
OUT5B="$TMP/cfg5b-out.json"
LOG5B="$TMP/log5b.txt"

run_block "$CFG5B" "$OUT5B" "$LOG5B" "$FIXTURE_PLUGINS_JSON" "1" "$BAD_DENYLIST"
rc5b=$?

if [[ "$rc5b" -eq 0 ]]; then
  pass "5b-i: unparseable (malformed JSON) deny-list file -> exits 0 (no crash)"
else
  fail "5b-i: unparseable deny-list file exited $rc5b (expected 0 -- fail-open must never crash the roll). Log:
$(cat "$LOG5B")"
fi

allow5b="$(python3 "$ALLOW_OF" "$OUT5B" 2>/dev/null)"
if printf '%s\n' "$allow5b" | grep -qx 'anthropic'; then
  pass "5b-ii: with an unparseable deny-list, plugins.allow falls back to the PRE-FIX behavior ('anthropic' included, nothing subtracted)"
else
  fail "5b-ii: expected 'anthropic' present in plugins.allow when the deny-list fails to parse (pre-fix fallback). allow=[$allow5b]"
fi

if grep -qi "WARNING" "$LOG5B" && grep -q "failed to parse plugins-sovereignty-denylist.json" "$LOG5B"; then
  pass "5b-iii: a WARNING is logged when the deny-list file fails to parse"
else
  fail "5b-iii: expected a WARNING about the unparseable deny-list file. Log:
$(cat "$LOG5B")"
fi

# (5c, bonus) present, parseable JSON, but deny_plugin_ids is not a list.
BAD_SHAPE_DENYLIST="$TMP/bad-shape-denylist.json"
printf '{"deny_plugin_ids": "anthropic"}' > "$BAD_SHAPE_DENYLIST"
CFG5C="$TMP/cfg5c-in.json"
printf '{}' > "$CFG5C"
OUT5C="$TMP/cfg5c-out.json"
LOG5C="$TMP/log5c.txt"

run_block "$CFG5C" "$OUT5C" "$LOG5C" "$FIXTURE_PLUGINS_JSON" "1" "$BAD_SHAPE_DENYLIST"
rc5c=$?

if [[ "$rc5c" -eq 0 ]]; then
  pass "5c-i [bonus]: deny-list with a non-list 'deny_plugin_ids' -> exits 0 (no crash)"
else
  fail "5c-i [bonus]: exited $rc5c (expected 0). Log:
$(cat "$LOG5C")"
fi

allow5c="$(python3 "$ALLOW_OF" "$OUT5C" 2>/dev/null)"
if printf '%s\n' "$allow5c" | grep -qx 'anthropic'; then
  pass "5c-ii [bonus]: non-list 'deny_plugin_ids' -> falls back to the PRE-FIX behavior ('anthropic' included)"
else
  fail "5c-ii [bonus]: expected 'anthropic' present in plugins.allow with a non-list deny_plugin_ids. allow=[$allow5c]"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all fleet-standards plugins.allow sovereignty checks pass"
exit 0
