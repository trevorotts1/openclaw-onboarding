#!/usr/bin/env bash
# repair-model-sovereignty.sh — retro-fix existing "no model" / "openrouter/free"
# agents + tasks on a box, per the PREFERENCE CASCADE (PLAN.md §8).
#
# WHAT IT FIXES (idempotent):
#   - openclaw.json agents whose primary model is null / a bare string-with-no-
#     fallbacks / the free sentinel / a forbidden (Anthropic) model -> re-resolves
#     a real, modality-correct, cascade-ordered dept-default model.
#   - Emits a CC-side repair payload (model-sweep receipt) listing every
#     agent_settings dept-default + tasks.model_id offender the CC repair driver
#     (command-center/scripts/repair-model-defaults.ts) must rewrite.
#   - Re-runs the AF-MODEL-SOVEREIGNTY gate over the box; the box is only marked
#     clean when the gate returns clean.
#
# DESIGN (per memory):
#   - PER-BOX receipt file (/tmp/model-sweep/<box>.json) — NEVER a shared ledger
#     appended by many concurrent agents (that loses writes).
#   - Idempotent: safe to re-run; skips agents already sovereign.
#   - Intended to run DETACHED on the box (the fleet driver SSHes, kicks this off
#     with nohup/at, and EXITS — never babysits). This script itself does only
#     local work on the box it runs on.
#   - Does NOT restart the gateway over SSH (N-rule: never `gateway restart` on a
#     rescue Mac over SSH). It only edits openclaw.json + writes a receipt; the
#     caller decides when/how to reload.
#
# USAGE (on the box):
#   repair-model-sovereignty.sh [--config <openclaw.json>] [--box <name>] \
#       [--receipt-dir /tmp/model-sweep] [--apply] [--shared-utils <dir>]
#
#   Without --apply it runs in DRY-RUN (reports offenders + planned fixes, writes
#   the receipt, changes nothing). With --apply it rewrites openclaw.json (after a
#   timestamped .bak) and re-runs the gate.
#
# EXIT: 0 = clean (or dry-run found nothing) ; 3 = offenders remain after repair ;
#       2 = could not locate config / shared-utils.
set -euo pipefail

CONFIG=""
BOX="$(hostname -s 2>/dev/null || echo box)"
RECEIPT_DIR="/tmp/model-sweep"
APPLY=0
SHARED_UTILS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2;;
    --box) BOX="$2"; shift 2;;
    --receipt-dir) RECEIPT_DIR="$2"; shift 2;;
    --apply) APPLY=1; shift;;
    --shared-utils) SHARED_UTILS="$2"; shift 2;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "[repair] unknown arg: $1" >&2; exit 2;;
  esac
done

# ── Locate openclaw.json ──
if [ -z "$CONFIG" ]; then
  for c in "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -f "$c" ] && CONFIG="$c" && break
  done
fi
if [ -z "$CONFIG" ] || [ ! -f "$CONFIG" ]; then
  echo "[repair] FATAL: no openclaw.json found (use --config)" >&2; exit 2
fi

# ── Locate shared-utils (select_model.py + assert_model_sovereignty.py) ──
if [ -z "$SHARED_UTILS" ]; then
  for d in \
    "$HOME/Downloads/openclaw-master-files/shared-utils" \
    "$HOME/.openclaw/skills/shared-utils" \
    "$(cd "$(dirname "$0")/../shared-utils" 2>/dev/null && pwd)"; do
    if [ -n "$d" ] && [ -f "$d/select_model.py" ] && [ -f "$d/assert_model_sovereignty.py" ]; then
      SHARED_UTILS="$d"; break
    fi
  done
fi
if [ -z "$SHARED_UTILS" ] || [ ! -f "$SHARED_UTILS/select_model.py" ]; then
  echo "[repair] FATAL: cannot find shared-utils (select_model.py)" >&2; exit 2
fi

mkdir -p "$RECEIPT_DIR"
RECEIPT="$RECEIPT_DIR/${BOX}.json"

echo "[repair] box=$BOX config=$CONFIG apply=$APPLY shared-utils=$SHARED_UTILS" >&2

# ── The work is in Python (JSON-safe edits + the cascade + the gate) ──
SHARED_UTILS="$SHARED_UTILS" CONFIG="$CONFIG" BOX="$BOX" RECEIPT="$RECEIPT" APPLY="$APPLY" \
python3 - <<'PY'
import json, os, sys, datetime
sys.path.insert(0, os.environ["SHARED_UTILS"])
import select_model as sm
import assert_model_sovereignty as gate

CONFIG = os.environ["CONFIG"]
BOX = os.environ["BOX"]
RECEIPT = os.environ["RECEIPT"]
APPLY = os.environ["APPLY"] == "1"

with open(CONFIG) as f:
    cfg = json.load(f)

inventory = sm._list_available_models(cfg)

FREE = set(sm.FREE_SENTINELS)

def is_offender(primary):
    if not primary or not str(primary).strip():
        return "NULL_MODEL"
    p = str(primary).strip().lower()
    if p in FREE:
        return "FREE_DEFAULT"
    if sm._is_forbidden(p):
        return "FORBIDDEN"
    if inventory and primary not in inventory:
        return "NOT_IN_INVENTORY"
    return None

def primary_of(model_field):
    if isinstance(model_field, str):
        return model_field
    if isinstance(model_field, dict):
        return model_field.get("primary") or model_field.get("model")
    return None

def dept_of_agent(agent_id):
    # dept-<slug> -> <slug> ; otherwise treat the id as the dept hint
    aid = agent_id or ""
    return aid[5:] if aid.startswith("dept-") else aid

agents = cfg.setdefault("agents", {})
alist = agents.setdefault("list", [])

openclaw_fixes = []   # changes we apply to openclaw.json on this box
cc_payload = {        # what the CC repair driver must rewrite in the CC DB
    "agent_settings_dept_defaults": [],   # offending dept defaults to re-resolve
    "tasks_model_id": [],                 # offending tasks to re-resolve (CC-side only)
}

for a in alist:
    if not isinstance(a, dict):
        continue
    aid = a.get("id", "?")
    primary = primary_of(a.get("model"))
    code = is_offender(primary)
    if not code:
        continue  # already sovereign — idempotent skip
    dept = dept_of_agent(aid)
    res = sm.resolve_dept_default_model(dept, inventory=inventory)
    new_model = res.get("model_id")
    fix = {
        "agent": aid, "department": dept, "old": primary, "offense": code,
        "new": new_model, "tier": res.get("tier"),
        "required_modality": res.get("required_modality"),
        "needs_owner_input": bool(res.get("needs_owner_input")),
    }
    openclaw_fixes.append(fix)
    # CC dept-default row to rewrite (role_id IS NULL, setting_type='model')
    cc_payload["agent_settings_dept_defaults"].append({
        "department": dept, "model_id": new_model,
        "setting_type": "model", "role_id": None,
        "needs_owner_input": bool(res.get("needs_owner_input")),
    })
    if APPLY and new_model and not res.get("needs_owner_input"):
        # Rewrite as the canonical N31 object form (primary + fallbacks).
        a["model"] = {
            "primary": new_model,
            "fallbacks": [
                "openrouter/moonshotai/kimi-k2.6",
                "ollama/deepseek-v4-pro:cloud",
                "openrouter/deepseek/deepseek-v4-pro",
            ],
        }

if APPLY and openclaw_fixes:
    import shutil
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{CONFIG}.bak-model-sweep-{ts}"
    # Back up the ORIGINAL config byte-for-byte before rewriting.
    shutil.copy2(CONFIG, bak)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[repair] applied {len(openclaw_fixes)} fix(es); backup -> {bak}", file=sys.stderr)

# ── Re-run the gate over the (possibly repaired) config — ground truth ──
offenders_after, scanned = gate.scan_config(CONFIG)

receipt = {
    "box": BOX,
    "config": CONFIG,
    "ts": datetime.datetime.now().isoformat(),
    "apply": APPLY,
    "inventory_count": len(inventory),
    "openclaw_fixes_planned": openclaw_fixes,
    "cc_repair_payload": cc_payload,
    "gate_scanned": len(scanned),
    "gate_offenders_after": offenders_after,
    "clean": not offenders_after,
}
with open(RECEIPT, "w") as f:
    json.dump(receipt, f, indent=2)
print(f"[repair] receipt -> {RECEIPT} (clean={not offenders_after}, "
      f"planned_fixes={len(openclaw_fixes)}, "
      f"cc_dept_defaults={len(cc_payload['agent_settings_dept_defaults'])})", file=sys.stderr)

sys.exit(0 if not offenders_after else 3)
PY
rc=$?
echo "[repair] done (rc=$rc). receipt: $RECEIPT" >&2
exit $rc
