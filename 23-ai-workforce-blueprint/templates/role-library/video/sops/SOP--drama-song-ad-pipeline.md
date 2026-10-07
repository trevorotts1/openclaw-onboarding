# SOP — Drama Song Ad Pipeline (End-to-End Factory Run)

**Source:** 23-ai-workforce-blueprint department map, skill `75-drama-song-ad-factory` (owner decisions D1, D2, D5, D9, D10, D11, D15–D18, D19, D21, D22, D23, D25, D26, D27, D29–D34; plan sections 4, 4.1, 5.3, 5.4, 6.1–6.14, 7, 9, 10.1, 10.2, 10.3, 11, 12).
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
2. **Creative Strategy** — offer, twelve-beat arc, look from the five styles (Lifelike 3D, 2D Hand-Painted, Sketch to Life, Canvas to Life, Canvas to 3D — section 9.1, D21).
3. **Script / Lyrics** — twelve-beat story, spoken-word share inside owner limits (D15), lyrics beat by beat, one voice tag per character (D20).
4. **Music** — all audio via Suno (C3 method, D22): one Suno song carries singing and every spoken line, tagged per character; **no singing-underneath layer** (dropped, D27); spoken lines play over the music bed, or the client picks **Velvet Voiceover** (section 9.3, D25).
5. **Continuity Bible** — characters, product, locations, style locks.
6. **Storyboard** — shots against the timing map, lip-sync line selection (D10): pain-peak line, product line, call to action, chorus hook — 3 to 4 lines, **Kling avatar** first, InfiniTalk second, Volcengine dropped (section 9.5).
7. **Image / Keyframes** — one keyframe per shot per shape, product reveal (D9 when a product image was supplied).
8. **Video Generation** — shots on the approved model, chained shots wait on their predecessor's last frame; every KIE job is resolved by querying KIE task status, never left open.
9. **QC / Retakes** — per-shot repair, creative-fidelity gate, lyric sign-off.
10. **Assembly** — one edit per shape; captions (D16) and clean master; clips cut for the 5- and 10-minute versions (section 9.4, D23).
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
| Book batch (D26) | One lane per book, all lanes parallel after the single batch approval | One card covers the batch; books never share files |
| Clips for 5 / 10 minutes (D23) | Parallel, one editor per clip, cut from the finished video | FFmpeg cut only — no new AI media |

Both runtimes (OpenClaw department workers and Claude-Nine workflow lanes) read the same lane map; neither adapter may skip it. Paid jobs never exceed the ledger's reservation or the provider's concurrency limit.

## 3. Choice card and price approval (no card, no spend)

- Intake asks at most three questions (offer + optional product image, audience + action after watching, approval of the card). Everything already in the brief is not asked again.
- Both intake modes — **Quick** (default, one sentence in, factory does everything) and **Concept** (client supplies story idea, script, lyrics) — end in **one approval card**: short story summary, length, shape, style, music style, voice version, clips, video model, lip-sync lines, price. **All defaults are pre-selected**, so a client approves with one click.
- The card's fields: **Length** 60 s / 90 s / 3 min / 5 min / 10-minute long version (default 60 s when the brief gives none); **Shape** 9:16 / 16:9 / both (default 9:16, D2); **Style** the five looks (section 9.1); **Music** Soul Ballad / R&B Flow / Soul Rise (section 9.2); **Voice** All Suno / Velvet Voiceover (section 9.3); **Clips** automatic 60- or 90-second clips, offered for the 5- and 10-minute lengths only (D23); **Video model** MiniMax H3, 768P (recommended); **Price** computed for the chosen length, model and shape count.
- Defaults on the card: length/shape from the brief (60 s, 9:16 if none), Style **Lifelike 3D**, Music **Soul Ballad**, Voice **All Suno**, model **MiniMax H3, 768P (recommended)**.
- **Book campaigns and batch mode (D26):** intake takes the book title, author, cover image (used as the product image), buy link, audience and the pain or transformation. The client approves **one choice card for the whole batch** (look, music, voice, length, shape) and the card shows the **batch total**; each book then gets one ad in its own campaign folder, receipt, ledger run and Command Center deliverable. Books and authors are never mixed.
- **Prices are computed, never typed in.** Every price on the card — including lip-sync close-ups, per-character voice packs, both shapes and the batch total — comes from **Skill 74 `price --model ID --units N`**, the single price authority (plan 5.4). The adapter runs in `preflight` before approval, `prompt-budget --check` on every compiled prompt, and `health` for mode. If the live rate cannot be read, the card says price unavailable and no paid work starts. Both shapes show their own price before approval (D2).
- **Skill 74 only:** upload, submit, poll and download all go through Skill 74 (`upload`, `run`/`submit` + `wait`, `save`); this pipeline never carries a second KIE client. In shadow or off mode the run stops before approval and tells the client plainly that media generation is not switched on for their box yet — a `skipped` result means "not generated", never success.
- **Approval records the spending limit**: chosen price **plus 20% retake allowance**, in USD and KIE-credit equivalent. No paid call happens before that record exists (Rule-Zero: announce provider, model identifier and estimated USD cost first).
- Every paid call reserves against the spend ledger before submission. On resume, the card shows only what changed and the next stage.

## 4. MiniMax H3 is the default model

- **MiniMax H3, 768P is the recommended default** (owner decision D5). If the client makes no choice on the card, the factory uses MiniMax H3 — the card states this.
- The client may pick any model on the price chart; Seedance 2.5 is marked PREMIUM with its real price shown plainly. Model names come from the current router/provider settings, never from a hard-coded table; the drama skill asks Skill 67/66/68 for capabilities and never hard-codes a model (directive 16).
- **If MiniMax H3 is unavailable** (blocked, failing, absent from the live catalog): tell the client and offer the next cheapest APPROVED model that fits the job with its price — never switch silently (plan 5.3, directive 9.1). Resumes and retakes reuse the saved model and resolution.
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
- **Creative-fidelity gate:** style injected in every visual prompt, twelve-beat arc present, product reveal after the mentor. Hybrid looks (section 9.1) also check the switching rules: style held at least 3 seconds, dissolve on matching poses, one identical character across both styles, no lip-sync on sketch or 2D shots.
- **Human lyric sign-off** is required before the song is generated.
- **Speaker-on-screen check (reference recipe):** for every line, the person visible is the speaking character or the device the voice comes from; a narrator, phone or laptop voice may play as voice-over but is **never lip-synced onto a person** (D26). Every lip-sync input clip carries only that on-screen speaker's own isolated line.
- **Voice packs (D20):** no two characters share a voice — distinct per-character Suno voice packs, same-gender characters clearly different. **Pitch check:** each line must measure inside its character's gender range (about 85–155 Hz male, 165–255 Hz female) with an octave-error guard; a miss fails QC and the line is regenerated in Suno.
- **Lip-sync QC:** flagged lines require mouth movement matching the sung words, tight front-facing close-ups only; unflagged shots keep the no-accidental-mouth-movement rule. Lip-sync model order is Kling avatar (`kling/ai-avatar-standard`), then InfiniTalk; Volcengine is dropped (D33).
- **Length check:** Suno extend is used only to hit the exact chosen length (or to repair a section); an unknown KIE job result is resolved by querying KIE task status and never left open.
- Final QC checks: sync within one frame, loudness −14 LUFS, call-to-action on screen at least 3 seconds, correct format, spoken-word share inside the 40–70% limits, captions correct and never covering a face or the product, device screens oriented correctly. Each length, shape and clip is judged on its own files.

## 7. Delivery

- **Mac clients / Claude-Nine users:** finished deliverables (final videos, song, receipts) are **copied** — never moved — to `~/Downloads/Drama Song Ads/<campaign-id>/<length>-<shape>/`. Working files stay in the run folder so resume and repair still work. The long versions also carry their clips and SRT files.
- **VPS clients** (no Downloads folder): delivered through Command Center deliverables for the campaign — **one deliverable per ad** (plan 12).
- **Board (plan 10.3):** one parent campaign per brief plus the twelve stage cards (Research, Creative Strategy, Script/Lyrics, Music, Continuity Bible, Storyboard, Image/Keyframes, Video Generation, QC/Retakes, Assembly, Final QC, Delivery) through the existing `/api/ad-campaigns` endpoint — no new board. **One Kanban card per ad and per batch**; variants are carded from Script/Lyrics onward (lengths) and Storyboard onward (shapes), keyed `(campaign_id, run_id, stage_id, variant)` so retries update instead of duplicating. Activities are logged at milestones only; `blocked` stays reserved for a human.
- **Batch campaigns:** each book's ad gets its own campaign folder, receipt, ledger run and Command Center deliverable. Nothing crosses between books or authors.
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

## 9. The option menu (version 2)

### 9.1 Looks — five styles (D21, D29)

| Style | Look | Switching / lip-sync rule |
|---|---|---|
| **Lifelike 3D** (default) | Cinematic CGI, lifelike faces | Lip-sync on close-ups |
| **2D Hand-Painted** | Hand-painted 2D cartoon | Lip-sync only on large front-facing close-ups |
| **Sketch to Life** | B&W sketch with speech bubbles → realism → back, golden realism finale | No lip-sync on sketch shots; realism close-ups only |
| **Canvas to Life** | 2D painted → realism → back, golden finale | Same switching rules as Sketch to Life |
| **Canvas to 3D** | 2D painted → lifelike 3D → back (Version E) | Lip-sync only on lifelike 3D close-ups |

Hybrid switching: comedy/setup on the drawn style, hard emotional moments on realism, transformation on the golden finale; dissolve about 0.3–0.4 s on matching poses, each style held at least 3 seconds, no flicker, one identical character across both styles. Realism means real-looking live-action (`style-bibles/realism-cinematic.md`, D19), not 3D animation. Each look carries its own Style Bible block, switching rules and QC.

### 9.2 Music styles (D18, D30)

**Soul Ballad** (default, slow and emotional) · **R&B Flow** (rap verses with a sung hook, spoken share at the upper end of D15, never above 70%) · **Soul Rise** (slow through the pain, lifts at the mentor/product turn).

### 9.3 Voice versions (D25, D31)

- **All Suno (default):** one Suno song carries every sung and spoken line, tagged per character (C3 method, D22).
- **Velvet Voiceover** (renamed from Velvet Echo): the Suno song plus Google text-to-speech for the spoken lines, a plain voiceover with the song underneath — **no echo or reverb**. Character-gender and speaker-on-screen checks (section 6) still apply.
- Both versions use per-character voice packs; no two characters share a voice.

### 9.4 Lengths, shapes and clips (D2, D23, D32)

- Lengths: **60 s, 90 s, 3 min, 5 min, 10-minute long version** — each its own song and timing map, shared research/story world/Bible. One Suno generation per length; extend only to hit the exact length.
- Shapes: **9:16, 16:9, or both** — each generated natively, never cropped from the other (free centre-crop only if the client accepts it on the card).
- **Clips:** for 5- and 10-minute versions only, automatic **60- or 90-second clips** for ads and Reels — a free FFmpeg cut of the finished video, on whole lines with a short music fade, own re-timed captions, ending "Watch the full story on YouTube, link in comments".

### 9.5 Lip-sync model (D10, D33)

**Kling avatar** first (`kling/ai-avatar-standard`: front-facing close-up image plus that character's own isolated line), **InfiniTalk** second, **Volcengine dropped**. Selected lines only: pain-peak line, product line, call to action, chorus hook — typically 3 to 4 lines. Narrator and off-screen voices are never lip-synced onto a person (D26).

---

**Doctrine refs:** Rule-Zero paid-call announce + budget cap (`universal-sops/native-skill-invocation.md`), spend ledger reserve/reconcile (plan 11), QC independence (plan 9), delivery paths (plan 12), Skill 74 as the only KIE client (plan 5.4), batch and card rules (plan 10.3, 6.14).
