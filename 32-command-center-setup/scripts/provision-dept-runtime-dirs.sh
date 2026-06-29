#!/usr/bin/env bash
# provision-dept-runtime-dirs.sh — the ONBOARDING HALF of the dispatch-furnace fix.
#
# The dispatch furnace had TWO onboarding-side causes that block a department from
# ever executing dispatched work:
#   1. The dispatcher expects a runtime dir per department agent
#      (<stateDir>/agents/<id>/agent, the gateway default), but if it is missing the
#      agent cannot be spawned for a routed task.
#   2. A dept agent with a NULL / empty / Anthropic / free-sentinel model cannot be
#      dispatched at all (dispatch is blocked by a model-less agent).
#
# This script makes BOTH idempotently true for EVERY dept-<slug> agent already in
# openclaw.json:
#   - ensures <stateDir>/agents/<agent-id>/agent/ exists (mkdir -p; idempotent), using
#     the agent entry's own agentDir when present (the authoritative gateway path).
#   - detects any dept agent whose model.primary is NULL / empty / a free sentinel /
#     Anthropic, and DELEGATES the repair to the existing scripts/repair-model-
#     sovereignty.sh (the box's OWN models, modality-correct cascade, NEVER Anthropic,
#     NEVER a hardcoded pin). It never re-implements model resolution.
#
# Department slugs are CANONICAL (shared-utils/canonical_slug.py is the single legacy->
# canonical alias map both Skill 23 and Skill 32 use), so a legacy slug the dispatcher
# might present resolves to the same canonical dept-<slug> runtime dir — no duplicate
# runtime dirs, no divergence.
#
# Idempotent + FAIL-SOFT: re-running creates nothing twice and never crashes the box.
#
# Usage:
#   bash 32-command-center-setup/scripts/provision-dept-runtime-dirs.sh [--dry-run] [--config <openclaw.json>]
#
# Exit codes:
#   0 — runtime dirs ensured (and model repair delegated when needed), or dry-run.
#   1 — fatal (no openclaw.json / python3 missing).

set -uo pipefail

DRY_RUN=0
CONFIG_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --config)  CONFIG_FILE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,33p' "$0"; exit 0 ;;
    *) shift ;;
  esac
done

# ─── Platform detection ──────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[provision-dept-runtime-dirs] FATAL: no OpenClaw root found" >&2
  exit 1
fi
[ -n "$CONFIG_FILE" ] || CONFIG_FILE="$OC_ROOT/openclaw.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "[provision-dept-runtime-dirs] FATAL: openclaw.json not found at $CONFIG_FILE" >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "[provision-dept-runtime-dirs] FATAL: python3 missing" >&2; exit 1; }

# ─── Ensure a runtime dir per dept agent + collect NULL-model offenders ───────
NEEDS_MODEL="$(OC_ROOT="$OC_ROOT" CONFIG_FILE="$CONFIG_FILE" DRY_RUN="$DRY_RUN" python3 - <<'PY'
import json, os
from pathlib import Path
oc_root = Path(os.environ["OC_ROOT"])
cfg_path = Path(os.environ["CONFIG_FILE"])
dry = os.environ.get("DRY_RUN") == "1"
try:
    cfg = json.loads(cfg_path.read_text())
except Exception as exc:
    print("", end="")
    import sys; print(f"[provision] cannot read config: {exc}", file=sys.stderr); raise SystemExit(0)

agents = ((cfg.get("agents") or {}).get("list")) or []
needs_model = []
made, present = 0, 0
import sys
def _ok(mid):
    low = (mid or "").strip().lower()
    return bool(low) and "anthropic/" not in low and "claude-" not in low and low not in ("openrouter/free", "free")

for a in agents:
    if not isinstance(a, dict):
        continue
    aid = a.get("id") or ""
    if not aid.startswith("dept-"):
        continue
    # authoritative agentDir when present, else the gateway default <stateDir>/agents/<id>/agent
    adir = a.get("agentDir") or str(oc_root / "agents" / aid / "agent")
    p = Path(adir)
    if p.exists():
        present += 1
    else:
        if dry:
            print(f"[provision] would create runtime dir: {p}", file=sys.stderr)
        else:
            p.mkdir(parents=True, exist_ok=True)
            made += 1
            print(f"[provision] created runtime dir: {p}", file=sys.stderr)
    # NULL / empty / forbidden model -> needs sovereign-model repair
    m = a.get("model")
    primary = m.get("primary") if isinstance(m, dict) else (m if isinstance(m, str) else None)
    if not _ok(primary):
        needs_model.append(aid)

print(f"[provision] dept runtime dirs: {present} present, {made} created "
      f"({'dry-run' if dry else 'applied'}); {len(needs_model)} agent(s) need a sovereign model.",
      file=sys.stderr)
# stdout = space-separated agent ids needing a model (consumed by the shell below)
print(" ".join(needs_model))
PY
)"

# ─── Delegate NULL-model repair to the existing sovereign-model resolver ──────
NEEDS_MODEL="$(printf '%s' "$NEEDS_MODEL" | tr -d '\n')"
if [[ -n "${NEEDS_MODEL// /}" ]]; then
  echo "[provision-dept-runtime-dirs] dept agents with NULL/forbidden model (dispatch-blocking): $NEEDS_MODEL"
  REPAIR="$REPO_ROOT/scripts/repair-model-sovereignty.sh"
  if [[ -f "$REPAIR" ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "[provision-dept-runtime-dirs] dry-run — would run: bash $REPAIR --config $CONFIG_FILE --apply (resolves each from the box's OWN models, never Anthropic)."
    else
      echo "[provision-dept-runtime-dirs] delegating sovereign-model repair to repair-model-sovereignty.sh (box's own models; never Anthropic)."
      bash "$REPAIR" --config "$CONFIG_FILE" --box "$(hostname)" --apply || \
        echo "[provision-dept-runtime-dirs] repair-model-sovereignty.sh returned non-zero (non-fatal); a model-less agent remains dispatch-blocked until repaired." >&2
    fi
  else
    echo "[provision-dept-runtime-dirs] repair-model-sovereignty.sh not found at $REPAIR — REPORT only; a model-less dept agent stays dispatch-blocked until a sovereign model is stamped." >&2
  fi
else
  echo "[provision-dept-runtime-dirs] all dept agents carry a sovereign (non-NULL, non-Anthropic) model — dispatch not model-blocked."
fi

echo "[provision-dept-runtime-dirs] done (idempotent, fail-soft)."
exit 0
