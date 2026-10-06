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

# WHERE AM I. ${BASH_SOURCE[0]} is EMPTY under zsh, and the onboarding resume
# prompt sources this file from the agent's own shell -- zsh on every Mac box.
# The old one-liner therefore resolved _SHIM_SCRIPT_DIR to $PWD there, and
# "$PWD/../lib-onboarding-state.sh" is not this repo's library on any box.
_OBS_SELF=""
if [ -n "${BASH_SOURCE:-}" ]; then
    _OBS_SELF="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    # Hidden behind eval so bash never has to expand a zsh-only prompt flag.
    eval '_OBS_SELF="${(%):-%x}"'
fi
[ -n "$_OBS_SELF" ] || _OBS_SELF="$0"
_SHIM_SCRIPT_DIR="$(cd "$(dirname "$_OBS_SELF")" 2>/dev/null && pwd)" || _SHIM_SCRIPT_DIR="."

# WHERE IS THE CANONICAL LIB. Box-side layouts, in the order they are likeliest:
#   ../lib-...            repo / ~/.openclaw/onboarding checkout (scripts/ child)
#   ./lib-...             delivered BESIDE the scripts tree by update-skills.sh
#   ~/.openclaw/onboarding, ~/.openclaw/skills, /data/... (VPS)
# The old code named exactly ONE candidate, ../lib-onboarding-state.sh, which
# from the delivered ~/.openclaw/scripts resolves to ~/.openclaw/lib-onboarding-state.sh --
# a path nothing has ever delivered. So every box warned on every source and
# oc_* was undefined box-side.
_OBS_CANONICAL=""
for _obs_lib_cand in \
    "${_SHIM_SCRIPT_DIR}/../lib-onboarding-state.sh" \
    "${_SHIM_SCRIPT_DIR}/lib-onboarding-state.sh" \
    "$HOME/.openclaw/onboarding/lib-onboarding-state.sh" \
    "$HOME/.openclaw/skills/lib-onboarding-state.sh" \
    "/data/.openclaw/onboarding/lib-onboarding-state.sh"; do
    if [ -n "$_obs_lib_cand" ] && [ -f "$_obs_lib_cand" ]; then
        _OBS_CANONICAL="$_obs_lib_cand"; break
    fi
done
unset _obs_lib_cand

if [ -n "$_OBS_CANONICAL" ]; then
    # shellcheck source=/dev/null
    source "$_OBS_CANONICAL" || return 1
else
    echo "[onboarding-state shim] WARNING: lib-onboarding-state.sh not found (looked beside and above $_SHIM_SCRIPT_DIR, in ~/.openclaw/onboarding, ~/.openclaw/skills and /data/.openclaw/onboarding)" >&2
    echo "  Cannot provide onboarding state-machine (oc_*). The obs_* gate below still works. Install may be incomplete." >&2
fi

# ============================================================
# obs_* COMPATIBILITY API — restored self-contained state-machine + gate.
# Idempotent; safe to source multiple times (guarded below). Never destructive.
# ============================================================
[ -n "${__OBS_SOURCED:-}" ] && return 0

# ── Path resolution (Mac primary, VPS fallback) ──────────────────────────────
OBS_OC_ROOT="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}}"
OBS_OC_JSON="$OBS_OC_ROOT/openclaw.json"

# Workspace (where CORE_UPDATES land + where the state file lives). Mirror the
# install.sh / apply-fleet-standards.sh resolver: per-agent override -> defaults
# -> canonical default. Clawd is dead; never fall back to ~/clawd.
obs_resolve_workspace() {
  if [[ -n "${OPENCLAW_WORKSPACE_PATH:-}" && -n "${OPENCLAW_WORKSPACE_ROOT:-}" && "${OPENCLAW_WORKSPACE_PATH%/}" != "${OPENCLAW_WORKSPACE_ROOT%/}" ]]; then
    echo "Conflicting client workspace pins" >&2; return 1
  fi
  if [[ -n "${OPENCLAW_WORKSPACE_PATH:-${OPENCLAW_WORKSPACE_ROOT:-}}" ]]; then
    local pinned="${OPENCLAW_WORKSPACE_PATH:-$OPENCLAW_WORKSPACE_ROOT}"
    case "$pinned" in /*) ;; *) echo "Client workspace pin must be absolute" >&2; return 1 ;; esac
    printf '%s' "${pinned%/}"; return 0
  fi
  local ws=""
  if [ -f "$OBS_OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
    ws="$(OC_JSON="$OBS_OC_JSON" python3 - <<'PYEOF'
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    # The main agent workspace: agents.entries (OpenClaw 2026.9.x, keyed by id)
    # or the legacy agents.list[], then agents.defaults.workspace.
    a = cfg.get("agents", {}) or {}
    e = a.get("entries") if isinstance(a.get("entries"), dict) else {}
    lst = a.get("list") if isinstance(a.get("list"), list) else []
    ws = ((e.get("main") or {}).get("workspace")
          or next((x.get("workspace") for x in lst
                   if isinstance(x, dict) and x.get("id") == "main" and x.get("workspace")), None)
          or (a.get("defaults") or {}).get("workspace"))
    if ws:
        print(os.path.expanduser(ws))
except (OSError, ValueError, AttributeError, TypeError) as exc:
    raise SystemExit('Cannot resolve configured client workspace: '+str(exc))
PYEOF
)" || return 1
  fi
  [ -z "$ws" ] && ws="$OBS_OC_ROOT/workspace"
  case "$ws" in /*) ;; *) echo "Configured client workspace must be absolute" >&2; return 1 ;; esac
  printf '%s' "$ws"
}
OBS_WORKSPACE="$(obs_resolve_workspace)" || return 1
__OBS_SOURCED=1
OBS_STATE_FILE="$OBS_WORKSPACE/.onboarding-state.json"

# Where the installed skills live + the source repo (for discovering qc/CORE).
OBS_SKILLS_DIR="${SKILLS_DIR:-$OBS_OC_ROOT/skills}"

obs_log() { printf '  [onboarding-state] %s\n' "$*"; }

# ── Resolve an agent id for CLI calls that require an explicit owner ─────────
# v25.0.4 fix. OpenClaw 2026.9.1 refuses agent-scoped CLI operations when more
# than one agent is configured and no owner is named:
#   "Multiple agents are configured, but the skills command has no explicit
#    owner. Pass --agent <id>."
# The verification gate below called `openclaw skills info` with NO --agent and
# sent stderr to /dev/null, so on every multi-agent box the CLI errored,
# $info_out came back EMPTY, and the gate recorded "skills-info:not-visible"
# for EVERY skill. Measured on a VPS box carrying 39 dept-* agents and no
# `main`: all 79 skills reported NOT verified while `openclaw skills info
# superpowers --agent dept-research` returned "superpowers ✓ Ready".
#
# That is a broken instrument reported as a finding — the same failure class
# this repo already retired the obsolete updater shim over. It is WORSE than a
# crash because it exits cleanly: a fleet roll marks every box "not verified",
# and the operator learns to ignore the gate.
#
# Order: explicit env override -> agents.defaults.systemAgent.agentId ->
# an entry flagged default -> legacy "main" -> first entry. Empty output means
# no --agent is passed, preserving single-agent behaviour exactly.
obs_default_agent() {
  [ -n "${OPENCLAW_AGENT_ID:-}" ] && { printf '%s' "$OPENCLAW_AGENT_ID"; return 0; }
  command -v python3 >/dev/null 2>&1 || return 0
  [ -f "$OBS_OC_JSON" ] || return 0
  OC_JSON="$OBS_OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
def pick(cfg):
    agents = cfg.get("agents", {}) or {}
    sa = (agents.get("defaults", {}) or {}).get("systemAgent", {}) or {}
    if sa.get("agentId"):
        return sa["agentId"]
    entries = agents.get("entries", {}) or {}
    for k, v in entries.items():
        if isinstance(v, dict) and v.get("default"):
            return k
    lst = agents.get("list", []) or []
    for a in lst:
        if isinstance(a, dict) and a.get("id") == "main":
            return "main"
    if entries:
        return sorted(entries)[0]
    for a in lst:
        if isinstance(a, dict) and a.get("id"):
            return a["id"]
    return ""
try:
    print(pick(json.load(open(os.environ["OC_JSON"]))))
except Exception:
    pass
PYEOF
}

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
import json, os, glob, re, datetime
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

# ROLLBACK COPIES ARE NOT SKILLS. A rename beside the live skills
# ("02-x" -> "02-x.bak-20260901", ".rollback", ".orig") still matches the
# [0-9]* glob and is still a directory, so it used to seed as a skill. It ships
# nothing anyone will install and no qc-*.sh that can pass, so it parked at
# "pending" forever -- and obs_gate_summary counts its DENOMINATOR straight off
# this file, so one such folder pinned the gate below 100% permanently and the
# resume cron never self-removed. Mirrors _BACKUP_DIR_RE in
# 23-ai-workforce-blueprint/scripts/department-floor.py.
rollback_re = re.compile(r"\.(bak|rollback|orig)(\b|[-_.]|$)", re.IGNORECASE)

# Skipping at discovery cannot help an entry an EARLIER run already wrote, and
# nothing else would ever remove it. Purge those too -- narrowly, by this regex
# only, never a real skill.
purged = [k for k in list(skills) if rollback_re.search(k)]
for k in purged:
    del skills[k]

# Discover non-archived numbered skill folders in the source.
found = []
for d in sorted(glob.glob(os.path.join(src_dir, "[0-9]*"))):
    name = os.path.basename(d.rstrip("/"))
    if not os.path.isdir(d):
        continue
    if "ARCHIVED" in name:
        continue
    if rollback_re.search(name):
        continue
    found.append(name)

for name in found:
    if name not in skills:
        skills[name] = {"status": "pending", "updatedAt": now}

state["discoveredSkills"] = found
json.dump(state, open(state_file, "w"), indent=2)
open(state_file, "a").write("\n")
print(f"  [onboarding-state] seeded {len(found)} skills (pending preserved/added) → {state_file}")
if purged:
    print(f"  [onboarding-state] purged {len(purged)} rollback folder(s) from the gate denominator: {', '.join(sorted(purged))}")
PYEOF
}

# ── Transition a single skill's status ───────────────────────────────────────
# obs_set_status <folder> <status>   status in:
#   pending|downloaded|wired|qc-passed|qc-failed|interview-pending
obs_set_status() {
  # `st`, never `status`: `status` is a READ-ONLY special variable in zsh, and
  # the onboarding resume prompt sources this shim from the agent's shell, which
  # is zsh on every Mac box. `local status=` aborts the function there before it
  # writes anything, so no skill could ever be recorded qc-passed.
  local folder="$1" st="$2" reason="${3:-}"
  command -v python3 >/dev/null 2>&1 || return 0
  [ -f "$OBS_STATE_FILE" ] || obs_seed_state >/dev/null 2>&1 || true
  FOLDER="$folder" STATUS="$st" REASON="$reason" STATE_FILE="$OBS_STATE_FILE" \
    python3 - <<'PYEOF' 2>/dev/null || true
import json, os, datetime
sf = os.environ["STATE_FILE"]; folder = os.environ["FOLDER"]; status = os.environ["STATUS"]
reason = os.environ.get("REASON", "").strip()
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
try:
    state = json.load(open(sf))
except Exception:
    state = {"skills": {}}
sk = state.setdefault("skills", {}).setdefault(folder, {})
sk["status"] = status
sk["updatedAt"] = now
# RECORD THE REASON. A negative verdict with no reason moves the whole diagnostic
# burden onto whoever reads the file later. Measured 2026-09-18: a live box
# carried 68/68 "qc-failed" with no reason field on any entry, so the state file
# could not say whether the skills were broken or the gate was — and they were
# not broken (`openclaw skills info` returned Ready, all 49 CORE_UPDATES
# sentinels were present, and the sampled qc-*.sh scripts exited 0).
if status == "qc-failed" and reason:
    sk["reason"] = reason
else:
    sk.pop("reason", None)
json.dump(state, open(sf, "w"), indent=2); open(sf, "a").write("\n")
PYEOF
}

# ── Is a failure reason an ENVIRONMENT failure rather than a skill failure? ───
# obs_reason_is_environmental <reason-string>
#
# THE DEFECT THIS EXISTS FOR. obs_verify_skill fails CLOSED when it cannot find
# the openclaw CLI (correct — unverifiable is not verified). But obs_set_status
# lets qc-failed overwrite qc-passed unconditionally, so ONE run under a minimal
# PATH — a cron, a launchd job, a non-login shell, none of which get
# ~/.local/bin — rewrites EVERY skill to qc-failed and nothing ever restores
# them. obs_gate_summary then never returns 0, so the "## UPDATE PENDING"
# section that update-skills.sh removes only when the gate passes becomes
# PERMANENT. Measured on a live box 2026-09-18: 66 skills rewritten to qc-failed
# in a SIX-SECOND window with zero QC diagnostics written, while the box's own
# CLI, sentinels and qc scripts all passed when run by hand.
#
# A reason that names the ENVIRONMENT is not evidence about the skill. It must
# not be allowed to demote a verdict that was previously PROVEN.
obs_reason_is_environmental() {
  case "$1" in
    *openclaw-cli:absent*|*deadline-runner-failed*|*skills-info:agent-required*)
      return 0 ;;
    *) return 1 ;;
  esac
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
#   (a) `openclaw skills info <name>` shows Ready/visible. If the openclaw CLI is
#       not on PATH this check FAILS (v20.0.91) — it is not skipped. It used to
#       be skipped, which meant an UNREGISTERED skill reached qc-passed whenever
#       the CLI was off PATH (a cron's minimal PATH is the common case).
#   (b) CORE_UPDATES sentinel present in workspace files (only if skill ships CORE_UPDATES.md)
#   (c) its qc-*.sh exits 0 (only if it ships one)
# Side effect: sets the skill's status to qc-passed (0) or qc-failed (non-zero).
# Echoes a one-line reason on failure. CLI/QC deadlines default to 30/180s;
# OBS_SKILLS_INFO_TIMEOUT_SECONDS / OBS_QC_TIMEOUT_SECONDS accept 1..3600.
# Raw diagnostics stay in the private $OBS_WORKSPACE/.onboarding-qc-diagnostics
# directory; timeout reasons contain no command output or credentials.
obs_verify_skill() {
  local folder="$1"
  local src_dir="${2:-$OBS_SKILLS_DIR}"
  local skill_path="$src_dir/$folder"
  local reasons=""
  local deadline_helper="$_SHIM_SCRIPT_DIR/run-with-deadline.py"
  local diagnostic_dir="$OBS_WORKSPACE/.onboarding-qc-diagnostics"

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
  # FIND THE CLI BEFORE DECLARING IT ABSENT. `command -v` proves only that a
  # NAME resolves on the CURRENT PATH, and the PATH that matters here is usually
  # cron's or launchd's, which carries none of the directories an OpenClaw
  # install actually uses. Declaring "absent" from that is a claim about the
  # environment of the CHECK, not about the box. Look in the known install
  # locations first, and only then say it cannot be found.
  if ! command -v openclaw >/dev/null 2>&1; then
    local _obs_cand
    for _obs_cand in "$HOME/.local/bin/openclaw" "$HOME/.npm-global/bin/openclaw" \
                     /usr/local/bin/openclaw /opt/homebrew/bin/openclaw \
                     /usr/bin/openclaw; do
      if [ -x "$_obs_cand" ]; then
        PATH="$(dirname "$_obs_cand"):$PATH"; export PATH
        break
      fi
    done
    unset _obs_cand
  fi

  if command -v openclaw >/dev/null 2>&1; then
    local info_out info_err _obs_agent _obs_agent_flag
    _obs_agent="$(obs_default_agent)"
    _obs_agent_flag=""
    [ -n "$_obs_agent" ] && _obs_agent_flag="--agent $_obs_agent"
    info_err="$(mktemp 2>/dev/null || printf '%s' "/tmp/obs-skills-info.$$")"
    # NEVER discard stderr here: the owner-required error (see obs_default_agent)
    # is emitted on stderr, and dropping it is what made an empty $info_out
    # indistinguishable from a genuinely unregistered skill.
    # shellcheck disable=SC2086
    local info_rc=0
    info_out="$(python3 "$deadline_helper" --seconds "${OBS_SKILLS_INFO_TIMEOUT_SECONDS:-30}" --diagnostics "$diagnostic_dir" --label skills-info --stdout -- openclaw skills info "$skill_name" $_obs_agent_flag 2>"$info_err")" || info_rc=$?
    if [ "$info_rc" -eq 124 ]; then
      reasons="${reasons}skills-info:timeout; "
      rm -f "$info_err"
    elif [ "$info_rc" -eq 125 ]; then
      reasons="${reasons}skills-info:deadline-runner-failed; "
      rm -f "$info_err"
    elif [ -z "$info_out" ] && grep -qiE 'no explicit owner|multiple agents are configured|AgentSelectionRequiredError' "$info_err" 2>/dev/null; then
      # Distinct, actionable reason — the box is not broken, the call was.
      reasons="${reasons}skills-info:agent-required(set agents.defaults.systemAgent.agentId or OPENCLAW_AGENT_ID); "
      rm -f "$info_err" 2>/dev/null || true
    elif [ -z "$info_out" ]; then
      rm -f "$info_err" 2>/dev/null || true
      reasons="${reasons}skills-info:not-visible; "
    elif [ "$info_rc" -ne 0 ]; then
      reasons="${reasons}skills-info:nonzero-exit; "
      rm -f "$info_err"
    elif rm -f "$info_err" 2>/dev/null; printf '%s' "$info_out" | grep -qiE 'not found|unknown skill|no such skill'; then
      reasons="${reasons}skills-info:not-registered; "
    elif ! printf '%s' "$info_out" | grep -qiE 'ready|enabled|visible|installed|name:|path:|details:|source:'; then
      reasons="${reasons}skills-info:not-registered; "
    fi
  else
    # v20.0.91 FAIL-OPEN FIX. This `if` had no `else`, so when openclaw was off
    # PATH check (a) was skipped ENTIRELY and contributed no reason — a skill
    # that ships neither CORE_UPDATES.md nor a qc-*.sh then collected zero
    # reasons and was marked qc-passed while UNREGISTERED. The canonical sibling
    # oc_skill_registered() in lib-onboarding-state.sh has always done
    # `command -v openclaw >/dev/null 2>&1 || return 1`; this was a fail-open
    # divergence between two copies of the same logic, and it bit hardest under
    # cron, whose minimal PATH routinely lacks openclaw.
    #
    # Registration is UNVERIFIABLE without the CLI, and unverifiable is not
    # verified. Fail closed and name the reason so the cause is actionable
    # rather than mysterious.
    reasons="${reasons}openclaw-cli:absent-cannot-verify-registration; "
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
    # DEFECT FIX: some qc-*.sh gates (e.g. skill 38's F17/F21/U-1/U-2/U-6
    # feature gates) are content-version-aware — they assert a marker is
    # present in the box's LIVE AGENTS.md, not just in the shipped source
    # script. They resolve AGENTS_MD themselves when unset, but their default
    # (the pointer-writer's own hardcoded platform path) can disagree with
    # THIS box's actual configured workspace. Hand them the SAME resolved
    # workspace this verification gate itself uses (obs_resolve_workspace,
    # cached in $OBS_WORKSPACE) unless the caller already set AGENTS_MD, so
    # the gate checks the file the wiring loop actually wrote.
    local qc_rc=0
    AGENTS_MD="${AGENTS_MD:-$OBS_WORKSPACE/AGENTS.md}" python3 "$deadline_helper" --seconds "${OBS_QC_TIMEOUT_SECONDS:-180}" --diagnostics "$diagnostic_dir" --label qc-script -- bash "$qc_script" >/dev/null 2>&1 || qc_rc=$?
    if [ "$qc_rc" -eq 124 ]; then
      reasons="${reasons}qc-script:timeout; "
    elif [ "$qc_rc" -eq 125 ]; then
      reasons="${reasons}qc-script:deadline-runner-failed; "
    elif [ "$qc_rc" -ne 0 ]; then
      reasons="${reasons}qc-script:nonzero-exit; "
    fi
  fi

  if [ -n "$reasons" ]; then
    # An ENVIRONMENT failure must not demote a skill that was previously PROVEN
    # to pass. See obs_reason_is_environmental for the incident this prevents:
    # one cron run without the CLI on PATH rewrote 66 verified skills to
    # qc-failed in six seconds and made the UPDATE PENDING notice permanent.
    # This is NOT fail-open — a skill that has never reached qc-passed still
    # fails, and the reason is still recorded and still returned to the caller.
    if obs_reason_is_environmental "$reasons" && [ "$(obs_get_status "$folder")" = "qc-passed" ]; then
      printf 'ENVIRONMENT-ONLY (prior qc-passed KEPT): %s' "${reasons% }"
      return 1
    fi
    obs_set_status "$folder" "qc-failed" "${reasons% }"
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
