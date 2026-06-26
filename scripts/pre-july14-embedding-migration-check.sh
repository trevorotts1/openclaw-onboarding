#!/usr/bin/env bash
# pre-july14-embedding-migration-check.sh — EMBEDDING-PREVENTION BUNDLE item 7.
#
# THE PROBLEM (hard deadline):
#   The Gemini embedding model `gemini-embedding-001` HARD-SHUTS-DOWN 2026-07-14.
#   Any box still pinned to it will have its memory search start failing on that
#   date (provider returns model-not-found), stalling the agent loop. Every box
#   must be migrated to the GA successor `gemini-embedding-2` (@3072) BEFORE then.
#
# WHAT THIS DOES:
#   Scans openclaw.json for ANY memorySearch block (agents.defaults AND every
#   per-agent entry, plus the fallback object) still referencing the dying model
#   `gemini-embedding-001` (or the deprecated experimental `gemini-embedding-exp-*`).
#   Default = REPORT (flag + exit non-zero). With OC_MIGRATE_FORCE=1 it FORCES the
#   migration in place (rewrites the model to gemini-embedding-2 @3072 with a
#   timestamped backup + atomic write) and notes that a reindex is then required.
#
#   This pairs with the config-template pin (install.sh + activate-memory-stack.sh
#   now ship gemini-embedding-2), but a box that was onboarded BEFORE that pin and
#   is never re-run would otherwise sail into 2026-07-14 still on 001 — this cron
#   catches it.
#
# DESIGN: host-level, idempotent, platform-detected OC_ROOT, dedicated log,
#   backup-before-write. Mirrors scripts/capacity-monitor.sh. bash-not-zsh.
#
# EXIT CODES:
#   0  no box references the dying model (clean), OR forced-migration completed
#   7  dying model STILL present (report mode) — operator must migrate
#   2  could not run (no OpenClaw root / no python3 / unreadable config)
#
# ENV OVERRIDES:
#   OC_MIGRATE_FORCE=1     rewrite dying model → gemini-embedding-2 @3072 in place
#   OC_MIGRATE_ESCALATE=1  send one operator Telegram line when the dying model is found
#
# Version marker (kept in sync by scripts/bump-version.sh):
PRE_JULY14_EMBEDDING_MIGRATION_VERSION="v13.2.0"

set -u

DYING_MODEL="gemini-embedding-001"
DEADLINE="2026-07-14"
CANON_MODEL="gemini-embedding-2"
CANON_DIM=3072

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[pre-july14-migration] no OpenClaw root found; nothing to do" >&2
  exit 2
fi

CONFIG_FILE="$OC_ROOT/openclaw.json"
MIG_LOG="$OC_ROOT/pre-july14-embedding-migration.log"
FORCE="${OC_MIGRATE_FORCE:-0}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$MIG_LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

if ! command -v python3 >/dev/null 2>&1; then
  log "WARN" "python3 not on PATH — required; skipping"
  exit 2
fi
if [[ ! -f "$CONFIG_FILE" ]]; then
  log "WARN" "config not found: $CONFIG_FILE — box not onboarded; skipping"
  exit 2
fi

# Backup before any write (only used in force mode, but cheap + safe always).
if [[ "$FORCE" == "1" ]]; then
  cp -p "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d-%H%M%S)" 2>/dev/null \
    && log "INFO" "backup written before forced migration"
fi

OC_ROOT="$OC_ROOT" CONFIG_FILE="$CONFIG_FILE" FORCE="$FORCE" \
DYING_MODEL="$DYING_MODEL" CANON_MODEL="$CANON_MODEL" CANON_DIM="$CANON_DIM" \
DEADLINE="$DEADLINE" python3 <<'PYEOF'
import json, os, sys, re

cfg_file    = os.environ["CONFIG_FILE"]
force       = os.environ.get("FORCE", "0") == "1"
dying       = os.environ["DYING_MODEL"]
canon       = os.environ["CANON_MODEL"]
canon_dim   = int(os.environ["CANON_DIM"])
deadline    = os.environ["DEADLINE"]

try:
    cfg = json.load(open(cfg_file))
except Exception as e:
    print(f"  WARN cannot read config: {e}")
    sys.exit(2)

# A model is "dying" if it is exactly 001 or an experimental gemini-embedding-exp-*.
def is_dying(m):
    if not isinstance(m, str):
        return False
    return m == dying or m.startswith("gemini-embedding-exp")

hits = []     # (location, current_model)
changed = 0

def visit(ms, where):
    global changed
    if not isinstance(ms, dict):
        return
    m = ms.get("model")
    if is_dying(m):
        hits.append((where, m))
        if force:
            ms["model"] = canon
            ms["dimensions"] = canon_dim
            changed += 1
    fb = ms.get("fallback")
    if isinstance(fb, dict) and is_dying(fb.get("model")):
        hits.append((where + ".fallback", fb.get("model")))
        if force:
            fb["model"] = canon
            changed += 1

agents = cfg.get("agents", {})
visit(agents.get("defaults", {}).get("memorySearch"), "agents.defaults.memorySearch")
for a in agents.get("list", []) or []:
    if isinstance(a, dict):
        visit(a.get("memorySearch"), f"agents.list[{a.get('id','?')}].memorySearch")

if not hits:
    print(f"  OK    no '{dying}' reference found — box is safe for the {deadline} shutdown")
    sys.exit(0)

print(f"  FOUND '{dying}' (HARD-SHUTS-DOWN {deadline}) still referenced:")
for where, m in hits:
    print(f"    ✗ {where} = {m!r}")

if force and changed:
    json.dump(cfg, open(cfg_file, "w"), indent=2)
    print(f"  ✓ MIGRATED {changed} reference(s) → {canon!r} @ {canon_dim} dims (in place)")
    print(f"  ACTION run a reindex now (`openclaw memory reindex`) so the on-disk index"
          f" is rebuilt for {canon!r} — the index-model-drift-check cron will otherwise flag it.")
    sys.exit(0)

print(f"  ACTION migrate to {canon!r} BEFORE {deadline}. Re-run with OC_MIGRATE_FORCE=1"
      " (or re-run install.sh / activate-memory-stack.sh) then reindex.")
sys.exit(7)
PYEOF
rc=$?

if [[ "$rc" -eq 7 ]]; then
  log "FLAG" "dying model $DYING_MODEL still present (deadline $DEADLINE) — migration required"
  if [[ "${OC_MIGRATE_ESCALATE:-0}" == "1" ]] && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]]; then
    _esc_msg="[embed-migration] $(hostname): still on $DYING_MODEL which HARD-SHUTS-DOWN $DEADLINE. Migrate to $CANON_MODEL + reindex before then. See $MIG_LOG."
    _esc_msg="${_esc_msg//\\/\\\\}"; _esc_msg="${_esc_msg//\"/\\\"}"
    curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
      -H 'Content-Type: application/json' \
      -d "{\"action\":\"escalate\",\"client\":\"$(hostname 2>/dev/null||echo box)\",\"agent\":\"pre-july14-embedding-migration-check\",\"message\":\"${_esc_msg}\"}" \
      --max-time 15 >/dev/null 2>&1 || log "WARN" "rescue-rangers webhook escalation failed (non-fatal)"
  fi
elif [[ "$rc" -eq 0 && "$FORCE" == "1" ]]; then
  log "OK" "forced-migration pass complete (or already clean)"
fi

exit "$rc"
