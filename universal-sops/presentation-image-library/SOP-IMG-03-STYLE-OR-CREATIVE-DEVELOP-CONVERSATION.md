# SOP-IMG-03 - "Do you have a style, or should I creatively develop one?" Conversation Branch + the NAMED-STYLES Seed

**Cluster:** Image-Gen Mechanics + Design-Library (skill 45) Integration
**Status:** DRAFT for overhaul - adds the missing conversation path + the missing seed file
**Owner roles:** Brainstorming Buddy - Presentations (asks the branch), Brand Steward (resolves it), Style Analyst (writes the seed file)
**Master authority extended:** `presentations/brainstorming-buddy-presentations.md`; `graphics/brainstorming-buddy-graphics.md` Q21/Q22; `SOP-DIU-607` (Named Styles); `45-design-intelligence-library/library/_system/STYLE-CARD-TEMPLATE.md`
**Library-version pin:** SOP-DIU-607 v1.0; STYLE-CARD-TEMPLATE v1.0; PPT-ANALYSIS-SOP v1.1

---

## 0. WHY THIS SOP EXISTS (the two gaps it closes)

The design-library investigation found two gaps in the intake/recall flow:

- **GAP b - no "do you have a particular image style, or should I creatively develop one for you?" path.** The closest today is BB-graphics Q21/Q22 (reference-images? / saved-style-ID?), but there is NO branch that, when the client has NO reference and NO saved style, says "I'll creatively develop a signature style for you - answer these few questions about the look you want," then runs a defined creative-development flow. Today the downstream is just "Style Analyst runs Workflow A from scratch" with nothing to analyze (no reference images = nothing for the analyzer to read).
- **GAP e - the NAMED-STYLES seed file is missing.** SOP-DIU-607 refers to `templates/NAMED-STYLES.md` as the file to copy when `_local/NAMED-STYLES.md` does not exist, but no such template ships in the repo. The agent can construct the YAML inline, but there is no canonical seed.

This SOP writes the conversation branch (including the creative-develop flow), and defines the NAMED-STYLES seed file so it can be committed as a template.

This is build/intake doctrine. None of it is printed on a slide. The branch is asked of the CLIENT in conversation; the answers become intake fields, never slide copy.

---

## 1. PURPOSE

Make the FIRST style question in every Presentations intake a clean three-way branch the agent asks verbatim, with a defined downstream for each branch - including a real "creatively develop one" workflow for clients with no references. Provide the canonical NAMED-STYLES.md seed so signature-style recall (SOP-IMG-04) has a file to write to.

---

## 2. THE BRANCH (asked verbatim by the Brainstorming Buddy - Presentations)

At the style step of intake, the Brainstorming Buddy asks, verbatim:

> **"For the look of your slides - do you have a particular image style in mind? You can: (1) point me at an existing deck, past designs, or reference images you want me to match; (2) tell me a saved style name from your library if you already have one (like 'Style 1'); or (3) let me creatively develop a signature style for you. Which one?"**

The three answers map to three intake values:

| Answer | Intake fields set | Downstream |
|---|---|---|
| **(1) Match a reference** | `STYLE_SOURCE = match_reference`, `STYLE_REFERENCES = <paths/links>`, `ANALYZE_REQUEST = true` | Brand Steward fires Crossing A (SOP-IMG-02 §3): analyze the reference deck → families → Foundation Prompt Block → STYLE BLOCK. |
| **(2) Use a saved style** | `STYLE_SOURCE = saved_style`, `STYLE_ID = <name or ID>` | Signature-style recall (SOP-IMG-04): resolve the alias in NAMED-STYLES.md → card ID@version → STYLE BLOCK. |
| **(3) Creatively develop one** | `STYLE_SOURCE = creative_develop` | The creative-develop flow (§3 below). |

**Hard rule:** the branch is asked on EVERY new deck. The agent does not assume. A deck that proceeds to Phase 2 with `STYLE_SOURCE` unset = a defect (the agent skipped the question and is about to invent a look with no client direction - the exact ad-hoc path that produced the reference failure case's cookie-cutter single-device typography).

This branch supersedes the bare reference question. It is asked once, early, before the STYLE BLOCK is built.

---

## 3. THE "CREATIVELY DEVELOP ONE" FLOW (closes GAP b)

When `STYLE_SOURCE = creative_develop` (the client has no reference and no saved style), the system does NOT silently "run Workflow A from scratch" with nothing to read. It runs a defined micro-interview, builds a style from the answers, renders a small style probe, and gets client sign-off BEFORE the full deck - then optionally saves it as a named signature style.

**Steps:**
1. **Micro-interview (the Brainstorming Buddy asks 3–5 short questions, not 50):**
   - "What feeling should your slides give - premium and calm, bold and high-energy, warm and personal, clean and corporate?" → `STYLE_MOOD`
   - "Any colors that are you, or any you hate?" → `STYLE_COLORS`, `STYLE_AVOID_COLORS`
   - "Photos of real people, illustration, or mostly typography?" → `STYLE_IMAGERY`
   - "Show me one deck, ad, or brand whose LOOK you admire (even if it's not yours)?" → `STYLE_ADMIRED` (optional aspiration anchor; this is admiration, not a deck to match exactly)
   - "Any look you want to avoid - anything that's tested badly or feels off-brand?" → `STYLE_AVOID`
   These reuse the BB question stems already in the files (mood/imagery/avoid) - do not re-invent the question bank; this branch just sequences them into a style-development mini-flow.
2. **Brand Steward drafts a candidate style** from the answers + the client's brand fields (logo, any brand colors). It reaches for the closest seeded reference family (e.g. the gold-standard reference deck bootstrap PPT-001 family that matches `STYLE_MOOD`) as a STARTING scaffold, then adapts the palette/type to the client. This is "creatively develop," anchored on a proven family rather than from a blank page.
3. **Render a style probe (small, before the full deck):** generate 2–3 sample slides (a hook-type slide, a content slide, a price slide) at the candidate style. This is a probe, not the deck.
4. **Client sign-off:** show the probe. "Here's the signature style I developed for you - love it, tweak it, or try a different direction?" Iterate the probe (not the deck) until the client approves.
5. **On approval:** the approved style becomes the deck's STYLE BLOCK foundation. Offer to SAVE it as a named signature style (SOP-IMG-04 / SOP-DIU-607): "Want me to save this as your Signature Style 1 so you can just say 'use Style 1' next time?" If yes → the Style Analyst captures the alias and (if the probe slides warrant) the Deck Systems Specialist registers a production PPT card.

**The creative-develop flow never fabricates the CLIENT'S content** (no invented wins, no invented prices - those rules live in the slide-craft cluster). It develops the visual STYLE only, and it always gets client sign-off on a probe before committing the full deck.

---

## 4. THE NAMED-STYLES SEED FILE (closes GAP e)

SOP-DIU-607 step A.5 says "create the file from the template at `templates/NAMED-STYLES.md` if it does not exist." That template is missing. Below is the canonical seed. It is committed to the repo as a TEMPLATE; the live per-client file lives at `$OC_ROOT/master-files/design-library/_local/NAMED-STYLES.md` (box-level, never repo-committed - it is client data).

**Canonical seed (`templates/NAMED-STYLES.md`):**
```markdown
# NAMED STYLES - {client_slug}
# Per-client alias map: plain-English name -> card ID @ pinned version + frozen refs + overrides.
# Authority: SOP-DIU-607. Owner: Style Analyst. This file lives in _local/ and is NEVER repo-committed (client data).
# Created from templates/NAMED-STYLES.md. One YAML block per approved, named style.

named_styles_version: 1.0
client_slug: "{client_slug}"
generated_at: "{ISO_8601}"

aliases:
  # --- one block per named style; appended at client-approval time per SOP-DIU-607 §A ---
  # - alias: "Signature Style 1"        # plain-English, unique per client, verbatim from the approval record
  #   card_id: "PPT-002-C"              # resolves in INDEX.md; must be production status
  #   card_version: "v1.0"             # pinned; v1.x auto-advances, v2.0 needs CDO confirm + regression render
  #   frozen_refs:
  #     - "/abs/path/to/approved-output.png"   # ground truth for v2.0 regression checks
  #   brand_overrides:                  # only fields where this client diverges from card defaults; empty if none
  #     # BRAND_COLOR_1: "#1A1A2E"
  #   captured_at: "{ISO_8601}"
  #   captured_from_receipt: "{receipt filename}"
```

This seed is empty-but-valid: a fresh client box has a NAMED-STYLES.md with zero aliases, which is correct (no styles saved yet). SOP-IMG-04 reads it; SOP-DIU-607 appends to it.

---

## 5. ENFORCEMENT CHECKS (auto-fail conditions)

| # | Check (trigger) | PASS | AUTO-FAIL |
|---|---|---|---|
| 1 | **Branch asked.** Every new deck intake sets `STYLE_SOURCE` to one of `match_reference` / `saved_style` / `creative_develop`. | Set to a valid value | Phase 2 reached with `STYLE_SOURCE` unset (the question was skipped) |
| 2 | **Creative-develop ran a probe.** When `STYLE_SOURCE = creative_develop`, a style probe (2–3 sample slides) was rendered and client-approved BEFORE the full deck generated. | Probe approved first | Full deck generated with no probe / no client sign-off |
| 3 | **Micro-interview, not a 50-question wall.** The creative-develop flow asked ≤5 short questions. | ≤5 questions | A long interview that re-asks everything (BB anti-pattern) |
| 4 | **Save offered on approval.** On creative-develop approval, the client was offered "save as Signature Style N." | Offer made | Approved style discarded with no save offer (client cannot recall it later) |
| 5 | **NAMED-STYLES file present + valid.** `_local/NAMED-STYLES.md` exists (from the seed) and parses as YAML. | Present + valid | File missing when an alias write is attempted (SOP-DIU-607 would fail) |
| 6 | **No fabricated content.** The creative-develop flow set only VISUAL style fields; it did not invent client wins, prices, or copy. | Style-only | Style flow leaked invented client content |

---

## 6. ESCALATION / REPAIR PATH

| Condition | First action | If unresolved |
|---|---|---|
| `STYLE_SOURCE` unset at Phase 2 (check 1) | Halt; Brainstorming Buddy asks the §2 branch before any prompt is written. | Director of Presentations |
| Client cannot decide between the three branches | Default to `creative_develop` and run the probe flow - it is the safe path that always ends in client sign-off. | Brand Steward |
| Creative-develop probe rejected 3 times | Brand Steward switches the starting scaffold to a different seeded family (different `STYLE_MOOD` match) and re-probes; escalate if still rejected. | Director |
| NAMED-STYLES.md missing (check 5) | Style Analyst creates it from the §4 seed before any alias write. | CDO |
| Client wants to save a style but no production card exists yet | CDO promotes the probe's style to a production PPT card (PPT-ANALYSIS-SOP register step) before the alias is assigned (SOP-DIU-607 requires production status). | CDO |

---

## 7. PASS vs FAIL EXAMPLES

**FAIL (the current gap):** The reference failure case had no reference deck and no saved style. The system never asked the branch; it just built slides with one black-headline-plus-teal-accent-word device on ~40 of 45 slides (the cookie-cutter typography defect, density-floor overhaul). No probe, no client style sign-off. Fails checks 1 and 2.

**PASS:** The client answers "creatively develop one." Buddy asks 4 short questions (mood = premium/warm; colors = their brand teal; imagery = real families; avoid = anything cheesy/clip-arty). Brand Steward scaffolds on the gold-standard reference deck premium-warm family, adapts the palette, renders a 3-slide probe. The client approves slide 2's treatment, asks for bolder headlines; probe iterated and approved. Offered "save as Signature Style 1?" - yes. Style Analyst writes the alias into NAMED-STYLES.md. Passes checks 1–6.

**PASS (saved style):** A returning client says "use Style 1." `STYLE_SOURCE = saved_style`, `STYLE_ID = Style 1`. Goes to SOP-IMG-04 recall. (No probe needed - the style is already approved.)

**FAIL:** The creative-develop flow, lacking real client wins, invented "[Client] helped 200 families" as on-slide proof. Fails check 6 (style flow must never fabricate client content).

---

*End of SOP-IMG-03. This SOP adds the conversation branch + the creative-develop flow + the NAMED-STYLES seed. It reuses the existing BB question stems; it does not duplicate the question bank.*
