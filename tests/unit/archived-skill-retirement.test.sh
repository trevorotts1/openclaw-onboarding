#!/usr/bin/env bash
# Archived skills: old live copy retired (moved) per docs/archived-skill-tombstones.json,
# stale state-file key dropped, live non-archived skills untouched. Hermetic.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
awk '/^    python3 - "\$_TOMB_JSON"/{f=1;next} /^PYEOF/{f=0} f' "$REPO/update-skills.sh" > "$T/retire.py"
[ -s "$T/retire.py" ] || { bad "could not extract retirement block"; exit 1; }
mkdir -p "$T/oc/skills/11-superdesign" "$T/oc/skills/03-agent-browser" "$T/src/11-superdesign-ARCHIVED" "$T/src/03-agent-browser"
python3 -c "import json;json.dump({'archived':{'11-superdesign-ARCHIVED':{}}},open('$T/tomb.json','w'))"
python3 "$T/retire.py" "$T/tomb.json" "$T/oc/skills" "$T/oc/retired-skills" >/dev/null
[ ! -e "$T/oc/skills/11-superdesign" ] && [ -d "$T/oc/retired-skills/11-superdesign" ] && ok "archived live copy moved out" || bad "not retired"
[ -d "$T/oc/skills/03-agent-browser" ] && ok "live skill untouched" || bad "live skill removed"
# stale state key
echo '{"skills":{"11-superdesign":{"status":"qc-failed"},"03-agent-browser":{"status":"pending"}}}' > "$T/ws.json"
mkdir -p "$T/h"
seedout="$(HOME="$T/h" bash -c 'source "$1" 2>/dev/null; OBS_STATE_FILE="$2"; obs_seed_state v1 "$3"' _ "$REPO/scripts/onboarding-state.sh" "$T/ws.json" "$T/src" 2>&1)"
python3 -c "import json,sys;d=json.load(open('$T/ws.json'))['skills'];sys.exit(0 if '11-superdesign' not in d and '03-agent-browser' in d else 1)" && ok "stale state key dropped" || { bad "state key kept"; echo "$seedout" | tail -15; cat "$T/ws.json"; }
exit $fail
