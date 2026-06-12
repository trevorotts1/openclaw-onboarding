# Skill 45 CORE_UPDATES — AGENTS.md / TOOLS.md / MEMORY.md appends

Paste these blocks into the respective core files after installation.

---

## AGENTS.md append

### DIU Specialist Roles (activated at interview-complete / converge)

Add this section to your AGENTS.md under the "GRAPHICS DEPARTMENT" header:

```markdown
#### Design Intelligence Unit (DIU) roles

The DIU brings style-card-driven image generation, photo-shoot identity-lock, and fidelity-testing to your graphics workflow.

| Role | Persona | Function |
|---|---|---|
| **Style Analyst** | Visual-forensics, taxonomy-rigorous, detail-obsessive | Analyzes images/batches, writes reusable style cards in 3 tiers, registers in library |
| **Deck Systems Specialist** | Systems-thinker, rhythm-aware, manifest-disciplined | Analyzes deck style systems; runs Style Rotation Engine for multi-slide generation |
| **Generation Operator** | Prompt-engineer, routing-fluent, budget-precise | Executes style-card-driven generation; routes across 7 endpoints; manages negative-prompting |
| **Photo Shoot Director** | Identity-guardian, consent-first, retouch-restrained | Personal photo shoots with identity-lock guarantees; consent gates; surgical retouching (Seedream 4.5) |
| **Fidelity Tester** | Adversarial, evidence-driven, standards-immovable | Pre-production style-transfer tests; 12-dim fidelity scoring; patch loops; diagnosis mode |

All five roles report to **Chief Design Officer** (producer/gatekeeper). No DIU role delivers directly to owner; all outputs route through CDO Gate 4.

Request routing (via extended Brainstorming Buddy — Graphics):
- "Analyze this image / batch" → Style Analyst
- "Generate using style {ID}" → Generation Operator
- "Build slides using PPT style {ID}" → Deck Systems Specialist
- "Photo shoot of [client]" → Photo Shoot Director (consent gate first)
- "This generation came out wrong" → Fidelity Tester (Diagnosis Mode)
```

---

## TOOLS.md append

Add this section to TOOLS.md under the GRAPHICS DEPARTMENT / DESIGN TOOLS:

```markdown
### Design Intelligence Library (Skill 45)

**Runtime home:** `$OC_ROOT/master-files/design-library/`

**Key files (read in this order):**
1. `_system/MASTER-SOP.md` — 12-dimension style analysis protocol
2. `_system/MODEL-SPECS.md` — Kie.ai endpoint limits, character tiers, model routing
3. `INDEX.md` — master lookup table for all registered styles (populated by your team)
4. Category `_RULES.md` files — hard rules, safe zones, aspect ratios per design type

**Five system SOPs (repo-owned — never edit, sync on skill update):**
- `_system/MASTER-SOP.md` — single-image and batch analysis
- `_system/PPT-ANALYSIS-SOP.md` — deck analysis + Style Rotation Engine
- `_system/PHOTO-SHOOT-SOP.md` — consent, identity lock, retouching (Seedream 4.5)
- `_system/NEGATIVE-PROMPTING-SOP.md` — 3-layer avoid-list system
- `_system/TEST-PROTOCOL.md` — fidelity testing (12 dimensions, ≥4.0 avg, 3-strike escalation)

**Prerequisite:** Skill 07 (Kie.ai) must be installed; KIE_API_KEY must be configured.

**Two-zone contract:**
- **System files + _RULES.md** = repo-owned, updated on `update-skills.sh`
- **INDEX.md + style cards + identity profiles** = box-owned, persisted across updates

**Key vocabulary:**
- **Style Card**: reusable 3-tier prompt (SHORT ≤500 / MEDIUM ≤2,800 / LONG ≤18,000 chars) describing an image's transferable aesthetic
- **Style ID**: unique identifier (FB-001, SI-015, etc.) used to look up style cards in INDEX
- **Identity Lock Block**: mandatory prompt block for personal photo shoots; preserves skin tone, facial structure, age exactly
- **Style Rotation Engine**: deterministic multi-slide generation for decks; varies flex variables while maintaining family cohesion
- **Fidelity Test**: 12-dimensional scoring (render, composition, subject, color, grading, lighting, typography, layering, subject-bg, negative space, workflow, unity); ≥4.0 avg, no dim <3
```

---

## MEMORY.md append

Add this section to MEMORY.md under GRAPHICS DEPARTMENT MEMORY:

```markdown
### DIU Library & Style Card Registry

**Location:** `$OC_ROOT/master-files/design-library/INDEX.md`

**Current state:**
- Total registered styles: [count from INDEX.md]
- Categories active: single-image (SI), facebook-ad (FB), book-cover (BC), magazine-cover (MAG), social-media (SM), banner (BN), advertisement (AD), powerpoint (PPT), personal-photo-shoot (PS)
- Status breakdown: [# draft / # tested / # production / # retired]

**Recent activities:**
- Last style added: [ID, name, date]
- Last fidelity failure: [card ID, failure mode, patch result]
- Avoid-list recent additions: [1–3 phrases added by Fidelity Tester this quarter]

**Standing DIU operating rules:**
1. **Producer Gatekeeper**: all outputs → Chief Design Officer before owner approval
2. **Library Is Law**: no silent on-box edits to _system/ or _RULES; changes via repo
3. **Single Source of Truth**: role SOP Section 9 points to library file; style logic never duplicates into role files
4. **3-Strike Escalation**: Fidelity Tester third failure → CDO with evidence
5. **Intake Routing**: extended Brainstorming Buddy — Graphics captures DIU intent; CDO routes per the 5-way routing table

**Registrar-dormant duty (activates when INDEX >50 cards):**
- INDEX integrity audits (no duplicate IDs, all statuses match files)
- Quarterly avoid-list pruning (remove outdated phrases, union results across patch failures)
- MODEL-SPECS updates when Kie.ai endpoints change (test new endpoint on 3–5 cards, update limits/tiers/routing)
- Embedding index refresh (if semantic style search enabled) — keep card text and metadata current

**Optional semantic search index:**
- If enabled, `$OC_ROOT/master-files/design-library/.embedding-index.json` provides ranked matches for "find a style like this"
- Powered by `gemini-embedding-2` @3072 dims (multimodal)
- Refresh command: `bash $OC_ROOT/skills/45-design-intelligence-library/scripts/index-style-cards-embedding.sh`
```

---

## End of CORE_UPDATES.md
