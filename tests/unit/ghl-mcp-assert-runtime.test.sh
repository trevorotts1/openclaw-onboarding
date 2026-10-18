#!/usr/bin/env bash
# tests/unit/ghl-mcp-assert-runtime.test.sh — W07 retirement rewrite
#
# Proves scripts/ghl-mcp-assert-runtime.sh in the ONLY direction that still
# matters after retirement: ABSENT = PASS on every branch, and every surface
# that is still there is named exactly.
#
#   rc 0  RETIRED_OK       nothing present, receipt VERIFIED_OFF + archive
#   rc 1  STILL_RUNNING    a launchd/pm2/systemd/process/listener/probe/
#                          registration identity was FOUND (named in the output)
#   rc 2  NOT_APPLICABLE   no community MCP history on this box (preserved skip)
#   rc 3  MISCONFIGURED    residual or unverifiable retirement state
#
# THE PRE-REWRITE CONTRADICTION this file now locks shut: the old gate FAILED
# on an absent plist (mac branch) and on no live supervisor (pm2/systemd
# branch), while its registration check PASSED only when the service was
# absent. "Retired" and "broken" were the same verdict. Cases (A)/(B) below are
# the proof that absence now passes; every other case is the anti-vacuity
# control that a surface still present is not waved through.
#
# HERMETIC. Every supervisor is a PATH STUB inside the sandbox: launchctl, pm2,
# systemctl, crontab, openclaw, lsof, curl and ps. Nothing here can read the
# runner's real launchd/pm2 state, and the simulated port is 18765, never the
# fleet's 8765. Temp trees live under the workflow tmp dir, never in $HOME.
#
# Exit 0 = all cases behaved. Exit 1 = one or more did not (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_SRC="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"
LIB_SRC="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
TMPBASE="${GHL_TEST_TMPBASE:-/Volumes/mac mini m4/Downloads/GHL updates/tmp}"
mkdir -p "$TMPBASE"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-assert-runtime.test.sh (W07 retirement) ==="
echo ""

[ -f "$GATE_SRC" ] || { echo "  FAIL: runtime gate not found at $GATE_SRC"; exit 1; }
[ -f "$LIB_SRC" ]  || { echo "  FAIL: shared path library not found at $LIB_SRC"; exit 1; }
bash -n "$GATE_SRC" || { echo "  FAIL: $GATE_SRC does not parse"; exit 1; }

SIM_PORT=18765
SIM_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"

# ── _make_box: a hermetic simulated box. All external tools stubbed. ─────────
_make_box() {
  local tmp
  tmp="$(mktemp -d "$TMPBASE/assert.XXXXXX")"
  mkdir -p "$tmp/scripts/lib" "$tmp/config" "$tmp/bin" "$tmp/state" \
           "$tmp/archive/ghl-mcp" "$tmp/logs" "$tmp/pm2home"
  cp "$GATE_SRC" "$tmp/scripts/ghl-mcp-assert-runtime.sh"
  cp "$LIB_SRC"  "$tmp/scripts/lib/ghl-mcp-paths.sh"

  cat > "$tmp/config/ghl-mcp-pin.env" <<EOF
GHL_MCP_VETTED_COMMIT="$SIM_COMMIT"
GHL_MCP_TOOL_PROFILE="curated"
GHL_MCP_PORT="$SIM_PORT"
GHL_MCP_EXPECT_MIN_TOOLS="1"
GHL_MCP_EXPECT_MAX_TOOLS="200"
GHL_MCP_LOG_MAX_BYTES="10485760"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"
EOF
  printf '{"mcp":{"servers":{"ghl-mcp":{}}}}\n' > "$tmp/openclaw.json"
  : > "$tmp/procs.txt"
  : > "$tmp/listeners.txt"
  : > "$tmp/launchd_loaded.txt"

  # ── launchd stub. `print gui/<uid>/<label>` honours the fixture; `list`
  # prints "<pid> <status> <label>" so the gate's label-column match is real.
  cat > "$tmp/bin/launchctl" <<EOF
#!/usr/bin/env bash
case "\$1" in
  print)
    label="\${2##*/}"
    grep -qx "\$label" "$tmp/launchd_loaded.txt" 2>/dev/null && exit 0
    exit 1 ;;
  list)
    while IFS= read -r l; do [ -n "\$l" ] && printf -- '-\t0\t%s\n' "\$l"; done < "$tmp/launchd_loaded.txt"
    exit 0 ;;
esac
exit 1
EOF

  # ── pm2 stub. `describe` answers only when the app fixture exists; `jlist`
  # emits one record in the exact shape the secret filter reads.
  cat > "$tmp/bin/pm2" <<EOF
#!/usr/bin/env bash
case "\$1" in
  describe) [ -f "$tmp/pm2_app" ] && exit 0 || exit 1 ;;
  jlist)
    if [ -f "$tmp/pm2_app" ]; then
      cat "$tmp/pm2_jlist.json"
    else
      printf '[]\n'
    fi
    exit 0 ;;
esac
exit 0
EOF

  cat > "$tmp/pm2_jlist.json" <<EOF
[{"name":"ghl-community-mcp","pm2_env":{"status":"online","pm_exec_path":"$tmp/mcp/.ghl-mcp-launch.sh","stop_exit_codes":0,"GHL_TOOL_PROFILE":"curated","PORT":"$SIM_PORT","MCP_SERVER_PORT":"$SIM_PORT","GHL_MCP_LOG_DIR":"$tmp/logs"}}]
EOF

  cat > "$tmp/bin/systemctl" <<EOF
#!/usr/bin/env bash
case "\$1" in
  is-enabled) [ -f "$tmp/systemd_enabled" ] && exit 0 || exit 1 ;;
  is-active)  [ -f "$tmp/systemd_active" ]  && exit 0 || exit 1 ;;
esac
exit 1
EOF

  cat > "$tmp/bin/crontab" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "-l" ] && [ -f "$tmp/crontab.txt" ]; then cat "$tmp/crontab.txt"; exit 0; fi
exit 1
EOF

  cat > "$tmp/bin/openclaw" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "cron" ] && [ "\$2" = "list" ] && [ -f "$tmp/cron_store.json" ]; then
  cat "$tmp/cron_store.json"
fi
exit 0
EOF

  # ── lsof stub: the gate reads column 9. A fixture line is a full lsof row.
  cat > "$tmp/bin/lsof" <<EOF
#!/usr/bin/env bash
if [ -s "$tmp/listeners.txt" ]; then
  printf 'COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n'
  cat "$tmp/listeners.txt"
fi
exit 0
EOF

  # ── ps stub: `ps -eo pid=,args=` yields live process fixtures; the pm2
  # daemon sweep (`ps -eo args`) yields nothing, which is correct here because
  # PM2_HOME is pinned inside the box.
  cat > "$tmp/bin/ps" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *pid*) cat "$tmp/procs.txt" 2>/dev/null ;;
esac
exit 0
EOF

  printf '#!/usr/bin/env bash\nexit 1\n' > "$tmp/bin/curl"
  chmod +x "$tmp/bin/"*
  printf '%s' "$tmp"
}

# ── _run <box> <platform> -> "<rc>|<output>" ────────────────────────────────
_run() {
  local box="$1" platform="${2:-mac}" out rc=0
  out="$(PATH="$box/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
         HOME="$box" \
         PM2_HOME="$box/pm2home" \
         GHL_MCP_PLATFORM_OVERRIDE="$platform" \
         GHL_MCP_DIR="$box/mcp" \
         GHL_MCP_LOG_DIR_OVERRIDE="$box/logs" \
         GHL_MCP_OC_JSON="$box/openclaw.json" \
         GHL_MCP_PLIST="$box/com.clawd.ghl-mcp.plist" \
         GHL_MCP_PROBE_PLIST="$box/com.clawd.ghl-mcp-probe.plist" \
         GHL_MCP_SYSTEMD_UNIT="$box/ghl-mcp.service" \
         GHL_MCP_RETIREMENT_RECEIPT="$box/state/ghl-mcp-retirement.json" \
         GHL_MCP_ARCHIVE_ROOT="$box/archive/ghl-mcp" \
         /bin/bash "$box/scripts/ghl-mcp-assert-runtime.sh" 2>&1)" || rc=$?
  printf '%s|%s' "$rc" "$out"
}

_expect() {  # _expect <desc> <rc> <out> <expected_rc> [needle ...]
  local desc="$1" rc="$2" out="$3" want="$4"; shift 4
  local ok=1 n
  [ "$rc" = "$want" ] || ok=0
  for n in "$@"; do printf '%s' "$out" | grep -qF "$n" || ok=0; done
  if [ "$ok" = "1" ]; then
    pass "$desc"
  else
    fail "$desc — expected rc=$want; got rc=$rc"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

# ── (A) A FRESH INSTALL: no history anywhere -> rc=2 NOT_APPLICABLE ─────────
# This is the preserved skip. Fresh installs omit the community MCP entirely,
# so the gate must not demand a service or a receipt.
BOX="$(_make_box "")"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(A) a fresh box with no community MCP history is NOT_APPLICABLE (rc=2), not a failure" \
  "$RC" "$OUT" 2 "NOT_APPLICABLE" "fresh installs omit it"
if printf '%s' "$OUT" | grep -qF 'FAIL '; then
  fail "(A2) a fresh box produced a FAIL line"
else
  pass "(A2) a fresh box produces no FAIL line"
fi
rm -rf "$BOX"

# ── (B) RETIRED = PASS ON THE MAC BRANCH ────────────────────────────────────
BOX="$(_make_box "")"
mkdir -p "$BOX/archive/ghl-mcp/run1"
printf 'deadbeef  probe.sh\n' > "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256"
MSHA="$(shasum -a 256 "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256" | awk '{print $1}')"
cat > "$BOX/state/ghl-mcp-retirement.json" <<EOF
{"final_state":"VERIFIED_OFF","box":"sim","cohort":"mac","archive_path":"$BOX/archive/ghl-mcp/run1","archive_manifest_sha256":"$MSHA"}
EOF
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(B1) retired mac box: absent plist is a PASS and the verdict is RETIRED_OK (rc=0)" \
  "$RC" "$OUT" 0 "RETIRED_OK" "no launchd service definition" "records final_state=VERIFIED_OFF" "archive manifest hash matches"
if printf '%s' "$OUT" | grep -qF 'STILL_RUNNING'; then
  fail "(B2) a retired box was reported STILL_RUNNING"
else
  pass "(B2) a retired box is never reported STILL_RUNNING"
fi
rm -rf "$BOX"

# ── (C) RETIRED = PASS ON THE LINUX-HOME BRANCH (no pm2/systemd) ────────────
BOX="$(_make_box "")"
mkdir -p "$BOX/archive/ghl-mcp/run1"
printf 'deadbeef  probe.sh\n' > "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256"
MSHA="$(shasum -a 256 "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256" | awk '{print $1}')"
cat > "$BOX/state/ghl-mcp-retirement.json" <<EOF
{"final_state":"VERIFIED_OFF","box":"sim","cohort":"linux-home","archive_path":"$BOX/archive/ghl-mcp/run1","archive_manifest_sha256":"$MSHA"}
EOF
RES="$(_run "$BOX" linux-home)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(C) retired linux-home box: no pm2 app and no systemd unit is a PASS (rc=0)" \
  "$RC" "$OUT" 0 "RETIRED_OK" "not supervised (retired)"
if printf '%s' "$OUT" | grep -qi 'launchd'; then
  fail "(C2) the Linux branch still mentions launchd"
else
  pass "(C2) no launchd assertion is made on a Linux box"
fi
rm -rf "$BOX"

# ── (D) STILL_RUNNING: launchd plist, loaded — names the label ─────────────
BOX="$(_make_box "")"
cat > "$BOX/com.clawd.ghl-mcp.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>Label</key><string>com.clawd.ghl-mcp</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>/x/.ghl-mcp-launch.sh</string></array>
<key>EnvironmentVariables</key><dict>
<key>PORT</key><string>18765</string>
<key>MCP_SERVER_PORT</key><string>18765</string>
<key>GHL_TOOL_PROFILE</key><string>curated</string>
<key>GHL_MCP_LOG_DIR</key><string>/x/logs</string>
</dict>
<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/><key>Crashed</key><true/></dict>
<key>ThrottleInterval</key><integer>300</integer>
</dict></plist>
EOF
printf 'com.clawd.ghl-mcp\n' > "$BOX/launchd_loaded.txt"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(D) a loaded launchd plist is STILL_RUNNING (rc=1) and names the exact label" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "launchd:com.clawd.ghl-mcp" "LOADED in launchd"
rm -rf "$BOX"

# ── (E) STILL_RUNNING: pm2 app registered (pm2 resurrect would restart it) ──
BOX="$(_make_box "")"
: > "$BOX/pm2_app"
RES="$(_run "$BOX" linux-home)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(E1) a registered pm2 app is STILL_RUNNING (rc=1) and is named" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "pm2:ghl-community-mcp"
_expect "(E2) the still-installed service is still judged for conformance (crash-only launcher)" \
  "$RC" "$OUT" 1 "PASS  pm2 runs the crash-only launcher"
rm -rf "$BOX"

# ── (F) STILL_RUNNING: systemd unit, enabled + active ──────────────────────
BOX="$(_make_box "")"
printf 'Restart=on-failure\nExecStart=/bin/bash /x/.ghl-mcp-launch.sh\nEnvironment=GHL_TOOL_PROFILE=curated\nEnvironment=PORT=18765\nEnvironment=MCP_SERVER_PORT=18765\nEnvironment=GHL_MCP_LOG_DIR=/x/logs\n' > "$BOX/ghl-mcp.service"
: > "$BOX/systemd_enabled"; : > "$BOX/systemd_active"
RES="$(_run "$BOX" linux-home)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(F) an enabled, active systemd unit is STILL_RUNNING and names ghl-mcp.service" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "systemd:ghl-mcp.service" "ENABLED" "ACTIVE"
rm -rf "$BOX"

# ── (G) STILL_RUNNING: a live process from the install dir ─────────────────
BOX="$(_make_box "")"
printf '4242 /bin/bash %s/mcp/.ghl-mcp-launch.sh\n' "$BOX" > "$BOX/procs.txt"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(G) a live process from the install dir is STILL_RUNNING and names the pid" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "process:4242"
rm -rf "$BOX"

# ── (G2/G3) THE SCANNER MUST NEVER MATCH ITSELF ────────────────────────────
# GU-020: the process filter's own awk helper carries -v l=".ghl-mcp-launch.sh"
# in its ps argv, so a naive matcher reports the scanner as a live service and
# a provably retired box fails its own gate. G2: ps output contains ONLY that
# helper line (no real service) -> must be RETIRED_OK (rc=0), never
# STILL_RUNNING. G3, the mirror: a real process running the launcher -> must
# still be STILL_RUNNING (rc=1) naming that exact identity, so the self-match
# fix never weakens real detection.
_make_retired() {  # _make_retired <box> — a valid VERIFIED_OFF receipt + archive
  local b="$1"
  mkdir -p "$b/archive/ghl-mcp/run1"
  printf 'deadbeef  probe.sh\n' > "$b/archive/ghl-mcp/run1/MANIFEST.sha256"
  local msha
  msha="$(shasum -a 256 "$b/archive/ghl-mcp/run1/MANIFEST.sha256" | awk '{print $1}')"
  cat > "$b/state/ghl-mcp-retirement.json" <<EOF
{"final_state":"VERIFIED_OFF","box":"sim","cohort":"mac","archive_path":"$b/archive/ghl-mcp/run1","archive_manifest_sha256":"$msha"}
EOF
}

BOX="$(_make_box "")"
_make_retired "$BOX"
printf '99682 awk -v d %s/mcp -v l .ghl-mcp-launch.sh -v s .ghl-mcp-supervise.sh -v self 99681 -v pp 99680\n' "$BOX" > "$BOX/procs.txt"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(G2) the scanner's own awk helper carrying the launcher name is NOT a live service: RETIRED_OK (rc=0)" \
  "$RC" "$OUT" 0 "RETIRED_OK"
if printf '%s' "$OUT" | grep -qF 'STILL_RUNNING'; then
  fail "(G2b) a retired box was reported STILL_RUNNING by the scanner matching its own helper"
  printf '%s\n' "$OUT" | sed 's/^/        /'
else
  pass "(G2b) no STILL_RUNNING verdict when ps output holds only the scanner helper line"
fi
if printf '%s' "$OUT" | grep -qF 'process:99682'; then
  fail "(G2c) the awk helper pid 99682 was named as an identity"
else
  pass "(G2c) the awk helper pid is never named as an identity"
fi
rm -rf "$BOX"

BOX="$(_make_box "")"
_make_retired "$BOX"
printf '99682 awk -v d %s/mcp -v l .ghl-mcp-launch.sh -v s .ghl-mcp-supervise.sh -v self 99681 -v pp 99680\n' "$BOX" > "$BOX/procs.txt"
printf '51501 /bin/bash %s/mcp/.ghl-mcp-launch.sh\n' "$BOX" >> "$BOX/procs.txt"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(G3) with a real launcher process alongside the scanner helper: STILL_RUNNING (rc=1) naming the real pid only" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "process:51501"
if printf '%s' "$OUT" | grep -qF 'process:99682'; then
  fail "(G3b) the awk helper pid 99682 leaked into the identity list next to the real service"
else
  pass "(G3b) only the real launcher process is named; the scanner helper stays excluded"
fi
rm -rf "$BOX"

# ── (H) STILL_RUNNING: a listener on the configured port ───────────────────
BOX="$(_make_box "")"
printf 'node 5150 user 20u IPv4 0x1 0x2 TCP 127.0.0.1:18765 (LISTEN)\n' > "$BOX/listeners.txt"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(H) a LISTEN socket on the configured port is STILL_RUNNING and names the address" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "listener:tcp:127.0.0.1:18765"
rm -rf "$BOX"

# ── (I) STILL_RUNNING: probe schedule (all three schedulers) ───────────────
BOX="$(_make_box "")"
printf '*/15 * * * * /bin/bash "%s/scripts/ghl-mcp-probe.sh" --once --heal # ghl-mcp-probe\n' "$BOX" > "$BOX/crontab.txt"
RES="$(_run "$BOX" linux-home)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(I1) a probe cron line is STILL_RUNNING and names the target" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "probe:crontab:" "ghl-mcp-probe.sh"
rm -rf "$BOX"

BOX="$(_make_box "")"
printf '[{"name": "ghl-mcp-probe", "cron": "*/15 * * * *"}]\n' > "$BOX/cron_store.json"
RES="$(_run "$BOX" linux-home)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(I2) a probe in the OpenClaw cron store is STILL_RUNNING and names it" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "probe:openclaw-cron-store:ghl-mcp-probe"
rm -rf "$BOX"

BOX="$(_make_box "")"
printf '<plist><dict><key>Label</key><string>com.clawd.ghl-mcp-probe</string></dict></plist>\n' > "$BOX/com.clawd.ghl-mcp-probe.plist"
printf 'com.clawd.ghl-mcp-probe\n' > "$BOX/launchd_loaded.txt"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(I3) a probe launchd job is STILL_RUNNING and names the probe label" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "probe:launchd:com.clawd.ghl-mcp-probe"
rm -rf "$BOX"

# ── (J) STILL_RUNNING: registration in mcp.servers ─────────────────────────
BOX="$(_make_box "")"
printf '{"mcp":{"servers":{"ghl-mcp":{},"ghl-community-mcp":{}}}}\n' > "$BOX/openclaw.json"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(J) a registration in mcp.servers is STILL_RUNNING and carries the exact removal command" \
  "$RC" "$OUT" 1 "STILL_RUNNING" "registration:mcp.servers.ghl-community-mcp" "openclaw mcp unset ghl-community-mcp"
rm -rf "$BOX"

# ── (K) MISCONFIGURED: residual install dir, nothing running, no receipt ──
BOX="$(_make_box "")"
mkdir -p "$BOX/mcp"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(K) a leftover install dir with no receipt is MISCONFIGURED (rc=3), naming the residual" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "residual:install-dir:$BOX/mcp"
rm -rf "$BOX"

# ── (L) MISCONFIGURED: a .plist.bak can be restored by hand ────────────────
BOX="$(_make_box "")"
printf '<plist><dict><key>Label</key><string>com.clawd.ghl-mcp</string></dict></plist>\n' > "$BOX/com.clawd.ghl-mcp.plist.bak-p0fix-20260803"
mkdir -p "$BOX/archive/ghl-mcp/run1"
printf 'deadbeef  x\n' > "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256"
MSHA="$(shasum -a 256 "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256" | awk '{print $1}')"
cat > "$BOX/state/ghl-mcp-retirement.json" <<EOF
{"final_state":"VERIFIED_OFF","box":"sim","cohort":"mac","archive_path":"$BOX/archive/ghl-mcp/run1","archive_manifest_sha256":"$MSHA"}
EOF
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(L) a backup plist that could be restored is MISCONFIGURED (rc=3)" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "launchd backups that must never be auto-restored" ".plist.bak-p0fix-20260803"
rm -rf "$BOX"

# ── (M) MISCONFIGURED: MIGRATION_FAILED receipt names the stage ────────────
BOX="$(_make_box "")"
cat > "$BOX/state/ghl-mcp-retirement.json" <<'EOF'
{"final_state":"MIGRATION_FAILED","failed_stage":"stage","residual_state":"service not stopped","remediation":"re-run the update path"}
EOF
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(M) a MIGRATION_FAILED receipt is MISCONFIGURED and names the failed stage" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "final_state=MIGRATION_FAILED" "stage='stage'" "re-run the update path"
rm -rf "$BOX"

# ── (N) MISCONFIGURED: malformed / incomplete receipts ─────────────────────
BOX="$(_make_box "")"
printf '{ not json\n' > "$BOX/state/ghl-mcp-retirement.json"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(N1) a receipt that is not valid JSON is MISCONFIGURED" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "is not valid JSON"
rm -rf "$BOX"

BOX="$(_make_box "")"
printf '{"box":"sim"}\n' > "$BOX/state/ghl-mcp-retirement.json"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(N2) a receipt with no final_state is MISCONFIGURED" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "has no final_state"
rm -rf "$BOX"

# ── (O) MISCONFIGURED: VERIFIED_OFF claims that cannot be stood up ─────────
BOX="$(_make_box "")"
cat > "$BOX/state/ghl-mcp-retirement.json" <<'EOF'
{"final_state":"VERIFIED_OFF","archive_path":"/does/not/exist","archive_manifest_sha256":"00"}
EOF
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(O1) a VERIFIED_OFF receipt naming a missing archive is MISCONFIGURED" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "which does not exist"
rm -rf "$BOX"

BOX="$(_make_box "")"
mkdir -p "$BOX/mcp-servers/ghl-community-mcp"
printf 'deadbeef  x\n' > "$BOX/mcp-servers/ghl-community-mcp/MANIFEST.sha256"
MSHA="$(shasum -a 256 "$BOX/mcp-servers/ghl-community-mcp/MANIFEST.sha256" | awk '{print $1}')"
cat > "$BOX/state/ghl-mcp-retirement.json" <<EOF
{"final_state":"VERIFIED_OFF","archive_path":"$BOX/mcp-servers/ghl-community-mcp","archive_manifest_sha256":"$MSHA"}
EOF
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(O2) an archive inside an ACTIVE install search path is MISCONFIGURED (never scannable as live)" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "ACTIVE install search path"
rm -rf "$BOX"

BOX="$(_make_box "")"
mkdir -p "$BOX/archive/ghl-mcp/run1"
printf 'deadbeef  x\n' > "$BOX/archive/ghl-mcp/run1/MANIFEST.sha256"
cat > "$BOX/state/ghl-mcp-retirement.json" <<EOF
{"final_state":"VERIFIED_OFF","archive_path":"$BOX/archive/ghl-mcp/run1","archive_manifest_sha256":"0000000000000000000000000000000000000000000000000000000000000000"}
EOF
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(O3) a manifest hash mismatch is MISCONFIGURED" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "archive manifest hash MISMATCH"
rm -rf "$BOX"

# ── (P) A PARTIAL scripts/ TREE IS A REFUSAL, NEVER A GUESS ────────────────
BOX="$(_make_box "")"
rm -f "$BOX/scripts/lib/ghl-mcp-paths.sh"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(P) a missing shared path library is MISCONFIGURED (rc=3), naming every location searched" \
  "$RC" "$OUT" 3 "MISCONFIGURED" "ghl-mcp-paths.sh is not on this box"
rm -rf "$BOX"

# ═════════════════════════════════════════════════════════════════════════════
# CONFORMANCE MUTATIONS — a service still present is not waved through. Each
# case keeps the old diagnostic AND must still exit 1.
# ═════════════════════════════════════════════════════════════════════════════
_write_plist() {  # _write_plist <box> <prog> <keepalive> <throttle> <profile> <portline> <logdirline>
  local box="$1" prog="$2" keepalive="$3" throttle="$4" profile="$5" portline="$6" logdirline="$7"
  cat > "$box/com.clawd.ghl-mcp.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>Label</key><string>com.clawd.ghl-mcp</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>${prog}</string></array>
<key>EnvironmentVariables</key><dict>
${portline}
<key>MCP_SERVER_PORT</key><string>${SIM_PORT}</string>
<key>GHL_TOOL_PROFILE</key><string>${profile}</string>
${logdirline}
</dict>
<key>RunAtLoad</key><true/>
${keepalive}
<key>ThrottleInterval</key><integer>${throttle}</integer>
</dict></plist>
EOF
}

_mutation_case() {  # <desc> <needle> <function that mutates $BOX>
  local desc="$1" needle="$2" mut="$3"
  local box res rc out
  box="$(_make_box "")"
  mkdir -p "$box/mcp"; : > "$box/mcp/.ghl-mcp-launch.sh"
  printf '{"commit":"%s","profile":"curated"}\n' "$SIM_COMMIT" > "$box/mcp/.ghl-mcp-build.json"
  "$mut" "$box"
  res="$(_run "$box" mac)"; rc="${res%%|*}"; out="${res#*|}"
  if [ "$rc" = "1" ] && printf '%s' "$out" | grep -qF "$needle"; then
    pass "$desc"
  else
    fail "$desc — expected rc=1 with '$needle', got rc=$rc"
    printf '%s\n' "$out" | grep -F '[ghl-mcp-runtime] FAIL' | sed 's/^/        /'
  fi
  rm -rf "$box"
}

_m_direct_node()   { local b="$1"; _write_plist "$b" "$b/mcp/dist/main.js" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/><key>Crashed</key><true/></dict>' 300 curated "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_keepalive()     { local b="$1"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><true/>' 300 curated "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_hot_throttle()  { local b="$1"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 10 curated "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_profile_full()  { local b="$1"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 300 full "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_unpinned_port() { local b="$1"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 300 curated "" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_no_log_dir()    { local b="$1"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 300 curated "        <key>PORT</key><string>${SIM_PORT}</string>" ""; }
_m_stale_build()   { local b="$1"; printf '{"commit":"0000000000000000000000000000000000000000","profile":"curated"}\n' > "$b/mcp/.ghl-mcp-build.json"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 300 curated "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_unrotated_log() { local b="$1"; dd if=/dev/zero of="$b/logs/stderr.log" bs=1048576 count=16 >/dev/null 2>&1 || true; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 300 curated "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; }
_m_dead_probe()    { local b="$1"; _write_plist "$b" "$b/mcp/.ghl-mcp-launch.sh" '<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>' 300 curated "        <key>PORT</key><string>${SIM_PORT}</string>" "        <key>GHL_MCP_LOG_DIR</key><string>$b/logs</string>"; printf '<plist><dict><key>Label</key><string>com.clawd.ghl-mcp-probe</string><key>ProgramArguments</key><array><string>/bin/bash</string><string>%s/dead/ghl-mcp-probe.sh</string></array></dict></plist>\n' "$b" > "$b/com.clawd.ghl-mcp-probe.plist"; }

_mutation_case "(Q1) plist launches node dist/main.js directly" "DIRECTLY, bypassing" _m_direct_node
_mutation_case "(Q2) plist uses the unconditional KeepAlive boolean" "UNCONDITIONAL boolean" _m_keepalive
_mutation_case "(Q3) ThrottleInterval=10 is a hot relaunch loop" "ThrottleInterval=10" _m_hot_throttle
_mutation_case "(Q4) live GHL_TOOL_PROFILE=full" "GHL_TOOL_PROFILE=full" _m_profile_full
_mutation_case "(Q5) PORT is not pinned" "PORT='<unset>'" _m_unpinned_port
_mutation_case "(Q6) no GHL_MCP_LOG_DIR — rotation is a no-op" "NO GHL_MCP_LOG_DIR" _m_no_log_dir
_mutation_case "(Q7) build stamp records a commit that is NOT the pin" "is NOT the vetted commit" _m_stale_build
_mutation_case "(Q8) stderr.log over the size ceiling" "rotation is not happening" _m_unrotated_log
_mutation_case "(Q9) probe points at a script that does not exist" "DOES NOT EXIST" _m_dead_probe

# ── (R) A missing pin with a surviving service is MISCONFIGURED evidence ───
BOX="$(_make_box "")"
mkdir -p "$BOX/mcp"; : > "$BOX/mcp/.ghl-mcp-launch.sh"
printf '777 /bin/bash %s/mcp/.ghl-mcp-launch.sh\n' "$BOX" > "$BOX/procs.txt"
rm -f "$BOX/config/ghl-mcp-pin.env"
RES="$(_run "$BOX" mac)"; RC="${RES%%|*}"; OUT="${RES#*|}"
_expect "(R) no pin file on a box that still carries a service is reported, not guessed" \
  "$RC" "$OUT" 1 "MISCONFIGURED" "NO expectation to compare"
rm -rf "$BOX"

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
