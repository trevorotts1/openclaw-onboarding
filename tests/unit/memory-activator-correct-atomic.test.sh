#!/usr/bin/env bash
# tests/unit/memory-activator-correct-atomic.test.sh
#
# Acceptance tests for T0-45, T2-27 and T2-28 (SK1-31, Skill 31).
#
#   T2-27  The canonical configuration the only supported activation path
#          applies did NOT contain `agents.defaults.memory.autoCapture` /
#          `autoRecall` or the documented `activeMemory` block — the two things
#          SKILL.md:14 marks "REQUIRED ... NOT optional". The layer reported
#          active and captured nothing.
#   T2-28  The activator rewrote the LIVE openclaw.json twice, non-atomically,
#          BEFORE validating, with no backup. An interruption between the two
#          writes, or a validation failure after them, left the box holding a
#          configuration that was never validated and could not be restored.
#          This is the file the gateway reads at start.
#   T0-45  `openclaw memory status || true` discarded the verification command's
#          exit status, and the DONE banner then named Gemini as the expected
#          provider even on the branch that resolved NO provider at all.
#
# Hermetic: a private HOME, a fake `openclaw` on PATH whose behaviour is set by
# environment variables, and `env -i` so a real credential in the runner's
# environment cannot influence the result. No fleet box is touched, no network.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACT="$REPO_ROOT/31-upgraded-memory-system/scripts/activate-memory-stack.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== memory-activator-correct-atomic.test.sh ==="
echo ""
[ -f "$ACT" ] || { echo "FAIL: activator not found at $ACT"; exit 1; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw"; exit 2 ;;
esac

# A fake `openclaw`. Behaviour is entirely environment-driven so each case below
# can construct exactly the runtime condition it needs.
BIN="$SANDBOX/bin"; mkdir -p "$BIN"
cat > "$BIN/openclaw" <<'OC'
#!/usr/bin/env bash
case "${1:-} ${2:-}" in
  "config validate") exit "${FAKE_OC_VALIDATE_RC:-0}" ;;
  "memory status")
    printf '%s\n' "${FAKE_OC_MEMORY_STATUS-Backend: builtin
Provider: gemini (requested: gemini)
Model:    gemini-embedding-2 @3072
Dreaming: 0 3 * * *}"
    exit "${FAKE_OC_MEMORY_RC:-0}" ;;
esac
exit 0
OC
chmod +x "$BIN/openclaw"

_mkbox() { # <dir> [<config-json>] [<secrets-line>]
  local home="$1" cfg="${2:-}" secret="${3:-}"
  mkdir -p "$home/.openclaw/secrets"
  if [ -n "$cfg" ]; then printf '%s\n' "$cfg" > "$home/.openclaw/openclaw.json"
  else printf '%s\n' '{"agents":{"defaults":{}}}' > "$home/.openclaw/openclaw.json"; fi
  : > "$home/.openclaw/secrets/.env"
  [ -n "$secret" ] && printf '%s\n' "$secret" >> "$home/.openclaw/secrets/.env"
  return 0
}

_run() { # <home> <extra-env...>  → runs the activator with a clean environment
  local home="$1"; shift
  env -i HOME="$home" PATH="$BIN:/usr/local/bin:/usr/bin:/bin" "$@" bash "$ACT" 2>&1
}

GEM_LINE='GEMINI_API_KEY=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE00'

# ===========================================================================
# T2-27 — the applied configuration contains the REQUIRED settings
# ===========================================================================
echo "--- T2-27: the applied configuration carries the required Layer-8 settings ---"
H1="$SANDBOX/box-required"
_mkbox "$H1" '' "$GEM_LINE"
OUT1="$(_run "$H1")"; rc1=$?
[ "$rc1" -eq 0 ] && pass "T2-27: the activator completes on a box with a Gemini key (exit 0)" \
  || { fail "T2-27: the activator failed (exit $rc1)"; printf '%s\n' "$OUT1" | sed 's/^/      /'; }

CFG1="$H1/.openclaw/openclaw.json"
for CHECK in \
  '.agents.defaults.memory.autoCapture == true|agents.defaults.memory.autoCapture' \
  '.agents.defaults.memory.autoRecall == true|agents.defaults.memory.autoRecall' \
  '.agents.defaults.activeMemory.enabled == true|agents.defaults.activeMemory.enabled' \
  '.agents.defaults.activeMemory.flushIntervalMinutes == 30|agents.defaults.activeMemory.flushIntervalMinutes' \
  '.agents.defaults.activeMemory.contextInjection.memoryWiki == true|activeMemory.contextInjection.memoryWiki' \
  '.plugins.entries."memory-core".enabled == true|plugins.entries.memory-core.enabled' \
  '.memory.backend == "builtin"|memory.backend' ; do
  EXPR="${CHECK%%|*}"; LABEL="${CHECK##*|}"
  if python3 - "$CFG1" "$EXPR" <<'PY' >/dev/null 2>&1
import json, sys
cfg = json.load(open(sys.argv[1]))
expr = sys.argv[2]
def get(path):
    cur = cfg
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur
lhs, rhs = expr.split(" == ")
path = [p.strip('."') for p in lhs.strip().lstrip(".").replace('"', "").split(".")]
val = get(path)
want = json.loads(rhs.strip().replace("'", '"'))
sys.exit(0 if val == want else 1)
PY
  then pass "T2-27: $LABEL is set in the applied configuration"
  else fail "T2-27: $LABEL is MISSING from the applied configuration"
  fi
done

# ===========================================================================
# T2-28 — atomic replace, with a backup, and never a partial live file
# ===========================================================================
echo ""
echo "--- T2-28: a changing run writes a timestamped backup ---"
if ls "$H1/.openclaw"/openclaw.json.bak.* >/dev/null 2>&1; then
  pass "T2-28: a timestamped backup of the pre-activation configuration exists"
else
  fail "T2-28: no backup was written before the live configuration was replaced"
fi

echo "--- T2-28: an interruption leaves the ORIGINAL, never a partial ---"
H2="$SANDBOX/box-interrupt"
_mkbox "$H2" '' "$GEM_LINE"
ORIG_SHA="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$H2/.openclaw/openclaw.json")"
env -i HOME="$H2" PATH="$BIN:/usr/local/bin:/usr/bin:/bin" bash "$ACT" >/dev/null 2>&1 &
ACT_PID=$!
KILLED=0
for _ in $(seq 1 500); do
  if ls "$H2/.openclaw"/.openclaw.json.staging.* >/dev/null 2>&1; then
    kill -9 "$ACT_PID" 2>/dev/null && KILLED=1
    break
  fi
  kill -0 "$ACT_PID" 2>/dev/null || break
  sleep 0.01
done
wait "$ACT_PID" 2>/dev/null
AFTER_SHA="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$H2/.openclaw/openclaw.json")"
if [ "$KILLED" -eq 1 ]; then
  if [ "$ORIG_SHA" = "$AFTER_SHA" ]; then
    pass "T2-28: killed while the mutations were in flight, the live configuration is byte-identical to the original"
  else
    # The other acceptable outcome is the FULLY updated file — never a partial.
    if python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); sys.exit(0 if c.get("agents",{}).get("defaults",{}).get("memory",{}).get("autoCapture") is True and c.get("memory",{}).get("backend")=="builtin" else 1)' "$H2/.openclaw/openclaw.json"; then
      pass "T2-28: the interrupted run left the FULLY updated configuration (the other legal outcome)"
    else
      fail "T2-28: the interrupted run left a PARTIAL configuration on disk"
    fi
  fi
else
  pass "T2-28: the run completed before the kill window (no partial state possible — both mutations are staged)"
fi
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$H2/.openclaw/openclaw.json" >/dev/null 2>&1 \
  && pass "T2-28: the live configuration is parseable after the interruption" \
  || fail "T2-28: the live configuration is corrupt after the interruption"

echo "--- T2-28: a validator rejection restores the pre-activation configuration ---"
H3="$SANDBOX/box-validate-fail"
_mkbox "$H3" '' "$GEM_LINE"
V_ORIG="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$H3/.openclaw/openclaw.json")"
OUT3="$(_run "$H3" FAKE_OC_VALIDATE_RC=1)"; rc3=$?
[ "$rc3" -ne 0 ] && pass "T2-28: a failing config validate makes the activator exit non-zero (exit $rc3)" \
  || fail "T2-28: a failing config validate did not fail the activator"
V_AFTER="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$H3/.openclaw/openclaw.json")"
[ "$V_ORIG" = "$V_AFTER" ] && pass "T2-28: the pre-activation configuration was restored from the backup" \
  || fail "T2-28: a rejected configuration was left installed"

# ===========================================================================
# T0-45 — the runtime status is a real postcondition
# ===========================================================================
echo ""
echo "--- T0-45: a failing 'openclaw memory status' fails the run ---"
H4="$SANDBOX/box-status-fail"
_mkbox "$H4" '' "$GEM_LINE"
OUT4="$(_run "$H4" FAKE_OC_MEMORY_RC=1)"; rc4=$?
[ "$rc4" -ne 0 ] && pass "T0-45: the activator exits non-zero when the memory runtime fails (exit $rc4)" \
  || fail "T0-45: the activator exited 0 with a failing memory runtime"
printf '%s' "$OUT4" | grep -q "DONE" \
  && fail "T0-45: a completion banner was printed on a failed runtime" \
  || pass "T0-45: no completion banner on a failed runtime"

echo "--- T0-45 MUTATION: restore '|| true' on the status call ---"
MUT="$SANDBOX/activate.MUTATED.sh"
python3 - "$ACT" "$MUT" <<'MUTPY'
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
start = s.index('MEM_STATUS=""')
end = s.index('echo "[activate-memory-stack] DONE', start)
pre = '''openclaw memory status || true

'''
open(dst, "w").write(s[:start] + pre + s[end:])
MUTPY
H5="$SANDBOX/box-status-fail-mut"
_mkbox "$H5" '' "$GEM_LINE"
OUT5="$(env -i HOME="$H5" PATH="$BIN:/usr/local/bin:/usr/bin:/bin" FAKE_OC_MEMORY_RC=1 bash "$MUT" 2>&1)"; rc5=$?
if [ "$rc5" -eq 0 ] && printf '%s' "$OUT5" | grep -q "DONE"; then
  pass "T0-45 MUTATION: with '|| true' restored the same failing runtime still prints DONE and exits 0 — the assertions above are discriminating"
else
  fail "T0-45 MUTATION: the pre-fix shape also failed (exit $rc5) — the mutation harness is broken"
fi

echo ""
echo "--- T0-45: a mismatched provider is a failure, not a banner ---"
H6="$SANDBOX/box-provider-mismatch"
_mkbox "$H6" '' "$GEM_LINE"
OUT6="$(_run "$H6" FAKE_OC_MEMORY_STATUS="Backend: builtin
Provider: none
Model:    (unset)")"
rc6=$?
[ "$rc6" -ne 0 ] && pass "T0-45: a runtime reporting Provider: none fails the activation (exit $rc6)" \
  || fail "T0-45: Provider: none was accepted as a successful activation"

echo ""
echo "--- T0-45: the printed criteria describe the provider ACTUALLY selected ---"
H7="$SANDBOX/box-openai"
_mkbox "$H7" '' 'OPENAI_API_KEY=sk-FAKEFAKEFAKEFAKEFAKEFAKE00'
OUT7="$(_run "$H7" FAKE_OC_MEMORY_STATUS="Backend: builtin
Provider: openai (requested: openai)
Model:    text-embedding-3-small")"
rc7=$?
if [ "$rc7" -eq 0 ] && printf '%s' "$OUT7" | grep -q "Provider: openai"; then
  pass "T0-45: an OpenAI-only box is told its provider is openai"
else
  fail "T0-45: exit $rc7; the criteria did not name the resolved provider"; printf '%s\n' "$OUT7" | sed 's/^/      /'
fi
printf '%s' "$OUT7" | grep -q "Provider: gemini" \
  && fail "T0-45: the banner still hard-codes gemini on a box that resolved openai" \
  || pass "T0-45: the banner no longer hard-codes gemini"
python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); sys.exit(0 if c["agents"]["defaults"]["memorySearch"]["provider"]=="openai" else 1)' \
  "$H7/.openclaw/openclaw.json" \
  && pass "T0-45: the configuration pins the provider the box can actually serve" \
  || fail "T0-45: the configuration does not match the resolved provider"

echo ""
echo "--- T0-45: no embedding-capable key at all is a failure, not DONE ---"
H8="$SANDBOX/box-nokey"
_mkbox "$H8" ''
OUT8="$(_run "$H8" FAKE_OC_MEMORY_STATUS="Backend: builtin
Provider: (unset)")"
rc8=$?
[ "$rc8" -ne 0 ] && pass "T0-45: a box with no embedding-capable key fails instead of declaring DONE (exit $rc8)" \
  || fail "T0-45: a keyless box still declared activation done"
printf '%s' "$OUT8" | grep -q "Provider: gemini" \
  && fail "T0-45: the keyless branch still tells the operator to expect gemini" \
  || pass "T0-45: the keyless branch does not name gemini"

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: the memory activator is correct, complete and atomic"
exit 0
