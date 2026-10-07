#!/bin/sh
# run_install_rollback.sh — W4-04-U1 clean install / migration / rollback proof.
#
# Runs every family, prints a summary table, exits non-zero on any failure.
# Writes only into tests/install-rollback-proof/{receipts,evidence}/ plus the
# lane log folder and /tmp/<box>-W4-04-U1-* scratch (removed by the tests).
#
# Order matters: the clean install runs first, the migration and rollback
# receipts are written next, and the final release_check re-runs the clean
# install with --require-receipts so a missing receipt fails the run.
set -u
cd "$(dirname "$0")" || exit 2

LANE=/Users/blackceomacmini/drama-song-factory-build/swarm-plans/lanes/W4-04-U1-lane
mkdir -p "$LANE" || exit 2

export BOX_SLUG="${BOX_SLUG:-local}"
export W404_BOX="${W404_BOX:-/tmp/${BOX_SLUG}-W4-04-U1-box}"
rm -rf "$W404_BOX"

pass=0; fail=0; rows=""
record() {
  # $1 label, $2 ok(0/1), $3 detail
  if [ "$2" -eq 0 ]; then
    pass=$((pass+1))
    rows="$rows
  $1  PASS  $3"
  else
    fail=$((fail+1))
    rows="$rows
  $1  FAIL  $3"
  fi
}

for t in test_fresh_install.py test_migration.py test_rollback.py; do
  if [ ! -f "$t" ]; then
    record "$t" 1 "missing"
    continue
  fi
  if python3 "$t" > "$LANE/$t.log" 2>&1; then
    record "$t" 0 "$(tail -1 "$LANE/$t.log")"
  else
    record "$t" 1 "(see $LANE/$t.log)"
  fi
done

# Final gate: clean install again, receipts now mandatory.
if python3 release_check.py --box "$W404_BOX" --require-receipts \
    --receipt receipts/release-check.json \
    > "$LANE/release-check.log" 2>&1; then
  record "release_check --require-receipts" 0 "$(grep -E '^counts:' "$LANE/release-check.log" | tail -1)"
else
  record "release_check --require-receipts" 1 "(see $LANE/release-check.log)"
fi

rm -rf "$W404_BOX"

echo "=== W4-04-U1 install-rollback-proof summary ==="
echo "  file  result  detail$rows"
echo "  pass=$pass fail=$fail"
echo "  receipts: tests/install-rollback-proof/receipts/"
echo "  evidence: tests/install-rollback-proof/evidence/"
echo "  lane logs: $LANE"
[ "$fail" -eq 0 ] || { echo "FAILED: $fail step(s)"; exit 1; }
echo ALL_INSTALL_ROLLBACK_PROOFS_PASS
