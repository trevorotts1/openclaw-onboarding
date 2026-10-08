#!/usr/bin/env bash
# Manual 02 B6 static check — no operator/build-workspace paths in core code.
#
# Fails when any non-test file under 75-drama-song-ad-factory/scripts/core/
# (paths not matching test_*.py) contains:
#   • 'Downloads'
#   • 'drama-song-factory-build'
#   • the path-like occurrence 'openclaw-onboarding/'
#
# Why. B3/B6: the operator Mac is a contaminated test bed — code in
# scripts/core/ looked into ~/Downloads and the build workspace, so the
# green suite on that box proved nothing about a client box. The C3 unit
# removed the operator-home defaults; this guard keeps them out: any
# reintroduction of an operator path as a load-bearing search root is a red
# build, not a silent pass. test_*.py files are exempt (they plant the
# needles at run time to prove the ban bites); generated __pycache__ is
# skipped; binary-ish files are skipped (grep -I).
#
# Fails closed: no scanned files found == fail (a moved/deleted tree must
# not produce a green check). Stdlib-only bash; no network; no writes.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$SKILL_DIR/scripts/core"

if [ ! -d "$CORE" ]; then
  echo "operator-path-leak: FAIL — scripts/core/ not found at $CORE (fail closed)"
  exit 2
fi

# Collect non-test files: everything except test_*.py, __pycache__, .pyc.
mapfile -t FILES < <(
  find "$CORE" -type f \
    ! -name 'test_*.py' ! -name '*.pyc' \
    ! -path '*/__pycache__/*' -print
)

if [ "${#FILES[@]}" -eq 0 ] || [ -z "${FILES[0]}" ]; then
  echo "operator-path-leak: FAIL — no non-test files found under scripts/core/ (fail closed)"
  exit 2
fi

offenders=0
for f in "${FILES[@]}"; do
  # -I: skip binary files. The three needles, verbatim as the manual words
  # them: 'Downloads', 'drama-song-factory-build', path-like
  # 'openclaw-onboarding/'.
  if grep -Iqn -e 'Downloads' -e 'drama-song-factory-build' -e 'openclaw-onboarding/' -- "$f"; then
    if [ "$offenders" -eq 0 ]; then
      echo "operator-path-leak: FAIL — operator/build-workspace path string(s) in non-test core file(s):"
    fi
    echo "  $f"
    grep -In -e 'Downloads' -e 'drama-song-factory-build' -e 'openclaw-onboarding/' -- "$f" | sed 's/^/      /'
    offenders=$((offenders + 1))
  fi
done

if [ "$offenders" -gt 0 ]; then
  echo "operator-path-leak: $offenders offending file(s) — remove the operator path(s); resolve dependencies as install-time data, never an operator-box literal"
  exit 1
fi

n="${#FILES[@]}"
echo "operator-path-leak: clean — scanned $n non-test file(s) under scripts/core/, zero operator/build-workspace path strings"
exit 0