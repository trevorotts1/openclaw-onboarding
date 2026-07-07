#!/usr/bin/env bash
# ============================================================================
# harden-gws-credential-resilience.sh
#
# Idempotent, ADDITIVE, box-user resilience so a HEADLESS `gws` (Google Workspace
# CLI) call can NEVER self-wipe the default credential, and so that a wipe — if
# one ever happens by any path — is always recoverable off-box.
#
# BACKGROUND (proven root cause of the v16.1.x fleet credential wipe): with the
# gws DEFAULT keyring backend ("keyring" = the OS keychain), a bare `gws` run in
# a HEADLESS / non-interactive context (no TTY, cannot unlock the keychain) hits
# gws's OWN failure mode and rewrites ~/.config/gws/credentials.enc to
# credential_source:"none" — erasing every account's OAuth. Forcing the FILE
# keyring backend (GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file) makes gws use the
# on-disk key deterministically, so the self-clear can no longer happen.
#
# The skill-14 QC (qc-google-workspace-integration.sh) already pins the backend
# for its own run. THIS script closes the rest of the class fleet-wide by baking
# the resilience into every box, so ANY bare gws call — from a doc/EXAMPLES step,
# an agent shell, a cron, or a future script — is safe:
#
#   (1) ~/.zshenv (+ ~/.bashrc, ~/.profile) get an APPEND-ONLY managed block that
#       exports GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file. On a Mac box the agent
#       shell is zsh, and ~/.zshenv is sourced for EVERY zsh invocation (login,
#       interactive, AND non-interactive script) — so every gws the agent runs
#       inherits the file backend. The bash/profile copies cover bash login /
#       interactive shells on other boxes. Set-if-absent via a sentinel; never
#       overwrites the file and never drops a value the client already exported.
#
#   (2) the `gws-as` wrapper is installed on the agent PATH (~/.openclaw/bin).
#       It FORCES the file backend for any explicit / scripted / cron gws call
#       (belt-and-suspenders for non-zsh, non-interactive shells that do not read
#       ~/.zshenv) and routes to a per-account gws config dir.
#
#   (3) an off-box encrypted snapshot of the DEFAULT credential store
#       (credentials.enc + its file-keyring key) is written under
#       ~/.openclaw/secrets/backups/<box>-gws/<ts>/ (700 dir / 600 files). That
#       tree rides the existing off-box secrets backup, so a wipe is always
#       restorable from the latest snapshot that still has both files.
#
# This script NEVER invokes `gws`, never deletes/moves/re-keys/rewrites any
# credential store (it only READS + copies it), takes no client-specific input,
# and writes only inside the box user's HOME / OpenClaw config. Best-effort:
# every step is guarded and it exits 0 even when parts are skipped, so it can be
# dropped into the install / update / verify path without ever breaking it.
#
# Safe to re-run any number of times (idempotent). Run AS THE BOX USER, not root.
# ============================================================================
set -uo pipefail

log() { printf '  [gws-harden] %s\n' "$*"; }

# ── Never write as root ──────────────────────────────────────────────────────
# Writing dotfiles/creds as root would either target /root (wrong HOME) or leave
# root-owned files the box user (e.g. `node` on VPS) cannot read (EACCES). If we
# are root, re-exec as the owner of the OpenClaw config dir (best-effort, NON-
# interactive so it can never hang); if that is not possible, SKIP cleanly.
if [ "$(id -u 2>/dev/null || echo 0)" = "0" ] && [ "${OPENCLAW_GWS_HARDEN_REEXEC:-0}" != "1" ]; then
  _cfg="/data/.openclaw"; [ -d "$_cfg" ] || _cfg="${OC_CONFIG:-$HOME/.openclaw}"
  _owner=""
  _owner="$(stat -f '%Su' "$_cfg" 2>/dev/null || stat -c '%U' "$_cfg" 2>/dev/null || echo "")"
  if [ -n "$_owner" ] && [ "$_owner" != "root" ] && command -v sudo >/dev/null 2>&1; then
    log "running as root — re-executing as box user '$_owner' (config writes must never be root-owned)"
    if sudo -n -H -u "$_owner" env OPENCLAW_GWS_HARDEN_REEXEC=1 bash "$0" "$@" 2>/dev/null; then
      exit 0
    fi
    log "could not drop to '$_owner' non-interactively"
  fi
  log "SKIP — running as root and cannot drop to the box user; re-run this as the box user to harden gws."
  exit 0
fi

# ── Resolve platform paths (respect an inherited OC_CONFIG from install.sh) ───
OC_CONFIG="${OC_CONFIG:-}"
if [ -z "$OC_CONFIG" ]; then
  if [ -d "/data/.openclaw" ]; then OC_CONFIG="/data/.openclaw"; else OC_CONFIG="$HOME/.openclaw"; fi
fi
OC_BIN="$OC_CONFIG/bin"
# The DEFAULT gws credential store. Honor an explicit CONFIG_DIR override.
GWS_DEFAULT_STORE="${GOOGLE_WORKSPACE_CLI_CONFIG_DIR:-$HOME/.config/gws}"
BK_ROOT="$OC_CONFIG/secrets/backups"

# ============================================================================
# (1) Shell-env managed block — force the file keyring backend for every shell.
# ============================================================================
# APPEND-ONLY, sentinel-guarded. We never rewrite the dotfile (an overwrite could
# drop the client's own exports), and we never emit a bare/unset value (req: the
# backend export must never be dropped). If a line already exports the backend,
# the managed block is harmless (later export wins to `file`, which is what we
# want) — but we still only add our block once, keyed on the sentinel.
OC_ENV_SENTINEL="openclaw:gws-keyring-backend"
add_env_block() {
  local rc="$1"
  # Already hardened this file? (idempotent)
  if [ -f "$rc" ] && grep -q "$OC_ENV_SENTINEL" "$rc" 2>/dev/null; then
    return 0
  fi
  # Append (>>) — NEVER overwrite (>). Creates the file if absent.
  {
    printf '\n# >>> %s (managed — added by harden-gws-credential-resilience.sh) >>>\n' "$OC_ENV_SENTINEL"
    printf '# Force the gws FILE keyring backend so a headless gws can never self-wipe\n'
    printf '# the default credential (the v16.1.x self-wipe vector). "file" is the SAFE\n'
    printf '# value and "keyring" (the OS keychain) is the dangerous one, so we force it.\n'
    printf 'export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file\n'
    printf '# <<< %s (managed) <<<\n' "$OC_ENV_SENTINEL"
  } >> "$rc" 2>/dev/null && log "hardened $rc (GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file)" \
    || log "could not write $rc (skipped)"
}
for _rc in "$HOME/.zshenv" "$HOME/.bashrc" "$HOME/.profile"; do
  add_env_block "$_rc"
done

# ============================================================================
# (2) Install the `gws-as` wrapper on the agent PATH.
# ============================================================================
mkdir -p "$OC_BIN" 2>/dev/null || true
GWS_AS="$OC_BIN/gws-as"
write_gws_as() {
  # Quoted heredoc — the wrapper body is written verbatim (nothing expands here;
  # $HOME / $1 / $acct expand when the wrapper RUNS on the box).
  cat > "$GWS_AS" <<'GWS_AS_EOF'
#!/usr/bin/env bash
# gws-as — run the Google Workspace CLI (gws) with the FILE keyring backend
# FORCED, so a headless / non-interactive call can never self-wipe the default
# credential (the v16.1.x self-wipe vector). Installed + kept in sync by
# scripts/harden-gws-credential-resilience.sh.
#
# Usage:
#   gws-as <account> <gws args...>
#   gws-as default drive files list
#   gws-as sales gmail messages list --params '{"q":"is:unread"}'
#
# <account> selects the gws config dir (multi-account = separate config dirs):
#   default | primary | ""   -> the default store (~/.config/gws)
#   <name>                   -> ~/.config/gws-acct-<name> (or ~/.config/gws-<name>)
#   /abs/path | ./rel        -> that directory, used verbatim if it exists
#
# It only ever ADDS environment (keyring backend + optional config dir) and then
# execs gws. It never deletes, moves, re-keys, or rewrites any credential store.
export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file   # load-bearing: never self-wipe

acct="${1:-default}"
if [ "$#" -gt 0 ]; then shift; fi

case "$acct" in
  default|primary|"")
    : ;;                                       # gws's built-in default store
  /*|./*|../*)
    [ -d "$acct" ] && export GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$acct" ;;
  *)
    for d in "$HOME/.config/gws-acct-$acct" "$HOME/.config/gws-$acct"; do
      if [ -d "$d" ]; then export GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$d"; break; fi
    done
    if [ -z "${GOOGLE_WORKSPACE_CLI_CONFIG_DIR:-}" ]; then
      export GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$HOME/.config/gws-acct-$acct"
    fi ;;
esac

exec gws "$@"
GWS_AS_EOF
}
if write_gws_as; then
  chmod 0755 "$GWS_AS" 2>/dev/null || true
  log "installed gws-as wrapper: $GWS_AS"
else
  log "could not install gws-as wrapper at $GWS_AS (skipped)"
fi

# ============================================================================
# (3) Off-box encrypted snapshot of the default credential store.
# ============================================================================
# Snapshots credentials.enc + its file-keyring key(s) into
# ~/.openclaw/secrets/backups/<box>-gws/<ts>/ so a wipe is always recoverable.
# Only snapshots when creds are PRESENT and CHANGED vs the latest snapshot; keeps
# the last 10. Pure copy (cp) — the source store is never mutated.
backup_gws_store() {
  local store="$GWS_DEFAULT_STORE"
  local cred="$store/credentials.enc"
  if [ ! -f "$cred" ]; then
    log "no default gws credentials at $cred yet — nothing to back up (resilience still installed)"
    return 0
  fi
  local box ts dest latest
  box="$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo box)"
  box="$(printf '%s' "$box" | tr -c 'A-Za-z0-9._-' '_' )"
  ts="$(date +%Y%m%d-%H%M%S)"
  local base="$BK_ROOT/${box}-gws"
  mkdir -p "$base" 2>/dev/null || { log "could not create backup dir $base (skipped)"; return 0; }
  chmod 0700 "$BK_ROOT" "$base" 2>/dev/null || true

  # Change detection: skip if the newest snapshot's credentials.enc is identical.
  latest="$(ls -1dt "$base"/*/ 2>/dev/null | head -1 || true)"
  if [ -n "$latest" ] && [ -f "${latest}credentials.enc" ]; then
    if cmp -s "$cred" "${latest}credentials.enc"; then
      log "gws credentials unchanged since last snapshot — no new backup needed"
      return 0
    fi
  fi

  dest="$base/$ts"
  mkdir -p "$dest" 2>/dev/null || { log "could not create snapshot dir $dest (skipped)"; return 0; }
  chmod 0700 "$dest" 2>/dev/null || true

  # Copy credentials.enc + every key/enc file at the store root (covers the
  # file-keyring key under its various names: .encryption_key, keyring.key, *.key).
  local copied=0 f name
  for f in "$cred" "$store"/.encryption_key "$store"/keyring.key "$store"/*.key "$store"/*.enc; do
    [ -f "$f" ] || continue
    name="$(basename "$f")"
    [ -e "$dest/$name" ] && continue          # dedupe: a glob may re-match a file
    if cp -p "$f" "$dest/$name" 2>/dev/null; then
      chmod 0600 "$dest/$name" 2>/dev/null || true
      copied=$((copied + 1))
    fi
  done
  if [ "$copied" -gt 0 ]; then
    log "off-box gws snapshot written: $dest ($copied file(s), 600/700)"
  else
    log "gws snapshot produced no files (skipped)"
    rmdir "$dest" 2>/dev/null || true
    return 0
  fi

  # Prune: keep the newest 10 snapshots.
  local old
  old="$(ls -1dt "$base"/*/ 2>/dev/null | tail -n +11 || true)"
  if [ -n "$old" ]; then
    printf '%s\n' "$old" | while IFS= read -r d; do [ -n "$d" ] && rm -rf "$d" 2>/dev/null || true; done
  fi
}
backup_gws_store || true

log "gws credential-resilience hardening complete (idempotent)."
exit 0
