#!/usr/bin/env bash
# Skill 30 install QC. Read-only, no paid calls, no secret values in output.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SKILL_DIR/../lib-shared.sh"
if [ -f "$LIB" ]; then
  source "$LIB"
  resolve_platform_paths
else
  [ -n "${OPENCLAW_ROOT:-}" ] || { echo "FAIL - shared path resolver unavailable; set OPENCLAW_ROOT to this client installation"; exit 1; }
  OC_ROOT="$OPENCLAW_ROOT"
fi
for file in SKILL.md INSTALL.md QC.md README.md fish-audio-voice-sop.md skill-version.txt production-policy.json references/fish-audio-api-reference.md scripts/fish_audio_config.py; do
  [ -s "$SKILL_DIR/$file" ] || { echo "FAIL - required Skill 30 file missing: $file"; exit 1; }
done
python3 "$SKILL_DIR/scripts/fish_audio_config.py" check --root "$OC_ROOT"
echo "Skill 30 configuration QC PASS. Live synthesis and listening review are separate, paid checks."
