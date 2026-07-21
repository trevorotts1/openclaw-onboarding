#!/usr/bin/env bash
# ============================================================
# scripts/onboarding-state.sh — compatibility shim (PRD 2.1 unified)
# ============================================================
# The canonical onboarding state-machine is now:
#   lib-onboarding-state.sh  (repo root, v10.16.48) — the oc_* API.
#
# This shim exists so any script that still sources
# scripts/onboarding-state.sh (the old Mac-only path) gets
# the correct implementation without code duplication.
#
# It ALSO re-provides the legacy obs_* state-machine + verification-gate API
# (obs_seed_state / obs_set_status / obs_verify_skill / obs_gate_summary /
#  obs_resolve_workspace). RATIONALE (v17.0.19 fix): the PRD-2.1 unify
# (commit 2c798c72) renamed the implementation from obs_* to oc_* and turned this
# file into a thin lib-sourcing shim, but the RUNTIME callers were never migrated —
# update-skills.sh (the seed at ~line 975 + the verification gate at ~line 2019),
# install.sh's compat-fallback branch, and resume-onboarding.sh all still invoke
# the obs_* names. With no obs_* compatibility layer, sourcing this shim defined
# only oc_*, so `obs_seed_state` fired "command not found" and the internal
# verification gate (guarded by `command -v obs_verify_skill`) silently degraded
# to "verification gate unavailable / file-sync-only" on EVERY roll. The obs_*
# implementation below is the original self-contained state-machine + gate
# (pure bash + python3) restored verbatim so the callers behave EXACTLY as
# designed. Both namespaces now coexist: oc_* for the migrated callers, obs_* for
# the legacy ones.
# ============================================================

_SHIM_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_OBS_CANONICAL="${_SHIM_SCRIPT_DIR}/../lib-onboarding-state.sh"

if [ -f "$_OBS_CANONICAL" ]; then
    # shellcheck source=/dev/null
    source "$_OBS_CANONICAL"
else
    echo "[onboarding-state shim] WARNING: lib-onboarding-state.sh not found at $_OBS_CANONICAL" >&2
    echo "  Cannot provide onboarding state-machine (oc_*). Install may be incomplete." >&2
fi

# ============================================================
# obs_* COMPATIBILITY API — restored self-contained state-machine + gate.
# Idempotent; safe to source multiple times (guarded below). Never destructive.
# ============================================================
[ -n "${__OBS_SOURCED:-}" ] && return 0
__OBS_SOURCED=1

# ── Path resolution (Mac primary, VPS fallback) ──────────────────────────────
if [ -f /data/.openclaw/openclaw.json ] || [ -d /data/.openclaw ]; then
  OBS_OC_ROOT="/data/.openclaw"
else
  OBS_OC_ROOT="$HOME/.openclaw"
fi
OBS_OC_JSON="$OBS_OC_ROOT/openclaw.json"

# Workspace (where CORE_UPDATES land + where the state file lives). Mirror the
# install.sh / apply-fleet-standards.sh resolver: per-agent override -> defaults
# -> canonical default. Clawd is dead; never fall back to ~/clawd.
obs_resolve_workspace() {
  local ws=""
  if [ -f "$OBS_OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
    ws="$(OC_JSON="$OBS_OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict) and ag.get("id") == "main" and ag.get("workspace"):
            print(os.path.expanduser(ag["workspace"])); break
    else:
        ws = cfg.get("agents", {}).get("defaults", {}).get("workspace")
        if ws:
            print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
)"
  fi
  [ -z "$ws" ] && ws="$OBS_OC_ROOT/workspace"
  printf '%s' "$ws"
}
OBS_WORKSPACE="$(obs_resolve_workspace)"
OBS_STATE_FILE="$OBS_WORKSPACE/.onboarding-state.json"

# Where the installed skills live + the source repo (for discovering qc/CORE).
OBS_SKILLS_DIR="${SKILLS_DIR:-$OBS_OC_ROOT/skills}"

obs_log() { printf '  [onboarding-state] %s\n' "$*"; }

# ── Seed the state file with every non-archived skill at "pending" ───────────
# Idempotent: existing per-skill statuses are PRESERVED; only newly-discovered
# skills are added at "pending". Records the onboarding version + a timestamp.
#   obs_seed_state [version] [src_dir]
obs_seed_state() {
  local version="${1:-${ONBOARDING_VERSION:-unknown}}"
  local src_dir="${2:-$OBS_SKILLS_DIR}"
  mkdir -p "$OBS_WORKSPACE" 2>/dev/null || true
  command -v python3 >/dev/null 2>&1 || { obs_log "python3 missing — cannot seed state"; return 1; }
  VERSION="$version" SRC_DIR="$src_dir" STATE_FILE="$OBS_STATE_FILE" python3 - <<'PYEOF'
import json, os, glob, datetime
state_file = os.environ["STATE_FILE"]
src_dir = os.environ["SRC_DIR"]
version = os.environ["VERSION"]
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

try:
    state = json.load(open(state_file))
except Exception:
    state = {}
state.setdefault("version", version)
state["version"] = version
state.setdefault("seededAt", now)
state["lastSeedAt"] = now
skills = state.setdefault("skills", {})

# Discover non-archived numbered skill folders in the source.
found = []
for d in sorted(glob.glob(os.path.join(src_dir, "[0-9]*"))):
    name = os.path.basename(d.rstrip("/"))
    if not os.path.isdir(d):
        continue
    if "ARCHIVED" in name:
        continue
    found.append(name)

for name in found:
    if name not in skills:
        skills[name] = {"status": "pending", "updatedAt": now}

state["discoveredSkills"] = found
json.dump(state, open(state_file, "w"), indent=2)
open(state_file, "a").write("\n")
print(f"  [onboarding-state] seeded {len(found)} skills (pending preserved/added) → {state_file}")
PYEOF
}

# ── Transition a single skill's status ───────────────────────────────────────
# obs_set_status <folder> <status>   status in:
#   pending|downloaded|wired|qc-passed|qc-failed|interview-pending
obs_set_status() {
  local folder="$1" status="$2"
  command -v python3 >/dev/null 2>&1 || return 0
  [ -f "$OBS_STATE_FILE" ] || obs_seed_state >/dev/null 2>&1 || true
  FOLDER="$folder" STATUS="$status" STATE_FILE="$OBS_STATE_FILE" python3 - <<'PYEOF' 2>/dev/null || true
import json, os, datetime
sf = os.environ["STATE_FILE"]; folder = os.environ["FOLDER"]; status = os.environ["STATUS"]
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
try:
    state = json.load(open(sf))
except Exception:
    state = {"skills": {}}
sk = state.setdefault("skills", {}).setdefault(folder, {})
sk["status"] = status
sk["updatedAt"] = now
json.dump(state, open(sf, "w"), indent=2); open(sf, "a").write("\n")
PYEOF
}

obs_get_status() {
  local folder="$1"
  command -v python3 >/dev/null 2>&1 || { echo "unknown"; return 0; }
  FOLDER="$folder" STATE_FILE="$OBS_STATE_FILE" python3 - <<'PYEOF' 2>/dev/null || echo "unknown"
import json, os
try:
    state = json.load(open(os.environ["STATE_FILE"]))
    print(state.get("skills", {}).get(os.environ["FOLDER"], {}).get("status", "unknown"))
except Exception:
    print("unknown")
PYEOF
}

# ── The VERIFICATION GATE for a single skill ─────────────────────────────────
# obs_verify_skill <folder> [src_dir]
# Returns 0 (INSTALLED) only if ALL applicable checks pass:
#   (a) `openclaw skills info <name>` shows Ready/visible (skipped if CLI absent)
#   (b) CORE_UPDATES sentinel present in workspace files (only if skill ships CORE_UPDATES.md)
#   (c) its qc-*.sh exits 0 (only if it ships one)
# Side effect: sets the skill's status to qc-passed (0) or qc-failed (non-zero).
# Echoes a one-line reason on failure.
obs_verify_skill() {
  local folder="$1"
  local src_dir="${2:-$OBS_SKILLS_DIR}"
  local skill_path="$src_dir/$folder"
  local reasons=""

  # Resolve the canonical OpenClaw name from SKILL.md frontmatter `name:`
  # (docs.openclaw.ai/tools/skills: name | else directory name).
  local skill_name="$folder"
  if [ -f "$skill_path/SKILL.md" ]; then
    local fm_name
    fm_name="$(grep -m1 -E '^name:' "$skill_path/SKILL.md" 2>/dev/null | sed -E 's/^name:[[:space:]]*//' | tr -d '"'"'"'' | tr -d '[:space:]')"
    [ -n "$fm_name" ] && skill_name="$fm_name"
  fi

  # (a) openclaw skills info <name> -> Ready/visible
  #
  # v19.0.1 fix: a bare `error` substring match false-positives on any skill
  # whose own SKILL.md description legitimately contains the word "error"
  # (e.g. skill 05's frontmatter: "...and handle errors."), which `openclaw
  # skills info` echoes back verbatim in its description block. That flagged
  # 05-ghl-setup as skills-info:not-registered on every install even though
  # the skill IS registered (Source: openclaw-managed; Path:/Details: present)
  # and its own qc-*.sh passed. Bring this in line with the canonical
  # oc_skill_registered() in lib-onboarding-state.sh: require a positive
  # registration signal AND check negative signals against SPECIFIC phrases
  # only (never a bare "error" substring).
  #
  # FAIL CLOSED WHEN THE CLI IS NOT REACHABLE. This `if` used to have no `else`,
  # so check (a) was skipped ENTIRELY whenever `openclaw` was not on PATH — the
  # normal condition under a cron's minimal PATH. A skill that was never
  # registered then collected no reason at all, and if it also shipped no
  # CORE_UPDATES.md and no qc-*.sh, obs_verify_skill fell straight through to
  # `obs_set_status qc-passed` and returned 0. Registration was asserted by
  # nothing. The canonical implementation of this same check,
  # oc_skill_registered() in lib-onboarding-state.sh, has always done
  # `command -v openclaw >/dev/null 2>&1 || return 1` — this was a fail-open
  # divergence between two copies of one rule, and the copies now agree.
  #
  # ABSENT vs BROKEN: there is no benign "absent" here. The gate's entire job is
  # to confirm the runtime can see the skill. With no runtime to ask, the answer
  # is not "yes" and it is not "nothing to check" — it is UNVERIFIED, which this
  # gate reports as a failure with a reason that names the cause.
  if command -v openclaw >/dev/null 2>&1; then
    local info_out
    info_out="$(openclaw skills info "$skill_name" 2>/dev/null || true)"
    if [ -z "$info_out" ]; then
      reasons="${reasons}skills-info:not-visible; "
    elif printf '%s' "$info_out" | grep -qiE 'not found|unknown skill|no such skill'; then
      reasons="${reasons}skills-info:not-registered; "
    elif ! printf '%s' "$info_out" | grep -qiE 'ready|enabled|visible|installed|name:|path:|details:|source:'; then
      reasons="${reasons}skills-info:not-registered; "
    fi
  else
    reasons="${reasons}skills-info:openclaw-cli-not-on-path; "
  fi

  # (b) CORE_UPDATES sentinel present (only if the skill ships CORE_UPDATES.md)
  if [ -f "$skill_path/CORE_UPDATES.md" ]; then
    local sentinel="<!-- skill:${folder}:core-update-applied -->"
    local found_sentinel=0
    for wf in AGENTS.md TOOLS.md MEMORY.md SOUL.md; do
      if [ -f "$OBS_WORKSPACE/$wf" ] && grep -qF "$sentinel" "$OBS_WORKSPACE/$wf" 2>/dev/null; then
        found_sentinel=1; break
      fi
    done
    [ "$found_sentinel" -eq 0 ] && reasons="${reasons}core-updates:sentinel-missing; "
  fi

  # (c) qc-*.sh exits 0 (only if it ships one).
  # Prefer canonical qc-<folder>.sh, then qc-<skill_name>.sh (the SKILL.md
  # `name:` frontmatter, already resolved above as $skill_name), then the
  # old "first qc-*.sh alphabetically" fallback.
  #
  # v19.0.1 fix: some skills (06-ghl-install-pages, 28-cinematic-forge,
  # 35-social-media-planner, 44-convert-and-flow-operator) ship MULTIPLE
  # qc-*.sh files — a canonical per-skill install-QC gate plus one or more
  # BUILT-ARTIFACT helper QC scripts that require a positional argument
  # (evidence_root/slug/workflow-id) and are meant to be run by hand AFTER a
  # build, not by this gate. The canonical gate script is named after the
  # skill's frontmatter name (e.g. folder 06-ghl-install-pages, name
  # ghl-install-pages -> qc-ghl-install-pages.sh), not the folder and not
  # alphabetical order. The old fallback picked qc-built-form.sh for 06 and
  # qc-built-workflow.sh for 44 — both exit non-zero on a bare usage error
  # with no argument, which is what tripped the "05/06 not verified" Wave-7
  # install advisory (05 was a separate, since-fixed false-positive in check
  # (a) above; this is 06's qc-script:nonzero-exit half).
  local qc_script=""
  if [ -x "$skill_path/qc-${folder}.sh" ]; then
    qc_script="$skill_path/qc-${folder}.sh"
  elif [ -n "$skill_name" ] && [ -x "$skill_path/qc-${skill_name}.sh" ]; then
    qc_script="$skill_path/qc-${skill_name}.sh"
  else
    # first qc-*.sh in the folder
    for c in "$skill_path"/qc-*.sh; do
      [ -x "$c" ] && { qc_script="$c"; break; }
    done
  fi
  if [ -n "$qc_script" ]; then
    if ! bash "$qc_script" >/dev/null 2>&1; then
      reasons="${reasons}qc-script:nonzero-exit; "
    fi
  fi

  if [ -n "$reasons" ]; then
    obs_set_status "$folder" "qc-failed"
    printf '%s' "${reasons% }"
    return 1
  fi
  obs_set_status "$folder" "qc-passed"
  return 0
}

# ── Gate summary across ALL non-archived skills ──────────────────────────────
# obs_gate_summary [src_dir]
# Prints a human line + a machine line; returns 0 ONLY when every skill is
# qc-passed OR explicitly interview-pending. Prints the failing list otherwise.
obs_gate_summary() {
  local src_dir="${1:-$OBS_SKILLS_DIR}"
  command -v python3 >/dev/null 2>&1 || { echo "GATE: python3 missing — cannot evaluate"; return 1; }
  [ -f "$OBS_STATE_FILE" ] || obs_seed_state >/dev/null 2>&1 || true
  STATE_FILE="$OBS_STATE_FILE" python3 - <<'PYEOF'
import json, os, sys
try:
    state = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    print("GATE: no state file — nothing verified yet")
    sys.exit(1)
skills = state.get("skills", {})
total = len(skills)
passed = [k for k, v in skills.items() if v.get("status") == "qc-passed"]
park   = [k for k, v in skills.items() if v.get("status") == "interview-pending"]
failed = [k for k, v in skills.items()
          if v.get("status") not in ("qc-passed", "interview-pending")]
ok = (len(failed) == 0) and total > 0
verified = len(passed) + len(park)
human = f"{verified}/{total} skills verified-installed"
if park:
    human += f" ({len(park)} parked INTERVIEW_PENDING: {', '.join(sorted(park))})"
if failed:
    human += f", {len(failed)} NOT verified: {', '.join(sorted(failed))}"
print("GATE-HUMAN: " + human)
print("GATE-MACHINE: " + json.dumps({
    "ok": ok, "total": total, "passed": len(passed),
    "interviewPending": len(park), "failed": failed,
}))
sys.exit(0 if ok else 1)
PYEOF
}
