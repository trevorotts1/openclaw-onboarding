#!/usr/bin/env bash
# CEO gate removed 2026-08-05 per Trevor — was creating loops; see openclaw-telegram-master-plan.md
# u134-tool-allowlist-patch.sh -- NOW A NO-OP. The CEO production-tool deny has been
# removed from the canonical source (hooks/lib-ceo-tool-gate.sh CEO_GATE_DENY_TOOLS=()).
# It always reports CANONICAL_SKIP and exits 0.
#
# It is kept present, not deleted, only so an out-of-tree or hand-written caller on
# an already-rolled box does not break. It has NO caller inside this repo any more:
# install.sh and update-skills.sh no longer invoke it (the call sites went away with
# the gate). tests/unit/test-u134.sh asserts BOTH that it stays inert (never writes
# a tools.deny into a box config) and that it stays un-wired — re-teaching it to
# stamp a deny would re-create the write-deny loop that ate two weeks of messages.
set -euo pipefail
echo "[u134] CEO gate removed 2026-08-05 — no-op (keeper SKIP)"
echo "STATUS: tool-allowlist=CANONICAL_SKIP"
echo "[u134] done"
