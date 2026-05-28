#!/usr/bin/env bash
# 01-locate-master-files-folder.sh
# Skill 38 — Step O.2 (Locate or, last resort, create the client's master
# files folder). Implements O.2.A semantic discovery, O.2.B disambiguation,
# O.2.C operator-confirmed creation, O.2.D playbook copy, O.2.E run manifest.
#
# Idempotent. Safe to re-run. Persists selection to
# $HOME/.openclaw/.skill-38-master-files-dir.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLAYBOOK_SRC="$SKILL_ROOT/references/v5.14-source-playbook.md"
OS="$(uname -s)"
TS="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$HOME/.openclaw"
STATE_FILE="$HOME/.openclaw/.skill-38-master-files-dir"

# ---------- O.2.A — Semantic discovery (read-only) ----------
if [ "$OS" = "Darwin" ]; then
  ROOTS=("$HOME/Downloads" "$HOME/Documents" "$HOME/Desktop" "$HOME/OpenClaw" "$HOME/.openclaw" "$HOME")
  DEFAULT_CREATE="$HOME/Downloads/OpenClaw Master Files"
else
  ROOTS=("/data" "/root" "/var/openclaw" "/home" "$HOME" "$HOME/.openclaw")
  DEFAULT_CREATE="/data/openclaw-master-files"
fi

CANDIDATES=()
for root in "${ROOTS[@]}"; do
  [ -d "$root" ] || continue
  while IFS= read -r line; do
    [ -n "$line" ] && CANDIDATES+=("$line")
  done < <(find "$root" -maxdepth 4 -type d 2>/dev/null \
      | grep -iE '(openclaw.*master|claw.*master|openclaw.*files|master.*files)' \
      || true)
done

# Dedupe candidates
if [ "${#CANDIDATES[@]}" -gt 0 ]; then
  IFS=$'\n' CANDIDATES=($(printf '%s\n' "${CANDIDATES[@]}" | sort -u))
  unset IFS
fi

N="${#CANDIDATES[@]}"
SELECTION_REASON=""
MASTER_FILES_DIR=""

# ---------- O.2.B — Disambiguate ----------
if [ "$N" -eq 1 ]; then
  MASTER_FILES_DIR="${CANDIDATES[0]}"
  SELECTION_REASON="single match"
elif [ "$N" -gt 1 ]; then
  echo "I found multiple candidate folders that look like OpenClaw master files folders:" >&2
  i=1
  for c in "${CANDIDATES[@]}"; do
    if [ "$OS" = "Darwin" ]; then
      MTIME="$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$c" 2>/dev/null || echo unknown)"
    else
      MTIME="$(stat -c '%y' "$c" 2>/dev/null | cut -d. -f1 || echo unknown)"
    fi
    MD_COUNT="$(find "$c" -maxdepth 2 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
    echo "  $i. $c" >&2
    echo "     Last modified: $MTIME" >&2
    echo "     Contains: $MD_COUNT .md files" >&2
    i=$((i+1))
  done
  echo "" >&2
  echo "Which one is the active master files folder? (Reply with the number — I will NOT touch the others.)" >&2
  read -r CHOICE
  if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "$N" ]; then
    echo "Invalid selection: $CHOICE" >&2
    exit 1
  fi
  MASTER_FILES_DIR="${CANDIDATES[$((CHOICE-1))]}"
  SELECTION_REASON="operator chose"
fi

# ---------- O.2.C — Last-resort create (explicit YES required) ----------
if [ -z "$MASTER_FILES_DIR" ]; then
  echo "I couldn't find an existing master files folder after a full search of:" >&2
  for r in "${ROOTS[@]}"; do echo "  - $r" >&2; done
  echo "" >&2
  echo "May I create one at: $DEFAULT_CREATE ?" >&2
  echo "Type YES to confirm (anything else aborts):" >&2
  read -r CONFIRM
  if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted by operator — no folder created." >&2
    exit 1
  fi
  mkdir -p "$DEFAULT_CREATE"
  MASTER_FILES_DIR="$DEFAULT_CREATE"
  SELECTION_REASON="newly created with operator approval"
fi

# Persist selection for downstream scripts
printf '%s\n' "$MASTER_FILES_DIR" > "$STATE_FILE"

# ---------- O.2.D — Save playbook copy (idempotent) ----------
DEST_PLAYBOOK="$MASTER_FILES_DIR/v5.14-source-playbook.md"
if [ -f "$PLAYBOOK_SRC" ]; then
  if [ ! -f "$DEST_PLAYBOOK" ] || [ "$PLAYBOOK_SRC" -nt "$DEST_PLAYBOOK" ]; then
    cp "$PLAYBOOK_SRC" "$DEST_PLAYBOOK"
    echo "[O.2.D] Playbook copied to: $DEST_PLAYBOOK" >&2
  else
    echo "[O.2.D] Playbook already current at: $DEST_PLAYBOOK (skipped)" >&2
  fi
else
  echo "[O.2.D] WARNING: playbook source not found at $PLAYBOOK_SRC — skipping copy" >&2
fi

# ---------- O.2.E — Append to Run Manifest ----------
RUN_MANIFEST="$(ls -1t "$MASTER_FILES_DIR"/run-manifest-*.md 2>/dev/null | head -n1 || true)"
if [ -z "$RUN_MANIFEST" ]; then
  RUN_MANIFEST="$MASTER_FILES_DIR/run-manifest-$TS.md"
  {
    echo "# Skill 38 — Run Manifest ($TS)"
    echo ""
  } > "$RUN_MANIFEST"
fi

{
  echo ""
  echo "## O.2 — Master files folder discovery"
  echo ""
  echo "- Candidates found: $N"
  echo "- Candidate paths:"
  if [ "$N" -gt 0 ]; then
    for c in "${CANDIDATES[@]}"; do echo "  - $c"; done
  else
    echo "  - (none)"
  fi
  echo "- Selected MASTER_FILES_DIR: $MASTER_FILES_DIR"
  echo "- Selection reason: $SELECTION_REASON"
  echo "- Playbook saved as: $DEST_PLAYBOOK"
  echo "- Recorded at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$RUN_MANIFEST"

echo "$MASTER_FILES_DIR"
