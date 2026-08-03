#!/usr/bin/env bash
# tests/unit/ghl-mcp-assert-runtime.test.sh — v21.6.0
#
# Proves scripts/ghl-mcp-assert-runtime.sh (R4) in BOTH directions against a
# SIMULATED BOX LAYOUT — a correct installed service must PASS, and each single
# mutation of that service must FAIL with the right diagnosis.
#
# WHY BOTH DIRECTIONS. A gate that only ever says FAIL is useless; a gate that
# only ever says PASS is worse, and that is precisely what shipped in v21.5.0:
# qc-assert-ghl-mcp-supervised.sh reads the SHIPPED SCRIPT, so on 2026-08-03 it
# would have reported PASS for a box whose LIVE service had KeepAlive=<true/>,
# GHL_TOOL_PROFILE=full, 859 tools, no build stamp, an unrotated 5.4 MB
# stderr.log and ghl-community-mcp still registered in mcp.servers. Every
# mutation below is one of those observed real-world states.
#
# ISOLATION. The simulated box uses port 18765, not 8765, so the test can never
# be answered by (or fail because of) a real GHL MCP running on the machine
# executing it. The service definition, MCP dir, log dir, openclaw.json and
# both plists are all redirected into a temp dir via the script's documented
# override env vars.
#
# Exit 0 = all cases behaved. Exit 1 = one or more did not (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_SRC="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-assert-runtime.test.sh (v21.6.0) ==="
echo ""

if [ ! -f "$GATE_SRC" ]; then
  echo "  FAIL: runtime gate not found at $GATE_SRC"
  exit 1
fi

SIM_PORT=18765
SIM_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"

# ── Build a simulated box. $1 = mutation name ("" = fully correct). ──────────
# Echoes the sandbox root; caller runs _run_gate on it.
_make_box() {
  local mut="${1:-}" tmp
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts" "$tmp/config" "$tmp/mcp" "$tmp/logs" "$tmp/agents"
  cp "$GATE_SRC" "$tmp/scripts/ghl-mcp-assert-runtime.sh"

  # The pin — the EXPECTATION the running service is compared against.
  cat > "$tmp/config/ghl-mcp-pin.env" <<EOF
GHL_MCP_VETTED_COMMIT="$SIM_COMMIT"
GHL_MCP_TOOL_PROFILE="curated"
GHL_MCP_PORT="$SIM_PORT"
GHL_MCP_EXPECT_MIN_TOOLS="1"
GHL_MCP_EXPECT_MAX_TOOLS="200"
GHL_MCP_LOG_MAX_BYTES="10485760"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"
EOF

  # The launcher + build stamp (correct unless mutated).
  : > "$tmp/mcp/.ghl-mcp-launch.sh"
  local stamp_commit="$SIM_COMMIT"
  [ "$mut" = "stale-build" ] && stamp_commit="0000000000000000000000000000000000000000"
  if [ "$mut" != "no-stamp" ]; then
    printf '{\n  "commit": "%s",\n  "profile": "curated"\n}\n' "$stamp_commit" > "$tmp/mcp/.ghl-mcp-build.json"
  fi

  # ---- the INSTALLED launchd service definition ----
  local prog="$tmp/mcp/.ghl-mcp-launch.sh"
  [ "$mut" = "direct-node" ] && prog="$tmp/mcp/dist/main.js"
  local keepalive='<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/><key>Crashed</key><true/></dict>'
  [ "$mut" = "keepalive-true" ] && keepalive='<key>KeepAlive</key><true/>'
  local throttle=300
  [ "$mut" = "hot-throttle" ] && throttle=10
  local profile=curated
  [ "$mut" = "profile-full" ] && profile=full
  local logdirline="        <key>GHL_MCP_LOG_DIR</key><string>$tmp/logs</string>"
  [ "$mut" = "no-log-dir" ] && logdirline=""
  local portline="        <key>PORT</key><string>${SIM_PORT}</string>"
  [ "$mut" = "unpinned-port" ] && portline=""

  cat > "$tmp/com.clawd.ghl-mcp.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp</string>
    <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>${prog}</string>
    </array>
    <key>EnvironmentVariables</key><dict>
${portline}
        <key>MCP_SERVER_PORT</key><string>${SIM_PORT}</string>
        <key>GHL_TOOL_PROFILE</key><string>${profile}</string>
${logdirline}
    </dict>
    <key>RunAtLoad</key><true/>
    ${keepalive}
    <key>ThrottleInterval</key><integer>${throttle}</integer>
</dict>
</plist>
EOF

  # ---- the periodic probe plist, pointing at a script that EXISTS ----
  if [ "$mut" != "no-probe" ]; then
    : > "$tmp/scripts/ghl-mcp-probe.sh"
    cat > "$tmp/com.clawd.ghl-mcp-probe.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp-probe</string>
    <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>$tmp/scripts/ghl-mcp-probe.sh</string>
    </array>
</dict>
</plist>
EOF
    # A cron/plist line pointing at a DELETED script is a silently dead probe.
    [ "$mut" = "dead-probe-path" ] && rm -f "$tmp/scripts/ghl-mcp-probe.sh"
  fi

  # ---- openclaw.json: Tier 2 must be ABSENT from mcp.servers ----
  if [ "$mut" = "tier2-registered" ]; then
    printf '{"mcp":{"servers":{"ghl-mcp":{},"ghl-community-mcp":{}}}}\n' > "$tmp/openclaw.json"
  else
    printf '{"mcp":{"servers":{"ghl-mcp":{}}}}\n' > "$tmp/openclaw.json"
  fi

  # ---- logs: under the ceiling unless mutated ----
  printf 'small\n' > "$tmp/logs/stderr.log"
  if [ "$mut" = "unrotated-log" ]; then
    # 16 MB > 10 MB * 1.5 ceiling
    if command -v mkfile >/dev/null 2>&1; then
      mkfile -n 16m "$tmp/logs/stderr.log" 2>/dev/null || true
    else
      dd if=/dev/zero of="$tmp/logs/stderr.log" bs=1048576 count=16 >/dev/null 2>&1 || true
    fi
  fi

  # ---- no pin at all ----
  [ "$mut" = "no-pin" ] && rm -f "$tmp/config/ghl-mcp-pin.env"

  printf '%s' "$tmp"
}

_run_gate() {  # _run_gate <box>  -> echoes "<rc>|<stderr+stdout>"
  local box="$1" out rc=0
  out="$(GHL_MCP_DIR="$box/mcp" \
         GHL_MCP_LOG_DIR_OVERRIDE="$box/logs" \
         GHL_MCP_OC_JSON="$box/openclaw.json" \
         GHL_MCP_PLIST="$box/com.clawd.ghl-mcp.plist" \
         GHL_MCP_PROBE_PLIST="$box/com.clawd.ghl-mcp-probe.plist" \
         GHL_MCP_SYSTEMD_UNIT="$box/nonexistent.service" \
         bash "$box/scripts/ghl-mcp-assert-runtime.sh" 2>&1)" || rc=$?
  printf '%s|%s' "$rc" "$out"
}

# ── (A) A CORRECT installed service PASSES ───────────────────────────────────
BOX="$(_make_box "")"
RES="$(_run_gate "$BOX")"; RC="${RES%%|*}"; OUT="${RES#*|}"
if [ "$RC" = "0" ]; then
  pass "(A) a correctly-installed service PASSES (rc=0) — the gate is not a permanent FAIL"
else
  fail "(A) a correct service was rejected (rc=$RC). Offending lines:"
  printf '%s\n' "$OUT" | grep -F '[ghl-mcp-runtime] FAIL' | sed 's/^/        /'
fi
rm -rf "$BOX"

# ── (B) An EMPTY box reports SKIP (rc=2), never a failure ────────────────────
EMPTY="$(mktemp -d)"; mkdir -p "$EMPTY/scripts"
cp "$GATE_SRC" "$EMPTY/scripts/ghl-mcp-assert-runtime.sh"
RC=0
GHL_MCP_DIR="$EMPTY/absent-mcp" \
GHL_MCP_LOG_DIR_OVERRIDE="$EMPTY/absent-logs" \
GHL_MCP_OC_JSON="$EMPTY/absent.json" \
GHL_MCP_PLIST="$EMPTY/absent.plist" \
GHL_MCP_PROBE_PLIST="$EMPTY/absent-probe.plist" \
GHL_MCP_SYSTEMD_UNIT="$EMPTY/absent.service" \
  bash "$EMPTY/scripts/ghl-mcp-assert-runtime.sh" >/dev/null 2>&1 || RC=$?
if [ "$RC" = "2" ]; then
  pass "(B) a box without Tier 2 reports rc=2 (SKIP), so CI and non-GHL boxes are not failed"
else
  fail "(B) a box without Tier 2 returned rc=$RC (expected 2 = nothing to assert)"
fi
rm -rf "$EMPTY"

# ── MUTATION PROOFS — each one must FAIL, and name what it saw ──────────────
# mutation | human description | a distinctive fragment of the expected FAIL
_mutation_case() {
  local mut="$1" desc="$2" needle="$3"
  local box res rc out
  box="$(_make_box "$mut")"
  res="$(_run_gate "$box")"; rc="${res%%|*}"; out="${res#*|}"
  if [ "$rc" != "1" ]; then
    fail "($mut) $desc — expected rc=1, got rc=$rc"
  elif ! printf '%s' "$out" | grep -qF "$needle"; then
    fail "($mut) $desc — failed (rc=1) but without the expected diagnosis '$needle'. Got:"
    printf '%s\n' "$out" | grep -F '[ghl-mcp-runtime] FAIL' | sed 's/^/        /'
  else
    pass "($mut) $desc"
  fi
  rm -rf "$box"
}

_mutation_case direct-node \
  "plist launches node dist/main.js directly instead of the crash-only launcher" \
  "DIRECTLY, bypassing"
_mutation_case keepalive-true \
  "plist uses the UNCONDITIONAL KeepAlive boolean (the observed operator-box state)" \
  "UNCONDITIONAL boolean"
_mutation_case hot-throttle \
  "ThrottleInterval=10 (a hot relaunch loop) instead of >= 300" \
  "ThrottleInterval=10"
_mutation_case profile-full \
  "live GHL_TOOL_PROFILE=full — the 858-tool surface (the observed operator-box state)" \
  "GHL_TOOL_PROFILE=full"
_mutation_case unpinned-port \
  "PORT not pinned in the installed definition (main.js reads PORT first)" \
  "PORT='<unset>'"
_mutation_case no-log-dir \
  "no GHL_MCP_LOG_DIR in the installed definition — rotation is a no-op" \
  "NO GHL_MCP_LOG_DIR"
_mutation_case no-stamp \
  "no .ghl-mcp-build.json — dist/ is of unknown provenance" \
  "no build stamp"
_mutation_case stale-build \
  "build stamp records a commit that is NOT the vetted pin" \
  "is NOT the vetted commit"
_mutation_case tier2-registered \
  "ghl-community-mcp still REGISTERED in mcp.servers (the observed operator-box state)" \
  "IS REGISTERED in mcp.servers"
_mutation_case no-probe \
  "no periodic liveness probe installed — alive-but-deaf would go undetected" \
  "no periodic liveness probe installed"
_mutation_case dead-probe-path \
  "probe plist points at a script that no longer exists (silently dead probe)" \
  "DOES NOT EXIST"
_mutation_case unrotated-log \
  "stderr.log over the size ceiling — rotation is not happening (5.4 MB observed fleet-side)" \
  "rotation is not happening"
_mutation_case no-pin \
  "no pin file on the box — there is no expectation to compare against" \
  "NO expectation to compare"

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
