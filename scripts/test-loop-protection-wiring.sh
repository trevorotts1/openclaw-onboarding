#!/usr/bin/env bash
# ============================================================
# scripts/test-loop-protection-wiring.sh
# ============================================================
# Offline, no-network, no-openclaw-CLI proof that the furnace / loop protection
# pair (Skill 60 EWS + Skill 61 Loop Protection) is WIRED into onboarding + the
# updater, HELD by default, and that the shared helper + operator-box
# first-proof script work.
#
# GRAPHICS-FURNACE-CONTEXT-RESCUE-SPEC Topic 2, §2.3 items 1-2.
#
# WHAT IS VERIFIED:
#   W1  install.sh runs the shared activation helper with --role client
#   W2  update-skills.sh runs the shared activation helper with --role client
#   W3  install.sh persists activate-loop-protection.sh + BOTH loop-protection
#       first-proof script names (new path + the D20 one-release old-path shim)
#   W4  update-skills.sh persists the same three (survive temp-clone)
#   W5  the fleet rollout gate exists and defaults to HELD (fleet_rollout_enabled=false)
#   W6  scripts/activate-loop-protection.sh --self-test PASSES (gate + 60->61 order + never-arm)
#   W7  scripts/loop-protection-first-proof.sh --self-test PASSES (install/burn-in/arm gate/disarm)
#   W8  Skill 60 install.sh --self-test PASSES  (installer intact, idempotent, never re-pins)
#   W9  Skill 61 install.sh --self-test PASSES  (installer intact, idempotent, never arms)
#   W10 D20 rename (U93): scripts/loop-protection-canary.sh (old path) is a
#       compatibility shim whose --self-test output is BYTE-IDENTICAL to the
#       new path's — proves the shim delegates, not just that it runs
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
FIRST_PROOF="$REPO/scripts/loop-protection-first-proof.sh"
OLD_PATH_SHIM="$REPO/scripts/loop-protection-canary.sh"
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

# W3 — install.sh persists all three (helper + new first-proof path + old shim)
if grep -Eq 'activate-loop-protection.sh loop-protection-first-proof.sh loop-protection-canary.sh' "$INSTALL"; then
    ok "W3 install.sh persists activate-loop-protection.sh + loop-protection-first-proof.sh + the loop-protection-canary.sh shim"
else
    bad "W3 install.sh does not persist all three loop-protection scripts"
fi

# W4 — update-skills.sh persists the full canonical tree, which includes all
# three loop-protection entrypoints. Do not reintroduce a filename allowlist.
if grep -q 'deliver_canonical_scripts_tree "$ONBOARDING_DIR/scripts"' "$UPDATE" \
   && [ -f "$REPO/scripts/activate-loop-protection.sh" ] \
   && [ -f "$REPO/scripts/loop-protection-first-proof.sh" ] \
   && [ -f "$REPO/scripts/loop-protection-canary.sh" ]; then
    ok "W4 update-skills.sh recursive delivery persists all three loop-protection scripts"
else
    bad "W4 update-skills.sh full-tree delivery does not persist all three loop-protection scripts"
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
        bad "W5 rollout gate not HELD by default (got: $HELD) — a client box would auto-activate before the operator's own first-proof run"
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

# W7 — new-path first-proof self-test (tmp output kept for W10's diff below)
if bash "$FIRST_PROOF" --self-test >/tmp/lp-w7.$$ 2>&1; then
    ok "W7 loop-protection-first-proof.sh --self-test"
else
    bad "W7 loop-protection-first-proof.sh --self-test FAILED"; sed 's/^/      /' /tmp/lp-w7.$$ >&2
fi

# W10 — D20 rename (U93): the old-path shim must exist, be executable, and its
# --self-test output must be BYTE-IDENTICAL to the new path's — this proves the
# shim actually delegates to the new script rather than merely also passing on
# its own (a regression here would mean the old path silently forked behavior).
if [ -x "$OLD_PATH_SHIM" ]; then
    if bash "$OLD_PATH_SHIM" --self-test >/tmp/lp-w10.$$ 2>&1; then
        if diff -q /tmp/lp-w7.$$ /tmp/lp-w10.$$ >/dev/null 2>&1; then
            ok "W10 loop-protection-canary.sh (old-path shim) --self-test output is byte-identical to the new path"
        else
            bad "W10 old-path shim --self-test output DIFFERS from the new path — shim has drifted from a pure delegate"
            diff /tmp/lp-w7.$$ /tmp/lp-w10.$$ | sed 's/^/      /' >&2 || true
        fi
    else
        bad "W10 loop-protection-canary.sh (old-path shim) --self-test FAILED"; sed 's/^/      /' /tmp/lp-w10.$$ >&2
    fi
else
    bad "W10 old-path shim scripts/loop-protection-canary.sh missing or not executable"
fi
rm -f /tmp/lp-w7.$$ /tmp/lp-w10.$$ 2>/dev/null || true

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
