#!/usr/bin/env bash
# ============================================================
#  check-credential.sh  —  Authoritative credential existence checker
#  Version: v12.3.3  |  Added: 2026-06-13
#
#  PURPOSE
#  -------
#  One script, one contract: given a credential key name, check every
#  location a key can actually live — in the correct order — and report
#  the FIRST hit with all locations checked.
#
#  "Missing" is only output after ALL four layers have come up empty.
#  Never trust a file-grep alone.
#
#  USAGE
#  -----
#    check-credential.sh <KEY_NAME>               # human-readable output
#    check-credential.sh <KEY_NAME> --json        # JSON output for piping
#    check-credential.sh <KEY_NAME> --quiet       # exit 0=found / 1=absent, no output
#
#  EXAMPLES
#    check-credential.sh NOTION_API_KEY
#    check-credential.sh GHL_PIT_TOKEN
#    check-credential.sh OLLAMA_API_KEY
#    check-credential.sh GOOGLE_API_KEY --json
#
#  EXIT CODES
#    0  — key found (at least one location)
#    1  — key genuinely absent from ALL checked locations
#    2  — usage error
#
#  CHECK ORDER (matches the 4-layer contract)
#  -------------------------------------------
#  (a) LIVE PROCESS ENV — the definitive source.
#       Docker VPS : docker exec <container> printenv | grep -i KEY
#       Mac/host   : ps eww <gateway-pid> | tr ' ' '\n' | grep -i KEY
#       If found here → EXISTS. Done. No further checks needed.
#  (b) /docker/<project>/.env — Docker Compose env file on VPS
#  (c) openclaw.json mcp.servers.<svc>.headers / mcp.servers.<svc>.env
#       (Notion, GHL, and other MCP-wired keys live here — not as bare env vars)
#  (d) All .env file stores:
#       ~/.openclaw/secrets/.env
#       ~/.openclaw/workspace/.env
#       ~/clawd/secrets/.env
#       ~/clawd/.env
#       ~/.openclaw/service-env/ai.openclaw.gateway.env
#       openclaw.json env.vars
#       /data/.openclaw/secrets/.env
#       /data/.openclaw/workspace/.env
#       auth-profiles.json (scanned as text)
#
#  OUTPUT FORMAT (human-readable)
#  --------------------------------
#    FOUND-in-LIVE-PROCESS-ENV  : KEY=****** (masked)
#    FOUND-in-COMPOSE-ENV       : /docker/<project>/.env → KEY=****** (masked)
#    FOUND-in-MCP-HEADERS       : openclaw.json mcp.servers.<svc>.headers → KEY=****** (masked)
#    FOUND-in-ENV-STORE         : <path> → KEY=****** (masked)
#
#    GENUINELY-ABSENT: <KEY> not found in any of the following checked locations:
#      [x] live process env (docker exec printenv / ps eww)
#      [x] /docker/<project>/.env
#      [x] openclaw.json mcp.servers.*.headers + env
#      [x] ~/.openclaw/secrets/.env
#      [x] ~/.openclaw/workspace/.env
#      [x] ~/clawd/secrets/.env
#      [x] ~/clawd/.env
#      [x] ~/.openclaw/service-env/ai.openclaw.gateway.env
#      [x] openclaw.json env.vars
#      [x] /data/.openclaw/secrets/.env
#      [x] /data/.openclaw/workspace/.env
#      [x] auth-profiles.json
#
#  SECURITY: values are ALWAYS masked in output (shown as ******). This script
#  never prints a credential value in cleartext.
# ============================================================

set -euo pipefail

# ─── Args ────────────────────────────────────────────────────────────────────
KEY_NAME="${1:-}"
MODE="${2:-}"  # --json | --quiet | (empty = human)

if [[ -z "$KEY_NAME" ]]; then
  echo "Usage: check-credential.sh <KEY_NAME> [--json|--quiet]" >&2
  exit 2
fi

MASKED="******"
FOUND=0
FOUND_LOCATION=""
CHECKED=()

# ─── Helper: mask a value ────────────────────────────────────────────────────
mask_value() {
  echo "$MASKED"
}

# ─── Helper: emit result ─────────────────────────────────────────────────────
emit_found() {
  local location="$1"
  local detail="${2:-}"
  FOUND=1
  FOUND_LOCATION="$location"
  if [[ "$MODE" == "--quiet" ]]; then
    return
  fi
  if [[ "$MODE" == "--json" ]]; then
    echo "{\"found\":true,\"key\":\"${KEY_NAME}\",\"location\":\"${location}\",\"detail\":\"${detail}\"}"
  else
    if [[ -n "$detail" ]]; then
      echo "FOUND-in-${location}: ${KEY_NAME}=${MASKED}  [${detail}]"
    else
      echo "FOUND-in-${location}: ${KEY_NAME}=${MASKED}"
    fi
  fi
}

emit_absent() {
  if [[ "$MODE" == "--quiet" ]]; then
    return
  fi
  if [[ "$MODE" == "--json" ]]; then
    # Build checked array as JSON
    local arr=""
    for loc in "${CHECKED[@]}"; do
      arr="${arr}\"${loc}\","
    done
    arr="${arr%,}"
    echo "{\"found\":false,\"key\":\"${KEY_NAME}\",\"checked\":[${arr}]}"
  else
    echo "GENUINELY-ABSENT: ${KEY_NAME} not found in any of the following checked locations:"
    for loc in "${CHECKED[@]}"; do
      echo "  [x] ${loc}"
    done
    echo ""
    echo "  ACTION REQUIRED: add ${KEY_NAME} to the appropriate env store before reporting it missing to the owner."
  fi
}

# ─── Detect platform ─────────────────────────────────────────────────────────
detect_platform() {
  if [[ -d "/data/.openclaw" ]]; then
    echo "vps"
  else
    echo "mac"
  fi
}

PLATFORM="$(detect_platform)"

# ─── Detect gateway PID (Mac) / Docker container name (VPS) ─────────────────
detect_gateway_pid() {
  # openclaw gateway run / node process
  pgrep -f "openclaw.*gateway" 2>/dev/null | head -1 || \
  pgrep -f "node.*openclaw" 2>/dev/null | head -1 || \
  echo ""
}

detect_docker_container() {
  # Common openclaw container names
  for name in openclaw openclaw-gateway openclaw-app app; do
    if docker inspect "$name" >/dev/null 2>&1; then
      echo "$name"
      return
    fi
  done
  # Fallback: first running container
  docker ps --format '{{.Names}}' 2>/dev/null | head -1 || echo ""
}

# ─── (a) LIVE PROCESS ENV ────────────────────────────────────────────────────
CHECKED+=("live process env (docker exec printenv / ps eww)")

if [[ "$PLATFORM" == "vps" ]]; then
  # Docker VPS: check via docker exec
  CONTAINER="$(detect_docker_container)"
  if [[ -n "$CONTAINER" ]]; then
    # Use grep -i for case-insensitive key match, exact KEY= prefix for precision
    PROC_VAL="$(docker exec "$CONTAINER" printenv 2>/dev/null | grep -i "^${KEY_NAME}=" | head -1 | cut -d'=' -f2- || true)"
    if [[ -n "$PROC_VAL" ]]; then
      emit_found "LIVE-PROCESS-ENV" "docker exec ${CONTAINER} printenv"
    fi
  else
    # No container found — try host process env as fallback
    GW_PID="$(detect_gateway_pid)"
    if [[ -n "$GW_PID" ]]; then
      PROC_VAL="$(ps eww "$GW_PID" 2>/dev/null | tr ' ' '\n' | grep -i "^${KEY_NAME}=" | head -1 | cut -d'=' -f2- || true)"
      if [[ -n "$PROC_VAL" ]]; then
        emit_found "LIVE-PROCESS-ENV" "ps eww pid=${GW_PID}"
      fi
    fi
  fi
else
  # Mac/host: check gateway process env via ps eww
  GW_PID="$(detect_gateway_pid)"
  if [[ -n "$GW_PID" ]]; then
    PROC_VAL="$(ps eww "$GW_PID" 2>/dev/null | tr ' ' '\n' | grep -i "^${KEY_NAME}=" | head -1 | cut -d'=' -f2- || true)"
    if [[ -n "$PROC_VAL" ]]; then
      emit_found "LIVE-PROCESS-ENV" "ps eww pid=${GW_PID}"
    fi
  fi
fi

[[ "$FOUND" == "1" ]] && exit 0

# ─── (b) Docker Compose .env file ────────────────────────────────────────────
CHECKED+=("/docker/<project>/.env (Docker Compose env file)")

if [[ "$PLATFORM" == "vps" ]] && [[ -d "/docker" ]]; then
  # Find all .env files under /docker/<project>/
  while IFS= read -r -d '' env_file; do
    if grep -qi "^${KEY_NAME}=" "$env_file" 2>/dev/null; then
      emit_found "COMPOSE-ENV" "$env_file"
      break
    fi
  done < <(find /docker -maxdepth 2 -name ".env" -print0 2>/dev/null)
fi

[[ "$FOUND" == "1" ]] && exit 0

# ─── (c) openclaw.json MCP server headers / env ──────────────────────────────
CHECKED+=("openclaw.json mcp.servers.*.headers + mcp.servers.*.env")

# Locate openclaw.json
CONFIG_CANDIDATES=(
  "${HOME}/.openclaw/openclaw.json"
  "/data/.openclaw/openclaw.json"
)
# Also check OC_CONFIG_FILE if set
if [[ -n "${OC_CONFIG_FILE:-}" ]]; then
  CONFIG_CANDIDATES=("$OC_CONFIG_FILE" "${CONFIG_CANDIDATES[@]}")
fi

for cfg in "${CONFIG_CANDIDATES[@]}"; do
  if [[ -f "$cfg" ]]; then
    # Python is more reliable for JSON traversal than jq (not always present)
    MCP_MATCH="$(python3 - "$cfg" "$KEY_NAME" 2>/dev/null <<'PYEOF'
import sys, json, re

cfg_path = sys.argv[1]
key_name = sys.argv[2]

try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except Exception:
    sys.exit(0)

mcp = cfg.get("mcp", {}).get("servers", {})
if not mcp:
    # legacy: root-level mcpServers
    mcp = cfg.get("mcpServers", {})

pattern = re.compile(re.escape(key_name), re.IGNORECASE)

for svc_name, svc_cfg in mcp.items():
    if not isinstance(svc_cfg, dict):
        continue
    # Check headers dict
    headers = svc_cfg.get("headers", {})
    if isinstance(headers, dict):
        for hk, hv in headers.items():
            if pattern.search(hk):
                print(f"mcp.servers.{svc_name}.headers.{hk}")
                sys.exit(0)
    # Check env dict
    env_block = svc_cfg.get("env", {})
    if isinstance(env_block, dict):
        for ek, ev in env_block.items():
            if pattern.search(ek):
                print(f"mcp.servers.{svc_name}.env.{ek}")
                sys.exit(0)
    # Check args list (some MCP servers pass key via --token KEY args)
    args = svc_cfg.get("args", [])
    if isinstance(args, list):
        for i, arg in enumerate(args):
            if isinstance(arg, str) and pattern.search(arg):
                print(f"mcp.servers.{svc_name}.args[{i}]={arg[:20]}...")
                sys.exit(0)

sys.exit(1)
PYEOF
    )" || true

    if [[ -n "$MCP_MATCH" ]]; then
      emit_found "MCP-HEADERS" "${cfg} → ${MCP_MATCH}"
      break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

# ─── (d) All .env file stores ────────────────────────────────────────────────
# Build the candidate list
declare -a ENV_STORES=()

# Platform-specific primary paths
if [[ "$PLATFORM" == "vps" ]]; then
  ENV_STORES+=(
    "/data/.openclaw/secrets/.env"
    "/data/.openclaw/workspace/.env"
    "/data/.openclaw/.env"
  )
else
  ENV_STORES+=(
    "${HOME}/.openclaw/secrets/.env"
    "${HOME}/.openclaw/workspace/.env"
    "${HOME}/clawd/secrets/.env"
    "${HOME}/clawd/.env"
    "${HOME}/.openclaw/service-env/ai.openclaw.gateway.env"
  )
fi

# Common to both
ENV_STORES+=(
  "${HOME}/.openclaw/secrets/.env"
  "${HOME}/.openclaw/workspace/.env"
  "${HOME}/clawd/secrets/.env"
  "${HOME}/clawd/.env"
  "${HOME}/.openclaw/service-env/ai.openclaw.gateway.env"
  "/data/.openclaw/secrets/.env"
  "/data/.openclaw/workspace/.env"
)

# openclaw.json env.vars block
for cfg in "${CONFIG_CANDIDATES[@]}"; do
  if [[ -f "$cfg" ]]; then
    ENV_VARS_MATCH="$(python3 - "$cfg" "$KEY_NAME" 2>/dev/null <<'PYEOF'
import sys, json, re

cfg_path = sys.argv[1]
key_name = sys.argv[2]
pattern = re.compile(r'^' + re.escape(key_name) + r'$', re.IGNORECASE)

try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except Exception:
    sys.exit(1)

env_vars = cfg.get("env", {}).get("vars", {})
if isinstance(env_vars, dict):
    for k in env_vars:
        if pattern.match(k) and env_vars[k]:
            print(f"env.vars.{k}")
            sys.exit(0)
sys.exit(1)
PYEOF
    )" || true
    if [[ -n "$ENV_VARS_MATCH" ]]; then
      CHECKED+=("openclaw.json env.vars")
      emit_found "ENV-STORE" "${cfg} → ${ENV_VARS_MATCH}"
      break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

# auth-profiles.json (text scan only — not parsed as JSON to avoid complexity)
AUTH_PROFILE_CANDIDATES=(
  "${HOME}/.openclaw/auth-profiles.json"
  "/data/.openclaw/auth-profiles.json"
)
for ap in "${AUTH_PROFILE_CANDIDATES[@]}"; do
  if [[ -f "$ap" ]]; then
    if grep -qi "\"${KEY_NAME}\"" "$ap" 2>/dev/null; then
      CHECKED+=("auth-profiles.json")
      emit_found "ENV-STORE" "${ap} (auth-profiles.json text match)"
      break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

# Deduplicate ENV_STORES
declare -A _seen=()
declare -a UNIQUE_STORES=()
for s in "${ENV_STORES[@]}"; do
  if [[ -z "${_seen[$s]+_}" ]]; then
    _seen[$s]=1
    UNIQUE_STORES+=("$s")
  fi
done

for store in "${UNIQUE_STORES[@]}"; do
  CHECKED+=("$store")
  if [[ -f "$store" ]]; then
    # grep -i for key, exact KEY= prefix
    if grep -qi "^${KEY_NAME}=" "$store" 2>/dev/null; then
      emit_found "ENV-STORE" "$store"
      break
    fi
  fi
done

[[ "$FOUND" == "1" ]] && exit 0

# ─── Not found anywhere ───────────────────────────────────────────────────────
emit_absent
exit 1
