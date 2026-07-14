# Funnel & Automation Build-Quality Rubric (FAB-QC) — the standing ≥ 8.5 build gate

**Scope:** EVERY Skill-6 funnel build AND EVERY Skill-44 automation build.
**Threshold:** **8.5 / 10** (the binding repo-wide bar — same as `QC-PROTOCOL.md`, the Skill-44
8-dimension rubric, Skill-23 `funnel_rubrics.py`, and Skill-6 `QC.md`. Do NOT introduce a new
threshold.)
**Scorer:** `shared-utils/fab_qc.py` (one shared, importable, deterministic scorer — both skills
use it, mirroring how `flex.py` is the shared matcher core).
**Wrappers:** Skill 6 → `06-ghl-install-pages/qc-built-funnel.sh <slug>` · Skill 44 →
`44-convert-and-flow-operator/qc-built-workflow.sh … --fab` (overlay AFTER WF-1..21).

---

## Why this exists

The mechanical gates are **library-blind**:

- Skill 44's `qc-built-workflow.sh` scores the EXPORTED workflow JSON on WF-1..21 + an
  8-dimension weighted rubric — but it never opens the **matched automation template**, the
  `copy_persona`, or the recorded **flex decision**. A workflow can score 10/10 while drifting
  from the template it was matched to, shipping thin copy, ignoring the persona, or force-copying
  a template over an explicit user spec.
- Skill 6's only per-build bar is `ghl_verify.render_check` (HTTP 200 + marker in the hydrated
  DOM). That proves the page **loads** — not that it is faithful to the matched template,
  substantive, persona-grounded, or flexibility-honored.

FAB-QC is a **SUPERSET OVERLAY** on top of those mechanical floors — it does **not** replace
them. `ghl_verify` (funnels) and WF-1..21 (automations) remain the **hard mechanical floor**;
FAB-QC adds the six library-aware dimensions they are blind to and is itself the FLOOR for the
`render/soundness` dimension (D3), so a build can never "buy back" a 5xx or a WF FAIL.

---

## The six dimensions (weights sum to 100; each scored 0–10)

| Dim | Name | Weight | What it proves | Evidence read |
|-----|------|-------:|----------------|---------------|
| **D1** | Template fidelity | 22 | The built artifact reproduces the **matched** template's required structure | funnel: template `pageStructure` vs built pages; automation: template `sequence` vs built steps (channel+order). `routing/match-decision.json` → `template_path` |
| **D2** | Copy substance / real-not-thin | 20 | Every required section/step carries substantive copy | **lengthClass-keyed floors (FIX-XC-04a):** per-slot — body/content slots **≥40 words**, headline/subhead/CTA/button (legitimately-short) slots exempt at **≥4 words**; **page-level** — whole-funnel stripped-word floor keyed to the matched template's `lengthClass` (**short-form ≥350 / medium ≥700 / long-form ≥1,800**, adjustable constants table in `shared-utils/fab_qc.py`) + **ZERO** surviving placeholder tokens (`lorem`, `[HEADLINE]`, `{{…}}` unfilled, `TODO`, "Your text here", "Insert X", empty). Legit merge fields (`{{contact.first_name}}`) are allowed. **Any below-floor slot or page in a live artifact is a HARD MISS** (cannot be averaged away) → bounded re-author loop (verifier ≠ author, ≤5 attempts). Automation steps keep the light ≥4-word floor |
| **D3** | Render / soundness | 18 | The build actually works | funnel: `ghl_verify` `overall_pass` (200 + marker + sections); automation: WF-1..21 mechanical PASS. **This is the hard mechanical floor.** |
| **D4** | Persona grounding | 15 | The matched book persona governs the copy | `persona-selection-log.md` names the template's `books`/`copyFramework.primaryPersona` (funnel) or `copy_persona.primary` (automation). **Fail-closed** if the selector did not run. Template persona slugs/labels are reconciled to the canonical Skill-22 `persona-categories.json` ids via `shared-utils/persona-crosswalk.json` (resolver `shared-utils/persona_crosswalk.py`) so "copy from the personas" pulls the right persona-blueprint |
| **D5** | Flexibility honored (guide-not-rule) | 13 | The template never dominated the user's desire | recorded `intent_mode` + `flex_decision` in `routing/match-decision.json`. An **EXPLICIT** user spec that was NOT honored verbatim (overridden by a template) is a hard miss |
| **D6** | Funnel↔automation link integrity | 12 | When a funnel implies follow-ups, the `_links` pairing was honored | `match-decision.json` → `funnel_template_id` + `linked_automations` vs `_links/funnel-to-automation.json`. **N/A → 10.** A primary follow-up silently dropped (not attached AND not user-overridden) is a hard miss |

**Weighted score** = Σ(dimension_score × weight ÷ 10) ÷ 10, on a 0–10 scale. **Pass** iff
**score ≥ 8.5 AND no hard miss**.

### Hard-miss rule (lifted from `funnel_rubrics.py`)

A load-bearing sub-check that earns 0 **fails its dimension regardless of the weighted mean** —
a missing load-bearing artifact cannot be averaged away. The hard misses are:

- D1: < 50 % of the matched template's required structure reproduced.
- D2: any surviving placeholder token in a **LIVE** artifact (a `trust:MOCK` artifact is exempt).
- D3: any 5xx, `overall_pass:false`, or a WF mechanical FAIL.
- D4: the persona selector did not run / no `persona-selection-log.md` (fail-closed), or the
  matched persona is not named in the log.
- D5: an EXPLICIT user spec was overridden by a template.
- D6: a primary linked follow-up was silently dropped (neither attached nor user-overridden).

---

## How to run it

```bash
# Funnel build (Skill 6) — runs AFTER the canonical ghl_verify gate
06-ghl-install-pages/qc-built-funnel.sh <slug>            # exit 0 iff FAB-QC >= 8.5

# Automation build (Skill 44) — runs AFTER WF-1..21
44-convert-and-flow-operator/qc-built-workflow.sh <wf-id> --fab --evidence <root>

# Direct (any evidence tree)
python3 shared-utils/fab_qc.py --evidence <evidence_root> --kind funnel|automation --json --gate
```

The scorer reads the build's **evidence tree**:

```
<evidence_root>/
  routing/match-decision.json     # {matched_template_id, matched_template_key, template_path,
                                   #  intent_mode, flex_decision, confident_match,
                                   #  funnel_template_id, linked_automations}  <- written by the matchers' step0
  build/fab-artifact.json         # normalised built artifact (pages[]/copy or steps[]/copy)
  scorecard/verify-summary.json   # funnel: ghl_verify summary (overall_pass, pages[].status)
  qc/wf-checklist.json            # automation: WF-1..21 items[] {id,status}
  persona-selection-log.md        # the P1/P2 persona log (D4)
```

The **match-decision receipt** (`routing/match-decision.json`) is emitted automatically by
`funnel_matcher.step0_match` (Skill 6) and `automation_matcher.step0_match` (Skill 44), so D1/D4/
D5/D6 always have evidence to read.

---

## The gate is BINDING

- **Skill 6:** `v2_dispatcher.py` marks a task `verified` only after `ghl_verify overall_pass`
  AND the build is held to FAB-QC ≥ 8.5 (`v2-autonomous-build-sop.md §9` "BUILD-QC GATE").
- **Skill 44:** `INSTRUCTIONS.md` Step 9.3c runs the FAB overlay AFTER WF-1..21 + the 8-dim
  rubric; "done" requires WF-1..21 all PASS **AND** the combined weighted score ≥ 8.5.
- **Loop:** name the lowest dimension, fix it, re-run. Max 5 loops, then escalate (hallucination
  escalation path per `44-.../INSTRUCTIONS.md`).
- **CI guard:** `scripts/guard-fab-qc-gate.sh` asserts the rubric + scorer exist, the threshold
  is 8.5 in both skills, and the two gate call-sites are present — so the gate cannot be silently
  weakened or removed.

---

## Page-QC v2 (U25/B-U11) — the SEMANTIC layer, on top

FAB-QC is structural: D2 counts words and checks for surviving placeholders. It cannot tell flat
copy from moving copy. `shared-utils/page_qc.py` is the semantic scorer FAB-QC is blind to — six
0-10 dimensions (weights sum 100): **S1** conversion likelihood (25), **S2** emotional strength
(20), **S3** voice/persona fidelity (15, judged against the blend directive — the semantic
upgrade of D4), **S4** image quality & congruence (15, vision judge + a deterministic
broken-image sub-check), **S5** search-engine-optimization STRENGTH not presence (15), **S6**
whole-page coherence (10). Same 8.5 threshold, never a new one. Judge: the client's OWN judge
model via `06-ghl-install-pages/tools/model_router.py`'s `qc` role — never Anthropic. Hard
misses: S1 ≤ 3; any S4 broken-image finding; S3 ≤ 3 on a task carrying a blend directive. A
two-pass determinism guard (spread > 1.5 → third pass + median) keeps a single noisy call from
deciding a build. **No judge key → the whole scorecard SKIPs honestly** (`available: false`,
`score: null`, verdict `"page_qc: unavailable (no judge key)"`) — never a fabricated score.
Invoked by `qc-built-funnel.sh` AFTER FAB-QC, on the SAME evidence tree, producing
`scorecard/page-qc.json`; flag-gated behind `PAGE_QC_ENABLED=1` (unset = inert, the revert path).
It **extends, never replaces** FAB-QC — `ghl_verify` and FAB-QC's six dimensions stay exactly as
they are above. `scripts/guard-fab-qc-gate.sh` asserts the Page-QC v2 scorer exists, its
threshold stays 8.5, and its weights still sum to 100.

---

*This rubric is fleet-wide. It is cited by `06-ghl-install-pages/QC.md`,
`44-convert-and-flow-operator/QC.md`, and `SOP-07-Full-Funnel-Build-Orchestration.md`. The shared
scorer is `shared-utils/fab_qc.py`; the shared matcher core it reads from is `flex.py`.*
