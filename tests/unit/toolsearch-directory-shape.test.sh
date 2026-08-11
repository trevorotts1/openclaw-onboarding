#!/usr/bin/env bash
# tests/unit/toolsearch-directory-shape.test.sh
#
# CI guard for the tools.toolSearch shape written by scripts/apply-fleet-standards.sh
# and for the fleet drift guard that keeps it there.
#
# THE DEFECT THIS GUARDS AGAINST
#   tools.toolSearch must be the EXPLICIT object {"enabled": true, "mode": "directory"}.
#   Two distinct failures were seen on boxes:
#
#   (a) SHAPE DRIFT. apply-fleet-standards.sh's CANONICAL block wrote only `mode`.
#       A box whose config carried no `enabled` key therefore never got one --
#       the feature's on/off state was left to whatever default the running
#       gateway applied, and the persisted shape differed box to box. Both keys
#       must be written so the object is fully specified and identical fleet-wide.
#
#   (b) VALUE KNOCKED OFF "directory" AFTER THE WRITE. This is NOT caused by any
#       fleet script. OpenClaw's own config persistence rewrites the file during
#       the container boot window and drops the value. The post-merge assertion
#       inside apply-fleet-standards.sh is a WRITE-TIME check -- it proves what
#       that script is about to persist, at the instant it persists it, and by
#       construction CANNOT observe a third-party writer that acts between
#       passes. Closing that gap needs a PERIODIC guard, which is
#       scripts/guard-toolsearch-directory.sh. This file tests both halves.
#
#   Why the value matters: a scalar `tools.toolSearch` (e.g. bare `true`) selects
#   a prompt surface with NO hydration path. Every tool call returns "Tool not
#   found", the model starts guessing, and loop-detection blocks the tool without
#   ending the turn -- an unbounded, paid, self-sustaining loop.
#
# UPSTREAM, DELIBERATELY NOT ATTEMPTED HERE: the real root-cause fix is making
#   OpenClaw's own merge-patch guard in writeConfigFile unconditional. That is an
#   UPSTREAM change and is not ours to make. The guard tested here is the
#   fleet-side mitigation that holds the value until upstream lands.
#
# Assertion groups:
#   (0) EXTRACTION       -- the CANONICAL/deep_merge/assertion block is extracted
#                           LIVE from the shipped script and compiles.
#   (1) SHIPPED_SHAPE    -- the shipped CANONICAL declares BOTH enabled and mode.
#   (2) BEHAVIORAL_MERGE -- exec the real block against real-shaped configs and
#                           check what actually lands, for five drift shapes
#                           including the exact "mode but no enabled" box case.
#   (3) OVERRIDE_SAFETY  -- per-box tuning keys inside toolSearch are preserved.
#   (4) ASSERTION_LIVE   -- MUTATION PROOF: corrupt the extracted block's own
#                           CANONICAL value and confirm the post-merge assertion
#                           actually raises. Proves the assertion enforces, not
#                           merely that its source text exists.
#   (5) DRIFT_GUARD      -- scripts/guard-toolsearch-directory.sh exists, parses
#                           under STOCK /bin/bash 3.2, and is behaviorally
#                           correct: detects drift, backs up, restores, is
#                           fail-safe on an unreadable/garbage config, and is
#                           idempotent when the value is already correct.
#
# Run: bash tests/unit/toolsearch-directory-shape.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$REPO_ROOT/scripts/apply-fleet-standards.sh"
DRIFT_GUARD="$REPO_ROOT/scripts/guard-toolsearch-directory.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== toolsearch-directory-shape.test.sh ==="
echo "  interpreter: ${BASH_VERSION}"
echo ""

if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
  echo "FATAL: scripts/apply-fleet-standards.sh not found at $SCRIPT_UNDER_TEST" >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/toolsearch-shape.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# (0) Extract the CANONICAL + deep_merge + post-merge-assertion block LIVE from
#     the shipped script. Anchored on structural landmarks that exist
#     independently of this fix, so a revert still extracts something and the
#     assertions below fail for the RIGHT reason instead of no-oping on an
#     empty extraction.
#
#     grep -nE + sed -n a,bp (not awk -v with a regex variable): this repo's
#     em-dash-heavy comments have been observed to silently fail to match via
#     awk on this host even when the identical ERE matches under grep -E.
# ---------------------------------------------------------------------------
echo "--- (0) EXTRACTION: pull the live CANONICAL/merge/assertion block ---"

START_MARKER='^CANONICAL = \{'
END_MARKER='^# PROVIDER timeoutSeconds FLOOR\.'

start_count="$(grep -cE "$START_MARKER" "$SCRIPT_UNDER_TEST")"
end_count="$(grep -cE "$END_MARKER" "$SCRIPT_UNDER_TEST")"

if [[ "$start_count" -ne 1 ]]; then
  echo "FATAL: start anchor 'CANONICAL = {' matched $start_count time(s), expected exactly 1 -- cannot extract unambiguously. STOPPING." >&2
  exit 1
fi
if [[ "$end_count" -ne 1 ]]; then
  echo "FATAL: end anchor '# PROVIDER timeoutSeconds FLOOR.' matched $end_count time(s), expected exactly 1 -- cannot extract unambiguously. STOPPING." >&2
  exit 1
fi

start_line="$(grep -nE "$START_MARKER" "$SCRIPT_UNDER_TEST" | head -1 | cut -d: -f1)"
end_line="$(grep -nE "$END_MARKER" "$SCRIPT_UNDER_TEST" | head -1 | cut -d: -f1)"

if [[ -z "$start_line" || -z "$end_line" || "$end_line" -le "$start_line" ]]; then
  echo "FATAL: anchor line numbers unusable (start=$start_line end=$end_line)" >&2
  exit 1
fi

BLOCK="$TMP/canonical-block.py"
sed -n "${start_line},$((end_line - 1))p" "$SCRIPT_UNDER_TEST" > "$BLOCK"

if [[ ! -s "$BLOCK" ]]; then
  fail "0a: extraction produced an empty block -- anchors matched but nothing between them"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi

if ! python3 -m py_compile "$BLOCK" 2>"$TMP/pycompile.err"; then
  fail "0b: extracted block fails python3 -m py_compile: $(cat "$TMP/pycompile.err")"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi
pass "0b: extracted block (lines ${start_line}-$((end_line - 1)) of $(basename "$SCRIPT_UNDER_TEST")) compiles clean"

# ---------------------------------------------------------------------------
# Driver: load a fixture cfg, exec the REAL extracted block against it, dump
# the result. Exits 3 (not 1) if the block's own post-merge assertion raises,
# so (4) can tell "assertion fired" apart from "driver crashed".
# ---------------------------------------------------------------------------
DRIVER="$TMP/driver.py"
cat > "$DRIVER" <<'DRIVEREOF'
import json, os, sys
from pathlib import Path

cfg_path = os.environ["TEST_CFG_PATH"]
block_path = os.environ["TEST_BLOCK_PATH"]
out_path = os.environ["TEST_OUT_PATH"]

with open(cfg_path) as f:
    cfg = json.loads(f.read())
with open(block_path) as f:
    _code = f.read()

try:
    exec(compile(_code, block_path, "exec"))
except SystemExit as _e:
    sys.stderr.write("ASSERTION_FIRED: %s\n" % (_e,))
    sys.exit(3)

with open(out_path, "w") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
DRIVEREOF

# Reader: print the resulting toolSearch object as compact sorted JSON, or a
# marker if it is absent / not an object.
READER="$TMP/read_ts.py"
cat > "$READER" <<'READEREOF'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
tools = d.get("tools")
ts = tools.get("toolSearch") if isinstance(tools, dict) else None
if ts is None:
    print("MISSING")
elif not isinstance(ts, dict):
    print("SCALAR:%s" % json.dumps(ts))
else:
    print(json.dumps(ts, sort_keys=True, separators=(",", ":")))
READEREOF

# run_case FIXTURE_JSON -> echoes the resulting toolSearch, or DRIVER_RC:<n>
run_case() {
  local _fixture="$1"
  local _cfg="$TMP/case-cfg.json"
  local _out="$TMP/case-out.json"
  rm -f "$_out"
  printf '%s\n' "$_fixture" > "$_cfg"
  local _rc=0
  TEST_CFG_PATH="$_cfg" TEST_BLOCK_PATH="$BLOCK" TEST_OUT_PATH="$_out" \
    python3 "$DRIVER" 2>"$TMP/case-err.txt" || _rc=$?
  if [[ "$_rc" -ne 0 ]]; then
    echo "DRIVER_RC:${_rc}"
    return 0
  fi
  python3 "$READER" "$_out"
}

EXPECTED='{"enabled":true,"mode":"directory"}'

# ---------------------------------------------------------------------------
# (1) SHIPPED_SHAPE: the shipped CANONICAL must declare BOTH keys. Static, but
#     cheap and it names the exact regression ("someone dropped enabled again").
# ---------------------------------------------------------------------------
echo ""
echo "--- (1) SHIPPED_SHAPE: CANONICAL declares both enabled and mode ---"

if grep -qE '"enabled":[[:space:]]*True' "$BLOCK" && grep -qE '"mode":[[:space:]]*"directory"' "$BLOCK"; then
  pass "1a: shipped CANONICAL toolSearch declares both \"enabled\": True and \"mode\": \"directory\""
else
  fail "1a: shipped CANONICAL toolSearch does NOT declare both keys -- per-box shape drift returns (a box with no 'enabled' key never gets one)"
fi

# ---------------------------------------------------------------------------
# (2) BEHAVIORAL_MERGE: run the REAL block against the real drift shapes.
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) BEHAVIORAL_MERGE: real block vs. real drift shapes ---"

# 2a: no tools key at all (fresh box)
got="$(run_case '{}')"
if [[ "$got" == "$EXPECTED" ]]; then
  pass "2a: empty config -> $EXPECTED"
else
  fail "2a: empty config produced '$got', expected '$EXPECTED'"
fi

# 2b: THE OBSERVED BOX CASE -- mode present, `enabled` key absent.
got="$(run_case '{"tools":{"toolSearch":{"mode":"directory"}}}')"
if [[ "$got" == "$EXPECTED" ]]; then
  pass "2b: box with mode but NO 'enabled' key -> 'enabled' is added ($EXPECTED)"
else
  fail "2b: box with mode but no 'enabled' produced '$got', expected '$EXPECTED' -- this is the measured per-box shape drift"
fi

# 2c: scalar true -- the loop-arming shape. Must be replaced wholesale.
got="$(run_case '{"tools":{"toolSearch":true}}')"
if [[ "$got" == "$EXPECTED" ]]; then
  pass "2c: scalar 'true' (no hydration path; arms the paid tool-not-found loop) -> replaced wholesale with $EXPECTED"
else
  fail "2c: scalar 'true' produced '$got', expected '$EXPECTED'"
fi

# 2d: wrong mode -- the exact drift the guard chases.
got="$(run_case '{"tools":{"toolSearch":{"enabled":true,"mode":"code"}}}')"
if [[ "$got" == "$EXPECTED" ]]; then
  pass "2d: mode 'code' -> forced back to 'directory'"
else
  fail "2d: mode 'code' produced '$got', expected '$EXPECTED'"
fi

# 2e: explicitly disabled -- must be re-enabled, not left off.
got="$(run_case '{"tools":{"toolSearch":{"enabled":false,"mode":"directory"}}}')"
if [[ "$got" == "$EXPECTED" ]]; then
  pass "2e: enabled=false -> forced back to true"
else
  fail "2e: enabled=false produced '$got', expected '$EXPECTED'"
fi

# ---------------------------------------------------------------------------
# (3) OVERRIDE_SAFETY: per-box tuning inside toolSearch survives the merge.
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) OVERRIDE_SAFETY: per-box tuning keys preserved ---"

got="$(run_case '{"tools":{"toolSearch":{"mode":"code","codeTimeoutMs":9000,"searchDefaultLimit":25}}}')"
if [[ "$got" == '{"codeTimeoutMs":9000,"enabled":true,"mode":"directory","searchDefaultLimit":25}' ]]; then
  pass "3a: codeTimeoutMs/searchDefaultLimit preserved while enabled+mode are enforced"
else
  fail "3a: per-box tuning not preserved -- got '$got'"
fi

# ---------------------------------------------------------------------------
# (4) ASSERTION_LIVE -- MUTATION PROOF.
#     Corrupt the extracted block's OWN CANONICAL value and confirm the
#     post-merge assertion actually raises SystemExit. Without this, (1) and
#     (2) could both pass while the assertion had been quietly gutted, which
#     is the same class of dead-enforcement bug this repo has already shipped
#     once (a cap asserted as DEFINED while nothing enforced it at runtime).
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) ASSERTION_LIVE: mutation proof that the post-merge assertion enforces ---"

assert_fires_when() {
  local _label="$1" _sed_expr="$2"
  local _mutant="$TMP/mutant-block.py"
  sed "$_sed_expr" "$BLOCK" > "$_mutant"
  if cmp -s "$BLOCK" "$_mutant"; then
    fail "4-${_label}: mutation was a no-op (sed matched nothing) -- cannot prove the assertion fires"
    return 0
  fi
  local _cfg="$TMP/mut-cfg.json" _out="$TMP/mut-out.json" _rc=0
  rm -f "$_out"
  printf '%s\n' '{}' > "$_cfg"
  TEST_CFG_PATH="$_cfg" TEST_BLOCK_PATH="$_mutant" TEST_OUT_PATH="$_out" \
    python3 "$DRIVER" 2>"$TMP/mut-err.txt" || _rc=$?
  if [[ "$_rc" -eq 3 ]] && grep -q 'ASSERTION_FIRED' "$TMP/mut-err.txt"; then
    pass "4-${_label}: assertion RAISED on a corrupted CANONICAL (enforcement is live, not just present in source)"
  else
    fail "4-${_label}: assertion did NOT fire (driver rc=$_rc) -- the post-merge check is dead; a wrong toolSearch would be written silently"
  fi
}

# Mutate mode "directory" -> "code" inside the CANONICAL dict.
assert_fires_when "wrong-mode" 's/"mode": "directory"/"mode": "code"/'
# Mutate enabled True -> False inside the CANONICAL dict.
assert_fires_when "disabled" 's/"enabled": True/"enabled": False/'

# ---------------------------------------------------------------------------
# (5) DRIFT_GUARD: the periodic guard that closes the third-party-writer gap.
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) DRIFT_GUARD: scripts/guard-toolsearch-directory.sh ---"

if [[ ! -f "$DRIFT_GUARD" ]]; then
  fail "5a: scripts/guard-toolsearch-directory.sh not found -- the write-time assertion alone CANNOT catch a writer that acts between passes"
else
  pass "5a: drift guard present at scripts/guard-toolsearch-directory.sh"

  # INTERPRETER TRAP: the fleet's Macs run STOCK /bin/bash 3.2.57, not the
  # homebrew bash 5 on a dev box. A gate has already shipped here that parsed
  # fine under 5 and failed under 3.2. Check with /bin/bash explicitly.
  if [[ -x /bin/bash ]]; then
    if /bin/bash -n "$DRIFT_GUARD" 2>"$TMP/guard-syntax.err"; then
      pass "5b: drift guard parses under STOCK /bin/bash ($(/bin/bash -c 'echo $BASH_VERSION'))"
    else
      fail "5b: drift guard FAILS to parse under stock /bin/bash: $(cat "$TMP/guard-syntax.err")"
    fi
  else
    fail "5b: /bin/bash not found -- cannot verify the stock-interpreter parse"
  fi

  # --- behavioral: drive the guard against fixture configs ---
  GTMP="$TMP/guardrun"
  mkdir -p "$GTMP"

  # 5c: drift present -> restored, and a backup is left behind.
  CFG="$GTMP/drift.json"
  printf '%s\n' '{"tools":{"toolSearch":{"enabled":true,"mode":"code"},"exec":{"security":"full"}},"other":{"keep":1}}' > "$CFG"
  rc=0
  TOOLSEARCH_GUARD_CONFIG="$CFG" TOOLSEARCH_GUARD_BACKUP_DIR="$GTMP/backups" \
    TOOLSEARCH_GUARD_LOG="$GTMP/guard.log" /bin/bash "$DRIFT_GUARD" >"$GTMP/out-drift.txt" 2>&1 || rc=$?
  got="$(python3 "$READER" "$CFG" 2>/dev/null || echo "UNREADABLE")"
  if [[ "$got" == "$EXPECTED" ]]; then
    pass "5c: guard RESTORED a drifted value ('mode':'code' -> $EXPECTED), rc=$rc"
  else
    fail "5c: guard did not restore drift -- config now reads '$got' (rc=$rc)"
  fi

  if ls "$GTMP/backups"/* >/dev/null 2>&1; then
    pass "5d: guard wrote a backup before mutating the config"
  else
    fail "5d: guard mutated the config WITHOUT leaving a backup"
  fi

  # 5e: unrelated keys must survive the restore.
  if python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('other',{}).get('keep')==1 and d.get('tools',{}).get('exec',{}).get('security')=='full' else 1)" "$CFG" 2>/dev/null; then
    pass "5e: unrelated config keys (tools.exec, other) survived the restore"
  else
    fail "5e: guard clobbered unrelated config keys -- restore is not surgical"
  fi

  # 5f: already-correct config -> idempotent, no rewrite, no new backup.
  CFG2="$GTMP/ok.json"
  printf '%s\n' '{"tools":{"toolSearch":{"enabled":true,"mode":"directory"}}}' > "$CFG2"
  before="$(cat "$CFG2")"
  rc=0
  TOOLSEARCH_GUARD_CONFIG="$CFG2" TOOLSEARCH_GUARD_BACKUP_DIR="$GTMP/backups2" \
    TOOLSEARCH_GUARD_LOG="$GTMP/guard2.log" /bin/bash "$DRIFT_GUARD" >"$GTMP/out-ok.txt" 2>&1 || rc=$?
  after="$(cat "$CFG2")"
  if [[ "$before" == "$after" ]] && [[ "$rc" -eq 0 ]]; then
    pass "5f: already-correct config left byte-for-byte unchanged (idempotent, rc=0)"
  else
    fail "5f: guard rewrote an already-correct config (rc=$rc) -- churn on every fire"
  fi
  if ls "$GTMP/backups2"/* >/dev/null 2>&1; then
    fail "5g: guard wrote a backup for a config it did not change -- backup dir will grow without bound"
  else
    pass "5g: no backup written when nothing changed"
  fi

  # 5h: FAIL-SAFE on unparseable config -- must NOT overwrite, must NOT exit 0
  # silently pretending success, and must NOT truncate the file.
  CFG3="$GTMP/garbage.json"
  printf '%s\n' '{ this is not json' > "$CFG3"
  before3="$(cat "$CFG3")"
  rc=0
  TOOLSEARCH_GUARD_CONFIG="$CFG3" TOOLSEARCH_GUARD_BACKUP_DIR="$GTMP/backups3" \
    TOOLSEARCH_GUARD_LOG="$GTMP/guard3.log" /bin/bash "$DRIFT_GUARD" >"$GTMP/out-garbage.txt" 2>&1 || rc=$?
  after3="$(cat "$CFG3")"
  if [[ "$before3" == "$after3" ]]; then
    pass "5h: unparseable config left untouched (fail-safe: a guard that cannot READ the config must never WRITE it)"
  else
    fail "5h: guard MODIFIED an unparseable config -- it would destroy a config it could not understand"
  fi
  if [[ "$rc" -ne 0 ]]; then
    pass "5i: unparseable config produced a non-zero exit ($rc) -- the failure is visible, not swallowed"
  else
    fail "5i: unparseable config exited 0 -- a broken config would be reported as healthy"
  fi

  # 5j: MISSING config -- box not provisioned yet. Must not crash or create one.
  CFG4="$GTMP/does-not-exist.json"
  rm -f "$CFG4"
  rc=0
  TOOLSEARCH_GUARD_CONFIG="$CFG4" TOOLSEARCH_GUARD_BACKUP_DIR="$GTMP/backups4" \
    TOOLSEARCH_GUARD_LOG="$GTMP/guard4.log" /bin/bash "$DRIFT_GUARD" >"$GTMP/out-missing.txt" 2>&1 || rc=$?
  if [[ ! -f "$CFG4" ]]; then
    pass "5j: missing config -- guard did not fabricate one (rc=$rc)"
  else
    fail "5j: guard CREATED a config file that did not exist"
  fi

  # 5k: scalar `true` -- the loop-arming shape must be repaired, not preserved.
  CFG5="$GTMP/scalar.json"
  printf '%s\n' '{"tools":{"toolSearch":true}}' > "$CFG5"
  rc=0
  TOOLSEARCH_GUARD_CONFIG="$CFG5" TOOLSEARCH_GUARD_BACKUP_DIR="$GTMP/backups5" \
    TOOLSEARCH_GUARD_LOG="$GTMP/guard5.log" /bin/bash "$DRIFT_GUARD" >"$GTMP/out-scalar.txt" 2>&1 || rc=$?
  got="$(python3 "$READER" "$CFG5" 2>/dev/null || echo "UNREADABLE")"
  if [[ "$got" == "$EXPECTED" ]]; then
    pass "5k: scalar 'true' repaired to $EXPECTED"
  else
    fail "5k: scalar 'true' not repaired -- config reads '$got'"
  fi

  # 5l: MISSING toolSearch key entirely -> installed.
  CFG6="$GTMP/absent.json"
  printf '%s\n' '{"tools":{"exec":{"security":"full"}}}' > "$CFG6"
  rc=0
  TOOLSEARCH_GUARD_CONFIG="$CFG6" TOOLSEARCH_GUARD_BACKUP_DIR="$GTMP/backups6" \
    TOOLSEARCH_GUARD_LOG="$GTMP/guard6.log" /bin/bash "$DRIFT_GUARD" >"$GTMP/out-absent.txt" 2>&1 || rc=$?
  got="$(python3 "$READER" "$CFG6" 2>/dev/null || echo "UNREADABLE")"
  if [[ "$got" == "$EXPECTED" ]]; then
    pass "5l: absent toolSearch key installed as $EXPECTED"
  else
    fail "5l: absent toolSearch key not installed -- config reads '$got'"
  fi
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all toolsearch-directory-shape checks pass"
exit 0
