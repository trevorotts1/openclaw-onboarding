#!/usr/bin/env bash
# 11-run-qc-checklist.sh -- Skill 41. Composes every qc-*.sh gate, tallies PASS/FAIL.
# Resolves its own root dynamically; never hardcodes a path.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "[skill 41 QC] Running QC checklist for $SKILL_ROOT"
# Per-run private temp file (a fixed /tmp/skill41-qc.out is clobbered by concurrent runs).
OUT="$(mktemp 2>/dev/null || mktemp -t skill41-qc)"
trap 'rm -f "$OUT"' EXIT
PASS=0; FAIL=0
for gate in "$SCRIPT_DIR"/qc-*.sh; do
  case "$gate" in *.test.sh) continue ;; esac
  [[ -f "$gate" ]] || continue
  name="$(basename "$gate")"
  if bash "$gate" >"$OUT" 2>&1; then
    echo "  PASS $name"; PASS=$((PASS + 1))
  else
    echo "  FAIL $name"; sed 's/^/      /' "$OUT" | tail -4; FAIL=$((FAIL + 1))
  fi
done
echo "[skill 41 QC] Totals: PASS=$PASS FAIL=$FAIL"
if [[ $FAIL -gt 0 ]]; then echo "[skill 41 QC] Do NOT seal the Run Manifest -- $FAIL gate(s) failed."; exit 1; fi
echo "[skill 41 QC] All gates passed."
exit 0
