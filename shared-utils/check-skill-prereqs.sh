#!/usr/bin/env bash
# check-skill-prereqs.sh -- Per-skill prerequisite checker.
#
# Reads <skill>/PREREQS.json and checks each declared prerequisite.
# Non-blocking: exit 2 means "installed with missing prereqs" (informational),
# NEVER a failure that blocks install. Mirrors Skill 44's proven contract.
#
# Interface: check-skill-prereqs.sh <skill-folder-abs-path>
#
# Exit codes:
#   0 -- all declared prereqs satisfied (or no PREREQS.json present)
#   2 -- installed-with-missing-prereqs: one or more prereqs unmet (informational)
#   3 -- malformed PREREQS.json (schema error; treated as no-op so a bad manifest
#        can never block an install; CI lint catches it upstream)
#
# This script is READ-ONLY: it never calls openclaw gateway restart,
# never writes credentials, never prints secret values (env-var NAMES only).
#
# Installed to $SKILLS_DIR/shared-utils/ by the existing shared-utils copy
# (install.sh and update-skills.sh) so it lands on every box.
#
# Reuses: search_env_var / has_cred / get_alias_list / platform paths from lib-shared.sh
# Self-records unmet prereqs into .onboarding-state.json via oc_state_set_prereqs.

set -euo pipefail

SKILL_DIR="${1:-}"

if [[ -z "$SKILL_DIR" ]]; then
  echo "[check-prereqs] ERROR: usage: check-skill-prereqs.sh <skill-folder-abs-path>" >&2
  exit 1
fi

if [[ ! -d "$SKILL_DIR" ]]; then
  echo "[check-prereqs] ERROR: skill folder not found: $SKILL_DIR" >&2
  exit 1
fi

PREREQS_JSON="$SKILL_DIR/PREREQS.json"
SKILL_NAME="$(basename "$SKILL_DIR")"

# No PREREQS.json = zero declared prereqs; backward-compatible no-op.
if [[ ! -f "$PREREQS_JSON" ]]; then
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[check-prereqs] WARN: python3 not on PATH -- skipping prereq check for $SKILL_NAME" >&2
  exit 0
fi

# ---- Resolve SKILLS_DIR (parent of this skill dir) -------------------------
SKILLS_DIR="${SKILLS_DIR:-$(dirname "$SKILL_DIR")}"

# ---- Resolve OC_ROOT -------------------------------------------------------
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT=""
fi

OC_CONFIG="$OC_ROOT"
OC_CONFIG_FILE="${OC_ROOT:+$OC_ROOT/openclaw.json}"
STATE_FILE="${OC_ROOT:+$OC_ROOT/.onboarding-state.json}"

export OC_PREREQS_JSON="$PREREQS_JSON"
export OC_SKILL_NAME="$SKILL_NAME"
export OC_SKILLS_DIR="$SKILLS_DIR"
export OC_CONFIG_FILE="${OC_CONFIG_FILE:-}"
export OC_STATE_FILE="${STATE_FILE:-}"
# Exported so type="state" prereqs can expand "$OC_ROOT/..." in their stateFile
# path. Empty OC_ROOT leaves an unresolvable path, which fails CLOSED (unmet).
export OC_ROOT="${OC_ROOT:-}"

python3 <<'PYEOF'
import json
import os
import subprocess
import sys

PREREQS_JSON = os.environ["OC_PREREQS_JSON"]
SKILL_NAME = os.environ["OC_SKILL_NAME"]
SKILLS_DIR = os.environ.get("OC_SKILLS_DIR", "")
CONFIG_FILE = os.environ.get("OC_CONFIG_FILE", "")
STATE_FILE = os.environ.get("OC_STATE_FILE", "")

# ---- Parse PREREQS.json ----------------------------------------------------
try:
    with open(PREREQS_JSON) as f:
        manifest = json.load(f)
except Exception as e:
    print(f"[prereq][{SKILL_NAME}] WARN: malformed PREREQS.json: {e}", file=sys.stderr)
    sys.exit(3)

prereqs = manifest.get("prerequisites", [])
if not isinstance(prereqs, list):
    print(f"[prereq][{SKILL_NAME}] WARN: PREREQS.json 'prerequisites' must be a list", file=sys.stderr)
    sys.exit(3)


# ---- Env-var search (Contract Rule 7 -- all stores) ------------------------
def search_env_var(var_name):
    """Check all env stores for the given var name. Returns the value or ''."""
    # 1. Current process env
    val = os.environ.get(var_name, "")
    if val:
        return val
    # 2. All .env files in known locations
    oc_root = os.environ.get("OC_CONFIG_FILE", "").replace("/openclaw.json", "")
    candidates = []
    if oc_root:
        candidates = [
            os.path.join(oc_root, "secrets", ".env"),
            os.path.join(oc_root, "workspace", ".env"),
            os.path.join(oc_root, ".env"),
        ]
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, ".openclaw", "secrets", ".env"),
        os.path.join(home, ".openclaw", "workspace", ".env"),
        os.path.join(home, "clawd", "secrets", ".env"),
        "/data/.openclaw/secrets/.env",
        "/data/.openclaw/workspace/.env",
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(var_name + "=") and not line.startswith("#"):
                            v = line[len(var_name)+1:]
                            if v:
                                return v
            except Exception:
                pass
    # 3. openclaw.json env.vars
    if CONFIG_FILE and os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            val = cfg.get("env", {}).get("vars", {}).get(var_name, "")
            if val:
                return val
        except Exception:
            pass
    return ""


def check_credential(check_def):
    env_var = check_def.get("envVar", "")
    if not env_var:
        return False
    return bool(search_env_var(env_var))


def _skill_id_to_folder(skill_id):
    """Resolve a numeric skill id (7) to its installed folder ('07-kie-setup').

    Skill folders are named '<zero-padded-number>-<slug>'. Matching is done on
    the parsed integer prefix so 7, 07 and 007 all resolve identically.
    """
    if not SKILLS_DIR or not os.path.isdir(SKILLS_DIR):
        return ""
    try:
        want = int(skill_id)
    except (TypeError, ValueError):
        return ""
    for entry in sorted(os.listdir(SKILLS_DIR)):
        if not os.path.isdir(os.path.join(SKILLS_DIR, entry)):
            continue
        prefix = entry.split("-", 1)[0]
        if prefix.isdigit() and int(prefix) == want:
            return entry
    return ""


def check_skill(check_def):
    """A skill dependency is satisfied when its folder exists in SKILLS_DIR.

    Two declaration forms are accepted and BOTH are enforced:
      {"skill": "07-kie-setup"}  -- canonical, explicit folder name
      {"skillId": 7}             -- numeric id, resolved to the folder above
    Before v12.11.0 only "skill" was implemented, so every {"skillId": N}
    dependency evaluated to a constant False -- it reported UNMET even when the
    dependency was installed, and therefore enforced nothing at all.
    """
    if not SKILLS_DIR:
        return False
    skill_folder = check_def.get("skill", "")
    if skill_folder and os.path.isdir(os.path.join(SKILLS_DIR, skill_folder)):
        return True
    if "skillId" in check_def:
        resolved = _skill_id_to_folder(check_def.get("skillId"))
        if resolved and os.path.isdir(os.path.join(SKILLS_DIR, resolved)):
            return True
    return False


def check_state(check_def):
    """Assert a JSON field inside an onboarding/build state file.

    check: {"stateFile": "$OC_ROOT/workspace/x.json", "field": "a.b", "equals": true}
    Fails CLOSED: a missing file, missing field or unreadable JSON is UNMET.
    """
    raw_path = check_def.get("stateFile", "")
    field = check_def.get("field", "")
    if not raw_path or not field:
        return False
    path = os.path.expanduser(os.path.expandvars(raw_path))
    if "$" in path or not os.path.isfile(path):
        return False
    try:
        with open(path) as f:
            state = json.load(f)
    except Exception:
        return False
    node = state
    for part in field.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    if "equals" in check_def:
        return node == check_def["equals"]
    return bool(node)


def check_manual(check_def):
    """Operator-verified fact that no offline check can prove (an external
    account exists, a paid balance is non-zero).

    Always reported as an advisory line, never counted as unmet. The CI lint
    (scripts/qc-prereqs-json.sh) forces severity="optional" on type="manual" so
    a REQUIRED dependency can never hide behind an unverifiable type.
    """
    return True


def check_binary(check_def):
    binary = check_def.get("binary", "")
    if not binary:
        return False
    try:
        result = subprocess.run(
            ["command", "-v", binary],
            capture_output=True,
            shell=False,
        )
        if result.returncode != 0:
            # Try via /bin/sh -c command -v
            result2 = subprocess.run(
                f"command -v {binary}",
                shell=True,
                capture_output=True,
            )
            if result2.returncode != 0:
                return False
        # Optionally check minVersion
        min_ver = check_def.get("minVersion", "")
        if not min_ver:
            return True
        # Try to get version output
        try:
            ver_result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ver_output = ver_result.stdout + ver_result.stderr
            # Extract X.Y or X.Y.Z from version output
            import re
            m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", ver_output)
            if m:
                got = (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
                need_parts = min_ver.split(".")
                need = tuple(int(x) for x in need_parts[:3])
                need = need + (0,) * (3 - len(need))
                return got >= need
        except Exception:
            pass
        return True  # binary exists but version check inconclusive; pass
    except Exception:
        return False


def check_config(check_def):
    if not CONFIG_FILE or not os.path.isfile(CONFIG_FILE):
        return False
    json_path = check_def.get("jsonPath", "")
    if not json_path:
        return False
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        parts = json_path.split(".")
        node = cfg
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                return False
            node = node[p]
        return bool(node)
    except Exception:
        return False


def check_mcp(check_def):
    if not CONFIG_FILE or not os.path.isfile(CONFIG_FILE):
        return False
    server = check_def.get("server", "")
    if not server:
        return False
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        return bool(cfg.get("mcp", {}).get("servers", {}).get(server))
    except Exception:
        return False


CHECKERS = {
    "credential": check_credential,
    "skill": check_skill,
    "binary": check_binary,
    "config": check_config,
    "mcp": check_mcp,
    "state": check_state,
    "manual": check_manual,
}

# Types that are reported for visibility but never counted as unmet.
ADVISORY_TYPES = {"manual"}

# ---- Run checks ------------------------------------------------------------
unmet = []

for prereq in prereqs:
    p_id = prereq.get("id", "unknown")
    p_type = prereq.get("type", "")
    p_label = prereq.get("label", p_id)
    p_severity = prereq.get("severity", "required")
    p_satisfy = prereq.get("satisfy", "")
    p_check = prereq.get("check", {})

    checker = CHECKERS.get(p_type)
    if checker is None:
        # FAIL CLOSED. Before v12.11.0 this branch did `continue`, so a prereq
        # carrying an unknown or missing "type" was dropped on the floor: the
        # dependency was declared, never checked, and the skill still exited 0.
        # An unverifiable declaration is now surfaced as unmet (exit 2 is
        # informational to install.sh/update-skills.sh -- it blocks nothing).
        print(
            f"[prereq][{SKILL_NAME}][{p_severity}] {p_id} :: {p_label} :: "
            f"UNVERIFIABLE (unknown prereq type '{p_type}'; valid: "
            f"{', '.join(sorted(CHECKERS))}) :: {p_satisfy}"
        )
        unmet.append({
            "id": p_id,
            "type": p_type,
            "label": p_label,
            "severity": p_severity,
            "satisfy": p_satisfy,
        })
        continue

    try:
        satisfied = checker(p_check)
    except Exception as e:
        print(f"[prereq][{SKILL_NAME}][warn] checker error for {p_id}: {e}", file=sys.stderr)
        satisfied = False  # treat as unmet but non-fatal

    if p_type in ADVISORY_TYPES:
        print(f"[prereq][{SKILL_NAME}][advisory] {p_id} :: {p_label} :: {p_satisfy}")
        continue

    if not satisfied:
        unmet.append({
            "id": p_id,
            "type": p_type,
            "label": p_label,
            "severity": p_severity,
            "satisfy": p_satisfy,
        })
        print(f"[prereq][{SKILL_NAME}][{p_severity}] {p_id} :: {p_label} :: {p_satisfy}")

# ---- Write state file via oc_state_set_prereqs logic (C.3) -----------------
if STATE_FILE and os.path.isfile(STATE_FILE):
    try:
        from datetime import datetime, timezone

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(STATE_FILE) as f:
            state = json.load(f)
        if SKILL_NAME not in state:
            state[SKILL_NAME] = {}
        state[SKILL_NAME]["missingPrereqs"] = unmet
        state[SKILL_NAME]["prereqCheckedAt"] = now_iso
        import tempfile
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f"[prereq][{SKILL_NAME}] WARN: could not update state file: {e}", file=sys.stderr)

# ---- Exit code -------------------------------------------------------------
if unmet:
    sys.exit(2)
else:
    sys.exit(0)
PYEOF

EXIT_CODE=$?
exit $EXIT_CODE
