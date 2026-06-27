#!/usr/bin/env bash
# qc-built-funnel.sh — Skill 6: per-build FAB-QC for a constructed funnel.
#
# DISTINCT from qc-ghl-install-pages.sh (install-level QC for the skill itself).
# This is the per-BUILD, library-aware quality gate — the Skill-6 parallel of
# Skill-44's qc-built-workflow.sh. It is a SUPERSET OVERLAY on top of the canonical
# ghl_verify render gate: ghl_verify (HTTP 200 + marker) stays the hard mechanical
# floor (scored as FAB-QC dimension D3); this script adds the six library-aware
# dimensions (template fidelity, copy substance, render/soundness, persona grounding,
# flexibility honored, funnel<->automation link integrity) and the >= 8.5 verdict.
#
# Usage:
#   ./qc-built-funnel.sh <evidence_root> [--json]
#   ./qc-built-funnel.sh <slug>          # resolves working/funnels/<slug>/ if it exists
#
# Exit codes:
#   0  = FAB-QC score >= 8.5 AND no hard miss
#   1  = FAB-QC score < 8.5 OR a hard miss (build is NOT done)
#   2  = evidence root not found / scorer unavailable
#
# The shared scorer is shared-utils/fab_qc.py; the rubric is
# universal-sops/funnel-automation-build-quality-rubric.md.
set -u

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
SCORER="$REPO_ROOT/shared-utils/fab_qc.py"

ARG="${1:-}"
JSON=""
[ "${2:-}" = "--json" ] && JSON="--json"

if [ -z "$ARG" ]; then
  echo "usage: qc-built-funnel.sh <evidence_root|slug> [--json]" >&2
  exit 2
fi

# Resolve the evidence root: a path as-is, or working/funnels/<slug>/.
EVIDENCE="$ARG"
if [ ! -d "$EVIDENCE" ]; then
  for cand in "$PWD/working/funnels/$ARG" "$HOME/clawd/working/funnels/$ARG"; do
    if [ -d "$cand" ]; then EVIDENCE="$cand"; break; fi
  done
fi

if [ ! -d "$EVIDENCE" ]; then
  echo "✗ evidence root not found: $ARG" >&2
  exit 2
fi
if [ ! -f "$SCORER" ]; then
  echo "✗ FAB-QC scorer not found at $SCORER" >&2
  exit 2
fi

echo "═══ Skill 6 — FAB-QC build gate (funnel) ═══"
echo "evidence: $EVIDENCE"
python3 "$SCORER" --evidence "$EVIDENCE" --kind funnel --gate $JSON
rc=$?
if [ $rc -eq 0 ]; then
  echo "✓ FAB-QC PASS (>= 8.5) — funnel build is done"
else
  echo "✗ FAB-QC FAIL (< 8.5 or hard miss) — funnel build is NOT done; fix the lowest dimension and re-run"
fi
exit $rc
