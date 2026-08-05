#!/usr/bin/env bash
# CEO gate removed 2026-08-05 per Trevor — was creating loops; see openclaw-telegram-master-plan.md
# u134-tool-allowlist-patch.sh -- NOW A NO-OP. The CEO production-tool deny has been
# removed from the canonical source (hooks/lib-ceo-tool-gate.sh CEO_GATE_DENY_TOOLS=()).
# This script is kept present but inert so existing caller sites (install.sh, update-skills.sh)
# do not break; it always reports CANONICAL_SKIP and exits 0.
set -euo pipefail
echo "[u134] CEO gate removed 2026-08-05 — no-op (keeper SKIP)"
echo "STATUS: tool-allowlist=CANONICAL_SKIP"
echo "[u134] done"
