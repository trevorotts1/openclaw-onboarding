#!/usr/bin/env bash
# Self-test for scripts/check-kie-image-defaults.py.
#
# The guard is only worth having if it can fail. This proves both directions:
#   1. the guard's own --self-test (stale fixture fails, real tree passes)
#   2. an INDEPENDENT fixture built here — a throwaway tree carrying one stale
#      prose claim, one live default field bound to 2.5, one 2-5 registry
#      row back at status "default", one 2.6 default row advertising a ratio
#      the 2.6 route does not serve, and one BARE 2.5 default claim with no
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

# ── 2. independent fixture: five deliberate defects ──────────────────────────
mkdir -p "$TMP/66-kie-image/scripts" "$TMP/docs"
# Fixture tokens are composed at runtime so the guard, which reads every tracked
# file, does not count this self-test's own literals as live defects.
M25='gpt-image-2-'"5"
M25D='2.'"5"
cat > "$TMP/66-kie-image/models.json" <<JSON
{"models": [
  {"canonical_model_id": "${M25}-sunburst-text-to-image", "family": "${M25}-sunburst", "status": "default"},
  {"canonical_model_id": "gpt-image-2-6/sunburst-text-to-image", "family": "gpt-image-2-6/sunburst", "status": "default",
   "aspect_ratios": ["auto", "1:1", "3:2", "2:3", "16:9", "9:16", "4:3", "3:4", "21:9", "27:16", "16:27", "9:8", "3:1"]}
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
grep -q "D_ratio=[1-9]" <<< "$OUT" || fail "D_ratio stayed zero on a 2.6 row claiming 3:1"
grep -q "RATIO .*3:1" <<< "$OUT" || fail "D_ratio did not name the ratio the 2.6 route does not serve"
grep -q "D_prose_bare=[1-9]" <<< "$OUT" || fail "D_prose_bare stayed zero on a bare 2.5 default claim"
grep -q "BARE .*docs/bare.md" <<< "$OUT" || fail "D_prose_bare did not name docs/bare.md"
if grep -q "docs/decoy.md" <<< "$OUT"; then fail "D_prose_bare over-reached onto a non GPT-Image version number"; fi

# ── 4. a pristine export of the committed tree must be clean ────────────────
# `git archive HEAD` is the committed base with no working-tree edits: the same
# content the gate must pass on the clean branch it is built from.
mkdir -p "$TMP/clean"
git -C "$REPO_ROOT" archive HEAD | tar -x -C "$TMP/clean"
set +e
OUT_CLEAN=$(python3 -I "$GUARD" --root "$TMP/clean" 2>&1)
RC_CLEAN=$?
set -e
printf '%s\n' "$OUT_CLEAN"
[ "$RC_CLEAN" -eq 0 ] || fail "clean committed tree is not clean (exit $RC_CLEAN)"
grep -q "DEFECTS=0" <<< "$OUT_CLEAN" || fail "clean committed tree did not report DEFECTS=0"
grep -q "D_ratio=0 .*D_prose_bare=0" <<< "$OUT_CLEAN" || fail "new axes are not zero on the clean tree"

# ── 5. the real working tree must be clean ──────────────────────────────────
set +e
OUT_REAL=$(python3 -I "$GUARD" --root "$REPO_ROOT" 2>&1)
RC_REAL=$?
set -e
printf '%s\n' "$OUT_REAL"
[ "$RC_REAL" -eq 0 ] || fail "real tree is not clean (exit $RC_REAL)"

echo "PASS: check-kie-image-defaults self-test"
