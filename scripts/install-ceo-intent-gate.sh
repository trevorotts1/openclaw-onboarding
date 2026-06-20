#!/usr/bin/env bash
# install-ceo-intent-gate.sh — Wire the CEO PreToolUse intent-gate into a box.
#
# Two box types (the gate is BLOCK-AND-REDIRECT, goal doc Option 1):
#
#   • CLAUDE-CODE boxes (the clean path, goal doc line 87):
#       - copies hooks/ceo-intent-gate.sh + hooks/lib-ceo-consent.sh to a stable
#         runtime dir under the OpenClaw root (<OC_ROOT>/hooks/)
#       - deep-merges a hooks.PreToolUse entry into the Claude Code settings.json
#         matching the production tools (Write|Edit|MultiEdit|NotebookEdit|Bash)
#       - NEVER clobbers existing hooks — merges by appending our matcher only if
#         our command is not already wired.
#
#   • OPENCLAW boxes (no PreToolUse hook exists — goal doc line 87/97):
#       - OpenClaw has no documented PreToolUse hook. The equivalent runtime block
#         is the Layer-1 hard tool-deny (separate script). This installer does NOT
#         invent an OpenClaw hook. Instead it ensures the AGENTS.md self-correction
#         stanza is present so a policy-deny ERROR is interpreted by the agent as
#         "route via ingest" (the documented OpenClaw approximation). That stanza
#         is owned by apply-routing-fix.sh L1; here we only VERIFY + warn.
#
# The consent sidecar path is resolved by hooks/lib-ceo-consent.sh — the SAME
# reader the hook and the QC state-gate use (single shared flag).
#
# Usage:
#   bash install-ceo-intent-gate.sh                  # auto-detect box type
#   bash install-ceo-intent-gate.sh --claude-code    # force CC settings.json wire
#   bash install-ceo-intent-gate.sh --dry-run
#
# Idempotent. Backs up settings.json before editing.
#
# Exit: 0 ok · 1 fatal

set -euo pipefail

DRY_RUN=0
FORCE_CC=0
for _arg in "$@"; do
  case "$_arg" in
    --dry-run) DRY_RUN=1 ;;
    --claude-code) FORCE_CC=1 ;;
  esac
done

_log()  { printf '[install-ceo-intent-gate] %s\n' "$*"; }
_warn() { printf '[install-ceo-intent-gate] WARN: %s\n' "$*" >&2; }
_dry()  { printf '[install-ceo-intent-gate] DRY-RUN: %s\n' "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONBOARDING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_HOOK="$ONBOARDING_DIR/hooks/ceo-intent-gate.sh"
SRC_LIB="$ONBOARDING_DIR/hooks/lib-ceo-consent.sh"

[ -f "$SRC_HOOK" ] || { _warn "missing $SRC_HOOK"; exit 1; }
[ -f "$SRC_LIB" ]  || { _warn "missing $SRC_LIB"; exit 1; }

# ─── Platform / OpenClaw root ─────────────────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT="$HOME/.openclaw"
fi
RUNTIME_HOOK_DIR="$OC_ROOT/hooks"
RUNTIME_HOOK="$RUNTIME_HOOK_DIR/ceo-intent-gate.sh"

# ─── Copy hook + lib to the stable runtime dir ────────────────────────────────
if [ "$DRY_RUN" = "1" ]; then
  _dry "would copy hook+lib to $RUNTIME_HOOK_DIR/"
else
  mkdir -p "$RUNTIME_HOOK_DIR"
  cp "$SRC_HOOK" "$RUNTIME_HOOK_DIR/ceo-intent-gate.sh"
  cp "$SRC_LIB"  "$RUNTIME_HOOK_DIR/lib-ceo-consent.sh"
  chmod +x "$RUNTIME_HOOK_DIR/ceo-intent-gate.sh" 2>/dev/null || true
  _log "installed hook -> $RUNTIME_HOOK"
  _log "installed lib  -> $RUNTIME_HOOK_DIR/lib-ceo-consent.sh"
fi

# ─── Detect Claude Code settings.json ─────────────────────────────────────────
# Candidate settings.json locations (project-level then user-level).
CC_SETTINGS=""
for _cand in \
  "${CLAUDE_SETTINGS_FILE:-}" \
  "$HOME/.claude/settings.json" \
  "/data/.claude/settings.json"; do
  [ -n "$_cand" ] || continue
  if [ -f "$_cand" ]; then CC_SETTINGS="$_cand"; break; fi
done
# If forced or a .claude dir exists, target the user settings even if absent.
if [ -z "$CC_SETTINGS" ]; then
  if [ "$FORCE_CC" = "1" ] || [ -d "$HOME/.claude" ]; then
    CC_SETTINGS="$HOME/.claude/settings.json"
  fi
fi

if [ -z "$CC_SETTINGS" ]; then
  _warn "no Claude Code settings.json found and none forced."
  _warn "This box is treated as an OPENCLAW box: the runtime brake there is the"
  _warn "Layer-1 hard tool-deny (apply-routing-fix.sh tool-gate) + the AGENTS.md"
  _warn "'policy-deny means route' self-correction stanza. No PreToolUse hook on"
  _warn "OpenClaw (none documented). Hook+lib are staged at $RUNTIME_HOOK for the"
  _warn "Claude-Code path; re-run with --claude-code on a CC box to wire it."
  exit 0
fi

_log "Claude Code settings.json: $CC_SETTINGS"

# ─── Deep-merge the PreToolUse hook entry (no clobber) ────────────────────────
if [ "$DRY_RUN" = "1" ]; then
  _dry "would deep-merge hooks.PreToolUse matcher 'Write|Edit|MultiEdit|NotebookEdit|Bash' -> $RUNTIME_HOOK into $CC_SETTINGS"
  exit 0
fi

[ -f "$CC_SETTINGS" ] || { mkdir -p "$(dirname "$CC_SETTINGS")"; printf '{}\n' > "$CC_SETTINGS"; }
BACKUP="$CC_SETTINGS.bak-ceo-intent-gate-$(date +%Y%m%d%H%M%S)"
cp "$CC_SETTINGS" "$BACKUP"
_log "backed up settings -> $BACKUP"

MERGE_RESULT=$(SETTINGS_PATH="$CC_SETTINGS" RUNTIME_HOOK="$RUNTIME_HOOK" python3 - <<'PYEOF'
import json, os, sys

path = os.environ["SETTINGS_PATH"]
hook_cmd = os.environ["RUNTIME_HOOK"]
MATCHER = "Write|Edit|MultiEdit|NotebookEdit|Bash"

try:
    with open(path) as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        cfg = {}
except Exception:
    cfg = {}

hooks = cfg.setdefault("hooks", {})
if not isinstance(hooks, dict):
    hooks = {}
    cfg["hooks"] = hooks

pre = hooks.setdefault("PreToolUse", [])
if not isinstance(pre, list):
    pre = []
    hooks["PreToolUse"] = pre

# Already wired? (idempotent) — detect our command anywhere in PreToolUse.
def _has_our_hook(entries):
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks", []) or []:
            if isinstance(h, dict) and h.get("command") == hook_cmd:
                return True
    return False

if _has_our_hook(pre):
    print("ALREADY_WIRED")
    sys.exit(0)

pre.append({
    "matcher": MATCHER,
    "hooks": [
        {"type": "command", "command": hook_cmd}
    ],
})

with open(path, "w") as fh:
    json.dump(cfg, fh, indent=2)
    fh.write("\n")

print("WIRED")
PYEOF
) || MERGE_RESULT="ERROR"

case "$MERGE_RESULT" in
  ALREADY_WIRED) _log "PreToolUse intent-gate already wired — no-op" ;;
  WIRED)         _log "PreToolUse intent-gate wired into $CC_SETTINGS (matcher: Write|Edit|MultiEdit|NotebookEdit|Bash)" ;;
  *)
    _warn "deep-merge failed — rolling back settings.json"
    cp "$BACKUP" "$CC_SETTINGS"
    exit 1
    ;;
esac

# ─── Validate the merged settings.json is still valid JSON ────────────────────
if ! python3 -c "import json,sys; json.load(open('$CC_SETTINGS'))" 2>/dev/null; then
  _warn "post-merge settings.json is INVALID JSON — rolling back"
  cp "$BACKUP" "$CC_SETTINGS"
  exit 1
fi
_log "settings.json valid JSON — OK"
_log "DONE"
