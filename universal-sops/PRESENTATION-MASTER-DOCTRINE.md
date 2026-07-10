# PRESENTATION MASTER DOCTRINE — THE ONE RECONCILED PROCESS
**The canonical doctrine home for the Presentations department.**
**Version 1.0 — 2026-07-10 (doctrine-schism reconciliation)**
**Owner authority:** Director of Presentations. **Gate authority:** QC Specialist.
**Status:** CANONICAL. This document is the single doctrine index the department reads
first. Where any other presentation document contradicts it on the *shape of the
process*, this document wins and the other document is the one to fix.

---

## 0. WHY THIS DOCUMENT EXISTS

For a period the department carried **two contradictory operating doctrines wearing one
name**:

1. A newer **deterministic-pipeline** SOP (`CLIENT-WEBINAR-DECK-SOP.md`, the "Slate"
   builder model): *write one `slides.json`, run `build_deck.py`, register the `.pptx`.*
2. An older **multi-phase, multi-role authoring pipeline** (the ~30 role files + the
   `SOP-*` cluster) that cites a numbered "master SOP" (Sections 4.1, 4.2, 4.2A, 4.3,
   4.4, 5.1, 5.2, 5.4, 5.5, 6.1, 7.2, 7.5, 9.0, 11.3, 11.4 …) whose numbered sections **no
   longer exist in any single file**.

An agent that followed only doctrine (1) wrote a `slides.json`, ran the entry command, and
slammed into `build_deck.py`'s ~50 preflight gates demanding a research brief, copy-QC
report, typography artifacts, owner approvals, and per-slide 9,000–18,000-char rich prompt
files that doctrine (1) never told it to produce — an impossible-to-complete sanctioned
path, so it improvised (went off-script). An agent that followed only doctrine (2) chased
"master SOP Section 4.4" citations into a void.

**The resolution is not to pick one and delete the other. The two doctrines are the two
LAYERS of ONE process.** This document states that reconciliation once, authoritatively,
and gives the crosswalk that makes every "master SOP Section N" citation resolve.

---

## 1. THE ONE PROCESS — TWO LAYERS OF A SINGLE PIPELINE

> A deck is built by **ONE** pipeline with **TWO** layers. They are not two products and
> not two choices; they are two stages in strict sequence. Layer A *makes the artifacts*;
> Layer B *renders and delivers them deterministically*. Layer B physically refuses to run
> until Layer A's artifacts exist — which is exactly why an agent that skips Layer A hits
> the preflight wall.

### LAYER A — THE AUTHORING PIPELINE (how the artifacts get made)
The multi-phase, multi-role pipeline governed by `PIPELINE-MANIFEST.json` and the role
library. This is the intake interview, priority-shift diagnosis, arc allocation, research,
copywriting, copy-QC, typography, **rich prompt authoring (the 9,000–18,000-char per-slide
prompt files)**, prompt-QC, and speech. Its output is the set of on-disk artifacts the
renderer consumes: `working/copy/intake.json`, `slides.json` / `slides_copy.md`,
`working/prompts/slide-NN.txt`, the QC reports, `PRESENTERS-SPEECH.md`, etc. **Roles,
phases, and doctrine (the pitch doctrine, the arc, the ten required components, the hook
ceiling) live here.** The manifest is the single source of truth for the phase order; the
runner (`run_signature_deck.py`) serves that order one step at a time (see §3).

### LAYER B — THE DETERMINISTIC RENDER + DELIVERY (how the render is invoked)
`CLIENT-WEBINAR-DECK-SOP.md` (the "Slate" contract). Once Layer A's artifacts exist, the
render is invoked deterministically: `build_deck.py` reads the pre-authored rich prompts
**verbatim** (it does **not** compose prompts and has **no** image tool of its own),
renders every image on kie.ai (`gpt-image-2-text-to-image` / `-image-to-image`, 16:9, 2K —
all pinned inside the script), verifies each PNG, assembles the full-bleed `.pptx`, and
runs the postflight completeness gate + delivery interlock over the seven-file bundle.

### THE HANDSHAKE BETWEEN THE LAYERS (the point that was lost)
- Layer A **authors** the rich prompt files and the copy; Layer B **consumes** them
  verbatim. The retired claim that "the script composes the KIE prompt mechanically" is
  **false** for the current engine and is a banned residual pattern.
- The single entry command (`presentation-canonical-entry.sh` → `run_signature_deck.py` →
  `build_deck.py`) enforces Layer A **before** Layer B: `build_deck.py`'s preflight requires
  the full Layer-A artifact set, and `run_signature_deck.py` refuses to attest a phase out
  of order. "Finishing at a bare `.pptx`" is a forbidden shortcut — the deck is DELIVERED
  only when the full bundle exists.
- **The correct mental model for every builder:** *you are always running Layer A up to the
  render, and Layer B is the render+delivery the runner dispatches for you.* You never
  choose between them.

---

## 2. THE CANONICAL DOCTRINE HOME (the source-of-truth rule)

**`universal-sops/` is the canonical doctrine ROOT for the Presentations department.**
The department copy at
`23-ai-workforce-blueprint/templates/role-library/presentations/sops/` is a **generated
mirror** of it. When a SOP exists in both places and they disagree, **the `universal-sops/`
copy wins** and the department mirror is the one to regenerate.

Canonical clusters under `universal-sops/`:

| Doctrine area | Canonical home (universal-sops/) |
|---|---|
| The deterministic render/delivery contract (Layer B) | `CLIENT-WEBINAR-DECK-SOP.md` |
| This doctrine index + the section crosswalk | `PRESENTATION-MASTER-DOCTRINE.md` (this file) |
| Slide-craft rules, pipeline manifest, master QC ruleset | `presentation-slide-craft/` (incl. `PIPELINE-MANIFEST.json`, `MASTER-QC-AUTOFAIL-RULESET.md`, `SOP-SLIDE-01..06`) |
| Typography / layout / logo design system (archetypes A1–A5) | `presentation-design-system/` (`02..05-SOP-*`) |
| Image / kie call mechanics / model manifest / exemplar prompt | `presentation-image-library/` (`SOP-IMG-01..04`) |

**Promotion backlog (flagged for the universal-sops-reconcile unit, spec §11 A7):** the
PITCH / STORY / PRIORITY / SIGPRES / MODE / OBJECTION / VISION / ENGINE / HARMONY /
PROCLAMATION / PERSON / CAST doctrine SOPs currently live **only** in the department
`sops/` directory. They carry doctrine that the crosswalk below points at, so they must be
**promoted into a `universal-sops/` cluster** (e.g. `presentation-pitch-craft/`) and the
department copies re-declared as mirrors. Until that promotion lands, the department
`sops/` copy of those specific files is the interim canonical location — noted per-row in
§4. **This foundation unit establishes the rule and the crosswalk; the file promotion and
the per-citation repair are the A6 (roles/SOP text) and A7 (universal-sops reconcile)
units.**

---

## 3. THE PROCESS IS SERVED ONE STEP AT A TIME (enforcement, not description)

Doctrine is not held in 30 documents an agent must reconcile in its head. **The RUNNER is
the agent's interface to what is next.** The orchestrating loop is:

```
run_signature_deck.py --run-dir DIR --next        # emits ONLY the single next phase
   → do EXACTLY that one phase (produce its produces_artifact per the cited sop_refs)
   → run_signature_deck.py … --phase <ID>          # verifies the artifact + attests it
   → run_signature_deck.py --run-dir DIR --next    # emits the following step
```

`--next` reads `PIPELINE-MANIFEST.json` + the on-disk attestation ledger and returns one
payload: the next required phase, its owning role, the artifact contract (path + the
manifest's `required_brief_categories` + whether a substance verifier runs), the SOP refs,
the gate codes, and the exact attest command. **It deliberately refuses to reveal any phase
further ahead.** Because attestation is order-enforced (`check_phase_preconditions`,
AF-PHASE-SKIPPED) and every governed phase has a substance verifier, the agent physically
cannot run the process out of the order the runner serves it. `--plan` remains available
for a read-only view of the whole plan.

---

## 4. THE SECTION CROSSWALK — "master SOP Section N" → its live home

Every legacy citation of the form "master SOP Section N.N" resolves to the live home
below. Repointing the citations in the role files to these homes is the A6 unit's
mechanical text task; this table is the authority for that repair. Homes marked **[dept]**
live (for now) only in the department `sops/` dir and are on the §2 promotion backlog;
homes marked **[univ]** already live in a `universal-sops/` cluster.

| Legacy citation | Doctrine it names | Live home |
|---|---|---|
| Section 2 | run-dir working-tree layout | `PIPELINE-MANIFEST.json` (`produces_artifact` paths) + `director-of-presentations` SOP 9.x **[univ manifest]** |
| Section 3.1 | intake questions (incl. Q5 VIP) | `SOP-SIGPRES-01-EIGHT-QUESTIONS-…` + `deck-intake-questions.json` + Director/Buddy intake SOP **[dept]** |
| Section 3.2 | no-fabrication of proof | `SOP-PITCH-02-VALUE-STACK-AND-PROMISES` (proof) + `SOP-SLIDE-00` AF ruleset + `devils-advocate` SOP 9.1 **[dept]** |
| Section 3.4 | Mode B / the three creation modes | `SOP-MODE-00-THREE-CREATION-MODES` **[dept]** |
| Section 4 | offer / pitch mechanics (Hormozi) | `SOP-PITCH-01..06` cluster **[dept]** |
| Section 4.1 | arc allocation table | `SOP-STORY-01-VILLAIN-HERO-ARC` + `SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE` + `director-of-presentations` SOP 9.3 **[dept]** |
| Section 4.2 | the proven 7-section flow | `SOP-STORY-01` + `SOP-PRIORITY-02` **[dept]** |
| Section 4.2A | the BlackCEO Signature Webinar Arc (labels A–J) | `SOP-STORY-01-VILLAIN-HERO-ARC` + `slide-copywriter` SOP 9.x **[dept]** |
| Section 4.3 | the 18/24-point Pitch Doctrine | `SOP-PITCH-*` + `SOP-PROCLAMATION-01`; reproduced verbatim (points 1–18) in `devils-advocate-presentations` SOP 9.1 (the operational home for the Kill List) **[dept]** |
| Section 4.4 | the ten required presentation components | enumerated in `director-of-presentations` SOP (`checklist_of_promises`); enforced in `qc-specialist-presentations` SOP 9.5 structural-completeness **[dept]** |
| Section 5.1 | hard copy limits (headline/subhead/slide) | `SOP-SLIDE-04-DECK-DENSITY-AND-PACING` + `slide-copywriter` SOP + `SOP-SLIDE-00` AF-C8/AF-OBI **[univ slide-craft]** |
| Section 5.2 | the per-slide entry template + PRESENTER NOTE | `slide-copywriter` SOP 9.x (the copy-block template) + `presenter-coach` / `presenters-guide-specialist` SOPs **[dept]** |
| Section 5.4 | guarantee types + real scarcity/urgency | `SOP-PITCH-02` (guarantee) + `SOP-OBJECTION-01` + `offer-price-strategist` SOP **[dept]** |
| Section 5.5 | the price sequence (both modes, VIP) | `SOP-PITCH-01-SLOW-DROP-PROCESS` + `offer-price-strategist` SOP 9.x **[dept]** |
| Section 6.1 | hook ceiling + anti-footer + density floor | `SOP-SLIDE-03-HOOK-DOCTRINE` + `qc-specialist-presentations` copy-QC criterion **[univ slide-craft]** |
| Section 7.2 | the five archetypes A1–A5 | `presentation-design-system/04-SOP-variable-layout-anti-template.md` (`SOP-DESIGN-03`) + `brand-steward` SOP **[univ design-system]** |
| Section 7.5 | the gold-standard exemplar prompt | `presentation-image-library/SOP-IMG-01-KIE-CALL-MECHANICS.md` + `prompt-author-presentations` SOP + `brand-steward` SOP 9.3 **[univ image-library]** |
| Section 9.0 | the MODEL MANIFEST (declared at echo) | `SOP-IMG-01-KIE-CALL-MECHANICS` + `director-of-presentations` SOP 9.x + `build_deck.py` `MODEL_*` pins **[univ image-library]** |
| Section 11.3 | QC render step + ≥ 8.5 pass threshold | `MASTER-QC-AUTOFAIL-RULESET.md` (`SOP-SLIDE-00`) + `qc-specialist-presentations` SOP 9.x **[univ slide-craft]** |
| Section 11.4 | delivery (destination + bundle) | `SOP-PITCH-05-DELIVERABLE-BUNDLE` + `delivery-concierge` SOP + `CLIENT-WEBINAR-DECK-SOP.md` §9a **[dept + univ]** |

**Rule for citations going forward:** cite the **live SOP file** (or its role SOP 9.x),
never a bare "master SOP Section N." A doctrine-residual check bans the reintroduction of
dead "master SOP Section 4.4"-style citations that are not backed by an entry in this
crosswalk.

---

## 5. WHAT THIS RECONCILIATION DOES AND DOES NOT CHANGE

- **Does NOT change the render path.** `build_deck.py`'s image pipeline, pins, floors, and
  gates are untouched by this document.
- **Does NOT delete either doctrine.** Layer A (the role pipeline) and Layer B (the Slate
  deterministic contract) are both retained — restated as the two layers of one pipeline.
- **DOES make `universal-sops/` the canonical root** and the department `sops/` a mirror.
- **DOES make the runner (`--next`) the agent's interface to the process** so the process
  is served one enforced step at a time instead of read out of 30 sometimes-conflicting
  documents.
- **DOES resolve every "master SOP Section N" citation** via §4, so the authoring pipeline
  no longer points into a void.

*Downstream units (per spec §11): A6 repoints the role-file citations to the §4 homes and
rewrites `BUILDER-PROMPT.md` to the real Layer-A→Layer-B contract; A7 promotes the [dept]
SOPs into `universal-sops/` clusters and re-declares the mirrors. This document is the
foundation both build on.*
