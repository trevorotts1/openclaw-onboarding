# Client price menu — drama song ad factory (version 2)

Snapshot for humans, seen 2026-10-07. KIE list prices, 1 credit = $0.005,
before any top-up bonus.

**This document is a snapshot, not an authority.** The choice card never
reads it. Every figure the client sees is produced live by Skill 74
(`74-kie-live-adapter`) through `price --model <id> --units <n>`, refreshed
before each run and daily. The code never hard-codes a rate from this file.
If a live rate cannot be read, the card says the price is unavailable and
paid work does not start.

## 1. What this menu is

Your ad is a sung story set to music, cut from many short silent video shots.
You choose which video model makes the shots, at what picture quality, and
whether you want the vertical (9:16) version, the widescreen (16:9) version,
or both. Every figure below is the total cost of the finished media: video,
the song, and one still keyframe image per shot. The "+20% retakes" column is
what you would add if one shot in five has to be regenerated.

## 2. Price tables

How to read them: "One shape" = 9:16 only or 16:9 only. "Both shapes" = 9:16
and 16:9 (video and keyframes doubled, one song shared). "+20% retakes" =
extra money to budget on top of the one-shape price (20% of its video plus
keyframes). CHEAPEST and PREMIUM mark the lowest and highest one-shape price
in each table.

### 60 seconds

| Model | Resolution | Shots per shape | One shape | Both shapes | +20% retakes (one shape) |
|---|---|---|---|---|---|
| Veo 3.1 Fast | 720p | 8 | $2.62 | $5.18 | +$0.51 |
| Veo 3.1 Fast | 1080p | 8 | $2.82 | $5.58 | +$0.55 |
| Veo 3.1 Quality | 720p | 8 | $10.22 | $20.38 | +$2.03 |
| Veo 3.1 Quality | 1080p | 8 | $10.42 | $20.78 | +$2.07 |
| HappyHorse 1.1 | 720p | 4 | $6.89 | $13.72 | +$1.37 |
| HappyHorse 1.1 | 1080p | 4 | $8.84 | $17.62 | +$1.76 |
| MiniMax H3 **(CHEAPEST)** | 768P (no 720p) | 4 | $2.54 | $5.02 | +$0.50 |
| MiniMax H3 | 2K (no 1080p) | 4 | $4.04 | $8.02 | +$0.80 |
| Kling 3.0 Omni | 720p | 4 | $4.34 | $8.62 | +$0.86 |
| Kling 3.0 Omni | 1080p | 4 | $5.54 | $11.02 | +$1.10 |
| Gemini Omni Flash 1.1 | 720p and 1080p (same price) | 6 | $3.96 | $7.86 | +$0.78 |
| Seedance 2.5 | 720p | 4 | $19.04 | $38.02 | +$3.80 |
| Seedance 2.5 **(PREMIUM)** | 1080p | 4 | $47.54 | $95.02 | +$9.50 |
| Wan 3.0 | 720p | 4 | $4.94 | $9.82 | +$0.98 |
| Wan 3.0 | 1080p | 4 | $9.74 | $19.42 | +$1.94 |
| Kling 3.0 | 720p (std) | 4 | $4.34 | $8.62 | +$0.86 |
| Kling 3.0 | 1080p (pro) | 4 | $5.54 | $11.02 | +$1.10 |
| Seedance 2.0 Mini | 720p (no 1080p) | 4 | $2.60 | $5.14 | +$0.51 |

### 90 seconds

| Model | Resolution | Shots per shape | One shape | Both shapes | +20% retakes (one shape) |
|---|---|---|---|---|---|
| Veo 3.1 Fast | 720p | 12 | $3.90 | $7.74 | +$0.77 |
| Veo 3.1 Fast | 1080p | 12 | $4.20 | $8.34 | +$0.83 |
| Veo 3.1 Quality | 720p | 12 | $15.30 | $30.54 | +$3.05 |
| Veo 3.1 Quality | 1080p | 12 | $15.60 | $31.14 | +$3.11 |
| HappyHorse 1.1 | 720p | 6 | $10.30 | $20.55 | +$2.05 |
| HappyHorse 1.1 | 1080p | 6 | $13.23 | $26.40 | +$2.63 |
| MiniMax H3 **(CHEAPEST)** | 768P (no 720p) | 6 | $3.78 | $7.50 | +$0.74 |
| MiniMax H3 | 2K (no 1080p) | 6 | $6.03 | $12.00 | +$1.19 |
| Kling 3.0 Omni | 720p | 6 | $6.48 | $12.90 | +$1.28 |
| Kling 3.0 Omni | 1080p | 6 | $8.28 | $16.50 | +$1.64 |
| Gemini Omni Flash 1.1 | 720p and 1080p (same price) | 9 | $5.91 | $11.76 | +$1.17 |
| Seedance 2.5 | 720p | 6 | $28.53 | $57.00 | +$5.69 |
| Seedance 2.5 **(PREMIUM)** | 1080p | 6 | $71.28 | $142.50 | +$14.24 |
| Wan 3.0 | 720p | 6 | $7.38 | $14.70 | +$1.46 |
| Wan 3.0 | 1080p | 6 | $14.58 | $29.10 | +$2.90 |
| Kling 3.0 | 720p (std) | 6 | $6.48 | $12.90 | +$1.28 |
| Kling 3.0 | 1080p (pro) | 6 | $8.28 | $16.50 | +$1.64 |
| Seedance 2.0 Mini | 720p (no 1080p) | 6 | $3.87 | $7.68 | +$0.76 |

### 2 minutes

New (F15, owner order 2026-10-08): computed with the same published rates
and the same formula as every table above - per-second models at 120 s x
their "Rates used" rate, Veo at ceil(120/8) = 15 clips, Gemini Omni Flash at
ceil(120/10) = 12 clips, one Imagen 4 Fast keyframe ($0.02) per shot, one
Suno V6 generation ($0.06) shared - so the same rate that prices the 90 s
rows prices these; the live card still reads Skill 74.

| Model | Resolution | Shots per shape | One shape | Both shapes | +20% retakes (one shape) |
|---|---|---|---|---|---|
| Veo 3.1 Fast | 720p | 15 | $4.86 | $9.66 | +$0.96 |
| Veo 3.1 Fast | 1080p | 15 | $5.23 | $10.41 | +$1.03 |
| Veo 3.1 Quality | 720p | 15 | $19.11 | $38.16 | +$3.81 |
| Veo 3.1 Quality | 1080p | 15 | $19.48 | $38.91 | +$3.89 |
| HappyHorse 1.1 | 720p | 8 | $13.72 | $27.38 | +$2.73 |
| HappyHorse 1.1 | 1080p | 8 | $17.62 | $35.18 | +$3.51 |
| MiniMax H3 **(CHEAPEST)** | 768P (no 720p) | 8 | $5.02 | $9.98 | +$0.99 |
| MiniMax H3 | 2K (no 1080p) | 8 | $8.02 | $15.98 | +$1.59 |
| Kling 3.0 Omni | 720p | 8 | $8.62 | $17.18 | +$1.71 |
| Kling 3.0 Omni | 1080p | 8 | $11.02 | $21.98 | +$2.19 |
| Gemini Omni Flash 1.1 | 720p and 1080p (same price) | 12 | $7.86 | $15.66 | +$1.56 |
| Seedance 2.5 | 720p | 8 | $38.02 | $75.98 | +$7.59 |
| Seedance 2.5 **(PREMIUM)** | 1080p | 8 | $95.02 | $189.98 | +$18.99 |
| Wan 3.0 | 720p | 8 | $9.82 | $19.58 | +$1.95 |
| Wan 3.0 | 1080p | 8 | $19.42 | $38.78 | +$3.87 |
| Kling 3.0 | 720p (std) | 8 | $8.62 | $17.18 | +$1.71 |
| Kling 3.0 | 1080p (pro) | 8 | $11.02 | $21.98 | +$2.19 |
| Seedance 2.0 Mini | 720p (no 1080p) | 8 | $5.14 | $10.22 | +$1.02 |

### 3 minutes

| Model | Resolution | Shots per shape | One shape | Both shapes | +20% retakes (one shape) |
|---|---|---|---|---|---|
| Veo 3.1 Fast **(CHEAPEST)** | 720p | 23 | $7.42 | $14.78 | +$1.47 |
| Veo 3.1 Fast | 1080p | 23 | $8.00 | $15.93 | +$1.59 |
| Veo 3.1 Quality | 720p | 23 | $29.27 | $58.48 | +$5.84 |
| Veo 3.1 Quality | 1080p | 23 | $29.84 | $59.63 | +$5.96 |
| HappyHorse 1.1 | 720p | 12 | $20.55 | $41.04 | +$4.10 |
| HappyHorse 1.1 | 1080p | 12 | $26.40 | $52.74 | +$5.27 |
| MiniMax H3 | 768P (no 720p) | 12 | $7.50 | $14.94 | +$1.49 |
| MiniMax H3 | 2K (no 1080p) | 12 | $12.00 | $23.94 | +$2.39 |
| Kling 3.0 Omni | 720p | 12 | $12.90 | $25.74 | +$2.57 |
| Kling 3.0 Omni | 1080p | 12 | $16.50 | $32.94 | +$3.29 |
| Gemini Omni Flash 1.1 | 720p and 1080p (same price) | 18 | $11.76 | $23.46 | +$2.34 |
| Seedance 2.5 | 720p | 12 | $57.00 | $113.94 | +$11.39 |
| Seedance 2.5 **(PREMIUM)** | 1080p | 12 | $142.50 | $284.94 | +$28.49 |
| Wan 3.0 | 720p | 12 | $14.70 | $29.34 | +$2.93 |
| Wan 3.0 | 1080p | 12 | $29.10 | $58.14 | +$5.81 |
| Kling 3.0 | 720p (std) | 12 | $12.90 | $25.74 | +$2.57 |
| Kling 3.0 | 1080p (pro) | 12 | $16.50 | $32.94 | +$3.29 |
| Seedance 2.0 Mini | 720p (no 1080p) | 12 | $7.68 | $15.30 | +$1.52 |

### 5 minutes

| Model | Resolution | Shots per shape | One shape | Both shapes | +20% retakes (one shape) |
|---|---|---|---|---|---|
| Veo 3.1 Fast **(CHEAPEST)** | 720p | 38 | $12.22 | $24.38 | +$2.43 |
| Veo 3.1 Fast | 1080p | 38 | $13.17 | $26.28 | +$2.62 |
| Veo 3.1 Quality | 720p | 38 | $48.32 | $96.58 | +$9.65 |
| Veo 3.1 Quality | 1080p | 38 | $49.27 | $98.48 | +$9.84 |
| HappyHorse 1.1 | 720p | 20 | $34.21 | $68.36 | +$6.83 |
| HappyHorse 1.1 | 1080p | 20 | $43.96 | $87.86 | +$8.78 |
| MiniMax H3 | 768P (no 720p) | 20 | $12.46 | $24.86 | +$2.48 |
| MiniMax H3 | 2K (no 1080p) | 20 | $19.96 | $39.86 | +$3.98 |
| Kling 3.0 Omni | 720p | 20 | $21.46 | $42.86 | +$4.28 |
| Kling 3.0 Omni | 1080p | 20 | $27.46 | $54.86 | +$5.48 |
| Gemini Omni Flash 1.1 | 720p and 1080p (same price) | 30 | $19.56 | $39.06 | +$3.90 |
| Seedance 2.5 | 720p | 20 | $94.96 | $189.86 | +$18.98 |
| Seedance 2.5 **(PREMIUM)** | 1080p | 20 | $237.46 | $474.86 | +$47.48 |
| Wan 3.0 | 720p | 20 | $24.46 | $48.86 | +$4.88 |
| Wan 3.0 | 1080p | 20 | $48.46 | $96.86 | +$9.68 |
| Kling 3.0 | 720p (std) | 20 | $21.46 | $42.86 | +$4.28 |
| Kling 3.0 | 1080p (pro) | 20 | $27.46 | $54.86 | +$5.48 |
| Seedance 2.0 Mini | 720p (no 1080p) | 20 | $12.76 | $25.46 | +$2.54 |

### 10 minutes (long version)

New in version 2 (decision 32). Computed with the same published rates and
the same formula as every table above, so the columns line up; the live card
still reads Skill 74. Shot counts follow the same rule: 15-second shots for
the per-second models, 8-second clips for Veo, 10-second clips for Gemini.

| Model | Resolution | Shots per shape | One shape | Both shapes | +20% retakes (one shape) |
|---|---|---|---|---|---|
| Veo 3.1 Fast **(CHEAPEST)** | 720p | 75 | $24.06 | $48.06 | +$4.80 |
| Veo 3.1 Fast | 1080p | 75 | $25.94 | $51.81 | +$5.18 |
| Veo 3.1 Quality | 720p | 75 | $95.31 | $190.56 | +$19.05 |
| Veo 3.1 Quality | 1080p | 75 | $97.19 | $194.31 | +$19.43 |
| HappyHorse 1.1 | 720p | 40 | $68.36 | $136.66 | +$13.66 |
| HappyHorse 1.1 | 1080p | 40 | $87.86 | $175.66 | +$17.56 |
| MiniMax H3 | 768P (no 720p) | 40 | $24.86 | $49.66 | +$4.96 |
| MiniMax H3 | 2K (no 1080p) | 40 | $39.86 | $79.66 | +$7.96 |
| Kling 3.0 Omni | 720p | 40 | $42.86 | $85.66 | +$8.56 |
| Kling 3.0 Omni | 1080p | 40 | $54.86 | $109.66 | +$10.96 |
| Gemini Omni Flash 1.1 | 720p and 1080p (same price) | 60 | $39.06 | $78.06 | +$7.80 |
| Seedance 2.5 | 720p | 40 | $189.86 | $379.66 | +$37.96 |
| Seedance 2.5 **(PREMIUM)** | 1080p | 40 | $474.86 | $949.66 | +$94.96 |
| Wan 3.0 | 720p | 40 | $48.86 | $97.66 | +$9.76 |
| Wan 3.0 | 1080p | 40 | $96.86 | $193.66 | +$19.36 |
| Kling 3.0 | 720p (std) | 40 | $42.86 | $85.66 | +$8.56 |
| Kling 3.0 | 1080p (pro) | 40 | $54.86 | $109.66 | +$10.96 |
| Seedance 2.0 Mini | 720p (no 1080p) | 40 | $25.46 | $50.86 | +$5.08 |

### Rates used (silent, no audio)

| Model (KIE id) | Low-res rate | High-res rate | Max clip | 9:16 and 16:9 native |
|---|---|---|---|---|
| Veo 3.1 Fast (veo3_fast; market id veo-3-1) | 720p $0.30 per clip (60 cr) | 1080p $0.325 per clip (65 cr) | 8 s | Yes, both |
| Veo 3.1 Quality (veo3; market id veo-3-1) | 720p $1.25 per clip (250 cr) | 1080p $1.275 per clip (255 cr) | 8 s | Yes, both |
| HappyHorse 1.1 (happyhorse-1-1/*) | 720p $0.1125/s | 1080p $0.145/s | 15 s (3-15) | Yes, both |
| MiniMax H3 (minimax-h3/*) | 768P $0.04/s (720p not offered) | 2K $0.065/s (1080p not offered) | 15 s (4-15) | Yes, both |
| Kling 3.0 Omni (kling-3.0-omni/*) | 720p $0.07/s | 1080p $0.09/s | 15 s (3-15) | Yes, both |
| Gemini Omni Flash 1.1 (google/gemini-omni-flash-1-1) | 720p $0.63 per 10 s clip (126 cr) | 1080p same $0.63 | 10 s (4, 6, 8 or 10) | Yes, both |
| Seedance 2.5 (bytedance/seedance-2-5) | 720p $0.315/s | 1080p $0.79/s | 30 s (4-30) | Yes, both |
| Wan 3.0 (wan/3-0-video) | 720p $0.08/s | 1080p $0.16/s | 30 s (2-30) | Yes, both |
| Kling 3.0 (kling-3.0/video; std=720p, pro=1080p) | 720p $0.07/s | 1080p $0.09/s | 15 s (3-15) | Yes, both |
| Seedance 2.0 Mini (bytedance/seedance-2-mini) | 720p $0.041/s | 1080p not offered (480p/720p only) | 15 s (4-15) | Yes, both |

## 3. Lip-sync close-ups

Lip-sync runs on 6 to 8 short clips of 4 to 6 seconds per 60 s ad, 30 to 40
seconds of footage per shape (choice card section 3.6), doubled 2026-10-08:
more pieces, not longer ones, scaled linearly with ad length, no clip over 6
seconds. Enforced at the final edit QC gate (Part E E6): at least 6 lip-sync
clips and 30 s of lip-sync in a 60 s ad (never fewer than 3 clips), scaling
linearly (50% of runtime) for longer or shorter ads.

Every clip is its own paid job, so the lip-sync line is about twice what it was.
Per-ad cap math: `lipsync_clips.check_budget(total_s, usd_per_s, remaining_usd,
shapes, attempts)` multiplies seconds x the Skill 74 rate x shapes x attempts (attempts defaults to 2, the
two-try rule: worst case is double the snapshot below) and
REFUSES loudly (`LIPSYNC_OVER_CAP`, `LIPSYNC_PRICE_UNKNOWN`, `LIPSYNC_CAP_UNKNOWN`)
rather than trimming the plan or running past the cap. The card also refuses a
plan with a clip over 6 s (`LIPSYNC_CLIP_OVER_CAP`).

| Order | Model (KIE id) | Rate | Snapshot for one ad, one shape |
|---|---|---|---|
| 1 (first) | Kling avatar (`kling/ai-avatar-standard`) | 8 cr/s = $0.04/s at 720P; 16 cr/s = $0.08/s at 1080P; up to 15 s per generation | one 6-second clip ≈ **$0.24** at 720P; a 60 s ad's 30-40 s (6-8 clips) ≈ **$1.20-$1.60** at 720P (double at 1080P) |
| manual backup only, not on by default | InfiniTalk (`infinitalk/from-audio`) | 12 cr/s = $0.06/s at 720P; 3 cr/s = $0.015/s at 480P; up to 15 s per generation | a 60 s ad's 30-40 s ≈ **$1.80-$2.40** at 720P |
| dropped | Volcengine | not offered | **Dropped** (decision 33) - it barely moves a closed mouth, so it carries no price and never appears on the card |

The card's own figure comes from `Skill 74 price --model
kling/ai-avatar-standard --units <seconds>`; the table above is the snapshot
that explains it. Lip-sync runs on both shapes when both shapes are ordered.

## 4. Voice packs and Velvet Voiceover

- **Per-character Suno voice packs:** no two characters share a voice. Packs
  are built from Suno generations through Skill 68; the registry price for
  one music generation is 12 credits (**$0.06**) per request. How many
  generations a pack needs is decided by the music director, so the card
  never predicts it - it asks Skill 74 `price`.
- **Velvet Voiceover** adds Google text-to-speech for the spoken lines, one
  distinct voice per character. It is a plain voiceover with the song
  underneath and **no echo effect**. The added cost is quoted on the card
  from Skill 74 `price`; it is the only line on the card that is not a KIE
  media call, and it is shown separately so the client can see it.
- **All Suno** (the default) adds nothing.

## 5. Clips

Automatic 60-second and 90-second clips come with the **3-minute, 5-minute
and 10-minute** lengths (`core/clip_cutdown`).

- Cutting a clip is **free**: an FFmpeg edit of the finished video, no new
  AI media, so the price of the ad already includes the clips.
- The card shows $0 for clips and says "included in the price".
- Long-version shape choice is separate: both shapes roughly double the
  video cost; a centre-crop to 9:16 is free but may cut off faces.

## 6. Batch total (book campaigns)

Batch mode prices every book in the list the same way as a single ad, then
sums them:

```text
batch total = sum over books of (Skill 74 price for that book's choices)
              + 20% retake allowance
```

One choice card covers look, music, voice, length and shape for the whole
batch; one ad per book; each book keeps its own campaign folder, receipt,
spend-ledger run and Command Center deliverable. The card shows the batch
total before approval. Books and authors are never mixed.

## 7. Which to pick

- **Budget.** Seedance 2.0 Mini 720p, MiniMax H3 768P, or Veo 3.1 Fast 720p.
  A 90-second single-shape ad is about $3.80 to $3.90; a 3-minute ad is $7.40
  to $7.70; a 10-minute ad is $24.06 to $25.46. The picture is lower
  resolution and quality has not been compared side by side for sung drama,
  so equal quality is not promised. Veo Fast is cheapest at 3, 5 and 10
  minutes because its clips are priced per clip, not per second.
- **Balanced.** Kling 3.0 or Kling 3.0 Omni at 1080p ($0.09/s), Wan 3.0 at
  720p, or Gemini Omni Flash 1.1. A 90-second single-shape ad is about $5.90
  to $8.30; a 3-minute ad is $11.80 to $16.50.
- **Premium.** Veo 3.1 Quality or Seedance 2.5 at 1080p ($47.54 for 60
  seconds, $237.46 for 5 minutes, $474.86 for 10 minutes, one shape).
  Seedance 2.5 at 1080p costs about 4 to 5 times Veo Quality per second of
  finished video; choose it only when the client specifically asks.
- Whichever tier: do both shapes only when the client needs both, and treat
  the retake column as the realistic spare budget.

## 8. Sources and assumptions

### Sources (all prices seen 2026-10-07 unless stated)

- Primary: the Skill 74 model registry snapshot
  (`74-kie-live-adapter/references/kie-model-registry.json`,
  `generated_at` 2026-10-06T04:28:00Z, field `pricing.raw`).
- Credit proven: a reconciled build receipt showed Wan 3.0 1080p, 21 s =
  672 credits = 336 cents, so 1 credit = $0.005.
- Live cross-checks that matched the registry: kie.ai/veo-3-1,
  kie.ai/happyhorse-1-1, kie.ai/minimax-h3, kie.ai/kling-o3,
  kie.ai/gemini-omni-flash-1-1, kie.ai/seedance-2-5, kie.ai/wan-3-0,
  kie.ai/kling-3-0, kie.ai/seedance-2-mini.
- Duration and aspect limits from docs.kie.ai: seedance-2-5 (4-30 s),
  seedance-2 (4-15 s), seedance-2-mini (4-15 s), wan-3-0-video (2-30 s),
  kling/v3-omni-text-to-video (3-15 s), kling-3-0 (up to 15 s, std=720p,
  pro=1080p), veo-3-video (4, 6 or 8 s; 16:9 and 9:16), and the registry
  `input_fields`.
- Lip-sync: kie.ai registry entries for `kling/ai-avatar-standard`,
  `kling/ai-avatar-pro` and `infinitalk/from-audio` (`pricing.raw`).
- Music: ai-music-api/generate = 12 credits ($0.06) per request.
  docs.kie.ai/suno-api (2026-10-07) states V6, V6_MINI and V6_WILD accept
  duration 10-360 s; V4_5 and V5 up to 8 min.
- Keyframes: google/imagen4-fast = 4 credits ($0.02) per image.

### Assumptions

- Shot length = the model's maximum clip length, capped at 15 s (Veo 8 s,
  Gemini Omni 10 s, everything else 15 s). Veo needs ceil(length / 8) clips:
  8 for 60 s, 12 for 90 s, 23 for 3 min, 38 for 5 min, 75 for 10 min.
- One candidate per shot; FFmpeg assembly $0; KIE list prices, no top-up
  bonus (a bonus would lower every figure about 10%).
- Per-second models: footage seconds x rate. Per-clip models: clips x clip
  price.
- Music: one Suno V6 generate ($0.06) for every length, because V6 produces
  up to 360 s in one generation. Music is shared by both shapes.
- Keyframes: one Imagen 4 Fast image ($0.02) per shot per shape.
- Both shapes = video x2 + keyframes x2 + music once.
- Retake allowance = 20% of (video + keyframes) for one shape; not included
  in the "One shape" or "Both shapes" figures. For both shapes, double it.
- Silent rates only; the shots carry no audio.
- Seedance 2.0 Mini 1080p and MiniMax H3 720p/1080p do not exist: Mini
  offers 480p/720p; H3 offers 768P and 2K. Both are shown with their
  nearest tiers.
- Gemini Omni Flash 1.1 is billed per clip by length (126 credits for 10 s),
  so 720p and 1080p cost the same and one row covers both.

### Undetermined

- Whether enabling audio raises the published per-second rate for Seedance,
  Wan and Veo; the surcharge is not published and is not needed because
  shots are silent.
- Quality equivalence between the Budget tier and the dearer models for sung
  drama: none has been measured, so Budget is cheaper, not proven equal.
- Live per-model aspect-ratio proof for image-to-video modes rests on the
  documented enums; the aspect normally comes from the keyframe shape.
- Prices here move. Every one of them is re-read from Skill 74 before the
  card is shown and before each run.
