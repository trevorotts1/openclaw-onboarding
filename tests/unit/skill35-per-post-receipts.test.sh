#!/usr/bin/env bash
# tests/unit/skill35-per-post-receipts.test.sh
#
# REGRESSION GUARD — Skill 35 U128: per-post immutable receipts + read-back.
#
# THE FALSE PASS THIS CLOSES. verify_receipts() in run-publishing-cycle.sh
# parsed three counters (connected_accounts / planned_posts / created_posts)
# but never inspected the posts array. A receipt declaring created_posts=N with
# an EMPTY posts array passed — the pipeline could announce success without a
# single post existing, and the audit trail recorded a compliant publish.
#
# The fix requires, whenever posts were actually created:
#   - a 'posts' array whose length matches created_posts,
#   - each post carrying a non-empty remote post_id and url (immutable receipt),
#   - at least one post carrying a read-back record (readback.id == post_id)
#     proving it was read back from the remote platform.
# A genuine no-op cycle (nothing planned, nothing created) is still a clean pass.
#
# WHAT THIS FILE PROVES (hermetic; fixtures in a tempdir, no box touched):
#   T1  a receipt with per-post receipts + read-back -> exit 0
#   T2  created>0 with an EMPTY posts array -> exit 6 (the core defect)
#   T3  a post missing post_id -> exit 6
#   T4  a post missing url -> exit 6
#   T5  posts present but NO read-back record -> exit 6
#   T6  read-back id that does not match post_id -> exit 6
#   T7  a legitimate no-op cycle (created=0, planned=0) -> exit 0 (anti-false-positive)
#   MUTATION: drop the posts-array presence check -> the empty-posts receipt
#             passes again (RED); revert -> it fails again (GREEN).
#
# Exit 0 = pass.  Exit 1 = a check regressed or the tripwire went blind.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/35-social-media-planner/scripts/run-publishing-cycle.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"
mkdir -p "$HOME"

# run_verify <receipts.json> -> echoes nothing; returns the script's exit code.
run_verify() {
  bash "$SCRIPT" --verify-receipts "$1" >/dev/null 2>&1
  echo $?
}

write_receipt() {  # write_receipt <file> <json>
  printf '%s' "$2" > "$1"
}

echo "--- T1: per-post receipts + read-back -> exit 0 ---"
write_receipt "$TMP/t1.json" '{
  "connected_accounts": 2, "planned_posts": 2, "created_posts": 2,
  "posts": [
    {"platform": "linkedin", "post_id": "li-123", "url": "https://linkedin.com/posts/li-123", "tier": 1, "readback": {"id": "li-123"}},
    {"platform": "medium", "post_id": "md-456", "url": "https://medium.com/p/md-456", "tier": 1, "readback": {"id": "md-456"}}
  ]
}'
rc="$(run_verify "$TMP/t1.json")"
[ "$rc" = "0" ] && pass "T1: a fully-receipted publish passes (exit 0)" \
  || fail "T1: a fully-receipted publish returned exit $rc (expected 0)"

echo "--- T2: created>0 with an EMPTY posts array -> exit 6 (the core defect) ---"
write_receipt "$TMP/t2.json" '{
  "connected_accounts": 2, "planned_posts": 2, "created_posts": 2,
  "posts": []
}'
rc="$(run_verify "$TMP/t2.json")"
[ "$rc" = "6" ] && pass "T2: an empty posts array with created=2 is rejected (exit 6)" \
  || fail "T2: an empty posts array returned exit $rc (expected 6) — the defect is live"

echo "--- T3: a post missing post_id -> exit 6 ---"
write_receipt "$TMP/t3.json" '{
  "connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
  "posts": [{"platform": "x", "post_id": "", "url": "https://x.com/i/status/1", "readback": {"id": ""}}]
}'
rc="$(run_verify "$TMP/t3.json")"
[ "$rc" = "6" ] && pass "T3: a post with no post_id is rejected (exit 6)" \
  || fail "T3: a post with no post_id returned exit $rc (expected 6)"

echo "--- T4: a post missing url -> exit 6 ---"
write_receipt "$TMP/t4.json" '{
  "connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
  "posts": [{"platform": "x", "post_id": "x-1", "url": "", "readback": {"id": "x-1"}}]
}'
rc="$(run_verify "$TMP/t4.json")"
[ "$rc" = "6" ] && pass "T4: a post with no url is rejected (exit 6)" \
  || fail "T4: a post with no url returned exit $rc (expected 6)"

echo "--- T5: posts present but NO read-back record -> exit 6 ---"
write_receipt "$TMP/t5.json" '{
  "connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
  "posts": [{"platform": "x", "post_id": "x-1", "url": "https://x.com/i/status/1"}]
}'
rc="$(run_verify "$TMP/t5.json")"
[ "$rc" = "6" ] && pass "T5: posts with no read-back are rejected (exit 6)" \
  || fail "T5: posts with no read-back returned exit $rc (expected 6)"

echo "--- T6: read-back id that does not match post_id -> exit 6 ---"
write_receipt "$TMP/t6.json" '{
  "connected_accounts": 1, "planned_posts": 1, "created_posts": 1,
  "posts": [{"platform": "x", "post_id": "x-1", "url": "https://x.com/i/status/1", "readback": {"id": "DIFFERENT"}}]
}'
rc="$(run_verify "$TMP/t6.json")"
[ "$rc" = "6" ] && pass "T6: a read-back whose id != post_id is rejected (exit 6)" \
  || fail "T6: a mismatched read-back returned exit $rc (expected 6)"

echo "--- T7: a legitimate no-op cycle (created=0, planned=0) -> exit 0 ---"
write_receipt "$TMP/t7.json" '{
  "connected_accounts": 0, "planned_posts": 0, "created_posts": 0,
  "posts": []
}'
rc="$(run_verify "$TMP/t7.json")"
[ "$rc" = "0" ] && pass "T7: a genuine no-op cycle still passes (exit 0, anti-false-positive)" \
  || fail "T7: a genuine no-op cycle returned exit $rc (expected 0)"

echo "--- MUTATION: disable the per-post receipt inspection entirely ---"
cp "$SCRIPT" "$TMP/mutated.sh"
# Reintroduce the defect: the pre-fix shape inspected only the counters and
# never the posts array. Disable the whole 'if created > 0:' per-post block so
# the empty-posts receipt passes on counters alone — exactly the pre-fix shape.
python3 - "$TMP/mutated.sh" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace(
    "if created > 0:\n    posts = d.get(\"posts\")",
    "if False:\n    posts = d.get(\"posts\")"
)
open(p, "w").write(s)
PYEOF
# With the per-post block disabled, the empty-posts receipt (T2) should now PASS
# (exit 0) — proving the assertion is discriminating.
rc="$(bash "$TMP/mutated.sh" --verify-receipts "$TMP/t2.json" >/dev/null 2>&1; echo $?)"
[ "$rc" = "0" ] && pass "MUTATION: with the per-post block disabled, the empty-posts receipt passes again (exit 0) — the assertion discriminates" \
  || fail "MUTATION: the mutated script returned exit $rc on the empty-posts receipt (expected 0) — mutation harness broken"
# And the original script still rejects it (GREEN, already proven in T2).
rc="$(run_verify "$TMP/t2.json")"
[ "$rc" = "6" ] && pass "MUTATION: the original script still rejects the empty-posts receipt (exit 6) — reverted to GREEN" \
  || fail "MUTATION: the original script returned exit $rc on the empty-posts receipt (expected 6)"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && { echo "PASS: Skill 35 per-post receipts are enforced"; exit 0; } \
  || { echo "FAIL: $FAIL check(s) failed"; exit 1; }
