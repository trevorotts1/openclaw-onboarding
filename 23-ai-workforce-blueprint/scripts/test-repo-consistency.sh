#!/usr/bin/env bash
# test-repo-consistency.sh — fixture tests for qc-assert-repo-consistency.py.
#
# Proves the gate is real (a green gate that never fails is worthless):
#
#   T1. CLEAN REPO PASSES        — the committed repo exits 0 (every floor
#                                  department consistent across floor / roster /
#                                  library / SOP / persona; no forbidden literals).
#   T2. MISSING ROSTER FAILS     — delete a floor dept's roster in a sandbox
#                                  copy → exit 5 (that dept can't materialize).
#   T3. UNRESOLVABLE ROLE FAILS  — add a roster role with a slug that resolves to
#                                  NO library/SOP template in a sandbox → exit 5
#                                  (a role with no SOP source).
#   T4. MISSING PERSONA-MAP FAILS — remove a floor dept's dept_to_domains entry
#                                  from build-workforce.py in a sandbox → exit 5
#                                  (the dept would fall back to ['leadership']).
#   T5. CORRUPT LIBRARY SLUG FAILS — re-introduce the \342\200\224 em-dash byte
#                                  corruption into a role-library slug + filename
#                                  in a sandbox → exit 5 (roster role no longer
#                                  resolves).
#   T6. STALE FLOOR LITERAL FAILS  — re-introduce the retired "7 universal-primary
#                                  = 29" floor framing into INSTRUCTIONS.md in a
#                                  sandbox → exit 7 (forbidden-literal guard, #10).
#   T7. LISTINGS-AS-UNIVERSAL FAILS — pitch "Listings Management" on a
#                                  universal-primary line in a sandbox → exit 7
#                                  (contextual guard, #10). The legit Real-Estate
#                                  Pack line stays clean — proven by T1.
#   T8. LATER-DEFERRAL LITERAL FAILS — re-introduce the "ask me again in 90 days"
#                                  deferral promise in a sandbox → exit 7
#                                  (forbidden-literal guard, #7 regression).
#
# Each negative test breaks exactly ONE invariant in an isolated sandbox copy so
# we know the gate bites on THAT specific drift, not on incidental noise.
#
# Exit 0 = all fixture tests pass; non-zero = a fixture test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-assert-repo-consistency.py"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

run_gate() {  # run_gate <skill-dir> [only] -> echoes rc
  # `only` (consistency|artifact) restricts the gate to one sub-gate. The
  # forbidden-literal guard runs with the consistency sub-gate, so the
  # forbidden-literal tests pass `consistency` to isolate rc=7 from the artifact
  # sub-gate's rc=6 — the lightweight sandbox has no repo-root bootstrap files, so
  # the artifact sub-gate always reports drift there and would mask the rc=7 the
  # test is actually asserting (artifact rc=6 outranks forbidden rc=7).
  local sd="$1"; local only="${2:-}"
  if [ -n "$only" ]; then
    python3 "$GATE" --skill-dir "$sd" --only "$only" >/dev/null 2>&1
  else
    python3 "$GATE" --skill-dir "$sd" >/dev/null 2>&1
  fi
  echo $?
}

# A sandbox needs BOTH the skill dir (for everything) AND a sibling
# 42-personal-assistant-library (the personal-assistant SOP source). We copy the
# skill into <tmp>/<repo>/23-ai-workforce-blueprint and symlink the PA library so
# the gate's repo-root sibling resolution works identically to the real repo.
make_sandbox() {  # make_sandbox -> echoes the sandbox skill dir
  local tmp; tmp="$(mktemp -d)"
  local sbroot="$tmp/repo"
  mkdir -p "$sbroot"
  cp -R "$SKILL_DIR" "$sbroot/23-ai-workforce-blueprint"
  # Provide the PA sibling library (copy if present, else the gate falls back to
  # Skill-23 lib for PA universal roles only — so we copy to keep PA resolvable).
  if [ -d "$REPO_ROOT/42-personal-assistant-library" ]; then
    cp -R "$REPO_ROOT/42-personal-assistant-library" "$sbroot/42-personal-assistant-library"
  fi
  # Drop any compiled pyc so the sandbox uses fresh source.
  find "$sbroot/23-ai-workforce-blueprint" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  echo "$sbroot/23-ai-workforce-blueprint"
  echo "$tmp" >> /tmp/.repo-consistency-sandboxes
}

: > /tmp/.repo-consistency-sandboxes
cleanup() {
  while IFS= read -r d; do [ -n "$d" ] && rm -rf "$d"; done < /tmp/.repo-consistency-sandboxes 2>/dev/null
  rm -f /tmp/.repo-consistency-sandboxes
}
trap cleanup EXIT

echo "=== T1: CLEAN REPO PASSES ==="
rc="$(run_gate "$SKILL_DIR")"
if [ "$rc" -eq 0 ]; then ok "clean repo exits 0 (rc=$rc)"; else bad "clean repo should exit 0, got rc=$rc"; fi

echo "=== T2: MISSING ROSTER FAILS ==="
sb="$(make_sandbox | head -1)"
rm -f "$sb/suggested-roles/marketing-suggested-roles.md"
rc="$(run_gate "$sb")"
if [ "$rc" -eq 5 ]; then ok "deleted marketing roster -> exit 5"; else bad "missing roster should exit 5, got rc=$rc"; fi

echo "=== T3: UNRESOLVABLE ROLE FAILS ==="
sb="$(make_sandbox | head -1)"
# Append a role whose explicit slug resolves to no library/SOP template.
cat >> "$sb/suggested-roles/marketing-suggested-roles.md" <<'ROLE'

### 99. Totally Fictional Nonexistent Role
**Slug:** zzz-this-role-has-no-library-template-anywhere
**What it does:** A role that exists in no library — must FAIL the gate.
ROLE
rc="$(run_gate "$sb")"
if [ "$rc" -eq 5 ]; then ok "roster role with no library/SOP template -> exit 5"; else bad "unresolvable role should exit 5, got rc=$rc"; fi

echo "=== T4: MISSING PERSONA-MAP ENTRY FAILS ==="
sb="$(make_sandbox | head -1)"
# Remove the canonical "billing-finance" key from BOTH dept_to_domains copies in
# build-workforce.py so the dept would fall back to the generic ['leadership'] pool.
python3 - "$sb/scripts/build-workforce.py" <<'PY'
import re, sys
p = sys.argv[1]
src = open(p, encoding="utf-8").read()
src = src.replace('        "billing-finance": ["finance", "operations"],\n', "")
open(p, "w", encoding="utf-8").write(src)
PY
rc="$(run_gate "$sb")"
if [ "$rc" -eq 5 ]; then ok "removed billing-finance dept_to_domains entry -> exit 5"; else bad "missing persona-map entry should exit 5, got rc=$rc"; fi

echo "=== T5: CORRUPT LIBRARY SLUG FAILS ==="
sb="$(make_sandbox | head -1)"
# Re-introduce the \342\200\224 byte corruption: rename a clean library file back
# to the corrupted form and point the index at it, so the roster role that
# resolves it via explicit slug can no longer find it.
corrupt='qc-specialist-\342\200\224-sales'
if [ -f "$sb/templates/role-library/sales/qc-specialist-sales.md" ]; then
  mv "$sb/templates/role-library/sales/qc-specialist-sales.md" \
     "$sb/templates/role-library/sales/$corrupt.md"
  python3 - "$sb/templates/role-library/_index.json" <<'PY'
import json, sys
p = sys.argv[1]
idx = json.load(open(p))
bad = 'qc-specialist-\\342\\200\\224-sales'
for r in idx.get("roles", []):
    if r.get("dept") == "sales" and r.get("slug") == "qc-specialist-sales":
        r["slug"] = bad
        r["path"] = f"templates/role-library/sales/{bad}.md"
        # Corrupt the TITLE too — the real corruption carried the escaped bytes in
        # BOTH the slug and the title, so the role-NAME fallback could not match
        # either. Without this the role still resolves via the clean title.
        r["title"] = 'QC Specialist \\342\\200\\224 Sales'
sales = idx.get("departments", {}).get("sales", {})
sales["roles"] = [bad if s == "qc-specialist-sales" else s for s in sales.get("roles", [])]
json.dump(idx, open(p, "w"), indent=2)
PY
  rc="$(run_gate "$sb")"
  if [ "$rc" -eq 5 ]; then ok "re-introduced em-dash byte corruption -> exit 5"; else bad "corrupt library slug should exit 5, got rc=$rc"; fi
else
  bad "T5 setup failed: clean qc-specialist-sales.md not present in sandbox"
fi

echo "=== T6: STALE CANONICAL-FLOOR LITERAL FAILS (Issue #10) ==="
sb="$(make_sandbox | head -1)"
# Re-introduce the retired "7 universal-primary = 29" floor framing (v2.6.1 floor
# is 22 + 6 = 28). The forbidden-literal guard must bite -> combined rc 7.
printf '\n> Canonical floor: 22 mandatory + 7 universal-primary = 29 departments.\n' \
  >> "$sb/INSTRUCTIONS.md"
rc="$(run_gate "$sb" consistency)"
if [ "$rc" -eq 7 ]; then ok "stale '7 universal-primary / =29' floor literal -> exit 7"; else bad "stale floor literal should exit 7, got rc=$rc"; fi

echo "=== T7: LISTINGS-MANAGEMENT-AS-UNIVERSAL-PRIMARY FAILS (Issue #10) ==="
sb="$(make_sandbox | head -1)"
# Pitch the industry-gated Listings Management dept as a universal-primary vertical
# (the v2.6.1-retired bug). The CONTEXTUAL guard fires only because both
# "Listings Management" and "universal-primary" are on the same line; the legit
# Real-Estate-Pack "- Listings Management" line (no universal-primary co-text) is
# untouched and T1 already proves the clean repo does NOT trip on it.
printf '\nFor EACH universal-primary vertical department (Presentations, Listings Management, Podcast) that does NOT fit, offer YES / NO / LATER.\n' \
  >> "$sb/INSTRUCTIONS.md"
rc="$(run_gate "$sb" consistency)"
if [ "$rc" -eq 7 ]; then ok "Listings Management pitched as universal-primary -> exit 7"; else bad "listings-as-universal-primary should exit 7, got rc=$rc"; fi

echo "=== T8: LATER-DEFERRAL LITERAL FAILS (Issue #7 regression) ==="
sb="$(make_sandbox | head -1)"
# LATER = build-now; the doc must never promise a 90-day defer.
printf '\n> If you say LATER, no problem — I will ask me again in 90 days.\n' \
  >> "$sb/INSTRUCTIONS.md"
rc="$(run_gate "$sb" consistency)"
if [ "$rc" -eq 7 ]; then ok "'ask me again in 90 days' deferral literal -> exit 7"; else bad "deferral literal should exit 7, got rc=$rc"; fi

echo
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL REPO-CONSISTENCY FIXTURE TESTS PASSED"
  exit 0
else
  echo "REPO-CONSISTENCY FIXTURE TEST FAILURES"
  exit 1
fi
