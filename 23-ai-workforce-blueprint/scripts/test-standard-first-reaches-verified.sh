#!/usr/bin/env bash
# test-standard-first-reaches-verified.sh — BU-110 (closes WF-129, part 1).
#
# Pins the standard-first lane all the way to a finished company: a prebuilt
# company, taken through the apply-diff build and ONE resume fire, reaches
# completionVerification.status == "verified" with buildCompletedAt set, no
# department entry left "prebuilt" or "pending", and the Skill 38 handoff
# recorded as "deferred" (BU-54) instead of holding the build open.
#
# The sandbox and PHASE A / PHASE B are the ones test-build-standard-first-
# roundtrip.sh already uses; the two deliberate differences are the point:
#   * DASHBOARD_DB_PATH is NOT placed in the environment — the lane must reach
#     verified without a live Command Center database in its environment
#     (the company tree is followed through companyRoot, BU-102);
#   * commsAutomationStatus is NOT pre-written — the resume job records the
#     deferral itself (BU-54), which is exactly what the assertion reads.
#
# Steps:
#   1. prebuild (PHASE 2 driver) + mock interview answers + apply-diff build
#   2. one resume-workforce-build.sh fire, with a stub `openclaw` on PATH
#   3. workforce_completion.py <state> --refresh (the BU-57 presentation probe
#      runs as its own non-required check; the qc check skips the same block)
#      -> assert verified, buildCompletedAt present, no prebuilt/pending
#         department, commsAutomationStatus == "deferred"
#   4. the apply-diff build a SECOND time -> rc 0 and company-config.json still
#      holds the company id
#   5. the resume job once more -> the state is still verified
#
# Hermetic: sandboxed $HOME and $MASTER_FILES_DIR, scratch build-state, a stub
# `openclaw` that records its arguments and exits 0. No network, no live box,
# no live database, nothing read from or written to a real installation.
#
# Exit 0 = every guard passed; non-zero = a guard failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
BW="$SCRIPT_DIR/build-workforce.py"
PREBUILD="$REPO_ROOT/scripts/prebuild-standard-workforce.sh"
RESUME="$SCRIPT_DIR/resume-workforce-build.sh"
COMPLETION="$SCRIPT_DIR/workforce_completion.py"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

for _f in "$BW" "$PREBUILD" "$RESUME" "$COMPLETION"; do
  if [ ! -f "$_f" ]; then bad "required file missing: $_f"; echo "ABORT"; exit 1; fi
done

TMP="$(mktemp -d -p "${TMPDIR:-$PWD}")"
trap 'rm -rf "$TMP"' EXIT
SANDBOX_HOME="$TMP/home"
MASTER="$TMP/master-files"
COMPANY="$MASTER/zero-human-company/scratch-canary-co"
STATE="$SANDBOX_HOME/.openclaw/workspace/.workforce-build-state.json"
DB="$TMP/mission-control.db"
CONSENT="$TMP/consent.json"
STUB_BIN="$TMP/bin"
mkdir -p "$SANDBOX_HOME/.openclaw/workspace" "$MASTER/zero-human-company" "$SANDBOX_HOME/.openclaw" \
         "$SANDBOX_HOME/Downloads/openclaw-master-files" "$COMPANY" "$STUB_BIN"
printf '{"decision":"prebuild","source":"operator-prebuild","decidedAt":"2026-08-04T12:00:00Z","decidedBy":"test-operator","sessionId":"sess-test"}\n' > "$CONSENT"
# The fixture box carries a client-configured default model (agents.defaults.model):
# model resolution stops with an ask-the-client error when neither a selector
# resolution nor a configured default exists, and a real client box always has one.
printf '{"models":{"list":[{"id":"ollama/qwen3-vl:cloud"}]},"agents":{"list":[],"defaults":{"model":{"primary":"ollama/box-default:cloud"}}}}\n' > "$SANDBOX_HOME/.openclaw/openclaw.json"
echo '{}' > "$STATE"

# Stub CLI: records every call, never reaches a real gateway.
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n' > "$STUB_BIN/openclaw"
chmod +x "$STUB_BIN/openclaw"
export STUB_LOG="$TMP/openclaw-calls.log"
: > "$STUB_LOG"

# The scratch build-state is pinned for EVERY build-workforce invocation via
# $WORKFORCE_BUILD_STATE_FILE (its _build_state_path override) so no code path
# can fall back to a live state file. DASHBOARD_DB_PATH is deliberately ABSENT.
RUN_ENV=(env "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw"
         "WORKFORCE_BUILD_STATE_FILE=$STATE")
CLIENT_ID="scratch-canary-co"
python3 - "$STATE" "$COMPANY" "$CLIENT_ID" <<'PYIDENTITY'
import json,sys
from pathlib import Path
state,root,identity=sys.argv[1:]
Path(state).write_text(json.dumps({'companyId':identity,'companySlug':'scratch-canary-co','companyRoot':root}))
Path(root,'company-config.json').write_text(json.dumps({'company_id':identity,'companySlug':'scratch-canary-co','name':'Scratch Canary Co'}))
PYIDENTITY

# ══ PHASE A: the prebuild (PHASE 2 driver) builds the fixture state ══
"${RUN_ENV[@]}" bash "$PREBUILD" \
  --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" \
  --company-name "Scratch Canary Co" --company-slug "scratch-canary-co" \
  --build-state-file "$STATE" --db "$DB" --apply --json \
  > "$TMP/prebuild.json" 2>"$TMP/prebuild.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "prebuild fixture ready (rc=0)"; else
  bad "prebuild fixture FAILED rc=$RC (see the log above)"; tail -5 "$TMP/prebuild.err" >&2; echo "ABORT"; exit 1; fi

# Model the supported Command Center archive migration in the isolated database.
python3 - "$DB" <<'PYDB'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    cols={r[1] for r in db.execute('PRAGMA table_info(workspaces)')}
    for name in ('archived_at','archived_reason','updated_at'):
        if name not in cols: db.execute('ALTER TABLE workspaces ADD COLUMN '+name+' TEXT')
PYDB

# ══ PHASE B: mock interview answers (genuine transcript for the gate) ══
DISCOVERY="$SANDBOX_HOME/.openclaw/workspace/company-discovery"
DISCOVERY2="$MASTER/company-discovery"
mkdir -p "$DISCOVERY" "$DISCOVERY2"
# Substance bar: verify_interview_complete requires >=3 **Q:** blocks AND
# >512 bytes — the answers must be substantive, exactly like a real interview.
{
  printf '# Workforce Interview Answers\n\nGenerated: August 4, 2026\n\n---\n\n'
  printf '**Q:** What is the name of your business?\n**A:** Scratch Canary Co\n\n---\n\n'
  printf '**Q:** What industry are you in?\n**A:** Professional Services — we run done-for-you operations for small businesses, covering their back office, their client communications, and their recurring reporting.\n\n---\n\n'
  printf '**Q:** What does your business do?\n**A:** We consult for small businesses and deliver done-for-you operations: we take over their scheduling, their invoicing, their client follow-up, and their weekly performance reporting, so the owner can focus on selling and delivery.\n\n---\n\n'
  printf '**Q:** What is your biggest challenge?\n**A:** Scaling delivery without hiring more people — every new client adds coordination overhead and we want the AI workforce to absorb the repetitive coordination so our human team stays on client-facing work.\n\n---\n\n'
} > "$DISCOVERY/workforce-interview-answers.md"
cp "$DISCOVERY/workforce-interview-answers.md" "$DISCOVERY2/workforce-interview-answers.md"

python3 - "$STATE" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s["interviewComplete"] = True
s["interviewCompletedAt"] = "2026-08-04T12:30:00Z"
s["interviewProgress"] = {"lastQuestionAt": "2026-08-04T12:30:00Z", "interviewComplete": True}
json.dump(s, open(p, "w"), indent=2)
PY

CONFIG="$TMP/apply-config.json"
cat > "$CONFIG" <<'JSON'
{
  "company_name": "Scratch Canary Co",
  "industry": "Professional Services",
  "company_description": "Done-for-you operations consulting",
  "tools": "Slack, Notion",
  "biggest_challenge": "Scaling delivery",
  "option": "A",
  "departments": {
    "listings": {
      "enabled": true,
      "name": "Listings Management",
      "activities": "Manage marketplace listings for clients",
      "kpis": "Listings refreshed weekly",
      "tools": "Marketplace tools",
      "challenges": "Keeping listings fresh"
    }
  }
}
JSON

# ══ STEP 1: the apply-diff build ══
"${RUN_ENV[@]}" python3 "$BW" --non-interactive --config-file "$CONFIG" \
  --apply-standard-edits > "$TMP/apply1.out" 2>"$TMP/apply1.err" < /dev/null
RC=$?
if [ "$RC" -eq 0 ]; then good "step 1: apply-diff build rc=0"; else
  bad "step 1: apply-diff build rc=$RC"; tail -12 "$TMP/apply1.err" >&2; echo "ABORT"; exit 1; fi

# ══ STEP 2: one resume fire, with the stub openclaw ══
env -u DASHBOARD_DB_PATH "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" \
  "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw" "WORKFORCE_BUILD_STATE_FILE=$STATE" \
  "PATH=$STUB_BIN:$PATH" \
  bash "$RESUME" > "$TMP/resume1.out" 2>"$TMP/resume1.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "step 2: resume fire rc=0"; else
  bad "step 2: resume fire rc=$RC"; tail -8 "$TMP/resume1.err" >&2; fi

# ══ STEP 3: the completion refresh (BU-57 presentation probe, not required) ══
"${RUN_ENV[@]}" env "QC_SKIP_PRESENTATION_DEPS=1" \
  python3 "$COMPLETION" "$STATE" --refresh > "$TMP/refresh1.out" 2>"$TMP/refresh1.err"
RC=$?
echo "  (refresh exit $RC)" >&2

python3 - "$STATE" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
verification = s.get("completionVerification") or {}
problems = []
if verification.get("status") != "verified":
    problems.append(f"completionVerification.status={verification.get('status')!r} unmet={verification.get('unmetRequirements')}")
if not s.get("buildCompletedAt"):
    problems.append("buildCompletedAt is absent")
depts = s.get("departments")
if not isinstance(depts, list) or not depts:
    problems.append("departments[] is absent or empty")
else:
    stuck = sorted(f"{(e.get('slug') or e.get('id'))}={e.get('status')}"
                   for e in depts if isinstance(e, dict) and e.get("status") in ("prebuilt", "pending"))
    if stuck:
        problems.append("departments not settled: " + ", ".join(stuck))
if s.get("commsAutomationStatus") != "deferred":
    problems.append(f"commsAutomationStatus={s.get('commsAutomationStatus')!r}")
print("PASS" if not problems else "FAIL: " + "; ".join(problems))
sys.exit(0 if not problems else 1)
PY
RC=$?
if [ "$RC" -eq 0 ]; then
  good "step 3: verified, buildCompletedAt set, no prebuilt/pending department, comms deferred"
else
  bad "step 3: the lane did not reach verified"
  python3 - "$STATE" <<'PY' >&2
import json, sys
s = json.load(open(sys.argv[1]))
print(json.dumps({"completionVerification": s.get("completionVerification"),
                  "buildCompletedAt": s.get("buildCompletedAt"),
                  "commsAutomationStatus": s.get("commsAutomationStatus"),
                  "departments": [(e.get("slug") or e.get("id"), e.get("status"))
                                  for e in (s.get("departments") or []) if isinstance(e, dict)]}, indent=2))
PY
fi

# ══ STEP 4: the apply-diff build a SECOND time ══
"${RUN_ENV[@]}" python3 "$BW" --non-interactive --config-file "$CONFIG" \
  --apply-standard-edits > "$TMP/apply2.out" 2>"$TMP/apply2.err" < /dev/null
RC=$?
if [ "$RC" -eq 0 ]; then good "step 4: second apply-diff build rc=0"; else
  bad "step 4: second apply-diff build rc=$RC"; tail -12 "$TMP/apply2.err" >&2; fi

python3 - "$COMPANY/company-config.json" "$CLIENT_ID" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
print("PASS" if cfg.get("company_id") == sys.argv[2] else
      f"FAIL: company_id={cfg.get('company_id')!r}, expected {sys.argv[2]!r}")
sys.exit(0 if cfg.get("company_id") == sys.argv[2] else 1)
PY
RC=$?
if [ "$RC" -eq 0 ]; then good "step 4: company-config.json still holds the company id"; else
  bad "step 4: the second build lost or changed the company id"; fi

# ══ STEP 5: the resume job once more — the state is still verified ══
env -u DASHBOARD_DB_PATH "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" \
  "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw" "WORKFORCE_BUILD_STATE_FILE=$STATE" \
  "PATH=$STUB_BIN:$PATH" \
  bash "$RESUME" > "$TMP/resume2.out" 2>"$TMP/resume2.err"
RC=$?
echo "  (second resume exit $RC)" >&2

python3 - "$STATE" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
verification = s.get("completionVerification") or {}
ok = (verification.get("status") == "verified"
      and bool(s.get("buildCompletedAt"))
      and s.get("commsAutomationStatus") == "deferred")
print("PASS" if ok else
      f"FAIL: still-verified check got status={verification.get('status')!r} "
      f"buildCompletedAt={s.get('buildCompletedAt')!r} "
      f"commsAutomationStatus={s.get('commsAutomationStatus')!r}")
sys.exit(0 if ok else 1)
PY
RC=$?
if [ "$RC" -eq 0 ]; then good "step 5: a later resume fire leaves the state verified"; else
  bad "step 5: a later resume fire un-verified the state"; fi

echo "=============================================="
echo "test-standard-first-reaches-verified.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
