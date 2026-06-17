#!/usr/bin/env bash
# qc-assert-ghl-mcp-supervised.sh — v12.24.0
#
# STATIC QC INVARIANT: enforces that the GHL Community MCP (Tier 2, skill 36) is
# configured for PROPER, REBOOT-SURVIVING, PORT-PINNED supervision on a FRESH
# install — so the fleet incident (12/19 boxes down/unsupervised) can NEVER ship
# again. This is the single-source-of-truth logic; scripts/qc-system-integrity.sh
# CHECK X.12 delegates to it.
#
# THE TWO ROOT CAUSES this gate forbids from ever shipping:
#
#   1. UNSUPERVISED BARE NOHUP.
#      `nohup node dist/main.js &` does NOT survive session/exec teardown and is
#      not restarted on crash. The shipped autostart scripts MUST start the
#      server under a real supervisor:
#        - Mac : launchd LaunchAgent (com.clawd.ghl-mcp) with KeepAlive + RunAtLoad
#        - VPS : pm2 (ecosystem.config.js) + `pm2 save` + an @reboot resurrect
#                hook, OR systemd. A detached `setsid` SUPERVISED relaunch LOOP is
#                an allowed last-resort fallback; a BARE nohup that is NOT inside a
#                relaunch loop is a HARD VIOLATION.
#
#   2. RANDOM PORT.
#      The community MCP's main.js reads `PORT` BEFORE `MCP_SERVER_PORT`
#      (src/main.ts:55). Without an EXPLICIT PORT, a stray inherited PORT binds a
#      random port (49032/63703) instead of 8765. Every launch surface the
#      autostart scripts write (launchd plist, pm2 env, systemd Environment, .env,
#      supervisor loop) MUST pin BOTH PORT and MCP_SERVER_PORT.
#
# This is a STATIC check of the SHIPPED SCRIPTS (not a live process probe), so it
# runs at install time and on every update — before the server is even started —
# and fails the build if a regression reintroduces bare nohup or an unpinned PORT.
#
# Scripts inspected (first that exists wins per role):
#   ghl-mcp-autostart.sh  — repo scripts/  | $HOME/.openclaw/skills/scripts/ | /data/.openclaw/skills/scripts/
#   start-ghl-mcp-server.sh (VPS overlay)  — repo platform/vps/36-ghl-mcp-setup-scripts/ | installed tree
#
# Exit codes:
#   0  — supervision + PORT-pinning invariants hold (or the autostart scripts are
#        genuinely absent — nothing to enforce, reported as INFO)
#   1  — one or more invariants VIOLATED (FATAL — block the build/QC)
#
# Usage:
#   bash qc-assert-ghl-mcp-supervised.sh
#   bash qc-assert-ghl-mcp-supervised.sh --quiet
#
# Wired in:
#   scripts/qc-system-integrity.sh  (CHECK X.12: GHL MCP supervision standard)

set -uo pipefail

QUIET=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-ghl-mcp-supervised] PASS  %s\n' "$*"; }
_fail() { printf '[qc-ghl-mcp-supervised] FATAL INVARIANT VIOLATED — %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-ghl-mcp-supervised] INFO  %s\n' "$*"; }

FAILURES=0

# ── Resolve this script's dir so we can find sibling scripts in the repo ──────
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_first() {
  # echo the first path that exists from the candidate list
  local p
  for p in "$@"; do
    [ -f "$p" ] && { printf '%s' "$p"; return 0; }
  done
  return 1
}

AUTOSTART="$(find_first \
  "$SELF_DIR/ghl-mcp-autostart.sh" \
  "$HOME/.openclaw/skills/scripts/ghl-mcp-autostart.sh" \
  "/data/.openclaw/skills/scripts/ghl-mcp-autostart.sh" || true)"

# The VPS overlay script lives one dir up from scripts/ in the repo
# (platform/vps/36-ghl-mcp-setup-scripts/), or under the installed skills tree.
REPO_ROOT="$(cd "$SELF_DIR/.." 2>/dev/null && pwd || echo "$SELF_DIR")"
VPS_START="$(find_first \
  "$REPO_ROOT/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" \
  "$HOME/.openclaw/skills/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" \
  "/data/.openclaw/skills/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" \
  "/data/.openclaw/onboarding/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" || true)"

# ── Helper: detect a BARE nohup (a `nohup node …` NOT inside a relaunch loop) ──
# A supervised relaunch loop writes a `.sh` wrapper containing `while true; do …
# node … ; sleep …; done` and then `setsid nohup bash "$SUP"` — that nohup wraps
# the LOOP (a supervisor), which is allowed. A bare `nohup node dist/main.js` with
# no surrounding loop is the forbidden pattern. We flag `nohup` directly launching
# `node` and NOT a bash wrapper.
#
# IMPORTANT: only inspect EXECUTABLE lines. Comment lines (and the leading-`#`
# portion of inline comments) are documentation/prose — a script that DOCUMENTS
# "we removed the bare nohup node" must not trip its own gate. We strip everything
# from the first `#` onward before matching.
bare_nohup_offenders() {
  local f="$1"
  grep -nE 'nohup' "$f" 2>/dev/null | while IFS= read -r line; do
    local lineno code
    lineno="${line%%:*}"
    code="${line#*:}"
    code="${code%%#*}"                              # drop inline + full-line comments
    case "$code" in
      *nohup*node*)
        case "$code" in *"nohup bash"*|*"nohup setsid"*) : ;; *) printf '%s:%s\n' "$lineno" "$code" ;; esac ;;
    esac
  done
}
has_bare_nohup_node() {
  [ -n "$(bare_nohup_offenders "$1")" ]
}

# ── Helper: assert a file pins BOTH PORT and MCP_SERVER_PORT ──────────────────
pins_both_ports() {
  local f="$1"
  grep -qE '(^|[^A-Z_])PORT[=:]' "$f" 2>/dev/null \
    && grep -qE 'MCP_SERVER_PORT[=:]' "$f" 2>/dev/null
}

# ──────────────────────────────────────────────────────────────────────────────
# CHECK 1: ghl-mcp-autostart.sh — supervisor present, no bare nohup, ports pinned
# ──────────────────────────────────────────────────────────────────────────────
if [ -z "${AUTOSTART:-}" ]; then
  _info "ghl-mcp-autostart.sh not found in any known location — nothing to enforce (older bundle or pre-skill-36 box)."
else
  _info "inspecting $AUTOSTART"

  # 1a. Mac path MUST install a launchd KeepAlive plist (com.clawd.ghl-mcp).
  if grep -q 'com.clawd.ghl-mcp' "$AUTOSTART" \
     && grep -q 'KeepAlive' "$AUTOSTART" \
     && grep -q 'RunAtLoad' "$AUTOSTART"; then
    _pass "Mac supervisor: launchd plist com.clawd.ghl-mcp with KeepAlive + RunAtLoad"
  else
    _fail "ghl-mcp-autostart.sh Mac path missing launchd KeepAlive/RunAtLoad supervision (com.clawd.ghl-mcp)"
    FAILURES=$((FAILURES+1))
  fi

  # 1b. VPS path MUST use pm2 (preferred) and persist it (pm2 save).
  if grep -qE '\bpm2\b' "$AUTOSTART" && grep -q 'pm2 save' "$AUTOSTART"; then
    _pass "VPS supervisor: pm2 + 'pm2 save' (fleet-standard, persisted)"
  else
    _fail "ghl-mcp-autostart.sh VPS path does not run under pm2 with 'pm2 save' (fleet-standard supervision)"
    FAILURES=$((FAILURES+1))
  fi

  # 1c. VPS path MUST wire a reboot-resurrect hook (pm2 resurrect via @reboot/startup).
  if grep -q 'pm2 resurrect' "$AUTOSTART" || grep -q 'pm2 startup' "$AUTOSTART"; then
    _pass "VPS reboot-survival: 'pm2 resurrect'/'pm2 startup' hook present"
  else
    _fail "ghl-mcp-autostart.sh VPS path has no reboot-resurrect hook (pm2 resurrect / pm2 startup)"
    FAILURES=$((FAILURES+1))
  fi

  # 1d. NO bare nohup launching node directly (the fleet-killer pattern).
  if has_bare_nohup_node "$AUTOSTART"; then
    _fail "ghl-mcp-autostart.sh contains a BARE 'nohup node …' (unsupervised, dies on teardown). Use pm2/systemd/launchd or a setsid relaunch LOOP wrapped in 'nohup bash'."
    bare_nohup_offenders "$AUTOSTART" | sed 's/^/    offender: /' >&2 || true
    FAILURES=$((FAILURES+1))
  else
    _pass "ghl-mcp-autostart.sh has no bare 'nohup node …' (no unsupervised launch)"
  fi

  # 1e. PORT is pinned explicitly (both PORT and MCP_SERVER_PORT appear).
  if pins_both_ports "$AUTOSTART"; then
    _pass "ghl-mcp-autostart.sh pins BOTH PORT and MCP_SERVER_PORT (no random-port bind)"
  else
    _fail "ghl-mcp-autostart.sh does not pin BOTH PORT and MCP_SERVER_PORT — main.js reads PORT first and will bind a random port."
    FAILURES=$((FAILURES+1))
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# CHECK 2: VPS overlay start-ghl-mcp-server.sh — pm2 + ports + no bare nohup
# (only enforced when the overlay script ships in this bundle / installed tree)
# ──────────────────────────────────────────────────────────────────────────────
if [ -z "${VPS_START:-}" ]; then
  _info "start-ghl-mcp-server.sh (VPS overlay) not found — skipping VPS-overlay supervision check."
else
  _info "inspecting $VPS_START"

  if grep -qE '\bpm2\b' "$VPS_START" && grep -q 'pm2 save' "$VPS_START"; then
    _pass "VPS overlay runs under pm2 + 'pm2 save'"
  else
    _fail "start-ghl-mcp-server.sh (VPS overlay) does not run under pm2 with 'pm2 save'"
    FAILURES=$((FAILURES+1))
  fi

  if grep -q 'pm2 resurrect' "$VPS_START" || grep -q 'pm2 startup' "$VPS_START"; then
    _pass "VPS overlay wires a reboot-resurrect hook"
  else
    _fail "start-ghl-mcp-server.sh (VPS overlay) has no reboot-resurrect hook (pm2 resurrect / pm2 startup)"
    FAILURES=$((FAILURES+1))
  fi

  if has_bare_nohup_node "$VPS_START"; then
    _fail "start-ghl-mcp-server.sh (VPS overlay) contains a BARE 'nohup node …' (unsupervised). Use pm2 or a setsid relaunch LOOP."
    bare_nohup_offenders "$VPS_START" | sed 's/^/    offender: /' >&2 || true
    FAILURES=$((FAILURES+1))
  else
    _pass "VPS overlay has no bare 'nohup node …'"
  fi

  if pins_both_ports "$VPS_START"; then
    _pass "VPS overlay pins BOTH PORT and MCP_SERVER_PORT"
  else
    _fail "start-ghl-mcp-server.sh (VPS overlay) does not pin BOTH PORT and MCP_SERVER_PORT"
    FAILURES=$((FAILURES+1))
  fi
fi

# ── Verdict ───────────────────────────────────────────────────────────────────
if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES GHL-MCP supervision invariant(s) violated — a fresh install could ship an unsupervised / random-port GHL MCP."
  exit 1
fi
_pass "GHL MCP supervision standard holds (proper supervisor, reboot-surviving, PORT pinned)."
exit 0
