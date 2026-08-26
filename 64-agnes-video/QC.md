# QC Checklist: Agnes Video (2.5 Flash + V2.0)

## 1. Purpose
Makes the agent fluent in the two approved Agnes video models
(`agnes-video-2.5-flash`: string seconds 4-12, 720P only, modes
text/keyframe/reference; `agnes-video-v2.0`: frame-driven duration, num_frames
8n+1 <= 441, 480p/720p/1080p), the deterministic router
`scripts/select_agnes_video_model.py`, and the create-then-poll flow over
`POST /v1/videos` + `GET /agnesapi?video_id=` — referencing the
fleet-provisioned `AGNES_AI_API_KEY` without ever printing it.

## 2. Installation Checks
- [ ] Skill folder contains `SKILL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`,
      `INSTALL.md`, `CORE_UPDATES.md`, `QC.md`, `agnes-video-full.md`,
      `models.json`, `scripts/select_agnes_video_model.py`, and
      `qc-agnes-video.sh`.
- [ ] `agnes-video-full.md` names BOTH models, the create endpoint
      `POST /v1/videos`, and the recommended result reads
      `GET /agnesapi?video_id=...&model_name=agnes-video-2.5-flash` (Flash) and
      `GET /agnesapi?video_id=` (V2.0).
- [ ] The router self-test passes: `python3 scripts/select_agnes_video_model.py
      --self-test` exits 0.
- [ ] `models.json` parses and carries both canonical ids with
      `last_verified_at: 2026-08-26`, `cap_status: NOT_PUBLISHED`, and the
      never-auto-select note for full `agnes-video-2.5`.

## 3. Dependency Checks
- [ ] TYP (Skill 01) and Backup (Skill 02) are installed first.
- [ ] `AGNES_AI_API_KEY` is present on the box (SET/NOT-SET checked; value never
      printed). It is fleet infrastructure — not provisioned by this skill.
- [ ] `curl` is available for the request examples.
- [ ] The installer understands video generation is ASYNCHRONOUS (create then
      poll) — unlike Agnes image generation, which is synchronous.

## 4. Credential Detection
- [ ] Confirm `AGNES_AI_API_KEY` with SET/NOT-SET ONLY. NEVER echo/cat/log the
      value. If NOT-SET, escalate as an infrastructure gap; never invent or
      substitute a key.

## 5. Router Checks (offline, no API)
- [ ] 5s 720P text -> `agnes-video-2.5-flash` / text / valid.
- [ ] 10s 720P first_frame -> `agnes-video-2.5-flash` / keyframe / valid.
- [ ] Audio ref -> `agnes-video-2.5-flash` / reference / valid.
- [ ] 1080p -> `agnes-video-v2.0` / valid.
- [ ] num_frames 121 + frame_rate 24 -> `agnes-video-v2.0` / valid.
- [ ] 18s @ 24fps -> V2.0 with derived num_frames 433 (<= 441, 8n+1); 20s @
      24fps -> valid=false (480 > 441), reason explains split/rate tradeoff.
- [ ] video_refs -> unsupported; handoff to KIE only with
      `allow_kie_handoff: true`.
- [ ] explicit Flash + 1080p -> valid=false, model STAYS
      `agnes-video-2.5-flash` (no silent switch).
- [ ] 6 image refs, no explicit keyframe mode -> valid=false (semantic guard;
      not reinterpreted as V2.0 keyframes).
- [ ] Determinism: any fixture run twice -> byte-identical output.

## 6. Functional Checks (optional, on-box)
- [ ] Create a minimal Flash text task (`"seconds": "5"`, `"size": "720P"`) and
      confirm the response returns a `video_id` and a `status`.
- [ ] Create a minimal V2.0 task (`num_frames: 81`, `frame_rate: 24`) and
      confirm the same.
- [ ] Poll both by `video_id`; Flash poll carries
      `&model_name=agnes-video-2.5-flash`; confirm `completed` returns
      `metadata.url`.
- [ ] Confirm duration/resolution are read from the RESPONSE
      (`size`/`seconds`/`metadata.size_mapping`), not the request.

## 7. MEDIA QC — inspect the actual video, not just the URL (REAL QC)
Before reporting a generated video as done:
- [ ] **Download and frame-inspect.** Do not report from the URL alone. Pull the
      mp4, extract sampled frames (`ffmpeg -i cli.mp4 -vf
      "select='not(mod(n\,30))'" -vsync vfr frames/f%03d.png`), and LOOK at
      them (read the PNGs visually). Check subject identity, motion continuity,
      no morphing, no artifacts that fail the user's intent.
- [ ] **Duration vs request.** Read returned `seconds`; compare with the
      requested duration. Flash: must land in 4-12. V2.0: expected ≈
      num_frames/frame_rate; a big delta means normalization or a wrong grid
      value — flag it.
- [ ] **Aspect/resolution vs request.** Compare returned `size` /
      `metadata.size_mapping` with the requested aspect/resolution. For V2.0
      normalization a different-but-close preset is expected; for Flash the
      pixel table (16:9 = 1280x720, 1:1 = 720x720, etc.) must match the
      requested ratio exactly.
- [ ] **Audio semantics.** If the request asked for audio/ambience/music, check
      it actually plays in the file (or confirm the selected model documented
      audio behavior — Flash accepts `audios` in reference mode; audio
      generation on both is not contradicted but no synthesis API is published).
- [ ] **Keyframe/reference fidelity.** For keyframe mode, the render must
      visibly start from the first-frame content (or end at last-frame) and keep
      identity/colors from reference images. Fail if the model ignored them.
- [ ] **No full-2.5 substitution.** Confirm the RESPONSE `model` field is the
      model the router selected — never `agnes-video-2.5` (full paid).
- [ ] If media QC fails: same model + corrected prompt/params first (spec 15
      retry ladder) — stop after the configured retry cap and report why. Do not
      silently burn credits across models.

## 8. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, credential, router, and (where run)
    functional + media checks pass with no ambiguity.
  - **8-9/10**: Core behavior works; one or two non-critical cleanups.
  - **6-7/10**: Basic install exists but a meaningful validation is missing.
  - **0-5/10**: Missing prerequisites, broken reference content, wrong credential
    handling, or the model/endpoint documented incorrectly.
- Record final result:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 9. QC Loop Rule
- Run at most **5 total QC/fix rounds**.
- After each failed round: record which items failed, apply the smallest fix,
  re-run only the failed checks.
- If it still fails after the 5th round, stop and escalate.
