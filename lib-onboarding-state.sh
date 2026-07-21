#!/usr/bin/env bash
# ============================================================
# lib-onboarding-state.sh — Onboarding honesty state-machine + verification gate
# ------------------------------------------------------------
# v10.16.48 — FIX 1 (ONBOARDING HONESTY)
#
# WHY THIS EXISTS
#   install.sh copies skill files to disk and pastes 5-Phase/Wave PROSE into
#   AGENTS.md. The prose is never executed; the only thing that ever gated
#   "done" was "files on disk." A skill could be DOWNLOADED but never
#   registered/wired/QC'd, and the install would still send "✅ complete."
#   That is the "#1 concern": downloaded-but-reported-installed.
#
#   This library makes "installed" a VERIFIED claim, not a file-copy claim.
#   Every place that wants to say "done" must call the gate first.
#
# THE STATE FILE
#   $OC_CONFIG/.onboarding-state.json  (sibling of .install-resume.json)
#   {
#     "version": "v10.16.48",
#     "startedAt": "…Z",
#     "skills": {
#       "05-ghl-setup": {
#         "status": "pending|downloaded|wired|qc-passed|qc-failed|interview-pending",
#         "hasCoreUpdates": true,
#         "coreUpdatesSentinelPresent": false,
#         "hasQcScript": true,
#         "qcExit": null,
#         "registered": false,
#         "lastError": "",
#         "updatedAt": "…Z"
#       }, …
#     }
#   }
#
# STATUS LADDER (a skill only advances; the gate is what proves each rung):
#   pending      → seeded; nothing done yet
#   downloaded   → skill folder present on disk in $OC_SKILLS_DIR
#   wired        → CORE_UPDATES merged + shell installers run + (GHL) mcp set
#   qc-passed    → VERIFICATION GATE passes (see oc_gate_skill)
#   qc-failed    → gate ran but failed (needs resume)
#   interview-pending → legitimately parked awaiting owner input (Skill 22/23/etc.)
#
# DESIGN RULES
#   - Pure bash + python3 (already mandatory prereqs). jq optional.
#   - Idempotent: seeding never clobbers a higher status; safe to re-source.
#   - Never throws under `set -euo pipefail` (all writes are guarded).
#   - ARCHIVED skills (folder name ends with -ARCHIVED) are excluded.
# ============================================================

# Resolve OC_CONFIG / OC_SKILLS_DIR if the sourcing script didn't set them.
: "${OC_CONFIG:=/data/.openclaw}"
: "${OC_SKILLS_DIR:=$OC_CONFIG/skills}"
ONBOARDING_STATE_FILE="${ONBOARDING_STATE_FILE:-$OC_CONFIG/.onboarding-state.json}"

# Skills that are legitimately INTERVIEW-gated (owner input required) and must
# NOT be treated as a failure when they park in interview-pending.
ONBOARDING_INTERVIEW_SKILLS="${ONBOARDING_INTERVIEW_SKILLS:-22-book-to-persona-coaching-leadership-system 23-ai-workforce-blueprint 32-command-center-setup 35-social-media-planner}"

# ------------------------------------------------------------
# oc_state_now — UTC ISO8601 timestamp
# ------------------------------------------------------------
oc_state_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ------------------------------------------------------------
# oc_state_seed <src_skills_dir> [version]
#   Seed/refresh .onboarding-state.json. Every non-archived numbered skill in
#   <src_skills_dir> gets an entry at status=pending IF it has no entry yet.
#   Existing entries are PRESERVED (never downgraded) — idempotent.
#
#   Returns 0 when the state file was written. Returns 1 when it could NOT be
#   written — python3 missing, the target path unwritable, or the parent
#   directory unusable.
#
#   ABSENT vs BROKEN (same doctrine as oc_state_mark_field below):
#     * ABSENT state file  -> NORMAL, and this function's whole job. Seed OWNS
#       creation; a first run has nothing to read and that is not a failure.
#     * PRESENT but the write FAILS -> a REAL failure. The reason is printed to
#       stderr and rc 1 is returned.
#
#   v20.0.9x FIX. The heredoc used to end `2>/dev/null || true`, so this
#   function returned 0 unconditionally — including when it wrote nothing at
#   all. install.sh's call site is
#       oc_state_seed ... && success "Onboarding state seeded" || warn ...
#   so a seed that never happened printed the seeded line. `|| true` is gone
#   and the write is now atomic (tempfile + os.replace): a failure mid-write no
#   longer leaves a truncated state file behind, i.e. it cannot turn a write
#   failure into the corruption this file refuses to ignore elsewhere.
#
#   KNOWN AND DELIBERATELY UNCHANGED HERE: an existing state file that is
#   present but unparseable is still reset to {} rather than reported. That is a
#   separate behaviour change (it removes the only self-heal path for a corrupt
#   file) and it is not folded into this fix.
# ------------------------------------------------------------
oc_state_seed() {
  local src_dir="$1"
  local version="${2:-${ONBOARDING_VERSION:-unknown}}"
  mkdir -p "$(dirname "$ONBOARDING_STATE_FILE")" 2>/dev/null || true

  SRC_DIR="$src_dir" VERSION="$version" STATE_FILE="$ONBOARDING_STATE_FILE" \
  NOW="$(oc_state_now)" python3 - <<'PYEOF'
import json, os, re, sys, tempfile
src    = os.environ["SRC_DIR"]
ver    = os.environ["VERSION"]
sf     = os.environ["STATE_FILE"]
now    = os.environ["NOW"]


def fail(msg):
    sys.stderr.write("oc_state_seed: %s\n" % msg)
    raise SystemExit(1)


state = {}
if os.path.isfile(sf):
    try: state = json.load(open(sf))
    except Exception: state = {}
state.setdefault("version", ver)
state["version"] = ver
state.setdefault("startedAt", now)
skills = state.setdefault("skills", {})

if os.path.isdir(src):
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if not os.path.isdir(p): continue
        if not re.match(r"^\d", name): continue          # numbered skills only
        if name.endswith("-ARCHIVED"): continue          # skip archived
        has_core = os.path.isfile(os.path.join(p, "CORE_UPDATES.md"))
        # any qc-*.sh shipped with the skill
        has_qc = any(f.startswith("qc-") and f.endswith(".sh") for f in os.listdir(p))
        e = skills.get(name)
        if e is None:
            skills[name] = {
                "status": "pending",
                "hasCoreUpdates": has_core,
                "coreUpdatesSentinelPresent": False,
                "hasQcScript": has_qc,
                "qcExit": None,
                "registered": False,
                "lastError": "",
                "updatedAt": now,
            }
        else:
            # refresh static facts but never downgrade status
            e["hasCoreUpdates"] = has_core
            e["hasQcScript"] = has_qc

# Atomic replace — never truncate the live file before the new content exists.
target_dir = os.path.dirname(os.path.abspath(sf)) or "."
tmp_path = None
try:
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".onboarding-state.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, sf)
    tmp_path = None
except OSError as exc:
    fail("could not write state file %s: %s" % (sf, exc))
finally:
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

raise SystemExit(0)
PYEOF
}

# ------------------------------------------------------------
# oc_state_set <skill_name> <status> [error]
#   Advance a skill's status. Refuses to DOWNGRADE qc-passed → lower unless the
#   new status is qc-failed (a re-run that regressed). Records timestamp.
#
#   Returns 0 when the status was recorded. Returns 1 when it was NOT — the
#   state file could not be seeded, python3 is unavailable, or the write failed.
#
#   v20.0.9x FIX. The heredoc used to end `2>/dev/null || true`, which made the
#   most consequential write in the state machine unfailable. The regression
#   path is what this cost: `oc_gate_skill` records a re-run that REGRESSED with
#     oc_state_set <skill> qc-failed <reason>
#   and that write is the ONLY thing that clears a stale `qc-passed`. When it
#   was swallowed, the old `qc-passed` stayed on disk and every reader —
#   oc_state_summary, oc_gate_summary, the watchdog's wave goal check — went on
#   reporting a skill as verified while the run that proved otherwise had
#   already finished. `|| true` is gone, the write is atomic, and the failure
#   reason is printed to stderr.
#
#   This lib is sourced by scripts running `set -euo pipefail`, so the two
#   internal call sites (oc_gate_skill's tail, and the seed below) fold a
#   nonzero return into an explicit branch rather than leaving a bare failing
#   statement that would ABORT the caller mid-install.
# ------------------------------------------------------------
oc_state_set() {
  local skill="$1" status="$2" err="${3:-}"
  if [ ! -f "$ONBOARDING_STATE_FILE" ]; then
    # Guarded, not bare: oc_state_seed can now fail, and this lib is sourced
    # under `set -euo pipefail`.
    oc_state_seed "$OC_SKILLS_DIR" || {
      printf 'oc_state_set: could not seed %s — %s/%s NOT recorded\n' \
        "$ONBOARDING_STATE_FILE" "$skill" "$status" >&2
      return 1
    }
  fi
  SKILL="$skill" STATUS="$status" ERR="$err" STATE_FILE="$ONBOARDING_STATE_FILE" \
  NOW="$(oc_state_now)" python3 - <<'PYEOF'
import json, os, sys, tempfile
sf=os.environ["STATE_FILE"]; skill=os.environ["SKILL"]; st=os.environ["STATUS"]
err=os.environ["ERR"]; now=os.environ["NOW"]


def fail(msg):
    sys.stderr.write("oc_state_set: %s\n" % msg)
    raise SystemExit(1)


order={"pending":0,"downloaded":1,"wired":2,"qc-failed":2,"interview-pending":2,"qc-passed":3}
try: state=json.load(open(sf))
except Exception: state={"skills":{}}
skills=state.setdefault("skills",{})
e=skills.setdefault(skill,{"status":"pending"})
cur=e.get("status","pending")
# Allow qc-failed to overwrite qc-passed (regression); otherwise never downgrade.
if st=="qc-failed" or order.get(st,0)>=order.get(cur,0):
    e["status"]=st
e["updatedAt"]=now
if err: e["lastError"]=err

# Atomic replace — never truncate the live file before the new content exists.
target_dir = os.path.dirname(os.path.abspath(sf)) or "."
tmp_path = None
try:
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".onboarding-state.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, sf)
    tmp_path = None
except OSError as exc:
    fail("could not write state file %s: %s" % (sf, exc))
finally:
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

raise SystemExit(0)
PYEOF
}

# ------------------------------------------------------------
# oc_state_mark_field <skill> <field> <json_value>
#   Set an arbitrary field (registered/coreUpdatesSentinelPresent/qcExit).
#   json_value is raw JSON: true / false / 0 / "\"text\"" / null
#
#   Returns 0 when the field was recorded (or when there is legitimately
#   nothing to record). Returns 1 when the state file EXISTS but could not be
#   read, parsed or rewritten -- see the ABSENT-vs-CORRUPT note below.
#
#   v20.0.86 FIX. This function never worked. Its body carried
#   `except Exception: return` -- a `return` outside any function -- so python
#   raised SyntaxError at COMPILE time, before the first statement ran. The
#   field was therefore NEVER written on ANY path, including the healthy one,
#   and `2>/dev/null || true` on the call site hid the error and forced rc 0.
#   `bash -n` does not parse heredoc bodies, so nothing caught it.
#
#   The consequences were real, and in BOTH directions, because
#   oc_wave_goal_check reads exactly these fields back:
#     * coreUpdatesSentinelPresent stayed at its seeded `false` forever, so
#       check (c) reported a missing sentinel for every skill shipping
#       CORE_UPDATES.md -- a permanent FALSE FAILURE that no re-run could clear.
#     * qcExit stayed at its seeded `null` forever, so check (d)
#       (`qc_exit is not None and qc_exit != 0`) could never fire -- a
#       permanently DEAD check that let a nonzero qc script pass the wave gate.
#
#   ABSENT vs CORRUPT -- these are deliberately NOT the same thing:
#     * ABSENT state file  -> NORMAL. oc_state_seed owns creation, and a gate
#       may legitimately run before the seed on a fresh box. There is nothing to
#       record yet, so this returns 0 quietly. This is a documented tolerance,
#       not a swallowed failure.
#     * PRESENT but unreadable / not JSON / not writable -> a REAL failure. The
#       reason is printed to stderr and rc 1 is returned. There is no `|| true`
#       and no blanket `2>/dev/null`: if we cannot record what the gate found,
#       the caller MUST be able to see that.
# ------------------------------------------------------------
oc_state_mark_field() {
  local skill="$1" field="$2" val="$3"
  # ABSENT is normal -- nothing to record yet. See the note above.
  [ -f "$ONBOARDING_STATE_FILE" ] || return 0
  SKILL="$skill" FIELD="$field" VAL="$val" STATE_FILE="$ONBOARDING_STATE_FILE" \
  python3 - <<'PYEOF'
import json, os, sys, tempfile

sf    = os.environ["STATE_FILE"]
skill = os.environ["SKILL"]
field = os.environ["FIELD"]
raw   = os.environ["VAL"]


def fail(msg):
    sys.stderr.write("oc_state_mark_field: %s\n" % msg)
    raise SystemExit(1)


# The value is raw JSON (true / false / 0 / null / "text"). A bare string that
# is not valid JSON is stored verbatim -- that is the documented contract.
try:
    val = json.loads(raw)
except ValueError:
    val = raw

# The file exists (the shell checked). If it cannot be read or is not JSON,
# that is corruption, and corruption must be LOUD -- never treated as absence.
try:
    with open(sf, encoding="utf-8") as fh:
        state = json.load(fh)
except OSError as exc:
    fail("state file exists but cannot be read: %s: %s" % (sf, exc))
except ValueError as exc:
    fail("state file is present but not valid JSON: %s: %s" % (sf, exc))

if not isinstance(state, dict):
    fail("state file is present but its top level is %s, not a JSON object: %s"
         % (type(state).__name__, sf))

entry = state.setdefault("skills", {}).setdefault(skill, {"status": "pending"})
entry[field] = val

# Atomic replace. The old body opened the real file in "w" mode, which
# TRUNCATES before serialising -- an exception midway through json.dump would
# have left a half-written state file behind, i.e. turned a write failure into
# the corruption this function now refuses to ignore.
target_dir = os.path.dirname(os.path.abspath(sf)) or "."
tmp_path = None
try:
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".onboarding-state.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, sf)
    tmp_path = None
except OSError as exc:
    fail("could not write state file %s: %s" % (sf, exc))
finally:
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

raise SystemExit(0)
PYEOF
}

# ------------------------------------------------------------
# oc_skill_registered <skill_name>
#   (a) of the GATE: returns 0 if `openclaw skills info <name>` shows the skill
#   as Ready/visible. The skill's REGISTERED NAME is its SKILL.md `name:` field
#   (which can differ from the folder, e.g. 35-social-media-planner →
#   name social-media-planner), so we resolve that first.
# ------------------------------------------------------------
oc_skill_registered() {
  local folder="$1"
  command -v openclaw >/dev/null 2>&1 || return 1
  local reg_name
  # v16.2.13: `|| true` — awk exits non-zero (rc 2) when SKILL.md is absent
  # (2>/dev/null hides the message, NOT the code); this plain assignment (local
  # was a separate statement above) would otherwise throw under a caller's
  # `set -e` if this public helper is ever invoked bare. Empty is handled below.
  reg_name=$(awk -F': ' '/^name:/{gsub(/[[:space:]]/,"",$2);print $2;exit}' \
               "$OC_SKILLS_DIR/$folder/SKILL.md" 2>/dev/null || true)
  [ -z "$reg_name" ] && reg_name="$folder"
  local out
  out=$(openclaw skills info "$reg_name" 2>/dev/null) || return 1
  # Ready / visible / enabled — any positive signal counts; empty/Not found fails.
  printf '%s' "$out" | grep -qiE "ready|enabled|visible|installed|name:" || return 1
  printf '%s' "$out" | grep -qiE "not found|unknown skill|no such skill" && return 1
  return 0
}

# ------------------------------------------------------------
# oc_core_sentinel_present <skill_name>
#   (b) of the GATE: if the skill ships CORE_UPDATES.md, confirm its first
#   labeled-section sentinel actually landed in a workspace core file. Mirrors
#   merge_core_updates' sentinel logic. Returns 0 if no CORE_UPDATES (nothing to
#   verify) OR the sentinel is present.
# ------------------------------------------------------------
oc_core_sentinel_present() {
  local folder="$1"
  local core="$OC_SKILLS_DIR/$folder/CORE_UPDATES.md"
  [ -f "$core" ] || return 0   # nothing to verify
  local ws="${OC_WORKSPACE_DEFAULT:-$OC_CONFIG/workspace}"
  CORE="$core" WS="$ws" python3 - <<'PYEOF' 2>/dev/null
import re, os, sys
core=open(os.environ["CORE"]).read()
ws=os.environ["WS"]
sections=re.split(r'\n(?=## )', core)
sentinels=[]
for s in sections:
    m=re.match(r'## (AGENTS|TOOLS|MEMORY|SOUL)\.md', s)
    if not m: continue
    if 'NO UPDATE NEEDED' in s.split('\n')[0]: continue
    body=s.split('\n',1)
    if len(body)<2: continue
    b=body[1].strip()
    if not b: continue
    sm=re.search(r'^##\s+.+', b, re.MULTILINE)
    sent=sm.group(0).strip() if sm else b.split('\n')[0].strip()
    if sent: sentinels.append(sent)
if not sentinels:
    sys.exit(0)   # CORE_UPDATES had no actionable section
present=0
for fn in ("AGENTS.md","TOOLS.md","MEMORY.md","SOUL.md"):
    p=os.path.join(ws,fn)
    if not os.path.isfile(p): continue
    txt=open(p,errors="ignore").read()
    for sent in sentinels:
        if sent in txt: present+=1; break
sys.exit(0 if present>0 else 1)
PYEOF
}

# ------------------------------------------------------------
# oc_gate_skill <skill_name>
#   THE VERIFICATION GATE. A skill counts INSTALLED only if ALL apply:
#     (a) openclaw skills info <name> → Ready/visible
#     (b) its CORE_UPDATES sentinel is present in workspace files (if it has one)
#     (c) its qc-*.sh exits 0 (if it ships one)
#   Records registered / coreUpdatesSentinelPresent / qcExit and sets status to
#   qc-passed or qc-failed. Returns 0 on pass, 1 on fail.
#   Interview-pending skills are NOT auto-gated here — caller decides.
#
#   v20.0.86: oc_state_mark_field can now report a real state-write failure
#   (rc 1) instead of silently pretending to have recorded the result. Every
#   call below folds that into _sw_ok rather than leaving a bare failing
#   statement, for two reasons:
#     * this lib is sourced by scripts that run `set -euo pipefail`
#       (update-skills.sh), where a bare nonzero statement would ABORT the
#       caller mid-gate — a crash is not an acceptable substitute for a
#       swallowed failure;
#     * a gate whose findings cannot be recorded has not verified anything, so
#       it FAILS CLOSED with reason `state-write-failed` instead of passing.
# ------------------------------------------------------------
oc_gate_skill() {
  local folder="$1"
  local ok=1 reason=""
  local _sw_ok=1          # state-write health; 0 once any field failed to record

  # (a) registration
  if oc_skill_registered "$folder"; then
    oc_state_mark_field "$folder" registered true || _sw_ok=0
  else
    oc_state_mark_field "$folder" registered false || _sw_ok=0
    ok=0; reason="not-registered"
  fi

  # (b) CORE_UPDATES sentinel
  if oc_core_sentinel_present "$folder"; then
    oc_state_mark_field "$folder" coreUpdatesSentinelPresent true || _sw_ok=0
  else
    oc_state_mark_field "$folder" coreUpdatesSentinelPresent false || _sw_ok=0
    ok=0; reason="${reason:+$reason,}core-sentinel-missing"
  fi

  # (c) qc-*.sh exit 0 (only the skill's own qc script, run read-only)
  #
  # v19.0.1 fix: some skills (06-ghl-install-pages, 28-cinematic-forge,
  # 35-social-media-planner, 44-convert-and-flow-operator) ship MULTIPLE
  # qc-*.sh files — a canonical per-skill install-QC gate plus one or more
  # BUILT-ARTIFACT helper QC scripts that take a required positional argument
  # (evidence_root/slug/workflow-id) and are meant to be invoked by hand
  # AFTER a build, not by this gate. The canonical gate script is named after
  # the skill's SKILL.md `name:` field (e.g. folder 06-ghl-install-pages,
  # name ghl-install-pages -> qc-ghl-install-pages.sh), NOT the folder name
  # and NOT alphabetical order. Picking "first qc-*.sh alphabetically" landed
  # on qc-built-form.sh for 06 and qc-built-workflow.sh for 44 — both exit
  # non-zero with a bare usage error when run with no argument, which is what
  # tripped the "05/06 not verified" Wave-7 install advisory (05 was a
  # separate, since-fixed false-positive in the (a) registration check; this
  # is 06's qc-script:nonzero-exit half). Resolution order below: exact
  # folder-name match, then exact skill-name match, then the old alphabetical
  # fallback (unchanged) for skills that only ever shipped one qc-*.sh.
  local qc="" _qc_skill_name
  # v16.2.13: `|| true` — awk/ls exit non-zero on a missing file / no-match
  # glob; `|| true` keeps this a plain assignment under a caller's `set -e`.
  _qc_skill_name=$(awk -F': ' '/^name:/{gsub(/[[:space:]]/,"",$2);print $2;exit}' \
                      "$OC_SKILLS_DIR/$folder/SKILL.md" 2>/dev/null || true)
  if [ -x "$OC_SKILLS_DIR/$folder/qc-${folder}.sh" ]; then
    qc="$OC_SKILLS_DIR/$folder/qc-${folder}.sh"
  elif [ -n "$_qc_skill_name" ] && [ -x "$OC_SKILLS_DIR/$folder/qc-${_qc_skill_name}.sh" ]; then
    qc="$OC_SKILLS_DIR/$folder/qc-${_qc_skill_name}.sh"
  else
    qc=$(ls "$OC_SKILLS_DIR/$folder"/qc-*.sh 2>/dev/null | head -1 || true)
  fi
  if [ -n "$qc" ] && [ -f "$qc" ]; then
    local qc_rc=0
    bash "$qc" >/dev/null 2>&1 || qc_rc=$?
    oc_state_mark_field "$folder" qcExit "$qc_rc" || _sw_ok=0
    if [ "$qc_rc" -ne 0 ]; then
      ok=0; reason="${reason:+$reason,}qc-exit-$qc_rc"
    fi
  else
    oc_state_mark_field "$folder" qcExit "null" || _sw_ok=0
  fi

  # A gate that could not RECORD what it found has not verified anything.
  # Fail closed and name the reason rather than report a pass we cannot back up.
  if [ "$_sw_ok" -eq 0 ]; then
    ok=0; reason="${reason:+$reason,}state-write-failed"
  fi

  # oc_state_set can now report a real write failure. Neither call below may be
  # left bare: this lib is sourced under `set -euo pipefail`, where a bare
  # nonzero statement ABORTS the caller mid-gate.
  if [ "$ok" -eq 1 ]; then
    # A pass that cannot be RECORDED is not a pass — the next reader would see
    # the previous (lower) status and the caller would have been told 0.
    oc_state_set "$folder" qc-passed || {
      printf 'oc_gate_skill: %s passed but qc-passed could not be written to %s — reporting FAIL\n' \
        "$folder" "$ONBOARDING_STATE_FILE" >&2
      return 1
    }
    return 0
  else
    # The regression write is the one that clears a stale qc-passed. If it does
    # not land, say so loudly — the on-disk status is now KNOWN to be wrong.
    oc_state_set "$folder" qc-failed "$reason" || \
      printf 'oc_gate_skill: %s FAILED (%s) and qc-failed could not be written to %s — the stale status on disk is NOT corrected\n' \
        "$folder" "${reason:-unknown}" "$ONBOARDING_STATE_FILE" >&2
    return 1
  fi
}

# ------------------------------------------------------------
# oc_state_summary
#   Prints "verified/total  failed=<list>  interview-pending=<list>  pending=<list>"
#   and sets globals: OC_VERIFIED OC_TOTAL OC_FAILED_LIST OC_PENDING_LIST
#   OC_INTERVIEW_LIST. Used by the HONEST REPORTING CONTRACT.
# ------------------------------------------------------------
oc_state_summary() {
  [ -f "$ONBOARDING_STATE_FILE" ] || { OC_VERIFIED=0; OC_TOTAL=0; OC_FAILED_LIST=""; OC_PENDING_LIST=""; OC_INTERVIEW_LIST=""; return 0; }
  local out
  out=$(STATE_FILE="$ONBOARDING_STATE_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os
try: s=json.load(open(os.environ["STATE_FILE"]))
except Exception: print("0|0|||"); raise SystemExit
sk=s.get("skills",{})
verified=[k for k,v in sk.items() if v.get("status")=="qc-passed"]
failed=[k for k,v in sk.items() if v.get("status")=="qc-failed"]
interview=[k for k,v in sk.items() if v.get("status")=="interview-pending"]
pending=[k for k,v in sk.items() if v.get("status") in ("pending","downloaded","wired")]
print("%d|%d|%s|%s|%s"%(len(verified),len(sk),
      ",".join(sorted(failed)),",".join(sorted(pending)),",".join(sorted(interview))))
PYEOF
)
  OC_VERIFIED=$(printf '%s' "$out" | cut -d'|' -f1)
  OC_TOTAL=$(printf '%s' "$out" | cut -d'|' -f2)
  OC_FAILED_LIST=$(printf '%s' "$out" | cut -d'|' -f3)
  OC_PENDING_LIST=$(printf '%s' "$out" | cut -d'|' -f4)
  OC_INTERVIEW_LIST=$(printf '%s' "$out" | cut -d'|' -f5)
  : "${OC_VERIFIED:=0}" "${OC_TOTAL:=0}"
}

# ------------------------------------------------------------
# oc_onboarding_complete
#   THE COMPLETION GATE. Returns 0 ONLY when every tracked skill is qc-passed OR
#   interview-pending (a legitimate park). Returns 1 if anything is still
#   pending/downloaded/wired/qc-failed. This is what gates "✅ complete".
# ------------------------------------------------------------
oc_onboarding_complete() {
  oc_state_summary
  [ "${OC_TOTAL:-0}" -gt 0 ] || return 1
  [ -z "$OC_FAILED_LIST" ] && [ -z "$OC_PENDING_LIST" ] && return 0
  return 1
}

# ============================================================
# PRD 2.13 — PER-WAVE GOAL STATE + CHEAP MACHINE-CHECKABLE GOALS
# ============================================================
# Wave goals are stored as a "waveGoals" object in the onboarding state file:
#   {
#     "waveGoals": {
#       "wave1": { "status": "pending|in-progress|passed|failed",
#                  "skills": ["01-teach-yourself-protocol","02-back-yourself-up-protocol"],
#                  "failStrikes": 0, "lastCheckedAt": "...", "passedAt": "..." },
#       "wave2": { ... },
#       "wave3": { ... },
#       "wave4": { ... },
#       "wave5": { ... },
#       "overall": { "status": "pending|passed",
#                    "interviewComplete": false,
#                    "workforceBuilt": false,
#                    "closeoutDelivered": false,
#                    "allWavesVerified": false }
#     }
#   }
#
# WAVE SKILL ASSIGNMENTS (mirrors the 5-wave install plan in install.sh):
#   Wave 1 (FOUNDATION):    01, 02
#   Wave 2 (INTEGRATIONS):  03,04,05,06,07,08,09,10,12,14
#   Wave 3 (CONTENT/SVC):   15,16,17,18,19,20,24,25,26,27,28,29,30,43
#   (11 and 21 were archived in v12.26.0 — see "ARCHIVED skills" note below.)
#   Wave 4 (INFRASTRUCTURE):31,36
#   Wave 5 (USER-INTERACT): 22,23,32,35
#
# PER-WAVE GOAL DEFINITION (all must hold for wave to pass):
#   (a) All skills in the wave have status=qc-passed (or interview-pending for Wave 5)
#   (b) Each skill's folder is present on disk in $OC_SKILLS_DIR
#   (c) Each skill with CORE_UPDATES.md has its sentinel present
#   (d) Each skill's qc-*.sh (if present) has recorded qcExit=0
#
# OVERALL GOAL (all must hold):
#   (i)   all 5 waves passed
#   (ii)  interviewComplete = true in workforce-build-state.json
#   (iii) workforce built (department-floor.py would exit 0 — checked by proxy:
#         buildCompletedAt is set in workforce-build-state.json)
#   (iv)  closeout delivered (closeoutStatus=done in workforce-build-state.json)
# ============================================================

# Canonical wave skill lists (match 5-wave install plan in install.sh).
#
# ARCHIVED skills are NEVER listed here. A wave passes only when every skill it
# names is present on disk (goal condition (b) above), so naming a folder that
# does not exist wedges that wave permanently on every box. Skills 11
# (superdesign) and 21 (tavily-search) were archived to `11-superdesign-ARCHIVED`
# / `21-tavily-search-ARCHIVED` in v12.26.0 (commit 0e53c677) but were left in
# Wave 2 / Wave 3 here, which is exactly that failure. Enforced by
# scripts/qc-assert-wave-list-integrity.sh — every name below must resolve to a
# real, non-ARCHIVED skill directory.
OC_WAVE1_SKILLS="01-teach-yourself-protocol 02-back-yourself-up-protocol"
OC_WAVE2_SKILLS="03-agent-browser 04-superpowers 05-ghl-setup 06-ghl-install-pages 07-kie-setup 08-vercel-setup 09-context7 10-github-setup 12-openrouter-setup 14-google-workspace-integration"
OC_WAVE3_SKILLS="15-blackceo-team-management 16-summarize-youtube 17-self-improving-agent 18-proactive-agent 19-humanizer 20-youtube-watcher 24-storyboard-writer 25-video-creator 26-caption-creator 27-video-editor 28-cinematic-forge 29-ghl-convert-and-flow 30-fish-audio-api-reference 43-graphify-knowledge-graph"
OC_WAVE4_SKILLS="31-upgraded-memory-system 36-ghl-mcp-setup"
OC_WAVE5_SKILLS="22-book-to-persona-coaching-leadership-system 23-ai-workforce-blueprint 32-command-center-setup 35-social-media-planner"

# ------------------------------------------------------------
# oc_wave_state_init
#   Seed the waveGoals block in the state file if not present.
#   Idempotent — only seeds; never clobbers existing wave status.
# ------------------------------------------------------------
oc_wave_state_init() {
  # Guarded, not bare: oc_state_seed can now fail, and this lib is sourced under
  # `set -euo pipefail`. Without the seed there is no file to init wave goals in.
  if [ ! -f "$ONBOARDING_STATE_FILE" ]; then
    oc_state_seed "${OC_SKILLS_DIR:-$OC_CONFIG/skills}" || {
      printf 'oc_wave_state_init: could not seed %s — wave goals NOT initialised\n' \
        "$ONBOARDING_STATE_FILE" >&2
      return 1
    }
  fi
  W1="$OC_WAVE1_SKILLS" W2="$OC_WAVE2_SKILLS" W3="$OC_WAVE3_SKILLS" \
  W4="$OC_WAVE4_SKILLS" W5="$OC_WAVE5_SKILLS" \
  STATE_FILE="$ONBOARDING_STATE_FILE" NOW="$(oc_state_now)" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
sf = os.environ["STATE_FILE"]
now = os.environ["NOW"]
try:    state = json.load(open(sf))
except Exception: state = {}
wg = state.setdefault("waveGoals", {})

for num, key in enumerate(["wave1","wave2","wave3","wave4","wave5"], 1):
    env_key = f"W{num}"
    skills = os.environ.get(env_key, "").split()
    if key not in wg:
        wg[key] = {
            "status": "pending",
            "skills": skills,
            "failStrikes": 0,
            "lastCheckedAt": None,
            "passedAt": None,
        }
    else:
        # Refresh skill list (never downgrade status)
        wg[key]["skills"] = skills
        wg[key].setdefault("failStrikes", 0)

if "overall" not in wg:
    wg["overall"] = {
        "status": "pending",
        "allWavesVerified": False,
        "interviewComplete": False,
        "workforceBuilt": False,
        "workspaceMaterialized": False,
        "closeoutDelivered": False,
    }

json.dump(state, open(sf, "w"), indent=2)
PYEOF
}

# ------------------------------------------------------------
# oc_wave_goal_check <wave_num>   (1-5)
#   CHEAP MACHINE-CHECKABLE per-wave goal check.
#   Reads .onboarding-state.json — near-zero tokens, no network.
#   Returns 0 = wave goal PASSED, 1 = incomplete.
#   Increments failStrikes on fail; records lastCheckedAt each call.
#   Does NOT call the agent or openclaw CLI.
# ------------------------------------------------------------
oc_wave_goal_check() {
  local wave_num="$1"
  local wave_key="wave${wave_num}"
  [ -f "$ONBOARDING_STATE_FILE" ] || return 1

  WAVE_KEY="$wave_key" STATE_FILE="$ONBOARDING_STATE_FILE" \
  OC_SKILLS_DIR="${OC_SKILLS_DIR:-$OC_CONFIG/skills}" NOW="$(oc_state_now)" \
  python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
sf   = os.environ["STATE_FILE"]
wkey = os.environ["WAVE_KEY"]
sdir = os.environ["OC_SKILLS_DIR"]
now  = os.environ["NOW"]

try:    state = json.load(open(sf))
except Exception: sys.exit(1)

wg = state.get("waveGoals", {})
wave = wg.get(wkey)
if not wave:
    sys.exit(1)

skills = wave.get("skills", [])
sk_state = state.get("skills", {})

# Goal check: all wave skills must be qc-passed (or interview-pending for wave5)
wave5 = (wkey == "wave5")
failed = []
for skill in skills:
    st = sk_state.get(skill, {}).get("status", "pending")
    if wave5 and st == "interview-pending":
        continue
    if st != "qc-passed":
        failed.append(f"{skill}:{st}")

# (b) folder present on disk
missing_folders = []
for skill in skills:
    p = os.path.join(sdir, skill)
    if not os.path.isdir(p):
        missing_folders.append(skill)

# (c) CORE_UPDATES sentinel
missing_sentinels = []
for skill in skills:
    if sk_state.get(skill, {}).get("hasCoreUpdates") and \
       not sk_state.get(skill, {}).get("coreUpdatesSentinelPresent"):
        missing_sentinels.append(skill)

# (d) qcExit == 0 (only for skills that have a qc script)
bad_qc = []
for skill in skills:
    e = sk_state.get(skill, {})
    qc_exit = e.get("qcExit")
    if qc_exit is not None and qc_exit != 0 and qc_exit != "null":
        bad_qc.append(f"{skill}:qcExit={qc_exit}")

now_val = now
if failed or missing_folders or missing_sentinels or bad_qc:
    wave["failStrikes"] = wave.get("failStrikes", 0) + 1
    wave["lastCheckedAt"] = now_val
    json.dump(state, open(sf, "w"), indent=2)
    sys.exit(1)

# All pass — mark wave passed
wave["status"] = "passed"
wave["passedAt"] = now_val
wave["lastCheckedAt"] = now_val
wave["failStrikes"] = 0  # reset on pass
json.dump(state, open(sf, "w"), indent=2)
sys.exit(0)
PYEOF
}

# ------------------------------------------------------------
# oc_workspace_departments_materialized
#   FAIL-CLOSED workspace-shell gate wrapper. Returns:
#     0  every required workspace department is FULLY MATERIALIZED (gate rc=0)
#     1  a required dept is SHELL/PARTIAL (gate rc=3) OR no workspace yet (rc=4)
#        OR the gate could not run (rc=2 / missing) — when in doubt, FAIL.
#   This is the workspace-layer extension of the onboarding HONESTY contract:
#   a role-library TEMPLATE copied to the skills/ tree ("TEMPLATE DEPLOYED") is
#   NOT a built workspace department ("WORKSPACE INSTANTIATED"). Reporting one as
#   the other is the exact false-"done" this gate makes impossible. Sets the
#   global OC_WORKSPACE_GATE_RC so callers can distinguish "shell" (3) from
#   "no workforce yet" (4).
# ------------------------------------------------------------
oc_workspace_departments_materialized() {
  OC_WORKSPACE_GATE_RC=2
  # Resolve the gate script: sibling scripts/ in the repo, or the deployed
  # skills/scripts/ tree on a client box (Mac ~/.openclaw, VPS /data/.openclaw).
  local _self_dir gate=""
  _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  for _c in \
    "${_self_dir:+$_self_dir/scripts/qc-assert-workspace-departments-built.sh}" \
    "$OC_CONFIG/skills/scripts/qc-assert-workspace-departments-built.sh" \
    "$HOME/.openclaw/skills/scripts/qc-assert-workspace-departments-built.sh" \
    "/data/.openclaw/skills/scripts/qc-assert-workspace-departments-built.sh"; do
    [ -n "$_c" ] && [ -f "$_c" ] && { gate="$_c"; break; }
  done
  # FAIL-CLOSED: if the gate is missing, we cannot prove materialization → fail.
  [ -z "$gate" ] && return 1
  # OC_WORKSPACE_DEPARTMENTS_DIR lets a caller that already resolved the
  # departments dir (tests; a build step that just wrote it) pin it precisely,
  # bypassing live detect_platform resolution. Otherwise the gate self-resolves.
  if [ -n "${OC_WORKSPACE_DEPARTMENTS_DIR:-}" ]; then
    bash "$gate" --departments-dir "$OC_WORKSPACE_DEPARTMENTS_DIR" >/dev/null 2>&1
  else
    bash "$gate" >/dev/null 2>&1
  fi
  OC_WORKSPACE_GATE_RC=$?
  [ "$OC_WORKSPACE_GATE_RC" -eq 0 ] && return 0
  return 1
}

# ------------------------------------------------------------
# oc_repo_consistency_ok
#   BUILD-START PREFLIGHT: the installed Skill 23 repo must be internally
#   consistent across its SIX independent sources of truth before a client
#   workforce build is allowed to run:
#     FLOOR (department-naming-map.json mandatory + universal-primary verticals)
#     ROSTERS (suggested-roles/*.md)         ROLE LIBRARY (templates/role-library/_index.json)
#     SOP SOURCE (role-library / Skill-42)   PERSONA DOMAINS (build-workforce dept_to_domains x2
#                                            + create_role_workspaces DEPT_DOMAIN_HINTS)
#     no ORPHANS.
#   Six departments once shipped UNBUILDABLE because NOTHING cross-checked floor
#   vs rosters. A client build must REFUSE to run against a drifted repo rather
#   than silently produce a half-built workforce. Delegates to the SAME gate CI
#   runs (qc-assert-repo-consistency.py — the BARE invocation runs BOTH the
#   5-dimension consistency gate AND the v12.25.0 artifact-coverage gate:
#   org-chart / routing / command-center / dreaming / bootstrap / skills-count /
#   version). Returns:
#     0  consistent (gate rc=0)
#     1  CONSISTENCY drift (rc=5) OR ARTIFACT drift (rc=6) OR the gate could not
#        run / is missing — FAIL-CLOSED (any nonzero rc refuses the build).
#   Sets OC_REPO_CONSISTENCY_RC so callers can distinguish 5-dimension drift (5)
#   from artifact drift (6) / could-not-run (2) / missing (127).
# ------------------------------------------------------------
oc_repo_consistency_ok() {
  OC_REPO_CONSISTENCY_RC=127
  local _self_dir gate=""
  _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  for _c in \
    "${_self_dir:+$_self_dir/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py}" \
    "$OC_CONFIG/skills/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py" \
    "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py" \
    "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py"; do
    [ -n "$_c" ] && [ -f "$_c" ] && { gate="$_c"; break; }
  done
  # FAIL-CLOSED: if the gate is missing, we cannot prove consistency → refuse.
  [ -z "$gate" ] && return 1
  local _skill_dir
  _skill_dir="$(cd "$(dirname "$gate")/.." 2>/dev/null && pwd)"
  python3 "$gate" --skill-dir "$_skill_dir" >/dev/null 2>&1
  OC_REPO_CONSISTENCY_RC=$?
  [ "$OC_REPO_CONSISTENCY_RC" -eq 0 ] && return 0
  return 1
}

# ------------------------------------------------------------
# oc_overall_goal_check
#   CHEAP overall goal check (reads two state files, no network):
#   (i) all 5 waves passed in waveGoals, (ii) interviewComplete in
#   workforce-build-state.json, (iii) workforce built — buildCompletedAt set AND
#   the WORKSPACE-SHELL gate passes (workspace departments materialized, NOT just
#   a template on disk), (iv) closeoutStatus=done.
#   Returns 0 = all goals met, 1 = incomplete.
#
#   v12.23.0: criterion (iii) no longer trusts buildCompletedAt alone. A
#   hand-seeded buildCompletedAt while the workspace departments are empty shells
#   was the false-"done" that cost the owner real money. The workspace-shell gate
#   (qc-assert-workspace-departments-built.sh) must ALSO pass with raw counts.
# ------------------------------------------------------------
oc_overall_goal_check() {
  [ -f "$ONBOARDING_STATE_FILE" ] || return 1
  local wf_state="${OC_WORKSPACE_DEFAULT:-$OC_CONFIG/workspace}/.workforce-build-state.json"

  # FAIL-CLOSED workspace-shell gate (raw on-disk verification, not JSON state).
  local ws_materialized="false"
  if oc_workspace_departments_materialized; then ws_materialized="true"; fi

  STATE_FILE="$ONBOARDING_STATE_FILE" WF_STATE="$wf_state" \
  WS_MATERIALIZED="$ws_materialized" \
  NOW="$(oc_state_now)" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
sf  = os.environ["STATE_FILE"]
wfs = os.environ["WF_STATE"]
now = os.environ["NOW"]

try:    state = json.load(open(sf))
except Exception: sys.exit(1)

wg = state.get("waveGoals", {})
ov = wg.setdefault("overall", {"status":"pending","allWavesVerified":False,
                                "interviewComplete":False,"workforceBuilt":False,
                                "workspaceMaterialized":False,
                                "closeoutDelivered":False})

# (i) all 5 waves passed
all_waves = all(
    wg.get(f"wave{n}", {}).get("status") == "passed"
    for n in range(1, 6)
)
ov["allWavesVerified"] = all_waves

# Read workforce build state (may not exist if workforce hasn't started)
wf = {}
if os.path.isfile(wfs):
    try: wf = json.load(open(wfs))
    except Exception: pass

# (ii) interview complete
ov["interviewComplete"] = bool(wf.get("interviewComplete"))

# v12.23.0 WORKSPACE-SHELL HONESTY: "TEMPLATE DEPLOYED" != "WORKSPACE
# INSTANTIATED". The workspace-shell gate (run by the bash wrapper) verifies the
# client's WORKSPACE departments are materialized with RAW counts — a template
# copied to the skills/ tree can never satisfy it. We record it as its own field
# AND require it for "workforce built": a hand-seeded buildCompletedAt is no
# longer sufficient.
ws_materialized = (os.environ.get("WS_MATERIALIZED") == "true")
ov["workspaceMaterialized"] = ws_materialized
# (iii) workforce built = buildCompletedAt set AND workspace actually materialized
ov["workforceBuilt"] = bool(wf.get("buildCompletedAt")) and ws_materialized
# (iv) closeout delivered
ov["closeoutDelivered"] = (wf.get("closeoutStatus") == "done")

passed = (all_waves and ov["interviewComplete"] and ov["workforceBuilt"]
          and ov["workspaceMaterialized"] and ov["closeoutDelivered"])
if passed:
    ov["status"] = "passed"
else:
    ov.setdefault("status", "pending")

json.dump(state, open(sf, "w"), indent=2)
sys.exit(0 if passed else 1)
PYEOF
}

# ------------------------------------------------------------
# oc_next_incomplete_wave
#   Print the wave number (1-5) of the FIRST wave that is not passed,
#   or empty string if all waves passed.
# ------------------------------------------------------------
oc_next_incomplete_wave() {
  [ -f "$ONBOARDING_STATE_FILE" ] || { echo "1"; return 0; }
  STATE_FILE="$ONBOARDING_STATE_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:    state = json.load(open(os.environ["STATE_FILE"]))
except Exception: print("1"); raise SystemExit
wg = state.get("waveGoals", {})
for n in range(1, 6):
    k = f"wave{n}"
    if wg.get(k, {}).get("status") != "passed":
        print(n); raise SystemExit
print("")  # all passed
PYEOF
}

# ------------------------------------------------------------
# oc_wave_fail_strikes <wave_num>
#   Print the failStrikes count for the wave (0 if unknown).
# ------------------------------------------------------------
oc_wave_fail_strikes() {
  local wave_num="$1"
  [ -f "$ONBOARDING_STATE_FILE" ] || { echo "0"; return 0; }
  WAVE_KEY="wave${wave_num}" STATE_FILE="$ONBOARDING_STATE_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:    state = json.load(open(os.environ["STATE_FILE"]))
except Exception: print("0"); raise SystemExit
print(state.get("waveGoals",{}).get(os.environ["WAVE_KEY"],{}).get("failStrikes",0))
PYEOF
}

# ------------------------------------------------------------
# oc_wave_skills_status <wave_num>
#   Print a compact summary of skill statuses for the given wave.
#   E.g.: "01-teach-yourself-protocol:qc-passed 02-back-yourself-up-protocol:pending"
# ------------------------------------------------------------
oc_wave_skills_status() {
  local wave_num="$1"
  [ -f "$ONBOARDING_STATE_FILE" ] || return 0
  WAVE_KEY="wave${wave_num}" STATE_FILE="$ONBOARDING_STATE_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:    state = json.load(open(os.environ["STATE_FILE"]))
except Exception: raise SystemExit
wg = state.get("waveGoals", {})
skills = wg.get(os.environ["WAVE_KEY"], {}).get("skills", [])
sk = state.get("skills", {})
parts = [f"{s}:{sk.get(s,{}).get('status','pending')}" for s in skills]
print(" ".join(parts))
PYEOF
}
