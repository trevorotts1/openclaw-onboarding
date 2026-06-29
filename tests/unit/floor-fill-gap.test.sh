#!/usr/bin/env bash
# tests/unit/floor-fill-gap.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance test for the v16.0.2 floor-fill materialization wiring.
#
# Before v16.0.2 the update path DETECTED missing canonical floor roles/SOPs
# (via detect-stale-artifacts.py) but never FILLED them, so every v16-updated
# box kept an incomplete floor. The fix wires floor-fill into the update path
# (migrate-existing-workforce.sh Step 2b) via two shipped scripts:
#   - make-gap-from-staleness.py : detect-stale verdict -> floor-fill gap-map
#   - floor-fill-driver.py       : idempotently materializes the missing slots
#
# This test proves, fully offline:
#   1. both scripts compile (py_compile) and migrate passes bash -n.
#   2. make-gap-from-staleness.py turns a MISSING detect-stale verdict into the
#      correct gap-map: role -> missing_roles; sop -> named-set + missing_sops
#      with ".md" appended; CURRENT / STALE / persona / dept items dropped;
#      non-named-set depts drop the missing_sops key.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
FFD="$SCRIPTS/floor-fill-driver.py"
MGS="$SCRIPTS/make-gap-from-staleness.py"
MIG="$SCRIPTS/migrate-existing-workforce.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }

# 1) compile / syntax
[ -f "$FFD" ] || fail "floor-fill-driver.py not shipped at $FFD"
[ -f "$MGS" ] || fail "make-gap-from-staleness.py not shipped at $MGS"
[ -f "$MIG" ] || fail "migrate-existing-workforce.sh not shipped at $MIG"
python3 -m py_compile "$FFD" "$MGS" || fail "py_compile failed"
bash -n "$MIG" || fail "migrate-existing-workforce.sh failed bash -n"

# 2) make-gap shape
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/verdict.json" <<'JSON'
{"items": [
  {"key": "sales/devils-advocate--sales",     "kind": "role",    "status": "MISSING"},
  {"key": "sales/closer",                      "kind": "role",    "status": "CURRENT"},
  {"key": "graphics/devils-advocate--graphics","kind": "role",    "status": "MISSING"},
  {"key": "graphics/SOP-DIU-615",              "kind": "sop",     "status": "MISSING"},
  {"key": "persona/growth-strategist",         "kind": "persona", "status": "MISSING"},
  {"key": "marketing",                         "kind": "dept",    "status": "STALE"}
]}
JSON

python3 "$MGS" "$TMP/verdict.json" --out "$TMP/gap.json" || fail "make-gap exited non-zero"

python3 - "$TMP/gap.json" <<'PY' || exit 1
import json, sys
gap = json.load(open(sys.argv[1]))
def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}\n  gap={json.dumps(gap)}", file=sys.stderr); sys.exit(1)
check(gap.get("sales", {}).get("missing_roles") == ["devils-advocate--sales"], "sales missing_roles wrong")
check("missing_sops" not in gap.get("sales", {}), "non-named-set sales should drop missing_sops key")
check(gap.get("graphics", {}).get("kind") == "named-set", "graphics should be named-set")
check(gap["graphics"]["missing_roles"] == ["devils-advocate--graphics"], "graphics missing_roles wrong")
check(gap["graphics"]["missing_sops"] == ["SOP-DIU-615.md"], "graphics missing_sops should append .md")
check("persona/growth-strategist" not in json.dumps(gap), "persona items must be dropped")
check("marketing" not in gap, "STALE / dept items must be dropped")
print("OK: make-gap-from-staleness produces the correct MISSING-only gap-map")
PY

echo "PASS: floor-fill-gap.test.sh — scripts compile + gap-map shape correct"
