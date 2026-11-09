#!/usr/bin/env bash
# Self-test for scripts/check-kie-image-defaults.py.
#
# The guard is only worth having if it can fail. This proves both directions:
#   1. the guard's own --self-test (stale fixture fails, true-enum row passes;
#      the real-tree count it prints is informational — expected RED until #2985)
#   2. an INDEPENDENT fixture built here — a throwaway tree carrying one stale
#      prose claim, one live default field bound to 2.5, one 2-5 registry
#      row back at status "default", one 2.6 default row advertising ratios
#      the 2.6 route does not serve (27:16/16:27/9:8/8:9) while dropping a
#      served ratio (5:4), and one BARE 2.5 default claim with no
#      model prefix must exit non-zero AND name each site
#   3. the same independent fixture must NOT report the decoy — a bare 2.5
#      version outside a GPT-Image context — proving D_prose_bare does not
#      over-reach into unrelated version numbers
#   4. a pristine export of the committed tree (the clean base) must exit 0 on
#      all six axes
#   5. the real working tree must exit 0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/check-kie-image-defaults.py"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

[ -f "$GUARD" ] || fail "guard not found at $GUARD"

# ── 1. the guard's built-in self-test ────────────────────────────────────────
python3 -I "$GUARD" --self-test || fail "guard --self-test reported a failure"

# ── 2. independent fixture: defects incl. true-enum D_ratio ───────────────────
mkdir -p "$TMP/66-kie-image/scripts" "$TMP/docs" "$TMP/74-kie-live-adapter/references"
# The served set is derived at check time from the vendor registry, so the
# fixture carries a minimal registry with the TRUE vendor enum (source of
# truth: 74-kie-live-adapter/references/kie-model-registry.json,
# gpt-image-2-6/sunburst-text-to-image input_fields.aspect_ratio.enum).
cat > "$TMP/74-kie-live-adapter/references/kie-model-registry.json" <<'REGJSON'
{"models": [{"id": "gpt-image-2-6/sunburst-text-to-image",
  "input_fields": {"aspect_ratio": {"enum": ["auto", "1:1", "3:2", "2:3",
    "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "2:1", "1:2", "21:9",
    "9:21", "3:1", "1:3"]}}}]}
REGJSON
# Fixture tokens are composed at runtime so the guard, which reads every tracked
# file, does not count this self-test's own literals as live defects.
M25='gpt-image-2-'"5"
M25D='2.'"5"
cat > "$TMP/66-kie-image/models.json" <<JSON
{"models": [
  {"canonical_model_id": "${M25}-sunburst-text-to-image", "family": "${M25}-sunburst", "status": "default"},
  {"canonical_model_id": "gpt-image-2-6/sunburst-text-to-image", "family": "gpt-image-2-6/sunburst", "status": "default",
   "aspect_ratios": ["auto", "1:1", "3:2", "2:3", "16:9", "9:16", "4:3", "3:4", "21:9", "27:16", "16:27", "9:8", "3:1"]},
  {"canonical_model_id": "gpt-image-2-6/sunburst-image-to-image", "family": "gpt-image-2-6/sunburst", "status": "default",
   "aspect_ratios": ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21", "3:1", "1:3"]}
],
 "owner_preferred_default": "GPT Image ${M25D} when compatible"}
JSON
cat > "$TMP/66-kie-image/scripts/select_image_model.py" <<'PYX'
import json
print(json.dumps({"selected_model_id": "gpt-image-2-6/sunburst-text-to-image"}))
PYX
printf 'GPT Image %s Sunburst is the default for everything.\n' "$M25D" > "$TMP/docs/stale.md"
# D_prose_bare: a bare version token claiming default in a GPT-Image context,
# with no `gpt-image` prefix on the token itself.
printf 'GPT-Image route: DEFAULT (%s) for everything.\n' "$M25D" > "$TMP/docs/bare.md"
# decoy: the same bare version, but NOT in a GPT-Image context.
printf 'Python %s is the default interpreter for that build.\n' "$M25D" > "$TMP/docs/decoy.md"

set +e
OUT=$(python3 -I "$GUARD" --root "$TMP" 2>&1)
RC=$?
set -e
printf '%s\n' "$OUT"

[ "$RC" -ne 0 ] || fail "stale fixture exited 0 — the guard cannot fail"
grep -q "DEFECTS=.*[1-9]" <<< "$OUT" || fail "stale fixture reported zero defects"
grep -q "docs/stale.md" <<< "$OUT" || fail "stale fixture did not name docs/stale.md"
grep -q "owner_preferred_default" <<< "$OUT" || fail "stale fixture did not name the live default field"
grep -q "ROW .*gpt-image-2-5" <<< "$OUT" || fail "stale fixture did not name the 2-5 row"

# ── 3. the new axes must fire, and only on their own defects ─────────────────
grep -q "D_ratio=[1-9]" <<< "$OUT" || fail "D_ratio stayed zero on a 2.6 row claiming 27:16"
grep -q "RATIO .*27:16" <<< "$OUT" || fail "D_ratio did not name 27:16 as not-served"
grep -q "RATIO .*5:4" <<< "$OUT" || fail "D_ratio did not name 5:4 as served-but-missing"
# positive control: the row advertising the TRUE 16-value enum must NOT be
# reported — only the defective row names its model id in a RATIO line.
RATIO_IDS=$(grep "^  RATIO" <<< "$OUT" | grep -o "gpt-image-2-6[^ ]*" | sort -u)
echo "$RATIO_IDS" | grep -q "sunburst-text-to-image" || fail "defective t2i row was not reported"
if echo "$RATIO_IDS" | grep -q "sunburst-image-to-image"; then fail "clean i2i row (true enum) was reported as a defect"; fi
grep -q "D_prose_bare=[1-9]" <<< "$OUT" || fail "D_prose_bare stayed zero on a bare 2.5 default claim"
grep -q "BARE .*docs/bare.md" <<< "$OUT" || fail "D_prose_bare did not name docs/bare.md"
if grep -q "docs/decoy.md" <<< "$OUT"; then fail "D_prose_bare over-reached onto a non GPT-Image version number"; fi

# ── 4. a pristine export of the committed tree must show the fail-closed ────
# RED this guard exists for: `git archive HEAD` is the committed base with no
# working-tree edits, and the base 2.6 rows still carry the WRONG 13-ratio set
# (27:16/16:27/9:8/8:9 invented, 5:4/4:5/2:1/1:2/9:21/3:1/1:3 omitted).
# PR #2985 corrects 66-kie-image/models.json to the true enum; until it lands
# this gate MUST report those four as defects. Expected RED, not a regression.
mkdir -p "$TMP/clean"
git -C "$REPO_ROOT" archive HEAD | tar -x -C "$TMP/clean"
set +e
OUT_CLEAN=$(python3 -I "$GUARD" --root "$TMP/clean" 2>&1)
RC_CLEAN=$?
set -e
printf '%s\n' "$OUT_CLEAN"
[ "$RC_CLEAN" -ne 0 ] || fail "clean committed tree exited 0 — the guard cannot see the wrong 13-ratio set"
grep -q "D_ratio=[1-9]" <<< "$OUT_CLEAN" || fail "D_ratio stayed zero on the committed tree's wrong ratios"
for R in 27:16 16:27 9:8 8:9; do
  grep -q "RATIO .*$R" <<< "$OUT_CLEAN" || fail "committed tree did not report $R as a defect"
done

# ── 5. the real tree is expected RED until #2985 lands ───────────────────────
# Same wrong 13-ratio set as the committed base (see §4): expect the four
# not-served ratios named, non-zero exit, and D_prose_bare quiet.
set +e
OUT_REAL=$(python3 -I "$GUARD" --root "$REPO_ROOT" 2>&1)
RC_REAL=$?
set -e
printf '%s\n' "$OUT_REAL"
[ "$RC_REAL" -ne 0 ] || fail "real tree exited 0 — the wrong 13-ratio set should still fail"
for R in 27:16 16:27 9:8 8:9; do
  grep -q "RATIO .*$R" <<< "$OUT_REAL" || fail "real tree did not report $R as a defect"
done

echo "PASS: check-kie-image-defaults self-test"
