# SOP-PODCAST-06: BOOK TEASER

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Skill:** 58-podcast-production-engine (the Podcast Production Engine)
**Owning role:** director-of-podcast owns the run; qc-specialist-podcast owns the fabrication and cliffhanger call (distinct from the writer)
**Stage:** Pipeline Step 13 (the bonus asset), Interview mode ONLY
**Produces:** a book-typeset teaser PDF (three pages or fewer, no font below fourteen point), its media URL, and the `book_teaser` field write or the founder reminder
**Enforcement pointer:** `58-podcast-production-engine/modules/book-teaser.md` plus `58-podcast-production-engine/scripts/render_book_teaser.py` (the fourteen-point font floor and the three-page cap, verified from the rendered PDF, exit 2 on breach) AND the EPISODE gate (Tier 1 check 12 fabrication via `qc-tier1-mechanical.py` and the judge tier, with `qc-attempt-gate.py` owning the three-strike cap).

---

## 0. WHY THIS SOP EXISTS

For the interview-style lead generation path, the finished episode is a gift engineered to make the guest feel Seen, Heard, Understood, and Acknowledged, and the book teaser is the coup de grace of that experience. The framing presented to the person (by Convert and Flow messaging, never by this agent) is that we loved the podcast so much that our ghostwriters drafted the intro to what we believe could be their best-selling book, and we would love to invite them into our book anthology. Because that gift lands directly with a real person, its floor is not negotiable. This SOP is the procedure that keeps every teaser truthful, beautifully typeset, and bounded, and every rule below names the script and the threshold that proves it.

## 1. WHEN IT RUNS, AND WHEN IT NEVER RUNS

INTERVIEW MODE ONLY. The teaser is produced only for Interview Style participants (mode `interview_style_podcast`, the INTERVIEW preset). Personal Podcast episodes (`personal_podcast_style`, the SOLO preset) SKIP this step entirely: no write, no render, no field, and no delivery-report line beyond a note that Personal mode has no teaser. The SEASON-STRATEGY preset produces no episode and no teaser. The EPISODE ASSET PACK preset MAY regenerate the teaser for an existing interview episode, idempotently against the ledger.

The mode guard is a hard branch in the pipeline, not a soft preference. If mode is anything other than `interview_style_podcast`, Step 13 returns immediately and the state machine advances to Step 14 with the teaser recorded as skipped for Personal mode.

## 2. WHAT THE TEASER IS, AND ITS SHAPE

Using the person's survey answers, their improved answers from the frozen Research Assistant stage (Step 3), and the verified web research collected about them, write the intro to the opening chapter of a book that could be theirs. It must be unbelievably enticing and end on an obvious cliffhanger that makes the person want to finish the book, with us. Do not give away the whole farm: this is a first-chapter teaser only, not a full chapter and not the whole book. Elevate and hold back.

- LENGTH: no more than three pages. Thin material means a tight, potent teaser, never padding. The three-page cap is enforced mechanically by the renderer; over the cap fails and the writer trims, and the renderer never silently truncates.
- VOICE: the person's own first-person voice and tone, taken from their stated tone and their answers. It reads like the beginning of a real, publishable book, not a summary and not a podcast script. Pronoun and honorific usage follows `contact.my_preferred_pronoun` exactly, the same governing rule as the episode script; nothing is guessed or defaulted.
- LAYOUT: a PDF laid out like a real book, with tasteful larger lettering for the title and opening, book-style paragraph indentation, generous leading, and no font below fourteen point. The pinned print stylesheet lives inside the renderer so the floor cannot drift.

## 3. THE WRITING MODEL (RUNTIME CONTENT TIER)

The teaser prose is written on the runtime content tier, thinking set to high, consistent with the skill's content routing policy in `config/models.yaml`:

1. Kimi 2.6 on Ollama Cloud (thinking high)
2. GLM 5.2 on Ollama Cloud (thinking high)
3. the OpenRouter equivalents of the two, in the same order
4. Gemini 3.1 Flash Lite as the final fallback (default thinking)

Fall back through that priority order when a tier is unavailable, and record any substitution in the delivery report. The router refuses any model id on the deny-pattern list; a substitution that would match the deny list is a hard error, never a fallback. Nothing from the build-time provider ever writes a client teaser; that boundary is enforced at the merge gate by `guard-no-anthropic-runtime.py`, not by prose. The render step makes no model call at all, so writing is the only billable part of this module and it draws from the shared per-episode content-token budget.

## 4. THE FABRICATION BOUNDARY (HARD)

The teaser is built ONLY from what the person actually shared plus verified research. Do not invent biographical facts, achievements, dates, institutions, or a fake life story. A cinematic retelling of a real moment is welcome; a fictional event is forbidden. Elevate and dramatize the truth into a captivating opening; never fabricate it.

This is the same no-fabrication standard as episode Tier 1 check 12. The renderer cannot judge fabrication, because that is semantic; the fabrication call is made by the qc-specialist-podcast persona on the judge tier, distinct from the writer, before the teaser is accepted. A fabrication failure on the teaser is handled like any episode fabrication failure: it may unlock at most one supplemental research pass of four calls, once per episode, and the teaser is rewritten from verified ground.

## 5. RENDER AND VERIFY (THE MECHANICAL FLOOR)

`scripts/render_book_teaser.py` is a deterministic typesetter and verifier. It takes prose already written on the content tier and lays it out as a book-typeset PDF. It writes no prose, makes no model call, opens no network socket, and touches no MCP tier. Same input, same layout. Its runtime cost is zero dollars.

The mechanical checks it proves from the rendered PDF, not from trust:

- the PDF opens and is non-empty;
- at most three pages, independently counted; over the cap fails;
- no font below fourteen point, measured directly from the smallest text span in the PDF (with pymupdf, with a page-count fallback), so the floor is proven and not merely trusted from the stylesheet;
- zero em dash characters and zero triple backtick fences in the teaser text, checked before rendering so a bad draft fails cheap;
- the pinned stylesheet self-check refuses to run if any declared font size ever drops below the fourteen-point floor.

Backends are auto-detected, cheapest reliable first: weasyprint (the fleet PDF toolchain reused from the Book Writer skill), then Chrome or Chromium headless print-to-pdf. If neither is present, the typeset HTML is written as a degraded artifact and the script exits with the toolchain-absent code so the pipeline surfaces the limitation honestly and never fakes a pass. The generate-verify-retry posture is reused from the Skill 35 render script: transient render failures retry the backend, and a render that succeeds but fails verification advances to the next backend rather than re-rendering identical output.

Exit codes: 0 pass, 2 a text or PDF mechanical check failed, 3 usage or IO error, 4 no PDF backend available (HTML emitted, PDF not rendered). Own-voice fidelity, the obvious cliffhanger, and the fabrication boundary are SEMANTIC and belong to the episode gate; the renderer emits only advisory hints for them and never gates on them.

## 6. STORE, LINK-BACK, AND THE FOUNDER REMINDER

- STORE (Step 14): upload the finished PDF to the client's Convert and Flow media storage, in the same podcast folder area used for the other episode assets (podcast, podcast images, podcast episodes; create-once, reuse-forever, case-insensitive). The upload is a Tier 3 direct REST multipart call to the media upload-file endpoint, never an MCP tier, because sub-agents get no MCP injection. HEAD-verify the returned public URL before it is trusted.
- LINK-BACK (Step 16): write the captured media URL into the contact custom field named `book_teaser`. The teaser link is written in the batched field write, never in the same call as `contact.podcast_survey_episode_url`, which is written alone and last because it is a live customer-facing workflow trigger. Read every write back byte-for-byte.
- FOUNDER REMINDER: the `book_teaser` custom field may not exist yet. Surface a founder reminder at onboarding to create it. Never silently create it. If the field is absent at run time, note it in the delivery report and continue; a missing `book_teaser` field NEVER fails the episode. The teaser PDF is still produced, stored, and reported even when the field is absent.

## 7. STATE, COST, SILENCE, AND FAILURE POSTURE

- STATE: Step 13 runs inside the documents-to-publishing span of the state machine; every transition is recorded through the sole writer `podcast_state.py` so the dashboard and kanban read it and never recompute it.
- COST: writing draws from the shared per-episode content-token budget metered by `podcast-cost-ledger.py`; the render is zero dollars. A cost-ceiling trip moves the job to `cost_hold`, never a silent drop.
- SILENCE: this module emits zero client-facing messages. Convert and Flow owns every customer message. The delivery report goes to the operator channel only and never inside the episode script.
- FAILURE POSTURE: a delayed teaser is acceptable, a lost one is not. A render-toolchain absence (exit 4) is surfaced honestly and the HTML artifact is retained. A mechanical verification failure (exit 2) returns the teaser to the writer for a targeted trim or fix, reusing the frozen research package. Nothing about the teaser relaxes the episode standards.

## 8. TEASER CHECKLIST (reproduced in the delivery report; Interview mode only)

- [ ] Teaser written (at most three pages) from answers, improved answers, and verified research, in the person's own first-person voice, ending on a cliffhanger, on the content tier (Kimi 2.6 then GLM 5.2, thinking high).
- [ ] No fabricated biography, achievement, institution, date, or life story.
- [ ] Rendered as a book-typeset PDF, no font below fourteen point, three pages or fewer, verified from the rendered PDF by `render_book_teaser.py`.
- [ ] PDF uploaded to Convert and Flow media storage via Tier 3 REST; public URL HEAD-verified.
- [ ] Link written to the `book_teaser` field, or the founder reminder surfaced if the field is absent (never silently created, never fails the episode).
- [ ] Personal Podcast mode: this entire step skipped, and the skip recorded.

## 9. OPERATOR RUNBOOK (PROVE THE FLOOR)

- Render and verify a fixture teaser, proving the fourteen-point floor and the three-page cap end to end:

      python3 58-podcast-production-engine/scripts/render_book_teaser.py --self-test

  A pass means either a PDF backend proved the floor (exit 0) or no backend exists on this box (exit 4) but the text law held and the typeset HTML was written.

- Render a real teaser and read the JSON verdict (pages, minimum font, backend, checks) with no code fences:

      python3 58-podcast-production-engine/scripts/render_book_teaser.py --content teaser.json --out teaser.pdf --json

## 10. ENFORCEMENT POINTER (BINDING)

- Mechanical floor and page cap: `58-podcast-production-engine/scripts/render_book_teaser.py` (exit 2 on a breach of the fourteen-point font floor, the three-page cap, or the em-dash and fence text law), driven by `58-podcast-production-engine/modules/book-teaser.md`.
- Build-time-provider runtime boundary: `58-podcast-production-engine/scripts/guard-no-anthropic-runtime.py` at the merge gate (zero build-time-provider model ids, providers, imports, hosts, or env keys in any shipped runtime file).
- Fabrication, voice, and cliffhanger: the EPISODE gate (Tier 1 check 12 plus the ten-dimension rubric) via `qc-tier1-mechanical.py` and the judge tier, with `qc-attempt-gate.py` owning the three-strike cap. This is Gate B, never the 8.5 build gate.
- Without these gates this document would be only a suggestion.
