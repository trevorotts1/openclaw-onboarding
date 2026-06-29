#!/usr/bin/env bash
# shared-utils/workspace-dept-refresh.sh
# ─────────────────────────────────────────────────────────────────────────────
# Shared helper: refresh a box's LIVE workspace department tree after a library
# update, so newly-shipped floor roles / SOPs / dept structure actually land in
# the client's departments/ and agents/ trees (not just in skills/).
#
# This is the additive department-refresh flow extracted into ONE sourceable
# entry point so install.sh / update-skills.sh call it instead of inlining the
# two-step migrate + staleness-detect sequence. It is the workspace twin of
# reconcile_qmd_persona_index (qmd store) and rewire_on_persona_set_change
# (governing-personas.md) — those refresh derived artifacts; THIS refreshes the
# department tree itself.
#
# It does two additive, idempotent things:
#   (1) MATERIALIZE — run migrate-existing-workforce.sh <client> --apply, which
#       installs copied skills into the dept tree and (v16.0.2+) fills missing
#       canonical floor roles/SOPs via floor-fill. Skip-existing, no-clobber.
#   (2) DETECT — run detect-stale-artifacts.py to compute which built roles/depts/
#       SOPs are stale vs the new role-library content manifest, and persist the
#       work queue (.artifact-refresh-queue.json) for a follow-up re-instantiation
#       pass. READ-ONLY: it queues, it does not mutate client bytes.
#
# NEVER restarts a gateway. NEVER edits openclaw.json. NEVER deletes/overwrites
# existing department content (migrate is skip-existing; detect is read-only).
#
# Source this file (do NOT execute it directly) then call:
#
#   refresh_workspace_departments <SKILLS_DIR> <WORKSPACE_DIR> [CLIENT]
#
#   SKILLS_DIR     installed skills root (…/.openclaw/skills) — holds skill 23.
#   WORKSPACE_DIR  active workspace root (the dir containing departments/).
#   CLIENT         optional client/box name for migrate; defaults to hostname.
#
# Always returns 0 (fully additive — warnings are logged, never fatal) unless
# called with missing required args (returns 1). Honors REFRESH_LOG_FILE for the
# migrate log tail (defaults to a temp file).
#
# Callers: install.sh Step 6b, update-skills.sh post-extract workforce pass.
# ─────────────────────────────────────────────────────────────────────────────

refresh_workspace_departments() {
    local _skills_dir="$1"
    local _ws="$2"
    local _client="${3:-$(hostname 2>/dev/null || echo unknown)}"
    local _log="${REFRESH_LOG_FILE:-$(mktemp 2>/dev/null || echo /tmp/workspace-dept-refresh.log)}"

    if [ -z "$_skills_dir" ] || [ -z "$_ws" ]; then
        echo "  dept-refresh: usage: refresh_workspace_departments <SKILLS_DIR> <WORKSPACE_DIR> [CLIENT]" >&2
        return 1
    fi

    local _blueprint="$_skills_dir/23-ai-workforce-blueprint"

    # ── (1) MATERIALIZE — migrate-existing-workforce.sh --apply ──────────────
    local _migrate="$_blueprint/scripts/migrate-existing-workforce.sh"
    if [ -f "$_migrate" ]; then
        echo "  dept-refresh: materializing floor roles/SOPs into dept tree (migrate --apply, additive)..."
        if bash "$_migrate" "$_client" --apply >> "$_log" 2>&1; then
            echo "  dept-refresh: migrate OK"
        else
            echo "  dept-refresh: migrate completed with warnings (see $_log)"
        fi
    else
        echo "  dept-refresh: migrate-existing-workforce.sh not found — skipping materialize (additive)"
    fi

    # ── (2) DETECT — per-artifact staleness → refresh work queue ─────────────
    local _detect="$_blueprint/scripts/detect-stale-artifacts.py"
    local _manifest="$_blueprint/templates/role-library/_index.json"

    if ! command -v python3 >/dev/null 2>&1; then
        echo "  dept-refresh: python3 not found — skipping staleness detect (additive)"
        return 0
    fi
    if [ ! -f "$_detect" ] || [ ! -f "$_manifest" ]; then
        echo "  dept-refresh: detect-stale-artifacts.py / manifest absent — skipping staleness detect (additive)"
        return 0
    fi
    if [ ! -d "$_ws/departments" ] && [ ! -f "$_ws/.workforce-build-state.json" ]; then
        echo "  dept-refresh: no departments/ tree or build-state at $_ws — nothing to detect (additive)"
        return 0
    fi

    echo "  dept-refresh: detecting per-artifact staleness vs new library manifest..."
    local _out _rc=0
    _out="$(python3 "$_detect" --workspace "$_ws" --manifest "$_manifest" --json 2>>"$_log")" || _rc=$?

    if [ -n "$_out" ]; then
        local _queue="$_ws/.artifact-refresh-queue.json"
        printf '%s' "$_out" > "$_queue" 2>/dev/null || true
        printf '%s' "$_out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
s = d.get('summary', {})
act = s.get('stale',0)+s.get('missing',0)+s.get('orphan',0)+s.get('untracked',0)
print(f\"  dept-refresh: artifact staleness CURRENT={s.get('current',0)} STALE={s.get('stale',0)} \"
      f\"MISSING={s.get('missing',0)} ORPHAN={s.get('orphan',0)} UNTRACKED={s.get('untracked',0)}\")
if act:
    print(f'  dept-refresh: {act} artifact(s) queued for refresh (.artifact-refresh-queue.json)')
else:
    print('  dept-refresh: all artifacts CURRENT (nothing to refresh)')
" 2>/dev/null || true
        [ "$_rc" -eq 10 ] && echo "  dept-refresh: refresh queue written: $_queue"
    else
        echo "  dept-refresh: detect produced no output — skipping (see $_log)"
    fi

    return 0
}
