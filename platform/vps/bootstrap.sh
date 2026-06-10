#!/usr/bin/env bash
# ============================================================
# platform/vps/bootstrap.sh — Hostinger Docker container re-exec + VPS pre-flight
# ============================================================
#
# Sourced by install.sh (unified) when OPENCLAW_PLATFORM=vps or when
# running on a Hostinger Docker host.
#
# Extracted from VPS install.sh v10.14.0–v10.16.48 for PRD 2.1 unified.
#
# Contains:
#   1. Hostinger Docker host-detect + container re-exec block (v10.14.0–v10.14.10)
#   2. Disk space pre-flight (v10.14.1)
#   3. Safety belt (host without /data + openclaw container) (v10.14.1)
#   4. openclaw.json schema validation (v10.14.5)
#   5. Hard + soft prereq checks (v10.14.3)
#   6. VPS canonical path variable setup
#
# NEVER enable set -euo pipefail before this block (the auto-detect uses
# conditional commands that may fail intentionally).
# ============================================================

# ── 1. Hostinger Docker host-detect + container re-exec ─────────────────────
if [ -z "${OPENCLAW_NO_CONTAINER_REEXEC:-}" ] \
   && [ ! -d /data ] \
   && command -v docker >/dev/null 2>&1; then

    _oc_container="${OPENCLAW_CONTAINER_NAME:-}"
    if [ -z "$_oc_container" ]; then
        # v10.14.1: detect multi-container false positives.
        _oc_matches=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E 'openclaw' || true)
        _oc_match_count=$(printf '%s\n' "$_oc_matches" | grep -c '.' || true)
        if [ "${_oc_match_count:-0}" -gt 1 ]; then
            echo "" >&2
            echo "ERROR: Multiple running OpenClaw containers detected on this host:" >&2
            printf '%s\n' "$_oc_matches" | sed 's/^/  - /' >&2
            echo "" >&2
            echo "Cannot auto-pick — would silently install into the wrong one." >&2
            echo "Re-run with the container name explicit:" >&2
            echo "  OPENCLAW_CONTAINER_NAME=<name-from-list-above> \\" >&2
            echo "    curl -fSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash" >&2
            exit 1
        fi
        _oc_container=$(printf '%s\n' "$_oc_matches" | head -1)
    fi

    if [ -n "$_oc_container" ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qF "$_oc_container"; then
        _oc_user="${OPENCLAW_CONTAINER_USER:-}"
        if [ -z "$_oc_user" ]; then
            _oc_user=$(docker inspect "$_oc_container" --format '{{.Config.User}}' 2>/dev/null)
            [ -z "$_oc_user" ] && _oc_user="node"
        fi

        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  Hostinger Docker host detected — re-executing inside container"
        echo "════════════════════════════════════════════════════════════"
        echo "  Container: $_oc_container"
        echo "  User:      $_oc_user"
        echo "  Reason:    /data lives inside this container, not on the host."
        echo "             Installing on host would silently land in the wrong"
        echo "             place (host /data/.openclaw is invisible to the"
        echo "             OpenClaw runtime, which only sees its bind mount)."
        echo "  Overrides: OPENCLAW_NO_CONTAINER_REEXEC=1   — skip auto-detect entirely"
        echo "             OPENCLAW_CONTAINER_NAME=<name>   — target a different container"
        echo "             OPENCLAW_CONTAINER_USER=<user>   — exec as a different user"
        echo "════════════════════════════════════════════════════════════"
        echo ""

        # v10.14.6: Detect + remove stale /usr/local CLI dual-install.
        docker exec -u root "$_oc_container" sh -c '
OLD=/usr/local/bin/openclaw
NEW=/data/.npm-global/bin/openclaw
if [ -e "$OLD" ] && [ -e "$NEW" ]; then
    OLD_VER=$("$OLD" --version 2>&1 | head -1)
    NEW_VER=$("$NEW" --version 2>&1 | head -1)
    if [ "$OLD_VER" != "$NEW_VER" ]; then
        echo "[install] CLI dual-install mismatch detected (Hostinger image baseline)" >&2
        echo "[install]   stale:   $OLD_VER at $OLD" >&2
        echo "[install]   current: $NEW_VER at $NEW (matches gateway)" >&2
        TS=$(date +%Y%m%d-%H%M%S)
        BAK=/data/.openclaw/backups/cli-cleanup-$TS
        mkdir -p "$BAK"
        cp -a "$OLD" "$BAK/openclaw.symlink" 2>/dev/null || true
        cp -a /usr/local/lib/node_modules/openclaw "$BAK/" 2>/dev/null || true
        rm -f "$OLD"
        rm -rf /usr/local/lib/node_modules/openclaw
        echo "[install] Removed stale CLI; backup at $BAK" >&2
    fi
fi
' 2>&1 || true

        # v10.14.10: forward OPENCLAW_* env vars from host SSH session into container.
        exec docker exec -i -u "$_oc_user" \
            -e OPENCLAW_OWNER_NAME \
            -e OPENCLAW_PODBEAN_CLIENT_ID \
            -e OPENCLAW_PODBEAN_CLIENT_SECRET \
            "$_oc_container" bash -c \
            "curl -fSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash"
    fi
fi

# ── 2. Disk space pre-flight ─────────────────────────────────────────────────
if [ -d /data ]; then
    _free_kb=$(df -k /data 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "${_free_kb:-}" ] && [ "$_free_kb" -lt 5242880 ]; then
        _free_mb=$((_free_kb / 1024))
        echo "ERROR: /data has only ${_free_mb} MB free." >&2
        echo "       This installer requires at least 5 GB free for skills + Calibre +" >&2
        echo "       Python packages. Free up space or upgrade the VPS plan, then retry." >&2
        exit 1
    fi
fi

# ── 3. Safety belt ───────────────────────────────────────────────────────────
if [ ! -d /data ] && command -v docker >/dev/null 2>&1 \
   && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qE 'openclaw'; then
    echo "ERROR: An OpenClaw container is configured on this host but the" >&2
    echo "       auto-detect re-exec did not complete. Refusing to install" >&2
    echo "       to host /data/.openclaw (the container cannot see it)." >&2
    echo "" >&2
    echo "       Diagnose: docker ps -a | grep openclaw" >&2
    exit 1
fi

# ── 4. openclaw.json schema validation ──────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ] && command -v openclaw >/dev/null 2>&1; then
    if ! _validate_out=$(openclaw config validate 2>&1); then
        echo "ERROR: /data/.openclaw/openclaw.json is invalid before install starts." >&2
        echo "" >&2
        printf '  %s\n' "$_validate_out" | head -10 >&2
        echo "" >&2
        echo "  Fix: openclaw doctor --fix" >&2
        echo "  See: platform/vps/INSTALL-GOTCHAS.md (gotchas #6, #11)" >&2
        exit 1
    fi
fi

# ── 5. Prereq checks ─────────────────────────────────────────────────────────
for _required in curl python3; do
    command -v "$_required" >/dev/null 2>&1 || {
        echo "ERROR: $_required is required but not installed." >&2
        exit 1
    }
done
_missing_soft=""
for _soft in unzip wget lsof; do
    command -v "$_soft" >/dev/null 2>&1 || _missing_soft="${_missing_soft}${_soft} "
done
[ -n "$_missing_soft" ] && echo "[install] Soft prereqs missing: ${_missing_soft}— using fallbacks (see platform/vps/INSTALL-GOTCHAS.md)" >&2

# ── 6. VPS canonical path variables ──────────────────────────────────────────
OC_PLATFORM="vps"
OC_CONFIG="/data/.openclaw"
OC_JSON="/data/.openclaw/openclaw.json"
OC_SECRETS_ENV="/data/.openclaw/secrets/.env"
OC_WORKSPACE_DEFAULT="/data/.openclaw/workspace"
OC_CREDENTIALS="/data/.openclaw/credentials"
OC_AGENTS="/data/.openclaw/agents"
OC_SKILLS_DIR="/data/.openclaw/skills"
OC_LOGS="/data/.openclaw/logs"
OC_BACKUPS="/data/.openclaw/backups"
OC_INSTALL_LOG_DIR="/data/.openclaw/logs/install"
OC_AUTH_PROFILES="/data/.openclaw/agents/main/agent/auth-profiles.json"
OC_DOWNLOADS="/data/Downloads"
