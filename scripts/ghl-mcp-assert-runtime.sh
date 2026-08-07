#!/usr/bin/env bash
# ghl-mcp-assert-runtime.sh — v21.6.0
#
# RUNTIME conformance gate for the GHL Community MCP (Tier 2, skill 36).
# It asserts what is ACTUALLY INSTALLED AND RUNNING ON THIS BOX.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS EXISTS — the single biggest guardrail v21.5.0 was missing
#
# qc-assert-ghl-mcp-supervised.sh is, by its own header, "a STATIC check of the
# SHIPPED SCRIPTS (not a live process probe)". It reads ghl-mcp-autostart.sh and
# asserts that the script WOULD write a crash-only plist with a pinned profile.
# It never opens the INSTALLED plist, never reads the live pm2 ecosystem or the
# systemd unit, never reads /health's tool count, and never looks at mcp.servers.
#
# The consequence, measured on the operator box on 2026-08-03: the static gate
# reports PASS while the live service runs `node dist/main.js` directly (not the
# crash-only launcher), with GHL_TOOL_PROFILE=full, KeepAlive=<true/> (the exact
# form the static gate calls FATAL), ThrottleInterval=10, no GHL_MCP_LOG_DIR, a
# 5.4 MB unrotated stderr.log, 859 tools on /health, ghl-community-mcp still
# registered in mcp.servers, and no build stamp at all. Every one of those is a
# FATAL invariant in the shipped script — and the static gate cannot see any of
# them, because a plist is only regenerated when the autostart actually runs,
# and a hand-edited plist persists indefinitely.
#
# A gate that reads the shipped script proves what a fresh install WOULD do.
# This gate proves what THIS box IS doing.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT IT ASSERTS (per-check PASS/FAIL with the OBSERVED value, never just a
# verdict — "FAIL" without the number it saw is not a diagnosis)
#
#   1  service definition present for this platform
#      Mac  : ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist
#      VPS  : pm2 app `ghl-community-mcp`, else /etc/systemd/system/ghl-mcp.service
#   2  it launches the CRASH-ONLY LAUNCHER (.ghl-mcp-launch.sh), not node directly
#   3  crash-only supervision:
#      Mac  : KeepAlive is a DICT with SuccessfulExit=false — never <true/>
#      VPS  : pm2 stop_exit_codes contains 0, or systemd Restart=on-failure
#   4  Mac: ThrottleInterval >= 300
#   5  GHL_TOOL_PROFILE in the live definition == the pin file's value
#   6  PORT and MCP_SERVER_PORT both == the pin file's port
#   7  GHL_MCP_LOG_DIR present in the live definition (the launcher cannot
#      rotate what it cannot find)
#   8  .ghl-mcp-build.json exists and its commit == GHL_MCP_VETTED_COMMIT
#   9  live /health tool count inside [EXPECT_MIN, EXPECT_MAX] for the profile
#  10  ghl-community-mcp ABSENT from mcp.servers (skill 36 v1.1.0 doctrine:
#      Tier 2 is on-demand curl. Verified against three independent sources in
#      this repo — 36-ghl-mcp-setup/wire.sh migration M2 REMOVES it,
#      qc-assert-ghl-mcp-supervised.sh CHECK 8 forbids re-registering it, and
#      ghl-mcp-autostart.sh deregister_tier2() removes it on every run.)
#  11  the periodic probe is installed AND its path exists (a cron line pointing
#      at a deleted script is a silently dead probe)
#  12  no log in $LOG_DIR exceeds GHL_MCP_LOG_MAX_BYTES * 1.5
#  13  the listener is bound to LOOPBACK, not 0.0.0.0  — WARN by default
#      ⚠️ WARN, NOT FAIL, and deliberately so: the pinned upstream build binds
#      0.0.0.0 and nothing in this repo can change that yet (it needs a
#      server-side patch — R2 in the hardening analysis). A check that fails on
#      every box for a condition this release does not fix is not a guardrail,
#      it is noise that gets the whole gate disabled. Set
#      GHL_MCP_REQUIRE_LOOPBACK=1 to promote it to FATAL the moment R2 lands.
#
# ─────────────────────────────────────────────────────────────────────────────
# SECRET HYGIENE — load-bearing, do not "simplify"
# `pm2 jlist` DUMPS the full process env, which on this box includes the GHL
# Private Integration Token. This script therefore NEVER echoes raw pm2/plist
# output. It extracts individual named keys and prints only those, and the ones
# it prints are non-secret by construction (profile, ports, log dir, script
# path). Never add a branch that prints the captured blob on failure.
#
# EXIT CODES
#   0  every FATAL check passed (warnings may still be present)
#   1  one or more FATAL checks failed — the INSTALLED service is misconfigured
#   2  nothing to assert on this box (no service definition and no MCP dir) —
#      INFO, not a failure: this is the state on every box that never installed
#      Tier 2, and on the repo/CI checkout. Callers must treat 2 as a SKIP.
#
# USAGE
#   ghl-mcp-assert-runtime.sh            # human-readable report
#   ghl-mcp-assert-runtime.sh --quiet    # exit code only
#
# Wired in:
#   scripts/qc-system-integrity.sh          CHECK X.13b
#   update-skills.sh                        post-autostart runtime verdict
#   config/ghl-mcp-pin.env                  step 6 of the pin-bump runbook

set -u

QUIET=0
for _arg in "$@"; do
  [ "$_arg" = "--quiet" ] && QUIET=1
done

FATAL_FAILURES=0
WARNINGS=0
CHECKS=0

_pass() { CHECKS=$((CHECKS+1)); [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] PASS  %s\n' "$*"; return 0; }
_fail() { CHECKS=$((CHECKS+1)); FATAL_FAILURES=$((FATAL_FAILURES+1))
          printf '[ghl-mcp-runtime] FAIL  %s\n' "$*" >&2; return 0; }
_warn() { CHECKS=$((CHECKS+1)); WARNINGS=$((WARNINGS+1))
          [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] WARN  %s\n' "$*"; return 0; }
_info() { [ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] INFO  %s\n' "$*"; return 0; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Platform + canonical paths (identical derivation to ghl-mcp-autostart.sh) ─
if [ -f /data/.openclaw/openclaw.json ]; then
  PLATFORM="vps"
  OC_ROOT="/data/.openclaw"
  MCP_DIR="/data/mcp-servers/ghl-community-mcp"
  LOG_DIR="/data/logs"
else
  PLATFORM="mac"
  OC_ROOT="$HOME/.openclaw"
  MCP_DIR="$HOME/mcp-servers/ghl-community-mcp"
  LOG_DIR="$HOME/Library/Logs/ghl-mcp"
fi
# Test/override hook, same convention as GHL_MCP_DIR / GHL_MCP_PLIST below: lets
# the VPS+pm2 branch (section B) be exercised in CI without a real /data mount.
# Real boxes never set this — PLATFORM is always detected from the filesystem.
PLATFORM="${GHL_MCP_PLATFORM_OVERRIDE:-$PLATFORM}"
# Test/override hooks so this gate can be exercised against a simulated box.
MCP_DIR="${GHL_MCP_DIR:-$MCP_DIR}"
LOG_DIR="${GHL_MCP_LOG_DIR_OVERRIDE:-$LOG_DIR}"
OC_JSON="${GHL_MCP_OC_JSON:-$OC_ROOT/openclaw.json}"
PLIST="${GHL_MCP_PLIST:-$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist}"
PROBE_PLIST="${GHL_MCP_PROBE_PLIST:-$HOME/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist}"
SYSTEMD_UNIT="${GHL_MCP_SYSTEMD_UNIT:-/etc/systemd/system/ghl-mcp.service}"
# Bind-determination sources (check 13). Overridable ONLY so the "no method
# available -> FATAL undeterminable" branch is reachable in CI; see the long
# note at check 13. Real boxes never set these.
_PROC_NET_TCP="${GHL_MCP_PROC_NET_TCP:-/proc/net/tcp}"
_PROC_NET_TCP6="${GHL_MCP_PROC_NET_TCP6:-/proc/net/tcp6}"
PM2_ECOSYSTEM="$MCP_DIR/ecosystem.config.js"
BUILD_STAMP="$MCP_DIR/.ghl-mcp-build.json"
LAUNCHER_NAME=".ghl-mcp-launch.sh"

# ── The pin is the expectation. Without it there is nothing to compare to. ───
_PIN_FILE=""
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  [ -f "$_c" ] && { _PIN_FILE="$_c"; break; }
done

# ── Is there anything installed here at all? ─────────────────────────────────
_HAVE_MAC_SVC=0; [ -f "$PLIST" ] && _HAVE_MAC_SVC=1
_HAVE_SYSTEMD=0; [ -f "$SYSTEMD_UNIT" ] && _HAVE_SYSTEMD=1
_HAVE_PM2=0
if command -v pm2 >/dev/null 2>&1 && pm2 describe ghl-community-mcp >/dev/null 2>&1; then _HAVE_PM2=1; fi
_HAVE_ECO=0; [ -f "$PM2_ECOSYSTEM" ] && _HAVE_ECO=1

if [ "$_HAVE_MAC_SVC" = "0" ] && [ "$_HAVE_SYSTEMD" = "0" ] && [ "$_HAVE_PM2" = "0" ] \
   && [ "$_HAVE_ECO" = "0" ] && [ ! -d "$MCP_DIR" ]; then
  _info "no GHL community MCP service definition and no $MCP_DIR on this box — Tier 2 is not installed here. Nothing to assert."
  exit 2
fi

if [ -z "$_PIN_FILE" ]; then
  _fail "config/ghl-mcp-pin.env is not on this box, so there is NO expectation to compare the running service against. Re-run update-skills.sh / install.sh (they deliver config/ to \$OC_CONFIG/config/)."
  printf '[ghl-mcp-runtime] VERDICT: %s FATAL, %s warning(s), %s check(s)\n' "$FATAL_FAILURES" "$WARNINGS" "$CHECKS" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$_PIN_FILE"
EXPECT_COMMIT="${GHL_MCP_VETTED_COMMIT:-}"
EXPECT_PROFILE="${GHL_MCP_TOOL_PROFILE:-}"
EXPECT_PORT="${GHL_MCP_PORT:-8765}"
EXPECT_MIN="${GHL_MCP_EXPECT_MIN_TOOLS:-1}"
EXPECT_MAX="${GHL_MCP_EXPECT_MAX_TOOLS:-200}"
EXPECT_LOG_MAX="${GHL_MCP_LOG_MAX_BYTES:-10485760}"
_info "platform=$PLATFORM  pin=$_PIN_FILE  expect: commit=${EXPECT_COMMIT:0:12} profile=$EXPECT_PROFILE port=$EXPECT_PORT tools=${EXPECT_MIN}..${EXPECT_MAX}"

# ── plist helpers ────────────────────────────────────────────────────────────
# Prefer PlistBuddy/plutil where present; fall back to a line-oriented read so
# this gate still works on a box without the developer tools. Only NAMED keys
# are ever extracted — never the whole dict (secret hygiene, see the header).
# NOTE ON THE sed FALLBACK: this repo writes `<key>K</key><string>V</string>`
# on ONE line, but a hand-edited or Xcode-formatted plist puts the value on the
# NEXT line. Both shapes are real on the fleet, so both are handled — a helper
# that only understood one of them would silently report <unset> and produce a
# confident, wrong FAIL.
_plist_value() {  # _plist_value <plist> <key>  — string or integer, any nesting
  local f="$1" k="$2" v=""
  # same-line form
  v="$(sed -n "s|.*<key>${k}</key>[[:space:]]*<string>\([^<]*\)</string>.*|\1|p" "$f" 2>/dev/null | head -1)"
  [ -n "$v" ] || v="$(sed -n "s|.*<key>${k}</key>[[:space:]]*<integer>\([^<]*\)</integer>.*|\1|p" "$f" 2>/dev/null | head -1)"
  # next-line form
  [ -n "$v" ] || v="$(sed -n "\|<key>${k}</key>|{n;s|.*<string>\([^<]*\)</string>.*|\1|p;}" "$f" 2>/dev/null | head -1)"
  [ -n "$v" ] || v="$(sed -n "\|<key>${k}</key>|{n;s|.*<integer>\([^<]*\)</integer>.*|\1|p;}" "$f" 2>/dev/null | head -1)"
  # PlistBuddy last (authoritative but absent on non-Mac and in CI containers)
  if [ -z "$v" ] && [ -x /usr/libexec/PlistBuddy ]; then
    v="$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:${k}" "$f" 2>/dev/null || true)"
    [ -n "$v" ] || v="$(/usr/libexec/PlistBuddy -c "Print :${k}" "$f" 2>/dev/null || true)"
  fi
  printf '%s' "$v"
}
_plist_env() { _plist_value "$1" "$2"; }
_plist_top() { _plist_value "$1" "$2"; }

# ── The pm2 field filter (see the SECRET HYGIENE note at the VPS branch) ─────
# Reduces a raw pm2 record to the SIX non-secret fields this gate reads, and
# emits nothing else. Everything in pm2_env other than these six — every
# credential value, the GHL PIT included — is dropped here and never leaves
# this program. Modelled on filter_pm2_record in
# 61-loop-protection-system/scripts/loop_common.py:164-172.
_GHL_FILTER_PM2_RECORD='
import json, sys
ALLOWED = ("GHL_TOOL_PROFILE", "PORT", "MCP_SERVER_PORT", "GHL_MCP_LOG_DIR")
try:
    apps = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
for a in apps:
    if a.get("name") != "ghl-community-mcp":
        continue
    env = a.get("pm2_env") if isinstance(a.get("pm2_env"), dict) else {}
    print("__script__=%s" % (env.get("pm_exec_path") or a.get("pm_exec_path") or ""))
    # DEFECT 3 (proven live 2026-08-04): pm2 v7.0.1 stores a single-element
    # stop_exit_codes as the BARE SCALAR 0, not the list [0]. The old
    # (env.get("stop_exit_codes") or []) treated the falsy int 0 as ABSENT and
    # silently dropped it, so a CORRECTLY configured box (stop_exit_codes=0)
    # produced an empty __stop_exit_codes__ field and a false FATAL downstream
    # (the runtime gate reported stop_exit_codes as unset). Verified live: an
    # isolated disposable pm2 app (exits 0, autorestart:true) was NOT
    # restarted -- restart_time stayed 0 for 14+ seconds -- so crash-only
    # semantics genuinely worked; only this parser was wrong. None (the dict
    # key truly absent) is the only shape that means "nothing declared"; a
    # real value -- scalar 0, "0", or a list -- must survive even when it is
    # falsy. NOTE: this Python body is wrapped in a bash SINGLE-quoted string
    # below, so these comments must never contain a literal apostrophe or
    # single-quote mark -- one did once, and it silently closed the bash
    # string early, splicing the rest of the Python source out onto the
    # command line as literal bash commands.
    _sec = env.get("stop_exit_codes")
    if _sec is None or _sec == "":
        _sec_list = []
    elif isinstance(_sec, (list, tuple)):
        _sec_list = list(_sec)
    else:
        _sec_list = [_sec]
    print("__stop_exit_codes__=%s" % ",".join(str(x) for x in _sec_list))
    for k in ALLOWED:
        print("%s=%s" % (k, env.get(k) or ""))
    break
'

# ═════════════════════════════════════════════════════════════════════════════
# A. Mac / launchd
# ═════════════════════════════════════════════════════════════════════════════
if [ "$PLATFORM" = "mac" ]; then
  if [ "$_HAVE_MAC_SVC" = "0" ]; then
    _fail "no installed launchd service at $PLIST — the MCP dir exists but nothing supervises it. Run scripts/ghl-mcp-autostart.sh on this box."
  else
    _PLIST_RAW="$(cat "$PLIST" 2>/dev/null || true)"

    # 2. launcher, not node directly
    case "$_PLIST_RAW" in
      *"$LAUNCHER_NAME"*)
        _pass "launchd ProgramArguments run the crash-only launcher ($LAUNCHER_NAME)" ;;
      *"dist/main.js"*)
        _fail "launchd ProgramArguments launch 'node dist/main.js' DIRECTLY, bypassing $LAUNCHER_NAME — a rejected PIT will make main.js exit(1) on every launch and the supervisor will relaunch it forever (D3). Re-run scripts/ghl-mcp-autostart.sh." ;;
      *)
        _fail "launchd ProgramArguments reference neither $LAUNCHER_NAME nor dist/main.js — the installed plist is not the one this repo writes." ;;
    esac

    # 3. crash-only KeepAlive
    case "$_PLIST_RAW" in
      *"<key>KeepAlive</key>"*"<true/>"*)
        # Distinguish the boolean form from the dict form containing <true/>.
        if printf '%s' "$_PLIST_RAW" | tr -d ' \t\n' | grep -q '<key>KeepAlive</key><true/>'; then
          _fail "launchd KeepAlive is the UNCONDITIONAL boolean <true/> — it restarts even a deliberate clean exit, which turns a bad/rotated PIT into an endless relaunch loop. The crash-only dict (SuccessfulExit=false / Crashed=true) is mandatory."
        elif printf '%s' "$_PLIST_RAW" | tr -d ' \t\n' | grep -q '<key>SuccessfulExit</key><false/>'; then
          _pass "launchd restart policy is CRASH-ONLY (KeepAlive dict, SuccessfulExit=false)"
        else
          _fail "launchd KeepAlive is present but is neither the crash-only dict nor a recognised form — observed plist does not contain <key>SuccessfulExit</key><false/>."
        fi ;;
      *)
        if printf '%s' "$_PLIST_RAW" | tr -d ' \t\n' | grep -q '<key>SuccessfulExit</key><false/>'; then
          _pass "launchd restart policy is CRASH-ONLY (KeepAlive dict, SuccessfulExit=false)"
        else
          _fail "launchd plist has no crash-only KeepAlive dict (SuccessfulExit=false)."
        fi ;;
    esac

    # 4. ThrottleInterval
    _TI="$(_plist_top "$PLIST" ThrottleInterval)"
    if [ -z "$_TI" ]; then
      _fail "launchd ThrottleInterval is absent — observed: <unset>; required: >= 300 (the canonical fleet shape). Without it launchd relaunches on its 10s default."
    elif [ "$_TI" -ge 300 ] 2>/dev/null; then
      _pass "launchd ThrottleInterval=$_TI (>= 300)"
    else
      _fail "launchd ThrottleInterval=$_TI — required >= 300. A low throttle is what turns a mis-detected crash into a hot relaunch loop."
    fi

    # 5/6/7. env pins
    _P="$(_plist_env "$PLIST" GHL_TOOL_PROFILE)"
    if [ -z "$_P" ]; then
      _fail "launchd EnvironmentVariables has NO GHL_TOOL_PROFILE — observed: <unset>; expected: $EXPECT_PROFILE. Upstream's default is 'full' = the entire 858-tool catalogue."
    elif [ "$_P" = "$EXPECT_PROFILE" ]; then
      _pass "launchd GHL_TOOL_PROFILE=$_P matches the pin"
    else
      _fail "launchd GHL_TOOL_PROFILE=$_P but the pin says $EXPECT_PROFILE — the live service is serving a different tool surface than the fleet standard."
    fi
    for _k in PORT MCP_SERVER_PORT; do
      _V="$(_plist_env "$PLIST" "$_k")"
      if [ "$_V" = "$EXPECT_PORT" ]; then
        _pass "launchd $_k=$_V matches the pin"
      else
        _fail "launchd $_k='${_V:-<unset>}' but the pin says $EXPECT_PORT — main.js reads PORT before MCP_SERVER_PORT, so an unpinned pair binds a random port."
      fi
    done
    _LD="$(_plist_env "$PLIST" GHL_MCP_LOG_DIR)"
    if [ -n "$_LD" ]; then
      _pass "launchd GHL_MCP_LOG_DIR=$_LD (the launcher can rotate)"
    else
      _fail "launchd EnvironmentVariables has NO GHL_MCP_LOG_DIR — the launcher's copytruncate rotation is a no-op without it, which is how stderr.log reached 5.4 MB on the operator box."
    fi
  fi

  # 11. periodic probe
  if [ -f "$PROBE_PLIST" ]; then
    if command -v launchctl >/dev/null 2>&1 && launchctl list 2>/dev/null | grep -q 'com.clawd.ghl-mcp-probe'; then
      _pass "periodic liveness probe installed AND loaded (com.clawd.ghl-mcp-probe)"
    else
      _warn "com.clawd.ghl-mcp-probe.plist exists but is not listed as loaded — the 15-minute deaf-server detector is not running. launchctl bootstrap it, or re-run scripts/ghl-mcp-autostart.sh."
    fi
    _PP="$(sed -n 's|.*<string>\(.*ghl-mcp-probe\.sh\)</string>.*|\1|p' "$PROBE_PLIST" 2>/dev/null | head -1)"
    if [ -n "$_PP" ] && [ ! -f "$_PP" ]; then
      _fail "the probe plist points at $_PP, which DOES NOT EXIST — a probe that cannot be found is a silently dead probe."
    fi
  else
    _fail "no periodic liveness probe installed ($PROBE_PLIST absent) — nothing on this box would detect an alive-but-deaf MCP, which is exactly the two-day outage signature."
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# B. VPS / pm2, else systemd
# ═════════════════════════════════════════════════════════════════════════════
if [ "$PLATFORM" = "vps" ]; then
  if [ "$_HAVE_PM2" = "1" ]; then
    # ── SECRET HYGIENE — the single choke point. Do not "simplify" this. ─────
    # A raw `pm2 jlist` record carries pm2_env, which is the process
    # ENVIRONMENT — live credential VALUES, including the GHL Private
    # Integration Token. A fleet review leaked secrets exactly that way.
    #
    # So the blob NEVER lands anywhere: it is piped STRAIGHT into the filter
    # below, which emits ONLY six non-secret fields as KEY=VALUE lines. No temp
    # file, no unfiltered shell variable, nothing to leak under `set -x` or an
    # error trace. Same discipline as filter_pm2_record in
    # 61-loop-protection-system/scripts/loop_common.py:164-172, which is the
    # canonical implementation of this rule.
    _PM2_SAFE=""
    if command -v python3 >/dev/null 2>&1; then
      _PM2_SAFE="$(pm2 jlist 2>/dev/null | python3 -c "$_GHL_FILTER_PM2_RECORD" 2>/dev/null || true)"
    fi
    _pm2_field() {  # read one already-filtered, already-non-secret field
      printf '%s\n' "$_PM2_SAFE" | sed -n "s|^$1=||p" | head -1
    }
    if ! command -v python3 >/dev/null 2>&1; then
      _warn "python3 not on PATH — cannot parse the live pm2 definition; falling back to the on-disk ecosystem.config.js, which is what pm2 WOULD load, not necessarily what it IS running."
      _HAVE_PM2=0
    else
      _SCRIPT="$(_pm2_field __script__)"
      case "$_SCRIPT" in
        *"$LAUNCHER_NAME"*) _pass "pm2 runs the crash-only launcher ($_SCRIPT)" ;;
        *dist/main.js*)     _fail "pm2 runs 'node dist/main.js' directly ($_SCRIPT), bypassing $LAUNCHER_NAME — a rejected PIT becomes an endless relaunch loop (D3)." ;;
        "")                 _fail "pm2 app ghl-community-mcp has no readable script path — cannot confirm it runs the crash-only launcher." ;;
        *)                  _fail "pm2 runs '$_SCRIPT', which is neither $LAUNCHER_NAME nor dist/main.js — this is not the definition this repo writes." ;;
      esac
      _SEC="$(_pm2_field __stop_exit_codes__)"
      case ",$_SEC," in
        *,0,*) _pass "pm2 stop_exit_codes includes 0 (a clean exit is not restarted)" ;;
        *)     _fail "pm2 stop_exit_codes='${_SEC:-<unset>}' — 0 must be present or a deliberate clean exit (bad PIT) relaunches forever." ;;
      esac
      _P="$(_pm2_field GHL_TOOL_PROFILE)"
      if [ "$_P" = "$EXPECT_PROFILE" ]; then _pass "pm2 env GHL_TOOL_PROFILE=$_P matches the pin"
      else _fail "pm2 env GHL_TOOL_PROFILE='${_P:-<unset>}' but the pin says $EXPECT_PROFILE."; fi
      for _k in PORT MCP_SERVER_PORT; do
        _V="$(_pm2_field "$_k")"
        if [ "$_V" = "$EXPECT_PORT" ]; then _pass "pm2 env $_k=$_V matches the pin"
        else _fail "pm2 env $_k='${_V:-<unset>}' but the pin says $EXPECT_PORT."; fi
      done
      _LD="$(_pm2_field GHL_MCP_LOG_DIR)"
      if [ -n "$_LD" ]; then _pass "pm2 env GHL_MCP_LOG_DIR=$_LD (the launcher can rotate)"
      else _fail "pm2 env has no GHL_MCP_LOG_DIR — the launcher's rotation is a no-op without it."; fi
    fi
  fi

  if [ "$_HAVE_PM2" = "0" ] && [ "$_HAVE_SYSTEMD" = "1" ]; then
    _UNIT="$(cat "$SYSTEMD_UNIT" 2>/dev/null || true)"
    case "$_UNIT" in
      *"$LAUNCHER_NAME"*) _pass "systemd ExecStart runs the crash-only launcher" ;;
      *)                  _fail "systemd ExecStart does not run $LAUNCHER_NAME — a rejected PIT becomes a restart loop (D3)." ;;
    esac
    case "$_UNIT" in
      *"Restart=always"*)     _fail "systemd unit uses Restart=always — crash-only requires Restart=on-failure." ;;
      *"Restart=on-failure"*) _pass "systemd Restart=on-failure (crash-only)" ;;
      *)                      _fail "systemd unit declares no Restart policy — observed: <unset>; required: on-failure." ;;
    esac
    _P="$(printf '%s\n' "$_UNIT" | sed -n 's/^Environment=GHL_TOOL_PROFILE=//p' | head -1)"
    if [ "$_P" = "$EXPECT_PROFILE" ]; then _pass "systemd Environment GHL_TOOL_PROFILE=$_P matches the pin"
    else _fail "systemd Environment GHL_TOOL_PROFILE='${_P:-<unset>}' but the pin says $EXPECT_PROFILE."; fi
    for _k in PORT MCP_SERVER_PORT; do
      _V="$(printf '%s\n' "$_UNIT" | sed -n "s/^Environment=${_k}=//p" | head -1)"
      if [ "$_V" = "$EXPECT_PORT" ]; then _pass "systemd Environment $_k=$_V matches the pin"
      else _fail "systemd Environment $_k='${_V:-<unset>}' but the pin says $EXPECT_PORT."; fi
    done
    case "$_UNIT" in
      *GHL_MCP_LOG_DIR*) _pass "systemd Environment carries GHL_MCP_LOG_DIR" ;;
      *)                 _fail "systemd Environment has no GHL_MCP_LOG_DIR — rotation is a no-op without it." ;;
    esac
  fi

  if [ "$_HAVE_PM2" = "0" ] && [ "$_HAVE_SYSTEMD" = "0" ]; then
    _fail "no live pm2 app 'ghl-community-mcp' and no $SYSTEMD_UNIT — the MCP dir exists but nothing supervises it. Run scripts/ghl-mcp-autostart.sh on this box."
  fi

  # 11. periodic probe (cron) — and its target must EXIST
  if command -v crontab >/dev/null 2>&1; then
    _CRON="$(crontab -l 2>/dev/null || true)"
    _CRON_PROBE="$(printf '%s\n' "$_CRON" | sed -n 's|.*[[:space:]]\(/[^[:space:]]*ghl-mcp-probe\.sh\).*|\1|p' | head -1)"
    if [ -z "$_CRON_PROBE" ]; then
      _fail "no ghl-mcp-probe.sh line in this box's crontab — nothing would detect an alive-but-deaf MCP."
    elif [ ! -f "$_CRON_PROBE" ]; then
      _fail "the probe cron line points at $_CRON_PROBE, which DOES NOT EXIST — a stale path means a silently dead 15-minute probe."
    else
      _pass "periodic liveness probe cron installed and its target exists ($_CRON_PROBE)"
    fi
  else
    _warn "crontab not available — cannot verify the periodic probe is scheduled."
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# C. Platform-independent: build stamp, live tool count, registration, logs, bind
# ═════════════════════════════════════════════════════════════════════════════

# 8. build stamp bound to the pin
if [ ! -f "$BUILD_STAMP" ]; then
  _fail "no build stamp at $BUILD_STAMP — this box has never run the pinned build path, so whatever is in dist/ is of unknown provenance."
else
  _BC="$(sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' "$BUILD_STAMP" 2>/dev/null | head -1)"
  if [ "$_BC" = "$EXPECT_COMMIT" ]; then
    _pass "build stamp commit=${_BC:0:12} matches the pin"
  else
    _fail "build stamp commit='${_BC:0:12}' but the pin says '${EXPECT_COMMIT:0:12}' — the running build is NOT the vetted commit. Re-run scripts/ghl-mcp-autostart.sh."
  fi
fi

# 9. live tool count inside the profile's band
if command -v curl >/dev/null 2>&1; then
  _HEALTH="$(curl -fsS --max-time 5 "http://127.0.0.1:${EXPECT_PORT}/health" 2>/dev/null || true)"
  if [ -z "$_HEALTH" ]; then
    _warn "nothing answered http://127.0.0.1:${EXPECT_PORT}/health — the tool-count assertion could not run (the server may be legitimately stopped after a clean credential-blocked exit; scripts/ghl-mcp-probe.sh is the liveness authority)."
  else
    case "$_HEALTH" in
      *0.5.3-local*|*cognee*|*Cognee*)
        _fail "port ${EXPECT_PORT} is answered by Cognee, not the GHL MCP — the wrong service owns the canonical port." ;;
      *)
        _TOOLS="$(printf '%s' "$_HEALTH" | sed -n 's/.*"tools":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
        if [ -z "$_TOOLS" ]; then
          _warn "/health answered but reported no tool count — cannot verify the profile took effect."
        elif [ "$_TOOLS" -ge "$EXPECT_MIN" ] 2>/dev/null && [ "$_TOOLS" -le "$EXPECT_MAX" ] 2>/dev/null; then
          _pass "live /health tools=$_TOOLS is inside the ${EXPECT_MIN}..${EXPECT_MAX} band for profile=$EXPECT_PROFILE"
        else
          _fail "live /health tools=$_TOOLS is OUTSIDE the ${EXPECT_MIN}..${EXPECT_MAX} band for profile=$EXPECT_PROFILE — GHL_TOOL_PROFILE is not taking effect on the running process (859 = the full 858-tool catalogue + 1)."
        fi ;;
    esac
  fi
else
  _warn "curl not on PATH — the live tool-count assertion could not run."
fi

# 10. Tier 2 must be ABSENT from mcp.servers (skill 36 v1.1.0 doctrine)
_REGISTERED="unknown"
if [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
  _REGISTERED="$(OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    servers = (cfg.get("mcp", {}) or {}).get("servers", {}) or {}
    print("yes" if "ghl-community-mcp" in servers else "no")
except Exception:
    print("unknown")
PYEOF
)"
fi
case "$_REGISTERED" in
  no)  _pass "ghl-community-mcp is ABSENT from mcp.servers (Tier 2 stays on-demand curl — no per-init tool-catalogue tax)" ;;
  yes) _fail "ghl-community-mcp IS REGISTERED in mcp.servers — skill 36 v1.1.0 doctrine (wire.sh migration M2, qc-ghl-mcp-setup.sh Section D, qc-assert CHECK 8) requires it ABSENT: its tool schemas otherwise ride in EVERY agent init, and a down/deaf server makes every init pay the full connectionTimeoutMs. Run: openclaw mcp unset ghl-community-mcp  (NOT 'mcp remove' — that is not a command on OpenClaw 2026.7.1-2 and exits 1 with 'Too many arguments for this command'; every call site in this repo used it, swallowed by '|| true', which is why this check never passed on any box). Then RE-READ the config: the gateway rewrites openclaw.json from memory and can undo a file-level removal." ;;
  *)   _warn "could not read mcp.servers from $OC_JSON — the Tier 2 registration assertion did not run." ;;
esac

# 12. log size ceiling
_LIMIT=$(( EXPECT_LOG_MAX * 3 / 2 ))
if [ -d "$LOG_DIR" ]; then
  _OVER=0
  for _lf in "$LOG_DIR/stderr.log" "$LOG_DIR/stdout.log" \
             "$LOG_DIR/ghl-mcp.log" "$LOG_DIR/ghl-mcp.err.log" "$LOG_DIR/probe.log"; do
    [ -f "$_lf" ] || continue
    _SZ="$(wc -c < "$_lf" 2>/dev/null | tr -d ' ')"
    [ -n "$_SZ" ] || continue
    if [ "$_SZ" -gt "$_LIMIT" ] 2>/dev/null; then
      _fail "$_lf is ${_SZ} bytes, over the ${_LIMIT}-byte ceiling (GHL_MCP_LOG_MAX_BYTES * 1.5) — rotation is not happening on this box."
      _OVER=1
    fi
  done
  [ "$_OVER" = "0" ] && _pass "no MCP log exceeds the ${_LIMIT}-byte ceiling (rotation is working)"
else
  _warn "$LOG_DIR does not exist — the log-size assertion did not run."
fi

# ── 13. LOOPBACK BIND ────────────────────────────────────────────────────────
#
# DEFECT 3 (proven on the VPS pilot box). The old form was `if command -v lsof`
# with NO else branch, so in a slim container — where lsof simply is not
# installed — `_BIND_VERDICT` stayed "unknown" and fell into an `_info` line
# reading "no listener observed (or lsof unavailable)". That single sentence
# conflated two completely different states:
#
#     the port is FREE                     (nothing to expose — genuinely fine)
#     we have NO WAY TO TELL what is bound (a security check that did not run)
#
# The second was reported as INFO, which is indistinguishable from a pass. It
# masked a real, independently-confirmed `0.0.0.0:8765` exposure on that box
# (LISTEN state `0A` in /proc/net/tcp). A security check that cannot determine
# its answer has FAILED; it has not passed.
#
# TWO CHANGES:
#   1. lsof is no longer the only way to ask. Fall back to `ss`, then to
#      /proc/net/tcp + /proc/net/tcp6 parsed directly (the container case — no
#      tools needed at all, state 0A = LISTEN, the local address is hex
#      ADDR:PORT). Determination now succeeds almost everywhere it previously
#      silently gave up.
#   2. UNDETERMINABLE IS FATAL. If no method could answer, that is a FATAL
#      "cannot determine", never an INFO. "Port proven free" stays INFO, because
#      that is a real answer, not an absence of one.
#
# The all-interfaces verdict is now FATAL BY DEFAULT. The old WARN existed
# because "fixing it needs a server-side change (R2)" — R2 has since landed: the
# generated .ghl-mcp-bind-guard.cjs moves the bind, proven differentially on a
# live box (*:8791 -> 127.0.0.1:8791) and by tests/unit/ghl-mcp-bind-guard.test.sh.
# The reason for the exemption is gone, so the exemption is gone.
# GHL_MCP_REQUIRE_LOOPBACK=0 downgrades it for a deliberate, per-box operator
# decision — it is no longer the default posture.

# _bind_addrs_for_port <port> — print one local address per LISTEN socket on the
# port, one per line. Exit 0 = the question was ANSWERED (zero lines = the port
# is genuinely free). Exit 1 = no method available; the answer is UNKNOWN.
_bind_addrs_for_port() {
  local _p="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$_p" -sTCP:LISTEN 2>/dev/null | tail -n +2 | awk '{print $9}'
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH 2>/dev/null | awk -v p=":$_p" '$4 ~ p"$" {print $4}'
    return 0
  fi
  # No tools at all — the slim-container case. /proc/net/tcp{,6} is always there
  # on Linux. Columns: sl local_address rem_address st … ; st 0A = TCP_LISTEN.
  # local_address is HEX addr:HEX port, little-endian for IPv4.
  #
  # The two paths are overridable for the SAME reason GHL_MCP_DIR / GHL_MCP_PLIST /
  # GHL_MCP_OC_JSON above are: this gate must be exercisable against a simulated
  # box. Specifically, the "no method available" branch below is otherwise
  # unreachable on Linux (where /proc always exists) and therefore untestable in
  # CI — and an untested fail-path is exactly what let the silent INFO downgrade
  # survive. Defaults are the real paths; nothing on a box sets these.
  # python3 is required to decode the hex addresses. Without it this branch would
  # `return 127` from a missing interpreter, which the caller would read as
  # "answered, zero listeners" — a FALSE INFO, i.e. the same silent downgrade in
  # a new costume. Fall through to the undeterminable FATAL instead.
  if { [ -r "$_PROC_NET_TCP" ] || [ -r "$_PROC_NET_TCP6" ]; } \
     && command -v python3 >/dev/null 2>&1; then
    PORT_DEC="$_p" PROC_TCP="$_PROC_NET_TCP" PROC_TCP6="$_PROC_NET_TCP6" python3 - <<'PYEOF' 2>/dev/null
import os, socket, struct
port = int(os.environ["PORT_DEC"])
def emit(path, v6):
    try:
        lines = open(path).read().splitlines()[1:]
    except Exception:
        return
    for ln in lines:
        f = ln.split()
        if len(f) < 4 or f[3] != "0A":
            continue
        hexaddr, hexport = f[1].split(":")
        if int(hexport, 16) != port:
            continue
        if v6:
            raw = bytes.fromhex(hexaddr)
            raw = b"".join(struct.pack("<I", struct.unpack(">I", raw[i:i+4])[0])
                           for i in range(0, 16, 4))
            ip = socket.inet_ntop(socket.AF_INET6, raw)
        else:
            ip = socket.inet_ntop(socket.AF_INET, struct.pack("<I", int(hexaddr, 16)))
        print("%s:%d" % (ip, port))
emit(os.environ.get("PROC_TCP", "/proc/net/tcp"), False)
emit(os.environ.get("PROC_TCP6", "/proc/net/tcp6"), True)
PYEOF
    return $?
  fi
  return 1
}

_BIND_ADDRS=""
_BIND_DETERMINED=1
if _BIND_ADDRS="$(_bind_addrs_for_port "$EXPECT_PORT")"; then
  _BIND_DETERMINED=0
fi

if [ "$_BIND_DETERMINED" != "0" ]; then
  _fail "the bind address on :${EXPECT_PORT} is UNDETERMINABLE on this box — lsof, ss and /proc/net/tcp are all unavailable, so this security check could not run. This is a FATAL 'cannot determine', NOT a pass: the identical situation on a VPS box silently degraded to INFO and masked a real 0.0.0.0:${EXPECT_PORT} exposure. Install lsof or iproute2, or run this gate where /proc is readable."
elif [ -z "$_BIND_ADDRS" ]; then
  _info "nothing is LISTENING on :${EXPECT_PORT} (determined, not assumed) — there is no bind to expose. The server may be legitimately stopped after a clean credential-blocked exit."
else
  _BIND_VERDICT="loopback"
  while IFS= read -r _addr; do
    [ -n "$_addr" ] || continue
    case "$_addr" in
      127.*|"[::1]:"*|"::1:"*|localhost:*)            : ;;                       # loopback
      "*:${EXPECT_PORT}"|"0.0.0.0:${EXPECT_PORT}"|"[::]:${EXPECT_PORT}"|":::${EXPECT_PORT}")
                                                      _BIND_VERDICT="all-interfaces" ;;
      *)                                              [ "$_BIND_VERDICT" = "all-interfaces" ] || _BIND_VERDICT="other" ;;
    esac
  done <<EOF
$_BIND_ADDRS
EOF
  case "$_BIND_VERDICT" in
    loopback)
      _pass "listener on :${EXPECT_PORT} is bound to LOOPBACK (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' '))" ;;
    all-interfaces)
      if [ "${GHL_MCP_REQUIRE_LOOPBACK:-1}" = "0" ]; then
        _warn "listener on :${EXPECT_PORT} is bound to ALL INTERFACES (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' ')). Demoted to WARN only because GHL_MCP_REQUIRE_LOOPBACK=0 was set explicitly on this box."
      else
        _fail "listener on :${EXPECT_PORT} is bound to ALL INTERFACES (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' ')) — an UNAUTHENTICATED, CRM-credentialed endpoint reachable by any local process and any LAN host. The bind guard (.ghl-mcp-bind-guard.cjs) either is not installed or was not loaded by the running process. FIX: re-run scripts/ghl-mcp-autostart.sh, which regenerates the guard and restarts the service through the launcher that preloads it."
      fi ;;
    *)
      _fail "listener on :${EXPECT_PORT} is bound to an address this gate does not recognise as loopback (observed: $(printf '%s' "$_BIND_ADDRS" | tr '\n' ' ')). An unrecognised bind on a CRM-credentialed, unauthenticated port is treated as exposed, never as fine — inspect it by hand." ;;
  esac
fi

# ── Verdict ──────────────────────────────────────────────────────────────────
if [ "$FATAL_FAILURES" -gt 0 ]; then
  printf '[ghl-mcp-runtime] VERDICT: %s FATAL, %s warning(s), %s check(s) — the INSTALLED service does not match the shipped standard. The static gate cannot see any of this.\n' \
    "$FATAL_FAILURES" "$WARNINGS" "$CHECKS" >&2
  exit 1
fi
[ "$QUIET" = "0" ] && printf '[ghl-mcp-runtime] VERDICT: OK — %s check(s) passed, %s warning(s). The RUNNING service matches the pin.\n' "$CHECKS" "$WARNINGS"
exit 0
