# DEPARTMENT COUNTS — CANONICAL

**This is the single authoritative page for the Presentations department's deliverable counts and step
counts.** Every other document in this department (00-START-HERE.md, BUILDER-PROMPT.md,
how-to-use-this-department.md, CLIENT-WEBINAR-DECK-SOP.md, MASTER-QC-AUTOFAIL-RULESET.md,
PRESENTATION-MASTER-DOCTRINE.md, delivery_gate.py's docstring, etc.) must **LINK HERE** rather than
restate any of the numbers below. If a number ever needs to change, it changes in exactly one place.

Every claim below was verified against the code in this worktree on 2026-08-19 (**Unit COUNTS-R2,
RUN 2** — Wave C raised the manifest's declared phase count since RUN 1's draft of this document), not
copied from prose, and not copied from `CONTROL/MASTER-WORK-ORDER-20260818.md` or
`CONTROL/FABLE-TRUTH.md`. The declared phase count is **never restated as a bare literal in this
document's prose** — it is read mechanically from `len(phases[])` in `PIPELINE-MANIFEST.json` (the
generated line in §2.40 quotes the live count and names its source; GATE 4 of
`scripts/ci/presentations-drift-gates.sh` fails CI if that line drifts from the manifest). Where a
proving command is shown, it was actually run against the files in
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
| **55** | Declared and machine-enforced phase count | **Changed by Wave C: 36 -> 40** (manifest_version 50 -> 51), then by later waves to **55** (manifest_version 55; count is read from `len(manifest.phases)`, never hardcoded) |
| **31 / 43 / 40 / 50** (standard) | Executed phases on a standard deck, by upsell election (both declined / sales-only / VSL-only / both elected) | Regenerated against the live manifest — see the full matrix in §2 |
| **35 / 47 / 44 / 54** (signature) | Same, on a signature deck | Regenerated against the live manifest — see §2 |
| **32 / 44 / 41 / 51** (content-conversion) | Same, on a content-conversion deck | Regenerated against the live manifest — see §2 |
| **~67** | Honest end-to-end mechanical step count (declared phase count, read from the manifest, + ~12 outside-manifest gates) | Descriptive, not a manifest number — the "~12 gates" arithmetic is unchanged; the base phase count under it moved 36 -> 40 -> 55 |

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
(RUN 2 snapshot, pinned 2026-08-19 — historical; the live manifest_version, total phase count, and
 every P-U phase id are read mechanically from PIPELINE-MANIFEST.json at GATE 4 time, never restated
 as a literal here)
P-U BUILD phase ids found in PIPELINE-MANIFEST.json at the RUN 2 snapshot: 4 of the then-declared
 phase set (the Wave D P-U COPY/DESIGN/HTML/GHL/QC families landed later, bringing the P-U total
 to 19 — read `len([p for p in phases if p["id"].startswith("P-U")])` from the live manifest for the
 current number)
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
the 4 new ids (`PHASE_VERIFIERS` lagged the declared count at that RUN 2 snapshot, and the department's two "enforced count" tests failed
naming exactly these 4 ids missing) — that was the live state this unit's brief anticipated,
attributed to concurrent Unit C4. **Unit C4 landed that work while this unit was still writing this
document** (confirmed: `phase_verifiers.py`'s mtime moved to 11:09, its size grew ~13KB, and this unit
never opened that file for writing — see the hard constraint below). Re-checked immediately before
publishing this revision:

```
At the RUN 2 snapshot, the live read was: manifest ids == registered verifier ids
(see §2.40 for the mechanical read; parity = 55/55 at the 2026-09-02 re-check).
missing from PHASE_VERIFIERS: []
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

### 2.40 — declared and machine-enforced phase count (GENERATED from the manifest)

**Source of truth:** `SOPS/presentation-slide-craft/PIPELINE-MANIFEST.json`, `manifest_version` and the
`phases[]` array. The declared phase count is **generated, never hand-written**: read it mechanically by
loading the JSON and counting `len(phases)` — verified in this worktree:

```
manifest_version = PIPELINE_MANIFEST["manifest_version"]
declared_phase_count = len(PIPELINE_MANIFEST["phases"])
```

The numbers that expression prints are the live manifest's, whatever they are at read time (the
2026-08-19 RUN 2 snapshot read one value; the Wave D merge raised it; GATE 4 of
`scripts/ci/presentations-drift-gates.sh` fails CI if any doc that restates this count goes stale
against the manifest). Do not copy a number from this document into another document — link here, or
read the manifest the same way this document does. At the 2026-09-02 re-check the live read was
manifest_version 55, declared count 55.

All declared phase ids, sorted mechanically by the true `order` field
(`sorted(phases, key=lambda p: p["order"])`, executed directly against the live manifest in this
worktree, not hand-ordered). Wave D's new P-U COPY/DESIGN/HTML/GHL/COLLATERAL/FORM-GATE/QC ids are
**bolded**; the Wave C BUILD ids keep their RUN 2 positions:

| # | order | id | # | order | id |
|---|---|---|---|---|---|
| 1 | -1 | `P-CONVERTER` | 29 | 5.3 | `P-U-HTML-CHECKOUT` |
| 2 | -0.5 | `P-0.5-RESEARCH` | 30 | 5.4 | `P-U-HTML-VSL` |
| 3 | 0.1 | `P0A-INTAKE` | 31 | 5.6 | `P-U-FORM-GATE` |
| 4 | 0.14 | `P-SP-CLAIM` | 32 | 6.2 | `P-U-GHL-SALES` |
| 5 | 0.15 | `P-SP-INTAKE` | 33 | 6.4 | `P-U-GHL-VSL` |
| 6 | 0.16 | `P-SP-INTAKE`-TRACE | 34 | 7.5 | `P-SHIFT-QC` |
| 7 | 0.2 | `P0B-PRIORITY` | 35 | 8 | `P8-ASSEMBLE` |
| 8 | 3 | `P3-ARC` | 36 | 8.1 | `P8.1-PDF-EXPORT` |
| 9 | 3.5 | `P-3.5-RESEARCH-MAP` | 37 | 8.2 | `P8.2-GUIDE` |
| 10 | 3.6 | `P-U-SALES-COPY` | 38 | 8.25 | `P8.25-WORKBOOK` |
| 11 | 3.7 | `P-U-CHECKOUT-COPY` | 39 | 8.5 | `P9-SPEECH` |
| 12 | 3.8 | `P-U-VSL-RESEARCH` | 40 | 8.52 | `P8.4-FISH-TAG` |
| 13 | 3.9 | `P-U-VSL-COPY` | 41 | 8.54 | `P9-SPEECH`-WEBINAR-INTRO |
| 14 | 4 | `P4-COPY` | 42 | 8.55 | `P9.1-SPEECH-PDF` |
| 15 | 4.1 | `P-SP-STRUCTURE` | 43 | 8.6 | `P-SPEECH-QC` |
| 16 | 4.15 | `P-SP-P3-HYGIENE` | 44 | 8.65 | `P-QC-AGGREGATE` |
| 17 | 4.2 | `P-U-DESIGN-SALES` | 45 | 8.7 | `P9.5-NOTES-SYNC` |
| 18 | 4.2 | `P1Q-COPY-QC` | 46 | 8.75 | `P-U-SALES-BUILD` |
| 19 | 4.3 | `P-U-DESIGN-CHECKOUT` | 47 | 8.76 | `P-U-CHECKOUT-BUILD` |
| 20 | 4.4 | `P-U-DESIGN-VSL` | 48 | 8.77 | `P-U-FORM-CHECKOUT` |
| 21 | 4.5 | `PF-DESIGN` | 49 | 8.8 | `P-U-COLLATERAL` |
| 22 | 4.6 | `P-TYPO-QC` | 50 | 8.9 | `P9.2-GHL-UPLOAD` |
| 23 | 4.7 | `P4-PROMPT` | 51 | 8.92 | `P9.6-WEBINAR-VIDEO` |
| 24 | 4.8 | `P-PROMPT-QC` | 52 | 8.93 | `P-U-VSL-BUILD` |
| 25 | 4.85 | `P-STYLE-PREVIEW` | 53 | 8.95 | `P7-TELEPROMPTER` |
| 26 | 4.9 | `P4-RENDER` | 54 | 9 | `P9-DELIVER` |
| 27 | 4.95 | `P-IMAGE-QC` | 55 | 9.05 | `P-U-QC` |
| 28 | 5.2 | `P-U-HTML-SALES` |  |  |  |

`DEPT/scripts/run_signature_deck.py`'s `declare_plan()` still sorts **every declared phase** by `order`
to build the unfiltered `steps`/`total` fields of `declared_plan.json` (the attestation-chain contract,
per B2, is unchanged in shape — only the count moved). `DEPT/scripts/phase_verifiers.py`'s
`PHASE_VERIFIERS` registry is checked programmatically against the manifest's declared ids in this
worktree:

```
total manifest ids: len(PIPELINE_MANIFEST["phases"])          (read live: registry parity 55/55 at the 2026-09-02 re-check)
total registered in PHASE_VERIFIERS: len(PHASE_VERIFIERS)     (55 at the same re-check)
missing from PHASE_VERIFIERS: []
```

**Enforcement surfaces** (the DAG builder, the runner's raw `_phase_index`, the engine's raw walk, and
`phase_verifiers.py`) all operate over the full declared phase set — registry parity is asserted, not
assumed, and drift fails CI via the drift gates.

### 2.31+ — executed count now depends on deck type AND upsell election

The executed (client-visible) phase count is **not one number** — it is the declared phase set minus
every conditional family this deck's intake proves inapplicable. The conditional-phase families, each
verified by reading the actual gating logic in
`DEPT/scripts/presentation_job/phases.py` (`_CONVERTER_ONLY_PHASE_IDS`, `_SP_ONLY_PHASE_IDS`,
`_SALES_CHECKOUT_ONLY_PHASE_IDS`, `_VSL_ONLY_PHASE_IDS`, and the `defers_unless` walk in
`Engine._client_visible_phases`) and `DEPT/scripts/run_signature_deck.py` (mirrored 1:1):

| Family | ids | Filtered OUT when |
|---|---|---|
| Content-conversion | `P-CONVERTER` (1) | `creation_mode` known AND not content-first |
| Signature-only | `P-SP-INTAKE`, `P-SP-INTAKE-TRACE`, `P-SP-STRUCTURE`, `P-SP-P3-HYGIENE` (4) | `deck_type` known AND not `signature_presentation` |
| Sales/checkout upsell — Wave C BUILD + Wave D COPY/DESIGN/HTML/GHL/COLLATERAL (11) | `P-U-SALES-COPY`, `P-U-CHECKOUT-COPY`, `P-U-DESIGN-SALES`, `P-U-DESIGN-CHECKOUT`, `P-U-HTML-SALES`, `P-U-HTML-CHECKOUT`, `P-U-GHL-SALES`, `P-U-COLLATERAL`, `P-U-SALES-BUILD`, `P-U-CHECKOUT-BUILD`, `P-U-FORM-CHECKOUT` | `WANT_SALES_CHECKOUT` known AND != "yes" |
| VSL upsell — Wave C BUILD + Wave D RESEARCH/COPY/DESIGN/HTML/GATE/GHL (7) | `P-U-VSL-RESEARCH`, `P-U-VSL-COPY`, `P-U-DESIGN-VSL`, `P-U-HTML-VSL`, `P-U-FORM-GATE`, `P-U-GHL-VSL`, `P-U-VSL-BUILD` | `WANT_VSL_PAGE` known AND != "yes" |
| Both-upsell QC | `P-U-QC` (1) | both flags known AND both != "yes" |

`P-SP-CLAIM` is still never filtered (runs on every deck as the router). An unknown/absent signal
**always widens**, never narrows — the same fail-safe direction on every family.

**Mechanical derivation actually run in this worktree (2026-09-02 re-check)** — the real
`run_signature_deck._client_visible_phases()` and the real
`presentation_job.phases.Engine._client_visible_phases()` called against real `intake.json` fixtures;
both methods agree exactly:

```
                          both        sales-only      VSL-only       both
                          declined    (VSL no)        (sales no)     elected
standard-from-scratch  ->   31            43              40             50
signature              ->   35            47              44             54
content-conversion     ->   32            44              41             51
```

**Unknown-flag / not-yet-asked cases — the numbers `test_client_step_count.py` pins directly,
re-run 2026-09-02, all 26 passing:**

```
standard-from-scratch, deck known, upsell flags unset  -> 44   (test_standard_from_scratch_is_31)
signature, deck known, upsell flags unset              -> 48   (test_signature_is_35)
content-conversion, deck known, upsell flags unset     -> 45   (test_content_conversion_is_32)
fully unknown deck (no intake.json / empty object)     -> 55   (test_unknown_intake_fails_safe_to_full_36)
```

(The flags-unset numbers are BELOW both-elected because an unelectable upsell still widens to visible
while a proven decline hides its 11/7 phases — widening is fail-safe for INTAKE uncertainty, not an
optimization.)

**Read this carefully — it is the single most confusing part of this document, so it gets its own
paragraph.** "31 phases execute on a standard deck" was always implicitly "...when neither upsell
applies." That is still true and still the right number for a declined-upsells standard deck. But a
REAL client run's client-facing count depends on what they actually elected — a standard deck whose
client said yes to sales+checkout (the default) sees **50** (or 43 with VSL-only, 40 with sales-only
forfeited for a VSL), not 31, and `declare_plan()`'s outbound message will correctly quote the elected
count, not 31. Any document that states a bare "31" without naming the upsell-election assumption
behind it is now incomplete. **Do not pick one number as "the" standard-deck count — state the
election it assumes, or link here.**

**Filter surfaces** — `run_signature_deck.py` (B2, pre-existing) and `presentation_job/phases.py`
(B2b, pre-existing) were extended by Wave C unit C1 to the BUILD-only upsell signals, then again by the
Wave D merge (DESIGN-OPUS §4, 2026-09-01) so the full P-U COPY/DESIGN/HTML/GHL/COLLATERAL/QC families
honor their own `defers_unless` gates through the same fail-safe shape (verified by reading
`_SALES_CHECKOUT_ONLY_PHASE_IDS` / `_VSL_ONLY_PHASE_IDS` / `Engine._client_visible_phases`'s
`defers_unless` branch in both files). This is pinned by `DEPT/scripts/tests/test_client_step_count.py`
(26 tests, all passing at the 2026-09-02 re-check) and
`DEPT/scripts/tests/test_engine_client_report.py`.

### 2.~67 — honest end-to-end, including the ~12 scripted gates outside `phases[]`

**Unchanged arithmetic shape, new base.** The ~12 scripted gates/steps outside `phases[]` (the intake
interview, poll/ingest, 6 entry gates in `presentation-canonical-entry.sh`, 3 phase-0 preflights, the
postflight bundle gate, delivery interlock, and process certificate) were not touched by Wave C — none
of them read `phases[]`'s length directly, they are independent scripted checkpoints. Re-verified
present in this worktree (same files/symbols as RUN 1: `deck-intake-driver.py`,
`presentation-intake-poll.sh`, `presentation-canonical-entry.sh`'s GATE 0/0b/1/1b/2/3,
`build_deck.py`'s `AF-OCR-ENGINE-MISSING`/`detect_platform`/`AF-KIE-BALANCE`, `fix_bundle_complete.py`,
`delivery_gate.py`, `prove-deck.py`).

**Arithmetic:** `len(phases[])` (read live from the manifest — the declared count at RUN 2's snapshot
was 40, the Wave D merge raised it; today it is what §2.40's generated line says) + ~12 (the scripted
gates above) ≈ **~67**, not ~48 or ~52 — the honest end-to-end count moves with the declared phase
count, because the ~12 outside-manifest gates wrap the WHOLE phase list, not a fixed subset of it.
Stated as **"~67"** deliberately, not as a precise count, for the same reason RUN 1 stated "~48"
imprecisely: the intake interview is conversational, not a single mechanical checkpoint. **RUN 1's
"~48" and RUN 2's "~52" are both stale — update any document that still says either to "~67," or
better, link here instead of restating the number. The Quick Reference row already reads "~67."**

**Ticket 6 (2026-08-27) added one MECHANICAL gate inside the phase-walk loop itself** (AF-INTAKE-GATE,
`presentation_job/phases.py`'s `Engine._check_intake_gate`), distinct from both the declared manifest
phases and the ~12 outside-manifest scripted gates above — it does not add a phase or a script step, so
it does not change the ~67 arithmetic. It blocks P0B-PRIORITY and every phase after it from starting
unless `working/copy/intake.json` already exists on disk, closing the gap where a content-authoring
phase could previously run before intake ever completed.

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
those documents predate Wave C and describe the pre-Wave-C world (the 36-phase era, upsell branch 0%
wired) — not a disagreement, a timeline difference. Where this document disagrees with the RUN 2
dispatch brief's own prose: **none found** — the brief's instruction to "derive mechanically, don't copy
numbers from the brief" was followed, and the derived numbers (the declared count at that RUN-2
snapshot, later raised by the Wave D merge; 31/34/35 standard, 35/38/39 signature, 32/35/36
content-conversion by upsell election as of that snapshot — superseded by the 2026-09-02 regenerated
matrix in §2, which reads the live manifest; landed-with-two-gaps upsell branch status) match what the
brief anticipated in shape, though the brief did not itself state the full election matrix — that matrix
is this document's own contribution, not copied from anywhere.

*Last verified: 2026-09-02, Fix 83 regeneration against manifest_version 55 (was: 2026-08-19, Unit
COUNTS-R2, RUN 2).*
