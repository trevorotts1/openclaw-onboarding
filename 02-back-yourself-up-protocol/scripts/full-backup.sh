#!/usr/bin/env bash
# full-backup.sh — the executable form of the Full Backup Step-by-Step Procedure
# in back-yourself-up-protocol-full.md.
#
# WHY THIS FILE EXISTS. The procedure was prose an agent transcribed by hand, so
# the two defects it carried (T2-08 and T0-24) could not be tested and could not
# fail:
#
#   T2-08  Rotation ran FIRST. The oldest backup was deleted before the
#          replacement had even been created, so any failure in the copy, disk or
#          verification steps that followed left ONE verified restore point
#          instead of the promised two — during exactly the failure window
#          backups exist to cover.
#
#   T0-24  Every copy sent stderr to /dev/null and captured no exit status, and a
#          missing critical file printed a warning and continued. Failed copies
#          from absent sources, permissions or a full disk were invisible and the
#          run still reported a completed backup.
#
# Here, rotation is the LAST step and is only reachable after verification
# passed; every copy's status is captured; and any recorded failure, or any
# missing critical file, exits non-zero WITHOUT deleting anything.
#
# The document remains the human narrative. This script is what
# tests/unit/full-backup-prune-after-verify.test.sh actually runs, in both
# directions, so the ordering and the fail-closed behaviour are enforced rather
# than described.
#
# Honours $HOME throughout, so it can be exercised against a fixture HOME with no
# access to a real box.
#
# Exit codes:
#   0 — backup created, verified, and rotation applied
#   1 — backup incomplete or unverifiable; NOTHING was deleted

set -u

# ── Step 1: Determine the Backup Directory ──────────────────────────────────
BACKUP_ROOT=""
FOUND=$(find "$HOME/Downloads" -maxdepth 1 -type d -iname "*openclaw*backup*" 2>/dev/null | head -1)

if [ -n "$FOUND" ]; then
    BACKUP_ROOT="$FOUND"
elif [ -d "$HOME/Downloads/backups" ]; then
    BACKUP_ROOT="$HOME/Downloads/backups"
elif [ -d "$HOME/Downloads/backup" ]; then
    BACKUP_ROOT="$HOME/Downloads/backup"
else
    mkdir -p "$HOME/Downloads/openclaw-backups"
    BACKUP_ROOT="$HOME/Downloads/openclaw-backups"
fi

mkdir -p "$BACKUP_ROOT/full-backup"

# ── Step 2: Create the New Backup Directory ─────────────────────────────────
# ROTATION DOES NOT HAPPEN HERE. See Step 16.
FULL_BACKUP_DIR="$BACKUP_ROOT/full-backup"
TODAY=$(date +%Y-%m-%d)
NEW_BACKUP="$FULL_BACKUP_DIR/full-backup-$TODAY"
mkdir -p "$NEW_BACKUP"/{workspace,config,secrets,memory,scripts,skills,projects,data,assets}

BACKUP_ERRORS=0
FAILED_ITEMS=""

record_failure() {
    echo "ERROR: $1"
    FAILED_ITEMS="$FAILED_ITEMS
  - $1"
    BACKUP_ERRORS=$((BACKUP_ERRORS + 1))
}

# The source MUST exist and the copy MUST succeed.
copy_required() {
    label="$1"; src="$2"; dest="$3"
    if [ ! -e "$src" ]; then
        record_failure "$label: REQUIRED source is missing ($src)"
        return 1
    fi
    if ! cp -R "$src" "$dest"; then
        record_failure "$label: copy FAILED ($src -> $dest)"
        return 1
    fi
    echo "  ok   $label"
}

# An ABSENT source is fine. A source that EXISTS and fails to copy is a failure —
# precisely the case the old `2>/dev/null` discarded.
copy_if_present() {
    label="$1"; src="$2"; dest="$3"
    if [ ! -e "$src" ]; then
        echo "  --   $label: not present on this box (skipped)"
        return 0
    fi
    if ! cp -R "$src" "$dest"; then
        record_failure "$label: source EXISTS but the copy FAILED ($src -> $dest)"
        return 1
    fi
    echo "  ok   $label"
}

# ── Step 3: Copy Workspace Markdown Files ───────────────────────────────────
WORKSPACE_MD_COUNT=0
for f in "$HOME"/clawd/*.md; do
    [ -e "$f" ] || continue
    if cp "$f" "$NEW_BACKUP/workspace/"; then
        WORKSPACE_MD_COUNT=$((WORKSPACE_MD_COUNT + 1))
    else
        record_failure "workspace file: copy FAILED ($f)"
    fi
done
if [ "$WORKSPACE_MD_COUNT" -eq 0 ]; then
    record_failure "workspace .md files: none were copied from ~/clawd"
else
    echo "  ok   workspace .md files ($WORKSPACE_MD_COUNT file(s))"
fi

# ── Step 4: Copy Configuration Files ────────────────────────────────────────
copy_required   "openclaw.json"        "$HOME/.openclaw/openclaw.json"   "$NEW_BACKUP/config/"

for pattern in "$HOME"/.openclaw/*.json "$HOME"/.openclaw/*.yaml "$HOME"/.openclaw/*.yml "$HOME"/.openclaw/*.toml; do
    [ -e "$pattern" ] || continue
    [ "$pattern" = "$HOME/.openclaw/openclaw.json" ] && continue
    cp "$pattern" "$NEW_BACKUP/config/" || record_failure "config file: copy FAILED ($pattern)"
done

copy_if_present "legacy clawdbot.json" "$HOME/.clawdbot/clawdbot.json"   "$NEW_BACKUP/config/"

# ── Step 5: Copy Secrets and Credentials ────────────────────────────────────
copy_if_present "secrets directory"    "$HOME/clawd/secrets"             "$NEW_BACKUP/secrets/"

# ── Step 6: Copy Memory Files ───────────────────────────────────────────────
copy_if_present "memory directory"     "$HOME/clawd/memory"              "$NEW_BACKUP/memory/"
copy_if_present "master files"         "$HOME/Downloads/openclaw-master-files" "$NEW_BACKUP/memory/"

# ── Step 7: Copy Scripts and Tools ──────────────────────────────────────────
copy_if_present "bin"                  "$HOME/clawd/bin"                 "$NEW_BACKUP/scripts/"
copy_if_present "scripts"              "$HOME/clawd/scripts"             "$NEW_BACKUP/scripts/"
copy_if_present "tools"                "$HOME/clawd/tools"               "$NEW_BACKUP/scripts/"

# ── Step 8: Copy Skills ─────────────────────────────────────────────────────
copy_if_present "installed skills"     "$HOME/.openclaw/skills"          "$NEW_BACKUP/skills/"

# ── Step 9: Export Cron Jobs ────────────────────────────────────────────────
if command -v openclaw >/dev/null 2>&1 && openclaw cron list > "$NEW_BACKUP/cron-jobs-export.txt" 2>&1; then
    echo "  ok   cron export"
else
    echo "NOTE: openclaw cron list unavailable or failed; cron jobs may need documenting manually." \
        > "$NEW_BACKUP/cron-jobs-export.txt"
    echo "  --   cron export unavailable (recorded in cron-jobs-export.txt)"
fi

# ── Step 10: Copy Project Files (Excluding Bloat) ───────────────────────────
if [ -d "$HOME/clawd/projects" ]; then
    if rsync -a \
        --exclude='node_modules/' --exclude='.git/' --exclude='__pycache__/' \
        --exclude='.cache/' --exclude='cache/' --exclude='tmp/' --exclude='temp/' \
        --exclude='.DS_Store' \
        --exclude='*.mp4' --exclude='*.mov' --exclude='*.avi' --exclude='*.mkv' \
        --exclude='*.webm' --exclude='*.mp3' --exclude='*.wav' --exclude='*.aac' \
        --exclude='*.flac' --exclude='*.log' \
        "$HOME/clawd/projects/" "$NEW_BACKUP/projects/"; then
        echo "  ok   projects"
    else
        record_failure "projects: rsync FAILED"
    fi
else
    echo "  --   projects: not present on this box (skipped)"
fi

# ── Step 11: Copy Data Files ────────────────────────────────────────────────
copy_if_present "data directory"       "$HOME/clawd/data"                "$NEW_BACKUP/data/"

# ── Step 12: Copy Small Brand Assets ────────────────────────────────────────
if [ -d "$HOME/clawd/assets" ]; then
    if rsync -a --max-size=5M "$HOME/clawd/assets/" "$NEW_BACKUP/assets/"; then
        echo "  ok   assets (files under 5 MB)"
    else
        record_failure "assets: rsync FAILED"
    fi
else
    echo "  --   assets: not present on this box (skipped)"
fi

# ── Step 13: Generate the Manifest ──────────────────────────────────────────
if find "$NEW_BACKUP" -type f | sort > "$NEW_BACKUP/MANIFEST.txt"; then
    echo "  ok   MANIFEST.txt"
else
    record_failure "MANIFEST.txt: could not be generated"
fi

# ── Step 14: Generate Backup Info ───────────────────────────────────────────
cat > "$NEW_BACKUP/BACKUP-INFO.txt" << EOF
Full Instance Backup
Date: $(date '+%A, %B %d, %Y')
Time: $(date '+%I:%M %p %Z')
Hostname: $(hostname)
User: $(whoami)
Backup Type: Full Instance (Automated Biweekly)
Protocol: Back Yourself Up Protocol v1.0

Files backed up: $(find "$NEW_BACKUP" -type f | wc -l | tr -d ' ')
Total size: $(du -sh "$NEW_BACKUP" | cut -f1)

Notes:
- This backup contains sensitive credentials. Store securely.
- Do not upload to cloud storage without encryption.
- To restore, follow the restoration procedure in BACK-YOURSELF-UP-PROTOCOL.md
EOF

# ── Step 15: Verify the Backup ──────────────────────────────────────────────
# A MISSING CRITICAL FILE IS A FAILED BACKUP, NOT A WARNING.
MISSING=""

[ ! -f "$NEW_BACKUP/config/openclaw.json" ] && MISSING="$MISSING openclaw.json"
[ ! -f "$NEW_BACKUP/workspace/AGENTS.md" ] && MISSING="$MISSING AGENTS.md"
[ ! -f "$NEW_BACKUP/workspace/TOOLS.md" ] && MISSING="$MISSING TOOLS.md"

if [ -n "$MISSING" ]; then
    record_failure "critical file(s) missing from the backup:$MISSING"
fi

if [ "$BACKUP_ERRORS" -gt 0 ]; then
    echo ""
    echo "BACKUP FAILED - $BACKUP_ERRORS problem(s):$FAILED_ITEMS"
    echo "The incomplete backup is left at $NEW_BACKUP for inspection."
    echo "NO existing backup was deleted - every previous restore point is intact."
    exit 1
fi

echo "Backup verification passed. All critical files present."
echo "Total backup size: $(du -sh "$NEW_BACKUP" | cut -f1)"

# ── Step 16: Rotate Old Backups (ONLY after Step 15 passed) ─────────────────
# Reaching this line means the new backup exists and has been verified, so
# pruning can never drop below the promised number of good restore points.
KEEP=2
ALL_BACKUPS=$(ls -d "$FULL_BACKUP_DIR"/full-backup-* 2>/dev/null | sort)
TOTAL=$(printf '%s\n' "$ALL_BACKUPS" | sed '/^$/d' | wc -l | tr -d ' ')

if [ "$TOTAL" -gt "$KEEP" ]; then
    REMOVE=$((TOTAL - KEEP))
    printf '%s\n' "$ALL_BACKUPS" | sed '/^$/d' | head -"$REMOVE" | while read -r OLD; do
        if [ "$OLD" = "$NEW_BACKUP" ]; then
            echo "Refusing to delete the backup just created: $OLD"
            continue
        fi
        echo "Deleting superseded backup: $OLD"
        rm -rf "$OLD"
    done
else
    echo "No rotation needed ($TOTAL backup(s), keeping $KEEP)."
fi

exit 0
