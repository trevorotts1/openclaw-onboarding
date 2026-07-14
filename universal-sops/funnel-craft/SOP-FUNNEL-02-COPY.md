# SOP-FUNNEL-02: AUTHOR THE SACRED 12-SECTION COPY

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Master authority:** `49-signature-funnel/MASTERDOC.md` §1–2 + `structure/funnel_structure.json`
**Owning role:** Signature Funnel Specialist
**Stage:** P1-COPY (+ P8-DERIVE for the derived pages)
**Produces:** `working/copy/copy_ledger.json`
**Prover:** `49-signature-funnel/scripts/prove_sf_copy.py`

---

## 0. WHY THIS SOP EXISTS

The 12 section names and every char/word band are the SACRED IP. "Never change the name of my page
sections." A section that is renamed, reordered, over-length, or missing its required CTA discipline is
a hard `AF-FUN-*` auto-fail. The prover measures STRIPPED text — whitespace never satisfies a floor and
a self-reported count is never trusted.

## 1. THE MAIN PAGE — 12 SECTIONS (verbatim bands)

| Sec | Name | Band | Rule |
|---|---|---|---|
| 1 | The Big Bold Claim / Promise | 180–225 chars | product title present; labeled CTA |
| 2–4 | The Big Bold Pain 1/2/3 | 180–225 chars each | 2nd person; NO questions; labeled CTA; three DIFFERENT pains (circumstantial / private / witnessed) |
| 5 | The Big Bold Why | ≤30 words | starts "That's the reason why…"; CTA |
| 6 | The Big Bold Who | ≤30 words | 3–6 personas; **NO CTA** |
| 7 | The Big Bold What | 70–120 words | 5–10 specific bullets |
| 8–9 | The Big Bold Benefit 1/2 | ≤30 words | **NO CTA button** |
| 10 | The Big Bold Benefit 3 | ≤30 words | inspirational CTA button (peak-end) |
| 11 | The Big How To | 100–150 words; **NO button** | 5–10 steps; steps 1–6 each 89–116 chars; step 7 ≤170; MUST include share / email-bonus / founder-text / community steps |
| 12 | The Big Bold Heartfelt Message | 100–150 words | 6 labeled parts; part 2 starts "I used to be just like you…" |

## 2. GENERATION CRAFT (governs the writer; the bands are the machine bar)

### Step 0 — Copywriter-persona grounding (MANDATORY, fail-closed — FIX-XC-02a)

Before writing a single section, ground the copy in the matched copywriter persona. This is a hard,
fail-closed gate — generation MUST NOT unlock without it.

1. **Select** the copy VOICE for this task — consume the task's already-acquired persona bundle
   (Skill 6's persona-bundle-acquisition ladder, B-U1/U15: `routing/persona-bundle-receipt.json` /
   `task['persona_bundle']`) when one is present, or **run the selector WITH `--blend`** against the
   CLIENT's providers when none was threaded:
   `python3 23-ai-workforce-blueprint/scripts/persona-selector-v2.py --blend --task "<page-type> <funnel-type> <ICP>" --department marketing`
   (voice-first blend selection — do NOT default by habit; the VOICE persona is the bundle's
   `voice_persona_id`, catalog-wide per D1/B-D1, never limited to a fixed surname list).
   `49-signature-funnel/scripts/copy_persona_blend_seam.py` is the machine-callable seam that
   renders the log entry + the `{{BLEND_DIRECTIVE}}` prompt variable from a bundle (below).
2. **Log** the result to `persona-selection-log.md` in the run dir — the entry MUST keep naming a
   `selected_persona: <registered-slug>` (the bundle's VOICE persona id — back-compat, unchanged
   shape) and `selector_ran: true`, and ADDS `voice_persona:` / `topic_persona:` / `task_persona:` /
   `blend_directive_sha:` lines (B-U3/U17) so the full blend is auditable, not just the voice.
3. **Load and apply** the matched persona-blueprint's **Section 4 "Agent Governance Framework"**
   (Execution Standard / Decision Logic / Definition of Done / Failure Patterns) via the copy seam in
   `49-signature-funnel/prompts/funnel-copy-prompts.md` (`{{PERSONA_TASK_MODE}}` / `{{SELECTED_PERSONA_ID}}`
   / `{{BLEND_DIRECTIVE}}`) — the persona's NAME alone does not load it; the copy is written TO that
   governance AND to the full audience+topic+task SYNERGY directive (B-U3/U17), guardrail included.
4. **Enforcement:** `prove_sf_intake.py` fails closed with **AF-FUN-INTAKE-PERSONA-LOG** when the
   persona-selection-log is absent or names no registered slug (mirrors FAB-QC D4). No log → no generation.
   The regex parses `selected_persona:` (or `applied_persona:` / `copy_persona:`) unmodified — the
   ADDED `voice_persona:` / `topic_persona:` / `task_persona:` / `blend_directive_sha:` lines never
   interfere with it.

- **Harmony Chain** — the 12 sections are ONE escalating argument; carry a word/image/idea from
  section N−1 into N; never reset the topic.
- **One CTA Voice** — ONE first-person possession/transformation CTA phrase per page (`Start My ___`,
  `Claim My ___`, `Reserve My Seat`), labeled `CTA: <phrase>` in every CTA-bearing section.
- **Pain Ladder** — Sec 2 circumstantial, Sec 3 private, Sec 4 witnessed; 2nd person, present tense,
  never a question.
- **Benefit Ladder** — Sec 8 felt, Sec 9 measured, Sec 10 become; peak-end CTA on Sec 10.
- **Specificity Laws + truth gate** — numbers beat adjectives; every bonus / founder-text / community
  confirmed real at intake; no fabricated urgency.

## 3. THE DERIVED PAGES (P8-DERIVE)

Author against the six profiles: `main`, `upsell`, `downsell`, `upsell-2`, `downsell-2`, `thank-you`
(+ `checkout` microcopy for 7-step). Derived pages **exclude Sections 8–11** and **replace Section 12**
with the renumbered **Section 8**:

- **Upsell / Upsell-2:** "7 Reasons To Commit To Your ____ Future" — exactly **7** numbered reasons
  (AF-FUN-SEC8REPL-COUNT). Upsell-2's blank-fill MUST differ from OTO1; Upsell-2 is a categorically
  different offer (change KIND, not size).
- **Downsell / Downsell-2:** "When Time Runs Out" — the **7** things they'll miss. CTA every section.
- **Thank-You:** the three labeled parts (TY-1 120–180 chars / TY-2 4–6 steps each 89–116 chars /
  TY-3 ≤170 chars). **NO offer CTAs** — utility buttons only. **After Downsell 2 the funnel never
  pitches again.**

## 4. VERIFY BEFORE ADVANCING

```
python3 49-signature-funnel/scripts/prove_sf_copy.py working/copy/copy_ledger.json
```

Exit 0 = every profile cleared its SACRED bands and P2-PROMPTS may begin. A failing section re-authors
ONLY itself under the bounded retry cap; copy cannot advance to image prompts until all sections pass.
Never floor, cap, or rename a section to make a gate pass — escalate instead.
