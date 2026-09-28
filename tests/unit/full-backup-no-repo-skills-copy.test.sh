#!/usr/bin/env bash
# full-backup-no-repo-skills-copy.test.sh — the Back Yourself Up full backup no longer
# copies the onboarding repo's skills (or an onboarding clone) into every backup.
#
#   T1  the run succeeds
#   T2  the box's own custom skill IS in the backup
#   T3  the installed version + manifest are recorded (enough to re-install the repo skills)
#   T4  repo-owned skills, shared-utils, universal-sops and an onboarding clone are NOT copied
#   T5  an openclaw-onboarding clone under ~/clawd/projects is NOT copied; other projects are
#   C1  CONTROL: a box with no content manifest still gets the whole skills folder
#       (without a record of what the repo owns, nothing may be dropped)
#
# Hermetic: fixture HOMEs in a tempdir. No network, no real backup, no box.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/02-back-yourself-up-protocol/scripts/full-backup.sh"
PASS=0; FAIL=0
pass() { echo "PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL  $1"; FAIL=$((FAIL+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
TODAY="$(date +%Y-%m-%d)"

build_home() {  # <home> <with-manifest 0|1>
  local h=$1 sk="$1/.openclaw/skills"
  mkdir -p "$h/clawd/projects/openclaw-onboarding" "$h/clawd/projects/client-site" "$sk"
  printf 'agents\n' > "$h/clawd/AGENTS.md"; printf 'tools\n' > "$h/clawd/TOOLS.md"
  printf '{"fixture":true}\n' > "$h/.openclaw/openclaw.json"
  printf 'clone file\n' > "$h/clawd/projects/openclaw-onboarding/README.md"
  printf 'site\n'       > "$h/clawd/projects/client-site/index.html"
  for n in 01-alpha 02-beta shared-utils universal-sops my-custom-skill; do
    mkdir -p "$sk/$n"; printf '%s\n' "$n" > "$sk/$n/SKILL.md"
  done
  mkdir -p "$sk/onboarding"; git -C "$sk/onboarding" init -q
  git -C "$sk/onboarding" remote add origin https://github.com/trevorotts1/openclaw-onboarding.git
  printf 'v9.9.9\n' > "$sk/.onboarding-version"
  if [ "$2" = 1 ]; then
    printf '{"version":"v9.9.9","src_git_sha":"%s","skills":{"01-alpha":"d1","02-beta":"d2"}}\n' \
      "0123456789abcdef0123456789abcdef01234567" > "$sk/.onboarding-content-manifest.json"
  fi
}
run_backup() { env HOME="$1" PATH="/usr/bin:/bin:/usr/local/bin" /bin/bash "$SCRIPT" > "$1.log" 2>&1; }

H="$TMP/home"; build_home "$H" 1
if run_backup "$H"; then pass "T1 full backup exit 0"; else fail "T1 full backup failed: $(tail -5 "$H.log")"; fi
B="$H/Downloads/openclaw-backups/full-backup/full-backup-$TODAY"
[ -f "$B/skills/my-custom-skill/SKILL.md" ] && pass "T2 custom skill backed up" || fail "T2 custom skill missing"
if [ -f "$B/skills/.onboarding-version" ] && [ -f "$B/skills/.onboarding-content-manifest.json" ]; then
  pass "T3 installed version + manifest recorded"; else fail "T3 version record missing"; fi
LEAK=""
# searched at any depth: the old step copied the folder one level down (skills/skills/...)
for n in 01-alpha 02-beta shared-utils universal-sops onboarding; do
  [ -n "$(find "$B" -type d -name "$n" 2>/dev/null | head -1)" ] && LEAK="$LEAK $n"
done
[ -z "$LEAK" ] && pass "T4 repo-owned skills and the onboarding clone were not copied" || fail "T4 copied anyway:$LEAK"
if [ ! -e "$B/projects/openclaw-onboarding" ] && [ -f "$B/projects/client-site/index.html" ]; then
  pass "T5 onboarding clone under projects skipped, other projects kept"; else fail "T5 projects handling wrong"; fi

HC="$TMP/home-nomanifest"; build_home "$HC" 0
run_backup "$HC"
BC="$HC/Downloads/openclaw-backups/full-backup/full-backup-$TODAY"
if [ -f "$BC/skills/skills/01-alpha/SKILL.md" ] || [ -f "$BC/skills/01-alpha/SKILL.md" ]; then
  pass "C1 control: no manifest -> whole skills folder still copied"
else fail "C1 CONTROL: a box with no manifest lost its skills from the backup"; fi

echo "----"; echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]
