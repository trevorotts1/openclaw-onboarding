#!/usr/bin/env bash
# tests/unit/full-backup-prune-after-verify.test.sh
#
# REGRESSION GUARD — the full backup prunes only after the replacement verifies,
# and a failed copy is never reported as a completed backup (T2-08, T0-24).
#
# THE TWO DEFECTS THIS CLOSES, both in the Full Backup Step-by-Step Procedure:
#
#   T2-08  Rotation ran FIRST ("Step 2: Rotate Old Backups ... Before creating a
#          new backup"), deleting the oldest backup at a point where the
#          replacement did not exist and had certainly not been verified. Any
#          failure in the copy, disk or verification steps that followed left ONE
#          verified restore point instead of the promised two — during exactly
#          the failure window backups exist to cover.
#
#   T0-24  Every copy redirected stderr to /dev/null and captured no exit status,
#          and the verification step printed "WARNING: ... missing" and continued.
#          A run whose copies failed still reported a completed backup.
#
# WHAT THIS FILE PROVES (hermetic; fixture HOMEs in a tempdir, no real box):
#   T1  DOCUMENT ORDERING — the rotate step appears AFTER the verify step in
#       back-yourself-up-protocol-full.md, and the old "Before creating a new
#       backup" rotation preamble is gone
#   T2  HAPPY PATH — a complete fixture backs up, exits 0, and the new backup
#       contains the critical files
#   T3  ...and rotation still happens: with more than KEEP backups present, the
#       oldest is pruned (the reorder did not disable pruning)
#   T4  ...and the backup just created is never the one deleted
#   T5  FAILURE PATH — a missing critical source exits NON-ZERO
#   T6  ...and NO pre-existing backup was deleted (the destructive step was
#       never reached)
#   T7  ...and the failure names the specific missing item, rather than
#       reporting a completed backup
#   T8  A PRESENT source that cannot be copied (permission denied) is a FAILURE,
#       not a silent skip — the exact case `2>/dev/null` used to discard
#
# Exit 0 = pass. Exit 1 = a defect regressed, or the backup stopped working.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/02-back-yourself-up-protocol"
SCRIPT="$SKILL_DIR/scripts/full-backup.sh"
DOC="$SKILL_DIR/back-yourself-up-protocol-full.md"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== full-backup-prune-after-verify.test.sh (T2-08, T0-24) ==="
echo ""

for f in "$SCRIPT" "$DOC"; do
  if [ ! -f "$f" ]; then echo "  FAIL: $f not found"; exit 1; fi
done

TMP="$(mktemp -d)"
trap 'chmod -R u+rwX "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT

# ── T1: document ordering ───────────────────────────────────────────────────
# SCOPED to the FULL BACKUP procedure. Part 1 (config edits) has its own
# unrelated "Step 4: Verify the Backup"; an unscoped grep matches that one and
# would pass no matter where full-backup rotation sits.
# The heading appears twice (contents/decision-tree area, then the procedure
# itself); the LAST occurrence is the procedure.
SECTION_LINE="$(grep -n '^Full Backup Step-by-Step Procedure' "$DOC" | tail -1 | cut -d: -f1)"
if [ -z "$SECTION_LINE" ]; then
  fail "T1a document: 'Full Backup Step-by-Step Procedure' heading not found"
  VERIFY_LINE=""; ROTATE_LINE=""
else
  VERIFY_LINE="$(awk -v s="$SECTION_LINE" 'NR>s && /^Step [0-9]+: Verify the Backup/ {print NR; exit}' "$DOC")"
  ROTATE_LINE="$(awk -v s="$SECTION_LINE" 'NR>s && /^Step [0-9]+: Rotate Old Backups/ {print NR; exit}' "$DOC")"
fi
if [ -n "$VERIFY_LINE" ] && [ -n "$ROTATE_LINE" ] && [ "$ROTATE_LINE" -gt "$VERIFY_LINE" ]; then
  pass "T1a document: within the full-backup procedure (from line $SECTION_LINE), rotate (line $ROTATE_LINE) comes AFTER verify (line $VERIFY_LINE)"
else
  fail "T1a document: full-backup verify=${VERIFY_LINE:-none} rotate=${ROTATE_LINE:-none} — rotation does not follow verification"
fi
if grep -q 'Before creating a new backup, check if rotation is needed' "$DOC"; then
  fail "T1b document: the prune-first preamble is still present"
else
  pass "T1b document: the prune-first preamble is gone"
fi

# ── fixture builder ─────────────────────────────────────────────────────────
# complete=1 builds a fixture that must succeed; complete=0 omits a critical file.
build_home() {
  local home="$1" complete="$2"
  mkdir -p "$home/clawd" "$home/.openclaw" "$home/Downloads/openclaw-backups/full-backup"
  printf 'agents\n' > "$home/clawd/AGENTS.md"
  printf 'tools\n'  > "$home/clawd/TOOLS.md"
  if [ "$complete" = "1" ]; then
    printf '{"fixture":true}\n' > "$home/.openclaw/openclaw.json"
  fi
  # Two pre-existing backups, older than today, so rotation has candidates.
  mkdir -p "$home/Downloads/openclaw-backups/full-backup/full-backup-2020-01-01"
  mkdir -p "$home/Downloads/openclaw-backups/full-backup/full-backup-2020-01-02"
  printf 'old1\n' > "$home/Downloads/openclaw-backups/full-backup/full-backup-2020-01-01/marker.txt"
  printf 'old2\n' > "$home/Downloads/openclaw-backups/full-backup/full-backup-2020-01-02/marker.txt"
}

run_backup() {  # <home> -> prints "<rc>|<output>"
  local home="$1" out rc=0
  out="$(env HOME="$home" PATH="/usr/bin:/bin:/usr/local/bin" /bin/bash "$SCRIPT" 2>&1)" || rc=$?
  printf '%s|%s' "$rc" "$out"
}

TODAY="$(date +%Y-%m-%d)"

# ── T2/T3/T4: happy path ────────────────────────────────────────────────────
HOME_OK="$TMP/home-ok"
build_home "$HOME_OK" 1
R="$(run_backup "$HOME_OK")"; RC="${R%%|*}"; OUT="${R#*|}"
NEW="$HOME_OK/Downloads/openclaw-backups/full-backup/full-backup-$TODAY"

if [ "$RC" = "0" ]; then
  pass "T2a complete fixture -> exit 0"
else
  fail "T2a complete fixture -> exit $RC: $OUT"
fi
if [ -f "$NEW/config/openclaw.json" ] && [ -f "$NEW/workspace/AGENTS.md" ] && [ -f "$NEW/workspace/TOOLS.md" ]; then
  pass "T2b the new backup contains every critical file"
else
  fail "T2b the new backup is missing critical files"
fi
if [ ! -d "$HOME_OK/Downloads/openclaw-backups/full-backup/full-backup-2020-01-01" ]; then
  pass "T3 rotation still prunes the oldest backup after verification"
else
  fail "T3 the oldest backup was NOT pruned — the reorder disabled rotation"
fi
if [ -d "$NEW" ]; then
  pass "T4 the backup just created was never the one deleted"
else
  fail "T4 the backup just created was deleted by its own rotation"
fi

# ── T5/T6/T7: failure path — a required source is missing ───────────────────
HOME_BAD="$TMP/home-bad"
build_home "$HOME_BAD" 0          # no ~/.openclaw/openclaw.json
R="$(run_backup "$HOME_BAD")"; RC="${R%%|*}"; OUT="${R#*|}"

if [ "$RC" != "0" ]; then
  pass "T5 missing critical source -> NON-ZERO exit (not a reported success)"
else
  fail "T5 missing critical source -> exit 0; the run reported a completed backup"
fi
KEPT=0
[ -d "$HOME_BAD/Downloads/openclaw-backups/full-backup/full-backup-2020-01-01" ] && KEPT=$((KEPT+1))
[ -d "$HOME_BAD/Downloads/openclaw-backups/full-backup/full-backup-2020-01-02" ] && KEPT=$((KEPT+1))
if [ "$KEPT" = "2" ]; then
  pass "T6 on failure NO pre-existing backup was deleted (both restore points intact)"
else
  fail "T6 on failure only $KEPT/2 pre-existing backups survived — the destructive step ran"
fi
if printf '%s\n' "$OUT" | grep -q 'openclaw.json'; then
  pass "T7 the failure names the specific missing item"
else
  fail "T7 the failure did not name the missing item: $OUT"
fi

# ── T8: a PRESENT source that cannot be copied is a failure ─────────────────
# This is the case the old `2>/dev/null` silently discarded: the source exists,
# so it is not an "absent, therefore fine" skip, but the copy cannot succeed.
HOME_PERM="$TMP/home-perm"
build_home "$HOME_PERM" 1
mkdir -p "$HOME_PERM/clawd/secrets"
printf 'secret-fixture\n' > "$HOME_PERM/clawd/secrets/.env"
# 0600 even for a synthetic fixture: the repo's chmod-600 coverage gate requires
# every .sh that writes secrets/.env to also restrict it, and a test fixture is
# not an excuse to model the insecure shape. The value is a placeholder string,
# never a real credential.
chmod 600 "$HOME_PERM/clawd/secrets/.env"
chmod 000 "$HOME_PERM/clawd/secrets"
R="$(run_backup "$HOME_PERM")"; RC="${R%%|*}"; OUT="${R#*|}"
chmod -R u+rwX "$HOME_PERM/clawd/secrets" 2>/dev/null

if [ "$(id -u)" = "0" ]; then
  echo "  SKIP: T8 — running as root, permission denial cannot be simulated"
elif [ "$RC" != "0" ] && printf '%s\n' "$OUT" | grep -qi 'secrets'; then
  pass "T8 a present-but-uncopyable source is a recorded FAILURE, not a silent skip"
else
  fail "T8 unreadable secrets dir -> exit $RC; expected non-zero naming secrets. Output: $OUT"
fi

# ── T9/T10: FAIL-FIRST CONTROL ──────────────────────────────────────────────
# A guard that cannot fail is worthless. This reproduces the PRE-FIX procedure
# verbatim in shape — rotate first, copies with `2>/dev/null` and no status
# captured, verification that warns and continues — and asserts this suite's two
# load-bearing legs (T5 non-zero exit, T6 nothing deleted) BOTH fail against it.
# If these two controls ever "pass", the legs above have stopped discriminating.
PREFIX_SCRIPT="$TMP/prefix-full-backup.sh"
cat > "$PREFIX_SCRIPT" <<'PREFIXEOF'
#!/usr/bin/env bash
set -u
BACKUP_ROOT="$HOME/Downloads/openclaw-backups"
mkdir -p "$BACKUP_ROOT/full-backup"
FULL_BACKUP_DIR="$BACKUP_ROOT/full-backup"
# Step 2 (PRE-FIX): rotate FIRST, before the replacement exists.
BACKUP_COUNT=$(ls -d "$FULL_BACKUP_DIR"/full-backup-* 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -ge 2 ]; then
    OLDEST=$(ls -d "$FULL_BACKUP_DIR"/full-backup-* 2>/dev/null | head -1)
    echo "Deleting oldest backup: $OLDEST"
    rm -rf "$OLDEST"
fi
TODAY=$(date +%Y-%m-%d)
NEW_BACKUP="$FULL_BACKUP_DIR/full-backup-$TODAY"
mkdir -p "$NEW_BACKUP"/{workspace,config}
# Copies with no status captured.
cp "$HOME"/clawd/*.md "$NEW_BACKUP/workspace/" 2>/dev/null
cp "$HOME/.openclaw/openclaw.json" "$NEW_BACKUP/config/" 2>/dev/null
# Verification that warns and continues.
MISSING=""
[ ! -f "$NEW_BACKUP/config/openclaw.json" ] && MISSING="$MISSING openclaw.json"
if [ -n "$MISSING" ]; then
    echo "WARNING: The following expected files are missing from the backup:$MISSING"
else
    echo "Backup verification passed. All critical files present."
fi
PREFIXEOF
chmod +x "$PREFIX_SCRIPT"

HOME_CTL="$TMP/home-control"
build_home "$HOME_CTL" 0          # same missing-critical-file fixture as T5/T6
CTL_RC=0
CTL_OUT="$(env HOME="$HOME_CTL" PATH="/usr/bin:/bin:/usr/local/bin" /bin/bash "$PREFIX_SCRIPT" 2>&1)" || CTL_RC=$?

if [ "$CTL_RC" = "0" ]; then
  pass "T9 CONTROL: the pre-fix procedure exits 0 despite the missing critical file (defect reproduced; T5 discriminates)"
else
  fail "T9 CONTROL: the pre-fix procedure exited $CTL_RC — the control no longer reproduces the defect, so T5 proves nothing"
fi
CTL_KEPT=0
[ -d "$HOME_CTL/Downloads/openclaw-backups/full-backup/full-backup-2020-01-01" ] && CTL_KEPT=$((CTL_KEPT+1))
[ -d "$HOME_CTL/Downloads/openclaw-backups/full-backup/full-backup-2020-01-02" ] && CTL_KEPT=$((CTL_KEPT+1))
if [ "$CTL_KEPT" -lt 2 ]; then
  pass "T10 CONTROL: the pre-fix procedure deleted a restore point on a run that failed (defect reproduced; T6 discriminates)"
else
  fail "T10 CONTROL: the pre-fix procedure deleted nothing — the control no longer reproduces the defect, so T6 proves nothing"
fi

echo ""
echo "  Result: $PASS passed | $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "full-backup-prune-after-verify.test.sh: FAILED"
  exit 1
fi
echo "full-backup-prune-after-verify.test.sh: PASSED"
exit 0
