#!/usr/bin/env bash
# ============================================================
# scripts/loop-registry.sh — Loop Registry (PRD 2.13)
# ============================================================
# Every autonomous loop (cron watchdog) that runs during onboarding
# MUST register itself here. The closeout QC asserts this registry
# is empty when onboarding finishes (no ghost loops left running).
#
# REGISTRY FILE:
#   $OC_WORKSPACE/.loop-registry.json
#   {
#     "loops": {
#       "<name>": {
#         "name": "watchdog-onboarding-loop",
#         "cronUuid": "<openclaw-cron-uuid>",
#         "registeredAt": "2026-06-10T00:00:00Z",
#         "killCommand": "openclaw cron rm <uuid>",
#         "status": "running|killed"
#       }
#     }
#   }
#
# DESIGN RULES
#   - Pure bash + python3. jq optional.
#   - Idempotent: re-registering the same name updates (not duplicates).
#   - lr_assert_empty exits 1 with LOUD stderr if any loop is still "running".
#     Called by closeout QC and the fixture test kill-condition check.
# ============================================================

: "${OC_CONFIG:=/data/.openclaw}"
: "${OC_WORKSPACE:=$OC_CONFIG/workspace}"
LOOP_REGISTRY_FILE="${LOOP_REGISTRY_FILE:-$OC_WORKSPACE/.loop-registry.json}"

_lr_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ------------------------------------------------------------
# lr_register <name> <cron_uuid> <kill_command>
#   Register or update a loop entry (status=running).
# ------------------------------------------------------------
lr_register() {
  local name="$1" cron_uuid="$2" kill_cmd="$3"
  mkdir -p "$(dirname "$LOOP_REGISTRY_FILE")" 2>/dev/null || true
  NAME="$name" UUID="$cron_uuid" KILL="$kill_cmd" NOW="$(_lr_now)" \
  FILE="$LOOP_REGISTRY_FILE" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
f = os.environ["FILE"]
try:    reg = json.load(open(f))
except Exception: reg = {}
loops = reg.setdefault("loops", {})
loops[os.environ["NAME"]] = {
    "name": os.environ["NAME"],
    "cronUuid": os.environ["UUID"],
    "registeredAt": os.environ["NOW"],
    "killCommand": os.environ["KILL"],
    "status": "running",
}
json.dump(reg, open(f, "w"), indent=2)
PYEOF
}

# ------------------------------------------------------------
# lr_kill <name>
#   Mark a loop as killed in the registry (does NOT run the kill command —
#   the watchdog calls openclaw cron rm itself before calling lr_kill).
# ------------------------------------------------------------
lr_kill() {
  local name="$1"
  [ -f "$LOOP_REGISTRY_FILE" ] || return 0
  NAME="$name" FILE="$LOOP_REGISTRY_FILE" python3 - <<'PYEOF' 2>/dev/null || true
import json, os, sys
f = os.environ["FILE"]
try:    reg = json.load(open(f))
except Exception: sys.exit(0)
loops = reg.get("loops", {})
if os.environ["NAME"] in loops:
    loops[os.environ["NAME"]]["status"] = "killed"
json.dump(reg, open(f, "w"), indent=2)
PYEOF
}

# ------------------------------------------------------------
# lr_list
#   Print a human-readable table of all registered loops.
# ------------------------------------------------------------
lr_list() {
  [ -f "$LOOP_REGISTRY_FILE" ] || { echo "(loop registry empty — no file)"; return 0; }
  FILE="$LOOP_REGISTRY_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:    reg = json.load(open(os.environ["FILE"]))
except Exception: print("(loop registry: parse error)"); raise SystemExit
loops = reg.get("loops", {})
if not loops: print("(loop registry empty)"); raise SystemExit
print(f"{'NAME':<35} {'STATUS':<10} {'UUID':<40} REGISTERED")
for k, v in sorted(loops.items()):
    print(f"{v.get('name','?'):<35} {v.get('status','?'):<10} {v.get('cronUuid','?'):<40} {v.get('registeredAt','?')}")
PYEOF
}

# ------------------------------------------------------------
# lr_assert_empty
#   Exit 1 if ANY loop has status=running.
#   Used by closeout QC and the fixture test's kill-condition check.
# ------------------------------------------------------------
lr_assert_empty() {
  [ -f "$LOOP_REGISTRY_FILE" ] || return 0
  FILE="$LOOP_REGISTRY_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
try:    reg = json.load(open(os.environ["FILE"]))
except Exception: sys.exit(0)
running = [k for k, v in reg.get("loops", {}).items() if v.get("status") == "running"]
if running:
    print(f"LOOP REGISTRY NOT EMPTY — still running: {', '.join(running)}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYEOF
}

# ------------------------------------------------------------
# lr_get_uuid <name>
#   Print the cron UUID for the named loop, or empty string.
# ------------------------------------------------------------
lr_get_uuid() {
  local name="$1"
  [ -f "$LOOP_REGISTRY_FILE" ] || return 0
  NAME="$name" FILE="$LOOP_REGISTRY_FILE" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:    reg = json.load(open(os.environ["FILE"]))
except Exception: raise SystemExit
e = reg.get("loops", {}).get(os.environ["NAME"], {})
print(e.get("cronUuid", ""))
PYEOF
}
