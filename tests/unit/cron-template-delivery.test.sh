#!/usr/bin/env bash
# tests/unit/cron-template-delivery.test.sh
#
# CI guard for scripts/check-cron-template-delivery.py — the cron delivery-path
# lint gate.
#
# THE DEFECT THIS GUARDS AGAINST
#   A cron's output must reach the client by EXACTLY ONE path. Measured on a live
#   box: two daily client deliverables were generated in full and then silently
#   lost, and both runs reported `succeeded`. The prompts instructed the model to
#   address the message itself ("Post the full briefing to this topic (#178)",
#   "Send a short daily digest to Topic #65"), so the model built the address and
#   intermittently invented invalid targets — to:'65', telegram_topic:65, and a
#   malformed shape that resolved to @telegram (Telegram's own broadcast channel,
#   403). One template also shipped delivery_mode:'none' on a CLIENT DELIVERABLE,
#   removing the announce backstop, so a failed self-send meant total loss.
#
#   The repo-side form of the same fault is a cron registered WITH delivery
#   (--channel/--to/--announce) whose prompt ALSO self-sends: the scheduler
#   auto-delivers whatever the final turn text happens to be — routinely a
#   partial or internal status line — while the real deliverable goes out, or
#   fails to, separately. That is exactly what direct-to-agent-install.md shipped.
#
# WHY A GATE AND NOT JUST A ONE-LINE FIX
#   The literal "Topic #N" phrasing does NOT exist anywhere in this repo today
#   (verified by the gate itself scanning every shipped template). Nothing
#   structurally prevented it from being added, and nothing would have caught it.
#   This gate is the regression barrier: it fails the build the moment a template
#   names a literal target, drops its only delivery path, or doubles up.
#
# Assertion groups:
#   (1) GATE_PRESENT   -- the checker exists and compiles.
#   (2) REAL_REPO      -- the gate PASSES against the real repo tree (validated
#                         against real data, not only fixtures).
#   (3) REAL_MUTATION  -- the gate FAILS against the genuine PRE-FIX file taken
#                         from git (origin/main), proving it catches the actual
#                         defect that shipped, not a strawman.
#   (4) SYNTHETIC      -- the gate FAILS on a purpose-built fixture for EACH
#                         check, and each failure names the right check.
#   (5) NO_FALSE_POS   -- the gate PASSES on the CORRECT shapes (silent cron +
#                         self-sending prompt; delivering cron + non-sending
#                         prompt; an internal cron that is legitimately silent).
#
# Run: bash tests/unit/cron-template-delivery.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/check-cron-template-delivery.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cron-template-delivery.test.sh ==="
echo "  interpreter: ${BASH_VERSION}"
echo ""

TMP="$(mktemp -d "${TMPDIR:-/tmp}/cron-template-delivery.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# (1) GATE_PRESENT
# ---------------------------------------------------------------------------
echo "--- (1) GATE_PRESENT ---"
if [[ ! -f "$GATE" ]]; then
  fail "1a: scripts/check-cron-template-delivery.py not found -- nothing enforces the one-delivery-path rule"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi
pass "1a: gate present"

if python3 -m py_compile "$GATE" 2>"$TMP/pyc.err"; then
  pass "1b: gate compiles"
else
  fail "1b: gate fails to compile: $(cat "$TMP/pyc.err")"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi

# run_gate ROOT -> echoes rc, writes output to $TMP/gate-out.txt
run_gate() {
  local _root="$1" _rc=0
  python3 "$GATE" --root "$_root" >"$TMP/gate-out.txt" 2>&1 || _rc=$?
  echo "$_rc"
}

# ---------------------------------------------------------------------------
# (2) REAL_REPO: the shipped tree must be clean.
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) REAL_REPO: gate passes against the real repo tree ---"
rc="$(run_gate "$REPO_ROOT")"
if [[ "$rc" -eq 0 ]]; then
  pass "2a: gate PASSES against the real repo ($(grep -c . "$TMP/gate-out.txt") lines of report)"
else
  fail "2a: gate FAILS against the real repo tree (rc=$rc):"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# ---------------------------------------------------------------------------
# (3) REAL_MUTATION: the genuine pre-fix file must be caught.
#     This is the anti-strawman check -- it uses the ACTUAL bytes that shipped,
#     pulled from git, not a fixture written to be catchable.
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) REAL_MUTATION: gate catches the genuine pre-fix file from git ---"
MUT="$TMP/real-mutation"
mkdir -p "$MUT"

# DO NOT anchor this to origin/main. Once the fix is merged, origin/main holds
# the FIXED file and this check goes red for the wrong reason -- which is exactly
# what happened the first time it ran after merge. Instead, walk the file's own
# history and take the most recent revision that genuinely still carried the
# defect. That is self-maintaining: it keeps testing real historical bytes no
# matter how far main advances, and it degrades to UNDETERMINED rather than a
# false pass if no such revision can be found.
_pre_fix_rev=""
_hist="$(git -C "$REPO_ROOT" rev-list HEAD -- direct-to-agent-install.md 2>/dev/null | head -60)"
for _rev in $_hist; do
  _blob="$(git -C "$REPO_ROOT" show "$_rev:direct-to-agent-install.md" 2>/dev/null)" || continue
  [[ -z "$_blob" ]] && continue
  # The defect: a cron registration line carrying delivery flags. Match the
  # registration itself, not prose that merely mentions the flags (the fixed
  # file deliberately names them in a "do NOT add this" warning).
  if printf '%s\n' "$_blob" | grep -qE '^[[:space:]]*--channel[[:space:]]+telegram[[:space:]]+--to\b'; then
    _pre_fix_rev="$_rev"
    break
  fi
done

if [[ -n "$_pre_fix_rev" ]]; then
  git -C "$REPO_ROOT" show "$_pre_fix_rev:direct-to-agent-install.md" > "$MUT/direct-to-agent-install.md" 2>/dev/null
  # Pair it with the prompt template from the SAME revision where possible, so
  # the pair is internally consistent; fall back to the current one.
  git -C "$REPO_ROOT" show "$_pre_fix_rev:cron-prompt.txt" > "$MUT/cron-prompt.txt" 2>/dev/null \
    || cp "$REPO_ROOT/cron-prompt.txt" "$MUT/cron-prompt.txt" 2>/dev/null
fi

if [[ -z "$_pre_fix_rev" ]] || [[ ! -s "$MUT/direct-to-agent-install.md" ]]; then
  echo "  SKIP: no historical revision of direct-to-agent-install.md carrying the"
  echo "        pre-fix wiring was found in the first 60 revisions (shallow clone?)."
  echo "        UNDETERMINED, not a pass -- the synthetic checks in (4) still run."
else
  echo "  (using pre-fix revision ${_pre_fix_rev:0:8} of direct-to-agent-install.md)"
  rc="$(run_gate "$MUT")"
  if [[ "$rc" -eq 1 ]] && grep -q "DOUBLE_DELIVERY" "$TMP/gate-out.txt"; then
    pass "3a: gate FLAGS the genuine pre-fix direct-to-agent-install.md as DOUBLE_DELIVERY (real bytes from git, not a fixture)"
  else
    fail "3a: gate did NOT flag the real pre-fix file (rc=$rc) -- it would not have caught the defect that shipped"
    sed 's/^/        /' "$TMP/gate-out.txt"
  fi
fi

# ---------------------------------------------------------------------------
# (4) SYNTHETIC: one purpose-built fixture per check.
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) SYNTHETIC: each check fires on its own fixture ---"

# --- 4a SELF_ADDRESSING: the exact live-box phrasing ---
S1="$TMP/f-selfaddr"; mkdir -p "$S1"
cat > "$S1/daily-briefing-prompt.txt" <<'FIXEOF'
Compile the morning briefing from the last 24 hours of activity.
Post the full briefing to this topic (#178) when it is ready.
FIXEOF
rc="$(run_gate "$S1")"
if [[ "$rc" -eq 1 ]] && grep -q "SELF_ADDRESSING" "$TMP/gate-out.txt"; then
  pass "4a: SELF_ADDRESSING fires on 'Post the full briefing to this topic (#178)'"
else
  fail "4a: SELF_ADDRESSING did not fire (rc=$rc) on the exact live-box phrasing"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# --- 4b SELF_ADDRESSING: the other live-box phrasing + invented targets ---
S2="$TMP/f-selfaddr2"; mkdir -p "$S2"
cat > "$S2/digest-prompt.txt" <<'FIXEOF'
Send a short daily digest to Topic #65 at the end of the day.
FIXEOF
rc="$(run_gate "$S2")"
if [[ "$rc" -eq 1 ]] && grep -q "SELF_ADDRESSING" "$TMP/gate-out.txt"; then
  pass "4b: SELF_ADDRESSING fires on 'Send a short daily digest to Topic #65'"
else
  fail "4b: SELF_ADDRESSING did not fire (rc=$rc) on the second live-box phrasing"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# --- 4c SELF_ADDRESSING: the @telegram broadcast-channel shape (403) ---
S3="$TMP/f-attelegram"; mkdir -p "$S3"
cat > "$S3/report-prompt.txt" <<'FIXEOF'
Deliver the weekly report by messaging @telegram with the summary.
FIXEOF
rc="$(run_gate "$S3")"
if [[ "$rc" -eq 1 ]] && grep -q "SELF_ADDRESSING" "$TMP/gate-out.txt"; then
  pass "4c: SELF_ADDRESSING fires on the @telegram broadcast-channel target (the 403 shape)"
else
  fail "4c: SELF_ADDRESSING did not fire (rc=$rc) on @telegram"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# --- 4d DELIVERY_NONE on a client deliverable ---
S4="$TMP/f-delnone"; mkdir -p "$S4"
cat > "$S4/client-briefing.cron.json" <<'FIXEOF'
{
  "name": "daily-client-briefing",
  "schedule": "0 8 * * *",
  "prompt": "Produce the daily client briefing and hand it over.",
  "delivery_mode": "none"
}
FIXEOF
rc="$(run_gate "$S4")"
if [[ "$rc" -eq 1 ]] && grep -q "DELIVERY_NONE" "$TMP/gate-out.txt"; then
  pass "4d: DELIVERY_NONE fires on a client briefing shipping delivery_mode 'none'"
else
  fail "4d: DELIVERY_NONE did not fire (rc=$rc) on a client deliverable with no delivery path"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# --- 4e DOUBLE_DELIVERY on a synthetic registration ---
S5="$TMP/f-double"; mkdir -p "$S5"
cat > "$S5/some-prompt.txt" <<'FIXEOF'
Compose the update and then run:
openclaw message send --channel telegram --target "$CLIENT_CHAT" --message "done"
FIXEOF
cat > "$S5/install-notes.md" <<'FIXEOF'
Register it:

```
openclaw cron create --name weekly-thing \
  --cron "0 3 * * 0" --channel telegram --to <chat_id> \
  --message-file some-prompt.txt
```
FIXEOF
rc="$(run_gate "$S5")"
if [[ "$rc" -eq 1 ]] && grep -q "DOUBLE_DELIVERY" "$TMP/gate-out.txt"; then
  pass "4e: DOUBLE_DELIVERY fires when a delivering cron feeds a self-sending prompt"
else
  fail "4e: DOUBLE_DELIVERY did not fire (rc=$rc)"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# ---------------------------------------------------------------------------
# (5) NO_FALSE_POS: the two CORRECT shapes must pass.
#     A gate that flags correct code gets disabled, and then guards nothing.
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) NO_FALSE_POS: correct shapes are not flagged ---"

# 5a: SILENT cron + self-sending prompt (what install.sh actually does).
G1="$TMP/g-silent"; mkdir -p "$G1"
cat > "$G1/good-prompt.txt" <<'FIXEOF'
Resolve the recipient with resolve_owner_chat_id, then deliver:
openclaw message send --channel telegram --target "$CLIENT_CHAT" --message "$SUMMARY"
FIXEOF
cat > "$G1/install-notes.md" <<'FIXEOF'
Register it SILENT:

```
openclaw cron create --name weekly-thing --agent main \
  --cron "0 3 * * 0" --tz America/New_York \
  --session main --system-event "$(cat good-prompt.txt)"
```
FIXEOF
rc="$(run_gate "$G1")"
if [[ "$rc" -eq 0 ]]; then
  pass "5a: silent cron + self-sending prompt (the canonical correct shape) is NOT flagged"
else
  fail "5a: FALSE POSITIVE on the canonical silent shape (rc=$rc)"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# 5b: DELIVERING cron + prompt that does NOT self-send.
G2="$TMP/g-deliver"; mkdir -p "$G2"
cat > "$G2/plain-prompt.txt" <<'FIXEOF'
Summarize yesterday's activity in one short paragraph. Output the summary only.
FIXEOF
cat > "$G2/install-notes.md" <<'FIXEOF'
Register it with delivery:

```
openclaw cron create --name daily-thing \
  --cron "0 8 * * *" --channel telegram --to <chat_id> \
  --message-file plain-prompt.txt
```
FIXEOF
rc="$(run_gate "$G2")"
if [[ "$rc" -eq 0 ]]; then
  pass "5b: delivering cron + non-sending prompt (the other correct shape) is NOT flagged"
else
  fail "5b: FALSE POSITIVE on the delivering shape (rc=$rc)"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

# 5c: an INTERNAL maintenance cron may legitimately have no delivery.
G3="$TMP/g-internal"; mkdir -p "$G3"
cat > "$G3/guard.cron.json" <<'FIXEOF'
{
  "name": "toolsearch-drift-guard",
  "schedule": "*/20 * * * *",
  "prompt": "Run the drift guard sweep.",
  "delivery_mode": "none"
}
FIXEOF
rc="$(run_gate "$G3")"
if [[ "$rc" -eq 0 ]]; then
  pass "5c: an internal guard/sweep cron with no delivery is NOT flagged (only client deliverables need a delivery path)"
else
  fail "5c: FALSE POSITIVE -- an internal maintenance cron was flagged for having no delivery (rc=$rc)"
  sed 's/^/        /' "$TMP/gate-out.txt"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all cron-template-delivery checks pass"
exit 0
