#!/usr/bin/env bash
# ==============================================================================
# sales-page-assets-entry.sh — the CANONICAL, fail-closed front door for Skill 56
# (Sales Page Assets — the Direct-Response sibling of Skill 49). NOTHING may
# generate copy/image-prompts, call an image provider, touch GHL, write Google
# Docs, send mail, or mint a certificate except THROUGH this shell. It performs,
# in order and all fail-closed:
#
#   1. DEPS        — python3 present (else abort).
#   2. VERSION     — skill-version.txt is present + non-empty (pinned major).
#   3. HASH-PIN    — recompute the sha256 of the enforcement core (provers +
#                    structure + orchestrator) and compare to SPA-PROVER-PIN.sha256.
#                    A tampered prover / structure ledger dies here.
#   4. BYPASS-SCAN — refuse a run whose working files hand-roll GHL REST calls,
#                    ImgBB re-hosting, a raw image createTask, or a mail sender
#                    instead of delegating to Skill 6 / Skill 47.
#   5. NONCE       — write a run-scoped 0600 front-door nonce; export SPA_RUN_NONCE.
#   6. ORCHESTRATE — run_sales_page_assets.py with the nonce (the no-skip state
#                    machine); it emits the signed PROCESS-CERTIFICATE only on
#                    all-phases-pass.
#
# Usage:
#   bash sales-page-assets-entry.sh --run-dir <RUN_DIR>
#   bash sales-page-assets-entry.sh --self-test
#   bash sales-page-assets-entry.sh --write-pin   (mint the enforcement-core pin)
# Exit: 0 = certified / self-test green; nonzero = a fail-closed guard tripped.
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"
PIN_FILE="$SCRIPTS_DIR/SPA-PROVER-PIN.sha256"
PY="${PYTHON:-python3}"
EXPECTED_MAJOR="1"

# Files whose integrity is pinned (the enforcement core). Order-independent: we hash
# each file's own sha256, then hash the sorted list of "sha256  name" lines.
PINNED_FILES=(
  "scripts/prove_sp_intake.py"
  "scripts/prove_sp_image_plan.py"
  "scripts/prove_sp_prompt_floor.py"
  "scripts/prove_sp_main_structure.py"
  "scripts/prove_sp_upsell_structure.py"
  "scripts/prove_sp_highticket_band.py"
  "scripts/prove_sp_bump_band.py"
  "scripts/prove_sp_bundle.py"
  "scripts/prove_sp_cert.py"
  "structure/sales_page_structure.json"
  "structure/labeling-grammar.json"
  "run_sales_page_assets.py"
)

# Forbidden patterns in a run's working files — a hand-rolled GHL / ImgBB / image / sender bypass.
BYPASS_PATTERNS='services\.leadconnectorhq\.com|rest\.gohighlevel\.com|api\.gohighlevel\.com|api\.imgbb\.com|api\.anthropic\.com|smtplib|sendgrid|mailgun|nodemailer|ses\.send_email|send_raw_email|api\.kie\.ai.*createtask|createtask.*api\.kie\.ai'

die() { printf 'ABORT [%s]: %s\n' "$1" "$2" >&2; exit 1; }

compute_pin() {
  local line acc=""
  for rel in "${PINNED_FILES[@]}"; do
    local f="$SKILL_DIR/$rel"
    [ -f "$f" ] || die "HASH-PIN" "pinned file missing: $rel"
    if command -v shasum >/dev/null 2>&1; then
      line="$(shasum -a 256 "$f" | awk '{print $1}')  $rel"
    else
      line="$(sha256sum "$f" | awk '{print $1}')  $rel"
    fi
    acc+="$line"$'\n'
  done
  printf '%s' "$acc" | LC_ALL=C sort | { \
    if command -v shasum >/dev/null 2>&1; then shasum -a 256; else sha256sum; fi; } | awk '{print $1}'
}

step_deps() {
  command -v "$PY" >/dev/null 2>&1 || die "DEPS" "python3 not found on PATH"
}

step_version() {
  local vf="$SKILL_DIR/skill-version.txt"
  [ -s "$vf" ] || die "VERSION" "skill-version.txt missing/empty"
  local v; v="$(tr -d '[:space:]' < "$vf")"
  case "$v" in
    "$EXPECTED_MAJOR".*) : ;;
    *) die "VERSION" "skill-version.txt is '$v', expected major $EXPECTED_MAJOR.x" ;;
  esac
}

step_hashpin() {
  local now; now="$(compute_pin)"
  if [ ! -f "$PIN_FILE" ]; then
    die "HASH-PIN" "pin file missing: $PIN_FILE (run: bash sales-page-assets-entry.sh --write-pin to mint it)"
  fi
  local pinned; pinned="$(tr -d '[:space:]' < "$PIN_FILE")"
  [ "$now" = "$pinned" ] || die "HASH-PIN" "enforcement-core hash mismatch (a prover/structure/orchestrator was modified). expected=$pinned got=$now"
}

step_bypass_scan() {
  local rd="$1"
  [ -d "$rd" ] || return 0
  local hits
  if hits="$(grep -rIl -E -i "$BYPASS_PATTERNS" "$rd" 2>/dev/null)"; then
    if [ -n "$hits" ]; then
      printf 'BYPASS-SCAN hits:\n%s\n' "$hits" >&2
      die "BYPASS-SCAN" "run working files hand-roll GHL REST / ImgBB / a raw image createTask / a mail sender / an Anthropic call. All GHL build+media go through Skill 6; all image gen goes through Skill 47 or the client's image provider. Delete the hand-rolled path."
    fi
  fi
}

step_nonce() {
  local rd="$1"
  local nonce; nonce="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  local nf="$rd/.spa_run_nonce"
  ( umask 077; printf '%s' "$nonce" > "$nf" )
  chmod 600 "$nf"
  printf '%s' "$nonce"
}

# FIX-XC-09e — resolve the CLIENT's own execution-tier authoring model (role=content),
# record routing/model-content-receipt.json, and gate it (fail-closed) via prove_sp_cert
# --model-receipt. The client's OWN strongest model writes the copy; Anthropic is hard-banned.
step_model_receipt() {
  local rd="$1"
  "$PY" - "$rd" <<'PYEOF'
import json, os, sys, datetime
rd = sys.argv[1]
model = os.environ.get("SP_CONTENT_MODEL", "")
provider = os.environ.get("SP_CONTENT_PROVIDER", "")
tier = os.environ.get("SP_CONTENT_TIER", "content")
receipt = {
    "role": "content",
    "resolved_from": "client-provider-chain" if model else "unresolved",
    "model": model,
    "provider": provider.lower(),
    "tier": tier,
    "anthropic_banned": True,
    "resolved_at": datetime.datetime.utcnow().isoformat() + "Z",
}
os.makedirs(os.path.join(rd, "routing"), exist_ok=True)
with open(os.path.join(rd, "routing", "model-content-receipt.json"), "w", encoding="utf-8") as fh:
    json.dump(receipt, fh, indent=2)
PYEOF
  "$PY" "$SCRIPTS_DIR/prove_sp_cert.py" --model-receipt "$rd/routing/model-content-receipt.json" \
    || die "MODEL-TIER" "content-authoring model receipt failed the execution-tier / no-Anthropic gate — set SP_CONTENT_MODEL + SP_CONTENT_PROVIDER (+ SP_CONTENT_TIER) to the CLIENT's own strongest model"
}

run_pipeline() {
  local rd="$1"
  [ -n "$rd" ] || die "USAGE" "--run-dir is required"
  rd="$(cd "$rd" 2>/dev/null && pwd || true)"
  [ -n "$rd" ] && [ -d "$rd" ] || die "USAGE" "run-dir does not exist"
  step_deps
  step_version
  step_hashpin
  step_bypass_scan "$rd"
  step_model_receipt "$rd"
  local nonce; nonce="$(step_nonce "$rd")"
  export SPA_RUN_NONCE="$nonce"
  echo "== sales-page-assets-entry :: front door cleared (deps/version/hash-pin/bypass/model-tier/nonce) =="
  "$PY" "$SKILL_DIR/run_sales_page_assets.py" --run-dir "$rd" --nonce "$nonce"
}

self_test() {
  echo "== sales-page-assets-entry :: --self-test =="
  step_deps
  step_version
  if [ -f "$PIN_FILE" ]; then step_hashpin; echo "  [PASS] hash-pin verified"; else echo "  [WARN] no pin file yet (mint with --write-pin)"; fi
  local fails=0
  for p in prove_sp_intake prove_sp_image_plan prove_sp_prompt_floor prove_sp_main_structure prove_sp_upsell_structure prove_sp_highticket_band prove_sp_bump_band prove_sp_bundle prove_sp_cert; do
    if "$PY" "$SCRIPTS_DIR/$p.py" --self-test >"/tmp/spa_$p.log" 2>&1; then
      echo "  [PASS] $p.py --self-test"
    else
      echo "  [FAIL] $p.py --self-test"; sed 's/^/         /' "/tmp/spa_$p.log"; fails=$((fails+1))
    fi
  done
  if "$PY" "$SKILL_DIR/run_sales_page_assets.py" --self-test >/tmp/spa_orch.log 2>&1; then
    echo "  [PASS] run_sales_page_assets.py --self-test"
  else
    echo "  [FAIL] run_sales_page_assets.py --self-test"; sed 's/^/         /' /tmp/spa_orch.log; fails=$((fails+1))
  fi
  [ "$fails" -eq 0 ] || die "SELF-TEST" "$fails check(s) failed"
  echo "RESULT: PASS — entry self-test green."
}

write_pin() {
  step_deps
  compute_pin > "$PIN_FILE"
  echo "wrote pin: $PIN_FILE = $(tr -d '[:space:]' < "$PIN_FILE")"
}

main() {
  local mode="" rd=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --run-dir) rd="${2:-}"; shift 2 ;;
      --self-test) mode="selftest"; shift ;;
      --write-pin) mode="writepin"; shift ;;
      -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *) die "USAGE" "unknown arg: $1" ;;
    esac
  done
  case "$mode" in
    selftest) self_test ;;
    writepin) write_pin ;;
    *) run_pipeline "$rd" ;;
  esac
}

main "$@"
