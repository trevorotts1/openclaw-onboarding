#!/usr/bin/env bash
# Folded from .github/workflows/presentations-drift-gates.yml (job "drift-gates + Skill-51 verify.sh (vps)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export OPENCLAW_PLATFORM=vps
( # step: Announce matrix leg
echo "--- step: Announce matrix leg"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentations-drift-gates--vps: step \"Announce matrix leg\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
echo "OPENCLAW_PLATFORM=${OPENCLAW_PLATFORM} leg: drift gates + Skill-51 verify.sh"
)
( # step: presentations-drift-gates.sh — GATE 1 / GATE 2 / GATE 3 / GATE 4 / GATE 5 (exit 0 required)
echo "--- step: presentations-drift-gates.sh — GATE 1 / GATE 2 / GATE 3 / GATE 4 / GATE 5 (exit 0 required)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentations-drift-gates--vps: step \"presentations-drift-gates.sh — GATE 1 / GATE 2 / GATE 3 / GATE 4 / GATE 5 (exit 0 required)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
chmod +x scripts/ci/presentations-drift-gates.sh
bash scripts/ci/presentations-drift-gates.sh
)
( # step: Fix-50 client-name denylist lint -- roster-fed, SKIP when roster absent (exit 0 required)
echo "--- step: Fix-50 client-name denylist lint -- roster-fed, SKIP when roster absent (exit 0 required)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentations-drift-gates--vps: step \"Fix-50 client-name denylist lint -- roster-fed, SKIP when roster absent (exit 0 required)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# Fix 50: no real fleet-client name may appear in the fleet-wide shipped
# presentations files. The denylist is built at RUNTIME from the fleet
# roster -- never from a committed list of names. Resolution order
# mirrors shared-utils/resolve-client-chat-id.sh:
#   1. $OPENCLAW_FLEET_ROSTER (env override)
#   2. $HOME/clawd/fleet-prover/fleet-roster.json (operator-box default)
#   3. /data/clawd/fleet-prover/fleet-roster.json (container default)
# GitHub runners never carry the roster, so this step SKIPS there and
# enforces on hosts where the roster exists.
ROSTER=""
if [[ -n "${OPENCLAW_FLEET_ROSTER:-}" && -f "${OPENCLAW_FLEET_ROSTER}" ]]; then
  ROSTER="${OPENCLAW_FLEET_ROSTER}"
elif [[ -f "${HOME:-/root}/clawd/fleet-prover/fleet-roster.json" ]]; then
  ROSTER="${HOME:-/root}/clawd/fleet-prover/fleet-roster.json"
elif [[ -f "/data/clawd/fleet-prover/fleet-roster.json" ]]; then
  ROSTER="/data/clawd/fleet-prover/fleet-roster.json"
fi
if [[ -z "$ROSTER" ]]; then
  echo "client-name lint: SKIP -- no fleet roster found (needs OPENCLAW_FLEET_ROSTER or the operator roster path)."
  exit 0
fi
PATTERNS="$(mktemp)"
trap 'rm -f "$PATTERNS"' EXIT
python3 -c '
import json, sys
roster_path, out_path = sys.argv[1], sys.argv[2]
with open(roster_path, encoding="utf-8") as fh:
    data = json.load(fh)
boxes = data.get("boxes", {})
if not isinstance(boxes, dict):
    boxes = {}
names = set()
for entry in boxes.values():
    if not isinstance(entry, dict):
        continue
    name = str(entry.get("client", "") or "").strip()
    if name:
        names.add(name)
with open(out_path, "w", encoding="utf-8") as fh:
    for name in sorted(names):
        fh.write(name + "\n")
print("client-name lint: %d roster client name(s) loaded from %s" % (len(names), roster_path))
' "$ROSTER" "$PATTERNS"
if [[ ! -s "$PATTERNS" ]]; then
  echo "client-name lint: SKIP -- roster at $ROSTER carries no client names."
  exit 0
fi
SCAN_ROOT="23-ai-workforce-blueprint/templates/role-library/presentations"
if grep -rInF -f "$PATTERNS" --exclude-dir=.git "$SCAN_ROOT"; then
  echo "client-name lint: FAIL -- roster client name(s) appear in shipped presentations files (matches above)." >&2
  exit 1
fi
echo "client-name lint: PASS -- no roster client name found under $SCAN_ROOT."
)
( # step: 51-signature-presentation/verify.sh — Skill 51 self-verification (exit 0 required)
echo "--- step: 51-signature-presentation/verify.sh — Skill 51 self-verification (exit 0 required)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentations-drift-gates--vps: step \"51-signature-presentation/verify.sh — Skill 51 self-verification (exit 0 required)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
VERIFY_SH="51-signature-presentation/verify.sh"
if [ ! -f "$VERIFY_SH" ]; then
  echo "FATAL: verify.sh not found at $VERIFY_SH" >&2
  exit 2
fi
chmod +x "$VERIFY_SH"
# Same gate the former presentations-lockstep.yml ran (deleted
# 2026-10-08 in the CIO002 consolidation; its folded copy runs in
# scripts/ci/fast-guards.d/presentations-lockstep.sh via
# fast-guards.yml): five prover self-tests,
# sacred-structure pin, engine wire-presence, sync_check lockstep,
# manifest P-SP phase + AF-SP floor, prover resolvability, register
# --check, FIX-14 self-test, FIX-19 sliced read, FIX-18 self-test.
# On the vps leg OPENCLAW_PLATFORM=vps proves the CI-safe subset of
# those checks holds under VPS path resolution too.
bash "$VERIFY_SH"
echo "verify.sh: Skill 51 self-verification PASSED (OPENCLAW_PLATFORM=${OPENCLAW_PLATFORM})."
)
