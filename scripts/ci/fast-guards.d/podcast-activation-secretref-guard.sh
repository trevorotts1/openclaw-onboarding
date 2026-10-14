#!/usr/bin/env bash
# NEW GUARD (wave 4, not folded): skill 58's activation guard runs B5 on every
# provisioned box from an arbitrary shell that need not inherit the gateway env.
# B5 now counts an env SecretRef declared anywhere in the box openclaw.json
# ({"source":"env","id":NAME} — labels and pointers only; the gateway resolves
# process.env[id] per request) as SET alongside the process env, and the guard's
# own self-test carries the fixture that proves it. This guard keeps that battery
# WIRED: a check nothing runs is a comment, and an assertion silently dropped
# from the battery still exits 0 — so the assertion name itself is asserted.
set -e
cd "$GITHUB_WORKSPACE"

GUARD="58-podcast-production-engine/scripts/guard-activation-health.py"

# 1. the guard byte-compiles (a syntax error must never read as "no output = fine")
python3 -m py_compile "$GUARD"

# 2. the full self-test battery passes, end to end
OUT="$(python3 "$GUARD" --self-test)"
printf '%s\n' "$OUT" | grep -q "ALL ASSERTIONS PASSED"

# 3. anti-vacuity: the SecretRef-as-SET assertion must be present in the battery.
#    The self-test drives a simulated openclaw.json whose entries carry ONLY
#    {"source":"env","id":...} labels with a bare process env and requires B5 to
#    PASS there; without those declarations the same fixture requires B5 FAIL.
printf '%s\n' "$OUT" | grep -q "B5-config-secretref-counts-as-set"
