#!/usr/bin/env bash
# test-populate-empty-manifest.sh — acceptance test for BU-74 (WF-092).
#
# Two cases, both run against a throwaway HOME so nothing on a real box is read
# or written:
#   1. A manifest whose `departments` list is empty exits 0 with the line
#      "no custom departments to author" (it used to exit 1 with the false
#      "Has the interview run?" error).
#   2. A custom department whose one SOP file is already on disk but below the
#      library gate's 7,168-byte floor exits 2 and prints that file's path after
#      "below the gate floor:" — the furnace skip must never read as done.
#
# Exit 0 = both cases behave as specified; 1 = a case failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/populate-sops-from-manifest.py"

# detect_platform exits 1 when it cannot find an OpenClaw install; this test
# always runs against an empty HOME, so pin the platform (documented CI override).
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"
export PYTHONDONTWRITEBYTECODE=1
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu74-empty-manifest.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# A short PATH keeps `env -i` under the command-length limit on macOS.
RUN_PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"

fail() {
  printf 'FAIL: %s\n' "$1"
  exit 1
}

run_target() {
  # run_target <home> <manifest> <outfile>
  env -i HOME="$1" PATH="$RUN_PATH" TMPDIR="${TMPDIR:-/tmp}" \
    PYTHONDONTWRITEBYTECODE=1 OPENCLAW_PLATFORM="$OPENCLAW_PLATFORM" \
    python3 -B "$TARGET" --manifest "$2" >"$3" 2>&1
}

# ── Case 1: empty departments list → exit 0 ────────────────────────────────
HOME1="$WORK/home1"
mkdir -p "$HOME1/.openclaw"
cat > "$WORK/manifest-empty.json" <<'JSON'
{
  "version": "1.0",
  "company": "Empty Co",
  "departments": [],
  "sub_agent_instructions": "no departments",
  "boundary_gate": {"canonical_refused": [], "custom_queued": [], "gate_available": true}
}
JSON
run_target "$HOME1" "$WORK/manifest-empty.json" "$WORK/case1.out"
rc1=$?
[ "$rc1" -eq 0 ] || fail "empty-departments manifest exited $rc1, expected 0"
python3 - "$WORK/case1.out" <<'PY' || exit 1
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
if "no custom departments to author" not in text:
    print("FAIL: expected line 'no custom departments to author' was not printed")
    sys.exit(1)
print("PASS: empty manifest exits 0 with the no-custom-departments line")
PY
[ $? -eq 0 ] || exit 1

# ── Case 2: one 300-byte SOP file below the gate floor → exit 2 ────────────
HOME2="$WORK/home2"
mkdir -p "$HOME2/.openclaw"
# A configured default model so populate gets past model resolution (it never
# spawns here — the dept is skipped as already authored).
cat > "$HOME2/.openclaw/openclaw.json" <<'JSON'
{"agents": {"defaults": {"model": "test/model-from-fixture"}}}
JSON

DEPT="$WORK/deptcustom"
ROLE="$DEPT/role1"
mkdir -p "$ROLE"
python3 - "$ROLE/how-to.md" <<'PY' || exit 1
import sys
# Exactly 300 bytes: above SOP_SUBSTANCE_MIN (256) so the furnace guard skips it,
# below SOP_GATE_FLOOR_BYTES (7168) so it must be re-queued. No placeholder markers.
body = ("Custom department procedure text. " * 9)[:300]
assert len(body.encode("utf-8")) == 300, len(body.encode("utf-8"))
open(sys.argv[1], "w", encoding="utf-8").write(body)
PY

python3 - "$WORK/manifest-below-floor.json" "$DEPT" "$ROLE" <<'PY' || exit 1
import json, sys
manifest_path, dept, role = sys.argv[1:4]
json.dump({
    "version": "1.0",
    "company": "Custom Co",
    "departments": [{
        "dept_id": "deptcustom",
        "dept_name": "Custom",
        "dept_head": "Head",
        "dept_dir": dept,
        "company_name": "Custom Co",
        "industry": "test",
        "sop_files": [{"role_folder": "role1", "sop_file": "how-to.md", "role_dir": role}],
    }],
    "sub_agent_instructions": "fixture instructions for {DEPT_NAME}",
    "boundary_gate": {"canonical_refused": [], "custom_queued": ["deptcustom"], "gate_available": True},
}, open(manifest_path, "w"), indent=2)
PY

run_target "$HOME2" "$WORK/manifest-below-floor.json" "$WORK/case2.out"
rc2=$?
[ "$rc2" -eq 2 ] || fail "below-floor manifest exited $rc2, expected 2"
python3 - "$WORK/case2.out" "$ROLE/how-to.md" <<'PY' || exit 1
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
path = sys.argv[2]
if path not in text:
    print(f"FAIL: below-floor path was not printed: {path}")
    sys.exit(1)
if "below the gate floor" not in text:
    print("FAIL: expected line 'below the gate floor' was not printed")
    sys.exit(1)
print("PASS: below-floor SOP exits 2 and its path is printed")
PY
[ $? -eq 0 ] || exit 1

printf 'test-populate-empty-manifest: PASS\n'
exit 0
