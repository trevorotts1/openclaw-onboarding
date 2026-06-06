#!/usr/bin/env bash
# onboarding-state.sh — v10.15.48  (FIX 1: ONBOARDING HONESTY)
#
# A real per-skill STATE MACHINE + VERIFICATION GATE, sourced by install.sh and
# update-skills.sh. This is the #1 honesty fix: previously install.sh copied
# files + pasted "5-Phase/Wave" PROSE into AGENTS.md (never executed), the ONLY
# gate was "files on disk," and "✅ complete" was sent UNCONDITIONALLY. There
# was no per-skill/per-wave state and no install-resume — so the agent would
# report "installed/done/onboarded" for skills that were merely DOWNLOADED.
#
# This file provides:
#   • a state file ~/.openclaw/workspace/.onboarding-state.json
#     (seeded with EVERY non-archived skill at status "pending")
#   • per-skill status transitions: pending -> downloaded -> wired ->
#     qc-passed | qc-failed   (plus the terminal park "interview-pending")
#   • obs_verify_skill <folder> : the VERIFICATION GATE — a skill counts
#     INSTALLED only if (a) `openclaw skills info <name>` returns Ready/visible,
#     (b) its CORE_UPDATES sentinel is present in the workspace files (if it
#     ships a CORE_UPDATES.md), and (c) its qc-*.sh exits 0 (if it ships one).
#   • obs_gate_summary : prints "X/Y verified-installed, Z failed: <list>" and
#     returns 0 ONLY when every non-archived skill is qc-passed or an explicit
#     interview-pending park.
#
# Pure bash + python3 (always present on Mac). Idempotent. Never destructive.
# Safe to source multiple times (guarded).

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
  if command -v openclaw >/dev/null 2>&1; then
    local info_out
    info_out="$(openclaw skills info "$skill_name" 2>/dev/null || true)"
    if [ -z "$info_out" ]; then
      reasons="${reasons}skills-info:not-visible; "
    elif printf '%s' "$info_out" | grep -qiE 'error|not found|unknown skill'; then
      reasons="${reasons}skills-info:not-registered; "
    fi
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

  # (c) qc-*.sh exits 0 (only if it ships one). Prefer canonical qc-<folder>.sh.
  local qc_script=""
  if [ -x "$skill_path/qc-${folder}.sh" ]; then
    qc_script="$skill_path/qc-${folder}.sh"
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
