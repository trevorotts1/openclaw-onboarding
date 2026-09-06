#!/usr/bin/env bash
# Shared read-only platform/topology and path resolution. Bash 3.2 compatible.
# Source this before selecting platform/<mac|vps>/bootstrap.sh. Hosting-provider
# names do not determine an operating system, container, or client directory.

oc_detect_platform() {
  case "$(uname -s)" in
    Darwin) printf '%s\n' mac ;;
    Linux) printf '%s\n' vps ;;
    *) echo "Unsupported onboarding OS: $(uname -s)" >&2; return 1 ;;
  esac
}

oc_container_marked() {
  [[ -f /.dockerenv || -f /run/.containerenv ]] && return 0
  [[ -r /proc/1/cgroup ]] && grep -qE '(^|/)(docker|kubepods|libpod)(/|[-.])' /proc/1/cgroup && return 0
  return 1
}

oc_runtime_topology() {
  if [[ "$(uname -s)" == Linux ]] && oc_container_marked; then
    printf '%s\n' container
  else
    printf '%s\n' native
  fi
}

oc_set_platform_paths() {
  local detected root workspace configured
  detected="$(oc_detect_platform)" || return 1
  if [[ -n "${OPENCLAW_PLATFORM:-}" && "${OPENCLAW_PLATFORM}" != "$detected" ]]; then
    echo "OPENCLAW_PLATFORM=${OPENCLAW_PLATFORM} conflicts with the actual OS ($detected)." >&2
    return 1
  fi
  OC_PLATFORM="$detected"
  OPENCLAW_PLATFORM="$detected"
  OPENCLAW_RUNTIME_TOPOLOGY="$(oc_runtime_topology)"
  root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-}}}"
  if [[ -z "$root" ]]; then
    # Preserve an existing /data installation on Linux, but an unrelated /data
    # directory on a native VPS is not evidence of Docker or client ownership.
    root="$HOME/.openclaw"
    if [[ "$detected" == vps && -d /data/.openclaw ]]; then
      if [[ -d "$HOME/.openclaw" && "$HOME/.openclaw" != /data/.openclaw ]]; then
        echo "Two OpenClaw roots exist; set OPENCLAW_ROOT to the intended client installation." >&2
        return 1
      fi
      root=/data/.openclaw
    elif [[ "$detected" == vps && "$OPENCLAW_RUNTIME_TOPOLOGY" == container && -d /data && ! -d "$HOME/.openclaw" ]]; then
      root=/data/.openclaw
    fi
  fi
  case "$root" in /*) ;; *) echo "OPENCLAW_ROOT must be an absolute path." >&2; return 1 ;; esac
  root="${root%/}"
  [[ -n "$root" && "$root" != / ]] || { echo "OpenClaw root cannot be the filesystem root." >&2; return 1; }
  if [[ -n "${OPENCLAW_WORKSPACE_PATH:-}" && -n "${OPENCLAW_WORKSPACE_ROOT:-}" && "${OPENCLAW_WORKSPACE_PATH%/}" != "${OPENCLAW_WORKSPACE_ROOT%/}" ]]; then
    echo "OPENCLAW_WORKSPACE_PATH and OPENCLAW_WORKSPACE_ROOT conflict." >&2
    return 1
  fi
  workspace="${OPENCLAW_WORKSPACE_PATH:-${OPENCLAW_WORKSPACE_ROOT:-}}"
  if [[ -z "$workspace" && -f "$root/openclaw.json" ]] && command -v python3 >/dev/null 2>&1; then
    configured="$(python3 - "$root/openclaw.json" <<'PY'
import json, os, sys
try:
    data = json.load(open(sys.argv[1]))
    value = data.get('agents', {}).get('defaults', {}).get('workspace', '')
    if isinstance(value, str) and value.strip():
        print(os.path.expanduser(value.strip()))
except (OSError, ValueError, AttributeError):
    sys.exit(1)
PY
)" || { echo "Cannot read the configured client workspace; refusing a replacement default." >&2; return 1; }
    workspace="$configured"
  fi
  workspace="${workspace:-$root/workspace}"
  case "$workspace" in /*) ;; *) echo "The client workspace must be an absolute path." >&2; return 1 ;; esac
  OC_CONFIG="$root"
  OC_ROOT="$root"
  OPENCLAW_ROOT="$root"
  OC_WORKSPACE_DEFAULT="${workspace%/}"
  OPENCLAW_WORKSPACE_PATH="$OC_WORKSPACE_DEFAULT"
  OPENCLAW_WORKSPACE_ROOT="$OC_WORKSPACE_DEFAULT"
  OC_JSON="$root/openclaw.json"
  OC_SECRETS_ENV="$root/secrets/.env"
  OC_CREDENTIALS="$root/credentials"
  OC_AGENTS="$root/agents"
  OC_SKILLS_DIR="$root/skills"
  OC_LOGS="$root/logs"
  OC_AUTH_PROFILES="$root/agents/main/agent/auth-profiles.json"
  OC_LEGACY_CLAWD="$HOME/clawd"
  if [[ "$detected" == mac ]]; then
    OC_DOWNLOADS="$HOME/Downloads"
    OC_BACKUPS="$HOME/Downloads/openclaw-backups"
    OC_INSTALL_LOG_DIR="$OC_BACKUPS/install-logs"
  else
    OC_DOWNLOADS="${root%/*}/Downloads"
    OC_BACKUPS="$root/backups"
    OC_INSTALL_LOG_DIR="$root/logs/install"
  fi
  export OPENCLAW_PLATFORM OPENCLAW_RUNTIME_TOPOLOGY OPENCLAW_ROOT
  export OPENCLAW_WORKSPACE_PATH OPENCLAW_WORKSPACE_ROOT
}
