#!/usr/bin/env bash
# make-video-fixtures.sh — materialize a GOOD and a BAD Movie-Producer run dir so the
# enforcement driver (executive_producer.py) can be self-tested in CI without OpenMontage
# present (AGPLv3-safe: no upstream source touched).
#
#   GOOD run:     a complete free documentary-montage job — every DMAIC phase receipt
#                 present + valid + a real >100KB MP4 + a logged owner-authorized skip of
#                 V-ANALYZE (the free path) -> the driver must ATTEST V-CONTROL (exit 0).
#   BAD-FREE run: the EXACT phase-skip bypass on the FREE path — V-IMPROVE dispatched with
#                 NO upstream phases attested and a render receipt with ffprobe_pass:false,
#                 on the free documentary-montage pipeline (kie_in_scope:false, cost 0) so
#                 phase-0 is N/A and the driver must HARD-ABORT at the phase-precondition
#                 check (AF-VID-PHASE-SKIPPED, exit 2). This is the fixture that proves the
#                 phase-skip gate specifically bites.
#   BAD run:      the SAME phase-skip signature but on a PAID Kie job (kie_in_scope:true,
#                 pipeline kie-video.yaml, cost 2.0) with NO KIE_API_KEY on the box. SK1-67
#                 makes phase-0 fail EARLIEST here: a keyless paid job can never run, so the
#                 driver must HARD-ABORT at phase-0 (AF-VID-KIE-BALANCE, exit 4) BEFORE the
#                 phase-precondition check is even reached. This fixture locks SK1-67 in.
#
# Usage: bash make-video-fixtures.sh OUTDIR
set -euo pipefail

OUT="${1:?usage: make-video-fixtures.sh OUTDIR}"
GOOD="$OUT/good-run"
BAD="$OUT/bad-run"
BAD_FREE="$OUT/bad-run-free"
rm -rf "$GOOD" "$BAD" "$BAD_FREE"
mkdir -p "$GOOD/working/checkpoints" "$BAD/working/checkpoints" \
         "$BAD_FREE/working/checkpoints"

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
  "final_mp4_path": "working/final.mp4",
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

# A finished MP4 deliverable. SK1-62/SK1-68: run_postflight_gate now ffprobe-decodes the
# declared final MP4 (not just its byte size), so the GOOD fixture must be a REAL video
# when ffmpeg is present. Falls back to a byte placeholder only when ffmpeg is absent
# (there the gate degrades to the size floor, so the placeholder still passes).
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -f lavfi -i "testsrc=size=320x240:rate=15:duration=2" \
    -pix_fmt yuv420p "$GOOD/working/final.mp4" >/dev/null 2>&1 || head -c 150000 /dev/zero > "$GOOD/working/final.mp4"
  # Pad up to the >100KB floor if the tiny clip is under it (trailing bytes after the
  # last box do not stop ffprobe from reading the streams).
  _sz=$(wc -c < "$GOOD/working/final.mp4" 2>/dev/null | tr -d ' ')
  if [ "${_sz:-0}" -lt 150000 ]; then head -c $((150000 - ${_sz:-0})) /dev/zero >> "$GOOD/working/final.mp4"; fi
else
  head -c 150000 /dev/zero > "$GOOD/working/final.mp4"
fi

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

# ---------- BAD-FREE: the phase-skip bypass on the FREE path ----------
# Identical bypass signature to BAD (V-IMPROVE dispatched with NO upstream phase
# attestations, NO owner-authorized skip, and an ffprobe-failing render receipt) but on
# the FREE documentary-montage pipeline: kie_in_scope:false + estimated_cost_usd:0, so
# phase-0 is N/A (no paid Kie call) and the driver reaches the phase-precondition check,
# where it must refuse the skip (AF-VID-PHASE-SKIPPED, exit 2). This proves the phase-skip
# gate itself bites — distinct from BAD, which now fails EARLIER at phase-0 (exit 4) under
# SK1-67 because it is a keyless PAID job.
cat > "$BAD_FREE/working/job-manifest.json" <<'JSON'
{
  "job_id": "fixture-bad-free-001",
  "pipeline_selected": "documentary-montage.yaml",
  "kie_in_scope": false,
  "brief_complete": true,
  "topic": "skip the whole pipeline (free path)",
  "target_duration_sec": 8,
  "aspect_ratio": "16:9",
  "budget_ceiling_usd": 1.0,
  "tone": "documentary",
  "estimated_cost_usd": 0.0
}
JSON

cat > "$BAD_FREE/working/checkpoints/render-receipt.json" <<'JSON'
{
  "job_id": "fixture-bad-free-001",
  "kie_in_scope": false,
  "ffprobe_pass": false
}
JSON

echo "GOOD run:      $GOOD"
echo "BAD-FREE run:  $BAD_FREE"
echo "BAD  run:      $BAD"
