# DEPARTMENT COUNTS — CANONICAL

**This is the single authoritative page for the Presentations department's deliverable counts and step
counts.** Every other document in this department (00-START-HERE.md, BUILDER-PROMPT.md,
how-to-use-this-department.md, CLIENT-WEBINAR-DECK-SOP.md, MASTER-QC-AUTOFAIL-RULESET.md,
PRESENTATION-MASTER-DOCTRINE.md, delivery_gate.py's docstring, etc.) must **LINK HERE** rather than
restate any of the numbers below. If a number ever needs to change, it changes in exactly one place.

Every claim below was verified against the code in this worktree on 2026-08-19 (Unit A10, RUN 2),
not copied from prose. Where a proving command is shown, it was actually run against the files in
this worktree — `DEPT` = `23-ai-workforce-blueprint/templates/role-library/presentations` (this
department's root), `SOPS` = `universal-sops`, both relative to the repo root.

**Not the same "10":** 00-START-HERE.md also has "The Ten Required Presentation Components" (Promise,
Hook, Case Studies, Wall of Wins, One Big Idea Per Slide, Guarantee, Scarcity, Story Arc, Price Ladder,
the checklist philosophy) — that is a content/doctrine checklist (PRESENTATION-MASTER-DOCTRINE.md §4),
completely unrelated to the deliverable-FILE counts below. Don't conflate the two.

---

## Quick reference

| Count | What it means | Status |
|---|---|---|
| **10** | Enforced operator build bundle (files the engine gates as complete) | Enforced today |
| **7** | Client package folder `delivery/[DECK_SLUG]-FINAL/` | Enforced today (all 7 hard-required) |
| **12** | What actually ships every run (10 + 2 workbook PDFs) | Ships today, but not in any deliverable list |
| **15** | 12 + 3 client-elected upsells (sales, checkout, VSL pages) | Asked today; **not buildable today** (Wave C) |
| **36** | Declared and machine-enforced phase count | Enforced today |
| **31 / 35 / 32** | Phases that actually execute — standard / signature / content-conversion deck | Enforced today |
| **~48** | Honest end-to-end mechanical step count (36 phases + ~12 outside-manifest gates) | Descriptive, not a manifest number |

---

## 1. DELIVERABLE COUNTS

### 10 — the enforced operator build bundle

**Source of truth:** `DEPT/scripts/presentation_job/deliverables.py`, constant `DELIVERABLE_AUDIT_SPEC`
(the file's own docstring calls it "THE single source of truth for the deliverable whitelist" — every
other consumer imports from here, no other file may hardcode a deliverable list). Derived constant
`DELIVERABLE_COUNT = len(DELIVERABLE_AUDIT_SPEC)`.

Verified by executing the module directly in this worktree:

```
DELIVERABLE_COUNT = 10
KEYS = ['deck_pptx', 'deck_pdf', 'guide_pdf', 'speech_md', 'speech_pdf', 'speech_fish_md',
        'audio_mp3', 'infographic_png', 'teleprompter_html', 'webinar_mp4']
```

The manifest's `build_bundle_files` array (`SOPS/presentation-slide-craft/PIPELINE-MANIFEST.json`,
top-level key) is **byte-identical** to those 10 keys, in the same order — confirmed by reading the
JSON directly. The postflight gate `DEPT/scripts/fix_bundle_complete.py` imports
`DELIVERABLE_AUDIT_SPEC` / `DELIVERABLE_COUNT` straight from `deliverables.py` (`from
presentation_job.deliverables import DELIVERABLE_AUDIT_SPEC, ..., DELIVERABLE_COUNT`) and self-tests
`rec.get("deliverable_count") != len(DELIVERABLE_AUDIT_SPEC)` — the gate cannot drift from the spec
because it never carries its own copy of the number.

The ten real filenames (from `filename_template` in the spec, `{deck_slug}` = the run's deck slug):

| # | key | filename |
|---|---|---|
| 1 | deck_pptx | `{deck_slug}-FINAL.pptx` |
| 2 | deck_pdf | `{deck_slug}-FINAL.pdf` |
| 3 | guide_pdf | `PRESENTER-GUIDE.pdf` |
| 4 | speech_md | `PRESENTERS-SPEECH.md` |
| 5 | speech_pdf | `PRESENTERS-SPEECH.pdf` |
| 6 | speech_fish_md | `PRESENTERS-SPEECH-FISH-TAGGED.md` |
| 7 | audio_mp3 | `PRESENTER-AUDIO.mp3` |
| 8 | infographic_png | `infographic.png` |
| 9 | teleprompter_html | `presenter-teleprompter.html` |
| 10 | webinar_mp4 | `{deck_slug}-WEBINAR.mp4` |

### 7 — the client package folder `delivery/[DECK_SLUG]-FINAL/`

**Source of truth:** `DEPT/scripts/delivery_gate.py`, function `check_af_dh1()` (line 218), gated by
`CLIENT_PACKAGE_WARN_ONLY` (line 193). Verified directly:

```python
CLIENT_PACKAGE_WARN_ONLY = frozenset()   # stage 3 — nothing is warn-only; all 7 are HARD-required
```

The code comment immediately above the `CLIENT_PACKAGE` constant declaration (lines 782–784 — not the
call site; `check_af_dh1` is actually invoked at line 738) reads: "webinar video as a SEVENTH
client-package file. Named CLIENT_PACKAGE, not SIX, so a [reader sees the true count]." The manifest's
`client_package_files` array (top-level key in `PIPELINE-MANIFEST.json`) confirms the same 7 keys:

```
client_package_files = [deck_pptx, deck_pdf, guide_pdf, speech_pdf, audio_mp3,
                         teleprompter_html, webinar_mp4]
```

The 7 filenames (same naming convention as the 10 above):

| # | key | filename |
|---|---|---|
| 1 | deck_pptx | `{deck_slug}-FINAL.pptx` |
| 2 | deck_pdf | `{deck_slug}-FINAL.pdf` |
| 3 | guide_pdf | `PRESENTER-GUIDE.pdf` |
| 4 | speech_pdf | `PRESENTERS-SPEECH.pdf` |
| 5 | audio_mp3 | `PRESENTER-AUDIO.mp3` |
| 6 | teleprompter_html | `presenter-teleprompter.html` |
| 7 | webinar_mp4 | `{deck_slug}-WEBINAR.mp4` |

Note the 7 is a **subset** of the 10 minus three internal/raw-format artifacts that don't go to the
client folder: `speech_md` (raw markdown — the client gets the PDF), `speech_fish_md` (Fish-Audio
tagging markup — internal to the TTS pipeline), and `infographic_png` (delivered via GHL media upload,
not the package folder).

### 12 — what actually ships every run

**The 10 above, PLUS the two workbook PDFs from phase `P8.25-WORKBOOK`:**
`{deck_slug}-WORKBOOK.pdf` and `{deck_slug}-WORKBOOK-FILLABLE.pdf`.

Proof: `DEPT/scripts/workbook_builder.py` builds both — "2a. REGULAR PDF
(`{deck_slug}-WORKBOOK.pdf`) — every page image, NO AcroForm fields" and "2b. FILLABLE PDF
(`{deck_slug}-WORKBOOK-FILLABLE.pdf`) — the SAME pages, then the [form fields layered in]" — and
verifies both landed distinctly (`AF-WORKBOOK-BOTH`, docstring: "the dual-PDF workbook contract").
The manifest phase entry:

```
id: "P8.25-WORKBOOK"
order: 8.25
produces_artifact: "working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-WORKBOOK-FILLABLE.pdf"
gate_codes: ["AF-WORKBOOK-PROMPT-NO-CONTENT", "AF-WORKBOOK-EMPTY", "AF-WORKBOOK-BOTH"]
```

`WORKBOOK-BUILDER-SOP.md` (`DEPT/sops/WORKBOOK-BUILDER-SOP.md`, line 21) states verbatim: **"TWO PDFs
ship, always."**

**These two are in NEITHER the 10 nor the 7 today.** `deliverables.py`'s own module docstring says so
explicitly, describing a historical drift bug where `phase_verifiers.py` once carried a stray
`"workbook_pdf"` key: *"NOT part of the canonical bundle (the workbook is a separate P8.25-WORKBOOK
deliverable with its own gate)."* That is the current, correct, intentional state — the workbook is
gated by its own three `AF-WORKBOOK-*` codes at `P8.25-WORKBOOK`, independent of the 10-file
`fix_bundle_complete.py` gate and the 7-file `check_af_dh1` gate. It always ships (both PDFs, every
run, uploaded to the client's GHL per `WORKBOOK-BUILDER-SOP.md` §2/§8); it just isn't counted in
either enforced list. That is why "12" is the honest "what ships" number, distinct from "10" (what the
build-bundle gate enforces) and "7" (what the client-package gate enforces).

**Also produced and phase-gated, handed to no one, on no deliverable list:**
`PRESENTER-AUDIO-WEBINAR.mp3` — the webinarized speech audio (welcome + Q&A + crescendo-close framing)
produced by phase `P9-SPEECH-WEBINAR-INTRO` (manifest order 8.54, `produces_artifact:
"working/delivery/PRESENTER-AUDIO-WEBINAR.mp3"`, gate `AF-WEBINAR-INTRO`). It is a required
intermediate — it feeds `P9.6-WEBINAR-VIDEO` — verified consumed by `_verify_webinarized_speech()`
(def `DEPT/scripts/phase_verifiers.py:1491`, artifact path referenced at lines 1496/1514/1517 of the
same function; NOT `_verify_webinar_video()` at line 1432, which is the separate verifier for the
`{deck_slug}-WEBINAR.mp4` artifact) and referenced in `DEPT/sops/WEBINAR-BUILDER-SOP.md:45` and
`DEPT/sops/audio-demonstration-specialist-sops.md:120`. It is not in the 10, not in the 7, and not in
the "12 shipped" count above — it never leaves the run directory as a standalone artifact; it exists
only to be assembled into `{deck_slug}-WEBINAR.mp4` (deliverable #10/#7 above).

### 15 — 12 + the three client-elected upsells

**The 12 above, PLUS the three upsell pages** defined in
`DEPT/intake/upsell-questions.json` (v1.0.0) and mirrored at orders 7.6/7.61/7.7/7.71 in
`DEPT/intake/deck-intake-questions.json` (repo copy verified: version `1.5.0`, 55 questions, all four
upsell-order questions present):

- **Sales page** (`want_sales_checkout`) — **default YES**. Help text: "The sales page + checkout page
  is a standard upsell deliverable and one of the engine's fail-closed gates." A "no" requires the
  client's own verbatim reason (`sales_checkout_declined_reason`) recorded as a waiver — never inferred
  from silence, never assistant-authored.
- **Checkout page** — bundled with the sales page under the same `want_sales_checkout` flag.
- **VSL page** (`want_vsl_page`) — **default NO**, opt-in only (a VSL page requires a video to exist
  first). Same waiver mechanic on decline (`vsl_page_declined_reason`).

**Current status, stated honestly:** the question is **asked live** by the deployed interview app
(`DEPT/intake/interview-app/`, worker `src/lib.js` + `payload/build_questions_payload.py` load
`upsell-questions.json`) — the answer is captured and stored
(`pre_presentation_capture.WANT_SALES_CHECKOUT` / `WANT_VSL_PAGE` in `working/copy/intake.json`).

**It does not build today.** Verified directly against this worktree's manifest:

```
P-U phase ids found in PIPELINE-MANIFEST.json: []   (0 of 36 phases)
```

No `P-U-SALES-*`, `P-U-CHECKOUT-*`, `P-U-FORM-CHECKOUT`, or `P-U-VSL-*` phase exists in
`PIPELINE-MANIFEST.json`, `phase_verifiers.py`'s `PHASE_VERIFIERS` registry, or any script in
`DEPT/scripts/`. The build path for these three upsells is **under construction in Wave C** of the
current work order (`CONTROL/MASTER-WORK-ORDER-20260818.md` §"WAVE C — BUILD THE UPSELL BRANCH") — do
not claim, in any document, that these three build today. A client who answers "yes" today gets a
recorded flag and nothing else, until Wave C lands.

---

## 2. STEP COUNTS

### 36 — declared and machine-enforced phase count

**Source of truth:** `SOPS/presentation-slide-craft/PIPELINE-MANIFEST.json`, `manifest_version` and the
`phases[]` array. Verified by loading the JSON and counting mechanically in this worktree:

```
manifest_version: 50
len(phases): 36
```

All 36 phase ids, **sorted mechanically by the true `order` field** (parsed directly from
`PIPELINE-MANIFEST.json` with `sorted(phases, key=lambda p: p["order"])` in this worktree — not
hand-ordered). A prior draft of this table was captioned "manifest order" but was not actually sorted
that way: it grouped the 5 signature-only phases at positions 32-36 and swapped `P-CONVERTER` /
`P-0.5-RESEARCH`. The `order` value is included below so the sort is self-evidencing:

| # | order | id | # | order | id |
|---|---|---|---|---|---|
| 1 | -1 | P-CONVERTER | 19 | 4.9 | P4-RENDER |
| 2 | -0.5 | P-0.5-RESEARCH | 20 | 4.95 | P-IMAGE-QC |
| 3 | 0.1 | P0A-INTAKE | 21 | 7.5 | P-SHIFT-QC |
| 4 | 0.14 | P-SP-CLAIM | 22 | 8 | P8-ASSEMBLE |
| 5 | 0.15 | P-SP-INTAKE | 23 | 8.1 | P8.1-PDF-EXPORT |
| 6 | 0.16 | P-SP-INTAKE-TRACE | 24 | 8.2 | P8.2-GUIDE |
| 7 | 0.2 | P0B-PRIORITY | 25 | 8.25 | P8.25-WORKBOOK |
| 8 | 3 | P3-ARC | 26 | 8.5 | P9-SPEECH |
| 9 | 3.5 | P-3.5-RESEARCH-MAP | 27 | 8.52 | P8.4-FISH-TAG |
| 10 | 4 | P4-COPY | 28 | 8.54 | P9-SPEECH-WEBINAR-INTRO |
| 11 | 4.1 | P-SP-STRUCTURE | 29 | 8.55 | P9.1-SPEECH-PDF |
| 12 | 4.15 | P-SP-P3-HYGIENE | 30 | 8.6 | P-SPEECH-QC |
| 13 | 4.2 | P1Q-COPY-QC | 31 | 8.65 | P-QC-AGGREGATE |
| 14 | 4.5 | PF-DESIGN | 32 | 8.7 | P9.5-NOTES-SYNC |
| 15 | 4.6 | P-TYPO-QC | 33 | 8.9 | P9.2-GHL-UPLOAD |
| 16 | 4.7 | P4-PROMPT | 34 | 8.92 | P9.6-WEBINAR-VIDEO |
| 17 | 4.8 | P-PROMPT-QC | 35 | 8.95 | P7-TELEPROMPTER |
| 18 | 4.85 | P-STYLE-PREVIEW | 36 | 9 | P9-DELIVER |

Note the 5 signature-only phases sit at their true positions — `P-SP-CLAIM`/`P-SP-INTAKE`/
`P-SP-INTAKE-TRACE` at 4-6 (order 0.14/0.15/0.16) and `P-SP-STRUCTURE`/`P-SP-P3-HYGIENE` at 11-12
(order 4.1/4.15) — not grouped at the end. The id **set** was already correct in the prior draft;
only the ordering and the missing `order` column are fixed here.

`DEPT/scripts/run_signature_deck.py`'s `declare_plan()` (def line 901) sorts **all 36** by `order`
(`sorted(phases, key=lambda p: p.get("order", 0))`, line 927) to build the `steps`/`total` fields of
`declared_plan.json` — this stays the full, unfiltered 36 deliberately, because `prove-deck.py`
cross-references every one of the 36 declared steps against the attestation chain (FIX 2a /
AF-PROCESS-INTEGRITY) and B2 must not weaken that certificate. See the "31" section below for what the
CLIENT actually gets told, which is a different, now-fixed number.
`DEPT/scripts/presentation_job/execution_plan.py` builds its Kahn-algorithm DAG (`topological_sort`)
from the same unfiltered 36-node manifest. `DEPT/scripts/phase_verifiers.py`'s `PHASE_VERIFIERS`
registry was checked programmatically against the manifest's 36 ids in this worktree:

```
total manifest ids: 36
total registered in PHASE_VERIFIERS: 36
missing from PHASE_VERIFIERS: []
```

Every one of the 36 has a substance verifier; `verify()` fails closed ("no verifier registered ... —
pass" is treated as a FAIL, per its own docstring) for anything that somehow isn't registered.

### 31 — executes on a standard from-scratch deck (35 signature, 32 content-conversion)

**The 5 conditional phases**, each verified by reading its actual gating logic in
`DEPT/scripts/build_deck.py`:

1. **`P-CONVERTER`** (order -1) — content-conversion path only. Its own preflight checker
   `_chk_converter_no_invent()` (line 8695) defers (`return ""`) whenever no `source_brief.md` is
   present — i.e., it is inert on any deck not built via the content-to-presentation-architect path.
   The manifest entry's own `routing_note` says: *"Content-first path only."*
2. **`P-SP-INTAKE`** — its checker `_chk_sp_intake()` (line 9020): *"DEFERS unless
   signature_presentation"* — literally, `if not _sp_active(run_dir): return ""`.
3. **`P-SP-INTAKE-TRACE`** — `_chk_sp_intake_trace()` docstring: *"DEFERS (no-op) unless intake.json
   declares deck_type == signature_presentation, so every other deck type takes the identical
   pre-existing path."*
4. **`P-SP-STRUCTURE`** — `_chk_sp_structure()` (line 9027): same `_sp_active()` defer.
5. **`P-SP-P3-HYGIENE`** — `_chk_sp_no_pitch()` (line 9034): same `_sp_active()` defer.

**`P-SP-CLAIM` is NOT in this list** — verified via its own docstring at
`_chk_sp_claim()` (line 9164): *"the routing/claim gate. Runs for EVERY deck (does NOT defer, unlike
the three gates above)."* It fails closed (`AF-SP-TYPE-UNDECLARED`) only if signature signals are
detected but undeclared; on a clean standard deck with no signature signals it passes through, but it
always **executes** (the check runs), unlike the 5 that no-op entirely. This is why it's excluded from
the "5 that don't execute" count.

Arithmetic, all verified against the same 36-id list above:
- **Standard from-scratch deck:** 36 − (`P-CONVERTER` + 4 SP-only) = **31**.
- **Signature deck:** 36 − `P-CONVERTER` only (the 4 SP-only phases now apply) = **35**.
- **Content-conversion standard deck:** 36 − (4 SP-only) only (`P-CONVERTER` now applies) = **32**.

**Fixed in `run_signature_deck.py` (B2, 2026-08-19) — client is now told the honest, deck-shaped count.**
`_client_visible_phases()` (def `DEPT/scripts/run_signature_deck.py:857`) filters the 36 down to the
phases that will actually do work for THIS run's deck shape (fails safe to the full 36 whenever a
deck-shape signal isn't yet knowable). `declare_plan()` calls it at line 942 and the outbound client
message at line 947 now reads *"Starting {slug}. I'll follow these {len(client_visible)} steps..."* —
31 on a standard from-scratch deck, 35 on signature, 32 on content-conversion, per the arithmetic
above. `declared_plan.json` also now carries `client_facing_total` / `client_facing_step_ids`
alongside the unchanged full-36 `steps`/`total` (lines 954-961). This is pinned by
`DEPT/scripts/tests/test_client_step_count.py` (`test_client_facing_fields_match_deck_type`,
`test_signature_deck_message_says_35`, `test_content_conversion_deck_message_says_32`, and others in
that file) — all passing in this worktree (see VERIFICATION METHOD below).

**Production-path caveat — checked and now closed, NOT open.** `presentation-canonical-entry.sh`
prefers the newer engine over this runner: it dispatches through `presentation_job.py`
(`ENGINE_ENTRY="$SCRIPTS_DIR/presentation_job.py"`, line 877) whenever that file is present (line 913),
and falls back to `run_signature_deck.py` only when the engine component is missing from the box (the
`engine_fail` path, lines 868-873, 885-890) — verified by reading `presentation-canonical-entry.sh`
directly in this worktree. `presentation_job/__main__.py:17` imports `Engine` from `.phases` and
instantiates it at line 397 — `phases.py`'s `Engine` class IS the code the engine entrypoint runs.

At the time this document was first drafted, `DEPT/scripts/presentation_job/phases.py` had no
equivalent of `_client_visible_phases()`. **That has since changed inside this same worktree**, under
a distinct, already-landed fix labelled "B2b" in its own code comments (`phases.py` lines 41-75; see
`phases.py.bak-B2b-20260819` for the pre-fix version, confirming this is a real, in-worktree change,
not a hypothetical): `Engine._client_deck_shape()` (def line 202), `Engine._client_visible_phases()`
(def line 225) and `Engine._client_phase_index()` (def line 249) mirror `run_signature_deck.py`'s B2
fix 1:1 — same `_SP_ONLY_PHASE_IDS` / `_CONVERTER_ONLY_PHASE_IDS` sets (lines 76-79), same fail-safe
direction (unknown deck-shape signal widens to the full 36, never guesses smaller). The engine's ack
message (`n = len(self._client_visible_phases(phases))`, line 738, sent via
`self.report.to_requester(...)`, lines 739-742) and its per-phase `{k}/{N}` messages
(`Engine._render_client_report_msg()`, def line 264, called from `run_phase()` at lines 378 and 468)
both use this filtered count. Per the code comment (lines 51-58), B2b's original defect was actually
**worse** than the one B2 fixed: before B2b, `run_phase()` handed the manifest's raw
`"Step {k} of {N} — {name} — starting{eta}"` template straight to the client UNFORMATTED — braces and
all — never a real number.

This is pinned by `DEPT/scripts/tests/test_engine_client_report.py` — **28 tests, all passing** in
this worktree (`python3 -m pytest tests/test_engine_client_report.py -q` → `28 passed`, reproduced
during this verification pass). **Conclusion:** as of 2026-08-19 in this worktree, BOTH the runner
(`run_signature_deck.py`, B2) and the production engine (`presentation_job/phases.py`, B2b) tell the
client the honest, deck-shaped step count — there is no known gap between them. Anyone re-reading an
older draft of this document, or `MASTER-WORK-ORDER-20260818.md`'s Wave B2 note, should treat "engine
path not yet fixed" as **stale** — re-check `phases.py` git status before repeating that claim.

### ~48 — honest end-to-end, including the ~12 scripted gates outside `phases[]`

The 36 manifest phases are wrapped by real, code-enforced steps that are **not phase entries** in
`PIPELINE-MANIFEST.json` — each confirmed present in this worktree:

| # | Step | Where |
|---|---|---|
| 1 | The intake interview itself (turn-gated conversation) | `DEPT/scripts/deck-intake-driver.py` |
| 2 | Intake poll → engine launch | `DEPT/scripts/presentation-intake-poll.sh` (confirmed present, executable) |
| 3 | Intake ingest → Command Center kanban card | `intake_bridge.py` → `cc_board.ingest_deck_task()` (confirmed at `DEPT/scripts/cc_board.py`; referenced from `DEPT/intake/interview-app/bridge/intake_bridge.py`) |
| 4 | GATE 0 — intake ledger check | `DEPT/scripts/presentation-canonical-entry.sh` (confirmed: `note "GATE 0 — INTAKE-LEDGER CHECK"`) |
| 5 | GATE 0b — intake conversation trace | same file (confirmed: `note "GATE 0b — INTAKE-TRACE CHECK..."`) |
| 6 | GATE 1 — deps check | same file (confirmed: `note "GATE 1/3 — DEPS CHECK..."`) |
| 7 | GATE 1b — Skill-48 GHL module co-location | same file (confirmed: `note "GATE 1b/3 — SKILL-48 GHL MODULE CO-LOCATION..."`) |
| 8 | GATE 2 — bypass-scan | same file (confirmed: `note "GATE 2/3 — BYPASS-SCAN..."`) |
| 9 | GATE 3 — version/hash pin | same file (confirmed: `note "GATE 3/3 — VERSION/HASH PIN..."`) |
| 10 | Phase-0 preflight: OCR-engine availability | `DEPT/scripts/build_deck.py` (confirmed: `AF-OCR-ENGINE-MISSING`, ~line 5998) |
| 11 | Phase-0 preflight: platform detection | `DEPT/scripts/build_deck.py`, `detect_platform()` (confirmed, line 10329) |
| 12 | Phase-0 preflight: Kie.ai balance | `DEPT/scripts/build_deck.py` (confirmed: `AF-KIE-BALANCE`, ~line 5939) |
| — | Postflight bundle gate | `DEPT/scripts/fix_bundle_complete.py` (confirmed present) |
| — | Delivery interlock | `DEPT/scripts/delivery_gate.py` (confirmed present, `check_af_dh1`) |
| — | Process certificate | `DEPT/scripts/prove-deck.py` (confirmed present) |

**Arithmetic:** 36 (manifest phases) + ~12 (the scripted gates/steps above, several of which — GATE 0
through GATE 3, the 3 phase-0 preflights, the bundle gate, delivery interlock, and certificate — are
individually countable at 12; the interview and poll/ingest steps push the honest total slightly past
that) ≈ **~48**. This is stated as **"~48" deliberately, not as a precise count** — some of these
(e.g. the intake interview) are conversational, not single mechanical checkpoints, so a false-precision
number would misstate what's being counted. Do not present this as an exact figure anywhere.

---

## 3. VERIFICATION METHOD

Every number in this document was checked directly against the code in this worktree on 2026-08-19,
not taken on the authority of `CONTROL/FABLE-TRUTH.md` or any other prose document. Method used per
number: load the JSON/Python source, execute or grep the actual defining symbol, and (for the 36/10/7
counts) run a mechanical count in Python rather than eyeballing a list.

**Disagreement with FABLE-TRUTH.md: none found.** Every number in this document (10, 7, 12, 15, 36, 31,
35, 32, ~48) matches `CONTROL/FABLE-TRUTH.md` §1 and §2 exactly, and matches
`CONTROL/MASTER-WORK-ORDER-20260818.md`'s "THE THREE ANSWERS" section exactly. Where this document goes
further than FABLE-TRUTH is only in showing the executed verification (exact line numbers, executed
Python output, mechanical set-difference checks) rather than asserting the numbers.

*Last verified: 2026-08-19, Unit A10 RUN 2.*
