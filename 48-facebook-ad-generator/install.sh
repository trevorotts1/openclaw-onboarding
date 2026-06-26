#!/usr/bin/env bash
# Skill 48 — Facebook & Instagram Ad Generator — installer (client box). Fail-loud.
#
# The skill is read-by-file-path (like Skill 47); installing it never runs the Gemini
# indexer and adds no persona blueprint — it REUSES the 42 built authors. This installer
# only proves the payload is intact, wires the reused integration modules, and runs the
# enforcement self-test so a broken install can never masquerade as a good one.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${SKILL_DIR}/.."
echo "=== Installing Skill 48 — Facebook & Instagram Ad Generator ==="

# 1) Payload integrity (fail loud on a missing spine file).
need() { [ -e "$1" ] || { echo "FATAL: missing $1" >&2; exit 1; }; }
need "${SKILL_DIR}/scripts/ad_director.py"
need "${SKILL_DIR}/scripts/ad_build_check.py"
need "${SKILL_DIR}/scripts/ad_sync_check.py"
need "${SKILL_DIR}/scripts/ad_gate_integrity_check.py"
need "${SKILL_DIR}/scripts/test_ad_preflight.py"
need "${SKILL_DIR}/test-fixtures/make-ad-fixtures.sh"
need "${SKILL_DIR}/tools/ghl_media.py"
need "${REPO_ROOT}/universal-sops/fb-ad-craft/AD-PIPELINE-MANIFEST.json"
need "${REPO_ROOT}/universal-sops/fb-ad-craft/MASTER-AD-QC-AUTOFAIL-RULESET.md"

# 2) The reused Kie image adapter ships with Skill 47; assert it is reachable on the box.
KIE_ADAPTER="${REPO_ROOT}/47-movie-producer/kie-adapters/tools/graphics/kie_image.py"
if [ -f "${KIE_ADAPTER}" ]; then
  echo "  [ok]   reused Kie image adapter found (47-movie-producer/kie-adapters/.../kie_image.py)"
else
  echo "  [note] Kie image adapter not found beside this install — S5 generation requires"
  echo "         the client's KIE_API_KEY + the reused gpt-image adapter at run time."
fi

# 3) Enforcement self-test (the install is only good if the gates bite).
echo "--- enforcement self-test ---"
python3 "${SKILL_DIR}/scripts/ad_sync_check.py" >/dev/null
python3 "${SKILL_DIR}/scripts/test_ad_preflight.py" >/dev/null
python3 "${SKILL_DIR}/scripts/ad_gate_integrity_check.py" >/dev/null
echo "  [ok]   sync + negative-suite + Guard A all green"

# 4) Install QC.
bash "${SKILL_DIR}/qc-facebook-ad-generator.sh"

echo ""
echo "Skill 48 installed. Reminders:"
echo "  - Generation uses the CLIENT's own KIE_API_KEY (never the operator's)."
echo "  - Hosting uses the CLIENT's own GoHighLevel LOCATION PIT (medias.write)."
echo "  - PLAI is the only ad path; no direct Meta API."
