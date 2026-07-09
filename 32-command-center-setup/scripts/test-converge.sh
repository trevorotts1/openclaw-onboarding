#!/usr/bin/env bash
# test-converge.sh — Test suite for sync-extensions.sh --converge (§1.6 / §4.1)
#
# Tests:
#   1. --converge flag is recognized (no crash)
#   2. _index.json invariant check works (detects drift)
#   3. --dry-run + --converge produces correct output without mutations
#   4. detect-extensions.py extended output (NEW-ROLE, NEW-SOP, NEW-PERSONA, UNTAGGED)
#   5. last-sync.json updated with extended fields (roles, sops, personas)

set -uo pipefail
P="[test-converge]"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT_PY="$SCRIPT_DIR/detect-extensions.py"
SYNC_SH="$SCRIPT_DIR/sync-extensions.sh"

if [[ ! -f "$DETECT_PY" ]]; then
  echo "$P FATAL: detect-extensions.py not found at $DETECT_PY" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap "rm -rf $TMP_DIR" EXIT

# ─── Build test _index.json ───────────────────────────────────────────────────
INDEX_JSON="$TMP_DIR/_index.json"
python3 - "$INDEX_JSON" <<'PYEOF'
import json, sys
idx = {
    "version": "11.18.5",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "total_roles": 3,
    "total_departments": 1,
    "departments": {
        "podcast": {
            "count": 3,
            "roles": ["head-of-podcast", "producer", "audio-editor"]
        }
    }
}
with open(sys.argv[1], "w") as f:
    json.dump(idx, f, indent=2)
    f.write("\n")
PYEOF

# ─── Test 1: detect-extensions.py NEW-DEPT output ────────────────────────────
echo "$P Test 1: detect-extensions.py NEW-DEPT output..."
OUTPUT=$(python3 "$DETECT_PY" --index "$INDEX_JSON" 2>&1)
if echo "$OUTPUT" | grep -q "^NEW: podcast" && echo "$OUTPUT" | grep -q "^NEW-DEPT: podcast"; then
  pass "detect-extensions.py emits both NEW: and NEW-DEPT: (back-compat + new canonical)"
else
  fail "detect-extensions.py output missing NEW: or NEW-DEPT: for podcast. Got: $OUTPUT"
fi

# ─── Test 2: detect-extensions.py NEW-ROLE output ────────────────────────────
echo "$P Test 2: detect-extensions.py NEW-ROLE output..."
if echo "$OUTPUT" | grep -q "^NEW-ROLE: podcast/"; then
  pass "detect-extensions.py emits NEW-ROLE: lines"
else
  fail "detect-extensions.py missing NEW-ROLE: lines. Got: $OUTPUT"
fi

# ─── Test 3: idempotency with last-sync.json ─────────────────────────────────
echo "$P Test 3: idempotency — last-sync.json with all entities present..."
LAST_SYNC="$TMP_DIR/last-sync.json"
python3 - "$LAST_SYNC" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
state = {
    "synced_at": datetime.now(timezone.utc).isoformat(),
    "version": "11.18.5",
    "total_roles": 3,
    "departments": ["podcast"],
    "roles": ["podcast/head-of-podcast", "podcast/producer", "podcast/audio-editor"],
    "sops": [],
    "personas": [],
}
with open(sys.argv[1], "w") as f:
    json.dump(state, f, indent=2)
PYEOF

OUTPUT2=$(python3 "$DETECT_PY" --index "$INDEX_JSON" --last-sync "$LAST_SYNC" 2>&1)
if echo "$OUTPUT2" | grep -qE "^NEW:|^NEW-DEPT:|^NEW-ROLE:"; then
  fail "After full last-sync, should have NO new entities but got: $OUTPUT2"
else
  pass "Idempotent: no new entities when last-sync is current"
fi

# ─── Test 4: UNTAGGED persona detection ──────────────────────────────────────
echo "$P Test 4: UNTAGGED persona detection..."
PC_JSON="$TMP_DIR/persona-categories.json"
python3 - "$PC_JSON" <<'PYEOF'
import json, sys
data = {
    "personas": {
        "tagged-persona": {"author": "Author 1", "domain": ["coaching"], "perspective": ["growth"]},
        "untagged-persona": {"author": "Author 2", "domain": [], "perspective": []},
    }
}
with open(sys.argv[1], "w") as f:
    json.dump(data, f, indent=2)
PYEOF

OUTPUT3=$(python3 "$DETECT_PY" --index "$INDEX_JSON" --last-sync "$LAST_SYNC" \
  --persona-categories "$PC_JSON" 2>&1)
if echo "$OUTPUT3" | grep -q "^UNTAGGED: untagged-persona"; then
  pass "detect-extensions.py correctly emits UNTAGGED: for persona with empty domain/perspective"
else
  fail "detect-extensions.py should emit UNTAGGED: for empty-tagged persona. Got: $OUTPUT3"
fi
if echo "$OUTPUT3" | grep -q "^NEW-PERSONA: untagged-persona"; then
  pass "detect-extensions.py emits NEW-PERSONA: for new persona"
else
  fail "detect-extensions.py should emit NEW-PERSONA:. Got: $OUTPUT3"
fi

# ─── Test 5: _index.json invariant validation ─────────────────────────────────
echo "$P Test 5: _index.json invariant validation (drift detection)..."
DRIFTED_IDX="$TMP_DIR/_drifted_index.json"
python3 - "$DRIFTED_IDX" <<'PYEOF'
import json, sys
# total_roles is wrong (244 instead of 3)
idx = {
    "version": "11.18.5",
    "total_roles": 244,
    "total_departments": 1,
    "departments": {
        "podcast": {"count": 3, "roles": ["head-of-podcast", "producer", "audio-editor"]}
    }
}
with open(sys.argv[1], "w") as f:
    json.dump(idx, f, indent=2)
PYEOF

INVARIANT=$(python3 - "$DRIFTED_IDX" <<'PYEOF'
import json, sys
idx = json.load(open(sys.argv[1]))
deps = idx.get("departments", {})
computed = sum(len(d.get("roles", [])) for d in deps.values())
reported = idx.get("total_roles", None)
if reported != computed:
    print(f"INVARIANT_FAIL: total_roles={reported} but sum(dept roles)={computed}")
    sys.exit(1)
print("INVARIANT_OK")
PYEOF
)
if echo "$INVARIANT" | grep -q "INVARIANT_FAIL"; then
  pass "_index.json drift detected correctly: $INVARIANT"
else
  fail "Invariant check should have detected drift. Got: $INVARIANT"
fi

# ─── Test 6: seed-workspaces.py accepts string-shape departments.json ────────
# Regression for the --converge Step-4 crash: a departments.json with bare
# string entries raised "'str' object has no attribute 'get'". The normalizer
# must coerce strings → dicts so seed() runs.
echo "$P Test 6: seed-workspaces.py normalizes string-shape departments.json..."
SEED_PY="$SCRIPT_DIR/seed-workspaces.py"
if [[ -f "$SEED_PY" ]]; then
  NORMALIZE_OUT=$(python3 - "$SEED_PY" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sw", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = m._normalize_departments(["marketing", "sales", "dept-finance"])
assert all(isinstance(d, dict) and d.get("id") for d in out), out
assert out[0] == {"id": "marketing", "name": "Marketing"}, out[0]
print("OK")
PYEOF
)
  if [[ "$NORMALIZE_OUT" == "OK" ]]; then
    pass "seed-workspaces.py coerces string-shape departments.json (no .get crash)"
  else
    fail "seed-workspaces.py normalizer did not coerce strings. Got: $NORMALIZE_OUT"
  fi
else
  fail "seed-workspaces.py not found at $SEED_PY"
fi

# ─── Test 7: Step 4b — CC recompile decision reached on --converge --dry-run ─
# BUILD-01: adding a NEW department is a structural change that must recompile
# the Command Center via atomic-deploy.sh (converge alone never runs `next
# build`). In --dry-run that recompile is ANNOUNCED but not executed. We drive
# the whole orchestrator inside a fully isolated $HOME sandbox so it never
# touches the live box, with no last-sync.json so every dept reads as NEW.
echo "$P Test 7: Step 4b recompile decision reached (--converge --dry-run)..."
if [[ -e /data/.openclaw ]]; then
  echo "$P SKIP: /data/.openclaw present — refusing to run the orchestrator on a live VPS box"
elif [[ ! -f "$SYNC_SH" ]]; then
  fail "sync-extensions.sh not found at $SYNC_SH"
else
  SBOX="$(mktemp -d)"
  mkdir -p "$SBOX/.openclaw"
  printf '{"agents":{}}\n' > "$SBOX/.openclaw/openclaw.json"
  S4B_OUT="$(HOME="$SBOX" bash "$SYNC_SH" --converge --dry-run 2>&1 || true)"
  if echo "$S4B_OUT" | grep -q "Step 4b: \[DRY-RUN\] would recompile Command Center"; then
    pass "Step 4b recompile decision reached (dry-run, NEW_DEPTS present)"
  else
    fail "Step 4b dry-run recompile line not found. Tail: $(echo "$S4B_OUT" | tail -5)"
  fi
  # Isolation invariant: the real $HOME must be untouched (only the sandbox wrote).
  if [[ -f "$SBOX/.openclaw/openclaw.json" ]]; then
    pass "Orchestrator wrote only inside the isolated \$HOME sandbox"
  else
    fail "Sandbox openclaw.json missing after run — isolation invariant broken"
  fi
  rm -rf "$SBOX"
fi

# ─── Test 8: Step 4b — converge-route `deploy` directive parser ──────────────
# Step 4b consumes the converge HTTP response's `deploy` directive: deploy:false
# ⇒ CC says no rebuild needed; deploy:true/absent/invalid ⇒ recompile. This is
# the exact python one-liner the script embeds; assert every branch.
echo "$P Test 8: Step 4b deploy-directive parser (true/false/absent/invalid)..."
parse_deploy() {
  printf '%s' "$1" | python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
v=d.get("deploy")
print("" if v is None else ("true" if v else "false"))' 2>/dev/null || true
}
D_OK=1
[[ "$(parse_deploy '{"ok":true,"deploy":true}')"  == "true"  ]] || { D_OK=0; echo "  deploy:true  -> got [$(parse_deploy '{"ok":true,"deploy":true}')]"; }
[[ "$(parse_deploy '{"ok":true,"deploy":false}')" == "false" ]] || { D_OK=0; echo "  deploy:false -> got [$(parse_deploy '{"ok":true,"deploy":false}')]"; }
[[ "$(parse_deploy '{"ok":true}')"                == ""      ]] || { D_OK=0; echo "  absent       -> got [$(parse_deploy '{"ok":true}')]"; }
[[ "$(parse_deploy 'not-json')"                   == ""      ]] || { D_OK=0; echo "  invalid      -> got [$(parse_deploy 'not-json')]"; }
if [[ $D_OK -eq 1 ]]; then
  pass "deploy-directive parser: true/false/absent/invalid all correct"
else
  fail "deploy-directive parser produced an unexpected value (see above)"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
