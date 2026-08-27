# DEPARTMENT COUNTS — CANONICAL

**This is the single authoritative page for the Presentations department's deliverable counts and step
counts.** Every other document in this department (00-START-HERE.md, BUILDER-PROMPT.md,
how-to-use-this-department.md, CLIENT-WEBINAR-DECK-SOP.md, MASTER-QC-AUTOFAIL-RULESET.md,
PRESENTATION-MASTER-DOCTRINE.md, delivery_gate.py's docstring, etc.) must **LINK HERE** rather than
restate any of the numbers below. If a number ever needs to change, it changes in exactly one place.

Every claim below was verified against the code in this worktree on 2026-08-19 (**Unit COUNTS-R2,
RUN 2** — Wave C landed manifest_version 51 / 40 phases since RUN 1's draft of this document), not
copied from prose, and not copied from `CONTROL/MASTER-WORK-ORDER-20260818.md` or
`CONTROL/FABLE-TRUTH.md`. Where a proving command is shown, it was actually run against the files in
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
| **10** | Enforced operator build bundle (files the engine gates as complete) | Enforced today — unchanged by Wave C |
| **7** | Client package folder `delivery/[DECK_SLUG]-FINAL/` | Enforced today (all 7 hard-required) — unchanged by Wave C |
| **12** | What actually ships every run (10 + 2 workbook PDFs) | Ships today, but not in any deliverable list — unchanged by Wave C |
| **15** | 12 + 3 client-elected upsells (sales, checkout, VSL pages) | Asked today; **buildable as of Wave C, one named gap** (`P-U-FORM-CHECKOUT`'s real form-wiring is a placeholder) — see §1.15 |
| **40** | Declared and machine-enforced phase count | **Changed by Wave C: 36 -> 40** (manifest_version 50 -> 51) |
| **31 / 34 / 35** (standard) | Executed phases on a standard deck, by upsell election (both declined / sales+checkout only / both elected) | New in RUN 2 — see the full matrix in §2 |
| **35 / 38 / 39** (signature) | Same, on a signature deck | New in RUN 2 — see §2 |
| **32 / 35 / 36** (content-conversion) | Same, on a content-conversion deck | New in RUN 2 — see §2 |
| **~48** | Honest end-to-end mechanical step count (40 phases + ~12 outside-manifest gates) | Descriptive, not a manifest number — the "~12 gates" arithmetic is unchanged; the base phase count under it moved 36 -> 40 |

**RUN 1 -> RUN 2, what actually changed:** only the step-count side (§2) and the "15" deliverable
status (§1.15). The 10/7/12 deliverable counts (§1) are byte-for-byte unchanged — `deliverables.py`,
`delivery_gate.py`, and the manifest's `build_bundle_files`/`client_package_files` arrays were not
touched by Wave C, and this run re-verified that directly (see §1 for the re-run proof).

---

## 1. DELIVERABLE COUNTS

### 1.10 — the enforced operator build bundle

**Source of truth:** `DEPT/scripts/presentation_job/deliverables.py`, constant `DELIVERABLE_AUDIT_SPEC`
(the file's own docstring calls it "THE single source of truth for the deliverable whitelist" — every
other consumer imports from here, no other file may hardcode a deliverable list). Derived constant
`DELIVERABLE_COUNT = len(DELIVERABLE_AUDIT_SPEC)`.

Re-verified in RUN 2 by executing the module directly in this worktree (unchanged from RUN 1):

```
DELIVERABLE_COUNT = 10
KEYS = ['deck_pptx', 'deck_pdf', 'guide_pdf', 'speech_md', 'speech_pdf', 'speech_fish_md',
        'audio_mp3', 'infographic_png', 'teleprompter_html', 'webinar_mp4']
```

The manifest's `build_bundle_files` array (`SOPS/presentation-slide-craft/PIPELINE-MANIFEST.json`,
top-level key, manifest_version 51) is still **byte-identical** to those 10 keys, in the same order —
re-confirmed by reading the JSON directly in this run: `len(build_bundle_files) == 10`, same 10 keys.
Wave C's 4 new phases did not touch this array. `scripts/ci/presentations-drift-gates.sh` GATE 3
(deliverable whitelist parity) re-ran clean in this session: all 4 consumers
(`fix_bundle_complete.py`, `presentation_job/curate.py`, `phase_verifiers.py`, `self_audit.py`) match
canon exactly, same 10 keys.

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

### 1.7 — the client package folder `delivery/[DECK_SLUG]-FINAL/`

**Source of truth:** `DEPT/scripts/delivery_gate.py`, function `check_af_dh1()` (line 218), gated by
`CLIENT_PACKAGE_WARN_ONLY` (line 193). Re-verified directly in this run, same line numbers as RUN 1
(delivery_gate.py was not touched by Wave C):

```python
CLIENT_PACKAGE_WARN_ONLY = frozenset()   # stage 3 — nothing is warn-only; all 7 are HARD-required
```

The manifest's `client_package_files` array (top-level key in `PIPELINE-MANIFEST.json`, manifest_version
51) confirms the same 7 keys, unchanged by Wave C:

```
client_package_files = [deck_pptx, deck_pdf, guide_pdf, speech_pdf, audio_mp3,
                         teleprompter_html, webinar_mp4]
```

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
not the package folder). None of the four new upsell phases produce a `build_bundle_files` or
`client_package_files` entry — the sales/checkout/VSL pages ship to the client's GHL funnel, not the
package folder (see §1.15).

### 1.12 — what actually ships every run

**The 10 above, PLUS the two workbook PDFs from phase `P8.25-WORKBOOK`:**
`{deck_slug}-WORKBOOK.pdf` and `{deck_slug}-WORKBOOK-FILLABLE.pdf`. Unchanged by Wave C — re-verified
`P8.25-WORKBOOK` is still present in the manifest at order 8.25 with the same three gate codes
(`AF-WORKBOOK-PROMPT-NO-CONTENT`, `AF-WORKBOOK-EMPTY`, `AF-WORKBOOK-BOTH`).

`WORKBOOK-BUILDER-SOP.md` (`DEPT/sops/WORKBOOK-BUILDER-SOP.md`, §0) states verbatim: **"TWO PDFs
ship, always."** These two are still in **neither** the 10 nor the 7 — `deliverables.py`'s own module
docstring still says the workbook "is NOT part of the canonical bundle (the workbook is a separate
P8.25-WORKBOOK deliverable with its own gate)." That is the current, correct, intentional state.

**Also still produced and phase-gated, handed to no one, on no deliverable list:**
`PRESENTER-AUDIO-WEBINAR.mp3` (`P9-SPEECH-WEBINAR-INTRO`, order 8.54) — feeds `P9.6-WEBINAR-VIDEO`,
never leaves the run directory as a standalone artifact. Unchanged by Wave C.

### 1.15 — 12 + the three client-elected upsells (RUN 2: status materially changed)

**The 12 above, PLUS the three upsell pages** defined in `DEPT/intake/upsell-questions.json` (v1.0.0):
sales page + checkout page (one combined `want_sales_checkout` flag, **default YES**) and the VSL page
(`want_vsl_page`, **default NO**, opt-in only, requires the webinar video to exist first). Same waiver
mechanic as RUN 1 documented: a "no" requires the client's own verbatim reason
(`SALES_CHECKOUT_DECLINED_REASON` / `VSL_PAGE_DECLINED_REASON`), never inferred from silence.

**RUN 1 said this does not build at all. That is now stale. Verified directly against this worktree,
2026-08-19:**

```
P-U phase ids found in PIPELINE-MANIFEST.json (manifest_version 51): 4 of 40 phases
  P-U-SALES-BUILD    order 8.75   executor: scripts/sales_checkout_builder.py --run-dir {run_dir}
  P-U-CHECKOUT-BUILD order 8.76   executor: scripts/sales_checkout_builder.py --run-dir {run_dir} --skip-design
  P-U-FORM-CHECKOUT  order 8.77   executor: scripts/sales_checkout_builder.py --run-dir {run_dir} --skip-design
  P-U-VSL-BUILD      order 8.93   executor: scripts/vsl_builder.py --run-dir {run_dir}
```

**What is LANDED (independently confirmed in this worktree, not taken on any document's word):**
- **Manifest phases** — all 4 ids present, correctly ordered (`P-U-VSL-BUILD` at 8.93, strictly after
  `P9.6-WEBINAR-VIDEO` at 8.92, as its video dependency requires).
- **Executors on disk** — `DEPT/scripts/sales_checkout_builder.py` (68,868 bytes) and
  `DEPT/scripts/vsl_builder.py` (87,748 bytes) both exist and both parse: `python3 -c "import ...")`
  succeeds for both under GATE 1's import-smoke style check. Both scripts' real argparse contract
  (read directly from source, `def main()`): `--run-dir`, `--skip-design`, `--no-push`, `--selftest` —
  **no `--mode` flag on either script.** This matters: `SALES-CHECKOUT-BUILDER-SOP.md` (as of this
  writing) still describes a `--mode sales|checkout|form-checkout` contract that does not match the
  landed script — the manifest's own `routing_note` on `P-U-SALES-BUILD` already documents the
  correction ("no --mode flag exists — corrected 2026-08-19 after C2's script landed"). **This
  document defers to the code, not the SOP, per this unit's brief** — flagged here as a live,
  unresolved doc/SOP inconsistency for whichever unit owns those two SOPs next, not fixed by this unit
  (out of this unit's file scope).
- **Client step count** — `run_signature_deck._client_visible_phases()` and
  `presentation_job/phases.py`'s `Engine._client_visible_phases()` both already carry
  `_SALES_CHECKOUT_ONLY_PHASE_IDS` / `_VSL_ONLY_PHASE_IDS` filter sets (same fail-safe-widens rule as
  the pre-existing `P-CONVERTER`/`P-SP-*` sets) — a client's `declare_plan()` count already reflects
  the upsell election the moment `intake.json` records it. See §2 for the full matrix.
- **Autofail registry** — `AF-U-SALES-BUILD`, `AF-U-CHECKOUT-BUILD`, `AF-U-FORM-CHECKOUT`,
  `AF-U-VSL-BUILD` are all present in `PIPELINE-MANIFEST.json`'s `autofails[]` array with
  `in_ruleset: true`, and `SOPS/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md` already carries
  matching rows for all four (checked directly, lines ~311-314 in this worktree).
- **SOPs** — `DEPT/sops/SALES-CHECKOUT-BUILDER-SOP.md` and `DEPT/sops/VSL-BUILDER-SOP.md` both exist
  and both self-report "PARTIALLY LANDED, mid-build" (their own status sections, re-read in this run) —
  treat their prose as a draft in progress, not a finished contract; the manifest and the executor
  source are the ground truth this document defers to.

**Verifier registration — landed DURING this unit's own session (timeline matters here, stated
honestly).** Earlier in this run, `phase_verifiers.py` had ZERO substance-verifier registrations for
the 4 new ids (`PHASE_VERIFIERS` held 36 of 40, and the department's two "enforced count" tests failed
naming exactly these 4 ids missing) — that was the live state this unit's brief anticipated,
attributed to concurrent Unit C4. **Unit C4 landed that work while this unit was still writing this
document** (confirmed: `phase_verifiers.py`'s mtime moved to 11:09, its size grew ~13KB, and this unit
never opened that file for writing — see the hard constraint below). Re-checked immediately before
publishing this revision:

```
total manifest ids: 40 / total registered in PHASE_VERIFIERS: 40 / missing: []
```

Both previously-failing tests (`test_client_step_count.py` and `test_engine_client_report.py`,
`TestEnforcedCountUnchanged::test_verifier_registry_covers_all_36`) now PASS. **As of this document's
last-verified timestamp, the verifier gap is CLOSED — do not describe it as pending in any document
dated after this one; re-check `phase_verifiers.py` before repeating that claim, the same caution RUN
1 gave about the engine-path claim.**

**What is confirmed NOT landed (checked live in this worktree, not assumed):**
- **`P-U-FORM-CHECKOUT` has no real implementation** — both the manifest's own `routing_note` and the
  `AF-U-FORM-CHECKOUT` autofail trigger text say so explicitly: it currently re-verifies the SAME
  `build_receipt.json` `P-U-SALES-BUILD` produces (an interim placeholder), not an independent
  payment/lead-capture form check. `SALES-CHECKOUT-BUILDER-SOP.md` §4 "THE CHECKOUT FORM" proposes
  the real wiring as a follow-up unit's work, not yet done. This is a real, still-open gap regardless
  of the verifier landing above — a verifier can only check that the placeholder receipt exists, it
  cannot verify a form that was never built.

**Bottom line, stated once:** the upsell branch went from **0% wired** (RUN 1: no phases, no
executors, no verifiers, no autofail rows) to **manifest + executors + autofail registry + verifiers
ALL LANDED, with exactly one named gap remaining: `P-U-FORM-CHECKOUT`'s real form/payment wiring is
still an interim placeholder** (tracked, unassigned follow-up — not the same thing as "the phase
doesn't run," it runs and passes its current, narrower gate). Do not describe the branch as either
"fully buildable" or "0% wired" in any document — both are now false; describe it as
landed-with-one-named-gap, per this section.

---

## 2. STEP COUNTS

### 2.40 — declared and machine-enforced phase count (RUN 2: was 36, now 40)

**Source of truth:** `SOPS/presentation-slide-craft/PIPELINE-MANIFEST.json`, `manifest_version` and the
`phases[]` array. Verified by loading the JSON and counting mechanically in this worktree:

```
manifest_version: 51   (was 50 at RUN 1 — Wave C unit C1 landed this bump; this unit did NOT touch it)
len(phases): 40         (was 36 at RUN 1 — +4: P-U-SALES-BUILD, P-U-CHECKOUT-BUILD,
                          P-U-FORM-CHECKOUT, P-U-VSL-BUILD)
```

All 40 phase ids, sorted mechanically by the true `order` field
(`sorted(phases, key=lambda p: p["order"])`, executed directly against the live manifest in this
worktree, not hand-ordered):

| # | order | id | # | order | id |
|---|---|---|---|---|---|
| 1 | -1 | P-CONVERTER | 21 | 7.5 | P-SHIFT-QC |
| 2 | -0.5 | P-0.5-RESEARCH | 22 | 8 | P8-ASSEMBLE |
| 3 | 0.1 | P0A-INTAKE | 23 | 8.1 | P8.1-PDF-EXPORT |
| 4 | 0.14 | P-SP-CLAIM | 24 | 8.2 | P8.2-GUIDE |
| 5 | 0.15 | P-SP-INTAKE | 25 | 8.25 | P8.25-WORKBOOK |
| 6 | 0.16 | P-SP-INTAKE-TRACE | 26 | 8.5 | P9-SPEECH |
| 7 | 0.2 | P0B-PRIORITY | 27 | 8.52 | P8.4-FISH-TAG |
| 8 | 3 | P3-ARC | 28 | 8.54 | P9-SPEECH-WEBINAR-INTRO |
| 9 | 3.5 | P-3.5-RESEARCH-MAP | 29 | 8.55 | P9.1-SPEECH-PDF |
| 10 | 4 | P4-COPY | 30 | 8.6 | P-SPEECH-QC |
| 11 | 4.1 | P-SP-STRUCTURE | 31 | 8.65 | P-QC-AGGREGATE |
| 12 | 4.15 | P-SP-P3-HYGIENE | 32 | 8.7 | P9.5-NOTES-SYNC |
| 13 | 4.2 | P1Q-COPY-QC | 33 | **8.75** | **P-U-SALES-BUILD** |
| 14 | 4.5 | PF-DESIGN | 34 | **8.76** | **P-U-CHECKOUT-BUILD** |
| 15 | 4.6 | P-TYPO-QC | 35 | **8.77** | **P-U-FORM-CHECKOUT** |
| 16 | 4.7 | P4-PROMPT | 36 | 8.9 | P9.2-GHL-UPLOAD |
| 17 | 4.8 | P-PROMPT-QC | 37 | 8.92 | P9.6-WEBINAR-VIDEO |
| 18 | 4.85 | P-STYLE-PREVIEW | 38 | **8.93** | **P-U-VSL-BUILD** |
| 19 | 4.9 | P4-RENDER | 39 | 8.95 | P7-TELEPROMPTER |
| 20 | 4.95 | P-IMAGE-QC | 40 | 9 | P9-DELIVER |

(New ids **bolded**. All 36 pre-existing ids kept their exact prior `order` value — Wave C only
inserted, it never renumbered.)

`DEPT/scripts/run_signature_deck.py`'s `declare_plan()` still sorts **all 40** by `order` to build the
unfiltered `steps`/`total` fields of `declared_plan.json` (the attestation-chain contract, per B2, is
unchanged in shape — only the count moved). `DEPT/scripts/phase_verifiers.py`'s `PHASE_VERIFIERS`
registry was checked programmatically against the manifest's 40 ids in this worktree:

```
total manifest ids: 40
total registered in PHASE_VERIFIERS: 40
missing from PHASE_VERIFIERS: []
```

**This was the one enforcement surface that had not caught up to 40 earlier in this same session —
Unit C4 landed the 4 missing registrations while this document was being written; re-checked
immediately before publishing (see §1.15 for the full timeline).** Every enforcement surface checked
in this run (the DAG builder, the runner's raw `_phase_index`, the engine's raw walk, and now
`phase_verifiers.py`) operates over the full 40.

### 2.31–40 — executed count now depends on BOTH deck type AND upsell election (RUN 2: new axis)

**RUN 1's "31/35/32" answer is still correct as far as it goes — it is the count when BOTH upsells
are declined or unknown.** It is no longer the complete answer, because Wave C added two more
independent yes/no signals (`sales_checkout_known`/`wants_sales_checkout`,
`vsl_known`/`wants_vsl`) to the same fail-safe-widens filter that already handled deck type. The
conditional-phase families, each verified by reading the actual gating logic in
`DEPT/scripts/presentation_job/phases.py` (lines 76-88) and `DEPT/scripts/run_signature_deck.py`
(lines 831-842, mirrored 1:1):

| Family | ids | Filtered OUT when |
|---|---|---|
| Content-conversion | `P-CONVERTER` (1) | `creation_mode` known AND not content-first |
| Signature-only | `P-SP-INTAKE`, `P-SP-INTAKE-TRACE`, `P-SP-STRUCTURE`, `P-SP-P3-HYGIENE` (4) | `deck_type` known AND not `signature_presentation` |
| Sales/checkout upsell (Wave C) | `P-U-SALES-BUILD`, `P-U-CHECKOUT-BUILD`, `P-U-FORM-CHECKOUT` (3) | `WANT_SALES_CHECKOUT` known AND != "yes" |
| VSL upsell (Wave C) | `P-U-VSL-BUILD` (1) | `WANT_VSL_PAGE` known AND != "yes" |

`P-SP-CLAIM` is still never filtered (runs on every deck as the router). An unknown/absent signal
**always widens**, never narrows — the same fail-safe direction on all four families.

**Mechanical derivation actually run in this worktree** (both a standalone re-implementation of the
filter against the raw manifest, AND, independently, the real `run_signature_deck._client_visible_phases()`
called against real `intake.json` fixtures — both methods agree exactly):

```
                          both        sales/checkout      both
                          declined    YES, VSL NO          YES
standard-from-scratch  ->   31            34                35
signature              ->   35            38                39
content-conversion     ->   32            35                36
```

(A fourth cell, sales/checkout NO + VSL YES, is arithmetically valid — standard 32, signature 36,
content-conversion 33 — but has no realistic client path since VSL requires the webinar video and is
opt-in-only; included in the executed derivation script, omitted from the table above as not a
real-world case.)

**Unknown-flag / not-yet-asked cases (both the deck-shape signal AND the upsell signals unknown) —
these are the numbers `test_client_step_count.py` pins directly, re-run in this session, all passing:**

```
standard-from-scratch, upsell flags unset -> 35   (test_standard_from_scratch_is_31: comment notes
                                                     "31 + 4 upsell phases, flags unset -> unknown widens")
signature, upsell flags unset             -> 39   (test_signature_is_35, same widening note)
content-conversion, upsell flags unset    -> 36   (test_content_conversion_is_32, same widening note)
fully unknown deck (no intake.json)       -> 40   (test_unknown_intake_fails_safe_to_full_36)
```

**Read this carefully — it is the single most confusing part of this document, so it gets its own
paragraph.** "31 phases execute on a standard deck" (Quick Reference, RUN 1's number) was always
implicitly "...when neither upsell applies." That is still true and still the right number for a
declined-upsells standard deck. But a REAL client run's client-facing count depends on what they
actually elected — a standard deck whose client said yes to sales+checkout (the default) sees **34**,
not 31, and `declare_plan()`'s outbound message will correctly say "I'll follow these 34 steps," not
31. Any document that states a bare "31" without naming the upsell-election assumption behind it is
now incomplete. **Do not pick one number as "the" standard-deck count — state the election it assumes,
or link here.**

**Fixed in `run_signature_deck.py` (B2, pre-existing) and `presentation_job/phases.py` (B2b,
pre-existing) — BOTH already extended by Wave C unit C1** to filter on the two new upsell signals with
the identical fail-safe shape as the pre-existing two families (verified by reading
`_SALES_CHECKOUT_ONLY_PHASE_IDS` / `_VSL_ONLY_PHASE_IDS` in both files — see line refs above). This is
pinned by `DEPT/scripts/tests/test_client_step_count.py` and
`DEPT/scripts/tests/test_engine_client_report.py`, both re-run in this session (see §3).

### 2.~48 — honest end-to-end, including the ~12 scripted gates outside `phases[]`

**Unchanged arithmetic shape, new base.** The ~12 scripted gates/steps outside `phases[]` (the intake
interview, poll/ingest, 6 entry gates in `presentation-canonical-entry.sh`, 3 phase-0 preflights, the
postflight bundle gate, delivery interlock, and process certificate) were not touched by Wave C — none
of them read `phases[]`'s length directly, they are independent scripted checkpoints. Re-verified
present in this worktree (same files/symbols as RUN 1: `deck-intake-driver.py`,
`presentation-intake-poll.sh`, `presentation-canonical-entry.sh`'s GATE 0/0b/1/1b/2/3,
`build_deck.py`'s `AF-OCR-ENGINE-MISSING`/`detect_platform`/`AF-KIE-BALANCE`, `fix_bundle_complete.py`,
`delivery_gate.py`, `prove-deck.py`).

**Arithmetic:** 40 (manifest phases, was 36) + ~12 (the scripted gates above) ≈ **~52**, not ~48 — the
honest end-to-end count moved by the same +4 that moved the enforced phase count, because the ~12
outside-manifest gates wrap the WHOLE phase list, not a fixed subset of it. Stated as **"~52"
deliberately, not as a precise count**, for the same reason RUN 1 stated "~48" imprecisely: the intake
interview is conversational, not a single mechanical checkpoint. **RUN 1's "~48" is now stale — update
any document that still says "~48" to "~52," or better, link here instead of restating either number.**

**Ticket 6 (2026-08-27) added one MECHANICAL gate inside the phase-walk loop itself** (AF-INTAKE-GATE,
`presentation_job/phases.py`'s `Engine._check_intake_gate`), distinct from both the 40 manifest phases
and the ~12 outside-manifest scripted gates above — it does not add a phase or a script step, so it does
not change the ~52 arithmetic. It blocks P0B-PRIORITY and every phase after it from starting unless
`working/copy/intake.json` already exists on disk, closing the gap where a content-authoring phase could
previously run before intake ever completed.

---

## 3. VERIFICATION METHOD

Every number in this document was checked directly against the code in this worktree on 2026-08-19
(Unit COUNTS-R2, RUN 2), not taken on the authority of `CONTROL/FABLE-TRUTH.md`,
`CONTROL/MASTER-WORK-ORDER-20260818.md`, or any prose document — including this unit's own dispatch
brief, which explicitly instructed "whatever the code says is the truth." Method used per number: load
the JSON/Python source, execute or grep the actual defining symbol, and, for every executed-count cell
in §2's matrix, cross-check TWO independent computations (a standalone re-implementation of the filter
logic against the raw manifest, AND a direct call into the real `run_signature_deck._client_visible_phases()`
against real `intake.json` fixtures) rather than trusting either alone.

**Where this document disagrees with `CONTROL/MASTER-WORK-ORDER-20260818.md` / `FABLE-TRUTH.md`:**
those documents predate Wave C and describe the pre-Wave-C world (36 phases, upsell branch 0% wired) —
not a disagreement, a timeline difference. Where this document disagrees with the RUN 2 dispatch
brief's own prose: **none found** — the brief's instruction to "derive mechanically, don't copy numbers
from the brief" was followed, and the derived numbers (40 phases; 31/34/35 standard, 35/38/39
signature, 32/35/36 content-conversion by upsell election; landed-with-two-gaps upsell branch status)
match what the brief anticipated in shape, though the brief did not itself state the full election
matrix — that matrix is this document's own contribution, not copied from anywhere.

*Last verified: 2026-08-19, Unit COUNTS-R2, RUN 2.*
