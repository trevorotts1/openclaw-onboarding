#!/usr/bin/env bash
# bump-version.sh — atomically bump the OpenClaw version across ALL files.
#
# The problem this solves: "the version" is encoded in 9 separate markers
# (across 8 files — README.md carries 2). Drift is mathematically guaranteed
# unless one tool updates all of them in one shot.
#
# Coverage history:
#   v10.14.0 and earlier: 5 files (version, install.sh, skill-version.txt,
#                                  _index.json, _qc-summary.md)
#   v10.14.34+:           8 files — added README.md, update-skills.sh,
#                                   DIRECT-TO-AGENT-UPDATE-MESSAGE.md
#                                   (per 2-day forensics finding #23)
#   v10.15.16+:           9 markers — added the README.md "Current Version:
#                                   vX.Y.Z" prose line (a SECOND marker in
#                                   README.md, separate from the "this repo at
#                                   vX.Y.Z" marker). It drifted to v10.15.15
#                                   one patch behind /version because no script
#                                   or CI check rolled it. Now rolled here AND
#                                   CI-tracked in version-consistency.yml.
#   PRD P3-1:             11 markers — added the 23-ai-workforce-blueprint/SKILL.md
#                                   YAML frontmatter `version:` field (marker #11,
#                                   after cc-compat.json = #10). It drifted to
#                                   v16.2.9 while skill-version.txt was v16.2.16
#                                   because nothing rolled the frontmatter field.
#                                   Now rolled + drift-checked here.
#
# VERSION-BUMP CHECKLIST — SKILL 38 SELF-COUNT RE-VERIFICATION (added 2026-05-29):
#   Skill 38's SKILL.md "What This Skill Ships" hard-codes file counts
#   (protocols/, scripts/, references/, journey templates). They drift silently
#   whenever a file is added/removed. On EVERY Skill-38 bump (its own
#   38-conversational-ai-system/skill-version.txt — NOT one of the 8 files
#   above), re-verify and correct those counts. The exact command:
#     ( cd 38-conversational-ai-system && \
#       echo "protocols=$(ls -1 protocols/*.md | wc -l)" && \
#       echo "scripts=$(ls -1 scripts/*.sh | wc -l)" && \
#       echo "references=$(ls -1 references/*.md | wc -l)" && \
#       echo "journeys=$(ls -1d templates/journey-templates/*/ | wc -l)" )
#   Then make SKILL.md's SELF-COUNTS comment + bullets match. The 23-key linter
#   qc-23-key-bodies.sh + trinity qc-trinity-registry.sh are part of scripts/.
#
# Usage:
#   ./scripts/bump-version.sh v10.6.2          # update all version markers
#   ./scripts/bump-version.sh v10.6.2 --tag    # also create a git tag
#   ./scripts/bump-version.sh v10.6.2 --tag --push   # also push the tag
#   ./scripts/bump-version.sh --check          # exit 1 if drift; print state
#
# Works for both Mac and VPS platforms in the unified repo (paths are the same).
set -euo pipefail

# ─── Locate the repo root ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -f "$REPO_ROOT/version" ] || [ ! -f "$REPO_ROOT/install.sh" ]; then
  echo "ERROR: $REPO_ROOT does not look like an OpenClaw repo (missing /version or /install.sh)" >&2
  exit 1
fi

# ─── The 11 version-marker locations (relative to repo root) ─────────────────
F_VERSION="$REPO_ROOT/version"
F_INSTALL="$REPO_ROOT/install.sh"
F_SKILL_VERSION="$REPO_ROOT/23-ai-workforce-blueprint/skill-version.txt"
F_INDEX_JSON="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json"
F_QC_SUMMARY="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_qc-summary.md"
F_README="$REPO_ROOT/README.md"
F_UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"
F_DIRECT_TO_AGENT="$REPO_ROOT/DIRECT-TO-AGENT-UPDATE-MESSAGE.md"
# Marker #10 (v13.8.1) — cc-compat.json onboardingVersion. The repo-consistency
# gate (qc-assert-repo-consistency.py) and CI both fail if this != /version, but
# bump-version.sh historically did not roll it, so a bump silently drifted it.
F_CC_COMPAT="$REPO_ROOT/cc-compat.json"
# Marker #11 (PRD P3-1) — 23-ai-workforce-blueprint/SKILL.md YAML frontmatter
# `version:` field. It is the ONLY SKILL.md frontmatter version that tracks the
# repo /version (its skill-version.txt is rolled at the repo version, above).
# Nothing rolled the frontmatter field, so it silently drifted (found at v16.2.9
# while skill-version.txt was v16.2.16). Roll it here, in lockstep, so it can never
# drift again. NOTE: other skills' SKILL.md `version:` fields (35/42/43/45) track
# their OWN independent skill versions — NOT the repo version — so they are
# deliberately EXCLUDED here; rolling them to the repo version would corrupt them.
F_23_SKILL_MD="$REPO_ROOT/23-ai-workforce-blueprint/SKILL.md"

# ─── Read current values ─────────────────────────────────────────────────────
read_current() {
  V_ROOT=$(cat "$F_VERSION" 2>/dev/null | head -1 | tr -d '[:space:]' || echo "MISSING")
  V_INSTALL=$(grep -E '^ONBOARDING_VERSION=' "$F_INSTALL" 2>/dev/null | head -1 | sed -E 's/^ONBOARDING_VERSION="?([^"]*)"?.*/\1/' || echo "MISSING")
  V_SKILL=$(cat "$F_SKILL_VERSION" 2>/dev/null | head -1 | tr -d '[:space:]' || echo "MISSING")
  if [ -f "$F_INDEX_JSON" ]; then
    V_INDEX=$(python3 -c "import json; print(json.load(open('$F_INDEX_JSON')).get('version','MISSING'))" 2>/dev/null || echo "MISSING")
  else
    V_INDEX="MISSING"
  fi
  V_QC=$(grep -oE 'Role Library v[0-9]+\.[0-9]+\.[0-9]+' "$F_QC_SUMMARY" 2>/dev/null | head -1 | sed 's/Role Library //' || echo "MISSING")
  [ -z "$V_QC" ] && V_QC="MISSING"

  # New trackers (v10.14.34) — guards must not abort under set -e
  if [ -f "$F_README" ]; then
    V_README=$(grep -oE 'this repo at v[0-9]+\.[0-9]+\.[0-9]+' "$F_README" 2>/dev/null | head -1 | sed 's/this repo at //' || echo "MISSING")
    if [ -z "$V_README" ]; then V_README="MISSING"; fi
    # Marker #9 (v10.15.16) — the README "Current Version: vX.Y.Z" prose line.
    # A SECOND marker in the same file; drifted to v10.15.15 because nothing rolled it.
    V_README_CURRENT=$(grep -oE 'Current Version: v[0-9]+\.[0-9]+\.[0-9]+' "$F_README" 2>/dev/null | head -1 | sed 's/Current Version: //' || echo "MISSING")
    if [ -z "$V_README_CURRENT" ]; then V_README_CURRENT="MISSING"; fi
  else
    V_README="MISSING"
    V_README_CURRENT="MISSING"
  fi
  if [ -f "$F_UPDATE_SKILLS" ]; then
    V_UPDATE_SKILLS=$(grep -E '^ONBOARDING_VERSION=' "$F_UPDATE_SKILLS" 2>/dev/null | head -1 | sed -E 's/^ONBOARDING_VERSION="?([^"]*)"?.*/\1/' || echo "MISSING")
    if [ -z "$V_UPDATE_SKILLS" ]; then V_UPDATE_SKILLS="MISSING"; fi
  else
    V_UPDATE_SKILLS="MISSING"
  fi
  if [ -f "$F_DIRECT_TO_AGENT" ]; then
    V_DIRECT=$(grep -oE '\*\*v[0-9]+\.[0-9]+\.[0-9]+\*\*' "$F_DIRECT_TO_AGENT" 2>/dev/null | head -1 | tr -d '*' || echo "MISSING")
    if [ -z "$V_DIRECT" ]; then V_DIRECT="MISSING"; fi
  else
    V_DIRECT="MISSING"
  fi
  if [ -f "$F_CC_COMPAT" ]; then
    V_CC_COMPAT=$(python3 -c "import json; print(json.load(open('$F_CC_COMPAT')).get('onboardingVersion','MISSING'))" 2>/dev/null || echo "MISSING")
    if [ -z "$V_CC_COMPAT" ]; then V_CC_COMPAT="MISSING"; fi
  else
    V_CC_COMPAT="MISSING"
  fi
  # Marker #11 (PRD P3-1) — SKILL.md YAML frontmatter `version:` (no v prefix).
  # Parse ONLY the first `version:` line inside the leading `---`…`---` block so a
  # later `version:` mention in the body can never be misread.
  if [ -f "$F_23_SKILL_MD" ]; then
    V_23_SKILL_MD=$(python3 - "$F_23_SKILL_MD" <<'PYEOF' 2>/dev/null || echo "MISSING"
import re, sys
try:
    txt = open(sys.argv[1]).read()
except OSError:
    print("MISSING"); sys.exit(0)
m = re.match(r'^---\s*\n(.*?)\n---\s*\n', txt, re.DOTALL)
block = m.group(1) if m else ""
vm = re.search(r'^version:\s*(\S+)', block, re.MULTILINE)
print(vm.group(1) if vm else "MISSING")
PYEOF
)
    if [ -z "$V_23_SKILL_MD" ]; then V_23_SKILL_MD="MISSING"; fi
  else
    V_23_SKILL_MD="MISSING"
  fi
}

# Normalize a version: strip leading 'v', collapse to X.Y.Z
norm() { echo "${1#v}"; }

print_state() {
  read_current
  echo ""
  echo "Current version state (in this repo):"
  printf "  %-50s %s\n" "version" "$V_ROOT"
  printf "  %-50s %s\n" "install.sh ONBOARDING_VERSION" "$V_INSTALL"
  printf "  %-50s %s\n" "23-ai-workforce-blueprint/skill-version.txt" "$V_SKILL"
  printf "  %-50s %s\n" "templates/role-library/_index.json [version]" "$V_INDEX"
  printf "  %-50s %s\n" "templates/role-library/_qc-summary.md heading" "$V_QC"
  printf "  %-50s %s\n" "README.md (this repo at vX.Y.Z)" "$V_README"
  printf "  %-50s %s\n" "README.md (Current Version: vX.Y.Z)" "$V_README_CURRENT"
  printf "  %-50s %s\n" "update-skills.sh ONBOARDING_VERSION" "$V_UPDATE_SKILLS"
  printf "  %-50s %s\n" "DIRECT-TO-AGENT-UPDATE-MESSAGE.md (**vX.Y.Z**)" "$V_DIRECT"
  printf "  %-50s %s\n" "cc-compat.json onboardingVersion" "$V_CC_COMPAT"
  printf "  %-50s %s\n" "23-ai-workforce-blueprint/SKILL.md [version:]" "$V_23_SKILL_MD"
}

check_drift() {
  read_current
  N_ROOT=$(norm "$V_ROOT")
  N_INSTALL=$(norm "$V_INSTALL")
  N_SKILL=$(norm "$V_SKILL")
  N_INDEX=$(norm "$V_INDEX")
  N_QC=$(norm "$V_QC")
  N_README=$(norm "$V_README")
  N_README_CURRENT=$(norm "$V_README_CURRENT")
  N_UPDATE=$(norm "$V_UPDATE_SKILLS")
  N_DIRECT=$(norm "$V_DIRECT")
  N_CC_COMPAT=$(norm "$V_CC_COMPAT")
  N_23_SKILL_MD=$(norm "$V_23_SKILL_MD")
  if [ "$N_ROOT" = "$N_INSTALL" ] && [ "$N_ROOT" = "$N_SKILL" ] && \
     [ "$N_ROOT" = "$N_INDEX" ] && [ "$N_ROOT" = "$N_QC" ] && \
     [ "$N_ROOT" = "$N_README" ] && [ "$N_ROOT" = "$N_README_CURRENT" ] && \
     [ "$N_ROOT" = "$N_UPDATE" ] && [ "$N_ROOT" = "$N_DIRECT" ] && \
     [ "$N_ROOT" = "$N_CC_COMPAT" ] && [ "$N_ROOT" = "$N_23_SKILL_MD" ]; then
    return 0
  fi
  return 1
}

# ─── --check mode: report drift and exit ─────────────────────────────────────
if [ "${1:-}" = "--check" ]; then
  print_state
  if check_drift; then
    echo ""
    echo "All 11 version markers agree."
    exit 0
  else
    echo ""
    echo "DRIFT DETECTED — at least one file disagrees with /version."
    exit 1
  fi
fi

# ─── Bump mode: require target version ──────────────────────────────────────
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "Usage: $0 vX.Y.Z [--tag] [--push]"
  echo "       $0 --check"
  exit 1
fi

# Validate format
if ! echo "$TARGET" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: version must be vX.Y.Z format (got '$TARGET')" >&2
  exit 1
fi

TARGET_NOV="${TARGET#v}"  # 10.6.2 (no v)

echo "Bumping repo at $REPO_ROOT → $TARGET"

# 1. /version (with v prefix)
echo "$TARGET" > "$F_VERSION"

# 2. /install.sh — update ONBOARDING_VERSION line (portable sed for Mac+Linux)
python3 - <<PYEOF
import re, sys
p = "$F_INSTALL"
target = "$TARGET"
content = open(p).read()
new = re.sub(r'^(ONBOARDING_VERSION=)"?[^"\n]*"?',
             r'\1"' + target + '"', content, count=1, flags=re.MULTILINE)
if new == content:
    print(f"WARN: ONBOARDING_VERSION line not found in {p}", file=sys.stderr)
open(p, "w").write(new)
PYEOF

# 3. /23-ai-workforce-blueprint/skill-version.txt (no v prefix)
echo "$TARGET_NOV" > "$F_SKILL_VERSION"

# 4. /_index.json (JSON-safe update)
if [ -f "$F_INDEX_JSON" ]; then
  python3 - <<PYEOF
import json
p = "$F_INDEX_JSON"
d = json.load(open(p))
d["version"] = "$TARGET_NOV"
with open(p, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
PYEOF
fi

# 5. /_qc-summary.md (heading line)
if [ -f "$F_QC_SUMMARY" ]; then
  python3 - <<PYEOF
import re
p = "$F_QC_SUMMARY"
content = open(p).read()
new = re.sub(r'(Role Library )v[0-9]+\.[0-9]+\.[0-9]+',
             r'\1' + "$TARGET", content)
open(p, "w").write(new)
PYEOF
fi

# 6. /README.md (this repo at vX.Y.Z + any other v10.x.y headings) — v10.14.34
if [ -f "$F_README" ]; then
  python3 - <<PYEOF
import re
p = "$F_README"
target = "$TARGET"
content = open(p).read()
# Replace "this repo at vX.Y.Z." patterns
new = re.sub(r'(this repo at )v[0-9]+\.[0-9]+\.[0-9]+',
             r'\1' + target, content)
# Marker #9 (v10.15.16): "Current Version: vX.Y.Z" prose line. This is a
# SECOND, independent version marker in README.md. It silently drifted to
# v10.15.15 (one patch behind /version) because no script rolled it. Roll it
# here on every bump so it can never drift again.
new = re.sub(r'(Current Version: )v[0-9]+\.[0-9]+\.[0-9]+',
             r'\1' + target, new)
# Replace any "(vX.Y.Z)" heading suffix that matches the prior version
# (heuristic: only first 200 lines, to avoid rewriting CHANGELOG entries)
lines = new.split('\n')
for i in range(min(200, len(lines))):
    lines[i] = re.sub(r'\(v[0-9]+\.[0-9]+\.[0-9]+\)', '(' + target + ')', lines[i])
new = '\n'.join(lines)
open(p, "w").write(new)
PYEOF
fi

# 7. /update-skills.sh ONBOARDING_VERSION + leading comment line — v10.14.34
if [ -f "$F_UPDATE_SKILLS" ]; then
  python3 - <<PYEOF
import re
p = "$F_UPDATE_SKILLS"
target = "$TARGET"
content = open(p).read()
new = re.sub(r'^(ONBOARDING_VERSION=)"?[^"\n]*"?',
             r'\1"' + target + '"', content, count=1, flags=re.MULTILINE)
# Top-of-file "#  v10.x.y" header line — first match only
new = re.sub(r'^(#\s+)v[0-9]+\.[0-9]+\.[0-9]+',
             r'\1' + target, new, count=1, flags=re.MULTILINE)
open(p, "w").write(new)
PYEOF
fi

# 8. /DIRECT-TO-AGENT-UPDATE-MESSAGE.md (**vX.Y.Z** boldface) — v10.14.34
if [ -f "$F_DIRECT_TO_AGENT" ]; then
  python3 - <<PYEOF
import re
p = "$F_DIRECT_TO_AGENT"
target = "$TARGET"
content = open(p).read()
new = re.sub(r'\*\*v[0-9]+\.[0-9]+\.[0-9]+\*\*',
             '**' + target + '**', content)
open(p, "w").write(new)
PYEOF
fi

# 9. /cc-compat.json onboardingVersion (with v prefix) — v13.8.1.
#    The repo-consistency gate + CI fail if this != /version. Roll it on every
#    bump so it can never silently drift again (caught in v13.8.1 QC).
if [ -f "$F_CC_COMPAT" ]; then
  python3 - <<PYEOF
import json
p = "$F_CC_COMPAT"
target = "$TARGET"
d = json.load(open(p))
d["onboardingVersion"] = target
with open(p, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
PYEOF
fi

# 9b. /23-ai-workforce-blueprint/SKILL.md YAML frontmatter `version:` (no v prefix,
#     matching skill-version.txt) — PRD P3-1. Only the FIRST `version:` line inside
#     the leading `---`…`---` frontmatter block is rewritten, so a later `version:`
#     mention in the body is never touched.
if [ -f "$F_23_SKILL_MD" ]; then
  python3 - <<PYEOF
import re, sys
p = "$F_23_SKILL_MD"
target_nov = "$TARGET_NOV"
content = open(p).read()
m = re.match(r'^(---\s*\n.*?\n---\s*\n)', content, re.DOTALL)
if m:
    head = m.group(1)
    rest = content[m.end():]
    new_head, n = re.subn(r'^(version:\s*)\S+', r'\g<1>' + target_nov, head, count=1, flags=re.MULTILINE)
    if n == 0:
        print(f"WARN: no 'version:' field in {p} frontmatter", file=sys.stderr)
    open(p, "w").write(new_head + rest)
else:
    print(f"WARN: no YAML frontmatter found in {p}", file=sys.stderr)
PYEOF
fi

# 10. Script-embedded version markers (mirrors how ORPHAN_TEMP_SWEEP_VERSION is
#     tracked). The browser-safety bundle adds BROWSER_MANAGER_VERSION (shell +
#     .py), AGENT_BROWSER_REAPER_VERSION, and a guard marker; roll them so the
#     version-consistency CI + pre-commit gate 5 stay green and these never drift.
_roll_marker() {
  # $1 = file (relative to repo root), $2 = marker name (e.g. FOO_VERSION)
  local f="$REPO_ROOT/$1" marker="$2"
  [ -f "$f" ] || return 0
  python3 - "$f" "$marker" "$TARGET" <<'PYEOF'
import re, sys
path, marker, target = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path).read()
# Match: MARKER="vX.Y.Z"  (bash) or MARKER = "vX.Y.Z" (python)
new = re.sub(
    r'(' + re.escape(marker) + r'\s*=\s*")v[0-9]+\.[0-9]+\.[0-9]+(")',
    r'\g<1>' + target + r'\g<2>',
    src, count=1)
if new != src:
    open(path, "w").write(new)
PYEOF
}
_roll_marker "06-ghl-install-pages/tools/browser_manager.sh" "BROWSER_MANAGER_VERSION"
_roll_marker "06-ghl-install-pages/tools/browser_manager.py" "BROWSER_MANAGER_PY_VERSION"
_roll_marker "scripts/agent-browser-reaper.sh"               "AGENT_BROWSER_REAPER_VERSION"
_roll_marker "scripts/guard-agent-browser-managed.sh"        "GUARD_AGENT_BROWSER_MANAGED_VERSION"

# 11. G3-on-06 GAP FIX (v14.0.1): the two _roll_marker calls above rewrite files
#     INSIDE the 06-ghl-install-pages/ skill dir (browser_manager.sh + .py). CI guard
#     G3 (version-consistency.yml) fails any release where a file under a skill dir
#     changes WITHOUT that skill's own skill-version.txt changing in the same diff.
#     Because nothing bumped 06-ghl-install-pages/skill-version.txt, EVERY release that
#     rolled the browser-manager markers tripped G3 (flagged on the v14.0.0 ship).
#     Roll 06's skill-version.txt here, in lockstep with the markers it gates, so G3
#     stays green on every release. The 06 skill version is intentionally tracked at
#     the repo /version (with the v prefix) like 23-ai-workforce-blueprint/skill-version.txt.
F_06_SKILL_VERSION="$REPO_ROOT/06-ghl-install-pages/skill-version.txt"
if [ -f "$F_06_SKILL_VERSION" ]; then
  echo "$TARGET" > "$F_06_SKILL_VERSION"
fi

# 12. 06 SKILL.md nested `metadata: version:` (v17.0.4 — July-3 audit finding P1-4).
#     06-ghl-install-pages/SKILL.md carries a version under `metadata:` that ALSO
#     tracks the repo /version (like 06's skill-version.txt above), but nothing
#     rolled it, so it silently drifted (found stale at 16.2.14). It is indented,
#     quoted, and nested under `metadata:` (NOT a top-level frontmatter field like
#     23's), so the frontmatter-version CI gate deliberately skips it — roll it
#     HERE, in lockstep, so it can never drift again. Rewrite the first `version:`
#     line inside the leading `---`…`---` block, preserving its quoting.
F_06_SKILL_MD="$REPO_ROOT/06-ghl-install-pages/SKILL.md"
if [ -f "$F_06_SKILL_MD" ]; then
  python3 - "$F_06_SKILL_MD" "$TARGET" <<'PYEOF'
import re, sys
path, target = sys.argv[1], sys.argv[2]
content = open(path).read()
m = re.match(r'^(---\s*\n.*?\n---\s*\n)', content, re.DOTALL)
if m:
    head = m.group(1); rest = content[m.end():]
    new_head, n = re.subn(r'(?m)^(\s*version:\s*)(["\']?)[^"\'\n]*(["\']?)\s*$',
                          lambda mo: f'{mo.group(1)}{mo.group(2)}{target}{mo.group(3)}',
                          head, count=1)
    if n == 0:
        print(f"WARN: no version: field in {path} frontmatter", file=sys.stderr)
    open(path, "w").write(new_head + rest)
else:
    print(f"WARN: no YAML frontmatter in {path}", file=sys.stderr)
PYEOF
fi

echo ""
echo "Result:"
print_state

if ! check_drift; then
  echo ""
  echo "Bump completed but drift still detected. Manual inspection required."
  exit 1
fi

echo ""
echo "All 11 version markers agree at $TARGET"

# ─── Optional: tag + push ───────────────────────────────────────────────────
if [ "${2:-}" = "--tag" ] || [ "${3:-}" = "--tag" ]; then
  cd "$REPO_ROOT"
  if git rev-parse --git-dir > /dev/null 2>&1; then
    if git tag | grep -qx "$TARGET"; then
      echo "Tag $TARGET already exists locally; skipping tag creation."
    else
      git tag -a "$TARGET" -m "Release $TARGET"
      echo "Created git tag: $TARGET"
    fi
    if [ "${2:-}" = "--push" ] || [ "${3:-}" = "--push" ]; then
      git push origin "$TARGET"
      echo "Pushed tag $TARGET to origin"
    fi
  else
    echo "Not inside a git repo, skipping tag."
  fi
fi
