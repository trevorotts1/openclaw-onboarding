#!/bin/bash
# Generate or update the skill manifest
# Can be called independently or from install.sh / update-skills.sh

SKILLS_DIR="$HOME/.openclaw/skills"
MANIFEST_PATH="$SKILLS_DIR/.skill-manifest.json"
ONBOARDING_VER=$(cat "$SKILLS_DIR/.onboarding-version" 2>/dev/null || echo "unknown")

python3 -c "
import os, json
from datetime import datetime, timezone

skills_dir = os.path.expanduser('$SKILLS_DIR')
manifest = {
    'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'onboardingVersion': '$ONBOARDING_VER',
    'skills': {}
}
for entry in sorted(os.listdir(skills_dir)):
    full = os.path.join(skills_dir, entry)
    if not os.path.isdir(full) or not entry[0].isdigit():
        continue
    ver_file = os.path.join(full, 'skill-version.txt')
    ver = 'unknown'
    if os.path.isfile(ver_file):
        with open(ver_file) as f:
            ver = f.read().strip()
    manifest['skills'][entry] = ver
with open('$MANIFEST_PATH', 'w') as f:
    json.dump(manifest, f, indent=2)
print(json.dumps(manifest, indent=2))
" 2>/dev/null
