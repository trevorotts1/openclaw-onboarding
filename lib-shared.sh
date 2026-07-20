#!/usr/bin/env bash
# ============================================================
#  OpenClaw Onboarding — Shared Library Functions (v1.0.1)
#
#  Sourced by install.sh, update-skills.sh, check-updates.sh, and
#  any skill that needs platform detection or master-files lookup.
#
#  All functions here are platform-aware (Mac vs VPS) and use
#  CANONICAL paths and CANONICAL env-var names.
#
#  PRD 2.1 unified — this file is the single shared copy for
#  both mac and vps platforms. Platform overlays live in
#  platform/mac/ and platform/vps/.
# ============================================================

# ----------------------------------------------------------
# Platform detection
# ----------------------------------------------------------
detect_platform() {
  if [ -d "/data/.openclaw" ]; then
    echo "vps"
  else
    echo "mac"
  fi
}

resolve_platform_paths() {
  if [ -d "/data/.openclaw" ]; then
    export OPENCLAW_PLATFORM="vps"
    export OPENCLAW_HOME="/data"
    export SECRETS_ENV="/data/.openclaw/secrets/.env"
    export CONFIG_JSON="/data/.openclaw/openclaw.json"
    export WORKSPACE="/data/.openclaw/workspace"
    export CANONICAL_MASTER="/data/Downloads/openclaw-master-files"
    export SKILLS_DIR_DEFAULT="/data/.openclaw/skills"
    export BACKUP_DIR_DEFAULT="$HOME/openclaw-backups"
  else
    export OPENCLAW_PLATFORM="mac"
    export OPENCLAW_HOME="$HOME"
    export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
    export CONFIG_JSON="$HOME/.openclaw/openclaw.json"
    export WORKSPACE="$HOME/.openclaw/workspace"
    export WORKSPACE_LEGACY="$HOME/clawd"  # dead legacy path — read-only migration only
    export CANONICAL_MASTER="$HOME/Downloads/openclaw-master-files"
    export SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"
    export BACKUP_DIR_DEFAULT="$HOME/Downloads/openclaw-backups"
  fi
}

# ----------------------------------------------------------
# Master-files folder fuzzy locator
#
# Catches all common name variants:
#   openclaw-master-files
#   OpenClaw Master Files (two words, spaces)
#   openclaw_master_files (underscores)
#   open-claw-master-files (hyphen between "open" and "claw")
#   open claw master files (all spaces)
#   OpenClawMasterFiles (camel case)
#   OpenClaw Documents / openclaw files / etc.
#
# Returns: absolute path of detected folder, or empty string.
# ----------------------------------------------------------
find_master_files() {
  local FOUND=""
  local ROOTS=(
    "$HOME/Downloads"
    "/data/Downloads"
    "/root/Downloads"
    "/data"
    "$HOME"
    "$HOME/clawd"
    "/data/.openclaw/workspace"
    "/opt"
    "/srv"
  )

  for r in "${ROOTS[@]}"; do
    [ -d "$r" ] || continue
    # Two-arm pattern: "openclaw" as one token OR "open claw" as two tokens.
    # Case-insensitive. Excludes backup/zip/bak/tmp folders.
    FOUND=$(find "$r" -maxdepth 2 -type d \
      \( \
        -iname "*openclaw*master*file*" -o \
        -iname "*open*claw*master*file*" -o \
        -iname "*openclaw*master*doc*" -o \
        -iname "*open*claw*master*doc*" -o \
        -iname "*openclaw*document*" -o \
        -iname "*open*claw*document*" \
      \) \
      ! -iname "*backup*" \
      ! -iname "*.zip*" \
      ! -iname "*.bak*" \
      ! -iname "*tmp*" \
      2>/dev/null | head -1)
    [ -n "$FOUND" ] && break
  done

  echo "$FOUND"
}

# Get-or-create. Creates at canonical path if not found.
get_or_create_master_files() {
  resolve_platform_paths
  local FOUND
  FOUND=$(find_master_files)
  if [ -n "$FOUND" ]; then
    echo "$FOUND"
    return 0
  fi
  mkdir -p "$CANONICAL_MASTER"
  echo "$CANONICAL_MASTER"
  return 0
}

# ----------------------------------------------------------
# GHL alias awareness
# Returns 0 if the given string refers to GHL/GoHighLevel/etc.
# ----------------------------------------------------------
is_ghl_alias() {
  local s
  s=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]_-')
  case "$s" in
    ghl|gohighlevel|highlevel|convertandflow|leadconnector|leadconnectorhq|cnf)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# ----------------------------------------------------------
# Canonical GHL credential env-var names
#
# NOTE on the env-var name "GOHIGHLEVEL_API_KEY":
#   This is a LEGACY name. Its value is NOT an API key — it is a
#   Private Integration Token (PIT). GoHighLevel stopped issuing
#   API keys ~2 years ago. Every skill that uses this env var
#   treats the value as a PIT. Do not rename this variable —
#   too many skills reference it.
# ----------------------------------------------------------
canonical_ghl_pit_name() {
  echo "GOHIGHLEVEL_API_KEY"
}

canonical_ghl_location_id_name() {
  echo "GOHIGHLEVEL_LOCATION_ID"
}

# Reads GHL PIT from canonical → JSON → deprecated names. Empty if not found.
read_ghl_pit() {
  resolve_platform_paths
  local v=""
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env"; do
    [ -f "$f" ] || continue
    v=$(grep -E "^GOHIGHLEVEL_API_KEY=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [ -n "$v" ] && echo "$v" && return 0
  done
  for j in "$CONFIG_JSON" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -f "$j" ] || continue
    v=$(python3 -c "
import json
try:
  cfg=json.load(open('$j'))
  print(cfg.get('env',{}).get('vars',{}).get('GOHIGHLEVEL_API_KEY',''))
except: pass
" 2>/dev/null)
    [ -n "$v" ] && echo "$v" && return 0
  done
  # Fall to deprecated names (migration path)
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env"; do
    [ -f "$f" ] || continue
    for name in GHL_API_KEY GHL_PRIVATE_TOKEN GHL_PIT; do
      v=$(grep -E "^${name}=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
      [ -n "$v" ] && echo "$v" && return 0
    done
  done
  echo ""
}

read_ghl_location_id() {
  resolve_platform_paths
  local v=""
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env"; do
    [ -f "$f" ] || continue
    v=$(grep -E "^GOHIGHLEVEL_LOCATION_ID=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [ -n "$v" ] && echo "$v" && return 0
  done
  for j in "$CONFIG_JSON" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -f "$j" ] || continue
    v=$(python3 -c "
import json
try:
  cfg=json.load(open('$j'))
  print(cfg.get('env',{}).get('vars',{}).get('GOHIGHLEVEL_LOCATION_ID',''))
except: pass
" 2>/dev/null)
    [ -n "$v" ] && echo "$v" && return 0
  done
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env"; do
    [ -f "$f" ] || continue
    v=$(grep -E "^GHL_LOCATION_ID=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [ -n "$v" ] && echo "$v" && return 0
  done
  echo ""
}

#=== BEGIN OPENCLAW-BACKUP-RETENTION-V1 ===
# ============================================================
#  Backup retention + disk pre-check -- ONE policy, every site.
#
#  WHY: every update/fix path on every box took a backup and NOTHING
#  ever removed one. Boxes accumulated GB-scale piles. Because a FAILED
#  backup now correctly aborts that box, a box that is tight on disk
#  fails the roll -- turning a storage problem into a roll failure.
#  These helpers close that permanently:
#    oc_backup_precheck_disk  fails LOUD and EARLY, before a byte is
#                             copied, when free space cannot hold it
#    oc_backup_prune          keeps the newest N, deletes older ones,
#                             and is only ever called AFTER a new
#                             backup has already succeeded
#
#  POLICY: keep the newest N. Default 3 = the backup this run just
#  wrote, the previous run's, and one older as safety margin. Two is
#  enough to undo one bad update; the third covers a bad update that
#  was only noticed one run later. Override per run with
#  OPENCLAW_BACKUP_KEEP (integer >= 1; anything else falls back to 3).
#
#  SAFETY RULES -- do not relax:
#    1. Prune runs AFTER a successful new backup, never before. The
#       only good backup is never deleted to make room for one that
#       then fails.
#    2. The current run's backup is never deleted, even when the keep
#       count would otherwise reach it.
#    3. Matching is against the tool's OWN literal name prefix followed
#       by a 4-digit year, one directory deep, and nothing else. A
#       prefix that is empty, shorter than 4 characters, contains a path
#       separator, or contains a glob metacharacter is REFUSED, and a
#       sibling that shares the prefix but is not timestamped is never
#       matched at all. A retention bug that deletes the wrong thing is
#       far worse than the disk it reclaims.
#    4. Every kept and every pruned entry is printed. Never silent.
#
#  This block is duplicated BYTE-FOR-BYTE into update-skills.sh, which
#  is curl-piped and so cannot source this file.
#  tests/unit/backup-retention.test.sh FAILS if the copies drift.
# ============================================================

# How many backups to keep. Never returns less than 1.
oc_backup_keep() {
  local n="${OPENCLAW_BACKUP_KEEP:-3}"
  case "$n" in
    ''|*[!0-9]*) n=3 ;;
  esac
  [ "$n" -lt 1 ] && n=1
  printf '%s' "$n"
}

# Size of a file or directory in KB. Prints 0 when it cannot be read.
oc_backup_size_kb() {
  local p="$1" kb=""
  [ -e "$p" ] || { printf '0'; return 0; }
  kb="$(du -sk "$p" 2>/dev/null | awk 'NR==1 {print $1}')"
  case "$kb" in
    ''|*[!0-9]*) kb=0 ;;
  esac
  printf '%s' "$kb"
}

# oc_backup_precheck_disk <dest_path> <needed_kb> [label]
#
# Verifies the filesystem holding <dest_path> can hold a backup of
# <needed_kb>, plus 20% headroom, plus a 10 MB floor. Walks up to the
# nearest existing parent so it works before mkdir.
#
# Returns 0 when there is room (or when free space genuinely cannot be
# read -- an unreadable df is not evidence of a full disk, so it warns
# and proceeds). Returns 1 LOUDLY, naming the path and the exact
# shortfall, when there is not.
oc_backup_precheck_disk() {
  local dest="$1" need_kb="$2" label="${3:-backup}"
  case "$need_kb" in
    ''|*[!0-9]*) need_kb=0 ;;
  esac

  local probe="$dest"
  while [ -n "$probe" ] && [ "$probe" != "/" ] && [ ! -d "$probe" ]; do
    probe="$(dirname "$probe")"
  done
  [ -d "$probe" ] || probe="/"

  local free_kb
  free_kb="$(df -Pk "$probe" 2>/dev/null | awk 'NR==2 {print $4}')"
  case "$free_kb" in
    ''|*[!0-9]*)
      echo "  [backup-precheck] WARN: cannot read free space for $probe -- proceeding with $label"
      return 0
      ;;
  esac

  # 20% headroom over the measured size, and never less than 10 MB free.
  local want_kb=$(( need_kb + need_kb / 5 + 10240 ))
  if [ "$free_kb" -lt "$want_kb" ]; then
    local short_kb=$(( want_kb - free_kb ))
    echo "" >&2
    echo "  ############################################################" >&2
    echo "  ## BACKUP ABORTED -- NOT ENOUGH FREE DISK" >&2
    echo "  ##   what      : $label" >&2
    echo "  ##   target    : $dest" >&2
    echo "  ##   filesystem: $probe" >&2
    echo "  ##   need      : ${want_kb} KB (${need_kb} KB of data + 20% headroom + 10 MB floor)" >&2
    echo "  ##   free      : ${free_kb} KB" >&2
    echo "  ##   short by  : ${short_kb} KB" >&2
    echo "  ## Refusing to start a backup that would die halfway and" >&2
    echo "  ## leave a corrupt archive. Free space on $probe, then re-run." >&2
    echo "  ############################################################" >&2
    echo "" >&2
    return 1
  fi

  echo "  [backup-precheck] OK: $label needs ~${want_kb} KB, ${free_kb} KB free on $probe"
  return 0
}

# oc_backup_prune <parent_dir> <literal_name_prefix> [current_backup_path]
#
# Keeps the newest N entries in <parent_dir> whose basename is
# <literal_name_prefix> followed immediately by a 4-digit year, deletes
# the rest, and prints every decision. Newest is decided by reverse
# lexical sort of the name, which is exactly newest-first for the
# YYYYmmdd-HHMMSS / YYYY-mm-dd-HHMMSS / YYYYmmddTHHMMSSZ stamps every
# caller here embeds. Requiring the year means an untimestamped sibling
# that happens to share the prefix is never matched and never counted.
#
# CALL THIS ONLY AFTER THE NEW BACKUP SUCCEEDED.
#
# Returns 1 without deleting anything if the prefix is not safely specific.
oc_backup_prune() {
  local parent="$1" prefix="$2" current="${3:-}"

  [ -d "$parent" ] || return 0

  case "$prefix" in
    ''|.|..)          echo "  [backup-prune] REFUSING: empty or dot prefix" >&2; return 1 ;;
    */*)              echo "  [backup-prune] REFUSING: prefix contains a path separator: $prefix" >&2; return 1 ;;
    *'*'*|*'?'*|*'['*|*']'*)
                      echo "  [backup-prune] REFUSING: prefix contains a glob metacharacter: $prefix" >&2; return 1 ;;
  esac
  if [ "${#prefix}" -lt 4 ]; then
    echo "  [backup-prune] REFUSING: prefix too short to be specific: $prefix" >&2
    return 1
  fi

  local keep_n current_base=""
  keep_n="$(oc_backup_keep)"
  [ -n "$current" ] && current_base="$(basename "$current")"

  local seen=0 pruned=0 entry base
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    base="$(basename "$entry")"
    seen=$(( seen + 1 ))

    if [ "$seen" -le "$keep_n" ]; then
      echo "  [backup-prune] KEEP  ($seen/$keep_n): $entry"
      continue
    fi
    if [ -n "$current_base" ] && [ "$base" = "$current_base" ]; then
      echo "  [backup-prune] KEEP  (current run -- never pruned): $entry"
      continue
    fi
    if rm -rf -- "$entry" 2>/dev/null; then
      pruned=$(( pruned + 1 ))
      echo "  [backup-prune] PRUNE: $entry"
    else
      echo "  [backup-prune] WARN: could not remove $entry" >&2
    fi
  done <<EOF
$(find "$parent" -mindepth 1 -maxdepth 1 -name "${prefix}[0-9][0-9][0-9][0-9]*" 2>/dev/null | LC_ALL=C sort -r)
EOF

  echo "  [backup-prune] $parent/${prefix}<timestamp>* -- kept $(( seen - pruned )), pruned $pruned (keep=$keep_n)"
  return 0
}
#=== END OPENCLAW-BACKUP-RETENTION-V1 ===
