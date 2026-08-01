#!/usr/bin/env bash
# bump-version.sh — atomically bump the OpenClaw version across ALL files.
#
# The problem this solves: "the version" is encoded in 10 separate markers
# (across 9 files — README.md carries 2). Drift is mathematically guaranteed
# unless one tool updates all of them in one shot.
#
# WHAT THIS SCRIPT MUST NEVER ROLL: a MEASUREMENT artifact. A version marker
# says "this file ships in release X". A measurement says "I ran a check and
# this is what I observed". Rolling the second kind forges evidence — see the
# _qc-summary.md removal in the coverage history below.
#
# SINGLE SOURCE OF TRUTH: the drift-checked marker SET is enumerated ONCE in
# scripts/version-markers.json. That manifest is ALSO read by the repo-consistency
# gate (23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py, VERSION-MARKERS
# dimension) so the two tools can never disagree on which/how-many markers track
# /version. This script fails loudly at startup (see the guard below) if its own
# checked-marker count ever diverges from that manifest. The per-marker READ/WRITE
# logic still lives here (each marker needs bespoke rewrite handling), but the
# COUNT/SET is owned by the manifest.
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
#   T0-07 (this change): 10 markers — REMOVED the role-library
#                                   _qc-summary.md heading. It was never a
#                                   release marker; it is the recorded RESULT of
#                                   a Stage-2 quality-control run. Rolling it
#                                   restamped a frozen "244 / 244 — ALL PASS"
#                                   verdict, measured once on 2026-06-09 at
#                                   v11.0.1, onto every subsequent release: by
#                                   v20.0.85 the heading read v20.0.85 against a
#                                   sibling index declaring 438 roles across 36
#                                   departments, and the artifact renewed that
#                                   false certification automatically on every
#                                   single release. Every version gate stayed
#                                   green the whole time, because the marker DID
#                                   agree with /version — the number it agreed on
#                                   was simply meaningless.
#                                   That file is now rewritten ONLY by a real
#                                   quality-control run, which must write the
#                                   observed count and the real timestamp.
#                                   Enforced by
#                                   scripts/qc-assert-qc-summary-provenance.py.
#                                   DO NOT RE-ADD IT HERE.
#
# VERSION-BUMP CHECKLIST — SKILL 38 SELF-COUNT RE-VERIFICATION (added 2026-05-29;
#   extended 2026-07-05 FIX-XC-13c to ALSO cover INSTALL.md; extended 2026-07-30
#   FIX-XC-13d to ALSO cover the scripts/ TOTAL — the "91 scripts" SKILL.md bullet
#   drifted silently to 92 when qc-lattice-pointer.sh shipped in v1.9.2 because the
#   advisory checked protocols/references/highest-numbered-script but never the
#   scripts/ grand total; that gap is why the earlier 3 checks caught nothing):
#   Skill 38 hard-codes file counts in TWO docs — SKILL.md "What This Skill Ships"
#   AND INSTALL.md "What this installs" (protocols/, scripts/ range 00-NN,
#   references/, journey templates, and which Round-2 features are shipped). They
#   drift silently whenever a file is added/removed. On EVERY Skill-38 bump (its own
#   38-conversational-ai-system/skill-version.txt — NOT one of the 8 files
#   above), re-verify and correct those counts IN BOTH FILES. The exact command:
#     ( cd 38-conversational-ai-system && \
#       echo "protocols=$(ls -1 protocols/*.md | wc -l)" && \
#       echo "scripts=$(ls -1 scripts/*.sh | wc -l)" && \
#       echo "references=$(ls -1 references/*.md | wc -l)" && \
#       echo "journeys=$(ls -1d templates/journey-templates/*/ | wc -l)" && \
#       echo "highest-numbered-script=$(ls -1 scripts/ | grep -E '^[0-9]' | \
#         sed -E 's/-.*//' | sort -n | tail -1)" )
#   Then make BOTH SKILL.md's SELF-COUNTS comment/bullets AND INSTALL.md's
#   "What this installs" bullets match (protocol count, the `00`-`NN` script range,
#   the scripts/ TOTAL, reference count, and the shipped-vs-OFF-by-default feature
#   status — INSTALL.md must NEVER describe a shipped feature as "pending"). The
#   advisory diff below (skill38_doc_selfcount_advisory) prints WARNs against disk
#   to catch drift in both files, non-fatally, on every --check and bump. NOTE:
#   the scripts/-total check only runs against SKILL.md (the only doc that states
#   a "NN scripts" grand total in prose) — INSTALL.md documents the numbered range
#   + named script list, never a bare total, so looping it into that file would be
#   a permanent false WARN. The 23-key linter qc-23-key-bodies.sh + trinity
#   qc-trinity-registry.sh are part of scripts/.
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

# ─── SSOT GUARD — this script vs scripts/version-markers.json ────────────────
# BUMP_CHECKED_MARKERS = the number of markers check_drift() physically compares
# (and that the roll steps below rewrite). It MUST equal the marker count in the
# shared SSOT manifest, which the repo-consistency gate also reads. If someone
# adds/removes a marker in one place but not the other, this guard aborts before
# any file is touched, so the manifest and this script can never silently diverge.
BUMP_CHECKED_MARKERS=10
MARKERS_MANIFEST="$SCRIPT_DIR/version-markers.json"
if [ -f "$MARKERS_MANIFEST" ]; then
  MANIFEST_MARKER_COUNT=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['markers']))" "$MARKERS_MANIFEST" 2>/dev/null || echo "")
  if [ -n "$MANIFEST_MARKER_COUNT" ] && [ "$MANIFEST_MARKER_COUNT" != "$BUMP_CHECKED_MARKERS" ]; then
    echo "ERROR: version-marker SSOT drift — $MARKERS_MANIFEST lists $MANIFEST_MARKER_COUNT markers" >&2
    echo "       but bump-version.sh checks $BUMP_CHECKED_MARKERS. Reconcile the two (edit the manifest AND this script)." >&2
    exit 1
  fi
fi

# ─── The 10 version-marker locations (relative to repo root) ─────────────────
#     (enumerated as the SSOT in scripts/version-markers.json — keep in lockstep)
# NOT HERE, DELIBERATELY: the role-library _qc-summary.md heading. See T0-07 in
# the coverage history above — it is a measurement, not a release marker.
F_VERSION="$REPO_ROOT/version"
F_INSTALL="$REPO_ROOT/install.sh"
F_SKILL_VERSION="$REPO_ROOT/23-ai-workforce-blueprint/skill-version.txt"
F_INDEX_JSON="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json"
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

# Compare two vX.Y.Z strings numerically (NOT lexically — "v21.4.9" vs "v21.4.10"
# sorts wrong as text). Prints -1 if $1 < $2, 0 if equal, 1 if $1 > $2.
# Exits 1 and prints NOTHING if either argument is not vX.Y.Z, so every caller
# must treat an empty result as "could not compare" rather than as "equal".
semver_cmp() {
  python3 - "$1" "$2" <<'PYEOF'
import re, sys
def parse(s):
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', s.strip())
    return tuple(int(x) for x in m.groups()) if m else None
a, b = parse(sys.argv[1]), parse(sys.argv[2])
if a is None or b is None:
    sys.exit(1)
print((a > b) - (a < b))
PYEOF
}

# ─── SKILL 38 doc self-count advisory (FIX-XC-13c) ───────────────────────────
# Skill 38 hard-codes file counts in BOTH SKILL.md and INSTALL.md. This diffs the
# stated counts against what is actually on disk and prints a WARN on drift. It is
# ADVISORY ONLY — it never mutates a file and never changes the exit code (returns
# 0 unconditionally), so it can run under `set -e` without aborting a release bump.
# It exists so a Skill-38 file add/remove that forgot to update INSTALL.md (or
# SKILL.md) is surfaced at bump time instead of shipping stale docs.
skill38_doc_selfcount_advisory() {
  local d="$REPO_ROOT/38-conversational-ai-system"
  [ -d "$d" ] || return 0
  local p r s hi f
  p=$(ls -1 "$d"/protocols/*.md 2>/dev/null | wc -l | tr -d ' ')
  r=$(ls -1 "$d"/references/*.md 2>/dev/null | wc -l | tr -d ' ')
  s=$(ls -1 "$d"/scripts/*.sh 2>/dev/null | wc -l | tr -d ' ')
  hi=$(ls -1 "$d"/scripts/ 2>/dev/null | grep -E '^[0-9]' | sed -E 's/-.*//' | sort -n | tail -1)
  echo ""
  echo "Skill 38 doc self-count advisory (disk: protocols=$p references=$r scripts=$s highest-numbered-script=$hi):"
  for f in SKILL.md INSTALL.md; do
    [ -f "$d/$f" ] || continue
    grep -q "$p protocol" "$d/$f" 2>/dev/null \
      || echo "  WARN: 38-conversational-ai-system/$f does not state '$p protocol…' — protocol count may have drifted"
    grep -q "$r reference" "$d/$f" 2>/dev/null \
      || echo "  WARN: 38-conversational-ai-system/$f does not state '$r reference…' — reference count may have drifted"
  done
  if [ -f "$d/SKILL.md" ]; then
    grep -q "$s script" "$d/SKILL.md" 2>/dev/null \
      || echo "  WARN: 38-conversational-ai-system/SKILL.md does not state '$s script…' — total script count may have drifted"
  fi
  if [ -f "$d/INSTALL.md" ]; then
    grep -qE "\`00\`.\`$hi\`" "$d/INSTALL.md" 2>/dev/null \
      || echo "  WARN: 38-conversational-ai-system/INSTALL.md numbered-script range may not reach \`$hi\` (expected \`00\`-\`$hi\`)"
    if grep -qiE 'does not implement pending roadmap features' "$d/INSTALL.md" 2>/dev/null; then
      echo "  WARN: 38-conversational-ai-system/INSTALL.md still calls shipped Round-2 features 'pending' (see SKILL.md 'What This Skill Does NOT Do')"
    fi
  fi
  return 0
}

# ─── TAG-CONTAINMENT ADVISORY (--check) — the v21.4.25 signature ─────────────
# The exact assertion that would have caught the v21.4.25 incident: if an
# annotated tag matching ./version already exists, does that tag actually
# CONTAIN this commit? On 2026-07-30 it did not — `v21.4.25` is tagged at
# `9bac4243` and `git merge-base --is-ancestor 1fff3038 v21.4.25` returns false,
# so the release shipped a tag that does not carry the work it claimed.
#
# CI guard G4 (tag-ancestry-guard.yml) already asserts the OPPOSITE direction —
# "the tag is an ancestor of main" — and `v21.4.25` passed it, because being ON
# main says nothing about what a tag CONTAINS. This advisory is the missing half.
#
# ADVISORY, NOT FATAL, and deliberately so. It returns 0 unconditionally and
# never mutates a file, exactly like skill38_doc_selfcount_advisory above, so
# `--check`'s exit code is unchanged and the CI gate that delegates to it
# (version-consistency.yml) cannot go red on this. A hard assert would be wrong
# in two ordinary situations that are not incidents at all:
#   * on a feature branch the tag for the version you just bumped to does not
#     exist yet — it is cut after the merge — so every pre-merge --check and
#     every pre-commit run would fail;
#   * on main there is a legitimate window between "merge landed" and "tag
#     pushed" where HEAD is genuinely not yet inside the tag.
# The hard, fail-closed enforcement lives at BUMP time instead (see
# release_integrity_guard), where the collision can still be prevented rather
# than merely reported.
tag_containment_advisory() {
  git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
  local v tag_sha head_sha
  v=$(head -1 "$F_VERSION" 2>/dev/null | tr -d '[:space:]' || true)
  [ -n "$v" ] || return 0
  echo ""
  if ! git -C "$REPO_ROOT" rev-parse -q --verify "refs/tags/$v" >/dev/null 2>&1; then
    echo "Tag-containment advisory: no tag $v in this clone yet"
    echo "  (normal before the release is tagged, and on a shallow/tagless CI checkout)."
    return 0
  fi
  tag_sha=$(git -C "$REPO_ROOT" rev-parse "refs/tags/$v^{commit}" 2>/dev/null || echo "")
  head_sha=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "")
  if [ -z "$tag_sha" ] || [ -z "$head_sha" ]; then
    echo "Tag-containment advisory: could not resolve tag $v or HEAD — check SKIPPED."
    return 0
  fi
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$head_sha" "$tag_sha" 2>/dev/null; then
    echo "Tag-containment advisory: tag $v (${tag_sha:0:8}) CONTAINS HEAD (${head_sha:0:8}) — OK."
  else
    echo "Tag-containment advisory:"
    echo "  WARN: ./version says $v, and tag $v exists at ${tag_sha:0:8}, but that tag does"
    echo "  WARN: NOT contain HEAD (${head_sha:0:8}) — HEAD carries work that release does not ship."
    echo "  WARN: This is the v21.4.25 signature: anyone auditing releases by tag, and any client"
    echo "  WARN: box comparing update-skills.sh's ONBOARDING_VERSION against a tag, gets a FALSE"
    echo "  WARN: 'already current' answer."
    echo "  WARN: EXPECTED FIX: bump to the next patch and cut the tag on the commit that actually"
    echo "  WARN: contains the work (that is what v21.4.26 did for v21.4.25)."
    echo "  WARN: (Advisory only on a branch — before merge this is the normal pre-tag state.)"
  fi
  return 0
}

print_state() {
  read_current
  echo ""
  echo "Current version state (in this repo):"
  printf "  %-50s %s\n" "version" "$V_ROOT"
  printf "  %-50s %s\n" "install.sh ONBOARDING_VERSION" "$V_INSTALL"
  printf "  %-50s %s\n" "23-ai-workforce-blueprint/skill-version.txt" "$V_SKILL"
  printf "  %-50s %s\n" "templates/role-library/_index.json [version]" "$V_INDEX"
  printf "  %-50s %s\n" "README.md (this repo at vX.Y.Z)" "$V_README"
  printf "  %-50s %s\n" "README.md (Current Version: vX.Y.Z)" "$V_README_CURRENT"
  printf "  %-50s %s\n" "update-skills.sh ONBOARDING_VERSION" "$V_UPDATE_SKILLS"
  printf "  %-50s %s\n" "DIRECT-TO-AGENT-UPDATE-MESSAGE.md (**vX.Y.Z**)" "$V_DIRECT"
  printf "  %-50s %s\n" "cc-compat.json onboardingVersion" "$V_CC_COMPAT"
  printf "  %-50s %s\n" "23-ai-workforce-blueprint/SKILL.md [version:]" "$V_23_SKILL_MD"
  skill38_doc_selfcount_advisory
}

check_drift() {
  read_current
  N_ROOT=$(norm "$V_ROOT")
  N_INSTALL=$(norm "$V_INSTALL")
  N_SKILL=$(norm "$V_SKILL")
  N_INDEX=$(norm "$V_INDEX")
  N_README=$(norm "$V_README")
  N_README_CURRENT=$(norm "$V_README_CURRENT")
  N_UPDATE=$(norm "$V_UPDATE_SKILLS")
  N_DIRECT=$(norm "$V_DIRECT")
  N_CC_COMPAT=$(norm "$V_CC_COMPAT")
  N_23_SKILL_MD=$(norm "$V_23_SKILL_MD")
  if [ "$N_ROOT" = "$N_INSTALL" ] && [ "$N_ROOT" = "$N_SKILL" ] && \
     [ "$N_ROOT" = "$N_INDEX" ] && \
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
  tag_containment_advisory
  if check_drift; then
    echo ""
    echo "All $BUMP_CHECKED_MARKERS version markers agree."
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

# ─── RELEASE-INTEGRITY GUARD — stale base / colliding version ────────────────
# WHY THIS EXISTS (real incident, 2026-07-30, not a hypothetical):
# This script rolls all 10 markers to whatever TARGET the caller supplies, and
# the caller derives TARGET by reading the WORKING TREE's ./version and adding
# one. Two pull requests cut from the same base therefore compute the SAME next
# version. Git then auto-merges the byte-identical `version` edit with NO
# conflict, so the second merge ships real content whose version markers are
# identical to its parent's: the version never advances for that change, and the
# annotated tag ends up pointing at a commit that does not contain the work it
# claims to ship.
#   PR #778 and PR #779 were both cut from f9c6efb4 at v21.4.24 and both bumped
#   to v21.4.25. #778 merged first and took the tag at 9bac4243. The result:
#   `git merge-base --is-ancestor 1fff3038 v21.4.25` returns FALSE — the
#   presentations doctrine fix that release claimed is NOT in it. It also turned
#   CI guard G3 red on main until v21.4.26 corrected it.
# Nothing caught it: G1 saw a tag, G2 saw a CHANGELOG entry, G4 saw the tag was
# on main, and --check saw 10 markers agreeing. They agreed on the wrong number.
#
# THE FIX: compare TARGET against origin/main's ./version — the real, shipped
# release floor — instead of trusting the working tree, and against the tags
# that already exist locally and on the remote.
#
# FAIL-CLOSED, WITH NO BYPASS FLAG. A blocked bump costs one `git merge`; a
# wrong tag silently lies to every release audit and lets update-skills.sh tell
# a client box it is current when it is not. There is deliberately no
# --force/--skip-guard escape hatch: an escape hatch on a guard this cheap to
# satisfy just becomes the thing everyone types.
#
# OFFLINE / BARE CI RUNNER: `git fetch` failing is NOT fatal. The guard degrades
# to the last-known origin/main ref (if this clone has one) plus the LOCAL tag
# list, and says loudly, line by line, which checks it could not perform. A
# legitimate offline bump still completes.
guard_fatal() {
  echo "" >&2
  echo "═══════════════════════════════════════════════════════════════════════" >&2
  echo "RELEASE-INTEGRITY GUARD — BUMP REFUSED (no file was modified)" >&2
  echo "═══════════════════════════════════════════════════════════════════════" >&2
  local line
  for line in "$@"; do echo "  $line" >&2; done
  echo "" >&2
  exit 1
}

release_integrity_guard() {
  local target="$1"
  local remote="origin" branch="main"
  local fetched=0 base_ver="" tree_ver="" cmp_tree="" cmp_target=""
  local ls_out="" ls_rc=0

  if ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    echo ""
    echo "Release-integrity guard: not a git repo — checks SKIPPED."
    return 0
  fi

  echo ""
  echo "Release-integrity guard (target $target vs $remote/$branch):"

  # 1. Refresh our view of the remote. Non-fatal by design.
  if git -C "$REPO_ROOT" fetch --quiet "$remote" "$branch" 2>/dev/null; then
    fetched=1
    echo "  fetched $remote/$branch"
  else
    echo "  WARN: could not fetch $remote/$branch (offline, or no such remote)."
    echo "  WARN: falling back to the last-known $remote/$branch ref and LOCAL tags only."
  fi

  # 2. The release floor is origin/main's ./version, NOT the working tree's.
  #    Prefer FETCH_HEAD (just fetched, therefore current) over the tracking ref.
  if [ "$fetched" -eq 1 ]; then
    base_ver=$(git -C "$REPO_ROOT" show FETCH_HEAD:version 2>/dev/null | head -1 | tr -d '[:space:]' || true)
  fi
  if [ -z "$base_ver" ]; then
    base_ver=$(git -C "$REPO_ROOT" show "$remote/$branch:version" 2>/dev/null | head -1 | tr -d '[:space:]' || true)
  fi
  tree_ver=$(head -1 "$F_VERSION" 2>/dev/null | tr -d '[:space:]' || true)

  if [ -z "$base_ver" ]; then
    echo "  WARN: no $remote/$branch ./version available in this clone."
    echo "  WARN: CANNOT verify $target is ahead of the released floor — the stale-base"
    echo "  WARN: and colliding-version checks are SKIPPED for this run."
  else
    echo "  $remote/$branch ./version = $base_ver ; working tree ./version = $tree_ver"
    cmp_tree=$(semver_cmp "$tree_ver" "$base_ver" 2>/dev/null || echo "")
    cmp_target=$(semver_cmp "$target" "$base_ver" 2>/dev/null || echo "")
    if [ -z "$cmp_tree" ] || [ -z "$cmp_target" ]; then
      echo "  WARN: a version is not parseable as vX.Y.Z (tree=$tree_ver base=$base_ver"
      echo "  WARN: target=$target) — ordering comparison SKIPPED."
    else
      # 2a. STALE BASE — the working tree is behind what main has already shipped.
      #     This is the root cause of the v21.4.25 collision.
      if [ "$cmp_tree" -lt 0 ]; then
        guard_fatal \
          "STALE BASE: working tree ./version ($tree_ver) is BEHIND $remote/$branch ($base_ver)." \
          "" \
          "Your branch was cut before $base_ver shipped, so any 'next patch' computed from" \
          "the working tree collides with a release that already exists. Merging that edit" \
          "produces NO git conflict, which is exactly how v21.4.25 shipped a tag that does" \
          "not contain the work it claimed (merge-base --is-ancestor 1fff3038 v21.4.25 = false)." \
          "" \
          "FIX:  git fetch $remote $branch && git merge $remote/$branch" \
          "      then re-read ./version and bump from THAT value."
      fi
      # 2b. COLLIDING VERSION — target does not advance past the released floor.
      if [ "$cmp_target" -le 0 ]; then
        guard_fatal \
          "COLLIDING VERSION: target $target is not strictly ahead of $remote/$branch ($base_ver)." \
          "" \
          "$remote/$branch has already shipped $base_ver. Rolling the markers to $target would" \
          "either re-issue a released version or move it backwards, and git would auto-merge" \
          "the identical marker edits with no conflict — so nothing downstream would notice." \
          "" \
          "FIX:  git fetch $remote $branch && git merge $remote/$branch" \
          "      then bump to the next patch AFTER $base_ver."
      fi
      echo "  OK: $target is strictly ahead of the released floor $base_ver"
    fi
  fi

  # 3. The target tag must not already exist — locally or on the remote.
  #    A tag that exists is a release that shipped; re-pointing it rewrites history.
  if git -C "$REPO_ROOT" rev-parse -q --verify "refs/tags/$target" >/dev/null 2>&1; then
    guard_fatal \
      "TAG ALREADY EXISTS LOCALLY: $target is tagged at $(git -C "$REPO_ROOT" rev-parse --short "refs/tags/$target^{commit}" 2>/dev/null || echo '?')." \
      "" \
      "That version has already been cut. Bumping to it again would produce a second," \
      "different tree claiming the same release, which is precisely the v21.4.25 failure." \
      "" \
      "FIX:  pick the next unused patch, or delete the stray local tag if it was never pushed."
  fi
  ls_out=$(git -C "$REPO_ROOT" ls-remote --tags "$remote" "refs/tags/$target" 2>/dev/null) && ls_rc=0 || ls_rc=$?
  if [ "$ls_rc" -ne 0 ]; then
    echo "  WARN: could not list remote tags (offline) — remote tag collision NOT checked."
    echo "  WARN: the local tag check above still ran."
  elif [ -n "$ls_out" ]; then
    guard_fatal \
      "TAG ALREADY PUBLISHED ON $remote: $target exists on the remote." \
      "" \
      "Another branch has already released $target. Continuing would ship a second tree" \
      "under a version that is already public." \
      "" \
      "FIX:  git fetch $remote $branch && git merge $remote/$branch, then bump past $target."
  else
    echo "  OK: tag $target does not exist locally or on $remote"
  fi

  return 0
}

release_integrity_guard "$TARGET"

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

# 5. DELETED (T0-07) — the role-library quality-control summary is NOT rolled.
#    A release does not re-run quality control, so a release must not restamp a
#    quality-control result. The removed block rewrote the summary's
#    "Role Library vX.Y.Z" heading on every bump while the generation date, the
#    role count and the ALL PASS verdict stayed frozen at a single run from
#    2026-06-09. That artifact is regenerated ONLY by a real run, which writes
#    the observed role count and the real timestamp.
#    scripts/qc-assert-qc-summary-provenance.py fails CI if it is ever restamped
#    or re-registered as a version marker. Do not add a step 5 back.

# 6. /README.md — roll ONLY the two TRACKED README version markers:
#    #6 "this repo at vX.Y.Z" and #9 "Current Version: vX.Y.Z". — v10.14.34;
#    narrowed U92.
#    U92 CO-FIX: earlier revisions ALSO rewrote EVERY inline "(vX.Y.Z)" in the
#    first 200 lines as a heading heuristic. That silently rolled the version
#    marker embedded in historical "**NOTE (vX.Y.Z)**" release lines at the top
#    of the README — rewriting released, changelog-style prose that the standing
#    "git history / released entries are never rewritten" doctrine forbids, and
#    (because two of those historical NOTE lines legitimately carry the retired
#    coded term inside them) turning those pre-existing lines into "added" lines
#    on every bump. That made the docs-language guard
#    (scripts/check-docs-language.py) go RED on its OWN version-bump ripple
#    (README.md:20 / README.md:22). Those NOTE lines are NOT tracked version
#    markers (they are not in scripts/version-markers.json), so freezing them
#    cannot drift /version or trip any version gate. Only the two tracked
#    markers are rolled now; the inline "(vX.Y.Z)" heuristic is removed.
if [ -f "$F_README" ]; then
  python3 - <<PYEOF
import re
p = "$F_README"
target = "$TARGET"
content = open(p).read()
# Marker #6: "this repo at vX.Y.Z." prose line.
new = re.sub(r'(this repo at )v[0-9]+\.[0-9]+\.[0-9]+',
             r'\1' + target, content)
# Marker #9 (v10.15.16): "Current Version: vX.Y.Z" prose line. A SECOND,
# independent version marker in README.md; roll it in lockstep so it can never
# drift again (it silently drifted to v10.15.15 before it was tracked here).
new = re.sub(r'(Current Version: )v[0-9]+\.[0-9]+\.[0-9]+',
             r'\1' + target, new)
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
echo "All $BUMP_CHECKED_MARKERS version markers agree at $TARGET"

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
