#!/usr/bin/env bash
# bump-version.sh — atomically bump the OpenClaw version across ALL files.
#
# The problem this solves: "the version" is encoded in 8 separate files. Drift
# is mathematically guaranteed unless one tool updates all 8 in one shot.
#
# Coverage history:
#   v10.14.0 and earlier: 5 files (version, install.sh, skill-version.txt,
#                                  _index.json, _qc-summary.md)
#   v10.14.34+:           8 files — added README.md, update-skills.sh,
#                                   DIRECT-TO-AGENT-UPDATE-MESSAGE.md
#                                   (per 2-day forensics finding #23)
#
# Usage:
#   ./scripts/bump-version.sh v10.6.2          # update all 8 files
#   ./scripts/bump-version.sh v10.6.2 --tag    # also create a git tag
#   ./scripts/bump-version.sh v10.6.2 --tag --push   # also push the tag
#   ./scripts/bump-version.sh --check          # exit 1 if drift; print state
#
# Works identically on Mac and VPS repos (paths are the same).
set -euo pipefail

# ─── Locate the repo root ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -f "$REPO_ROOT/version" ] || [ ! -f "$REPO_ROOT/install.sh" ]; then
  echo "ERROR: $REPO_ROOT does not look like an OpenClaw repo (missing /version or /install.sh)" >&2
  exit 1
fi

# ─── The 8 locations (relative to repo root) ─────────────────────────────────
F_VERSION="$REPO_ROOT/version"
F_INSTALL="$REPO_ROOT/install.sh"
F_SKILL_VERSION="$REPO_ROOT/23-ai-workforce-blueprint/skill-version.txt"
F_INDEX_JSON="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json"
F_QC_SUMMARY="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_qc-summary.md"
F_README="$REPO_ROOT/README.md"
F_UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"
F_DIRECT_TO_AGENT="$REPO_ROOT/DIRECT-TO-AGENT-UPDATE-MESSAGE.md"

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
  else
    V_README="MISSING"
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
  printf "  %-50s %s\n" "update-skills.sh ONBOARDING_VERSION" "$V_UPDATE_SKILLS"
  printf "  %-50s %s\n" "DIRECT-TO-AGENT-UPDATE-MESSAGE.md (**vX.Y.Z**)" "$V_DIRECT"
}

check_drift() {
  read_current
  N_ROOT=$(norm "$V_ROOT")
  N_INSTALL=$(norm "$V_INSTALL")
  N_SKILL=$(norm "$V_SKILL")
  N_INDEX=$(norm "$V_INDEX")
  N_QC=$(norm "$V_QC")
  N_README=$(norm "$V_README")
  N_UPDATE=$(norm "$V_UPDATE_SKILLS")
  N_DIRECT=$(norm "$V_DIRECT")
  if [ "$N_ROOT" = "$N_INSTALL" ] && [ "$N_ROOT" = "$N_SKILL" ] && \
     [ "$N_ROOT" = "$N_INDEX" ] && [ "$N_ROOT" = "$N_QC" ] && \
     [ "$N_ROOT" = "$N_README" ] && [ "$N_ROOT" = "$N_UPDATE" ] && \
     [ "$N_ROOT" = "$N_DIRECT" ]; then
    return 0
  fi
  return 1
}

# ─── --check mode: report drift and exit ─────────────────────────────────────
if [ "${1:-}" = "--check" ]; then
  print_state
  if check_drift; then
    echo ""
    echo "All 8 locations agree."
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

echo ""
echo "Result:"
print_state

if ! check_drift; then
  echo ""
  echo "Bump completed but drift still detected. Manual inspection required."
  exit 1
fi

echo ""
echo "All 8 locations agree at $TARGET"

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
