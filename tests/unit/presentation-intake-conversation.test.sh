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
#       passes -- the record layer (record_committed_atomically / one_block; the
#       machine layer no longer teaches batching) still gates the atomic commit;
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
# The RECORD layer must be LEFT INTACT (prove_sp_intake still validates the
# atomic-commit fact). v1.1: the canonical field is record_committed_atomically;
# asked_all_at_once is a deprecated alias (accepted for one release). Accept
# either as the truthy record-committed signal, and mode must stay 'one_block'.
_committed = d.get("record_committed_atomically")
if _committed is None:
    _committed = d.get("asked_all_at_once")  # deprecated alias
if _committed is not True:
    errs.append("RECORD layer regressed: delivery.record_committed_atomically "
                "(or its deprecated alias asked_all_at_once) must stay true")
if d.get("mode") != "one_block":
    errs.append("RECORD layer regressed: delivery.mode must stay 'one_block'")
# The machine layer must NOT teach batching: one_question_per_turn was removed
# from the record layer (it describes the one-per-turn conversation, not the record).
if "one_question_per_turn" in d:
    errs.append("delivery.one_question_per_turn must be REMOVED from the record "
                "layer (it describes the conversation, not the record commit)")
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

# ---- (H) SIGNATURE mode has a REAL turn-gate: deck-intake-turngate.py --signature --selftest ----
echo "--- SIGNATURE mode: --signature --next/--answer real turn-gate self-tests green ---"
DRIVER="$ROOT/23-ai-workforce-blueprint/scripts/deck-intake-turngate.py"
if [ -f "$DRIVER" ]; then
  if OUT="$("$PY" "$DRIVER" --signature --selftest 2>&1)"; then
    ok "deck-intake-turngate.py --signature --selftest PASS (signature mode is a real one-question-per-turn gate)"
  else
    bad "deck-intake-turngate.py --signature --selftest FAILED"
    printf '%s\n' "$OUT" | sed 's/^/         /' >&2
  fi
else
  bad "deck-intake-turngate.py missing at $DRIVER"
fi

# ---- (J) E5 REGRESSION GUARD: the SIGNATURE turn-gate is REQUIRED, not optional ----
# Before this fix, a bare `--signature` call (no --next/--answer/--record) fell
# through to the SAME full 8-Questions-plus-frame payload as the dry-run plan --
# an unenforced escape hatch letting a caller bypass the one-question-per-turn
# gate entirely. This asserts (a) the bare call no longer leaks that payload and
# instead points at the required --next entrypoint, and (b) the explicit --plan
# dry-run/inspection escape hatch still works (it is documented, not hidden).
echo "--- SIGNATURE mode: bare --signature no longer leaks the full 8-question payload (E5) ---"
if [ -f "$DRIVER" ]; then
  BARE_OUT="$("$PY" "$DRIVER" --signature 2>&1)"
  if printf '%s' "$BARE_OUT" | grep -q '"status": "use_turn_gate"' \
     && printf '%s' "$BARE_OUT" | grep -q -- '--signature --next' \
     && ! printf '%s' "$BARE_OUT" | grep -q '"questions"'; then
    ok "bare --signature points at the turn-gate (--next) instead of dumping the question payload"
  else
    bad "bare --signature did not gate to the turn-gate pointer as expected"
    printf '%s\n' "$BARE_OUT" | sed 's/^/         /' >&2
  fi

  PLAN_OUT="$("$PY" "$DRIVER" --signature --plan 2>&1)"
  if printf '%s' "$PLAN_OUT" | grep -q '"questions"' \
     && printf '%s' "$PLAN_OUT" | grep -q '"frame_selection_question"'; then
    ok "--signature --plan still emits the full read-only dry-run payload (explicit escape hatch preserved)"
  else
    bad "--signature --plan no longer emits the full intake plan"
    printf '%s\n' "$PLAN_OUT" | sed 's/^/         /' >&2
  fi
else
  bad "deck-intake-turngate.py missing at $DRIVER -- cannot regression-test E5"
fi

# ---- (I) AF-INTAKE-BATCH: the scanner does not autofail a COMPLIANT transcript ----
# LIVE-CONFIRMED regression guard (E2): a one-question-per-turn transcript whose
# frame_selection turn is asked VERBATIM, alone, was previously misdetected as a
# 3-question BATCH-IN-TURN ([sp:frame_selection, sp:q5, sp:q6]) purely from
# incidental keyword overlap inside that ONE compliant bank question. This must
# now PASS (exit 0), not autofail (exit 2). FIX-3: the compliant transcript is a
# SIGNED DRIVER ENVELOPE (the shape deck-intake-turngate.py writes), so it passes
# the conversation scan AND the driver-provenance gate.
echo "--- AF-INTAKE-BATCH: compliant transcript (frame prompt verbatim, alone) does not autofail ---"
if [ -f "$TRACE_CHECK" ]; then
  TRANSCRIPT_TMP="$(mktemp -t sp-intake-compliant-transcript.XXXXXX.json 2>/dev/null || mktemp)"
  if OUT="$("$PY" - "$SPEC" "$TRANSCRIPT_TMP" <<'PYEOF'
import json, sys, os, importlib.util
spec = json.load(open(sys.argv[1]))
frame_prompt = spec["frame_selection_question"]["prompt"]
turns = [
    {"role": "assistant", "text": "Love this -- QUICK or IN-DEPTH, which would you like?", "qid": "interview_choice"},
    {"role": "owner", "text": "quick", "qid": "interview_choice"},
    {"role": "assistant", "text": "What is the title of your Signature Presentation?", "qid": "q1"},
    {"role": "owner", "text": "The Signature Talk", "qid": "q1"},
    {"role": "assistant", "text": frame_prompt, "qid": "frame_selection"},
    {"role": "owner", "text": "rulebook", "qid": "frame_selection"},
]
# Build the signed driver envelope via the checker's own canonical producer
# (51-signature-presentation/scripts/intake_trace_check.py, resolved from $SPEC).
cand = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(sys.argv[1])),
                                     "..", "scripts", "intake_trace_check.py"))
if os.path.exists(cand):
    s = importlib.util.spec_from_file_location("itc_fix3", cand)
    itc = importlib.util.module_from_spec(s); s.loader.exec_module(itc)
    env = itc.build_driver_envelope(["interview_choice", "q1", "frame_selection"], turns)
else:
    env = turns
json.dump(env, open(sys.argv[2], "w"))
PYEOF
  )"; then
    if OUT="$("$PY" "$TRACE_CHECK" "$TRANSCRIPT_TMP" --json 2>&1)"; then
      ok "intake_trace_check.py: compliant one-per-turn transcript (frame prompt verbatim, alone) PASSES (no false BATCH-IN-TURN)"
    else
      bad "intake_trace_check.py: compliant transcript AUTOFAILED (E2 regression)"
      printf '%s\n' "$OUT" | sed 's/^/         /' >&2
    fi
  else
    bad "intake_trace_check.py: could not build the compliant-transcript fixture"
    printf '%s\n' "$OUT" | sed 's/^/         /' >&2
  fi
  rm -f "$TRANSCRIPT_TMP"
else
  bad "intake_trace_check.py missing at $TRACE_CHECK -- cannot regression-test E2"
fi

# ---- (K) FIX-3: intake must be a REAL conversation — a hand-written bare-list
# transcript is REJECTED by the scanner (exit 2, NO-DRIVER-ENVELOPE). This is the
# file-level gate that makes a hand-written intake_ledger.json with no driver
# transcript fail the build. A compliant transcript that is NOT driver-produced is
# indistinguishable from fabrication, so it must fail regardless of content.
echo "--- FIX-3: hand-written bare-list transcript is REJECTED (NO-DRIVER-ENVELOPE) ---"
if [ -f "$TRACE_CHECK" ]; then
  BARE_TMP="$(mktemp -t sp-intake-bare-transcript.XXXXXX.json 2>/dev/null || mktemp)"
  "$PY" - "$SPEC" "$BARE_TMP" <<'PYEOF' >/dev/null
import json, sys
spec = json.load(open(sys.argv[1]))
frame_prompt = spec["frame_selection_question"]["prompt"]
turns = [
    {"role": "assistant", "text": "Love this -- QUICK or IN-DEPTH, which would you like?"},
    {"role": "owner", "text": "quick"},
    {"role": "assistant", "text": "What is the title of your Signature Presentation?"},
    {"role": "owner", "text": "The Signature Talk"},
    {"role": "assistant", "text": frame_prompt},
    {"role": "owner", "text": "rulebook"},
]
json.dump(turns, open(sys.argv[2], "w"))
PYEOF
  if OUT="$("$PY" "$TRACE_CHECK" "$BARE_TMP" --json 2>&1)"; then
    bad "intake_trace_check.py: hand-written bare-list transcript PASSED (FIX-3 regression — fabricated transcript not rejected)"
  else
    if printf '%s' "$OUT" | grep -q 'NO-DRIVER-ENVELOPE'; then
      ok "intake_trace_check.py: hand-written bare-list transcript REJECTED (NO-DRIVER-ENVELOPE)"
    else
      bad "intake_trace_check.py: bare-list transcript rejected but not as NO-DRIVER-ENVELOPE"
      printf '%s\n' "$OUT" | sed 's/^/         /' >&2
    fi
  fi
  rm -f "$BARE_TMP"
else
  bad "intake_trace_check.py missing at $TRACE_CHECK -- cannot regression-test FIX-3"
fi

# ---- (L) FIX-3: a SIGNED driver envelope (the shape deck-intake-turngate.py writes)
# passes the scanner end-to-end. Proves the positive control for (K): the scanner is
# not broken, it specifically rejects the fabricated (bare) shape.
echo "--- FIX-3: signed driver envelope transcript PASSES (positive control) ---"
if [ -f "$TRACE_CHECK" ]; then
  SIGNED_TMP="$(mktemp -t sp-intake-signed-transcript.XXXXXX.json 2>/dev/null || mktemp)"
  "$PY" - "$SPEC" "$TRACE_CHECK" "$SIGNED_TMP" <<'PYEOF' >/dev/null
import json, sys, importlib.util, os
spec = json.load(open(sys.argv[1]))
frame_prompt = spec["frame_selection_question"]["prompt"]
cand = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(sys.argv[2])), "..", "scripts", "intake_trace_check.py"))
s = importlib.util.spec_from_file_location("itc_fix3b", cand)
itc = importlib.util.module_from_spec(s); s.loader.exec_module(itc)
turns = [
    {"role": "assistant", "text": "Love this -- QUICK or IN-DEPTH, which would you like?", "qid": "interview_choice"},
    {"role": "owner", "text": "quick", "qid": "interview_choice"},
    {"role": "assistant", "text": "What is the title of your Signature Presentation?", "qid": "q1"},
    {"role": "owner", "text": "The Signature Talk", "qid": "q1"},
    {"role": "assistant", "text": frame_prompt, "qid": "frame_selection"},
    {"role": "owner", "text": "rulebook", "qid": "frame_selection"},
]
json.dump(itc.build_driver_envelope(["interview_choice", "q1", "frame_selection"], turns), open(sys.argv[3], "w"))
PYEOF
  if OUT="$("$PY" "$TRACE_CHECK" "$SIGNED_TMP" --json 2>&1)"; then
    ok "intake_trace_check.py: signed driver envelope transcript PASSES (positive control for FIX-3)"
  else
    bad "intake_trace_check.py: signed driver envelope AUTOFAILED (positive control broken)"
    printf '%s\n' "$OUT" | sed 's/^/         /' >&2
  fi
  rm -f "$SIGNED_TMP"
else
  bad "intake_trace_check.py missing at $TRACE_CHECK -- cannot run FIX-3 positive control"
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
