#!/usr/bin/env bash
# test-qc-podcast-n8n-probe.sh — U038 verification.
#
# Tests the n8n host connectivity probe in 58-podcast-production-engine/
# qc-podcast.sh: the install QC gate now probes the configured n8n host for
# reachability (bounded HTTP HEAD) before the skill is marked installed, so a
# down deploy target is caught here, not as a silent publish failure later.
#
# Usage:
#   bash 58-podcast-production-engine/tests/test-qc-podcast-n8n-probe.sh
#
# Pass criteria (all must hold):
#   1. bash -n qc-podcast.sh passes (AC#1).
#   2. AC#2: probe_n8n_host does an HTTP HEAD; a reachable host -> rc 0.
#   3. AC#3: an unreachable host -> probe rc 1, and the full gate FAILs in
#      QC_N8N_PROBE_MODE=fail / WARNs in the default warn mode.
#   4. AC#4: the probe is bounded — a non-routable host returns within the
#      timeout (never hangs).
#   5. resolve_n8n_host: N8N_HOST wins; webhook URL -> host portion; default.
#
# MUTATION PROOF (verified during development): inverting the probe's success
# test (`if curl ... ; then return 0` -> `return 1`) makes the reachable-host
# test FAIL (RED); reverting restores GREEN. The test genuinely guards the probe.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/58-podcast-production-engine/qc-podcast.sh"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

# ─── GUARD 1: bash -n (AC#1) ─────────────────────────────────────────────────
bash -n "$SCRIPT" || fail "bash -n qc-podcast.sh failed (AC#1)"
pass "bash -n qc-podcast.sh passes (AC#1)"

# ─── Extract the probe + resolver functions under test ───────────────────────
TMP_LIB="$(mktemp)"
TMP_HOME="$(mktemp -d)"
SERVER_LOG="$(mktemp)"
cleanup() {
  [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null || true
  rm -f "$TMP_LIB" "$SERVER_LOG"
  rm -rf "$TMP_HOME"
}
trap cleanup EXIT

PROBE_SRC="$(sed -n '/^probe_n8n_host() {/,/^}/p' "$SCRIPT")"
RESOLVE_SRC="$(sed -n '/^resolve_n8n_host() {/,/^}/p' "$SCRIPT")"
[ -n "$PROBE_SRC" ] || fail "could not extract probe_n8n_host"
[ -n "$RESOLVE_SRC" ] || fail "could not extract resolve_n8n_host"
printf '%s\n%s\n' "$PROBE_SRC" "$RESOLVE_SRC" > "$TMP_LIB"
# shellcheck source=/dev/null
source "$TMP_LIB"

# ─── AC#2: a reachable host -> probe rc 0 (HTTP HEAD) ────────────────────────
# Start a throwaway local HTTP server to be a reachable target.
PORT=$(( (RANDOM % 20000) + 30000 ))
python3 -m http.server "$PORT" --bind 127.0.0.1 >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
# Wait for it to come up (bounded).
for _ in $(seq 1 50); do
  if curl -sS -o /dev/null -I -m 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then break; fi
  sleep 0.1
done
rc=0
probe_n8n_host "http://127.0.0.1:$PORT/" 5 || rc=$?
[ "$rc" -eq 0 ] || fail "AC#2: a reachable host must probe rc 0, got rc=$rc"
pass "AC#2: reachable host -> probe rc 0 (HTTP HEAD)"

# ─── AC#3: an unreachable host -> probe rc 1 ─────────────────────────────────
# 127.0.0.1:1 -> connection refused (fast, deterministic).
rc=0
probe_n8n_host "http://127.0.0.1:1/" 5 || rc=$?
[ "$rc" -eq 1 ] || fail "AC#3: an unreachable host must probe rc 1, got rc=$rc"
pass "AC#3: unreachable host -> probe rc 1"

# ─── AC#4: the probe is bounded (returns within the timeout, never hangs) ────
# 192.0.2.1 (TEST-NET-1) is non-routable -> the probe must hit the timeout and
# return, not hang. With a 2s timeout it must return within ~4s.
start=$(date +%s)
rc=0
probe_n8n_host "http://192.0.2.1/" 2 || rc=$?
elapsed=$(( $(date +%s) - start ))
[ "$rc" -eq 1 ] || fail "AC#4: non-routable host must probe rc 1, got rc=$rc"
[ "$elapsed" -le 5 ] || fail "AC#4: probe must be bounded (returned in ${elapsed}s, expected <=5s)"
pass "AC#4: probe is bounded (non-routable host returned rc 1 in ${elapsed}s)"

# ─── resolve_n8n_host: N8N_HOST wins ─────────────────────────────────────────
out="$(N8N_HOST="https://custom.example.com" resolve_n8n_host)"
[ "$out" = "https://custom.example.com" ] || fail "resolve_n8n_host: N8N_HOST must win, got: $out"
pass "resolve_n8n_host: N8N_HOST wins"

# ─── resolve_n8n_host: webhook URL -> host portion ───────────────────────────
out="$(unset N8N_HOST; PODBEAN_PUBLISH_WEBHOOK_URL="https://main.blackceoautomations.com/webhook/podbean-publish" resolve_n8n_host)"
[ "$out" = "https://main.blackceoautomations.com" ] || fail "resolve_n8n_host: webhook URL must reduce to host, got: $out"
pass "resolve_n8n_host: webhook URL -> host portion"

# ─── resolve_n8n_host: default ───────────────────────────────────────────────
out="$(unset N8N_HOST PODBEAN_PUBLISH_WEBHOOK_URL PODBEAN_BROKER_WEBHOOK_URL; resolve_n8n_host)"
[ "$out" = "https://main.blackceoautomations.com" ] || fail "resolve_n8n_host: default must be the fleet host, got: $out"
pass "resolve_n8n_host: default is the fleet host"

# ─── AC#3 (full gate): unreachable host + fail mode -> gate FAILs (exit 1) ───
# Set up a fake installed skill + creds so the n8n probe is the deciding factor.
mkdir -p "$TMP_HOME/.openclaw/skills/58-podcast-production-engine"
rc=0
out="$(HOME="$TMP_HOME" PODBEAN_PODCAST_ID=12345 PODBEAN_PUBLISH_TOKEN=dummy \
  N8N_HOST="http://127.0.0.1:1" QC_N8N_PROBE_MODE=fail QC_N8N_PROBE_TIMEOUT=3 \
  bash "$SCRIPT" 2>&1)" || rc=$?
[ "$rc" -eq 1 ] || fail "AC#3: unreachable host + fail mode must exit 1, got rc=$rc: $out"
echo "$out" | grep -qi "UNREACHABLE" || fail "AC#3: fail-mode output must say UNREACHABLE, got: $out"
pass "AC#3 (full gate): unreachable host + fail mode -> gate FAILs (exit 1)"

# ─── AC#3 (full gate): unreachable host + warn mode -> WARN, gate passes ─────
rc=0
out="$(HOME="$TMP_HOME" PODBEAN_PODCAST_ID=12345 PODBEAN_PUBLISH_TOKEN=dummy \
  N8N_HOST="http://127.0.0.1:1" QC_N8N_PROBE_MODE=warn QC_N8N_PROBE_TIMEOUT=3 \
  bash "$SCRIPT" 2>&1)" || rc=$?
[ "$rc" -eq 0 ] || fail "AC#3: unreachable host + warn mode must exit 0 (warn only), got rc=$rc: $out"
echo "$out" | grep -qi "WARN" || fail "AC#3: warn-mode output must say WARN, got: $out"
echo "$out" | grep -qi "UNREACHABLE" || fail "AC#3: warn-mode output must say UNREACHABLE, got: $out"
pass "AC#3 (full gate): unreachable host + warn mode -> WARN, gate passes (exit 0)"

echo ""
echo "All U038 tests passed."
