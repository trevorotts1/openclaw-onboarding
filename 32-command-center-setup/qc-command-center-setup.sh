#!/usr/bin/env bash
# Skill 32 — Command Center Setup — Install QC (Next.js dashboard)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" CC_PORT=4000; }
fi
resolve_platform_paths
# Drive-by fix: the REAL lib-shared.sh resolve_platform_paths() (as opposed to
# this script's own fallback stub above) never exports CC_PORT, so under
# `set -u` the port-reachability check below trips "CC_PORT: unbound variable"
# on every box that has lib-shared.sh (i.e. every real box) instead of running
# the check. Default it here, matching the fallback stub's own value.
: "${CC_PORT:=4000}"
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${CLOUDFLARE_TUNNEL_TOKEN:=}"; : "${TUNNEL_TOKEN:=}"

# ── CC locator: known locations FIRST, bounded/pruned/timed find as last resort ──
# WAS: an unconditional `find $HOME /data -maxdepth 4 -name blackceo-command-center`
# (times two — one more for package.json) on EVERY QC pass. maxdepth 4 alone does
# not bound the COST of a real, in-use Mac's $HOME: ~/Library, node_modules trees,
# iCloud/Dropbox sync mirrors and Time Machine local snapshots explode into
# thousands of entries within 4 levels. Measured 20+ minutes PER find on a real
# box (40+ min for the pair) — a routine QC pass reads as a hang. Fix: check the
# same known/candidate paths update-skills.sh's cc_resolve_existing_dir() already
# uses (so this QC and the updater agree on where CC lives) before ever touching
# find; only fall back to a depth- and time-bounded, heavy-dir-pruned find; and
# fail fast with a clear message instead of grinding through the whole home dir.
_CC_QC_CANDIDATES="$HOME/projects/command-center /data/projects/command-center $HOME/projects/blackceo-command-center /data/projects/blackceo-command-center $HOME/projects/mission-control $HOME/blackceo-command-center /opt/mission-control /app"

_cc_qc_bounded_find() {
  # $1 = 'dir' (find the blackceo-command-center directory itself) or
  #      'pkg' (find blackceo-command-center/package.json)
  local want="$1" timeout_bin="" hit=""
  command -v timeout  >/dev/null 2>&1 && timeout_bin="timeout 10"
  command -v gtimeout  >/dev/null 2>&1 && [ -z "$timeout_bin" ] && timeout_bin="gtimeout 10"
  # Prune the directories that make an unbounded scan expensive: framework/cache
  # trees, VCS internals, dependency trees, and the trash.
  if [ "$want" = "dir" ]; then
    hit=$($timeout_bin find $HOME /data -maxdepth 4 \
      \( -name 'Library' -o -name 'node_modules' -o -name '.git' -o -name '.Trash' -o -name '.cache' -o -name '.npm' \) -prune -o \
      -type d -name 'blackceo-command-center' -print 2>/dev/null | head -1)
  else
    hit=$($timeout_bin find $HOME /data -maxdepth 4 \
      \( -name 'Library' -o -name 'node_modules' -o -name '.git' -o -name '.Trash' -o -name '.cache' -o -name '.npm' \) -prune -o \
      -path '*blackceo-command-center/package.json' -print 2>/dev/null | head -1)
  fi
  [ -n "$hit" ]
}

# Returns 0 (found) / 1 (not found). Known locations are checked first — the
# common case (CC installed at its canonical or documented-alternate path) never
# touches find at all. NOTE: the canonical on-box checkout is commonly renamed to
# "command-center" (not "blackceo-command-center") — see update-skills.sh's
# _CC_DIR_CANONICAL — so the candidate list itself (not a basename filter) is
# what encodes "known CC location"; a real git checkout at any candidate counts.
cc_qc_locate_dir() {
  local c
  for c in $_CC_QC_CANDIDATES; do
    [ -d "$c/.git" ] && return 0
  done
  _cc_qc_bounded_find dir
}
cc_qc_locate_pkg() {
  local c
  for c in $_CC_QC_CANDIDATES; do
    [ -f "$c/package.json" ] && return 0
  done
  _cc_qc_bounded_find pkg
}

echo ""
echo "═══ Skill 32 — Command Center Setup — Install QC ═══"
echo ""
assert "Skill 32 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/32-command-center-setup\" ]"
assert "Skill 23 (Workforce — provides ORG-CHART CC reads) installed" "[ -d \"$SKILLS_DIR_DEFAULT/23-ai-workforce-blueprint\" ]"
warn_only "Command Center repo cloned locally" "cc_qc_locate_dir"
warn_only "package.json exists in CC repo"     "cc_qc_locate_pkg"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
warn_only "PM2 installed" "command -v pm2"
warn_only "cloudflared installed (Mac only — VPS skip)" "[ \"${OPENCLAW_PLATFORM:-}\" = 'vps' ] || command -v cloudflared"
warn_only "Cloudflare tunnel token present" "[ -n \"$CLOUDFLARE_TUNNEL_TOKEN\" ] || [ -n \"$TUNNEL_TOKEN\" ]"
warn_only "Port ${CC_PORT} reachable (CC running locally)" "curl -sS -m 3 http://localhost:${CC_PORT}/ -o /dev/null -w '%{http_code}' 2>/dev/null | grep -qE '^(200|301|302|404|307)'"
assert "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 32 QC FAILED"; exit 1; } || { green "Skill 32 QC PASS"; exit 0; }
