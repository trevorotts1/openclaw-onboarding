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
# ------------------------------------------------------------
oc_state_seed() {
  local src_dir="$1"
  local version="${2:-${ONBOARDING_VERSION:-unknown}}"
  mkdir -p "$(dirname "$ONBOARDING_STATE_FILE")" 2>/dev/null || true

  SRC_DIR="$src_dir" VERSION="$version" STATE_FILE="$ONBOARDING_STATE_FILE" \
  NOW="$(oc_state_now)" python3 - <<'PYEOF' 2>/dev/null || true
import json, os, re
src    = os.environ["SRC_DIR"]
ver    = os.environ["VERSION"]
sf     = os.environ["STATE_FILE"]
now    = os.environ["NOW"]

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

json.dump(state, open(sf, "w"), indent=2)
PYEOF
}

# ------------------------------------------------------------
# oc_state_set <skill_name> <status> [error]
#   Advance a skill's status. Refuses to DOWNGRADE qc-passed → lower unless the
#   new status is qc-failed (a re-run that regressed). Records timestamp.
# ------------------------------------------------------------
oc_state_set() {
  local skill="$1" status="$2" err="${3:-}"
  [ -f "$ONBOARDING_STATE_FILE" ] || oc_state_seed "$OC_SKILLS_DIR"
  SKILL="$skill" STATUS="$status" ERR="$err" STATE_FILE="$ONBOARDING_STATE_FILE" \
  NOW="$(oc_state_now)" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
sf=os.environ["STATE_FILE"]; skill=os.environ["SKILL"]; st=os.environ["STATUS"]
err=os.environ["ERR"]; now=os.environ["NOW"]
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
json.dump(state,open(sf,"w"),indent=2)
PYEOF
}

# ------------------------------------------------------------
# oc_state_mark_field <skill> <field> <json_value>
#   Set an arbitrary field (registered/coreUpdatesSentinelPresent/qcExit).
#   json_value is raw JSON: true / false / 0 / "\"text\"" / null
# ------------------------------------------------------------
oc_state_mark_field() {
  local skill="$1" field="$2" val="$3"
  [ -f "$ONBOARDING_STATE_FILE" ] || return 0
  SKILL="$skill" FIELD="$field" VAL="$val" STATE_FILE="$ONBOARDING_STATE_FILE" \
  python3 - <<'PYEOF' 2>/dev/null || true
import json, os
sf=os.environ["STATE_FILE"]; skill=os.environ["SKILL"]; field=os.environ["FIELD"]
raw=os.environ["VAL"]
try: val=json.loads(raw)
except Exception: val=raw
try: state=json.load(open(sf))
except Exception: return
e=state.setdefault("skills",{}).setdefault(skill,{"status":"pending"})
e[field]=val
json.dump(state,open(sf,"w"),indent=2)
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
  reg_name=$(awk -F': ' '/^name:/{gsub(/[[:space:]]/,"",$2);print $2;exit}' \
               "$OC_SKILLS_DIR/$folder/SKILL.md" 2>/dev/null)
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
# ------------------------------------------------------------
oc_gate_skill() {
  local folder="$1"
  local ok=1 reason=""

  # (a) registration
  if oc_skill_registered "$folder"; then
    oc_state_mark_field "$folder" registered true
  else
    oc_state_mark_field "$folder" registered false
    ok=0; reason="not-registered"
  fi

  # (b) CORE_UPDATES sentinel
  if oc_core_sentinel_present "$folder"; then
    oc_state_mark_field "$folder" coreUpdatesSentinelPresent true
  else
    oc_state_mark_field "$folder" coreUpdatesSentinelPresent false
    ok=0; reason="${reason:+$reason,}core-sentinel-missing"
  fi

  # (c) qc-*.sh exit 0 (only the skill's own qc script, run read-only)
  local qc
  qc=$(ls "$OC_SKILLS_DIR/$folder"/qc-*.sh 2>/dev/null | head -1)
  if [ -n "$qc" ] && [ -f "$qc" ]; then
    local qc_rc=0
    bash "$qc" >/dev/null 2>&1 || qc_rc=$?
    oc_state_mark_field "$folder" qcExit "$qc_rc"
    if [ "$qc_rc" -ne 0 ]; then
      ok=0; reason="${reason:+$reason,}qc-exit-$qc_rc"
    fi
  else
    oc_state_mark_field "$folder" qcExit "null"
  fi

  if [ "$ok" -eq 1 ]; then
    oc_state_set "$folder" qc-passed
    return 0
  else
    oc_state_set "$folder" qc-failed "$reason"
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
