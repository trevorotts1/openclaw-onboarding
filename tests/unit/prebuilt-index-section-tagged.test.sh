#!/usr/bin/env bash
# tests/unit/prebuilt-index-section-tagged.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance test for prebuilt-index v2.1.0 dual-path provisioning.
#
# Asserts that BOTH install.sh and update-skills.sh provision the same
# section-tagged 54-persona DB + GHL funnel catalog, via the shared helper.
#
# Three layers (all offline, no live Gemini API):
#
#   (A) STATIC source asserts — grep patterns prove that:
#       - update-skills.sh calls provision_persona_index + wire_ghl_funnel_catalog
#       - install.sh calls wire_ghl_funnel_catalog and references GHL_FUNNEL_CATALOG
#       - shared-utils/provision-persona-index.sh exists and contains:
#         * PRAGMA table_info(embeddings) column check (section_number/mode)
#         * sha256 hard gate
#         * .prebuilt-index-version sentinel compare
#
#   (B) MANIFEST asserts (python3 json) — prove:
#       - persona_count == 54
#       - chunk_count == 4413
#       - asset_rebuild_required is false
#       - section_tagged is true
#       - release_tag == 'prebuilt-index-v2.1.0'
#       - schema.columns_required contains section_number + mode
#       - asset_url ends with /prebuilt-index-v2.1.0/gemini-index.sqlite.gz
#       - sha256 == '7282796558edfcf109664c4ee958d15fa184db6cd7274712667de83201e73fe3'
#
#   (C) FIXTURE structural assert — open the committed fixture SQLite
#       (tests/fixtures/prebuilt-index-section-tagged.fixture.sqlite) and assert:
#       - embeddings table has section_number + mode columns
#       - at least one row with mode='coaching' and section_number=3
#       - at least one row with mode='leadership' and section_number=4
#
# Layer (D) — FULL ARTIFACT (90MB download, sha256 verify, 54-persona count) —
# is intentionally NOT in this script so it never runs on every PR. It runs only
# in the `artifact-verify` CI job, which is gated to workflow_dispatch + release.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== prebuilt-index-section-tagged.test.sh ==="
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# (A) STATIC SOURCE ASSERTS
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (A) Static source asserts ---"

# A1: shared helper exists
if [ -f "$REPO_ROOT/shared-utils/provision-persona-index.sh" ]; then
    pass "A1: shared-utils/provision-persona-index.sh exists"
else
    fail "A1: shared-utils/provision-persona-index.sh MISSING"
fi

# A2: helper contains PRAGMA table_info check (column gate)
if grep -q "PRAGMA table_info(embeddings)" "$REPO_ROOT/shared-utils/provision-persona-index.sh" 2>/dev/null; then
    pass "A2: provision-persona-index.sh contains PRAGMA table_info(embeddings) column check"
else
    fail "A2: provision-persona-index.sh missing PRAGMA table_info(embeddings) column check"
fi

# A3: helper contains sha256 hard gate
if grep -q "sha256" "$REPO_ROOT/shared-utils/provision-persona-index.sh" 2>/dev/null && \
   grep -q "MISMATCH\|HARD" "$REPO_ROOT/shared-utils/provision-persona-index.sh" 2>/dev/null; then
    pass "A3: provision-persona-index.sh contains sha256 hard gate"
else
    fail "A3: provision-persona-index.sh missing sha256 hard gate"
fi

# A4: helper contains version sentinel compare
if grep -q "prebuilt-index-version" "$REPO_ROOT/shared-utils/provision-persona-index.sh" 2>/dev/null; then
    pass "A4: provision-persona-index.sh contains .prebuilt-index-version sentinel logic"
else
    fail "A4: provision-persona-index.sh missing .prebuilt-index-version sentinel logic"
fi

# A5: update-skills.sh calls provision_persona_index
if grep -q "provision_persona_index" "$REPO_ROOT/update-skills.sh" 2>/dev/null; then
    pass "A5: update-skills.sh calls provision_persona_index"
else
    fail "A5: update-skills.sh does NOT call provision_persona_index"
fi

# A6: update-skills.sh calls wire_ghl_funnel_catalog
if grep -q "wire_ghl_funnel_catalog" "$REPO_ROOT/update-skills.sh" 2>/dev/null; then
    pass "A6: update-skills.sh calls wire_ghl_funnel_catalog"
else
    fail "A6: update-skills.sh does NOT call wire_ghl_funnel_catalog"
fi

# A7: install.sh calls wire_ghl_funnel_catalog
if grep -q "wire_ghl_funnel_catalog" "$REPO_ROOT/install.sh" 2>/dev/null; then
    pass "A7: install.sh calls wire_ghl_funnel_catalog"
else
    fail "A7: install.sh does NOT call wire_ghl_funnel_catalog"
fi

# A8: install.sh references GHL_FUNNEL_CATALOG (via the helper call)
if grep -q "GHL_FUNNEL_CATALOG" "$REPO_ROOT/install.sh" 2>/dev/null || \
   grep -q "wire_ghl_funnel_catalog" "$REPO_ROOT/install.sh" 2>/dev/null; then
    pass "A8: install.sh wires GHL_FUNNEL_CATALOG (via helper call)"
else
    fail "A8: install.sh does not wire GHL_FUNNEL_CATALOG"
fi

# A9: install.sh sources provision-persona-index.sh
if grep -q "provision-persona-index.sh" "$REPO_ROOT/install.sh" 2>/dev/null; then
    pass "A9: install.sh sources provision-persona-index.sh"
else
    fail "A9: install.sh does not source provision-persona-index.sh"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# (B) MANIFEST ASSERTS
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (B) Manifest asserts ---"

MANIFEST="$REPO_ROOT/shared-utils/prebuilt-index/INDEX-MANIFEST.json"

if [ ! -f "$MANIFEST" ]; then
    fail "B0: INDEX-MANIFEST.json not found at $MANIFEST"
else
    pass "B0: INDEX-MANIFEST.json present"

    python3 - "$MANIFEST" <<'PYEOF'
import json, sys

EXPECTED_SHA = "7282796558edfcf109664c4ee958d15fa184db6cd7274712667de83201e73fe3"
EXPECTED_TAG = "prebuilt-index-v2.1.0"

m = json.load(open(sys.argv[1]))
results = []

def check(label, ok, detail=""):
    if ok:
        print(f"  PASS: {label}")
        results.append(("PASS", label))
    else:
        print(f"  FAIL: {label}" + (f" ({detail})" if detail else ""))
        results.append(("FAIL", label))

check("B1: persona_count == 54", m.get("persona_count") == 54,
      f"got {m.get('persona_count')}")
check("B2: chunk_count == 4413", m.get("chunk_count") == 4413,
      f"got {m.get('chunk_count')}")
check("B3: asset_rebuild_required is false", m.get("asset_rebuild_required") is False,
      f"got {m.get('asset_rebuild_required')}")
check("B4: section_tagged is true", m.get("section_tagged") is True,
      f"got {m.get('section_tagged')}")
check("B5: release_tag == prebuilt-index-v2.1.0",
      m.get("release_tag") == EXPECTED_TAG,
      f"got {m.get('release_tag')}")
check("B6: schema.columns_required contains section_number",
      "section_number" in m.get("schema", {}).get("columns_required", []),
      f"got {m.get('schema', {}).get('columns_required')}")
check("B7: schema.columns_required contains mode",
      "mode" in m.get("schema", {}).get("columns_required", []),
      f"got {m.get('schema', {}).get('columns_required')}")
check("B8: asset_url ends with /prebuilt-index-v2.1.0/gemini-index.sqlite.gz",
      m.get("asset_url", "").endswith("/prebuilt-index-v2.1.0/gemini-index.sqlite.gz"),
      f"got {m.get('asset_url')}")
check("B9: sha256 matches expected",
      m.get("sha256") == EXPECTED_SHA,
      f"got {m.get('sha256')}")
check("B10: canonical_persona_count == 54",
      m.get("canonical_persona_count") == 54,
      f"got {m.get('canonical_persona_count')}")

fails = [r for r in results if r[0] == "FAIL"]
sys.exit(len(fails))
PYEOF
    B_EXIT=$?
    if [ "$B_EXIT" -eq 0 ]; then
        PASS=$((PASS + 10))
    else
        FAIL=$((FAIL + B_EXIT))
        PASS=$((PASS + 10 - B_EXIT))
    fi
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# (C) FIXTURE STRUCTURAL ASSERT
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (C) Fixture structural assert ---"

FIXTURE="$REPO_ROOT/tests/fixtures/prebuilt-index-section-tagged.fixture.sqlite"

if [ ! -f "$FIXTURE" ]; then
    fail "C0: fixture SQLite not found at $FIXTURE"
else
    pass "C0: fixture SQLite present"

    python3 - "$FIXTURE" <<'PYEOF'
import sqlite3, sys

db_path = sys.argv[1]
results = []

def check(label, ok, detail=""):
    if ok:
        print(f"  PASS: {label}")
        results.append(("PASS", label))
    else:
        print(f"  FAIL: {label}" + (f" ({detail})" if detail else ""))
        results.append(("FAIL", label))

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    cols = [r[1] for r in c.execute('PRAGMA table_info(embeddings)').fetchall()]
    check("C1: embeddings table has section_number column",
          "section_number" in cols,
          f"cols={cols}")
    check("C2: embeddings table has mode column",
          "mode" in cols,
          f"cols={cols}")

    coaching_row = c.execute(
        "SELECT COUNT(*) FROM embeddings WHERE mode='coaching' AND section_number=3"
    ).fetchone()[0]
    check("C3: at least one coaching row (mode=coaching, section_number=3)",
          coaching_row > 0,
          f"count={coaching_row}")

    leadership_row = c.execute(
        "SELECT COUNT(*) FROM embeddings WHERE mode='leadership' AND section_number=4"
    ).fetchone()[0]
    check("C4: at least one leadership row (mode=leadership, section_number=4)",
          leadership_row > 0,
          f"count={leadership_row}")

    conn.close()
except Exception as e:
    print(f"  FAIL: fixture open/query error: {e}")
    results.append(("FAIL", "fixture open error"))

fails = [r for r in results if r[0] == "FAIL"]
sys.exit(len(fails))
PYEOF
    C_EXIT=$?
    if [ "$C_EXIT" -eq 0 ]; then
        PASS=$((PASS + 4))
    else
        FAIL=$((FAIL + C_EXIT))
        PASS=$((PASS + 4 - C_EXIT))
    fi
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
