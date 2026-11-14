#!/usr/bin/env bash
# test-standard-first-reaches-verified.sh — BU-110 (closes WF-129, part 1).
#
# Pins the standard-first lane all the way to a finished company: a prebuilt
# company, taken through the apply-diff build and ONE resume fire, reaches
# completionVerification.status == "verified" with buildCompletedAt set, no
# department entry left "prebuilt" or "pending", and the Skill 38 handoff
# recorded as "deferred" (BU-54) instead of holding the build open.
#
# The sandbox and PHASE A are the ones test-build-standard-first-
# roundtrip.sh already uses; the deliberate differences are the point:
#   * commsAutomationStatus is NOT pre-written — the resume job records the
#     deferral itself (BU-54), which is exactly what the assertion reads;
#   * the interview completes through the real --complete evidence gate, not
#     a hand-set flag — the resume QC lane keys off interviewQc;
#   * the board assertions resolve through the scratch board file (seeded by
#     the prebuild, reseeded after the vertical adds): the ZHE prover needs a
#     database to check, and a hermetic test must hand it its own sandbox
#     file, never a live box's database.
#
# Steps:
#   1. prebuild (PHASE 2 driver) + mock interview answers + --complete gate +
#      apply-diff build
#   2. one resume-workforce-build.sh fire, with a stub `openclaw` on PATH
#   3. library closeout (author-missing-sops deterministic fill), then
#      workforce_completion.py <state> --refresh (the BU-57 presentation probe
#      runs as its own non-required check; the qc check skips the same block)
#      -> assert verified, buildCompletedAt present, no prebuilt/pending
#         department, commsAutomationStatus == "deferred"
#   4. record the vertical-added departments' provenanced yes decisions, then
#      the apply-diff build a SECOND time -> rc 0 and company-config.json still
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
# can fall back to a live state file. DASHBOARD_DB_PATH points at the scratch
# board database the prebuild seeds; the ZHE prover resolves the board through
# that variable, exactly like a live box's own configured database.
# STANDARD_FIRST_ONBOARDING=1 arms the rollback flag the prebuild driver
# requires (a live box carries it in the operator environment; the sibling
# prebuild tests export the same flag).
export STANDARD_FIRST_ONBOARDING=1
# Persona corpus for the ZHE prover: the repo's shipped canonical roster
# (22-book-to-persona-coaching-leadership-system/persona-categories.json,
# the same file the sibling persona-selector tests seed from) plus one empty
# personadir per roster entry and a section-level fixture index, built the way
# gemini-section-indexer.py builds it (one row per ## section, mode + section
# tagged). The fixture plants the corpus the installer lays down on a live box;
# nothing here weakens the prover, which reads the sandbox corpus read-only.
PERSONA_CATS="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/persona-categories.json"
RUN_ENV=(env "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw"
         "WORKFORCE_BUILD_STATE_FILE=$STATE" "STANDARD_FIRST_ONBOARDING=1"
         "DASHBOARD_DB_PATH=$DB")
CLIENT_ID="scratch-canary-co"
setup_persona_corpus() {
  local cats="$1" dest="$2"
  mkdir -p "$dest/personas"
  cp "$cats" "$dest/persona-categories.json"
  python3 - "$cats" "$dest/personas" <<'PYPERSONAS'
import json, sqlite3, sys
from pathlib import Path
cats, pdir = Path(sys.argv[1]), Path(sys.argv[2])
d = json.load(open(cats))
names = sorted((d.get("personas") or {}).keys())
for n in names:
    (pdir / n).mkdir(parents=True, exist_ok=True)
    (pdir / n).joinpath("persona-blueprint.md").write_text(
        "# %s\n\n## Role\nFixture persona stub for %s.\n\n## Method\nStub section.\n\n"
        "## Evidence\nStub section.\n\n## Cadence\nStub section.\n\n## Failure Modes\nStub section.\n" % (n, n))
con = sqlite3.connect(str(Path(sys.argv[2]).parent / "gemini-index.sqlite"))
con.execute("CREATE TABLE IF NOT EXISTS embeddings (id INTEGER PRIMARY KEY, persona_id TEXT, persona TEXT, mode TEXT, section_number INTEGER, content TEXT)")
con.execute("DELETE FROM embeddings")
for i, n in enumerate(names):
    for k in range(1, 6):
        con.execute("INSERT INTO embeddings (persona_id, persona, mode, section_number, content) VALUES (?,?,?,?,?)",
                    (n, n, "both", k, "## Section %d of %s" % (k, n)))
con.commit()
print("personas=%d rows=%d" % (len(names), con.execute("SELECT count(*) FROM embeddings").fetchone()[0]))
con.close()
PYPERSONAS
}
setup_persona_corpus "$PERSONA_CATS" "$SANDBOX_HOME/.openclaw/workspace/data/coaching-personas"
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

# A standard-first edit-mode interview: 4 substantive **Q:** blocks (the
# verify_interview_complete substance bar: >=3 blocks, >512 bytes) PLUS the
# 8-question owner review of the prebuilt set. The review answers are
# time-bearing (lastQuestionAt) and the state carries the buildType +
# standardPrebuild the edit-mode exemption requires — the same shape the
# evidence-gate battery's R6 case pins. The transcript is planted in BOTH
# discovery dirs so the gate, the QC writer and the build all resolve it.
#
# SEPARATOR LAYOUT IS LOAD-BEARING. qc-interview-completion.py's check #1 does
# not recognise the canonical "**Q:**" line (its raw-count regexes match the
# colonless "**Q**" form), so for a **Q:**-only transcript it falls back to
# counting "---" separator lines as Q/A blocks. build-workforce.py's
# log_answer() and every sibling fixture write exactly ONE separator per
# block, so the fallback reads the real block count. Plant a doubled
# separator (a trailing "---" plus the next block's leading "---") and the
# same 12 blocks read as 16 — a fixture-side count that trips the
# lastQuestionNumber disagreement gate (>3) and refuses completion with 87.
DISCOVERY="$SANDBOX_HOME/.openclaw/workspace/company-discovery"
DISCOVERY2="$MASTER/company-discovery"
mkdir -p "$DISCOVERY" "$DISCOVERY2"
python3 - "$DISCOVERY/workforce-interview-answers.md" <<'PYTRANSCRIPT'
import sys
p = sys.argv[1]
lines = ['# Workforce Interview Answers', '', 'Generated: August 4, 2026', '']
qa = [
("What is the name of your business?", "Scratch Canary Co"),
("What industry are you in?", "We run done-for-you operations for small businesses, covering back office, client communications, and recurring reporting."),
("What does your business do?", "We consult for small businesses and deliver done-for-you operations: scheduling, invoicing, client follow-up, weekly performance reporting."),
("What is your biggest challenge?", "Scaling delivery without hiring more people; absorb recurring coordination with the AI workforce."),
]
# ONE "---" per block, the layout log_answer() writes and the sibling fixtures
# use: the counter's separator fallback then reads 12 for 12 blocks, not 16.
for q, a in qa:
    lines += ['---', '', '**Q:** ' + q, '**A:** ' + a, '']
for i in range(1, 9):
    lines += ['---', '', '**Q:** Review question %d: walk through department %d with me - keep, tune, or remove?' % (i, i),
              '**A:** A real owner answer for question %d: keep this department and focus it on our core service line and main offer.' % i, '', '']
open(p, 'w').write('\n'.join(lines))
PYTRANSCRIPT
cp "$DISCOVERY/workforce-interview-answers.md" "$DISCOVERY2/workforce-interview-answers.md"

# The edit-mode fixture state: the prebuild wrote standardPrebuild done; the
# owner now reviews the prebuilt set on a standard-first box.
python3 - "$STATE" <<'PYEDITSTATE'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s["interviewComplete"] = False
s["buildType"] = "standard-first"
s["standardPrebuild"] = {"status": "done", "standardReadyAt": "2026-08-04T09:00:00Z", "agentRegistration": "deferred"}
s["ownerChat"] = 9999999999
s["ownerName"] = "Test Owner"
s["companyName"] = "TestCo LLC"
s["industry"] = "personal-pro-dev"
s["agentName"] = "TestCEO"
s["brand_evokes"] = "confident"
s["customer_feeling"] = "empowered"
s["brand_descriptors"] = "bold, direct, warm"
s["ideal_customer"] = "Black women entrepreneurs over 40"
s["unique_differentiator"] = "We build what big agencies ignore"
s["departments"] = [{"slug": "marketing", "status": "pending"}]
# Counter rule (R4/R4b): the state counter must never claim MORE than the
# transcript holds. The transcript carries 4 substantive intake blocks plus
# 8 review blocks = 12 Q-blocks, and one "---" separator each, so the gate's
# separator fallback reads 12; the counter records 12, exactly in sync.
s["interviewProgress"] = {"lastQuestionNumber": 12, "lastQuestionPhase": "phase5.5", "lastQuestionAskedBy": "TestCEO", "lastQuestionAt": "2026-08-04T10:00:00Z"}
json.dump(s, open(p, "w"), indent=2)
PYEDITSTATE

# Complete through the REAL evidence gate. update-interview-state.sh --complete
# is the entry the web route calls: it runs the gate (refuses thin/fabricated
# interviews with exit 87) and on pass writes interviewComplete + interviewQc.
# A hand-set flag would never exercise the gate, and the resume QC lane keys
# off interviewQc. Hermetic: DASHBOARD_DB_PATH / DATABASE_PATH are cleared so
# the completion's database mirror can never touch a host database, and the
# openclaw CLI stays the stub (the build-kick dispatch records its call only).
UPD="$SCRIPT_DIR/update-interview-state.sh"
( unset DASHBOARD_DB_PATH DATABASE_PATH; HOME="$SANDBOX_HOME" SHIM_LOG="$STUB_LOG" PATH="$STUB_BIN:$PATH" bash "$UPD" --complete ) > "$TMP/complete.out" 2>&1
RC=$?
if [ "$RC" -eq 0 ]; then good "complete: real evidence gate passes the edit-mode interview (rc=0)"; else
  bad "complete: real evidence gate FAILED rc=$RC"; tail -8 "$TMP/complete.out" >&2; echo "ABORT"; exit 1; fi
python3 - "$STATE" <<'PYCOMPLETECHECK'
import json, sys
s = json.load(open(sys.argv[1]))
qc = s.get("interviewQc") or {}
ok = s.get("interviewComplete") is True and qc.get("status") == "pass" and (qc.get("editModeExemption") or {}).get("granted") is True
print("PASS" if ok else "FAIL: interviewQc=%r" % (qc,))
sys.exit(0 if ok else 1)
PYCOMPLETECHECK
RC=$?
if [ "$RC" -eq 0 ]; then good "complete: interviewComplete=true, interviewQc=pass, edit-mode exemption granted"; else
  bad "complete: state missing the gated completion"; echo "ABORT"; exit 1; fi

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
# DASHBOARD_DB_PATH is scrubbed from this fire: the resume must prove it
# advances the lane without depending on a live Command Center database in
# its environment (the company tree is followed through companyRoot, BU-102).
# The board assertions resolve through the scratch board file in step 3.
env -u DASHBOARD_DB_PATH "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" \
  "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw" "WORKFORCE_BUILD_STATE_FILE=$STATE" \
  "PATH=$STUB_BIN:$PATH" "STANDARD_FIRST_ONBOARDING=1" \
  bash "$RESUME" > "$TMP/resume1.out" 2>"$TMP/resume1.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "step 2: resume fire rc=0"; else
  bad "step 2: resume fire rc=$RC"; tail -8 "$TMP/resume1.err" >&2; fi

# ══ STEP 2b: library closeout for the hermetic fixture ══
# The resume materializes roles from the role library; roles with no matching
# template are routed to general-task with an open SOP-NEEDED record, and the
# library gate fails while any record is open. A live box closes them through
# the authoring lane; the fixture closes them here with the repo's own
# author-missing-sops.finalize_record (QC-gated, provenance-stamped,
# harvested), filled from the box's own role-library templates — every record
# carries authored_via=test-fixture-library-fill naming the template. Records
# with no comparable library template are reported, not guessed: the fixture
# aborts, because those need the live authoring lane.
# OPENCLAW_PLATFORM=mac: the helper resolves the platform the way the repo
# sibling tests do (no live /data/.openclaw or ~/clawd inside the sandbox).
OPENCLAW_PLATFORM=mac python3 "$SCRIPT_DIR/finalize-test-fixture-libraries.py" "$SCRIPT_DIR" "$SKILL_DIR" "$COMPANY/SOP-NEEDED.json" > "$TMP/finalize-lib.out" 2>&1
RC=$?
if [ "$RC" -eq 0 ]; then good "step 2b: SOP-NEEDED records all authored from the role library"; else
  bad "step 2b: library closeout FAILED rc=$RC"; tail -6 "$TMP/finalize-lib.out" >&2; echo "ABORT"; exit 1; fi

# ══ STEP 2c: workspace doctrine + board reseed for the ZHE prover ══
# The ZHE prover holds an interview-completed box to the full sequence:
# personas (seeded above), a live board with every department lane, and a
# WORKSPACE/AGENTS.md carrying the five doctrine elements the prover greps
# for (routing, persona reflex, full-context handoff, owner reporting,
# platform facts — the markers the fleet stampers write on a live box). The
# fixture writes the same elements; the prover's patterns, not this file,
# decide the verdict.
cat > "$SANDBOX_HOME/.openclaw/workspace/AGENTS.md" <<'EOFAGENTS'
# Scratch Canary Co — Workspace Operating Doctrine (test fixture)

<!-- CEO_ORCHESTRATOR_RULE_V2 -->
Route the task to the right department: the CEO orchestrator assigns every
inbound task to exactly one owning department and never works two lanes at once.

<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->
No loopholes: a task without an owning department is refused, never absorbed.

<!-- PERSONA_REFLEX_V1 -->
Before responding to any task, run the persona-reflex: persona-matching
selects the governing persona for the task's department and records the choice.

<!-- FULL_CONTEXT_HANDOFF_V1 -->
Every handoff carries the full-context handoff: pointer references name where
the documentation lives, so the next agent resumes with the full context.

<!-- OWNER_REPORTING_V1 -->
Reporting to the owner: every finished build reports back to the owner with
receipts, never bare claims.

<!-- PLATFORM_FACTS_V1 -->
Platform facts: here is WHERE your environments file lives for this box, and
which values are box-local versus shared.
EOFAGENTS
# The board live-check (prove-zhe.py resolve_cc_db) probes the sandbox CC app
# dir layout candidate and the DASHBOARD_DB_PATH variable: keep the scratch
# seeded board visible at BOTH, so the check passes with or without the host
# exporting a database path.
mkdir -p "$SANDBOX_HOME/projects/command-center"
cp "$DB" "$SANDBOX_HOME/projects/command-center/mission-control.db"
# The ZHE prover discovers built departments from the roots
# materialize-dept-agents.sh also scans — <oc_root>/workspace/departments
# first. The canonical home for the built tree is
# master-files/zero-human-company/<company>/departments (PRD 1.9, see
# migrate-zhc-to-master-files.sh), which the prover does not scan, so expose
# the SAME tree at that first root with a link: one tree, no copy drift, and
# the prover proves the department folders and agent rows the build actually
# wrote.
[ -e "$SANDBOX_HOME/.openclaw/workspace/departments" ] || \
  ln -s "$COMPANY/departments" "$SANDBOX_HOME/.openclaw/workspace/departments"

# ══ STEP 3: reseed the board, then the completion refresh ══
# The first apply added the industry vertical-pack departments AFTER the
# prebuild seeded the board, so the new lanes are missing until the repo's own
# seed-workspaces.py runs again against the scratch database (a live box
# re-seeds through the same seeder). Then the refresh: the BU-57 presentation
# probe runs as its own non-required check; the qc check skips the same block.
# DASHBOARD_DB_PATH stays set here (unlike step 2): the ZHE prover resolves
# the board through that variable, exactly like a live box's own database.
# The seeder discovers the board through DASHBOARD_DB_PATH (shared resolver
# order) and the company through MASTER_FILES_DIR: run it with both pinned to
# the sandbox so it reseeds the scratch board, never a host database.
DASHBOARD_DB_PATH="$DB" MASTER_FILES_DIR="$MASTER" python3 "$REPO_ROOT/32-command-center-setup/scripts/seed-workspaces.py" > "$TMP/reseed.out" 2>&1
RC=$?
if [ "$RC" -eq 0 ]; then good "step 3: board reseeded with the vertical-added lanes"; else
  bad "step 3: board reseed FAILED rc=$RC"; tail -6 "$TMP/reseed.out" >&2; echo "ABORT"; exit 1; fi
cp "$DB" "$SANDBOX_HOME/projects/command-center/mission-control.db"
# Refresh the library gate: the fixture closed the SOP-NEEDED records after
# the resume materialized the roles, so this refresh — the same
# verify-library-gate.sh the resume and the apply build invoke — re-measures
# the tree and stamps roleLibraryStatus/sopLibraryStatus done into the state.
# (The resume only READS those fields; it never re-measures them.)
"${RUN_ENV[@]}" bash "$SCRIPT_DIR/verify-library-gate.sh" > "$TMP/gate1.out" 2>&1
RC=$?
if [ "$RC" -eq 0 ]; then good "step 3: library gate passes (role + SOP libraries done)"; else
  bad "step 3: library gate FAILED rc=$RC"; tail -6 "$TMP/gate1.out" >&2; echo "ABORT"; exit 1; fi
# Second resume fire: the first fire ran while the libraries were dirty, so
# only the gate refresh (step 2b) has since turned them clean — this fire is
# the first one that evaluates the comms deferral and the closeout stamp on a
# clean library state, exactly like the next 15-minute tick on a live box.
env "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" \
  "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw" "WORKFORCE_BUILD_STATE_FILE=$STATE" \
  "PATH=$STUB_BIN:$PATH" "STANDARD_FIRST_ONBOARDING=1" \
  "DASHBOARD_DB_PATH=$DB" \
  bash "$RESUME" > "$TMP/resume1b.out" 2>"$TMP/resume1b.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "step 3: second resume fire rc=0 (clean-library tick)"; else
  bad "step 3: second resume fire rc=$RC"; tail -8 "$TMP/resume1b.err" >&2; fi
# Gate-failure forensics: when the refresh refuses verified, print the
# library-gate verdict line (which sub-gate failed and why) plus the three
# state fields the refresh evaluates, so a RED run names its blocker instead
# of only printing the unmet list.
print_gate_forensics() {
  grep -h "verify-library-gate.*gaps" "$TMP/refresh1.err" 2>/dev/null | head -2
  python3 - "$STATE" "$COMPANY/SOP-NEEDED.json" <<'PYGATEDEBUG'
import json, sys
s = json.load(open(sys.argv[1]))
print("gate-forensics roleLib=%r sopLib=%r comms=%r closeout=%r" % (s.get("roleLibraryStatus"), s.get("sopLibraryStatus"), s.get("commsAutomationStatus"), s.get("closeoutStatus")))
try:
    d = json.load(open(sys.argv[2]))
    print("gate-forensics sop-needed open=%r total=%d" % (d.get("open_count"), len(d.get("records", []))))
    for r in d.get("records", []):
        if r.get("status") != "authored":
            print("gate-forensics STILL OPEN %s %s (%s)" % (r.get("id"), r.get("role"), r.get("department")))
except OSError as e:
    print("gate-forensics sop-needed unreadable: %s" % (e,))
PYGATEDEBUG
}
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
  print_gate_forensics >&2
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

# ══ STEP 4: record the vertical adds' decisions, then re-run the build ══
# The first apply records the industry vertical-pack additions as recorded
# adds; the decision-coverage gate requires a provenanced yes/no/later for
# every recorded add before the floor is rebuilt. A live owner records those
# in the Phase 5.5 review; the fixture records yes for each vertical-added
# department with the repo's own record-dept-decision.sh (owner-interview
# source), then re-runs the build and asserts exit 0 plus identity survival.
python3 - "$STATE" <<'PYVPACKDECISIONS'
import json, subprocess, sys
state_path = sys.argv[1]
s = json.load(open(state_path))
adds = [d.get("id") for d in ((s.get("verticalPacks") or {}).get("addedDepartments") or []) if isinstance(d, dict) and d.get("id")]
print("vertical adds needing decisions: %s" % (adds,))
sys.exit(0)
PYVPACKDECISIONS
for _vdid in $(python3 -c "import json,sys; s=json.load(open('$STATE')); print(' '.join(d.get('id') for d in ((s.get('verticalPacks') or {}).get('addedDepartments') or []) if isinstance(d, dict) and d.get('id')))"); do
  if ! HOME="$SANDBOX_HOME" WORKFORCE_BUILD_STATE_FILE="$STATE" bash "$SCRIPT_DIR/record-dept-decision.sh" --dept "$_vdid" --decision yes --source owner-interview --by test-owner --session sess-test --state "$STATE" >> "$TMP/decisions.out" 2>&1; then
    python3 - "$STATE" "$_vdid" <<'PYSEEDDECISION' >> "$TMP/decisions.out" 2>&1
import json, sys
p, did = sys.argv[1], sys.argv[2]
s = json.load(open(p))
dec = s.setdefault("canonicalReconciliation", {}).setdefault("decisions", {})
# Industry-extra ids are not canonical-floor members, so the recorder (which
# only accepts canonical + recorded-custom ids) refuses them; seed the same
# provenanced shape the recorder writes for canonical ids. The shared reader
# enforces provenance identically for seeded and recorded decisions.
dec[did] = {"decision": "yes", "source": "owner-interview", "decidedAt": "2026-08-04T12:29:00Z", "decidedBy": "test-owner", "sessionId": "sess-test"}
json.dump(s, open(p, "w"), indent=2)
print("seeded provenanced yes for industry-extra %s" % (did,))
PYSEEDDECISION
  fi
done
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
# The board database stays visible here (DASHBOARD_DB_PATH pinned to the
# scratch board): a live box's resume fire always runs with its own database
# configured, and the ZHE board lane is only checkable while it resolves.
env "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" \
  "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw" "WORKFORCE_BUILD_STATE_FILE=$STATE" \
  "PATH=$STUB_BIN:$PATH" "STANDARD_FIRST_ONBOARDING=1" \
  "DASHBOARD_DB_PATH=$DB" \
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
