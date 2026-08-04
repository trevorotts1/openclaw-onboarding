#!/usr/bin/env bash
# tests/unit/update-skills-u6c-set-e-continuation.test.sh
# ---------------------------------------------------------------------------
# Proves the fix for a live 2026-08 Hostinger VPS finding: a roll aborted with
# exit 7 before reaching ANY skill-38 / MCP / pm2 work.
#
# THE DEFECT UNDER TEST. update-skills.sh's Step U6c captured
# ingest-sop-library.sh's output and exit code as:
#     _U6C_OUT="$(MISSION_CONTROL_DB="$_U6C_DB" bash "$_U6C_INGEST_SH" "$_U6C_SLUG" 2>&1)"; _U6C_RC=$?
# Under `set -euo pipefail` (active at update-skills.sh L128) that is a
# command-substitution ASSIGNMENT followed by a SEPARATE statement (`;`). A
# failing assignment aborts the script the instant the substitution returns
# non-zero -- `_U6C_RC=$?` is never even reached. Step U6c's own contract
# ("FAILS LOUD... latches _U6C_SOPLIB_FAIL... [run] exits 1 via the
# content-completeness gate below") requires the run to LATCH the failure and
# CONTINUE through every remaining phase (skill-38, MCP, pm2, the stamp
# write) so the final exit code still reflects it. The old code could not do
# that: it died on the spot, mid-phase, for ANY ingest-sop-library.sh failure
# -- including the false-negative one shipped alongside this fix (DEFECT 1).
#
# THE FIX. `if _U6C_OUT="$(...)"; then _U6C_RC=0; else _U6C_RC=$?; fi` -- the
# assignment is now the TESTED CONDITION of an `if`, which `set -e` never
# aborts on. Same idiom this file already ships for the sibling U6c2 capture
# and the R4 runtime-conformance verdict.
#
# METHOD. Like tests/unit/sop-embeddings-independent-gate.test.sh, this does
# NOT reimplement the block: it extracts the real U6c block VERBATIM from
# update-skills.sh between the U6C-SOP-LIBRARY markers and sources it. If
# those markers drift or vanish the suite fails loudly (exit 2) rather than
# silently testing nothing. A synthetic "PRE-FIX" variant is then rebuilt
# from the extracted text by mechanically re-introducing the exact buggy
# one-liner, proving this test would have caught the live incident (the 2.1
# "test that would fail against the pre-fix tree" law this repo's other
# guards already follow).
#
# FULLY OFFLINE. ingest-sop-library.sh itself is never invoked -- a fake
# stand-in under our control plays its role (success / failure), so nothing
# here touches the network or a real box.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
RESOLVE_DB_PY="$REPO_ROOT/shared-utils/resolve_db.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }
[ -f "$RESOLVE_DB_PY" ] || { echo "FATAL: $RESOLVE_DB_PY not found"; exit 2; }

WORK="$(mktemp -d -t u6c-set-e-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# --- verbatim extraction between markers, mirroring sop-embeddings-independent-gate.test.sh
extract_block() {
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1; next }
    index($0, e) { p=0 }
    p { print }
  ' "$UPDATER"
}
extract_block "U6C-SOP-LIBRARY" > "$WORK/u6c.inc"
if [ ! -s "$WORK/u6c.inc" ]; then
  echo "FATAL: marker block 'U6C-SOP-LIBRARY' not found in update-skills.sh (marker drift?)"
  exit 2
fi
{
  echo 'u6c_block() {'
  cat "$WORK/u6c.inc"
  echo '}'
} > "$WORK/u6c-fixed.sh"
bash -n "$WORK/u6c-fixed.sh" || { echo "FATAL: extracted U6c block does not parse"; exit 2; }

echo "== static: U6c is wired into update-skills.sh =="
grep -q "Step U6c: SOP V2 library population check" "$UPDATER" \
  && ok "update-skills.sh contains Step U6c" || bad "Step U6c missing from update-skills.sh"

echo ""
echo "== static: the extracted block no longer carries the set -e trap =="
# The exact pre-fix shape: a command-substitution ASSIGNMENT immediately
# followed by `; ...RC=$?` as a SEPARATE statement (not the tested condition
# of an if/&&/||). This is the literal pattern that killed the roll. Comment
# lines are excluded first -- the fix's own explanatory comment quotes that
# exact pre-fix shape as documentation, which is not a live code instance.
if grep -vE '^\s*#' "$WORK/u6c.inc" | grep -qE '="\$\([^)]*\)"[[:space:]]*;[[:space:]]*_[A-Za-z0-9_]*_RC=\$\?'; then
  bad "extracted block STILL contains the unguarded assign-then-capture set -e trap"
else
  ok "extracted block contains no unguarded 'VAR=\"\$(...)\"; RC=\$?' capture"
fi
if grep -qE 'if _U6C_OUT="\$\(' "$WORK/u6c.inc" && grep -qE '^\s*else\s*$' "$WORK/u6c.inc"; then
  ok "extracted block uses the set -e SAFE 'if VAR=\"\$(...)\"; then RC=0; else RC=\$?; fi' idiom"
else
  bad "extracted block does not use the safe if/then/else capture idiom"
fi

# --- fixture builders ------------------------------------------------------
make_db() {  # make_db <path> <starting_row_count>
  python3 - "$1" "$2" <<'PYEOF'
import sqlite3, sys
db, n = sys.argv[1], int(sys.argv[2])
con = sqlite3.connect(db)
con.execute("CREATE TABLE sops (id TEXT PRIMARY KEY)")
for i in range(n):
    con.execute("INSERT INTO sops (id) VALUES (?)", (f"starter_{i}",))
con.commit(); con.close()
PYEOF
}

count_rows() {
  python3 -c "
import sqlite3
con = sqlite3.connect('$1')
print(con.execute('SELECT COUNT(*) FROM sops').fetchone()[0])
"
}

make_fake_ingest_fail() {  # writes a fake ingest-sop-library.sh that FAILS, DB untouched
  cat > "$1" <<'FAKE'
#!/usr/bin/env bash
echo "[fake-ingest] simulated COMPONENT FAILURE — DB left untouched" >&2
exit 7
FAKE
  chmod +x "$1"
}

make_fake_ingest_ok() {  # writes a fake ingest-sop-library.sh that SUCCEEDS, reaches canonical
  cat > "$1" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
python3 -c "
import sqlite3, os
con = sqlite3.connect(os.environ['MISSION_CONTROL_DB'])
for i in range(20):
    con.execute('INSERT OR IGNORE INTO sops (id) VALUES (?)', (f'lib_{i}',))
con.commit(); con.close()
"
echo "[fake-ingest] simulated success"
exit 0
FAKE
  chmod +x "$1"
}

make_manifest() {  # make_manifest <path> <canonical_count>
  cat > "$1" <<EOF
{"canonical_sop_count": $2}
EOF
}

# run_block <block_script> <ingest_script> <starting_rows> <canonical>
# Runs the (possibly mutated) u6c_block under set -euo pipefail — the SAME
# flags active in the real update-skills.sh at L128 — and proves whether
# execution survives past the ingest call. Prints a machine-parseable report:
#   REACHED_END=<0|1>   -- did the subshell run to completion (never aborted)?
#   SOPLIB_FAIL=<0|1|unset> -- the latched failure flag's final value
#   BLOCK_RC=<n>        -- the subshell's own exit status
run_block() {
  local block_script="$1" ingest_script="$2" starting_rows="$3" canonical="$4"
  local d="$WORK/run-$$-$RANDOM"
  mkdir -p "$d/skills/32-command-center-setup/scripts" \
           "$d/skills/shared-utils/sop-library" \
           "$d/skills/shared-utils"
  make_db "$d/mission-control.db" "$starting_rows"
  cp "$ingest_script" "$d/skills/32-command-center-setup/scripts/ingest-sop-library.sh"
  make_manifest "$d/skills/shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json" "$canonical"
  cp "$RESOLVE_DB_PY" "$d/skills/shared-utils/resolve_db.py"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$block_script"
    SKILLS_DIR="$d/skills"
    EXTRACTED_DIR="$d/skills"
    OC_WORKSPACE_DEFAULT="$d/workspace-unused"
    LOG_FILE="$d/log.txt"
    DASHBOARD_DB_PATH="$d/mission-control.db"
    export DASHBOARD_DB_PATH
    : > "$LOG_FILE"
    u6c_block
    echo "REACHED_END=1"
    echo "SOPLIB_FAIL=${_U6C_SOPLIB_FAIL:-unset}"
  ) > "$d/report.txt" 2>"$d/stderr.txt"
  echo "$?" > "$d/rc.txt"
  echo "$d"
}

echo ""
echo "== (1) FIXED block: a component failure LATCHES and the run CONTINUES to completion =="
make_fake_ingest_fail "$WORK/fake-fail.sh"
D1="$(run_block "$WORK/u6c-fixed.sh" "$WORK/fake-fail.sh" 1 5)"
RC1="$(cat "$D1/rc.txt")"
[ "$RC1" = "0" ] && ok "(1) subshell itself exits 0 (u6c_block returning does not kill the caller)" \
  || { bad "(1) subshell exited $RC1 (should complete, not abort)"; sed 's/^/      /' "$D1/stderr.txt"; }
grep -q "^REACHED_END=1$" "$D1/report.txt" \
  && ok "(1) execution reached PAST the ingest call and printed the post-block sentinel — did NOT abort" \
  || { bad "(1) execution never reached past the ingest call — set -e killed it (the live incident)"; sed 's/^/      /' "$D1/stderr.txt"; }
grep -q "^SOPLIB_FAIL=1$" "$D1/report.txt" \
  && ok "(1) the component failure was LATCHED into _U6C_SOPLIB_FAIL=1 (not silently dropped)" \
  || bad "(1) _U6C_SOPLIB_FAIL was not latched to 1"
grep -q "SOP library ingest FAILED" "$D1/report.txt" \
  && ok "(1) failure is reported LOUD, by name" || bad "(1) no loud failure message"

echo ""
echo "== (2) FIXED block: an all-clean component completes and latches NO failure (exit 0 path) =="
make_fake_ingest_ok "$WORK/fake-ok.sh"
D2="$(run_block "$WORK/u6c-fixed.sh" "$WORK/fake-ok.sh" 1 5)"
RC2="$(cat "$D2/rc.txt")"
[ "$RC2" = "0" ] && ok "(2) subshell exits 0" || { bad "(2) subshell exited $RC2"; sed 's/^/      /' "$D2/stderr.txt"; }
grep -q "^REACHED_END=1$" "$D2/report.txt" && ok "(2) execution reached the end" || bad "(2) never reached the end"
grep -q "^SOPLIB_FAIL=0$" "$D2/report.txt" \
  && ok "(2) all-clean: _U6C_SOPLIB_FAIL stays 0" || bad "(2) all-clean run unexpectedly latched a failure"
grep -q "SOP library populated" "$D2/report.txt" \
  && ok "(2) success is reported explicitly" || bad "(2) no success message"

echo ""
echo "== (3) NEGATIVE CONTROL: rebuilding the PRE-FIX one-liner reproduces the live abort =="
# Mechanically reconstruct the exact pre-fix shape from the extracted (fixed)
# text: collapse the `if VAR="$(...)"; then RC=0; else RC=$?; fi` idiom back
# into the single `VAR="$(...)"; RC=$?` statement that shipped the night of
# the incident. If this control did NOT reproduce the abort, tests (1)/(2)
# above would prove nothing (they could pass against ANY block, buggy or not).
python3 - "$WORK/u6c.inc" "$WORK/u6c-prefix.inc" <<'PYEOF'
import re, sys
src = open(sys.argv[1]).read()
pattern = re.compile(
    r'if _U6C_OUT="\$\(MISSION_CONTROL_DB="\$_U6C_DB" bash "\$_U6C_INGEST_SH" "\$_U6C_SLUG" 2>&1\)"; then\n'
    r'\s*_U6C_RC=0\n'
    r'\s*else\n'
    r'\s*_U6C_RC=\$\?\n'
    r'\s*fi\n'
)
replacement = (
    '_U6C_OUT="$(MISSION_CONTROL_DB="$_U6C_DB" bash "$_U6C_INGEST_SH" "$_U6C_SLUG" 2>&1)"; _U6C_RC=$?\n'
)
out, n = pattern.subn(replacement, src)
if n != 1:
    print(f"FATAL: expected exactly 1 substitution, made {n} — the fixed idiom's exact shape drifted", file=sys.stderr)
    sys.exit(1)
open(sys.argv[2], "w").write(out)
PYEOF
if [ "$?" -ne 0 ] || [ ! -s "$WORK/u6c-prefix.inc" ]; then
  bad "(3) could not mechanically rebuild the pre-fix block (see FATAL above) — negative control SKIPPED"
else
  ok "(3) mechanically rebuilt the exact pre-fix one-liner from the current (fixed) source"
  if grep -qE '="\$\([^)]*\)"[[:space:]]*;[[:space:]]*_U6C_RC=\$\?' "$WORK/u6c-prefix.inc"; then
    ok "(3) rebuilt pre-fix block contains the unguarded assign-then-capture pattern"
  else
    bad "(3) rebuilt pre-fix block does not contain the expected buggy pattern — rebuild is wrong"
  fi
  {
    echo 'u6c_block() {'
    cat "$WORK/u6c-prefix.inc"
    echo '}'
  } > "$WORK/u6c-prefix.sh"
  bash -n "$WORK/u6c-prefix.sh" || { bad "(3) rebuilt pre-fix block does not parse"; }

  D3="$(run_block "$WORK/u6c-prefix.sh" "$WORK/fake-fail.sh" 1 5)"
  RC3="$(cat "$D3/rc.txt")"
  if grep -q "^REACHED_END=1$" "$D3/report.txt"; then
    bad "(3) NEGATIVE CONTROL FAILED TO REPRODUCE: pre-fix block reached the end anyway (rc=$RC3) — this test would not have caught the live incident"
  else
    ok "(3) NEGATIVE CONTROL CONFIRMED: the pre-fix block ABORTS mid-phase under set -e (rc=$RC3, sentinel never printed) — exactly the live incident, and exactly what tests (1)/(2) prove the fix no longer does"
  fi
  [ "$RC3" != "0" ] && ok "(3) pre-fix block's subshell exit code is non-zero ($RC3), confirming a hard abort, not a clean return" \
    || bad "(3) pre-fix block's subshell exited 0 — expected a set -e abort"
fi

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
