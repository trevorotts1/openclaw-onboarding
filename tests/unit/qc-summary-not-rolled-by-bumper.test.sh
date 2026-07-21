#!/usr/bin/env bash
# qc-summary-not-rolled-by-bumper.test.sh — a release must not restamp a measurement.
#
# FINDING T0-07. scripts/bump-version.sh used to rewrite the role-library
# quality-control summary's "Role Library vX.Y.Z" heading on every release,
# because the file was registered as a repo version marker. Nothing re-ran
# quality control; only the number moved. The summary's own generation date,
# role count and pass verdict were frozen at a single run from 2026-06-09
# (v11.0.1) and rode forward onto every release through v20.0.85.
#
# This test pins BOTH halves of the fix, against the real bump-version.sh:
#
#   1. A full version bump leaves the quality-control summary BYTE-IDENTICAL.
#   2. A full version bump still rolls every OTHER marker correctly, and
#      --check agrees afterwards. (Removing a marker must not break the bumper.)
#
# It runs the real script against a disposable fixture repo, so it measures
# behaviour rather than reading the source for a pattern.
#
# Usage:
#   tests/unit/qc-summary-not-rolled-by-bumper.test.sh
#   tests/unit/qc-summary-not-rolled-by-bumper.test.sh --repo-root DIR
#       ^ run the bumper/manifest FROM DIR (used to demonstrate the pre-fix
#         failure against an older checkout).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ "${1:-}" = "--repo-root" ]; then
  REPO_ROOT="$(cd "$2" && pwd)"
fi

echo "Testing bump-version.sh from: $REPO_ROOT"

FIX="$(mktemp -d "${TMPDIR:-/tmp}/qc-summary-bumper-test.XXXXXX")"
cleanup() { rm -rf "$FIX"; }
trap cleanup EXIT

FAILURES=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAILURES=$((FAILURES + 1)); }

# ─── Build a minimal fixture repo carrying every marker the bumper rolls ─────
START_VER="v1.0.0"
TARGET_VER="v99.44.7"

mkdir -p "$FIX/scripts" \
         "$FIX/23-ai-workforce-blueprint/templates/role-library"

cp "$REPO_ROOT/scripts/bump-version.sh"     "$FIX/scripts/bump-version.sh"
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

# The artifact under protection. It carries a version token deliberately — that
# token is the tripwire. If any future revision re-adds a roll step, this file
# changes and the test goes red.
QC_SUMMARY="$FIX/23-ai-workforce-blueprint/templates/role-library/_qc-summary.md"
cat > "$QC_SUMMARY" <<'QCEOF'
# Stage 2 QC Summary — role library

**Measurement status:** not-measured
**Last measured at repo version:** v0.9.9
**Last measured (UTC):** 2020-01-01
**Roles observed at last measurement:** 3

The run on record is Role Library v0.9.9. A release must not touch this file.
QCEOF

BEFORE_SHA="$(shasum -a 256 "$QC_SUMMARY" | cut -d' ' -f1)"

# ─── Run the real bumper ────────────────────────────────────────────────────
echo ""
echo "== running: bump-version.sh $TARGET_VER =="
BUMP_OUT="$(cd "$FIX" && bash scripts/bump-version.sh "$TARGET_VER" 2>&1)"
BUMP_RC=$?
if [ "$BUMP_RC" -eq 0 ]; then
  pass "bump completed end-to-end (exit 0)"
else
  fail "bump exited $BUMP_RC — a version bump must still work"
  echo "$BUMP_OUT" | sed 's/^/      /'
fi

# ─── 1. THE INVARIANT: the quality-control summary was not touched ──────────
echo ""
echo "== 1. the quality-control summary must be byte-identical after a release =="
AFTER_SHA="$(shasum -a 256 "$QC_SUMMARY" | cut -d' ' -f1)"
if [ "$BEFORE_SHA" = "$AFTER_SHA" ]; then
  pass "_qc-summary.md unchanged by the bump (sha256 ${BEFORE_SHA:0:12})"
else
  fail "_qc-summary.md WAS REWRITTEN by the version bump — a release restamped a measurement"
  echo "      before sha256: $BEFORE_SHA"
  echo "      after  sha256: $AFTER_SHA"
  echo "      --- what the release changed ---"
  grep -n 'Role Library' "$QC_SUMMARY" | sed 's/^/      /'
fi

# The measured-at version must still be the one the fixture recorded.
if grep -qF 'Role Library v0.9.9' "$QC_SUMMARY"; then
  pass "recorded measurement version v0.9.9 survived the release"
else
  fail "the recorded measurement version was rewritten to the release version"
fi

# ─── 2. every OTHER marker still rolls, and --check agrees ──────────────────
echo ""
echo "== 2. removing the marker must not break the bump =="
NOV="${TARGET_VER#v}"
check_marker() {
  # $1 = label, $2 = file, $3 = expected literal to find
  if grep -qF -- "$3" "$FIX/$2"; then
    pass "$1 rolled to $TARGET_VER"
  else
    fail "$1 did NOT roll to $TARGET_VER (looked for '$3' in $2)"
  fi
}
check_marker "/version"                       "version"                                              "$TARGET_VER"
check_marker "install.sh"                     "install.sh"                                           "ONBOARDING_VERSION=\"$TARGET_VER\""
check_marker "update-skills.sh"               "update-skills.sh"                                     "ONBOARDING_VERSION=\"$TARGET_VER\""
check_marker "README this-repo-at"            "README.md"                                            "this repo at $TARGET_VER"
check_marker "README Current-Version"         "README.md"                                            "Current Version: $TARGET_VER"
check_marker "DIRECT-TO-AGENT"                "DIRECT-TO-AGENT-UPDATE-MESSAGE.md"                    "**$TARGET_VER**"
check_marker "cc-compat onboardingVersion"    "cc-compat.json"                                       "\"onboardingVersion\": \"$TARGET_VER\""
check_marker "23 skill-version.txt"           "23-ai-workforce-blueprint/skill-version.txt"          "$NOV"
check_marker "23 SKILL.md frontmatter"        "23-ai-workforce-blueprint/SKILL.md"                   "version: $NOV"
check_marker "_index.json version"            "23-ai-workforce-blueprint/templates/role-library/_index.json" "\"version\": \"$NOV\""

echo ""
echo "== 3. --check agrees after the bump =="
CHECK_OUT="$(cd "$FIX" && bash scripts/bump-version.sh --check 2>&1)"
CHECK_RC=$?
if [ "$CHECK_RC" -eq 0 ]; then
  pass "bump-version.sh --check exits 0 after the bump"
else
  fail "bump-version.sh --check exits $CHECK_RC after its own bump"
  echo "$CHECK_OUT" | sed 's/^/      /'
fi

# The --check report must no longer enumerate the quality-control summary as a
# tracked marker; if it does, the marker is still wired in somewhere.
if echo "$CHECK_OUT" | grep -qF '_qc-summary.md'; then
  fail "--check still lists _qc-summary.md as a tracked version marker"
else
  pass "--check does not list _qc-summary.md as a tracked version marker"
fi

echo ""
if [ "$FAILURES" -ne 0 ]; then
  echo "QC-SUMMARY / BUMPER: FAIL ($FAILURES assertion(s))"
  echo "A release must not rewrite a quality-control result. See finding T0-07."
  exit 1
fi
echo "QC-SUMMARY / BUMPER: PASS (release leaves the measurement alone; every other marker still rolls)"
exit 0
