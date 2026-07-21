#!/usr/bin/env bash
# ==============================================================================
# signature-funnel-entry.sh — the CANONICAL, fail-closed front door for Skill 49
# (Signature Funnel). NOTHING may generate copy/prompts, call Kie, touch GHL, or
# mint a certificate except THROUGH this shell. It performs, in order and all
# fail-closed:
#
#   1. DEPS        — python3 present (else abort).
#   2. VERSION     — skill-version.txt is present + non-empty (pinned major).
#   3. HASH-PIN    — recompute the sha256 of the enforcement core (provers +
#                    structure + orchestrator) and compare to SF-PROVER-PIN.sha256.
#                    A tampered prover / structure ledger dies here.
#   4. BYPASS-SCAN — refuse a run whose working files hand-roll GHL REST calls or
#                    mail/senders instead of delegating to Skill 6 / Skill 47.
#                    (Authorship + build MUST go through the delegated adapters.)
#   5. NONCE       — write a run-scoped 0600 front-door nonce; export SF_RUN_NONCE.
#   6. ORCHESTRATE — run_signature_funnel.py with the nonce (the no-skip state
#                    machine); it emits the signed PROCESS-CERTIFICATE only on
#                    all-phases-pass.
#
# Usage:
#   bash signature-funnel-entry.sh --run-dir <RUN_DIR>
#   bash signature-funnel-entry.sh --self-test
# Exit: 0 = certified / self-test green; nonzero = a fail-closed guard tripped.
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"
PIN_FILE="$SCRIPTS_DIR/SF-PROVER-PIN.sha256"
PY="${PYTHON:-python3}"
EXPECTED_MAJOR="1"

# Files whose integrity is pinned (the enforcement core). Order-independent: we
# hash each file's own sha256, then hash the sorted list of "sha256  name" lines.
PINNED_FILES=(
  "scripts/prove_sf_intake.py"
  "scripts/prove_sf_copy.py"
  "scripts/prove_sf_prompt_floor.py"
  "scripts/prove_sf_graph.py"
  "scripts/prove_sf_build.py"
  "scripts/prove_sf_no_pitch.py"
  "scripts/prove_sf_cert.py"
  "scripts/gate_integrity_check.py"
  "structure/funnel_structure.json"
  "run_signature_funnel.py"
  # A10 / T0-09, T0-10 — the delegated-phase receipt contract is enforcement core:
  # the P-IMAGES/-MEDIA/-DOCS/-DELIVER/-HANDOFF seams call require()/validate_if_present(),
  # so an unpinned copy could be swapped for a permissive one without tripping the pin.
  "scripts/delegation_receipt.py"
)

# Forbidden patterns in a run's working files — a hand-rolled GHL/sender bypass.
# Extended regex; matched case-insensitively across the run dir (NOT the skill dir).
BYPASS_PATTERNS='services\.leadconnectorhq\.com|rest\.gohighlevel\.com|api\.gohighlevel\.com|smtplib|sendgrid|mailgun|nodemailer|ses\.send_email|send_raw_email|api\.kie\.ai.*createtask|createtask.*api\.kie\.ai'

die() { printf 'ABORT [%s]: %s\n' "$1" "$2" >&2; exit 1; }

compute_pin() {
  # Print the canonical pin digest for the current PINNED_FILES content.
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
    die "HASH-PIN" "pin file missing: $PIN_FILE (run: bash signature-funnel-entry.sh --write-pin to mint it)"
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
      die "BYPASS-SCAN" "run working files hand-roll GHL REST / a mail sender / a raw Kie createTask. All GHL build+media go through Skill 6; all image gen goes through Skill 47. Delete the hand-rolled path."
    fi
  fi
}

step_nonce() {
  local rd="$1"
  local nonce; nonce="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  local nf="$rd/.sf_run_nonce"
  ( umask 077; printf '%s' "$nonce" > "$nf" )
  chmod 600 "$nf"
  printf '%s' "$nonce"
}

# FIX-XC-09e — resolve the CLIENT's own execution-tier authoring model (role=content),
# record routing/model-content-receipt.json, and gate it (fail-closed) via prove_sf_cert
# --model-receipt. The client's OWN strongest model writes the copy; Anthropic is hard-banned.
step_model_receipt() {
  local rd="$1"
  "$PY" - "$rd" <<'PYEOF'
import json, os, sys, datetime
rd = sys.argv[1]
# Client-chain resolver seam: reuse model_router.select(role="content") semantics against the
# CLIENT's providers. Operator/orchestrator supplies the resolved id via env (never Anthropic).
model = os.environ.get("SF_CONTENT_MODEL", "")
provider = os.environ.get("SF_CONTENT_PROVIDER", "")
tier = os.environ.get("SF_CONTENT_TIER", "content")
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
  "$PY" "$SCRIPTS_DIR/prove_sf_cert.py" --model-receipt "$rd/routing/model-content-receipt.json" \
    || die "MODEL-TIER" "content-authoring model receipt failed the execution-tier / no-Anthropic gate — set SF_CONTENT_MODEL + SF_CONTENT_PROVIDER (+ SF_CONTENT_TIER) to the CLIENT's own strongest model"
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
  export SF_RUN_NONCE="$nonce"
  echo "== signature-funnel-entry :: front door cleared (deps/version/hash-pin/bypass/model-tier/nonce) =="
  "$PY" "$SKILL_DIR/run_signature_funnel.py" --run-dir "$rd" --nonce "$nonce"
}

self_test() {
  echo "== signature-funnel-entry :: --self-test =="
  step_deps
  step_version
  if [ -f "$PIN_FILE" ]; then step_hashpin; echo "  [PASS] hash-pin verified"; else echo "  [WARN] no pin file yet (mint with --write-pin)"; fi
  local fails=0
  for p in prove_sf_intake prove_sf_copy prove_sf_prompt_floor prove_sf_graph prove_sf_build prove_sf_no_pitch prove_sf_cert; do
    if "$PY" "$SCRIPTS_DIR/$p.py" --self-test >/tmp/sf_$p.log 2>&1; then
      echo "  [PASS] $p.py --self-test"
    else
      echo "  [FAIL] $p.py --self-test"; sed 's/^/         /' "/tmp/sf_$p.log"; fails=$((fails+1))
    fi
  done
  if "$PY" "$SKILL_DIR/run_signature_funnel.py" --self-test >/tmp/sf_orch.log 2>&1; then
    echo "  [PASS] run_signature_funnel.py --self-test"
  else
    echo "  [FAIL] run_signature_funnel.py --self-test"; sed 's/^/         /' /tmp/sf_orch.log; fails=$((fails+1))
  fi
  # FIX-XC-05a — gate-integrity harness: (re)emit the negative-test coverage, then
  # prove DECLARED == ENFORCED == TESTED for every python-enforced autofail.
  if "$PY" "$SCRIPTS_DIR/test_sf_gate_coverage.py" >/tmp/sf_cov.log 2>&1 \
     && "$PY" "$SCRIPTS_DIR/gate_integrity_check.py" >/tmp/sf_gic.log 2>&1; then
    echo "  [PASS] gate_integrity_check.py (declared==enforced==tested)"
  else
    echo "  [FAIL] gate_integrity_check.py"; sed 's/^/         /' /tmp/sf_cov.log /tmp/sf_gic.log; fails=$((fails+1))
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
