#!/usr/bin/env bash
# tests/unit/operator-chat-id-resolver.test.sh
#
# Regression lock for the CIRCULAR ALERTING DEPENDENCY: `resolve_chat()`-style
# lookups that call `openclaw config get` depend on a LIVE gateway websocket
# connection. Proven live 2026-08-03: a client box was down ~20h, its watchdog
# wrote 79 "RECOVERY FAILED" entries, and every single one blanked because the
# CLI call failed ("1006 abnormal closure") and the old resolver's ONLY lookup
# path required exactly the thing it existed to report as broken.
#
# THREE DEFECTS THIS LOCKS (see shared-utils/operator-chat-id.sh header for the
# full writeup):
#   (1) The resolver never checked OPERATOR_HELP_CHAT_ID — the back-compat key
#       scripts/configure-operator-telegram.sh writes alongside the primary
#       key on every run. Proven live: a box with ONLY that key set in config
#       resolved empty.
#   (2) The resolver's ONLY lookup path was `openclaw config get`, which
#       requires the gateway. A dead/unreachable gateway blanked EVERY key,
#       even ones that WERE configured on disk.
#   (3) closeout-readiness-watchdog.sh and run-closeout.sh each reimplemented
#       their own pure-process-environment fallback chain instead of calling
#       the shared resolver — bypassing both the config-file lookup AND the
#       OPERATOR_HELP_CHAT_ID fallback, and (for the cron-dispatched watchdog)
#       reading an environment frozen at the LAST gateway restart.
#
# HERMETIC. A fake `openclaw` CLI (tests/fixtures/operator-chat-id-resolver/
# fake-openclaw-chatid.py) simulates a dead gateway without any live gateway,
# process, or network call anywhere near this test. No `openclaw message send`
# is ever real — the fake CLI only appends the argv it was called with to a
# capture file. NOTHING in this file sends a Telegram message, hits a webhook,
# or touches a real ~/.openclaw. Every fixture chat id below is a synthetic
# placeholder, never a real operator/client id.
#
# MUTATION PROOF (non-vacuous, house style — see
# tests/unit/closeout-watchdog-stuck-classes.test.sh for the same pattern):
# the two headline behavioral assertions (CLI-failure-still-resolves, and
# HELP-only-config-resolves) are run TWICE — once against the current, fixed
# shared-utils/operator-chat-id.sh (must PASS), and once against a frozen,
# verbatim snapshot of the pre-fix resolver (tests/fixtures/
# operator-chat-id-resolver/pre-fix-operator-chat-id.sh, must FAIL / resolve
# empty). This proves the new assertions are not vacuously true — they would
# have caught the live incident.
#
# Exit 0 = all checks pass. Exit 1 = a regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER="$REPO_ROOT/shared-utils/operator-chat-id.sh"
PRE_FIX="$REPO_ROOT/tests/fixtures/operator-chat-id-resolver/pre-fix-operator-chat-id.sh"
FAKE_OC="$REPO_ROOT/tests/fixtures/operator-chat-id-resolver/fake-openclaw-chatid.py"
WATCHDOG="$REPO_ROOT/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
RUN_CLOSEOUT="$REPO_ROOT/37-zhc-closeout/scripts/run-closeout.sh"

PASS=0; FAIL=0
pass() { printf "  PASS: %s\n" "$1"; PASS=$((PASS+1)); }
fail() { printf "  FAIL: %s\n" "$1"; FAIL=$((FAIL+1)); }

echo "=== operator-chat-id-resolver.test.sh ==="
echo ""

for _need in "$RESOLVER" "$PRE_FIX" "$FAKE_OC" "$WATCHDOG" "$RUN_CLOSEOUT"; do
  [[ -f "$_need" ]] || { echo "FAIL: required file missing: $_need"; exit 1; }
done
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 required"; exit 1; }

BASH_BIN="${TEST_BASH_BIN:-bash}"

# ─────────────────────────────────────────────────────────────────────────────
# (0) STATIC — syntax, and the shape of the fix
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (0) static checks ---"

bash -n "$RESOLVER" && pass "0a: operator-chat-id.sh is bash -n clean" \
                     || fail "0a: operator-chat-id.sh has a syntax error"
/bin/bash -n "$RESOLVER" 2>/dev/null && pass "0a2: operator-chat-id.sh is bash-3.2 clean (Mac boxes)" \
                     || fail "0a2: operator-chat-id.sh fails under /bin/bash (bash 3.2 — a real Mac-box shell)"
bash -n "$WATCHDOG" && pass "0b: closeout-readiness-watchdog.sh is bash -n clean" \
                     || fail "0b: closeout-readiness-watchdog.sh has a syntax error"
bash -n "$RUN_CLOSEOUT" && pass "0c: run-closeout.sh is bash -n clean" \
                     || fail "0c: run-closeout.sh has a syntax error"

if grep -q 'OPERATOR_HELP_CHAT_ID' "$RESOLVER" && \
   grep -q 'env.vars.OPERATOR_HELP_CHAT_ID\|"OPERATOR_HELP_CHAT_ID"' "$RESOLVER"; then
  pass "0d: operator-chat-id.sh's chain now includes OPERATOR_HELP_CHAT_ID"
else
  fail "0d: operator-chat-id.sh does not reference OPERATOR_HELP_CHAT_ID"
fi

# Check functional USAGE only (env.vars.KEY / ${KEY...), not the explanatory
# header comment (which necessarily names the key it is frozen BEFORE fixing).
if grep -qE 'env\.vars\.OPERATOR_HELP_CHAT_ID|\$\{?OPERATOR_HELP_CHAT_ID' "$PRE_FIX"; then
  fail "0e: the frozen pre-fix fixture unexpectedly RESOLVES OPERATOR_HELP_CHAT_ID — it no longer represents the historical bug"
else
  pass "0e: the frozen pre-fix fixture genuinely predates the OPERATOR_HELP_CHAT_ID fix (sanity check on the fixture itself)"
fi

if grep -qE '\$\{OPERATOR_ESCALATION_CHAT_ID:-\$\{OPERATOR_TELEGRAM_CHAT_ID:-\}\}' "$WATCHDOG"; then
  fail "0f: closeout-readiness-watchdog.sh still contains the old pure-env-var chain (bypasses config + CLI + OPERATOR_HELP_CHAT_ID)"
else
  pass "0f: closeout-readiness-watchdog.sh no longer contains the old pure-env-var chain"
fi
if grep -q 'shared-utils/operator-chat-id.sh' "$WATCHDOG"; then
  pass "0g: closeout-readiness-watchdog.sh now sources the shared resolver"
else
  fail "0g: closeout-readiness-watchdog.sh does not reference the shared resolver"
fi

if grep -qE '\$\{OPERATOR_ESCALATION_CHAT_ID:-\$\{OPERATOR_TELEGRAM_CHAT_ID:-\}\}' "$RUN_CLOSEOUT"; then
  fail "0h: run-closeout.sh still contains the old pure-env-var chain at one or more sites"
else
  pass "0h: run-closeout.sh no longer contains the old pure-env-var chain anywhere"
fi
if grep -q 'shared-utils/operator-chat-id.sh' "$RUN_CLOSEOUT"; then
  pass "0i: run-closeout.sh now sources the shared resolver"
else
  fail "0i: run-closeout.sh does not reference the shared resolver"
fi

# No hardcoded operator id in the resolver (co-mingling doctrine — must never regress).
if grep -qE "printf '%s' \"5252140759\"|v=\"5252140759\"" "$RESOLVER"; then
  fail "0j: operator-chat-id.sh hardcodes an operator id as a fallback"
else
  pass "0j: operator-chat-id.sh has no hardcoded operator-id fallback"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Sandbox + fake-CLI harness
# ─────────────────────────────────────────────────────────────────────────────
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

# _fakebin MODE — writes a `bin/openclaw` wrapper for the given FAKE_OC_MODE
# into a fresh dir under the sandbox and echoes its path (to be prepended to
# PATH). MODE = gateway_fail | clean_notfound | ok | absent ("absent" = no
# wrapper at all, PATH excludes openclaw entirely).
_fakebin() {
  local mode="$1" d
  d="$(mktemp -d "$SANDBOX/fakebin.XXXXXX")"
  if [[ "$mode" == "absent" ]]; then
    printf '%s' "$d"
    return 0
  fi
  mkdir -p "$d/bin"
  cat > "$d/bin/openclaw" <<EOF
#!/bin/sh
FAKE_OC_MODE="$mode" exec python3 "$FAKE_OC" "\$@"
EOF
  chmod +x "$d/bin/openclaw"
  printf '%s' "$d"
}

# _mkconfig OC_ROOT_DIR JSON — writes JSON as OC_ROOT_DIR/openclaw.json
# (creating the dir), so both the fake CLI's "ok" mode and the resolver's
# on-disk fallback have something real to read.
_mkconfig() {
  local root="$1" json="$2"
  mkdir -p "$root"
  printf '%s' "$json" > "$root/openclaw.json"
}

# _resolve RESOLVER_PATH FAKEBIN_DIR OC_ROOT EXTRA_ENV... — sources
# RESOLVER_PATH in an isolated bash process and prints "VALUE|STDERR_B64", so
# both the resolved OPERATOR_CHAT_ID and any stderr diagnostics can be
# asserted on. Runs under $BASH_BIN (overridable, so the caller can also drive
# this under /bin/bash for the bash-3.2 proof).
_resolve() {
  local resolver="$1" fakebin="$2" ocroot="$3"; shift 3
  local out err rc
  err="$(mktemp "$SANDBOX/stderr.XXXXXX")"
  out="$(env -i PATH="$fakebin/bin:/usr/bin:/bin:/opt/homebrew/bin" \
             HOME="$SANDBOX/emptyhome" OC_ROOT="$ocroot" "$@" \
             "$BASH_BIN" -c "source '$resolver'; printf '%s' \"\$OPERATOR_CHAT_ID\"" \
             2>"$err")"
  rc=$?
  LAST_STDERR="$(cat "$err" 2>/dev/null)"
  rm -f "$err"
  LAST_VALUE="$out"
  return $rc
}

# ─────────────────────────────────────────────────────────────────────────────
# (1) HEADLINE #1 — CLI failing (1006 / dead gateway) still resolves
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (1) CLI failing (simulated 1006 abnormal closure) — destination still resolves ---"

FB1="$(_fakebin gateway_fail)"
OCROOT1="$SANDBOX/box1/.openclaw"
_mkconfig "$OCROOT1" '{"env":{"vars":{"OPERATOR_ESCALATION_CHAT_ID":"440011002200"}}}'

_resolve "$RESOLVER" "$FB1" "$OCROOT1"
if [[ "$LAST_VALUE" == "440011002200" ]]; then
  pass "1a: current resolver returns the configured chat id even though every CLI call fails with a gateway signature"
else
  fail "1a: current resolver did not resolve under a simulated dead gateway (got '$LAST_VALUE')"
fi

_resolve "$PRE_FIX" "$FB1" "$OCROOT1"
if [[ -z "$LAST_VALUE" ]]; then
  pass "1-MUT: the frozen pre-fix resolver resolves EMPTY under the identical fixture — 1a is non-vacuous, this is the live-proven bug"
else
  fail "1-MUT: the pre-fix resolver unexpectedly resolved ('$LAST_VALUE') — the mutation proof is broken, 1a proves nothing"
fi

# Same proof again under real bash 3.2 (a genuine Mac-box shell), since the
# resolver must survive there too.
BASH_BIN=/bin/bash
_resolve "$RESOLVER" "$FB1" "$OCROOT1"
if [[ "$LAST_VALUE" == "440011002200" ]]; then
  pass "1b: same proof holds under real bash 3.2 (/bin/bash), a genuine Mac-box shell"
else
  fail "1b: resolver did not survive a dead gateway under bash 3.2 (got '$LAST_VALUE')"
fi
BASH_BIN=bash

# ─────────────────────────────────────────────────────────────────────────────
# (2) HEADLINE #2 — a config carrying ONLY OPERATOR_HELP_CHAT_ID resolves
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (2) config carrying ONLY OPERATOR_HELP_CHAT_ID resolves ---"

FB2="$(_fakebin absent)"   # no openclaw CLI at all — pure disk-path proof
OCROOT2="$SANDBOX/box2/.openclaw"
_mkconfig "$OCROOT2" '{"env":{"vars":{"OPERATOR_HELP_CHAT_ID":"330099008800"}}}'

_resolve "$RESOLVER" "$FB2" "$OCROOT2"
if [[ "$LAST_VALUE" == "330099008800" ]]; then
  pass "2a: current resolver returns the OPERATOR_HELP_CHAT_ID-only value (no openclaw CLI on PATH at all)"
else
  fail "2a: current resolver did not resolve an OPERATOR_HELP_CHAT_ID-only config (got '$LAST_VALUE')"
fi

_resolve "$PRE_FIX" "$FB2" "$OCROOT2"
if [[ -z "$LAST_VALUE" ]]; then
  pass "2-MUT: the frozen pre-fix resolver resolves EMPTY for the identical HELP-only config — 2a is non-vacuous, this is the live-proven bug"
else
  fail "2-MUT: the pre-fix resolver unexpectedly resolved ('$LAST_VALUE') — the mutation proof is broken, 2a proves nothing"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (3) Regression guard — a genuine opt-out (nothing configured) stays SILENT
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (3) legitimately unconfigured box: empty result, NO loud failure log ---"

FB3="$(_fakebin clean_notfound)"
OCROOT3="$SANDBOX/box3/.openclaw"
_mkconfig "$OCROOT3" '{"env":{"vars":{}}}'

_resolve "$RESOLVER" "$FB3" "$OCROOT3"
if [[ -z "$LAST_VALUE" ]]; then
  pass "3a: an unconfigured box resolves empty (the documented, safe opt-out default)"
else
  fail "3a: an unconfigured box unexpectedly resolved a value ('$LAST_VALUE')"
fi
if [[ "$LAST_STDERR" != *OPERATOR_CHAT_ID_RESOLUTION_FAILED* ]] && [[ ! -f "$OCROOT3/workspace/.operator-alert-resolution.log" ]]; then
  pass "3b: no loud failure log for the legitimate opt-out case — must not spam every non-opted-in client box"
else
  fail "3b: the resolver logged a loud failure for a legitimate, clean opt-out (stderr='$LAST_STDERR')"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (4) Fail-loud — CLI gateway failure AND disk unreadable: unmistakable, not silent
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (4) CLI gateway failure + no readable config: resolves empty but FAILS LOUD ---"

FB4="$(_fakebin gateway_fail)"
OCROOT4="$SANDBOX/box4-does-not-exist/.openclaw"   # deliberately never created

_resolve "$RESOLVER" "$FB4" "$OCROOT4"
if [[ -z "$LAST_VALUE" ]]; then
  pass "4a: still resolves to a safe empty string (never crashes, never invents a destination)"
else
  fail "4a: resolved an unexpected value with no config anywhere ('$LAST_VALUE')"
fi
if [[ "$LAST_STDERR" == *OPERATOR_CHAT_ID_RESOLUTION_FAILED* ]]; then
  pass "4b: the double-failure (gateway down AND config unreadable) is logged UNMISTAKABLY to stderr — never a silent empty string"
else
  fail "4b: no loud failure marker on stderr for a genuine double-failure (stderr='$LAST_STDERR')"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (5) Precedence — config-tier ESCALATION beats TELEGRAM beats HELP
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (5) precedence: OPERATOR_ESCALATION_CHAT_ID wins when all three are set ---"

FB5="$(_fakebin absent)"
OCROOT5="$SANDBOX/box5/.openclaw"
_mkconfig "$OCROOT5" '{"env":{"vars":{"OPERATOR_ESCALATION_CHAT_ID":"111111111","OPERATOR_TELEGRAM_CHAT_ID":"222222222","OPERATOR_HELP_CHAT_ID":"333333333"}}}'

_resolve "$RESOLVER" "$FB5" "$OCROOT5"
if [[ "$LAST_VALUE" == "111111111" ]]; then
  pass "5a: OPERATOR_ESCALATION_CHAT_ID (primary) wins over TELEGRAM and HELP"
else
  fail "5a: wrong precedence winner (got '$LAST_VALUE', want 111111111)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (6) Plain-environment fallback tiers still work with NO config at all
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (6) plain environment variables still resolve with no CLI and no config file ---"

FB6="$(_fakebin absent)"
OCROOT6="$SANDBOX/box6-does-not-exist/.openclaw"

_resolve "$RESOLVER" "$FB6" "$OCROOT6" OPERATOR_ESCALATION_CHAT_ID=999888777
if [[ "$LAST_VALUE" == "999888777" ]]; then
  pass "6a: \$OPERATOR_ESCALATION_CHAT_ID env var resolves with no config file present"
else
  fail "6a: env-var tier did not resolve (got '$LAST_VALUE')"
fi

_resolve "$RESOLVER" "$FB6" "$OCROOT6" OPERATOR_HELP_CHAT_ID=666555444
if [[ "$LAST_VALUE" == "666555444" ]]; then
  pass "6b: \$OPERATOR_HELP_CHAT_ID env var (new chain addition) resolves with no config file present"
else
  fail "6b: \$OPERATOR_HELP_CHAT_ID env-var tier did not resolve (got '$LAST_VALUE')"
fi

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== operator-chat-id-resolver: $PASS passed | $FAIL failed ==="
[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0
