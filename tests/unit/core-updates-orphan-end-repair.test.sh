#!/usr/bin/env bash
# core-updates-orphan-end-repair.test.sh
#
# Regression guard for the orphan-END self-heal in update-skills.sh's
# CORE_UPDATES merge.
#
# THE BUG. The merge's idempotency guard only tests for the BEGIN marker:
#     if begin_marker in existing: continue
# so a block whose BEGIN was lost — an interrupted write, an external edit, a
# summariser — is invisible to it. The stray END is never detected and never
# repaired, and it stays orphaned forever.
#
# WHY IT MATTERS. Measured on real fleet data 2026-07-31: three of four sampled
# boxes carried the SAME orphan (`16-summarize-youtube:agents  BEGIN=0 END=1`).
# Every BEGIN/END pair-balance check on those boxes fails, and
# scripts/dedup-agents-md.py refuses to worsen wiring — so those boxes also
# never got their duplicate blocks cleaned. One stray line blocked the whole
# self-heal path.
#
# CONTRACT UNDER TEST
#   1. END present + BEGIN absent  -> orphan removed, then a clean pair appended
#      (net: exactly one BEGIN and one END, file balanced).
#   2. A MATCHED pair is never touched (idempotent skip, no duplicate append).
#   3. A different skill's markers are never touched (narrow scoping).
#
# Mirrors the shipped logic rather than invoking update-skills.sh (which would
# need a full box). If the shipped logic changes, this must change with it.

set -uo pipefail

PASS=0
FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The shipped repair+append logic, extracted verbatim in behaviour.
run_merge() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys
target_file, skill_folder, target = sys.argv[1], sys.argv[2], sys.argv[3]
begin_marker = f'<!-- BEGIN skill:{skill_folder}:{target} -->'
end_marker   = f'<!-- END skill:{skill_folder}:{target} -->'
block = 'BLOCK BODY'
try:
    existing = open(target_file, encoding='utf-8', errors='replace').read()
except Exception:
    existing = ''
if begin_marker in existing:
    sys.exit(0)                     # already merged — skip
if end_marker in existing:          # orphan END -> repair before appending
    repaired = existing.replace(end_marker + '\n', '').replace(end_marker, '')
    open(target_file, 'w', encoding='utf-8').write(repaired)
with open(target_file, 'a', encoding='utf-8') as fh:
    fh.write(f'\n\n{begin_marker}\n'); fh.write(block); fh.write(f'\n{end_marker}\n')
PY
}

# NOTE: `grep -c` prints 0 AND exits 1 on no-match, so `|| echo 0` would emit
# "0\n0" and break the arithmetic tests. Swallow the exit code only.
count() { grep -cF "$2" "$1" 2>/dev/null || true; }

echo "-- (1) orphan END is repaired, then a clean pair is written --"
F1="$WORK/orphan.md"
printf '# AGENTS.md\n\nSome content.\n\n<!-- END skill:16-summarize-youtube:agents -->\n\nMore content.\n' > "$F1"
[ "$(count "$F1" '<!-- END skill:16-summarize-youtube:agents -->')" -eq 1 ] \
  && [ "$(count "$F1" '<!-- BEGIN skill:16-summarize-youtube:agents -->')" -eq 0 ] \
  && ok "(1) fixture starts orphaned (BEGIN=0 END=1)" || bad "(1) fixture setup"
run_merge "$F1" 16-summarize-youtube agents
B1=$(count "$F1" '<!-- BEGIN skill:16-summarize-youtube:agents -->')
E1=$(count "$F1" '<!-- END skill:16-summarize-youtube:agents -->')
[ "$B1" -eq 1 ] && ok "(1) exactly one BEGIN after repair" || bad "(1) exactly one BEGIN after repair (got $B1)"
[ "$E1" -eq 1 ] && ok "(1) exactly one END after repair (orphan removed)" || bad "(1) exactly one END after repair (got $E1)"
grep -q 'Some content.' "$F1" && grep -q 'More content.' "$F1" \
  && ok "(1) surrounding content preserved" || bad "(1) surrounding content preserved"

echo "-- (2) a matched pair is left alone (no duplicate append) --"
F2="$WORK/matched.md"
printf '# AGENTS.md\n\n<!-- BEGIN skill:16-summarize-youtube:agents -->\nBLOCK BODY\n<!-- END skill:16-summarize-youtube:agents -->\n' > "$F2"
cp "$F2" "$WORK/matched-before.md"
run_merge "$F2" 16-summarize-youtube agents
if cmp -s "$F2" "$WORK/matched-before.md"; then
  ok "(2) matched pair untouched (byte-identical)"
else
  bad "(2) matched pair untouched (file changed)"
fi

echo "-- (3) another skill's markers are never touched --"
F3="$WORK/other.md"
printf '# AGENTS.md\n\n<!-- END skill:99-other-skill:agents -->\n' > "$F3"
run_merge "$F3" 16-summarize-youtube agents
[ "$(count "$F3" '<!-- END skill:99-other-skill:agents -->')" -eq 1 ] \
  && ok "(3) unrelated skill's orphan left intact" || bad "(3) unrelated skill's orphan left intact"
[ "$(count "$F3" '<!-- BEGIN skill:16-summarize-youtube:agents -->')" -eq 1 ] \
  && ok "(3) own pair still appended" || bad "(3) own pair still appended"

echo ""
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
