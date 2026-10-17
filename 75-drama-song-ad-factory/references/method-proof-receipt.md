# Method end to end on fixtures, no spend — proof receipt (AGN W4-proof-U3)

I am a unit agent, not the conductor: I did not run the tick, act as conductor, or edit
`LEDGER.md`, `TODO.md` or any `SWARM-PLAN` file. This unit owns one file, this receipt.

Unit **AGN-W4-proof-U3** · plan row `W4-proof-U3` · proves **SPEC acceptance 3** line by line,
and retains the CHECKLIST "Hybrid + transitions" block in this same receipt (BUILD-PLAN
`W4-proof-U3`). Receipt only: no code change, no version bump, no CHANGELOG edit, no provider call.

| | |
|---|---|
| Date | 2026-10-15 (operator Mac Mini; times local) |
| Repo / branch | `trevorotts1/openclaw-onboarding`, worktree `<PATH>/agnes-wt/W4-proof-U3`, branch `unit/AGN-W4-proof-U3`, base `origin/main` = `1e1c12dcc` |
| What runs | fixture records only. **No Suno, no KIE, no Agnes, no image or video job, no spend.** The only network-ish call in the whole proof is one local `ffprobe` read of a file already on this disk (§9) |
| Gates under test | the eight open **O-method / O-card** candidate branches (§2), because none of the method code is on `main` yet — Wave 4 is pinned to candidate heads for exactly this reason (BUILD-PLAN, *Wave release and hygiene*) |
| Lane (drivers, fixture runs, raw output) | `run/lanes/W4-proof-U3-lane/` — `prove.py`, `hybrid.py`, `out/step1..8.json`, `out/hybrid.json`, `out/card/` |

**Result: every SPEC acceptance-3 line and every CHECKLIST method line is evidenced below, and
every CHECKLIST hybrid/transition line is evidenced from read-only test F plus owned-unit fixture
results.** Two things are named rather than hidden: the two lines that stay **UNDETERMINED** (§11)
and one **FOUND-ELSEWHERE** defect this unit hit in another unit's file (§3.4). No line was turned
into a PASS by reuse.

---

## 1. What SPEC acceptance 3 asks for

> a 3-minute campaign plan from a fixture run: card → `method.json` → blueprint validated →
> length plan carries the method block → a fixture song take judged (first vocal at ERM, both
> seams, hook after breakthrough) → storyboard cards with states and a planted Transformation
> Lock break refused → two trailer plans with end cards and destinations → `platform_fit` on
> `trial-oct13/test-a-30s-cartoon/final_30s.mp4` → checklist rows with evidence levels.

Eight steps, eight driver processes (one process per step, because each step imports exactly one
candidate unit's `scripts/core` and two steps must never see each other's modules):

```
$ cd <PATH>/Downloads/Agnes Drama Ad Factory/run/lanes/W4-proof-U3-lane
$ python3 prove.py 1     # card replies -> method.json (5 purposes + 2 length-cap controls)
$ python3 prove.py 2     # Story Beat Blueprint validated, anchors ordered, plants refused
$ python3 prove.py 3     # length_formula.plan(180, method=True)
$ python3 prove.py 4     # fixture take judged: first vocal, both seams, hook after breakthrough
$ python3 prove.py 5     # storyboard cards + planted Transformation Lock break
$ python3 prove.py 6     # two trailer plans
$ python3 prove.py 7     # platform_fit on trial A's final_30s.mp4
$ python3 prove.py 8     # checklist method rows with evidence levels
$ python3 hybrid.py      # the CHECKLIST hybrid/transition block, read-only
```

Each step writes `out/step<N>.json` and prints `wrote <path>`. Nothing else is written outside
this lane; the trial folders are opened read-only.

## 2. Which code ran — pinned candidate heads, hash-checked

`git show <head>:<file> | sha256` compared against the working file for **every** module the
drivers imported, and `git status --porcelain` on each worktree (`out/step*.json` → `sources[]`):

| step | unit | head (worktree, clean) | files hash-checked |
|---|---|---|---|
| 1 | `W1-card-questions-U1` | `72841f2b9` | `intake_card.py`, `test_purpose_agnes.py` — **match** |
| 2 | `W1-method-story-U1` | `39ba63ae9` | `method_plan.py`, `fixtures/blueprint-90s.json` — **match** |
| 3 | `W1-method-song-U3` | `d2de2750d` | `length_formula.py`, `method_runtime.json` — **match** |
| 4 | `W1-method-song-U1` | `cbccc6a58` | `song_dispatch.py`, `spoken_share.py`, `test_method_song.py` — **match** |
| 4 | `W1-method-story-U1` (2nd on `sys.path`, only `method_plan` resolves from it) | `39ba63ae9` | `method_plan.py` — **match** |
| 5 | `W1-method-story-U3` | `88a34e0c2` | `scene_match.py`, `approval_package.py` — **match** |
| 6 | `W1-method-trailer-U1` | `f37518b39` | `trailer.py` — **match** |
| 7 | `W1-method-qc-U2` | `fd1ba9088` | `platform_fit.py`, `platform-specs.json` — **match** |
| 8 | `W1-method-qc-U1` | `05ee759a7` | `delivery_checklist.py` — **match** |

Every one of those worktrees reported `worktree: clean`. At this branch's base (`1e1c12dcc`)
none of it exists: `git ls-tree -r --name-only 1e1c12dcc | grep -E 'method_plan|platform_fit|clip_cutdown/trailer'` → empty. When the `O-method` and `O-card-wiring` batches merge, the
same eight commands run unchanged against `main` and produce the same numbers.

Each owning unit's own Prove file also passes on its own head (re-runnable anywhere):

```
W1-card-questions-U1  72841f2b9  pytest choice_card/intake_card/test_purpose_agnes.py   16 passed
W1-method-story-U1    39ba63ae9  pytest scripts/core/method_plan                       22 passed
W1-method-song-U3     d2de2750d  pytest scripts/core/length_formula                    13 passed
W1-method-song-U1     cbccc6a58  pytest scripts/core/song_dispatch/test_method_song.py 15 passed
W1-method-story-U3    88a34e0c2  pytest scripts/core/storyboard_director/test_transformation_lock.py  6 passed
W1-method-trailer-U1  f37518b39  pytest scripts/core/clip_cutdown/test_trailer.py      22 passed
W1-method-qc-U2       fd1ba9088  pytest scripts/core/platform_fit                      21 passed
W1-method-qc-U1       05ee759a7  pytest scripts/core/delivery_checklist/test_method_rows.py 13 passed
```

---

## 3. Card replies → `method.json` (SPEC acceptance 3, clause 1)

The card is driven **two ways on purpose**, because they answer two different halves of the line
(`out/step1.json`):

* **Path A — `IC.conversation(replies, purpose_flow=True, run_dir=…)`**: the path that actually
  writes `control/method.json` and `control/card-receipt.json` to a run folder.
* **Path B — `IC._shaped(IC.QUESTIONS, answers)` rebuilt from `QUESTIONS` on every screen**: the
  card's own question list, which is what `test_purpose_agnes.py::_plan` / `_answers_for` and
  `studio_questions(conditional=True)` use.

### 3.1 Path A — what each purpose's run folder actually holds

| purpose (reply) | screens | follow-up asked | `control/method.json` |
|---|---|---|---|
| 1 Grow my business (3 min) | **14** | **none — see §3.4** | `purpose=campaign`, `output_types=[MASTER_EPISODE, TRAILER_CLIP, TRAILER_CLIP, AD_CLIP, AD_CLIP]`, `platform=null`, `chosen_length_s=null`, `runtime_targets={}`, `gates A–F=planned` |
| 2 Client success story | 18 | **PERMISSION** at screen 2 | `purpose=testimonial`, `chosen_length_s=60`, `delivered_s=58`, `testimonial_permission=yes`, `gates A–F=planned` |
| 3 Teach a lesson | 17 | none (correct: choice 3 has no follow-up) | `purpose=lesson`, `60 / 58`, `gates A–F=planned` |
| 4a social → FB/IG paid | 17 | **WHERE** at screen 2 | `purpose=paid_ad`, `platform=meta`, `60 / 58`, `gates A–F=planned` |
| 4b social → free post | 17 | **WHERE** at screen 2 | `purpose=short_post`, `platform=organic`, `60 / 58`, `gates A–F=planned` |

Every run also wrote `control/card-receipt.json` carrying `storyboard_approval: true`, and the
four non-campaign runs carry `agnes: {answer: "yes"}`. Last screen on all five:
`Question 14/17/18 of … - SCRIPT APPROVAL`, then `Locked in. I am starting now.`

### 3.2 Path B — the right follow-up, per purpose, with the screen text

Exact headers printed by `IC.render_step` (`out/step1.json` → `question_flow[].transcript`):

```
purpose1-campaign-3min  Question 1 of 15  - PURPOSE
purpose1-campaign-3min  Question 8 of 16  - EPISODE LENGTH     <- choice 1's one follow-up
purpose1-campaign-3min  Question 12 of 17 - AGNES
purpose2-testimonial    Question 2 of 17  - PERMISSION         <- immediately after PURPOSE
purpose2-testimonial    Question 9 of 17  - LENGTH
purpose2-testimonial    Question 13 of 18 - AGNES
purpose3-lesson         Question 8 of 16  - LENGTH             <- no follow-up screen
purpose4a-paid-ad       Question 2 of 16  - WHERE
purpose4a-paid-ad       Question 9 of 16  - LENGTH
purpose4b-short-post    Question 2 of 16  - WHERE
purpose4b-short-post    Question 9 of 16  - LENGTH
```

`EPISODE LENGTH` takes LENGTH's own slot (METHOD-INTEGRATION 3.2), `PERMISSION` and `WHERE` sit
directly after `PURPOSE`, and the lesson gets neither. The follow-up order is `episode_length`,
`permission`, `where` — recorded per purpose in `question_flow[].follow_up`.

**The 3-minute campaign plan, from Path B's answers** (`_method_record(answers, qs)` — the same
function `conversation` calls at `done`):

```json
{"purpose": "campaign", "platform": null,
 "output_types": ["MASTER_EPISODE", "TRAILER_CLIP", "TRAILER_CLIP", "AD_CLIP", "AD_CLIP"],
 "chosen_length_s": 180, "runtime_targets": {"chosen_length_s": 180, "delivered_s": 178},
 "testimonial_permission": null, "gates": {"A": "planned", "B": "planned", "C": "planned",
 "D": "planned", "E": "planned", "F": "planned"}}
```

### 3.3 The Agnes 5-minute cap is a card rule too (SPEC A15)

Same Path B driver, only the `EPISODE LENGTH` answer changed:

| answer | screens | AGNES screen |
|---|---|---|
| 3 minutes (180 s) | 17 | present (`Question 12 of 17 - AGNES`) |
| 7 minutes (420 s) | **16** | **absent** |
| 10 minutes (600 s) | **16** | **absent** |

`_AGNES_MAX_LENGTH_S = 300`, so 7- and 10-minute episodes are KIE-only and the card never offers
Agnes for them. (The Agnes-path refusal itself is §11, line 5.)

### 3.4 FOUND-ELSEWHERE — `_shaped` is not idempotent for purpose 1 (another unit's file)

**This is not this unit's acceptance and this unit does not fix it** (QC-AND-FIXER §2.2: out of
scope is not a FAIL). Named with proof because this unit hit it:

`choice_card/intake_card/intake_card.py` — `_shaped` is documented as idempotent ("The conditional
ids are stripped before the rebuild, so shaping twice on the same answers gives the same list"),
and `conversation()` relies on that: it does `qs = shaped(qs, answers)` cumulatively, on the
already-shaped list. For a **campaign** the rebuild places `episode_length`, so the base list no
longer contains `length` — and `length` is **not** in `_CONDITIONAL_IDS` — so from the third screen
onwards `EPISODE LENGTH`, `SHAPE` and (through `length_text`) `AGNES` disappear from the list.

Control (same driver, same answers, `out/step1.json` → `shaped_idempotency_control`):

```
purpose 1  cumulative 14 screens   fresh-from-QUESTIONS 17 screens   idempotent False
   cumulative: purpose,offer,link,audience,character,photos,models,music,look,model,spend,storyboard,song,script
   fresh      : purpose,offer,link,audience,character,photos,models,episode_length,shape,music,look,agnes,model,spend,storyboard,song,script
purpose 2  cumulative 18 screens   fresh-from-QUESTIONS 18 screens   idempotent True
```

Purpose 2 is the control that shows the reshape mechanism itself works; the split falls exactly on
the campaign, which is the only purpose whose length question is renamed by the rebuild.

Consequence, visible in §3.1: **a campaign run driven through `IC.conversation` writes
`chosen_length_s: null`**, and Path A never asks `EPISODE LENGTH`. Path B (and the studio page's
`shows_when` evaluation, which reads the fresh list) are unaffected. Everything in §4–§10 runs on
the method's own records and does not depend on that field.

---

## 4. Blueprint validated, anchors ordered, planted early hook refused (clause 2)

`out/step2.json` · `method_plan.validate(fixture, method)` on
`method_plan/fixtures/blueprint-90s.json` with `purpose=campaign`, `chosen_length_s=90`:

| check | result |
|---|---|
| outcome | `ok`, `reason_code: null` |
| anchors | `backstory 0.0 → erm_apex 22.0 → hero_shift 38.0 → breakthrough 58.0 → hook 60.0 → commercial 72.0` |
| strictly ordered, and `breakthrough ≤ hook` | **True** |
| cue list | `BASELINE, PAIN_BUILD, ERM_DROP, PAIN_DEEPEN, HERO_SHIFT, BREAKTHROUGH, SOLUTION_HOOK, COMMERCIAL_CONTINUATION` |
| `pace_order(bp)` | `boundary_s 22.0` (ERM Drop), `return_boundary_s 38.0` (Hero Shift), `drop "heavier, sparser half-time"`, `return "steadier, more open pace"`, `true_at_beat "the_turn"` — two distinct timestamps, the shape `music_qc.pace_change.check_pace_plan` requires |
| `true_at_beat(bp)` | `"the_turn"`; declared `"the_world"` → **refused to `"the_turn"`**; declared `"lowest_point"` (the 60 s golden-sheet defect, conflict C6) → **refused to `"the_turn"`** |

**Plants (each starts from the passing fixture and moves exactly one cue):**

| plant | outcome | reason code | detail |
|---|---|---|---|
| `SOLUTION_HOOK.start_s = 30.0` (before the Hero Shift at 38 s) | **rejected** | `HOOK_UNEARNED` | "the first hook starts at 30.0 s, before the solution is introduced at the Hero Shift (38.0 s); the build toward the hook starts once help arrives, never before it (Trevor 2026-10-13)" — plus "breakthrough at 58.0 s does not come at or before hook at 30.0 s" |
| `COMMERCIAL_CONTINUATION.start_s = 50.0` (before the hook at 60 s) | **rejected** | `ANCHOR_ORDER` | "backstory < ERM apex < Hero Shift < …" |

---

## 5. Length plan 180 s carries the method block (clause 3)

`out/step3.json` · `length_formula.plan(180, method=True)` on `W1-method-song-U3` @ `d2de2750d`:

```
chosen_length_s 180   delivered_s 178
plan(180, method=True)["method"] =
  origin "method"   profile "story"   total_s 180.0
  backstory_s [10.0, 15.0]      erm_window_s [25.0, 40.0]    erm_apex_s 32.5
  first_sung_by_s 32.5          hero_shift_s 75.0            hook_from_s 95.0
  commercial_from_s 140.0       cta_reserve_s [30.0, 45.0]
  block_anchors_s {backstory_instrumental 12.0, problem_and_tension_escalation 35.0,
                   erm_first_singing_and_pain 65.0, solution_introduction_and_hero_shift 75.0,
                   solution_use_and_first_breakthrough 95.0,
                   first_earned_solution_signature_hook 110.0,
                   further_story_and_reprises 140.0, closing_commercial_and_cta 180.0}
  note "planning targets, not timing laws: the ERM target is an arrival timestamp …"
  source "Drama-to-Demand Method by Trevor Otts, section 7.1 (editorial starting targets)
          and section 7.2 (complete illustrative time allocations). Read 2026-10-13 …"
```

Control: `plan(180)` with no `method` argument has **no `method` key at all** — inert until wired.
(`backstory_s [10, 15]` is the method's 3-minute row; conflict C2's opener change is what lets the
opener carry that narration — recorded here as `plan_keys`, not re-measured.)

---

## 6. A fixture song take judged — first vocal at ERM, both seams, hook after breakthrough (clause 4)

`out/step4.json` · `song_dispatch.judge_take` on `W1-method-song-U1` @ `cbccc6a58`, with the run's
method block `{"erm_apex_s": 15.0, "profile": "story", "erm_window_s": [12, 18]}`.

**The take is a measured-take stub** (`test_method_song.py::take()`), so the gates that can be
measured on it are the ones read below; the gates that need a real Suno return (`hook`,
`hook_placement`, `song_contract`, `script_words`) report FAIL/UNMEASURED on it and the take's
overall `verdict` is therefore `FAIL`. That is recorded, not hidden — no fixture verdict is
presented as a product PASS.

### 6.1 First vocal at the ERM

| take | `first_sung` gate | wording | in `failed`? |
|---|---|---|---|
| first sung 15.4 s | **PASS** | "first sung word at 15.4 s is inside the ERM apex window 13.5-16.5 s (+0.4 s): pass" | no |
| first sung **8.0 s** | **FAIL** | "first sung word at 8.0 s is 7.0 s BEFORE the ERM apex 15.0 s (window 13.5-16.5 s): early, redo" | yes (`first_sung`) |
| first sung 17.2 s | **FAIL** | "first sung word at 17.2 s is 2.2 s AFTER the ERM apex 15.0 s …: late, redo" | yes (`first_sung`) |

Control — **inert until wired**: the same 8.0 s take on a plan with **no** method block gives
`first_sung PASS` ("8.0 s"), because a non-method run keeps today's 15 % rule. And a method plan
that names no apex returns `UNMEASURED`, never PASS.

### 6.2 Both seams are required

| evidence | result |
|---|---|
| `SDM._pace_required({}, {})` | **True** (no plan at all) |
| `SDM._pace_required(PLAN, take())` | **True** |
| `judge_take` with a method block and **no** pace order | `pace_change = UNMEASURED`, detail `PACE_TURNS_REQUIRED: both pace turns are mandatory and measured on every run (Trevor 2026-10-13) …`; `pace_change` is in `required_gates` **and** in `flagged`, not in `failed`-as-passed; take `verdict != PASS` |
| `SD.run_takes` (dispatch) with a method block and **no** pace order | raises `DispatchError: PACE_TURNS_REQUIRED: …` — refused **before** any generation |
| `judge_take` with the order present | `PACE_TURNS_REQUIRED` **absent** from the detail (the refusal is about the missing order, nothing else); `pace_change UNMEASURED "before window must be a mapping, got None"` — a stub take carries no measured pace audio, so it is unmeasured, never PASS |
| the order itself | `boundary_s 15.0`, `return_boundary_s 38.0`, `drop "half-time drop, thin drums"`, `return "turn and rise back to the groove"` |

### 6.3 Hook after breakthrough

The beat is read off the blueprint (§4), so the plan-time rule and the sheet/take gate cannot
disagree: `true_at_beat = "the_turn"`, which starts at **33.14 s** of a 58 s delivered ad;
`min_first_hook_s = 13.4 s`.

A method-shaped fixture sheet (two build-up verses, two hook blocks — `hook_target` allows 2 after
the turn) puts its hooks at 64.0 % and 78.6 % = **37.12 s** and 45.59 s. The "Suno return" fed to
`hook_placement.check_returned` is a **stub that echoes the sheet's own section headers at the
sheet's own hook times** — no provider call, and every negative moves exactly one thing:

| case | gate | verdict | why |
|---|---|---|---|
| method sheet, `check_story` | plan | **`[]` (pass)** | first hook at 64 % ≥ the turn at 57 %, 2 hooks ≤ 2 allowed |
| unit's own pre-method fixture sheet, `check_story` | plan | **refused** | "3 hook blocks, the 58 s plan fits at most 2 after the beat 'the_turn'" + "the first hook sits at 28 % of the song (beat 'villain_arrives'), before 'the_turn' (from 57 %) where its words become true" |
| same sheet, its own `the_world` beat | plan | **`[]` (pass)** | control: the rule did not become unsatisfiable, it became method-strict |
| compliant return | take | **PASS** | `first_hook_s 37.12`, `hook_blocks_returned 2`, `hook_blocks_sheet 2`, no reasons |
| first hook moved to 5.0 s | take | **FAIL** | "first hook sung at 5.0 s, inside the 13.4 s build-up window" + "first hook sung at 5.0 s (beat 'the_world'), before 'the_turn' starts at 33.1 s where its words become true" |
| Suno returns one hook block too many | take | **FAIL** | "Suno sang 3 hook blocks, the sheet has 2 (added at 50.0 s)" + "Suno returned 8 sections, the sheet has 7" |
| the unit's own stub take (empty `aligned_words`) | take | **FAIL / UNMEASURED** | "UNMEASURED: section headers (Suno returned none; hook placement cannot be read)" |

Plus the blueprint-side refusal in §4 (`HOOK_UNEARNED`). So "hook after breakthrough" is proven
where the method puts it — at plan time — and re-measured on a take, with the no-return case
failing closed rather than passing.

---

## 7. Storyboard cards with states, planted Transformation Lock break refused (clause 5)

`out/step5.json` · `scene_match.transformation_lock` + `approval_package.build` on
`W1-method-story-U3` @ `88a34e0c2`. Fixture: three shots (pain side → breakthrough at 42.0 s →
post-breakthrough), lock token `cape off`, every card carrying `story_beat_id`, `music_cue_id(s)`
and `character_state`.

| case | result |
|---|---|
| method cards | `outcome ok`, `reason_code I2_CARDS_COMPLETE` |
| **planted break** — post-breakthrough shot back in the `before` state | **`rejected` / `TRANSFORMATION_LOCK_BROKEN`**, finding `s3`: "present-time shot after the breakthrough still shows the before-state of cape off" — only `s3` is named; the pain-side shot is not |
| the same plant through `AP.build(..., method=True, lock_token=…, breakthrough_s=42.0)` | raises `ApprovalError`: `TRANSFORMATION_LOCK_BROKEN: s3: present-time shot after the breakthrough still shows the before-state of cape off` — the approval package fails closed |
| repaired (`character_state: "after"` on `s3`) | `outcome ok`, `reason_code TRANSFORMATION_LOCK_HELD` |
| `continuity_tag: "flashback"` **with no reason** | still **`TRANSFORMATION_LOCK_BROKEN`** — "marked flashback with no reason" |
| `continuity_tag: "flashback"` **+ `continuity_reason`** | `TRANSFORMATION_LOCK_HELD` — the one escape hatch SPEC C4 allows |

---

## 8. Two trailer plans with end cards and destinations (clause 6)

`out/step6.json` · `clip_cutdown.trailer.plan_trailers(timeline, blueprint, 180, show)` on
`W1-method-trailer-U1` @ `f37518b39`, with the unit's own 180 s timeline/blueprint fixture and
`show = {name "Carry It, Sis", episode "Episode 4", channel/destination "youtube.com/@carryitsis"}`.

| | 60 s plan | 90 s plan |
|---|---|---|
| `clip_length_s` / `duration_s` / budget | 60 / **56.9** / 58 — within | 90 / **86.9** / 88 — within |
| piece order (source pieces) | `opening, opening, pain, erm, erm, hero, breakthrough, hook` | same arc, **different source ranges** |
| opens on the master's instrumental opening | yes (`opening` first) | yes |
| ERM before Hero Shift | yes | yes |
| hook only after a local breakthrough | yes (`breakthrough` index < `hook` index) | yes |
| last piece | **`END_CARD`** | **`END_CARD`** |
| end card | `3.0 s`, lines `["Carry It, Sis", "Episode 4", "Watch the full episode on youtube.com/@carryitsis"]`, `source_in 124.5` | `3.0 s`, same three lines, `source_in 129.5` |
| `destination` | `youtube.com/@carryitsis` | `youtube.com/@carryitsis` |
| `viewing_reason` | present ("she is always on and never asks") | present |
| `spoiler_boundary` | `master_s 124.5`, "the resolution and everything after this point in the master are withheld from the cut" | `master_s 129.5`, same note |
| source ranges differ from the other plan | **True** (the 90 s cut adds context, never repeats 30 s of setup) | |

`end_card.lines` also shows the trailer's destination is the **episode/channel**, never the
checkout (SPEC C5 / conflict C8). Fail-closed control: the same call with an empty
`show.channel`/`show.destination` raises
`TrailerError: TRAILER_NO_DESTINATION: the trailer's destination is the episode/channel, never the checkout: pass timeline.show with channel or destination`.

---

## 9. `platform_fit` on trial A's `final_30s.mp4`, read dates shown (clause 7)

`out/step7.json` · `platform_fit.probe_file` + `check` + `fits` on `W1-method-qc-U2` @ `fd1ba9088`.

```
file  trial-oct13/test-a-30s-cartoon/final_30s.mp4   sha256 35adc69cd03c9066…  (13,956,855 bytes)
probe container mp4 · h264 · 720x1280 · 24.0 fps · aac · duration 30.375034 s
today 2026-10-15   every spec row read_utc 2026-10-13, reverify_after_days 30 → days_since_read 2
```

| placement | verdict | code | why |
|---|---|---|---|
| `instagram_reels_ad` | **PASS** | — | "2 documented limit(s) checked, all inside the spec" |
| `tiktok_video_ad` | **PASS** | — | 4 documented limits |
| `linkedin_video_ad` | **PASS** | — | 5 documented limits |
| `youtube_short` | **PASS** | — | 4 documented limits |
| `instagram_reel` | **PASS** | — | 4 documented limits |
| `facebook_reel` | **PASS** | — | 4 documented limits |
| `facebook_reels_ad` | **FLAG** | `UNDETERMINED_SPEC` | "spec status UNDETERMINED -- verify by hand before publishing …" — never PASS |
| `x_twitter` | **NOT_AVAILABLE** | — | "not available: GHL disabled X/Twitter posting on 2024-12-04; never offered as a destination" |

`fits(probe)` → 8 destinations (`instagram_story, instagram_reel, instagram_feed, facebook_story,
facebook_reel, linkedin_video, youtube_short, pinterest_video_pin`), `x_twitter` not among them.

**Re-verify clock works** (the row is 2 days old today, so it cannot be stale by observation):

```
check(probe, "instagram_reels_ad", today=2026-11-25) →
  verdict FLAG  code STALE_SPEC  stale true  days_since_read 43
  "STALE_SPEC: read 43 day(s) ago, past the 30 day re-verify window -- re-read
   https://www.facebook.com/business/ads-guide/update/video/instagram-reels before trusting it"
```

Every row's `source`, `source_url`, `read_utc`, `reverify_after_days` and `status` is recorded in
`out/step7.json → spec_rows[]` (22 rows, all `read_utc 2026-10-13`).

---

## 10. Checklist method rows carry evidence levels (clause 8)

`out/step8.json` · `delivery_checklist.measure_method` on `W1-method-qc-U1` @ `05ee759a7`.
Levels are exactly `("planned", "generated", "inspected", "approved")`; a PASS only rides
`inspected` or `approved`.

**Campaign run** (`control/gates/*.json` fixtures):

| row | verdict | evidence_level | evidence |
|---|---|---|---|
| `ERM_DROP` | **PASS** | **inspected** | "first sung word 55.4 s vs ERM apex 55.0 s" (carried by `measurement`) |
| `HERO_SHIFT` | **UNAVAILABLE** | planned | record claims PASS but declares no inspected/approved level → downgraded, never a PASS |
| `EARNED_HOOK` | **PASS** | **approved** | "client said the hook lands after the breakthrough" + `approval_answer: yes` |
| `TRANSFORMATION_LOCK` | **checked, client waived approval** | inspected | `waived: true` — never spelled "approved" |
| `TRAILER_PURPOSE` | **UNAVAILABLE** | planned | "no method record: control/gates/TRAILER_PURPOSE.json missing" — no record, no verdict |

**Testimonial run** — `CLAIMS_PERMISSION` falls back to `control/method.json`:
`PASS / approved / "control/method.json testimonial_permission=yes"`. Every other row with no
record is `UNAVAILABLE / planned`.

**The two honesty laws, both fail-closed:**

* a record claiming `evidence_level: "approved"` with **no** recorded human answer
  (`{"verdict": "PASS", "evidence_level": "approved", "evidence": "looks fine to me"}`) comes back
  **`verdict UNAVAILABLE`, `evidence_level planned`** — `lying_claim_stands_as_approved = False`;
* a run with **no** `control/method.json` returns **`None`** — inert until wired.

Every row carries exactly `{verdict, evidence_level, evidence}` (`every_row_has_exactly_three_keys
= True`). Row/purpose applicability is `METHOD_ROWS`: `TRAILER_PURPOSE`→campaign only,
`CLAIMS_PERMISSION`→testimonial only, `LESSON_LINK`→lesson only, `PLATFORM_FIT`→paid_ad/short_post.

---

## 11. Hybrid + transitions — retained in this receipt (CHECKLIST)

BUILD-PLAN `W4-proof-U3`: *"Also retain CHECKLIST's hybrid/transition acceptance in this existing
receipt using read-only test F evidence and owned-unit fixture results … Missing evidence is
UNDETERMINED/parked; do not buy a new hybrid trial or create another receipt/unit."*
Source files are opened **read-only**; nothing is written into `trial-oct13/`.
Raw quotes with file:line are in `out/hybrid.json → trial_f_read_only`.

| CHECKLIST line | Evidence | Status |
|---|---|---|
| Storyboard + full image prompts written before any generation | `references/stage-runbook.md` order: `storyboard` (line 17) → `image-keyframes` (18) → `video-generation` (19); trial F delivered `STORYBOARD.md` + `IMAGE-PROMPTS.md` beside the video (`trial-f/RESULTS.md:3`), and its own prompt build "failed a length check **before it wrote**" | **Evidenced** |
| Drawn character sings, hard cut on a music change, real person sings, real + ink-doodle ending chained from the lip-sync's last frame | `trial-f/RESULTS.md:7` "lip-sync exists on both sides, no giant hand, no morph clip at all (the change from drawing to real person is one hard cut)"; timeline rows `RESULTS.md:13-16` (drawn wide → drawn lip-sync → **HARD CUT at 15.46 s** → real lip-sync → "21.9-30.0 s (plain cut) … first = last frame of the lip-sync"); `RESULTS.md:56` "no giant hand, no morph, one clean hard cut, lip-sync on both sides" | **Evidenced, except** the cut landing *on a music change* → **UNDETERMINED** (`RESULTS.md:53` "Whether the beat falls on a musical change: UNDETERMINED") |
| No morph clip, no extra hands | `trial-f/STORYBOARD.md:14` "Rules kept: no morphing clip anywhere …"; `trial-f/IMAGE-PROMPTS.md` `WHAT MUST NOT APPEAR` lists "no extra people, no extra hands or fingers"; `RESULTS.md:56` | **Evidenced** |
| No stray text (OCR) | `trial-f/RESULTS.md:40` "tesseract (psm 11) on 30 frames (1 per second): no words, only 1 to 8 character noise …"; unit `W1-agnes-core-U5` `onscreen_text`: `OCR_UNAVAILABLE = "OCR_UNAVAILABLE" # no engine, no read, never a PASS`, `test_onscreen_text.py` **18 passed** | **Evidenced** |
| No smiling lip-sync source | `trial-f/STORYBOARD.md:14` "real stills have no smile and no teeth for the lip-sync shot"; `IMAGE-PROMPTS.md` mouth-state wording "NO smile, no smirk … NO teeth visible"; the two smile-promising tries were **discarded** (`IMAGE-PROMPTS.md:19`); unit `W1-method-lipsync-U2` `picture_gate.py` carries the teeth-smile remake hook, `test_crop_ladder.py` **9 passed** | **Evidenced** |
| Face-only lip-sync crops | `trial-f/RESULTS.md:15` "KIE kling/ai-avatar-standard on a face-only crop of still C"; `RESULTS.md` "Attempt 2 used the same still cropped to the face and collar only … clean, no text"; `CROP_LADDER_WIDTHS = (0.70, 0.60, 0.80)` in `picture_gate.py` | **Evidenced** |
| Joins: chained joins plain cut or ≤ 0.2 s crossfade; scene changes 0.4 s | trial F (the joins as delivered): `RESULTS.md:13` "0.2 s crossfade from 7.9" (inside one scene), `RESULTS.md:16` "plain cut" at 21.9 s, `RESULTS.md:14` the scene change at 15.46 s is a **HARD CUT** — 0 s, never a morph; unit `W1-agnes-core-U9` `agnes_transitions.py` sets both allowances: `XFADE_INTRA_S = 0.2`, `XFADE_SCENE_S = 0.4` (0 s is allowed by passing `xfade_s=0.0`, "a plain cut"), `test_agnes_transitions.py` **12 passed** | **Evidenced** |
| The song is the only audio | `trial-f/RESULTS.md:3` "exactly 30.000 s, 720 frames, **one audio stream = the song only**"; unit `agnes_transitions.py` builds `["-an", "-i", src]` per Agnes input and "one audio map, and it is the song" | **Evidenced** |
| A 7- or 10-minute request is refused on the Agnes path (`AGNES_LENGTH_CAP`) and offered on KIE | unit `W1-agnes-core-U4` `agnes_plan.py`: `if delivered_s > AGNES_MAX_DELIVERED_S: raise PlanError("AGNES_LENGTH_CAP", "Agnes is capped at 5 minutes: … 7- and 10-minute episodes are KIE-only")`, `test_agnes_plan.py` **12 passed**; the card side hides AGNES at 420 s and 600 s (§3.3) | **Evidenced** |
| Wrong lip-sync audio still fails for every look (the lip-sync input cannot be a lucky match) | unit `W1-method-lipsync-U1` `test_cartoon_sync.py` — full `lip_gate` suite **9 passed** | **Evidenced** |

Owned-unit fixture runs (`out/hybrid.json → units[]`, every worktree `clean`, head recorded):

```
W1-agnes-core-U4      12 passed      W1-agnes-core-U5      18 passed
W1-agnes-core-U9      12 passed      W1-method-lipsync-U1   9 passed
W1-method-lipsync-U2   9 passed
```

### UNDETERMINED / parked (not turned into PASS, no new trial bought)

1. **The hard cut landing on a musical change** — trial F records it as UNDETERMINED
   (`trial-f/RESULTS.md:53`); the cut was placed on a breath gap between two sung lines, which is
   not a verified pace change. Needs a measured pace change in a live run → Trevor's operator box (SPEC
   acceptance 5), not this unit.
2. **Lip-sync accuracy on either side of test F's cut** — trial F records UNDETERMINED; that is
   `W4-proof-U4`'s subject, not this unit's.

Both are parked in this receipt, exactly as BUILD-PLAN tells this unit to park them.

---

## 12. No spend, no provider call — how that is shown

* `prove.py` imports only candidate-branch modules and stdlib; it opens files and calls gates.
  There is no HTTP client, no `requests`, no provider SDK and no ledger write anywhere in it.
  The only external binary is one local `ffprobe` read of `trial-oct13/test-a-30s-cartoon/final_30s.mp4`,
  routed through `core/load_governor` (`[load-governor] START platform-fit-probe … END … ran 0.2 s`).
* The Suno-shaped input in §6.3 is an explicit **stub** (`aligned_words` built from the sheet's own
  headers), labelled as such in the code and in this receipt; nothing was submitted to a provider.
* No Agnes call, no KIE call, no image or video job, no credit spend, no trial folder written.

## 13. Reproduce

```
cd <PATH>/Downloads/Agnes Drama Ad Factory/run/lanes/W4-proof-U3-lane
python3 prove.py 1 2 3 4 5 6 7 8      # one process per step; writes out/step<N>.json
python3 hybrid.py                     # writes out/hybrid.json

# owning units' own Prove files (each from its own worktree, path from the repo root)
cd <PATH>/agnes-wt/<unit> && python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/<area>
```

The area **Regression** commands at the top of BUILD-PLAN were run on this branch's tree and are
pasted in the PR body. This branch adds one file (`references/method-proof-receipt.md`) and changes
no code, so the regression result is the base's result.
