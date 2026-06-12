# Skill 45 CHANGELOG — Design Intelligence Library

## [v1.1.0] - 2026-06-12 - feat: full DIU role set — 8 remaining specialists + ROLE-- files

### Added
- **Eight remaining DIU specialist roles** (ROLE-- files in `23-ai-workforce-blueprint/templates/role-library/graphics/`):
  - `ROLE--design-producer.md`: producer gatekeeper, client-facing delivery loop, intake briefs, revision rounds, per-client taste profile
  - `ROLE--style-librarian.md`: style-card catalog management, INDEX.md maintenance, dormancy/archival workflows, cross-unit catalog surface
  - `ROLE--likeness-rights-officer.md`: identity-lock enforcement, consent gate, likeness rights clearance, legal escalation protocol
  - `ROLE--render-dispatcher.md`: render job routing, endpoint selection, retry/fallback logic, throughput monitoring
  - `ROLE--asset-provenance-librarian.md`: asset chain-of-custody, provenance records, source attribution, audit trail
  - `ROLE--style-steward.md`: cross-department style request contract, catalog digest publication, version-pin notifications, brand-fit tagging
  - `ROLE--brand-systems-specialist.md`: brand token enforcement, brand-fit tag assignment, brand-change propagation, generation preflight brand-check
  - `ROLE--motion-systems-specialist.md`: motion/animation generation, video-frame style consistency, motion SOP execution
- **`ROLE--brand-systems-specialist.md`** created (was the sole missing ROLE-- file from the 13-role DIU set; source: `brand-systems-specialist.md`)

### Updated
- **`23-ai-workforce-blueprint/templates/role-library/_index.json`:**
  - `departments.graphics.roles` += 8 slugs (sorted): design-producer, style-librarian, likeness-rights-officer, render-dispatcher, asset-provenance-librarian, style-steward, brand-systems-specialist, motion-systems-specialist
  - `departments.graphics.count`: 23 → 31
  - `total_roles`: 323 → 331
  - +8 flat `roles[]` entries
  - Invariant verified: count == len(roles) == 31; total_roles == sum(dept counts) == 331
- **`README.md`:** skill-45 row added to skill inventory table; folder count 44 → 45; v12.2.0 DIU NOTE line added
- **`CHANGELOG.md`:** v12.2.0 entry added

### Version & markers
- **Skill 45 independent line:** skill-version.txt: 1.0.0 → 1.1.0
- **Repo version:** v12.1.1 → v12.2.0 (markers already at v12.2.0 from prior bump; `--check` confirms all 9 agree)

### QC
- All 13 ROLE-- files present and verified
- All 26 SOP-DIU files (SOP-DIU-101 through SOP-DIU-615) present
- SOP-DIU ids unique across sops/ directory
- `_index.json` invariant: PASS

---

## [v1.0.0] - 2026-06-12 - feat: Design Intelligence Unit launch

**Initial release:** Ship the DIU library system files, five specialist roles (style-analyst, deck-systems-specialist, generation-operator, photo-shoot-director, fidelity-tester), extended Brainstorming Buddy — Graphics, producer gatekeeper (Chief Design Officer) integration, and five operating rules.

### Added
- **Library system (16 files):**
  - 7 protocol files under `library/_system/`: MASTER-SOP.md, MODEL-SPECS.md, PHOTO-SHOOT-SOP.md, PPT-ANALYSIS-SOP.md, NEGATIVE-PROMPTING-SOP.md, STYLE-CARD-TEMPLATE.md, TEST-PROTOCOL.md
  - 9 category _RULES.md files (advertisement-designs, banner-designs, book-cover-designs, facebook-ad-designs, magazine-cover-designs, personal-photo-shoot, powerpoint-designs, single-image-designs, social-media-designs)
  - README.md and empty-seed INDEX.md
- **Five specialist roles** (in 23-ai-workforce-blueprint/templates/role-library/graphics/):
  - style-analyst.md: MASTER-SOP analysis, style-card creation, batch clustering, Registrar dormant duty (activates >50 cards)
  - deck-systems-specialist.md: PPT-ANALYSIS-SOP, Style Rotation Engine, Slide Manifest, multi-slide cohesion
  - generation-operator.md: MASTER-SOP Workflow B, negative prompting, API routing, model selection
  - photo-shoot-director.md: PHOTO-SHOOT-SOP, consent gates, identity lock, surgical retouching, legal escalation
  - fidelity-tester.md: TEST-PROTOCOL, 12-dim scoring, patch loops, diagnosis mode, avoid-list growth, status lifecycle
- **Chief Design Officer edits:**
  - New Section 9 SOP: DIU Intake Routing & Producer Gate (manifest approval, consent verification, 3-strike escalation)
  - §11 Handoffs updated for DIU inputs/outputs
  - §17 Edge case: likeness without consent → halt + legal
- **Extended Brainstorming Buddy — Graphics:**
  - 4 new questions in the `_brainstorming-buddy-question-banks.json` extensive question bank (reference images, style ID reuse, likeness/identity, deck slides + resolution)
  - Routed brief answers capture DIU intent and route to appropriate specialist
- **Boundary patch to ai-image-generator-specialist.md:**
  - §1 "What This Role Is NOT": clarified that DIU owns style-card-driven generation; AI Image Generator owns general generative briefs
  - §11 Handoffs: added cross-reference row for style-card requests → Generation Operator
- **Skill scaffold files:**
  - SKILL.md, INSTALL.md, INSTRUCTIONS.md, CORE_UPDATES.md, CHANGELOG.md, PREREQS.json
  - skill-version.txt: 1.0.0
  - QC script: qc-design-intelligence-library.sh
  - docs/VENDOR-BUILD-BRIEF.md: provenance document (vendor original + superseded header)
- **Five role-library mirrors** (templates/role-library/graphics/sops/):
  - style-analyst-sops.md, deck-systems-specialist-sops.md, generation-operator-sops.md, photo-shoot-director-sops.md, fidelity-tester-sops.md
  - Verbatim Section 9 copies; regenerated on role file update per the "mirror rule"
- **Graphics department 00-START-HERE.md:**
  - All 23 graphics roles listed with slug/role_type
  - DIU unit grouping (5 roles under subheading "Design Intelligence Unit (DIU)")
  - DIU pipeline + intake routing table (5-way routing to specialists)
  - Unit operating rules (5 restated against our names)
  - Vendor §6 onboarding sequence
  - SOP mirror index
  - Master SOP authority pointer
  - Bug-filing + Healer-Graphics block
- **23-ai-workforce-blueprint/_index.json updates:**
  - departments.graphics.roles += 5 slugs (deck-systems-specialist, fidelity-tester, generation-operator, photo-shoot-director, style-analyst) — sorted
  - departments.graphics.count: 18 → 23
  - total_roles: 318 → 323
  - +5 flat `roles[]` entries for forward hygiene
  - generated_at: refreshed to v12.2.0 release date
- **suggested-roles/graphics-suggested-roles.md:**
  - +5 role entries (Core SOPs + Persona Traits per role)
  - Header counts and version line bumped
- **Skill 45 wiring:**
  - install.sh: skill-45 install block + explicit listing (pattern mirror 43/44)
  - ONBOARDING-TRIGGERS.md: updated skill count + Skill 45 bullet
  - README.md: skill-45 row in table + v12.2.0 NOTE line
  - cc-compat.json: onboardingVersion bumped to v12.2.0

### Port-time patches applied (vendor → repo)
- Kebab-case directory names (vendor spaces → repo hyphens): `advertisement-designs`, `banner-designs`, etc.
- Path references: `design library/` → `design-library/`, `openclaw master files/` → `$OC_ROOT/master-files/`
- Brand genericization:
  - MASTER-SOP §9: "Brand Default (BlackCEO)" → "Brand Default ({{COMPANY_NAME}})"
  - facebook-ad-designs/_RULES.md: "(BlackCEO standard)" → "(client brand standard — see workspace brand config)"
  - social-media-designs/_RULES.md: same brand-standard update
  - powerpoint-designs/_RULES.md: "Dr. Brown program clients" → "client-specific document standards recorded in the workspace's brand notes apply"
- Core-file casing: `agents.md` → `AGENTS.md`, `tools.md` → `TOOLS.md`, etc. (our canonical casing)
- MODEL-SPECS: vendor-asserted (no-guessing policy; first on-box generation is verification gate)

### Not included (deferred per risk/decision J.7–J.9)
- Pre-existing `_index.json` flat-list backfill (275 vs 318 entries; separate hygiene PR)
- Graphics SOP mirrors for 13 legacy roles (v12.2.0 mirrors only the 6 new files)
- `_qc-summary.md` full regeneration (stale counts; Stage-2 QC re-run needed)

### Dependencies & prerequisites
- **Skill 07 (Kie.ai):** required; KIE_API_KEY must be configured for image generation via Kie.ai endpoints
- **Skill 23 (AI Workforce Blueprint):** roles materialize via its ROLE LIBRARY gate; no new blueprint machinery
- **Command Center (v4.39.0+):** new roles wire via existing `sync-extensions.sh --converge`; no new CC API calls

### Version & markers
- **Skill 45 independent line:** skill-version.txt = 1.0.0
- **Repo version:** v12.1.1 → v12.2.0
- **All 9 version markers + cc-compat updated** (bump-version.sh + manual cc-compat onboardingVersion)

### Testing & QC
- `qc-design-intelligence-library.sh` verifies 16 library files present, INDEX.md parses, no client data committed
- `verify-role-library.sh` (Skill 23 gate): ≥19 sections per role file, ≥7KB substantive per role
- `qc-completeness.sh`: verifies FILE-SIZE threshold on role files
- `qc-prereqs-json.sh`: validates PREREQS.json Skill 07 dependency declaration
- Pre-commit: Step-2c `_index.json` invariant (total_roles == sum(dept counts)) runs to green
- Post-merge: tag v12.2.0 annotated + push

### Known limitations
- Flat `roles[]` list in `_index.json` not back-filled (275 vs 328 entries if untouched); future hygiene PR
- em-dash legacy slugs in existing roles left untouched (not a v12.2.0 change)
- Gemini embedding index (`index-style-cards-embedding.sh`) is optional; v1.0 ships as documented future step, not active by default

---

## End of Skill 45 CHANGELOG
