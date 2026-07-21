# Changelog — Skill 28: Cinematic Forge

## v6.6.0 — SK1-32: the delivered artifact is the REQUESTED artifact, and the gate that says so checks the approved intake

- **T0-47 (BLOCKER) — the un-transformed file was the one that shipped.** Phase 5
  wrote captions to `final_video_captioned.mp4` and the logo overlay to
  `final_video_branded.mp4`; both read `final_video.mp4`. Phase 6 then uploaded
  `final_video.mp4`, and the delivery verification ran on `final_video.mp4`. When
  a client asked for captions or logo placement the work was performed correctly,
  verified correctly, and the file without it was delivered — every stage
  reporting success. Phase 5 now defines ONE authoritative `$FINAL_ARTIFACT`
  variable and an `apply_step` helper: each transformation reads the current
  artifact, writes a new file, and advances the variable *only* if the command
  succeeds, writing a receipt with the input and output hashes. Phase 6 uploads
  and verifies that variable.

- **T0-46 (BLOCKER) — the gate certified a request-wrong video as safe to
  deliver.** Every value it compared against was supplied by its caller, so
  nothing bound the file to the approved intake. `qc-output.sh` now has two
  modes. The positional form runs TECHNICAL probes and says, in as many words,
  that it is *not* a delivery verdict. The new DELIVERY mode
  (`--artifact --requirements [--receipts] [--upload-response]`) checks the
  artifact against a delivery-requirements record derived from the approved
  intake before generation — approved aspect ratio, approved duration, and each
  `requires_*` overlay flag — and demands, for every requested transformation, a
  receipt whose output hash IS the artifact being delivered. A record with no
  `approval_ref` is refused: it attests to nothing.

- **T0-48 — the hosted check proved only that the host was up.** It was a ranged
  first-byte request plus a content-type match, on a URL grepped out of the
  upload response body; any reachable video URL satisfied it. The gate now
  resolves the asset IDENTIFIER the upload returned, requires the response's own
  filename/size metadata to match the artifact, downloads the object bound to
  that identifier and probes it against the same approved requirements. A
  response with no identifier, or with nothing to match against, is a failure —
  never a skip.

- **T2-29 — the documented fallback could not host the deliverable.** INSTALL.md
  named an image host as the fallback when the media upload is unavailable, and
  QC.md's knowledge test marked that answer correct — while SKILL.md said the
  opposite for the final artifact. The image host is labelled REFERENCE-IMAGES-ONLY
  everywhere, and the final-video fallback is a video-capable store the client
  controls, verified exactly like the primary path.

- **T2-30 — the install directory and the runtime path could not both be
  right.** INSTALL.md directed the operator to an unprefixed `cinematic-forge/`
  while SKILL.md's Phase 0 resolves `28-cinematic-forge/`; QC.md tried the
  unprefixed path first and fell back, which is the only reason the checklist
  worked. The prefixed form is canonical in all three, and QC.md resolves it
  once.

Tests: `tests/unit/cinematic-forge-delivery-gate.test.sh` (26 assertions on real
ffmpeg fixtures, including a mutation that removes the receipt chain and
requires the un-transformed artifact to be certified again).
CI: `.github/workflows/cinematic-forge-delivery-guard.yml`.

## v6.5.9 — Fleet-hygiene: sanitize changelog wording + drop the stale leaky skill bundle
- Reworded the v6.5.8 PRD-removal note so the changelog itself no longer embeds the literal client name or operator path; it now describes the same change generically.
- Deleted the stale `cinematic-forge.skill` bundle. It was a compressed snapshot of an older, pre-fix `SKILL.md` that still embedded the client-specific PRD reference plus an operator secrets path, so it re-introduced the exact leak the loose files had already scrubbed. The bundle is not an install-source or learn-source for this skill: the installer copies the loose skill folder, the agent learns from the loose `SKILL.md`, nothing unpacks the bundle, and the skill's own QC treats its absence as a non-blocking INFO. The loose skill files are authoritative.

## v6.5.8 — GHL upload hardening, output-QC gate, Command Center, VPS-aware, Anthropic scrub
- GHL upload (Phase 6): resolve canonical `GOHIGHLEVEL_API_KEY` + `GOHIGHLEVEL_LOCATION_ID` from the platform-correct secrets file, pass `locationId`, check HTTP status, parse the returned URL, and retry once on failure instead of assuming success. Removed the `[PIT_TOKEN]` placeholder.
- Killed imgBB as the FINAL-VIDEO fallback (imgBB hosts still images/GIF only). imgBB remains a valid fallback for reference images (Q9).
- Fixed the "11 structured intake questions" contradiction in SKILL.md "What This Skill Does" -> 14 (matches the rest of the skill).
- Removed a hardcoded client-specific PRD reference (a client name plus an operator path) from the SKILL.md intake example (fleet-hygiene leak + broken ref); replaced it with a generic master-files pointer.
- Added `qc-output.sh <final.mp4> <target_seconds> <WxH> [hosted_url]` — a dependency-light (bash + ffprobe/ffmpeg) OUTPUT-QC gate that fails on missing/zero-byte file, wrong resolution, missing video OR audio stream, silent audio (mean_volume <= -80 dB), or duration off by >0.75s, plus an optional hosted-URL reachability check. Required to exit 0 before delivery (SKILL.md Phase 4 + Phase 6, QC.md §1/§4.4/§6).
- Added an OPTIONAL, reachability-gated Command Center (Kanban) integration: gated on `localhost:4000/api/health` + `$MC_API_TOKEN`; PATCH `in_progress` on budget approval and `review` on draft delivery (never self-promote to `done`); `return-to-orchestrator` on low credits / awaiting approval. HTTP only, never the SQLite DB. Skips silently when unreachable.
- VPS-awareness: SKILL.md Phase 0 resolves SECRETS_ENV / OUTPUT_ROOT / SKILL_DIR by detecting `/data/.openclaw`; `qc-cinematic-forge.sh` fallback resolver is now VPS-aware and adds `set -o pipefail`; INSTALL.md and QC.md reference the VPS secrets path.
- Canonicalized GoHighLevel credential names away from the drifted `GHL_API_KEY` / `GHL_LOCATION_ID` to `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID` across SKILL.md and QC.md; removed an operator-name reference from QC.md.
- Anthropic scrub: removed the external `summarize`-tool Anthropic credential option from the key lists (kept `GEMINI_API_KEY` / `OPENAI_API_KEY`, which keep the tool working) in SKILL.md and QC.md; minimally removed the two stale Anthropic client-model recommendations (vision line + executor line) from the `cinematic-forge.skill` bundle and repacked it. The existing "never Anthropic" / "BANNED: Anthropic" vision and executor guidance was left intact.
