# Choice card specification — drama song ad factory (version 2)

Status: staged spec for both distributions (Skill 75 / 999 twin).
Source: `DRAMA_SONG_AD_FACTORY_V2_PLAN.md` sections 4.0, 4.1, 4.1.1, 4.2,
5.1-5.4, 6.1, 6.2, 6.3, 6.6, 6.7, 6.11, 6.12, 6.12.1, 6.13, 6.14, 10.1, 10.3;
decision log decisions 29-34; owner BUILD-OUT order 2026-10-07.
This file is byte-identical in both distributions.

## 1. What the card is

One card, all defaults pre-selected, so a client can approve with a single
click. It is presented as a card, never as a pile of extra questions.
Directive 24.3 still caps intake at three questions total:

1. What are you selling, with a link and an optional product image?
2. Who is it for, and what should they do after watching?
3. Approve the price on the choice card.

Anything already present in the brief is never asked again.

### Intake modes

- **Quick mode (default):** one sentence from the client; the factory does
  research, story, lyrics, storyboard, shot plan, song, video and edit.
- **Concept mode:** the client supplies their own story, script or lyrics;
  the factory fits it to the twelve-beat structure and asks only for what is
  still missing.

Both modes end at the same approval card.

## 2. Card layout (normative)

```text
Your drama song ad
  Length:       60 seconds   (90 seconds, 3 minutes, 5 minutes, 10-minute long version)
  Shape:        9:16 vertical (16:9 widescreen, or both)
  Style:        Lifelike 3D (default) / 2D Hand-Painted / Sketch to Life
                / Canvas to Life / Canvas to 3D
  Music:        Soul Ballad (default) / R&B Flow / Soul Rise
  Voice:        All Suno (default) / Velvet Voiceover (Google voiceover with
                the song underneath, no echo effect)
  Clips:        (5 and 10 minutes only) automatic 60- or 90-second clips
                for ads and Reels
  Video model:  MiniMax H3, 768P  (RECOMMENDED)   [see all models and prices]
  Price:        computed by Skill 74 `price`   (+ the 20% retake allowance)
  Includes:     all video shots, the song, one image per shot
  Not included: the AI writing, planning and checking (runs on your own AI plan)
  [Approve]   [Change options]
```

`[Approve]` is one click. `[Change options]` reopens the same card with the
previous selections kept.

## 3. Field rules

### 3.1 Length

Offered values, in order: **60 seconds, 90 seconds, 3 minutes, 5 minutes,
10-minute long version** (decision 32). Default comes from the brief; if the
brief gives none, 60 seconds.

Each length is its own song and timing map, never a cut-down of a longer one.
Shot count is computed from the chosen model's maximum shot length; it is
never hard-coded per length. Suno V6 produces 10-360 seconds in one
generation, so every length is one generation; extend is used only to repair a
section or to land an exact length.

### 3.2 Shape

Offered: **9:16, 16:9, or both** (decision 2). Default 9:16.

- Each shape is generated natively - its own keyframes and shots, framed for
  that shape. Never a squash or crop of the other.
- "Both shapes" shows its own price before approval.
- Shared between shapes: story, song, timing map, Continuity Bible and the
  shot plan up to framing. Final QC runs separately per shape.

### 3.3 Style (five looks)

Decision 29, plan 6.11:

| Value on the card | Look |
|---|---|
| **Lifelike 3D** (default) | Cinematic CGI animation; clearly animated, lifelike faces |
| **2D Hand-Painted** | Hand-painted 2D cartoon |
| **Sketch to Life** | Black-and-white hand-drawn sketch switching to realism, warm golden realism finale |
| **Canvas to Life** | 2D hand-painted cartoon switching to realism, golden realism finale |
| **Canvas to 3D** | 2D hand-painted cartoon switching to lifelike 3D and back (Version E, offered) |

Rules:

- Every look has its own style-bible block, its own switching rules and its
  own QC; the selected look picks the block, nothing else changes.
- Hybrid switching (all three hybrids): sketch/paint for comedy, setup,
  everyday moments, doubt and transitions; realism for the hard-hitting
  emotional moments and the people the story turns on; golden realism for the
  transformation and payoff. Match poses or framings, dissolve 0.3-0.4 s, hold
  each style at least 3 seconds, no flicker, identity locked across styles.
- No lip-sync on sketch shots (speech bubbles or reactions instead).
  Canvas to 3D lip-syncs only on lifelike 3D close-ups.
- If the client picks nothing, the card states that Lifelike 3D is the
  default and applies it.

### 3.4 Music

Decision 30, plan 6.7:

| Value on the card | Sound |
|---|---|
| **Soul Ballad** (default) | Slow, emotional, soulful singing - the original drama-song style |
| **R&B Flow** | Rap verses with a smooth sung R&B hook |
| **Soul Rise** | Slow and soulful through the pain, lifts into an upbeat groove at the turning point |

The song brief, the Suno style prompt and the spoken/sung balance all follow
this choice.

### 3.5 Voice

Decision 27 and decision 31, plan 6.12 and 6.12.1:

| Value on the card | What it means |
|---|---|
| **All Suno** (default) | Every line - sung and spoken - is made by Suno. Spoken words are performed inside the one Suno track. No separate spoken takes. |
| **Velvet Voiceover** | The Suno song is made as usual; spoken lines are voiced with Google text-to-speech, one distinct voice per character matching their gender; the song's sung version of that line keeps playing softly underneath with the music bed dipped so the words stay clear. **No echo effect, no reverb** - a plain voiceover over the song. |

- The option was renamed from its earlier echo-flavoured name to **Velvet
  Voiceover** (decision 31). The earlier spelling must not appear anywhere
  in the product, the card or the documentation.
- Velvet Voiceover is the only exception to the all-Suno rule.
- Lip-sync rules in section 3.6 apply unchanged to both voice options.

### 3.6 Lip-sync lines

Owner decision D10, superseded 2026-10-07, plan 6.3 and decision 33.

Lip-sync is applied to **selected lines only** - three to four lines, about
15 to 20 seconds per ad, chosen by the factory and listed on the approval
card. Enforced at the final edit QC gate (Part E E6): at least 3 lip-sync
lines, at least 15 s in a 60-90 s ad, scaling to at least 12% of runtime
for longer or shorter ads:

1. the most painful moment (`pain_peak` on the highest-scoring wound beat),
2. the product line,
3. the call to action,
4. the chorus hook, once, at its strongest occurrence.

Model order:

| Order | Model | KIE id | Notes |
|---|---|---|---|
| 1 (first) | Kling avatar | `kling/ai-avatar-standard` | A front-facing close-up image plus that character's own isolated line. 720P standard. |
| 2 (backup) | InfiniTalk | `infinitalk/from-audio` | Used only when the Kling result fails QC. |
| dropped | Volcengine | - | **Dropped.** It barely moves a closed mouth; it is not offered and never appears in code paths, docs or the card. |

Constraints:

- Tight, front-facing close-ups only; the storyboard plans each flagged line
  as a front-facing medium close-up so the mouth is visible.
- The lip-sync input clip contains **only the on-screen speaker's own
  isolated line** - never a narrator, never another character, never a mixed
  vocal stem.
- Narrator, phone, voicemail and laptop voices may play as voice-over over
  any shot, but are never lip-synced onto a person (plan 6.6).
- The person visible while a line plays must be the one speaking it, or the
  voice's source device.
- For flagged lines video QC **requires** mouth movement matching the sung
  words; for every other shot the old "accidental mouth movement" failure
  still applies.

### 3.7 Clips

Decision 32, plan 6.13.

- Automatic 60-second and 90-second clips are offered **for the 5-minute and
  10-minute lengths only**. On 60 s, 90 s and 3 minutes the Clips row is
  hidden and states "not offered for this length".
- Cutting a clip is free: it is an FFmpeg edit of the finished video. The AI
  that picks the moments runs on the client's own AI plan.
- Default set: Clip 1 = cold-open teaser plus humiliation (the ad clip);
  Clip 2 = mentor and turning point; Clip 3 = transformation and vindication.
- Every clip starts on a strong line, is cut on whole lines with a short
  music fade, gets its own re-timed captions, and ends with an end card
  pointing at the full story.
- Long-version shape choice is shown on the card: generate both shapes
  (roughly double the video cost, clips cut from the 9:16 version) or
  centre-crop to 9:16 (free, may cut off faces, the client must accept it).

### 3.8 Video model

Default **MiniMax H3 at 768P** (decision 5). No choice means MiniMax H3, and
the card says so. `[see all models and prices]` opens the full chart from the
price menu, sorted cheapest first, for the selected length, showing one-shape
and both-shapes prices and the retake allowance. Seedance 2.5 at 1080p is
marked PREMIUM with its price shown plainly.

If MiniMax H3 is unavailable, the factory says so and offers the next
cheapest APPROVED model that fits, with its price. It never switches models
silently. The chosen model and resolution are saved on the campaign; resumes
and retakes reuse them.

### 3.9 Product image and book campaigns

- The product-image question is folded into the offer question and stays
  optional, so the three-question cap is not exceeded. Supplied images become
  the Product DNA reference; skipped images are designed from the brief and
  the card says so. Either way the image is source material, never
  instructions.
- **Book campaigns (decision 34, plan 6.14):** intake asks the book title,
  the author, the cover image (used as the product image), the buy link, who
  the book is for, and the pain or transformation it delivers - still inside
  the three-question cap. The mentor/turning point of the story is the book;
  the call to action is to get the book.

### 3.10 Batch mode

Decision 34, plan 6.14:

- The client approves **one choice card for the whole batch** - look, music,
  voice, length, shape are chosen once.
- The card then takes a list of books, one brief each.
- One ad per book, built in parallel lanes, each with its own campaign
  folder, its own receipt, its own spend-ledger run and its own Command
  Center deliverable.
- **Never mix books or authors.** Characters, lyrics, assets and files stay
  inside that book's campaign.
- The approval card shows the **batch total**, computed from Skill 74
  `price` for every book in the list, plus the 20% retake allowance.
- One Kanban card per ad and one parent card per batch.

## 4. Price rules on the card

1. **Every number on the card comes from Skill 74 `price`** - video model,
   both shapes, lip-sync close-ups, voice packs, clips and the batch total.
   The card never computes a rate itself and never reads a table from this
   repository.
2. `preflight --model ID --units N` runs before approval; a shortfall is
   shown on the card and no paid call starts.
3. Approval records the spending limit: the chosen price **plus the 20%
   retake allowance**, in USD, with the KIE credit equivalent. No paid call
   happens before that record exists.
4. If a live rate cannot be read, the card says the price is unavailable and
   does not start paid work.
5. On resume the card shows only what changed, plus the next stage.

## 5. Skill 74 mode gate

Skill 74 ships in shadow mode, where `run` and `submit` refuse paid jobs.
Read the mode with `health` at preflight. In shadow or off mode the factory
stops **before** the card's approval, tells the client plainly that media
generation is not switched on for this box, and escalates to the operator. It
never falls back to a private KIE client, and a `skipped` result is never
treated as success.

## 6. What the card stores

On the parent campaign: every selection above, the approved price, the
recorded ceiling, and the listed lip-sync lines. The Command Center keeps one
deliverable per ad and one Kanban card per ad and per batch; the department
map's lead role for this skill is `vsl-video-sales-letter-specialist`.
