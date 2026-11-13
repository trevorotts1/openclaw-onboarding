#!/usr/bin/env bash
# test-org-chart-regenerate.sh — acceptance test for BU-82 (WF-099).
#
# Runs `build-workforce.py --regenerate-org-chart-only` against a throwaway HOME
# and a scratch company, so nothing on a real box is read or written:
#   1. A build-state recording `companyRoot`, two departments and one role
#      folder in each writes ORG-CHART.md INTO the company folder, and the chart
#      names both roles (they are read from the role folders on disk).
#   2. A build-state with no `companyRoot` is refused with exit 1 and no
#      ORG-CHART.md is written anywhere.
#
# Exit 0 = both cases behave as specified; 1 = a case failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/build-workforce.py"

# detect_platform exits 1 when it cannot find an OpenClaw install; this test
# always runs against an empty HOME, so pin the platform (documented CI override).
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"
export PYTHONDONTWRITEBYTECODE=1
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu82-org-chart.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# A short PATH keeps `env -i` under the command-length limit on macOS.
RUN_PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"

fail() {
  printf 'FAIL: %s\n' "$1"
  exit 1
}

run_target() {
  # run_target <home> <state-file> <outfile>
  env -i HOME="$1" PATH="$RUN_PATH" TMPDIR="${TMPDIR:-/tmp}" \
    PYTHONDONTWRITEBYTECODE=1 OPENCLAW_PLATFORM="$OPENCLAW_PLATFORM" \
    WORKFORCE_BUILD_STATE_FILE="$2" \
    python3 -B "$TARGET" --regenerate-org-chart-only >"$3" 2>&1
}

# ── Case 1: recorded companyRoot + two role folders → ORG-CHART.md written ──
HOME1="$WORK/home1"
mkdir -p "$HOME1/.openclaw"

COMPANY="$WORK/scratch-company"
MARKETING_ROLE="$COMPANY/departments/marketing/00-marketing-head"
SALES_ROLE="$COMPANY/departments/sales/00-sales-head"
mkdir -p "$MARKETING_ROLE" "$SALES_ROLE"
printf '# Marketing Director\n\n**Role Type:** permanent\n' > "$MARKETING_ROLE/00-START-HERE.md"
printf '# Sales Director\n\n**Role Type:** on-call\n' > "$SALES_ROLE/00-START-HERE.md"

python3 - "$WORK/state1.json" "$COMPANY" <<'PY' || exit 1
import json, sys
state_path, company = sys.argv[1:3]
json.dump({
    "companySlug": "scratch-company",
    "companyRoot": company,
    "departments": [
        {"slug": "marketing", "name": "Marketing", "emoji": "", "head": "Marketing Director"},
        {"slug": "sales", "name": "Sales", "emoji": "", "head": "Sales Director"},
    ],
}, open(state_path, "w"), indent=2)
PY

run_target "$HOME1" "$WORK/state1.json" "$WORK/case1.out"
rc1=$?
[ "$rc1" -eq 0 ] || {
  cat "$WORK/case1.out" >&2
  fail "regenerate exited $rc1, expected 0"
}
[ -f "$COMPANY/ORG-CHART.md" ] || {
  cat "$WORK/case1.out" >&2
  fail "ORG-CHART.md was not written in the company folder: $COMPANY"
}
python3 - "$COMPANY/ORG-CHART.md" <<'PY' || exit 1
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
missing = [n for n in ("Marketing Director", "Sales Director") if n not in text]
if missing:
    print(f"FAIL: ORG-CHART.md does not name: {', '.join(missing)}")
    sys.exit(1)
print("PASS: ORG-CHART.md written in the company folder and names both roles")
PY
[ $? -eq 0 ] || exit 1

# ── Case 2: no companyRoot in build-state → refused, nothing written ───────
HOME2="$WORK/home2"
mkdir -p "$HOME2/.openclaw"
NO_ROOT="$WORK/no-root-company"
mkdir -p "$NO_ROOT"

python3 - "$WORK/state2.json" <<'PY' || exit 1
import json, sys
state_path = sys.argv[1]
json.dump({"companySlug": "no-root-company"}, open(state_path, "w"), indent=2)
PY

run_target "$HOME2" "$WORK/state2.json" "$WORK/case2.out"
rc2=$?
[ "$rc2" -eq 1 ] || {
  cat "$WORK/case2.out" >&2
  fail "missing companyRoot exited $rc2, expected 1"
}
[ ! -f "$NO_ROOT/ORG-CHART.md" ] || fail "ORG-CHART.md was written despite a missing companyRoot"
python3 - "$WORK/case2.out" <<'PY' || exit 1
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
if "companyRoot" not in text:
    print("FAIL: the refusal did not name the missing companyRoot")
    sys.exit(1)
print("PASS: missing companyRoot refused with exit 1")
PY
[ $? -eq 0 ] || exit 1

printf 'test-org-chart-regenerate: PASS\n'
exit 0
