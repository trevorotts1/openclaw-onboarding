#!/usr/bin/env bash
# 01-locate-master-files-folder.sh -- Skill 41 Build With AI Playbook Generator
# The master-files discovery "teacher protocol" (TYP Self-Orientation O.2.A-O.2.E).
# BYTE-IDENTICAL on Mac and VPS: portability is by uname -s branch, not by divergent files.
# NEVER hardcodes a path. NEVER silently creates a folder. Reuses Skill 38's canonical
# pointer as the cross-skill single source of truth. Persists its own pointer (read, never sourced).
set -euo pipefail

OS="$(uname -s)"
mkdir -p "$HOME/.openclaw"
SKILL41_POINTER="$HOME/.openclaw/.skill-41-master-files-dir"
SKILL38_POINTER="$HOME/.openclaw/.skill-38-master-files-dir"

if [[ "$OS" == "Darwin" ]]; then
  DEFAULT_CREATE="$HOME/Downloads/OpenClaw Master Files"
  ROOTS=("$HOME/Downloads" "$HOME/Documents" "$HOME/Desktop" "$HOME/OpenClaw" "$HOME/.openclaw" "$HOME")
elif [[ "$OS" == "Linux" ]]; then
  DEFAULT_CREATE="/data/openclaw-master-files"
  ROOTS=(/data /root /var/openclaw /home "$HOME" "$HOME/.openclaw")
else
  echo "[skill 41] Unsupported OS: $OS" >&2
  exit 2
fi

SELECTED=""
REASON=""

# Precedence 1: explicit env override
if [[ -n "${MASTER_FILES_DIR:-}" && -d "${MASTER_FILES_DIR:-}" ]]; then
  SELECTED="$MASTER_FILES_DIR"; REASON="env override"
fi

# Precedence 2: reuse Skill 38's canonical pointer (cross-skill source of truth)
if [[ -z "$SELECTED" && -f "$SKILL38_POINTER" ]]; then
  cand="$(head -n1 "$SKILL38_POINTER" | tr -d '\r')"
  if [[ -d "$cand" ]]; then SELECTED="$cand"; REASON="reused Skill 38 pointer"; fi
fi

# Precedence 3: reuse this skill's own prior pointer
if [[ -z "$SELECTED" && -f "$SKILL41_POINTER" ]]; then
  cand="$(head -n1 "$SKILL41_POINTER" | tr -d '\r')"
  if [[ -d "$cand" ]]; then SELECTED="$cand"; REASON="reused Skill 41 pointer"; fi
fi

# O.2.A: read-only semantic (fuzzy) discovery across roots
if [[ -z "$SELECTED" ]]; then
  CANDIDATES=()
  for root in "${ROOTS[@]}"; do
    [[ -d "$root" ]] || continue
    while IFS= read -r d; do
      [[ -n "$d" ]] && CANDIDATES+=("$d")
    done < <(find "$root" -maxdepth 4 -type d 2>/dev/null | grep -iE '(openclaw.*master|claw.*master|openclaw.*files|master.*files)' || true)
  done
  if [[ ${#CANDIDATES[@]} -gt 0 ]]; then
    IFS=$'\n' read -r -d '' -a CANDIDATES < <(printf '%s\n' "${CANDIDATES[@]}" | sort -u && printf '\0')
  fi
  N=${#CANDIDATES[@]}

  if [[ $N -eq 1 ]]; then
    SELECTED="${CANDIDATES[0]}"; REASON="single match"
  elif [[ $N -gt 1 ]]; then
    # O.2.B: never auto-pick; show each candidate with mtime + .md count, ask operator
    echo "[skill 41] Multiple candidate master-files folders found:"
    idx=1
    for c in "${CANDIDATES[@]}"; do
      if [[ "$OS" == "Darwin" ]]; then mt="$(stat -f '%Sm' "$c" 2>/dev/null || echo '?')"; else mt="$(stat -c '%y' "$c" 2>/dev/null || echo '?')"; fi
      mdc="$(find "$c" -maxdepth 2 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
      echo "  [$idx] $c  (modified: $mt, .md files: $mdc)"
      idx=$((idx + 1))
    done
    if [[ -t 0 ]]; then
      printf "[skill 41] Which one is the active master files folder? Reply with the number (I will NOT touch the others): "
      read -r CHOICE
      if [[ "$CHOICE" =~ ^[0-9]+$ && "$CHOICE" -ge 1 && "$CHOICE" -le $N ]]; then
        SELECTED="${CANDIDATES[$((CHOICE - 1))]}"; REASON="operator chose"
      else
        echo "[skill 41] Invalid choice. Aborting without touching anything." >&2; exit 1
      fi
    else
      echo "[skill 41] Multiple candidates and no interactive terminal. Set MASTER_FILES_DIR and re-run." >&2; exit 1
    fi
  fi
fi

# O.2.C: create ONLY as a last resort, WITH explicit YES approval
if [[ -z "$SELECTED" ]]; then
  echo "[skill 41] No master files folder found. Searched roots:"
  printf '  %s\n' "${ROOTS[@]}"
  if [[ -t 0 ]]; then
    printf "[skill 41] May I create one at: %s ? Type YES to confirm (anything else aborts): " "$DEFAULT_CREATE"
    read -r CONFIRM
    if [[ "$CONFIRM" == "YES" ]]; then
      mkdir -p "$DEFAULT_CREATE"; SELECTED="$DEFAULT_CREATE"; REASON="created with operator approval"
    else
      echo "[skill 41] Aborted by operator -- no folder created." >&2; exit 1
    fi
  else
    echo "[skill 41] No folder and no interactive terminal -- refusing to create silently. Set MASTER_FILES_DIR and re-run." >&2; exit 1
  fi
fi

# Persist the pointer (downstream scripts READ this with head/cat -- never source it)
printf '%s\n' "$SELECTED" > "$SKILL41_POINTER"

# O.2.E: write a run manifest into the selected folder
TS="$(date -u +%Y%m%dT%H%M%SZ)"
{
  echo "# Skill 41 master-files discovery run manifest"
  echo "- timestamp: $TS"
  echo "- os: $OS"
  echo "- selected: $SELECTED"
  echo "- selection reason: $REASON"
  echo "- pointer file: $SKILL41_POINTER"
} > "$SELECTED/run-manifest-skill41-$TS.md" 2>/dev/null || true

echo "[skill 41] MASTER_FILES_DIR = $SELECTED ($REASON)"
# Last line is the resolved dir for downstream capture
echo "$SELECTED"
