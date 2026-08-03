#!/usr/bin/env bash
# qc-assert-ghl-mcp-supervised.sh — v21.5.0
#
# STATIC QC INVARIANT: enforces that the GHL Community MCP (Tier 2, skill 36) is
# configured for PROPER, REBOOT-SURVIVING, PORT-PINNED supervision on a FRESH
# install — so the fleet incident (12/19 boxes down/unsupervised) can NEVER ship
# again. This is the single-source-of-truth logic; scripts/qc-system-integrity.sh
# CHECK X.12 delegates to it.
#
# v21.5.0 adds the five INSTALL-TIME invariants that the 2026-08-02/03 outage
# proved were missing (CHECKS 3-8 below). Supervision alone was never enough:
# every box was supervised the whole time it was deaf.
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

# ──────────────────────────────────────────────────────────────────────────────
# v21.5.0 INSTALL-TIME INVARIANTS (CHECKS 3-8)
#
# The 2026-08-02/03 outage was NOT a supervision failure: every box stayed
# supervised, listening and "healthy" for two days while answering nothing.
# These checks forbid the five installer diseases that produced it.
# ──────────────────────────────────────────────────────────────────────────────

# Executable lines only (strip full-line and inline comments), so a script that
# DOCUMENTS a forbidden pattern in prose does not trip its own gate.
#
# NOTE: these deliberately capture into a variable and match with a HERESTRING
# instead of piping `sed | grep -q`. Under this script's `set -o pipefail`, a
# `grep -q` that matches early closes the pipe, `sed` dies of SIGPIPE (141), and
# pipefail returns that failure — so a pattern that IS present in a large file
# reads as ABSENT. That false-negative would silently disable every check below.
code_lines() { sed 's/#.*$//' "$1" 2>/dev/null; }
code_has()   { local _out; _out="$(code_lines "$1")"; grep -qE "$2" <<< "$_out"; }
code_has_f() { local _out; _out="$(code_lines "$1")"; grep -qF "$2" <<< "$_out"; }

PIN_FILE="$(find_first \
  "$REPO_ROOT/config/ghl-mcp-pin.env" \
  "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
  "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" || true)"

SCRIPTS_TO_CHECK=""
[ -n "${AUTOSTART:-}" ] && SCRIPTS_TO_CHECK="$AUTOSTART"
[ -n "${VPS_START:-}" ] && SCRIPTS_TO_CHECK="$SCRIPTS_TO_CHECK $VPS_START"

# ── CHECK 3: SUPPLY-CHAIN PIN (D-pin) ─────────────────────────────────────────
# The executed autostart used to `git pull --ff-only` / clone `--depth 1` and run
# whatever `main` pointed at. Upstream force-pushes rewritten history, so a
# floating checkout is not reproducible and is not reviewable.
if [ -z "$SCRIPTS_TO_CHECK" ]; then
  _info "no autostart scripts present — skipping pin/profile/build invariants."
else
  if [ -z "${PIN_FILE:-}" ]; then
    _fail "config/ghl-mcp-pin.env is missing — there is no single source of truth for the vetted community-MCP commit."
    FAILURES=$((FAILURES+1))
  elif grep -qE '^GHL_MCP_VETTED_COMMIT="[0-9a-f]{40}"' "$PIN_FILE"; then
    _pass "pin config declares a FULL 40-char vetted commit ($(basename "$PIN_FILE"))"
  else
    _fail "config/ghl-mcp-pin.env does not declare GHL_MCP_VETTED_COMMIT as a full 40-char SHA (a short SHA or branch name is not a pin)."
    FAILURES=$((FAILURES+1))
  fi

  for f in $SCRIPTS_TO_CHECK; do
    b="$(basename "$f")"
    if code_has_f "$f" "GHL_MCP_VETTED_COMMIT"; then
      _pass "$b pins the checkout to GHL_MCP_VETTED_COMMIT"
    else
      _fail "$b does not pin the community-MCP checkout to GHL_MCP_VETTED_COMMIT (floating HEAD = supply-chain roulette)."
      FAILURES=$((FAILURES+1))
    fi
    if code_has "$f" 'git .*pull'; then
      _fail "$b runs 'git pull' on the third-party MCP — that is a floating checkout; check out the pinned commit instead."
      FAILURES=$((FAILURES+1))
    else
      _pass "$b never 'git pull's the third-party MCP"
    fi
    if code_has "$f" 'git clone[^|]*--depth'; then
      _fail "$b clones with --depth (a shallow clone frequently cannot resolve the pinned SHA)."
      FAILURES=$((FAILURES+1))
    else
      _pass "$b does not shallow-clone (pinned SHA stays resolvable)"
    fi
  done

  # ── CHECK 4: TOOL PROFILE PINNED IN EVERY LAUNCH SURFACE (D2) ──────────────
  # Upstream default GHL_TOOL_PROFILE=full serves the whole 858-tool catalogue.
  for f in $SCRIPTS_TO_CHECK; do
    b="$(basename "$f")"
    if code_has_f "$f" "GHL_TOOL_PROFILE"; then
      _pass "$b sets GHL_TOOL_PROFILE explicitly (never the 858-tool default)"
    else
      _fail "$b does not set GHL_TOOL_PROFILE — the server will serve the FULL 858-tool surface."
      FAILURES=$((FAILURES+1))
    fi
  done
  if [ -n "${AUTOSTART:-}" ]; then
    if code_has_f "$AUTOSTART" "<key>GHL_TOOL_PROFILE</key>" && code_has_f "$AUTOSTART" "GHL_TOOL_PROFILE:"; then
      _pass "autostart pins the tool profile in BOTH the launchd plist and the pm2 ecosystem"
    else
      _fail "ghl-mcp-autostart.sh must set GHL_TOOL_PROFILE in EVERY launch surface (launchd plist AND pm2 ecosystem AND systemd AND the server .env)."
      FAILURES=$((FAILURES+1))
    fi
  fi

  # ── CHECK 5: CRASH-ONLY RESTART SEMANTICS (D3) ─────────────────────────────
  # main.js exits 1 on a bad PIT at boot. An unconditional restart policy turns a
  # rotated token into a 10s relaunch loop that burns the box.
  if [ -n "${AUTOSTART:-}" ]; then
    if code_has_f "$AUTOSTART" "<key>KeepAlive</key><true/>"; then
      _fail "ghl-mcp-autostart.sh writes an UNCONDITIONAL launchd KeepAlive=true — use the crash-only dict (SuccessfulExit=false / Crashed=true)."
      FAILURES=$((FAILURES+1))
    elif code_has_f "$AUTOSTART" "<key>SuccessfulExit</key><false/>"; then
      _pass "Mac restart policy is CRASH-ONLY (KeepAlive dict, SuccessfulExit=false)"
    else
      _fail "ghl-mcp-autostart.sh launchd plist has no crash-only KeepAlive dict (SuccessfulExit=false)."
      FAILURES=$((FAILURES+1))
    fi
  fi
  for f in $SCRIPTS_TO_CHECK; do
    b="$(basename "$f")"
    if code_has_f "$f" "stop_exit_codes"; then
      _pass "$b pm2 config sets stop_exit_codes (a clean exit is not restarted)"
    else
      _fail "$b pm2 config does not set stop_exit_codes: [0] — a bad-token clean exit would relaunch forever."
      FAILURES=$((FAILURES+1))
    fi
    if code_has_f "$f" "Restart=always"; then
      _fail "$b systemd unit uses Restart=always — use Restart=on-failure (crash-only)."
      FAILURES=$((FAILURES+1))
    fi
  done

  # ── CHECK 6: BUILD HYGIENE (D1 + D4) ───────────────────────────────────────
  # Upstream's build rm -rf's dist BEFORE compiling and walks every .ts under
  # src/ (including orphaned node_modules), so a failed build leaves a broken
  # partial dist. Build a `git archive` of the pinned commit in a temp dir and
  # swap dist/ only after verifying the artifact.
  for f in $SCRIPTS_TO_CHECK; do
    b="$(basename "$f")"
    if code_has_f "$f" "git -C"  && code_has_f "$f" "archive"; then
      _pass "$b builds from a 'git archive' of the pinned commit (immune to working-tree junk)"
    else
      _fail "$b does not build from a 'git archive' of the pinned commit — a dirty working tree can break the build."
      FAILURES=$((FAILURES+1))
    fi
    if code_has "$f" 'rm -rf [^;]*/dist("|'"'"'|[[:space:]]|$)'; then
      _fail "$b deletes dist/ outright — never rm -rf dist before a SUCCESSFUL build (that is how a failed build leaves a box with no server at all)."
      FAILURES=$((FAILURES+1))
    else
      _pass "$b never rm -rf's dist/ before a successful build"
    fi
    if code_has_f "$f" "connect(transport)"; then
      _pass "$b asserts the built artifact contains the MCP transport wiring (stale-dist deafness guard)"
    else
      _fail "$b does not verify the built dist/main.js contains 'connect(transport)' — a stale compiled dist would ship again."
      FAILURES=$((FAILURES+1))
    fi
  done

  # ── CHECK 7: LIVENESS PROBE EXISTS AND ASSERTS A RESPONSE (D5) ─────────────
  PROBE="$(find_first \
    "$SELF_DIR/ghl-mcp-probe.sh" \
    "$HOME/.openclaw/skills/scripts/ghl-mcp-probe.sh" \
    "/data/.openclaw/skills/scripts/ghl-mcp-probe.sh" || true)"
  if [ -z "${PROBE:-}" ]; then
    _fail "scripts/ghl-mcp-probe.sh is missing — nothing asserts that the MCP ANSWERS (KeepAlive cannot detect alive-but-deaf)."
    FAILURES=$((FAILURES+1))
  else
    if grep -qF '"method":"initialize"' "$PROBE" && grep -qF 'serverInfo' "$PROBE"; then
      _pass "ghl-mcp-probe.sh POSTs a JSON-RPC initialize and requires a serverInfo response"
    else
      _fail "ghl-mcp-probe.sh does not assert a JSON-RPC response (a GET /health is served even by a deaf server)."
      FAILURES=$((FAILURES+1))
    fi
    if [ -n "${AUTOSTART:-}" ]; then
      if code_has_f "$AUTOSTART" "ghl-mcp-probe.sh"; then
        _pass "autostart wires the liveness probe (post-install + periodic)"
      else
        _fail "ghl-mcp-autostart.sh does not wire ghl-mcp-probe.sh — the deaf-server state would go undetected again."
        FAILURES=$((FAILURES+1))
      fi
    fi
  fi

  # ── CHECK 9: LOG ROTATION (fleet gap, 2026-08-03) ──────────────────────────
  # Nothing in the fleet ever rotated this server's logs: 5.4 MB of
  # ghl-mcp/stderr.log on the operator box and 2.2 MB on a second fleet box,
  # both growing since May. Rotation MUST be copytruncate-style: the supervisor
  # holds an open
  # fd, so renaming the file leaves the server writing to an orphaned inode.
  for f in $SCRIPTS_TO_CHECK; do
    b="$(basename "$f")"
    if code_has_f "$f" "GHL_MCP_LOG_MAX_BYTES"; then
      _pass "$b caps + rotates the MCP logs (GHL_MCP_LOG_MAX_BYTES)"
    else
      _fail "$b does not rotate the MCP logs — ghl-mcp stderr.log grows without bound (5.4 MB observed fleet-side)."
      FAILURES=$((FAILURES+1))
    fi
  done
  if [ -n "${AUTOSTART:-}" ]; then
    if code_has_f "$AUTOSTART" "<key>GHL_MCP_LOG_DIR</key>"; then
      _pass "autostart passes the log dir into the launchd service definition"
    else
      _fail "ghl-mcp-autostart.sh does not pass GHL_MCP_LOG_DIR into the launchd plist — the launcher cannot rotate what it cannot find."
      FAILURES=$((FAILURES+1))
    fi
  fi

  # ── CHECK 8: TIER 2 STAYS ON-DEMAND (D2) ──────────────────────────────────
  # skill 36 v1.1.0 doctrine + qc-ghl-mcp-setup.sh Section D + 36/wire.sh M2 all
  # require ghl-community-mcp to be ABSENT from mcp.servers. The autostart used
  # to re-register it seconds after wire.sh removed it, putting the whole tool
  # catalogue back into every agent init and making every init pay the full
  # connectionTimeoutMs whenever the server was down or deaf.
  if [ -n "${AUTOSTART:-}" ]; then
    if code_has "$AUTOSTART" 'openclaw mcp set +ghl-community-mcp'; then
      _fail "ghl-mcp-autostart.sh REGISTERS ghl-community-mcp in mcp.servers — Tier 2 is on-demand curl (skill 36 v1.1.0); registration contradicts wire.sh M2 and qc-ghl-mcp-setup.sh Section D."
      FAILURES=$((FAILURES+1))
    else
      _pass "autostart leaves Tier 2 unregistered (on-demand curl, no per-init tool-catalogue tax)"
    fi
  fi
fi

# ── Verdict ───────────────────────────────────────────────────────────────────
if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES GHL-MCP install/supervision invariant(s) violated — a fresh install could ship an unsupervised, unpinned, 858-tool, deaf or crash-looping GHL MCP."
  exit 1
fi
_pass "GHL MCP install + supervision standard holds (supervised, reboot-surviving, PORT pinned, commit pinned, profile pinned, crash-only, build-verified, liveness-probed)."
exit 0
