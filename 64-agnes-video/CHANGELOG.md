# Changelog - agnes-video

All notable changes to this skill are documented here.

---

## [1.0.0] - July 21, 2026

### Added
- Initial release: endpoint reference and asynchronous workflow for Agnes Video
  V2.0 (`agnes-video-v2.0`) on the Agnes AI gateway (`apihub.agnes-ai.com`).
- Documents the two-step async flow: `POST /v1/videos` to create a task, then
  poll `GET /agnesapi?video_id=<id>` (recommended) or the legacy
  `GET /v1/videos/<task_id>`.
- Covers text-to-video, image-to-video, and keyframe animation
  (`extra_body.image[]` + `extra_body.mode: "keyframes"`).
- Documents the `num_frames` rules (`<= 441` and `8n + 1`), `frame_rate` range,
  the `480p`/`720p`/`1080p` resolution tiers, and that the RETURNED
  `size`/`seconds`/`metadata.size_mapping` are the source of truth, not the
  request.
- Tier and rate-limit awareness: Agnes meters on two axes (RPM + daily/weekly
  quota) by account tier; treat HTTP `429` as the live ceiling, do not hardcode.
  Reference table sourced from `AgnesAI-Labs/AgnesAI-Models` (dated 2026-06-28),
  labeled non-contractual.
- References the fleet-provisioned `AGNES_AI_API_KEY` (SET/NOT-SET only, value
  never printed). This skill does not provision a new account or credential.
- Ships `qc-agnes-video.sh` (install QC with hard structural/content asserts that
  can return a failing exit code on a real defect).
