#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE :: test_install_podcast_department.sh
# -----------------------------------------------------------------------------
# Behavioral test suite for scripts/install-podcast-department.sh (act-3, the
# dept-podcast materializer). Covers: dry-run (no mutation), install,
# idempotency (re-run adds zero duplicates), verify-mode pass/fail, input
# validation fail-closed, the interview-incomplete precondition, the
# PODCAST_CLIENT_SLUG env fallback, the --prime-session storage path (fake
# openclaw CLI), and secret hygiene (env values never printed).
#
# Every test runs inside a throwaway HOME containing a fake OpenClaw root --
# the REAL $HOME/.openclaw is never touched. Tests skip cleanly if /data/
# .openclaw exists on the test machine (the shared root resolver prefers it,
# which would point the shared skill-32 materializer at a real tree).
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$SKILL_ROOT/scripts/install-podcast-department.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== test_install_podcast_department.sh ==="
echo ""

[ -f "$SCRIPT" ] || { echo "FATAL: $SCRIPT not found"; exit 1; }
if [ -d /data/.openclaw ]; then
  echo "SKIP: /data/.openclaw exists on this machine; the shared OC-root resolver"
  echo "      would point the skill-32 materializer at a real tree. Run on a box"
  echo "      without it."
  exit 0
fi

# --------------------------------------------------------------------------- #
# Fixture: throwaway HOME with a fake OpenClaw root
# --------------------------------------------------------------------------- #
FIXTURE_ROOT=""
make_fixture() {
  # $1 = interviewComplete (true|false)
  local interview="${1:-true}"
  FIXTURE_ROOT="$(mktemp -d /tmp/install-podcast-dept.XXXXXX)"
  local oc="$FIXTURE_ROOT/.openclaw"
  mkdir -p "$oc/workspace/departments/podcast" "$oc/agents" "$oc/backups"
  python3 - "$oc/openclaw.json" <<'PYEOF'
import json, sys
cfg = {"agents": {"list": []}}
with open(sys.argv[1], "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
  python3 - "$oc/workspace/.workforce-build-state.json" "$interview" <<'PYEOF'
import json, sys
state = {"interviewComplete": sys.argv[2] == "true"}
with open(sys.argv[1], "w") as f:
    json.dump(state, f, indent=2)
PYEOF
}

clean_fixture() {
  [ -n "$FIXTURE_ROOT" ] && rm -rf "$FIXTURE_ROOT"
  FIXTURE_ROOT=""
}

# Run the installer inside the fixture HOME. Extra args pass through.
# INSTALL_ENV holds KEY=VALUE pairs; the __none__ sentinel keeps the array
# non-empty so bash 3.2 (set -u) never trips on an empty array expansion.
INSTALL_ENV=(__none__)
run_installer() {
  local extra=()
  for kv in "${INSTALL_ENV[@]}"; do
    [ "$kv" = "__none__" ] || extra+=("$kv")
  done
  env -i HOME="$FIXTURE_ROOT" PATH="$PATH" \
      PODCAST_INSTALL_OC_ROOT="$FIXTURE_ROOT/.openclaw" \
      ${extra[@]+"${extra[@]}"} \
      bash "$SCRIPT" "$@" 2>&1
}

config_json() { cat "$FIXTURE_ROOT/.openclaw/openclaw.json"; }

count_entries() {
  python3 - "$FIXTURE_ROOT/.openclaw/openclaw.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
lst = cfg.get("agents", {}).get("list", [])
print(sum(1 for a in lst if isinstance(a, dict) and a.get("id") == "dept-podcast"))
PYEOF
}

inject_hooks_prefix() {
  python3 - "$FIXTURE_ROOT/.openclaw/openclaw.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault("hooks", {})["allowedSessionKeyPrefixes"] = ["podcast:"]
with open(p, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
}

trap 'clean_fixture' EXIT

INSTALL_ENV=(__none__)

# --------------------------------------------------------------------------- #
# Test 1: syntax gate
# --------------------------------------------------------------------------- #
echo "-- syntax and conventions"
if bash -n "$SCRIPT" 2>/dev/null; then pass "bash -n clean"; else fail "bash -n"; fi
# Build the em dash from UTF-8 bytes (U+2014) so this suite contains zero
# literal em dashes itself while still detecting them.
EM_DASH="$(printf '\342\200\224')"
if [ "$(grep -c "$EM_DASH" "$SCRIPT" || true)" = "0" ]; then pass "zero em dashes"; else fail "em dash found"; fi

# --------------------------------------------------------------------------- #
# Test 2: usage / help
# --------------------------------------------------------------------------- #
echo "-- usage"
make_fixture true
INSTALL_ENV=(__none__)
OUT="$(run_installer --help)"; RC=$?
if [ $RC -eq 0 ] && printf '%s' "$OUT" | grep -q -- "--client-slug"; then
  pass "--help exits 0 and prints usage"
else
  fail "--help (rc=$RC)"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 3: input validation fail-closed
# --------------------------------------------------------------------------- #
echo "-- input validation"
make_fixture true
INSTALL_ENV=(__none__)
OUT="$(run_installer)"; RC=$?
if [ $RC -ne 0 ]; then pass "missing slug refused (rc=$RC)"; else fail "missing slug accepted"; fi

OUT="$(run_installer --client-slug 'Bad Slug!')"; RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "lowercase"; then
  pass "invalid slug refused with message"
else
  fail "invalid slug (rc=$RC)"
fi

OUT="$(run_installer --client-slug x)"; RC=$?
if [ $RC -ne 0 ]; then pass "1-char slug refused"; else fail "1-char slug accepted"; fi
clean_fixture

# No openclaw.json at all
FIXTURE_ROOT="$(mktemp -d /tmp/install-podcast-dept.XXXXXX)"
mkdir -p "$FIXTURE_ROOT/.openclaw"
INSTALL_ENV=(__none__)
OUT="$(run_installer --client-slug test-client)"; RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "openclaw.json not found"; then
  pass "missing openclaw.json refused"
else
  fail "missing openclaw.json (rc=$RC)"
fi
clean_fixture

# Malformed openclaw.json
FIXTURE_ROOT="$(mktemp -d /tmp/install-podcast-dept.XXXXXX)"
mkdir -p "$FIXTURE_ROOT/.openclaw"
echo "{ not json" > "$FIXTURE_ROOT/.openclaw/openclaw.json"
OUT="$(run_installer --client-slug test-client)"; RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "not valid JSON"; then
  pass "malformed openclaw.json refused"
else
  fail "malformed openclaw.json (rc=$RC)"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 4: dry-run plans but writes nothing
# --------------------------------------------------------------------------- #
echo "-- dry-run"
make_fixture true
BEFORE="$(config_json | python3 -c 'import sys,hashlib; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())')"
INSTALL_ENV=(__none__)
OUT="$(run_installer --client-slug test-client --dry-run)"; RC=$?
AFTER="$(config_json | python3 -c 'import sys,hashlib; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())')"
if [ $RC -eq 0 ] && printf '%s' "$OUT" | grep -q "dry-run"; then
  pass "dry-run exits 0 and says so"
else
  fail "dry-run (rc=$RC)"
fi
if [ "$BEFORE" = "$AFTER" ]; then pass "dry-run left openclaw.json untouched"; else fail "dry-run mutated config"; fi
if [ ! -d "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/agent" ]; then
  pass "dry-run created no storage dirs"
else
  fail "dry-run created storage dirs"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 5: full install materializes the agent
# --------------------------------------------------------------------------- #
echo "-- install"
make_fixture true
INSTALL_ENV=(__none__)
OUT="$(run_installer --client-slug test-client)"; RC=$?
if [ $RC -eq 0 ]; then pass "install exits 0"; else fail "install rc=$RC out=$(printf '%s' "$OUT" | tail -3)"; fi
if [ "$(count_entries)" = "1" ]; then pass "agents.list has exactly one dept-podcast entry"; else fail "entry count=$(count_entries)"; fi
if [ -d "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/agent" ] && \
   [ -d "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/sessions" ]; then
  pass "storage tree agent/ + sessions/ created"
else
  fail "storage tree missing"
fi
if [ -f "$FIXTURE_ROOT/.openclaw/workspace/departments/podcast/IDENTITY.md" ]; then
  pass "per-agent files scaffolded (IDENTITY.md present)"
else
  fail "per-agent files missing"
fi
AGENTDIR_VAL="$(config_json | python3 -c 'import sys,json; [print(a.get("agentDir","")) for a in json.load(sys.stdin)["agents"]["list"] if a.get("id")=="dept-podcast"]')"
if [ "$AGENTDIR_VAL" = "$FIXTURE_ROOT/.openclaw/agents/dept-podcast" ]; then
  pass "agentDir registered and correct"
else
  fail "agentDir=$AGENTDIR_VAL"
fi
# No sqlite yet: registration never creates it (lazy on first dispatch)
if [ ! -f "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/agent/openclaw-agent.sqlite" ]; then
  pass "sqlite NOT created by registration (lazy contract held)"
else
  fail "sqlite appeared without a dispatch"
fi
if printf '%s' "$OUT" | grep -q "lazily"; then
  pass "post-install note documents the lazy sqlite"
else
  fail "lazy-sqlite note missing from output"
fi

# --------------------------------------------------------------------------- #
# Test 6: idempotency -- re-run changes nothing structurally
# --------------------------------------------------------------------------- #
echo "-- idempotency"
OUT2="$(run_installer --client-slug test-client)"; RC=$?
if [ $RC -eq 0 ]; then pass "second install exits 0"; else fail "second install rc=$RC"; fi
if [ "$(count_entries)" = "1" ]; then pass "re-run adds zero duplicate entries"; else fail "entry count=$(count_entries) after re-run"; fi
config_json | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null \
  && pass "config still valid JSON after re-run" \
  || fail "config invalid after re-run"
if printf '%s' "$OUT2" | grep -qE "no-op|already in sync"; then
  pass "materializer reports no-op for the synced dept"
else
  fail "no sync marker in re-run output: $(printf '%s' "$OUT2" | tail -3)"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 7: verify mode -- fail on empty box, pass on materialized box
# --------------------------------------------------------------------------- #
echo "-- verify mode"
make_fixture true
INSTALL_ENV=(__none__)
OUT="$(run_installer --verify --client-slug test-client)"; RC=$?
if [ $RC -ne 0 ]; then pass "verify fails on un-materialized box (rc=$RC)"; else fail "verify passed on empty box"; fi
if printf '%s' "$OUT" | grep -q "MISS"; then pass "verify prints MISS lines"; else fail "no MISS lines"; fi

# Materialize, then satisfy the two checks verify needs beyond install:
# the sqlite store (simulate the gateway's lazy creation) and the podcast:
# session-namespace prefix (written by register-podcast-hook.sh, act-1).
OUT="$(run_installer --client-slug test-client)"; RC=$?
[ $RC -eq 0 ] || fail "pre-verify install rc=$RC"
touch "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/agent/openclaw-agent.sqlite"
inject_hooks_prefix
OUT="$(run_installer --verify --client-slug test-client)"; RC=$?
if [ $RC -eq 0 ] && printf '%s' "$OUT" | grep -q "verify: PASS"; then
  pass "verify passes when fully materialized"
else
  fail "verify on materialized box (rc=$RC): $(printf '%s' "$OUT" | grep MISS)"
fi

# Namespace missing -> verify fails even with everything else present
python3 - "$FIXTURE_ROOT/.openclaw/openclaw.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.get("hooks", {}).pop("allowedSessionKeyPrefixes", None)
with open(p, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
OUT="$(run_installer --verify --client-slug test-client)"; RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "namespace"; then
  pass "verify fails when podcast: prefix absent"
else
  fail "verify without prefix (rc=$RC)"
fi

# Legacy sqlite layout (agentDir/openclaw-agent.sqlite) also verifies
rm "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/agent/openclaw-agent.sqlite"
inject_hooks_prefix
touch "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/openclaw-agent.sqlite"
OUT="$(run_installer --verify --client-slug test-client)"; RC=$?
if [ $RC -eq 0 ]; then pass "legacy top-level sqlite layout accepted by verify"; else fail "legacy sqlite verify rc=$RC"; fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 8: interview-incomplete precondition (fail closed)
# --------------------------------------------------------------------------- #
echo "-- interview precondition"
make_fixture false
INSTALL_ENV=(__none__)
OUT="$(run_installer --client-slug test-client)"; RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "interview"; then
  pass "interview-incomplete stops the install with a clear message"
else
  fail "interview precondition (rc=$RC)"
fi
if [ "$(count_entries)" = "0" ]; then pass "no entry written when interview incomplete"; else fail "entry written despite precondition"; fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 9: PODCAST_CLIENT_SLUG env fallback
# --------------------------------------------------------------------------- #
echo "-- slug env fallback"
make_fixture true
INSTALL_ENV=(PODCAST_CLIENT_SLUG=env-client)
OUT="$(run_installer)"; RC=$?
if [ $RC -eq 0 ] && printf '%s' "$OUT" | grep -q "podcast:intake:env-client"; then
  pass "PODCAST_CLIENT_SLUG used when --client-slug absent"
else
  fail "env fallback (rc=$RC)"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 10: --prime-session with a fake openclaw CLI
# --------------------------------------------------------------------------- #
echo "-- prime-session"
make_fixture true
FAKE_BIN="$FIXTURE_ROOT/bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/openclaw" <<EOF
#!/usr/bin/env bash
# Fake gateway CLI: mimic a successful no-op turn by lazily creating storage.
AD="$FIXTURE_ROOT/.openclaw/agents/dept-podcast"
mkdir -p "\$AD/agent" "\$AD/sessions"
printf 'sqlite-stub' > "\$AD/agent/openclaw-agent.sqlite"
echo "ok"
EOF
chmod +x "$FAKE_BIN/openclaw"
INSTALL_ENV=(__none__)
OUT="$(env -i HOME="$FIXTURE_ROOT" PATH="$FAKE_BIN:$PATH" \
      PODCAST_INSTALL_OC_ROOT="$FIXTURE_ROOT/.openclaw" \
      bash "$SCRIPT" --client-slug test-client --prime-session 2>&1)"; RC=$?
if [ $RC -eq 0 ] && [ -f "$FIXTURE_ROOT/.openclaw/agents/dept-podcast/agent/openclaw-agent.sqlite" ]; then
  pass "--prime-session dispatches and verifies the sqlite + sessions dir"
else
  fail "prime-session (rc=$RC): $(printf '%s' "$OUT" | tail -2)"
fi

# Prime with a failing gateway CLI -> fail closed (exit 4)
cat > "$FAKE_BIN/openclaw" <<'EOF'
#!/usr/bin/env bash
echo "gateway turn failed" >&2
exit 1
EOF
chmod +x "$FAKE_BIN/openclaw"
OUT="$(env -i HOME="$FIXTURE_ROOT" PATH="$FAKE_BIN:$PATH" \
      PODCAST_INSTALL_OC_ROOT="$FIXTURE_ROOT/.openclaw" \
      bash "$SCRIPT" --client-slug test-client --prime-session 2>&1)"; RC=$?
if [ $RC -eq 4 ] && printf '%s' "$OUT" | grep -q "prime dispatch failed"; then
  pass "failed prime turn fails closed (exit 4)"
else
  fail "failed prime (rc=$RC)"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Test 11: secret hygiene -- env values never appear in output
# --------------------------------------------------------------------------- #
echo "-- secret hygiene"
make_fixture true
INSTALL_ENV=(PODCAST_CLIENT_ID=sekrit-value-123 PODCAST_CLIENT_LOCATION_ID=loc_abc_999 PODCAST_CLIENT_EMAIL=who@example.com)
OUT="$(run_installer --client-slug test-client)"
if printf '%s' "$OUT" | grep -q "sekrit-value-123"; then
  fail "PODCAST_CLIENT_ID value leaked into output"
else
  pass "PODCAST_CLIENT_ID value never printed"
fi
if printf '%s' "$OUT" | grep -q "loc_abc_999"; then
  fail "PODCAST_CLIENT_LOCATION_ID value leaked into output"
else
  pass "PODCAST_CLIENT_LOCATION_ID value never printed"
fi
if printf '%s' "$OUT" | grep -q "PODCAST_CLIENT_ID.*SET"; then
  pass "labels reported SET/NOT SET only"
else
  fail "label presence report missing"
fi
clean_fixture

# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
echo ""
echo "== install-podcast-department suite: PASS=$PASS FAIL=$FAIL =="
[ "$FAIL" -eq 0 ]
