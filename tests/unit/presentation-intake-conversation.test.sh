#!/usr/bin/env bash
# presentation-intake-conversation.test.sh -- guard for the Client Intake
# Conversation Contract (CLIENT-WEBINAR-DECK-SOP.md section 0.5).
#
# The presentation department must OFFER the quick-vs-in-depth CHOICE FIRST, then
# ask ONE question at a time -- never dump a batch of questions. This guard makes
# that rule self-defending: it asserts, across every conversation-governing
# artifact, that
#   (A) the CHOICE is present (quick AND in-depth/deep, plus a choice question on
#       the canonical-prompt artifacts),
#   (B) the ONE-AT-A-TIME rule is present (one question, at a time / per message),
#   (C) AF-INTAKE-BATCH is named in the doctrine artifacts, and the exact
#       screenshot batch anti-pattern is BANNED, and
#   (D) no OWNER-FACING message regresses to a batch (the screenshot phrase
#       "give me whatever you have got" / the old "ask a few quick questions"
#       framing must be absent).
#
# It touches NO build phase: the image-prompt floor, build_deck.py,
# run_signature_deck.py, and the deterministic pipeline are out of scope here.
#
# EXIT CODES: 0 all pass; 1 one or more assertions failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$ROOT/23-ai-workforce-blueprint"
PRES="$SKILL/templates/role-library/presentations"
SEND="$SKILL/scripts/send-presentation-dept-welcome.sh"

SOP_DOCTRINE="$ROOT/universal-sops/CLIENT-WEBINAR-DECK-SOP.md"
BUDDY_ROLE="$PRES/brainstorming-buddy-presentations.md"
BUDDY_SOPS="$PRES/sops/brainstorming-buddy-presentations-sops.md"
IDENTITY="$PRES/IDENTITY.md"
SOUL="$PRES/SOUL.md"
XDEPT_TEMPLATE="$SKILL/templates/role-library/_brainstorming-buddy-template.md"
HOWTO_TEMPLATE="$SKILL/templates/how-to-use-this-department.template.md"
HOWTO_PRES="$PRES/how-to-use-this-department.md"

PASS=0; FAIL=0
ok()  { printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  [FAIL] %s\n' "$1" >&2; FAIL=$((FAIL+1)); }

# grep helpers (case-insensitive). present_e/absent_e use ERE.
present()   { if grep -qiF "$2" "$1"; then ok "$3"; else bad "$3 (missing '$2' in $(basename "$1"))"; fi; }
present_e() { if grep -qiE "$2" "$1"; then ok "$3"; else bad "$3 (pattern /$2/ not found in $(basename "$1"))"; fi; }
absent()    { if grep -qiF "$2" "$1"; then bad "$3 (forbidden '$2' present in $(basename "$1"))"; else ok "$3"; fi; }

# present/absent against a STRING (resolved message), not a file.
s_present()   { if printf '%s' "$1" | grep -qiF "$2"; then ok "$3"; else bad "$3 (missing '$2')"; fi; }
s_present_e() { if printf '%s' "$1" | grep -qiE "$2"; then ok "$3"; else bad "$3 (pattern /$2/ not found)"; fi; }
s_absent()    { if printf '%s' "$1" | grep -qiF "$2"; then bad "$3 (forbidden '$2' present)"; else ok "$3"; fi; }

# Reusable phrase atoms.
ONE_AT_A_TIME='one (question )?(at a time|per message)'
CHOICE_QUESTION='which would you like|which do you want|whether you want|quick or in-depth|quick or deep|quick path or'

echo "===================================================================="
echo " presentation-intake-conversation.test.sh -- choice-first / one-at-a-time"
echo "===================================================================="

# ---- (A)+(B) every DOCTRINE artifact: choice + one-at-a-time + AF-INTAKE-BATCH
echo "--- doctrine artifacts: choice present, one-at-a-time present, AF-INTAKE-BATCH named ---"
for f in "$SOP_DOCTRINE" "$BUDDY_ROLE" "$BUDDY_SOPS" "$IDENTITY" "$SOUL" "$XDEPT_TEMPLATE"; do
  b="$(basename "$f")"
  [ -f "$f" ] || { bad "$b missing"; continue; }
  present   "$f" "quick" "$b: offers QUICK option"
  present_e "$f" "in-depth|in depth|deep" "$b: offers IN-DEPTH/DEEP option"
  present_e "$f" "$ONE_AT_A_TIME" "$b: states one-question-at-a-time"
  present   "$f" "AF-INTAKE-BATCH" "$b: names the AF-INTAKE-BATCH auto-fail"
done

# ---- (A) canonical-prompt artifacts carry the literal CHOICE question ----
echo "--- canonical-prompt artifacts: the choice is a real question ---"
for f in "$SOP_DOCTRINE" "$BUDDY_ROLE" "$BUDDY_SOPS"; do
  present_e "$f" "$CHOICE_QUESTION" "$(basename "$f"): asks a quick-vs-in-depth choice question"
done

# ---- (C) the doctrine BANS the exact screenshot anti-pattern verbatim ----
echo "--- doctrine bans the screenshot batch anti-pattern (documented) ---"
present "$SOP_DOCTRINE" "give me whatever you have got" "section 0.5: documents the banned batch phrase"
present "$BUDDY_ROLE"   "give me whatever you have got" "buddy role: documents the banned batch phrase"

# ---- how-to-use template: choice + one-at-a-time (owner-facing wording) ----
echo "--- cross-department how-to-use template ---"
present   "$HOWTO_TEMPLATE" "quick interview" "how-to template: offers a quick interview"
present   "$HOWTO_TEMPLATE" "in-depth" "how-to template: offers an in-depth interview"
present_e "$HOWTO_TEMPLATE" "$ONE_AT_A_TIME" "how-to template: one question at a time"
absent    "$HOWTO_TEMPLATE" "ask you one or two quick questions" "how-to template: old batch framing removed"

# ---- (D) OWNER-FACING messages: choice + one-at-a-time AND no batch ----
echo "--- owner-facing: regenerated presentations how-to guide ---"
if [ -f "$HOWTO_PRES" ]; then
  present   "$HOWTO_PRES" "quick interview" "presentations guide: offers a quick interview"
  present   "$HOWTO_PRES" "in-depth" "presentations guide: offers an in-depth interview"
  present_e "$HOWTO_PRES" "$ONE_AT_A_TIME" "presentations guide: one question at a time"
  absent    "$HOWTO_PRES" "give me whatever you have got" "presentations guide: no screenshot batch phrase"
  absent    "$HOWTO_PRES" "ask you one or two quick questions" "presentations guide: no old batch framing"
else
  bad "presentations how-to-use-this-department.md missing"
fi

echo "--- owner-facing: resolved welcome message (--dry-run) ---"
TMPH="$(mktemp -d)"
mkdir -p "$TMPH/.openclaw/workspace"
cat > "$TMPH/.openclaw/workspace/.workforce-build-state.json" <<'JSON'
{
  "version": 1,
  "ownerChat": 9999999999,
  "ownerName": "Sample Owner",
  "companyName": "Sample Business Co",
  "departments": [
    { "slug": "presentations", "name": "Presentations", "status": "done",
      "wiringStatus": "done", "roleLibraryFilled": true, "sopLibraryFilled": true,
      "deptHeadPersona": "Sample Dept Head", "presentationDeptWelcomeSent": false }
  ]
}
JSON
WELCOME="$(HOME="$TMPH" bash "$SEND" --dry-run 2>&1)"
rm -rf "$TMPH"
s_present   "$WELCOME" "quick interview" "welcome message: offers a quick interview"
s_present   "$WELCOME" "in-depth" "welcome message: offers an in-depth interview"
s_present_e "$WELCOME" "$ONE_AT_A_TIME" "welcome message: one question at a time"
s_absent    "$WELCOME" "give me whatever you have got" "welcome message: no screenshot batch phrase"
s_absent    "$WELCOME" "ask a few quick questions" "welcome message: no old batch framing"

echo "===================================================================="
echo " RESULTS: $PASS passed, $FAIL failed"
echo "===================================================================="
[ "$FAIL" -gt 0 ] && exit 1
exit 0
