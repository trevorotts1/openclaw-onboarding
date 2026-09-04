#!/usr/bin/env bash
# presentation-type-contract.test.sh -- regression guard for the two-field
# presentation_type question contract (U059).
#
# This test asserts:
#   1. The two-field shape survives in deck-intake-questions.json:
#      presentation_type is order:0 with exactly the four allowed values,
#      and both recipient_name and signature_source still carry a
#      conditional_on naming presentation_type.
#   2. The derivation is total: for each of the four types,
#      derive_legacy_fields() returns all four keys with creation_mode in
#      CREATION_MODES -- non-empty and legal.  creation_mode != "" explicitly
#      asserted (that is the AF-MODE-UNSET condition).
#   3. The override holds:
#      signature + existing_content -> creation_mode == content_general,
#      signature + from_scratch     -> creation_mode == from_scratch.
#   4. The two mapping tables agree: the JSON legacy_field_mapping and the
#      Python LEGACY_FIELD_MAPPING have the identical type set with the
#      identical four derived values per type.  The JSON may carry extra
#      keys by design (_comment, requires, note per type); the test ignores
#      them and asserts only the four value keys per type.
#   5. Both consumers in build_deck.py still read what is written:
#      CREATION_MODES has exactly the three values, _chk_mode reads
#      intake.get("creation_mode"), _sp_active compares deck_type to
#      "signature_presentation", and AF-MODE-UNSET is wired at the gate.
#      Asserted by AST import, not by line-number grep.
#   6. The driver's own proof still passes: --selftest exits 0 and the
#      Test 9 / 10 / 11 strings are present.
#
# EXIT CODES: 0 all pass; 1 one or more assertions failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QUESTIONS_JSON="$ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/intake/deck-intake-questions.json"
DRIVER="$ROOT/23-ai-workforce-blueprint/scripts/deck-intake-driver.py"
BUILD_DECK="$ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py"

PY="${PYTHON:-python3}"

PASS=0; FAIL=0
ok()  { printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  [FAIL] %s\n' "$1" >&2; FAIL=$((FAIL+1)); }

echo "===================================================================="
echo " presentation-type-contract.test.sh -- U059 two-field type contract guard"
echo "===================================================================="

# --------------------------------------------------------------------
# 1. Two-field shape survives in the JSON question definitions
# --------------------------------------------------------------------
echo "--- 1. two-field shape: presentation_type + conditional sub-questions ---"
"$PY" - "$QUESTIONS_JSON" <<'PYEOF'
import json, sys

with open(sys.argv[1]) as f:
    qdata = json.load(f)

questions = qdata.get("questions", [])

# presentation_type must be order:0 with exactly the four allowed values
pt = None
for q in questions:
    if q.get("id") == "presentation_type":
        pt = q
        break
assert pt is not None, "presentation_type question not found"
assert pt.get("order") == 0, f"presentation_type order is {pt.get('order')}, expected 0"
assert pt.get("kind") == "enum", f"presentation_type kind is {pt.get('kind')}, expected enum"
assert pt.get("required") is True, f"presentation_type required is {pt.get('required')}, expected True"
allowed = pt.get("allowed_values", [])
assert set(allowed) == {"from_scratch", "content_personal", "content_general", "signature"}, \
    f"allowed_values is {allowed}"
assert pt.get("storeOn") == "PRESENTATION_TYPE", f"storeOn is {pt.get('storeOn')}"

# recipient_name must carry conditional_on pointing to presentation_type with equals="content_personal"
rn = None
ss = None
for q in questions:
    if q.get("id") == "recipient_name":
        rn = q
    if q.get("id") == "signature_source":
        ss = q

assert rn is not None, "recipient_name question not found"
co = rn.get("conditional_on")
assert co is not None, f"recipient_name missing conditional_on"
assert co.get("id") == "presentation_type", \
    f"recipient_name conditional_on.id is {co.get('id')}"
assert co.get("equals") == "content_personal", \
    f"recipient_name conditional_on.equals is {co.get('equals')}"
assert rn.get("storeOn") == "RECIPIENT_NAME", f"recipient_name storeOn is {rn.get('storeOn')}"

# signature_source must carry conditional_on pointing to presentation_type with equals="signature"
assert ss is not None, "signature_source question not found"
co2 = ss.get("conditional_on")
assert co2 is not None, f"signature_source missing conditional_on"
assert co2.get("id") == "presentation_type", \
    f"signature_source conditional_on.id is {co2.get('id')}"
assert co2.get("equals") == "signature", \
    f"signature_source conditional_on.equals is {co2.get('equals')}"
assert ss.get("storeOn") == "SIGNATURE_SOURCE", f"signature_source storeOn is {ss.get('storeOn')}"

print("OK: two-field shape intact (presentation_type order:0 + both conditionals)")
PYEOF
if [ $? -eq 0 ]; then
    ok "two-field shape: presentation_type is order:0 with 4 allowed values; recipient_name + signature_source carry conditional_on"
else
    bad "two-field shape assertion FAILED (see above)"
fi

# --------------------------------------------------------------------
# 2. Derivation is total: all four types produce legal creation_mode
# --------------------------------------------------------------------
echo "--- 2. derivation is total: derive_legacy_fields covers all 4 types ---"
"$PY" - "$DRIVER" <<'PYEOF'
import importlib.util, sys

spec = importlib.util.spec_from_file_location("deck_intake_driver", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CREATION_MODES = ("from_scratch", "content_personal", "content_general")

for t in mod.PRESENTATION_TYPES:
    r = mod.derive_legacy_fields(t)
    # Must return all four keys
    for k in ("deck_type", "creation_mode", "presentation_mode", "audience_mode", "presentation_type"):
        assert k in r, f"{t}: missing key {k}"
    assert r["creation_mode"] != "", f"{t}: creation_mode is empty (AF-MODE-UNSET would fire)"
    assert r["creation_mode"] in CREATION_MODES, \
        f"{t}: creation_mode={r['creation_mode']!r} not in {CREATION_MODES}"

print("OK: all 4 types derive legally, creation_mode never empty")
PYEOF
if [ $? -eq 0 ]; then
    ok "derivation total: all 4 types produce legal creation_mode, never empty"
else
    bad "derivation total assertion FAILED (see above)"
fi

# --------------------------------------------------------------------
# 3. Override holds for both signature_source branches
# --------------------------------------------------------------------
echo "--- 3. override: signature_source branches ---"
"$PY" - "$DRIVER" <<'PYEOF'
import importlib.util, sys

spec = importlib.util.spec_from_file_location("deck_intake_driver", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

r_existing = mod.derive_legacy_fields("signature", "existing_content")
r_scratch  = mod.derive_legacy_fields("signature", "from_scratch")

assert r_existing["creation_mode"] == "content_general", \
    f"signature+existing_content -> {r_existing['creation_mode']}, expected content_general"
assert r_scratch["creation_mode"] == "from_scratch", \
    f"signature+from_scratch -> {r_scratch['creation_mode']}, expected from_scratch"

print("OK: signature override holds (existing_content -> content_general, from_scratch -> from_scratch)")
PYEOF
if [ $? -eq 0 ]; then
    ok "override: signature+existing_content -> content_general; signature+from_scratch -> from_scratch"
else
    bad "override assertion FAILED (see above)"
fi

# --------------------------------------------------------------------
# 4. Two mapping tables agree (JSON vs Python LEGACY_FIELD_MAPPING)
# --------------------------------------------------------------------
echo "--- 4. table agreement: JSON legacy_field_mapping == Python LEGACY_FIELD_MAPPING ---"
"$PY" - "$QUESTIONS_JSON" "$DRIVER" <<'PYEOF'
import json, importlib.util, sys

# Load JSON table
j = json.loads(open(sys.argv[1]).read())
jm = j.get("legacy_field_mapping", {})

# Load Python table
spec = importlib.util.spec_from_file_location("deck_intake_driver", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
pm = mod.LEGACY_FIELD_MAPPING

# Strip JSON-only keys: _comment, and per-type requires / note (item 8 of the card:
# the JSON may carry extra keys by design -- this test asserts only the four value
# keys match, not that the JSON has no extras)
json_types = {k: v for k, v in jm.items() if not k.startswith("_")}
# Per type, keep only the four value keys
VALUE_KEYS = ("deck_type", "creation_mode", "presentation_mode", "audience_mode")
json_normalized = {}
for t, vals in json_types.items():
    json_normalized[t] = {k: vals.get(k) for k in VALUE_KEYS}

# Type sets must be identical
assert set(json_normalized.keys()) == set(pm.keys()), \
    f"type sets differ: JSON={set(json_normalized.keys())}, Python={set(pm.keys())}"

# Every type's four values must match
for t in json_normalized:
    for k in VALUE_KEYS:
        jv = json_normalized[t].get(k)
        pv = pm[t].get(k)
        assert jv == pv, f"{t}['{k}'] differs: JSON={jv!r} Python={pv!r}"

print("OK: JSON and Python legacy_field_mapping agree on all 4 types x 4 keys")
PYEOF
if [ $? -eq 0 ]; then
    ok "table agreement: JSON and Python LEGACY_FIELD_MAPPING agree on all 4 types x 4 keys"
else
    bad "table agreement assertion FAILED (see above)"
fi

# --------------------------------------------------------------------
# 5. Both consumers in build_deck.py still read what is written
# --------------------------------------------------------------------
echo "--- 5. consumers: build_deck.py symbols ---"
"$PY" - "$BUILD_DECK" <<'PYEOF'
import ast, sys

# Parse build_deck.py and inspect key symbols structurally (no line-number grep)
with open(sys.argv[1]) as f:
    tree = ast.parse(f.read())

found_creation_modes = False
found_chk_mode = False
found_sp_active = False
found_wired = False

for node in ast.walk(tree):
    # CREATION_MODES = ("from_scratch", "content_personal", "content_general")
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        t = node.targets[0]
        if isinstance(t, ast.Name) and t.id == "CREATION_MODES":
            vals = [c.value for c in node.value.elts if hasattr(c, 'value')]
            assert vals == ["from_scratch", "content_personal", "content_general"], \
                f"CREATION_MODES = {vals}"
            found_creation_modes = True

    # _chk_mode reads intake.get("creation_mode")
    if isinstance(node, ast.FunctionDef) and node.name == "_chk_mode":
        source = ast.unparse(node)
        # Assert it reads creation_mode from intake
        assert "creation_mode" in source and "intake" in source, \
            "_chk_mode does not read creation_mode from intake"
        found_chk_mode = True

    # _sp_active compares deck_type to "signature_presentation"
    if isinstance(node, ast.FunctionDef) and node.name == "_sp_active":
        source = ast.unparse(node)
        assert "signature_presentation" in source and "deck_type" in source, \
            "_sp_active does not compare deck_type to signature_presentation"
        found_sp_active = True

    # AF-MODE-UNSET is wired at a gate
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and "AF-MODE-UNSET" in node.value:
        found_wired = True

assert found_creation_modes, "CREATION_MODES not found in build_deck.py"
assert found_chk_mode, "_chk_mode not found in build_deck.py"
assert found_sp_active, "_sp_active not found in build_deck.py"
assert found_wired, "AF-MODE-UNSET string not found in build_deck.py"

print("OK: CREATION_MODES has 3 members, _chk_mode reads creation_mode, _sp_active reads deck_type, AF-MODE-UNSET wired")
PYEOF
if [ $? -eq 0 ]; then
    ok "consumers: CREATION_MODES=3, _chk_mode reads creation_mode, _sp_active reads deck_type, AF-MODE-UNSET wired"
else
    bad "consumers assertion FAILED (see above)"
fi

# --------------------------------------------------------------------
# 6. Driver's own proof still passes
# --------------------------------------------------------------------
echo "--- 6. driver selftest ---"
SELFTEST_OUT="$("$PY" "$DRIVER" --selftest 2>&1)"
SELFTEST_EXIT=$?
if [ "$SELFTEST_EXIT" -eq 0 ]; then
    ok "driver selftest exit=0"
else
    bad "driver selftest exit=$SELFTEST_EXIT (expected 0)"
    printf '%s\n' "$SELFTEST_OUT" | sed 's/^/         /' >&2
fi

for test_str in \
    "Test 9 PASS" \
    "Test 10 PASS" \
    "Test 11 PASS"; do
    if printf '%s' "$SELFTEST_OUT" | grep -qF "$test_str"; then
        ok "selftest: '$test_str'"
    else
        bad "selftest: '$test_str' NOT FOUND"
    fi
done

echo "===================================================================="
echo " RESULTS: $PASS passed, $FAIL failed"
echo "===================================================================="
[ "$FAIL" -gt 0 ] && exit 1
exit 0
