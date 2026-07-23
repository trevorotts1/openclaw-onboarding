#!/usr/bin/env bash
set -euo pipefail
G="scripts/qc-assert-version-markers-agree.sh"; T=""; F=0
cleanup() { [ -n "$T" ] && rm -rf "$T"; }; trap cleanup EXIT
echo "=== Test 1: bash -n ==="; bash -n "$G" || { echo FAIL; F=$((F+1)); }; echo "  PASS"
echo "=== Test 2: self-test ==="; bash "$G" --self-test >/dev/null 2>&1 || { echo FAIL; F=$((F+1)); }; echo "  PASS"
echo "=== Test 3: Mutation ==="
T="$(mktemp -d)"; cp "$G" "$T/g.sh"; chmod +x "$T/g.sh"
mkdir -p "$T/f/99-t"; printf '1.0.0\n' > "$T/f/99-t/skill-version.txt"
printf -- '---\nname:t\nversion:1.0.0\n---\n' > "$T/f/99-t/SKILL.md"
printf '# QC\n**Version:** v1.0.0\n' > "$T/f/99-t/QC.md"
printf '# CHANGELOG\n## v1.0.0\n' > "$T/f/99-t/CHANGELOG.md"
bash "$T/g.sh" --root "$T/f" >/dev/null 2>&1 || { echo "FAIL: clean"; F=$((F+1)); }
printf '1.0.1\n' > "$T/f/99-t/skill-version.txt"
bash "$T/g.sh" --root "$T/f" >/dev/null 2>&1 && { echo "FAIL: mutation"; F=$((F+1)); }
printf '1.0.0\n' > "$T/f/99-t/skill-version.txt"
bash "$T/g.sh" --root "$T/f" >/dev/null 2>&1 || { echo "FAIL: restore"; F=$((F+1)); }
echo "  PASS"
[ "$F" -eq 0 ] && { echo "ALL TESTS PASS"; exit 0; } || { echo "FAILURES: $F"; exit 1; }
