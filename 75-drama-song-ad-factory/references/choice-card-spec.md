# Choice card specification — drama song ad factory (version 2)

Status: staged spec for both distributions (Skill 75 / 999 twin).
Source: `DRAMA_SONG_AD_FACTORY_V2_PLAN.md` sections 4.0, 4.1, 4.1.1, 4.2,
5.1-5.4, 6.1, 6.2, 6.3, 6.6, 6.7, 6.11, 6.12, 6.12.1, 6.13, 6.14, 6.15,
10.1, 10.3;
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

Plan 4.0 adds two steps around it: the approval card carries a short
story summary (a summary row is not rendered by the card writer yet), and
an optional lyric sign-off may follow approval before the song is
generated - the approved lyric sheet is the campaign's `lyrics` record
(`scripts/core/contracts/campaign-schema.json`, critical offer, claim,
product and CTA lines flagged), never free-hand text.

## 2. Card layout (normative)

```text
Your drama song ad
  Length:       60 seconds   (90 seconds, 2 minutes, 3 minutes, 5 minutes,
                10-minute long version)
  Shape:        9:16 vertical (16:9 widescreen, or both)
  Style:        Lifelike 3D (default) / 2D Hand-Painted / Sketch to Life
                / Canvas to Life / Canvas to 3D
  Music:        Soul Ballad (default) / R&B Flow / Soul Rise
  Product tie:  about 7s (12.5% of runtime) planned connecting the story to
                the product (10-15% target, never a cap; measured at delivery)
  Voice:        All Suno (default) / Velvet Voiceover (Google voiceover with
                the song underneath, no echo effect; not with Sketch to Life)
  Clips:        (5 and 10 minutes only) automatic 60- or 90-second clips
                for ads and Reels

                the song underneath, no echo effect)
  Clips:        (3, 5 and 10 minutes) automatic 60-second and 90-second
                clips to post on social media, included in the price
  Video model:  MiniMax H3, 768P  (RECOMMENDED)   [see all models and prices]
  Villain:      <name>, shown in N shots    (FU-U16; from the story plan)
  Price:        computed by Skill 74 `price`   (+ the 20% retake allowance)
  Includes:     all video shots, the song (song mp3 included), one image per shot
  Not included: the AI writing, planning and checking (runs on your own AI plan)
  [Approve]   [Change options]
```

The `Villain:` line reads
`Villain: <name>, shown in N shots` (from
`length_formula.plan_villain_doctrine`'s `card_line`) and sits on the card so
the client sees the story's villain before approving: the villain may be a
person or not a person, and the count is the villain's OWN shots. Source:
FU-U16 story doctrine, Trevor order 2026-10-08.

**Book shots block (FU-U11, open branch `unit/FU-U11`; refresh when it lands).**
For a book campaign both card faces append, under the Price row, a Book shots
approval block: a plain contract line, the exact prompts with character counts,
the page mode, the camera, the checks and the two-attempt cap. It holds
approvals and notices only; it never adds a choice, and a paid book video job
runs only against the plan hash the client approved.

Directive 24.3 note (owner order 2026-10-08): the card is one step with
four picks, so the three-question cap applies to the story questions only.

`[Approve]` is one click. `[Change options]` reopens the same card with the
previous selections kept.

## 2.2 One question at a time (Part I7, normative)

The intake is a conversation, not a form. One message per turn:

1. `Question 3 of 6 - VIDEO STYLE`, then a one-sentence reason the question
   matters, then the question.
2. Options as a numbered list, one per line, each with a short plain
   description; the RECOMMENDED option is marked and followed by "I recommend
   option N (name) because ...".
3. Wait for the answer. A number, "recommended", or (spend only) a dollar
   amount is accepted; anything else gets "Sorry, I did not catch that." and
   the same question again.
4. After the last answer, a recap ("Here is what you picked:") and a request
   for "yes". A line number reopens only that question, then returns to the
   recap.

Built by `intake_card.conversation(replies)` (stateless: replay the replies so
far), exposed as `factory.py card --step --reply ...`. Same code in claude-nine
and OpenClaw. Test: `choice_card/intake_card/test_intake_step_i7.py`.

## 2.3 Intro message (FU-INTRO-MESSAGE)

The run opens with the intro, then the questions. The intro is sent ONCE, as
its own message, at the start of a new interactive run, right before the first
question. Exact text (one constant: `scripts/core/choice_card/intake_card/intro.py`):

> Turn your offer into a video dramatization with music that people actually feel.
>
> Answer a few quick questions, and we handle the rest:
> - Write the story and script, with the song lyrics woven in
> - Create your characters (or bring back ones you've saved)
> - Compose an original song in the music style you choose
> - Create every image and build the storyboard, shot by shot
> - Make the video shots and lip-sync the singers
> - Edit it all together with captions and your call to action
>
> You approve the script, pick your favorite of 3 song versions, and sign off on the storyboard before any video is made. Longer videos also come with 60- and 90-second clips for social media.
>
> Let's start - just a few quick questions.

Rules: never repeated on later replies, resume or recap; never shown by the
batch, weekly-planner or CLI-only paths (they never message a client).
`factory.py card --step --run-state-file <run-state.json>` with no replies
prints the intro on the first call and records `intro_shown` in that file;
the next call prints question 1. A run state that already shows `intro_shown`
never prints it again. Without `--run-state-file` the card is unchanged.
Test: `choice_card/intake_card/test_intro_message.py`.

## 2.1 Intake question card layout (Part H9, normative)

The six intake questions (length, music style, video style, video model,
spend limit, storyboard approval) are built by
`scripts/core/choice_card/intake_card/intake_card.py` and nowhere else. Never
write them free hand and never carry them as one JSON string.

- Each question is its own block: `Question 1 of 6 - LENGTH`, then the plain
  question, then one numbered option per line (`1. 60 seconds - one short
  sentence. (RECOMMENDED)`). A blank line separates questions. The last line
  is the "how to answer" line.
- Plain text only: no Markdown, no HTML, no parse mode, so no sender can strip
  or escape the line breaks.
- Claude Code chat: run `factory.py card` and show its stdout as is (raw text,
  not the JSON envelope, whose escaped `\n` is what got flattened).
- Telegram through OpenClaw: run `factory.py card --format openclaw-json
  --target <chat id>` and execute each argv list without a shell, one message
  per list. The card is split between questions under 4000 characters; a
  `--format telegram-json` body is the exact Bot API `sendMessage` payload.
- The intake `question_message` uses the same layout (`format_questions`).

## 2.3 Fit stop card (FU-U4, normative)

When the client brings their own lines (concept mode, `brief.mode == "concept"`),
their lines are a contract: `brief.packet_lines` is required (missing is refused
with `PACKET_REQUIRED_IN_CONCEPT_MODE`), every line keeps its id, and no line is
cut unless the client approves that exact line id.

Before the card, code runs the free fit step (`choice_card/intake_card`
`fit_card(brief, packet_lines)`; CLI `factory.py card --fit --brief-file F
--packet-file P`). It prints one row per real music style at the client's length:
room for N words, the seconds the client's words need, the delivery split, and
fits or does not fit. When the chosen style does not fit, the card is a STOP card
(outcome `waiting`, exit code 2). When it fits, exit code 0 and nothing is cut.

Options are built only from registries; a test refuses any other id:

| Option | Registry |
|---|---|
| A longer ad | `music_styles.OFFERED_LENGTHS_S`, only lengths above the client's |
| A different music style | `music_styles.style_ids()` |
| Voice | All Suno (default) or Velvet Voiceover, from `voice_velvet_echo` |
| Fewer words | `words_fit`'s own `fewer_words` option, naming the exact line ids that would be cut, for the client to approve |

The same card states, as notices and never as options, every storyboard item the
skill will not make: sound effects (sfx stay off), an echo or reverb voice, a
length that is not offered, and any fps other than the 30 fps master.

### 2.1a Saved character question (FU-SAVED-CHARACTER-QUESTION, normative)

Shown only when the client's data folder holds saved characters; it is then
question 1 and the card has one more question. Built by
`character_library.saved_character_question`, never free hand. N is how many
characters the client has saved ("1 character", "2 characters"):

```
Question 1 of 7 - CHARACTER
Do you want to create a new character for this ad, or use one you've used before?
You have 2 characters saved with us.
1. Create a new character (recommended)
2. Use <Name> - <the saved description, up to 90 characters>
3. Use <Name> - ...
Reply with a number, or 'recommended'.
```

Reply 1 or "recommended" makes a new character; reply 2 and up loads that
saved character. The recap line reads `Character: new` or
`Character: <Name> (saved)`, and replying with its number re-asks the question.

When the client has NO saved characters nothing is asked. One plain line is
shown once, before the first question: "You don't have any saved characters
yet, so I'll create a new one for this ad and save it for next time."

Test: `character_library/test_saved_character_question.py`.

## 3. Field rules

### 3.1 Length

The intake card asks it as one full question with five numbered options, each
saying what the client gets (`core/choice_card/intake_card`, LENGTH):

```text
How long do you want your ad to be? The longer ads also come with short clips you can post on social media.
1. 60 seconds
2. 90 seconds
3. 3 minutes + 60s and 90s clips
4. 5 minutes + 60s and 90s clips
5. 10 minutes (the long version) + 60s and 90s clips
Reply with a number, or say "recommended".
```

The recap reads plainly: "Length: 3 minutes + 60s and 90s clips". The intake
card offers these five lengths; the style-defaults menu (`style_defaults`)
still carries the F15 2-minute value for the batch card.

Offered values, in order: **60 seconds, 90 seconds, 2 minutes (new, added
by F15, owner order 2026-10-08), 3 minutes, 5 minutes, 10-minute long
version** (decision 32). Default comes from the brief; if the brief gives
none, 60 seconds. A brief pre-fills the RECOMMENDED picks but never skips
the card (F15): the card still shows and the answers still record before
ANY paid job.

That list is `references/prompt-templates/length-classes.json`, keyed
`60, 90, 120, 180, 300, 600`, and it is the ONE length table: the card, the
shot planner (`shot_planner.class_check`), the lip-sync budget
(`lipsync_clips.class_check`) and `length_formula.class_check` all read it, and
`prompt_templates.length_class(L)` raises `PROMPT_LENGTH_CLASS_DRIFT` naming
each drifted field rather than let a stale number be read. The card shows the
six values above, in that order and no others.

Offered lengths (seconds): 60, 90, 120, 180, 300, 600. A test
(`scripts/core/prompt_templates/test_docs_u12.py`) fails if this line differs
from `music_styles.OFFERED_LENGTHS_S`.

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

Each row picks its render modes from `references/prompt-templates/looks/`:
`lifelike-3d.json`, `2d-hand-painted.json`, `sketch-to-life.json`,
`canvas-to-life.json`, `canvas-to-3d.json`. A look file names the modes it
uses, its beat-to-mode map, its switch rules and the modes that may be
lip-synced. The mode text itself exists once, in
`references/prompt-templates/modes/`; the style-bible modules keep the plans
and rules, and the template system owns the prompt text (design 2.4).


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
- **Sketch to Life is always All Suno** (owner 2026-10-07): with that look
  Velvet Voiceover is not selectable - `choice_card.stl_voice_guard`
  disables it on the card (default mode keeps it listed with an unavailable
  note, `mode="hide"` drops it from the line), refuses intake with
  `stl-voice-velvet-not-offered` and re-asks with All Suno preselected, and
  writing Velvet onto a Sketch to Life card raises `StlGuardError`. The
  other four looks offer both voices.
- Voice choice is verified against the picture, not trusted: `qc_voice_match`
  measures every line's pitch into the D17 gender band (male 85-155 Hz,
  female 165-255 Hz, inclusive), fails two same-gender characters closer than
  15 Hz apart, and fails any line whose on-screen face is neither the speaker
  nor a declared source (phone, laptop, speaker). A failed report exits 5,
  so assembly cannot start.
- Lip-sync rules in section 3.6 apply unchanged to both voice options.

### 3.6 Lip-sync lines

Owner decision D10, superseded 2026-10-07, plan 6.3 and decision 33.

Lip-sync is applied to **selected lines only** - doubled 2026-10-08, more
pieces and not longer ones: 6 to 8 clips of 4 to 6 seconds per 60 s ad (30 to
40 seconds), scaled linearly with the ad length, no clip over 6 seconds,
chosen by the factory and listed on the approval card. Enforced at the final
edit QC gate (Part E E6): at least 6 lip-sync clips and at least 30 s in a 60 s
ad (never fewer than 3 clips), scaling linearly (50% of runtime) for longer or
shorter ads. Clips go first on every sung hook, the spoken opener and the
spoken closing line, then on:

1. the most painful moment (`pain_peak` on the highest-scoring wound beat),
2. the product line,
3. the call to action,
4. the chorus hook, once, at its strongest occurrence.

Model order:

| Order | Model | KIE id | Notes |
|---|---|---|---|
| 1 (first) | Kling avatar | `kling/ai-avatar-standard` | A front-facing close-up image plus that character's own isolated line. 720P standard. |
| manual backup only | InfiniTalk | `infinitalk/from-audio` | Not on by default and never called automatically. A person may run it by hand. The 2-try keep-best rule keeps the best Kling take instead of switching model. |
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
  TODO(FU-U9): refresh this sentence when caption read-back off the rendered
  frames lands (no onboarding branch; 999 `unit/FU-U9` carries only the
  excerpt burn).

- Automatic clips come with the **3-minute, 5-minute and 10-minute** ads:
  one 60-second clip and one 90-second clip each (`core/clip_cutdown`,
  `clips_for`). On 60 s and 90 s the Clips row says "not offered".
- Cutting a clip is free: it is an FFmpeg edit of the finished video, so the
  price of the ad already includes the clips (the Clips row shows $0.00 and
  says "included in the price").
- `core/clip_cutdown.plan_clips` picks each clip from the timeline's lines:
  whole lines only, at most L-2 seconds (58 s and 88 s), never into the end
  card, opening on a line that puts the first sung hook inside the first 15%
  of the clip (`core/sung_hook` placement), carrying as many hooks as fit
  (two when the ad has two), preferring the window with the most story beats.
  No window that meets those rules fails closed (`CLIP_NO_WINDOW`).
  `build_argv` / `run_clips` cut it with a short fade-out; the captions are
  re-timed by `captions_offset_s`.
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
- A supplied image costs one or two extra keyframe images (about $0.02 to
  $0.04), no extra video shots (plan 4.1.1): it is restyled into the chosen
  look for the keyframes at the product reveal (beat 8) and the
  call-to-action ending, then animated image-to-video on the chosen model.
  The delivered product tie measures 10-15% of runtime - a target, never a
  cap - and shows as `PRODUCT_CONNECTION` on the delivery checklist.
- **Book campaigns (decision 34, plan 6.14):** intake asks the book title,
  the author, the cover image (used as the product image), the buy link, who
  the book is for, and the pain or transformation it delivers - still inside
  the three-question cap. The mentor/turning point of the story is the book;
  the call to action is to get the book. Intake also records the book's
  `language` (default `en`, left-to-right; folded into the offer sentence) and
  measures the cover's aspect from the file; it never invents one.
  A book clip is accepted only with a PASS `book_orientation` record (cover is
  the front, not mirrored, page turn in the right direction), and book shots
  carry no camera move. See SKILL.md "Book campaigns". The Book shots approval
  block on the card is the FU-U11 open branch.

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

### 3.11 Social Media Planner card (Skill 35, plan 6.15)

The planner does not rebuild this card; it asks the style block ONCE at
setup, with defaults pre-selected, and the Saturday prompt offers
"keep this style or change it?" (no answer means keep). Code:
`core/smp/initial_questions` (the block, wired to `stl_voice_guard` so the
Sketch to Life / Velvet pair is refused there too), `core/smp/saturday_prompt`.

- Defaults: look Lifelike 3D, music Soul Ballad, voice All Suno, length
  60 seconds (90 seconds optional - nothing longer is offered here; the long
  menu belongs to this card, not the planner).
- The weekly version is 9:16 and must END by **59.0 seconds**
  (`core/smp/length_routing`, hard cap - approved 60 s ads run 62-63 s and
  are refused by name).
- Routing: the 60-second option posts to all seven destinations; the
  90-second option posts only to Facebook Reels, Instagram Reels, TikTok and
  LinkedIn (an explicit allow-list, not a limit calculation). Stories carry
  a 15-second teaser cut only (`core/smp/stories_teaser`); Google Business
  Profile is refused until its limit is verified.
- Skill 74 active mode only: with KIE switched off the weekly step skips and
  says why in plain English (`core/smp/weekly_step.client_skip_reason`);
  never a fallback to a private KIE client.

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

The card promises **"song mp3 included"**: every delivered ad folder carries
the final song as `<Author> - <Title> - Song.mp3` (320 kbps, the exact song
used, full length) beside the captioned and clean-master mp4s. It is gated by
`delivery_checklist.check_song_mp3()` (present, duration within 0.1 s of the
ad audio, cross-correlation >= 0.95), and a finished book/batch campaign also
ships one client zip (`batch_zip.build_batch_zip`) with every ad's three files
and a README listing file, duration, resolution and banner link, so the client
can release the whole album.

## Suno song recipe (applies to every Suno music style above)

Every Suno music style (Soul Ballad, R&B Flow, Soul Rise, and any Suno style
added later) follows this recipe by default. It is what made the Kiesett and
LeAnne Dolce songs land. The code is `scripts/core/suno_recipe/`; every Suno
request goes through `suno_recipe.prepare()` and the `music_director` seam
refuses a raw Suno style that skipped it.

The four rules (recipe v2, replaces G12):

1. Spoken tags only in [Intro] and [Outro]; spoken is named once in the style
   text, and the style says the full band keeps playing under the spoken lines.
2. Sung lines are short (5-6 syllables aimed, 8 at most), rhymed, with
   hyphen-held vowels, after a wordless sung vocalise.
3. The first hook comes after the vocalise, never at 0 s; the hook is the
   client's own words, repeated by length (`core/sung_hook`).
4. Each take's singing is measured, not taken from its labels.

Word budget, section plan, hook repeats, spoken placement, instrumental breaks
and the extend plan for any length come from ONE function,
`core/length_formula.plan(L, spoken_share_pct)`; L=60 gives the measured
65-word recipe. Style text is 1000 characters or less. Negative tags are
`rap, rapping, choir, reverb, echo, band dropout, acapella sections,
talk-singing, monotone delivery` (never "spoken word"; the rap style drops the
rap pair). KIE (snake_case input, checked against the live docs): model V6, custom_mode
true, instrumental false, style_weight 0.75, weirdness_constraint 0.3, variety
0, vocal_gender per brief, duration 10-360 s. A longer song is a base take plus
extends: extend input is audio_id, continue_at (seconds, inside the source
take) and model (must equal the source take's model); extend has no duration
field, so the extended length is measured, never assumed. Trevor's dry close-vocal rule stays.
`core/song_dispatch` judges EVERY take (singcheck v2, spoken share band, sung
of voice, 6 s stretch, hook sung 2+, script words, length, music under speech,
clean ending, first sung), stops at the first pass, saves the stem and
timestamps of every take, regenerates whole tracks only, and refuses
openai-whisper.

The targets (Trevor, 2026-10-08, SPK001): speaking is **20-25% of the
runtime** by default (center 22.5; each ad can set its own, Black Successful
Women uses 15-20), and the lyric writer derives its spoken word budget from the ad's
own spoken target and the length formula's measured word rates (no fixed
word percent). Singing is measured against **voice time**, sung / (sung + spoken),
with a default target of **77.5%** (75-80): a music-only intro, gaps and the
end card never count against it. Both numbers use Trevor's band: within 5
points accept, over 5 up to 10 accept with a flag, over 10 redo. The only
hard reject is no sung stretch of at least 6 seconds. One constants set holds
the numbers: `scripts/core/spoken_share/spoken_share.py`.
**TODO(FU-U3):** per-style bands change how these two numbers are read -
`STYLE_TARGETS` judges each music style by its own delivery (R&B Flow's rap
share comes from the approved plan, never the spoken runtime target). Landed
in 999 (2.7.31, PR #120); open PR #1752 on onboarding - refresh this
paragraph when it lands there.

The only exemption is the Velvet Voiceover version (the spoken Google voice
over the song, id `velvet_voiceover`), which keeps its own flow. Almost
nobody asks for it. Every other style, including the All Suno voice default,
uses the recipe.

