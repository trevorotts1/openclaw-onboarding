#!/usr/bin/env bash
# Linux VPS bootstrap (native or Docker). Hostinger and Contabo are providers,
# not runtime topologies: inspect the host before choosing a client directory.
# Sourced before set -euo pipefail; never install to a Docker host by accident.

_OC_PLATFORM_COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
# shellcheck source=platform/common.sh
if ! command -v oc_set_platform_paths >/dev/null 2>&1; then
    source "$_OC_PLATFORM_COMMON" || return 1
fi
if [[ "$(oc_detect_platform)" != vps ]]; then
    echo "The VPS bootstrap requires Linux; use the Mac bootstrap on Darwin." >&2
    return 1
fi
export OPENCLAW_PLATFORM=vps

# An explicit root pins a native installation. Existing native config/runtime also
# wins over an unrelated Docker daemon. An explicit container selection wins over
# these native signals, and must identify exactly one running container.
_oc_native_config="${OPENCLAW_ROOT:-${OC_ROOT:-$HOME/.openclaw}}/openclaw.json"
_oc_try_container=false
if [[ "$(oc_runtime_topology)" == native && -z "${OPENCLAW_NO_CONTAINER_REEXEC:-}" ]]; then
    if [[ -n "${OPENCLAW_CONTAINER_NAME:-}" ]]; then
        _oc_try_container=true
    elif [[ -z "${OPENCLAW_ROOT:-${OC_ROOT:-}}" && ! -d "${_oc_native_config%/*}" && ! -d /data/.openclaw ]] \
         && ! command -v openclaw >/dev/null 2>&1; then
        _oc_try_container=true
    fi
fi
if [[ "$_oc_try_container" == true ]]; then
    _oc_container="${OPENCLAW_CONTAINER_NAME:-}"
    if command -v docker >/dev/null 2>&1; then
        _oc_running=$(docker ps --format '{{.Names}}' 2>/dev/null) || _oc_running=""
        if [[ -z "$_oc_container" ]]; then
            _oc_matches=$(printf '%s\n' "$_oc_running" | grep -iE 'openclaw' || true)
            _oc_count=$(printf '%s\n' "$_oc_matches" | grep -c '.' || true)
            if [[ "$_oc_count" -gt 1 ]]; then
                echo "Multiple OpenClaw containers are running; set OPENCLAW_CONTAINER_NAME to the intended client container." >&2
                return 1
            fi
            _oc_container="$_oc_matches"
            if [[ -z "$_oc_container" ]] && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qiE 'openclaw'; then
                echo "An OpenClaw container exists but is stopped; start that client container before onboarding." >&2
                return 1
            fi
        fi
        if [[ -n "$_oc_container" ]]; then
            if ! printf '%s\n' "$_oc_running" | grep -Fxq -- "$_oc_container"; then
                echo "The selected client container is not running; refusing a host-side replacement installation." >&2
                return 1
            fi
            _oc_user="${OPENCLAW_CONTAINER_USER:-}"
            if [[ -z "$_oc_user" ]]; then
                _oc_user=$(docker inspect "$_oc_container" --format '{{.Config.User}}' 2>/dev/null) || return 1
                # Empty Docker Config.User means root, not the Hostinger-only node account.
                _oc_user="${_oc_user:-root}"
            fi
            echo "[install] OpenClaw Docker runtime selected: $_oc_container (user $_oc_user)."
            _oc_args=(exec -i -u "$_oc_user"
                -e OPENCLAW_OWNER_NAME
                -e OPENCLAW_COMPANY_NAME
                -e OPENCLAW_COMPANY_SLUG
                -e OPENCLAW_ROOT
                -e OPENCLAW_WORKSPACE_PATH
                -e OPENCLAW_WORKSPACE_ROOT
                -e OPENCLAW_BASH
                -e CC_APP_DIR
                -e CC_PORT
                -e OPENCLAW_PODBEAN_CLIENT_ID
                -e OPENCLAW_PODBEAN_CLIENT_SECRET
                -e OPENCLAW_PLATFORM=vps
                -e OPENCLAW_BOOTSTRAP_MODE
                -e OPENCLAW_NO_CONTAINER_REEXEC=1)
            _oc_ref="${ONBOARDING_VERSION:-main}"
            case "$_oc_ref" in *[!a-zA-Z0-9._/-]*) echo "Invalid onboarding source ref." >&2; return 1 ;; esac
            _oc_entrypoint=install.sh
            [[ "${OPENCLAW_BOOTSTRAP_MODE:-provision}" != update ]] || _oc_entrypoint=update-skills.sh
            _oc_source="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/$_oc_ref/$_oc_entrypoint"
            # A terminal client can answer the two intake questions inside Docker.
            # Agent/background callers must provide the answers in the scoped env.
            if [[ -t 2 && -r /dev/tty ]]; then
                _oc_args+=(-t)
                exec docker "${_oc_args[@]}" "$_oc_container" bash -c 'set -o pipefail; _oc_source_url=$1; shift; curl -fSL "$_oc_source_url" | bash -s -- "$@"' onboarding "$_oc_source" "$@" </dev/tty
            else
                exec docker "${_oc_args[@]}" "$_oc_container" bash -c 'set -o pipefail; _oc_source_url=$1; shift; curl -fSL "$_oc_source_url" | bash -s -- "$@"' onboarding "$_oc_source" "$@"
            fi
        fi
    elif [[ -n "$_oc_container" ]]; then
        echo "OPENCLAW_CONTAINER_NAME was set but Docker is unavailable." >&2
        return 1
    fi
fi

oc_set_platform_paths || return 1

# Measure the real target filesystem, including native VPS homes/custom roots.
_oc_disk_target="$OC_CONFIG"
while [[ ! -d "$_oc_disk_target" && "$_oc_disk_target" != / ]]; do
    _oc_disk_target="$(dirname "$_oc_disk_target")"
done
_free_kb=$(df -k "$_oc_disk_target" 2>/dev/null | awk 'NR==2 {print $4}')
if [[ "$_free_kb" =~ ^[0-9]+$ && "$_free_kb" -lt 5242880 ]]; then
    echo "ERROR: the client filesystem has less than 5 GB free. Free space and retry." >&2
    return 1
fi

for _required in curl python3; do
    command -v "$_required" >/dev/null 2>&1 || {
        echo "ERROR: $_required is required but not installed on this Linux runtime." >&2
        return 1
    }
done
if [[ -f "$OC_JSON" ]] && command -v openclaw >/dev/null 2>&1; then
    if ! _validate_out=$(openclaw config validate 2>&1); then
        echo "ERROR: the selected client's openclaw.json is invalid before install starts." >&2
        printf '  %s\n' "$_validate_out" | head -10
        return 1
    fi
fi
_missing_soft=""
for _soft in unzip wget lsof; do
    command -v "$_soft" >/dev/null 2>&1 || _missing_soft="${_missing_soft}${_soft} "
done
[[ -z "$_missing_soft" ]] || echo "[install] Optional utilities unavailable: $_missing_soft"

mkdir -p "$OC_INSTALL_LOG_DIR"
LOG_FILE="$OC_INSTALL_LOG_DIR/openclaw-install-$(date +%Y%m%d-%H%M%S).log"
exec 1> >(tee -a "$LOG_FILE") 2>&1
