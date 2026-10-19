#!/usr/bin/env bash
# tests/unit/ghl-mcp-probe.test.sh — W07 retirement contract (was: 28 liveness cases)
#
# scripts/ghl-mcp-probe.sh used to probe, self-heal, alert and escalate (healthy /
# deaf / no-listener / profile-drift verdicts, streak escalation, cards, --heal,
# off-switch). The GHL Community MCP (Tier 2, skill 36) is RETIRED, so the probe
# is now an INERT TOMBSTONE: it refuses every invocation with exit 69
# (EX_UNAVAILABLE — outside its historical 0/2/3/4/5 verdict vocabulary) and
# changes no state on the box.
#
# This suite asserts the RETIREMENT contract INSTEAD of the deleted behaviour:
#   (F1..F9)  every invocation form the old suite used exits 69 and prints a
#             refusal naming the retirement (bare call, --once, --once --heal,
#             the old health/dead-port/heal/escalation shapes, both off-switch
#             shapes, and the /bin/bash scheduler shape)
#   (M)       the GHL_MCP_RETIRED marker is present in the probe file
#   (C)       control: all four supervisor stubs on PATH are reachable and
#             record their invocation — a "never invoked" claim is worthless
#             unless the instrument is proven to discriminate first
#   (S1..S6)  launchctl / pm2 / systemctl / crontab / the old heal cmd / the old
#             card-route cmd are NEVER invoked by any form above
#   (L)       no probe log dir or file is created (the tombstone writes nothing)
#   (P)       the production probe.log is untouched
#
# Hermetic: supervisor stubs live in a throwaway sandbox under
# ${GHL_RETIRE_TEST_ROOT:-~/Downloads/GHL updates/tmp}; no real
# launchctl/pm2/systemctl/crontab on this machine is ever executed.
# Exit 0 = all cases pass.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/ghl-mcp-probe.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-probe.test.sh (retirement contract) ==="
echo ""

if [ ! -f "$PROBE" ]; then
  echo "  FAIL: probe not found at $PROBE"; exit 1
fi

# ── sandbox ──────────────────────────────────────────────────────────────────
BASE="${GHL_RETIRE_TEST_ROOT:-${TMPDIR:-/tmp}/ghl-retire-test}"
mkdir -p "$BASE" || exit 1
WORK="$(mktemp -d "$BASE/ghl-probe-retire.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# The off-switch MARKER FILE the old suite exercised (case 22). It must have
# no effect any more: a tombstone has no success path to switch off.
DIS_HOME="$WORK/disabled-home"
mkdir -p "$DIS_HOME/.openclaw"
: > "$DIS_HOME/.openclaw/.ghl-mcp-probe-disabled"

# Old heal cmd + card-route cmd, each recording its own invocations.
export HEAL_STUB_LOG="$WORK/heal-invocations.log"
export ROUTE_STUB_LOG="$WORK/route-invocations.log"
cat > "$WORK/heal-stub.sh" <<'STUB'
#!/usr/bin/env bash
printf 'heal %s\n' "$*" >> "${HEAL_STUB_LOG:?}"
STUB
cat > "$WORK/route-stub.sh" <<'STUB'
#!/usr/bin/env bash
printf 'route %s\n' "$*" >> "${ROUTE_STUB_LOG:?}"
STUB
chmod +x "$WORK/heal-stub.sh" "$WORK/route-stub.sh"

# ── supervisor stubs: record every invocation, never run the real thing ───────
STUB_BIN="$WORK/bin"
mkdir -p "$STUB_BIN"
export PROBE_STUB_LOG="$WORK/stub-invocations.log"
for _t in launchctl pm2 systemctl crontab; do
  cat > "$STUB_BIN/$_t" <<'STUB'
#!/bin/sh
printf '%s %s\n' "$(basename "$0")" "$*" >> "${PROBE_STUB_LOG:?}"
exit 0
STUB
  chmod +x "$STUB_BIN/$_t"
done
unset _t

# ── (C) KNOWN-GOOD CONTROL: prove the instrument discriminates ────────────────
# If these stubs are not reachable, every "never invoked" assertion below is a
# hollow zero. Exercise all four through the same PATH the probe will get.
for _t in launchctl pm2 systemctl crontab; do
  PATH="$STUB_BIN:$PATH" "$_t" --selftest-probe-guard >/dev/null 2>&1 || true
done
unset _t
CTL_N="$(wc -l < "$PROBE_STUB_LOG" 2>/dev/null | tr -d ' ')"
[ -n "$CTL_N" ] || CTL_N=0
if [ "$CTL_N" = "4" ]; then
  pass "(C) control: all four supervisor stubs reachable on PATH and recording (4/4)"
else
  fail "(C) control FAILED — stub log has $CTL_N line(s), expected 4; the never-invoked assertions below would prove nothing"
fi
: > "$PROBE_STUB_LOG"

DEAD_URL="http://127.0.0.1:9"          # nothing listens there; the tombstone never asks
BASH_SCHEDULER=/bin/bash                # the launchd plist / VPS cron interpreter
[ -x /bin/bash ] || BASH_SCHEDULER=bash

# assert_69 <label> <rc> <captured-output-file>
# The two load-bearing facts per form: exit 69, and a refusal that NAMES the
# retirement (REFUSED + RETIRED + the --retire entry point of record).
assert_69() {
  local label="$1" rc="$2" f="$3"
  if [ "$rc" = "69" ]; then
    pass "$label -> exit 69"
  else
    fail "$label — expected exit 69, got $rc"
  fi
  if grep -q 'REFUSED' "$f" 2>/dev/null \
     && grep -q 'RETIRED' "$f" 2>/dev/null \
     && grep -qF 'ghl-mcp-autostart.sh --retire' "$f" 2>/dev/null; then
    pass "$label -> refusal names the retirement (REFUSED + RETIRED + --retire)"
  else
    fail "$label -> output does not name the retirement (got: $(tr '\n' ' ' < "$f" | cut -c1-160))"
  fi
}

# Every form runs under the stub PATH with an isolated GHL_MCP_LOG_DIR, so a
# regression that re-arms logging is caught by (L) instead of poisoning the box.
LOGDIR="$WORK/probe-log"

# (F1) bare call — no arguments at all
OUT="$WORK/o.f1"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" bash "$PROBE" >"$OUT" 2>&1
assert_69 "(F1) bare call" "$?" "$OUT"

# (F2) --once (the periodic scheduler's own flag)
OUT="$WORK/o.f2"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" bash "$PROBE" --once >"$OUT" 2>&1
assert_69 "(F2) --once" "$?" "$OUT"

# (F3) --once --heal (the old self-heal shape)
OUT="$WORK/o.f3"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" bash "$PROBE" --once --heal >"$OUT" 2>&1
assert_69 "(F3) --once --heal" "$?" "$OUT"

# (F4) old health-check shape (old cases 1-5): quiet + timeout + url + tool band
OUT="$WORK/o.f4"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" GHL_MCP_EXPECT_MIN_TOOLS=1 GHL_MCP_EXPECT_MAX_TOOLS=200 \
  bash "$PROBE" --once --quiet --timeout 3 --url "$DEAD_URL" >"$OUT" 2>&1
assert_69 "(F4) old health shape (--once --quiet --timeout --url + tool band)" "$?" "$OUT"

# (F5) old dead-port escalation shape (old cases 9-13, 18b-e): webhook + slug +
# card-route stub. No escalation, no card, no log line may come out of it.
OUT="$WORK/o.f5"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" GHL_MCP_PROBE_ROUTE_CMD="$WORK/route-stub.sh" \
  RESCUE_RANGERS_WEBHOOK_URL="$DEAD_URL" FLEET_STANDING_BOX_SLUG="unit-test-box" \
  bash "$PROBE" --once --quiet --timeout 2 --url "$DEAD_URL" >"$OUT" 2>&1
assert_69 "(F5) old escalation shape (+ webhook, slug, card-route stub)" "$?" "$OUT"

# (F6) old self-heal shape (old cases 19-20): --heal + heal cmd stub
OUT="$WORK/o.f6"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" GHL_MCP_PROBE_HEAL_CMD="$WORK/heal-stub.sh" \
  GHL_MCP_PROBE_HEAL_WAIT_SECONDS=1 \
  bash "$PROBE" --once --quiet --heal --timeout 2 --url "$DEAD_URL" >"$OUT" 2>&1
assert_69 "(F6) old --heal shape (+ heal-cmd stub)" "$?" "$OUT"

# (F7) old env off-switch (old case 21): GHL_MCP_PROBE_DISABLED=1 used to yield
# exit 0 + a DISABLED verdict. There is no success path left to switch off.
OUT="$WORK/o.f7"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" GHL_MCP_PROBE_DISABLED=1 \
  bash "$PROBE" --once --quiet --timeout 2 --url "$DEAD_URL" >"$OUT" 2>&1
assert_69 "(F7) old off-switch env GHL_MCP_PROBE_DISABLED=1 (was exit 0)" "$?" "$OUT"

# (F8) old marker-file off-switch (old case 22): $HOME/.openclaw/.ghl-mcp-probe-disabled
OUT="$WORK/o.f8"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED PATH="$STUB_BIN:$PATH" \
  GHL_MCP_LOG_DIR="$LOGDIR" HOME="$DIS_HOME" GHL_MCP_PROBE_DISABLED= \
  bash "$PROBE" --once --quiet --timeout 2 --url "$DEAD_URL" >"$OUT" 2>&1
assert_69 "(F8) old off-switch marker file in \$HOME (was exit 0)" "$?" "$OUT"

# (F9) scheduler shape (old case 14): invoked as /bin/bash by the launchd plist
# and the VPS cron line, with the empty-header env that broke bash 3.2.
OUT="$WORK/o.f9"
env -u GHL_MCP_TOMBSTONE_EXIT -u GHL_MCP_RETIRED -u RESCUE_RANGERS_WEBHOOK_SECRET \
  PATH="$STUB_BIN:$PATH" GHL_MCP_LOG_DIR="$LOGDIR" \
  FLEET_STANDING_BOX_SLUG="unit-test-box-32" RESCUE_RANGERS_WEBHOOK_URL="$DEAD_URL" \
  "$BASH_SCHEDULER" "$PROBE" --once --quiet --timeout 2 --url "$DEAD_URL" >"$OUT" 2>&1
assert_69 "(F9) scheduler shape under $BASH_SCHEDULER (no webhook secret set)" "$?" "$OUT"

# ── (M) the gate's contract marker is in the file ─────────────────────────────
# scripts/qc-assert-ghl-mcp-supervised.sh reads GHL_MCP_RETIRED as THE contract;
# without it the supervised gate has nothing to assert.
if grep -q 'GHL_MCP_RETIRED' "$PROBE"; then
  pass "(M) GHL_MCP_RETIRED marker present in $PROBE"
else
  fail "(M) GHL_MCP_RETIRED marker missing from the probe file — the retirement contract is unverifiable"
fi

# ── (S1..S6) NO STATE CHANGES across all nine forms ──────────────────────────
stub_count() {  # stub_count <tool>
  if [ -f "$PROBE_STUB_LOG" ]; then grep -c "^$1 " "$PROBE_STUB_LOG" 2>/dev/null || echo 0; else echo 0; fi
}
for pair in "S1 launchctl" "S2 pm2" "S3 systemctl" "S4 crontab"; do
  set -- $pair
  _n="$(stub_count "$2")"
  case "$_n" in ''|*[!0-9]*) _n=0 ;; esac
  if [ "$_n" = "0" ]; then
    pass "($1) $2 was never invoked by any invocation form"
  else
    fail "($1) $2 was invoked $_n time(s) by the tombstone — it can change state again"
  fi
done
unset pair _n

if [ -f "$HEAL_STUB_LOG" ]; then
  fail "(S5) the old heal cmd was invoked ($(wc -l < "$HEAL_STUB_LOG" | tr -d ' ') time(s)) — self-heal is back"
else
  pass "(S5) the old heal cmd was never invoked (--heal changes no state)"
fi
if [ -f "$ROUTE_STUB_LOG" ]; then
  fail "(S6) the old card-route cmd was invoked ($(wc -l < "$ROUTE_STUB_LOG" | tr -d ' ') time(s)) — alerting is back"
else
  pass "(S6) the old card-route cmd was never invoked (no alert, no escalation)"
fi

# ── (L) the tombstone opens no log ───────────────────────────────────────────
if [ ! -e "$LOGDIR" ]; then
  pass "(L) no log dir/file created under GHL_MCP_LOG_DIR ($LOGDIR)"
else
  fail "(L) the tombstone created $LOGDIR — it is writing state again"
fi

# ── (P) the production probe.log is untouched (kept from old case 7) ─────────
PROD_LOG_DIR="${HOME}/Library/Logs/ghl-mcp"
[ -d /data/logs ] && PROD_LOG_DIR="/data/logs"
PROD_LOG="$PROD_LOG_DIR/probe.log"
PROD_LOG_AFTER="absent"
[ -f "$PROD_LOG" ] && PROD_LOG_AFTER="$(wc -c < "$PROD_LOG" 2>/dev/null | tr -d ' ')"
# Baseline was taken by the absence of any write path: every form above ran with
# an isolated GHL_MCP_LOG_DIR, and the tombstone must not have touched the
# default location either. Re-read twice around a final bare invocation:
OUT="$WORK/o.p"
env -u GHL_MCP_TOMBSTONE_EXIT PATH="$STUB_BIN:$PATH" GHL_MCP_LOG_DIR="$LOGDIR" \
  bash "$PROBE" --once >"$OUT" 2>&1
PROD_LOG_FINAL="absent"
[ -f "$PROD_LOG" ] && PROD_LOG_FINAL="$(wc -c < "$PROD_LOG" 2>/dev/null | tr -d ' ')"
if [ ! -e "$LOGDIR" ] && [ "$PROD_LOG_AFTER" = "$PROD_LOG_FINAL" ]; then
  pass "(P) production probe.log untouched and isolated log still absent (was: $PROD_LOG_AFTER, now: $PROD_LOG_FINAL)"
else
  fail "(P) state was written — prod probe.log $PROD_LOG_AFTER -> $PROD_LOG_FINAL, isolated log exists: $([ -e "$LOGDIR" ] && echo yes || echo no)"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1