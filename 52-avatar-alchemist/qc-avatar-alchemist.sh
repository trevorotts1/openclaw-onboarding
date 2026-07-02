#!/usr/bin/env bash
# qc-avatar-alchemist.sh — CI gate for Skill 52. Manifest↔prompts lockstep (40/40),
# every prover self-test, the negative suite, gate-integrity, tone-core sync, no-Anthropic sweep.
# Tested under bash -c and zsh -c. Exit 0 only when everything is green.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
fail=0
run() { echo "--- $1"; shift; "$@"; if [ $? -ne 0 ]; then echo "  FAIL"; fail=1; else echo "  ok"; fi; }

echo "== deps =="
run "verify-deps" bash "$HERE/verify-deps.sh"

echo "== prover self-tests =="
run "intake-gate --self-test"   python3 "$HERE/scripts/aa_intake_gate.py" --self-test
run "build-check --self-test"   python3 "$HERE/scripts/aa_build_check.py" --self-test
run "delivery-gate --self-test" python3 "$HERE/scripts/aa_delivery_gate.py" --self-test
run "links-gate --self-test"    python3 "$HERE/scripts/aa_links_gate.py" --self-test
run "director --self-test"      python3 "$HERE/scripts/aa_director.py" --self-test
run "package --self-test"       python3 "$HERE/scripts/aa_package.py" --self-test

echo "== negative suite (every gate fails its bad fixture) =="
run "test_aa_preflight"         python3 "$HERE/scripts/test_aa_preflight.py"

echo "== gate integrity + tone-core sync =="
run "gate-integrity --check"    python3 "$HERE/scripts/aa_gate_integrity_check.py" --check
run "tone-core sync"            python3 "$HERE/scripts/verify_tone_core_sync.py"

echo "== manifest ↔ prompts lockstep (40/40) =="
DIRS=$(find "$HERE/prompts" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
if [ "$DIRS" != "40" ]; then echo "  FAIL: $DIRS prompt dirs != 40"; fail=1; else echo "  ok: 40 prompt dirs"; fi

echo "== no usable Anthropic model id baked =="
if grep -REn 'anthropic/[a-z]|claude-sonnet-[0-9]|claude-opus|claude-haiku|claude-[0-9]' "$HERE/prompts" "$HERE"/*.json >/dev/null 2>&1; then
  echo "  FAIL: a usable Anthropic model id is baked"; fail=1
else echo "  ok: zero usable Anthropic ids"; fi

echo "== golden BRAND intake passes; BOOK parks without skill 53 =="
python3 "$HERE/scripts/aa_intake_gate.py" --intake "$HERE/test-fixtures/intake-brand.json" >/dev/null 2>&1 || { echo "  FAIL: brand fixture"; fail=1; }
python3 "$HERE/scripts/aa_intake_gate.py" --intake "$HERE/test-fixtures/intake-book.json" >/dev/null 2>&1 && { echo "  FAIL: book fixture should park"; fail=1; } || echo "  ok: brand passes, book parks"

if [ "$fail" = 0 ]; then echo; echo "QC-AVATAR-ALCHEMIST: ALL GREEN"; else echo; echo "QC-AVATAR-ALCHEMIST: FAILURES ABOVE"; fi
exit "$fail"
