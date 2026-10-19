#!/usr/bin/env bash
# ghl-mcp-assert-runtime.sh — v22.0.0 (W07 retirement)
#
# THE COMMUNITY MCP IS RETIRED. This gate's job is no longer "prove the
# installed service matches the pin"; its job is to prove the community MCP is
# GONE, and — when something is still there — to name the exact identity that
# refuses to die. A box that never had it is not a failure. A box that had it
# and now has none of it is a PASS.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE SELF-CONTRADICTION THIS REPLACES (recorded in the live ledger)
#
# The old gate FAILED on absence at both supervisor branches — the mac branch
# when the plist was missing, the pm2/systemd branch when no supervisor was
# alive — while check 10 PASSED only when the service was ABSENT from
# mcp.servers. On a retired box the two halves contradicted each other, so
# "retired" and "broken" were indistinguishable. That is fixed here:
# ABSENT = PASS on every branch.
#
# ─────────────────────────────────────────────────────────────────────────────
# EXIT CODES (the four states this gate distinguishes)
#
#   0  RETIRED_OK       every community surface is provably absent and, when a
#                       retirement receipt exists, it says VERIFIED_OFF with a
#                       verifiable archive. Absence is a PASS, not a skip.
#   1  STILL_RUNNING    at least one matched identity was FOUND. The verdict and
#                       the FAIL lines name it exactly: launchd label, pm2 app,
#                       systemd unit, process pid, listener address, probe
#                       schedule, or mcp.servers registration.
#   2  NOT_APPLICABLE   the documented SKIP: this box has no history of a
#                       community MCP at all (a fresh install now omits it).
#                       Callers MUST treat 2 as a skip, never as a failure.
#   3  MISCONFIGURED    nothing is running, but the retirement state cannot be
#                       verified: residual inert artifacts (a leftover install
#                       dir, a `.plist.bak` that could be restored, an archive
#                       with no receipt), a MIGRATION_FAILED receipt, an
#                       unreadable/malformed receipt, a missing shared path
#                       library, or an unreadable registration config.
#
# PRECEDENCE: a found identity always wins (1). MISCONFIGURED (3) is only
# reported when nothing is left to name as a live/resurrection surface.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT IT INVENTORIES (the ordered-transaction inventory, in the same order)
#
#   1  install dir <root>/mcp-servers/ghl-community-mcp (and legacy locations)
#   2  pin file config/ghl-mcp-pin.env
#   3  supervisor actually present:
#        mac        : ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist + launchd
#        pm2        : app `ghl-community-mcp` under the derived PM2_HOME
#        systemd    : /etc/systemd/system/ghl-mcp.service + is-enabled/is-active
#        fallback B : <install dir>/.ghl-mcp-supervise.sh + setsid loop
#        none
#   4  registration in openclaw.json mcp.servers
#   5  the 15-minute probe: launchd plist, OS crontab, or OpenClaw cron store
#   6  live processes and LISTEN sockets on the configured port
#   7  the retirement receipt <root>/state/ghl-mcp-retirement.json
#
# ─────────────────────────────────────────────────────────────────────────────
# THE RECEIPT (written by the retirement transaction; this gate only reads it)
#
#   <root>/.retired/ghl-mcp-retirement.json       final_state VERIFIED_OFF
#   <root>/.retired/ghl-mcp-migration-failed.json final_state MIGRATION_FAILED
#
# Schema ghl-mcp-retirement-receipt/v1 (written by scripts/ghl-mcp-autostart.sh
# --retire). Only the fields this gate reads are shown:
#
#   {
#     "schema": "ghl-mcp-retirement-receipt/v1",
#     "final_state": "VERIFIED_OFF" | "MIGRATION_FAILED",
#     "stage": "complete" | "<failed stage>",
#     "reason": "...", "timestamp_utc": "...",
#     "box": {"platform": "...", "cohort": "..."},
#     "release": {"from": "...", "to": "...", "commit": "..."},
#     "old_service": {"kind": "...", "identity": "...", "install_dir": "..."},
#     "archive": {"path": "...", "manifest_sha256": "<sha256 of manifest.sha256>"},
#     "migrated_callers": [...], "disabled_hooks": [...],
#     "stop_result": [...],
#     "verification": {"ok": [...], "live": [...], "unknown": [...]},
#     "remediation": "..."
#   }
#
# A VERIFIED_OFF receipt is only accepted when its archive exists, is NOT inside
# any active install search path, and (when a manifest hash is recorded) the
# archive's manifest.sha256 hashes to it. An archive must never be scannable as
# a live install and must never auto-restore.
#
# GHL_MCP_RETIRED
# This file is the retirement VERIFIER. It never starts, builds, clones,
# registers, schedules or supervises the community MCP. Every supervisor call
# here is read-only (`launchctl print`, `pm2 describe/jlist`,
# `systemctl is-enabled/is-active`, `crontab -l`).
#
# ─────────────────────────────────────────────────────────────────────────────
# SECRET HYGIENE — load-bearing, do not "simplify"
# `pm2 jlist` DUMPS the full process env, which on a live box includes the GHL
# Private Integration Token. This script therefore NEVER echoes raw pm2/plist
# output. It extracts individual named keys and prints only those, and the ones
# it prints are non-secret by construction (profile, ports, log dir, script
# path, status). Never add a branch that prints the captured blob on failure.
# The receipt is asserted to be secret-free by the retirement transaction; this
# gate never prints archive contents, only paths and hashes.
#
# USAGE
#   ghl-mcp-assert-runtime.sh            # human-readable report
#   ghl-mcp-assert-runtime.sh --quiet    # exit code only (FAIL lines still shown)
#
# TEST/OVERRIDE HOOKS (real boxes set none of these)
#   GHL_MCP_PLATFORM_OVERRIDE, GHL_MCP_DIR, GHL_MCP_LOG_DIR_OVERRIDE,
#   GHL_MCP_DATA_ROOT, GHL_MCP_UNAME_S   (see scripts/lib/ghl-mcp-paths.sh)
#   GHL_MCP_OC_JSON, GHL_MCP_PLIST, GHL_MCP_PROBE_PLIST, GHL_MCP_SYSTEMD_UNIT
#   GHL_MCP_RETIREMENT_RECEIPT       default <root>/.retired/ghl-mcp-retirement.json
#   GHL_MCP_RETIREMENT_FAIL_RECEIPT  default <root>/.retired/ghl-mcp-migration-failed.json
#   GHL_MCP_ARCHIVE_ROOT             default <root>/.retired (archive-* subdirs)
#   GHL_MCP_PROC_NET_TCP, GHL_MCP_PROC_NET_TCP6 (check 13, see below)

set -u

QUIET=0
for _arg in "$@"; do
  [ "$_arg" = "--quiet" ] && QUIET=1
done

EXIT_RETIRED_OK=0
EXIT_STILL_RUNNING=1
EXIT_NOT_APPLICABLE=2
EXIT_MISCONFIGURED=3

FATAL_FAILURES=0
WARNINGS=0
CHECKS=0

# Classifiers. These are STRINGS, not bash arrays: macOS /bin/bash is 3.2 and
# `"${arr[@]}"` on an empty array is an unbound-variable abort under `set -u`.
HAS_IDENTITY=0
HAS_RESIDUAL=0
HAS_MISCONFIG=0
IDENTITIES=""
RESIDUALS=""
MISCONFIGS=""

_pass() { CHECKS=$((CHECKS+1)); [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] PASS  %s\n' "$*"; return 0; }
_fail() { CHECKS=$((CHECKS+1)); FATAL_FAILURES=$((FATAL_FAILURES+1))
          printf '[ghl-mcp-runtime] FAIL  %s\n' "$*" >&2; return 0; }
_warn() { CHECKS=$((CHECKS+1)); WARNINGS=$((WARNINGS+1))
          [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] WARN  %s\n' "$*"; return 0; }
_info() { [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] INFO  %s\n' "$*"; return 0; }

# _identity <surface>: a live or self-resurrecting community surface. ALWAYS a
# failure; always printed (never suppressed by --quiet) because this line is
# the exact evidence the operator needs. The surface is named verbatim.
_identity() {
  CHECKS=$((CHECKS+1)); HAS_IDENTITY=1
  IDENTITIES="${IDENTITIES}${IDENTITIES:+; }$1"
  printf '[ghl-mcp-runtime] FAIL  STILL_RUNNING  %s\n' "$1" >&2
  return 0
}
# _residual <surface>: inert leftover that could be restored or re-supervised.
# Not currently running, so the box is MISCONFIGURED rather than STILL_RUNNING.
_residual() {
  CHECKS=$((CHECKS+1)); HAS_RESIDUAL=1
  RESIDUALS="${RESIDUALS}${RESIDUALS:+; }$1"
  printf '[ghl-mcp-runtime] FAIL  RESIDUAL  %s\n' "$1" >&2
  return 0
}
# _misconfigured <reason>: the retirement state cannot be verified.
_misconfigured() {
  CHECKS=$((CHECKS+1)); HAS_MISCONFIG=1
  MISCONFIGS="${MISCONFIGS}${MISCONFIGS:+; }$1"
  printf '[ghl-mcp-runtime] FAIL  MISCONFIGURED  %s\n' "$1" >&2
  return 0
}

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Platform + canonical paths: THE SAME DERIVATION, not a copy of it ────────
_GHL_PATHS_LIB=""
for _c in "${GHL_MCP_PATHS_LIB:-}" \
          "$SELF_DIR/lib/ghl-mcp-paths.sh" \
          "$HOME/.openclaw/scripts/lib/ghl-mcp-paths.sh" \
          "$HOME/.openclaw/skills/scripts/lib/ghl-mcp-paths.sh" \
          "$HOME/.openclaw/onboarding/scripts/lib/ghl-mcp-paths.sh" \
          "/data/.openclaw/scripts/lib/ghl-mcp-paths.sh" \
          "/data/.openclaw/skills/scripts/lib/ghl-mcp-paths.sh" \
          "/data/.openclaw/onboarding/scripts/lib/ghl-mcp-paths.sh"; do
  [ -n "$_c" ] && [ -f "$_c" ] && { _GHL_PATHS_LIB="$_c"; break; }
done
if [ -z "$_GHL_PATHS_LIB" ]; then
  _misconfigured "scripts/lib/ghl-mcp-paths.sh is not on this box, so the Tier 2 install path and the platform CANNOT be derived. This gate refuses to guess them rather than report a confident verdict about a directory it invented. Searched: $SELF_DIR/lib, \$HOME/.openclaw/{scripts,skills/scripts,onboarding/scripts}/lib, /data/.openclaw/{scripts,skills/scripts,onboarding/scripts}/lib. Re-run update-skills.sh or install.sh; both deliver the whole scripts/ tree recursively."
  printf '[ghl-mcp-runtime] VERDICT: MISCONFIGURED — %s\n' "$MISCONFIGS" >&2
  exit "$EXIT_MISCONFIGURED"
fi
# shellcheck disable=SC1090
. "$_GHL_PATHS_LIB"
ghl_mcp_resolve_paths
PLATFORM="$GHL_MCP_RESOLVED_PLATFORM"
OC_ROOT="$GHL_MCP_RESOLVED_ROOT"
MCP_DIR="$GHL_MCP_RESOLVED_DIR"
LOG_DIR="$GHL_MCP_RESOLVED_LOG_DIR"
# PM2_HOME IS PART OF THE ADDRESS OF THE APP. Export ONLY when a candidate home
# actually exists: `pm2 describe` under a non-existent PM2_HOME SPAWNS a pm2
# daemon, and a read-only gate must never do that.
_GHL_PM2_HOME="$(ghl_mcp_pm2_home_existing "$OC_ROOT")"
[ -n "$_GHL_PM2_HOME" ] && export PM2_HOME="$_GHL_PM2_HOME"
OC_JSON="${GHL_MCP_OC_JSON:-$OC_ROOT/openclaw.json}"
PLIST="${GHL_MCP_PLIST:-$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist}"
PROBE_PLIST="${GHL_MCP_PROBE_PLIST:-$HOME/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist}"
SYSTEMD_UNIT="${GHL_MCP_SYSTEMD_UNIT:-/etc/systemd/system/ghl-mcp.service}"
# The producer is scripts/ghl-mcp-autostart.sh --retire. These are ITS paths;
# do not invent a second receipt location.
RETIRE_DIR="$OC_ROOT/.retired"
RECEIPT="${GHL_MCP_RETIREMENT_RECEIPT:-$RETIRE_DIR/ghl-mcp-retirement.json}"
RECEIPT_FAIL="${GHL_MCP_RETIREMENT_FAIL_RECEIPT:-$RETIRE_DIR/ghl-mcp-migration-failed.json}"
ARCHIVE_ROOT="${GHL_MCP_ARCHIVE_ROOT:-$RETIRE_DIR}"
LAUNCHD_LABEL="com.clawd.ghl-mcp"
PROBE_LABEL="com.clawd.ghl-mcp-probe"
PM2_APP="ghl-community-mcp"
SYSTEMD_NAME="ghl-mcp.service"
# Bind-determination sources (check 13). Overridable ONLY so the "no method
# available -> FATAL undeterminable" branch is reachable in CI; see the long
# note at check 13. Real boxes never set these.
_PROC_NET_TCP="${GHL_MCP_PROC_NET_TCP:-/proc/net/tcp}"
_PROC_NET_TCP6="${GHL_MCP_PROC_NET_TCP6:-/proc/net/tcp6}"
PM2_ECOSYSTEM="$MCP_DIR/ecosystem.config.js"
BUILD_STAMP="$MCP_DIR/.ghl-mcp-build.json"
LAUNCHER_NAME=".ghl-mcp-launch.sh"
SUPERVISE_NAME=".ghl-mcp-supervise.sh"

# ── The pin is the expectation, when there is still a service to compare. ────
_PIN_FILE=""
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  [ -f "$_c" ] && { _PIN_FILE="$_c"; break; }
done

_bind_addrs_for_port() {
  local _p="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$_p" -sTCP:LISTEN 2>/dev/null | tail -n +2 | awk '{print $9}'
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH 2>/dev/null | awk -v p=":$_p" '$4 ~ p"$" {print $4}'
    return 0
  fi
  if { [ -r "$_PROC_NET_TCP" ] || [ -r "$_PROC_NET_TCP6" ]; } \
     && command -v python3 >/dev/null 2>&1; then
    PORT_DEC="$_p" PROC_TCP="$_PROC_NET_TCP" PROC_TCP6="$_PROC_NET_TCP6" python3 - <<'PYEOF' 2>/dev/null
import os, socket, struct
port = int(os.environ["PORT_DEC"])
def emit(path, v6):
    try:
        lines = open(path).read().splitlines()[1:]
    except Exception:
        return
    for ln in lines:
        f = ln.split()
        if len(f) < 4 or f[3] != "0A":
            continue
        hexaddr, hexport = f[1].split(":")
        if int(hexport, 16) != port:
            continue
        if v6:
            raw = bytes.fromhex(hexaddr)
            raw = b"".join(struct.pack("<I", struct.unpack(">I", raw[i:i+4])[0])
                           for i in range(0, 16, 4))
            ip = socket.inet_ntop(socket.AF_INET6, raw)
        else:
            ip = socket.inet_ntop(socket.AF_INET, struct.pack("<I", int(hexaddr, 16)))
        print("%s:%d" % (ip, port))
emit(os.environ.get("PROC_TCP", "/proc/net/tcp"), False)
emit(os.environ.get("PROC_TCP6", "/proc/net/tcp6"), True)
PYEOF
    return $?
  fi
  return 1
}

_receipt_field() {  # _receipt_field <receipt-file> <key> — dotted path, strings/lists
  local file="$1" key="$2"
  if command -v python3 >/dev/null 2>&1; then
    RECEIPT="$file" KEY="$key" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:
    cur = json.load(open(os.environ["RECEIPT"]))
except Exception:
    raise SystemExit(0)
for part in os.environ["KEY"].split("."):
    cur = cur.get(part, "") if isinstance(cur, dict) else ""
v = cur
if isinstance(v, (dict, list)):
    print(json.dumps(v, separators=(",", ":")))
elif v is None:
    print("")
else:
    print(v)
PYEOF
  else
    key="${key##*.}"
    sed -n 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$file" 2>/dev/null | head -1
  fi
}

_receipt_alias() {  # _receipt_alias <file> <preferred> <fallback>
  local v
  v="$(_receipt_field "$1" "$2")"
  [ -n "$v" ] || v="$(_receipt_field "$1" "$3")"
  printf '%s' "$v"
}

_sha256() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
  fi
}

# Early read of the terminal state. A VERIFIED_OFF receipt changes how the
# leftover tree is judged: it is inert archive material, not a live install.
_OFF_RECEIPT=0
if [ -f "$RECEIPT" ] && command -v python3 >/dev/null 2>&1; then
  [ "$(_receipt_field "$RECEIPT" final_state)" = "VERIFIED_OFF" ] && _OFF_RECEIPT=1
fi

# ═════════════════════════════════════════════════════════════════════════════
# INVENTORY — read-only. Every probe here answers "is this surface present?"
# A present surface is recorded exactly once, with its identity.
# ═════════════════════════════════════════════════════════════════════════════

_HAVE_MCP_DIR=0; [ -d "$MCP_DIR" ] && _HAVE_MCP_DIR=1
_HAVE_MAC_SVC=0; [ -f "$PLIST" ] && _HAVE_MAC_SVC=1
_HAVE_PLIST_BAK=0; PLIST_BAKS=""
for _b in "$PLIST".bak*; do
  [ -e "$_b" ] && { _HAVE_PLIST_BAK=1; PLIST_BAKS="${PLIST_BAKS}${PLIST_BAKS:+, }$_b"; }
done
_HAVE_PROBE_PLIST=0; [ -f "$PROBE_PLIST" ] && _HAVE_PROBE_PLIST=1
_HAVE_PROBE_BAK=0; PROBE_BAKS=""
for _b in "$PROBE_PLIST".bak*; do
  [ -e "$_b" ] && { _HAVE_PROBE_BAK=1; PROBE_BAKS="${PROBE_BAKS}${PROBE_BAKS:+, }$_b"; }
done
_HAVE_SYSTEMD=0; [ -f "$SYSTEMD_UNIT" ] && _HAVE_SYSTEMD=1
_SYSTEMD_ENABLED=0; _SYSTEMD_ACTIVE=0
if [ "$_HAVE_SYSTEMD" = "1" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl is-enabled "$SYSTEMD_NAME" >/dev/null 2>&1 && _SYSTEMD_ENABLED=1
  systemctl is-active "$SYSTEMD_NAME" >/dev/null 2>&1 && _SYSTEMD_ACTIVE=1
fi
_HAVE_ECO=0; [ -f "$PM2_ECOSYSTEM" ] && _HAVE_ECO=1
_HAVE_SUPERVISE_SCRIPT=0; [ -f "$MCP_DIR/$SUPERVISE_NAME" ] && _HAVE_SUPERVISE_SCRIPT=1

# ── pm2 discovery. ONE process list per PM2_HOME, so the alternate-home sweep
# stays: a gate that asks the wrong home reports "app not found" about an app
# that is online.
_HAVE_PM2=0
if command -v pm2 >/dev/null 2>&1; then
  if pm2 describe "$PM2_APP" >/dev/null 2>&1; then _HAVE_PM2=1
  else
    for _h in $(ps -eo args 2>/dev/null | sed -n 's/.*God Daemon (\(.*\))$/\1/p') \
              /root/.pm2 /home/*/.pm2 /data/.pm2 "${OC_ROOT:-}/.pm2"; do
      [ -r "$_h/pm2.pid" ] || continue
      [ "$_h" = "${PM2_HOME:-}" ] && continue
      if PM2_HOME="$_h" pm2 describe "$PM2_APP" >/dev/null 2>&1; then
        export PM2_HOME="$_h"; _HAVE_PM2=1; _info "pm2 app found under PM2_HOME=$_h (not this user's default home)"; break
      fi
    done
  fi
fi

# ── launchd loaded state. `launchctl print` first (authoritative); `launchctl
# list` is a fallback, and matched by the LABEL COLUMN so the probe label can
# never satisfy it.
_LAUNCHD_LOADED=0
if command -v launchctl >/dev/null 2>&1; then
  if launchctl print "gui/$(id -u)/$LAUNCHD_LABEL" >/dev/null 2>&1; then
    _LAUNCHD_LOADED=1
  elif launchctl list 2>/dev/null | awk -v l="$LAUNCHD_LABEL" '$3==l{found=1} END{exit !found}'; then
    _LAUNCHD_LOADED=1
  fi
fi
_PROBE_LOADED=0
if command -v launchctl >/dev/null 2>&1; then
  if launchctl print "gui/$(id -u)/$PROBE_LABEL" >/dev/null 2>&1; then
    _PROBE_LOADED=1
  elif launchctl list 2>/dev/null | awk -v l="$PROBE_LABEL" '$3==l{found=1} END{exit !found}'; then
    _PROBE_LOADED=1
  fi
fi

# ── Live processes. Matched on the resolved install dir, the crash-only
# launcher, or the fallback supervise script — never a broad `pkill`-style
# pattern. The scanner must never match ITSELF: $$ and $PPID are excluded,
# any ps line carrying this script's own name is excluded (the script and its
# subshells), and this pipeline's own awk helper is excluded by its argv shape
# ("awk -v d") — that helper's command line literally contains $LAUNCHER_NAME
# because it is passed via -v l=, which used to make a retired box report
# itself STILL_RUNNING. Detection of a real service is untouched: it matches
# because its command line really runs the launcher/supervise script or lives
# under $MCP_DIR, neither of which ever appears in a scanner helper line.
_PROC_LINES=""
_SELF_NAME="$(basename "${BASH_SOURCE[0]:-$0}")"
if command -v ps >/dev/null 2>&1; then
  _PROC_LINES="$(ps -eo pid=,args= 2>/dev/null | awk -v d="$MCP_DIR" -v l="$LAUNCHER_NAME" -v s="$SUPERVISE_NAME" -v self="$$" -v pp="$PPID" -v me="$_SELF_NAME" '
    { pid=$1; line=$0; sub(/^[[:space:]]*[0-9]+[[:space:]]+/, "", line)
      if (pid==self || pid==pp) next
      if (index(line, "awk -v d") > 0) next
      if (me != "" && index(line, me) > 0) next
      if ((d != "" && index(line, d "/") > 0) || index(line, l) > 0 || index(line, s) > 0)
        print pid " " line }')"
fi

# ── Registration in mcp.servers: a persistence surface even though it is not a
# process. Read early because it is part of the inventory.
_REGISTERED="unknown"
if [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
  _REGISTERED="$(OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    servers = (cfg.get("mcp", {}) or {}).get("servers", {}) or {}
    print("yes" if "ghl-community-mcp" in servers else "no")
except Exception:
    print("unknown")
PYEOF
)"
fi

# ── Probe schedule: three schedulers, because autostart uses three.
_CRON_PROBE=""
if command -v crontab >/dev/null 2>&1; then
  _CRON="$(crontab -l 2>/dev/null || true)"
  # A quoted command path is the only correct cron spelling when the path
  # contains spaces (the operator's own `GHL updates` tree does). Try the
  # quoted form first, then the historical unquoted one.
  _CRON_PROBE="$(printf '%s\n' "$_CRON" | sed -n 's|.*"\([^"]*ghl-mcp-probe\.sh\)".*|\1|p' | head -1)"
  [ -n "$_CRON_PROBE" ] || _CRON_PROBE="$(printf '%s\n' "$_CRON" | sed -n 's|.*[[:space:]]\(/[^[:space:]]*ghl-mcp-probe\.sh\).*|\1|p' | head -1)"
fi
_PROBE_IN_STORE=0
if command -v openclaw >/dev/null 2>&1 \
   && openclaw cron list --json 2>/dev/null | grep -q '"name": *"ghl-mcp-probe"'; then
  _PROBE_IN_STORE=1
fi

_HAVE_RECEIPT=0; [ -f "$RECEIPT" ] && _HAVE_RECEIPT=1
_HAVE_FAIL_RECEIPT=0; [ -f "$RECEIPT_FAIL" ] && _HAVE_FAIL_RECEIPT=1
_HAVE_ARCHIVE=0
for _a in "$ARCHIVE_ROOT"/archive-*; do
  [ -d "$_a" ] && [ -n "$(ls -A "$_a" 2>/dev/null)" ] && { _HAVE_ARCHIVE=1; break; }
done
if [ "$_HAVE_ARCHIVE" = "0" ]; then
  case "$ARCHIVE_ROOT" in
    */.retired) : ;;   # receipts live here; only archive-* subdirs count
    *) [ -d "$ARCHIVE_ROOT" ] && [ -n "$(ls -A "$ARCHIVE_ROOT" 2>/dev/null)" ] && _HAVE_ARCHIVE=1 ;;
  esac
fi

# ── HISTORY: has this box ever known about the community MCP? If not, the
# documented rc=2 SKIP is preserved (a fresh install now omits it entirely).
_HISTORY=0
[ "$_HAVE_MCP_DIR" = "1" ] && _HISTORY=1
[ "$_HAVE_MAC_SVC" = "1" ] && _HISTORY=1
[ "$_LAUNCHD_LOADED" = "1" ] && _HISTORY=1
[ "$_PROBE_LOADED" = "1" ] && _HISTORY=1
[ "$_HAVE_PLIST_BAK" = "1" ] && _HISTORY=1
[ "$_HAVE_PM2" = "1" ] && _HISTORY=1
[ "$_HAVE_ECO" = "1" ] && _HISTORY=1
[ "$_HAVE_SYSTEMD" = "1" ] && _HISTORY=1
[ "$_HAVE_SUPERVISE_SCRIPT" = "1" ] && _HISTORY=1
[ -n "$_PROC_LINES" ] && _HISTORY=1
[ "$_HAVE_PROBE_PLIST" = "1" ] && _HISTORY=1
[ "$_HAVE_PROBE_BAK" = "1" ] && _HISTORY=1
[ -n "$_CRON_PROBE" ] && _HISTORY=1
[ "$_PROBE_IN_STORE" = "1" ] && _HISTORY=1
[ "$_REGISTERED" = "yes" ] && _HISTORY=1
[ "$_HAVE_RECEIPT" = "1" ] && _HISTORY=1
[ "$_HAVE_FAIL_RECEIPT" = "1" ] && _HISTORY=1
[ "$_HAVE_ARCHIVE" = "1" ] && _HISTORY=1

# A listener ALONE can be a community service that was started by hand after
# its files were removed. Probe the configured port (from the pin, if one is
# delivered) before declaring NOT_APPLICABLE. A box with nothing on that port
# still exits 2, so this cannot turn a fresh install into a failure.
if [ "$_HISTORY" = "0" ] && [ -n "$_PIN_FILE" ]; then
  _EARLY_PORT="$(sed -n 's/^GHL_MCP_PORT=//p' "$_PIN_FILE" 2>/dev/null | tr -d '"' | head -1)"
  [ -n "$_EARLY_PORT" ] || _EARLY_PORT=8765
  if _EARLY_ADDRS="$(_bind_addrs_for_port "$_EARLY_PORT")" && [ -n "$_EARLY_ADDRS" ]; then
    _HISTORY=1
  fi
fi

if [ "$_HISTORY" = "0" ]; then
  _info "no GHL community MCP install dir, supervisor definition, probe schedule, registration, archive or receipt on this box — the community MCP is not part of this install. Nothing to assert."
  [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] VERDICT: NOT_APPLICABLE — no community MCP history on this box (fresh installs omit it).\n'
  exit "$EXIT_NOT_APPLICABLE"
fi

# ── Record every found identity. The exact identity is the evidence.
if [ "$_HAVE_MAC_SVC" = "1" ]; then
  _L="launchd:$LAUNCHD_LABEL at $PLIST (plist present"
  [ "$_LAUNCHD_LOADED" = "1" ] && _L="$_L, LOADED in launchd" || _L="$_L, not currently loaded — RunAtLoad resurrects it at login"
  _identity "$_L)"
elif [ "$_LAUNCHD_LOADED" = "1" ]; then
  _identity "launchd:$LAUNCHD_LABEL (LOADED in launchd with no plist on disk — bootout/disable did not take effect)"
fi
if [ "$_HAVE_PLIST_BAK" = "1" ]; then
  _residual "launchd backups that must never be auto-restored: $PLIST_BAKS"
fi
if [ "$_HAVE_PM2" = "1" ]; then
  _identity "pm2:$PM2_APP (registered under PM2_HOME=${PM2_HOME:-default} — pm2 resurrect brings it back)"
fi
if [ "$_HAVE_SYSTEMD" = "1" ]; then
  _S="systemd:$SYSTEMD_NAME at $SYSTEMD_UNIT (unit file present"
  [ "$_SYSTEMD_ENABLED" = "1" ] && _S="$_S, ENABLED" || _S="$_S, not enabled"
  [ "$_SYSTEMD_ACTIVE" = "1" ] && _S="$_S, ACTIVE" || _S="$_S, inactive"
  _identity "$_S)"
fi
if [ -n "$_PROC_LINES" ]; then
  while IFS= read -r _pl; do
    [ -n "$_pl" ] && _identity "process:$_pl"
  done <<EOF
$_PROC_LINES
EOF
fi
if [ "$_HAVE_PROBE_PLIST" = "1" ]; then
  _P="probe:launchd:$PROBE_LABEL at $PROBE_PLIST"
  [ "$_PROBE_LOADED" = "1" ] && _P="$_P (loaded)"
  _identity "$_P"
elif [ "$_PROBE_LOADED" = "1" ]; then
  _identity "probe:launchd:$PROBE_LABEL (LOADED with no plist on disk — the probe can still heal/restart)"
fi
if [ "$_HAVE_PROBE_BAK" = "1" ]; then
  _residual "probe plist backups that must never be auto-restored: $PROBE_BAKS"
fi
if [ -n "$_CRON_PROBE" ]; then
  _identity "probe:crontab:$_CRON_PROBE (15-minute heal schedule)"
fi
if [ "$_PROBE_IN_STORE" = "1" ]; then
  _identity "probe:openclaw-cron-store:ghl-mcp-probe (the gateway runs the heal probe)"
fi
if [ "$_REGISTERED" = "yes" ]; then
  _identity "registration:mcp.servers.$PM2_APP — remove with: openclaw mcp unset $PM2_APP (NOT 'mcp remove'); then RE-READ openclaw.json, the gateway rewrites it from memory"
fi
# The install tree, its ecosystem file and its fallback supervise script are
# classified AFTER the receipt is read: a VERIFIED_OFF retirement deliberately
# leaves the source tree in place as the source the archive was copied from,
# so those files are inert remnants of a completed transaction — not surfaces.
# Without a valid VERIFIED_OFF receipt they are residual state.

# ── The pin. Needed only to judge a service that IS still present.
if [ -z "$_PIN_FILE" ]; then
  if [ "$HAS_IDENTITY" = "1" ] || [ "$HAS_RESIDUAL" = "1" ]; then
    _misconfigured "config/ghl-mcp-pin.env is not on this box, so there is NO expectation to compare a surviving service against. Re-run update-skills.sh / install.sh (they deliver config/ to \$OC_CONFIG/config/)."
  else
    _info "no pin file on this box — nothing to compare (no service present)."
  fi
  EXPECT_COMMIT=""; EXPECT_PROFILE=""; EXPECT_PORT="8765"; EXPECT_MIN="1"; EXPECT_MAX="200"; EXPECT_LOG_MAX="10485760"
else
  # shellcheck disable=SC1090
  . "$_PIN_FILE"
  EXPECT_COMMIT="${GHL_MCP_VETTED_COMMIT:-}"
  EXPECT_PROFILE="${GHL_MCP_TOOL_PROFILE:-}"
  EXPECT_PORT="${GHL_MCP_PORT:-8765}"
  EXPECT_MIN="${GHL_MCP_EXPECT_MIN_TOOLS:-1}"
  EXPECT_MAX="${GHL_MCP_EXPECT_MAX_TOOLS:-200}"
  EXPECT_LOG_MAX="${GHL_MCP_LOG_MAX_BYTES:-10485760}"
  _info "platform=$PLATFORM  pin=$_PIN_FILE  expect: commit=${EXPECT_COMMIT:0:12} profile=$EXPECT_PROFILE port=$EXPECT_PORT tools=${EXPECT_MIN}..${EXPECT_MAX}"
fi

# ── plist helpers. Only NAMED keys are ever extracted — never the whole dict
# (secret hygiene, see the header). Both the same-line and next-line shapes are
# real on the fleet, so both are handled.
_plist_value() {  # _plist_value <plist> <key>  — string or integer, any nesting
  local f="$1" k="$2" v=""
  v="$(sed -n "s|.*<key>${k}</key>[[:space:]]*<string>\([^<]*\)</string>.*|\1|p" "$f" 2>/dev/null | head -1)"
  [ -n "$v" ] || v="$(sed -n "s|.*<key>${k}</key>[[:space:]]*<integer>\([^<]*\)</integer>.*|\1|p" "$f" 2>/dev/null | head -1)"
  [ -n "$v" ] || v="$(sed -n "\|<key>${k}</key>|{n;s|.*<string>\([^<]*\)</string>.*|\1|p;}" "$f" 2>/dev/null | head -1)"
  [ -n "$v" ] || v="$(sed -n "\|<key>${k}</key>|{n;s|.*<integer>\([^<]*\)</integer>.*|\1|p;}" "$f" 2>/dev/null | head -1)"
  if [ -z "$v" ] && [ -x /usr/libexec/PlistBuddy ]; then
    v="$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:${k}" "$f" 2>/dev/null || true)"
    [ -n "$v" ] || v="$(/usr/libexec/PlistBuddy -c "Print :${k}" "$f" 2>/dev/null || true)"
  fi
  printf '%s' "$v"
}
_plist_env() { _plist_value "$1" "$2"; }
_plist_top() { _plist_value "$1" "$2"; }

# ── The pm2 field filter (see the SECRET HYGIENE note). Reduces a raw pm2
# record to the non-secret fields this gate reads and emits nothing else.
_GHL_FILTER_PM2_RECORD='
import json, sys
ALLOWED = ("GHL_TOOL_PROFILE", "PORT", "MCP_SERVER_PORT", "GHL_MCP_LOG_DIR")
try:
    apps = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
for a in apps:
    if a.get("name") != "ghl-community-mcp":
        continue
    env = a.get("pm2_env") if isinstance(a.get("pm2_env"), dict) else {}
    print("__script__=%s" % (env.get("pm_exec_path") or a.get("pm_exec_path") or ""))
    print("__status__=%s" % (env.get("status") or ""))
    _sec = env.get("stop_exit_codes")
    if _sec is None or _sec == "":
        _sec_list = []
    elif isinstance(_sec, (list, tuple)):
        _sec_list = list(_sec)
    else:
        _sec_list = [_sec]
    print("__stop_exit_codes__=%s" % ",".join(str(x) for x in _sec_list))
    for k in ALLOWED:
        print("%s=%s" % (k, env.get(k) or ""))
    break
'

# ═════════════════════════════════════════════════════════════════════════════
# A. Mac / launchd: DARWIN ONLY. ABSENT = PASS: no plist means retired.
# ═════════════════════════════════════════════════════════════════════════════
if [ "$PLATFORM" = "mac" ]; then
  if [ "$_HAVE_MAC_SVC" = "0" ]; then
    _pass "no launchd service definition at $PLIST — the community MCP is not installed here (retired)"
  else
    _PLIST_RAW="$(cat "$PLIST" 2>/dev/null || true)"

    case "$_PLIST_RAW" in
      *"$LAUNCHER_NAME"*)
        _pass "launchd ProgramArguments run the crash-only launcher ($LAUNCHER_NAME)" ;;
      *"dist/main.js"*)
        _fail "launchd ProgramArguments launch 'node dist/main.js' DIRECTLY, bypassing $LAUNCHER_NAME — a rejected PIT will make main.js exit(1) on every launch and the supervisor will relaunch it forever (D3). Re-run scripts/ghl-mcp-autostart.sh." ;;
      *)
        _fail "launchd ProgramArguments reference neither $LAUNCHER_NAME nor dist/main.js — the installed plist is not the one this repo writes." ;;
    esac

    case "$_PLIST_RAW" in
      *"<key>KeepAlive</key>"*"<true/>"*)
        if printf '%s' "$_PLIST_RAW" | tr -d ' \t\n' | grep -q '<key>KeepAlive</key><true/>'; then
          _fail "launchd KeepAlive is the UNCONDITIONAL boolean <true/> — it restarts even a deliberate clean exit, which turns a bad/rotated PIT into an endless relaunch loop. The crash-only dict (SuccessfulExit=false / Crashed=true) is mandatory."
        elif printf '%s' "$_PLIST_RAW" | tr -d ' \t\n' | grep -q '<key>SuccessfulExit</key><false/>'; then
          _pass "launchd restart policy is CRASH-ONLY (KeepAlive dict, SuccessfulExit=false)"
        else
          _fail "launchd KeepAlive is present but is neither the crash-only dict nor a recognised form — observed plist does not contain <key>SuccessfulExit</key><false/>."
        fi ;;
      *)
        if printf '%s' "$_PLIST_RAW" | tr -d ' \t\n' | grep -q '<key>SuccessfulExit</key><false/>'; then
          _pass "launchd restart policy is CRASH-ONLY (KeepAlive dict, SuccessfulExit=false)"
        else
          _fail "launchd plist has no crash-only KeepAlive dict (SuccessfulExit=false)."
        fi ;;
    esac

    _TI="$(_plist_top "$PLIST" ThrottleInterval)"
    if [ -z "$_TI" ]; then
      _fail "launchd ThrottleInterval is absent — observed: <unset>; required: >= 300 (the canonical fleet shape). Without it launchd relaunches on its 10s default."
    elif [ "$_TI" -ge 300 ] 2>/dev/null; then
      _pass "launchd ThrottleInterval=$_TI (>= 300)"
    else
      _fail "launchd ThrottleInterval=$_TI — required >= 300. A low throttle is what turns a mis-detected crash into a hot relaunch loop."
    fi

    _P="$(_plist_env "$PLIST" GHL_TOOL_PROFILE)"
    if [ -z "$_P" ]; then
      _fail "launchd EnvironmentVariables has NO GHL_TOOL_PROFILE — observed: <unset>; expected: $EXPECT_PROFILE. Upstream's default is 'full' = the entire 858-tool catalogue."
    elif [ "$_P" = "$EXPECT_PROFILE" ]; then
      _pass "launchd GHL_TOOL_PROFILE=$_P matches the pin"
    else
      _fail "launchd GHL_TOOL_PROFILE=$_P but the pin says $EXPECT_PROFILE — the live service is serving a different tool surface than the fleet standard."
    fi
    for _k in PORT MCP_SERVER_PORT; do
      _V="$(_plist_env "$PLIST" "$_k")"
      if [ "$_V" = "$EXPECT_PORT" ]; then
        _pass "launchd $_k=$_V matches the pin"
      else
        _fail "launchd $_k='${_V:-<unset>}' but the pin says $EXPECT_PORT — main.js reads PORT before MCP_SERVER_PORT, so an unpinned pair binds a random port."
      fi
    done
    _LD="$(_plist_env "$PLIST" GHL_MCP_LOG_DIR)"
    if [ -n "$_LD" ]; then
      _pass "launchd GHL_MCP_LOG_DIR=$_LD (the launcher can rotate)"
    else
      _fail "launchd EnvironmentVariables has NO GHL_MCP_LOG_DIR — the launcher's copytruncate rotation is a no-op without it, which is how stderr.log reached 5.4 MB on the operator box."
    fi
  fi

  # Probe: ABSENT = PASS (retired). A present probe is already named as an
  # identity above; here we only judge its target, because a probe pointing at a
  # deleted script is a silently dead probe that still expects the service.
  if [ "$_HAVE_PROBE_PLIST" = "1" ]; then
    if [ "$_PROBE_LOADED" = "1" ]; then
      _warn "periodic liveness probe ($PROBE_LABEL) is LOADED — it is a resurrection surface and must be removed by retirement, not merely stopped."
    fi
    _PP="$(sed -n 's|.*<string>\(.*ghl-mcp-probe\.sh\)</string>.*|\1|p' "$PROBE_PLIST" 2>/dev/null | head -1)"
    if [ -n "$_PP" ] && [ ! -f "$_PP" ]; then
      _fail "the probe plist points at $_PP, which DOES NOT EXIST — a probe that cannot be found is a silently dead probe."
    fi
  else
    _pass "no periodic liveness probe installed ($PROBE_PLIST absent) — nothing can heal or restart a retired service"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# B. VPS and linux-home / pm2, else systemd, else the supervised relaunch loop.
# ABSENT = PASS: no supervisor at all means retired.
# ═════════════════════════════════════════════════════════════════════════════
if [ "$PLATFORM" = "vps" ] || [ "$PLATFORM" = "linux-home" ]; then
  if [ "$_HAVE_PM2" = "1" ]; then
    _PM2_SAFE=""
    if command -v python3 >/dev/null 2>&1; then
      _PM2_SAFE="$(pm2 jlist 2>/dev/null | python3 -c "$_GHL_FILTER_PM2_RECORD" 2>/dev/null || true)"
    fi
    _pm2_field() {  # read one already-filtered, already-non-secret field
      printf '%s\n' "$_PM2_SAFE" | sed -n "s|^$1=||p" | head -1
    }
    if ! command -v python3 >/dev/null 2>&1; then
      _warn "python3 not on PATH — cannot parse the live pm2 definition; falling back to the on-disk ecosystem.config.js, which is what pm2 WOULD load, not necessarily what it IS running."
    else
      _STATUS="$(_pm2_field __status__)"
      [ -n "$_STATUS" ] && _info "pm2 app $PM2_APP status=$_STATUS"
      _SCRIPT="$(_pm2_field __script__)"
      case "$_SCRIPT" in
        *"$LAUNCHER_NAME"*) _pass "pm2 runs the crash-only launcher ($_SCRIPT)" ;;
        *dist/main.js*)     _fail "pm2 runs 'node dist/main.js' directly ($_SCRIPT), bypassing $LAUNCHER_NAME — a rejected PIT becomes an endless relaunch loop (D3)." ;;
        "")                 _fail "pm2 app ghl-community-mcp has no readable script path — cannot confirm it runs the crash-only launcher." ;;
        *)                  _fail "pm2 runs '$_SCRIPT', which is neither $LAUNCHER_NAME nor dist/main.js — this is not the definition this repo writes." ;;
      esac
      _SEC="$(_pm2_field __stop_exit_codes__)"
      case ",$_SEC," in
        *,0,*) _pass "pm2 stop_exit_codes includes 0 (a clean exit is not restarted)" ;;
        *)     _fail "pm2 stop_exit_codes='${_SEC:-<unset>}' — 0 must be present or a deliberate clean exit (bad PIT) relaunches forever." ;;
      esac
      _P="$(_pm2_field GHL_TOOL_PROFILE)"
      if [ "$_P" = "$EXPECT_PROFILE" ]; then _pass "pm2 env GHL_TOOL_PROFILE=$_P matches the pin"
      else _fail "pm2 env GHL_TOOL_PROFILE='${_P:-<unset>}' but the pin says $EXPECT_PROFILE."; fi
      for _k in PORT MCP_SERVER_PORT; do
        _V="$(_pm2_field "$_k")"
        if [ "$_V" = "$EXPECT_PORT" ]; then _pass "pm2 env $_k=$_V matches the pin"
        else _fail "pm2 env $_k='${_V:-<unset>}' but the pin says $EXPECT_PORT."; fi
      done
      _LD="$(_pm2_field GHL_MCP_LOG_DIR)"
      if [ -n "$_LD" ]; then _pass "pm2 env GHL_MCP_LOG_DIR=$_LD (the launcher can rotate)"
      else _fail "pm2 env has no GHL_MCP_LOG_DIR — the launcher's rotation is a no-op without it."; fi
    fi
  fi

  if [ "$_HAVE_PM2" = "0" ] && [ "$_HAVE_SYSTEMD" = "1" ]; then
    _UNIT="$(cat "$SYSTEMD_UNIT" 2>/dev/null || true)"
    case "$_UNIT" in
      *"$LAUNCHER_NAME"*) _pass "systemd ExecStart runs the crash-only launcher" ;;
      *)                  _fail "systemd ExecStart does not run $LAUNCHER_NAME — a rejected PIT becomes a restart loop (D3)." ;;
    esac
    case "$_UNIT" in
      *"Restart=always"*)     _fail "systemd unit uses Restart=always — crash-only requires Restart=on-failure." ;;
      *"Restart=on-failure"*) _pass "systemd Restart=on-failure (crash-only)" ;;
      *)                      _fail "systemd unit declares no Restart policy — observed: <unset>; required: on-failure." ;;
    esac
    _P="$(printf '%s\n' "$_UNIT" | sed -n 's/^Environment=GHL_TOOL_PROFILE=//p' | head -1)"
    if [ "$_P" = "$EXPECT_PROFILE" ]; then _pass "systemd Environment GHL_TOOL_PROFILE=$_P matches the pin"
    else _fail "systemd Environment GHL_TOOL_PROFILE='${_P:-<unset>}' but the pin says $EXPECT_PROFILE."; fi
    for _k in PORT MCP_SERVER_PORT; do
      _V="$(printf '%s\n' "$_UNIT" | sed -n "s/^Environment=${_k}=//p" | head -1)"
      if [ "$_V" = "$EXPECT_PORT" ]; then _pass "systemd Environment $_k=$_V matches the pin"
      else _fail "systemd Environment $_k='${_V:-<unset>}' but the pin says $EXPECT_PORT."; fi
    done
    case "$_UNIT" in
      *GHL_MCP_LOG_DIR*) _pass "systemd Environment carries GHL_MCP_LOG_DIR" ;;
      *)                 _fail "systemd Environment has no GHL_MCP_LOG_DIR — rotation is a no-op without it." ;;
    esac
  fi

  if [ "$_HAVE_PM2" = "0" ] && [ "$_HAVE_SYSTEMD" = "0" ]; then
    # No pm2 and no systemd. If a fallback-B supervise loop is RUNNING the
    # process check above already named it as an identity; if only the script
    # is on disk it was named as a supervisor identity. ABSENT = PASS.
    if [ "$_HAVE_SUPERVISE_SCRIPT" = "0" ]; then
      _pass "no live pm2 app '$PM2_APP', no $SYSTEMD_UNIT, and no fallback-B supervise loop — the community service is not supervised (retired)"
    else
      _info "fallback-B supervisor definition present at $MCP_DIR/$SUPERVISE_NAME (no loop is running; its status is judged below against the retirement receipt)"
    fi
  fi

  # Probe: ABSENT = PASS. Present is an identity; here judge its target.
  if [ -n "$_CRON_PROBE" ]; then
    if [ ! -f "$_CRON_PROBE" ]; then
      _fail "the probe cron line points at $_CRON_PROBE, which DOES NOT EXIST. A stale path means a silently dead 15-minute probe."
    else
      _pass "periodic liveness probe cron target exists ($_CRON_PROBE)"
    fi
  elif [ "$_PROBE_IN_STORE" = "1" ]; then
    _pass "periodic liveness probe is registered in the OpenClaw cron store (this box has no crontab probe line)"
  else
    _pass "no ghl-mcp-probe.sh line in this box's crontab and no 'ghl-mcp-probe' entry in the OpenClaw cron store — no probe can heal or restart a retired service"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# C. Platform-independent: build stamp, live tool count, registration, logs, bind
# ═════════════════════════════════════════════════════════════════════════════

# 8. build stamp — only meaningful when an install dir still exists.
if [ "$_OFF_RECEIPT" = "1" ]; then
  _pass "the retirement receipt records VERIFIED_OFF — the leftover tree is inert archive material, so no build-stamp conformance is asserted"
elif [ "$_HAVE_MCP_DIR" = "0" ]; then
  _pass "no Tier 2 install dir at $MCP_DIR — nothing to build-check (retired)"
elif [ ! -f "$BUILD_STAMP" ]; then
  _fail "no build stamp at $BUILD_STAMP — this box has never run the pinned build path, so whatever is in dist/ is of unknown provenance."
else
  _BC="$(sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' "$BUILD_STAMP" 2>/dev/null | head -1)"
  if [ "$_BC" = "$EXPECT_COMMIT" ]; then
    _pass "build stamp commit=${_BC:0:12} matches the pin"
  else
    _fail "build stamp commit='${_BC:0:12}' but the pin says '${EXPECT_COMMIT:0:12}' — the running build is NOT the vetted commit."
  fi
fi

# 9. live tool count — only meaningful when some service definition exists.
_HAVE_SERVICE_ANY=0
[ "$_HAVE_MAC_SVC" = "1" ] && _HAVE_SERVICE_ANY=1
[ "$_HAVE_PM2" = "1" ] && _HAVE_SERVICE_ANY=1
[ "$_HAVE_SYSTEMD" = "1" ] && _HAVE_SERVICE_ANY=1
[ -n "$_PROC_LINES" ] && _HAVE_SERVICE_ANY=1
if [ "$_HAVE_SERVICE_ANY" = "0" ]; then
  _pass "no community service definition on this box — /health is not asserted (retired)"
elif command -v curl >/dev/null 2>&1; then
  _HEALTH="$(curl -fsS --max-time 5 "http://127.0.0.1:${EXPECT_PORT}/health" 2>/dev/null || true)"
  if [ -z "$_HEALTH" ]; then
    _warn "nothing answered http://127.0.0.1:${EXPECT_PORT}/health — the tool-count assertion could not run for the still-installed service."
  else
    case "$_HEALTH" in
      *0.5.3-local*|*cognee*|*Cognee*)
        _fail "port ${EXPECT_PORT} is answered by Cognee, not the GHL MCP — the wrong service owns the canonical port." ;;
      *)
        _TOOLS="$(printf '%s' "$_HEALTH" | sed -n 's/.*"tools":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
        if [ -z "$_TOOLS" ]; then
          _warn "/health answered but reported no tool count — cannot verify the profile took effect."
        elif [ "$_TOOLS" -ge "$EXPECT_MIN" ] 2>/dev/null && [ "$_TOOLS" -le "$EXPECT_MAX" ] 2>/dev/null; then
          _pass "live /health tools=$_TOOLS is inside the ${EXPECT_MIN}..${EXPECT_MAX} band for profile=$EXPECT_PROFILE"
        else
          _fail "live /health tools=$_TOOLS is OUTSIDE the ${EXPECT_MIN}..${EXPECT_MAX} band for profile=$EXPECT_PROFILE — GHL_TOOL_PROFILE is not taking effect on the running process (859 = the full 858-tool catalogue + 1)."
        fi ;;
    esac
  fi
else
  _warn "curl not on PATH — the live tool-count assertion could not run."
fi

# 10. Tier 2 must be ABSENT from mcp.servers. The identity (when present) was
# already recorded verbatim in the inventory; this branch adds the PASS and the
# undeterminable case.
case "$_REGISTERED" in
  no)  _pass "ghl-community-mcp is ABSENT from mcp.servers (Tier 2 stays on-demand curl — no per-init tool-catalogue tax)" ;;
  yes) : ;;  # recorded as an identity in the inventory, with the exact remediation
  *)   _misconfigured "could not read mcp.servers from $OC_JSON — the Tier 2 registration assertion did not run. A retirement receipt cannot be accepted while this is undetermined." ;;
esac

# 12. log size ceiling — a retired box may have no log dir at all.
_LIMIT=$(( EXPECT_LOG_MAX * 3 / 2 ))
if [ -d "$LOG_DIR" ]; then
  _OVER=0
  for _lf in "$LOG_DIR/stderr.log" "$LOG_DIR/stdout.log" \
             "$LOG_DIR/ghl-mcp.log" "$LOG_DIR/ghl-mcp.err.log" "$LOG_DIR/probe.log"; do
    [ -f "$_lf" ] || continue
    _SZ="$(wc -c < "$_lf" 2>/dev/null | tr -d ' ')"
    [ -n "$_SZ" ] || continue
    if [ "$_SZ" -gt "$_LIMIT" ] 2>/dev/null; then
      _fail "$_lf is ${_SZ} bytes, over the ${_LIMIT}-byte ceiling (GHL_MCP_LOG_MAX_BYTES * 1.5) — rotation is not happening on this box."
      _OVER=1
    fi
  done
  [ "$_OVER" = "0" ] && _pass "no MCP log exceeds the ${_LIMIT}-byte ceiling (rotation is working, or no logs remain)"
else
  _pass "$LOG_DIR does not exist — no MCP logs to bound (retired)"
fi

# ── 13. LOOPBACK BIND / LISTENER DETECTION ───────────────────────────────────
# The messages in this section are load-bearing for
# tests/unit/ghl-mcp-bind-determination.test.sh; do not reword them.
_BIND_ADDRS=""
_BIND_DETERMINED=1
if _BIND_ADDRS="$(_bind_addrs_for_port "$EXPECT_PORT")"; then
  _BIND_DETERMINED=0
fi

if [ "$_BIND_DETERMINED" != "0" ]; then
  _misconfigured "the bind address on :${EXPECT_PORT} is UNDETERMINABLE on this box — lsof, ss and /proc/net/tcp are all unavailable, so this check could not run. This is a FAILED check, NOT a pass. Install lsof or iproute2, or run this gate where /proc is readable."
elif [ -z "$_BIND_ADDRS" ]; then
  _info "nothing is LISTENING on :${EXPECT_PORT} (determined, not assumed) — there is no bind to expose. The community service is stopped."
else
  while IFS= read -r _addr; do
    [ -n "$_addr" ] && _identity "listener:tcp:$_addr on the configured port ${EXPECT_PORT}"
  done <<EOF
$_BIND_ADDRS
EOF
  _BIND_VERDICT="loopback"
  while IFS= read -r _addr; do
    [ -n "$_addr" ] || continue
    case "$_addr" in
      127.*|"[::1]:"*|"::1:"*|localhost:*)            : ;;                       # loopback
      "*:${EXPECT_PORT}"|"0.0.0.0:${EXPECT_PORT}"|"[::]:${EXPECT_PORT}"|":::${EXPECT_PORT}")
                                                      _BIND_VERDICT="all-interfaces" ;;
      *)                                              [ "$_BIND_VERDICT" = "all-interfaces" ] || _BIND_VERDICT="other" ;;
    esac
  done <<EOF
$_BIND_ADDRS
EOF
  case "$_BIND_VERDICT" in
    loopback)
      _pass "listener on :${EXPECT_PORT} is bound to LOOPBACK (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' '))" ;;
    all-interfaces)
      if [ "${GHL_MCP_REQUIRE_LOOPBACK:-1}" = "0" ]; then
        _warn "listener on :${EXPECT_PORT} is bound to ALL INTERFACES (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' ')). Demoted to WARN only because GHL_MCP_REQUIRE_LOOPBACK=0 was set explicitly on this box."
      else
        _fail "listener on :${EXPECT_PORT} is bound to ALL INTERFACES (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' ')) — an UNAUTHENTICATED, CRM-credentialed endpoint reachable by any local process and any LAN host."
      fi ;;
    *)
      _fail "listener on :${EXPECT_PORT} is bound to an address this gate does not recognise as loopback (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' ')). An unrecognised bind on a CRM-credentialed, unauthenticated port is treated as exposed, never as fine — inspect it by hand." ;;
  esac
fi

# ═════════════════════════════════════════════════════════════════════════════
# D. THE RETIREMENT RECEIPT
# ═════════════════════════════════════════════════════════════════════════════

RECEIPT_STATE=""
_RECEIPT_FILE=""
if [ "$_HAVE_RECEIPT" = "1" ]; then
  _RECEIPT_FILE="$RECEIPT"
elif [ "$_HAVE_FAIL_RECEIPT" = "1" ]; then
  _RECEIPT_FILE="$RECEIPT_FAIL"
fi

if [ -n "$_RECEIPT_FILE" ]; then
  if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$_RECEIPT_FILE" >/dev/null 2>&1; then
      _misconfigured "the retirement receipt at $_RECEIPT_FILE is not valid JSON — the transaction's final state cannot be trusted."
      RECEIPT_STATE="invalid"
    fi
  fi
  if [ "$RECEIPT_STATE" != "invalid" ]; then
    RECEIPT_STATE="$(_receipt_field "$_RECEIPT_FILE" final_state)"
    _R_ARCHIVE="$(_receipt_alias "$_RECEIPT_FILE" archive.path archive_path)"
    _R_MANIFEST_SHA="$(_receipt_alias "$_RECEIPT_FILE" archive.manifest_sha256 archive_manifest_sha256)"
    _R_STAGE="$(_receipt_alias "$_RECEIPT_FILE" stage failed_stage)"
    _R_RESIDUAL="$(_receipt_alias "$_RECEIPT_FILE" verification.live residual_state)"
    _R_REMEDIATION="$(_receipt_field "$_RECEIPT_FILE" remediation)"
    case "$RECEIPT_STATE" in
      VERIFIED_OFF)
        _pass "retirement receipt at $_RECEIPT_FILE records final_state=VERIFIED_OFF"
        if [ -n "$_R_ARCHIVE" ]; then
          if [ ! -d "$_R_ARCHIVE" ]; then
            _misconfigured "the receipt names archive.path=$_R_ARCHIVE, which does not exist — the archive cannot be verified."
          else
            case "$_R_ARCHIVE" in
              "$MCP_DIR"|"$OC_ROOT"/mcp-servers/*|"$(ghl_mcp_data_parent)"/mcp-servers/*|"${HOME:-}"/mcp-servers/*)
                _misconfigured "archive.path=$_R_ARCHIVE is inside an ACTIVE install search path — an archive must never be scannable as a live install."
                ;;
            esac
            if [ -n "$_R_MANIFEST_SHA" ] && [ "$_R_MANIFEST_SHA" != "none" ]; then
              _MANIFEST=""
              for _mf in "$_R_ARCHIVE/manifest.sha256" "$_R_ARCHIVE/MANIFEST.sha256"; do
                [ -f "$_mf" ] && { _MANIFEST="$_mf"; break; }
              done
              if [ -z "$_MANIFEST" ]; then
                _misconfigured "the receipt records archive.manifest_sha256 but $_R_ARCHIVE carries no manifest.sha256 — the archived file list cannot be verified."
              else
                _GOT_SHA="$(_sha256 "$_MANIFEST")"
                if [ -z "$_GOT_SHA" ]; then
                  _warn "no shasum/sha256sum on this box — the archive manifest hash could not be recomputed."
                elif [ "$_GOT_SHA" = "$_R_MANIFEST_SHA" ]; then
                  _pass "archive manifest hash matches the receipt (${_GOT_SHA:0:12})"
                else
                  _misconfigured "archive manifest hash MISMATCH: receipt=${_R_MANIFEST_SHA:0:12} actual=${_GOT_SHA:0:12} at $_MANIFEST."
                fi
              fi
            fi
          fi
        else
          _misconfigured "the receipt records VERIFIED_OFF with no archive.path — a secret-free archive is part of the contract and must be named."
        fi
        ;;
      MIGRATION_FAILED)
        _misconfigured "retirement receipt final_state=MIGRATION_FAILED stage='${_R_STAGE:-<unset>}' residual='${_R_RESIDUAL:-<unset>}' remediation='${_R_REMEDIATION:-<unset>}'"
        ;;
      "")
        _misconfigured "the retirement receipt at $_RECEIPT_FILE has no final_state — malformed receipt."
        ;;
      *)
        _misconfigured "the retirement receipt at $_RECEIPT_FILE has an unrecognised final_state='$RECEIPT_STATE' (expected VERIFIED_OFF or MIGRATION_FAILED)."
        ;;
    esac
  fi
else
  if [ "$_HAVE_ARCHIVE" = "1" ]; then
    _misconfigured "an archive exists at $ARCHIVE_ROOT but there is no retirement receipt at $RETIRE_DIR — the transaction did not complete (or the receipt was lost)."
  fi
fi

# ── Inert tree remnants. A VERIFIED_OFF transaction archives the source tree
# and leaves it in place; that is expected and not a surface. Anything else is
# residual state an updater could rebuild and re-supervise.
if [ "$RECEIPT_STATE" = "VERIFIED_OFF" ]; then
  [ "$_HAVE_MCP_DIR" = "1" ] && _info "the retired source tree remains at $MCP_DIR (inert; the transaction archived it and nothing supervises it)"
  [ "$_HAVE_ECO" = "1" ] && _info "an inert $PM2_ECOSYSTEM remains in the retired tree (no app is registered)"
  [ "$_HAVE_SUPERVISE_SCRIPT" = "1" ] && _info "an inert $SUPERVISE_NAME remains in the retired tree (no loop is running)"
else
  [ "$_HAVE_MCP_DIR" = "1" ] && _residual "residual:install-dir:$MCP_DIR (an updater can rebuild and re-supervise it; archive it and finish the retirement transaction)"
  [ "$_HAVE_ECO" = "1" ] && _residual "residual:$PM2_ECOSYSTEM (a pm2 ecosystem definition with no app registered — an updater can start it again)"
  [ "$_HAVE_SUPERVISE_SCRIPT" = "1" ] && _residual "residual:$MCP_DIR/$SUPERVISE_NAME (fallback-B relaunch loop definition with no completed retirement)"
fi

# ── Verdict. Identity wins; then misconfiguration; then, with a VERIFIED_OFF
# receipt, RETIRED_OK. A history-bearing box with nothing left and a valid
# receipt is a PASS, which is the entire point of this rewrite.
if [ "$FATAL_FAILURES" -gt 0 ] && [ "$HAS_IDENTITY" = "0" ] && [ "$HAS_RESIDUAL" = "0" ]; then
  HAS_MISCONFIG=1
  MISCONFIGS="${MISCONFIGS}${MISCONFIGS:+; }$FATAL_FAILURES conformance check(s) failed without a matched service identity"
fi

if [ "$HAS_IDENTITY" = "1" ]; then
  printf '[ghl-mcp-runtime] VERDICT: STILL_RUNNING — %s FOUND: %s\n' "$CHECKS" "$IDENTITIES" >&2
  exit "$EXIT_STILL_RUNNING"
fi

if [ "$HAS_RESIDUAL" = "1" ] || [ "$HAS_MISCONFIG" = "1" ]; then
  printf '[ghl-mcp-runtime] VERDICT: MISCONFIGURED — %s check(s), %s warning(s). Residual/undetermined: %s%s%s\n' \
    "$CHECKS" "$WARNINGS" "$RESIDUALS" "${RESIDUALS:+; }" "$MISCONFIGS" >&2
  exit "$EXIT_MISCONFIGURED"
fi

if [ "$RECEIPT_STATE" = "VERIFIED_OFF" ]; then
  [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] VERDICT: RETIRED_OK — every community MCP surface is absent; the receipt records VERIFIED_OFF. %s check(s) passed, %s warning(s).\n' "$CHECKS" "$WARNINGS"
  exit "$EXIT_RETIRED_OK"
fi

# A history-bearing box with nothing left but no receipt: we cannot claim the
# transaction completed, so this is not a silent pass.
printf '[ghl-mcp-runtime] VERDICT: MISCONFIGURED — every community surface is absent but no retirement receipt proves the transaction completed at %s.\n' "$RECEIPT" >&2
exit "$EXIT_MISCONFIGURED"
