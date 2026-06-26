#!/usr/bin/env bash
# make-ad-fixtures.sh — materialize a GOOD and a BAD FB/IG-ad run dir so the
# dependency-map foreman (ad_director.py) can be self-tested in CI.
#
#   GOOD run: a complete, valid batch — every stage receipt + scorecard present and
#             valid + every produces_artifact on disk -> the foreman must ATTEST every
#             phase in dependency order, ending at PUBLISH (exit 0 each).
#   BAD  run: the EXACT bypass signature — S5-IMAGE-GEN dispatched with NO dependency
#             attested (a perfectly valid s5 receipt is present, but S4-IMAGE-PROMPTS
#             was never attested) -> the foreman must HARD-ABORT (AF-FBAD-DEP-SKIPPED,
#             exit 2).
#
# The GOOD run reuses test_ad_preflight._good() (the same builder the negative-test
# suite uses) so the fixture can never drift from the checkers.
#
# Usage: bash make-ad-fixtures.sh OUTDIR
set -euo pipefail

OUT="${1:?usage: make-ad-fixtures.sh OUTDIR}"
SCRIPTS="$(cd "$(dirname "$0")/../scripts" && pwd)"
GOOD="$OUT/good-run"
BAD="$OUT/bad-run"
rm -rf "$GOOD" "$BAD"
mkdir -p "$GOOD/working/checkpoints" "$GOOD/working/qc" "$BAD/working/checkpoints"

# ---------- GOOD: a complete, valid batch (reuse the test's _good builder) ----------
python3 - "$SCRIPTS" "$GOOD" <<'PY'
import sys
from pathlib import Path
scripts, good = sys.argv[1], sys.argv[2]
sys.path.insert(0, scripts)
from test_ad_preflight import _good
_good(Path(good))
print("GOOD run populated via test_ad_preflight._good()")
PY

# ---------- BAD: the bypass signature ----------
# A valid S5 image receipt is present, but NO ad_process_manifest.json attestations
# exist — so dispatching S5-IMAGE-GEN (depends_on S4-IMAGE-PROMPTS) is the exact bypass
# the foreman must refuse (AF-FBAD-DEP-SKIPPED, exit 2).
cat > "$BAD/working/job-manifest.json" <<'JSON'
{
  "brief_complete": true,
  "job_id": "fixture-bad-001",
  "show_name": "Skip The Pipeline",
  "audience_profile_ref": "working/inputs/audience.md",
  "money_ceiling_usd": 5.0,
  "estimated_cost_usd": 0.65,
  "cost_estimate_approved": true,
  "owner": "Owner Name"
}
JSON

cat > "$BAD/working/checkpoints/s5-image-receipt.json" <<'JSON'
{
  "image_count": 10,
  "images": [
    {"kie_task_id": "a27542cb60343417e562afc2be65da5c", "width": 1500, "height": 1500, "model": "gpt-image-2-text-to-image", "would_cross": false}
  ]
}
JSON

echo "GOOD run: $GOOD"
echo "BAD  run: $BAD"
