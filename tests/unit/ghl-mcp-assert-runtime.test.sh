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
# skill 36 v2.0.2: THE PLATFORM IS NOW PINNED PER CASE, and that is the point.
# The launchd cases below assert Darwin behaviour, so they set
# GHL_MCP_PLATFORM_OVERRIDE=mac; before this release they inherited whatever the
# runner happened to be, and on a Linux runner they exercised the mac branch
# only because the gate wrongly called a Linux box a Mac. Section (L) adds the
# shape that bug was about: a HOME-layout Linux container, supervised by pm2
# under a root-persisted PM2_HOME, with no launchd anywhere. Its pm2 and crontab
# are PATH stubs, so the case measures the gate and not the machine running it.
#
# Exit 0 = all cases behaved. Exit 1 = one or more did not (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_SRC="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"
LIB_SRC="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
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
if [ ! -f "$LIB_SRC" ]; then
  echo "  FAIL: shared path library not found at $LIB_SRC"
  exit 1
fi

SIM_PORT=18765
SIM_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"

# ── Build a simulated box. $1 = mutation name ("" = fully correct). ──────────
# Echoes the sandbox root; caller runs _run_gate on it.
_make_box() {
  local mut="${1:-}" tmp
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts/lib" "$tmp/config" "$tmp/mcp" "$tmp/logs" "$tmp/agents"
  cp "$GATE_SRC" "$tmp/scripts/ghl-mcp-assert-runtime.sh"
  # The gate derives paths and platform from the shared library and REFUSES
  # rather than guessing when it is absent (case (M) proves that). A simulated
  # box therefore has to carry it, exactly as a real delivered scripts/ tree does.
  [ "$mut" = "no-paths-lib" ] || cp "$LIB_SRC" "$tmp/scripts/lib/ghl-mcp-paths.sh"

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
  out="$(GHL_MCP_PLATFORM_OVERRIDE=mac \
         GHL_MCP_DIR="$box/mcp" \
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
EMPTY="$(mktemp -d)"; mkdir -p "$EMPTY/scripts/lib"
cp "$GATE_SRC" "$EMPTY/scripts/ghl-mcp-assert-runtime.sh"
cp "$LIB_SRC" "$EMPTY/scripts/lib/ghl-mcp-paths.sh"
RC=0
GHL_MCP_PLATFORM_OVERRIDE=mac \
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

# ═════════════════════════════════════════════════════════════════════════════
# (L) THE linux-home SHAPE: the box this release exists for
#
# A HOME-layout Linux container: no /data, no launchd, Tier 2 installed under
# the OpenClaw root (the bind-mounted directory) and supervised by pm2 under a
# root-persisted PM2_HOME. Before this fix the gate called it a Mac and emitted
# two FATALs for launchd plists that nothing on the box could ever load, so the
# updater exited 2 ("GHL MCP Tier 2 MISCONFIGURED") about a service that was
# online and answering. Every case below therefore asserts on a box whose
# runtime is CORRECT, and case (L1) additionally asserts that the word launchd
# never appears in the verdict.
#
# pm2, crontab and the openclaw CLI are PATH STUBS. The alternative is a test
# whose result depends on whether the machine running it happens to have a pm2
# daemon with an app of the same name, which is measuring the runner, not the
# gate. The stub emits the same pm2 jlist record shape the gate's secret filter
# reads, and nothing else.
# ═════════════════════════════════════════════════════════════════════════════

# _make_linux_box <mutation>  -> echoes the sandbox root
#   ""            fully correct: pm2 online, crontab probe line present
#   "pm2-down"    pm2 does not know the app, and there is no systemd unit
#   "cron-store"  no crontab entry, but the OpenClaw cron store has the probe
_make_linux_box() {
  local mut="${1:-}" tmp
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts/lib" "$tmp/config" "$tmp/mcp" "$tmp/logs" "$tmp/bin"
  cp "$GATE_SRC" "$tmp/scripts/ghl-mcp-assert-runtime.sh"
  cp "$LIB_SRC" "$tmp/scripts/lib/ghl-mcp-paths.sh"

  cat > "$tmp/config/ghl-mcp-pin.env" <<EOF
GHL_MCP_VETTED_COMMIT="$SIM_COMMIT"
GHL_MCP_TOOL_PROFILE="curated"
GHL_MCP_PORT="$SIM_PORT"
GHL_MCP_EXPECT_MIN_TOOLS="1"
GHL_MCP_EXPECT_MAX_TOOLS="200"
GHL_MCP_LOG_MAX_BYTES="10485760"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"
EOF
  : > "$tmp/mcp/.ghl-mcp-launch.sh"
  printf '{\n  "commit": "%s",\n  "profile": "curated"\n}\n' "$SIM_COMMIT" > "$tmp/mcp/.ghl-mcp-build.json"
  printf '{"mcp":{"servers":{"ghl-mcp":{}}}}\n' > "$tmp/openclaw.json"
  printf 'small\n' > "$tmp/logs/stderr.log"
  : > "$tmp/scripts/ghl-mcp-probe.sh"

  # ── pm2 stub: `describe` answers for the app, `jlist` emits ONE record in the
  #    exact shape the gate's filter reads (script path, stop_exit_codes, and the
  #    four non-secret env keys).
  cat > "$tmp/bin/pm2" <<EOF
#!/usr/bin/env bash
case "\$1" in
  describe)
    [ "${mut}" = "pm2-down" ] && exit 1
    exit 0 ;;
  jlist)
    [ "${mut}" = "pm2-down" ] && { printf '[]\n'; exit 0; }
    cat <<'JSON'
[{"name":"ghl-community-mcp","pm2_env":{"pm_exec_path":"__LAUNCHER__","exec_interpreter":"bash","stop_exit_codes":0,"GHL_TOOL_PROFILE":"curated","PORT":"__PORT__","MCP_SERVER_PORT":"__PORT__","GHL_MCP_LOG_DIR":"__LOGS__"}}]
JSON
    exit 0 ;;
esac
exit 0
EOF
  # Substitute the sandbox paths into the record without fighting heredoc quoting.
  sed -i.bak -e "s|__LAUNCHER__|$tmp/mcp/.ghl-mcp-launch.sh|" \
             -e "s|__PORT__|$SIM_PORT|g" \
             -e "s|__LOGS__|$tmp/logs|" "$tmp/bin/pm2" && rm -f "$tmp/bin/pm2.bak"
  chmod +x "$tmp/bin/pm2"

  # ── crontab stub: the probe line, unless the case is about the cron STORE.
  cat > "$tmp/bin/crontab" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "-l" ]; then
  [ "${mut}" = "cron-store" ] && exit 0
  printf '*/15 * * * * GHL_MCP_LOG_DIR=%s /bin/bash %s --once --heal # ghl-mcp-probe\n' \\
    "$tmp/logs" "$tmp/scripts/ghl-mcp-probe.sh"
fi
exit 0
EOF
  chmod +x "$tmp/bin/crontab"

  # ── openclaw stub: the cron STORE, which is where autostart registers the
  #    probe on a container with no usable crontab.
  cat > "$tmp/bin/openclaw" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "cron" ] && [ "\$2" = "list" ]; then
  [ "${mut}" = "cron-store" ] && printf '[{"name": "ghl-mcp-probe", "cron": "*/15 * * * *"}]\n'
fi
exit 0
EOF
  chmod +x "$tmp/bin/openclaw"

  printf '%s' "$tmp"
}

_run_linux_gate() {  # _run_linux_gate <box> -> "<rc>|<output>"
  local box="$1" out rc=0
  out="$(PATH="$box/bin:$PATH" \
         GHL_MCP_PLATFORM_OVERRIDE=linux-home \
         GHL_MCP_DIR="$box/mcp" \
         GHL_MCP_LOG_DIR_OVERRIDE="$box/logs" \
         GHL_MCP_OC_JSON="$box/openclaw.json" \
         GHL_MCP_PLIST="$box/absent.plist" \
         GHL_MCP_PROBE_PLIST="$box/absent-probe.plist" \
         GHL_MCP_SYSTEMD_UNIT="$box/nonexistent.service" \
         bash "$box/scripts/ghl-mcp-assert-runtime.sh" 2>&1)" || rc=$?
  printf '%s|%s' "$rc" "$out"
}

BOX="$(_make_linux_box "")"
RES="$(_run_linux_gate "$BOX")"; RC="${RES%%|*}"; OUT="${RES#*|}"
if [ "$RC" = "0" ]; then
  pass "(L1) a healthy linux-home container PASSES: pm2 under the derived PM2_HOME, no launchd demanded"
else
  fail "(L1) a healthy linux-home container was rejected (rc=$RC). Offending lines:"
  printf '%s\n' "$OUT" | grep -F '[ghl-mcp-runtime] FAIL' | sed 's/^/        /'
fi
if printf '%s' "$OUT" | grep -qi 'launchd'; then
  fail "(L2) the verdict still mentions launchd on a Linux box: the mac branch is being entered off Darwin"
  printf '%s\n' "$OUT" | grep -i 'launchd' | sed 's/^/        /'
else
  pass "(L2) no launchd assertion is made on a Linux box (the pre-fix FATAL pair is gone)"
fi
if printf '%s' "$OUT" | grep -qF 'pm2 runs the crash-only launcher'; then
  pass "(L3) the gate READ the pm2 registration (it inspected the supervisor autostart actually installs)"
else
  fail "(L3) the gate did not report on the pm2 registration: it is not inspecting the real supervisor"
fi
rm -rf "$BOX"

BOX="$(_make_linux_box pm2-down)"
RES="$(_run_linux_gate "$BOX")"; RC="${RES%%|*}"; OUT="${RES#*|}"
if [ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'nothing supervises it'; then
  pass "(L4) a linux-home box with NO live pm2 app and no systemd still FAILS (the gate did not go blind)"
else
  fail "(L4) an unsupervised linux-home box returned rc=$RC without the expected diagnosis"
  printf '%s\n' "$OUT" | grep -F '[ghl-mcp-runtime] FAIL' | sed 's/^/        /'
fi
rm -rf "$BOX"

BOX="$(_make_linux_box cron-store)"
RES="$(_run_linux_gate "$BOX")"; RC="${RES%%|*}"; OUT="${RES#*|}"
if [ "$RC" = "0" ] && printf '%s' "$OUT" | grep -qF 'OpenClaw cron store'; then
  pass "(L5) a probe registered in the OpenClaw cron store counts (containers with no usable crontab)"
else
  fail "(L5) the cron-store probe was not recognised (rc=$RC)"
  printf '%s\n' "$OUT" | grep -F '[ghl-mcp-runtime] FAIL' | sed 's/^/        /'
fi
rm -rf "$BOX"

# ── (M) A PARTIAL scripts/ TREE IS A REFUSAL, NEVER A GUESS ──────────────────
# The gate derives the install path from scripts/lib/ghl-mcp-paths.sh. If that
# file did not reach the box, the honest answer is "I cannot determine where
# Tier 2 lives here", not a verdict about a directory the gate invented.
BOX="$(_make_box no-paths-lib)"
RES="$(_run_gate "$BOX")"; RC="${RES%%|*}"; OUT="${RES#*|}"
if [ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'ghl-mcp-paths.sh is not on this box'; then
  pass "(M) a missing shared path library is a LOUD refusal naming every location searched"
else
  fail "(M) a missing shared path library returned rc=$RC without the expected refusal"
  printf '%s\n' "$OUT" | sed 's/^/        /'
fi
rm -rf "$BOX"

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
