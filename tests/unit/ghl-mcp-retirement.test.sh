#!/usr/bin/env bash
# tests/unit/ghl-mcp-retirement.test.sh
#
# GU-019/020/021 — the community GHL MCP is RETIRED. This test is OFFLINE and
# HERMETIC: every supervisor is stubbed on PATH (launchctl, pm2, crontab,
# openclaw) and nothing outside a throwaway sandbox is read or written. No
# launchctl/pm2/systemctl/crontab on this machine is ever invoked.
#
# Sandboxes live under $GHL_RETIRE_TEST_ROOT (default: this package's tmp/),
# never in the repo, never in $HOME.
#
# Asserts:
#   A  the START path fails closed (START_REFUSED_RETIRED) — it cannot restart
#   B  --status reports SERVICE_PRESENT and changes nothing
#   C  --retire --dry-run prints a plan and touches nothing
#   D  --retire archives secret-free, disables resurrection, stops the matched
#      identity and writes a VERIFIED_OFF receipt
#   E  re-running --retire is a no-op (idempotent, no second archive)
#   F  a resurrection path that cannot be disabled -> MIGRATION_FAILED, exit 1,
#      no success marker
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOSTART="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
ASSERT="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"
PATHS_LIB="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
BASE="${GHL_RETIRE_TEST_ROOT:-/Volumes/mac mini m4/Downloads/GHL updates/tmp}"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }

[ -f "$AUTOSTART" ] || { echo "missing $AUTOSTART" >&2; exit 1; }
[ -f "$ASSERT" ]    || { echo "missing $ASSERT" >&2; exit 1; }
[ -f "$PATHS_LIB" ] || { echo "missing $PATHS_LIB" >&2; exit 1; }
mkdir -p "$BASE" || exit 1
WORK="$(mktemp -d "$BASE/ghl-retire-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# ── stubs ───────────────────────────────────────────────────────────────────
mkdir -p "$WORK/bin"
cat > "$WORK/bin/launchctl" <<'STUB'
#!/bin/sh
S="${LAUNCHCTL_STATE:?}"; mkdir -p "$S"
case "$1" in
  print)
    label="${2##*/}"
    [ -f "$S/loaded.$label" ] && exit 0
    [ "${LC_UNDEAD:-0}" = "1" ] && exit 0
    exit 1 ;;
  print-disabled)
    printf 'disabled services = {\n'
    printf '\t"com.clawd.ghl-mcp" => %s\n' "$(cat "$S/ovr.com.clawd.ghl-mcp" 2>/dev/null || echo enabled)"
    printf '\t"com.clawd.ghl-mcp-probe" => %s\n' "$(cat "$S/ovr.com.clawd.ghl-mcp-probe" 2>/dev/null || echo enabled)"
    printf '}\n'
    exit 0 ;;
  list)
    for f in "$S"/loaded.*; do [ -e "$f" ] || continue; printf -- '-\t0\t%s\n' "${f##*/loaded.}"; done
    exit 0 ;;
  bootout)
    [ "${LC_BOOTOUT_FAIL:-0}" = "1" ] && exit 1
    if [ -n "${3:-}" ] && [ -f "${3:-}" ]; then label="$(basename "$3" .plist)"; else label="${2##*/}"; fi
    rm -f "$S/loaded.$label"; exit 0 ;;
  disable) printf 'disabled\n' > "$S/ovr.${2##*/}"; exit 0 ;;
esac
exit 0
STUB
cat > "$WORK/bin/pm2" <<'STUB'
#!/bin/sh
S="${PM2_STATE:?}"; mkdir -p "$S"
case "$1" in
  describe) [ -f "$S/app" ] && exit 0 || exit 1 ;;
  jlist)
    if [ -f "$S/app" ]; then printf '[{"name":"ghl-community-mcp","pm2_env":{}}]\n'; else printf '[]\n'; fi ;;
  delete) rm -f "$S/app" ;;
  save)   touch "$S/saved" ;;
esac
exit 0
STUB
cat > "$WORK/bin/crontab" <<'STUB'
#!/bin/sh
S="${CRON_STATE:?}"; mkdir -p "$S"
case "$1" in
  -l) [ -f "$S/table" ] && cat "$S/table" || exit 1 ;;
  -)  cat > "$S/table" ;;
esac
exit 0
STUB
cat > "$WORK/bin/openclaw" <<'STUB'
#!/bin/sh
S="${OC_STATE:?}"; mkdir -p "$S"
case "$1 $2" in
  "cron list")   [ -f "$S/cron" ] && cat "$S/cron" || echo "No cron jobs." ;;
  "cron delete") rm -f "$S/cron" ;;
  "mcp list")    echo "ghl-mcp  https://services.leadconnectorhq.com/mcp/anthropic/v2" ;;
esac
exit 0
STUB
cat > "$WORK/bin/lsof" <<'STUB'
#!/bin/sh
exit 0
STUB
cat > "$WORK/bin/ps" <<'STUB'
#!/bin/sh
exit 0
STUB
cat > "$WORK/bin/curl" <<'STUB'
#!/bin/sh
exit 1
STUB
chmod +x "$WORK/bin/"*

make_box() {  # make_box <dir>
  local W="$1"
  local H="$W/home"
  local OC="$W/home/.openclaw"
  mkdir -p "$H" "$OC/scripts/lib" "$OC/config" "$OC/mcp-servers/ghl-community-mcp/dist" \
           "$OC/mcp-servers/ghl-community-mcp/node_modules/foo" \
           "$W/logs" "$W/lc" "$W/pm2" "$W/cron" "$W/oc" \
           "$H/Library/LaunchAgents"
  cp "$AUTOSTART" "$OC/scripts/ghl-mcp-autostart.sh"
  cp "$ASSERT" "$OC/scripts/ghl-mcp-assert-runtime.sh"
  cp "$PATHS_LIB" "$OC/scripts/lib/ghl-mcp-paths.sh"

  cat > "$OC/config/ghl-mcp-pin.env" <<'PIN'
GHL_MCP_VETTED_COMMIT="0e417166569064f5ccc3c694f745dbb74004852b"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"
GHL_MCP_TOOL_PROFILE="curated"
GHL_MCP_REPO_URL="https://example.invalid/ghl-mirror.git"
GHL_MCP_PORT="18765"
GHL_MCP_BIND_HOST="127.0.0.1"
PIN

  local M="$OC/mcp-servers/ghl-community-mcp"
  echo "source tree" > "$M/README.md"
  echo "console.log('ok')" > "$M/dist/main.js"
  printf 'GHL_API_KEY=pit-secret-value-0123456789\nGHL_LOCATION_ID=loc123\n' > "$M/.env"
  printf 'GHL_API_KEY=pit-secret-value-0123456789\n' > "$M/.ghl-mcp.env"
  echo "x" > "$M/node_modules/foo/index.js"
  echo '{"commit":"0e417166569064f5ccc3c694f745dbb74004852b"}' > "$M/.ghl-mcp-build.json"
  printf '#!/bin/sh\nwhile true; do :; done\n' > "$M/.ghl-mcp-supervise.sh"

  printf '<plist><dict><key>Label</key><string>com.clawd.ghl-mcp</string><key>RunAtLoad</key><true/></dict></plist>\n' \
    > "$H/Library/LaunchAgents/com.clawd.ghl-mcp.plist"
  printf '<plist><dict><key>Label</key><string>com.clawd.ghl-mcp-probe</string></dict></plist>\n' \
    > "$H/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist"

  touch "$W/lc/loaded.com.clawd.ghl-mcp"
  touch "$W/pm2/app"
  printf '*/15 * * * * bash x --once --heal # managed:ghl-mcp-probe\n@reboot PM2_HOME=x pm2 resurrect # managed:ghl-mcp-pm2-resurrect\n0 3 * * * other job\n' \
    > "$W/cron/table"

  printf '{"mcp":{"servers":{"ghl-mcp":{}}}}' > "$OC/openclaw.json"
}

run_as() {  # run_as <box> <extra env assignments> [script args...]
  local W="$1" extra="${2:-}"
  shift 2
  env -i \
    PATH="$WORK/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin" \
    HOME="$W/home" OPENCLAW_ROOT="$W/home/.openclaw" \
    GHL_MCP_UNAME_S=Darwin GHL_MCP_PLATFORM_OVERRIDE=mac \
    GHL_MCP_DIR="$W/home/.openclaw/mcp-servers/ghl-community-mcp" \
    GHL_MCP_LOG_DIR_OVERRIDE="$W/logs" PM2_HOME="$W/pm2" \
    LAUNCHCTL_STATE="$W/lc" PM2_STATE="$W/pm2" CRON_STATE="$W/cron" OC_STATE="$W/oc" \
    ${extra} \
    bash "$W/home/.openclaw/scripts/ghl-mcp-autostart.sh" "$@"
}

status_of() { printf '%s\n' "$1" | grep -E '^STATUS:' | tail -1; }

# The SHIPPED verifier, over the same hermetic box. Every supervisor remains a
# PATH stub; nothing real is read.
run_verify() {  # run_verify <box> [extra env assignment]
  local W="$1" extra="${2:-}"
  env -i \
    PATH="$WORK/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin" \
    HOME="$W/home" OPENCLAW_ROOT="$W/home/.openclaw" \
    GHL_MCP_UNAME_S=Darwin GHL_MCP_PLATFORM_OVERRIDE=mac \
    GHL_MCP_DIR="$W/home/.openclaw/mcp-servers/ghl-community-mcp" \
    GHL_MCP_LOG_DIR_OVERRIDE="$W/logs" PM2_HOME="$W/pm2" \
    LAUNCHCTL_STATE="$W/lc" PM2_STATE="$W/pm2" CRON_STATE="$W/cron" OC_STATE="$W/oc" \
    GHL_MCP_PLIST="$W/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" \
    GHL_MCP_PROBE_PLIST="$W/home/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist" \
    GHL_MCP_OC_JSON="$W/home/.openclaw/openclaw.json" \
    GHL_MCP_SYSTEMD_UNIT="$W/no-such.service" \
    GHL_MCP_RETIREMENT_RECEIPT="$W/home/.openclaw/.retired/ghl-mcp-retirement.json" \
    GHL_MCP_RETIREMENT_FAIL_RECEIPT="$W/home/.openclaw/.retired/ghl-mcp-migration-failed.json" \
    GHL_MCP_ARCHIVE_ROOT="$W/home/.openclaw/.retired" \
    ${extra} \
    bash "$W/home/.openclaw/scripts/ghl-mcp-assert-runtime.sh" 2>&1
}

# ── Box 1: full retirement ──────────────────────────────────────────────────
BOX="$WORK/box1"; make_box "$BOX"

# A. START fails closed.
OUT="$(run_as "$BOX" "")"; RC=$?
S="$(status_of "$OUT")"
case "$S" in
  *START_REFUSED_RETIRED*) pass "(A) START path fails closed: $S" ;;
  *) fail "(A) START was not refused: '$S' (rc=$RC)" ;;
esac
[ "$RC" = "0" ] && pass "(A2) START refusal exits 0 (no build, no supervisor)" || fail "(A2) START refusal rc=$RC"
[ -f "$BOX/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" ] && pass "(A3) START touched no plist" || fail "(A3) START removed the plist"

# B. --status reports SERVICE_PRESENT and changes nothing.
OUT="$(run_as "$BOX" "" --status)"; S="$(status_of "$OUT")"
case "$S" in *SERVICE_PRESENT*) pass "(B) --status reports SERVICE_PRESENT" ;; *) fail "(B) --status: '$S'" ;; esac
[ -e "$BOX/home/.openclaw/.retired" ] && fail "(B2) --status created .retired" || pass "(B2) --status wrote nothing"

# C. dry run touches nothing.
OUT="$(run_as "$BOX" "" --retire --dry-run)"; S="$(status_of "$OUT")"
case "$S" in *RETIRE_DRY_RUN*) pass "(C) dry run reports RETIRE_DRY_RUN" ;; *) fail "(C) dry run: '$S'" ;; esac
[ -f "$BOX/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" ] && pass "(C2) dry run left the plist" || fail "(C2) dry run removed the plist"
[ -f "$BOX/pm2/app" ] && pass "(C3) dry run left the pm2 app registered" || fail "(C3) dry run deleted the pm2 app"
[ -e "$BOX/home/.openclaw/.retired" ] && fail "(C4) dry run created .retired" || pass "(C4) dry run wrote nothing"

# D. the real transaction.
OUT="$(run_as "$BOX" "" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in *RETIRED_VERIFIED_OFF*) pass "(D) --retire -> VERIFIED_OFF" ;; *) fail "(D) --retire: '$S' (rc=$RC)" ;; esac
[ "$RC" = "0" ] && pass "(D2) --retire exit 0" || fail "(D2) --retire rc=$RC"
[ -f "$BOX/home/.openclaw/.retired/ghl-mcp-retirement.json" ] && pass "(D3) success receipt written" || fail "(D3) no success receipt"
python3 -I -c 'import json,sys; json.load(open(sys.argv[1]))' "$BOX/home/.openclaw/.retired/ghl-mcp-retirement.json" 2>/dev/null \
  && pass "(D4) receipt is valid JSON" || fail "(D4) receipt is not valid JSON"

ARC="$(ls -d "$BOX"/home/.openclaw/.retired/archive-* 2>/dev/null | head -1)"
[ -n "$ARC" ] && pass "(D5) archive created: $ARC" || fail "(D5) no archive"
[ -n "$ARC" ] && [ -s "$ARC/manifest.sha256" ] && pass "(D6) manifest with sha256 written" || fail "(D6) no manifest"
if [ -n "$ARC" ]; then
  if find "$ARC" -type f \( -name '.env' -o -name '.ghl-mcp.env' \) | grep -q .; then
    fail "(D7) a secret file entered the archive"
  else
    pass "(D7) no .env/.ghl-mcp.env in the archive"
  fi
  if grep -rIlF -- 'pit-secret-value-0123456789' "$ARC" 2>/dev/null | grep -q .; then
    fail "(D8) the live token value is present in the archive"
  else
    pass "(D8) the live token value is absent from the archive"
  fi
  [ -f "$ARC/tree/README.md" ] && pass "(D9) source tree archived" || fail "(D9) source tree not archived"
  [ -d "$ARC/tree/node_modules" ] && fail "(D10) node_modules archived" || pass "(D10) node_modules excluded"
fi

[ -f "$BOX/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" ] && fail "(D11) plist still installed" || pass "(D11) plist quarantined out of LaunchAgents"
[ "$(cat "$BOX/lc/ovr.com.clawd.ghl-mcp" 2>/dev/null)" = "disabled" ] && pass "(D12) launchd override disabled" || fail "(D12) launchd override not disabled"
[ -f "$BOX/pm2/app" ] && fail "(D13) pm2 app still registered" || pass "(D13) pm2 app deleted"
[ -f "$BOX/pm2/saved" ] && pass "(D14) pm2 save ran" || fail "(D14) pm2 save did not run"
if grep -qE 'managed:ghl-mcp-(probe|pm2-resurrect)' "$BOX/cron/table" 2>/dev/null; then
  fail "(D15) a managed cron tag survived"
else
  pass "(D15) both managed cron tags removed"
fi
grep -q 'other job' "$BOX/cron/table" 2>/dev/null && pass "(D16) unmanaged cron entries preserved" || fail "(D16) unmanaged cron entry was dropped"
[ -f "$BOX/home/.openclaw/config/ghl-mcp-pin.env" ] && fail "(D17) the delivered pin survived retirement" || pass "(D17) the delivered pin was removed"

# E. idempotent second run.
N_ARC="$(ls -d "$BOX"/home/.openclaw/.retired/archive-* 2>/dev/null | wc -l | tr -d ' ')"
OUT="$(run_as "$BOX" "" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in *RETIRED_VERIFIED_OFF*) pass "(E) re-run still VERIFIED_OFF" ;; *) fail "(E) re-run: '$S'" ;; esac
[ "$RC" = "0" ] && pass "(E2) re-run exit 0" || fail "(E2) re-run rc=$RC"
N_ARC2="$(ls -d "$BOX"/home/.openclaw/.retired/archive-* 2>/dev/null | wc -l | tr -d ' ')"
[ "$N_ARC" = "$N_ARC2" ] && pass "(E3) re-run created no second archive" || fail "(E3) archive count $N_ARC -> $N_ARC2"
OUT="$(run_as "$BOX" "" --status)"; S="$(status_of "$OUT")"
case "$S" in *RETIRED_VERIFIED_OFF*) pass "(E4) --status after retirement is VERIFIED_OFF" ;; *) fail "(E4) --status: '$S'" ;; esac

# ── Box 2: an undying supervisor -> MIGRATION_FAILED ────────────────────────
BOX2="$WORK/box2"; make_box "$BOX2"
OUT="$(run_as "$BOX2" "LC_UNDEAD=1" --retire)"; RC=$?
S="$(status_of "$OUT")"
case "$S" in *MIGRATION_FAILED*) pass "(F) undying launchd job -> MIGRATION_FAILED" ;; *) fail "(F) undying job: '$S'" ;; esac
[ "$RC" = "1" ] && pass "(F2) MIGRATION_FAILED exits 1" || fail "(F2) MIGRATION_FAILED rc=$RC"
[ -f "$BOX2/home/.openclaw/.retired/ghl-mcp-retirement.json" ] && fail "(F3) a success marker was written" || pass "(F3) no success marker"
[ -f "$BOX2/home/.openclaw/.retired/ghl-mcp-migration-failed.json" ] && pass "(F4) failure receipt written" || fail "(F4) no failure receipt"


# ═════════════════════════════════════════════════════════════════════════════
# FROZEN RETIREMENT STATE MACHINE (GU-019/020/021)
# The verifier is the shipped one; every state below is real files and real
# stub answers, never a mocked verdict.
# ═════════════════════════════════════════════════════════════════════════════

# ── G. The retired box is RETIRED_OK to the shipped verifier ────────────────
OUT="$(run_verify "$BOX")"; RC=$?
printf '%s' "$OUT" | grep -qF 'VERDICT: RETIRED_OK' \
  && pass "(G) verifier: retired box -> RETIRED_OK" \
  || { fail "(G) verifier did not report RETIRED_OK on the retired box (rc=$RC)"; printf '%s\n' "$OUT" | tail -8 >&2; }
[ "$RC" = "0" ] && pass "(G2) verifier exit 0 on a verified-off box" || fail "(G2) verifier rc=$RC"

# ── G3. The verifier is READ-ONLY: nothing in the box changes ───────────────
snap() { find "$1" -type f -exec shasum -a 256 {} + 2>/dev/null | sort | shasum -a 256 | awk '{print $1}'; }
B_SNAP="$(snap "$BOX/home/.openclaw")"
run_verify "$BOX" >/dev/null 2>&1 || true
A_SNAP="$(snap "$BOX/home/.openclaw")"
[ -n "$B_SNAP" ] && [ "$B_SNAP" = "$A_SNAP" ] \
  && pass "(G3) the verifier mutates nothing (tree hash identical before/after)" \
  || fail "(G3) the verifier changed the retired tree ($B_SNAP -> $A_SNAP)"

# ── H. FRESH INSTALL OMISSION: a box with no history is NOT_APPLICABLE ─────
FRESH="$WORK/fresh"; mkdir -p "$FRESH/home/.openclaw/scripts/lib" "$FRESH/lc" "$FRESH/pm2" "$FRESH/cron" "$FRESH/oc"
cp "$ASSERT" "$FRESH/home/.openclaw/scripts/ghl-mcp-assert-runtime.sh"
cp "$PATHS_LIB" "$FRESH/home/.openclaw/scripts/lib/ghl-mcp-paths.sh"
OUT="$(run_verify "$FRESH")"; RC=$?
[ "$RC" = "2" ] && printf '%s' "$OUT" | grep -qF 'NOT_APPLICABLE' \
  && pass "(H) a fresh box is NOT_APPLICABLE (rc=2): fresh installs omit the service" \
  || { fail "(H) fresh box: expected rc=2 NOT_APPLICABLE, got rc=$RC"; printf '%s\n' "$OUT" | tail -5 >&2; }
if awk '{ sub(/#.*/, "") } /ghl-mcp-autostart/' "$REPO_ROOT/install.sh" 2>/dev/null | grep -q .; then
  fail "(H2) install.sh still invokes the community MCP start path (fresh installs must omit it)"
else
  pass "(H2) install.sh carries no community MCP start path (fresh installs omit it)"
fi
if awk '{ sub(/#.*/, "") } /--retire/ || /ghl-mcp-migration-failed/' "$REPO_ROOT/update-skills.sh" 2>/dev/null | grep -q .; then
  pass "(H3) update-skills.sh carries the retirement entry point"
else
  printf 'SKIP (H3) update-skills.sh retirement entry point not landed yet (owner lane W20)\n'
fi

# ── I. FAILED PREREQUISITE: migration-failed BEFORE the stop leaves the
#      service alive, writes no success marker, and names the stage. This is
#      BOX2, whose launchd job still answers loaded (LC_UNDEAD).
OUT="$(run_verify "$BOX2" "LC_UNDEAD=1")"; RC=$?
printf '%s' "$OUT" | grep -qF 'final_state=MIGRATION_FAILED' \
  && printf '%s' "$OUT" | grep -qE "stage='(stage|disable-resurrection|stop|verify-off)'" \
  && printf '%s' "$OUT" | grep -qF 'launchd:com.clawd.ghl-mcp' \
  && pass "(I) failed prerequisite is reported with its stage and live residual, no success claim" \
  || { fail "(I) migration-failed stage/residual was not reported"; printf '%s\n' "$OUT" | grep -F 'MIGRATION_FAILED' | head -3 >&2; }
[ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'STILL_RUNNING' \
  && pass "(I2) the still-live service is STILL_RUNNING (rc=1), not a pass" \
  || fail "(I2) the live service was not named after a failed transaction (rc=$RC)"
[ -f "$BOX2/home/.openclaw/.retired/ghl-mcp-retirement.json" ] \
  && fail "(I3) a success marker exists after a failed transaction" \
  || pass "(I3) no success marker after a failed transaction"

# ── J. FAILED STOP: bootout refuses, the transaction must not claim OFF ────
BOX3="$WORK/box3"; make_box "$BOX3"
OUT="$(run_as "$BOX3" "LC_BOOTOUT_FAIL=1" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in
  *MIGRATION_FAILED*) pass "(J) a stuck launchd job -> MIGRATION_FAILED, never a success claim" ;;
  *) fail "(J) expected MIGRATION_FAILED, got: $S" ;;
esac
[ "$RC" = "1" ] && pass "(J2) failed stop exits 1" || fail "(J2) failed stop rc=$RC"
[ -f "$BOX3/lc/loaded.com.clawd.ghl-mcp" ] \
  && pass "(J3) the stub job is still loaded: the real old-service state survives the failed stop" \
  || fail "(J3) the loaded fixture disappeared — the test cannot prove residual state"
[ -f "$BOX3/home/.openclaw/.retired/ghl-mcp-retirement.json" ] \
  && fail "(J4) a success marker was written on a failed stop" \
  || pass "(J4) no success marker on a failed stop"
python3 -I -c 'import json,sys
d=json.load(open(sys.argv[1]))
st=d.get("final_state"); stage=d.get("stage"); live=" ".join((d.get("verification") or {}).get("live") or [])
sys.exit(0 if st=="MIGRATION_FAILED" and stage in ("stage","disable-resurrection","stop","verify-off") and "launchd:com.clawd.ghl-mcp" in live else 1)' \
  "$BOX3/home/.openclaw/.retired/ghl-mcp-migration-failed.json" 2>/dev/null \
  && pass "(J5) the failure receipt records a real stage and the launchd residual" \
  || fail "(J5) the failure receipt is missing, stage-less, or does not name the residual"

OUT="$(run_verify "$BOX3")"; RC=$?
[ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'launchd:com.clawd.ghl-mcp' \
  && pass "(J6) the verifier names the surviving launchd identity, not a blanket failure" \
  || fail "(J6) verifier did not name the surviving launchd identity (rc=$RC)"

# ── K. RETRY: the same box retires cleanly once the blocker is gone ───────
OUT="$(run_as "$BOX3" "" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in
  *RETIRED_VERIFIED_OFF*) pass "(K) retry after a failed stop -> VERIFIED_OFF" ;;
  *) fail "(K) retry did not reach VERIFIED_OFF: $S" ;;
esac
[ "$RC" = "0" ] && pass "(K2) retry exits 0" || fail "(K2) retry rc=$RC"
[ -f "$BOX3/home/.openclaw/.retired/ghl-mcp-retirement.json" ] \
  && pass "(K3) the success receipt exists after the retry" \
  || fail "(K3) no success receipt after the retry"
OUT="$(run_verify "$BOX3")"; RC=$?
[ "$RC" = "0" ] && pass "(K4) the verifier agrees the retried box is RETIRED_OK" \
  || { fail "(K4) verifier rc=$RC after a successful retry"; printf '%s\n' "$OUT" | tail -6 >&2; }

# ── L. PARTIAL TRANSACTION: leftovers without a receipt are MISCONFIGURED ──
BOX4="$WORK/box4"; make_box "$BOX4"
rm -f "$BOX4/lc/loaded.com.clawd.ghl-mcp" "$BOX4/pm2/app" "$BOX4/cron/table" \
      "$BOX4/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" \
      "$BOX4/home/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist"
OUT="$(run_verify "$BOX4")"; RC=$?
[ "$RC" = "3" ] && printf '%s' "$OUT" | grep -qF 'residual:install-dir:' \
  && pass "(L) a half-retired box (no receipt, tree left) is MISCONFIGURED and names the residual" \
  || { fail "(L) partial transaction: expected rc=3 with residual:install-dir, got rc=$RC"; printf '%s\n' "$OUT" | grep -F FAIL | head -5 >&2; }

# ── M. UPDATE / RESTART NO-RESURRECTION ───────────────────────────────────
# A stale updater or a reboot re-creates the launch surface. The verifier must
# catch each one on the already-retired box.
printf '<plist><dict><key>Label</key><string>com.clawd.ghl-mcp</string><key>RunAtLoad</key><true/></dict></plist>\n' \
  > "$BOX/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist"
touch "$BOX/lc/loaded.com.clawd.ghl-mcp"
OUT="$(run_verify "$BOX")"; RC=$?
[ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'launchd:com.clawd.ghl-mcp' \
  && pass "(M) an update/reboot that re-creates the plist is caught as STILL_RUNNING" \
  || fail "(M) a resurrected launchd job was not caught (rc=$RC)"
rm -f "$BOX/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" "$BOX/lc/loaded.com.clawd.ghl-mcp"
touch "$BOX/pm2/app"
OUT="$(run_verify "$BOX")"; RC=$?
[ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'pm2:ghl-community-mcp' \
  && pass "(M2) a re-registered pm2 app (pm2 resurrect path) is caught" \
  || fail "(M2) a re-registered pm2 app was not caught (rc=$RC)"
rm -f "$BOX/pm2/app"
printf '*/15 * * * * bash "%s" --once --heal # managed:ghl-mcp-probe\n' \
  "$BOX/home/.openclaw/scripts/ghl-mcp-probe.sh" > "$BOX/cron/table"
OUT="$(run_verify "$BOX")"; RC=$?
[ "$RC" = "1" ] && printf '%s' "$OUT" | grep -qF 'probe:crontab:' \
  && pass "(M3) a re-installed probe schedule is caught" \
  || fail "(M3) a re-installed probe schedule was not caught (rc=$RC)"
rm -f "$BOX/cron/table"

echo ""
echo "ghl-mcp-retirement: $PASS passed, $FAIL failed"
[ "$FAIL" = "0" ] || exit 1
exit 0
