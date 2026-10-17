#!/usr/bin/env bash
# Skill 48 — Facebook & Instagram Ad Generator — Install QC (fail-loud).
# Mirrors qc-movie-producer.sh: scores the things TRUE IN BOTH the repo/CI state and a
# post-install client box as HARD assertions. Exits 0 in repo/CI AND on an installed
# box; FAILS loudly only on a real defect.
set -u
PASS=0; FAIL=0; WARN=0; PREFLAG=0
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${SKILL_DIR}/.."
# FIX-PRF-001 (replaces the FIX-S36-38 directory marker): repo-level artifacts resolve
# through a PER-FILE candidate chain, never through "[ -d .github ] || [ -d .git ]". A
# deployed box can carry a STALE $REPO_ROOT/.github/ tree while the SPECIFIC asserted
# files are absent, and the old directory gate then re-armed the original client-install
# aborts (it could also silently skip an assertion that had to run). resolve_repo_path
# <relative/path> returns the FIRST existing candidate, in order:
#   (1) $REPO_ROOT/<path>
#   (2) $HOME/.openclaw/onboarding/<path>
#   (3) scripts/ paths only: $HOME/.openclaw/scripts/<path> (scripts/-stripped, then bare)
# It prints nothing and returns 1 when no candidate exists, so every caller below turns
# that into a loud FAIL: nothing passes and nothing silently skips.
resolve_repo_path() {
  local _rel="$1" _c
  for _c in "${REPO_ROOT}/${_rel}" "${HOME}/.openclaw/onboarding/${_rel}"; do
    [ -f "${_c}" ] && { printf '%s\n' "${_c}"; return 0; }
  done
  case "${_rel}" in
    scripts/*)
      for _c in "${HOME}/.openclaw/scripts/${_rel#scripts/}" "${HOME}/.openclaw/scripts/${_rel}"; do
        [ -f "${_c}" ] && { printf '%s\n' "${_c}"; return 0; }
      done
      ;;
  esac
  return 1
}

red()   { printf "\033[31m%s\033[0m\n" "$1"; }
green() { printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
blue()  { printf "\033[34m%s\033[0m\n" "$1"; }

assert() {
  if eval "$2" >/dev/null 2>&1; then green "  PASS -- $1"; PASS=$((PASS+1));
  else red "  FAIL -- $1"; FAIL=$((FAIL+1)); fi
}
warn_only() {
  if eval "$2" >/dev/null 2>&1; then green "  PASS -- $1"; PASS=$((PASS+1));
  else yellow "  WARN -- $1 (non-blocking)"; WARN=$((WARN+1)); fi
}

echo ""
echo "=== Skill 48 -- Facebook & Instagram Ad Generator -- Install QC ==="
echo ""

# ---- System deps ----
assert "python3 installed" "command -v python3"

# ---- Skill payload structure ----
for f in SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md \
         skill-version.txt install.sh preflight.sh verify-deps.sh \
         DEPENDENCY-MANIFEST.md facebook-ad-generator.skill; do
  assert "$f present" "[ -f \"${SKILL_DIR}/$f\" ]"
done

# ---- The enforcement spine (single source of truth + foreman + checks + ruleset) ----
AD_MANIFEST="$(resolve_repo_path "universal-sops/fb-ad-craft/AD-PIPELINE-MANIFEST.json")"
AD_RULESET="$(resolve_repo_path "universal-sops/fb-ad-craft/MASTER-AD-QC-AUTOFAIL-RULESET.md")"
AD_DRIVER="${SKILL_DIR}/scripts/ad_director.py"
AD_BUILDCHK="${SKILL_DIR}/scripts/ad_build_check.py"
AD_SYNC="${SKILL_DIR}/scripts/ad_sync_check.py"
AD_GUARDA="${SKILL_DIR}/scripts/ad_gate_integrity_check.py"
AD_TEST="${SKILL_DIR}/scripts/test_ad_preflight.py"
AD_RECOVERY="${SKILL_DIR}/scripts/ad_recovery.py"
AD_RECOVERY_TEST="${SKILL_DIR}/scripts/test_ad_recovery.py"
CC_BOARD="${SKILL_DIR}/scripts/cc_board.py"
CC_BOARD_TEST="${SKILL_DIR}/scripts/test_cc_board.py"
AD_MODELSOV="${SKILL_DIR}/scripts/ad_model_sovereignty.py"
AD_UNPARK="$(resolve_repo_path "scripts/unpark-ad-run.sh")"
AD_FIXTURES="${SKILL_DIR}/test-fixtures/make-ad-fixtures.sh"
# Paid fixtures need a synthetic key + stubbed balance (a keyless paid run aborts, exit 4).
AD_STUB="${SKILL_DIR}/test-fixtures/run-foreman-stubbed.py"
AD_CI="$(resolve_repo_path ".github/workflows/ad-pipeline-lockstep.yml")"

assert "AD-PIPELINE-MANIFEST.json present (single source of truth)" "[ -f \"${AD_MANIFEST}\" ]"
assert "MASTER-AD-QC-AUTOFAIL-RULESET.md present" "[ -f \"${AD_RULESET}\" ]"
assert "ad_director.py foreman present" "[ -f \"${AD_DRIVER}\" ]"
assert "ad_build_check.py receipt validators present" "[ -f \"${AD_BUILDCHK}\" ]"
assert "ad_sync_check.py lockstep present" "[ -f \"${AD_SYNC}\" ]"
assert "ad_gate_integrity_check.py (Guard A) present" "[ -f \"${AD_GUARDA}\" ]"
assert "test_ad_preflight.py negative-test suite present" "[ -f \"${AD_TEST}\" ]"
assert "ad_recovery.py self-correct/park engine present" "[ -f \"${AD_RECOVERY}\" ]"
assert "test_ad_recovery.py recovery proof suite present" "[ -f \"${AD_RECOVERY_TEST}\" ]"
assert "cc_board.py producer-side board caller present" "[ -f \"${CC_BOARD}\" ]"
assert "test_cc_board.py board-caller test suite present" "[ -f \"${CC_BOARD_TEST}\" ]"
assert "ad_model_sovereignty.py no-Anthropic/model-tier gate present" "[ -f \"${AD_MODELSOV}\" ]"
if [ -n "${AD_UNPARK}" ]; then
  assert "unpark-ad-run.sh operator un-park tool present" "[ -f \"${AD_UNPARK}\" ]"
else
  red "  FAIL -- unpark-ad-run.sh operator un-park tool present (no candidate resolved: \$REPO_ROOT, ~/.openclaw/onboarding, ~/.openclaw/scripts)"; FAIL=$((FAIL+1))
fi
assert "make-ad-fixtures.sh GOOD/BAD fixtures present" "[ -f \"${AD_FIXTURES}\" ]"
if [ -n "${AD_CI}" ]; then
  assert "ad-pipeline-lockstep.yml CI workflow present" "[ -f \"${AD_CI}\" ]"
else
  red "  FAIL -- ad-pipeline-lockstep.yml CI workflow present (no candidate resolved: \$REPO_ROOT, ~/.openclaw/onboarding)"; FAIL=$((FAIL+1))
fi

# ---- The enforcement code must parse ----
for py in "${AD_DRIVER}" "${AD_BUILDCHK}" "${AD_SYNC}" "${AD_GUARDA}" "${AD_TEST}" \
          "${AD_RECOVERY}" "${AD_RECOVERY_TEST}" "${AD_MODELSOV}"; do
  assert "$(basename "$py") parses" "python3 -c \"import ast; ast.parse(open('${py}').read())\""
done
if [ -n "${AD_UNPARK}" ]; then
  assert "unpark-ad-run.sh is valid bash" "bash -n \"${AD_UNPARK}\""
else
  red "  FAIL -- unpark-ad-run.sh is valid bash (no candidate resolved; bash -n is never run on an empty path)"; FAIL=$((FAIL+1))
fi

# ---- The 8 creative SOPs exist ----
for n in 01-INTAKE 02-OVERLAYS 03-PICK-10 04-PRIMARY-TEXT 05-HEADLINES \
         06-IMAGE-PROMPTS 07-TARGETING 08-DELIVERY; do
  AD_SOP_N="$(resolve_repo_path "universal-sops/fb-ad-craft/SOP-FBAD-${n}.md")"
  assert "SOP-FBAD-${n}.md present" "[ -f \"${AD_SOP_N}\" ]"
done

# ---- The 2 new role seats exist ----
AD_ROLE_PRODUCER="$(resolve_repo_path "23-ai-workforce-blueprint/templates/role-library/paid-advertisement/facebook-instagram-ad-run-producer.md")"
AD_ROLE_COPYWRITER="$(resolve_repo_path "23-ai-workforce-blueprint/templates/role-library/paid-advertisement/direct-response-ad-copywriter.md")"
assert "facebook-instagram-ad-run-producer role present" "[ -f \"${AD_ROLE_PRODUCER}\" ]"
assert "direct-response-ad-copywriter role present" "[ -f \"${AD_ROLE_COPYWRITER}\" ]"

# ---- The manifest must declare the 10 ordered stages ----
assert "AD-PIPELINE-MANIFEST declares 10 ordered stages (S0-INTAKE..PUBLISH)" \
  "python3 -c \"
import json,sys
m=json.load(open('${AD_MANIFEST}'))
ids=[p['id'] for p in sorted(m['phases'],key=lambda p:p['order'])]
sys.exit(0 if ids==['S0-INTAKE','S1-OVERLAYS','PICK-10','S2-PRIMARY-TEXT','S3-HEADLINES','S4-IMAGE-PROMPTS','S5-IMAGE-GEN','S6-TARGETING','S7-DELIVER','PUBLISH'] else 1)\""

# ---- Every autofail must declare a recovery policy (two-tier self-correct/park) ----
assert "every AD-PIPELINE-MANIFEST autofail carries a recovery field (auto|park)" \
  "python3 -c \"
import json,sys
m=json.load(open('${AD_MANIFEST}'))
bad=[a['code'] for a in m['autofails'] if a.get('recovery') not in ('auto','park')]
sys.exit(0 if (not bad and isinstance(m.get('recovery_policy'),dict)) else 1)\""

# ---- Lockstep + negative suite + recovery suite + Guard A must pass ----
assert "ad_sync_check.py — manifest/code/ruleset LOCKSTEP incl recovery R1-R4 (exit 0)" \
  "python3 \"${AD_SYNC}\" >/dev/null 2>&1"
assert "test_ad_preflight.py — every gate negative-tested (exit 0, emits af-coverage)" \
  "python3 \"${AD_TEST}\" >/dev/null 2>&1"
assert "test_ad_recovery.py — self-correct/park proven (exit 0, emits recovery-coverage)" \
  "python3 \"${AD_RECOVERY_TEST}\" >/dev/null 2>&1"
assert "test_cc_board.py — board caller fail-soft + auth/HMAC parity + legal-path (exit 0)" \
  "python3 \"${CC_BOARD_TEST}\" >/dev/null 2>&1"
assert "test_kie_install_note.py — installs with or without a KIE key; any store/alias; placeholder never shadows a real key (exit 0)" \
  "python3 \"${SKILL_DIR}/scripts/test_kie_install_note.py\" >/dev/null 2>&1"
assert "ad_gate_integrity_check.py — Guard A declared==enforced==tested+recovery (exit 0)" \
  "python3 \"${AD_GUARDA}\" >/dev/null 2>&1"
assert "test_kie_adapter_resultjson_decode.py — Skill 48 rides the Skill 47 adapters (Skill 74 transport): result extraction proven (exit 0)" \
  "python3 \"${SKILL_DIR}/scripts/test_kie_adapter_resultjson_decode.py\" >/dev/null 2>&1"
assert "ad_model_sovereignty.py — model-content-receipt + no-Anthropic gate (self-test exit 0)" \
  "python3 \"${AD_MODELSOV}\" --self-test >/dev/null 2>&1"

# ---- The foreman must HARD-ABORT a bypass and ATTEST a complete run ----
QC_TMP="$(mktemp -d 2>/dev/null || echo /tmp/fbad-qc-$$)"
if [ -f "${AD_FIXTURES}" ]; then
  bash "${AD_FIXTURES}" "${QC_TMP}/adfix" >/dev/null 2>&1
  assert "foreman HARD-ABORTS the BAD bypass run (AF-FBAD-DEP-SKIPPED, exit 2)" \
    "python3 \"${AD_STUB}\" \"${QC_TMP}/adfix/bad-run\" S5-IMAGE-GEN >/dev/null 2>&1; [ \$? -eq 2 ]"
  GOOD_OK=1
  for ph in S0-INTAKE S1-OVERLAYS PICK-10 S2-PRIMARY-TEXT S3-HEADLINES S4-IMAGE-PROMPTS S5-IMAGE-GEN S6-TARGETING S7-DELIVER PUBLISH; do
    python3 "${AD_STUB}" "${QC_TMP}/adfix/good-run" "$ph" >/dev/null 2>&1 || GOOD_OK=0
  done
  assert "foreman ATTESTS the GOOD run through PUBLISH (exit 0 each phase)" "[ \"${GOOD_OK}\" = 1 ]"
  rm -rf "${QC_TMP}" 2>/dev/null
fi

# ---- No literal client GHL/Kie key value committed in the skill payload ----
assert "No literal long API-key value committed in skill payload" \
  "! grep -rIE '(KIE_API_KEY|GOHIGHLEVEL_API_KEY)\\s*=\\s*[\"'\"'\"']?[A-Za-z0-9]{20,}' \"${SKILL_DIR}\" 2>/dev/null | grep -qv 'YOUR_CLIENT'"

echo ""
echo "=== Result: $PASS passed | $FAIL failed | $WARN warnings | $PREFLAG pre-install notes ==="
[ "$FAIL" -gt 0 ] && { red "Skill 48 QC FAILED"; exit 1; } || { green "Skill 48 QC PASS"; exit 0; }
