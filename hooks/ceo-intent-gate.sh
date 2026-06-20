#!/usr/bin/env bash
# ceo-intent-gate.sh — PreToolUse "Intent Gate" hook (Claude Code path).
#
# Goal doc Option 1 (lines 83-87): a PreToolUse hook on the AI CEO matching
# production tools (Write, Edit, Bash/exec, KIE skill, deck skill) checks a
# consent flag set only when the owner typed explicit consent.
#   • No consent  -> permissionDecision:"deny" with a redirect reason. The
#                    blocked reason feeds back into context so the CEO self-
#                    corrects and POSTs the task to /api/tasks/ingest instead.
#   • Consent     -> allow (exit 0, no output).
#
# This is the RUNTIME brake (goal doc line 135). It backstops the Layer-1 hard
# tool-deny for the consented-session edge case: during a consented session the
# CEO might try to self-execute an UNCONSENTED sub-task; the hook still fires a
# corrective deny.
#
# Claude Code PreToolUse protocol:
#   stdin  = JSON event: { "hook_event_name":"PreToolUse", "tool_name":"...",
#                          "tool_input":{...}, "session_id":"...", ... }
#   stdout = JSON decision (we emit hookSpecificOutput.permissionDecision)
#   exit 0 = our decision is in stdout; non-blocking tools just exit 0 silently.
#
# Consent is read via the SINGLE SHARED flag (hooks/lib-ceo-consent.sh) — the
# same sidecar the QC state-gate and the grant script use.
#
# Install: scripts/install-ceo-intent-gate.sh wires this into the box's
# Claude Code settings.json hooks.PreToolUse via JSON deep-merge.

set -euo pipefail

# ─── Locate the shared consent reader ─────────────────────────────────────────
_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_CONSENT_LIB=""
for _cand in \
  "$_HOOK_DIR/lib-ceo-consent.sh" \
  "/data/.openclaw/hooks/lib-ceo-consent.sh" \
  "$HOME/.openclaw/hooks/lib-ceo-consent.sh"; do
  [ -f "$_cand" ] && _CONSENT_LIB="$_cand" && break
done

if [ -z "$_CONSENT_LIB" ]; then
  # Fail OPEN on a missing library would defeat the gate. The consent reader is
  # mandatory; without it we cannot prove consent, so we FAIL CLOSED (deny).
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"CEO intent-gate consent library missing — failing closed. Route this work: POST /api/tasks/ingest with {title, description, department_slug}. The department specialist executes; you route."}}'
  exit 0
fi
# shellcheck source=/dev/null
. "$_CONSENT_LIB"

# ─── Read the hook event from stdin ───────────────────────────────────────────
_EVENT_JSON="$(cat 2>/dev/null || true)"

# Extract tool_name + session_id with python3 (robust to absent fields).
read -r TOOL_NAME SESSION_ID <<EOF
$(EVENT_JSON="$_EVENT_JSON" python3 - <<'PYEOF'
import json, os
try:
    ev = json.loads(os.environ.get("EVENT_JSON") or "{}")
except Exception:
    ev = {}
tool = ev.get("tool_name") or ev.get("toolName") or ""
sess = ev.get("session_id") or ev.get("sessionId") or ""
# Single-line, space-free fallbacks so the shell read split is safe.
print((tool or "_").replace(" ", "_"), (sess or "_").replace(" ", "_"))
PYEOF
)
EOF

[ "$TOOL_NAME" = "_" ] && TOOL_NAME=""
[ "$SESSION_ID" = "_" ] && SESSION_ID=""

# ─── Production-tool match list ───────────────────────────────────────────────
# Goal doc line 84: Write, Edit, Bash, exec, KIE skill, deck skill. We match the
# Claude Code built-in tool names (case-insensitive) plus the production skill
# invocations that produce deliverables. Read/Grep/Glob/WebFetch/WebSearch and
# the routing path (curl to ingest) are intentionally NOT matched.
#
# NOTE: Bash is matched broadly. The legitimate routing action (curl .../ingest)
# is allowed via a Bash-command allowlist check below — only NON-ingest Bash is
# treated as production. This preserves the CEO's ability to ROUTE while denying
# self-execution.
_is_production_tool() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    write|edit|multiedit|notebookedit|apply_patch|applypatch) return 0 ;;
    bash|exec|shell) return 0 ;;
    *) return 1 ;;
  esac
}

# If it's not a production tool, allow silently.
if ! _is_production_tool "$TOOL_NAME"; then
  exit 0
fi

# ─── Bash carve-out: allow ingest-routing commands, deny everything else ──────
# The CEO routes by POSTing to /api/tasks/ingest. A Bash call whose command is
# (only) a curl to the ingest endpoint is the routing action, not production —
# allow it even without consent. Any other Bash/exec is production -> gate it.
if printf '%s' "$TOOL_NAME" | grep -qiE '^(bash|exec|shell)$'; then
  _CMD="$(EVENT_JSON="$_EVENT_JSON" python3 - <<'PYEOF'
import json, os
try:
    ev = json.loads(os.environ.get("EVENT_JSON") or "{}")
except Exception:
    ev = {}
ti = ev.get("tool_input") or ev.get("toolInput") or {}
cmd = ""
if isinstance(ti, dict):
    cmd = ti.get("command") or ti.get("cmd") or ""
print(cmd if isinstance(cmd, str) else "")
PYEOF
)"
  # Routing allowlist: command references the ingest endpoint and is a curl/http
  # call. Conservative — must contain the ingest path AND look like an HTTP call.
  if printf '%s' "$_CMD" | grep -qE '/api/tasks/ingest' \
     && printf '%s' "$_CMD" | grep -qiE '\b(curl|wget|http)\b'; then
    exit 0
  fi
fi

# ─── Consent check (the single shared flag) ───────────────────────────────────
# Scope the consent to this session id so a task-scoped or session-scoped grant
# matches. A `global` or unexpired `until:` grant matches regardless.
if ceo_consent_active "$SESSION_ID"; then
  # Owner has consented — the carve-out path. Allow.
  exit 0
fi

# ─── No consent → DENY + REDIRECT ─────────────────────────────────────────────
# permissionDecision:"deny" with a redirect reason that is fed back into the
# CEO's context so it self-corrects and routes. Mirrors AGENTS.md owner-
# permission exception and the CEO_ROUTING_NO_LOOPHOLES_V1 doctrine.
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"CEO does not self-execute. Route this work instead: POST /api/tasks/ingest with {\"title\":\"...\",\"description\":\"...\",\"department_slug\":\"<dept-or-general-task>\"}. The department specialist executes; you route. (If the owner has explicitly consented to direct execution, they must grant consent via the owner consent flag first — you cannot grant it yourself.)"}}'
exit 0
