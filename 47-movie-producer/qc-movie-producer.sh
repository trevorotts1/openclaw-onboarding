#!/usr/bin/env bash
# Skill 47 — Movie Producer (Automated Video Production) — Install QC
# ("OpenMontage" below = the UPSTREAM engine cloned onto the client box; the skill dir is 47-movie-producer/.)
# Mirrors the fail-loud pattern from Skill 26 (caption-creator) and
# the presentation-deps-gate.yml CI gate.
#
# TWO-PHASE / INSTALL-STATE-AWARE (v13.8.19):
#   The OpenMontage clone (its source tree, remotion-composer/node_modules, the
#   in-clone .env / config.yaml, and the adapters copied INTO the clone) only
#   exists AFTER install.sh has run on a real box. A repo / CI run has NONE of
#   those. So this gate scores the things that are TRUE IN BOTH STATES as HARD
#   assertions (system binaries, the skill payload structure, the Kie adapter
#   SOURCE files shipped in this folder, the no-vendoring boundary, the SOP DMAIC
#   headers) and treats the clone-dependent checks as:
#     - HARD assertions when the clone IS present (post-install client box), and
#     - informational PRE-INSTALL notes when the clone is ABSENT (repo / CI).
#   Result: `bash qc-movie-producer.sh` exits 0 in the repo / CI AND on a
#   fully-installed client box, and FAILS loudly only on a genuine defect (a real
#   missing binary, a broken adapter, vendored AGPLv3 source, or a post-install
#   box with a broken clone). This is the receipt the rubric's 1C requires.
set -u
PASS=0; FAIL=0; WARN=0; PREFLAG=0
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
blue()   { printf "\033[34m%s\033[0m\n" "$1"; }

assert() {
  if eval "$2" >/dev/null 2>&1; then
    green "  PASS -- $1"; PASS=$((PASS+1))
  else
    red   "  FAIL -- $1"; FAIL=$((FAIL+1))
  fi
}

warn_only() {
  if eval "$2" >/dev/null 2>&1; then
    green  "  PASS -- $1"; PASS=$((PASS+1))
  else
    yellow "  WARN -- $1 (non-blocking)"; WARN=$((WARN+1))
  fi
}

# pre_or_hard: when the OpenMontage clone is present (post-install), this is a HARD
# assertion; when the clone is absent (repo / CI), it is a non-blocking PRE-INSTALL
# note (the artifact legitimately does not exist yet).
pre_or_hard() {
  if [ "$CLONE_PRESENT" = "1" ]; then
    assert "$1" "$2"
  else
    if eval "$2" >/dev/null 2>&1; then
      green "  PASS -- $1"; PASS=$((PASS+1))
    else
      blue  "  PRE  -- $1 (pre-install: produced at install time)"; PREFLAG=$((PREFLAG+1))
    fi
  fi
}

# The skill folder is THIS dir (works whether run from the repo or from an installed
# ~/.openclaw/skills/47-movie-producer/ copy).
SELF_SKILL_DIR="$SKILL_DIR"
# The installed-clone path (only exists post-install).
# v14.0.1: the clone lives OUTSIDE the hashed skill dir (A3 content-hash fix), in a
# sibling runtime dir, so a ~56MB clone can never break the skill's content hash.
# Honor the OPENCLAW_OPENMONTAGE_DIR override first (matches install.sh).
CLONE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"
CLONE_PRESENT=0; [ -d "${CLONE_DIR}" ] && CLONE_PRESENT=1

# The Kie adapter SOURCE files always live in the skill payload (this folder),
# regardless of install state. These are OUR files (not OpenMontage source).
ADAPTER_IMG_SRC="${SELF_SKILL_DIR}/kie-adapters/tools/graphics/kie_image.py"
ADAPTER_VID_SRC="${SELF_SKILL_DIR}/kie-adapters/tools/video/kie_video.py"

echo ""
echo "=== Skill 47 -- Movie Producer (Automated Video Production) -- Install QC ==="
if [ "$CLONE_PRESENT" = "1" ]; then
  echo "    (mode: POST-INSTALL — OpenMontage clone present; clone checks are HARD)"
else
  echo "    (mode: PRE-INSTALL / CI — OpenMontage clone absent; clone checks are PRE notes)"
fi
echo ""

# ---- System binaries (HARD FAIL if missing — needed in BOTH states) ----
assert "ffmpeg installed"  "command -v ffmpeg"
assert "ffprobe installed" "command -v ffprobe"
assert "node installed"    "command -v node"
assert "npx installed"     "command -v npx"
assert "python3 installed" "command -v python3"
assert "git installed"     "command -v git"

# ---- Node version >= 18 (HARD FAIL) ----
assert "node >= 18" "node -e 'process.exit(parseInt(process.versions.node.split(\".\")[0]) >= 18 ? 0 : 1)'"

# ---- Skill payload structure (HARD — always present in repo + post-install) ----
assert "SKILL.md present"        "[ -f \"${SELF_SKILL_DIR}/SKILL.md\" ]"
assert "INSTALL.md present"      "[ -f \"${SELF_SKILL_DIR}/INSTALL.md\" ]"
assert "INSTRUCTIONS.md present" "[ -f \"${SELF_SKILL_DIR}/INSTRUCTIONS.md\" ]"
assert "EXAMPLES.md present"     "[ -f \"${SELF_SKILL_DIR}/EXAMPLES.md\" ]"
assert "CORE_UPDATES.md present" "[ -f \"${SELF_SKILL_DIR}/CORE_UPDATES.md\" ]"
assert "skill-version.txt present" "[ -f \"${SELF_SKILL_DIR}/skill-version.txt\" ]"
assert "install.sh present"      "[ -f \"${SELF_SKILL_DIR}/install.sh\" ]"
assert "preflight.sh present"    "[ -f \"${SELF_SKILL_DIR}/preflight.sh\" ]"
assert "verify-deps.sh present"  "[ -f \"${SELF_SKILL_DIR}/verify-deps.sh\" ]"
assert "DEPENDENCY-MANIFEST.md present" "[ -f \"${SELF_SKILL_DIR}/DEPENDENCY-MANIFEST.md\" ]"
assert "movie-producer.skill bundle present" "[ -f \"${SELF_SKILL_DIR}/movie-producer.skill\" ]"

# ---- Kie adapter SOURCE files in the skill payload (HARD — always present) ----
assert "kie_image.py source present in skill payload" "[ -f \"${ADAPTER_IMG_SRC}\" ]"
assert "kie_video.py source present in skill payload" "[ -f \"${ADAPTER_VID_SRC}\" ]"
assert "kie_image.py source parses (no syntax errors)" \
  "python3 -c \"import ast; ast.parse(open('${ADAPTER_IMG_SRC}').read())\""
assert "kie_video.py source parses (no syntax errors)" \
  "python3 -c \"import ast; ast.parse(open('${ADAPTER_VID_SRC}').read())\""
assert "kie_image.py source declares provider=kie" \
  "grep -Eq 'provider[[:space:]]*=[[:space:]]*.kie.' \"${ADAPTER_IMG_SRC}\""
assert "kie_video.py source declares provider=kie" \
  "grep -Eq 'provider[[:space:]]*=[[:space:]]*.kie.' \"${ADAPTER_VID_SRC}\""
assert "kie_image.py source declares image_generation capability" \
  "grep -Eq 'capability[[:space:]]*=[[:space:]]*.image_generation.' \"${ADAPTER_IMG_SRC}\""
assert "kie_video.py source declares video_generation capability" \
  "grep -Eq 'capability[[:space:]]*=[[:space:]]*.video_generation.' \"${ADAPTER_VID_SRC}\""
assert "kie_image.py source uses the fleet gpt-image-2-image-to-image model id" \
  "grep -q 'gpt-image-2-image-to-image' \"${ADAPTER_IMG_SRC}\""
assert "kie_video.py source uses the fleet gemini-omni-video model id" \
  "grep -q 'gemini-omni-video' \"${ADAPTER_VID_SRC}\""
assert "kie_video.py source uses the fleet veo3_fast fallback model id" \
  "grep -q 'veo3_fast' \"${ADAPTER_VID_SRC}\""
assert "kie_image.py source gates on KIE_API_KEY (not an operator key value)" \
  "grep -q 'KIE_API_KEY' \"${ADAPTER_IMG_SRC}\""
assert "kie_video.py source gates on KIE_API_KEY (not an operator key value)" \
  "grep -q 'KIE_API_KEY' \"${ADAPTER_VID_SRC}\""

# ---- No operator KIE_API_KEY value committed in the skill payload (HARD) ----
assert "No literal operator KIE_API_KEY value committed in skill payload" \
  "! grep -rIE 'KIE_API_KEY\\s*=\\s*[\"'\"'\"']?[A-Za-z0-9]{20,}' \"${SELF_SKILL_DIR}\" 2>/dev/null | grep -qv 'YOUR_CLIENT_KIE_API_KEY_HERE'"

# ---- No OpenMontage AGPLv3 source vendored into the skill payload (HARD) ----
assert "No tools/ dir at skill payload root (no AGPLv3 source vendored)" \
  "[ ! -d \"${SELF_SKILL_DIR}/tools\" ] || [ -d \"${SELF_SKILL_DIR}/kie-adapters/tools\" ]"
assert "No pipeline_defs/ in skill payload (no AGPLv3 source vendored)" \
  "[ ! -d \"${SELF_SKILL_DIR}/pipeline_defs\" ]"
assert "No remotion-composer/ in skill payload (no AGPLv3 source vendored)" \
  "[ ! -d \"${SELF_SKILL_DIR}/remotion-composer\" ]"
assert "kie-adapters payload carries ONLY our two adapter files (no OpenMontage source)" \
  "[ \"\$(find \"${SELF_SKILL_DIR}/kie-adapters/tools\" -name '*.py' | wc -l | tr -d ' ')\" = '2' ]"

# ---- SOP DMAIC headers (HARD — the standalone SOP must satisfy the gate regex) ----
# Resolve the role-library video SOP relative to the repo root (skill folder is a
# sibling of 23-ai-workforce-blueprint/ in the repo). Post-install it may be absent;
# treat absent as a PRE note, present-but-missing-DMAIC as a HARD fail.
SOP_FILE="${SELF_SKILL_DIR}/../23-ai-workforce-blueprint/templates/role-library/video/sops/SOP--automated-video-production-specialist-openmontage-sops.md"
if [ -f "${SOP_FILE}" ]; then
  assert "OpenMontage SOP carries all 5 DMAIC '## Define/Measure/Analyze/Improve/Control' headers (gate regex)" \
    "python3 -c \"
import re,sys
t=open('${SOP_FILE}').read()
rx=re.compile(r'^#{1,4}\\\\s*(define|measure|analyze|improve|control)\\\\b', re.I|re.M)
found={m.group(1).lower() for m in rx.finditer(t)}
sys.exit(0 if {'define','measure','analyze','improve','control'} <= found else 1)\""
else
  blue "  PRE  -- OpenMontage SOP DMAIC-header check (SOP not present beside this install copy)"; PREFLAG=$((PREFLAG+1))
fi

# ---- Python deps (HARD: needed in both states once make setup / pip ran; many boxes
#      already have these system-wide. Soft on a bare CI runner via warn_only.) ----
warn_only "PyYAML importable (installed by make setup)"   "python3 -c 'import yaml'"
warn_only "pydantic importable (installed by make setup)" "python3 -c 'import pydantic'"
warn_only "Pillow importable (installed by make setup)"   "python3 -c 'import PIL'"
warn_only "requests importable (installed by make setup)" "python3 -c 'import requests'"
warn_only "jsonschema importable (installed by make setup)" "python3 -c 'import jsonschema'"

# ---- HyperFrames (npm via npx) — warn_only (network-dependent on a fresh box) ----
warn_only "npx hyperframes resolves (cache-warmed by make setup)" "npx --yes hyperframes --version >/dev/null 2>&1"

# ---- Piper TTS (soft-fail: missing is WARN not FAIL) ----
warn_only "piper-tts importable (soft-fail: cloud TTS fallback if missing)" \
  "python3 -c 'import piper'"

echo ""
echo "--- Clone-dependent checks (HARD post-install / PRE-INSTALL note in repo+CI) ---"

# ---- OpenMontage clone ----
pre_or_hard "OpenMontage cloned at install path" "[ -d \"${CLONE_DIR}\" ]"
pre_or_hard "OpenMontage remote is calesthio/OpenMontage" \
  "git -C \"${CLONE_DIR}\" remote get-url origin 2>/dev/null | grep -q 'calesthio/OpenMontage'"

# ---- make setup outputs (clone-dependent) ----
pre_or_hard "Remotion node_modules present in clone" "[ -d \"${CLONE_DIR}/remotion-composer/node_modules\" ]"

# ---- Kie adapters copied INTO the clone (clone-dependent) ----
pre_or_hard "kie_image.py installed into clone tools/graphics/" \
  "[ -f \"${CLONE_DIR}/tools/graphics/kie_image.py\" ]"
pre_or_hard "kie_video.py installed into clone tools/video/" \
  "[ -f \"${CLONE_DIR}/tools/video/kie_video.py\" ]"

# ---- config.yaml budget cap in the clone (clone-dependent) ----
pre_or_hard "config.yaml exists in clone" "[ -f \"${CLONE_DIR}/config.yaml\" ]"
pre_or_hard "config.yaml has budget.mode: cap" \
  "python3 -c \"import yaml; c=yaml.safe_load(open('${CLONE_DIR}/config.yaml')); exit(0 if c.get('budget',{}).get('mode')=='cap' else 1)\""

# ---- No operator key value in the clone .env (clone-dependent) ----
pre_or_hard "No operator KIE_API_KEY value in clone .env (only var name / client placeholder)" \
  "! grep -E '^KIE_API_KEY=.+' \"${CLONE_DIR}/.env\" 2>/dev/null | grep -v 'YOUR_CLIENT_KIE_API_KEY_HERE' | grep -qE '=[A-Za-z0-9]{20,}'"

echo ""
echo "--- v14.1.0 anti-bypass enforcement layer (HARD — always present in repo + post-install) ---"

# The enforcement spine: manifest (single source of truth) + driver + receipt
# validators + ruleset + lockstep/Guard-A/test + GOOD/BAD fixtures + CI workflow.
REPO_ROOT_QC="${SELF_SKILL_DIR}/.."
VID_MANIFEST="${REPO_ROOT_QC}/universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json"
VID_RULESET="${REPO_ROOT_QC}/universal-sops/video-pipeline-craft/MASTER-VIDEO-QC-AUTOFAIL-RULESET.md"
VID_DRIVER="${SELF_SKILL_DIR}/scripts/executive_producer.py"
VID_BUILDCHK="${SELF_SKILL_DIR}/scripts/video_build_check.py"
VID_SYNC="${SELF_SKILL_DIR}/scripts/video_sync_check.py"
VID_GUARDA="${SELF_SKILL_DIR}/scripts/video_gate_integrity_check.py"
VID_TEST="${SELF_SKILL_DIR}/scripts/test_video_preflight.py"
VID_FIXTURES="${SELF_SKILL_DIR}/test-fixtures/make-video-fixtures.sh"
VID_CI="${REPO_ROOT_QC}/.github/workflows/video-pipeline-lockstep.yml"

assert "VIDEO-PIPELINE-MANIFEST.json present (single source of truth)" "[ -f \"${VID_MANIFEST}\" ]"
assert "MASTER-VIDEO-QC-AUTOFAIL-RULESET.md present" "[ -f \"${VID_RULESET}\" ]"
assert "executive_producer.py driver present" "[ -f \"${VID_DRIVER}\" ]"
assert "video_build_check.py receipt validators present" "[ -f \"${VID_BUILDCHK}\" ]"
assert "video_sync_check.py lockstep present" "[ -f \"${VID_SYNC}\" ]"
assert "video_gate_integrity_check.py (Guard A) present" "[ -f \"${VID_GUARDA}\" ]"
assert "test_video_preflight.py negative-test suite present" "[ -f \"${VID_TEST}\" ]"
assert "make-video-fixtures.sh GOOD/BAD fixtures present" "[ -f \"${VID_FIXTURES}\" ]"
assert "video-pipeline-lockstep.yml CI workflow present" "[ -f \"${VID_CI}\" ]"

# The enforcement code must parse.
assert "executive_producer.py parses" "python3 -c \"import ast; ast.parse(open('${VID_DRIVER}').read())\""
assert "video_build_check.py parses" "python3 -c \"import ast; ast.parse(open('${VID_BUILDCHK}').read())\""

# The manifest must declare exactly the 5 DMAIC phases in ascending order.
assert "VIDEO-PIPELINE-MANIFEST declares 5 ordered DMAIC phases (V-DEFINE..V-CONTROL)" \
  "python3 -c \"
import json,sys
m=json.load(open('${VID_MANIFEST}'))
ids=[p['id'] for p in sorted(m['phases'],key=lambda p:p['order'])]
sys.exit(0 if ids==['V-DEFINE','V-MEASURE','V-ANALYZE','V-IMPROVE','V-CONTROL'] else 1)\""

# Lockstep + Guard A must pass (manifest<->driver<->ruleset in sync; every gate tested).
assert "video_sync_check.py — manifest/code/ruleset LOCKSTEP (exit 0)" \
  "python3 \"${VID_SYNC}\" >/dev/null 2>&1"
assert "test_video_preflight.py — every gate negative-tested (exit 0, emits af-coverage)" \
  "python3 \"${VID_TEST}\" >/dev/null 2>&1"
assert "video_gate_integrity_check.py — Guard A declared==enforced==tested (exit 0)" \
  "python3 \"${VID_GUARDA}\" >/dev/null 2>&1"

# The driver must HARD-ABORT a bypass (AF-VID-PHASE-SKIPPED) and ATTEST a complete run.
QC_TMP="$(mktemp -d 2>/dev/null || echo /tmp/mp-qc-$$)"
if [ -f "${VID_FIXTURES}" ]; then
  bash "${VID_FIXTURES}" "${QC_TMP}/vfix" >/dev/null 2>&1
  assert "driver HARD-ABORTS the BAD bypass run (AF-VID-PHASE-SKIPPED, exit 2)" \
    "python3 \"${VID_DRIVER}\" --run-dir \"${QC_TMP}/vfix/bad-run\" --phase V-IMPROVE >/dev/null 2>&1; [ \$? -eq 2 ]"
  # GOOD run: attest the free path through every phase; final V-CONTROL must be exit 0.
  GOOD_OK=1
  for ph in V-DEFINE V-MEASURE V-IMPROVE V-CONTROL; do
    python3 "${VID_DRIVER}" --run-dir "${QC_TMP}/vfix/good-run" --phase "$ph" >/dev/null 2>&1 || GOOD_OK=0
  done
  assert "driver ATTESTS the GOOD run through V-CONTROL (exit 0 each phase)" "[ \"${GOOD_OK}\" = 1 ]"
  rm -rf "${QC_TMP}" 2>/dev/null
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed | $WARN warnings | $PREFLAG pre-install notes ==="
[ "$FAIL" -gt 0 ] && { red "Skill 47 QC FAILED"; exit 1; } || { green "Skill 47 QC PASS"; exit 0; }
