# Changelog — Skill 47 (Movie Producer / Automated Video Production)

## v15.1.4 - 2026-10-08 - INF002

- Re-embedded the Skill 74 client in `kie_image.py` (its header names Skill 74 v1.1.4, which now reads its QC version from `skill-version.txt`). No adapter behavior change.

## v15.1.2 - 2026-10-06 - delta QC round 2

- A lost createTask answer is an unknown outcome, not a rejection: with no task id, an error code of `network` or `bad_response` (a gateway 502 page, any non-KIE-JSON body) or any 5xx now means no fallback, no resubmit and `data.needs_repoll`. The same rule covers the veo3 / veo3_fast legacy submit. A definite rejection (for example 402) still falls back. Test: createTask HTTP 502 with a non-JSON body gives one createTask, zero veo calls, `createTask_outcome_unknown`.
- Unexpected client faults (for example a truncated read) no longer raise out of `execute()`: before createTask they return a failed result with no spend; after it may have been sent they are unresolved (no fallback, no resubmit). Both adapters. `kie_image.py` now also records the task id and `needs_repoll` when a run times out (parity with video).
## v15.1.1 - 2026-10-06 - QC follow-ups on the Skill 74 consolidation

- No fallback on an unknown outcome: when gemini-omni-video times out (the task may still finish), its task status cannot be read, or the createTask answer is lost to a network error, `kie_video.py` no longer starts a veo3_fast job and never resubmits. The result is `success=False` with `data.needs_repoll`, `data.kie_task_id` (when KIE returned one) and `data.kie_task_state` (`unresolved` or `createTask_outcome_unknown`) for the Dispatcher to re-poll. The same holds for Seedance and for the veo3 / veo3_fast legacy route (timeout, lost answer, unreadable status, result not saved). A definite failure still falls back; a prompt or credit refusal never falls back.
- Key gate in a bare clone: `_real_kie_key` used `shared-utils/secret_helper.py`, which the Docker image and a bare OpenMontage clone do not have, so a well-formed key read as UNAVAILABLE. A second generated block in `kie_image.py` (the `looks_like_real_key` gate, copied verbatim from `shared-utils/secret_helper.py`, sha256-stamped) is used when shared-utils is absent; `kie_video.py` reads it from there. `embed_kie_client.py` now generates and checks both blocks and `test_kie_embedded_client_hashlock.py` locks both (mutation proofs, and parity of the embedded gate with the shared one).
- Phase-0 credit check: `video_build_check._fetch_kie_balance` no longer makes its own HTTP call; it reads the balance through Skill 74 (credits, body `code` checked) with the same installed-or-embedded client selection, and says which path it used.
- Owner rule 12: a descriptive prompt under 80 percent of the model maximum is now a HARD REJECT in both adapters (via Skill 74 prompt-budget), with the exact characters to add; over the maximum is refused with the characters to cut.
- Tests: new `test_kie_adapter_safety.py` (unknown-outcome rules, empty-HOME bare clone with no shared-utils, 79 / 80 / 95 / 101 percent for image, gemini and Seedance); `test_video_preflight.py` covers the credit read on both paths; QC runs the new test and asserts the secret-helper block.

## v15.1.0 - 2026-10-06 - one KIE path: both adapters run on Skill 74

- `kie_image.py` and `kie_video.py` are thin BaseTool wrappers. Upload, live-schema validation, prompt-budget, credit preflight (price x 1.30), createTask, wait and save run through Skill 74 (`74-kie-live-adapter`) in `active` mode per call. Removed: both `_create_task` / `_submit_*` / `_poll_*` / `_download_*` / `_upload_local_image` HTTP clients, `_decode_result_json`, the hard-coded Seedance prompt band (2500 / 3 characters), and the `requests` dependency of the adapters.
- Client resolution: the installed sibling skill 74 first; otherwise the EMBEDDED copy at the bottom of `kie_image.py`, generated verbatim from Skill 74's source by `scripts/embed_kie_client.py` and locked by `scripts/test_kie_embedded_client_hashlock.py` (equality with Skill 74's source, stamped sha256, mutation proof, clone-layout run, identical createTask bodies on both paths). `kie_video.py` reads the block from its sibling `kie_image.py`. Exactly two `.py` files remain under `kie-adapters/`; `install.sh` and the `Dockerfile` copy lines are unchanged and still carry everything. Each run prints `path=skill74` or `path=embedded` and records `kie_client_path` in the result.
- Prompt length comes from Skill 74 prompt-budget: over the model maximum is refused before any paid call (exact characters to cut); under the 80 percent floor is reported in `data.warnings` (Skills 66 and 67 enforce the floor). An insufficient credit balance (price x 1.30) refuses before createTask; an unpriced model is reported and proceeds. Cost in the result uses the live credit price (1 credit = 0.005 USD) when Skill 74 returns one, else the fallback constants.
- gemini-omni-video: one retry only on a transient image-fetch failure; any other failure falls back to veo3_fast. A failed or errored createTask is never resent (the old code retried on any RuntimeError, which could charge twice).
- veo3 / veo3_fast stay on KIE's legacy Veo route, which Skill 74 does not model; the body and the successFlag poll are in `kie_video.py`, the transport (auth, HTTP, 429 retry, redaction, download) is Skill 74's `Adapter`.
- Tests rewritten over a fake Skill 74 transport (no network, no key): `test_kie_adapter_resultjson_decode.py` (also the shared harness), `test_kie_adapter_key_and_i2i_field.py`, `test_kie_video_seedance.py`, new `test_kie_embedded_client_hashlock.py`. `qc-movie-producer.sh`: the `_decode_result_json` greps are replaced by Skill 74 assertions and the four tests run in QC.

## v15.0.3 - 2026-10-05 - close open items on the image consumers PR

- `kie_image.py` builds the createTask input only from fields the model schema declares (`prompt`, `input_urls` for image-to-image, `aspect_ratio`, `resolution`, `background`); the undeclared `output_format` is no longer sent. Tests extended. INSTRUCTIONS no longer claims a PNG output format is requested.

## v15.0.2 - 2026-10-05 - fix(image consumers): sunburst-first order, unified model ids and credit preflight

- Credit preflight: `VID_KIE_BALANCE_FLOOR_MULTIPLIER` 1.25 -> 1.30 (fleet-wide rule: required balance = estimated cost x 1.30). `_fetch_kie_balance` now checks the response BODY `code` (HTTP 200 with a non-200 body code is an unverifiable balance). New probe in `test_video_preflight.py`.
- `kie_image.py` `estimate_cost`: one fallback constant set (2K 0.05, other 0.04; was 0.03) mirrored by Skill 58, with a docstring naming the price authority (`kie_live_adapter.py price`). Prices removed from prose.
- Placeholder keys (the installer writes `YOUR_CLIENT_KIE_API_KEY_HERE`) are NOT-SET in both adapters and the driver loader via the shared `secret_helper.looks_like_real_key` (shared-utils extended with `your_client`/`key_here`/`token_here`). Credits per USD 100 -> 200 (kie.ai/pricing "1 credit ~= $0.005"; vendor example 160 credits = 0.80 USD). `kie_image.py` sends the documented sunburst image-to-image field `input_urls` (was Nano Banana `image_input`). Balance message names `shortfall=`. New `scripts/test_kie_adapter_key_and_i2i_field.py`; seedance test fixture key made synthetic.
- Docs: INSTRUCTIONS credit-preflight section; TTS section now matches SKILL.md (Fish Audio primary, Piper opt-in); EXAMPLES no longer claims veo3_fast is used when no image is supplied and reads result key `model`. Adapter files still exactly two `.py`.

## v14.3.0 — 2026-07-13 — Piper demoted to OPTIONAL/opt-in (Fish Audio 2.1 Pro is the primary narrator)

Demotes Piper to an **optional, opt-in, offline-only** TTS fallback that is **OFF by default**.
The operator already has cloud TTS (Fish Audio / Gemini / OpenAI / MiniMax), so a box without
Piper must install cleanly. This reverses the v14.2.0 FAIL-LOUD Piper behavior. Remotion +
HyperFrames provisioning and the Node ≥ 22 preflight are unchanged.

- **`provision-render-deps.sh`** — the Piper step (§5) is now gated behind an explicit opt-in
  flag **`SKILL47_INSTALL_PIPER=1`**. **Default path skips Piper entirely** — no
  `pip install piper-tts`, no `en_US-lessac-medium` voice-model download. The former FAIL-LOUD
  behavior is removed: a Piper install/download failure is now **WARN-only and NEVER aborts the
  install**. Removed the `SKILL47_PIPER_OPTIONAL` toggle (superseded by the off-by-default gate).
  Remotion + arch/OS compositor + Chrome-Headless-Shell, HyperFrames CLI + bundled Chrome, and
  the Linux Chromium system libs + ffmpeg are **unchanged** (still installed by default).
- **`install.sh` (Step 3.5)** — messaging updated: Piper is optional/opt-in and never causes the
  render-provisioning step to abort; removed the `SKILL47_PIPER_OPTIONAL` guidance.
- **`qc-movie-producer.sh`** — the two HARD asserts that *required* Piper (pinned `PIPER_VERSION`
  default, pre-staged voice ONNX model) are replaced by asserts that Piper is **optional/opt-in**
  (the `SKILL47_INSTALL_PIPER` gate is present) and that **Piper is never installed on the default
  path** (the opt-in gate precedes any `piper-tts` install). Remotion/HyperFrames/Chromium-libs
  and Node ≥ 22 asserts are kept as-is. The runtime `import piper` check stays soft (WARN).
- **Docs (`SKILL.md`, `INSTALL.md`, `DEPENDENCY-MANIFEST.md`)** — new voice order documented:
  **Fish Audio 2.1 Pro (`s2.1-pro`) primary; Gemini TTS / OpenAI TTS / MiniMax (a.k.a. "Mimo")
  cloud fallbacks; Piper optional, opt-in, offline-only, not installed by default.** Notes that
  OpenMontage's TTS auto-discovery uses the cloud providers when Piper is absent.
- **Unchanged:** the `Dockerfile` stays the opt-in Linux/VPS artifact (native install remains the
  default); the Node ≥ 22 preflight requirement is left exactly as-is.
- `skill-version.txt` + `SKILL.md` frontmatter: **v14.2.0 → v14.3.0**.

## v14.2.0 — 2026-07-13 — Render runtime provisioned for macOS AND Linux/VPS (Piper/Remotion/HyperFrames)

Fixes the "Mac-only in practice" gap in the OpenMontage engine's browser-based render
paths and the silent Piper soft-fail. `make setup` installed the upstream npm/pip deps but
NO Chromium system libraries and NO Piper voice model, so a fresh Linux/VPS container FAILED
every Remotion/HyperFrames (headless-Chromium) render and often ended up with no offline
Piper TTS. All version claims are pinned to their source registry (bump in one place).

- **NEW `provision-render-deps.sh`** — arch/OS-aware, idempotent render-runtime provisioner
  wired into `install.sh` as Step 3.5. For BOTH macOS and Linux it: (Linux) `apt-get`s the
  Chromium system libraries + ffmpeg that headless Chrome needs to launch (Remotion's
  documented Debian/Ubuntu set, incl. the `libasound2`→`libasound2t64` rename fallback);
  installs the pinned latest **Remotion 4.0.489** + the arch/OS-specific
  `@remotion/compositor-<os>-<arch>[-<libc>]` + `npx remotion browser ensure`
  (Chrome-Headless-Shell); cache-warms the pinned latest **HyperFrames 0.7.56** CLI +
  bundled Chrome; installs the latest arch-aware **Piper `piper-tts==1.4.2`**
  (OHF-voice/piper1-gpl) **FAIL-LOUD** (root-cause fix for the Makefile's silent
  `pip install piper-tts || echo skip`) and **pre-stages the default `en_US-lessac-medium`
  voice ONNX model** (direct from the pinned `rhasspy/piper-voices` HuggingFace tag).
  Toggles: `SKILL47_SKIP_RENDER_PROVISION=1`, `SKILL47_PIPER_OPTIONAL=1`, `SKILL47_SKIP_APT=1`.
- **NEW `Dockerfile`** — Linux/VPS image on `node:22-bookworm-slim` (Remotion's recommended
  base; Node 22 satisfies HyperFrames' `engines: node>=22`) that bakes the Chromium system
  libs + ffmpeg, clones OpenMontage at the pinned SHA, runs `make setup` then the
  provisioner. The client's own `KIE_API_KEY` is injected at RUNTIME, never baked in.
- **`preflight.sh`** — Node floor raised **18 → 22** (HyperFrames hard-requires Node ≥ 22;
  a box on 18–21 passed preflight yet failed every HyperFrames render). nodesource hint
  bumped to `setup_22.x`.
- **`qc-movie-producer.sh`** — `node >= 18` assertion raised to `node >= 22`; added HARD
  asserts that the provisioner + Dockerfile exist, the provisioner is valid bash, pins all
  three versions, installs a compositor, ensures Chrome-Headless-Shell, and pre-stages a
  voice model, that `install.sh` wires the provisioner, and that preflight/Dockerfile carry
  the Node-22 floor + Chromium libs.
- **`.github/workflows/video-pipeline-lockstep.yml`** — adds an `actions/setup-node@v4`
  (Node 22) step so the `qc-movie-producer.sh` Node≥22 assertion is provisioned in CI; adds
  the provisioner + Dockerfile to the path triggers.
- Docs (`INSTALL.md`, `DEPENDENCY-MANIFEST.md`) updated: Node ≥ 22, the new Step 3.5, the
  Linux/VPS + Docker provisioning path, and the pinned versions with source URLs.

## v14.1.4 — 2026-07-05 (Wave-0 merge-train T-47-movie-producer)

Seven fixes from the 2026-07-05 master fix-plan (skills-36-to-end weakness sweep).
All changes are scoped to `47-movie-producer/`.

- **FIX-S36-38** — `qc-movie-producer.sh`: the `.github/workflows/video-pipeline-lockstep.yml` CI-workflow assertion is now gated behind repo detection (HARD only when a `.git`/`.github` tree exists beside the skill; a PRE note on a client box). It no longer aborts every client install at Step 8, since no installer copies the repo-root CI workflow to client boxes.
- **FIX-S36-39** — `install.sh` Step 6 now idempotently **WRITES** the Rule-Zero budget cap into the clone's `config.yaml` via PyYAML (`budget.mode: cap`, `total_usd` ≤ 5 — never raising an already-lower client cap, `single_action_approval_usd: 0.50`, `require_approval_for_new_paid_tool: true`, `checkpoint.policy: guided`), preserving all other keys. QC stays pure verification. `INSTALL.md` Step 6 updated.
- **FIX-S36-40** — new `scripts/cc_board.py` (ported from Skill 48, fail-soft): the production run now lands on the Command Center as one campaign with 5 phase cards, and `executive_producer.py` walks each attested phase card `in_progress → review → done` via the legal-transition path (the QC `review` column is never skipped). At V-CONTROL the `campaign_id` + finished MP4 path are stamped into `render-receipt.json`. Board outage / missing token is a clean no-op. New `scripts/test_cc_board.py` proves the contract; QC wires both in.
- **FIX-S36-41** — added a binding **Attestation spine** section to `INSTRUCTIONS.md`, `CORE_UPDATES.md`, and `INSTALL.md` requiring per-phase `executive_producer.py --phase V-*` attestation, and listed the `scripts/` inventory in `SKILL.md` / `INSTALL.md`.
- **FIX-S36-42** — `video_build_check.py`: the provider-audit / native-provider ban is scoped to imagery/video **generation** tools. A bare `GOOGLE_API_KEY`/`GEMINI_API_KEY` embedding key (legitimately present on fleet boxes for memory / Skill 45) is allowlisted and no longer hard-stops a paid video job; a real Google generation tool (`imagen`, `provider_used` naming google, etc.) still fails. Regression probes added to `test_video_preflight.py`.
- **FIX-S36-43** — `install.sh` pins the OpenMontage clone to a verified upstream commit (`OPENMONTAGE_PINNED_SHA=ce11f6a…`, overridable via `OPENCLAW_OPENMONTAGE_SHA`); the `INSTRUCTIONS.md` pipeline table was regenerated from that pinned tree's real 13 `pipeline_defs/*.yaml` (removing the invented `script-to-video`/`explainer-video`/`brand-video`/`news-recap` entries). `SKILL.md` pipeline list + documentary-montage source list corrected to the pinned tree.
- **FIX-S36-44** — `video_build_check.py` `run_postflight_gate`: the `final_mp4` deliverable is validated against the render receipt's specific `final_mp4_path` (falling back to `output_path`), excluding any path under `assets/` (raw stock footage), instead of a blind recursive `**/*.mp4` glob; the downstream handoff must be an EXACT enum token, not a substring. Fixtures updated; regression probes added.

## [15.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
