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
#   4. A POISONED entry (role folder that does not exist on disk) is reported
#      loudly on stderr WITHOUT crashing the drain and WITHOUT being removed
#      from the queue — and, since 2026-07-21, the run is recorded as
#      CONTRACT-FAILED (rc 3) rather than silently succeeding.
#   5. Dry-run (no --apply) touches NO files and leaves the queue unchanged.
#   6. A corrupt queue JSON file does not crash the script (rc 0, WARN).
#
# ─────────────────────────────────────────────────────────────────────────────
# 2026-07-21 — THE DEPARTMENT-PATH / SILENT-SUCCESS REGRESSION (scenarios 7-10)
# ─────────────────────────────────────────────────────────────────────────────
# The role branch used to build its department path as `departments/<dept>-dept`
# unconditionally. Live boxes use the UNSUFFIXED layout `departments/<dept>` —
# which is also the layout the PRODUCER (detect-stale-artifacts.py) walks when
# it writes the queue, and the layout whose BARE dept ids it puts in queue keys.
# Every role row therefore resolved to a path that does not exist: the consumer
# logged "SKIPPED ... nothing written" for all of them and returned 0, because
# the role branch never incremented failed_inscope and remaining_inscope_stale
# counted only sop/dept rows. A repair tool that reported success on every
# department while repairing nothing.
#
# NOTE ON SCENARIOS 1/2/5: their fixture deliberately KEEPS the "-dept"-suffixed
# layout. That is not an oversight — it is the back-compat column. The fix must
# handle BOTH layouts, so the suffixed fixture proves the legacy layout still
# works while scenario 7 proves the unsuffixed (real) one now works too.
#
#   7. UNSUFFIXED layout `departments/<dept>/<NN-slug>/` — the layout real boxes
#      use — is RESOLVED and the role is actually REFILLED with real library
#      content. (FAILS against the pre-fix tree: nothing is written.)
#   8. A department directory that cannot be resolved under EITHER layout FAILS
#      LOUDLY: rc 3, a "FAILED" line, DRAIN_STATUS ok=0, and a receipt whose
#      ok is false — instead of "SKIPPED" + rc 0.
#   9. HEALTHY box: refreshable roles on the unsuffixed layout drain to rc 0
#      with no false failure, and the role's sibling files (IDENTITY.md et al.)
#      are never clobbered.
#  10. Case-drifted department folder (`Account-Management` vs the manifest's
#      `account-management`) still resolves. Matters on every case-SENSITIVE
#      Linux box in the fleet, where an exact-path probe silently misses.
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

# _mk_workspace_at <workspace-dir> <department-dir-name>
# Seeds ONE role folder (STALE how-to.md) under a REAL dept/role the library
# actually ships, so try_library_fill() gets a real match -- never a fabricated
# fixture. The department DIRECTORY NAME is a parameter so the same fixture can
# be laid down in either on-disk layout.
_mk_workspace_at() {
  local ws="$1"
  local deptdir="$2"
  mkdir -p "$ws/departments/$deptdir/05-client-relationship-manager"
  cat > "$ws/departments/$deptdir/05-client-relationship-manager/how-to.md" <<'EOF'
<!-- workforce-provenance: source=role-library role-slug=client-relationship-manager dept=account-management content_sha=sha256:0000000000000000000000000000000000000000000000000000000000000000 content_version=0.0.1 instantiated=2020-01-01 generator=create_role_workspaces.py -->
# STALE PRE-UPGRADE CONTENT -- THIS IS THE OLD ROLE DOC THAT MUST BE REPLACED
This is deliberately stale test content standing in for a pre-upgrade how-to.md.
EOF
}

_mk_workspace() {
  # BACK-COMPAT column: the legacy "-dept"-suffixed layout. Deliberately kept
  # (see the header note) so the fix is proven to handle BOTH layouts.
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

# ─── Scenario 4: a POISONED entry (nonexistent role path) is reported loudly, ─
# never aborts the drain, never removed from the queue -- and is recorded as a
# CONTRACT FAILURE (rc 3), not a silent success. ────────────────────────────
#
# EXPECTATION CHANGE, 2026-07-21: this scenario previously asserted rc 0. That
# assertion is what let the department-path defect ship and survive: it froze
# "detected a gap, wrote nothing, reported success" in as the CORRECT contract.
# The drain still must not ABORT (that part is unchanged and still asserted --
# the row stays queued and later rows keep draining); what changed is that the
# RUN is now reported as failed so update-skills.sh's _D2_REFRESH_STATUS latch
# trips. This is a gate being tightened, never loosened.
_section "Scenario 4 — poisoned entry (nonexistent role folder) FAILS LOUDLY (rc 3), drain does not abort"
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
if [ "$RC4" -eq 3 ] && echo "$OUT4" | grep -q "FAILED" && [ "$POISONED_STILL_QUEUED" = "1" ]; then
  _pass "poisoned entry reported as a loud FAILED, drain exited 3 (contract failed), item left queued for next run"
else
  _fail "poisoned-entry handling wrong (rc=$RC4, expected 3; remaining=$POISONED_STILL_QUEUED): $OUT4"
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

# ─── Scenario 7: THE REGRESSION — UNSUFFIXED `departments/<dept>` layout ────
# This is the layout every live box actually uses AND the layout the producer
# (detect-stale-artifacts.py) walks. Against the pre-fix tree the consumer
# probed `departments/<dept>-dept`, found nothing, logged SKIPPED and returned
# 0. This scenario is the fail-first proof for the whole fix.
_section "Scenario 7 — UNSUFFIXED departments/<dept> layout is RESOLVED and the role is actually REFILLED"
TMP7="$(mktemp -d)"
_mk_workspace_at "$TMP7" "account-management"
cat > "$TMP7/.artifact-refresh-queue.json" <<'EOF'
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
OUT7="$(python3 "$CONSUMER" --workspace "$TMP7" --apply 2>&1)"
RC7=$?
HOWTO7="$TMP7/departments/account-management/05-client-relationship-manager/how-to.md"
if [ "$RC7" -eq 0 ] && [ -f "$HOWTO7" ] && ! grep -q "STALE PRE-UPGRADE CONTENT" "$HOWTO7" \
   && grep -q "workforce-provenance:" "$HOWTO7" && grep -q "$REAL_ROLE_INFO" "$HOWTO7"; then
  _pass "unsuffixed layout: how-to.md REFILLED with real current library content + CURRENT content_sha (rc 0)"
else
  _fail "unsuffixed layout NOT refilled -- this is the departments/<dept>-dept path defect (rc=$RC7): $OUT7"
fi
# The refill must be REAL content, not a stub: the same >=3072B floor
# try_library_fill() enforces.
BYTES7="$(wc -c < "$HOWTO7" 2>/dev/null | tr -d ' ')"
if [ -n "$BYTES7" ] && [ "$BYTES7" -ge 3072 ]; then
  _pass "refilled how-to.md is real library content ($BYTES7 bytes, >= the 3072B floor)"
else
  _fail "refilled how-to.md is only ${BYTES7:-0} bytes -- below the 3072B library floor (thin/stub output)"
fi
DRAINED7="$(python3 -c "
import json
d = json.load(open('$TMP7/.artifact-refresh-queue.json'))
print(len(d['items']))
")"
if [ "$DRAINED7" = "0" ]; then
  _pass "unsuffixed layout: the STALE role row was drained from the queue"
else
  _fail "unsuffixed layout: $DRAINED7 item(s) still queued -- the row was not drained"
fi
rm -rf "$TMP7"

# ─── Scenario 8: an UNRESOLVABLE department FAILS LOUDLY ────────────────────
_section "Scenario 8 — department directory resolvable under NEITHER layout -> loud FAILURE, never a silent skip"
TMP8="$(mktemp -d)"
# A departments/ tree that EXISTS but does not contain the queued department
# under any naming convention. The pre-fix tree logged SKIPPED here and still
# reported ok=1 / rc 0.
mkdir -p "$TMP8/departments/some-other-department"
cat > "$TMP8/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "account-management/client-relationship-manager", "kind": "role",
     "label": "Client Relationship Manager", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT8="$(python3 "$CONSUMER" --workspace "$TMP8" --apply 2>&1)"
RC8=$?
if [ "$RC8" -eq 3 ]; then
  _pass "unresolvable department -> rc 3 (contract FAILED), not a silent 0"
else
  _fail "unresolvable department returned rc=$RC8 -- expected 3; this is the silent-success defect: $OUT8"
fi
if echo "$OUT8" | grep -q "FAILED"; then
  _pass "a loud FAILED line names the unresolvable department"
else
  _fail "no FAILED line printed for an unresolvable department: $OUT8"
fi
if echo "$OUT8" | grep -q "DRAIN_STATUS ok=0"; then
  _pass "DRAIN_STATUS reports ok=0 (pipe-immune cross-check agrees with the exit code)"
else
  _fail "DRAIN_STATUS did not report ok=0: $OUT8"
fi
RECEIPT8="$(python3 -c "
import json
try:
    d = json.load(open('$TMP8/.artifact-refresh-receipt.json'))
    print(d.get('ok'), d.get('failed_inscope'), d.get('remaining_inscope_stale'))
except Exception as e:
    print('NO-RECEIPT', e)
")"
if [ "$RECEIPT8" = "False 1 1" ]; then
  _pass "receipt records ok=false, failed_inscope=1, remaining_inscope_stale=1 (role rows now counted)"
else
  _fail "receipt wrong -- got '$RECEIPT8', expected 'False 1 1'"
fi
rm -rf "$TMP8"

# ─── Scenario 9: HEALTHY box -> no false failures, nothing clobbered ────────
_section "Scenario 9 — healthy box: refreshable role drains clean (rc 0) and sibling role files are never clobbered"
TMP9="$(mktemp -d)"
_mk_workspace_at "$TMP9" "account-management"
ROLE9="$TMP9/departments/account-management/05-client-relationship-manager"
# Role-specific files that are NEVER library-templated and must survive a refresh.
printf 'ROLE-SPECIFIC IDENTITY -- MUST SURVIVE\n' > "$ROLE9/IDENTITY.md"
printf 'ROLE-SPECIFIC SOUL -- MUST SURVIVE\n'     > "$ROLE9/SOUL.md"
printf 'ROLE-SPECIFIC MEMORY -- MUST SURVIVE\n'   > "$ROLE9/MEMORY.md"
SIB_BEFORE="$(cat "$ROLE9/IDENTITY.md" "$ROLE9/SOUL.md" "$ROLE9/MEMORY.md")"
cat > "$TMP9/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "account-management/client-relationship-manager", "kind": "role",
     "label": "Client Relationship Manager", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"},
    {"key": "persona/some-persona", "kind": "persona", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"},
    {"key": "account-management/some-role", "kind": "role", "status": "MISSING",
     "built_from": null, "current": "sha256:new"}
  ]
}
EOF
OUT9="$(python3 "$CONSUMER" --workspace "$TMP9" --apply 2>&1)"
RC9=$?
SIB_AFTER="$(cat "$ROLE9/IDENTITY.md" "$ROLE9/SOUL.md" "$ROLE9/MEMORY.md")"
if [ "$RC9" -eq 0 ]; then
  _pass "healthy box drains with rc 0 -- out-of-scope persona/MISSING rows raise NO false failure"
else
  _fail "healthy box wrongly reported failure (rc=$RC9): $OUT9"
fi
if [ "$SIB_BEFORE" = "$SIB_AFTER" ]; then
  _pass "IDENTITY.md / SOUL.md / MEMORY.md byte-identical after the refresh -- nothing clobbered"
else
  _fail "role-specific sibling files were clobbered by the refresh"
fi
OUTOFSCOPE9="$(python3 -c "
import json
d = json.load(open('$TMP9/.artifact-refresh-queue.json'))
print(len(d['items']))
")"
if [ "$OUTOFSCOPE9" = "2" ]; then
  _pass "the 2 out-of-scope rows stay queued untouched; only the in-scope STALE role drained"
else
  _fail "queue left $OUTOFSCOPE9 item(s) -- expected the 2 out-of-scope rows to remain"
fi
rm -rf "$TMP9"

# ─── Scenario 10: case-drifted department folder still resolves ─────────────
# Real boxes carry folders like `Sales` while the manifest id is `sales`. An
# exact-path probe finds that on macOS (case-INSENSITIVE volume) but MISSES it
# on every case-SENSITIVE Linux box -- i.e. most of the fleet, and CI.
_section "Scenario 10 — case-drifted department folder resolves (case-sensitive filesystems)"
TMP10="$(mktemp -d)"
_mk_workspace_at "$TMP10" "Account-Management"
cat > "$TMP10/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "account-management/client-relationship-manager", "kind": "role",
     "label": "Client Relationship Manager", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT10="$(python3 "$CONSUMER" --workspace "$TMP10" --apply 2>&1)"
RC10=$?
HOWTO10="$TMP10/departments/Account-Management/05-client-relationship-manager/how-to.md"
if [ "$RC10" -eq 0 ] && [ -f "$HOWTO10" ] && ! grep -q "STALE PRE-UPGRADE CONTENT" "$HOWTO10"; then
  _pass "case-drifted department folder resolved and the role was refilled (rc 0)"
else
  _fail "case-drifted department folder not resolved (rc=$RC10): $OUT10"
fi
rm -rf "$TMP10"

# ─────────────────────────────────────────────────────────────────────────────
# 2026-08-04 — DEFECT: "no reconciliation path" for a STALE row whose
# department is legitimately RETIRED (owner-declined), scenarios 11-16.
# ─────────────────────────────────────────────────────────────────────────────
# A STALE role/sop/dept row whose department cannot be resolved on disk used
# to be an UNCONDITIONAL failure, even when the box owner explicitly,
# provenance-gated DECLINED that department (canonical_decline.py — the SAME
# single source of truth build-workforce.py and department-floor.py's floor
# gate already read). That declined department's absence is the box's
# recorded INTENT, not a gap — but the pre-fix drain could never pass again.
# Live: 5 missing department directories (billing/legal-compliance family)
# blocked a box in one wave. Mutation-proven BOTH directions below: a
# genuinely-missing (unprovenanced / not declined) row must still FAIL
# LOUDLY, exactly as before this fix — the discrimination only ADDS the
# retired outcome, it never weakens the existing one.

# _mk_decline_state <path> <declined-dept-id> [provenanced=yes]
# Writes a .workforce-build-state.json carrying a PROPERLY PROVENANCED
# decline (object form, all 4 required fields) for one department id, or an
# UNPROVENANCED bare-string "no" when provenanced=no (must still be REJECTED
# by canonical_decline.py's fail-safe default).
_mk_decline_state() {
  local path="$1" dept_id="$2" provenanced="${3:-yes}"
  if [ "$provenanced" = "yes" ]; then
    cat > "$path" <<EOF
{
  "companyName": "Fixture Co",
  "canonicalReconciliation": {
    "decisions": {
      "$dept_id": {"decision": "no", "source": "interview", "decidedAt": "2026-08-01T00:00:00Z", "decidedBy": "owner"}
    }
  }
}
EOF
  else
    cat > "$path" <<EOF
{
  "companyName": "Fixture Co",
  "canonicalReconciliation": {
    "decisions": {"$dept_id": "no"}
  }
}
EOF
  fi
}

# ─── Scenario 11: dept-branch STALE row, department PROPERLY DECLINED -> RETIRED, dropped, rc 0 ──
_section "Scenario 11 — dept-kind STALE row, department carries a PROVENANCED owner decline -> RETIRED (dropped, rc 0)"
TMP11="$(mktemp -d)"
mkdir -p "$TMP11/departments/research"   # an unrelated dept stays on disk
_mk_decline_state "$TMP11/.workforce-build-state.json" "billing-finance"
cat > "$TMP11/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "billing-finance", "kind": "dept", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT11="$(python3 "$CONSUMER" --workspace "$TMP11" --apply 2>&1)"
RC11=$?
if [ "$RC11" -eq 0 ]; then
  _pass "declined department: rc 0 (never counted against the completeness contract)"
else
  _fail "declined department wrongly failed the contract (rc=$RC11): $OUT11"
fi
if echo "$OUT11" | grep -q "RETIRED billing-finance"; then
  _pass "a loud RETIRED line names the declined department"
else
  _fail "no RETIRED line printed for a declined department: $OUT11"
fi
DRAINED11="$(python3 -c "
import json
d = json.load(open('$TMP11/.artifact-refresh-queue.json'))
print(len(d['items']))
")"
if [ "$DRAINED11" = "0" ]; then
  _pass "declined department's stale row DROPPED from the queue"
else
  _fail "declined department's row was NOT dropped ($DRAINED11 remain)"
fi
rm -rf "$TMP11"

# ─── Scenario 12: dept-branch STALE row, department NOT declined -> STILL FAILS LOUDLY (unchanged) ──
_section "Scenario 12 — dept-kind STALE row, department genuinely missing (NO decline record) -> STILL FAILS (fail-closed preserved)"
TMP12="$(mktemp -d)"
mkdir -p "$TMP12/departments/research"
# No .workforce-build-state.json at all -- the fail-safe default.
cat > "$TMP12/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "legal", "kind": "dept", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT12="$(python3 "$CONSUMER" --workspace "$TMP12" --apply 2>&1)"
RC12=$?
if [ "$RC12" -eq 3 ] && echo "$OUT12" | grep -q "FAILED UNRESOLVABLE department directory for 'legal'"; then
  _pass "genuinely-missing department (no decline evidence) still FAILS LOUDLY (rc 3) -- the fix never weakens this"
else
  _fail "genuinely-missing department did not fail as expected (rc=$RC12): $OUT12"
fi
STILLQUEUED12="$(python3 -c "
import json
d = json.load(open('$TMP12/.artifact-refresh-queue.json'))
print(len(d['items']))
")"
if [ "$STILLQUEUED12" = "1" ]; then
  _pass "genuinely-missing department's row stays queued (no reconciliation path fabricated)"
else
  _fail "genuinely-missing department's row was incorrectly dropped ($STILLQUEUED12 remain)"
fi
rm -rf "$TMP12"

# ─── Scenario 13: role-branch STALE row, department declined -> RETIRED ─────
_section "Scenario 13 — role-kind STALE row, department carries a PROVENANCED owner decline -> RETIRED (dropped, rc 0)"
TMP13="$(mktemp -d)"
mkdir -p "$TMP13/departments/research"
_mk_decline_state "$TMP13/.workforce-build-state.json" "legal"
cat > "$TMP13/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "legal-compliance/compliance-officer", "kind": "role",
     "label": "Compliance Officer", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT13="$(python3 "$CONSUMER" --workspace "$TMP13" --apply 2>&1)"
RC13=$?
if [ "$RC13" -eq 0 ] && echo "$OUT13" | grep -q "RETIRED: 'legal-compliance/compliance-officer'"; then
  _pass "role under a declined department (via 'legal-compliance' alias of canonical 'legal'): RETIRED, rc 0"
else
  _fail "role under a declined department was not retired correctly (rc=$RC13): $OUT13"
fi
rm -rf "$TMP13"

# ─── Scenario 14: sop-branch STALE row, department declined -> RETIRED ──────
# Uses a REAL library SOP source (graphics/SOP--chief-design-officer-sops.md)
# so refresh_sop()'s own "no library SOP source" pre-check (which runs BEFORE
# department resolution) does not short-circuit the scenario before it ever
# reaches the retirement-evidence check under test.
_section "Scenario 14 — sop-kind STALE row, department carries a PROVENANCED owner decline -> RETIRED (dropped, rc 0)"
TMP14="$(mktemp -d)"
mkdir -p "$TMP14/departments/research"
_mk_decline_state "$TMP14/.workforce-build-state.json" "graphics"
cat > "$TMP14/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "graphics/SOP--chief-design-officer-sops", "kind": "sop", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT14="$(python3 "$CONSUMER" --workspace "$TMP14" --apply 2>&1)"
RC14=$?
if [ "$RC14" -eq 0 ] && echo "$OUT14" | grep -q "RETIRED: 'graphics/SOP--chief-design-officer-sops'"; then
  _pass "SOP under a declined department ('graphics'): RETIRED, rc 0"
else
  _fail "SOP under a declined department was not retired correctly (rc=$RC14): $OUT14"
fi
rm -rf "$TMP14"

# ─── Scenario 15: UNPROVENANCED decline is REJECTED (fail-safe) -- still FAILS ──
_section "Scenario 15 — an UNPROVENANCED bare 'no' decline is REJECTED (fail-safe) -- department still FAILS LOUDLY"
TMP15="$(mktemp -d)"
mkdir -p "$TMP15/departments/research"
_mk_decline_state "$TMP15/.workforce-build-state.json" "billing-finance" no
cat > "$TMP15/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "billing-finance", "kind": "dept", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT15="$(python3 "$CONSUMER" --workspace "$TMP15" --apply 2>&1)"
RC15=$?
if [ "$RC15" -eq 3 ] && echo "$OUT15" | grep -q "FAILED UNRESOLVABLE department directory for 'billing-finance'"; then
  _pass "unprovenanced bare 'no' decline is REJECTED -- fail-safe to the larger floor preserved, still FAILS LOUDLY"
else
  _fail "unprovenanced decline was incorrectly honored as retirement (rc=$RC15): $OUT15"
fi
rm -rf "$TMP15"

# ─── Scenario 16: a role MISSING from an EXISTING department is UNCHANGED -- ─
# still fails loudly even when the box has SOME (unrelated) decline record.
# This is the "should exist and is unexpectedly missing" branch of the fix's
# own stated distinction -- no per-role decline concept exists in this repo,
# so this must NEVER be treated as retired.
_section "Scenario 16 — role folder missing from an EXISTING (non-declined) department -- UNCHANGED, still fails loudly"
TMP16="$(mktemp -d)"
_mk_workspace_at "$TMP16" "research"   # the department exists...
rm -rf "$TMP16/departments/research/05-client-relationship-manager"  # ...but the specific role folder is gone
mkdir -p "$TMP16/departments/research/01-other-role"
_mk_decline_state "$TMP16/.workforce-build-state.json" "billing-finance"  # unrelated decline present
cat > "$TMP16/.artifact-refresh-queue.json" <<'EOF'
{
  "summary": {"current": 0, "stale": 1, "missing": 0, "orphan": 0, "untracked": 0},
  "items": [
    {"key": "research/qc-specialist---research", "kind": "role",
     "label": "QC Specialist", "status": "STALE",
     "built_from": "sha256:old", "current": "sha256:new"}
  ]
}
EOF
OUT16="$(python3 "$CONSUMER" --workspace "$TMP16" --apply 2>&1)"
RC16=$?
if [ "$RC16" -eq 3 ] && echo "$OUT16" | grep -q "no EXISTING role folder for 'research/qc-specialist---research'"; then
  _pass "role missing from an existing, non-declined department still FAILS LOUDLY -- unrelated decline never leaks in"
else
  _fail "role-within-existing-department case regressed (rc=$RC16): $OUT16"
fi
rm -rf "$TMP16"

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
