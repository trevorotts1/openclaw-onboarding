# SOP — Drama Song Ad Pipeline (End-to-End Factory Run)

**Source:** 23-ai-workforce-blueprint department map, skill `75-drama-song-ad-factory` (owner decisions D1, D2, D5, D11; plan sections 4, 6, 7, 9, 10.2, 11, 12).
**Authority:** Binding operating SOP for every drama-song ad campaign. Lead role: `vsl-video-sales-letter-specialist` (Video department, owner decision D1). Support roles: `video-editor` (assembly), `storyboard-pre-production-specialist`, `qc-specialist-video`, `head-of-video-production`.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 75-drama-song-ad-factory (installs at `~/.openclaw/skills/75-drama-song-ad-factory/` on the client box)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

---

## 1. Stage order (fixed — never reorders)

The overall order is fixed by factory doctrine: **story → lyrics → song → timing → visuals**. The twelve stages, in order:

1. **Research** — audience, competitors, claim evidence.
2. **Creative Strategy** — offer, twelve-beat arc, visual style (2D / Lifelike 3D / Hybrid).
3. **Script / Lyrics** — twelve-beat story, spoken-word share inside owner limits (D15), lyrics beat by beat.
4. **Music** — all audio via Suno (C3 method, D22): singing, spoken parts, character voices, singing-underneath layer.
5. **Continuity Bible** — characters, product, locations, style locks.
6. **Storyboard** — shots against the timing map, lip-sync line selection (D10).
7. **Image / Keyframes** — one keyframe per shot per shape, product reveal (D9 when a product image was supplied).
8. **Video Generation** — shots on the approved model, chained shots wait on their predecessor's last frame.
9. **QC / Retakes** — per-shot repair, creative-fidelity gate, lyric sign-off.
10. **Assembly** — one edit per shape; captions (D16) and clean master.
11. **Final QC** — audio, sync, visuals, call-to-action claims; one final pass or fail.
12. **Delivery** — copy to the client's Downloads folder (Mac) or Command Center deliverables (VPS).

A stage does not start until its inputs passed QC. The lane planner (`scripts/core/lane_planner.py`) refuses a start whose inputs are unproven, and refuses chained shots run in parallel; its refusals are exit code 4 (rejected), not warnings.

## 2. What runs in parallel

Speed comes from running each stage's independent pieces at the same time — the order above never changes.

| Work | Parallel or in order | Why |
|---|---|---|
| Intake and choice card | In order | One short conversation |
| Research topics | Parallel, one worker per topic | Topics are independent |
| Twelve-beat story drafts | Parallel drafts (3–5), then one independent judge picks | Judge never drafter |
| Lyrics | In order, plus one critic | Lines follow the chosen story beat by beat |
| Song generation | Parallel candidate takes, scored by an independent judge | Takes are independent |
| Song QC, master, timing map | In order | Every visual depends on the final timing |
| Continuity Bible entities | Parallel, one worker per entity | Independent once the story is fixed |
| Shot list | In order | One timeline aligned to the song |
| Keyframe images | Parallel, one per shot per shape | Independent once the Bible is locked |
| Video shots | Parallel across scenes; in order inside a scene when a shot starts on the previous shot's last frame | Largest speed gain; chained shots must wait |
| Per-shot QC repair | Parallel, one checker per shot; repair only the failed shot | Directive 17.7 |
| Assembly | In order, once per shape | One edit per shape |
| Final QC | Parallel checkers (audio, sync, visuals, call-to-action), then one final pass or fail | A critical defect can hide in no average |
| Two shapes | Parallel from the shot plan onward | Shared story and song |
| Several lengths | Parallel from the lyrics onward | Shared research, story world, Bible |

Both runtimes (OpenClaw department workers and Claude-Nine workflow lanes) read the same lane map; neither adapter may skip it. Paid jobs never exceed the ledger's reservation or the provider's concurrency limit.

## 3. Choice card and price approval (no card, no spend)

- Intake asks at most three questions (offer + optional product image, audience + action after watching, approval of the card). Everything already in the brief is not asked again.
- Both intake modes — **Quick** (default, one sentence in, factory does everything) and **Concept** (client supplies story idea, script, lyrics) — end in **one approval card**: short story summary, length, shape, style, music style, video model, lip-sync lines, price.
- Defaults on the card: length/shape from the brief (60 s, 9:16 if none), Style **Lifelike 3D**, Music **Soul Ballad**, model **MiniMax H3, 768P (recommended)**.
- **Prices are computed, never typed in.** The price comes from the live KIE catalog read through the Skill 74 registry. If the live rate cannot be read, the card says price unavailable and no paid work starts. Both shapes show their own price before approval (D2).
- **Approval records the spending limit**: chosen price **plus 20% retake allowance**, in USD and KIE-credit equivalent. No paid call happens before that record exists (Rule-Zero: announce provider, model identifier and estimated USD cost first).
- Every paid call reserves against the spend ledger before submission. On resume, the card shows only what changed and the next stage.

## 4. MiniMax H3 is the default model

- **MiniMax H3, 768P is the recommended default** (owner decision D5). If the client makes no choice on the card, the factory uses MiniMax H3 — the card states this.
- The client may pick any model on the price chart; Seedance 2.5 is marked PREMIUM with its real price shown plainly. Model names come from the current router/provider settings, never from a hard-coded table.
- A model-quality canary runs whenever the approved default first changes: one or two animated test shots on the same keyframe, compared against the previous default, result recorded, operator decides.

## 5. Hand-offs

- **Lead — `vsl-video-sales-letter-specialist`:** owns the campaign brief, twelve-beat structure, spoken/sung split (D15), lyric sign-off, and the choice card presented to the client.
- **`video-editor`:** assembly, pacing, captions, loudness, final format.
- **`storyboard-pre-production-specialist`:** shot list, keyframes, lip-sync line selection.
- **`qc-specialist-video`:** independent QC judgments (never the maker).
- **Paid Advertisement:** `direct-response-ad-copywriter` reviews lyrics for sales-copy claims; `tiktok-ads-specialist`, `youtube-ads-specialist`, `facebook-ads-specialist`, `instagram-ads-specialist` advise on length and shape for each platform.
- **Marketing:** audience research feeding the Research stage.
- Hand-offs cross departments only through the cross-dept request template; activities are logged at milestones only.

## 6. QC gates

- `qc_gate.py` + `acceptance-profile.json`: a fresh, independent checker — never the maker — judges every stage. Each check records PASS, FAIL or UNAVAILABLE with evidence and the checker's identity. **UNAVAILABLE never counts as PASS.**
- A startup check refuses to start when the QC judge is the same model family as the maker, or when the assigned visual QC model cannot see images. Every verdict records which model judged it.
- Failed items are repaired up to **two** times; after that the run goes PARKED with a reason (section 8).
- **Real-media rule:** a stage meant to produce media cannot pass unless a media file exists, is the right duration and format, and the checker inspected it (multiple frames of video, listening checks on audio).
- Per-variant verdicts: separate PASS/FAIL per length and per shape. Variants get their own cards from Script/Lyrics onward (storyboard onward for shapes); shared early stages show once.
- **Creative-fidelity gate:** style injected in every visual prompt, twelve-beat arc present, product reveal after the mentor.
- **Human lyric sign-off** is required before the song is generated.
- Final QC checks: sync within one frame, loudness −14 LUFS, call-to-action on screen at least 3 seconds, correct format, spoken-word share inside the 40–70% limits.

## 7. Delivery

- **Mac clients / Claude-Nine users:** finished deliverables (final videos, song, receipts) are **copied** — never moved — to `~/Downloads/Drama Song Ads/<campaign-id>/<length>-<shape>/`. Working files stay in the run folder so resume and repair still work.
- **VPS clients** (no Downloads folder): delivered through Command Center deliverables for the campaign.
- **Only real files are registered as deliverables.** A receipt or placeholder is never registered as a delivered video or song.

## 8. When a run goes PARKED

1. **Read the PARKED reason first.** It is recorded in the run's metadata (`blocked` on the board stays reserved for humans — directive 20.5; PARKED reasons live in metadata, not in the blocked column).
2. **Common causes and the fix for each:**
   - *Repair budget exhausted* (two failed repairs on the same item): re-scope the item, ask the client for a decision, or park the variant while other variants continue.
   - *Retakes would exceed the ceiling* (approved price + 20%): the run parks and asks the client to approve more. It never spends past the ceiling.
   - *Live price unreadable / provider down:* wait and resume; do not invent a price and do not switch models silently.
   - *Creative refusal* (lyric sign-off withheld, claim unsupported): return to the named hand-off (section 5), not to a random stage.
3. **Resume path:** on restart the choice card shows only what changed plus the next stage; spend is reconciled against the ledger before any new paid call (double-spend impossible).
4. **Never** force a parked stage past its gate, never mark a media stage PASS without the media file, and never resolve a park by swapping the client's model/provider.

---

**Doctrine refs:** Rule-Zero paid-call announce + budget cap (`universal-sops/native-skill-invocation.md`), spend ledger reserve/reconcile (plan 11), QC independence (plan 9), delivery paths (plan 12).
