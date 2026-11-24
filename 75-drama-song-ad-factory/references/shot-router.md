# The Shot Router and the Clip Sizer

Code: `scripts/core/shot_router/`. Stdlib only. No network, no spend, no file
written except the records a caller asks for.

The Shot Router gives every storyboard shot one route and an exact picture
list (section 3E). The Clip Sizer runs inside it and chooses each clip's
length (section 3I). Nothing is drawn or bought for a shot until the Shot
Router has routed it.

The run owner's story-clip model, picture provider and quality mode pass
through unchanged. The lip-sync model is not a choice: it is OmniHuman 2.0
(`omnihuman-2-0`) on every run.

## N-60: the four routes, the decision rules, the adjustments, the record

### The four routes (3E.1)

| Route | Use it for | Pictures to make | Video call |
|---|---|---|---|
| **ONE-PICTURE** (start frame) | Simple shots: one or two characters, exact framing, the ending can be carried by the prompt | 1 keyframe | The run's story-clip model, image-to-video, start picture = the keyframe (default `minimax-h3/image-to-video`) |
| **TWO-PICTURE** (start plus end) | A shot that must land on an exact ending: a walk to a door, a hand-off, a reveal, a match cut | 2 keyframes: start and end | Both in one request where the model takes both (3E.3); otherwise the end picture is the next clip's start picture and both clips go in the same burst |
| **NINE-PICTURE** | Busy or detailed scenes: the choir, a group of three or more, a wide room, a moving-camera energy shot | Up to 9 pictures from the lock, plus a composition keyframe | `minimax-h3/reference-to-video` |
| **LIP-SYNC** | A whole line or phrase someone mouths on camera | 1 lip-sync keyframe with 1 to 3 faces, large in frame | OmniHuman 2.0 (`omnihuman-2-0`): no prompt, watermark off, one audio piece carrying the whole line or phrase |
| **MERGED CLIP** (rule 2a) | 2 or 3 neighbouring short shots with the same place, people and camera idea | The pictures the shots already had | One clip of 5 to 10 seconds on the shots' own route, cut by the edit |
| **LONG TAKE** (rule 2b) | One continuous ordered action, or an instrumental stretch with no lyric cue and no writing, or a master wide | Up to 9 from the lock, plus a composition keyframe | 8 to 15 seconds on `minimax-h3/reference-to-video`, cut by the edit |

### The decision rules (3E.2, first rule that fits wins)

| # | If | Then |
|---|---|---|
| 1 | The line is a lip-sync role and the lip-sync plan chose that passage | LIP-SYNC; a choir line also gets a NINE-PICTURE wide shot placed just before it |
| 2 | 3 or more named people, a group or crowd, a wide view of a full room, or a travelling camera | NINE-PICTURE |
| 2a | 2 or 3 neighbouring shots share the place, the people and the camera idea, and none carries readable writing | MERGED CLIP, 5 to 10 seconds, cut by the edit |
| 2b | One continuous ordered action in one place, an instrumental stretch with no lyric cue and no writing, or a master wide | LONG TAKE, 8 to 15 seconds |
| 3 | The storyboard marks the ending as exact | TWO-PICTURE |
| 4 | Anything else | ONE-PICTURE |

`_pick_route` implements N-82 on top of this order: when two rules fit, the
route with more pictures wins; a tie falls back to rule order. A shot with
readable writing on a prop is forced to ONE-PICTURE from its checked still
(rule T-1 applied to routing). A lip-sync passage is never routed away from
LIP-SYNC.

**The choir wide (rule 1's second half).** A `choir` or `lead_in_choir` line
keeps its LIP-SYNC route, and `choir_wide_companion` adds one NINE-PICTURE
row placed immediately *before* it (`<shot>-wide`, rule 1): wide choir energy
first, then the close piece of 1 to 3 faces (section 3.4). It is never one wide
lip-sync job for a whole choir, and a lead line gets no companion.

### Adjustments after the route is set

- A shot shorter than the model's shortest clip (4 seconds for H3) is made at
  that length and trimmed in time. No story shot is planned under 2.5 seconds.
- A set appearing in 3 or more shots gets one location reference picture,
  added to each of those shots' picture lists.
- Any written object comes from the text record, on the keyframe.
- Every keyframe is image-to-image from the character references. The Shot
  Router never orders a text-to-image picture of a known character; a shot
  with cast but no locked reference is refused `CAST_REFERENCE_MISSING`.
- A shot whose cast or place differs from its beat is refused `SHOT_OFF_BEAT`
  before any picture is drawn.

### The record

`build_shot_routes(shots, beats=..., ctx=...)` returns the body of
`storyboard/shot-routes.json`; `write_shot_routes(path, record)` writes it.
Each shot carries: `shot_id`, `beat_id`, `route`, `rule`, `model`,
`model_role`, the picture list (each with purpose, kind, `image_to_image`,
references and candidate count), the song window, readable-writing flag and
notes. `two_picture_mode` records `single_request` or `chained`.

`route_summary(record)` counts shots by route and by rule for a quick read
before spend.

### Errors

`ShotRouterError` carries a `.code`: `SHOT_INVALID`, `SHOT_DUPLICATE`,
`SHOT_OFF_BEAT`, `CAST_REFERENCE_MISSING`, `LIPSYNC_FACES_INVALID`,
`ROUTE_INVALID`, `OWNER_CHOICES_INVALID`.

## N-61: it reads what the models can do, never assumes (3E.3)

`capabilities.py`. The video registry is the live skill 67 `models.json`, found
through `prompt_limits.find_catalogs()` (or `KIE_MODELS_JSON` / an explicit
path). `video_capabilities()` returns `{model_id: capability}`;
`start_plus_end_in_one_request` is DERIVED from the entry's own `control_fields`
and `max_reference_images`:

- H3 declares a first-frame and a last-frame field but one image, and its media
  line says "first OR last" -> **No**. A TWO-PICTURE shot on H3 takes the chained
  path.
- Kling 3.0 Omni, Kling 3.0, Kling 2.5 Turbo Pro, Wan 2.7 and PixVerse
  transition declare both fields with room for two images -> **Yes**.

The picture provider is a capability record (`picture-providers.json`), or the
newest GPT-image entry of an image catalog passed to `picture_capability()`. A
provider that cannot take reference pictures cannot hold a known character:
`require_character_references()` refuses it with
`PROVIDER_CANNOT_HOLD_CHARACTER`. The router never falls back to text-to-image
and never overrides the run owner's model or provider.

## N-62: cost and time, shown before any paid job (3E.4)

`estimate.py` + `rates.json`. Measured rates on file: a Sunburst picture 13.1
credits (12.4 to 13.1 listed; the high end is used), two candidates per keyframe;
H3 image-to-video 32/40/48/56/64 credits for 4/5/6/7/8 s; H3 nine-picture
32/56/64/72/64; OmniHuman 14 credits per whole audio second, rounded up. A credit
is half a cent. A failed job costs 0.

`estimate_run(records)` gives per-shot credits and the run total; the run's
minutes are its SLOWEST job (a burst takes as long as its slowest route), not a
sum. A model with no rate on file is `PRICE_MISSING` and withholds the run
total; `require_estimate()` refuses to hand a run to a paid job while any price
is missing.

## N-82: more pictures is better

`pictures.py`. When two routes could apply the one with more pictures wins
(nine beats two beats one). Every keyframe is made as two candidates and the
better is picked by the severity table: no MAJOR, then the fewest MEDIUM, then
the one carrying the planned words (`pick_candidate`). Every nine-picture shot
gets a composition keyframe (`ensure_composition_keyframe`). Cost never reduces
the picture list: a list marked `reduced_for_cost` is refused
`PICTURE_LIST_REDUCED_FOR_COST`.

## N-90: chains, and seamless move is opt-in (3E.3)

`chains.py`. Default: a two-picture shot on H3 uses the NEXT shot's storyboard
picture as its end; both keyframes exist before the burst, so both clips go in it
together and nothing waits. Seamless-move mode is off by default; when on it
marks every shot that uses it, waits one clip time per link, and reports the
longest wait before the burst (`wait_report`). A model that takes both pictures
in one request never chains.

## N-91 / N-93 / N-95 / N-102: the Clip Sizer (3I)

`sizer.py` (with `clip_sizer.py` for the merge rule and the report). Hard rules
H1 to H8 are never scored away:

- **H1** readable writing: a short one-picture clip from its checked still
  (4 to 6 s); never merged, never a long take.
- **H2** a word-exact lyric hit: short, cut to the word.
- **H3** a change of room, outfit or time of day: separate clips.
- **H4** a lip-sync piece is whole sentences, 5 to 30 s; under 5 is
  `LIPSYNC_AUDIO_TOO_SHORT`, over 30 without a stitch is `LIPSYNC_AUDIO_TOO_LONG`,
  a piece that starts or ends inside a sentence is `LIPSYNC_CUTS_SENTENCE`.
- **H5** many people, hugs or close hands: 4 to 6 s unless one ordered action.
- **H6** the run owner's model is never changed to get a length.
- **H7** on a tie, the option with more checked pictures wins.
- **H8** a camera move gets at least 6 s; 8 to 10 for a slow move across a room,
  choir or group; up to 15 when the move is the point. The move starts in the
  first half second and ends inside the used window; otherwise the edit uses the
  final part of the move, or the shot is static.

Long takes of 8 to 15 s are ONLY for one continuous ordered action, an
instrumental stretch with no lyric cue and no writing, or a master wide; every
used piece of a clip over 8 s is checked alone. The first true 15-second take is
a measured trial beside its short version. Every nine-picture clip of up to 10 s
is bought as two takes in the burst (N-93). The Clip Sizer chooses by expected
minutes to a finished video (`SIGNAL_THRESHOLDS` is 3I.3a's table), and every
run writes rendered seconds against used seconds per route (`rendered_against_used`).

## N-116: lip-sync placement (3.3c)

`lipsync_plan.py`. The two anchors are placed first: the opening passage (lead,
inside the first 15 s) and the ending (the call to action on camera and the
closing echo, the last sung line); either missing is
`LIPSYNC_ANCHOR_MISSING`. Every other passage is scored for impact (emotion
change 0-3, hook 2, speaks to the viewer 2, story turn 2, face is the point 1).
The share is spent on the highest scores to the 25-30 percent target, with whole
sentences winning over the 35 percent top. Then it is spread: no more than 20 s
of sung time (or 15 percent of the length) between pieces is
`LIPSYNC_GAP_TOO_LONG`; no quarter holds more than 40 percent of the lip-sync
seconds is `LIPSYNC_CLUMPED`. An instrumental stretch never counts toward a gap.
`plan_lipsync()` returns and `write_plan()` writes `storyboard/lipsync-plan.json`
with every candidate's points and reasons, the chosen set, the anchors, the
share, the longest gap and each quarter's share -- before any spend.

## N-73: the lip-sync picture comes from the matching sheet (3G.5)

`expression.py`. The router NAMES the sheet a line's emotion requires (pain ->
sad, worry -> worried, exhaustion -> tired, hope and relief -> hopeful, joy ->
joyful, resolve and pride -> determined, tenderness -> hopeful; anger gets an
angry sheet, and an intensity-3 tag gets its own). The sheet is a required
reference of the lip-sync keyframe, and a pain-like line at intensity 2 or 3
starts one step stronger (3G.6 lever 2). A picture drawn for another emotion, or
a smiling picture under a pain line, is refused
`LIPSYNC_EXPRESSION_MISMATCH` before any paid job (`check_before_paid_job`).

## N-120: Prop Facing (3P)

`prop_facing.py`. A prop faces its user: its reading side is toward the eyes of
the person using it. The text record gains `user`, `faces` (`user`, `camera` for
a sign or held-up card, `other person`) and `viewer_must_read`; when the viewer
must read a prop that faces its user, the Shot Router adds an INSERT SHOT over
the user's shoulder (a one-picture clip from its own checked still). The check
first reads one known-good and one known-bad picture and reports
`PROP_CHECK_UNAVAILABLE` rather than guess. Codes: `PROP_FACES_CAMERA`,
`PROP_TURNED_TO_CAMERA`, `INSERT_WRONG_SIDE`, `PICTURE_TEXT_WRONG`.

## Module map

| Module | Row |
|---|---|
| `common.py` | shared error type and helpers |
| `routes.py` | N-60 |
| `capabilities.py`, `picture-providers.json` | N-61 |
| `estimate.py`, `rates.json` | N-62 |
| `pictures.py` | N-82 |
| `chains.py` | N-90 |
| `sizer.py`, `clip_sizer.py` | N-91, N-93, N-94, N-95, N-102 |
| `lipsync_plan.py` | N-116 |
| `expression.py` | N-73 |
| `prop_facing.py` | N-120 |
