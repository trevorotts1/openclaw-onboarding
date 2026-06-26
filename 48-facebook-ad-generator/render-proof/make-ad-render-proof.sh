#!/usr/bin/env bash
# Skill 48 — OPTIONAL sample-first render proof. Generates a few REAL ads up front so a
# human can eyeball whether the engine spells the baked-in text correctly. This is the
# human eyeball check, NOT a machine gate (the dropped OCR step is a human call here +
# the seeing-reviewer Gate C + the approve pause).
set -u
echo "=== Skill 48 render-proof (optional, sample-first) ==="
if [ -z "${KIE_API_KEY:-}" ]; then
  echo "  SKIP -- no CLIENT KIE_API_KEY; cannot generate sample ads. Set the client's key and re-run."
  exit 0
fi
N="${1:-3}"
echo "  (would: generate ${N} real 1500x1500 gpt-image ads with baked-in text, write them to"
echo "   ~/Downloads/fbad-render-proof/, and ask a human to confirm the text is legible)"
echo "render-proof: human eyeball check, not a machine gate."
exit 0
