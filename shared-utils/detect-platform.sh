#!/usr/bin/env bash
# Platform detection for OpenClaw scripts.
# Sets OPENCLAW_ROOT and related paths based on detected environment.
#
# Source this file at the top of every shell script:
#   source "$(dirname "$0")/../shared-utils/detect-platform.sh"
#
# Exit code: 1 if no platform can be detected.

detect_openclaw_platform() {
  if [ -d "/data/.openclaw" ]; then
    # VPS / Hostinger Docker
    export OPENCLAW_ROOT="/data/.openclaw"
    export OPENCLAW_PLATFORM="vps"
    export OPENCLAW_WORKSPACE="/data/.openclaw/workspace"
    export OPENCLAW_SKILLS="/data/.openclaw/skills"
    export OPENCLAW_SECRETS="/data/.openclaw/secrets"
    export OPENCLAW_MASTER_FILES="/data/.openclaw/master-files"
    export OPENCLAW_COMPANY_ROOT="/data/.openclaw/workspace/zero-human-company"
  elif [ -d "$HOME/.openclaw" ]; then
    # Mac (new install)
    export OPENCLAW_ROOT="$HOME/.openclaw"
    export OPENCLAW_PLATFORM="mac"
    export OPENCLAW_WORKSPACE="$HOME/.openclaw/workspace"
    export OPENCLAW_SKILLS="$HOME/.openclaw/skills"
    export OPENCLAW_SECRETS="$HOME/.openclaw/secrets"
    export OPENCLAW_MASTER_FILES="$HOME/Downloads/openclaw-master-files"
    # Legacy workspace path support
    if [ -d "$HOME/clawd" ]; then
      export OPENCLAW_COMPANY_ROOT="$HOME/clawd/zero-human-company"
    else
      export OPENCLAW_COMPANY_ROOT="$HOME/.openclaw/workspace/zero-human-company"
    fi
  elif [ -d "$HOME/clawd" ]; then
    # Mac legacy (clawd era)
    export OPENCLAW_ROOT="$HOME/clawd"
    export OPENCLAW_PLATFORM="mac-legacy"
    export OPENCLAW_WORKSPACE="$HOME/clawd"
    export OPENCLAW_SKILLS="$HOME/clawd/skills"
    export OPENCLAW_SECRETS="$HOME/clawd/secrets"
    export OPENCLAW_MASTER_FILES="$HOME/Downloads/openclaw-master-files"
    export OPENCLAW_COMPANY_ROOT="$HOME/clawd/zero-human-company"
  else
    echo "ERROR: Cannot detect OpenClaw platform." >&2
    echo "None of these directories exist:" >&2
    echo "  - /data/.openclaw (expected on VPS / Hostinger Docker)" >&2
    echo "  - ~/.openclaw (expected on Mac, new install)" >&2
    echo "  - ~/clawd (expected on Mac, legacy install)" >&2
    echo "Run the OpenClaw installer before executing this script." >&2
    return 1
  fi
}

detect_openclaw_platform
