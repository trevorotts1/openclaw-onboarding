#!/usr/bin/env bash
# sp-hook.sh — thin dispatcher for Skill 51 host hooks (PRES-051).
# Install-relative: resolves the skill dir from its own path, never $HOME.
# Usage: sp-hook.sh {session-start|pre-tool-use|post-tool-use|stop} < stdin-event.json
# All handlers are local, bounded (see hooks/hooks.json timeouts), read-only
# toward the engine. Never invokes a Claude binary. Never prints secrets.
set -uo pipefail
SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PY="${PYTHON:-python3}"
case "${1:-}" in
    session-start) exec "$PY" "$SELF/sp_session_start.py" ;;
    pre-tool-use)  exec "$PY" "$SELF/sp_pre_tool_use.py" ;;
    post-tool-use) exec "$PY" "$SELF/sp_post_tool_use.py" ;;
    stop)          exec "$PY" "$SELF/sp_stop.py" ;;
    *) echo "sp-hook.sh: usage: $0 {session-start|pre-tool-use|post-tool-use|stop}" >&2; exit 2 ;;
esac
