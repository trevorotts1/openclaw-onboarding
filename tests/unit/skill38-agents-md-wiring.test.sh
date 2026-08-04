#!/usr/bin/env bash
# tests/unit/skill38-agents-md-wiring.test.sh
# ============================================================================
# DEFECT: 38-conversational-ai-system/scripts/05-update-agents-md.sh (the
# AGENTS.md pointer-stanza rewriter -- the source of the ~24k-char win over
# the old 52KB full-corpus paste) was invoked NOWHERE in the automated update
# pipeline: not by the wiring phase, not by wire_core_updates(), not by
# obs_verify_skill. It was documented only as a MANUAL INSTALL.md step-5.
# Evidence it had not run in months on a real box: the newest
# AGENTS.md.bak-skill38-* was ~7 version bumps stale while sibling skills
# wrote fresh backups on every roll.
#
# THIS SUITE PROVES, MECHANICALLY:
#   (A) STATIC   — update-skills.sh's per-skill wiring loop calls
#       05-update-agents-md.sh for 38-conversational-ai-system, and the call
#       sits BEFORE the per-version WIRED_SENTINEL short-circuit (so it runs
#       on EVERY pass, not just once per version bump -- required for the
#       script's own "staged descent" convergence design on a box running a
#       core-file watcher).
#   (B) BEHAVIORAL — invoking the script EXACTLY the way update-skills.sh now
#       does (`AGENTS_MD=<workspace>/AGENTS.md bash 05-update-agents-md.sh`)
#       against a fixture AGENTS.md that has NEVER been touched by it
#       transitions that file from "no SKILL38 stanzas" to "current SKILL38
#       stanzas present" -- i.e. proves the exact defect scenario (a stale
#       box AGENTS.md) is what this wiring now fixes.
#   (C) IDEMPOTENT — a second pass against the now-current file is a true
#       no-op (byte-identical, no new backup) -- the property the wiring
#       relies on to be safe running unconditionally on every update pass.
#
# Exit 0 = all checks pass. Exit 1 = a regression was found.
# ============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
AG_SCRIPT="$REPO_ROOT/38-conversational-ai-system/scripts/05-update-agents-md.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

[ -f "$UPDATE_SH" ] || { echo "FATAL: $UPDATE_SH not found"; exit 2; }
[ -f "$AG_SCRIPT" ] || { echo "FATAL: $AG_SCRIPT not found"; exit 2; }

echo "=== (A) STATIC: the wiring loop actually calls 05-update-agents-md.sh ==="

# Locate the (1-indexed) line numbers of the three load-bearing anchors inside
# update-skills.sh's per-skill wiring loop.
read -r WIRE_GHL_LINE WIRE_38_LINE SENTINEL_LINE <<PYEOF
$(python3 - "$UPDATE_SH" << 'PYSCRAPE'
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8", errors="replace").readlines()
wire_ghl = wire_38 = sentinel = 0
for i, l in enumerate(lines, 1):
    if 'wire_ghl_mcp "$SKILL_NAME"' in l and wire_ghl == 0:
        wire_ghl = i
    if '05-update-agents-md.sh' in l and 'SKILL_NAME" = "38-conversational-ai-system"' in lines[max(0,i-2)] and wire_38 == 0:
        wire_38 = i
    if 'WIRED_SENTINEL="$SKILL_DIR/.wired-${ONBOARDING_VERSION}"' in l and sentinel == 0:
        sentinel = i
print(wire_ghl, wire_38, sentinel)
PYSCRAPE
)
PYEOF

if [ "${WIRE_38_LINE:-0}" -gt 0 ]; then
  pass "update-skills.sh invokes 05-update-agents-md.sh in the wiring loop (line $WIRE_38_LINE)"
else
  fail "update-skills.sh does NOT invoke 05-update-agents-md.sh anywhere in the wiring loop"
fi

if [ "${WIRE_38_LINE:-0}" -gt 0 ] && [ "${SENTINEL_LINE:-0}" -gt 0 ] && [ "$WIRE_38_LINE" -lt "$SENTINEL_LINE" ]; then
  pass "the call sits BEFORE the per-version WIRED_SENTINEL short-circuit (runs every pass, not once per version)"
else
  fail "the call is missing or sits AFTER the WIRED_SENTINEL gate (line38=$WIRE_38_LINE sentinel=$SENTINEL_LINE) — it would only fire once per version bump, breaking the corefile-watcher staged-descent design"
fi

if [ "${WIRE_GHL_LINE:-0}" -gt 0 ] && [ "${WIRE_38_LINE:-0}" -gt 0 ] && [ "$WIRE_GHL_LINE" -lt "$WIRE_38_LINE" ]; then
  pass "call ordering is sane (wire_ghl_mcp before the skill-38 AGENTS.md rewire)"
fi

# The call must scope itself to skill 38 only (never fire for any other skill).
if grep -q 'if \[ "\$SKILL_NAME" = "38-conversational-ai-system" \]' "$UPDATE_SH"; then
  pass "the call is scoped to 38-conversational-ai-system only"
else
  fail "could not find the skill-38 scoping guard around the 05-update-agents-md.sh call"
fi

# The call must pass AGENTS_MD pointed at the resolved workspace, not rely on
# the script's own hardcoded ~/clawd default (which would silently target the
# wrong file on any box with a non-default workspace).
if grep -q 'AGENTS_MD="\$WIRE_WORKSPACE_DIR/AGENTS.md" bash "\$SKILL_DIR/scripts/05-update-agents-md.sh"' "$UPDATE_SH"; then
  pass "the call passes AGENTS_MD=\$WIRE_WORKSPACE_DIR/AGENTS.md (the same resolved workspace wire_core_updates uses)"
else
  fail "the call does not explicitly point AGENTS_MD at the resolved workspace"
fi

echo ""
echo "=== (B) BEHAVIORAL: invoking it the way update-skills.sh now does fixes a stale box AGENTS.md ==="

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FIXTURE_AGENTS="$WORK/workspace/AGENTS.md"
mkdir -p "$WORK/workspace"
cat > "$FIXTURE_AGENTS" << 'EOF'
# AGENTS.md

Some pre-existing operator-authored content that must survive untouched.
EOF

# Sanity: the fixture starts with NO skill-38 stanzas (simulates a box this
# wiring has never reached — exactly the reported defect).
if grep -q "BEGIN SKILL38" "$FIXTURE_AGENTS"; then
  fail "test setup error: fixture AGENTS.md already carries SKILL38 stanzas before the first run"
else
  pass "fixture AGENTS.md starts with NO SKILL38 stanzas (simulates the reported stale-box defect)"
fi
BEFORE_BYTES="$(wc -c < "$FIXTURE_AGENTS" | tr -d ' ')"

# Invoke it EXACTLY the way the wiring loop now does.
if AGENTS_MD="$FIXTURE_AGENTS" SKILL38_MASTER_FILES_DIR="$WORK/master-files" \
     bash "$AG_SCRIPT" >"$WORK/run1.log" 2>&1; then
  pass "05-update-agents-md.sh exits 0 under the wiring invocation contract"
else
  fail "05-update-agents-md.sh exited non-zero under the wiring invocation contract (see $WORK/run1.log)"
  cat "$WORK/run1.log" | sed 's/^/      /'
fi

if grep -q "BEGIN SKILL38" "$FIXTURE_AGENTS"; then
  pass "after the wired call, the LIVE fixture AGENTS.md now carries current SKILL38 stanzas"
else
  fail "after the wired call, the fixture AGENTS.md still has NO SKILL38 stanzas — the wiring did not actually rewrite the live file"
fi

if grep -qF "Some pre-existing operator-authored content that must survive untouched." "$FIXTURE_AGENTS"; then
  pass "pre-existing operator content survives the rewrite untouched"
else
  fail "pre-existing operator content was lost/altered by the rewrite"
fi

AFTER_BYTES="$(wc -c < "$FIXTURE_AGENTS" | tr -d ' ')"
if [ "$AFTER_BYTES" -gt "$BEFORE_BYTES" ]; then
  pass "file grew from stale ($BEFORE_BYTES bytes) to current ($AFTER_BYTES bytes) — a real write happened, not a silent no-op"
else
  fail "file did not grow ($BEFORE_BYTES -> $AFTER_BYTES bytes) — the write did not land"
fi

echo ""
echo "=== (C) IDEMPOTENT: a second pass against the now-current file is a true no-op ==="

cp "$FIXTURE_AGENTS" "$WORK/after-run1.snapshot"
BACKUPS_BEFORE="$(find "$WORK/workspace" -maxdepth 1 -name 'AGENTS.md.bak-skill38-*' | wc -l | tr -d ' ')"

if AGENTS_MD="$FIXTURE_AGENTS" SKILL38_MASTER_FILES_DIR="$WORK/master-files" \
     bash "$AG_SCRIPT" >"$WORK/run2.log" 2>&1; then
  pass "second pass exits 0"
else
  fail "second pass exited non-zero (see $WORK/run2.log)"
fi

if diff -q "$WORK/after-run1.snapshot" "$FIXTURE_AGENTS" >/dev/null 2>&1; then
  pass "second pass is byte-identical to the first pass's result (true no-op)"
else
  fail "second pass changed the file — not idempotent"
fi

BACKUPS_AFTER="$(find "$WORK/workspace" -maxdepth 1 -name 'AGENTS.md.bak-skill38-*' | wc -l | tr -d ' ')"
if [ "$BACKUPS_AFTER" = "$BACKUPS_BEFORE" ]; then
  pass "no new backup was written on the no-op second pass ($BACKUPS_BEFORE unchanged)"
else
  fail "second pass wrote a new backup despite being a no-op ($BACKUPS_BEFORE -> $BACKUPS_AFTER)"
fi

grep -qi "already carries exactly the current .* stanza" "$WORK/run2.log" \
  && pass "second-pass log explicitly states the no-op reason" \
  || fail "second-pass log does not explain why nothing changed"

printf '\n=========================================\n'
printf 'SKILL-38 AGENTS.MD WIRING SUITE: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
printf '=========================================\n'
[ "$FAIL" -eq 0 ]
