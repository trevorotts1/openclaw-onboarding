#!/usr/bin/env bash
# tests/unit/prebuilt-index-section-tagged.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance test for prebuilt-index v2.2.x dual-path provisioning.
#
# Asserts that BOTH install.sh and update-skills.sh provision the same
# section-tagged 81-persona DB + GHL funnel catalog, via the shared helper.
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
#       - persona_count == 82 (DEP-6 STAGED: hunt-thomas-pragmatic-programmer added
#         to the blueprint dirs + categories keys in the same change; the SET triad
#         holds at 82. The published ASSET is still the 81-persona v2.3.0 base while
#         asset_rebuild_required=true — see base_tag/base_sha256/base_asset_url.)
#       - chunk_count == 1161 (still the v2.3.0 base asset; the +1 delta is embedded
#         by the operator's atomic delta publish before the next release is cut)
#       - asset_rebuild_required is false (published) OR base_tag/base_sha256/base_asset_url
#         are present and valid (pre-release: a newer tag pre-staged over a published base)
#       - section_tagged is true
#       - release_tag is one of the KNOWN_TAGS (v2.2.0 / v2.2.1 / v2.3.0)
#       - schema.columns_required contains section_number + mode
#       - the PUBLISHED asset URL (asset_url when rebuild not required; base_asset_url
#         when pre-release) ends with /<known-tag>/gemini-index.sqlite.gz
#       - the VERIFIED sha256 (sha256 when published; base_sha256 when pre-release) is
#         either the v2.2.0 or v2.2.1 real hash (not a pending placeholder)
#
#   (C) FIXTURE structural assert — open the committed fixture SQLite
#       (tests/fixtures/prebuilt-index-section-tagged.fixture.sqlite) and assert:
#       - embeddings table has section_number + mode columns
#       - at least one row with mode='coaching' and section_number=3
#       - at least one row with mode='leadership' and section_number=4
#
# Layer (D) — FULL ARTIFACT (90MB download, sha256 verify, 81-persona count) —
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

# Verified SHA256 hashes for PUBLISHED assets. v2.2.1 = the real published asset
# (backstamp + Gemini re-embed, 14-section format, 935 rows, 11 delta personas
# provider-stamped); sha confirmed against the published GitHub release asset.
KNOWN_SHAS = {
    "prebuilt-index-v2.2.0": "e1097792b0efa16a50e19dd2cd6bf61689225fcd2e019c144378939413f14177",
    "prebuilt-index-v2.2.1": "27a8cc0f9991666a43b7dd0806f286248ff03861a5ef899fa14de602a8622280",
    "prebuilt-index-v2.3.0": "6cc5f9a1b649aab64cd7d4dc2fde1d9df72b2ee244607cf1e7567358a5fa3cdf",
}
KNOWN_TAGS = {"prebuilt-index-v2.2.0", "prebuilt-index-v2.2.1", "prebuilt-index-v2.3.0"}

m = json.load(open(sys.argv[1]))
results = []

def check(label, ok, detail=""):
    if ok:
        print(f"  PASS: {label}")
        results.append(("PASS", label))
    else:
        print(f"  FAIL: {label}" + (f" ({detail})" if detail else ""))
        results.append(("FAIL", label))

# Determine whether this is a published state or a pre-release (rebuild pending) state.
# Pre-release: asset_rebuild_required=true + base_tag/base_sha256/base_asset_url present.
# Published:   asset_rebuild_required=false, release_tag/sha256/asset_url are the live values.
rebuild_pending = m.get("asset_rebuild_required") is True
base_tag   = m.get("base_tag", "")
base_sha   = m.get("base_sha256", "")
base_url   = m.get("base_asset_url", "")

# Effective live values: when pre-release use base_* (the last published asset).
live_tag = base_tag if rebuild_pending and base_tag else m.get("release_tag", "")
live_sha = base_sha if rebuild_pending and base_sha else m.get("sha256", "")
live_url = base_url if rebuild_pending and base_url else m.get("asset_url", "")

check("B1: persona_count == 82 (DEP-6 staged; asset base still 81)", m.get("persona_count") == 82,
      f"got {m.get('persona_count')}")
check("B2: chunk_count == 1161", m.get("chunk_count") == 1161,
      f"got {m.get('chunk_count')}")
check("B3: asset state valid (published or pre-release with base present)",
      (not rebuild_pending) or (bool(base_tag) and bool(base_sha) and bool(base_url)),
      f"asset_rebuild_required={rebuild_pending}, base_tag={base_tag!r}")
check("B4: section_tagged is true", m.get("section_tagged") is True,
      f"got {m.get('section_tagged')}")
check("B5: release_tag in known tags",
      m.get("release_tag") in KNOWN_TAGS,
      f"got {m.get('release_tag')}")
check("B6: schema.columns_required contains section_number",
      "section_number" in m.get("schema", {}).get("columns_required", []),
      f"got {m.get('schema', {}).get('columns_required')}")
check("B7: schema.columns_required contains mode",
      "mode" in m.get("schema", {}).get("columns_required", []),
      f"got {m.get('schema', {}).get('columns_required')}")
check("B8: live asset_url ends with a known version path",
      any(live_url.endswith(f"/{t}/gemini-index.sqlite.gz") for t in KNOWN_TAGS),
      f"got {live_url!r}")
check("B9: live sha256 is a verified hash (not a pending placeholder)",
      live_sha in KNOWN_SHAS.values(),
      f"got {live_sha!r}")
check("B10: canonical_persona_count == 82 (DEP-6 staged; asset base still 81)",
      m.get("canonical_persona_count") == 82,
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
