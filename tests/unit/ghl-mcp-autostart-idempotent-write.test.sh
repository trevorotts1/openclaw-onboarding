#!/usr/bin/env bash
# tests/unit/ghl-mcp-autostart-idempotent-write.test.sh
#
# CI guard: verifies the idempotency guard inside deregister_tier2() in
# scripts/ghl-mcp-autostart.sh only calls
#   `openclaw config set env.vars.GHL_COMMUNITY_MCP_URL ...`
# when the stored value actually differs from the desired value. A prior
# unconditional `config set` on every run was measured to rewrite 10-103
# unrelated config paths per box; when that rewrite landed on plugins.allow
# the gateway treated it as a config change requiring a restart and issued
# SIGUSR1 -> a full process restart that killed every in-flight agent run
# mid-task. The fix must repair genuine drift (never silently stop doing its
# job) while eliminating the no-op churn writes that were restarting gateways.
#
# Assertion groups:
#   (1) NO_WRITE_WHEN_MATCHED  -- config already holds the desired URL -> NO
#                                  `openclaw config set` call (the churn fix)
#   (2) WRITE_WHEN_DRIFTED     -- config holds a DIFFERENT URL -> a write DOES
#                                  occur, carrying the current desired URL
#                                  (genuine drift is still repaired)
#   (3) WRITE_WHEN_UNREADABLE  -- config file missing (and the /data fallback
#                                  is also absent) -> a write DOES occur
#                                  (fail-open by construction)
#   (3b) WRITE_WHEN_MALFORMED  -- config file exists but is not valid JSON ->
#                                  a write DOES occur (fail-open on parse
#                                  errors too) [bonus, strengthens (3)]
#
# The guard body is extracted LIVE out of the shipped script (everything
# between `deregister_tier2() {` and the unrelated `if openclaw mcp list`
# block that follows it) rather than pasted as a frozen copy, so this test
# tracks the real source. It is sourced into a stub-`openclaw` sandbox and
# never executes the real script or a real `openclaw` binary.
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-autostart-idempotent-write.test.sh ==="
echo ""

if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
  fail "0: scripts/ghl-mcp-autostart.sh not found at $SCRIPT_UNDER_TEST"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# PRESENCE CHECK (GHL002): deregister_tier2() was deleted with the community
# MCP retirement, so its guard body can no longer be extracted. The legacy lock
# below is NOT deleted -- it stays reachable behind LEGACY_PRESENT, so restoring
# the function re-arms the original churn assertions instead of bypassing them.
# While the function is gone, what is locked is the contract that replaced it:
#   (1) no live line anywhere in the tree writes
#       `openclaw config set env.vars.GHL_COMMUNITY_MCP_URL` (the churn write
#       that SIGUSR1'd gateways, comment-stripped so prose cannot hide it),
#   (2) the GHL002 record naming the deleted function and the deleted write
#       stays on file (deletion is documented, never silent) -- this doubles as
#       the control that proves assertion (1) is not matching nothing,
#   (3) the script refuses to start (START_REFUSED_RETIRED), so no path can
#       reach a config write behind a service that no longer exists.
# ---------------------------------------------------------------------------
LEGACY_PRESENT=0
if grep -qF 'deregister_tier2() {' "$SCRIPT_UNDER_TEST"; then
  LEGACY_PRESENT=1
fi

if [[ "$LEGACY_PRESENT" -eq 0 ]]; then
  echo "--- RETIRED: deregister_tier2() does not ship; locking the retirement contract instead ---"
  echo ""

  _code_of() { awk '{ sub(/#.*/, ""); print }' "$1"; }   # live code only
  C_AUTO="$TMP/code-autostart.txt"
  C_INSTALL="$TMP/code-install.txt"
  C_UPDATE="$TMP/code-update.txt"
  _code_of "$SCRIPT_UNDER_TEST" > "$C_AUTO"
  _code_of "$REPO_ROOT/install.sh" > "$C_INSTALL"
  _code_of "$REPO_ROOT/update-skills.sh" > "$C_UPDATE"

  URL_WRITE_RE='openclaw[[:space:]]+config[[:space:]]+set[^|;&]*GHL_COMMUNITY_MCP_URL'

  # (1) the churn write itself must not exist as live code anywhere.
  if grep -qE "$URL_WRITE_RE" "$C_AUTO"; then
    fail "1: scripts/ghl-mcp-autostart.sh still carries a LIVE 'openclaw config set ... GHL_COMMUNITY_MCP_URL' write (comment-stripped) — the churn write this test locked is back"
  else
    pass "1: no live 'openclaw config set ... GHL_COMMUNITY_MCP_URL' write in scripts/ghl-mcp-autostart.sh (the churn write stayed retired)"
  fi
  if grep -qE "$URL_WRITE_RE" "$C_INSTALL"; then
    fail "2: install.sh still carries a LIVE 'openclaw config set ... GHL_COMMUNITY_MCP_URL' write (comment-stripped) — a fresh install would mutate the URL var again"
  else
    pass "2: no live 'openclaw config set ... GHL_COMMUNITY_MCP_URL' write in install.sh"
  fi
  if grep -qE "$URL_WRITE_RE" "$C_UPDATE"; then
    fail "3: update-skills.sh still carries a LIVE 'openclaw config set ... GHL_COMMUNITY_MCP_URL' write (comment-stripped) — a roll would mutate the URL var again"
  else
    pass "3: no live 'openclaw config set ... GHL_COMMUNITY_MCP_URL' write in update-skills.sh"
  fi

  # (2) the deletion record + control: the exact write text is still present in
  #     raw form (inside the GHL002 note), which is what makes (1) a real test —
  #     if the pattern itself could not match, (1) would pass vacuously.
  if grep -qF 'deregister_tier2() is GONE (GHL002)' "$SCRIPT_UNDER_TEST" \
     && grep -qF 'openclaw config set env.vars.GHL_COMMUNITY_MCP_URL' "$SCRIPT_UNDER_TEST"; then
    pass "4: GHL002 record still names deregister_tier2() and the exact write that was removed (control: the pattern in (1)-(3) is one that matches)"
  else
    fail "4: the GHL002 retirement record (deregister_tier2() + the config-set write) is missing from scripts/ghl-mcp-autostart.sh — the deletion is no longer on file"
  fi

  # (3) the script refuses to start, so nothing can reach a config write.
  if grep -qF 'report "START_REFUSED_RETIRED"' "$C_AUTO"; then
    pass "5: scripts/ghl-mcp-autostart.sh refuses to start (live START_REFUSED_RETIRED) — no live path reaches a config write behind the retired service"
  else
    fail "5: scripts/ghl-mcp-autostart.sh no longer reports START_REFUSED_RETIRED on a live line — the retirement refusal is gone"
  fi

  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  if [[ "$FAIL" -gt 0 ]]; then
    echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
    exit 1
  fi
  echo "PASS: community-MCP retirement contract holds (deregister_tier2() absent, no live URL-var write, start refused)"
  exit 0
fi

# ---------------------------------------------------------------------------
# Extract the write-guard body of deregister_tier2() out of the live script.
# Bounded by the function open and the (unrelated) `if openclaw mcp list`
# de-registration block that follows it -- NOT anchored to the guard's own
# comment text, so a revert to the old unconditional write still extracts
# something and this test fails assertion (1) for the right reason, instead
# of silently no-oping on an empty extraction.
# ---------------------------------------------------------------------------
GUARD_BODY="$TMP/guard-body.sh"
awk '
  /deregister_tier2\(\) \{/ { flag=1; next }
  /if openclaw mcp list/ { exit }
  flag { print }
' "$SCRIPT_UNDER_TEST" > "$GUARD_BODY"

if [[ ! -s "$GUARD_BODY" ]]; then
  fail "0: could not extract deregister_tier2() guard body from $SCRIPT_UNDER_TEST (anchors not found)"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi

GUARD_FN="$TMP/guard-fn.sh"
{
  # gw_up is the D03 gateway-up gate; this test is about the write guard, so
  # the gateway is "up" here. tests/unit/ghl-mcp-gateway-guard.test.sh owns gw_up.
  echo 'gw_up() { return 0; }'
  echo 'guard_under_test() {'
  cat "$GUARD_BODY"
  echo '}'
} > "$GUARD_FN"

# ---------------------------------------------------------------------------
# Stub `openclaw` on PATH. Records every invocation (args, space-joined) as
# one line in $OC_STUB_CALL_LOG. The real `openclaw` binary is never invoked.
# ---------------------------------------------------------------------------
mkdir -p "$TMP/bin"
cat > "$TMP/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
echo "$@" >> "$OC_STUB_CALL_LOG"
exit 0
STUB
chmod +x "$TMP/bin/openclaw"
export PATH="$TMP/bin:$PATH"
export GHL_MCP_PORT="18080"

# run_guard_case CFG_PATH
#   Sources the extracted guard into a subshell with OPENCLAW_CONFIG=CFG_PATH,
#   calls it once, and prints the path to that run's call-log file.
run_guard_case() {
  local cfg="$1"
  local call_log
  call_log="$(mktemp "$TMP/calls.XXXXXX")"
  : > "$call_log"
  (
    export OC_STUB_CALL_LOG="$call_log"
    export OPENCLAW_CONFIG="$cfg"
    # shellcheck disable=SC1090
    source "$GUARD_FN"
    guard_under_test
  )
  printf '%s' "$call_log"
}

# ---------------------------------------------------------------------------
# (1) NO_WRITE_WHEN_MATCHED
# ---------------------------------------------------------------------------
echo "--- (1) NO_WRITE_WHEN_MATCHED: config already holds the desired URL ---"

CFG_MATCH="$TMP/cfg-match.json"
printf '{"env":{"vars":{"GHL_COMMUNITY_MCP_URL":"http://localhost:18080"}}}' > "$CFG_MATCH"

log1="$(run_guard_case "$CFG_MATCH")"
calls1="$(grep -c '^config set ' "$log1" || true)"
if [[ "${calls1:-0}" -eq 0 ]]; then
  pass "1: config already matches desired URL -> no 'config set' call (churn fix holds)"
else
  fail "1: config already matches desired URL but 'config set' was invoked ${calls1} time(s) -- churn regression"
fi

# ---------------------------------------------------------------------------
# (2) WRITE_WHEN_DRIFTED
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) WRITE_WHEN_DRIFTED: config holds a different URL -> a write DOES occur ---"

CFG_DRIFT="$TMP/cfg-drift.json"
printf '{"env":{"vars":{"GHL_COMMUNITY_MCP_URL":"http://localhost:9999"}}}' > "$CFG_DRIFT"

log2="$(run_guard_case "$CFG_DRIFT")"
calls2="$(grep -c '^config set ' "$log2" || true)"
if [[ "${calls2:-0}" -ge 1 ]]; then
  pass "2a: config holds a stale URL (port 9999) -> 'config set' WAS invoked ${calls2} time(s) (drift still repaired)"
else
  fail "2a: config holds a stale URL (port 9999) but 'config set' was NOT invoked -- genuine drift would go unrepaired"
fi
if grep -q 'http://localhost:18080' "$log2" 2>/dev/null; then
  pass "2b: the write carries the currently desired URL (http://localhost:18080), not the stale one"
else
  fail "2b: the write did not carry the expected desired URL"
fi

# ---------------------------------------------------------------------------
# (3) WRITE_WHEN_UNREADABLE (missing file, /data fallback also absent)
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) WRITE_WHEN_UNREADABLE: config file missing -> a write DOES occur (fail-open) ---"

if [[ -e /data/.openclaw/openclaw.json ]]; then
  # SKIP, not FAIL. On a container layout /data/.openclaw/openclaw.json is the
  # REAL config, so exercising the missing-file fallback here would read it.
  # A test must fail for a defect in the code, never for a property of the host
  # it happens to run on -- an environment-dependent FAIL trains people to
  # ignore red. Cases (2) and (3b) already prove the fail-open write path.
  echo "  SKIP: 3: /data/.openclaw/openclaw.json exists on this host (container layout) --"
  echo "        missing-file fallback not exercised here; fail-open is still covered by (3b)."
else
  CFG_MISSING="$TMP/no-such-dir/openclaw.json"
  log3="$(run_guard_case "$CFG_MISSING")"
  calls3="$(grep -c '^config set ' "$log3" || true)"
  if [[ "${calls3:-0}" -ge 1 ]]; then
    pass "3: config file missing (and /data fallback absent) -> 'config set' WAS invoked ${calls3} time(s) (fail-open holds)"
  else
    fail "3: config file missing but 'config set' was NOT invoked -- fail-open broken, drift would go unrepaired"
  fi
fi

# ---------------------------------------------------------------------------
# (3b) WRITE_WHEN_MALFORMED -- bonus: config exists but fails to parse
# ---------------------------------------------------------------------------
echo ""
echo "--- (3b) WRITE_WHEN_MALFORMED: config exists but is not valid JSON -> a write DOES occur [bonus] ---"

CFG_MALFORMED="$TMP/cfg-malformed.json"
printf '{ this is not valid json' > "$CFG_MALFORMED"

log3b="$(run_guard_case "$CFG_MALFORMED")"
calls3b="$(grep -c '^config set ' "$log3b" || true)"
if [[ "${calls3b:-0}" -ge 1 ]]; then
  pass "3b: config file is malformed JSON -> 'config set' WAS invoked ${calls3b} time(s) (fail-open holds on parse errors too)"
else
  fail "3b: config file is malformed JSON but 'config set' was NOT invoked -- fail-open broken on parse errors"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all ghl-mcp-autostart idempotent-write checks pass"
exit 0
