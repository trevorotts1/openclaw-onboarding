#!/usr/bin/env bash
# ============================================================
#  test-p209-jev-live-decision-probe.sh — regression lock for
#  scripts/probe/p209-jev-live-decision-probe.py
#
#  Standalone: every scenario builds its OWN fake shared-utils/decision-
#  engine.py under a throwaway temp skills root. This test NEVER imports,
#  copies, or shells out to this repo's real shared-utils/decision-engine.py
#  -- the whole point of p209 is to check whatever bridge is ACTUALLY
#  installed on a box, and a fake bridge is the only way to prove both the
#  pre-JGT101 (legacy) and post-JGT101 (live) shapes deterministically.
#
#  FAIL-FIRST PROOF (reproducible): before
#  scripts/probe/p209-jev-live-decision-probe.py existed, scenario 0 below
#  fails (script not found) and every dependent scenario fails with it --
#  0/N pass. With the script shipped, N/N pass.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/probe/p209-jev-live-decision-probe.py"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "Scenario 0 — the probe script must exist and be syntactically valid python3"
if [ -f "$PROBE" ]; then
  _pass "p209-jev-live-decision-probe.py shipped at $PROBE"
else
  _fail "p209-jev-live-decision-probe.py NOT FOUND at $PROBE -- pre-fix tree"
fi
if [ -f "$PROBE" ] && python3 -m py_compile "$PROBE" 2>/dev/null; then
  _pass "python3 -m py_compile OK"
else
  [ -f "$PROBE" ] && _fail "python3 -m py_compile FAILED"
fi
if [ ! -f "$PROBE" ]; then
  _section "SUMMARY"; echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"; exit 1
fi

TESTHOME="$(mktemp -d)"
trap 'rm -rf "$TESTHOME"' EXIT

# ─── fake bridge builders ────────────────────────────────────────────────

_mk_bridge_correct() {
  # $1 = path to write the fake shared-utils/decision-engine.py to.
  # Contract-correct: --capability answers schemaVersion 1.1.0; --evaluate
  # answers intent + route per the 3 fixed probe messages, echoes
  # configRevision, and emits no forbidden key.
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<'PYEOF'
import sys, json

def main():
    argv = sys.argv[1:]
    if "--capability" in argv:
        print(json.dumps({"schemaVersion": "1.1.0"}))
        return 0
    if "--evaluate" in argv:
        req = json.loads(sys.stdin.read())
        text = req.get("taskDescription", "")
        cfg = req.get("configRevision")
        if "Tokyo" in text:
            resp = {
                "intent": "answer_only",
                "route": {"action": "answer", "department": None, "confidence": 0.0,
                          "fallback": False, "catalog": "empty"},
                "configRevision": cfg,
            }
        elif "press release" in text:
            resp = {
                "intent": "task_request",
                "route": {"action": "route", "department": "communications", "confidence": 0.9,
                          "fallback": False, "catalog": "standard-floor"},
                "configRevision": cfg,
            }
        else:
            resp = {
                "intent": "task_request",
                "route": {"action": "route", "department": "general-task", "confidence": 0.0,
                          "fallback": True, "catalog": "standard-floor"},
                "configRevision": cfg,
            }
        print(json.dumps(resp))
        return 0
    print("usage: decision-engine.py [--capability] [--evaluate]", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
PYEOF
}

_mk_bridge_legacy() {
  # $1 = path. Pre-JGT101 shape: capability is fine (schema was already
  # 1.1.0), but --evaluate answers only {roleId, confidence, rationale,
  # configRevision} -- no intent, no route.
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<'PYEOF'
import sys, json

def main():
    argv = sys.argv[1:]
    if "--capability" in argv:
        print(json.dumps({"schemaVersion": "1.1.0"}))
        return 0
    if "--evaluate" in argv:
        req = json.loads(sys.stdin.read())
        resp = {
            "schemaVersion": "1.1.0",
            "configRevision": req.get("configRevision"),
            "recommendation": {"roleId": "none_suitable", "confidence": 0.0, "rationale": "no fit"},
        }
        print(json.dumps(resp))
        return 0
    print("usage: decision-engine.py [--capability] [--evaluate]", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
PYEOF
}

_checksum_tree() {
  # A single stable checksum of every file's contents + relative path under $1.
  ( cd "$1" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}' )
}

# ─── Scenario 1: contract-correct fake -> PASS, exit 0 ─────────────────────
_section "Scenario 1 — contract-correct fake bridge, mode unset (default auto) -> PASS, exit 0"
SKILLS1="$TESTHOME/skills1"
_mk_bridge_correct "$SKILLS1/shared-utils/decision-engine.py"
OCCFG1="$TESTHOME/occfg1"; mkdir -p "$OCCFG1"
OUT1="$(env -u OPENCLAW_DECISION_ENGINE_MODE python3 "$PROBE" --json --skills-root "$SKILLS1" --oc-config "$OCCFG1" 2>&1)"; RC1=$?
if [ "$RC1" -eq 0 ] && echo "$OUT1" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['verdict'] == 'PASS', d
assert d['mode'] == 'auto' and d['mode_source'] == 'default', d
assert all(c['passed'] for c in d['checks']), d
" 2>/dev/null; then
  _pass "contract-correct fake -> PASS, exit 0, mode default auto, all checks passed"
else
  _fail "contract-correct fake did not report PASS (rc=$RC1): $OUT1"
fi

# ─── Scenario 2: legacy fake (roleId only) -> exit 1 with 'predates' ────────
_section "Scenario 2 — legacy fake bridge (roleId only, no intent/route) -> FAIL exit 1, 'predates'"
SKILLS2="$TESTHOME/skills2"
_mk_bridge_legacy "$SKILLS2/shared-utils/decision-engine.py"
OUT2="$(env -u OPENCLAW_DECISION_ENGINE_MODE python3 "$PROBE" --json --skills-root "$SKILLS2" --oc-config "$OCCFG1" 2>&1)"; RC2=$?
if [ "$RC2" -eq 1 ] && echo "$OUT2" | grep -q "predates" && echo "$OUT2" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['verdict'] == 'FAIL', d
assert d['predates'] is True, d
" 2>/dev/null; then
  _pass "legacy fake correctly reported FAIL exit 1 with 'predates' message"
else
  _fail "legacy fake did not report FAIL/predates correctly (rc=$RC2): $OUT2"
fi

# ─── Scenario 3: correct fake + conf file 'off' -> PASS_KILL_SWITCH_OFF ─────
_section "Scenario 3 — contract-correct fake + decision-engine-mode.conf 'off' -> PASS_KILL_SWITCH_OFF"
OCCFG3="$TESTHOME/occfg3"; mkdir -p "$OCCFG3"
echo "off" > "$OCCFG3/decision-engine-mode.conf"
OUT3="$(env -u OPENCLAW_DECISION_ENGINE_MODE python3 "$PROBE" --json --skills-root "$SKILLS1" --oc-config "$OCCFG3" 2>&1)"; RC3=$?
if [ "$RC3" -eq 0 ] && echo "$OUT3" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['verdict'] == 'PASS_KILL_SWITCH_OFF', d
assert d['mode'] == 'off' and d['mode_source'] == 'file', d
assert all(c['passed'] for c in d['checks']), d
" 2>/dev/null; then
  _pass "conf file 'off' correctly reported PASS_KILL_SWITCH_OFF, exit 0, source file"
else
  _fail "conf file 'off' did not report PASS_KILL_SWITCH_OFF correctly (rc=$RC3): $OUT3"
fi

# ─── Scenario 4: env auto overrides file off -> PASS, source env ───────────
_section "Scenario 4 — OPENCLAW_DECISION_ENGINE_MODE=auto overrides file 'off' -> PASS, source env"
OUT4="$(OPENCLAW_DECISION_ENGINE_MODE=auto python3 "$PROBE" --json --skills-root "$SKILLS1" --oc-config "$OCCFG3" 2>&1)"; RC4=$?
if [ "$RC4" -eq 0 ] && echo "$OUT4" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['verdict'] == 'PASS', d
assert d['mode'] == 'auto' and d['mode_source'] == 'env', d
" 2>/dev/null; then
  _pass "env auto correctly overrides file off -> PASS, source env"
else
  _fail "env override did not report PASS/source env correctly (rc=$RC4): $OUT4"
fi

# ─── Scenario 5: no bridge -> exit 1 ────────────────────────────────────────
_section "Scenario 5 — no shared-utils/decision-engine.py at all -> FAIL, exit 1"
SKILLS5="$TESTHOME/skills5-empty"; mkdir -p "$SKILLS5"
OUT5="$(env -u OPENCLAW_DECISION_ENGINE_MODE python3 "$PROBE" --json --skills-root "$SKILLS5" --oc-config "$OCCFG1" 2>&1)"; RC5=$?
if [ "$RC5" -eq 1 ] && echo "$OUT5" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['verdict'] == 'FAIL', d
assert d['bridge_present'] is False, d
" 2>/dev/null; then
  _pass "missing bridge correctly reported FAIL, exit 1"
else
  _fail "missing bridge did not report FAIL correctly (rc=$RC5): $OUT5"
fi

# ─── Scenario 6: a bad arg -> exit 2 ────────────────────────────────────────
_section "Scenario 6 — an unrecognized argument -> usage error, exit 2"
OUT6="$(python3 "$PROBE" --this-flag-does-not-exist 2>&1)"; RC6=$?
if [ "$RC6" -eq 2 ]; then
  _pass "bad arg correctly exits 2 (usage error)"
else
  _fail "bad arg did not exit 2 (rc=$RC6): $OUT6"
fi

# ─── Scenario 7: the temp tree checksum is unchanged (read-only proof) ─────
_section "Scenario 7 — probe run leaves the temp skills tree byte-for-byte unchanged"
SKILLS7="$TESTHOME/skills7"
_mk_bridge_correct "$SKILLS7/shared-utils/decision-engine.py"
OCCFG7="$TESTHOME/occfg7"; mkdir -p "$OCCFG7"; echo "auto" > "$OCCFG7/decision-engine-mode.conf"
BEFORE="$(_checksum_tree "$SKILLS7")"
BEFORE_OC="$(_checksum_tree "$OCCFG7")"
python3 "$PROBE" --json --skills-root "$SKILLS7" --oc-config "$OCCFG7" >/dev/null 2>&1
AFTER="$(_checksum_tree "$SKILLS7")"
AFTER_OC="$(_checksum_tree "$OCCFG7")"
if [ "$BEFORE" = "$AFTER" ] && [ "$BEFORE_OC" = "$AFTER_OC" ]; then
  _pass "temp skills root and oc-config tree checksums unchanged after the probe ran (read-only)"
else
  _fail "the probe modified the temp tree it was checking (skills before=$BEFORE after=$AFTER; oc before=$BEFORE_OC after=$AFTER_OC)"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
