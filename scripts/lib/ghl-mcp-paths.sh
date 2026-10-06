#!/usr/bin/env bash
# ghl-mcp-paths.sh: the ONE derivation of platform + paths for the GHL
# community MCP (Tier 2, skill 36). Sourced by scripts/ghl-mcp-autostart.sh
# and scripts/ghl-mcp-assert-runtime.sh. Nothing here starts, writes or probes
# anything: it answers "where does this box keep its Tier 2 install, and what
# shape of box is it" and nothing else.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS: two independent copies of one derivation, drifted
#
# ghl-mcp-assert-runtime.sh carried the comment "identical derivation to
# ghl-mcp-autostart.sh" directly above a derivation that was NOT identical:
#
#   autostart knew three platforms   vps | mac | linux-home
#   assert    knew two               vps | mac
#
# So a Linux container with no /data was called "mac" by the gate and asked for
# two launchd plists that nothing on the box could ever run. Two FATALs, on a
# box whose service was provably healthy, with no way to act on them.
#
# Both copies also hardcoded the install directory as /data/mcp-servers (vps)
# or $HOME/mcp-servers (everything else). On the Contabo client-container shape
# only $OPENCLAW_ROOT, its workspace and $HOME/.config/openclaw are bind-mounted
# ($HOME/mcp-servers lives in the container layer and is DESTROYED on every
# recreate). The working installs there deliberately live under the OpenClaw
# root, where the bind mount keeps them, and both scripts looked straight past
# them: the updater reported "GHL MCP Tier 2 MISCONFIGURED" (exit 2) about a pm2
# app that was online, answering /health with 43 tools, on the pinned build.
#
# One sourced copy is the only structural answer. Duplicating a derivation and
# writing "identical to" above it is how these two disagreed for two releases.
#
# ─────────────────────────────────────────────────────────────────────────────
# OVERRIDE HOOKS (tests only; real boxes set none of these)
#   GHL_MCP_PLATFORM_OVERRIDE   vps | mac | linux-home
#   GHL_MCP_DIR                 the Tier 2 install dir, verbatim
#   GHL_MCP_LOG_DIR_OVERRIDE    the log dir, verbatim
#   GHL_MCP_DATA_ROOT           stand-in for /data/.openclaw (a test cannot
#                               create /data, and the vps branch must still be
#                               reachable in CI)
#   GHL_MCP_UNAME_S             stand-in for `uname -s`
# Every hook is READ ONLY HERE, so the two consumers cannot honour different
# ones, which is exactly the failure this file replaces.

# ghl_mcp_canon_dir <path>: the canonical PHYSICAL directory behind <path>
# (symlinks resolved), or <path> unchanged when it is not a directory.
#
# `cd -P` + `pwd -P` rather than realpath(1): macOS ships no coreutils realpath,
# and half the fleet is macOS. Same approach as scripts/wire-social-media.sh.
ghl_mcp_canon_dir() {
  [ -n "${1:-}" ] || { printf ''; return 0; }
  [ -d "$1" ] || { printf '%s' "$1"; return 0; }
  ( cd -P "$1" 2>/dev/null && pwd -P ) || printf '%s' "$1"
}

# ghl_mcp_data_root: the data-rooted OpenClaw root this box WOULD use.
ghl_mcp_data_root() { printf '%s' "${GHL_MCP_DATA_ROOT:-/data/.openclaw}"; }

# ghl_mcp_data_parent: the parent of the data root (/data on a real VPS). The
# legacy install dir and the vps log dir both hang off it.
ghl_mcp_data_parent() {
  local _d; _d="$(ghl_mcp_data_root)"
  printf '%s' "$(dirname "$_d")"
}

# ghl_mcp_openclaw_root: the OpenClaw root, CANONICALIZED.
#
# Order, and why:
#   1. $OPENCLAW_ROOT when it names a real directory. It is the first-class
#      override every other consumer in this repo honours.
#   2. the data root when it carries openclaw.json. This is the ORIGINAL
#      vps marker, kept verbatim: a bare/empty /data/.openclaw (a stray mount)
#      must not capture a box whose real install is under $HOME.
#   3. $HOME/.openclaw.
# The result is canonicalized, so a /data that is really a symlink into $HOME
# resolves to the one physical root instead of presenting as two.
ghl_mcp_openclaw_root() {
  local _data; _data="$(ghl_mcp_data_root)"
  if [ -n "${OPENCLAW_ROOT:-}" ] && [ -d "${OPENCLAW_ROOT}" ]; then
    ghl_mcp_canon_dir "$OPENCLAW_ROOT"; return 0
  fi
  if [ -f "$_data/openclaw.json" ]; then
    ghl_mcp_canon_dir "$_data"; return 0
  fi
  ghl_mcp_canon_dir "${HOME:-}/.openclaw"
}

# ghl_mcp_platform [root]: vps | mac | linux-home
#
#   vps         data-rooted: the resolved root IS the data root, and the data
#               root is a REAL path (it canonicalizes to itself). pm2/systemd,
#               logs under the data parent.
#   mac         Darwin. launchd is the supervisor.
#   linux-home  Linux with a HOME-layout root: a client container, or a box
#               whose /data is a symlink back into $HOME. Shares the VPS
#               supervisor chain (pm2, else systemd, else the supervised
#               relaunch loop) and has NO launchd: handing one a plist installs
#               a supervisor that can never run, which is how a container
#               reported STARTED_UNHEALTHY forever with zero supervisors.
#
# The symlink test is the whole reason canonicalization is here. If /data is a
# symlink to $HOME, "$root = $data_root" is TRUE for a box that has no data
# volume at all; requiring the data root to canonicalize to itself separates a
# real /data mount from a symlink pointing back at the home layout.
ghl_mcp_platform() {
  [ -n "${GHL_MCP_PLATFORM_OVERRIDE:-}" ] && { printf '%s' "$GHL_MCP_PLATFORM_OVERRIDE"; return 0; }
  local _root _data _data_canon _uname
  _root="${1:-}"; [ -n "$_root" ] || _root="$(ghl_mcp_openclaw_root)"
  _data="$(ghl_mcp_data_root)"
  _data_canon="$(ghl_mcp_canon_dir "$_data")"
  if [ "$_root" = "$_data_canon" ] && [ "$_data_canon" = "$_data" ] && [ -d "$_data" ]; then
    printf 'vps'; return 0
  fi
  _uname="${GHL_MCP_UNAME_S:-$(uname -s 2>/dev/null || printf 'unknown')}"
  if [ "$_uname" = "Darwin" ]; then printf 'mac'; else printf 'linux-home'; fi
}

# ghl_mcp_has_build_stamp <dir>: rc 0 when <dir> carries a Tier 2 build stamp
# that names a commit. A stamp is the receipt that the pinned build path has
# actually run there, which is what makes a legacy location worth preferring
# over a fresh, empty, root-derived one.
ghl_mcp_has_build_stamp() {
  [ -n "${1:-}" ] || return 1
  [ -s "$1/.ghl-mcp-build.json" ] || return 1
  grep -q '"commit"' "$1/.ghl-mcp-build.json" 2>/dev/null
}

# ghl_mcp_dir_is_installed <dir>: a build stamp OR a git checkout. Used for the
# PREFERRED location only: a half-finished install there (cloned, not yet built)
# still owns the box and must not silently lose to a stale legacy tree.
ghl_mcp_dir_is_installed() {
  [ -n "${1:-}" ] || return 1
  ghl_mcp_has_build_stamp "$1" && return 0
  [ -d "$1/.git" ]
}

# ghl_mcp_install_dir [root]: where Tier 2 lives on THIS box.
#
#   1. $GHL_MCP_DIR, verbatim (test hook).
#   2. <root>/mcp-servers/ghl-community-mcp when something is installed there.
#      This is the DEFAULT for a fresh install, because the OpenClaw root is the
#      one directory a client container is guaranteed to keep across a recreate.
#   3. the legacy locations, <data parent>/mcp-servers and $HOME/mcp-servers,
#      when they carry a build stamp. Every box installed before this change has
#      its working tree in one of them, so a stamp there wins over an empty
#      preferred path and no box is asked to rebuild for a path change.
#   4. otherwise the preferred path (nothing is installed anywhere yet).
ghl_mcp_install_dir() {
  [ -n "${GHL_MCP_DIR:-}" ] && { printf '%s' "$GHL_MCP_DIR"; return 0; }
  local _root _pref _c
  _root="${1:-}"; [ -n "$_root" ] || _root="$(ghl_mcp_openclaw_root)"
  _pref="$_root/mcp-servers/ghl-community-mcp"
  if ghl_mcp_dir_is_installed "$_pref"; then printf '%s' "$_pref"; return 0; fi
  for _c in "$(ghl_mcp_data_parent)/mcp-servers/ghl-community-mcp" \
            "${HOME:-}/mcp-servers/ghl-community-mcp"; do
    [ "$_c" = "$_pref" ] && continue
    if ghl_mcp_has_build_stamp "$_c"; then printf '%s' "$_c"; return 0; fi
  done
  printf '%s' "$_pref"
}

# ghl_mcp_log_dir <platform>: unchanged per-platform destinations, in one place.
ghl_mcp_log_dir() {
  [ -n "${GHL_MCP_LOG_DIR_OVERRIDE:-}" ] && { printf '%s' "$GHL_MCP_LOG_DIR_OVERRIDE"; return 0; }
  case "${1:-}" in
    vps) printf '%s' "$(ghl_mcp_data_parent)/logs" ;;
    mac) printf '%s' "${HOME:-}/Library/Logs/ghl-mcp" ;;
    *)   printf '%s' "${HOME:-}/logs" ;;
  esac
}

# ghl_mcp_pm2_home [root]: the PM2_HOME this box's Tier 2 app lives under.
#
# pm2 keeps its process list per PM2_HOME. On a client container the app is
# registered under <root>/.pm2 precisely because $HOME/.pm2 does not survive a
# recreate, so a `pm2 describe` run with the DEFAULT home reports "app not
# found" about an app that is online, which is half of the false MISCONFIGURED
# verdict this release fixes.
#
#   1. an explicit PM2_HOME always wins (an operator said so).
#   2. <root>/.pm2 when it exists: the persisted, bind-mounted home.
#   3. $HOME/.pm2 when it exists: every box installed before this change.
#   4. <root>/.pm2 as the destination for a NEW install, so the next container
#      recreate keeps the registration.
ghl_mcp_pm2_home() {
  [ -n "${PM2_HOME:-}" ] && { printf '%s' "$PM2_HOME"; return 0; }
  local _root="${1:-}"
  [ -n "$_root" ] || _root="$(ghl_mcp_openclaw_root)"
  [ -d "$_root/.pm2" ] && { printf '%s' "$_root/.pm2"; return 0; }
  [ -d "${HOME:-}/.pm2" ] && { printf '%s' "${HOME:-}/.pm2"; return 0; }
  printf '%s' "$_root/.pm2"
}

# ghl_mcp_pm2_home_existing [root]: as above, but EMPTY when no candidate home
# exists yet. A read-only caller (the runtime gate) must never point PM2_HOME at
# a directory that does not exist: `pm2 describe` under a fresh PM2_HOME SPAWNS
# a new pm2 daemon. Inspect with what is there, or with pm2's own default.
ghl_mcp_pm2_home_existing() {
  [ -n "${PM2_HOME:-}" ] && { printf '%s' "$PM2_HOME"; return 0; }
  local _root="${1:-}"
  [ -n "$_root" ] || _root="$(ghl_mcp_openclaw_root)"
  [ -d "$_root/.pm2" ] && { printf '%s' "$_root/.pm2"; return 0; }
  [ -d "${HOME:-}/.pm2" ] && { printf '%s' "${HOME:-}/.pm2"; return 0; }
  printf ''
}

# ghl_mcp_resolve_paths: set the five canonical variables in the CALLER'S shell:
#   GHL_MCP_RESOLVED_ROOT  GHL_MCP_RESOLVED_PLATFORM  GHL_MCP_RESOLVED_DIR
#   GHL_MCP_RESOLVED_LOG_DIR  GHL_MCP_RESOLVED_PM2_HOME
# Consumers call THIS, not the individual functions, so neither can skip a step
# or apply the overrides in a different order.
ghl_mcp_resolve_paths() {
  GHL_MCP_RESOLVED_ROOT="$(ghl_mcp_openclaw_root)"
  GHL_MCP_RESOLVED_PLATFORM="$(ghl_mcp_platform "$GHL_MCP_RESOLVED_ROOT")"
  GHL_MCP_RESOLVED_DIR="$(ghl_mcp_install_dir "$GHL_MCP_RESOLVED_ROOT")"
  GHL_MCP_RESOLVED_LOG_DIR="$(ghl_mcp_log_dir "$GHL_MCP_RESOLVED_PLATFORM")"
  GHL_MCP_RESOLVED_PM2_HOME="$(ghl_mcp_pm2_home "$GHL_MCP_RESOLVED_ROOT")"
  return 0
}
