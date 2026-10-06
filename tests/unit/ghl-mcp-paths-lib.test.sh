#!/usr/bin/env bash
# tests/unit/ghl-mcp-paths-lib.test.sh (skill 36 v2.0.2)
#
# Proves scripts/lib/ghl-mcp-paths.sh, the ONE derivation of platform and paths
# for the GHL community MCP, and proves that both consumers actually source it.
#
# WHY EACH CASE EXISTS: every one is a state measured on a real box, not an
# invented permutation:
#
#   ROOT-DERIVED INSTALL WINS. On the client-container shape only the OpenClaw
#   root and its workspace are bind-mounted; $HOME/mcp-servers lives in the
#   container layer and is destroyed on recreate. The working installs are under
#   the root, and both scripts used to look straight past them and report a
#   healthy box as MISCONFIGURED.
#
#   LEGACY STILL WINS WHEN IT HOLDS THE BUILD. Every box installed before this
#   change has its tree at /data/mcp-servers or $HOME/mcp-servers. If the
#   resolver preferred an empty root-derived path there, every one of them would
#   be told to rebuild. A build stamp is the receipt that the pinned build path
#   ran there, so a stamped legacy tree beats an empty preferred one.
#
#   SYMLINKED /data IS ONE ROOT, NOT TWO. A box whose /data is a symlink back
#   into $HOME has a single physical root. Reading it as "data-rooted" routes it
#   to the VPS log paths and the VPS supervisor assumptions for a box that is
#   really the HOME layout.
#
#   THE PLATFORM FUNCTION MUST KNOW THREE SHAPES. The runtime gate knew two,
#   which is how a Linux container was judged as a Mac and failed for the
#   absence of two launchd plists that nothing on it could ever load.
#
# Hermetic: every case runs against directories this test creates under its own
# temp root, through the library's documented override hooks. It never reads
# /data, never touches $HOME, and starts no process.
#
# Exit 0 = every case behaved. Exit 1 = one or more did not.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
AUTOSTART="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
ASSERT="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-paths-lib.test.sh (skill 36 v2.0.2) ==="
echo ""

if [ ! -f "$LIB" ]; then
  echo "  FAIL: shared path library not found at $LIB"
  exit 1
fi

bash -n "$LIB" || { echo "  FAIL: $LIB does not parse"; exit 1; }

# A stamped Tier 2 tree: the receipt that the pinned build path ran there.
_stamp() {
  mkdir -p "$1"
  printf '{\n  "commit": "%s",\n  "profile": "curated"\n}\n' \
    "bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3" > "$1/.ghl-mcp-build.json"
}

# _derive <key>: run the library in a clean subshell with the environment the
# caller exported, and print one resolved value. The library is SOURCED, never
# reimplemented here: a test that restates the logic proves only that it can
# restate the logic.
_derive() {
  local key="$1"
  (
    # shellcheck disable=SC1090
    . "$LIB"
    ghl_mcp_resolve_paths
    case "$key" in
      root)     printf '%s' "$GHL_MCP_RESOLVED_ROOT" ;;
      platform) printf '%s' "$GHL_MCP_RESOLVED_PLATFORM" ;;
      dir)      printf '%s' "$GHL_MCP_RESOLVED_DIR" ;;
      logs)     printf '%s' "$GHL_MCP_RESOLVED_LOG_DIR" ;;
      pm2)      printf '%s' "$GHL_MCP_RESOLVED_PM2_HOME" ;;
    esac
  )
}

_eq() {  # _eq <label> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected '$2', got '$3'"; fi
}

# mktemp -d hands back /var/... on macOS, which is really /private/var. The
# library canonicalizes, so the fixture root must be canonical too or every
# comparison fails for a reason that has nothing to do with the code.
TMP_ROOT="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TMP_ROOT"' EXIT

# ─────────────────────────────────────────────────────────────────────────────
# 1. HOME-layout Linux container (the Contabo client shape): the install lives
#    under the OpenClaw root, which is the bind-mounted directory.
# ─────────────────────────────────────────────────────────────────────────────
BOX1="$TMP_ROOT/box1"
mkdir -p "$BOX1/.openclaw"
printf '{}\n' > "$BOX1/.openclaw/openclaw.json"
_stamp "$BOX1/.openclaw/mcp-servers/ghl-community-mcp"
(
  export HOME="$BOX1"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  printf '%s\n%s\n%s\n' "$(_derive platform)" "$(_derive dir)" "$(_derive logs)"
) > "$TMP_ROOT/out1"
_eq "(1a) a HOME-layout Linux box is linux-home, never mac" "linux-home" "$(sed -n 1p "$TMP_ROOT/out1")"
_eq "(1b) the install resolves under the OpenClaw root (survives a container recreate)" \
    "$BOX1/.openclaw/mcp-servers/ghl-community-mcp" "$(sed -n 2p "$TMP_ROOT/out1")"
_eq "(1c) linux-home logs go to \$HOME/logs, not \$HOME/Library/Logs" \
    "$BOX1/logs" "$(sed -n 3p "$TMP_ROOT/out1")"

# ─────────────────────────────────────────────────────────────────────────────
# 2. A pre-existing box whose ONLY install is the legacy $HOME/mcp-servers tree.
#    It carries a build stamp, so it must keep winning: nothing on the fleet is
#    asked to rebuild because the default path moved.
# ─────────────────────────────────────────────────────────────────────────────
BOX2="$TMP_ROOT/box2"
mkdir -p "$BOX2/.openclaw"
printf '{}\n' > "$BOX2/.openclaw/openclaw.json"
_stamp "$BOX2/mcp-servers/ghl-community-mcp"
(
  export HOME="$BOX2"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Darwin"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  printf '%s\n%s\n%s\n' "$(_derive platform)" "$(_derive dir)" "$(_derive logs)"
) > "$TMP_ROOT/out2"
_eq "(2a) a Darwin box is mac" "mac" "$(sed -n 1p "$TMP_ROOT/out2")"
_eq "(2b) a STAMPED legacy \$HOME/mcp-servers install still wins (no forced rebuild)" \
    "$BOX2/mcp-servers/ghl-community-mcp" "$(sed -n 2p "$TMP_ROOT/out2")"
_eq "(2c) mac logs stay at \$HOME/Library/Logs/ghl-mcp" \
    "$BOX2/Library/Logs/ghl-mcp" "$(sed -n 3p "$TMP_ROOT/out2")"

# ─────────────────────────────────────────────────────────────────────────────
# 3. An UNSTAMPED legacy directory is not an install. A bare directory (or one
#    left behind by a failed clone) must not capture a box away from the
#    root-derived default, or a fresh install lands back in the ephemeral layer.
# ─────────────────────────────────────────────────────────────────────────────
BOX3="$TMP_ROOT/box3"
mkdir -p "$BOX3/.openclaw" "$BOX3/mcp-servers/ghl-community-mcp"
printf '{}\n' > "$BOX3/.openclaw/openclaw.json"
(
  export HOME="$BOX3"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  _derive dir
) > "$TMP_ROOT/out3"
_eq "(3) an UNSTAMPED legacy directory loses to the root-derived default" \
    "$BOX3/.openclaw/mcp-servers/ghl-community-mcp" "$(cat "$TMP_ROOT/out3")"

# ─────────────────────────────────────────────────────────────────────────────
# 4. A real data-rooted VPS: /data/.openclaw is a genuine directory carrying
#    openclaw.json, and the legacy /data/mcp-servers tree holds the build.
# ─────────────────────────────────────────────────────────────────────────────
BOX4="$TMP_ROOT/box4"
mkdir -p "$BOX4/data/.openclaw"
printf '{}\n' > "$BOX4/data/.openclaw/openclaw.json"
_stamp "$BOX4/data/mcp-servers/ghl-community-mcp"
mkdir -p "$BOX4/home"
(
  export HOME="$BOX4/home"
  export GHL_MCP_DATA_ROOT="$BOX4/data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  printf '%s\n%s\n%s\n' "$(_derive platform)" "$(_derive dir)" "$(_derive logs)"
) > "$TMP_ROOT/out4"
_eq "(4a) a genuine data-rooted box is vps" "vps" "$(sed -n 1p "$TMP_ROOT/out4")"
_eq "(4b) the stamped legacy data-parent install still wins on a VPS" \
    "$BOX4/data/mcp-servers/ghl-community-mcp" "$(sed -n 2p "$TMP_ROOT/out4")"
_eq "(4c) vps logs stay under the data parent" "$BOX4/data/logs" "$(sed -n 3p "$TMP_ROOT/out4")"

# ─────────────────────────────────────────────────────────────────────────────
# 5. /data is a SYMLINK back into $HOME. The marker file is reachable through
#    it, so the pre-fix test ("is there a /data/.openclaw/openclaw.json?") said
#    vps, for a box that has no data volume at all. Canonicalization collapses
#    the two spellings to the one physical root, and the shape reads as what it
#    is: the HOME layout.
# ─────────────────────────────────────────────────────────────────────────────
BOX5="$TMP_ROOT/box5"
mkdir -p "$BOX5/home/.openclaw"
printf '{}\n' > "$BOX5/home/.openclaw/openclaw.json"
_stamp "$BOX5/home/.openclaw/mcp-servers/ghl-community-mcp"
ln -s "$BOX5/home" "$BOX5/data"
(
  export HOME="$BOX5/home"
  export GHL_MCP_DATA_ROOT="$BOX5/data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  printf '%s\n%s\n%s\n' "$(_derive platform)" "$(_derive root)" "$(_derive dir)"
) > "$TMP_ROOT/out5"
_eq "(5a) a /data that is a symlink into \$HOME is NOT a data-rooted box" \
    "linux-home" "$(sed -n 1p "$TMP_ROOT/out5")"
_eq "(5b) the root canonicalizes to the one physical directory" \
    "$BOX5/home/.openclaw" "$(sed -n 2p "$TMP_ROOT/out5")"
_eq "(5c) the install resolves under that one canonical root" \
    "$BOX5/home/.openclaw/mcp-servers/ghl-community-mcp" "$(sed -n 3p "$TMP_ROOT/out5")"

# ─────────────────────────────────────────────────────────────────────────────
# 6. PM2_HOME. pm2 keeps one process list per home, so the home is part of the
#    address of the app. An existing root-persisted home wins; an existing
#    $HOME/.pm2 keeps every pre-existing box working; a box with neither is
#    pointed at the root so the NEXT container recreate keeps the registration.
# ─────────────────────────────────────────────────────────────────────────────
BOX6="$TMP_ROOT/box6"
mkdir -p "$BOX6/.openclaw/.pm2" "$BOX6/.pm2"
printf '{}\n' > "$BOX6/.openclaw/openclaw.json"
(
  export HOME="$BOX6"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  _derive pm2
) > "$TMP_ROOT/out6a"
_eq "(6a) the root-persisted .pm2 wins over \$HOME/.pm2 when both exist" \
    "$BOX6/.openclaw/.pm2" "$(cat "$TMP_ROOT/out6a")"

BOX7="$TMP_ROOT/box7"
mkdir -p "$BOX7/.openclaw" "$BOX7/.pm2"
printf '{}\n' > "$BOX7/.openclaw/openclaw.json"
(
  export HOME="$BOX7"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  _derive pm2
) > "$TMP_ROOT/out6b"
_eq "(6b) an existing \$HOME/.pm2 is honoured (no pre-existing box is moved)" \
    "$BOX7/.pm2" "$(cat "$TMP_ROOT/out6b")"

BOX8="$TMP_ROOT/box8"
mkdir -p "$BOX8/.openclaw"
printf '{}\n' > "$BOX8/.openclaw/openclaw.json"
(
  export HOME="$BOX8"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT PM2_HOME GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  printf '%s\n%s\n' "$(_derive pm2)" "$(. "$LIB"; ghl_mcp_pm2_home_existing "$BOX8/.openclaw")"
) > "$TMP_ROOT/out6c"
_eq "(6c) a box with no pm2 home yet is pointed at the persisted root location" \
    "$BOX8/.openclaw/.pm2" "$(sed -n 1p "$TMP_ROOT/out6c")"
_eq "(6d) the READ-ONLY accessor returns EMPTY rather than a path that does not exist (a 'pm2 describe' under a fresh PM2_HOME spawns a daemon)" \
    "" "$(sed -n 2p "$TMP_ROOT/out6c")"

# ─────────────────────────────────────────────────────────────────────────────
# 7. An explicit PM2_HOME is an operator decision and always wins.
# ─────────────────────────────────────────────────────────────────────────────
(
  export HOME="$BOX6"
  export PM2_HOME="/some/operator/choice"
  export GHL_MCP_DATA_ROOT="$TMP_ROOT/absent-data/.openclaw"
  export GHL_MCP_UNAME_S="Linux"
  unset OPENCLAW_ROOT GHL_MCP_DIR GHL_MCP_LOG_DIR_OVERRIDE GHL_MCP_PLATFORM_OVERRIDE
  _derive pm2
) > "$TMP_ROOT/out7"
_eq "(7) an explicit PM2_HOME is never overridden" "/some/operator/choice" "$(cat "$TMP_ROOT/out7")"

# ─────────────────────────────────────────────────────────────────────────────
# 8. THE ANTI-DRIFT ASSERT. The defect this library exists to close was two
#    copies of one derivation under a comment claiming they were identical. If
#    either consumer stops sourcing it, that failure is back, so the wiring is
#    checked here, not left to a code review.
# ─────────────────────────────────────────────────────────────────────────────
for _consumer in "$AUTOSTART" "$ASSERT"; do
  _b="$(basename "$_consumer")"
  if [ ! -f "$_consumer" ]; then
    fail "(8) consumer $_b is missing"
    continue
  fi
  # Executable lines only: a path named in a comment is documentation.
  #
  # HERESTRINGS, NEVER `printf | grep -q`. Under `set -o pipefail` a `grep -q`
  # that matches early closes the pipe, the writer dies of SIGPIPE (141), and
  # the pipeline reports FAILURE for a pattern that IS present. Measured here
  # on bash 3.2, which is what half the fleet runs. The same trap is documented
  # at scripts/qc-assert-ghl-mcp-supervised.sh code_has().
  _code="$(sed 's/#.*$//' "$_consumer")"
  if grep -q 'lib/ghl-mcp-paths\.sh' <<< "$_code" \
     && grep -q 'ghl_mcp_resolve_paths' <<< "$_code"; then
    pass "(8) $_b sources the shared path library and calls ghl_mcp_resolve_paths"
  else
    fail "(8) $_b does NOT source scripts/lib/ghl-mcp-paths.sh: the two derivations can drift again"
  fi
  # And it must not have quietly kept its own copy of the hardcoded paths.
  if grep -qE '(MCP_DIR|_pref)="?/data/mcp-servers' <<< "$_code"; then
    fail "(8) $_b still hardcodes /data/mcp-servers outside the shared library"
  else
    pass "(8) $_b carries no hardcoded /data/mcp-servers install path"
  fi
done

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
