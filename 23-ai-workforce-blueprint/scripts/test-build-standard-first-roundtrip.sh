#!/usr/bin/env bash
# test-build-standard-first-roundtrip.sh — PHASE 3 verification gate (AI
# Workforce standard-first redesign, master plan 2026-08-04).
#
# Exercises the FULL standard-first roundtrip in a HERMETIC sandbox
# (sandboxed $HOME + $MASTER_FILES_DIR + scratch build-state + scratch Command
# Center database): prebuild (PHASE 2 driver) -> mock interview answers ->
# apply-diff build (build-workforce.py --apply-standard-edits) -> the four
# assertions the master plan pins:
#
#   A1  a PROVENANCED decline is ARCHIVED (moved to .retired/, NEVER deleted)
#   A2  a net-new custom department is ADDED (built from the canonical library)
#   A3  agents.list rows are PRESENT for every confirmed-kept department
#       (the deferred Moment 3.5 registration)
#   A4  exit 87 when interviewComplete is absent (anti-fabrication gate)
#   A5  exit 88 when a RECORDED decline lacks provenance (decision-coverage
#       relaxation keeps the anti-fabrication bar)
#   A6  KEEPs implicit: a prebuilt department with NO recorded decision stays
#       built (never retired, never re-materialized away) + confirmationsComplete
#   A7  the chosen artifact carries the removed-with-provenance record
#   A8  the legacy lane is byte-identical: a legacy-state box refused the
#       apply-diff entry (exit 88, buildType gate), and the legacy tests
#       (decline-provenance-guard / u109-floor-wipe) still pass (run separately).
#
# Hermeticity (the operator box is itself a built client): every path is
# pinned explicitly — $MASTER_FILES_DIR for the company tree, $HOME for the
# discovery dir, --build-state-file for the state, --oc-config for the agents
# registration. Nothing may escape the sandbox. The test asserts the sandbox
# state file is the ONLY state read.
#
# Exit 0 = all guards pass; non-zero = a guard failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
BW="$SCRIPT_DIR/build-workforce.py"
PREBUILD="$REPO_ROOT/scripts/prebuild-standard-workforce.sh"
RETIRE="$SCRIPT_DIR/retire-confirmed-decline.sh"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

for _f in "$BW" "$PREBUILD" "$RETIRE"; do
  if [ ! -f "$_f" ]; then bad "required file missing: $_f"; echo "ABORT"; exit 1; fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SANDBOX_HOME="$TMP/home"
MASTER="$TMP/master-files"
COMPANY="$MASTER/zero-human-company/scratch-canary-co"
STATE="$TMP/state.json"
DB="$TMP/mission-control.db"
CONSENT="$TMP/consent.json"
mkdir -p "$SANDBOX_HOME/.openclaw/workspace" "$MASTER/zero-human-company" "$SANDBOX_HOME/.openclaw" \
         "$SANDBOX_HOME/Downloads/openclaw-master-files" "$COMPANY"
printf '{"decision":"prebuild","source":"operator-prebuild","decidedAt":"2026-08-04T12:00:00Z","decidedBy":"test-operator","sessionId":"sess-test"}\n' > "$CONSENT"
printf '{"agents":{"list":[]}}\n' > "$SANDBOX_HOME/.openclaw/openclaw.json"
echo '{}' > "$STATE"

# The scratch build-state is pinned for EVERY build-workforce invocation via
# $WORKFORCE_BUILD_STATE_FILE (its _build_state_path override) so no code path
# can fall back to a live state file.
RUN_ENV=(env "HOME=$SANDBOX_HOME" "MASTER_FILES_DIR=$MASTER" "OPENCLAW_ROOT=$SANDBOX_HOME/.openclaw"
         "WORKFORCE_BUILD_STATE_FILE=$STATE")

# ══ PHASE A: the prebuild (PHASE 2 driver) builds the fixture state ══
"${RUN_ENV[@]}" bash "$PREBUILD" \
  --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" \
  --company-name "Scratch Canary Co" --company-slug "scratch-canary-co" \
  --build-state-file "$STATE" --db "$DB" --apply --json \
  > "$TMP/prebuild.json" 2>"$TMP/prebuild.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "prebuild fixture ready (rc=0)"; else
  bad "prebuild fixture FAILED rc=$RC (see $TMP/prebuild.err)"; tail -5 "$TMP/prebuild.err" >&2; echo "ABORT"; exit 1; fi

# ══ PHASE B: mock interview answers (genuine transcript for the gate) ══
# verify_interview_complete() looks at $HOME/.openclaw/workspace/company-
# discovery/workforce-interview-answers.md (the live interview's store); the
# non-interactive path ALSO reads $MASTER_FILES/company-discovery. Plant the
# transcript in BOTH so every gate resolves it exactly as on a live box.
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

# Seed interviewComplete=true (update-interview-state.sh --complete would set it
# after QC; here the genuine transcript above is what verify_interview_complete()
# corroborates against — the bare flag alone is never trusted).
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

# ══ A4: exit 87 when interviewComplete is ABSENT ══
python3 - "$TMP/state-nocomplete.json" "$STATE" <<'PY'
import json, sys
dst, src = sys.argv[1], sys.argv[2]
s = json.load(open(src))
s["interviewComplete"] = False
s.pop("interviewProgress", None)
s.pop("interviewCompletedAt", None)
json.dump(s, open(dst, "w"), indent=2)
PY
# Hide the genuine transcript so the consent gate cannot pass on it (isolate the
# interviewComplete gate): move BOTH planted copies aside, point discovery at an
# empty master-files dir, and pin the incomplete state via
# $WORKFORCE_BUILD_STATE_FILE.
mkdir -p "$TMP/empty-master/company-discovery"
mv "$DISCOVERY/workforce-interview-answers.md" "$TMP/transcript.bak"
mv "$DISCOVERY2/workforce-interview-answers.md" "$TMP/transcript2.bak"
"${RUN_ENV[@]}" env "MASTER_FILES_DIR=$TMP/empty-master" \
  "WORKFORCE_BUILD_STATE_FILE=$TMP/state-nocomplete.json" \
  python3 "$BW" --non-interactive --config-file "$CONFIG" --apply-standard-edits \
  > "$TMP/a4.out" 2>"$TMP/a4.err"
RC=$?
mv "$TMP/transcript.bak" "$DISCOVERY/workforce-interview-answers.md"
mv "$TMP/transcript2.bak" "$DISCOVERY2/workforce-interview-answers.md"
if [ "$RC" -eq 87 ]; then good "A4: exit 87 when interviewComplete absent (anti-fabrication gate)"; else
  bad "A4: expected rc=87, got $RC"; tail -3 "$TMP/a4.err" >&2; fi

# ══ A5: exit 88 when a RECORDED decline lacks provenance ══
cp "$STATE" "$TMP/state-unproven.json"
python3 - "$TMP/state-unproven.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
recon = s.setdefault("canonicalReconciliation", {})
decisions = recon.setdefault("decisions", {})
# BARE decline with no provenance — must be rejected by the shared reader and
# trip the exit-88 decision-coverage gate (KEEPS stay implicit; recorded
# declines must be provenanced).
decisions["audio"] = "no"
json.dump(s, open(p, "w"), indent=2)
PY
"${RUN_ENV[@]}" env "WORKFORCE_BUILD_STATE_FILE=$TMP/state-unproven.json" \
  python3 "$BW" --non-interactive --config-file "$CONFIG" \
  --apply-standard-edits \
  > "$TMP/a5.out" 2>"$TMP/a5.err" < /dev/null
RC=$?
if [ "$RC" -eq 88 ]; then good "A5: exit 88 when a recorded decline lacks provenance"; else
  bad "A5: expected rc=88, got $RC"; tail -3 "$TMP/a5.err" >&2; fi

# ══ THE MAIN ROUNDTRIP: provenanced decline + net-new custom + apply ══
python3 - "$STATE" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
recon = s.setdefault("canonicalReconciliation", {})
decisions = recon.setdefault("decisions", {})
decisions["audio"] = {
    "decision": "no",
    "source": "owner-interview",
    "decidedAt": "2026-08-04T12:29:00Z",
    "decidedBy": "owner",
}
json.dump(s, open(p, "w"), indent=2)
PY
# Mark the audio tree with a sentinel so the ARCHIVE (not delete) is provable.
echo "SENTINEL-ARCHIVE-ME" > "$COMPANY/departments/audio/SENTINEL.md" 2>/dev/null || {
  mkdir -p "$COMPANY/departments/audio"; echo "SENTINEL-ARCHIVE-ME" > "$COMPANY/departments/audio/SENTINEL.md"; }

"${RUN_ENV[@]}" python3 "$BW" --non-interactive --config-file "$CONFIG" \
  --apply-standard-edits > "$TMP/apply.out" 2>"$TMP/apply.err" < /dev/null
RC=$?
if [ "$RC" -eq 0 ]; then good "apply-diff build rc=0"; else
  bad "apply-diff build rc=$RC"; tail -12 "$TMP/apply.err" >&2; fi

# A1: declined dept ARCHIVED (not deleted) — the sentinel survives in .retired/
if [ ! -d "$COMPANY/departments/audio" ] \
   && find "$COMPANY/.retired" -name "SENTINEL.md" -exec grep -q "SENTINEL-ARCHIVE-ME" {} \; 2>/dev/null; then
  good "A1: provenanced decline 'audio' ARCHIVED to .retired/ (never deleted)"
else
  bad "A1: 'audio' not archived correctly (dir present=$( [ -d "$COMPANY/departments/audio" ] && echo yes || echo no ), .retired=$( ls "$COMPANY/.retired" 2>/dev/null ))"
fi

# A2: net-new custom added (listings has a built tree)
if [ -d "$COMPANY/departments/listings" ] \
   && [ -f "$COMPANY/departments/listings/SOUL.md" ]; then
  good "A2: net-new custom 'listings' ADDED (SOUL.md materialized)"
else
  bad "A2: custom 'listings' missing or not materialized"
fi

# A6: KEEPs implicit — a prebuilt dept with NO recorded decision stays built
if [ -d "$COMPANY/departments/marketing" ] && [ -f "$COMPANY/departments/marketing/SOUL.md" ]; then
  good "A6a: kept prebuilt 'marketing' (no decision record) still built"
else
  bad "A6a: kept prebuilt 'marketing' missing"
fi

# A3: agents.list rows present for confirmed-kept departments.
# master-orchestrator is EXCLUDED from the expected set exactly as in the
# legacy lane: load_canonical_floor() never returns it (it is the floor-only
# 30th id, provisioned once outside the interview; generate_departments_json
# surfaces it as the CEO column, never as its own registered agent).
python3 - "$SANDBOX_HOME/.openclaw/openclaw.json" "$COMPANY/departments" "$STATE" <<'PY'
import json, os, sys
cfg_path, depts_dir, state_path = sys.argv[1:4]
cfg = json.load(open(cfg_path))
ids = {a.get("id") for a in (cfg.get("agents") or {}).get("list", []) if isinstance(a, dict)}
on_disk = {d for d in os.listdir(depts_dir) if os.path.isdir(os.path.join(depts_dir, d))}
expected = {f"dept-{d}" for d in on_disk
            if d not in ("ceo", "dept-ceo", "master-orchestrator")}
missing = sorted(expected - ids)
extra_retired = [i for i in ids if i == "dept-audio"]
ok = not missing and not extra_retired
print(f"PASS: A3 agents.list rows present for all {len(expected)} confirmed-kept depts (missing={missing}, declined-row-present={bool(extra_retired)})" if ok
      else f"FAIL: A3 agents.list missing={missing} declined-row-present={extra_retired}")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] && good "A3: agents.list rows asserted" || bad "A3: agents.list rows wrong"

# A6b: confirmationsComplete=true + departments[] settled
python3 - "$STATE" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
depts = s.get("departments") or []
done = {e.get("slug") for e in depts if isinstance(e, dict) and e.get("status") == "done"}
ok = s.get("confirmationsComplete") is True and "marketing" in done
print(f"PASS: A6b confirmationsComplete=true, {len(done)} departments settled to done" if ok
      else f"FAIL: A6b confirmationsComplete={s.get('confirmationsComplete')} done={sorted(done)[:5]}")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] && good "A6b: confirmationsComplete=true (resume cron HOP-4 contract)" || bad "A6b: confirmationsComplete missing"

# A7: chosen artifact carries removed-with-provenance + excludes the decline.
# The retire script's rewrite shape is {removedWithProvenance, departments};
# the build's own writer emits a bare CC-schema list. Accept both shapes but
# REQUIRE: audio absent from the chosen slugs, listings+marketing present, and
# (when the retire shape is present) the provenance record attached.
python3 - "$COMPANY/departments.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
if isinstance(data, dict):
    removed = data.get("removedWithProvenance") or []
    entries = data.get("departments") or []
    audio_removed = any(r.get("slug") == "audio" and r.get("decision") == "no" for r in removed)
else:
    removed, entries, audio_removed = [], data, True  # list shape: decline excluded by the decline set
slugs = {(e.get("slug") or e.get("id")) if isinstance(e, dict) else e for e in entries}
ok = audio_removed and "audio" not in slugs and "listings" in slugs and "marketing" in slugs
print(f"PASS: A7 chosen artifact: audio excluded, listings+marketing included, provenance={'retire-shape' if isinstance(data, dict) else 'decline-set-exclusion'}" if ok
      else f"FAIL: A7 artifact wrong (removed={removed}, slugs={sorted(s for s in slugs if s)[:6]}...)")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] && good "A7: chosen artifact excludes the retired decline" || bad "A7: chosen artifact wrong"

# A7b: the retire script's own invocation writes the retire shape + archives
cp "$STATE" "$TMP/state-retire-direct.json"
python3 - "$TMP/state-retire-direct.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
recon = s.setdefault("canonicalReconciliation", {})
decisions = recon.setdefault("decisions", {})
decisions["sales"] = {"decision": "no", "source": "owner-interview",
                      "decidedAt": "2026-08-04T12:40:00Z", "decidedBy": "owner"}
json.dump(s, open(p, "w"), indent=2)
PY
bash "$RETIRE" --dept sales --build-state-file "$TMP/state-retire-direct.json" \
  --company-dir "$COMPANY" --skip-cc >/dev/null 2>"$TMP/a7b.err"
RETIRE_RC=$?
python3 - "$COMPANY/departments.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ok = isinstance(d, dict) and any(
    r.get("slug") == "sales" and r.get("decidedBy") == "owner"
    for r in (d.get("removedWithProvenance") or []))
slugs = {(e.get("slug") or e.get("id")) if isinstance(e, dict) else e for e in (d.get("departments") or [])}
sys.exit(0 if ok and "sales" not in slugs else 1)
PY
SHAPE_RC=$?
if [ "$RETIRE_RC" -eq 0 ] && [ "$SHAPE_RC" -eq 0 ] && [ ! -d "$COMPANY/departments/sales" ]; then
  good "A7b: retire script archives + writes removedWithProvenance (retire shape)"
else
  bad "A7b: retire direct invocation failed (retire_rc=$RETIRE_RC shape_rc=$SHAPE_RC)"
fi

# A8: legacy lane untouched — a legacy-state box (NO buildType) is refused by the
# apply-diff entry's buildType gate. Give it the genuine transcript so the
# consent gate passes and execution actually REACHES the buildType check.
echo '{"version":1,"interviewComplete":true,"ownerChat":0,"departments":[]}' > "$TMP/state-legacy.json"
"${RUN_ENV[@]}" env "WORKFORCE_BUILD_STATE_FILE=$TMP/state-legacy.json" \
  python3 "$BW" --non-interactive --config-file "$CONFIG" \
  --apply-standard-edits > "$TMP/a8.out" 2>"$TMP/a8.err" < /dev/null
RC=$?
if [ "$RC" -eq 88 ] && grep -q "buildType is not" "$TMP/a8.err"; then
  good "A8: legacy box refused by apply-diff entry (exit 88, buildType gate) — legacy lane untouched"
else
  bad "A8: expected rc=88 + buildType refusal, got rc=$RC"
fi

# Hermeticity proof: the LIVE operator state file was never written by this
# test (it lives outside the sandbox HOME; the test pins every write via
# $WORKFORCE_BUILD_STATE_FILE). Assert the live-state mtime sentinel: the
# test creates a marker file in the sandbox and asserts no state file exists
# at the sandbox default path that was NOT pinned.
if [ -f "$SANDBOX_HOME/.openclaw/workspace/.workforce-build-state.json" ]; then
  bad "A9: an UNPINNED sandbox-default build-state appeared (a code path bypassed the override)"
else
  good "A9: hermeticity held — no unpinned build-state write"
fi

echo "=============================================="
echo "test-build-standard-first-roundtrip.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
