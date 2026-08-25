# GOLDEN-BOOK-BIBLE — the pinned contract for the Skill 53 golden regression sample

**Status:** CONTRACT (Agent A / linchpin). This file is the single source of truth for the
checked-in golden sample. Every downstream author (Wave-2 prose authors + Agent D who assembles
the run and generates broken-variant fixtures) MUST echo these strings **byte-exact**. Nothing here
is a suggestion; the fail-closed provers measure against it.

- **Fleet law:** fictional names only. The only permitted real name anywhere is the owner
  "Trevor Otts" (method attribution) — and this sample does not need it in deliverable content.
  Public figures named as tone influences (e.g. Simon Sinek) are *style references*, not clients.
- **No Anthropic / `claude-*` model ids** in any golden artifact or receipt.
- **No absolute paths** baked into any shipped file.

---

## 1. Fictional author + book identity (PINNED — byte-exact)

| Field | Value (verbatim) |
|---|---|
| `first_name` | `Marcus` |
| `last_name` | `Halloway` |
| Author label (deliverable prefix) | `Marcus_Halloway` |
| Golden slug | `marcus-halloway` |
| Golden example dir | `53-book-writer/examples/golden-marcus-halloway/` |
| Blended-tone voice name | **The Marcus Halloway Tone** |
| **LOCKED title** | `The Quiet Authority` |
| **LOCKED subtitle** | `How the Best New Leaders Trade Control for Trust` |
| Manuscript filename stem | `The_Quiet_Authority` |
| GATE-1 receipt id | `GATE-1-title` |
| GATE-2 receipt id | `GATE-2-outline` |

> The **LOCKED title** and **LOCKED subtitle** are the two strings `prove_bw_titlelock.py` requires to
> appear **byte-exact** (as raw substrings) in: the blurb, the approved outline, every chapter payload /
> title page, the manuscript title page, the 30-Day Challenge title page, and the cover prompt. Do not
> re-case, re-punctuate, curly-quote, or abbreviate them anywhere.

Topic (genuinely writable, clean 12-chapter arc): a leadership / self-development book for the
newly-promoted first-time engineering manager — the former star individual contributor who is now
failing at the human side of leadership. The through-line: *stop being the smartest person in the
room; become the leader who multiplies everyone else.*

---

## 2. The full `intake.json` object (PINNED — mirrors Skill 52 `test-fixtures/intake-book.json`)

Ships verbatim at `examples/golden-marcus-halloway/run/intake.json` and (identically) at
`examples/golden-marcus-halloway/intake.json`.

```json
{
  "version": "book",
  "mode": "full",
  "first_name": "Marcus",
  "last_name": "Halloway",
  "ideal_avatar": "newly-promoted first-time engineering managers who were the top individual contributor on their team and now feel they are failing at the human side of leadership",
  "niche": "leadership development for first-time technical managers",
  "primary_goal": "lead a high-trust team that ships without them being the bottleneck, and stop micromanaging",
  "tone_style_1": "Simon Sinek in Leaders Eat Last",
  "tone_style_2": "N/A",
  "book_about": "how a first-time manager stops being the smartest person in the room and becomes the leader who multiplies the people around them",
  "book_stories": "STORY-A ||| STORY-B (see section 6 — each verbatim block, N/A-guarded)",
  "cover_description": "a single unlit lamp on a calm dark desk with a soft warm glow just beginning at its base, minimalist, high-contrast, room to breathe; conveys quiet, earned authority rather than force",
  "email": "marcus@example.com"
}
```

Notes for the intake gate (`prove_bw_intake.py`): `version` MUST equal `book` (enum, fail-closed —
`brand` is a hand-off to Skill 52, never run here). `mode` MUST be in `{full, 4x3x3}`. `book_stories`
is required and `N/A` is permitted; here it is non-N/A, so `prove_bw_stories` enforces placement. The
literal `book_stories` value shipped in the golden `intake.json` is the two verbatim story blocks in
section 6 joined by a blank line (the `STORY-A ||| STORY-B` shorthand above is documentation only).

---

## 3. Avatar dossier summary (authored to `run/artifacts/01-avatar.md`, delivered as `Avatar_Document-Marcus_Halloway.md`)

The dossier is the reconstructed Phase-B avatar analysis. Wave-2 authors the full document; it MUST
open by naming the avatar and carry, at minimum, these pinned anchors so the packager and QC can bind:

- **Who:** a 28–38-year-old senior engineer promoted 0–12 months ago to manage a team of 4–8 they
  used to code alongside; identity is still fused to being the best technical mind on the team.
- **The wound:** believes leadership = being the person with the answers; equates delegating with
  losing quality; works nights redoing others' work; the team has gone quiet and dependent.
- **The desired transformation:** a team that ships high-quality work without the manager in the
  critical path; trust that survives the manager leaving the room; feedback that lands without fear.
- **Primary goal (verbatim echo of intake):** `lead a high-trust team that ships without them being
  the bottleneck, and stop micromanaging`.

---

## 4. The blended tone — "The Marcus Halloway Tone" (authored to `run/artifacts/08-blended-tone.md`)

**Floor: ≥ 3000 stripped words** (per `shared-utils/tone-writing-core`; enforced by `prove_bw_tone.py`
→ `AF-BK-TONE-LEN`). Delivered as `Tone_Communication_Style_Analysis-Marcus_Halloway.md`. The doc MUST
name the voice exactly **The Marcus Halloway Tone** and echo the LOCKED title once on its title line.

**Voice rules every chapter author MUST obey (pinned):**

1. **Grade level:** write at a 9th–10th-grade reading level — short, load-bearing sentences; a
   working manager reads this at 10pm, tired.
2. **Cadence:** vary sentence length deliberately; land each section on a short declarative line
   (≤ 8 words) that a reader could underline.
3. **Second person, warm-direct:** address the reader as "you"; coach, never lecture; no jargon
   without an immediate plain-English gloss.
4. **Motif — the lamp:** recurring image of *quiet, earned light* vs. *forced brightness* (ties to
   the cover); use sparingly (≤ once per chapter) so it stays a signature, not a tic.
5. **Motif — "the smartest person in the room":** name and dismantle this trap across the arc; it is
   the book's spine phrase.
6. **Evidence rhythm:** every claim is followed by either a concrete scene, a small number, or a
   named practice the reader can run tomorrow. No abstraction stands alone.
7. **No fear language as a tool:** the book models psychological safety; never shame the reader for
   the old habits — normalize them, then replace them.
8. **Signature close:** end each chapter with a single-line challenge to the reader (bridges into the
   30-Day Challenge companion).

---

## 5. The 12 chapter titles (PINNED — byte-exact; `prove_bw_chapters.py` binds count = 12)

Chapter headings in the manuscript and `chapters/chNN.md` MUST use these exact titles.

| # | Chapter title (verbatim) |
|---|---|
| 1 | `The Promotion That Broke You` |
| 2 | `Why Your Old Superpower Now Fails` |
| 3 | `The Myth of the Indispensable Leader` |
| 4 | `Listening Louder Than You Speak` |
| 5 | `Delegation Is Not Abandonment` |
| 6 | `The Trust Equation` |
| 7 | `Feedback Without Fear` |
| 8 | `Running Meetings People Don't Dread` |
| 9 | `Protecting Your Team's Focus` |
| 10 | `When to Step In, When to Step Back` |
| 11 | `Growing Leaders, Not Followers` |
| 12 | `The Legacy of Quiet Authority` |

---

## 6. The two personal stories (PINNED — verbatim; `prove_bw_stories.py` → `AF-BK-STORIES`)

Both stories are non-N/A, so each story's **normalized key phrase** MUST appear in BOTH the approved
outline AND the manuscript. The verbatim blocks are shipped in `run/stories.json` (with `key_phrase` +
`chapter`) and inside `intake.json`'s `book_stories`. Normalization = lowercase, strip punctuation,
collapse whitespace (see `_bw_common.normalize_phrase`).

**STORY-A — place in Chapter 1 (`The Promotion That Broke You`):**
> In my third week as a manager, I rewrote a junior engineer's pull request at 2 a.m. because I could
> not stand to see it done differently than I would have done it. The next morning she quietly asked
> to transfer teams. That was the night I learned my competence had become my team's ceiling.

- **Pinned `key_phrase` (STORY-A):** `rewrote a junior engineer's pull request at 2 a.m.`
- Normalized target: `rewrote a junior engineers pull request at 2 am`

**STORY-B — place in Chapter 6 (`The Trust Equation`):**
> When I finally handed the launch decision to my team and left the office at five, I sat in my car
> certain everything would fall apart. They shipped it flawlessly without me, and the pride I felt was
> bigger than anything I had ever built alone.

- **Pinned `key_phrase` (STORY-B):** `handed the launch decision to my team and left the office at five`
- Normalized target: `handed the launch decision to my team and left the office at five`

`run/stories.json` (PINNED shape):
```json
[
  {"id": "STORY-A", "chapter": 1, "key_phrase": "rewrote a junior engineer's pull request at 2 a.m.",
   "text": "In my third week as a manager, I rewrote a junior engineer's pull request at 2 a.m. because I could not stand to see it done differently than I would have done it. The next morning she quietly asked to transfer teams. That was the night I learned my competence had become my team's ceiling."},
  {"id": "STORY-B", "chapter": 6, "key_phrase": "handed the launch decision to my team and left the office at five",
   "text": "When I finally handed the launch decision to my team and left the office at five, I sat in my car certain everything would fall apart. They shipped it flawlessly without me, and the pride I felt was bigger than anything I had ever built alone."}
]
```

---

## 7. Detailed per-chapter outline (3–5 beats each) — authored to `run/artifacts/13-outline.md`

Delivered as `APPROVED-OUTLINE.md`. The outline MUST open with the LOCKED title + subtitle title line,
place both pinned story key phrases (Ch1, Ch6), and give each chapter 3–5 beats. Each chapter body is
**2000–3500 stripped words** (`prove_bw_chapters.py` → `AF-BK-CHAP-LEN`).

**PART I — Unlearn the Star (Ch 1–3)**
1. **The Promotion That Broke You** — (a) the day you got promoted for being the best coder; (b)
   STORY-A: the 2 a.m. pull-request rewrite and the transfer request; (c) the hidden job change no one
   told you about; (d) "your competence became your team's ceiling"; (e) close: name the version of you
   this book retires.
2. **Why Your Old Superpower Now Fails** — (a) the individual-contributor scoreboard vs. the manager
   scoreboard; (b) why "I'll just do it" scales to zero; (c) the dopamine trap of being needed; (d) the
   first metric that actually matters now (team throughput, not your commits).
3. **The Myth of the Indispensable Leader** — (a) the manager who cannot take a vacation; (b) bus-factor
   as a leadership grade; (c) the lamp motif introduced: earned light vs. forced brightness; (d) redefine
   indispensable = builds people who do not need you.

**PART II — Lead Through Others (Ch 4–6)**
4. **Listening Louder Than You Speak** — (a) the 2-minute silence rule; (b) questions that outperform
   answers; (c) one-on-ones that surface truth; (d) how to stop finishing people's sentences.
5. **Delegation Is Not Abandonment** — (a) delegation ≠ dumping; (b) the ownership ladder (tell → ask →
   decide-and-inform → own); (c) letting work be "good enough and theirs"; (d) the cost of taking it back.
6. **The Trust Equation** — (a) trust = reliability × safety ÷ self-interest; (b) STORY-B: handing off
   the launch and leaving at five; (c) the pride of a team that ships without you; (d) trust compounds,
   control decays; (e) close.

**PART III — Build the System (Ch 7–9)**
7. **Feedback Without Fear** — (a) why fear kills the signal; (b) the situation-behavior-impact frame;
   (c) praise in public, correct in private, both specific; (d) receiving feedback as the model.
8. **Running Meetings People Don't Dread** — (a) the meeting audit; (b) agendas as respect; (c) decisions,
   not status; (d) protecting the introverts and the makers.
9. **Protecting Your Team's Focus** — (a) the manager as a shield, not a funnel; (b) saying no upward;
   (c) maker time vs. manager time; (d) the true cost of interruption.

**PART IV — Multiply Yourself (Ch 10–12)**
10. **When to Step In, When to Step Back** — (a) the intervention ladder; (b) letting small failures
    teach; (c) the fires only you can fight; (d) stepping back as an act of respect.
11. **Growing Leaders, Not Followers** — (a) the multiplier vs. the diminisher; (b) growing your
    replacement on purpose; (c) sponsorship over mentorship; (d) the team that promotes itself.
12. **The Legacy of Quiet Authority** — (a) authority you do not have to assert; (b) the lamp fully lit
    by the people you grew; (c) what they say when you leave the room; (d) the reader's charge forward.

---

## 8. The 30-Day Challenge (authored to `run/artifacts/21-30day-challenge.md`) — EXACTLY 30 day-sections

Delivered as `30_Day_Challenge-Marcus_Halloway.md`. `prove_bw_challenge.py` (`AF-BK-CHALLENGE`) counts
day-sections by the heading pattern `Day <n> —`; there MUST be **exactly 30**. Title page echoes the
LOCKED title. Theme per day (grouped to the 4 parts):

- **Week 1 — Unlearn the Star:** Day 1 — Audit where you are the bottleneck · Day 2 — List every task
  only you "can" do · Day 3 — Do nothing for one blocked ticket · Day 4 — Ask instead of answer, all day
  · Day 5 — Track your commits vs. your team's · Day 6 — Write your bus-factor honestly · Day 7 — Retire
  one hero habit.
- **Week 2 — Lead Through Others:** Day 8 — Run a silent 2-minute question · Day 9 — Delegate one task
  fully and don't take it back · Day 10 — Hold a truth-surfacing one-on-one · Day 11 — Let "good enough
  and theirs" ship · Day 12 — Map one person up the ownership ladder · Day 13 — Name one thing you trust
  them with today · Day 14 — Leave at five once, on purpose.
- **Week 3 — Build the System:** Day 15 — Give one piece of situation-behavior-impact feedback · Day 16 —
  Praise something specific in public · Day 17 — Audit your recurring meetings · Day 18 — Cancel or halve
  one meeting · Day 19 — Say no upward to protect focus · Day 20 — Give the team two hours of maker time ·
  Day 21 — Ask for feedback on yourself.
- **Week 4 — Multiply Yourself:** Day 22 — Let one small failure teach · Day 23 — Identify a fire only you
  can fight · Day 24 — Step back from a fire you don't own · Day 25 — Name your possible replacement · Day
  26 — Sponsor someone in a room they're not in · Day 27 — Grow one leadership rep in a teammate · Day 28 —
  Write what you want said when you leave the room · Day 29 — Hand off one thing permanently · Day 30 —
  Define your quiet authority in one sentence.

---

## 9. The 4x3x3 numbers (offer-book mode — authored under `run/433/`)

Only exercised in `mode: 4x3x3`; pinned here so `prove_bw_433.py` has golden targets (same author/book).

**Four Transformational Outcomes (PINNED — exactly 4; `AF-BK-433-COUNTS`):**
1. `From Star Performer to Team Multiplier`
2. `Trust That Runs the Team When You're Not in the Room`
3. `A Feedback Culture Without Fear`
4. `A Self-Sustaining System That Grows Leaders`

**Phase → chapter mapping (12 chapters = 4 phases × 3; `AF-BK-433-MAP`):**
| Phase | Outcome | Chapters |
|---|---|---|
| Phase 1 — Unlearn the Star | Outcome 1 | 1, 2, 3 |
| Phase 2 — Lead Through Others | Outcome 2 | 4, 5, 6 |
| Phase 3 — Build the System | Outcome 3 | 7, 8, 9 |
| Phase 4 — Multiply Yourself | Outcome 4 | 10, 11, 12 |

**30 program-title options (PINNED — exactly 30; `AF-BK-433-COUNTS`)** authored to `run/433/41-30-titles.md`,
delivered as `30_Titles-Marcus_Halloway.md`:
1. The Quiet Authority 2. Trade Control for Trust 3. The Multiplier Manager 4. Stop Being the Bottleneck
5. Lead Through Others 6. The First-Time Manager's Reset 7. From Star to Steward 8. The Trust Equation
9. Quiet Authority Method 10. The Un-Bottleneck Playbook 11. Manage Like a Multiplier 12. The Room You
Leave Behind 13. Earned Authority 14. The New Manager's 30 Days 15. Ship Without You 16. The Delegation
Ladder 17. Feedback Without Fear 18. The Manager Who Multiplies 19. Grow Your Replacement 20. The Calm
Command Method 21. Beyond the Best Coder 22. The Human Side of the Promotion 23. Trust Compounds, Control
Decays 24. The Team That Promotes Itself 25. Lead Quiet, Ship Loud 26. The Multiplier Reset 27. From
Answers to Questions 28. The Unforced Leader 29. Authority You Never Have to Assert 30. The Quiet
Authority System

**`run/433/433_Deck_Data.json` (PINNED schema — handed to Skill 51):**
```json
{
  "ProductName": "The Quiet Authority System",
  "BrandName": "Marcus Halloway",
  "ShortMDM": "A 30-day method that turns a first-time technical manager from the team bottleneck into a leader who multiplies everyone around them.",
  "BookTitle": "The Quiet Authority",
  "BookSubtitle": "How the Best New Leaders Trade Control for Trust",
  "outcomes": [
    "From Star Performer to Team Multiplier",
    "Trust That Runs the Team When You're Not in the Room",
    "A Feedback Culture Without Fear",
    "A Self-Sustaining System That Grows Leaders"
  ],
  "phases": [
    {"title": "Unlearn the Star",       "outcome": "From Star Performer to Team Multiplier",              "chapters": ["The Promotion That Broke You", "Why Your Old Superpower Now Fails", "The Myth of the Indispensable Leader"]},
    {"title": "Lead Through Others",     "outcome": "Trust That Runs the Team When You're Not in the Room", "chapters": ["Listening Louder Than You Speak", "Delegation Is Not Abandonment", "The Trust Equation"]},
    {"title": "Build the System",        "outcome": "A Feedback Culture Without Fear",                     "chapters": ["Feedback Without Fear", "Running Meetings People Don't Dread", "Protecting Your Team's Focus"]},
    {"title": "Multiply Yourself",       "outcome": "A Self-Sustaining System That Grows Leaders",         "chapters": ["When to Step In, When to Step Back", "Growing Leaders, Not Followers", "The Legacy of Quiet Authority"]}
  ]
}
```

---

## 10. GOLDEN LAYOUT — exact relative paths (all under `53-book-writer/examples/golden-marcus-halloway/`)

Two zones: **authored** (Wave-2 prose authors write these) and **assembled** (Agent D runs
`run_book_writer.py` which reads the authored zone, assembles the delivery bundle, runs all provers,
and mints the certificate). Paths are relative to the golden example dir.

### 10a. Authored zone — `run/` (Wave-2 writes; DATA anchors already shipped by Agent A)
| Path | Author | Floor / rule |
|---|---|---|
| `run/intake.json` | A (shipped) | mirrors §2; `version=book`, `mode=full` |
| `run/stories.json` | A (shipped) | §6 pinned key phrases + chapters |
| `run/artifacts/01-avatar.md` | Wave-2 | avatar dossier (§3) |
| `run/artifacts/08-blended-tone.md` | Wave-2 | "The Marcus Halloway Tone", **≥3000 stripped words** |
| `run/artifacts/10-suggested-titles.md` | Wave-2 | title candidates; LOCKED title present |
| `run/artifacts/APPROVED-TITLE.txt` | A (shipped) | LOCKED title + subtitle + GATE-1 receipt id (§11) |
| `run/artifacts/11-blurb.md` | Wave-2 | jacket blurb; LOCKED title+subtitle byte-exact |
| `run/artifacts/12-chapter-titles.md` | Wave-2 | the 12 titles (§5), byte-exact |
| `run/artifacts/13-outline.md` | Wave-2 | full outline (§7); both story key phrases; LOCKED title |
| `run/chapters/ch01.md` … `run/chapters/ch12.md` | Wave-2 | each **2000–3500 stripped words**; heading = §5 title; ch01 has STORY-A, ch06 has STORY-B, all echo LOCKED title on title/running line |
| `run/artifacts/21-30day-challenge.md` | Wave-2 | **exactly 30** `Day <n> —` sections (§8) |
| `run/artifacts/22-cover-prompt.md` | Wave-2 | cover prompt; LOCKED title byte-exact |
| `run/receipts/G-STAGE-15-chapters-b1.json` … `-b4.json` | Wave-2 / D | continuity: each batch receipt records sha256 of every prior chapter embedded (§ `AF-BK-CONTINUITY`) |
| `run/RUN-LEDGER.json` | D | one entry per stage: status/model/tokens/sha256; **no `/anthropic|claude/i` model id** |
| `run/433/41-30-titles.md` | Wave-2 (4x3x3) | exactly 30 titles (§9) |
| `run/433/42-outcomes.md` | Wave-2 (4x3x3) | exactly 4 outcomes (§9) |
| `run/433/43-kp-document.md` | Wave-2 (4x3x3) | knowledge-product doc |
| `run/433/433_Deck_Data.json` | A (shipped) | §9 schema; 4 phases × 3 chapters |
| `run/433/433_Deck_Outline.md` | Wave-2 (4x3x3) | deck outline handed to Skill 51 |

### 10b. Assembled zone — `delivery/Marcus_Halloway-Book/` (Agent D via `run_book_writer.py`)
| Path | Source |
|---|---|
| `delivery/Marcus_Halloway-Book/Avatar_Document-Marcus_Halloway.md` | copy of `run/artifacts/01-avatar.md` |
| `delivery/Marcus_Halloway-Book/Tone_Communication_Style_Analysis-Marcus_Halloway.md` | copy of `08-blended-tone.md` |
| `delivery/Marcus_Halloway-Book/Suggested_Titles-Marcus_Halloway.md` | copy of `10-suggested-titles.md` |
| `delivery/Marcus_Halloway-Book/APPROVED-TITLE.txt` | copy of `APPROVED-TITLE.txt` |
| `delivery/Marcus_Halloway-Book/Book_Blurb_and_Chapter_Titles-Marcus_Halloway.md` | assembled from `11-blurb.md` + `12-chapter-titles.md` |
| `delivery/Marcus_Halloway-Book/APPROVED-OUTLINE.md` | copy of `13-outline.md` |
| `delivery/Marcus_Halloway-Book/The_Quiet_Authority-Manuscript.md` | deterministic concat of `chapters/ch01..ch12.md` + title page |
| `delivery/Marcus_Halloway-Book/chapters/ch01.md` … `ch12.md` | copies of `run/chapters/*` |
| `delivery/Marcus_Halloway-Book/30_Day_Challenge-Marcus_Halloway.md` | copy of `21-30day-challenge.md` |
| `delivery/Marcus_Halloway-Book/Book_Cover_Prompt.md` | copy of `22-cover-prompt.md` |
| `delivery/Marcus_Halloway-Book/00-INDEX.md` | assembled (what each file is) |
| `delivery/Marcus_Halloway-Book/MANIFEST.json` | assembled (files, sha256, word counts, receipts, certificate id) |
| `delivery/Marcus_Halloway-Book/PROCESS-CERTIFICATE.json` | minted by `run_book_writer.py` on a full pass |
| `delivery/Marcus_Halloway-Book/PROCESS-CERTIFICATE.md` | minted alongside the JSON |
| `delivery/Marcus_Halloway-Book/433/…` | 4x3x3 extras (only on a 4x3x3 assemble) |

### 10c. Broken-variants — `broken-variants/`
`make_broken.py` (authored by A, RUN by Agent D once golden prose exists) derives **one fixture per
AF-BK code** by single-defect mutation of the authored zone, and writes `REJECTION-RESULTS.json`
mapping each variant → `{prover, expected_code, rc, rejected, got_codes}`.

---

## 11. `run/artifacts/APPROVED-TITLE.txt` (PINNED — byte-exact, shipped by Agent A)

```
TITLE: The Quiet Authority
SUBTITLE: How the Best New Leaders Trade Control for Trust
LOCKED_BY: GATE-1-title
APPROVED_BY: Marcus Halloway (author, in-chat checkpoint)
```

---

## 12. Floors table (every artifact must hit — `prove_bw_*` enforce)

| Artifact | Floor / exact count | Prover → AF code |
|---|---|---|
| Each chapter `chNN.md` | **2000–3500 stripped words** | `prove_bw_chapters.py` → `AF-BK-CHAP-LEN` |
| Chapter count | **exactly 12** | `prove_bw_chapters.py` → `AF-BK-CHAP-COUNT` |
| Blended tone `08-blended-tone.md` | **≥ 3000 stripped words** | `prove_bw_tone.py` → `AF-BK-TONE-LEN` |
| 30-Day Challenge | **exactly 30** `Day <n> —` sections | `prove_bw_challenge.py` → `AF-BK-CHALLENGE` |
| Title/subtitle echo | **byte-exact** in blurb, outline, every chapter, cover prompt, manuscript | `prove_bw_titlelock.py` → `AF-BK-TITLE-LOCK` |
| Personal stories | each non-N/A key phrase in outline AND manuscript | `prove_bw_stories.py` → `AF-BK-STORIES` |
| Batch continuity | batch N receipt records sha256 of every prior chapter | `prove_bw_continuity.py` → `AF-BK-CONTINUITY` |
| 4x3x3 counts | exactly 4 outcomes AND 30 titles | `prove_bw_433.py` → `AF-BK-433-COUNTS` |
| 4x3x3 map | 12 chapters = 4 phases × 3; deck-data schema-valid | `prove_bw_433.py` → `AF-BK-433-MAP` |
| Any artifact | no unresolved `{{…}}` / `$('…')` tokens | `prove_bw_placeholder.py` → `AF-BK-PLACEHOLDER` |
| RUN-LEDGER model ids | none match `/anthropic\|claude/i` | `prove_bw_noanthropic.py` → `AF-BK-ANTHROPIC` |
| All files + metadata | no configured client-name token | `prove_bw_anon.py` → `AF-BK-ANON` |

**Stripped word counting is deterministic (`_bw_common.word_count`)** — markdown syntax and whitespace
are removed before counting, so padding a short chapter with blank lines cannot fake a floor.
