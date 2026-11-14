#!/usr/bin/env bash
# skill51-version-equal.test.sh — Skill 51's three version numbers must agree.
#
# FINDING PD-025. Skill 51 (51-signature-presentation) records its version in
# three places, and nothing kept them together:
#   * skill-version.txt            (vX.Y.Z)
#   * SKILL.md frontmatter         (version: vX.Y.Z)
#   * skill.json                   ("version": "X.Y.Z", no leading v)
# A manual bump edited the first two and left skill.json at 2.1.8 while the
# other two said 2.1.9, so anything reading skill.json (an installer, a
# launcher, a CLI parity check) shipped a version nobody meant.
#
# This test pins BOTH halves of the fix:
#
#   1. In the real tree the three records agree.
#   2. Against a disposable fixture repo, the real scripts/bump-version.sh
#      writes skill.json from skill-version.txt — not from the repo target —
#      and leaves every OTHER skill's skill.json BYTE-IDENTICAL (the script is
#      shared with the Skill 75 batch; see 02-SWARM-PLAN.md section 7).
#
# It runs the real script against the fixture, so it measures behaviour rather
# than reading the source for a pattern.
#
# Usage: tests/unit/skill51-version-equal.test.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
S51="$REPO_ROOT/51-signature-presentation"

FAILURES=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAILURES=$((FAILURES + 1)); }

# Read the three records; print nothing on failure, report which one broke.
read_versions() {
  python3 -I - "$S51" <<'PY'
import json, os, re, sys
d = sys.argv[1]
def norm(s):
    s = (s or '').strip().strip('"\'').lstrip('vV')
    return s
out = {}
try:
    out['txt'] = norm(open(os.path.join(d, 'skill-version.txt'), encoding='utf-8').readline())
except OSError:
    out['txt'] = 'MISSING'
try:
    t = open(os.path.join(d, 'SKILL.md'), encoding='utf-8').read()
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', t, re.DOTALL)
    fm = m.group(1) if m else ''
    vm = re.search(r'^version:\s*(\S+)', fm, re.MULTILINE)
    out['md'] = norm(vm.group(1)) if vm else 'MISSING'
except OSError:
    out['md'] = 'MISSING'
try:
    out['json'] = norm(json.load(open(os.path.join(d, 'skill.json'), encoding='utf-8')).get('version'))
except (OSError, ValueError):
    out['json'] = 'MISSING'
print('%s %s %s' % (out['txt'], out['md'], out['json']))
PY
}

echo "== 1. the real tree: all three records agree =="
VS="$(read_versions)"
V_TXT="$(echo "$VS" | awk '{print $1}')"
V_MD="$(echo "$VS" | awk '{print $2}')"
V_JSON="$(echo "$VS" | awk '{print $3}')"
echo "     skill-version.txt=$V_TXT  SKILL.md=$V_MD  skill.json=$V_JSON"

if [ "$V_TXT" = "MISSING" ] || [ "$V_MD" = "MISSING" ] || [ "$V_JSON" = "MISSING" ]; then
  fail "one of Skill 51's three version records is missing or unreadable"
elif [ "$V_TXT" = "$V_MD" ] && [ "$V_TXT" = "$V_JSON" ]; then
  pass "skill-version.txt, SKILL.md frontmatter and skill.json all say $V_TXT"
else
  fail "Skill 51's version numbers disagree: txt=$V_TXT md=$V_MD json=$V_JSON"
fi

# ─── Fixture: drive the real bumper and measure what it writes ───────────────
FIX="$(mktemp -d "${TMPDIR:-/var/tmp}/skill51-version-equal.XXXXXX")"
cleanup() { rm -rf "$FIX"; }
trap cleanup EXIT

START_VER="v1.0.0"
TARGET_VER="v99.44.7"
S51_OLD="2.1.8"   # the drifted value this finding was raised on
S51_NEW="2.1.9"   # what skill-version.txt in the fixture already says

mkdir -p "$FIX/scripts" "$FIX/23-ai-workforce-blueprint/templates/role-library" \
         "$FIX/51-signature-presentation" "$FIX/77-unrelated-skill"

cp "$REPO_ROOT/scripts/bump-version.sh" "$FIX/scripts/bump-version.sh"
[ -f "$REPO_ROOT/scripts/version-markers.json" ] && \
  cp "$REPO_ROOT/scripts/version-markers.json" "$FIX/scripts/version-markers.json"
chmod +x "$FIX/scripts/bump-version.sh"

echo "$START_VER" > "$FIX/version"
printf '#!/usr/bin/env bash\nONBOARDING_VERSION="%s"\n' "$START_VER" > "$FIX/install.sh"
printf '#!/usr/bin/env bash\n#  %s\nONBOARDING_VERSION="%s"\n' "$START_VER" "$START_VER" \
  > "$FIX/update-skills.sh"
printf '# Repo\n\nRuns this repo at %s.\n\nCurrent Version: %s\n' "$START_VER" "$START_VER" \
  > "$FIX/README.md"
printf 'Update to **%s** now.\n' "$START_VER" > "$FIX/DIRECT-TO-AGENT-UPDATE-MESSAGE.md"
printf '{\n  "onboardingVersion": "%s"\n}\n' "$START_VER" > "$FIX/cc-compat.json"
printf '%s\n' "${START_VER#v}" > "$FIX/23-ai-workforce-blueprint/skill-version.txt"
printf -- '---\nname: blueprint\nversion: %s\n---\n\nBody.\n' "${START_VER#v}" \
  > "$FIX/23-ai-workforce-blueprint/SKILL.md"
printf '{\n  "version": "%s",\n  "total_roles": 3\n}\n' "${START_VER#v}" \
  > "$FIX/23-ai-workforce-blueprint/templates/role-library/_index.json"

# Skill 51: the two records already agree with each other; skill.json lags, which
# is exactly the PD-025 drift. The bump must close that gap.
printf 'v%s\n' "$S51_NEW" > "$FIX/51-signature-presentation/skill-version.txt"
printf -- '---\nname: signature-presentation\ndescription: x\nversion: v%s\n---\n\nBody.\n' \
  "$S51_NEW" > "$FIX/51-signature-presentation/SKILL.md"
printf '{\n  "name": "signature-presentation",\n  "version": "%s",\n  "entry": "bin/presentation"\n}\n' \
  "$S51_OLD" > "$FIX/51-signature-presentation/skill.json"
mkdir -p "$FIX/51-signature-presentation/.claude-plugin"
printf '{\n  "name": "signature-presentation",\n  "version": "%s"\n}\n' "$S51_OLD" \
  > "$FIX/51-signature-presentation/.claude-plugin/plugin.json"

# A different skill's record, which this bump must not touch at all.
printf '{\n  "name": "unrelated",\n  "version": "%s"\n}\n' "$S51_OLD" \
  > "$FIX/77-unrelated-skill/skill.json"

OTHER_BEFORE="$(shasum -a 256 "$FIX/77-unrelated-skill/skill.json" | cut -d' ' -f1)"
PLUGIN_BEFORE="$(shasum -a 256 "$FIX/51-signature-presentation/.claude-plugin/plugin.json" | cut -d' ' -f1)"

echo ""
echo "== 2. a bump writes skill.json from skill-version.txt, not from the repo target =="
BUMP_OUT="$(cd "$FIX" && BATCH_PREP=0 bash scripts/bump-version.sh "$TARGET_VER" 2>&1)"
BUMP_RC=$?
if [ "$BUMP_RC" -eq 0 ]; then
  pass "bump completed end-to-end (exit 0)"
else
  fail "bump exited $BUMP_RC — a version bump must still work"
  echo "$BUMP_OUT" | sed 's/^/      /'
fi

FIX_JSON="$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1])).get('version'))" \
  "$FIX/51-signature-presentation/skill.json" 2>/dev/null || echo MISSING)"
if [ "$FIX_JSON" = "$S51_NEW" ]; then
  pass "skill.json rolled to $S51_NEW (from skill-version.txt)"
elif [ "$FIX_JSON" = "${TARGET_VER#v}" ]; then
  fail "skill.json was rolled to the REPO version ${TARGET_VER#v} — Skill 51 has its own line"
else
  fail "skill.json is '$FIX_JSON' after the bump; expected $S51_NEW"
fi

if python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('entry')=='bin/presentation' else 1)" \
    "$FIX/51-signature-presentation/skill.json" 2>/dev/null; then
  pass "skill.json's other keys survived the roll"
else
  fail "skill.json's other keys were lost or rewritten by the roll"
fi

echo ""
echo "== 3. every other skill path stays byte-identical =="
OTHER_AFTER="$(shasum -a 256 "$FIX/77-unrelated-skill/skill.json" | cut -d' ' -f1)"
if [ "$OTHER_BEFORE" = "$OTHER_AFTER" ]; then
  pass "an unrelated skill's skill.json is byte-identical"
else
  fail "an unrelated skill's skill.json WAS REWRITTEN by the bump"
fi
PLUGIN_AFTER="$(shasum -a 256 "$FIX/51-signature-presentation/.claude-plugin/plugin.json" | cut -d' ' -f1)"
if [ "$PLUGIN_BEFORE" = "$PLUGIN_AFTER" ]; then
  pass "the plugin's own version file is byte-identical"
else
  fail "the plugin's own version file was rewritten — it carries its own version line"
fi

echo ""
if [ "$FAILURES" -ne 0 ]; then
  echo "SKILL51 VERSION-EQUAL: FAIL ($FAILURES assertion(s))"
  echo "Skill 51's three version numbers must agree. See finding PD-025."
  exit 1
fi
echo "SKILL51 VERSION-EQUAL: PASS (all three records agree; a bump writes skill.json and nothing else)"
exit 0
