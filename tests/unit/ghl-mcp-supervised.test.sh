#!/usr/bin/env bash
# tests/unit/ghl-mcp-supervised.test.sh — v22.0.0
#
# Verifies the GHL MCP RETIREMENT invariant gate
# (scripts/qc-assert-ghl-mcp-supervised.sh — v22.0.0).
#
# WHY THIS FILE WAS REWRITTEN (v21.6.0 -> v22.0.0)
#   The gate used to enforce that the community MCP was PROPERLY SUPERVISED
#   (KeepAlive, pm2 resurrect, pinned commit, tool profile, bind guard, log
#   rotation …). W07/GU-019 RETIRED the service, and the gate now enforces the
#   retirement contract instead:
#     CHECK 1  install.sh must not invoke the community start path
#     CHECK 2  the update path must carry the ordered retirement transaction
#              (entry point, VERIFIED_OFF, MIGRATION_FAILED, and the stages
#              inventory/stage/archive/disable/stop/verify/receipt)
#     CHECK 3  any lifecycle script still shipped must be an inert tombstone
#              (a retirement refusal marker), or be absent entirely
#     CHECK 4  no shipped script may start, restart, register, schedule or
#              resurrect the community MCP — the FORBIDDEN_PATTERNS scan, plus
#              the INVOKE_RE pass that catches a plain
#              `bash scripts/ghl-mcp-autostart.sh` (no supervisor verb on the
#              line), which is the shape every supervisor-verb pattern missed
#     CHECK 5  the official ghl-mcp (Tier 1) registration must survive
#   Supervision QUALITY of a service that never runs is no longer a shipped-code
#   property, so the old content cases were re-cast onto the invariants the gate
#   actually enforces. Every case below still asserts a real discrimination and
#   every case can still go red (see evidence/QC/composed/last-mile-ci-tests.md
#   for the one production change that reddens each one).
#
# HERMETIC (v22.0.0 — this is a bug fix, not a rewrite of intent)
#   The v21 harness wrote its fixtures into a temp tree that was NOT a repo
#   layout, so the gate took its BOX branch and read $HOME/.openclaw — the LIVE
#   operator box. Every sandbox case returned 1 for a reason that had nothing to
#   do with the fixture: on a box that still carried the retired scripts the
#   negatives "passed" and the positives (A2/C/D) could never pass; on a clean
#   CI runner the same file inverted (positives pass, negatives fail). The
#   harness now builds a real REPO layout (install.sh + update-skills.sh +
#   36-ghl-mcp-setup/ at the sandbox root) with a SANDBOXED HOME, so the result
#   depends on the fixture only.
#
# Case letters are kept for continuity with v12.24.0/v21.6.0; the subject of
# each is whatever the CURRENT gate enforces. The four originals that survived:
#   (A) The SHIPPED repo scripts PASS (exit 0).
#   (B) A lifecycle script that ships WITHOUT a retirement refusal marker FAILS.
#   (C) A comment that merely DOCUMENTS a removed launch surface PASSES.
#   (D) `setsid nohup bash "$SUP"` PASSES; invoking the lifecycle script by
#       name, or naming the retired service on a setsid line, FAILS.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-ghl-mcp-supervised.sh"
PROBE_SRC="$REPO_ROOT/scripts/ghl-mcp-probe.sh"
PIN_SRC="$REPO_ROOT/config/ghl-mcp-pin.env"
RUNTIME_SRC="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-supervised.test.sh (v22.0.0) ==="
echo ""

if [ ! -f "$GATE" ]; then
  echo "  FAIL: gate script not found at $GATE"
  exit 1
fi

# ── (A) Shipped repo scripts PASS ─────────────────────────────────────────────
if bash "$GATE" >/dev/null 2>&1; then
  pass "(A) shipped repo autostart scripts pass the retirement + install gate"
else
  fail "(A) shipped repo autostart scripts FAIL the gate (regression!)"
  bash "$GATE" 2>&1 | grep -F 'INVARIANT VIOLATED' | sed 's/^/        /'
fi

# ── Sandbox harness ───────────────────────────────────────────────────────────
# _run_sandbox <autostart-body> <vps-body> <helper-body|-> [mode...]
#
#   $1  written to scripts/ghl-mcp-autostart.sh      (CHECK 3 name)
#   $2  written to platform/vps/36-ghl-mcp-setup-scripts/
#                                           start-ghl-mcp-server.sh (CHECK 3)
#   $3  written to scripts/legacy-community-supervisor.sh — a shipped script
#       that is NOT a CHECK 3 lifecycle name, so CHECK 4 scans its content
#       (a marker-less lifecycle name would trip CHECK 3 and mask which check
#       actually fired). "-" ships nothing.
#   modes:
#       no-probe           omit scripts/ghl-mcp-probe.sh
#       no-runtime-gate    omit scripts/ghl-mcp-assert-runtime.sh
#       no-updater         omit update-skills.sh (CHECK 2 then reads only the
#                          fixture, which is how the token cases isolate it)
#       no-tier1           omit update-skills.sh + 36-ghl-mcp-setup/ (CHECK 5)
#       install-mentions   install.sh invokes the community start path (CHECK 1)
#       strip-probe-marker / strip-runtime-marker / strip-vps-marker
#                          drop the retirement marker from that delivered file
#
# Sets SBX_RC and SBX_OUT. The sandbox is a REPO layout with a sandboxed HOME,
# so the live box can never decide the answer.
SBX_RC=0
SBX_OUT=""
_strip_markers() {   # remove every line carrying a retirement refusal marker
  grep -vE 'GHL_MCP_RETIRED|RETIRED_VERIFIED_OFF|START_REFUSED_RETIRED' "$1" > "$1.tmp" 2>/dev/null \
    && mv "$1.tmp" "$1"
}
_run_sandbox() {
  local autostart_body="$1" vps_body="$2" helper_body="$3"; shift 3
  local modes=" $* " tmp
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts" "$tmp/config" "$tmp/36-ghl-mcp-setup" \
           "$tmp/platform/vps/36-ghl-mcp-setup-scripts" "$tmp/home"
  cp "$GATE" "$tmp/scripts/qc-assert-ghl-mcp-supervised.sh"
  cp "$REPO_ROOT/install.sh" "$tmp/install.sh"
  case "$modes" in *" no-updater "*|*" no-tier1 "*) ;; *) cp "$REPO_ROOT/update-skills.sh" "$tmp/update-skills.sh" ;; esac
  case "$modes" in *" no-tier1 "*) ;; *) cp -Rp "$REPO_ROOT/36-ghl-mcp-setup/." "$tmp/36-ghl-mcp-setup/" ;; esac
  case "$modes" in
    *" install-mentions "*)
      printf 'bash "$HOME/.openclaw/scripts/ghl-mcp-autostart.sh" start\n' > "$tmp/install.sh" ;;
  esac
  [ -f "$PIN_SRC" ] && cp "$PIN_SRC" "$tmp/config/ghl-mcp-pin.env"
  case "$modes" in *" no-probe "*) ;; *) cp "$PROBE_SRC" "$tmp/scripts/ghl-mcp-probe.sh" ;; esac
  case "$modes" in *" no-runtime-gate "*) ;; *) cp "$RUNTIME_SRC" "$tmp/scripts/ghl-mcp-assert-runtime.sh" ;; esac
  case "$modes" in *" strip-probe-marker "*)    _strip_markers "$tmp/scripts/ghl-mcp-probe.sh" ;; esac
  case "$modes" in *" strip-runtime-marker "*)  _strip_markers "$tmp/scripts/ghl-mcp-assert-runtime.sh" ;; esac
  printf '%s\n' "$autostart_body" > "$tmp/scripts/ghl-mcp-autostart.sh"
  printf '%s\n' "$vps_body" > "$tmp/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
  case "$modes" in *" strip-vps-marker "*) _strip_markers "$tmp/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" ;; esac
  if [ "$helper_body" != "-" ]; then
    printf '%s\n' "$helper_body" > "$tmp/scripts/legacy-community-supervisor.sh"
  fi
  SBX_OUT="$(HOME="$tmp/home" bash "$tmp/scripts/qc-assert-ghl-mcp-supervised.sh" 2>&1)"
  SBX_RC=$?
  rm -rf "$tmp"
}
# _trip <message-fragment> — true when the gate named that specific violation.
# Asserting on the message (not just rc) is what proves WHICH check fired.
_trip() { case "$SBX_OUT" in *"$1"*) return 0 ;; *) return 1 ;; esac; }

# ── The synthetic tombstone pair ──────────────────────────────────────────────
# What a CORRECT tree looks like after the retirement: the launcher and the VPS
# start script are inert tombstones. The refusal marker lives in the header —
# the gate scans RAW text for it ("intent declarations legitimately live in the
# file header"), while CHECK 2 reads code only, so the retirement TRANSACTION
# tokens are written as code and each one can be removed on its own below.
GOOD_AUTOSTART='#!/usr/bin/env bash
# com.clawd.ghl-mcp launchd plist — RETIRED tombstone.
# The start path reports START_REFUSED_RETIRED and exits; nothing is built.
# GHL_MCP_RETIRED: this file is documentation, never a launch surface.
GHL_MCP_RETIRE_ENTRY="--retire"
GHL_MCP_RETIRE_STAGES="inventory stage archive disable stop verify receipt"
GHL_MCP_RETIRE_VERIFIED_OFF="VERIFIED_OFF"
GHL_MCP_RETIRE_FAILED="MIGRATION_FAILED"
git -C "$MCP_DIR" checkout --detach --force "$GHL_MCP_VETTED_COMMIT"
git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp"
echo "<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict> <key>RunAtLoad</key><true/>"
echo "<key>GHL_TOOL_PROFILE</key><string>curated</string>"
echo "GHL_TOOL_PROFILE: \"curated\","
echo "stop_exit_codes: [0],"
echo "PORT=8765 MCP_SERVER_PORT=8765"
echo "<key>GHL_MCP_LOG_DIR</key><string>$HOME/Library/Logs/ghl-mcp</string>"
GHL_MCP_LOG_MAX_BYTES=10485760
bash "$SELF_DIR/ghl-mcp-probe.sh" --once
pm2 start ecosystem.config.js
pm2 save
pm2 startup
crontab -l | grep "pm2 resurrect"
GHL_MCP_BIND_HOST="127.0.0.1"
cat > "$MCP_DIR/.ghl-mcp-bind-guard.cjs" <<GUARDEOF
net.Server.prototype.listen = function () {};
GUARDEOF
NODE_OPTIONS="--require \"$BIND_GUARD\" $NODE_OPTIONS"
npm ci --ignore-scripts --no-audit --no-fund
GHL_MCP_PIN_VETTED_VERDICT="${GHL_MCP_PIN_VETTED_VERDICT:-}"
[ "$GHL_MCP_PIN_VETTED_VERDICT" = "CLEAN" ] || { echo "STATUS: PIN_UNVETTED"; exit 0; }
[ -z "$_PIN_FILE" ] && { echo "STATUS: PIN_UNVERIFIED"; exit 0; }
[ -n "${GHL_MCP_PIN_OVERRIDE:-}" ] && [ -z "${GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST:-}" ] && exit 0'
GOOD_VPS='#!/usr/bin/env bash
# start-ghl-mcp-server.sh — RETIRED tombstone (GHL_MCP_RETIRED).
# START_REFUSED_RETIRED: this file no longer starts the community MCP.
GHL_MCP_RETIRE_ENTRY="--retire"
GHL_MCP_RETIRE_STAGES="inventory stage archive disable stop verify receipt"
GHL_MCP_RETIRE_VERIFIED_OFF="VERIFIED_OFF"
GHL_MCP_RETIRE_FAILED="MIGRATION_FAILED"
git -C "$MCP_DIR" checkout --detach --force "$GHL_MCP_VETTED_COMMIT"
git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp"
echo "GHL_TOOL_PROFILE: \"curated\","
echo "stop_exit_codes: [0],"
GHL_MCP_LOG_MAX_BYTES=10485760
pm2 start ecosystem.config.js
pm2 save
pm2 startup
echo "PORT=8765 MCP_SERVER_PORT=8765"
echo "@reboot pm2 resurrect"
GHL_MCP_BIND_HOST="127.0.0.1"'

# Sanity: the synthetic GOOD pair must itself pass, otherwise every negative
# case below would "pass" for the wrong reason.
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" -
if [ "$SBX_RC" = "0" ]; then
  pass "(A2) the synthetic fully-correct tombstone pair passes the gate (fixtures match the current gate)"
else
  fail "(A2) the synthetic fully-correct tombstone pair FAILED the gate (exit $SBX_RC) — fixtures are stale vs the gate"
  printf '%s\n' "$SBX_OUT" | grep -F 'INVARIANT VIOLATED' | sed 's/^/        /'
fi

# ── (B) A lifecycle script without a retirement refusal marker FAILS ─────────
# The realistic regression: the pre-retirement live launcher is shipped again.
# It cannot pass as documentation because it never declared itself inert.
NO_MARKER_AUTOSTART="$(printf '%s\n' "$GOOD_AUTOSTART" \
  | grep -vE 'GHL_MCP_RETIRED|RETIRED_VERIFIED_OFF|START_REFUSED_RETIRED')"
_run_sandbox "$NO_MARKER_AUTOSTART" "$GOOD_VPS" -
if [ "$SBX_RC" = "1" ] && _trip "scripts/ghl-mcp-autostart.sh still ships without a retirement refusal marker"; then
  pass "(B) an autostart that ships WITHOUT a retirement refusal marker FAILS (CHECK 3 names the file)"
else
  fail "(B) a marker-less autostart produced exit $SBX_RC — a live launcher could ship again as an 'inert tombstone'"
fi

# ── (C) Comment mentioning a removed launch surface is NOT a false positive ──
# The gate strips full-line and inline comments (_code_of) before scanning, so
# prose documenting a removed surface must never trip CHECK 4.
DOC_HELPER='#!/usr/bin/env bash
# NOTE: we REMOVED the bare nohup node path (it killed the fleet).
# LEGACY: "pm2 restart ghl-community-mcp" was removed by the retirement.'
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" "$DOC_HELPER"
if [ "$SBX_RC" = "0" ]; then
  pass "(C) a shipped script that only DOCUMENTS a removed launch surface in a comment PASSES (no false positive)"
else
  fail "(C) comment-only documentation tripped the gate (exit $SBX_RC) — false positive"
fi

# ── (D) What the launch-surface rules require now ─────────────────────────────
# Three halves, one contract. A supervised relaunch loop that names NOTHING is
# fine; the two shapes the gate must still catch are (1) INVOKING the community
# lifecycle script by name — the blind spot where every supervisor-verb pattern
# looked for `pm2`/`launchctl`/`systemctl` on the same line and a plain
# `bash scripts/ghl-mcp-autostart.sh` matched nothing — and (2) a setsid line
# that names the RETIRED SERVICE.
LOOP_HELPER='#!/usr/bin/env bash
setsid nohup bash "$SUP" >/dev/null 2>&1 &'
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" "$LOOP_HELPER"
_d_loop="$SBX_RC"
INVOKE_HELPER='#!/usr/bin/env bash
bash "$SELF_DIR/ghl-mcp-autostart.sh"'
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" "$INVOKE_HELPER"
_d_invoke="$SBX_RC"; _d_invoke_trip=$(_trip "is a live community-MCP resurrection surface" && echo yes || echo no)
SERVICE_HELPER='#!/usr/bin/env bash
setsid nohup bash -c "serve ghl-community-mcp" >/dev/null 2>&1 &'
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" "$SERVICE_HELPER"
_d_service="$SBX_RC"; _d_service_trip=$(_trip "is a live community-MCP resurrection surface" && echo yes || echo no)
if [ "$_d_loop" = "0" ] && [ "$_d_invoke" = "1" ] && [ "$_d_invoke_trip" = "yes" ] \
   && [ "$_d_service" = "1" ] && [ "$_d_service_trip" = "yes" ]; then
  pass "(D) 'setsid nohup bash \"\$SUP\"' PASSES; invoking the lifecycle script by name and naming the service on a setsid line both FAIL"
else
  fail "(D) launch-surface contract broken: loop=$_d_loop (want 0), invoke=$_d_invoke/$_d_invoke_trip (want 1/yes), service=$_d_service/$_d_service_trip (want 1/yes)"
fi

# ── (E)-(I),(K),(L) CHECK 4: every resurrection surface in a shipped script ──
# Each case plants ONE forbidden shape in a NON-lifecycle script and asserts on
# the gate's own violation line, so the message — not just the exit code —
# proves which rule fired.
_C4() {  # _C4 <label> <shape> <expected-pattern-fragment>
  local label="$1" shape="$2" frag="$3"
  _run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" "#!/usr/bin/env bash
${shape}"
  if [ "$SBX_RC" = "1" ] && _trip "is a live community-MCP resurrection surface" && _trip "$frag"; then
    pass "$label"
  else
    fail "$label — exit $SBX_RC; expected the CHECK 4 line for '$frag'"
  fi
}
_C4 "(E) 'launchctl kickstart … com.clawd.ghl-mcp' FAILS (a launchd kickstart is a live relaunch)" \
    'launchctl kickstart -k gui/501/com.clawd.ghl-mcp' \
    'launchctl kickstart -k gui/501/com.clawd.ghl-mcp'
_C4 "(F) 'launchctl bootstrap … com.clawd.ghl-mcp' FAILS (a new launchd load is a resurrection)" \
    'launchctl bootstrap gui/501 "$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist"' \
    'launchctl bootstrap gui/501'
_C4 "(G) 'pm2 start ghl-community-mcp' FAILS (Tier 2 must never be started again)" \
    'pm2 start ghl-community-mcp' \
    'pm2 start ghl-community-mcp'
_C4 "(H) 'pm2 restart ghl-community-mcp' FAILS (a restart is a resurrection)" \
    'pm2 restart ghl-community-mcp' \
    'pm2 restart ghl-community-mcp'
_C4 "(I) 'pm2 resurrect … ghl' FAILS (pm2 resurrect would bring the dead service back)" \
    'pm2 resurrect --only ghl-mcp' \
    'pm2 resurrect --only ghl-mcp'

# ── (J) A bundle with no scripts/ghl-mcp-probe.sh PASSES ─────────────────────
# v21.6.0 asserted the opposite ("a missing liveness probe FAILS"). Absence is
# now the RETIRED state: the probe heals a service that no longer exists.
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - no-probe
if [ "$SBX_RC" = "0" ]; then
  pass "(J) a bundle that omits scripts/ghl-mcp-probe.sh PASSES (absence is the retired state, not a defect)"
else
  fail "(J) a probe-less bundle was rejected (exit $SBX_RC) — the gate silently still requires the retired probe"
fi

# ── (K) Re-registering Tier 2 in mcp.servers -> FAILS ────────────────────────
_C4 "(K) re-registering ghl-community-mcp in mcp.servers FAILS (Tier 2 is on-demand curl)" \
    'openclaw mcp set ghl-community-mcp "{}"' \
    'openclaw mcp set ghl-community-mcp'

# ── (L) 'systemctl start ghl-mcp' -> FAILS ───────────────────────────────────
_C4 "(L) 'systemctl start ghl-mcp' FAILS (a systemd start is a resurrection on the VPS fleet)" \
    'systemctl start ghl-mcp.service' \
    'systemctl start ghl-mcp.service'

# ── (M),(M2),(M3) CHECK 3 is enforced per delivered lifecycle file ───────────
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - strip-probe-marker
if [ "$SBX_RC" = "1" ] && _trip "scripts/ghl-mcp-probe.sh still ships without a retirement refusal marker"; then
  pass "(M) a delivered scripts/ghl-mcp-probe.sh without a retirement marker FAILS"
else
  fail "(M) a marker-less probe was accepted (exit $SBX_RC)"
fi

_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - strip-runtime-marker
if [ "$SBX_RC" = "1" ] && _trip "scripts/ghl-mcp-assert-runtime.sh still ships without a retirement refusal marker"; then
  pass "(M2) a delivered scripts/ghl-mcp-assert-runtime.sh without a retirement marker FAILS"
else
  fail "(M2) a marker-less runtime gate was accepted (exit $SBX_RC)"
fi

_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - strip-vps-marker
if [ "$SBX_RC" = "1" ] && _trip "platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh still ships without a retirement refusal marker"; then
  pass "(M3) a delivered VPS start-ghl-mcp-server.sh without a retirement marker FAILS"
else
  fail "(M3) a marker-less VPS start script was accepted (exit $SBX_RC)"
fi

# ── (N) CHECK 1: install.sh must not invoke the community start path ─────────
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - install-mentions
if [ "$SBX_RC" = "1" ] && _trip "install.sh still invokes the community MCP start path"; then
  pass "(N) an install.sh that invokes ghl-mcp-autostart FAILS (fresh installs must omit Tier 2 entirely)"
else
  fail "(N) an installer that starts the community MCP was accepted (exit $SBX_RC)"
fi

# ── (O) CHECK 5: the official Tier 1 registration must survive ───────────────
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - no-tier1
if [ "$SBX_RC" = "1" ] && _trip "no shipped surface registers the official ghl-mcp"; then
  pass "(O) a tree with no official ghl-mcp (Tier 1) registration surface FAILS (retirement removes Tier 2 ONLY)"
else
  fail "(O) a Tier-1-less tree was accepted (exit $SBX_RC) — retirement could silently take the official MCP too"
fi

# ── (P),(Q),(R),(S) CHECK 2: the ordered retirement transaction ──────────────
# 'no-updater' drops update-skills.sh, so CHECK 2 reads the fixture alone and
# each token can be removed without masking the check behind the updater.
_C2() {  # _C2 <label> <fixture-with-token-removed> <message-fragment>
  local label="$1" body="$2" frag="$3"
  _run_sandbox "$body" "$GOOD_VPS" - no-updater
  if [ "$SBX_RC" = "1" ] && _trip "$frag"; then
    pass "$label"
  else
    fail "$label — exit $SBX_RC; expected the CHECK 2 line '$frag'"
  fi
}
_C2 "(P) an update path with NO retirement entry point FAILS (deleting the scripts is not a migration)" \
    "$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_MCP_RETIRE_ENTRY')" \
    "declares NO retirement entry point"
_C2 "(Q) an update path that never writes VERIFIED_OFF FAILS (the receipt cannot prove a retirement)" \
    "$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_MCP_RETIRE_VERIFIED_OFF')" \
    "never writes the terminal state VERIFIED_OFF"
_C2 "(R) an update path that never writes MIGRATION_FAILED FAILS (a failed migration must be distinguishable)" \
    "$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_MCP_RETIRE_FAILED')" \
    "never writes the terminal state MIGRATION_FAILED"
_C2 "(S) an update path missing the ordered transaction stages FAILS (inventory/stage/archive/…/receipt)" \
    "$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_MCP_RETIRE_STAGES')" \
    "the ordered retirement transaction is missing the 'inventory' stage"

# ── (T) A bundle with no scripts/ghl-mcp-assert-runtime.sh PASSES ────────────
# v21.6.0 asserted the opposite ("static-only cannot see the installed
# service"). The runtime assertion exists to police a RUNNING service; with the
# service retired its absence is the correct shipped state.
_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" - no-runtime-gate
if [ "$SBX_RC" = "0" ]; then
  pass "(T) a bundle with no scripts/ghl-mcp-assert-runtime.sh PASSES (absence is the retired state)"
else
  fail "(T) a runtime-gate-less bundle was rejected (exit $SBX_RC) — the gate silently still requires the retired runtime assert"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
