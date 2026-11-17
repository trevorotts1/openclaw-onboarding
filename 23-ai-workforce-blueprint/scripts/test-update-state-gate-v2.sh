#!/usr/bin/env bash
# test-update-state-gate-v2.sh
#
# Acceptance test for BU-12 (update-interview-state.sh gate-v2 work).
# Self-contained: every fixture lives under a temp folder on the drive,
# runs under an empty HOME with explicit --state, writes nothing outside.
#
# Cases (from 01-BUILD-SPEC.md BU-12):
#   A. gate state missing industry -> --complete exits 87,
#      interviewComplete absent, interviewQc.missingQuestionIds holds industry
#      plus the rest of the missing list.
#   B. ten refused completions in a row never exit 89 (refusals charge nothing).
#   C. complete gate state -> --complete exits 0, interviewComplete true.
#   D. --sync-from-gate writes lastQuestionNumber equal to the answer-log
#      line count.
#   E. after a successful --complete, --sync-from-gate and --drain-deferred
#      (with one queued stamp) exit 0 and leave the state file byte-identical.
#   F. stub mirror helper exiting 3: --complete on a complete gate state still
#      exits 0 with exactly one stderr line beginning "interview-complete mirror:".
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPD="$SCRIPT_DIR/update-interview-state.sh"
GATE="$SCRIPT_DIR/interview_gate.py"
REG="$SCRIPT_DIR/../interview/questions.v2.json"

RESULTS_FILE="$(mktemp -t update-state-gate-v2-results.XXXXXX)"
trap 'rm -f "$RESULTS_FILE"' EXIT
: > "$RESULTS_FILE"
pass() { printf 'PASS\n' >> "$RESULTS_FILE"; printf '[PASS] %s\n' "$1"; }
fail() { printf 'FAIL\n' >> "$RESULTS_FILE"; printf '[FAIL] %s\n' "$1"; [ -n "${2:-}" ] && printf '       %s\n' "$2"; }

FIXROOT="$(mktemp -d -t update-state-gate-v2.XXXXXX)"
trap 'rm -rf "$FIXROOT" "$RESULTS_FILE"' EXIT

# Run the gate answer/skip commands inside an empty HOME.
gate() {  # $1 = gate state dir; rest = gate args
  local gd="$1"; shift
  env -i HOME="$FIXROOT/home" PATH="/usr/bin:/bin" TMPDIR="${TMPDIR:-/tmp}" \
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$GATE" --registry "$REG" --state-dir "$gd" "$@"
}

# Run update-interview-state.sh inside an empty HOME with explicit --state.
upd() {  # $1 = state file; rest = script args
  local st="$1"; shift
  env -i HOME="$FIXROOT/home" PATH="/usr/bin:/bin" TMPDIR="${TMPDIR:-/tmp}" \
    PYTHONDONTWRITEBYTECODE=1 bash "$UPD" --state "$st" "$@"
}

mkdir -p "$FIXROOT/home"

# Answer only the first question; industry (2nd, required) stays unanswered,
# so it heads the missing list. Later questions cannot be answered before
# industry through the legal gate order, and the spec only needs industry
# missing with exit 87.
answer_first_only() {  # $1 = gate state dir
  local gd="$1"
  gate "$gd" answer --qid company_name --text "Acme Studio" --source test >/dev/null
}

answer_everything() {  # $1 = gate state dir
  local gd="$1"
  # legal gate order: current question first, optionals skipped in place.
  gate "$gd" answer --qid company_name --text "Acme Studio" --source test >/dev/null
  gate "$gd" answer --qid industry --text "coaching and training services" --source test >/dev/null
  gate "$gd" answer --qid what_you_sell --text "I sell group coaching programs for managers" --source test >/dev/null
  gate "$gd" answer --qid business_stage --text "Steady customers" --source test >/dev/null
  gate "$gd" answer --qid ideal_customer --text "New managers at mid-size firms seeking growth" --source test >/dev/null
  gate "$gd" answer --qid unique_differentiator --text "I did their job for ten years myself" --source test >/dev/null
  gate "$gd" answer --qid customer_feeling --text "Relieved and clear" --source test >/dev/null
  gate "$gd" answer --qid brand_descriptors --text "Honest, fast, friendly work" --source test >/dev/null
  gate "$gd" skip --qid brand_evokes >/dev/null
  gate "$gd" skip --qid brand_voice >/dev/null
  gate "$gd" skip --qid brand_primary_color >/dev/null
  gate "$gd" skip --qid brand_logo >/dev/null
  gate "$gd" answer --qid revenue_goal_12mo --text "Up to \$100,000" --source test >/dev/null
  gate "$gd" answer --qid top_priority_90d --text "Get more leads" --source test >/dev/null
  gate "$gd" answer --qid time_drain --text "Chasing invoices every week" --source test >/dev/null
  gate "$gd" answer --qid tools_used --text "Stripe|Canva" --source test >/dev/null
  gate "$gd" answer --qid customer_channels --text "Instagram" --source test >/dev/null
  gate "$gd" answer --qid department_review --text "keep-all" --source test >/dev/null
  gate "$gd" answer --qid focus_dept_1 --text "Twenty new leads a month" --source test >/dev/null
}

make_state() {  # $1 = file
  # No interviewComplete key: the refusal must leave the flag ABSENT
  # (spec: "interviewComplete is absent from the file"), not merely false.
  printf '{"version":1,"interviewProgress":{}}' > "$1"
}

# ── A + B: refused completion (industry missing) ─────────────────────────────
(
  D="$FIXROOT/case-ab"; mkdir -p "$D/ws/company-discovery" "$FIXROOT/home"
  S="$D/ws/state.json"; GD="$D/ws/company-discovery"; make_state "$S"
  answer_first_only "$GD"

  OUT=$(upd "$S" --sync-from-gate 2>&1); SRC=$?
  [ "$SRC" -eq 0 ] || { fail "A: --sync-from-gate exits 0" "rc=$SRC :: $OUT"; }

  OUT=$(upd "$S" --complete 2>&1); RC=$?
  MISSING=$(python3 -B -c "import json;d=json.load(open('$S'));print(' '.join(d.get('interviewQc',{}).get('missingQuestionIds',[])))" 2>/dev/null || echo "unreadable")
  HASFLAG=$(python3 -B -c "import json;d=json.load(open('$S'));print('absent' if 'interviewComplete' not in d else d.get('interviewComplete'))" 2>/dev/null || echo "unreadable")
  case "$MISSING" in
    *industry*) MOK=1 ;;
    *) MOK=0 ;;
  esac
  # Spec: "interviewComplete is absent from the file". The refusal writer never
  # seeds the flag; the fixture starts without the key so absent is provable.
  if [ "$RC" -eq 87 ] && [ "$HASFLAG" = "absent" ] && [ "$MOK" -eq 1 ]; then
    pass "A: gate state missing industry -> exit 87, interviewComplete absent, missingQuestionIds holds industry (+ rest)"
  else
    fail "A: expected exit=87 + interviewComplete absent + industry in missingQuestionIds" \
      "got rc=$RC interviewComplete=$HASFLAG missing=[$MISSING]; tail: $(echo "$OUT" | tail -3)"
  fi

  BAD=0
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    upd "$S" --complete >/dev/null 2>&1; [ "$?" -eq 89 ] && BAD=1
  done
  if [ "$BAD" -eq 0 ]; then
    pass "B: ten refused completions in a row never exit 89"
  else
    fail "B: a refused completion exited 89 (refusals must not consume the completion budget)"
  fi
)

# ── C + D + E: complete gate state ────────────────────────────────────────────
(
  D="$FIXROOT/case-cde"; mkdir -p "$D/ws/company-discovery" "$FIXROOT/home"
  S="$D/ws/state.json"; GD="$D/ws/company-discovery"; make_state "$S"
  answer_everything "$GD"

  OUT=$(upd "$S" --sync-from-gate 2>&1); SRC=$?
  LINES=$(wc -l < "$GD/interview-answers.jsonl" | tr -d ' ')
  GOT=$(python3 -B -c "import json;print(json.load(open('$S'))['interviewProgress']['lastQuestionNumber'])" 2>/dev/null || echo "unreadable")
  if [ "$SRC" -eq 0 ] && [ "$GOT" = "$LINES" ]; then
    pass "D: --sync-from-gate writes lastQuestionNumber ($GOT) equal to the answer-log line count ($LINES)"
  else
    fail "D: expected lastQuestionNumber == answer-log lines" "got sync rc=$SRC number=$GOT lines=$LINES; tail: $(echo "$OUT" | tail -3)"
  fi

  OUT=$(upd "$S" --complete 2>&1); RC=$?
  FLAG=$(python3 -B -c "import json;print(json.load(open('$S')).get('interviewComplete'))" 2>/dev/null || echo "unreadable")
  if [ "$RC" -eq 0 ] && [ "$FLAG" = "True" ]; then
    pass "C: complete gate state -> --complete exits 0, interviewComplete true"
  else
    fail "C: expected exit=0 + interviewComplete=true" "got rc=$RC interviewComplete=$FLAG; tail: $(echo "$OUT" | tail -4)"
  fi

  cp "$S" "$D/before.json"
  printf '{"session":"s1","phase":"operations","questionNumber":9,"askedBy":"tester","phasesComplete":null}\n' > "$D/ws/.interview-state-deferred.jsonl"
  OUT1=$(upd "$S" --sync-from-gate 2>&1); RC1=$?
  OUT2=$(upd "$S" --drain-deferred 2>&1); RC2=$?
  if [ "$RC1" -eq 0 ] && [ "$RC2" -eq 0 ] && cmp -s "$D/before.json" "$S" && [ ! -e "$D/ws/.interview-state-deferred.jsonl" ]; then
    pass "E: after --complete, --sync-from-gate + --drain-deferred (one queued stamp) exit 0, state byte-identical, queue emptied"
  else
    fail "E: expected rc 0/0 + byte-identical + queue emptied" \
      "got rc1=$RC1 rc2=$RC2 identical=$(cmp -s "$D/before.json" "$S" && echo yes || echo no); tail: $(echo "$OUT1 $OUT2" | tail -3)"
  fi
)

# ── F: mirror helper stub exiting 3 ───────────────────────────────────────────
(
  D="$FIXROOT/case-f"; mkdir -p "$D/proj/23-ai-workforce-blueprint/scripts" "$D/proj/23-ai-workforce-blueprint/interview" "$D/proj/shared-utils" "$D/ws/company-discovery" "$FIXROOT/home"
  for f in update-interview-state.sh lib-interview-rate-limit.sh lib-workforce-state.sh workforce_state.py interview_eligibility.py interview_gate.py; do
    cp "$SCRIPT_DIR/$f" "$D/proj/23-ai-workforce-blueprint/scripts/"
  done
  cp "$SCRIPT_DIR/../interview/questions.v2.json" "$D/proj/23-ai-workforce-blueprint/interview/"
  printf '#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n' > "$D/proj/shared-utils/ensure_cc_interview_flag.py"
  chmod +x "$D/proj/shared-utils/ensure_cc_interview_flag.py"
  S="$D/ws/state.json"; make_state "$S"
  cp -r "$FIXROOT/case-cde/ws/company-discovery/." "$D/ws/company-discovery/" 2>/dev/null || answer_everything "$D/ws/company-discovery"
  rm -f "$D/ws/.interview-state-deferred.jsonl"
  env -i HOME="$FIXROOT/home" PATH="/usr/bin:/bin" TMPDIR="${TMPDIR:-/tmp}" PYTHONDONTWRITEBYTECODE=1 \
    bash "$D/proj/23-ai-workforce-blueprint/scripts/update-interview-state.sh" --state "$S" --sync-from-gate >/dev/null 2>&1
  OUT=$(env -i HOME="$FIXROOT/home" PATH="/usr/bin:/bin" TMPDIR="${TMPDIR:-/tmp}" PYTHONDONTWRITEBYTECODE=1 \
    bash "$D/proj/23-ai-workforce-blueprint/scripts/update-interview-state.sh" --state "$S" --complete 2>&1); RC=$?
  FLAG=$(python3 -B -c "import json;print(json.load(open('$S')).get('interviewComplete'))" 2>/dev/null || echo "unreadable")
  N=$(printf '%s' "$OUT" | grep -c '^interview-complete mirror:' || true)
  if [ "$RC" -eq 0 ] && [ "$FLAG" = "True" ] && [ "$N" -eq 1 ]; then
    pass "F: mirror stub exiting 3 -> --complete still exits 0, exactly one 'interview-complete mirror:' stderr line"
  else
    fail "F: expected exit=0 + interviewComplete=true + one mirror line" "got rc=$RC interviewComplete=$FLAG lines=$N; tail: $(echo "$OUT" | tail -4)"
  fi
)

# nothing written outside the temp folder; HOME stays empty
HOME_ENTRIES=$(ls -A "$FIXROOT/home" 2>/dev/null | wc -l | tr -d ' ')
if [ "$HOME_ENTRIES" -eq 0 ]; then
  pass "HOME folder stays empty"
else
  fail "HOME folder stays empty" "entries: $(ls -A "$FIXROOT/home")"
fi

TOTAL=$(wc -l < "$RESULTS_FILE" | tr -d ' ')
NFAILED=$(grep -c '^FAIL$' "$RESULTS_FILE" || true)
NPASSED=$(grep -c '^PASS$' "$RESULTS_FILE" || true)

echo ""
echo "=========================================="
echo "Update-Interview-State Gate-v2 Results"
echo "=========================================="
echo "  PASSED: $NPASSED / $TOTAL"
echo "  FAILED: $NFAILED / $TOTAL"
echo "=========================================="
[ "$NFAILED" -eq 0 ]
exit $?
