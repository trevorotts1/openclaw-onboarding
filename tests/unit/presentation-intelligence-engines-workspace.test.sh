#!/usr/bin/env bash
# tests/unit/presentation-intelligence-engines-workspace.test.sh
#
# U86 [GK-24] — Reproduce + fix the on-box presentation Python breakage by
# root-cause class (stale content / deps preflight / --workspace flag).
#
# ROOT CAUSE (workspace-path defect, VERIFIED-BY-EXECUTION): 23-ai-workforce-
# blueprint/templates/role-library/presentations/scripts/intelligence_engines_
# check.py is a standalone CLI a QC specialist runs BY HAND, from wherever
# their shell happens to be (its own docstring: "invoked by the QC specialists
# at the 8.5 gate"). Before this fix its main() defaulted a missing RUN_DIR
# argument to a bare `Path("working")`, resolved against the CALLER's cwd. If
# an unrelated deck's run dir happened to sit there, the script silently
# graded THAT deck and reported a verdict with zero indication it read the
# wrong directory — the identical bare command, run from two different cwds,
# silently flips PASS/FAIL for two different decks.
#
# THE FIX: an explicit --run-dir/--workspace flag and an OC_DECK_WORKSPACE env
# override, in front of the historical CWD-relative default (kept, never a
# breaking change) — and every invocation now reports run_dir_resolved +
# run_dir_source (JSON) or a loud stderr NOTE (text) so the ambiguity can never
# be silent again. build_deck.py / phase_verifiers.py are unaffected: they
# call check_copy()/check_prompts() directly with an explicit run_dir and
# never go through this CLI default (asserted below, statically).
#
# This guard proves:
#   (A) --run-dir / --workspace / a positional RUN_DIR / OC_DECK_WORKSPACE all
#       resolve to the NAMED directory regardless of the caller's actual cwd,
#   (B) the ORIGINAL bug scenario — no RUN_DIR given, cwd holds an unrelated
#       deck's working/ — now surfaces run_dir_source=="implicit_cwd_default"
#       and the ACTUAL resolved path in both --json and human output, plus a
#       loud stderr NOTE, so the wrong-workspace read is detectable instead of
#       silent,
#   (C) a missing/nonexistent --run-dir value fails LOUD with a FATAL message
#       (never a Python traceback),
#   (D) the script remains read-only (no write_text/open(...'w'...)/mkdir call
#       anywhere in its source) — the defect class here is a silent WRONG READ,
#       never data corruption,
#   (E) build_deck.py and phase_verifiers.py — the ONLY canonical-render-path
#       callers — invoke check_copy()/check_prompts() with an explicit run_dir,
#       so the fix is additive: the canonical render path never touched the
#       buggy CLI default before or after this fix.
#
# EXIT CODES: 0 all pass; 1 one or more assertions failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/intelligence_engines_check.py"
BUILD_DECK="$ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py"
PHASE_VERIFIERS="$ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py"
PY="${PYTHON:-python3}"

PASS=0
FAIL=0
pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

[ -f "$SCRIPT" ] || { echo "FATAL: intelligence_engines_check.py not found at $SCRIPT" >&2; exit 1; }

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# Deck A: the deck the caller actually means to check — a copy set that PASSES
# every copy-beat engine (villain + felt-stakes present and correctly ordered).
DECK_A="$TMPDIR_TEST/deckA"
mkdir -p "$DECK_A/working/copy"
cat > "$DECK_A/working/copy/slides_copy.md" <<'EOF'
SLIDE 1
The broken old system is the real villain here, quietly stealing your time for years.

SLIDE 2
Every day you wait it will cost you 40,000 dollars in lost revenue.

SLIDE 3
Here is the hero of this story: the new way forward.
EOF

# Deck B: an UNRELATED deck sitting at the caller's actual shell cwd, with its
# OWN working/ dir and copy that TRIPS both copy-beat engines.
DECK_B_CWD="$TMPDIR_TEST/deckB-alien-cwd"
mkdir -p "$DECK_B_CWD/working/copy"
cat > "$DECK_B_CWD/working/copy/slides_copy.md" <<'EOF'
SLIDE 1
This slide describes our product features in plain marketing language for a
general audience, nothing more.
EOF

echo "--- (A) explicit resolution sources all reach deck A regardless of cwd ---"

OUT="$(cd "$DECK_B_CWD" && "$PY" "$SCRIPT" --run-dir "$DECK_A/working" --phase copy --json)"
if echo "$OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['ok'] is True and d['run_dir_source']=='flag' else 1)"; then
    pass "--run-dir from an alien cwd resolves to deck A (ok=true, source=flag)"
else
    fail "--run-dir from an alien cwd did not resolve to deck A: $OUT"
fi

OUT="$(cd "$DECK_B_CWD" && "$PY" "$SCRIPT" --workspace "$DECK_A/working" --phase copy --json)"
if echo "$OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['ok'] is True and d['run_dir_source']=='flag' else 1)"; then
    pass "--workspace alias resolves to deck A the same way"
else
    fail "--workspace alias did not resolve to deck A: $OUT"
fi

OUT="$(cd "$DECK_B_CWD" && OC_DECK_WORKSPACE="$DECK_A/working" "$PY" "$SCRIPT" --phase copy --json)"
if echo "$OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['ok'] is True and d['run_dir_source']=='env:OC_DECK_WORKSPACE' else 1)"; then
    pass "OC_DECK_WORKSPACE env override resolves to deck A from an alien cwd"
else
    fail "OC_DECK_WORKSPACE env override did not resolve to deck A: $OUT"
fi

OUT="$(cd /tmp && "$PY" "$SCRIPT" "$DECK_A/working" --phase copy --json)"
if echo "$OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['ok'] is True and d['run_dir_source']=='positional' else 1)"; then
    pass "positional RUN_DIR (back-compat) still resolves to deck A"
else
    fail "positional RUN_DIR did not resolve to deck A: $OUT"
fi

echo "--- (B) the ORIGINAL bug scenario: no RUN_DIR given, cwd = deck B ---"

OUT="$(cd "$DECK_B_CWD" && "$PY" "$SCRIPT" --phase copy --json 2>"$TMPDIR_TEST/stderr.log")"
# pwd -P (physical path, symlinks resolved) to match Path.resolve()'s realpath
# semantics on macOS, where /tmp and /var are themselves symlinks into /private.
EXPECT_PATH="$(cd "$DECK_B_CWD" && pwd -P)/working"
if echo "$OUT" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
assert d['run_dir_source'] == 'implicit_cwd_default', d['run_dir_source']
assert d['run_dir_resolved'] == '$EXPECT_PATH', d['run_dir_resolved']
assert d['ok'] is False
codes = {p['code'] for p in d['triggered']}
assert 'AF-NO-VILLAIN' in codes and 'AF-NO-FELT-STAKES' in codes, codes
"; then
    pass "no-RUN_DIR call reports run_dir_source=implicit_cwd_default + the ACTUAL (deck B) path read, not silently deck A"
else
    fail "no-RUN_DIR call did not report accurate provenance: $OUT"
fi

if grep -q "no RUN_DIR given" "$TMPDIR_TEST/stderr.log" && grep -q "$EXPECT_PATH" "$TMPDIR_TEST/stderr.log"; then
    pass "a loud stderr NOTE names the ambiguity and the actual resolved path"
else
    fail "no stderr NOTE naming the ambiguity/resolved path (found: $(cat "$TMPDIR_TEST/stderr.log"))"
fi

# Human-readable (non-JSON) path also states the resolved dir + source.
TXT_OUT="$(cd "$DECK_B_CWD" && "$PY" "$SCRIPT" --phase copy 2>/dev/null)"
if echo "$TXT_OUT" | grep -q "resolved via implicit_cwd_default"; then
    pass "human-readable output also states the resolution source"
else
    fail "human-readable output did not state the resolution source: $TXT_OUT"
fi

echo "--- (C) fail-honest on a bad --run-dir (never a Python traceback) ---"

ERR="$("$PY" "$SCRIPT" --run-dir 2>&1)"; RC=$?
if [ "$RC" -ne 0 ] && echo "$ERR" | grep -q "FATAL" && ! echo "$ERR" | grep -qi "traceback"; then
    pass "missing --run-dir value fails loud (FATAL, exit $RC, no traceback)"
else
    fail "missing --run-dir value did not fail honestly (exit=$RC): $ERR"
fi

ERR="$("$PY" "$SCRIPT" --run-dir /no/such/deck/dir/at/all --phase copy 2>&1)"; RC=$?
if [ "$RC" -ne 0 ] && echo "$ERR" | grep -q "FATAL" && echo "$ERR" | grep -q "resolved via flag" && ! echo "$ERR" | grep -qi "traceback"; then
    pass "nonexistent --run-dir target fails loud, names its resolution source, no traceback"
else
    fail "nonexistent --run-dir target did not fail honestly (exit=$RC): $ERR"
fi

echo "--- (D) the script stays read-only (the defect is a silent wrong READ, never a write) ---"

if grep -qE "\.write_text\(|open\([^)]*['\"]w['\"]|os\.makedirs|\.mkdir\(" "$SCRIPT"; then
    fail "intelligence_engines_check.py now contains a write/mkdir call — the workspace-path fix must stay read-only"
else
    pass "intelligence_engines_check.py contains no write/mkdir call (read-only preserved)"
fi

echo "--- (E) the canonical render path never goes through the CLI default ---"

if grep -q "iec.check_copy(" "$BUILD_DECK" || grep -q "iec\.check_prompts(" "$BUILD_DECK"; then
    pass "build_deck.py calls check_copy()/check_prompts() directly (not the CLI default)"
else
    fail "build_deck.py no longer calls intelligence_engines_check's functions directly — cannot confirm it bypasses the CLI default"
fi

if grep -q "_iec\.check_copy(\|_iec\.check_prompts(" "$PHASE_VERIFIERS"; then
    pass "phase_verifiers.py calls check_copy()/check_prompts() directly (not the CLI default)"
else
    fail "phase_verifiers.py no longer calls intelligence_engines_check's functions directly"
fi

echo "--- USAGE docstring documents the new resolution flags ---"

if grep -q -- "--run-dir" "$SCRIPT" && grep -q -- "--workspace" "$SCRIPT" && grep -q "OC_DECK_WORKSPACE" "$SCRIPT"; then
    pass "USAGE/module docstring documents --run-dir, --workspace, and OC_DECK_WORKSPACE"
else
    fail "USAGE/module docstring is missing one of --run-dir / --workspace / OC_DECK_WORKSPACE"
fi

echo
echo "===================================================================="
echo " presentation-intelligence-engines-workspace: PASS=$PASS FAIL=$FAIL"
echo "===================================================================="
[ "$FAIL" -eq 0 ]
