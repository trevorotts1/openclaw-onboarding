# MODULE: BOOK TEASER (Pipeline Step 13)

Part of the Podcast Production Engine (skill 58). This module owns Step 13 of the
canonical 18-step pipeline: the bonus book teaser. It is the coup de grace of the
SHUA experience (Seen, Heard, Understood, Acknowledged) for the interview-style
lead generation path.

Writing law binding on this module and on everything it produces: zero em dash
characters anywhere, no triple backtick fences in any produced PDF, HTML, JSON, or
script output, and loop-engineering framing throughout.

---

## 1. WHEN IT RUNS, AND WHEN IT NEVER RUNS

INTERVIEW MODE ONLY. The teaser is produced only for Interview Style participants
(mode `interview_style_podcast`, the INTERVIEW output-type preset). Personal
Podcast episodes (`personal_podcast_style`, the SOLO preset) SKIP this step
entirely: no write, no render, no field, no delivery-report line beyond a note
that Personal mode has no teaser. The SEASON-STRATEGY preset produces no episode
and no teaser. The EPISODE ASSET PACK preset MAY regenerate the teaser for an
existing interview episode, idempotently against the ledger.

The mode guard is a hard branch in the pipeline, not a soft preference. If mode is
anything other than interview_style_podcast, Step 13 returns immediately and the
state machine advances to Step 14 with `teaser: skipped (personal mode)`.

---

## 2. WHAT THE TEASER IS

Using the person's survey answers, their improved answers from the Research
Assistant stage (Step 3, frozen), and the verified web research collected about
them, write the intro to the opening chapter of a book that could be theirs.

The framing presented to the person (by Convert and Flow messaging, never by this
agent) is that we loved the podcast so much that our ghostwriters drafted the intro
to what we believe could be their best-selling book, and we would love to discuss
it and at the very least invite them into our book anthology. The teaser must be
unbelievably enticing and end on an obvious cliffhanger that makes the person want
to finish the book, with us.

Do not give away the whole farm. This is a first-chapter teaser only. It is not a
full chapter and it is not the whole book. Elevate and hold back.

---

## 3. LENGTH, VOICE, AND LAYOUT

LENGTH: no more than three pages. Thin material means a tight, potent teaser, never
padding to fill a page. The three-page cap is enforced mechanically by the renderer
(Section 6); over the cap fails and the writer trims, and the renderer never
silently truncates.

VOICE: the person's own voice and tone, taken from their stated tone and their
answers. Write it as a compelling first-person book opening, not a summary and not
a podcast script. It should read like the beginning of a real, publishable book.
Pronoun and honorific usage follows `contact.my_preferred_pronoun` exactly, the
same governing rule as the episode script; nothing is guessed or defaulted.

LAYOUT: a PDF laid out like a real book. Tasteful larger lettering for the title
and the opening, book-style paragraph indentation, generous leading, and book
typography best practices so it looks genuinely beautiful at a glance. No font
smaller than 14 point, and the average body font is about 14 point or larger. The
pinned print stylesheet lives inside the renderer so the floor cannot drift.

---

## 4. THE WRITING MODEL (RUNTIME CONTENT TIER)

The teaser prose is written on the runtime content tier, thinking set to high,
consistent with the skill's `models.content` routing policy in
`config/models.yaml`:

  1. Kimi 2.6 on Ollama Cloud (thinking high)
  2. GLM 5.2 on Ollama Cloud (thinking high)
  3. the OpenRouter equivalents of the two, in the same order
  4. Gemini 3.1 Flash Lite as the final fallback (default thinking)

Fall back through that priority order when a tier is unavailable, and record any
substitution in the delivery report. The router refuses any model id on the
`deny_patterns` list; a substitution that would match the deny list is a hard
error, never a fallback. Nothing from the build-time provider ever writes a
client teaser; that boundary is enforced at the merge gate by
`guard-no-anthropic-runtime.py`, not by prose.

The rendering step (Section 6) makes NO model call at all. Writing is the only
billable part of this module, and it draws from the shared per-episode content
token budget; the render is deterministic and costs 0.00 dollars.

---

## 5. FABRICATION BOUNDARY (HARD)

The teaser is built ONLY from what the person actually shared plus verified
research. Do not invent biographical facts, achievements, dates, institutions, or
a fake life story. Elevate and dramatize the truth into a captivating opening;
never fabricate it. A cinematic retelling of a real moment is welcome; a fictional
event is forbidden.

This is the same no-fabrication standard as episode Tier 1 check 12. The renderer
cannot judge fabrication (that is semantic); the fabrication call is made by the
qc-specialist-podcast persona on the judge tier, distinct from the writer, before
the teaser is accepted. A fabrication failure on the teaser is handled like any
episode fabrication failure: it may unlock at most one supplemental research pass
of four calls, once per episode, and the teaser is rewritten from verified ground.

---

## 6. RENDER AND VERIFY (scripts/render_book_teaser.py)

The renderer is a deterministic typesetter and verifier. It takes teaser prose
that was already written on the content tier and lays it out as a book-typeset PDF.
It writes no prose, makes no model call, opens no network socket, and touches no
MCP tier. Same input, same layout. Its runtime cost is 0.00 dollars.

INPUT: a content file. JSON is preferred and carries the metadata and the ordered
paragraphs; a plain `.md` or `.txt` file is also accepted with metadata passed as
flags. JSON fields: `person_name`, `book_title`, `chapter_label`,
`chapter_title`, `episode_title`, and either `paragraphs` (an ordered list) or
`body` (a blank-line-separated string).

INVOCATION (from the skill directory):

    python3 scripts/render_book_teaser.py \
      --content run/artifacts/teaser.json \
      --out run/artifacts/teaser.pdf --json

BACKENDS, cheapest reliable first, auto-detected:

  - weasyprint, the fleet PDF toolchain reused from the Book Writer skill (53)
  - Chrome or Chromium headless print-to-pdf, the automatic fallback
  - if neither is present the typeset HTML is written as a degraded artifact and
    the script exits 4 so the pipeline surfaces the limitation honestly and never
    fakes a pass

The generate, verify, retry posture is reused from the Skill 35 render script:
transient render failures retry the backend; a render that succeeds but fails
verification advances to the next backend rather than re-rendering identical
output.

MECHANICAL CHECKS OWNED BY THIS MODULE (the renderer proves them from the rendered
PDF, not from trust):

  - the PDF opens and is non-empty
  - at most three pages (independently counted; over the cap fails)
  - no font below 14 point (the smallest text span is measured directly from the
    PDF with pymupdf, with a poppler or pypdf page-count fallback)
  - zero em dash characters and zero triple backtick fences in the teaser text
    (checked before rendering so a bad draft fails cheap)
  - the pinned stylesheet self-check refuses to run if any declared font-size
    ever drops below the 14 point floor

EXIT CODES: 0 pass, 2 a text or PDF mechanical check failed, 3 usage or IO error,
4 no PDF backend available (HTML emitted, PDF not rendered). The renderer prints a
JSON verdict (pages, min font, backend, bytes, checks, advisory hints) with no code
fences for the pipeline to consume.

SEMANTIC CHECKS OWNED BY THE EPISODE GATE, not this renderer: own-voice fidelity,
the obvious cliffhanger, and the fabrication boundary. The renderer emits an
advisory cliffhanger hint only; it never gates on it.

---

## 7. STORAGE AND LINK-BACK

STORE (Step 14): upload the finished PDF to the client's Convert and Flow media
storage, in the same podcast folder area used for the other episode assets
(podcast, podcast images, podcast episodes; create-once, reuse-forever, case
insensitive). The upload is a Tier 3 direct REST multipart call
(`POST /medias/upload-file`), never an MCP tier, because sub-agents get no MCP
injection. HEAD-verify the returned public URL before it is trusted.

LINK-BACK (Step 16): write the captured media URL into the contact custom field
named `book_teaser`. The teaser link is written in the batched field write, never
in the same call as `contact.podcast_survey_episode_url`, which is written alone
and last because it is a live customer-facing workflow trigger. Read every write
back byte-for-byte.

FOUNDER REMINDER: the `book_teaser` custom field may not exist yet. Surface a
founder reminder at onboarding to create a custom field named `book_teaser`. Never
silently create it. If the field is absent at run time, note it in the delivery
report and continue; a missing `book_teaser` field NEVER fails the episode. The
teaser PDF is still produced, stored, and reported even when the field is absent.

---

## 8. DELIVERY REPORT (OPERATOR CHANNEL ONLY)

The teaser PDF and its media URL are part of the deliverable. The delivery report,
sent to the operator channel only and never to the customer and never inside the
episode script, records: teaser produced yes or no, the writing model used
(including any substitution), page count, minimum measured font size, the media
library location and public URL, whether the `book_teaser` field was present and
written or surfaced as a founder reminder, and the completed teaser checklist
lines. MOVE IN SILENCE: this module emits zero client-facing messages. Convert and
Flow owns every customer message.

---

## 9. STATE, COST, AND FAILURE POSTURE

STATE: Step 13 runs inside the `documents` to `publishing` span of the state
machine; every transition is recorded through the sole writer `podcast_state.py`
so the dashboard and kanban read it, never recompute it.

COST: writing draws from the shared per-episode content token budget metered by
`podcast-cost-ledger.py`; the render is 0.00 dollars. A cost ceiling trip moves the
job to `cost_hold`, not a silent drop.

FAILURE POSTURE: a delayed teaser is acceptable, a lost one is not. A render
toolchain absence (exit 4) is surfaced honestly and the HTML artifact is retained.
A mechanical verification failure (exit 2) returns the teaser to the writer for a
targeted trim or fix, reusing the frozen research package. Nothing about the teaser
relaxes the episode standards.

---

## 10. CHECKLIST (reproduced in the delivery report; Interview mode only)

- [ ] Teaser written (at most three pages) from answers, improved answers, and
      verified research, in the person's own first-person voice, ending on a
      cliffhanger, on the content tier (Kimi 2.6 then GLM 5.2, thinking high).
- [ ] No fabricated biography, achievement, institution, date, or life story.
- [ ] Rendered as a book-typeset PDF, no font below 14 point, three pages or fewer,
      verified from the rendered PDF by scripts/render_book_teaser.py.
- [ ] PDF uploaded to Convert and Flow media storage (Tier 3 REST); public URL
      HEAD-verified.
- [ ] Link written to the `book_teaser` field, or the founder reminder surfaced if
      the field is absent (never silently created, never fails the episode).
- [ ] Personal Podcast mode: this entire step skipped, and the skip recorded.

---

## 11. ENFORCEMENT POINTERS

- Mechanical floor and page cap: `scripts/render_book_teaser.py` (exit 2 on breach).
- Build-time-provider runtime boundary: `guard-no-anthropic-runtime.py` at the
  merge gate (zero build-time provider model ids, providers, imports, hosts, or
  env keys in any shipped runtime file).
- Fabrication, voice, and cliffhanger: the episode gate (Tier 1 check 12 plus the
  10-dimension rubric) via `qc-tier1-mechanical.py` and the judge tier, with
  `qc-attempt-gate.py` owning the three-strike cap.
- SOP: this module is the enforcement target of SOP Book Teaser (PRD Section 13),
  which without this gate would be only a suggestion.
