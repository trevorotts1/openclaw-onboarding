# Donor selections — drama-song-ad-factory (DTS-103)

Verification date: 2026-10-06. Method: GitHub REST API only (`api.github.com` `repos/{OWNER}/{REPO}`,
`repos/{OWNER}/{REPO}/license`, `contents/`, `git/trees`, `branches/{BRANCH}`). No donor repo cloned.
Unauthenticated `curl` quota (60/hr) exhausted mid-run after all 9 repo+license blocks were saved;
branch HEAD SHAs completed via authenticated `gh api` (same GitHub API, higher quota). Raw dumps:
`lanes/DTS-103-lane/endpoint-evidence.txt`, `/tmp/blackceo-DTS-103-verify/` (`api-dump.txt`,
`shas.txt`, `subdirs*.txt`, `treesearch.txt`, `filechecks.txt`, `rejectcheck.txt`, `smartcheck.txt`).

## Endpoint evidence (all 9)

| Donor | Repo endpoint `default_branch` | Repo `license.spdx_id` | License endpoint (`path` / blob `sha` / `spdx_id`) | Branch HEAD SHA | `pushed_at` | Archived |
|---|---|---|---|---|---|---|
| `ChrisChen667788/wind-comic` | `main` | MIT | `LICENSE` / `8ae7d9692619`… / MIT | `ca24db3ff59ceb2b4c8a520fa06a0d2fc793c398` | 2026-10-06T10:28:12Z | false |
| `holy-templar/drama-song-ad` | `main` | MIT | `LICENSE` / `ff6af4980c28`… / MIT | `6206a6db31d5659da4e62a11157e41418d5647b0` | 2026-09-30T15:47:20Z | false |
| `cxbxmxcx/commercial-creator` | `main` | MIT | `LICENSE` / `9fea5f787e58`… / MIT | `ea6a8a8c46b42a308a3e39138b520f0e92553055` | 2026-07-12T14:47:23Z | false |
| `HITsz-TMG/VideoClaw` | `main` | MIT | `LICENSE` / `f3efce12c9c1`… / MIT | `16c1ce0b553e30eff90ff1274e8a8a63c1d548a3` | 2026-08-26T05:31:29Z | false |
| `A-cat-with-carrots/OnlyShot` | `main` | MIT | `LICENSE` / `34f2c6347257a`… / MIT | `75c57f2fff6e2b3ab14004ce635a445e416c9b27` | 2026-07-07T17:24:47Z | false |
| `harry0703/MoneyPrinterTurbo` | `main` | MIT | `LICENSE` / `3b409c921f64`… / MIT | `68eb5a68b93cfe338198b3dfb151f6d5ec2fe4e5` | 2026-10-04T06:48:17Z | false |
| `FireRedTeam/FireRed-OpenStoryline` | `main` | Apache-2.0 | `LICENSE` / `1f941e9ef015`… / Apache-2.0 | `c9e945215586f45c12a61c1951ee9a8e9c43a027` | 2026-07-31T03:16:31Z | false |
| `calesthio/OpenMontage` | `main` | AGPL-3.0 | `LICENSE` / `be3f7b28e564`… / AGPL-3.0 | `9327439db69021ab4b0e2776729bf3b58fdb5a87` (branch protected) | 2026-10-03T16:28:55Z | false |
| `HBAI-Ltd/Toonflow-app` | `master` | MIT | `LICENSE` / `dd6492ccf3ec`… / MIT | `72a895c26aab3f54c5a914517615362208fa6008` (= directive snapshot commit) | 2026-10-05T13:18:34Z | false |

Repo-endpoint and license-endpoint SPDX agree on all 9. Toonflow default branch is `master`, not `main`.

## 1. Wind Comic (`ChrisChen667788/wind-comic`) — primary engineering donor, MIT, adapt

Verified modules (recursive tree endpoint, 2,393 blobs):

- `lib/character-dna.ts` + `app/api/projects/[id]/extract-character-dna/route.ts` + `tests/v2-21-character-dna.test.ts` → **adapt** (Character DNA → Continuity Bible character records)
- `lib/style-bible.ts` + `tests/v2-20-style-bible.test.ts` → **adapt** (Style Bible compiler-injected, not hand-copied)
- `lib/pipeline-checkpoints.ts` + `tests/pipeline-checkpoints.test.ts` → **adapt** (persistent project state / checkpoints)
- `lib/vision-audit.ts` + `app/api/projects/[id]/vision-audit/route.ts` + `.../vision-audit/run/route.ts` + `tests/v3-4-vision-audit.test.ts` → **adapt** (vision QC with targeted regeneration)

Nothing copied verbatim. Reimplement against KIE provider stack; do not inherit provider assumptions or UI.

**Rejected:** null-audit aggregate-pass. `lib/vision-audit.ts` returns `null` on audit failure
("失败返 null (不阻塞流程)" — non-blocking) and `aggregateFilmAudit` averages shot scores, so failed
shots can pass inside an aggregate. BlackCEO QC: null/nonblocking audits never qualify mandatory gates;
no aggregate average erases a critical identity/lyric/offer/product/CTA defect.

## 2. Drama Song Ad (`holy-templar/drama-song-ad`) — creative donor, MIT, adapt methodology

`SKILL.md` (~26 KB, blob `0187306a28be`) + `examples/` (character sheet, shot sheets, hero's journey).
Stages 00–10: tool check, intake, three story arcs, twelve-stage outline, sung script, song (Suno V5.5),
timing map, shot plan, character sheets, shot sheets, clips, edit. **Adapt, concept-level:**
reorganize into BlackCEO-owned `references/drama-song-methodology.md`,
`direct-response-story-arc.md`, `song-vsl-writing-rules.md`, `lyric-to-shot-contract.md`,
`resilia-mode-qc.md`. Do not copy the giant `SKILL.md`. Do not inherit stale pins (Suno V5.5,
Seedance 2.0, GPT Image 2, two-song crossfade, Claude-Code-only runtime) — modernize through KIE.

## 3. Commercial Creator (`cxbxmxcx/commercial-creator`) — ad control donor, MIT, adapt

Verified `commercial/` modules (contents endpoint):

- `store.py`, `jobs.py`, `shot_plan.py`, `compiler.py`, `lessons.py` → **adapt**
  (versioned artifact graph, job ledger, adversarial shot review, corrective regeneration, durable lessons)
- `agents/` (`intake/director/judge/shot_room/continuation/…`), `animatic.py`, `adapters.py`,
  `storyboard_sheet.py`, `keyframes.py`, `assembly.py`, `audio_vo.py`, `audio_final.py`, `music.py`,
  `overlay.py`, `mcp_server.py` (`commercial_server.py` + `mcp_server.py` at root) → **concept-only**,
  adapt selectively (animatic-before-spend, approval/cost gates, MCP surface ideas)

Approval gates policy-driven (`autonomous` vs `gated`), never hardcoded.

**Rejected:** timeout auto-requeue. `commercial/jobs.py` auto-requeues TRANSIENT failures once after 30 s,
matching `timeout`/`connection`/`reset`/`429`/`500`–`504`. A timeout during paid submission is not proof
of provider rejection — auto-resubmit risks double-spend. BlackCEO rule: retain reservation, mark
`unknown`, reconcile via provider records/operator evidence, park if undeterminable. Required ledger
states: `planned`, `reserved`, `submitted`, `unknown`, `succeeded`, `failed`, `reconciled`.

## 4. VideoClaw (`HITsz-TMG/VideoClaw`) — OpenClaw/resumability donor, MIT, adapt

Verified paths (tree + contents endpoints, 443 blobs):

- `video-claw/video-claw/backend/pipelines/storage.py` (task dirs, `create_task`/`update_task`/
  `append_artifact`/`mark_running`/`mark_completed`/`mark_failed`) → **adapt** (stage retention, resume)
- `video-claw/video-claw/backend/pipelines/standard.py` (narration/image-prompt parsing, segment builder) → **adapt** (stage pipeline shape)
- `video-claw/references/workflow/smart_continue.md` (+ `backend/prompts/script/smart_continue_script_zh.txt`) → **concept-only**: intervene on `script_generation` with `action: "smart_continue"` to append episodes (`episodes_to_add`, `sequel_idea`, `new_episodes`/`new_characters`/`new_settings` artifacts). Useful continuation pattern for campaign variants/sequels; not the core VSL path.
- `video-claw/video-claw/SKILL.md`, `references/` → **concept-only** (OpenClaw packaging conventions)

Do not replace BlackCEO skill system or Command Center with VideoClaw UI.

## 5. OnlyShot (`A-cat-with-carrots/OnlyShot`) — SOP/failure-intelligence donor, MIT, concept-only

`SKILL.md` (~26.9 KB, blob `03261224…`), `references/` (21 files: `visual-consistency-sop.md`,
`storyboard-craft.md`, `jimeng-failure-modes.md`, `cliche-detector.md`, `critic-checklist.md`, …),
`scripts/` (storyboard-first tooling), `evals/`, `assets/`. **Concept-only / adapt knowledge, not runtime:**
storyboard-before-video-spend, reference-library discipline, preflight validation, documented failure
modes and prevention rules. Not the central runtime unless fresh research proves it beats Wind Comic.

## 6. MoneyPrinterTurbo (`harry0703/MoneyPrinterTurbo`) — secondary, MIT, study

Root: `app/`, `cli.py`, `main.py`, `webui/` (29 entries). `app/services/`: `subtitle.py`, `voice.py`,
`video.py`, `bgm.py`, `task.py`, `llm.py`, provider adapters (`volcengine_seedance.py`, `ofox.py`,
`muapi.py`, `metaso_minimax.py`, `elevenlabs_music.py`, …), `material*.py`, `upload_post.py`.
**Study-only:** provider-adapter shape, batch execution, subtitle handling, audio/TTS routing, Fish Audio
integration patterns, API/CLI/WebUI separation. Do not replace core architecture. ElevenLabs paths are
reference only — Fish Audio stays the preferred spoken-voice path.

## 7. FireRed-OpenStoryline (`FireRedTeam/FireRed-OpenStoryline`) — secondary, Apache-2.0, study

`src/open_storyline/`: `agent.py`, `nodes/` (`core_nodes`, `node_manager/schema/state/summary`),
`storage/` (`file.py`, `agent_memory.py`, `session_manager.py`), `skills/skills_io.py`, `mcp/`,
`utils/`; root `agent_fastapi.py`, `cli.py`. **Study-only** (Apache-2.0 attribution preserved if adapted):
non-destructive post-production, natural-language edits, partial redo, reusable editing skills,
OpenClaw skill packaging. Potential future post-production/editor service, not v1 core.

## 8. OpenMontage (`calesthio/OpenMontage`) — STUDY-ONLY, AGPL-3.0

SPDX `AGPL-3.0` confirmed on both endpoints. **No AGPL source copied into BlackCEO skill without an
explicit license decision.** Study concepts only (`pipeline_defs/*.yaml` manifests,
`skills/core/`: `ffmpeg.md`, `whisperx.md`, `subtitle-sync.md`, `remotion.md`, … — agent-as-control-plane,
pipeline manifests, checkpoints); independently implement generic ideas or call an external install
across a clean boundary. Audit existing Skill 47 OpenMontage external-clone boundary first.

## 9. Toonflow-app (`HBAI-Ltd/Toonflow-app`) — secondary, MIT, study

Default branch `master`; HEAD `72a895c…` equals the directive snapshot commit. Layout: `apps/`
(`desktop`, `server`, `updateServer`, `web`), `packages/` (`nodes`, `providers`, `skills`, `tools`,
`ffmpeg`, `mcp`, …). **Study-only:** canvas/project model, plugins, agent workflow, extensibility —
adopt only if current architecture proves stronger than Wind Comic/VideoClaw for our exact needs.

## License gate summary

- MIT ×7 (wind-comic, drama-song-ad, commercial-creator, VideoClaw, OnlyShot, MoneyPrinterTurbo, Toonflow-app): adapt with notices preserved in `THIRD_PARTY_NOTICES.md`; never obscure provenance.
- Apache-2.0 ×1 (FireRed-OpenStoryline): study; preserve attribution if adapted.
- AGPL-3.0 ×1 (OpenMontage): study-only, hard boundary.
- Top-level LICENSE check does not clear vendored assets/transitive deps — inspect before incorporation.
- Prefer reimplementation of small concepts over vendoring large upstream projects.

## Test evidence (DTS-103 self-check)

- All 9 repo+license endpoint responses saved and SPDX cross-checked (repo vs license endpoint agree 9/9).
- All 9 default branches + HEAD SHAs recorded (8×`main`, 1×`master`).
- Module paths verified live via contents/tree endpoints, not README claims (wind-comic 2,393 blobs, VideoClaw 443 blobs enumerated; `smart_continue` located in `references/workflow/`, not in `pipelines/`).
- Rejected-behavior quotes pulled from file contents via API (`vision-audit.ts` null-return lines; `jobs.py` auto-requeue block).
- No `git clone` of any donor ran (API only). No merge, no publish, no approval claimed.
