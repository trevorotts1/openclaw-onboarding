#!/usr/bin/env bash
# make-video-fixtures.sh — materialize a GOOD and a BAD Movie-Producer run dir so the
# enforcement driver (executive_producer.py) can be self-tested in CI without OpenMontage
# present (AGPLv3-safe: no upstream source touched).
#
#   GOOD run: a complete free documentary-montage job — every DMAIC phase receipt
#             present + valid + a real >100KB MP4 + a logged owner-authorized skip of
#             V-ANALYZE (the free path) -> the driver must ATTEST V-CONTROL (exit 0).
#   BAD  run: the EXACT bypass signature — V-IMPROVE dispatched with NO upstream phases
#             attested and a render receipt with ffprobe_pass:false -> the driver must
#             HARD-ABORT (AF-VID-PHASE-SKIPPED, exit 2).
#
# Usage: bash make-video-fixtures.sh OUTDIR
set -euo pipefail

OUT="${1:?usage: make-video-fixtures.sh OUTDIR}"
GOOD="$OUT/good-run"
BAD="$OUT/bad-run"
rm -rf "$GOOD" "$BAD"
mkdir -p "$GOOD/working/checkpoints" "$BAD/working/checkpoints"

# ---------- GOOD: complete free documentary-montage job ----------
cat > "$GOOD/working/job-manifest.json" <<'JSON'
{
  "job_id": "fixture-good-001",
  "pipeline_selected": "documentary-montage.yaml",
  "kie_in_scope": false,
  "brief_complete": true,
  "topic": "the deep ocean at night",
  "target_duration_sec": 30,
  "aspect_ratio": "16:9",
  "budget_ceiling_usd": 1.0,
  "tone": "documentary",
  "estimated_cost_usd": 0.0,
  "status": "complete",
  "actual_cost_usd": 0.0,
  "handoff": "captions->Skill 26 (caption-creator)",
  "_pad": "padding so the job-manifest deliverable clears the 256-byte size floor for the postflight bundle check; this is a synthetic CI fixture only"
}
JSON

cat > "$GOOD/working/checkpoints/measure-receipt.json" <<'JSON'
{
  "preflight_pass": true,
  "provider_audit_pass": true,
  "budget_gate_pass": true,
  "providers_available": ["kie", "piper"],
  "estimated_cost_usd": 0.0,
  "budget_ceiling_usd": 1.0,
  "measured_at": "2026-06-24T10:00:00-0400"
}
JSON

# Free path -> a logged owner-authorized skip of V-ANALYZE (Rule-Zero) is required.
cat > "$GOOD/working/checkpoints/phase_skip_approvals.json" <<'JSON'
{
  "approvals": [
    {
      "phase_id": "V-ANALYZE",
      "owner_approved": true,
      "approved_by": "Head of Video Production",
      "reason": "free documentary-montage path; zero paid Kie calls so Rule-Zero announce/approval is not applicable",
      "approved_at": "2026-06-24T10:01:00-0400"
    }
  ]
}
JSON

RENDER_RECEIPT='{
  "job_id": "fixture-good-001",
  "kie_in_scope": false,
  "output_path": "working/final.mp4",
  "ffprobe_pass": true,
  "ffprobe_duration": 30.0,
  "ffprobe_codec": "h264",
  "ffprobe_width": 1280,
  "ffprobe_height": 720,
  "has_video_stream": true,
  "provider_used": "ffmpeg",
  "rendered_at": "2026-06-24T10:05:00-0400",
  "note": "free documentary-montage path; FFmpeg stitch of public-domain footage; no paid Kie call; synthetic CI fixture"
}'
printf '%s\n' "$RENDER_RECEIPT" > "$GOOD/working/checkpoints/render-receipt.json"
printf '%s\n' "$RENDER_RECEIPT" > "$GOOD/working/render-receipt.json"

# A real >100KB MP4 deliverable (zero-filled; the gate validates the receipt, not the codec).
: > "$GOOD/working/final.mp4"
head -c 150000 /dev/zero > "$GOOD/working/final.mp4"

# ---------- BAD: the bypass signature ----------
cat > "$BAD/working/job-manifest.json" <<'JSON'
{
  "job_id": "fixture-bad-001",
  "pipeline_selected": "kie-video.yaml",
  "kie_in_scope": true,
  "brief_complete": true,
  "topic": "skip the whole pipeline",
  "target_duration_sec": 8,
  "aspect_ratio": "16:9",
  "budget_ceiling_usd": 5.0,
  "tone": "promotional",
  "estimated_cost_usd": 2.0
}
JSON

# A render receipt that fails ffprobe — and NO V-DEFINE/V-MEASURE/V-ANALYZE attestations,
# NO owner-authorized skip. Dispatching V-IMPROVE here is the exact bypass the driver must
# refuse (AF-VID-PHASE-SKIPPED, exit 2).
cat > "$BAD/working/checkpoints/render-receipt.json" <<'JSON'
{
  "job_id": "fixture-bad-001",
  "kie_in_scope": true,
  "ffprobe_pass": false,
  "kie_task_id": "TASK_ID",
  "kie_result_url": ""
}
JSON

echo "GOOD run: $GOOD"
echo "BAD  run: $BAD"
