#!/usr/bin/env bash
# ============================================================
# scripts/test-loop-protection-wiring.sh
# ============================================================
# Offline, no-network, no-openclaw-CLI proof that the furnace / loop protection
# pair (Skill 60 EWS + Skill 61 Loop Protection) is WIRED into onboarding + the
# updater, HELD by default, and that the shared helper + operator canary work.
#
# GRAPHICS-FURNACE-CONTEXT-RESCUE-SPEC Topic 2, §2.3 items 1-2.
#
# WHAT IS VERIFIED:
#   W1  install.sh runs the shared activation helper with --role client
#   W2  update-skills.sh runs the shared activation helper with --role client
#   W3  install.sh persists BOTH loop-protection scripts to $SCRIPTS_DIR
#   W4  update-skills.sh persists BOTH loop-protection scripts (survive temp-clone)
#   W5  the fleet rollout gate exists and defaults to HELD (fleet_rollout_enabled=false)
#   W6  scripts/activate-loop-protection.sh --self-test PASSES (gate + 60->61 order + never-arm)
#   W7  scripts/loop-protection-canary.sh  --self-test PASSES (install/burn-in/arm gate/disarm)
#   W8  Skill 60 install.sh --self-test PASSES  (installer intact, idempotent, never re-pins)
#   W9  Skill 61 install.sh --self-test PASSES  (installer intact, idempotent, never arms)
#
# Usage: bash scripts/test-loop-protection-wiring.sh
# Exit 0 = all pass. Exit 1 = one or more failures.
# ============================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="$(cd "$SELF_DIR/.." && pwd)"
PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*" >&2; FAIL=$((FAIL+1)); }

INSTALL="$REPO/install.sh"
UPDATE="$REPO/update-skills.sh"
ACT="$REPO/scripts/activate-loop-protection.sh"
CANARY="$REPO/scripts/loop-protection-canary.sh"
ROLLOUT="$REPO/61-loop-protection-system/config/rollout.json"

echo "== loop-protection wiring test =="

# W1 — install.sh invokes the helper with --role client
if grep -q 'activate-loop-protection.sh' "$INSTALL" && grep -Eq 'bash "\$_ACT_LOOP" --role client' "$INSTALL"; then
    ok "W1 install.sh runs activate-loop-protection.sh --role client"
else
    bad "W1 install.sh does not run the activation helper with --role client"
fi

# W2 — update-skills.sh invokes the helper with --role client
if grep -q 'activate-loop-protection.sh' "$UPDATE" && grep -Eq 'bash "\$_ACT_LOOP" --role client' "$UPDATE"; then
    ok "W2 update-skills.sh runs activate-loop-protection.sh --role client"
else
    bad "W2 update-skills.sh does not run the activation helper with --role client"
fi

# W3 — install.sh persists both scripts
if grep -Eq 'activate-loop-protection.sh loop-protection-canary.sh' "$INSTALL"; then
    ok "W3 install.sh persists activate-loop-protection.sh + loop-protection-canary.sh"
else
    bad "W3 install.sh does not persist both loop-protection scripts"
fi

# W4 — update-skills.sh persists both scripts (in the persistent-copy loop)
if grep -q 'activate-loop-protection.sh loop-protection-canary.sh' "$UPDATE"; then
    ok "W4 update-skills.sh persists activate-loop-protection.sh + loop-protection-canary.sh"
else
    bad "W4 update-skills.sh does not persist both loop-protection scripts"
fi

# W5 — rollout gate exists + defaults HELD
if [ -f "$ROLLOUT" ] && command -v python3 >/dev/null 2>&1; then
    HELD="$(CFG="$ROLLOUT" python3 - <<'PY' 2>/dev/null || echo error
import json, os
try:
    d = json.load(open(os.environ["CFG"]))
    print("held" if d.get("fleet_rollout_enabled") is False else "OPEN")
except Exception:
    print("error")
PY
)"
    if [ "$HELD" = "held" ]; then
        ok "W5 fleet rollout gate present and defaults HELD (fleet_rollout_enabled=false)"
    else
        bad "W5 rollout gate not HELD by default (got: $HELD) — a client box would auto-activate before the canary"
    fi
else
    bad "W5 rollout.json missing at $ROLLOUT (or python3 absent)"
fi

# W6 — activation helper self-test
if bash "$ACT" --self-test >/tmp/lp-w6.$$ 2>&1; then
    ok "W6 activate-loop-protection.sh --self-test"
else
    bad "W6 activate-loop-protection.sh --self-test FAILED"; sed 's/^/      /' /tmp/lp-w6.$$ >&2
fi
rm -f /tmp/lp-w6.$$ 2>/dev/null || true

# W7 — canary self-test
if bash "$CANARY" --self-test >/tmp/lp-w7.$$ 2>&1; then
    ok "W7 loop-protection-canary.sh --self-test"
else
    bad "W7 loop-protection-canary.sh --self-test FAILED"; sed 's/^/      /' /tmp/lp-w7.$$ >&2
fi
rm -f /tmp/lp-w7.$$ 2>/dev/null || true

# W8 — Skill 60 installer self-test
if bash "$REPO/60-zhc-early-warning-system/install.sh" --self-test >/tmp/lp-w8.$$ 2>&1; then
    ok "W8 Skill 60 install.sh --self-test"
else
    bad "W8 Skill 60 install.sh --self-test FAILED"; sed 's/^/      /' /tmp/lp-w8.$$ >&2
fi
rm -f /tmp/lp-w8.$$ 2>/dev/null || true

# W9 — Skill 61 installer self-test
if bash "$REPO/61-loop-protection-system/install.sh" --self-test >/tmp/lp-w9.$$ 2>&1; then
    ok "W9 Skill 61 install.sh --self-test"
else
    bad "W9 Skill 61 install.sh --self-test FAILED"; sed 's/^/      /' /tmp/lp-w9.$$ >&2
fi
rm -f /tmp/lp-w9.$$ 2>/dev/null || true

echo ""
echo "== result: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
