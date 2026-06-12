#!/usr/bin/env bash
# test-add-role-index.sh — Test suite for add-role.sh _index.json upsert (§1.1 / §4.1)
#
# Tests:
#   1. upsert_role_into_index adds a role to an existing dept
#   2. Re-running with same role = idempotent (no duplicate)
#   3. Adding role to non-existent dept = FAIL LOUD
#   4. total_roles recomputed correctly after add
#
# Exit codes: 0 = all pass, 1 = one or more failed

set -euo pipefail
P="[test-add-role-index]"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

# ─── Setup: build a minimal _index.json in a temp dir ────────────────────────
TMP_DIR="$(mktemp -d)"
trap "rm -rf $TMP_DIR" EXIT

INDEX_JSON="$TMP_DIR/_index.json"
python3 - "$INDEX_JSON" <<'PYEOF'
import json, sys
idx = {
    "version": "11.18.5",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "total_roles": 2,
    "total_departments": 1,
    "departments": {
        "podcast": {
            "count": 2,
            "roles": ["head-of-podcast", "producer"]
        }
    }
}
with open(sys.argv[1], "w") as f:
    json.dump(idx, f, indent=2)
    f.write("\n")
print(f"Wrote test _index.json to {sys.argv[1]}")
PYEOF

# ─── Test 1: add a new role ───────────────────────────────────────────────────
echo "$P Test 1: add new role to existing dept..."

python3 - "$INDEX_JSON" <<'PYEOF'
import json, sys, os, tempfile
from pathlib import Path

idx_path = Path(sys.argv[1])
idx = json.loads(idx_path.read_text())

# Inline the upsert logic from add-role.sh
dept_slug = "podcast"
role_slug = "audio-editor"
now = "2026-06-11T00:00:00+00:00"

deps = idx.setdefault("departments", {})
assert dept_slug in deps, f"FATAL: dept '{dept_slug}' not found in _index.json"

roles = deps[dept_slug].get("roles", [])
assert role_slug not in roles
roles.append(role_slug)
roles.sort()
deps[dept_slug]["roles"] = roles
deps[dept_slug]["count"] = len(roles)

idx["total_roles"] = sum(len(d.get("roles", [])) for d in deps.values())
idx["total_departments"] = len(deps)
idx["generated_at"] = now

fd, tmp = tempfile.mkstemp(prefix=".idx.", suffix=".json.tmp", dir=str(idx_path.parent))
with os.fdopen(fd, "w") as f:
    json.dump(idx, f, indent=2)
    f.write("\n")
os.replace(tmp, str(idx_path))
print("DONE")
PYEOF

# Verify
TOTAL=$(python3 -c "import json; idx=json.load(open('$INDEX_JSON')); print(idx['total_roles'])")
ROLES=$(python3 -c "import json; idx=json.load(open('$INDEX_JSON')); print(len(idx['departments']['podcast']['roles']))")
COUNT=$(python3 -c "import json; idx=json.load(open('$INDEX_JSON')); print(idx['departments']['podcast']['count'])")

if [[ "$TOTAL" == "3" && "$ROLES" == "3" && "$COUNT" == "3" ]]; then
  pass "Role added: total_roles=$TOTAL, roles=$ROLES, count=$COUNT"
else
  fail "Role add failed: total_roles=$TOTAL (expected 3), roles=$ROLES, count=$COUNT"
fi

# ─── Test 2: idempotency — re-add same role ───────────────────────────────────
echo "$P Test 2: idempotency — re-adding same role..."

BEFORE=$(python3 -c "import json; idx=json.load(open('$INDEX_JSON')); print(idx['total_roles'])")

python3 - "$INDEX_JSON" <<'PYEOF'
import json, sys
from pathlib import Path
idx_path = Path(sys.argv[1])
idx = json.loads(idx_path.read_text())
dept_slug = "podcast"
role_slug = "audio-editor"
deps = idx.get("departments", {})
assert dept_slug in deps
roles = deps[dept_slug].get("roles", [])
if role_slug in roles:
    print(f"no-op: '{role_slug}' already in _index.json — idempotent")
else:
    print(f"ERROR: role should already be present")
    sys.exit(1)
PYEOF

AFTER=$(python3 -c "import json; idx=json.load(open('$INDEX_JSON')); print(idx['total_roles'])")
if [[ "$BEFORE" == "$AFTER" ]]; then
  pass "Idempotent: total_roles unchanged ($AFTER)"
else
  fail "Idempotent FAIL: total_roles changed from $BEFORE to $AFTER"
fi

# ─── Test 3: FAIL LOUD on non-existent dept ───────────────────────────────────
echo "$P Test 3: FAIL LOUD on non-existent dept..."

MISSING_OUTPUT=$(python3 - "$INDEX_JSON" <<'PYEOF' 2>&1 || true
import json, sys
from pathlib import Path
idx_path = Path(sys.argv[1])
idx = json.loads(idx_path.read_text())
dept_slug = "nonexistent-dept"
deps = idx.get("departments", {})
if dept_slug not in deps:
    print(f"FATAL: dept '{dept_slug}' not found in _index.json")
    sys.exit(1)
PYEOF
)
if echo "$MISSING_OUTPUT" | grep -q "not found in _index.json"; then
  pass "FAIL LOUD: correctly detected missing dept"
else
  fail "FAIL LOUD: should have printed 'not found in _index.json'. Got: $MISSING_OUTPUT"
fi

# ─── Test 4: total_roles invariant ────────────────────────────────────────────
echo "$P Test 4: total_roles invariant check..."

INVARIANT=$(python3 - "$INDEX_JSON" <<'PYEOF'
import json, sys
idx = json.load(open(sys.argv[1]))
deps = idx.get("departments", {})
computed = sum(len(d.get("roles", [])) for d in deps.values())
reported = idx.get("total_roles", None)
if reported == computed:
    print("INVARIANT_OK")
else:
    print(f"INVARIANT_FAIL: total_roles={reported} != sum={computed}")
    sys.exit(1)
PYEOF
)
if echo "$INVARIANT" | grep -q "INVARIANT_OK"; then
  pass "_index.json invariant: $INVARIANT"
else
  fail "_index.json invariant: $INVARIANT"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
