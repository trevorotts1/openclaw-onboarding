#!/usr/bin/env bash
# lib-paths.sh - Skill 70 (Pointer References): one place that resolves the
# box paths every Skill 70 script needs. Sourced, never executed.
#
# Platform rule (same one update-skills.sh and the other skill installers use):
#   a box that has /data/.openclaw/openclaw.json is a virtual private server
#   running OpenClaw in Docker; everything else is a Mac.
#     Mac:    ~/.openclaw/  ~/Downloads/openclaw-master-files/  ~/Downloads/openclaw-backups/
#     Server: /data/.openclaw/  /data/.openclaw/master-files/   /data/.openclaw/backups/
# Every value can be overridden by an environment variable (used by the tests).
#
# Compatible with macOS bash 3.2 and Linux bash.

pr_is_server() { [ -f /data/.openclaw/openclaw.json ]; }

pr_ocroot() {
  if [ -n "${OPENCLAW_ROOT_DIR:-}" ]; then printf '%s' "$OPENCLAW_ROOT_DIR"; return 0; fi
  if pr_is_server; then printf '%s' "/data/.openclaw"; else printf '%s' "$HOME/.openclaw"; fi
}

pr_master_files() {
  if [ -n "${OPENCLAW_MASTER_FILES_DIR:-}" ]; then printf '%s' "$OPENCLAW_MASTER_FILES_DIR"; return 0; fi
  if pr_is_server; then printf '%s' "/data/.openclaw/master-files"; else printf '%s' "$HOME/Downloads/openclaw-master-files"; fi
}

pr_backup_root() {
  if [ -n "${OPENCLAW_BACKUP_DIR:-}" ]; then printf '%s' "$OPENCLAW_BACKUP_DIR"; return 0; fi
  if pr_is_server; then printf '%s' "/data/.openclaw/backups"; else printf '%s' "$HOME/Downloads/openclaw-backups"; fi
}

# The main agent's workspace (where AGENTS.md, MEMORY.md and the other core
# files live). Same resolution order as update-skills.sh's core-update wiring:
# $OPENCLAW_WORKSPACE, then openclaw.json (agents.entries.main.workspace, the
# legacy agents.list[] main entry, agents.defaults.workspace), then
# <openclaw-root>/workspace. Reads only the workspace key; prints nothing else.
pr_workspace() {
  if [ -n "${OPENCLAW_WORKSPACE:-}" ]; then printf '%s' "$OPENCLAW_WORKSPACE"; return 0; fi
  local root ocjson ws=""
  root="$(pr_ocroot)"
  ocjson="$root/openclaw.json"
  if [ -f "$ocjson" ] && command -v python3 >/dev/null 2>&1; then
    ws="$(OC_JSON="$ocjson" python3 - <<'PY' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    a = cfg.get("agents", {}) or {}
    e = a.get("entries") if isinstance(a.get("entries"), dict) else {}
    lst = a.get("list") if isinstance(a.get("list"), list) else []
    w = ((e.get("main") or {}).get("workspace")
         or next((x.get("workspace") for x in lst
                  if isinstance(x, dict) and x.get("id") == "main" and x.get("workspace")), None)
         or (a.get("defaults") or {}).get("workspace"))
    if w:
        print(os.path.expanduser(w))
except Exception:
    pass
PY
)"
  fi
  [ -n "$ws" ] || ws="$root/workspace"
  printf '%s' "$ws"
}

# Where the installed skill folder lives on this box.
pr_skill_dir() { printf '%s' "$(pr_ocroot)/skills/70-pointer-references"; }

# Skill 70's own folder inside the master files folder: the installed copy of
# the playbook, the weekly reports and the first-run marker live here.
pr_skill_home() { printf '%s' "$(pr_master_files)/70-pointer-references"; }
