#!/usr/bin/env bash
# testsweep.sh — run every test_*.py under 75-drama-song-ad-factory in a repo
# root and print one PASS|FAIL|TIMEOUT line per suite, then SUMMARY.
# Usage: testsweep.sh <repo-root>
# Capture mode (exit 0 always): used to record the baseline. gate.sh compares
# two sweeps. One instrument for baseline and gate — no drift between them.
set -u
ROOT="${1:?testsweep.sh <repo-root>}"
cd "$ROOT/75-drama-song-ad-factory" || { echo "SWEEP-ERROR no 75-drama-song-ad-factory in $ROOT"; exit 2; }
pass=0; fail=0; timeout=0
while IFS= read -r f; do
  # < /dev/null: a suite that reads stdin must never eat the find pipe (that
  # corrupted two lines mid-path and faked suite verdicts; caught 2026-10-22).
  if perl -e 'alarm 120; exec @ARGV' python3 "$f" >/dev/null 2>&1 </dev/null; then
    echo "PASS $f"; pass=$((pass+1))
  else
    rc=$?
    if [ "$rc" -eq 142 ] || [ "$rc" -eq 143 ]; then echo "TIMEOUT $f"; timeout=$((timeout+1))
    else echo "FAIL $f"; fail=$((fail+1)); fi
  fi
done < <(find . -name 'test_*.py' | sort)
echo "SUMMARY pass=$pass fail=$fail timeout=$timeout"
exit 0
