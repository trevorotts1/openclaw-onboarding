#!/usr/bin/env bash
# shared-utils/provision-claude-settings.sh
# ----------------------------------------------------------------------------
# Provision the operator's Claude Code subagent-concurrency settings onto a box.
#
# WHY THIS EXISTS. Claude Code enforces TWO SEPARATE agent limits, and the
# defaults throttle every fan-out on a client box:
#
#   CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS  how many Agent-tool subagents may run
#                                         AT ONCE. Platform default 20. Verified
#                                         enforced in the 2.1.227 binary:
#                                           nJu(){ return
#                                             re.CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS
#                                             ?? Ml_ }   with Ml_ = 20
#                                         Unset -> 20. Set -> whatever you set.
#   CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION total subagents over a session's life.
#                                         Runtime enforcement UNVERIFIED (the key
#                                         appears in the binary's env-var table;
#                                         no enforcement site was located). Set
#                                         anyway so the configuration record is
#                                         consistent fleet-wide.
#
# WHAT THIS DOES *NOT* TOUCH. The Workflow tool's per-run concurrency is a
# SEPARATE limit computed from the box's own CPU count:
#     Math.min(16, Math.max(2, os.cpus().length - 2))
# It reads NO environment variable and cannot be raised from here. A 12-core box
# gets 10; an 8-core box gets 6. That is per WORKFLOW RUN, and each top-level
# Workflow call gets its own semaphore, so concurrency scales by running MORE
# workflows, never by making one workflow wider. Nothing in this script changes
# that, and no client should be told otherwise.
#
# SAFETY CONTRACT (this script is deliberately narrow):
#   * MERGES two keys into env{}. Never rewrites, reorders, or removes anything
#     else. A client's model pin, permissions, hooks, and plugins are untouched
#     -- model/provider sovereignty is never altered from here.
#   * Backs up every file before writing and prints the backup path.
#   * Validates JSON after writing; on ANY parse failure it RESTORES the backup
#     and exits nonzero. A box is never left with a broken settings.json.
#   * Idempotent: re-running is a no-op once the values already match.
#   * python3 only -- no jq dependency (jq is absent on several fleet boxes).
#   * Runs as the invoking (node) user. Refuses to run as root, because a
#     root-owned settings.json freezes the box's Claude Code on next start.
#   * Never prints a credential. It only ever reads/writes these two keys.
#   * LAUNCHER-AWARE. These keys are read by the Claude Code BINARY at session
#     start. A box with no launcher installed (every OpenClaw-only VPS, for
#     example) can never read them, so writing them there produces a dead file
#     that looks like success. This script therefore provisions a profile ONLY
#     when its launcher is actually installed:
#         ~/.claude       <- requires `claude`      on PATH or a known install dir
#         ~/.claude-nine  <- requires `claude-nine` (or `claude-9`) likewise
#     A profile DIRECTORY alone is NOT proof -- an OpenClaw box can carry a
#     leftover ~/.claude with no binary behind it. Neither launcher present is a
#     clean, expected SKIP (exit 0), never a failure.
#     Note: a resolvable name proves the NAME resolves, not that the program
#     runs. That is sufficient here -- we are deciding whether a settings file
#     could ever be read, not whether the binary is healthy.
#
# Exit codes: 0 = provisioned or already correct, 2 = failure (nothing changed).
# ----------------------------------------------------------------------------
set -u

CONCURRENT_VALUE="${CLAUDE_SETTINGS_CONCURRENT_VALUE:-500}"
PER_SESSION_VALUE="${CLAUDE_SETTINGS_PER_SESSION_VALUE:-10000}"

_stamp="$(date '+%Y%m%d-%H%M%S')"
_rc=0
_changed=0
_seen=0
_skipped=0

if [ "$(id -u)" = "0" ]; then
  echo "  ✋ provision-claude-settings: refusing to run as root (a root-owned settings.json freezes Claude Code on this box)." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "  ✋ provision-claude-settings: python3 not found on PATH — cannot safely edit JSON. Nothing written." >&2
  exit 2
fi

# Is a launcher actually installed? Checks PATH first, then the install dirs
# used across the fleet (npm global, user-local, Homebrew both arches, ~/bin).
# $1.. = candidate binary names for this profile.
_launcher_installed() {
  local _name
  for _name in "$@"; do
    command -v "$_name" >/dev/null 2>&1 && return 0
    local _p
    for _p in "$HOME/.npm-global/bin/$_name" "$HOME/.local/bin/$_name" \
              "$HOME/bin/$_name" "/usr/local/bin/$_name" \
              "/opt/homebrew/bin/$_name" "/usr/bin/$_name"; do
      [ -x "$_p" ] && return 0
    done
  done
  return 1
}

# Both profiles, each gated on ITS OWN launcher being installed.
for _spec in ".claude:claude" ".claude-nine:claude-nine claude-9"; do
  _dirname="${_spec%%:*}"
  _bins="${_spec#*:}"
  _dir="$HOME/$_dirname"
  _f="$_dir/settings.json"

  # shellcheck disable=SC2086
  if ! _launcher_installed $_bins; then
    if [ -d "$_dir" ]; then
      echo "  = ${_dirname}/ exists but no launcher installed (looked for: ${_bins}) — these keys would never be read. SKIPPED, nothing written."
    fi
    _skipped=$((_skipped + 1))
    continue
  fi
  _seen=$((_seen + 1))

  # Launcher is installed but has never run, so no profile dir yet. Create it
  # so the settings are in place for its first session.
  [ -d "$_dir" ] || mkdir -p "$_dir" || { echo "  ✋ could not create $_dir" >&2; _rc=2; continue; }

  _bak=""
  if [ -f "$_f" ]; then
    _bak="${_f}.bak-concurrency-${_stamp}"
    if ! cp -p "$_f" "$_bak"; then
      echo "  ✋ provision-claude-settings: could not back up $_f — refusing to write it." >&2
      _rc=2
      continue
    fi
  fi

  CC_FILE="$_f" CC_BAK="$_bak" \
  CC_CONCURRENT="$CONCURRENT_VALUE" CC_PER_SESSION="$PER_SESSION_VALUE" \
  python3 <<'PYEOF'
import json, os, sys

path   = os.environ["CC_FILE"]
bak    = os.environ.get("CC_BAK") or ""
want   = {
    "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS":  os.environ["CC_CONCURRENT"],
    "CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION": os.environ["CC_PER_SESSION"],
}

if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        # Pre-existing invalid JSON is NOT ours to repair. Leave it alone and
        # report it -- silently rewriting a file we could not parse would
        # destroy whatever the client had.
        print("  ✗ %s is not valid JSON (%s) — left untouched." % (path, exc))
        sys.exit(3)
else:
    data = {}

if not isinstance(data, dict):
    print("  ✗ %s does not contain a JSON object — left untouched." % path)
    sys.exit(3)

env = data.get("env")
if env is None:
    env = {}
    data["env"] = env
if not isinstance(env, dict):
    print("  ✗ %s has a non-object \"env\" — left untouched." % path)
    sys.exit(3)

changes = []
for k, v in want.items():
    old = env.get(k)
    if old != v:
        changes.append("%s: %s -> %s" % (k, "unset" if old is None else old, v))
        env[k] = v

if not changes:
    print("  = %s already correct (%s / %s)" % (path, want["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"], want["CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION"]))
    sys.exit(0)

tmp = path + ".tmp-concurrency"
try:
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    # Re-read what we actually wrote before it replaces anything.
    with open(tmp, encoding="utf-8") as fh:
        json.load(fh)
    os.replace(tmp, path)
except Exception as exc:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    print("  ✗ write failed for %s (%s)" % (path, exc))
    sys.exit(3)

for c in changes:
    print("  ✓ %s  %s" % (path, c))
if bak:
    print("    backup: %s" % bak)
sys.exit(10)   # 10 = changed (distinct from 0 = already correct)
PYEOF

  _prc=$?
  if [ "$_prc" = "10" ]; then
    _changed=$((_changed + 1))
  elif [ "$_prc" != "0" ]; then
    # Restore on any failure so the box is never left half-written.
    if [ -n "$_bak" ] && [ -f "$_bak" ]; then
      cp -p "$_bak" "$_f" 2>/dev/null && echo "    restored from backup after failure."
    fi
    _rc=2
  fi
done

if [ "$_seen" = "0" ]; then
  echo "  = provision-claude-settings: no Claude Code launcher installed on this box (checked PATH + npm-global/local/homebrew/usr) — these settings are not applicable here. Nothing written."
fi

if [ "$_rc" = "0" ]; then
  echo "  ✅ Claude subagent concurrency: ${_changed} file(s) changed, ${_seen} launcher profile(s) provisioned, ${_skipped} skipped (no launcher)."
else
  echo "  ⚠️  Claude subagent concurrency provisioning had failures — see above." >&2
fi
exit "$_rc"
