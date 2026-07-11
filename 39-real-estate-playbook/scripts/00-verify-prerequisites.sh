#!/usr/bin/env bash
# 00-verify-prerequisites.sh — Skill 39 (Real Estate Playbook)
# Verifies install prerequisites BEFORE any RE step runs.
#
# Governed by ../../QC-PROTOCOL.md (Sub-Agent Handoff + Mandatory QC Protocol).
#   - Category 10: presence + functional checks; halt with a clear error.
#
# Read-only (never writes). Idempotent. OS-aware Darwin + Linux.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P="[skill 39][prereq]"

# ---- Section E — INDUSTRY GATE (FAIL CLOSED) -------------------------------
# Skill 39 is the real-estate vertical. It must NEVER install/wire on a box
# whose captured industry is not real estate — unknown/absent industry means
# do NOT proceed (fail closed). This runs FIRST (before the other prereq
# checks below) so a non-real-estate box short-circuits without needing Skill
# 38 / jq / curl to even be present. See shared-utils/industry-gate.sh for the
# full gate-key + fail-closed contract (root cause: fix/industry-gate-and-idempotent-crons).
#
# exit 2 is RESERVED for this "industry mismatch — skip skill" outcome, kept
# distinct from exit 1 (a genuine missing hard prerequisite below).
_GATE_LIB=""
for _cand in \
  "$SKILL_ROOT/../shared-utils/industry-gate.sh" \
  "$(cd "$SKILL_ROOT/.." 2>/dev/null && pwd)/shared-utils/industry-gate.sh" \
  "${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/industry-gate.sh" \
  "/data/.openclaw/skills/shared-utils/industry-gate.sh"; do
  if [ -f "$_cand" ]; then
    _GATE_LIB="$_cand"
    break
  fi
done
if [ -z "$_GATE_LIB" ]; then
  echo "$P BLOCKED: shared-utils/industry-gate.sh not found — cannot verify this box's industry."
  echo "$P    FAIL CLOSED: refusing to proceed without the industry gate (absence is never permission)."
  exit 2
fi
# shellcheck source=/dev/null
. "$_GATE_LIB"
if oc_is_real_estate_industry; then
  echo "$P OK — Section E industry gate PASS ($OC_INDUSTRY_GATE_REASON)"
else
  echo "$P NOT-REAL-ESTATE: this box's captured industry is not real estate ($OC_INDUSTRY_GATE_REASON)."
  echo "$P    Skill 39 (real-estate playbook + its pipeline crons) is SKIPPED on this box. FAIL CLOSED — unknown/absent industry never installs the RE vertical."
  exit 2
fi

OS="$(uname -s)"
case "$OS" in
  Darwin) DEFAULT_SKILLS_DIR="$HOME/.openclaw/skills"; DEFAULT_MFD="$HOME/Downloads" ;;
  Linux)  DEFAULT_SKILLS_DIR="/data/.openclaw/skills"; DEFAULT_MFD="/data" ;;
  *) echo "$P BLOCKED: Unsupported OS: $OS"; exit 1 ;;
esac
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$DEFAULT_SKILLS_DIR}"
MFD="${MASTER_FILES_DIR:-$DEFAULT_MFD}"
FAIL=0

# ---- A. Skill 38 must be installed (Skill 39 is the RE vertical on top) ----
if [ -f "$SKILLS_DIR/38-conversational-ai-system/SKILL.md" ]; then
  echo "$P OK — Skill 38 (Conversational AI System) present at $SKILLS_DIR/38-conversational-ai-system"
else
  echo "$P BLOCKED: Skill 38 (Conversational AI System) not found at $SKILLS_DIR/38-conversational-ai-system"
  echo "$P    Skill 39 is the real-estate vertical ON TOP of Skill 38. Install Skill 38 first."
  FAIL=1
fi

# ---- B. MASTER_FILES_DIR resolvable (event log lives there) ----
if [ -d "$MFD" ]; then
  echo "$P OK — MASTER_FILES_DIR resolvable ($MFD)"
else
  echo "$P WARN: MASTER_FILES_DIR ($MFD) does not exist yet — 01-locate-master-files-folder.sh will resolve/create it."
fi

# ---- C. jq + curl ----
for bin in jq curl; do
  if command -v "$bin" >/dev/null 2>&1; then
    echo "$P OK — $bin present"
  else
    echo "$P BLOCKED: $bin not found on PATH (required for provider JSON + HTTP calls)"
    FAIL=1
  fi
done

# ---- D. Provider-key report (OPTIONAL — honest gap without them) ----
echo "$P provider-key report (optional; absence = honest gap, never fabricated data):"
report_key() {
  local name="$1" enables="$2"
  if [ -n "${!name:-}" ]; then
    echo "$P    [set]   $name — $enables"
  else
    echo "$P    [unset] $name — $enables (honest gap until set)"
  fi
}
report_key GOOGLE_MAPS_API_KEY "precise geocoding + Street View imagery"
report_key MAPBOX_TOKEN        "alternative geocoding"
report_key RENTCAST_API_KEY    "example property lookup + comps provider"
echo "$P    (US Census geocoder works with NO key — geocoding always available.)"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "$P ALL MANDATORY PREREQUISITES PASS — proceed to 01-locate-master-files-folder.sh"
  exit 0
else
  echo "$P PREREQUISITES FAILED — fix the BLOCKED item(s) above, then re-run."
  exit 1
fi
