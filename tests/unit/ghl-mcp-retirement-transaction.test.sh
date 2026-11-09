#!/usr/bin/env bash
# tests/unit/ghl-mcp-retirement-transaction.test.sh
#
# GU-019/020/021 — the ORDERED RETIREMENT TRANSACTION (stages 1,3,4,5,6,7) in
# scripts/ghl-mcp-autostart.sh. OFFLINE and HERMETIC: every supervisor is
# stubbed on PATH (launchctl, pm2, crontab, openclaw) and nothing outside a
# throwaway sandbox is read or written. No launchctl/pm2/systemctl/crontab on
# this machine is ever invoked.
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
#   G  every env-file shape (.env.bak-<ts>, .env.*, *.env, *.env.bak*) in the
#      MCP dir stays OUT of the archive and IN PLACE, so a client's own credential
#      backup no longer fails the retirement at archive-secret-risk
#   H  the secret scan still guards everything else: a live value in a non-env
#      file, or a credential-named file, still refuses the retirement
#   I  the updater's MISCONFIGURED banner names no script the same run prunes
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOSTART="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
PATHS_LIB="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
BASE="${GHL_RETIRE_TEST_ROOT:-${TMPDIR:-/tmp}/ghl-retire-test}"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }

[ -f "$AUTOSTART" ] || { echo "missing $AUTOSTART" >&2; exit 1; }
[ -f "$PATHS_LIB" ] || { echo "missing $PATHS_LIB" >&2; exit 1; }
mkdir -p "$BASE" || exit 1
WORK="$(mktemp -d "$BASE/ghl-retire-tx.XXXXXX")" || exit 1
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
  bootout)
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

# ── Box 3: client env-file backups (G) ──────────────────────────────────────
# Big Fleet Roll 20261029: the tar excluded only the exact names .env and
# .ghl-mcp.env, so a client's own .env.bak-<ts> (holding the live key) was
# copied into every archive and the secret scan refused the retirement.
ENV_SHAPES=".env.bak-20260804T085754Z .env.bak .env.production .env.local prod.env .ghl-mcp.env.bak-20260910-ghl old.env.bak2 dist/.env.bak-nested"
put_env_backups() {  # put_env_backups <mcp dir>
  local M="$1" f
  mkdir -p "$M/dist"
  for f in $ENV_SHAPES; do
    printf 'GHL_API_KEY=pit-secret-value-0123456789\nGOHIGHLEVEL_LOCATION_ID=loc123\n' > "$M/$f"
  done
  # look-alikes that are NOT env files and must still be archived
  echo "module.exports = {}" > "$M/environment.js"
  echo "how env vars work" > "$M/docs-env-notes.md"
}
env_sums() {  # env_sums <mcp dir>  -> one cksum line per client env file
  local M="$1" f
  for f in .env .ghl-mcp.env $ENV_SHAPES; do
    if [ -f "$M/$f" ]; then cksum < "$M/$f" | sed "s|\$| $f|"; else echo "MISSING $f"; fi
  done
}

BOX3="$WORK/box3"; make_box "$BOX3"
M3="$BOX3/home/.openclaw/mcp-servers/ghl-community-mcp"
put_env_backups "$M3"
BEFORE3="$(env_sums "$M3")"

OUT="$(run_as "$BOX3" "" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in *RETIRED_VERIFIED_OFF*) pass "(G) env-file backups in the MCP dir -> VERIFIED_OFF" ;; *) fail "(G) env-file backups: '$S' (rc=$RC)" ;; esac
[ "$RC" = "0" ] && pass "(G2) exit 0 with env-file backups present" || fail "(G2) rc=$RC"

ARC3="$(ls -d "$BOX3"/home/.openclaw/.retired/archive-* 2>/dev/null | head -1)"
if [ -n "$ARC3" ]; then
  LEFT="$(find "$ARC3/tree" -type f \( -name '.env' -o -name '.env.*' -o -name '*.env' -o -name '*.env.bak*' -o -name '.env.bak-*' \) 2>/dev/null)"
  [ -z "$LEFT" ] && pass "(G3) no env-file shape reached the archive tree" || fail "(G3) archived env files: $(printf '%s' "$LEFT" | tr '\n' ' ')"
  if grep -rIlF -- 'pit-secret-value-0123456789' "$ARC3" 2>/dev/null | grep -q .; then
    fail "(G4) the live key value is in the archive"
  else
    pass "(G4) the live key value is absent from the archive"
  fi
  [ -f "$ARC3/tree/environment.js" ] && [ -f "$ARC3/tree/docs-env-notes.md" ] && [ -f "$ARC3/tree/dist/main.js" ] \
    && pass "(G5) non-env look-alikes (environment.js, docs-env-notes.md) are still archived" \
    || fail "(G5) a non-env file was dropped by the env excludes"
else
  fail "(G3) no archive produced"; fail "(G4) no archive produced"; fail "(G5) no archive produced"
fi
AFTER3="$(env_sums "$M3")"
[ "$BEFORE3" = "$AFTER3" ] && pass "(G6) every client env file is still in place, byte-identical" || fail "(G6) a client env file was moved, deleted or changed"

# ── Box 4: the scan still guards everything else (H) ────────────────────────
BOX4="$WORK/box4"; make_box "$BOX4"
M4="$BOX4/home/.openclaw/mcp-servers/ghl-community-mcp"
put_env_backups "$M4"
echo "const k='pit-secret-value-0123456789'" > "$M4/dist/leak.js"
OUT="$(run_as "$BOX4" "" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in *MIGRATION_FAILED*) pass "(H) a live value in a non-env file still refuses" ;; *) fail "(H) leak in dist/leak.js was not refused: '$S'" ;; esac
[ "$RC" = "1" ] && pass "(H2) refusal exits 1" || fail "(H2) rc=$RC"
grep -q 'archive-secret-risk' "$BOX4/home/.openclaw/.retired/ghl-mcp-migration-failed.json" 2>/dev/null \
  && pass "(H3) the receipt names stage archive-secret-risk" || fail "(H3) receipt does not name archive-secret-risk"
[ -f "$BOX4/home/Library/LaunchAgents/com.clawd.ghl-mcp.plist" ] && [ -f "$BOX4/pm2/app" ] \
  && pass "(H4) nothing was disabled (plist installed, pm2 app registered)" || fail "(H4) the refusal disabled a surface"
[ -f "$BOX4/home/.openclaw/.retired/ghl-mcp-retirement.json" ] && fail "(H5) a success marker was written" || pass "(H5) no success marker"
[ -f "$M4/dist/leak.js" ] && [ "$BEFORE3" = "$(env_sums "$M4")" ] \
  && pass "(H6) the source tree and the client env files were left untouched" || fail "(H6) the refusal changed the source tree"

BOX5="$WORK/box5"; make_box "$BOX5"
M5="$BOX5/home/.openclaw/mcp-servers/ghl-community-mcp"
put_env_backups "$M5"
echo '{}' > "$M5/credentials.json"
OUT="$(run_as "$BOX5" "" --retire)"; RC=$?; S="$(status_of "$OUT")"
case "$S" in *MIGRATION_FAILED*) pass "(H7) a credential-named file (credentials.json) still refuses" ;; *) fail "(H7) credentials.json was not refused: '$S'" ;; esac
[ "$RC" = "1" ] && pass "(H8) refusal exits 1" || fail "(H8) rc=$RC"

# ── (I) the updater banner must not name a script the same run prunes ───────
US="$REPO_ROOT/update-skills.sh"
PRUNED="$(grep -m1 -E '^[[:space:]]*local _retired="' "$US" | sed -E 's/.*_retired="([^"]*)".*/\1/')"
BANNER="$(awk '/GHL MCP \(Tier 2\) IS MISCONFIGURED/{f=1} f{print} f&&/Exiting 2 = content current/{exit}' "$US")"
if [ -z "$PRUNED" ] || [ -z "$BANNER" ]; then
  fail "(I) could not locate the pruned list or the MISCONFIGURED banner in update-skills.sh"
else
  BAD=""
  for n in $PRUNED; do printf '%s' "$BANNER" | grep -qF "$n" && BAD="$BAD $n"; done
  [ -z "$BAD" ] && pass "(I) the MISCONFIGURED banner names no pruned script" || fail "(I) the banner points at pruned script(s):$BAD"
  printf '%s' "$BANNER" | grep -qF 'ghl-mcp-autostart.sh --status' \
    && pass "(I2) the banner points at the retained tool's --status" || fail "(I2) the banner does not name 'ghl-mcp-autostart.sh --status'"
fi

echo ""
echo "ghl-mcp-retirement-transaction: $PASS passed, $FAIL failed"
[ "$FAIL" = "0" ] || exit 1
exit 0
