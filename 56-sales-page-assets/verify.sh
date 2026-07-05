#!/usr/bin/env bash
# ==============================================================================
# verify.sh — read-only self-verification gate for Skill 56 (Sales Page Assets).
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (it never mutates a committed file; the golden reproduce
# and the no-cert proofs run in throwaway temp run-dirs that are always cleaned up).
# It runs, in order:
#   1. entry --self-test (deps/version/hash-pin + all 8 provers + orchestrator).
#   2. JSON validity of every shipped .json.
#   3. PROVIDER-PURITY scan: ZERO Anthropic ids (api.anthropic.com / claude-*) in the
#      BAKED PROMPTS (the client-path runtime generation content) — AC-1.
#   4. SECRET scan: no inline key patterns anywhere in the skill tree — AC-6.
#   5. GOLDEN REPRODUCE — content-authenticity gate, prove the five committed golden
#      ledgers pass their gates, re-verify the committed golden certificate, and drive
#      the golden ledgers through the canonical orchestrator (fresh nonce, temp run-dir)
#      to a fresh signed certificate that self-validates.
#   6. BROKEN-VARIANT REJECTIONS — each deliberately-broken variant must be REJECTED
#      (nonzero) carrying its DISTINCT AF-SP56-* code; the "missing provenance" and
#      "unapproved" variants must drive the orchestrator to NO certificate (fail-closed).
# Exit 0 = all green; nonzero = a check failed. No network, no writes to committed files.
# ==============================================================================
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
ORCH="$SKILL_DIR/run_sales_page_assets.py"
GOLDEN="$SKILL_DIR/examples/golden-momentum"
GOLDEN_NONCE="golden-momentum-nonce-v1"     # documented example nonce (specimen, not a secret)
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

reject() {                 # reject "<label>" "<code>" <cmd...>  — PASS iff rc!=0 AND code present
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

echo "== Skill 56 verify :: (1) entry --self-test =="
run "sales-page-assets-entry.sh --self-test" bash "$SKILL_DIR/sales-page-assets-entry.sh" --self-test

echo "== Skill 56 verify :: (2) JSON validity =="
while IFS= read -r j; do
  if "$PY" -c "import json,sys; json.load(open(sys.argv[1]))" "$j" >/dev/null 2>&1; then
    echo "  [PASS] ${j#$SKILL_DIR/}"
  else
    echo "  [FAIL] ${j#$SKILL_DIR/} does not parse"; fails=$((fails+1))
  fi
done < <(find "$SKILL_DIR" -name '*.json' -not -path '*/.*')

echo "== Skill 56 verify :: (3) provider-purity (ZERO provider/model ids in the BAKED PROMPTS) =="
# The baked prompts are the client-path RUNTIME generation content. They must be 100%
# provider-agnostic. The enforcement scripts, spec JSON, and docs name Anthropic/Gemini/OpenAI
# on purpose (to FORBID them / document rule R1) and are out of scope (AC-1).
if hits="$(grep -rIl -E -i 'api\.anthropic\.com|claude-[0-9]|\bgemini\b|gpt-image-1|\bopenai\b|gpt-4|dall-?e|sk-ant-|sk-proj-' \
            "$SKILL_DIR/prompts/baked" 2>/dev/null)"; then
  if [ -n "$hits" ]; then
    echo "  [FAIL] provider/model id(s) found in the baked prompts:"; echo "$hits" | sed 's/^/         /'; fails=$((fails+1))
  else
    echo "  [PASS] baked prompts are provider-agnostic"
  fi
else
  echo "  [PASS] baked prompts are provider-agnostic"
fi

echo "== Skill 56 verify :: (4) secret scan =="
# exclude this script itself (it necessarily contains the secret-shaped patterns it scans for).
if s="$(grep -rIl -E --exclude='verify.sh' 'sk-ant-[A-Za-z0-9]|sk-proj-[A-Za-z0-9]|Bearer sk-[A-Za-z0-9]{20}|eyJhbGciO' \
          "$SKILL_DIR" 2>/dev/null)"; then
  if [ -n "$s" ]; then
    echo "  [FAIL] secret-shaped token(s) found:"; echo "$s" | sed 's/^/         /'; fails=$((fails+1))
  else
    echo "  [PASS] no inline secrets"
  fi
else
  echo "  [PASS] no inline secrets"
fi

# ---------------------------------------------------------------------------
# 5) GOLDEN REPRODUCE — the committed golden bundle clears every gate + certifies.
# ---------------------------------------------------------------------------
echo "== Skill 56 verify :: (5) golden reproduce (examples/golden-momentum) =="
if [ -d "$GOLDEN" ]; then
  run "golden content authenticity (--content-check)" "$PY" "$GOLDEN/build_golden.py" --content-check
  run "golden brief   -> prove_sp_intake"          "$PY" "$SCRIPTS/prove_sp_intake.py" "$GOLDEN/brief.json"
  run "golden images  -> prove_sp_image_plan"      "$PY" "$SCRIPTS/prove_sp_image_plan.py" --plan "$GOLDEN/image_plan.json"
  run "golden prompts -> prove_sp_prompt_floor"    "$PY" "$SCRIPTS/prove_sp_prompt_floor.py" --ledger "$GOLDEN/image_plan.json"
  run "golden main    -> prove_sp_main_structure"  "$PY" "$SCRIPTS/prove_sp_main_structure.py" --ledger "$GOLDEN/copy_ledger.json"
  run "golden upsell  -> prove_sp_upsell_structure" "$PY" "$SCRIPTS/prove_sp_upsell_structure.py" --ledger "$GOLDEN/copy_ledger.json"
  run "golden hi-tkt  -> prove_sp_highticket_band" "$PY" "$SCRIPTS/prove_sp_highticket_band.py" --ledger "$GOLDEN/copy_ledger.json"
  run "golden bump    -> prove_sp_bump_band"       "$PY" "$SCRIPTS/prove_sp_bump_band.py" --ledger "$GOLDEN/copy_ledger.json"
  run "golden bundle  -> prove_sp_bundle"          "$PY" "$SCRIPTS/prove_sp_bundle.py" --manifest "$GOLDEN/funnel-manifest.json"

  CERT="$GOLDEN/delivery/golden-momentum-FINAL/PROCESS-CERTIFICATE.json"
  if [ -f "$CERT" ]; then
    run "committed golden certificate re-verifies" \
        "$PY" "$SCRIPTS/prove_sp_cert.py" --cert "$CERT" --nonce "$GOLDEN_NONCE"
  else
    printf '  [FAIL] committed golden certificate missing at %s\n' "$CERT"; fails=$((fails + 1))
  fi

  # reproduce through the canonical orchestrator in a throwaway run-dir (fresh nonce)
  TMP="$(mktemp -d "${TMPDIR:-/tmp}/spa56_golden.XXXXXX")"
  trap 'rm -rf "$TMP"' EXIT
  RD="$TMP/run-golden"
  mkdir -p "$RD"
  cp "$GOLDEN/brief.json" "$GOLDEN/image_plan.json" "$GOLDEN/copy_ledger.json" \
     "$GOLDEN/media_ledger.json" "$GOLDEN/funnel-manifest.json" "$RD/"
  # P5-P9 artifact-backed gates (FIX-XC-03b): carry the committed build artifacts into the run dir.
  [ -d "$GOLDEN/pages" ] && cp -R "$GOLDEN/pages" "$RD/pages"
  for a in drive_docs.json delivery.json build_receipt.json; do
    [ -f "$GOLDEN/$a" ] && cp "$GOLDEN/$a" "$RD/$a"
  done
  FRESH_NONCE="verify-golden-$$-$RANDOM"
  printf '%s' "$FRESH_NONCE" > "$RD/.spa_run_nonce"; chmod 600 "$RD/.spa_run_nonce"
  if "$PY" "$ORCH" --run-dir "$RD" --nonce "$FRESH_NONCE" >"$TMP/orch.log" 2>&1 && [ -f "$RD/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] golden through orchestrator -> signed certificate minted\n'
    run "reproduced certificate self-validates" \
        "$PY" "$SCRIPTS/prove_sp_cert.py" --cert "$RD/PROCESS-CERTIFICATE.json" --nonce "$FRESH_NONCE"
  else
    printf '  [FAIL] golden did not certify through the orchestrator\n'
    sed 's/^/         /' "$TMP/orch.log"; fails=$((fails + 1))
  fi
else
  printf '  [FAIL] golden example dir missing at %s\n' "$GOLDEN"; fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# 6) BROKEN-VARIANT REJECTIONS — each trips a DISTINCT AF-SP56-*, fail-closed.
# ---------------------------------------------------------------------------
echo "== Skill 56 verify :: (6) broken-variant rejections =="
BV="$GOLDEN/broken-variants"
reject "A out-of-band section"    "AF-SP56-MAIN-SECTION-ORDER" \
       "$PY" "$SCRIPTS/prove_sp_main_structure.py" --ledger "$BV/A_out_of_band_section/copy_ledger.json"
reject "B high-ticket word floor" "AF-SP56-HIGHTICKET-FLOOR" \
       "$PY" "$SCRIPTS/prove_sp_highticket_band.py" --ledger "$BV/B_high_ticket_word_floor/copy_ledger.json"
reject "C bump out-of-band"       "AF-SP56-BUMP-FLOOR" \
       "$PY" "$SCRIPTS/prove_sp_bump_band.py" --ledger "$BV/C_bump_out_of_band/copy_ledger.json"
reject "D image slice empty"      "AF-SP56-IMGPLAN-SLICE-EMPTY" \
       "$PY" "$SCRIPTS/prove_sp_image_plan.py" --plan "$BV/D_image_slice/image_plan.json"
reject "F unapproved brief"       "AF-SP56-INTAKE-UNLOCKED" \
       "$PY" "$SCRIPTS/prove_sp_intake.py" "$BV/F_unapproved/brief.json"

# 6b) E2E: missing-provenance + unapproved drive the orchestrator to NO certificate.
if [ -d "$GOLDEN" ]; then
  # E — media_ledger.json withheld -> P2 image-provenance seam aborts, no cert.
  TE="$(mktemp -d "${TMPDIR:-/tmp}/spa56_e.XXXXXX")"
  RE="$TE/run"; mkdir -p "$RE"
  cp "$GOLDEN/brief.json" "$GOLDEN/image_plan.json" "$GOLDEN/copy_ledger.json" \
     "$GOLDEN/funnel-manifest.json" "$RE/"   # deliberately NO media_ledger.json
  NE="verify-e-$$-$RANDOM"; printf '%s' "$NE" > "$RE/.spa_run_nonce"; chmod 600 "$RE/.spa_run_nonce"
  "$PY" "$ORCH" --run-dir "$RE" --nonce "$NE" >"$TE/orch.log" 2>&1; erc=$?
  if [ "$erc" -ne 0 ] && [ ! -f "$RE/PROCESS-CERTIFICATE.json" ] && grep -q 'media_ledger.json absent' "$TE/orch.log"; then
    printf '  [PASS] E missing-provenance -> orchestrator aborts (rc=%s) at P2, NO certificate\n' "$erc"
  else
    printf '  [FAIL] E missing-provenance -> expected P2 abort + no cert, got rc=%s\n' "$erc"
    sed 's/^/         /' "$TE/orch.log"; fails=$((fails + 1))
  fi
  rm -rf "$TE"

  # F — unapproved brief -> P0 intake gate aborts, no cert.
  TF="$(mktemp -d "${TMPDIR:-/tmp}/spa56_f.XXXXXX")"
  RF="$TF/run"; mkdir -p "$RF"
  cp "$GOLDEN/image_plan.json" "$GOLDEN/copy_ledger.json" "$GOLDEN/media_ledger.json" \
     "$GOLDEN/funnel-manifest.json" "$RF/"
  cp "$BV/F_unapproved/brief.json" "$RF/brief.json"
  NF="verify-f-$$-$RANDOM"; printf '%s' "$NF" > "$RF/.spa_run_nonce"; chmod 600 "$RF/.spa_run_nonce"
  "$PY" "$ORCH" --run-dir "$RF" --nonce "$NF" >"$TF/orch.log" 2>&1; frc=$?
  if [ "$frc" -ne 0 ] && [ ! -f "$RF/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] F unapproved -> orchestrator aborts (rc=%s) at P0, NO certificate\n' "$frc"
  else
    printf '  [FAIL] F unapproved -> expected P0 abort + no cert, got rc=%s\n' "$frc"
    sed 's/^/         /' "$TF/orch.log"; fails=$((fails + 1))
  fi
  rm -rf "$TF"
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
  echo "RESULT: PASS — all Skill 56 self-verification checks green (self-test + JSON + provider-purity + secret-scan + golden reproduce + broken rejections)."
  exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
