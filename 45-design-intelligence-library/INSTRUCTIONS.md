# Skill 45 Runtime Instructions — Design Intelligence Library

## Agent quick-start

After installation, you (the AI agent) can access the DIU library via:

```
$OC_ROOT/master-files/design-library/   (on-box runtime home)
```

This folder holds:
- **_system/**: 7 protocol files (MASTER-SOP, MODEL-SPECS, etc.) — read these first
- **INDEX.md**: the master lookup table for every registered style (populated by the team)
- **9 category folders**: each with _RULES.md (hard rules for that design type)

---

## The five jobs (from library/README.md, expanded)

### 1. Analyze an image / batch / deck

**Trigger:** "Analyze this image" / "Cluster these designs" / "What style is this deck?"

**Steps:**
1. Open `$OC_ROOT/master-files/design-library/_system/MASTER-SOP.md` — the 12-dimension protocol.
2. If it's a PowerPoint/PDF or 4+ related images → open `_system/PPT-ANALYSIS-SOP.md` instead.
3. Apply the analysis protocol, extract the style (not content).
4. Write a style card per `_system/STYLE-CARD-TEMPLATE.md`.
5. **Register in INDEX.md** immediately — add a row with ID, name, summary, status (draft), version, date, file path.
6. **Test the card** per `_system/TEST-PROTOCOL.md` (→ Fidelity Tester).
7. Hand off to Style Analyst for INDEX governance and versioning.

**Output:** a style card file and an INDEX entry.

---

### 2. Generate an image using a registered style

**Trigger:** "Generate an ad using style FB-003, subject: [new subject], headline: [text]"

**Steps:**

0. **STYLE BRANCH (do this FIRST, before anything else): "do you have a style, or should I create one?"** Every generation needs a registered style card. Before resolving anything, establish which style to use:
   - **(a) Operator named an ID** ("use style FB-003") → resolve it in `INDEX.md` and continue at step 1.
   - **(b) Operator named a friendly alias** ("use signature style 1" / "use signature 2") → resolve it via INDEX.md "Resolving a friendly name" (Sig # column, category-scoped), get the ID, continue at step 1.
   - **(c) Operator has a reference image/deck to match** ("make it look like this") → this is an ANALYSIS job first. Route to the Style Analyst (job 1 / MASTER-SOP Workflow A; a deck or 4+ images → Deck Systems Specialist / PPT-ANALYSIS-SOP) to produce and register a style card, THEN return here and continue at step 1 with the new ID.
   - **(d) Operator has NO style and wants you to create one** ("I don't have a style, make me one" / "create a signature style") → route to the Style Analyst to DESIGN a new style card (analyze any refs if provided, else design fresh from brand defaults per MASTER-SOP §9), register it in INDEX.md with a Sig #, THEN continue at step 1.
   - If it is unclear which of (a) to (d) applies, ASK the operator: "Do you have a style ID to reuse, a reference to match, or should I create a signature style for you?" Never guess a style or improvise one inline; an unregistered, untested style is not a valid input to generation.

1. Resolve the style ID in `INDEX.md` — find the row, get the file path.
2. Open the style card file → extract the prompt templates (SHORT / MEDIUM / LONG tiers).
3. Consult the card's category `_RULES.md` for hard rules and model routing.
4. Open `_system/NEGATIVE-PROMPTING-SOP.md` → assemble the avoid-list (3 layers).
5. Open `_system/MODEL-SPECS.md` → resolve the model, API endpoint, character limits, JSON template.
6. Fill the card's variables (`{SUBJECT}`, `{HEADLINE_TEXT}`, etc.) with provided values.
7. Select the prompt tier (SHORT/MEDIUM/LONG) based on endpoint character limit.
8. Build negative-prompt set per the model's requirements.
9. **Execute via Kie.ai** using the JSON template from MODEL-SPECS (via Generation Operator).
10. Log the generation: model, seed, style_ref, prompt_tier, endpoint used.
11. Hand off to CDO for approval or to Fidelity Tester if off-style.

**Output:** generated image + generation log.

---

### 3. Build a PowerPoint deck using a style

**Trigger:** "Build a 12-slide deck in style PPT-002"

**Steps:**
1. Resolve PPT-002 in INDEX.md → open the style card.
2. Open `_system/PPT-ANALYSIS-SOP.md` § 3B → **Style Rotation Engine**.
3. **Build the Slide Manifest FIRST** — decide which slides use which families (A, B, C, …) and record rhythm rules.
4. Always 16:9. Resolution = client's choice (ask if unspecified; default 2K).
5. For each slide:
   - Pick the family (from the card's families list).
   - Extract the family-specific prompt tier + flex variables.
   - Combine with Foundation Block (deck cohesion).
   - Rotate flex variables across slides (same family should differ).
6. If the client appears in any slide → combine the family prompt with Identity Lock Block (PHOTO-SHOOT-SOP Mode E).
7. Execute all slides via Kie.ai / Generation Operator.
8. **Hand to CDO for Slide Manifest approval** (≥10-slide decks require producer gate).
9. Hand off for cohesion check and final delivery.

**Output:** 12 slide images + Slide Manifest + delivery notes.

---

### 4. Execute a personal photo shoot (real person, style-faithful)

**Trigger:** "Do a photo shoot of [Client Name] in style SI-001"

**Steps:**
1. **Consent gate (MANDATORY):** open `_system/PHOTO-SHOOT-SOP.md` § 1.
   - If the person is the client themself → documented permission confirmed.
   - If the person is someone else → requires client's documented permission + routed through producer (CDO).
   - **Minors:** HARD NO without explicit owner + legal sign-off.
2. Verify the client's identity profile → `personal-photo-shoot/{client-slug}/IDENTITY.md`.
3. Gather reference images (order: attached > identity profile > media library > workspace config; see § 2).
4. **Identity Lock Block (mandatory in every prompt)** — preserve skin tone, facial structure, age, features exactly (see § 4).
5. Pick the shoot mode (A: location, B: wardrobe, C: action, D: editorial, E: slide integration, F: stylized, G: retouch).
6. If style-driven (e.g., "in style SI-001") → combine Identity Lock Block + style card prompt + `{SUBJECT}` = "this exact person."
7. Execute via Seedream 4.5 (preferred for identity work) or Nano Banana 2.
8. **Retouch protocol (if needed):** use Seedream 4.5 Edit, one change per pass, preserve-first phrasing (§ 6).
9. Log the shoot, reference photos used, retouch history, consent date in the identity profile.
10. **Hand to CDO** for approval and likeness verification. Any concern → CDO + Director of Legal simultaneously.

**Output:** photo shoot images + identity profile update + consent log.

---

### 5. A new image-generation model is released

**Trigger:** "Kie.ai added endpoint XYZ with better people handling"

**Steps:**
1. **NEVER edit style cards.** Style cards describe HOW an image looks; model changes are tools, not style.
2. Open `_system/MODEL-SPECS.md` § 6 → the new-model protocol.
3. **Registrar duty** (activate when INDEX >50 cards):
   - Test the new endpoint on 3–5 representative style cards (short/long/people-intensive).
   - Record test results: fidelity score (≥4.0?), character limits (SHORT/MEDIUM/LONG tier compliance?), failure modes.
   - Update MODEL-SPECS with the new endpoint's limits, tiers, and routing rules.
   - Update category _RULES.md if needed.
   - Changelog entry describing the addition + which cards it affects most.
4. Test-drive the updated MODEL-SPECS with the Generation Operator before fleet rollout.

**Output:** updated MODEL-SPECS + CHANGELOG + test results.

---

## Semantic style search — NOT YET AVAILABLE

Embedding-indexed semantic search (*"find me a style like this"* without scanning INDEX.md) is a **planned future capability**. The `index-style-cards-embedding.sh` companion script **does not ship in this skill version** — there is no activation command, no `.embedding-index.json`, and no embedding-refresh duty. Do not attempt to run an embedding index; it is not present.

**What to use instead — INDEX.md lookup (always available):**
- **Exact ID** — resolve `FB-003` (or any `{CAT}-{NNN}`) directly in the INDEX.md master table.
- **Friendly alias** — resolve "signature style 1" via the INDEX.md "Resolving a friendly name" rule (Sig # column, category-scoped).
- **Category scan** — open the relevant category section of INDEX.md and read the summaries; retired cards are marked in the Status column and skipped.

When the embedding index ships, this section will be replaced with its setup and usage. Until then, INDEX.md is the single lookup surface.

---

## Handoff & escalation summary

**All DIU outputs go through Chief Design Officer (Gate 4).** No role delivers directly to owner/client.

| Source | Sends to | What |
|---|---|---|
| Style Analyst | Fidelity Tester | new/edited style card |
| Fidelity Tester | Style Analyst | card failed fidelity (patch loop); or CDO after 3 failures |
| Generation Operator | CDO | generated image + generation log |
| Deck Systems Specialist | CDO | Slide Manifest (≥10 slides) + slides + cohesion notes |
| Photo Shoot Director | CDO | photos + identity profile update + consent log; legal concerns → CDO + Director of Legal simultaneously |
| CDO | Owner | approved deliverables via Gate 4 |

---

## Troubleshooting at runtime

**"I can't find style SI-003 in INDEX.md"**
- It may not be registered yet. Check the empty-seed row. Ask Style Analyst or operator if analysis is in progress.

**"The generated image looks nothing like the style card"**
- Possible causes: (1) wrong prompt tier for the endpoint character limit, (2) negative-prompt collision, (3) model doesn't support the style well. Hand to Fidelity Tester (Diagnosis Mode § 5).

**"The client in the photo shoot looks like the wrong person"**
- HALT. This is an identity-drift failure. DO NOT deliver. Flag to Photo Shoot Director + CDO immediately. Likely causes: insufficient reference images, model identity-fusion error, or retouch side-effect. § 4 Identity Lock Block may need stronger language.

**"MODEL-SPECS says to use endpoint X but Kie.ai says it's deprecated"**
- Possible: Kie docs updated after this library version. Registrar duty: test the replacement endpoint, update MODEL-SPECS, communicate change to team. § 6 of MODEL-SPECS is the protocol for this.

---

## End of INSTRUCTIONS.md
