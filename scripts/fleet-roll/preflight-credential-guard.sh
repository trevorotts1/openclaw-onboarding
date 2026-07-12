#!/usr/bin/env bash
# ============================================================================
# preflight-credential-guard.sh  (P6-01 fleet-roll machinery)
#
# Purpose: make a fleet roll fail-closed on credential drift. Before a box's
# roll payload runs we SNAPSHOT every credential store on the box; after the
# payload we VERIFY nothing changed; if anything did, we REFUSE (nonzero) and
# the roll RESTOREs from the snapshot. This is the enforcement behind
# docs/FLEET-ROLL-RUNBOOK.md §3/§6: the roll is code-only w.r.t. credentials —
# it must never re-init, re-key, reset, or clear a credential store.
#
# A credential "store" is any place a box keeps a secret:
#   - env stores           (e.g. ~/.openclaw/secrets/.env)
#   - the host-side .env    (VPS, e.g. /docker/<project>/.env)   [passed in]
#   - the pm2 dump          (~/.pm2/dump.pm2 — re-injects env on reboot)
#   - any other secrets file
#   - the LIVE process env  (named credential keys, fingerprinted by value hash)
#
# MODES
#   snapshot <backup_dir>   back up EVERY store to <backup_dir>, recording only
#                           SET / NOT-SET + a SHA-256 fingerprint. NEVER a value.
#   verify   <backup_dir>   re-fingerprint every store and compare to the
#                           snapshot. ANY change / disappearance -> EXIT NONZERO.
#   restore  <backup_dir>   restore file stores from the snapshot copies.
#
# GUARANTEES
#   * FAIL-CLOSED everywhere: any read/parse error, a missing/corrupt snapshot,
#     an unreadable store, or an unknown mode -> refuse (nonzero). Silence is
#     never treated as success.
#   * NEVER prints a secret value. Values are hashed via stdin (never in argv,
#     so `ps` cannot see them); only labels + SET/NOT-SET + hash are recorded,
#     and the manifest + store copies are written 0600 under a 0700 backup dir.
#   * Reads stores; never authors them. This script itself invokes no `gws`,
#     no credential CLI, and rewrites no live store.
#
# CONFIG (all optional; sandbox-overridable so the roll can point it anywhere)
#   PREFLIGHT_HOME            base for default store paths      (default: $HOME)
#   PREFLIGHT_STORES_FILE     file of `LABEL<TAB>PATH` file-store lines. If set,
#                             REPLACES the default file-store list.
#   PREFLIGHT_EXTRA_STORES    extra `LABEL<TAB>PATH` lines appended to the list
#                             (e.g. the VPS host-side .env). Newline-separated.
#   PREFLIGHT_ENV_KEYS_FILE   file of credential key NAMES (one per line) to
#                             fingerprint from the live process env. If set,
#                             REPLACES the default env-key list.
#   The caller is expected to have sourced the box env before `verify` so the
#   live-env keys reflect the box (documented in the runbook).
#
# Portable: bash 3.2 safe (no associative arrays, no mapfile). shasum|sha256sum.
# ============================================================================
set -u

# ---- tiny, side-effect-free helpers ----------------------------------------
err()  { printf '%s\n' "preflight-credential-guard: $*" >&2; }
die()  { err "$*"; exit 1; }              # fail-closed exit
usage() { err "usage: $0 {snapshot|verify|restore} <backup_dir>"; exit 2; }

# SHA-256 of stdin -> bare hex on stdout. Fail-closed if no hasher exists.
_sha_stdin() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
  else
    return 3
  fi
}

# Hash a FILE's bytes (value never surfaces). Empty string on unreadable is NOT
# allowed — caller must have already confirmed readability.
_sha_file() { _sha_stdin < "$1"; }

# Hash a VALUE via stdin so it never appears in argv / ps output.
_sha_value() { printf '%s' "$1" | _sha_stdin; }

# ---- store-list assembly ----------------------------------------------------
# Emits `file<TAB>LABEL<TAB>PATH` lines for every file store to a temp file.
# Default set mirrors a standard OpenClaw box; overridable for VPS + sandbox.
_default_home() { printf '%s' "${PREFLIGHT_HOME:-$HOME}"; }

_build_file_stores() {
  local out="$1" home
  home="$(_default_home)"
  : > "$out" || die "cannot write store list $out"
  if [ -n "${PREFLIGHT_STORES_FILE:-}" ]; then
    [ -r "${PREFLIGHT_STORES_FILE}" ] || die "stores file unreadable: ${PREFLIGHT_STORES_FILE}"
    # copy through, tagging each line as a file store; refuse malformed lines
    while IFS= read -r line || [ -n "$line" ]; do
      [ -z "$line" ] && continue
      case "$line" in \#*) continue ;; esac
      printf '%s' "$line" | grep -q "$(printf '\t')" || die "malformed stores-file line (need LABEL<TAB>PATH): $line"
      printf 'file\t%s\n' "$line" >> "$out"
    done < "${PREFLIGHT_STORES_FILE}"
  else
    # default file stores (only those that make sense on a stock box)
    printf 'file\t%s\t%s\n' "openclaw-secrets-env" "$home/.openclaw/secrets/.env" >> "$out"
    printf 'file\t%s\t%s\n' "pm2-dump"             "$home/.pm2/dump.pm2"          >> "$out"
  fi
  # append any extra stores (e.g. VPS host-side /docker/<project>/.env)
  if [ -n "${PREFLIGHT_EXTRA_STORES:-}" ]; then
    printf '%s\n' "${PREFLIGHT_EXTRA_STORES}" | while IFS= read -r line || [ -n "$line" ]; do
      [ -z "$line" ] && continue
      case "$line" in \#*) continue ;; esac
      printf '%s' "$line" | grep -q "$(printf '\t')" || die "malformed PREFLIGHT_EXTRA_STORES line: $line"
      printf 'file\t%s\n' "$line" >> "$out"
    done
  fi
}

# Emits the env-key NAMES (one per line) to fingerprint from the live env.
_build_env_keys() {
  local out="$1"
  : > "$out" || die "cannot write env-key list $out"
  if [ -n "${PREFLIGHT_ENV_KEYS_FILE:-}" ]; then
    [ -r "${PREFLIGHT_ENV_KEYS_FILE}" ] || die "env-keys file unreadable: ${PREFLIGHT_ENV_KEYS_FILE}"
    grep -v '^[[:space:]]*#' "${PREFLIGHT_ENV_KEYS_FILE}" | grep -v '^[[:space:]]*$' >> "$out" || true
  else
    # default credential key names watched in the live process env
    for k in GHL_API_KEY MC_API_TOKEN TELEGRAM_BOT_TOKEN GOOGLE_API_KEY \
             OPENROUTER_API_KEY KIE_API_KEY ANTHROPIC_API_KEY; do
      printf '%s\n' "$k" >> "$out"
    done
  fi
}

# ---- fingerprinting ---------------------------------------------------------
# Writes the manifest (LABEL\tKIND\tSTATE\tHASH) for the current box to stdout.
# KIND is file|env. STATE is SET|NOTSET. HASH is the sha or '-' for NOTSET.
# Fail-closed: a path that EXISTS but is unreadable is an error (not NOTSET).
_fingerprint() {
  local storelist="$1" envkeys="$2"
  # file stores
  while IFS="$(printf '\t')" read -r kind label path; do
    [ -z "${kind:-}" ] && continue
    if [ -e "$path" ]; then
      if [ -r "$path" ] && [ -f "$path" ]; then
        local h
        h="$(_sha_file "$path")" || die "hasher unavailable while reading store '$label'"
        [ -n "$h" ] || die "empty hash for store '$label' (read error)"
        printf 'file:%s\tfile\tSET\t%s\n' "$label" "$h"
      else
        die "store '$label' exists at $path but is unreadable/not-a-file (fail-closed)"
      fi
    else
      printf 'file:%s\tfile\tNOTSET\t-\n' "$label"
    fi
  done < "$storelist"
  # live-env keys
  while IFS= read -r key || [ -n "$key" ]; do
    [ -z "$key" ] && continue
    # Is the key set in the live env? Use printenv so empty-string values are
    # distinguishable and the value never lands in argv.
    if env | grep -q "^${key}=" ; then
      local v h
      v="$(printenv "$key" 2>/dev/null)" || v=""
      h="$(_sha_value "$v")" || die "hasher unavailable while reading env key '$key'"
      [ -n "$h" ] || die "empty hash for env key '$key'"
      printf 'env:%s\tenv\tSET\t%s\n' "$key" "$h"
    else
      printf 'env:%s\tenv\tNOTSET\t-\n' "$key"
    fi
  done < "$envkeys"
}

# ---- modes ------------------------------------------------------------------
MODE="${1:-}"; BACKUP="${2:-}"
[ -n "$MODE" ] || usage
[ -n "$BACKUP" ] || usage

TMPDIR_G="$(mktemp -d 2>/dev/null)" || die "mktemp failed"
trap 'rm -rf "$TMPDIR_G"' EXIT
STORELIST="$TMPDIR_G/stores.tsv"
ENVKEYS="$TMPDIR_G/envkeys.txt"

do_snapshot() {
  mkdir -p "$BACKUP" || die "cannot create backup dir $BACKUP"
  chmod 700 "$BACKUP" 2>/dev/null || true
  _build_file_stores "$STORELIST"
  _build_env_keys "$ENVKEYS"

  # copy file stores that are SET so restore is possible; record manifest.
  local storecopy="$BACKUP/stores"
  mkdir -p "$storecopy" || die "cannot create $storecopy"
  chmod 700 "$storecopy" 2>/dev/null || true

  # First fingerprint (this also fail-closes on any unreadable store).
  _fingerprint "$STORELIST" "$ENVKEYS" > "$BACKUP/manifest.snapshot" || die "fingerprint failed"
  chmod 600 "$BACKUP/manifest.snapshot" 2>/dev/null || true

  # Copy the actual bytes of every SET file store (for restore). 0600.
  # secrets/.env content is copied ONLY into the 0700/0600 private backup — it
  # is never printed. (chmod 600 satisfied for secrets/.env writers.)
  while IFS="$(printf '\t')" read -r kind label path; do
    [ "$kind" = "file" ] || continue
    if [ -f "$path" ] && [ -r "$path" ]; then
      cp "$path" "$storecopy/$label" || die "cannot back up store '$label'"
      chmod 600 "$storecopy/$label" 2>/dev/null || true
      # remember the origin path for restore
      printf '%s\t%s\n' "$label" "$path" >> "$BACKUP/stores.map"
    fi
  done < "$STORELIST"
  [ -f "$BACKUP/stores.map" ] && chmod 600 "$BACKUP/stores.map" 2>/dev/null || true

  printf 'snapshot OK -> %s\n' "$BACKUP"
  return 0
}

do_verify() {
  [ -d "$BACKUP" ] || die "backup dir missing: $BACKUP (cannot verify)"
  [ -r "$BACKUP/manifest.snapshot" ] || die "snapshot manifest missing/unreadable (cannot verify)"
  # Sanity: snapshot must be non-empty and well-formed (4 tab fields/line).
  awk -F'\t' 'NF!=4{exit 3}' "$BACKUP/manifest.snapshot" || die "corrupt snapshot manifest (bad shape)"
  [ -s "$BACKUP/manifest.snapshot" ] || die "empty snapshot manifest"

  _build_file_stores "$STORELIST"
  _build_env_keys "$ENVKEYS"
  _fingerprint "$STORELIST" "$ENVKEYS" > "$TMPDIR_G/current.manifest" || die "fingerprint failed"

  # Compare current vs snapshot. Any difference in the set of lines = drift.
  # Sort both so ordering never causes a false drift.
  sort "$BACKUP/manifest.snapshot" > "$TMPDIR_G/snap.sorted" || die "sort failed"
  sort "$TMPDIR_G/current.manifest" > "$TMPDIR_G/cur.sorted"  || die "sort failed"

  if diff "$TMPDIR_G/snap.sorted" "$TMPDIR_G/cur.sorted" >/dev/null 2>&1; then
    printf 'verify OK: all credential stores unchanged\n'
    return 0
  fi

  # Report WHICH stores drifted — by label only, NEVER a value/hash detail that
  # helps recover a secret. We print the label and the nature (changed/removed/
  # appeared), derived from field 1 (label) + field 3 (state).
  err "CREDENTIAL DRIFT DETECTED — refusing to proceed:"
  # labels present in exactly one side, or whose state/hash changed
  awk -F'\t' '{print $1"\t"$3"\t"$4}' "$TMPDIR_G/snap.sorted" > "$TMPDIR_G/s3"
  awk -F'\t' '{print $1"\t"$3"\t"$4}' "$TMPDIR_G/cur.sorted"  > "$TMPDIR_G/c3"
  # build label lists
  awk -F'\t' '{print $1}' "$TMPDIR_G/s3" | sort -u > "$TMPDIR_G/s.labels"
  awk -F'\t' '{print $1}' "$TMPDIR_G/c3" | sort -u > "$TMPDIR_G/c.labels"
  while IFS= read -r lbl; do
    snapline="$(awk -F'\t' -v L="$lbl" '$1==L{print $2":"$3}' "$TMPDIR_G/s3")"
    curline="$(awk -F'\t' -v L="$lbl" '$1==L{print $2":"$3}' "$TMPDIR_G/c3")"
    if [ -z "$curline" ]; then
      err "  $lbl : DISAPPEARED since snapshot"
    elif [ -z "$snapline" ]; then
      err "  $lbl : APPEARED since snapshot"
    elif [ "$snapline" != "$curline" ]; then
      # state or hash changed — report state transition, never the hash value
      snstate="${snapline%%:*}"; cstate="${curline%%:*}"
      if [ "$snstate" != "$cstate" ]; then
        err "  $lbl : $snstate -> $cstate"
      else
        err "  $lbl : CONTENT CHANGED (fingerprint differs)"
      fi
    fi
  done < <(cat "$TMPDIR_G/s.labels" "$TMPDIR_G/c.labels" | sort -u)
  return 1
}

do_restore() {
  [ -d "$BACKUP" ] || die "backup dir missing: $BACKUP (cannot restore)"
  [ -r "$BACKUP/manifest.snapshot" ] || die "snapshot manifest missing (cannot restore)"
  if [ ! -f "$BACKUP/stores.map" ]; then
    err "no file stores were captured in snapshot; nothing to restore"
    return 0
  fi
  [ -r "$BACKUP/stores.map" ] || die "stores.map unreadable (cannot restore)"
  local restored=0
  while IFS="$(printf '\t')" read -r label path; do
    [ -z "${label:-}" ] && continue
    src="$BACKUP/stores/$label"
    [ -r "$src" ] || die "backup copy for '$label' missing/unreadable (cannot restore)"
    cp "$src" "$path" || die "cannot restore store '$label' to $path"
    chmod 600 "$path" 2>/dev/null || true
    restored=$((restored+1))
  done < "$BACKUP/stores.map"
  printf 'restore OK: %s file store(s) restored from snapshot\n' "$restored"
  return 0
}

case "$MODE" in
  snapshot) do_snapshot ;;
  verify)   do_verify ;;
  restore)  do_restore ;;
  *)        usage ;;
esac
