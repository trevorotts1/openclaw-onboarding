#!/usr/bin/env bash
# test-company-config-identity-survives.sh — regression guard for WF-070.
#
# THE BUG: write_company_config_json() rebuilt company-config.json from scratch
# and wrote it with a bare open(), so any rebuild dropped the recorded company
# id (and the pinned slug). The next resolve_company_paths() then refused the
# company as foreign, and the build could no longer touch its own folder.
#
# WHAT THIS TEST PROVES
#   C1. A write on a config that carries companyId keeps companyId, keeps the
#       recorded slug, and a second resolve_company_paths() returns cleanly.
#   C2. A company whose slug is the pinned slug keeps that slug after the write
#       and the second resolve returns cleanly.
#
# BASELINE: against the unchanged function both cases fail at the second
# resolve — the rebuilt config carries no id key at all, so the resolver raises
# "canonical ownership missing". Run this file on the unchanged builder first
# and it must fail there.
#
# Exit 0 = all cases pass; non-zero = a case failed.
set -uo pipefail

REAL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILDER="$REAL_SCRIPT_DIR/build-workforce.py"
WORK_ROOT="$(cd "$REAL_SCRIPT_DIR/.." && pwd)"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

if [ ! -f "$BUILDER" ]; then
  echo "ABORT: build-workforce.py not found at $BUILDER" >&2
  exit 1
fi

# Fixtures live inside the worktree; nothing is written outside it.
TMP="$(mktemp -d "$WORK_ROOT/.test-company-config-identity.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home" "$TMP/workspace" "$TMP/runtime" "$TMP/master"

DRIVER="$TMP/driver.py"
cat > "$DRIVER" <<'PY'
import importlib.util, json, sys
from pathlib import Path

builder, state_path, company_dir, expected_id, expected_slug = sys.argv[1:6]
verdict = {"ok": False, "stage": "import"}
try:
    spec = importlib.util.spec_from_file_location("real_builder", builder)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    verdict["stage"] = "first_resolve"
    module.resolve_company_paths("Acme")

    verdict["stage"] = "write"
    module.write_company_config_json("Acme", "coaching", {},
                                     full_config={}, selected_departments={})

    verdict["stage"] = "second_resolve"
    resolved_dir, _ = module.resolve_company_paths("Acme")

    cfg = json.loads((Path(company_dir) / "company-config.json").read_text())
    verdict["companyId"] = cfg.get("companyId")
    verdict["slug"] = cfg.get("slug")
    verdict["created"] = cfg.get("created")
    verdict["resolved"] = resolved_dir == str(Path(company_dir).resolve())
    verdict["ok"] = (
        cfg.get("companyId") == expected_id
        and cfg.get("slug") == expected_slug
        and verdict["resolved"]
    )
except Exception as exc:
    verdict["error"] = "%s: %s" % (type(exc).__name__, exc)

print(json.dumps(verdict))
sys.exit(0 if verdict["ok"] else 1)
PY

# run_case <case_dir> <state_json> <config_json> <expected_id> <expected_slug>
run_case() {
  local case_dir="$1" state_json="$2" config_json="$3" want_id="$4" want_slug="$5"
  mkdir -p "$case_dir/company"
  printf '%s' "$state_json" > "$case_dir/state.json"
  printf '%s' "$config_json" > "$case_dir/company/company-config.json"
  env -i HOME="$TMP/home" PATH="$PATH" PYTHONDONTWRITEBYTECODE=1 \
      OPENCLAW_WORKSPACE_ROOT="$TMP/workspace" \
      OPENCLAW_ROOT="$TMP/runtime" \
      MASTER_FILES_DIR="$TMP/master" \
      WORKFORCE_BUILD_STATE_FILE="$case_dir/state.json" \
      python3 -B "$DRIVER" "$BUILDER" "$case_dir/state.json" \
      "$case_dir/company" "$want_id" "$want_slug" 2>"$case_dir/stderr.txt"
}

echo ""
echo "test-company-config-identity-survives.sh — WF-070 identity regression guard"
echo "==========================================================================="

# ---------------------------------------------------------------------------
# C1: companyId and the recorded slug survive the write.
# ---------------------------------------------------------------------------
echo ""
echo "C1: a write keeps companyId and slug; second resolve returns"

C1="$TMP/c1"
C1_OUT="$(run_case "$C1" \
  '{"companyRoot":"'"$C1"'/company","companyId":"c-1","companySlug":"acme","interviewComplete":true}' \
  '{"companyId":"c-1","companySlug":"acme","companyName":"Acme","name":"Acme","slug":"acme"}' \
  "c-1" "acme")"
C1_RC=$?
C1_KIND="$(printf '%s' "$C1_OUT" | python3 -B -c 'import json,sys
try: print(json.loads(sys.stdin.read()).get("stage",""))
except Exception: print("no-verdict")')"

if [ "$C1_RC" -eq 0 ]; then
  ok "C1 second resolve returned; companyId and slug unchanged"
elif [ "$C1_KIND" = "second_resolve" ]; then
  bad "C1 second resolve raised (identity lost by the write): $(cat "$C1/stderr.txt" | tail -2)"
else
  bad "C1 failed at stage '$C1_KIND' (rc=$C1_RC): $C1_OUT"
fi

# ---------------------------------------------------------------------------
# C2: a pinned slug is kept verbatim when the display name differs.
# ---------------------------------------------------------------------------
echo ""
echo "C2: pinned slug 'acme-001' survives a write for display name 'Acme'"

C2="$TMP/c2"
C2_OUT="$(run_case "$C2" \
  '{"companyRoot":"'"$C2"'/company","companyId":"c-1","companySlug":"acme-001","interviewComplete":true}' \
  '{"companyId":"c-1","companySlug":"acme-001","slug":"acme-001","name":"Acme"}' \
  "c-1" "acme-001")"
C2_RC=$?
C2_KIND="$(printf '%s' "$C2_OUT" | python3 -B -c 'import json,sys
try: print(json.loads(sys.stdin.read()).get("stage",""))
except Exception: print("no-verdict")')"

if [ "$C2_RC" -eq 0 ]; then
  ok "C2 second resolve returned; slug still acme-001"
elif [ "$C2_KIND" = "second_resolve" ]; then
  bad "C2 second resolve raised (slug or identity lost): $(cat "$C2/stderr.txt" | tail -2)"
else
  bad "C2 failed at stage '$C2_KIND' (rc=$C2_RC): $C2_OUT"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==========================================================================="
echo "Results: $PASS passed, $FAIL failed"
echo ""
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
