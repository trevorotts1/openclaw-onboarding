#!/usr/bin/env bash
# tests/unit/u052-department-doc-validation.test.sh
# Validates DEPARTMENTS.md canonical IDs match department-naming-map.json.
# Mutation-proof. Exit 0 = GREEN. Exit 1 = RED.
set -euo pipefail
R='\033[0;31m'; G='\033[0;32m'; N='\033[0m'
RR="$(cd "$(dirname "$0")/../.." && pwd)"
DM="${RR}/23-ai-workforce-blueprint/DEPARTMENTS.md"
NM="${RR}/23-ai-workforce-blueprint/department-naming-map.json"
MT=false; MID="marketing"; Q=false
while [[ $# -gt 0 ]]; do case "$1" in --mutation-test) MT=true; shift ;; --mutate-id) MID="$2"; shift 2 ;; --quiet) Q=true; shift ;; *) echo "Unknown: $1">&2; exit 2 ;; esac; done
F=0
p(){ [[ "$Q" != "true" ]] && echo -e "${G}PASS${N} $1"; }
fl(){ echo -e "${R}FAIL${N} $1"; F=1; }
[[ ! -f "$DM" ]] && echo "ERROR: DEPARTMENTS.md not found">&2 && exit 2
[[ ! -f "$NM" ]] && echo "ERROR: naming map not found">&2 && exit 2
if python3 "$RR/scripts/qc-validate-department-docs.py" --departments-md "$DM" --naming-map "$NM" --quiet 2>/dev/null; then
  p "qc-validate-department-docs.py: DEPARTMENTS.md matches naming map"
else
  out=$(python3 "$RR/scripts/qc-validate-department-docs.py" --departments-md "$DM" --naming-map "$NM" 2>&1 || true)
  fl "qc-validate-department-docs.py: MISMATCH"; echo "$out">&2
fi
if [[ "$MT" == "true" ]]; then
  TMP="$(mktemp /tmp/u052m.XXXXXX.md)"; trap "rm -f $TMP" EXIT; cp "$DM" "$TMP"
  if [[ "$(uname)" == "Darwin" ]]; then sed -i '' "s/${MID}/FAB-${MID}/g" "$TMP"; else sed -i "s/${MID}/FAB-${MID}/g" "$TMP"; fi
  if python3 "$RR/scripts/qc-validate-department-docs.py" --departments-md "$TMP" --naming-map "$NM" --quiet 2>/dev/null; then
    fl "MUTATION: mutated doc unexpectedly PASSED"
  else p "MUTATION: mutated doc FAILED validation (RED)"; fi
  if python3 "$RR/scripts/qc-validate-department-docs.py" --departments-md "$DM" --naming-map "$NM" --quiet 2>/dev/null; then
    p "MUTATION: reverted doc PASSES validation (GREEN)"
  else fl "MUTATION: reverted doc FAILED"; fi
  rm -f "$TMP"; trap - EXIT
fi
echo ""; if [[ "$F" -eq 0 ]]; then echo -e "${G}=== ALL CHECKS PASSED (GREEN) ===${N}"; exit 0; else echo -e "${R}=== ${F} CHECK(S) FAILED (RED) ===${N}"; exit 1; fi
