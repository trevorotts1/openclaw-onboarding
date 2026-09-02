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

# ---- Resolve the secret-name canon (FIX 67: one secret-name canon) ----------
# shared-utils/secret_names.json maps canonical -> aliases. Credential prereqs
# resolve through it so a key stored under ANY alias satisfies the check.
# Prefer the installed copy next to this script, then the repo clone. Missing
# or malformed canon is NON-FATAL: fall back to the built-in table below so a
# bad manifest can never block an install (same posture as PREREQS.json).
_canon_candidates=""
if [ -n "$SKILLS_DIR" ] && [ -f "$SKILLS_DIR/shared-utils/secret_names.json" ]; then
  _canon_candidates="$SKILLS_DIR/shared-utils/secret_names.json"
elif [ -n "${OC_CANON_SRC:-}" ] && [ -f "${OC_CANON_SRC}/shared-utils/secret_names.json" ]; then
  _canon_candidates="${OC_CANON_SRC}/shared-utils/secret_names.json"
elif [ -f "$(dirname "$SKILL_DIR")/shared-utils/secret_names.json" ]; then
  _canon_candidates="$(dirname "$SKILL_DIR")/shared-utils/secret_names.json"
fi
export OC_SECRET_NAMES_JSON="${_canon_candidates}"

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

# ---- FIX 67: one secret-name canon ------------------------------------------
# Canonical -> aliases, loaded from shared-utils/secret_names.json when the
# installed copy carries it, else the built-in mirror. Every credential prereq
# resolves through this table, so a key written under any alias (e.g.
# BRAVE_SEARCH_API_KEY for BRAVE_API_KEY, or OLLAMA_API_KEY for the
# OLLAMA_CLOUD_API_KEY canon) satisfies the check on Mac AND VPS.
BUILTIN_SECRET_ALIASES = {
    "GOHIGHLEVEL_API_KEY": ["GOHIGHLEVEL_API_KEY", "GHL_PRIVATE_INTEGRATION_TOKEN", "GHL_API_KEY", "GHL_PIT", "HIGHLEVEL_API_KEY", "HIGHLEVEL_TOKEN", "GHL_PRIVATE_TOKEN", "CONVERTFLOW_API_KEY", "CONVERTANDFLOW_API_KEY", "CONVERT_AND_FLOW_API_KEY", "CONVERTFLOW_PIT", "CONVERTANDFLOW_PIT"],
    "GOHIGHLEVEL_LOCATION_ID": ["GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID", "HIGHLEVEL_LOCATION_ID", "LOCATION_ID"],
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": ["GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", "GHL_FIREBASE_REFRESH_TOKEN", "FIREBASE_REFRESH_TOKEN"],
    "TELEGRAM_BOT_TOKEN": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TG_BOT_TOKEN", "BOT_TOKEN"],
    "GEMINI_API_KEY": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "GOOGLE_AI_API_KEY", "GEMINI_KEY", "GCP_API_KEY", "GOOGLE_CLOUD_API_KEY"],
    "GOOGLE_API_KEY": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "GOOGLE_AI_API_KEY", "GOOGLE_CLOUD_API_KEY", "GCP_API_KEY"],
    "OPENAI_API_KEY": ["OPENAI_API_KEY", "OPENAI_KEY", "OPEN_AI_KEY", "OPENAI_TOKEN"],
    "OPENROUTER_API_KEY": ["OPENROUTER_API_KEY", "OPENROUTER_KEY", "OR_API_KEY", "OPEN_ROUTER_API_KEY"],
    "FISH_AUDIO_API_KEY": ["FISH_AUDIO_API_KEY", "FISHAUDIO_API_KEY", "FISH_API_KEY"],
    "FISH_AUDIO_VOICE_ID": ["FISH_AUDIO_VOICE_ID", "FISHAUDIO_VOICE_ID"],
    "PODBEAN_CLIENT_ID": ["PODBEAN_CLIENT_ID", "PODBEAN_API_KEY"],
    "PODBEAN_CLIENT_SECRET": ["PODBEAN_CLIENT_SECRET", "PODBEAN_API_SECRET"],
    "PODBEAN_PODCAST_ID": ["PODBEAN_PODCAST_ID", "PODBEAN_CHANNEL_ID", "PODCAST_ID"],
    "TAVILY_API_KEY": ["TAVILY_API_KEY", "TAVILY_KEY"],
    "PERPLEXITY_API_KEY": ["PERPLEXITY_API_KEY", "PERPLEXITY_KEY"],
    "KIE_API_KEY": ["KIE_API_KEY", "KIE_AI_API_KEY", "KIE_KEY", "KIE_VIDEO_API_KEY", "KIE_API_KEY_IAFS"],
    "MOONSHOT_API_KEY": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
    "KIMI_API_KEY": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
    "OLLAMA_API_KEY": ["OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY", "OLLAMA_KEY", "OLLAMA_TOKEN"],
    "OLLAMA_CLOUD_API_KEY": ["OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY", "OLLAMA_KEY", "OLLAMA_TOKEN"],
    "SUPABASE_SERVICE_ROLE_KEY": ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY"],
    "VERCEL_TOKEN": ["VERCEL_TOKEN", "VERCEL_API_TOKEN"],
    "GITHUB_TOKEN": ["GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN"],
    "ANTHROPIC_API_KEY": ["ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY"],
    "CONTEXT7_API_KEY": ["CONTEXT7_API_KEY", "CTX7_API_KEY", "CONTEXT7_KEY"],
    "AIRTABLE_TOKEN": ["AIRTABLE_TOKEN", "AIRTABLE_API_KEY", "AIRTABLE_PAT", "AIRTABLE_KEY"],
    "DEEPSEEK_API_KEY": ["DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "DEEP_SEEK_API_KEY"],
    "ELEVENLABS_API_KEY": ["ELEVENLABS_API_KEY", "ELEVEN_API_KEY"],
    "BRAVE_API_KEY": ["BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY"],
    "BRAVE_SEARCH_API_KEY": ["BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"],
    "CLOUDFLARE_ZHW_APPS_API_TOKEN": ["CLOUDFLARE_ZHW_APPS_API_TOKEN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZHW_API_TOKEN"],
    "CLOUDFLARE_ZHW_ACCOUNT_ID": ["CLOUDFLARE_ZHW_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ZHW_ACCOUNT"],
    "AGNES_API_KEY": ["AGNES_API_KEY", "AGNES_AI_API_KEY", "AGNES_KEY"],
    "FAL_API_KEY": ["FAL_API_KEY", "FAL_KEY"],
    "TELEGRAM_OWNER_CHAT_ID": ["TELEGRAM_OWNER_CHAT_ID", "OWNER_CHAT_ID"],
}

SECRET_NAMES_JSON = os.environ.get("OC_SECRET_NAMES_JSON", "")
if not SECRET_NAMES_JSON:
    # Default: the canon ships beside this script in shared-utils (both the
    # repo checkout and the installed $SKILLS_DIR/shared-utils layout).
    _here = os.path.dirname(os.path.abspath(__file__))
    _default_canon = os.path.join(_here, "secret_names.json")
    if os.path.isfile(_default_canon):
        SECRET_NAMES_JSON = _default_canon
if SECRET_NAMES_JSON and os.path.isfile(SECRET_NAMES_JSON):
    try:
        with open(SECRET_NAMES_JSON) as _f:
            _canon = json.load(_f)
        if isinstance(_canon, dict):
            # Shape A (this repo, FIX 67): {"canonical_names": {"CANON": ["ALIAS", ...]}}
            _names = _canon.get("canonical_names")
            if isinstance(_names, dict):
                for _canon_name, _aliases in _names.items():
                    if isinstance(_aliases, list):
                        BUILTIN_SECRET_ALIASES[_canon_name] = [_canon_name] + [
                            a for a in _aliases
                            if isinstance(a, str) and a != _canon_name
                        ]
            # Shape B (alternate): {"version": N, "secrets": {"CANON": {"aliases": [...]}}}
            if _canon.get("version") is not None:
                for _canon_name, _entry in _canon.get("secrets", {}).items():
                    if isinstance(_entry, dict) and isinstance(_entry.get("aliases"), list):
                        BUILTIN_SECRET_ALIASES[_canon_name] = [_canon_name] + [
                            a for a in _entry["aliases"] if isinstance(a, str)
                        ]
    except Exception:
        pass  # malformed canon is non-fatal: keep the built-in mirror

def canonical_aliases(canonical_name):
    """All env-var names that hold the SAME credential as <canonical_name>."""
    return BUILTIN_SECRET_ALIASES.get(canonical_name, [canonical_name])

# ---- Placeholder rejection (FIX 67: placeholder is NEVER a present key) -----
# Mirrors install.sh looks_like_real_key's obvious-placeholder stage. A stored
# value like PASTE_REAL_TOKEN satisfies no reader; here it must not satisfy a
# credential prereq either.
PLACEHOLDER_SUBSTRINGS = (
    'xxxxx', 'your_key', 'your-key', 'your_api', 'your-api', 'yourkey',
    'your_token', 'replace_me', 'replace-me', 'replaceme', 'changeme',
    'change_me', 'change-me', '_here', '-here', 'placeholder',
    'sample', 'dummy', 'demo', 'test_key', 'fake_key', 'sk-test', 'sk-xxx',
    'sk-example', 'sk-replace', 'todo', 'tbd', 'fill_in', 'fillin',
    'paste-your', 'paste_your', 'paste_real', 'insert_your', 'enter_your',
    'set_your', 'no_key', 'none_yet',
)

def looks_like_real_value(value):
    """Obvious-placeholder rejection (value shape only; no provider regexes
    here -- the prereq checker is presence-checking, not validating shape)."""
    if not value:
        return False
    lo = value.lower()
    for sub in PLACEHOLDER_SUBSTRINGS:
        if sub in lo:
            return False
    if value.startswith('<') and value.endswith('>'):
        return False
    if value.startswith('[') and value.endswith(']'):
        return False
    if value.startswith('{{') and value.endswith('}}'):
        return False
    return True

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
        os.path.join(home, ".openclaw", "secrets", "secrets.env"),
        os.path.join(home, ".openclaw", "workspace", ".env"),
        os.path.join(home, "clawd", "secrets", ".env"),
        "/data/.openclaw/secrets/.env",
        "/data/.openclaw/secrets/secrets.env",
        "/data/.openclaw/workspace/.env",
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("export ") and line[7:].startswith(var_name + "="):
                            line = line[7:]
                        if line.startswith(var_name + "=") and not line.startswith("#"):
                            v = line[len(var_name)+1:].strip().strip('"').strip("'")
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
    """FIX 67: resolve through the secret-name canon — a key stored under any
    alias of the declared canonical name satisfies the check — and reject
    obvious placeholder values (PASTE_REAL_TOKEN & friends never count)."""
    env_var = check_def.get("envVar", "")
    if not env_var:
        return False
    for alias in canonical_aliases(env_var):
        value = search_env_var(alias)
        if value and looks_like_real_value(value):
            return True
    return False


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
