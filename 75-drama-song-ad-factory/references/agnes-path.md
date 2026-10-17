# The Agnes path (optional) — operator and runtime reference

An optional second picture/clip provider for clients who pay for an Agnes AI plan
(Starter, Plus or Pro). Agnes makes the **still pictures** and the **motion video
segments** on the client's own subscription; the **song stays Suno through KIE** and
the **lip-sync close-ups stay KIE Kling**. Nothing else about a run changes.

Sources: the Agnes part of the program's SPEC, the vendor research read on
2026-10-13, the 2026-10-13 trial measurements, and Trevor's DECISION lines. Those
are build-program documents kept with the plan, not files in this skill folder.
Vendor facts that could not be found are recorded there as UNDETERMINED and are
never restated here as fact.

**Reading the paths below.** A path written relative to this folder (for example
`references/client-messages.md`, `PREREQS.json`) is a file in this tree. Anything
under `control/`, `work/` or a client data folder is a **record inside a run folder**
or the platform's own state path, not a file in this tree. The Agnes door, quota
tracker, planner, transition and progress modules ship with the Agnes core batch in
the same release group; this reference describes the behaviour they implement and
names no module path. The Agnes refusal and waiting codes named below
(`AGNES_KEY_MISSING`, `AGNES_KEY_REFUSED`, `AGNES_NOT_CHOSEN`,
`AGNES_QUOTA_EXHAUSTED`, `AGNES_QUEUE_FULL`, `AGNES_PROMPT_OVER_BAND`,
`AGNES_TASK_FAILED`, `OCR_UNAVAILABLE`, `TEXT_OVERLAID`, `agnes-video-running`,
`agnes-quota-next-day`) ship with that batch too. Every other identifier named in this
document already exists in this tree.

---

## 1. Inert until wired

A run behaves exactly as it does today unless it carries the Agnes answer:

- `agnes.answer == "yes"` in the run's `control/card-receipt.json` (written by the
  card), and
- `control/method.json` for the Drama-to-Demand Method rows.

No Agnes code path runs on a run without them. There is no detection, no default-on
and no silent switch of provider.

## 2. Who is asked, and the remembered answer

- The **AGNES** question is asked after VIDEO STYLE: a paid Agnes plan makes this
  video's pictures and clips at no extra cost inside the daily quota; option 1 "use
  my Agnes plan", option 2 "use the studio's standard models". The exact client
  wording ships with the card.
- The answer is remembered in the client's own data folder (the folder the character
  library already uses) as `agnes.json` — `{"subscriber": "yes"|"no", "answered_at":
  "<UTC>"}`. **Never a key, never a plan screenshot.**
- A remembered **no** hides the question on later cards (one recap line; reply
  `agnes` at the recap to change it). A remembered **yes** still asks, with Yes
  marked RECOMMENDED — the client may not want Agnes for this video.
- 7- and 10-minute episodes are KIE-only, so the AGNES question is not shown for them.

## 3. The key — presence only

- Looked up in this order: env `AGNES_AI_API_KEY` (OpenClaw boxes), then
  `AGNES_API_KEY`, then the `AGNES_API_KEY=` line of `<Documents>/API docs.md`.
  A placeholder value counts as absent.
- **Presence only.** The value is held in memory, never printed, logged, written to a
  receipt, a ledger or a test output, and never compared with anything on screen.
- Client answered Yes but no key is found → the fallback question with reason
  `AGNES_KEY_MISSING`. 401/403 → `AGNES_KEY_REFUSED` (a dead key is never worked
  around by inventing one).

## 4. What Agnes makes

| Stage | On the Agnes path |
|---|---|
| research, creative-strategy, script-lyrics | unchanged (model work) |
| music | **unchanged — Suno via KIE** |
| continuity-bible | unchanged; the character reference set is Agnes Image |
| storyboard | unchanged, plus the 10-second segment plan |
| image-keyframes | Agnes Image, 2K, 9:16, no words in the picture by default |
| storyboard approval | unchanged (cards + stills) |
| video-generation (motion) | Agnes video, keyframe mode, **fixed 10-second clips** |
| video-generation (lip-sync) | **unchanged — KIE Kling**; the close-up still may be Agnes |
| qc-retakes | unchanged rule (≤ 2 per unit); an Agnes retake draws from quota |
| assembly, clips, final-qc, delivery | unchanged, plus clip conform and the frame-text gate |

Never in scope: Agnes music, Agnes lip-sync, the paid non-flash video model, and the
retired video model.

Agnes is **not** routed through the KIE transport and never opens a second paid door:
there is no dollar spend inside the daily quota, so there is no spend ceiling to
record for an Agnes job — but every Agnes job still gets a ledger row at cost 0, so
receipts, prompt compliance and resume behave exactly as they do for a paid job.

## 5. Clip math and the length cap

- The delivered timeline is cut into **10-second segments**:
  `segments = ceil(delivered_length / 10)`, each segment one Agnes clip of exactly
  `seconds "10"` (a string; any other value is refused locally, never sent).
  60 s → 6 clips, 90 s → 9, 3 min → 18, 5 min → 30.
- **Agnes length cap (Trevor 2026-10-13): 5 minutes.** 7- and 10-minute episodes are
  KIE-only; no run is ever split across days.
- One still per segment is made first (Agnes Image 2K), approved with the storyboard,
  and used as that segment's first frame.
- Lip-sync close-ups (KIE) are cut in over parts of a segment at their measured word
  times; the Agnes clip still covers its full 10 seconds.
- Clips are joined with the existing assembler. Each Agnes clip carries ~0.125 s more
  than 10 s, which feeds the 0.4 s crossfade; any shortfall is a hold, never a
  stretch, and no slow motion above 1.15x (`SLOWMO_OVER_LIMIT`).

## 6. Quota — 500 video-seconds and 4,000 images per day

- Limits: **500 video seconds per day** (the video model on every plan) and
  **4,000 images per day**, reset **00:00 UTC**. Keys of the same type share one pool;
  more keys do not add quota.
- The quota tracker is a **planner, not a permission**: one SQLite ledger per key pool
  on the platform's persistent path. Before the video stage it asks whether
  `clips × 10 × 1.2` fits today.
- Fits → run now. Does not fit → the run waits **as a whole** for the next 00:00 UTC
  reset (`waiting`, reason `agnes-quota-next-day`, exit 2). **No run is split across
  days.**
- A vendor **402** always wins the local count (`AGNES_QUOTA_EXHAUSTED`): other apps
  on the same account share the pool.
- Time budget: about **11-13 minutes per 10-second clip** measured, which is why the
  video stage runs as a background job.

## 7. Pacing, retries and refusal codes (measured in trial A)

- **At most 2 video jobs in flight** per key pool, shared across lanes and processes.
  A third job at the same time was refused; it waits for a slot.
- **503 `video_queue_full`** = not created, not charged: back off 60 s, 120 s, then
  every 120 s and resubmit; never counted as submitted. After 30 minutes of continuous
  503 the run reports `AGNES_QUEUE_FULL` loudly and keeps waiting — **it never
  switches provider by itself.**
- **429** = rate limit: back off and resubmit, never dropped.
- **Poll no faster than every 15 seconds per job** (faster polling drew vendor
  "too many video status queries" errors).
- Images: at most 80 creates per rolling 60 s at 2K.
- **402** → `AGNES_QUOTA_EXHAUSTED`; **401/403** → `AGNES_KEY_REFUSED`; a task that
  `failed` twice for one segment → `AGNES_TASK_FAILED` with the vendor message; a job
  whose state is unknown after a timeout is **polled, never resubmitted**.
- Video prompt length is banded **5,000-20,000 characters**: under the band is a FLAG
  expanded from the segment's facts (never padded), over the band is refused as
  `AGNES_PROMPT_OVER_BAND` before anything is sent. The vendor's own cap is
  UNDETERMINED.

## 8. Words in pictures

- **Default: no words, letters, numbers, logos or signage anywhere in the image**, in
  every still prompt and every video prompt.
- A shot that truly needs a word may try to bake it into the still and is verified by
  OCR against the exact words (up to 3 free tries). If it does not bake cleanly the
  words are drawn on top at assembly and the receipt says `TEXT_OVERLAID` — a garbled
  word is never delivered.
- Agnes clips are read back with the frame-text gate on sampled frames: a no-text
  segment showing a readable word of 3+ letters fails `GARBLED_TEXT_FRAME` and that
  segment alone is regenerated (≤ 2).
- **tesseract missing → `OCR_UNAVAILABLE`, never a PASS.** Installing tesseract on
  client boxes is a Trevor decision; the skill declares it as an optional prerequisite
  with `when: agnes-path`.

## 9. Conform (measured, trial A)

| Item | Value |
|---|---|
| Stills | 2K 9:16 = 1472x2624 |
| Clips | 704x1280, **24 fps**, ~10.125 s, H.264, **with an AAC audio track** |
| Clip audio | **stripped** — the song is the only audio |
| Scale | cover-scale to the export size (never a blur fill) |
| fps | 24 → 30 by motion interpolation |
| 16:9 | renders 1280x704; both shapes cost quota, so shape is chosen once |

## 10. Background job and progress

A 5-minute video is about three hours of Agnes time, so the video stage runs as a
background job:

- After every state change the run writes `control/agnes-progress.json` with
  `clips_total`, `clips_done`, `in_flight`, `waiting_reason`, `next_continue_utc`,
  `eta_minutes_low`, `eta_minutes_high`, `updated_utc` (written atomically: temp file
  in the same folder, then rename). The ETA uses the measured 11-13 minutes per round
  of two.
- The studio page shows "Making your video clips: 12 of 30 done — about 1 h 40 min to
  go", or the waiting reason ("waiting for tomorrow's Agnes time, continues at 8:00
  pm").
- While the job runs, the stage command answers `waiting`, reason
  `agnes-video-running` (exit 2). A resumed session **never resubmits a job the ledger
  already knows**.

## 11. Fallback — one question, never silent

Triggers: 402 / today's quota will not cover the run, 401/403, key missing, a segment
failed twice, Agnes unreachable after backoff.

Action: stop the affected segments only and ask **one** question — wait (free,
continues after the next reset), make these N segments with the backup model now at
its quoted price, or stop here. Only the middle option dispatches through the paid
KIE door, and only after its own recorded ceiling. The run never switches provider on
its own and never hides the reason from the operator; the client sees the sentence
from `references/client-messages.md`, never the reason code.

## 12. Platforms

| Platform | Key | Remembered answer | Quota ledger (persistent) | OCR |
|---|---|---|---|---|
| OpenClaw Mac | `AGNES_AI_API_KEY` in the gateway env | client data folder | `~/.openclaw/drama-runs/.agnes-quota.sqlite3` | tesseract if installed |
| Hostinger Docker (user `node`, HOME `/data`) | container env | client data folder under `/data` | `/data/.openclaw/drama-runs/.agnes-quota.sqlite3` | UNDETERMINED |
| Contabo Docker (only `~/.openclaw` persists) | container env | client data folder under `~/.openclaw` | `/home/node/.openclaw/drama-runs/.agnes-quota.sqlite3` | UNDETERMINED |
| Claude Code / claude-nine | `AGNES_API_KEY`, else `API docs.md` | client data folder | `~/.drama-song-ad-factory/agnes-quota.sqlite3` | tesseract (operator Mac has it) |

Heavy local work (OCR, frame sampling, ffmpeg) goes through the existing load
governor, never a second scheduler.

## 13. Prerequisites

Declared in `PREREQS.json`, both optional and both gated `when: agnes-path`, so a box
that never uses Agnes reports nothing missing:

- `agnes-key` — the key is **present** (its value is never read into a report).
- `tool-tesseract` — the OCR binary the words-in-pictures check uses; absent it
  degrades to `OCR_UNAVAILABLE` (overlaid words), never to a pass.

## 14. What this path does not do

- No Agnes music, no Agnes lip-sync, no retired or non-flash paid video model, no 3K
  or 4K stills, no quota-read API (the vendor publishes none — UNDETERMINED).
- No dollar figure on an Agnes line: with Agnes chosen, the video and image lines read
  "included in your Agnes plan", plus one line reading "Agnes video time: about N of
  your 500 seconds today".
- No key, no plan screenshot, no client name and no chat id in any receipt, log or
  test output.
