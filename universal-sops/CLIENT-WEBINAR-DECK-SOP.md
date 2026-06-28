# CLIENT WEBINAR DECK SOP — DETERMINISTIC PIPELINE
**Standard Operating Procedure — Branded Webinar / Slide Deck, End-to-End**
**Version 2.0 — 2026-06-16 (deterministic-pipeline rewrite)**
**Audience:** the Presentations builder ("Slate") and any sub-agent that builds a deck.
**Owner role:** Director of Presentations (authority); QC Specialist (gate).

> **THE ONE WAY A DECK IS BUILT.** This SOP is DETERMINISTIC. The builder writes a single
> `slides.json` file and runs `scripts/build_deck.py`. The script — not the builder —
> renders every image on KIE.ai, verifies each PNG, and assembles the `.pptx`. **The builder
> has NO image tool and CANNOT generate images itself.** Any image produced by the native
> `image_generate` tool, by an inline KIE.ai HTTP call, by the dead endpoint
> `/api/v1/image/gpt-image`, or by hand/stock/placeholder is an immediate FAIL (AF-I14).
>
> The literal step-by-step procedure the builder follows is in **`../BUILDER-PROMPT.md`**.
> Read it first on every deck task. This SOP is the procedure in DMAIC/checklist form so it
> can be pulled into the dispatch task message and gated at QC.

> **`build_deck.py` IS ONLY THE PHASE-4 RENDERER — A `.pptx` IS NOT A DELIVERED PRESENTATION.**
> The deterministic build above (`slides.json` -> `build_deck.py` -> `.pptx`) is the Phase-4
> image render + bare-deck assembler ONLY. It produces NO research, NO copy QC, NO presenter
> guide, NO presenter speech, NO presenter audio, NO PDF export, NO infographic PNG, and NO GHL
> upload. **Finishing "at a `.pptx`" is a forbidden shortcut.** A deck is DELIVERED only when
> the FULL experience exists: the **SIX-FILE deliverable bundle** —
>
> | File | Minimum size | Produced by |
> |---|---|---|
> | `[Deck-Title]-FINAL.pptx` | > 1 MB | build_deck.py (PPTX Assembly) |
> | `[Deck-Title]-FINAL.pdf` | > 50 KB | PPTX Assembly Specialist (PDF export) |
> | `PRESENTER-GUIDE.pdf` | > 50 KB | Presenters Guide Specialist |
> | `PRESENTERS-SPEECH.md` | > 2 KB | Presenters Speech Writer |
> | `PRESENTERS-SPEECH.pdf` | > 20 KB | Presenters Speech Writer (PDF render) |
> | `PRESENTER-AUDIO.mp3` | > 500 KB | Audio Demonstration Specialist |
>
> **PLUS** `infographic.png` (> 100 KB — produced by infographic-checklist role).
>
> **DEFAULT OUTPUT DESTINATION: `~/Downloads/<client-slug>-<deck-slug>/`.**
> `build_deck.py` defaults all bundle files to `~/Downloads/<client-slug>-<deck-slug>/` — never
> to a scratch or run dir. Use `--out <dir>` to override. Client receives files from a
> predictable, clean location.
>
> **REPORT COMPLETE ONLY WHEN `deliverables.json` IS ALL-VERIFIED.**
> `build_deck.py` writes a `deliverables.json` ledger in the bundle dir, updated incrementally
> (crash-safe + resume-safe). The POSTFLIGHT COMPLETENESS GATE (AF-BUNDLE-COMPLETE) reads
> `deliverables.json` — not in-memory state — and hard-fails (exit 5) if any artifact is
> absent or below its size threshold. Print "COMPLETE" / "DONE" ONLY when the gate passes
> (exit 0) and `deliverables.json` shows every entry as `"status": "verified"`.
> `PRESENTER-GUIDE.pdf` and `infographic.png` can NEVER be silently skipped — their absence
> is always an AF-BUNDLE-COMPLETE hard-fail at exit 5.
>
> The Director/Delivery flow MUST run the Presenters Guide Specialist, Presenters Speech Writer,
> Audio Demonstration Specialist, PPTX Assembly Specialist (PDF export + infographic PNG), and
> the Media Librarian / Delivery Concierge (GHL upload) before any "Done." This is gated by the
> POSTFLIGHT COMPLETENESS GATE (AF-BUNDLE-COMPLETE) AND the DELIVERY INTERLOCK:
> **AF-DELIVER** (presenter artifacts exist) + **AF-DH1** (bundle hygiene) +
> **AF-DELIVERY-COMPLETE** (the consolidating Done-gate). All must pass. The Command Center QC
> scorer mirrors AF-DELIVERY-COMPLETE and blocks review->Done independently.

---

## 0. THE TRUE GOAL — ATTENTION IS THE PRODUCT (read before §1)

> **This section governs everything below it. §1 ("produce a branded deck") is the SURFACE
> goal — the activity. This section is the TRUE goal — the purpose. When the two ever appear
> to conflict, the true goal wins.** A correct, complete, on-brand deck that does not do the
> following has still FAILED. Never confuse the activity (producing a deck) with the purpose.

**The #1 job of every presentation is to HOLD THE AUDIENCE'S ATTENTION for the entire
duration** — 15 minutes, 90 minutes, or 4 hours; the length is irrelevant. Attention is
rented every second and re-won every slide. You cannot teach, sell, or move a mind you have
lost. Holding attention is therefore the necessary condition for everything else this SOP
builds.

**Attention is in service of ONE true goal: the PRIORITY SHIFT.** Every deck exists to
re-rank the owner's offer or idea to the **top of the audience's existing priority stack**, so
that buying or acting becomes the natural consequence. People always find resources — money,
time, attention — for what they have decided matters most; what is usually missing is not the
resource but the ranking. The deck's job is to reach into the audience's existing list and pull
the owner's thing to number one. (This plugs into the existing belief-shift / villain→hero /
felt-stakes / cost-of-inaction machinery already wired below — it is the destination those
mechanics drive toward.)

**The creativity of the imagery is the ENGINE that holds attention.** The single most vivid
thing in the room is the thing the mind prioritizes (von Restorff / salience). That is *why*
this department spends its largest budget on image creation and refuses corporate,
seen-it-before, safe decks — and why "just a background with text" is an auto-fail. **The two
roles that win attention are the DESIGNER (creative, gallery-grade imagery) and the CONTENT
author (attention-snatching copy that dares to challenge the norm).** Every other role — price
ladder, hook, QC gates, delivery — exists to PROTECT the attention those two earn.

**Acceptance test (the deck ships only if both are true):**
1. It engineers a deliberate **peak** and a deliberate **ending** (peak-end rule). A flat
   ending is remembered as flat.
2. **The owner's thing is the single most vivid element in the room by the end.**

**Canonical doctrine home:** the North Star — `presentations/sops/SOP-NORTHSTAR-00` (when
present) and the *Powerful Presentation Framework*. The mechanics that execute it are the live
SOP/engine stack in §§3–7 below.

---

## 1. PURPOSE

Produce a complete, branded, webinar-ready slide deck with ZERO ad-hoc image generation.
The deck's words, scenes, and layout are decided by the builder and written to `slides.json`;
every pixel is rendered by `scripts/build_deck.py`. There is exactly ONE renderer and ONE
assembler, and it is the script.

**Non-negotiables (memorize before starting):**
- The builder writes ONE file — `slides.json` — and runs ONE command — `build_deck.py`.
- The builder NEVER generates, edits, fetches, or substitutes an image. It has no image tool.
- The builder NEVER writes an inline KIE.ai HTTP call and NEVER touches `/api/v1/image/gpt-image`.
- There are NO placeholder/stock slides. A render that fails after the script's retries is a
  build failure to report — never something the builder patches around.
- The deliverable registered + reported is the EXACT `.pptx` `build_deck.py` produced, and
  ONLY when the script exited 0.
- 16:9, 2K, `gpt-image-2-text-to-image` — all enforced INSIDE the script; the builder does
  not choose or pass any of them.
- Client's OWN `KIE_API_KEY` — the script reads it from the client/dept env stores itself;
  the builder never handles the key.

---

## 2. THE PIPELINE (the only path)

```
source material  ──▶  STEP 1: builder writes slides.json
                       (slides, scenes, EXACT copy; per scripts/slides.schema.json)
                              │
                              ▼
                 STEP 2: builder runs  python3 scripts/build_deck.py slides.json out.pptx
                              │   (the script does ALL of this — the builder does none of it:)
                              │     • mechanically composes the KIE prompt per slide
                              │       (scene + verbatim copy + logo + layout + English pin)
                              │     • POST /api/v1/jobs/createTask  (gpt-image-2-text-to-image, 16:9, 2K)
                              │     • GET  /api/v1/jobs/recordInfo?taskId=…  until state=success
                              │     • parse data.resultJson → resultUrls[0] → download PNG (unauth)
                              │     • verify PNG magic bytes + size; retry a slide up to 3×
                              │     • assemble full-bleed .pptx (no text boxes); FAIL LOUD on any gap
                              ▼
                 STEP 3: builder registers the EXACT outputPath (.pptx) from the script summary
                              ▼
                 STEP 4: QC runs on the registered .pptx (the real artifact)
```

The script prints a JSON summary the builder acts on:
```json
{ "slidesRendered": N, "kieTaskIds": ["..."], "outputPath": ".../presentation.pptx", "failures": [] }
```
- exit `0` + `failures: []` → built; `outputPath` is the deliverable.
- exit `1` → one or more slides failed (NO `.pptx`) or assembly failed; read `failures`.
- exit `2` → fatal config (no `KIE_API_KEY`, bad `slides.json`, `python-pptx` missing).

---

## 3. STEP 1 — WRITE `slides.json` (DMAIC)

**Define.** From the task title + description + any SOP steps, decide: deck title, slide
count, audience/tone/key messages, and the price-drop arc if this is an offer deck (see §6).
Slide count is CONTENT-DRIVEN — inventory every substantive point in the source and give
each its own slide (one big idea per slide). There is NO automatic ceiling; the deck is as
long as the content warrants and compressing a rich source is an AUTO-FAIL (AF-COVERAGE). A
maximum applies ONLY when an explicit `client_requested_slide_cap` is present in the task /
intake.json / mission_prd.json. Use 10 slides only as a fallback when the source genuinely
has no more substantive content than that — never as a cap on richer material.

**Measure / Analyze.** For each slide, decide the photographic `scene`, the EXACT `copy`
(the words that must appear, in reading order — index 0 is the headline), an optional `logo`
wordmark, and an optional `layout` hint.

**Improve (write the file).** Write a JSON array to `slides.json` per
`../scripts/slides.schema.json`. Each element:
```json
{
  "slide": 1,
  "scene": "A confident founder in a sunlit modern office, soft window light, warm neutral palette, shallow depth of field, 85mm, editorial photography.",
  "copy": ["Explore Growth", "Three moves that doubled our pipeline in 90 days"],
  "logo": "EXPLORE GROWTH",
  "layout": "headline lower-left over a soft dark gradient, subhead beneath, logo wordmark top-right"
}
```
Rules:
- `slide` — unique integer, starting at 1, contiguous. Sets order AND render filename.
- `scene` — describe a PHOTOGRAPH (subject, setting, light, mood, palette, framing). Never
  put slide wording in `scene`.
- `copy` — the EXACT text to appear, in reading order. **Spell every word correctly,
  letter-for-letter.** The script renders it verbatim into the image; it will not fix
  spelling or reword. Keep lines short (slide copy, not paragraphs).
- `logo` — optional brand wordmark. Omit if none.
- `layout` — optional placement hint. Omit for the script's safe default.

The builder does **NOT** write KIE prompts, pick a model, set aspect ratio/resolution, or
call any API. The script composes the prompt mechanically from `slides.json` and pins
`gpt-image-2-text-to-image` / 16:9 / 2K / English-Latin-only itself.

**Control.** Confirm `slides.json` is a single valid JSON array, ordinals are unique and
contiguous from 1, and every `copy[0]` is the intended headline with correct spelling.

---

## 4. STEP 2 — RUN THE BUILD SCRIPT

Run exactly (substitute the task's `ARTIFACT_DIR`):
```
python3 <WORKSPACE>/departments/Presentations/scripts/build_deck.py slides.json <ARTIFACT_DIR>/presentation.pptx
```
- The script renders every slide, retries up to 3× per slide, verifies each PNG, and
  assembles the `.pptx`. The builder watches the exit code and the JSON summary.
- **Exit 0 + empty `failures`** → proceed to Step 3 with `outputPath`.
- **Non-zero exit** → the build FAILED. Do NOT invent or substitute images. If `failures`
  shows a content/JSON problem, fix `slides.json` and re-run the script. If KIE is
  unreachable or a slide will not render after retries, report the failure (Step 5 of
  BUILDER-PROMPT.md / §7 here) — never fake a deliverable, never produce a placeholder.

**FORBIDDEN at this step (any one = immediate AF-I14 FAIL):**
- Generating an image with the native `image_generate` tool or any other image tool.
- Writing an inline KIE.ai HTTP call (curl/requests/urllib/fetch) instead of running the script.
- Using the dead endpoint `/api/v1/image/gpt-image`.
- Hand-editing PNGs or substituting any stock/placeholder image.
- Assembling a `.pptx` by hand.
- Reporting `TASK_COMPLETE` when the script exited non-zero.

---

## 5. STEP 3 — REGISTER THE `.pptx` THE SCRIPT PRODUCED

Register the EXACT `outputPath` from the script's summary (the `.pptx`) so the Kanban card
gets the REAL artifact and QC runs on it:
```
POST {missionControlUrl}/api/tasks/{task.id}/deliverables
{"deliverable_type": "artifact", "title": "presentation.pptx", "path": "<outputPath from build_deck.py summary>"}
```
Then log completion and advance status:
```
POST {missionControlUrl}/api/tasks/{task.id}/activities
{"activity_type": "completed", "message": "Built {N}-slide deck via build_deck.py: {title}. Output: {outputPath}. KIE task IDs: {kieTaskIds}"}

PATCH {missionControlUrl}/api/tasks/{task.id}
{"status": "review"}
```
Register NOTHING that the script did not produce. The path you register MUST equal the
`outputPath` the script printed.

---

## 6. OPTIONAL — OFFER / PRICE-DROP DECKS

If this is an offer/webinar deck, the `copy` arrays across the relevant slides must carry the
proven arc (promise → painful math → real-problem reframe → authority/proof → secrets →
value stack → anchor → successive justified drops → final price → guarantee → bonuses →
CTA). All of that lives in the `copy` you write — the price-drop logic is content, written
into `slides.json`. The script renders whatever you wrote; it does not invent or validate
prices. Confirm the price math and that drops end exactly at the client-approved final price
BEFORE you run the script. (Detailed pitch structure: see the SOP-PITCH-* series.)

---

## 7. FAILURE HANDLING (never fake a deliverable)

| Condition | Action |
|---|---|
| Script exit 1, `failures` shows bad JSON / empty `copy` / non-unique ordinal | Fix `slides.json`, re-run the script. |
| Script exit 1, a slide failed after 3 retries (KIE error/timeout) | Re-run the script once. If it persists, report the failure via the activities API; leave the task for the orchestrator. Do NOT substitute an image or report `TASK_COMPLETE`. |
| Script exit 1, KIE unreachable (network error) | Report the failure; do NOT switch tools, do NOT hand-make images. |
| Script exit 2, `python-pptx` missing | `pip3 install python-pptx`, re-run the script. |
| Script exit 2, `KIE_API_KEY` not found | Report a config error; the key belongs in the client/dept env stores the script searches. Never paste a key into a command. |

A "done" report without a verified `.pptx` from the script (exit 0) is a lie. Verify the file
exists at `outputPath` before reporting.

---

## 8. MASTER CHECKLIST (tick every box, in order)

```
[ ] 1.1  slides.json written: unique contiguous ordinals from 1; each slide has scene + copy
[ ] 1.2  Every copy[0] is the intended headline; ALL copy spelled correctly, verbatim
[ ] 1.3  slides.json parses as a single JSON array (validated)
[ ] 1.4  NO KIE prompt written by hand, NO model/aspect/resolution chosen by the builder
[ ] 2.1  Ran: python3 scripts/build_deck.py slides.json <ARTIFACT_DIR>/presentation.pptx
[ ] 2.2  NO native image_generate, NO inline KIE HTTP call, NO dead endpoint, NO hand/stock image
[ ] 2.3  Script exited 0 with failures: [] (else: handle per §7 — never fake)
[ ] 3.1  Registered the EXACT outputPath (.pptx) from the script summary as the deliverable
[ ] 3.2  Logged "completed" activity with N, outputPath, kieTaskIds
[ ] 3.3  PATCHed status → review
[ ] 4.1  Verified the .pptx exists at outputPath before reporting
[ ] 4.2  Replied TASK_COMPLETE only because the script exited 0
```

> **THIS CHECKLIST COMPLETES PHASE-4 (RENDER) ONLY — IT IS NOT DELIVERY.** A clean
> `build_deck.py` run + a registered `.pptx` means the deck is RENDERED, not DELIVERED. The
> deck is NOT done until the POSTFLIGHT COMPLETENESS GATE + DELIVERY INTERLOCK both pass.
> Hand off to the Director/Delivery flow:
> ```
> [ ] D.1  PRESENTER-GUIDE.pdf present in bundle dir (Presenters Guide Specialist) — >50KB; CANNOT be silently skipped
> [ ] D.2  PRESENTERS-SPEECH.md present (Presenters Speech Writer) — >2KB source
> [ ] D.3  PRESENTERS-SPEECH.pdf present (Presenters Speech Writer) — >20KB PDF render
> [ ] D.4  PRESENTER-AUDIO.mp3 present (Audio Demonstration Specialist) — Fish Audio S2, >500KB
> [ ] D.5  [Deck-Title]-FINAL.pdf present (PPTX Assembly Specialist PDF export) — >50KB
> [ ] D.6  infographic.png present in bundle dir (infographic-checklist role) — >100KB; CANNOT be silently skipped
> [ ] D.7  deliverables.json in bundle dir shows ALL 7 entries as "status": "verified"
> [ ] D.8  build_deck.py postflight completeness gate (AF-BUNDLE-COMPLETE) passed — exit 0, "=== COMPLETE ===" printed
> [ ] D.9  Bundle dir is ~/Downloads/<client-slug>-<deck-slug>/ (or --out override confirmed)
> [ ] D.10 Six-file bundle + AF-DH1 hygiene sweep passed (Delivery Concierge SOP 9.0)
> [ ] D.11 GHL media upload done + recorded (pptx_ghl_media_id) + ground-truth verified (Delivery Concierge SOP 9.2/9.4)
> [ ] D.12 AF-BUNDLE-COMPLETE + AF-DELIVER + AF-DH1 + AF-DELIVERY-COMPLETE all pass before "Done"
> ```
> A "Done" off a bare `.pptx` — with no guide, speech, audio, PDF, infographic PNG, or GHL
> upload — is an AF-BUNDLE-COMPLETE + AF-DELIVERY-COMPLETE failure and a false "done."
> REPORT "COMPLETE"/"DONE" ONLY when `deliverables.json` is all-verified (exit 0).

---

## 9. ENFORCEMENT (AF-I14)

QC scans the builder's runtime session trace (`~/.openclaw/agents/dept-presentations/sessions/`)
for the deterministic build path and for forbidden patterns. The build FAILS immediately if
the trace shows: the dead endpoint `/api/v1/image/gpt-image`; a native `image_generate`
invocation for a slide; an inline KIE.ai HTTP call written by the builder instead of running
the script; or a registered/reported artifact the script did not produce. The PASS condition
is a clean trace whose ONLY image path is `scripts/build_deck.py`, with the registered
deliverable equal to the script's `outputPath`. (Call-mechanics reference + the full check
table: `SOP-IMG-01-KIE-CALL-MECHANICS.md` check 10.)

AF-I14 gates the RENDER. It does NOT gate delivery — a clean AF-I14 trace plus a `.pptx`
is a rendered deck, not a delivered presentation.

---

## 9a. POSTFLIGHT COMPLETENESS GATE + DELIVERY INTERLOCK

### POSTFLIGHT COMPLETENESS GATE (AF-BUNDLE-COMPLETE)

`build_deck.py` enforces the six-file bundle via the POSTFLIGHT COMPLETENESS GATE
(AF-BUNDLE-COMPLETE), which runs automatically at the end of every `build_deck.py` execution.
The gate reads `deliverables.json` — written incrementally to the bundle dir throughout the
run — and hard-fails with **exit 5** if any artifact is absent or below its size threshold.
`PRESENTER-GUIDE.pdf` and `infographic.png` **can never be silently skipped** — their absence
always triggers exit 5. The script prints `=== COMPLETE ===` and exits 0 ONLY when all seven
entries in `deliverables.json` are `"status": "verified"`. A run that exits 5 may NOT be
reported as "done" or "complete."

**The SIX-FILE required bundle** (`~/Downloads/<client-slug>-<deck-slug>/` by default):
- `[Deck-Title]-FINAL.pptx` — > 1 MB — assembled deck (this script)
- `[Deck-Title]-FINAL.pdf` — > 50 KB — PDF export (PPTX Assembly Specialist)
- `PRESENTER-GUIDE.pdf` — > 50 KB — Presenters Guide Specialist **(HARD REQUIRED)**
- `PRESENTERS-SPEECH.md` — > 2 KB — Presenters Speech Writer
- `PRESENTERS-SPEECH.pdf` — > 20 KB — Presenters Speech Writer (PDF render)
- `PRESENTER-AUDIO.mp3` — > 500 KB — Audio Demonstration Specialist

**PLUS** `infographic.png` (> 100 KB — infographic-checklist role) **(HARD REQUIRED)**

`build_deck.py` does NOT produce PRESENTER-GUIDE.pdf, PRESENTERS-SPEECH.md/.pdf,
PRESENTER-AUDIO.mp3, or infographic.png — these are REQUIRED UPSTREAM STEPS. The gate
enforces that ALL of them exist before a run can complete successfully.

### DELIVERY INTERLOCK (AF-DELIVER + AF-DH1 + AF-DELIVERY-COMPLETE)

`build_deck.py` is ONLY the Phase-4 renderer. Even after the postflight completeness gate
passes, the closeout DELIVERY INTERLOCK must also pass before review->Done:

- **AF-DELIVER** — the presenter artifacts exist and are non-empty (PRESENTER-GUIDE.pdf,
  PRESENTERS-SPEECH.pdf, PRESENTER-AUDIO.mp3 > 500KB). See `SOP-PITCH-05-DELIVERABLE-BUNDLE.md`.
- **AF-DH1** — the client package `delivery/[DECK_SLUG]-FINAL/` contains EXACTLY the six
  allowed files and NO dev artifacts. Run by the Delivery Concierge at SOP 9.0.
- **AF-DELIVERY-COMPLETE** — the consolidating Done-gate: (1) the six-file bundle is complete
  and `deliverables.json` all-verified, (2) the infographic.png is present and verified, and
  (3) the GHL media upload is recorded (`pptx_ghl_media_id`) and ground-truth verified. See
  `SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md`.

> **BINDING — how GHL is touched.** The GoHighLevel media library is touched EXCLUSIVELY via the
> Tier-3 REST call `POST https://services.leadconnectorhq.com/medias/upload-file` (Version
> `2021-07-28`, multipart/form-data, optional `parentId`), authenticated with the CLIENT's GHL
> **LOCATION** Private Integration Token (NOT the agency token — the agency token returns 401 for
> media operations). The agent NEVER creates a GHL folder (the folder-create endpoint returns 404;
> folders are made by a human in the GHL UI and the id is passed as `parentId`, else upload to the
> shareable media root). Driving the GoHighLevel UI in a browser — agent-browser, Playwright, or any
> UI automation of GHL — is FORBIDDEN. Reference: `29-ghl-convert-and-flow/references/medias.md`.

The Director MUST run the Director/Delivery flow (guide + speech + audio + PDF export +
infographic PNG + GHL upload). The Director may NOT mark Done, register a final deliverable,
or notify the client off a bare `build_deck.py` `.pptx`. The Command Center QC scorer enforces
AF-DELIVERY-COMPLETE independently and blocks review->Done.

---

*End of SOP. The builder has no image tool. The script is the only renderer. If a live run
contradicts this document, stop and escalate to the Director — do not improvise around a hard
rule (one slides.json, one build_deck.py run, no self-generated images, register only the
script's output).*
