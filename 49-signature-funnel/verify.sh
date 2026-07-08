#!/usr/bin/env bash
# ==============================================================================
# verify.sh — Skill 49 (Signature Funnel) self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (it never mutates a committed file; the golden reproduce
# and the E2E no-cert proof run in throwaway temp dirs that are always cleaned up).
# It runs, in order:
#
#   1. the five fail-closed provers in --self-test mode (built-in VALID + VIOLATION
#      fixtures);
#   2. the orchestrator end-to-end self-test (front door + no-skip + signed cert);
#   3. the canonical entry --self-test (deps/version/hash-pin + all self-tests);
#   4. JSON sanity on the shipped contracts + intake-spec conformance;
#   5. GOLDEN REPRODUCE — prove the four committed golden ledgers pass their gates,
#      re-verify the committed golden certificate, and drive the golden ledgers
#      through the canonical orchestrator (fresh nonce, temp run-dir) to a fresh
#      signed certificate that self-validates;
#   6. BROKEN-VARIANT REJECTIONS — each deliberately-broken variant must be REJECTED
#      (nonzero) carrying its DISTINCT AF-FUN-* code, and the "unapproved" variant
#      must drive the orchestrator to NO certificate (fail-closed at P0).
#
# Exits NONZERO on ANY failure so it can gate a merge / CI / a post-install check.
#
# Usage:  bash 49-signature-funnel/verify.sh
# Exit:   0 = all green; nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
ORCH="$SKILL_DIR/run_signature_funnel.py"
GOLDEN="$SKILL_DIR/examples/golden-daybreak"
GOLDEN_NONCE="golden-daybreak-nonce-v1"     # documented example nonce (specimen, not a secret)
PY="${PYTHON:-python3}"
fails=0

run() {                    # run "<label>" <cmd...>  — PASS iff rc==0
  local label="$1"; shift
  local log rc
  log="$("$@" 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ]; then
    printf '  [PASS] %s\n' "$label"
  else
    printf '  [FAIL] %s (rc=%s)\n' "$label" "$rc"
    printf '%s\n' "$log" | sed 's/^/         /'
    fails=$((fails + 1))
  fi
}

reject() {                 # reject "<label>" "<AF-code>" <cmd...>  — PASS iff rc!=0 AND code present
  local label="$1" code="$2"; shift 2
  local log rc
  log="$("$@" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$log" | grep -q -- "$code"; then
    printf '  [PASS] %s -> rejected (rc=%s) carrying %s\n' "$label" "$rc" "$code"
  else
    printf '  [FAIL] %s -> expected nonzero + %s, got rc=%s\n' "$label" "$code" "$rc"
    printf '%s\n' "$log" | sed 's/^/         /'
    fails=$((fails + 1))
  fi
}

echo "== Skill 49 (Signature Funnel) :: verify.sh =="

# 1) the seven fail-closed provers — built-in self-test fixtures.
for p in prove_sf_intake prove_sf_copy prove_sf_prompt_floor prove_sf_graph prove_sf_build prove_sf_no_pitch prove_sf_cert; do
  if [ -f "$SCRIPTS/$p.py" ]; then
    run "$p.py --self-test" "$PY" "$SCRIPTS/$p.py" --self-test
  else
    printf '  [FAIL] %s.py missing at %s\n' "$p" "$SCRIPTS"; fails=$((fails + 1))
  fi
done

# 2) orchestrator end-to-end self-test (front door + no-skip + signed cert).
run "run_signature_funnel.py --self-test" "$PY" "$ORCH" --self-test

# 3) canonical entry self-test (deps/version/hash-pin + all self-tests).
run "signature-funnel-entry.sh --self-test" bash "$SKILL_DIR/signature-funnel-entry.sh" --self-test

# 4) JSON sanity on the shipped contracts + intake spec conformance.
run "manifest/structure JSON parse" "$PY" -c "import json,sys; \
[json.load(open('$SKILL_DIR/'+f)) for f in ('FUNNEL-MANIFEST.json','structure/funnel_structure.json','intake/sf-intake-questions.json')]"
run "intake spec conforms to prove_sf_intake" "$PY" "$SCRIPTS/prove_sf_intake.py" "$SKILL_DIR/intake/sf-intake-questions.json"

# 4b) FIX-BOARD-DEPT-01 — AST guard: the Command Center board department slug is a
#     REAL, seeded fleet department (Skill 49's declared web-development/marketing),
#     never the non-existent "funnels" (nor the sibling Skill 53 "books") defect.
run "board department slug is canonical (test_sf_department.py)" \
    "$PY" "$SCRIPTS/test_sf_department.py"

# ---------------------------------------------------------------------------
# 5) GOLDEN REPRODUCE — the committed golden funnel clears every gate + certifies.
# ---------------------------------------------------------------------------
echo "-- golden reproduce (examples/golden-daybreak) --"
if [ -d "$GOLDEN" ]; then
  run "golden brief  -> prove_sf_intake"       "$PY" "$SCRIPTS/prove_sf_intake.py" "$GOLDEN/brief.json"
  run "golden copy   -> prove_sf_copy"         "$PY" "$SCRIPTS/prove_sf_copy.py" --ledger "$GOLDEN/copy_ledger.json"
  run "golden prompts-> prove_sf_prompt_floor" "$PY" "$SCRIPTS/prove_sf_prompt_floor.py" --ledger "$GOLDEN/prompt_ledger.json"
  run "golden graph  -> prove_sf_graph"        "$PY" "$SCRIPTS/prove_sf_graph.py" --graph "$GOLDEN/funnel_graph.json"
  run "golden build  -> prove_sf_build"        "$PY" "$SCRIPTS/prove_sf_build.py" --receipt "$GOLDEN/build_receipt.json"
  run "golden media  -> prove_sf_no_pitch"     "$PY" "$SCRIPTS/prove_sf_no_pitch.py" --ledger "$GOLDEN/media_ledger.json"
  # FIX-IMG-07 — the golden prompt AND media ledgers cover every required image slot.
  run "golden prompt coverage (--structure)" "$PY" "$SCRIPTS/prove_sf_prompt_floor.py" \
      --structure --brief "$GOLDEN/brief.json" --ledger "$GOLDEN/prompt_ledger.json"
  run "golden image coverage (--structure)"  "$PY" "$SCRIPTS/prove_sf_prompt_floor.py" \
      --structure --brief "$GOLDEN/brief.json" --ledger "$GOLDEN/media_ledger.json"

  CERT="$GOLDEN/delivery/golden-daybreak-FINAL/PROCESS-CERTIFICATE.json"
  if [ -f "$CERT" ]; then
    run "committed golden certificate re-verifies" \
        "$PY" "$SCRIPTS/prove_sf_cert.py" --cert "$CERT" --nonce "$GOLDEN_NONCE"
  else
    printf '  [FAIL] committed golden certificate missing at %s\n' "$CERT"; fails=$((fails + 1))
  fi

  # reproduce through the canonical orchestrator in a throwaway run-dir (fresh nonce)
  TMP="$(mktemp -d "${TMPDIR:-/tmp}/sf49_golden.XXXXXX")"
  trap 'rm -rf "$TMP"' EXIT
  RD="$TMP/run-golden"
  mkdir -p "$RD"
  cp "$GOLDEN/brief.json" "$GOLDEN/copy_ledger.json" "$GOLDEN/prompt_ledger.json" "$GOLDEN/media_ledger.json" \
     "$GOLDEN/persona-selection-log.md" "$RD/"   # FIX-XC-02a: persona grounding is P0 fail-closed
  # P5-P8 artifacts (fragments + graph + build receipt + derived-page ledger)
  cp "$GOLDEN/funnel_graph.json" "$GOLDEN/build_receipt.json" "$GOLDEN/derived_pages.json" "$RD/"
  cp -R "$GOLDEN/pages" "$RD/pages"
  FRESH_NONCE="verify-golden-$$-$RANDOM"
  printf '%s' "$FRESH_NONCE" > "$RD/.sf_run_nonce"; chmod 600 "$RD/.sf_run_nonce"
  if "$PY" "$ORCH" --run-dir "$RD" --nonce "$FRESH_NONCE" >"$TMP/orch.log" 2>&1 && [ -f "$RD/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] golden through orchestrator -> signed certificate minted\n'
    run "reproduced certificate self-validates" \
        "$PY" "$SCRIPTS/prove_sf_cert.py" --cert "$RD/PROCESS-CERTIFICATE.json" --nonce "$FRESH_NONCE"
  else
    printf '  [FAIL] golden did not certify through the orchestrator\n'
    sed 's/^/         /' "$TMP/orch.log"; fails=$((fails + 1))
  fi
else
  printf '  [FAIL] golden example dir missing at %s\n' "$GOLDEN"; fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# 6) BROKEN-VARIANT REJECTIONS — each trips a DISTINCT AF-FUN-*, fail-closed.
# ---------------------------------------------------------------------------
echo "-- broken-variant rejections --"
BV="$GOLDEN/broken-variants"
reject "A wrong section count"  "AF-FUN-SECTION-MISSING" \
       "$PY" "$SCRIPTS/prove_sf_copy.py" --ledger "$BV/A_wrong_section_count/copy_ledger.json"
reject "B out-of-band copy"     "AF-FUN-SEC1-CHARBAND" \
       "$PY" "$SCRIPTS/prove_sf_copy.py" --ledger "$BV/B_out_of_band_copy/copy_ledger.json"
reject "C image-prompt too short" "AF-FUN-PROMPT-FLOOR" \
       "$PY" "$SCRIPTS/prove_sf_prompt_floor.py" --ledger "$BV/C_image_prompt_too_short/prompt_ledger.json"
reject "D missing provenance"   "AF-FUN-IMG-PROVENANCE" \
       "$PY" "$SCRIPTS/prove_sf_no_pitch.py" --ledger "$BV/D_missing_provenance/media_ledger.json"
reject "E unapproved brief"     "AF-FUN-INTAKE-UNLOCKED" \
       "$PY" "$SCRIPTS/prove_sf_intake.py" "$BV/E_unapproved/brief.json"

# 6b) E2E: the unapproved brief drives the orchestrator to NO certificate (P0 abort).
if [ -d "$GOLDEN" ]; then
  TMP2="$(mktemp -d "${TMPDIR:-/tmp}/sf49_e2e.XXXXXX")"
  RD2="$TMP2/run-unapproved"; mkdir -p "$RD2"
  cp "$GOLDEN/copy_ledger.json" "$GOLDEN/prompt_ledger.json" "$GOLDEN/media_ledger.json" "$RD2/"
  cp "$BV/E_unapproved/brief.json" "$RD2/brief.json"
  N2="verify-e2e-$$-$RANDOM"
  printf '%s' "$N2" > "$RD2/.sf_run_nonce"; chmod 600 "$RD2/.sf_run_nonce"
  "$PY" "$ORCH" --run-dir "$RD2" --nonce "$N2" >"$TMP2/orch.log" 2>&1; e2erc=$?
  if [ "$e2erc" -ne 0 ] && [ ! -f "$RD2/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] E2E unapproved -> orchestrator aborts (rc=%s), NO certificate issued\n' "$e2erc"
  else
    printf '  [FAIL] E2E unapproved -> expected abort + no cert, got rc=%s cert_exists=%s\n' \
           "$e2erc" "$([ -f "$RD2/PROCESS-CERTIFICATE.json" ] && echo yes || echo no)"
    fails=$((fails + 1))
  fi
  rm -rf "$TMP2"
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
  echo "RESULT: PASS — all Skill 49 self-verification checks green."
  exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
