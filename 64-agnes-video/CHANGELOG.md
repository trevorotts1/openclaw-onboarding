# Changelog - agnes-video

All notable changes to this skill are documented here.

---

## [1.1.0] - 2026-08-03 - fix: the core-file updates are now EXECUTED by `wire.sh`, not pasted as a recipe

### Why
Skill 64 shipped no installer, so its `CORE_UPDATES.md` was consumed by the generic
merger in `update-skills.sh`, which copies a section body VERBATIM. What landed in every
box's `AGENTS.md` / `TOOLS.md` / `MEMORY.md` was the literal INSTRUCTION -- the word
`Add:`, a markdown code fence, the payload, the closing fence -- the recipe pasted instead
of executed. Worse, the pointer inside it was NEVER FILLED: it landed on the box as the literal template
variable `[MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md` -- a pointer to a path
that exists on no box.

### What changed
- **New `wire.sh`** -- performs the add. It writes one compact pointer block per core file
  behind its version-free `<!-- BEGIN/END skill:64-agnes-video:<target> -->` marker,
  REPLACE-IN-PLACE, so a re-run is byte-identical and an already-pasted box is HEALED
  rather than appended to. The master-files path is RESOLVED to an absolute path on the box.
- It stamps `<!-- skill:64-agnes-video:core-update-applied -->`, which makes the generic merger
  short-circuit for this skill so the recipe can never be pasted again.
- It touches only its OWN `skill:64-agnes-video:*` markers -- the shared idempotency
  stamp bank ~44 other installers key on is never read, moved or removed.
- Backups are timestamped and taken ONLY when a file actually changes.
- `CORE_UPDATES.md` now documents that `wire.sh` performs these updates.

### Evidence (scratch only)
Seeded a fixture with the EXACT pasted junk carried on a live box: after `wire.sh` the
literal `Add:`, the code fences and the unfilled `[MASTER_FILES_FOLDER]` variable are all
gone, exactly one BEGIN/END pair per target remains, the pointer is an absolute path, and a
second run is byte-identical across AGENTS.md / TOOLS.md / MEMORY.md with no new backup.

## [1.0.1] - August 1, 2026

### Changed
- Updated the referenced Agnes text/reasoning model from `agnes-2.0-flash` to
  `agnes-2.5-flash` in the shared-credential notes (SKILL.md, INSTALL.md,
  PREREQS.json, agnes-video-full.md). The video model itself
  (`agnes-video-v2.0`) is unchanged.

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
