#!/usr/bin/env bash
# ============================================================================
# backup-retention.test.sh
#
# Regression guard for OPENCLAW-BACKUP-RETENTION-V1 (lib-shared.sh, duplicated
# into update-skills.sh). The ONE property this whole test exists for:
#
#     backups can never accumulate again, and retention can never delete
#     something it did not itself create — least of all the backup the
#     current run just took.
#
# Every test is that property asked a different way.
#
#   T1  block PRESENT + identical  — lib-shared.sh and update-skills.sh both
#                                    carry the block, byte-for-byte. update-skills.sh
#                                    is curl-piped and cannot source the library,
#                                    so a drifted copy silently reverts one of the
#                                    two update paths to unbounded backups.
#   T2  keeps exactly N            — with N+2 pre-existing backups plus this run's,
#                                    a prune leaves exactly N.
#   T3  never touches the newest   — the newest backup survives every prune.
#   T4  current run never pruned   — a current backup that sorts OLDER than N
#                                    others is still kept.
#   T5  unrelated entries untouched— siblings that do not match the literal
#                                    prefix + 4-digit year (including an
#                                    untimestamped sibling that SHARES the
#                                    prefix) are never deleted or counted.
#   T6  unsafe prefixes REFUSED    — empty, dot, too-short, path-separator and
#                                    glob-metacharacter prefixes delete nothing.
#   T7  disk pre-check fails LOUD  — a short-space pre-check returns nonzero and
#                                    prints the path AND the shortfall.
#   T8  failed backup prunes NOTHING — when the pre-check refuses, no prune runs
#                                    and every existing backup survives. Asserted
#                                    behaviourally AND against the real ordering
#                                    in update-skills.sh (prune is inside the
#                                    "backup dir exists" guard, and the pre-check
#                                    exits before mkdir).
#   T9  OPENCLAW_BACKUP_KEEP       — the override is honoured; garbage and 0 fall
#                                    back to the safe default of 3.
#   T10 every site wired           — each known update-path backup site calls the
#                                    policy. A new backup site added without
#                                    retention regresses this test.
#
# Self-contained: bash + coreutils. Temp dirs and fake backups only. No box, no
# network, no real backup is ever read or written.
#
# Run:  bash tests/unit/backup-retention.test.sh
# ============================================================================
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

LIB_SHARED="$REPO_ROOT/lib-shared.sh"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"
INSTALL_SH="$REPO_ROOT/install.sh"
PODBEAN_ROLL="$REPO_ROOT/scripts/fleet-roll/podbean-publish-provision-roll.sh"

BEGIN_MARK='#=== BEGIN OPENCLAW-BACKUP-RETENTION-V1 ==='
END_MARK='#=== END OPENCLAW-BACKUP-RETENTION-V1 ==='

PASS=0
FAIL=0
ok()   { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; [ $# -ge 2 ] && printf '        %s\n' "$2"; }
head2() { printf '\n== %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/backup-retention-test.XXXXXX")" || exit 1
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Extract the marker-delimited block from a file.
extract_block() {
  awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b { f=1 }
    f       { print }
    $0 == e { f=0 }
  ' "$1"
}

# ---------------------------------------------------------------------------
# T1 — the block exists in both copies and they are byte-identical
# ---------------------------------------------------------------------------
head2 "T1 block present in both copies and identical"

extract_block "$LIB_SHARED"    > "$WORK/block-lib.sh"    2>/dev/null
extract_block "$UPDATE_SKILLS" > "$WORK/block-update.sh" 2>/dev/null

if [ -s "$WORK/block-lib.sh" ]; then
  ok "lib-shared.sh carries the retention block"
else
  bad "lib-shared.sh carries the retention block" "no $BEGIN_MARK ... $END_MARK found in $LIB_SHARED"
fi

if [ -s "$WORK/block-update.sh" ]; then
  ok "update-skills.sh carries the retention block"
else
  bad "update-skills.sh carries the retention block" "no $BEGIN_MARK ... $END_MARK found in $UPDATE_SKILLS"
fi

if [ -s "$WORK/block-lib.sh" ] && [ -s "$WORK/block-update.sh" ]; then
  if diff -u "$WORK/block-lib.sh" "$WORK/block-update.sh" > "$WORK/block.diff" 2>&1; then
    ok "the two copies are byte-identical (no drift)"
  else
    bad "the two copies are byte-identical (no drift)" "$(head -20 "$WORK/block.diff")"
  fi
else
  bad "the two copies are byte-identical (no drift)" "one or both blocks missing"
fi

# Everything below needs the functions. Source the lib-shared copy — if it is
# missing, the remaining tests must FAIL loudly rather than silently skip.
if [ -s "$WORK/block-lib.sh" ]; then
  # shellcheck source=/dev/null
  . "$WORK/block-lib.sh"
fi
if ! command -v oc_backup_prune >/dev/null 2>&1; then
  bad "retention functions are loadable" "oc_backup_prune is undefined — remaining behavioural tests cannot run"
  printf '\n== SUMMARY\n  PASS %d\n  FAIL %d\n' "$PASS" "$FAIL"
  exit 1
fi
ok "retention functions are loadable"

# Helper: build a parent dir with the given timestamped backups (dirs).
seed_dirs() {
  local parent="$1"; shift
  mkdir -p "$parent"
  local ts
  for ts in "$@"; do mkdir -p "$parent/skills-backup-$ts"; done
}
count_matching() {
  find "$1" -mindepth 1 -maxdepth 1 -name "$2" 2>/dev/null | wc -l | tr -d ' '
}

# ---------------------------------------------------------------------------
# T2 — N+2 existing backups -> exactly N survive
# ---------------------------------------------------------------------------
head2 "T2 keeps exactly N (default 3)"
P="$WORK/t2"
# 5 total: 4 older + this run's = N+2 beyond the keep count
seed_dirs "$P" 20260101-000000 20260102-000000 20260103-000000 20260104-000000 20260105-000000
BEFORE=$(count_matching "$P" 'skills-backup-*')
oc_backup_prune "$P" "skills-backup-" "$P/skills-backup-20260105-000000" > "$WORK/t2.log" 2>&1
AFTER=$(count_matching "$P" 'skills-backup-*')
if [ "$BEFORE" = "5" ] && [ "$AFTER" = "3" ]; then
  ok "5 backups -> 3 kept (before=$BEFORE after=$AFTER)"
else
  bad "5 backups -> 3 kept" "before=$BEFORE after=$AFTER"
fi
if grep -q 'PRUNE:' "$WORK/t2.log" && grep -q 'KEEP' "$WORK/t2.log"; then
  ok "prune logged both what it kept and what it removed (not silent)"
else
  bad "prune logged both what it kept and what it removed" "$(cat "$WORK/t2.log")"
fi

# ---------------------------------------------------------------------------
# T3 — the newest is never removed
# ---------------------------------------------------------------------------
head2 "T3 never prunes the newest"
if [ -d "$P/skills-backup-20260105-000000" ] && [ -d "$P/skills-backup-20260104-000000" ] && [ -d "$P/skills-backup-20260103-000000" ]; then
  ok "the 3 newest survived"
else
  bad "the 3 newest survived" "$(ls -1 "$P" | tr '\n' ' ')"
fi
if [ ! -d "$P/skills-backup-20260101-000000" ] && [ ! -d "$P/skills-backup-20260102-000000" ]; then
  ok "the 2 oldest were removed"
else
  bad "the 2 oldest were removed" "$(ls -1 "$P" | tr '\n' ' ')"
fi

# ---------------------------------------------------------------------------
# T4 — the current run's backup is kept even when it sorts oldest
# ---------------------------------------------------------------------------
head2 "T4 the current run's backup is never pruned"
P="$WORK/t4"
seed_dirs "$P" 20250101-000000 20260101-000000 20260102-000000 20260103-000000 20260104-000000
# Pretend the OLDEST-sorting entry is the one this run just wrote. It falls
# outside the newest-3 window, so only rule 2 can save it.
oc_backup_prune "$P" "skills-backup-" "$P/skills-backup-20250101-000000" > "$WORK/t4.log" 2>&1
if [ -d "$P/skills-backup-20250101-000000" ]; then
  ok "current run's backup survived despite sorting oldest"
else
  bad "current run's backup survived despite sorting oldest" "$(cat "$WORK/t4.log")"
fi
if grep -q 'current run -- never pruned' "$WORK/t4.log"; then
  ok "the save was logged with its reason"
else
  bad "the save was logged with its reason" "$(cat "$WORK/t4.log")"
fi

# ---------------------------------------------------------------------------
# T5 — unrelated siblings are never touched
# ---------------------------------------------------------------------------
head2 "T5 unrelated entries in the same parent are untouched"
P="$WORK/t5"
seed_dirs "$P" 20260101-000000 20260102-000000 20260103-000000 20260104-000000 20260105-000000
mkdir -p "$P/some-other-project" "$P/cc-backup-20260101-000000"
: > "$P/README.txt"
: > "$P/notes-2026.md"
# Shares the prefix but is NOT timestamped — must never match or consume a slot.
mkdir -p "$P/skills-backup-README"
oc_backup_prune "$P" "skills-backup-" "$P/skills-backup-20260105-000000" > "$WORK/t5.log" 2>&1
UNTOUCHED=1
for keepme in some-other-project cc-backup-20260101-000000 README.txt notes-2026.md skills-backup-README; do
  [ -e "$P/$keepme" ] || { UNTOUCHED=0; bad "unrelated entry survived: $keepme" "it was deleted"; }
done
[ "$UNTOUCHED" = "1" ] && ok "all 5 unrelated siblings survived (incl. a prefix-sharing untimestamped dir)"
# and the untimestamped sibling must not have eaten a keep slot:
if [ -d "$P/skills-backup-20260103-000000" ]; then
  ok "the untimestamped sibling did not consume a keep slot"
else
  bad "the untimestamped sibling did not consume a keep slot" "$(cat "$WORK/t5.log")"
fi

# ---------------------------------------------------------------------------
# T6 — unsafe prefixes are refused, and delete nothing
# ---------------------------------------------------------------------------
head2 "T6 unsafe prefixes are refused"
for badpfx in "" "." ".." "ab" "a/b" "sk*" "sk?" "sk[a]"; do
  P="$WORK/t6-$(printf '%s' "$badpfx" | tr -c 'a-zA-Z0-9' '_')"
  seed_dirs "$P" 20260101-000000 20260102-000000 20260103-000000 20260104-000000 20260105-000000
  BEFORE=$(count_matching "$P" 'skills-backup-*')
  oc_backup_prune "$P" "$badpfx" "" > "$WORK/t6.log" 2>&1
  RC=$?
  AFTER=$(count_matching "$P" 'skills-backup-*')
  if [ "$RC" != "0" ] && [ "$BEFORE" = "$AFTER" ]; then
    ok "prefix '$badpfx' refused (rc=$RC) and deleted nothing ($BEFORE -> $AFTER)"
  else
    bad "prefix '$badpfx' refused and deleted nothing" "rc=$RC before=$BEFORE after=$AFTER"
  fi
done

# ---------------------------------------------------------------------------
# T7 — the disk pre-check fails loudly when space is short
# ---------------------------------------------------------------------------
head2 "T7 disk pre-check fails loudly when space is short"
P="$WORK/t7"; mkdir -p "$P"
# Ask for more KB than any filesystem here has free. Real function, real df.
HUGE=999999999999
if oc_backup_precheck_disk "$P/skills-backup-20260105-000000" "$HUGE" "oversized fixture backup" > "$WORK/t7.log" 2>&1; then
  bad "pre-check refuses an impossible request" "it returned 0 — a backup that cannot fit was allowed to start"
else
  ok "pre-check refuses an impossible request (nonzero)"
fi
if grep -q 'BACKUP ABORTED' "$WORK/t7.log"; then ok "failure is LOUD (banner printed)"; else bad "failure is LOUD (banner printed)" "$(cat "$WORK/t7.log")"; fi
if grep -q "$P/skills-backup-20260105-000000" "$WORK/t7.log"; then ok "failure names the target path"; else bad "failure names the target path" "$(cat "$WORK/t7.log")"; fi
if grep -q 'short by' "$WORK/t7.log"; then ok "failure states the shortfall"; else bad "failure states the shortfall" "$(cat "$WORK/t7.log")"; fi
# and a sane request must pass
if oc_backup_precheck_disk "$P/skills-backup-20260106-000000" 1 "tiny fixture backup" > "$WORK/t7b.log" 2>&1; then
  ok "pre-check allows a request that obviously fits"
else
  bad "pre-check allows a request that obviously fits" "$(cat "$WORK/t7b.log")"
fi

# ---------------------------------------------------------------------------
# T8 — a failed backup prunes NOTHING
# ---------------------------------------------------------------------------
head2 "T8 a failed backup prunes nothing"
P="$WORK/t8"
seed_dirs "$P" 20260101-000000 20260102-000000 20260103-000000 20260104-000000 20260105-000000
BEFORE=$(count_matching "$P" 'skills-backup-*')
# Behavioural: mirror the site's ordering — pre-check first, prune only after a
# backup lands. With an impossible pre-check the site must bail before pruning.
NEWDIR="$P/skills-backup-20260106-000000"
if oc_backup_precheck_disk "$NEWDIR" "$HUGE" "fixture" >/dev/null 2>&1; then
  mkdir -p "$NEWDIR"
  [ -d "$NEWDIR" ] && oc_backup_prune "$P" "skills-backup-" "$NEWDIR" >/dev/null 2>&1
fi
AFTER=$(count_matching "$P" 'skills-backup-*')
if [ "$BEFORE" = "$AFTER" ]; then
  ok "pre-check refusal left every existing backup in place ($BEFORE -> $AFTER)"
else
  bad "pre-check refusal left every existing backup in place" "before=$BEFORE after=$AFTER"
fi

# Source-order teeth: the REAL updater must have this ordering, not just the
# simulator above. Assert against update-skills.sh itself.
if awk '
  /RETENTION \(OPENCLAW-BACKUP-RETENTION-V1\)/ { region=1 }
  region && /oc_backup_precheck_disk/          { pre=NR }
  region && /mkdir -p "\$BACKUP_DIR"/          { mk=NR }
  region && /oc_backup_prune "\$_SKILLS_BACKUP_ROOT"/ { pr=NR }
  END { exit !(pre && mk && pr && pre < mk && mk < pr) }
' "$UPDATE_SKILLS"; then
  ok "update-skills.sh really orders pre-check -> mkdir -> prune"
else
  bad "update-skills.sh really orders pre-check -> mkdir -> prune" "ordering not found in $UPDATE_SKILLS"
fi
if grep -q 'if \[ -d "\$BACKUP_DIR" \]; then' "$UPDATE_SKILLS" ; then
  ok "update-skills.sh prunes only inside a 'backup dir exists' guard"
else
  bad "update-skills.sh prunes only inside a 'backup dir exists' guard" "guard not found"
fi

# ---------------------------------------------------------------------------
# T9 — OPENCLAW_BACKUP_KEEP override
# ---------------------------------------------------------------------------
head2 "T9 OPENCLAW_BACKUP_KEEP override"
P="$WORK/t9"
seed_dirs "$P" 20260101-000000 20260102-000000 20260103-000000 20260104-000000 20260105-000000
OPENCLAW_BACKUP_KEEP=1 oc_backup_prune "$P" "skills-backup-" "$P/skills-backup-20260105-000000" >/dev/null 2>&1
AFTER=$(count_matching "$P" 'skills-backup-*')
if [ "$AFTER" = "1" ]; then ok "KEEP=1 keeps exactly 1"; else bad "KEEP=1 keeps exactly 1" "after=$AFTER"; fi

for junk in "" "abc" "-2" "0" "3.5"; do
  GOT="$(OPENCLAW_BACKUP_KEEP="$junk" oc_backup_keep)"
  EXPECT=3
  [ "$junk" = "0" ] && EXPECT=1   # 0 is numeric; clamped to the 1 floor, never 0
  if [ "$GOT" = "$EXPECT" ]; then
    ok "OPENCLAW_BACKUP_KEEP='$junk' -> $GOT (safe)"
  else
    bad "OPENCLAW_BACKUP_KEEP='$junk' -> safe value" "got $GOT, expected $EXPECT"
  fi
done

# ---------------------------------------------------------------------------
# T10 — every known update-path backup site is wired
# ---------------------------------------------------------------------------
head2 "T10 every known update-path backup site is wired"
site_wired() { # file, human label, required needle
  if grep -q "$3" "$1" 2>/dev/null; then ok "$2"; else bad "$2" "missing '$3' in $1"; fi
}
site_wired "$UPDATE_SKILLS" "update-skills.sh: skills-backup-<ts> dirs pruned"     'oc_backup_prune "\$_SKILLS_BACKUP_ROOT" "skills-backup-"'
site_wired "$UPDATE_SKILLS" "update-skills.sh: skills backup disk pre-checked"     'oc_backup_precheck_disk "\$BACKUP_DIR"'
site_wired "$UPDATE_SKILLS" "update-skills.sh: cron-heal .bak.<ts> pruned"         'oc_backup_prune "\$(dirname "\$cron_script")"'
site_wired "$INSTALL_SH"    "install.sh: backup_config_file pruned"                'oc_backup_prune "\$OC_BACKUPS"'
site_wired "$INSTALL_SH"    "install.sh: backup_config_file disk pre-checked"      'oc_backup_precheck_disk "\$backup"'
site_wired "$PODBEAN_ROLL"  "fleet-roll: host env .bak.s58u18-<ts> pruned"         'hostenv_backup_pruned'

printf '\n== SUMMARY\n  PASS %d\n  FAIL %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
