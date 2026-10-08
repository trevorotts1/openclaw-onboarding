#!/usr/bin/env bash
# Folded from .github/workflows/presentations-lockstep.yml (job "Presentations SOP/manifest/code lockstep (sync_check)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Install presentation pipeline Python deps (reportlab, python-pptx — required by presenters_speech_pdf.py / build_deck.py imports in sync env; see install.sh Step 6.5 for the canonical four-dep set)
set -e -o pipefail
pip install reportlab python-pptx --quiet
)
( # step: sync_check.py — presentations lockstep (exit 0 required)
set -e -o pipefail
set -euo pipefail
SYNC_CHECK="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py"
if [ ! -f "$SYNC_CHECK" ]; then
  echo "FATAL: sync_check.py not found at $SYNC_CHECK" >&2
  exit 2
fi
# Run sync_check and require exit 0.
# Exit 4 = lockstep drift (AF code / checker / role / SOP mismatch).
# Exit 2 = sync_check could not run (missing input — also a hard fail).
python3 "$SYNC_CHECK"
echo "sync_check: presentations lockstep PASSED — renderer, ruleset, manifest, roles, and SOPs are in sync."
)
( # step: SOP-SLIDE-00 mirror body-compare (Fix 25 — generated mirror must match canonical)
set -e -o pipefail
set -euo pipefail
CANONICAL="universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md"
MIRROR="23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md"
for f in "$CANONICAL" "$MIRROR"; do
  if [ ! -f "$f" ]; then
    echo "FATAL: ruleset file not found at $f" >&2
    exit 2
  fi
done
# The dept mirror is the canonical text plus its 10-line header
# (lines 1-4 match the canonical; lines 5-10 are the 6-line dept
# header). Compare bodies only: mirror from line 11, canonical
# from line 6. Any drift fails the gate.
tail -n +6 "$CANONICAL" > /tmp/canonical-body.txt
tail -n +11 "$MIRROR" > /tmp/mirror-body.txt
if ! diff /tmp/canonical-body.txt /tmp/mirror-body.txt > /tmp/ruleset-body.diff; then
  echo "FATAL: SOP-SLIDE-00 mirror body has drifted from the canonical ruleset:" >&2
  head -40 /tmp/ruleset-body.diff >&2
  exit 1
fi
echo "SOP-SLIDE-00 mirror body matches the canonical ruleset."
)
( # step: test_preflight.py — process-gate unit tests (exit 0 required)
set -e -o pipefail
set -euo pipefail
TEST_PREFLIGHT="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/test_preflight.py"
if [ ! -f "$TEST_PREFLIGHT" ]; then
  echo "FATAL: test_preflight.py not found at $TEST_PREFLIGHT" >&2
  exit 2
fi
# The process-gate unit tests exercise every build_deck.py preflight/postflight
# checker (research-cited, claims, coverage, rich-prompt, KIE-baked, bundle
# completeness, teleprompter publish). Any regression in a gate exits non-zero
# and blocks the merge. This step ALSO emits scripts/working/af-coverage.json
# (every build_deck-enforced AF code a deliberately-failing fixture triggered),
# which Guard A (gate_integrity_check.py) consumes in the next step.
python3 "$TEST_PREFLIGHT"
echo "test_preflight: all process-gate unit tests PASSED (af-coverage emitted)."
)
( # step: test_cc_board.py — board contract unit tests (exit 0 required)
set -e -o pipefail
set -euo pipefail
TEST_CC_BOARD="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/test_cc_board.py"
if [ ! -f "$TEST_CC_BOARD" ]; then
  echo "FATAL: test_cc_board.py not found at $TEST_CC_BOARD" >&2
  exit 2
fi
python3 "$TEST_CC_BOARD"
echo "test_cc_board: all board contract unit tests PASSED."
)
( # step: test_cc_contract.py — contract integration unit tests (exit 0 required)
set -e -o pipefail
set -euo pipefail
TEST_CC_CONTRACT="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/test_cc_contract.py"
if [ ! -f "$TEST_CC_CONTRACT" ]; then
  echo "FATAL: test_cc_contract.py not found at $TEST_CC_CONTRACT" >&2
  exit 2
fi
python3 "$TEST_CC_CONTRACT"
echo "test_cc_contract: all contract integration unit tests PASSED."
)
( # step: gate_integrity_check.py — Guard A (declared==enforced==tested, exit 0 required)
set -e -o pipefail
set -euo pipefail
GUARD_A="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/gate_integrity_check.py"
AF_COV="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/working/af-coverage.json"
if [ ! -f "$GUARD_A" ]; then
  echo "FATAL: gate_integrity_check.py not found at $GUARD_A" >&2
  exit 2
fi
if [ ! -f "$AF_COV" ]; then
  echo "FATAL: af-coverage.json not found at $AF_COV — the test_preflight step must run first to emit it." >&2
  exit 2
fi
# Guard A: every PIPELINE-MANIFEST autofail with enforced_by==build_deck must
# have a referenced enforcing py_symbol AND a negative test that triggers it
# (present in af-coverage). A declared-but-no-op or declared-but-untested gate
# exits non-zero — this is what would have caught AF-QC-INDEPENDENCE as a no-op.
python3 "$GUARD_A"
echo "gate_integrity_check: Guard A PASSED — every build_deck-enforced gate is enforced AND tested."
)
( # step: runner_gate_integrity_check.py — Guard A (runner scope — declared runner codes referenced in runtime, exit 0 required)
set -e -o pipefail
set -euo pipefail
GUARD_RUNNER="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/runner_gate_integrity_check.py"
if [ ! -f "$GUARD_RUNNER" ]; then
  echo "FATAL: runner_gate_integrity_check.py not found at $GUARD_RUNNER" >&2
  exit 2
fi
# Guard A (runner scope): every PIPELINE-MANIFEST autofail with
# enforced_by==runner must appear as a string literal in
# run_signature_deck.py or prove-deck.py. A declared-but-never-cited
# runner code is a dead declaration that cannot be raised at runtime.
python3 "$GUARD_RUNNER"
echo "runner_gate_integrity_check: Guard A (runner scope) PASSED — every runner-enforced code is cited in the runner source."
)
( # step: CANONICAL-RENDERER-PIN.sha256 integrity (recompute and fail on mismatch)
set -e -o pipefail
set -euo pipefail
SCRIPTS="23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
BUILD_DECK="$SCRIPTS/build_deck.py"
RUN_SIG="$SCRIPTS/run_signature_deck.py"
PIN_FILE="$SCRIPTS/CANONICAL-RENDERER-PIN.sha256"
if [ ! -f "$BUILD_DECK" ]; then
  echo "FATAL: build_deck.py not found at $BUILD_DECK" >&2; exit 2
fi
if [ ! -f "$RUN_SIG" ]; then
  echo "FATAL: run_signature_deck.py not found at $RUN_SIG" >&2; exit 2
fi
# Recompute sha256 of build_deck.py + run_signature_deck.py (same formula
# as presentation-canonical-entry.sh GATE 3).
if command -v sha256sum >/dev/null 2>&1; then
  COMPUTED="$(cat "$BUILD_DECK" "$RUN_SIG" | sha256sum | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  COMPUTED="$(cat "$BUILD_DECK" "$RUN_SIG" | shasum -a 256 | awk '{print $1}')"
else
  echo "WARNING: no sha256 tool available; skipping pin check" >&2
  exit 0
fi
echo "Computed renderer hash: $COMPUTED"
if [ ! -f "$PIN_FILE" ]; then
  echo "WARNING: CANONICAL-RENDERER-PIN.sha256 not present — pin not yet generated." >&2
  echo "Run: cat build_deck.py run_signature_deck.py | sha256sum | awk '{print \$1}' > CANONICAL-RENDERER-PIN.sha256" >&2
  echo "and commit the pin file alongside any build_deck.py / run_signature_deck.py change." >&2
  echo "FAIL: pin file absent — cannot verify renderer integrity." >&2
  exit 1
fi
EXPECTED="$(tr -d ' \t\n\r' < "$PIN_FILE")"
if [ -z "$EXPECTED" ]; then
  echo "FAIL: CANONICAL-RENDERER-PIN.sha256 is empty." >&2; exit 1
fi
if [ "$COMPUTED" != "$EXPECTED" ]; then
  echo "FAIL: renderer hash mismatch — the committed pin does not match the current build_deck.py + run_signature_deck.py." >&2
  echo "  committed pin: $EXPECTED" >&2
  echo "  computed now:  $COMPUTED" >&2
  echo "Regenerate the pin: cat build_deck.py run_signature_deck.py | sha256sum | awk '{print \$1}' > CANONICAL-RENDERER-PIN.sha256" >&2
  exit 1
fi
echo "CANONICAL-RENDERER-PIN.sha256 PASSED — renderer hash matches the committed pin."
)
( # step: doctrine_residual_check.py — Guard B (retired-doctrine residual lint, exit 0 required)
set -e -o pipefail
set -euo pipefail
GUARD_B="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/doctrine_residual_check.py"
if [ ! -f "$GUARD_B" ]; then
  echo "FATAL: doctrine_residual_check.py not found at $GUARD_B" >&2
  exit 2
fi
# Guard B: a retired doctrine VALUE (registered in retired-doctrine-patterns.json,
# e.g. the old hook '>= 7 times' floor) must never re-appear as a LIVE instruction.
# Any match lacking a retirement context marker exits non-zero and blocks the merge.
python3 "$GUARD_B"
echo "doctrine_residual_check: Guard B PASSED — no retired doctrine present as a live instruction."
)
( # step: gate_integrity_check.py --purity — Guard B (RunFacts-pure AST lint, exit 0 required)
set -e -o pipefail
set -euo pipefail
GUARD_B_PURITY="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/gate_integrity_check.py"
if [ ! -f "$GUARD_B_PURITY" ]; then
  echo "FATAL: gate_integrity_check.py not found at $GUARD_B_PURITY" >&2
  exit 2
fi
# Guard B (purity, Trust Boundary Increment 1): AST-parses
# presentation_job/runfacts.py and asserts every function listed in
# PURITY_ASSERTED_FUNCTIONS (verify_owner_skip, verify_qc, and the
# composite verifiers migrated onto sealed RunFacts) contains no direct
# file/env I/O call. This is distinct from the doctrine_residual_check.py
# step above (also called "Guard B" in its own docstring) — two different
# checks share that label; this one is gate_integrity_check.py --purity.
# No || true, no continue-on-error: a purity violation fails this step
# and blocks the merge, same as every other gate in this job.
python3 "$GUARD_B_PURITY" --purity
echo "gate_integrity_check --purity: Guard B PASSED — RunFacts-pure gates confirmed by AST parse."
)
( # step: STANDARD-presenter-speech-layout.pdf present (H7 gate)
set -e -o pipefail
set -euo pipefail
PDF="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/STANDARD-presenter-speech-layout.pdf"
if [ ! -f "$PDF" ]; then
  echo "FAIL: $PDF is absent." >&2
  echo "Fix: run python3 .../presenters_speech_pdf.py --sample --out STANDARD-presenter-speech-layout.pdf" >&2
  echo "and commit the generated file. See H7 in the presentation review." >&2
  exit 1
fi
SIZE=$(wc -c < "$PDF")
if [ "$SIZE" -lt 1000 ]; then
  echo "FAIL: $PDF exists but is only $SIZE bytes — likely an empty or truncated file." >&2
  exit 1
fi
echo "STANDARD-presenter-speech-layout.pdf present ($SIZE bytes)."
)
( # step: prove_pres_prompt_floor.py — shared image-prompt gate self-test (exit 0 required)
set -e -o pipefail
set -euo pipefail
PROVER="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/prove_pres_prompt_floor.py"
if [ ! -f "$PROVER" ]; then
  echo "FATAL: prove_pres_prompt_floor.py not found at $PROVER" >&2
  exit 2
fi
# The shared prompt_gate.py (imported by build_deck.py and EVERY side-door —
# kie_generate.py x2 + the Skill-46 relay) is the ONE gate that keeps a thin /
# garbled / ungated prompt off the paid kie.ai API. Its fixture prover proves the
# KIE rule 12 length band (shared enforcer) + structural + 8-class negative + spelling-lock + density
# + demographic teeth still fire (a PASS fixture passes, each FAIL fixture fails),
# plus the pin / mode-consistency helpers. A regression that loosens the gate
# exits non-zero and blocks the merge.
python3 "$PROVER" --self-test
echo "prove_pres_prompt_floor: shared image-prompt gate self-test PASSED."
)
( # step: verify.sh — Skill 51 (Signature Presentation) self-verification gate (exit 0 required)
set -e -o pipefail
set -euo pipefail
VERIFY_SH="51-signature-presentation/verify.sh"
if [ ! -f "$VERIFY_SH" ]; then
  echo "FATAL: verify.sh not found at $VERIFY_SH" >&2
  exit 2
fi
# Verify.sh runs the five prover self-tests, the wire-presence check,
# sync_check.py lockstep, manifest phase/autofail declaration, prover
# resolvability, and register-library-additions --check. In CI there is
# no materialized department, so ENGINE_SRC is the skills template, which
# carries the canonical v25 manifest (5 P-SP phases, 16 AF-SP codes).
# Must roll after U004 so boxes that have not taken it yet don't go red.
bash "$VERIFY_SH"
echo "verify.sh: Skill 51 self-verification PASSED."
)
( # step: vendored-blob compare — persona_service vendored copies must match canonicals (exit 0 required)
set -e -o pipefail
set -euo pipefail
RES="23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/persona_service/resources"
# Fix 29: the PRES-053 packaged persona closure must be byte-identical
# to its canonicals. embedding_engine.py is a DELIBERATE shim
# (re-exports the canonical engine; see its docstring) and is
# excluded from this compare by design.
fail=0
while IFS='|' read -r canon vend; do
  if ! cmp -s "$canon" "$vend"; then
    echo "DRIFT: $vend differs from $canon — re-vendor with cp" >&2
    fail=1
  fi
done <<PAIRS
shared-utils/resolve_db.py|${RES}/helpers/resolve_db.py
shared-utils/llm_score.py|${RES}/helpers/llm_score.py
23-ai-workforce-blueprint/scripts/persona-selector-v2.py|${RES}/scripts/persona-selector-v2.py
PAIRS
if [ "$fail" -ne 0 ]; then exit 1; fi
echo "vendored-blob compare PASSED: 3 vendored copies byte-identical to canonicals (embedding_engine.py shim excluded)."
)
