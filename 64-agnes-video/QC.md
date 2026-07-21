# QC Checklist: Agnes Video V2.0

## 1. Purpose
Makes the agent fluent in the Agnes Video V2.0 asynchronous endpoint
(`agnes-video-v2.0`): create a task with `POST /v1/videos`, poll the result with
`GET /agnesapi?video_id=<id>`, across text-to-video, image-to-video, and keyframe
animation — referencing the fleet-provisioned `AGNES_AI_API_KEY` without ever
printing it.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTRUCTIONS.md`,
      `EXAMPLES.md`, `INSTALL.md`, `CORE_UPDATES.md`, `QC.md`, the full reference
      `agnes-video-full.md`, and `qc-agnes-video.sh`.
- [ ] `agnes-video-full.md` names the model `agnes-video-v2.0`, the create
      endpoint `POST /v1/videos`, and the recommended result read
      `GET /agnesapi?video_id=`.
- [ ] The full reference documents the `num_frames` rules (`<= 441` and `8n + 1`)
      and the `480p`/`720p`/`1080p` tiers.
- [ ] If TYP required a master copy, the full reference is stored in the master
      files folder and core files only carry a lean pointer.

## 3. Dependency Checks
- [ ] TYP (Skill 01) and Backup (Skill 02) are installed first.
- [ ] `AGNES_AI_API_KEY` is present on the box (SET/NOT-SET checked; value never
      printed). It is fleet infrastructure — not provisioned by this skill.
- [ ] `curl` is available for the request examples.
- [ ] The installer understands video generation is ASYNCHRONOUS (create then
      poll) — unlike Agnes image generation, which is synchronous.

## 4. Credential Detection
- [ ] Confirm `AGNES_AI_API_KEY` with SET/NOT-SET ONLY (e.g.
      `openclaw config get AGNES_AI_API_KEY`). NEVER echo/cat/log the value.
- [ ] If NOT-SET, this is an infrastructure gap to escalate — the agent must NOT
      invent or substitute a key.
- [ ] QC fails only on STRUCTURAL/CONTENT defects; a missing key is a WARNING so
      the reference still installs (the key is separate fleet infra).

## 5. Functional Checks (optional, on-box)
- [ ] Create a minimal task (`num_frames: 81`, `frame_rate: 24`) and confirm the
      response returns a `video_id` and a `status`.
- [ ] Poll by `video_id` and confirm the task reaches `completed` (or a valid
      in-progress state) and returns `metadata.url`.
- [ ] Confirm duration/resolution are read from the RESPONSE
      (`size`/`seconds`/`metadata.size_mapping`), not the request.
- [ ] Ask the agent what `400`, `401`, `404`, and `429` mean. Expected: bad
      request, bad/missing key, id not found, rate limited (back off).

## 6. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, credential, and (where run)
    functional checks pass with no ambiguity.
  - **8-9/10**: Core behavior works; one or two non-critical cleanups.
  - **6-7/10**: Basic install exists but a meaningful validation is missing.
  - **0-5/10**: Missing prerequisites, broken reference content, wrong credential
    handling, or the model/endpoint documented incorrectly.
- Record final result:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 7. QC Loop Rule
- Run at most **5 total QC/fix rounds**.
- After each failed round: record which items failed, apply the smallest fix,
  re-run only the failed checks.
- If it still fails after the 5th round, stop and escalate.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard)

After install, score honestly against this rubric. **Pass gate: 8.5/10.** Below
8.5 = loop back and fix (max 5 loops, then escalate to owner).

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | Contract read this session; Skills 01 and 02 installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, agnes-video-full.md, CORE_UPDATES.md, QC.md read BEFORE any command. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. |
| Credential handled correctly | 1.5 | `AGNES_AI_API_KEY` confirmed SET/NOT-SET only; value NEVER printed; no invented/substituted key. |
| Functional / structural checks pass | 1.5 | `qc-agnes-video.sh` exits 0; reference names the model + async endpoints. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections added to labeled core files; lean pointer, not the full reference. No SOUL/IDENTITY/USER/HEARTBEAT touched. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in sections 2-5 ticked. |
| Security | 0.5 | No credential value leaked to chat/logs/commits/.md files. |
| Owner-facing confirmation message sent | 0.5 | Plain-English summary: "Skill 64 active. Anything pending: [list]." |

### Bundled `qc-agnes-video.sh`
Run it. Exit 0 is required in addition to the rubric score. It catches the
mechanical items (folder + files present, reference names the model and the async
endpoints) and warns (non-fatally) on a missing key / missing TOOLS.md pointer.

### Self-audit before declaring done
1. INSTALL-CONTRACT.md acknowledged: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-agnes-video.sh exited 0: ✓ / ✗
6. No credential value printed anywhere: ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
