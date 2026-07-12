#!/usr/bin/env bash
# tests/unit/refresh-stale-roles.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance test for P2-08 (c) step 2 — the artifact-refresh-queue CONSUMER
# (23-ai-workforce-blueprint/scripts/refresh-stale-roles.py).
#
# FAIL-FIRST PROOF (run manually before this file was added to the repo, and
# reproducible any time by temporarily removing the script):
#   $ mv 23-ai-workforce-blueprint/scripts/refresh-stale-roles.py /tmp/x.py
#   $ bash tests/unit/refresh-stale-roles.test.sh
#   -> FAILs scenario 1 (script not found) and every scenario that depends on
#      it; 0/N pass. Restoring the file makes every scenario pass again. This
#      is the "fails against the pre-fix tree, passes with the fix" proof
#      meta-rule 2.1.3 requires.
#
# What this proves, against REAL role-library content (never a fabricated
# fixture — the whole point of the consumer is that it re-copies REAL
# canonical content):
#   1. A role folder seeded with STALE how-to.md content + a queued STALE
#      entry gets its how-to.md overwritten with the CURRENT library content
#      and a provenance marker carrying the CURRENT content_sha.
#   2. The queue's STALE role item is removed after --apply (drained).
#   3. A non-role / non-STALE item (e.g. kind=="sop") is left untouched in
#      the queue — out of this consumer's scope.
#   4. A POISONED entry (role folder that does not exist on disk) is skipped
#      loudly (stderr WARN) WITHOUT crashing the drain and WITHOUT being
#      removed from the queue (rc still 0 — best-effort, never aborts).
#   5. Dry-run (no --apply) touches NO files and leaves the queue unchanged.
#   6. A corrupt queue JSON file does not crash the script (rc 0, WARN).
#
# EXIT CODES: 0 all passed, 1 one or more failed.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONSUMER="$REPO_ROOT/23-ai-workforce-blueprint/scripts/refresh-stale-roles.py"

FAIL_COUNT=0
PASS_COUNT=0
_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "Scenario 0 — the consumer script must exist and compile"
if [ -f "$CONSUMER" ]; then
  _pass "refresh-stale-roles.py shipped at $CONSUMER"
else
  _fail "refresh-stale-roles.py NOT FOUND at $CONSUMER -- this is the pre-fix tree (the P2-08 gap: a producer with no consumer)"
fi
if [ -f "$CONSUMER" ] && python3 -m py_compile "$CONSUMER" 2>/dev/null; then
  _pass "py_compile OK"
else
  [ -f "$CONSUMER" ] && _fail "py_compile FAILED"
fi

# Everything below requires the script to exist -- exit early with the
# accumulated failure(s) recorded above if it does not (mirrors floor-fill-gap
# test's early-exit pattern; still reports FAIL_COUNT>0 so the harness catches it).
if [ ! -f "$CONSUMER" ]; then
  _section "SUMMARY"
  echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
  exit 1
fi

# Ground truth pulled LIVE from the real manifest (never hardcoded/guessed --
# a future content edit must not silently desync this test from reality).
REAL_ROLE_INFO="$(python3 -c "
import json
d = json.load(open('$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json'))
for r in d['roles']:
    if r['slug'] == 'client-relationship-manager' and r['dept'] == 'account-management':
        print(r['content_sha'])
        break
")"
if [ -z "$REAL_ROLE_INFO" ]; then
  _fail "could not resolve the real content_sha for account-management/client-relationship-manager from the live manifest -- test fixture assumption broke"
  echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"; exit 1
fi
_pass "resolved live current content_sha for the test role: ${REAL_ROLE_INFO:0:22}..."

_mk_workspace() {
  # $1 = target dir. Seeds ONE role folder (STALE how-to.md) under a REAL
  # dept/role the library actually ships, so try_library_fill() gets a real
  # match -- never a fabricated fixture.
  local ws="$1"
  mkdir -p "$ws/departments/account-management-dept/05-client-relationship-manager"
  cat > "$ws/departments/account-management-dept/05-client-relationship-manager/how-to.md" <<'EOF'
<!-- workforce-provenance: source=role-library role-slug=client-relationship-manager dept=account-management content_sha=sha256:0000000000000000000000000000000000000000000000000000000000000000 content_version=0.0.1 instantiated=2020-01-01 generator=create_role_workspaces.py -->
# STALE PRE-UPGRADE CONTENT -- THIS IS THE OLD ROLE DOC THAT MUST BE REPLACED
This is deliberately stale test content standing in for a pre-upgrade how-to.md.
EOF
}

# ─── Scenario 1: a queued STALE role item gets refreshed with REAL current content ──
_section "Scenario 1 — queued STALE role item -> how-to.md refreshed with current library content + provenance"
TMP1="$(mktemp -d)"
trap 'rm -rf "$TMP1"' RETURN 2>/dev/null || true
_mk_workspace "$TMP1"
cat > "$TMP1/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "account-management/client-relationship-manager", "kind": "role",
     "label": "Client Relationship Manager", "status": "STALE",
     "built_from": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
     "current": "PLACEHOLDER"}
  ]
}
EOF
OUT1="$(python3 "$CONSUMER" --workspace "$TMP1" --apply 2>&1)"
RC1=$?
HOWTO1="$TMP1/departments/account-management-dept/05-client-relationship-manager/how-to.md"
if [ "$RC1" -eq 0 ] && [ -f "$HOWTO1" ] && ! grep -q "STALE PRE-UPGRADE CONTENT" "$HOWTO1" \
   && grep -q "workforce-provenance:" "$HOWTO1" && grep -q "$REAL_ROLE_INFO" "$HOWTO1"; then
  _pass "how-to.md overwritten with real current content, stale marker gone, provenance carries the CURRENT content_sha"
else
  _fail "refresh did not land correctly (rc=$RC1): $OUT1"
fi
if echo "$OUT1" | grep -qE "REFRESHED.*account-management/client-relationship-manager"; then
  _pass "loud REFRESHED summary line printed"
else
  _fail "no loud REFRESHED line in output: $OUT1"
fi

_section "Scenario 2 — the queue's STALE role item is DRAINED (removed) after --apply"
QUEUE_AFTER="$(python3 -c "
import json
d = json.load(open('$TMP1/.artifact-refresh-queue.json'))
print(len(d['items']))
print(d['summary'].get('stale'))
")"
ITEM_COUNT="$(echo "$QUEUE_AFTER" | sed -n '1p')"
STALE_COUNT="$(echo "$QUEUE_AFTER" | sed -n '2p')"
if [ "$ITEM_COUNT" = "0" ] && [ "$STALE_COUNT" = "0" ]; then
  _pass "queue drained: 0 items remain, summary.stale decremented to 0"
else
  _fail "queue not drained (items=$ITEM_COUNT stale=$STALE_COUNT) -- expected 0/0"
fi
rm -rf "$TMP1"

# ─── Scenario 3: non-role / non-STALE items are left untouched (out of scope) ──
_section "Scenario 3 — a kind=='sop' STALE item is left in the queue untouched"
TMP3="$(mktemp -d)"
_mk_workspace "$TMP3"
cat > "$TMP3/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "graphics/SOP--chief-design-officer-sops", "kind": "sop", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
python3 "$CONSUMER" --workspace "$TMP3" --apply >/dev/null 2>&1
SOP_ITEM_STILL_PRESENT="$(python3 -c "
import json
d = json.load(open('$TMP3/.artifact-refresh-queue.json'))
print(any(i.get('kind')=='sop' for i in d['items']))
")"
if [ "$SOP_ITEM_STILL_PRESENT" = "True" ]; then
  _pass "sop-kind item correctly left in the queue (out of this consumer's scope)"
else
  _fail "sop-kind item was incorrectly removed -- consumer overstepped its scope"
fi
rm -rf "$TMP3"

# ─── Scenario 4: a POISONED entry (nonexistent role path) is skipped loudly, ──
# never aborts the drain, never removed from the queue. ─────────────────────
_section "Scenario 4 — poisoned entry (nonexistent role folder) skipped loudly, drain does not abort"
TMP4="$(mktemp -d)"
mkdir -p "$TMP4/departments"
cat > "$TMP4/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "totally-fake-dept/nonexistent-role", "kind": "role", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT4="$(python3 "$CONSUMER" --workspace "$TMP4" --apply 2>&1)"
RC4=$?
POISONED_STILL_QUEUED="$(python3 -c "
import json
d = json.load(open('$TMP4/.artifact-refresh-queue.json'))
print(len(d['items']))
")"
if [ "$RC4" -eq 0 ] && echo "$OUT4" | grep -qi "WARN SKIPPED" && [ "$POISONED_STILL_QUEUED" = "1" ]; then
  _pass "poisoned entry skipped with a loud WARN, drain exited 0, item left queued for next run"
else
  _fail "poisoned-entry handling wrong (rc=$RC4, remaining=$POISONED_STILL_QUEUED): $OUT4"
fi
rm -rf "$TMP4"

# ─── Scenario 5: dry-run (no --apply) touches NOTHING ───────────────────────
_section "Scenario 5 — dry-run (no --apply) writes no files and leaves the queue unchanged"
TMP5="$(mktemp -d)"
_mk_workspace "$TMP5"
cat > "$TMP5/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "account-management/client-relationship-manager", "kind": "role",
     "label": "Client Relationship Manager", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
HOWTO5="$TMP5/departments/account-management-dept/05-client-relationship-manager/how-to.md"
BEFORE_HASH="$(shasum -a 256 "$HOWTO5" 2>/dev/null || sha256sum "$HOWTO5" 2>/dev/null)"
QUEUE_BEFORE="$(cat "$TMP5/.artifact-refresh-queue.json")"
python3 "$CONSUMER" --workspace "$TMP5" >/dev/null 2>&1   # no --apply
AFTER_HASH="$(shasum -a 256 "$HOWTO5" 2>/dev/null || sha256sum "$HOWTO5" 2>/dev/null)"
QUEUE_AFTER5="$(cat "$TMP5/.artifact-refresh-queue.json")"
if [ "$BEFORE_HASH" = "$AFTER_HASH" ] && [ "$QUEUE_BEFORE" = "$QUEUE_AFTER5" ]; then
  _pass "dry-run touched no files and left the queue byte-identical"
else
  _fail "dry-run mutated state -- --apply gating is broken"
fi
rm -rf "$TMP5"

# ─── Scenario 6: a corrupt queue file never crashes the script ─────────────
_section "Scenario 6 — corrupt queue JSON is handled gracefully (rc 0, WARN, no crash)"
TMP6="$(mktemp -d)"
mkdir -p "$TMP6/departments"
printf '{ this is not valid json' > "$TMP6/.artifact-refresh-queue.json"
OUT6="$(python3 "$CONSUMER" --workspace "$TMP6" --apply 2>&1)"
RC6=$?
if [ "$RC6" -eq 0 ] && echo "$OUT6" | grep -qi "corrupt\|WARN"; then
  _pass "corrupt queue file handled gracefully, rc 0, WARN printed"
else
  _fail "corrupt queue file was not handled gracefully (rc=$RC6): $OUT6"
fi
rm -rf "$TMP6"

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
