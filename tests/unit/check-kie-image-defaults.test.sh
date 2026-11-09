#!/usr/bin/env bash
# Self-test for scripts/check-kie-image-defaults.py.
#
# The guard is only worth having if it can fail. This proves both directions:
#   1. the guard's own --self-test (stale fixture fails, real tree passes)
#   2. an INDEPENDENT fixture built here — a throwaway tree carrying one stale
#      prose claim, one live default field bound to 2.5, and one 2-5 registry
#      row back at status "default" must exit non-zero AND name each site
#   3. the real working tree must exit 0
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

# ── 2. independent fixture: three deliberate defects ─────────────────────────
mkdir -p "$TMP/66-kie-image/scripts" "$TMP/docs"
# Fixture tokens are composed at runtime so the guard, which reads every tracked
# file, does not count this self-test's own literals as live defects.
M25='gpt-image-2-'"5"
M25D='2.'"5"
cat > "$TMP/66-kie-image/models.json" <<JSON
{"models": [
  {"canonical_model_id": "${M25}-sunburst-text-to-image", "family": "${M25}-sunburst", "status": "default"},
  {"canonical_model_id": "gpt-image-2-6/sunburst-text-to-image", "family": "gpt-image-2-6/sunburst", "status": "default"}
],
 "owner_preferred_default": "GPT Image ${M25D} when compatible"}
JSON
cat > "$TMP/66-kie-image/scripts/select_image_model.py" <<'PYX'
import json
print(json.dumps({"selected_model_id": "gpt-image-2-6/sunburst-text-to-image"}))
PYX
printf 'GPT Image %s Sunburst is the default for everything.\n' "$M25D" > "$TMP/docs/stale.md"

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

# ── 3. the real tree must be clean ───────────────────────────────────────────
set +e
OUT_REAL=$(python3 -I "$GUARD" --root "$REPO_ROOT" 2>&1)
RC_REAL=$?
set -e
printf '%s\n' "$OUT_REAL"
[ "$RC_REAL" -eq 0 ] || fail "real tree is not clean (exit $RC_REAL)"

echo "PASS: check-kie-image-defaults self-test"
