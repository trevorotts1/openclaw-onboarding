#!/usr/bin/env bash
# presentation-intake-conversation.test.sh -- guard for the Signature-Presentation
# (Skill 51) CLIENT INTAKE CONVERSATION contract (AF-INTAKE-BATCH).
#
# DOCTRINE (Trevor's ruling -- one-question-at-a-time wins): the signature-
# presentation intake must OFFER the quick-vs-in-depth CHOICE FIRST, then ask ONE
# question at a time -- never dump the 8 Questions as a batch. This guard makes
# that rule self-defending across the Skill-51 intake artifacts this repo owns:
#   (A) the CHOICE is present (quick AND in-depth),
#   (B) the ONE-AT-A-TIME rule is present (one question at a time / per message),
#   (C) AF-INTAKE-BATCH is named, and the exact screenshot batch anti-pattern is
#       DOCUMENTED as banned,
#   (D) the spec's structured conversation_contract declares choice_first +
#       one_question_per_message + af_on_violation == AF-INTAKE-BATCH, and no
#       Skill-51 intake artifact regresses to the old "delivered as ONE block" /
#       "asked in the SAME block" conversation framing, and
#   (E) the deterministic RECORD gate (prove_sp_intake.py --self-test) still
#       passes -- the record layer (asked_all_at_once / one_block) is UNCHANGED;
#       only the CONVERSATION doctrine is added, and
#   (F) the client-facing WORDING never regresses: the banned quick-questions
#       phrases ("ask a few quick questions" / "ask you one or two quick
#       questions") appear NOWHERE in the presentations welcome script, the
#       how-to-use-this-department template, or any generated department how-to
#       (the PR-440 remainder -- the doctrine must reach the copy the OWNER reads).
#
# SCOPE: this guards the Skill-51 INTAKE CONVERSATION plus the client-facing
# wording that carries the same doctrine. It touches NO build phase -- the
# image-prompt floor, build_deck.py, and run_signature_deck.py are out of scope.
# The AF-SP-8Q-* RECORD gate is deliberately left intact (it gates the assembled
# machine record, not the conversation).
#
# EXIT CODES: 0 all pass; 1 one or more assertions failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL51="$ROOT/51-signature-presentation"
SPEC="$SKILL51/intake/sp-8-questions.json"
SKILLMD="$SKILL51/SKILL.md"
PROVER="$SKILL51/scripts/prove_sp_intake.py"
PY="${PYTHON:-python3}"

PASS=0; FAIL=0
ok()  { printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  [FAIL] %s\n' "$1" >&2; FAIL=$((FAIL+1)); }

# grep helpers (case-insensitive). present_e uses ERE; present/absent use fixed.
present()   { if grep -qiF "$2" "$1"; then ok "$3"; else bad "$3 (missing '$2' in $(basename "$1"))"; fi; }
present_e() { if grep -qiE "$2" "$1"; then ok "$3"; else bad "$3 (pattern /$2/ not found in $(basename "$1"))"; fi; }
absent()    { if grep -qiF "$2" "$1"; then bad "$3 (forbidden '$2' present in $(basename "$1"))"; else ok "$3"; fi; }

ONE_AT_A_TIME='one (question )?(at a time|per message)'

echo "===================================================================="
echo " presentation-intake-conversation.test.sh -- Skill 51 choice-first / one-at-a-time"
echo "===================================================================="

for f in "$SPEC" "$SKILLMD"; do
  [ -f "$f" ] || { bad "$(basename "$f") missing at $f"; continue; }
done

# ---- (A)+(B)+(C): the intake artifacts carry choice + one-at-a-time + AF-INTAKE-BATCH
echo "--- intake artifacts: choice present, one-at-a-time present, AF-INTAKE-BATCH named ---"
for f in "$SPEC" "$SKILLMD"; do
  [ -f "$f" ] || continue
  b="$(basename "$f")"
  present   "$f" "quick" "$b: offers the QUICK option"
  present_e "$f" "in-depth|in depth|deep" "$b: offers the IN-DEPTH option"
  present_e "$f" "$ONE_AT_A_TIME" "$b: states one question at a time"
  present   "$f" "AF-INTAKE-BATCH" "$b: names the AF-INTAKE-BATCH auto-fail"
done

# ---- (C) the spec DOCUMENTS the exact screenshot batch anti-pattern verbatim ----
echo "--- spec documents the banned batch anti-pattern ---"
present "$SPEC" "give me whatever you have got" "spec: documents the banned batch phrase"

# ---- (D) structured conversation_contract in the spec (parsed, not grepped) ----
echo "--- spec conversation_contract is structurally correct ---"
if [ -f "$SPEC" ]; then
  if "$PY" - "$SPEC" <<'PYEOF'
import json, sys
spec = json.load(open(sys.argv[1]))
d = spec.get("delivery", {})
cc = d.get("conversation_contract", {})
errs = []
if cc.get("choice_first") is not True:
    errs.append("delivery.conversation_contract.choice_first must be true")
if cc.get("one_question_per_message") is not True:
    errs.append("delivery.conversation_contract.one_question_per_message must be true")
if cc.get("af_on_violation") != "AF-INTAKE-BATCH":
    errs.append("delivery.conversation_contract.af_on_violation must be 'AF-INTAKE-BATCH'")
choices = [str(c).lower() for c in (cc.get("interview_choices") or [])]
if "quick" not in choices or not any("depth" in c for c in choices):
    errs.append("delivery.conversation_contract.interview_choices must include quick + in-depth")
# The RECORD layer must be LEFT INTACT (prove_sp_intake still validates one_block).
if d.get("asked_all_at_once") is not True:
    errs.append("RECORD layer regressed: delivery.asked_all_at_once must stay true")
if d.get("mode") != "one_block":
    errs.append("RECORD layer regressed: delivery.mode must stay 'one_block'")
if errs:
    print("\n".join(errs)); sys.exit(1)
sys.exit(0)
PYEOF
  then ok "spec: conversation_contract declares choice-first + one-at-a-time + AF-INTAKE-BATCH; record layer intact"
  else bad "spec: conversation_contract / record-layer assertion failed (see above)"
  fi
else
  bad "spec missing -- cannot check conversation_contract"
fi

# ---- (D) no regression to the old batch conversation framing ----
echo "--- no regression to the old one-block conversation framing ---"
if [ -f "$SKILLMD" ]; then
  absent "$SKILLMD" "delivered as ONE block" "SKILL.md: old 'delivered as ONE block' conversation framing removed"
  absent "$SKILLMD" "asked in the SAME block" "SKILL.md: old 'asked in the SAME block' framing removed"
fi

# ---- (E) the deterministic RECORD gate still passes (record layer unchanged) ----
echo "--- record gate: prove_sp_intake.py --self-test still green ---"
if [ -f "$PROVER" ]; then
  if OUT="$("$PY" "$PROVER" --self-test 2>&1)"; then
    ok "prove_sp_intake.py --self-test PASS (record layer intact)"
  else
    bad "prove_sp_intake.py --self-test FAILED"
    printf '%s\n' "$OUT" | sed 's/^/         /' >&2
  fi
else
  bad "prove_sp_intake.py missing at $PROVER"
fi

# ---- (G) AF-INTAKE-BATCH now has a REAL runtime implementation, not just spec prose ----
echo "--- AF-INTAKE-BATCH: real scanner exists and self-tests green ---"
TRACE_CHECK="$SKILL51/scripts/intake_trace_check.py"
if [ -f "$TRACE_CHECK" ]; then
  if OUT="$("$PY" "$TRACE_CHECK" --self-test 2>&1)"; then
    ok "intake_trace_check.py --self-test PASS (AF-INTAKE-BATCH scanner is real, not just a spec-file assertion)"
  else
    bad "intake_trace_check.py --self-test FAILED"
    printf '%s\n' "$OUT" | sed 's/^/         /' >&2
  fi
else
  bad "intake_trace_check.py missing at $TRACE_CHECK (AF-INTAKE-BATCH still has no runtime implementation)"
fi

# ---- (H) SIGNATURE mode has a REAL turn-gate: deck-intake-driver.py --signature --selftest ----
echo "--- SIGNATURE mode: --signature --next/--answer real turn-gate self-tests green ---"
DRIVER="$ROOT/23-ai-workforce-blueprint/scripts/deck-intake-driver.py"
if [ -f "$DRIVER" ]; then
  if OUT="$("$PY" "$DRIVER" --signature --selftest 2>&1)"; then
    ok "deck-intake-driver.py --signature --selftest PASS (signature mode is a real one-question-per-turn gate)"
  else
    bad "deck-intake-driver.py --signature --selftest FAILED"
    printf '%s\n' "$OUT" | sed 's/^/         /' >&2
  fi
else
  bad "deck-intake-driver.py missing at $DRIVER"
fi

# ---- (F) client-facing WORDING never regresses to the banned quick-questions phrasing ----
# PR-440 remainder: the one-question-at-a-time doctrine must reach the CLIENT-FACING copy,
# not only the guard/record layers. These two phrases are BANNED and must appear NOWHERE in
# the welcome script, the how-to template, or any generated how-to-use-this-department.md.
echo "--- client-facing wording: banned quick-questions phrases absent ---"
BLUEPRINT="$ROOT/23-ai-workforce-blueprint"
WELCOME_SCRIPT="$BLUEPRINT/scripts/send-presentation-dept-welcome.sh"
HOWTO_TEMPLATE="$BLUEPRINT/templates/how-to-use-this-department.template.md"
BANNED_A="ask a few quick questions"
BANNED_B="ask you one or two quick questions"

check_banned() {  # $1=file  $2=human-label
  local f="$1" lbl="$2"
  if [ ! -f "$f" ]; then bad "$lbl: file missing ($f)"; return; fi
  absent "$f" "$BANNED_A" "$lbl: no '$BANNED_A'"
  absent "$f" "$BANNED_B" "$lbl: no '$BANNED_B'"
}

check_banned "$WELCOME_SCRIPT" "welcome script"
check_banned "$HOWTO_TEMPLATE" "how-to template"

HOWTO_DOCS="$(find "$BLUEPRINT/templates/role-library" -name how-to-use-this-department.md 2>/dev/null | sort)"
if [ -z "$HOWTO_DOCS" ]; then
  bad "generated how-to docs: none found under role-library"
else
  while IFS= read -r doc; do
    [ -n "$doc" ] || continue
    dept="$(basename "$(dirname "$doc")")"
    check_banned "$doc" "how-to[$dept]"
  done <<< "$HOWTO_DOCS"
fi

echo "===================================================================="
echo " RESULTS: $PASS passed, $FAIL failed"
echo "===================================================================="
[ "$FAIL" -gt 0 ] && exit 1
exit 0
