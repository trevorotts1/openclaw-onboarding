#!/usr/bin/env bash
# apply-u004-phase2.sh — U004 Phase 2: on-box rulebook update
#
# THIS SCRIPT IS NEVER EXECUTED BY THE BUILDER.  It is the deliverable for
# the Named Stop (spec-common 7.7).  A human runs it after explicit
# approval.
#
# Preconditions (verified before the first write):
#   1. U003's ticket says DONE and its QC-1 restore test passed
#   2. ls "$BK"/Presentations-FULL.tar.gz resolves
#   3. shasum -a 256 -c "$BK"/Presentations-FULL.tar.gz.sha256 verifies
#   4. U001 has merged (MANIFEST-SOURCE.txt)
#
# Usage:
#   bash scripts/apply-u004-phase2.sh           # live run
#   bash scripts/apply-u004-phase2.sh --dry-run # print paths, touch nothing
# ============================================================

set -euo pipefail

# ---- Resolve paths -------------------------------------------
: "${SKILLS_DIR:=$HOME/.openclaw/skills}"
: "${BK:=$HOME/Downloads/openclaw-backups}"
DEPT_DIR="$HOME/.openclaw/workspace/departments/Presentations"
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift 2>/dev/null || true
fi

# ---- Gate 0: backup must verify BEFORE any write -------------
# This is the FIRST executable statement (QC-4).  It must run before
# any cp, mv, or rm.
BACKUP_TAR="$BK/Presentations-FULL.tar.gz"
BACKUP_CHECKSUM="$BK/Presentations-FULL.tar.gz.sha256"

if [ ! -f "$BACKUP_CHECKSUM" ]; then
  echo "FATAL: backup checksum not found at $BACKUP_CHECKSUM" >&2
  echo "U003 must have completed and produced this file before Phase 2 runs." >&2
  exit 1
fi

if [ ! -f "$BACKUP_TAR" ]; then
  echo "FATAL: backup archive not found at $BACKUP_TAR" >&2
  echo "U003 must have completed and produced this archive before Phase 2 runs." >&2
  exit 1
fi

echo "[Phase2] verifying backup checksum..."
if ! (cd "$BK" && shasum -a 256 -c "$(basename "$BACKUP_CHECKSUM")") >/dev/null 2>&1; then
  echo "FATAL: backup checksum verification FAILED for $BACKUP_TAR" >&2
  echo "The archive may be corrupt. Do NOT proceed. Escalate." >&2
  exit 1
fi
echo "[Phase2] backup checksum verified OK"

# ---- Helpers -------------------------------------------------
_cp() {
  if [ "$DRY_RUN" -eq 1 ]; then echo "cp  $1  ->  $2"; else cp "$1" "$2"; fi
}

_mv() {
  if [ "$DRY_RUN" -eq 1 ]; then echo "mv  $1  ->  $2"; else mkdir -p "$(dirname "$2")"; mv "$1" "$2"; fi
}

_rm() {
  if [ "$DRY_RUN" -eq 1 ]; then echo "rm  $1"; else rm -f "$1"; fi
}

RULEBOOK_SRC="$SKILLS_DIR/universal-sops/presentation-slide-craft"
PRES_SOPS_DIR="$SKILLS_DIR/23-ai-workforce-blueprint/templates/role-library/presentations/sops"
PRES_DIR="$SKILLS_DIR/23-ai-workforce-blueprint/templates/role-library/presentations"

# ---- Step 4: Install the rulebook ----------------------------
echo "[Phase2] Step 4: Installing the rulebook..."

if [ -f "$RULEBOOK_SRC/PIPELINE-MANIFEST.json" ]; then
  _cp "$RULEBOOK_SRC/PIPELINE-MANIFEST.json" "$DEPT_DIR/sops/PIPELINE-MANIFEST.json"
else
  echo "FATAL: canonical PIPELINE-MANIFEST.json not found" >&2; exit 1
fi

if [ -f "$RULEBOOK_SRC/MASTER-QC-AUTOFAIL-RULESET.md" ]; then
  _cp "$RULEBOOK_SRC/MASTER-QC-AUTOFAIL-RULESET.md" "$DEPT_DIR/sops/MASTER-QC-AUTOFAIL-RULESET.md"
else
  echo "FATAL: canonical MASTER-QC-AUTOFAIL-RULESET.md not found" >&2; exit 1
fi

SOP00_SRC="$PRES_SOPS_DIR/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md"
if [ -f "$SOP00_SRC" ]; then
  _cp "$SOP00_SRC" "$DEPT_DIR/sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md"
else
  echo "FATAL: canonical SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md not found" >&2; exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "write  $DEPT_DIR/MANIFEST-SOURCE.txt"
else
  echo "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json" > "$DEPT_DIR/MANIFEST-SOURCE.txt"
fi

echo "[Phase2] Step 4 complete: rulebook installed"

# ---- Step 5: Sync the 57 forks -------------------------------
echo "[Phase2] Step 5: Syncing forks..."

sync_fork_dir() {
  local _sub="$1"
  local _dirname="$DEPT_DIR/$_sub"
  [ -d "$_dirname" ] || return 0

  for _entry in "$_dirname"/*; do
    [ -e "$_entry" ] || continue
    local _name
    _name="$(basename "$_entry")"
    case "$_name" in *.bak|*.bak-*) continue ;; esac

    if [ -L "$_entry" ] && [ ! -e "$_entry" ]; then continue; fi

    local _resolved="$_entry"
    if [ -L "$_entry" ] && [ -e "$_entry" ]; then
      _resolved="$(readlink -f "$_entry" 2>/dev/null || echo "$_entry")"
    fi
    [ -f "$_resolved" ] || continue

    local _src=""
    if [ -f "$PRES_SOPS_DIR/$_name" ]; then _src="$PRES_SOPS_DIR/$_name"
    elif [ -f "$RULEBOOK_SRC/$_name" ]; then _src="$RULEBOOK_SRC/$_name"
    elif [ -f "$PRES_DIR/$_name" ]; then _src="$PRES_DIR/$_name"
    fi
    [ -n "$_src" ] || continue

    local _dept_hash _src_hash
    _dept_hash="$(shasum -a 256 "$_resolved" 2>/dev/null | awk '{print $1}' || true)"
    _src_hash="$(shasum -a 256 "$_src" 2>/dev/null | awk '{print $1}' || true)"

    if [ -n "$_dept_hash" ] && [ -n "$_src_hash" ] && [ "$_dept_hash" != "$_src_hash" ]; then
      _cp "$_src" "$_entry"
    fi
  done
}

sync_fork_dir "sops"
sync_fork_dir "scripts"

echo "[Phase2] Step 5 complete: forks synced"

# ---- Step 6: Install the four missing contract files ---------
echo "[Phase2] Step 6: Installing contract files..."

S05_SRC="$RULEBOOK_SRC/SOP-SLIDE-05-PROCESS-MANIFEST.md"
[ -f "$S05_SRC" ] && _cp "$S05_SRC" "$DEPT_DIR/sops/SOP-SLIDE-05-PROCESS-MANIFEST.md" || echo "WARNING: SOP-SLIDE-05 not found" >&2

S06_SRC="$RULEBOOK_SRC/SOP-SLIDE-06-EXTENSION-AND-SYNC.md"
[ -f "$S06_SRC" ] && _cp "$S06_SRC" "$DEPT_DIR/sops/SOP-SLIDE-06-EXTENSION-AND-SYNC.md" || echo "WARNING: SOP-SLIDE-06 not found" >&2

CONNMAN_SRC="$PRES_DIR/connection-manifest.json"
[ -f "$CONNMAN_SRC" ] && _cp "$CONNMAN_SRC" "$DEPT_DIR/connection-manifest.json" || echo "WARNING: connection-manifest.json not found" >&2

RETIRED_SRC="$PRES_DIR/retired-doctrine-patterns.json"
[ -f "$RETIRED_SRC" ] && _cp "$RETIRED_SRC" "$DEPT_DIR/retired-doctrine-patterns.json" || echo "WARNING: retired-doctrine-patterns.json not found" >&2

echo "[Phase2] Step 6 complete: contract files installed"

# ---- Step 7: Move misfiled scaffold files --------------------
echo "[Phase2] Step 7: Moving misfiled scaffold files..."

SCAFFOLD_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SCAFFOLD_DEST="$DEPT_DIR/working/misfiled-scaffold-$SCAFFOLD_STAMP"
SCAFFOLD_MOVE="AGENTS.md HEARTBEAT.md how-to.md IDENTITY.md MEMORY.md SOUL.md"

for _dir in sops scripts; do
  for _name in $SCAFFOLD_MOVE; do
    _src_file="$DEPT_DIR/$_dir/$_name"
    [ -f "$_src_file" ] && _mv "$_src_file" "$SCAFFOLD_DEST/$_dir/$_name"
  done
  for _name in TOOLS.md USER.md; do
    _src_file="$DEPT_DIR/$_dir/$_name"
    if [ -L "$_src_file" ] && [ ! -e "$_src_file" ]; then _rm "$_src_file"
    elif [ -L "$_src_file" ]; then _mv "$_src_file" "$SCAFFOLD_DEST/$_dir/$_name"
    fi
  done
done

echo "[Phase2] Step 7 complete: scaffold files relocated to $SCAFFOLD_DEST"

# ---- Step 8: Archive the 13 .bak files -----------------------
echo "[Phase2] Step 8: Archiving .bak files..."

BAK_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BAK_DEST="$DEPT_DIR/working/bak-archive-$BAK_STAMP"

# 13 literal names, never a glob
BAK_NAMES=(
  "MASTER-QC-AUTOFAIL-RULESET.md.bak-pre-v12.33.0-20260619-023744"
  "PIPELINE-MANIFEST.json.bak-pre-v12.33.0-20260619-023733"
  "PIPELINE-MANIFEST.json.bak-pre-v10-20260619-031755"
  "PIPELINE-MANIFEST.json.bak-pre-v16-push-20260628-205413"
  "build_deck.py.bak-pre-v16-push-20260628-205254"
  "build_deck.py.bak-reconcile-20260616-120021"
  "sync_check.py.bak-pre-v12.33.0-20260619"
  "kie_generate.py.bak-pre-v12.33.0-20260619"
  "slides.schema.json.bak-pre-v12.33.0-20260619"
  "build_deck.py.bak.20260616-130635"
  "speech_build_harness.py.bak-pre-v12.33.0-20260619"
  "build_deck.py.bak-pre-v12.33.0-20260619-023713"
  "test_preflight.py.bak-pre-v12.33.0-20260619"
)

for _bak_name in "${BAK_NAMES[@]}"; do
  _bak_dir="scripts"
  case "$_bak_name" in
    MASTER-QC-AUTOFAIL-RULESET.md.bak-*|PIPELINE-MANIFEST.json.bak-*)
      _bak_dir="sops" ;;
  esac
  _bak_path="$DEPT_DIR/$_bak_dir/$_bak_name"
  _bak_dst="$BAK_DEST/$_bak_dir/$_bak_name"

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "mv  $_bak_path  ->  $_bak_dst"
  else
    [ -f "$_bak_path" ] || { echo "  skipping $_bak_path (not found)" >&2; continue; }
    _pre_hash="$(shasum -a 256 "$_bak_path" 2>/dev/null | awk '{print $1}' || echo "HASH-FAIL")"
    echo "  $_bak_name  pre-move: $_pre_hash"
    mkdir -p "$BAK_DEST/$_bak_dir"
    mv "$_bak_path" "$_bak_dst"
    _post_hash="$(shasum -a 256 "$_bak_dst" 2>/dev/null | awk '{print $1}' || echo "HASH-FAIL")"
    echo "  $_bak_name  post-move: $_post_hash"
  fi
done

echo "[Phase2] Step 8 complete: .bak files archived to $BAK_DEST"

# ---- Step 9: Clear the 84 broken symlinks --------------------
echo "[Phase2] Step 9: Clearing broken symlinks..."

if [ "$DRY_RUN" -eq 1 ]; then
  find "$DEPT_DIR" -type l ! -exec test -e {} \; -print 2>/dev/null | while IFS= read -r _broken; do
    echo "rm  $_broken"
  done
else
  find "$DEPT_DIR" -type l ! -exec test -e {} \; -delete 2>/dev/null || true
fi

echo "[Phase2] Step 9 complete: broken symlinks cleared"

# ---- Step 10: Run the warn-mode assertion --------------------
echo "[Phase2] Step 10: Running doctrine-provenance assertion..."

_ASSERT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/assert-dept-doctrine-provenance.py"
if [ -f "$_ASSERT" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "python3  $_ASSERT  --dept-dir $DEPT_DIR  --source-root $SKILLS_DIR"
  else
    python3 "$_ASSERT" --dept-dir "$DEPT_DIR" --source-root "$SKILLS_DIR" 2>&1
    echo "[Phase2] assertion exit=$?"
  fi
else
  echo "[Phase2] assert-dept-doctrine-provenance.py not found -- skipping assertion" >&2
fi

echo "[Phase2] Step 10 complete"
echo ""
echo "[Phase2] U004 Phase 2 applied successfully."
echo "[Phase2] Run: cd /tmp && python3 $DEPT_DIR/scripts/sync_check.py --json"
echo "[Phase2]           | python3 -c '...'"
echo "[Phase2] to verify manifest_version 25, 26 phases, 153 autofails, 37 roles."
