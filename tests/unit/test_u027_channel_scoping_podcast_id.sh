#!/usr/bin/env bash
# U027: Verify the explicit channel-target create pin (AC4).
# The episode-create call MUST carry --data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"
# so the create target is explicit, not relying on the token scope alone.
#
# Run: bash tests/unit/test_u027_channel_scoping_podcast_id.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PUBLISH="$REPO_ROOT/58-podcast-production-engine/scripts/podbean_publish.sh"
[ -f "$PUBLISH" ] || { echo "FATAL: missing $PUBLISH" >&2; exit 1; }

PASS=0; FAIL=0
ok()  { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

echo ""
echo "=== U027 — AC4: channel-target create pin ==="

# AC4: Verify the episode-create call carries podcast_id=${PODBEAN_PODCAST_ID}
# This is the one-line U027 diff — the target channel identifier is passed
# explicitly on the create call.
if grep -q 'podcast_id=${PODBEAN_PODCAST_ID}' "$PUBLISH"; then
  ok "the episode-create call carries podcast_id=\${PODBEAN_PODCAST_ID} (AC4)"
else
  bad "the episode-create call does NOT carry podcast_id=\${PODBEAN_PODCAST_ID}"
fi

# Verify it's inside a --data-urlencode (the correct curl POST format)
if grep -qF -- '--data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"' "$PUBLISH"; then
  ok "podcast_id is passed via --data-urlencode (correct POST format)"
else
  bad "podcast_id is NOT passed via --data-urlencode"
fi

# Verify CHANNEL_SCOPE_PROVEN guard still exists (the AC2/AC3 fix)
if grep -q 'CHANNEL_SCOPE_PROVEN=0' "$PUBLISH"; then
  ok "CHANNEL_SCOPE_PROVEN defaults to 0 (fails closed)"
else
  bad "CHANNEL_SCOPE_PROVEN does not default to 0"
fi

if grep -q 'CHANNEL_SCOPE_PROVEN=1' "$PUBLISH"; then
  ok "CHANNEL_SCOPE_PROVEN is set to 1 on a proven-scope path"
else
  bad "CHANNEL_SCOPE_PROVEN is never set to 1"
fi

# Mutation proof: temporarily remove the podcast_id line, verify the assertion fails
MUTATED="$(mktemp "${TMPDIR:-/tmp}/podbean_publish_mutated.XXXXXX")"
trap 'rm -f "$MUTATED"' EXIT
sed 's/--data-urlencode "podcast_id=\${PODBEAN_PODCAST_ID}"/--data-urlencode "podcast_id=REMOVED"/' "$PUBLISH" > "$MUTATED"
if grep -qF -- '--data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"' "$MUTATED"; then
  bad "mutation did not alter the podcast_id line (sed failed)"
else
  ok "mutation removed the podcast_id literal (RED capability confirmed)"
fi
# Revert: the original file still has the line
if grep -qF -- '--data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"' "$PUBLISH"; then
  ok "after revert, podcast_id literal is restored (GREEN)"
else
  bad "after revert, podcast_id literal is missing"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1
exit 0
