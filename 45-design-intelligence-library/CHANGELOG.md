# Skill 45 CHANGELOG — Design Intelligence Library

## [v1.3.4] - 2026-07-15 - GK-20: band<->routing contradiction reconciled in ONE place (`prompt-bands.json` v2), CI locks added

### Why
`prompt-bands.json` (P3-05, v1.3.3) listed `nano-banana-2` as a `text_bearing_long` endpoint and
named NO Ideogram endpoint in any text-bearing band, while the fleet's mandatory routing rule
(`social-media-designs/_RULES.md`) and Skill 35's `pregen_prompt_gate.py` both REFUSE Nano Banana
for any text-overlay deliverable and REQUIRE Ideogram V3 DESIGN for every quote-card/text-led
post. A Graphics-authored text-bearing social asset written to its own band's guidance (>=5,000
chars, nano-banana-listed) was refused by Skill 35's routing gate; re-routing it to the mandated
Ideogram endpoint put it in the `medium` band whose cap (2,800) plus MODEL-SPECS.md's own verified
Ideogram V3 API cap (5,000 chars, LONG tier NOT SUPPORTED on this endpoint) meant the floors and
the routing rule could never both be satisfied as written.

### Changed
- **`library/_system/prompt-bands.json` (v1 -> v2):** `nano-banana-2` REMOVED from
  `text_bearing_long.endpoints` (it is refused for text everywhere else in the fleet — the JSON
  was the outlier). Added a NEW `text_bearing_medium` band (MIN 1,600 / MAX 4,500 /
  min_distinct_words 90 / `text_bearing: true` / `endpoints: ["ideogram/v3-text-to-image"]`) — the
  ONLY text-bearing band naming an Ideogram endpoint, sized to Ideogram V3's own verified
  5,000-char API cap (MODEL-SPECS.md) minus the same ~10% safety margin every other band keeps
  under its endpoint's real cap; MIN=1,600 is measured as 2x the non-text-bearing `medium` band's
  own floor (800), mirroring the established text-bearing/non-text-bearing 2x ratio between
  `text_bearing_long` (5,000) and `visual_long` (2,500). `social post graphic with baked text`
  moved from `text_bearing_long.applies_to` to `text_bearing_medium.applies_to`.
- **`library/social-media-designs/_RULES.md`:** the model-routing section now names
  `text_bearing_medium` explicitly as the band the mandated Ideogram route resolves to, closing
  the loop between the routing rule and the band file (single authoritative reconciliation point).
- **`scripts/diu_validator.py`:** docstring + `--band` help text updated to list
  `text_bearing_medium` alongside the existing three bands (band resolution itself is already
  fully data-driven from `prompt-bands.json` — no gate-logic change was needed).
- **`scripts/prove_gip_prompt_floor.py`:** added `rich_text_bearing_medium()` fixture builder + 4
  new `--self-test` fixtures (rich pass, under-floor, over-cap, no-spelling-lock quality fail) plus
  a dedicated exit-code-contract assertion for the new band. Added a machine-checked regression
  assertion, read from the SAME `prompt-bands.json` the validator loads at runtime, that (a) no
  `text_bearing: true` band ever lists a `nano-banana` endpoint and (b) the Ideogram-routed
  text-bearing band's MAX never exceeds Ideogram V3's verified 5,000-char cap — so this exact
  contradiction can never silently regress.
- **`scripts/test_prompt_band_cli.py`:** added two new real-CLI (subprocess) cases proving a
  genuinely compliant `text_bearing_medium` prompt clears the gate (exit 0) and an under-floor one
  is refused (exit 3, `AF-GIP-PROMPT-FLOOR`) — the same fail-first discipline as the existing
  `text_bearing_long` cases.
- **15 graphics role docs + 2 dept-level SOPs** (`ad-creative-specialist`,
  `ai-image-generator-specialist`, `book-cover-designer`, `brand-identity-specialist-logo-color-type`,
  `course-slide-designer`, `deck-systems-specialist`, `email-designer`, `generation-operator`,
  `infographic-specialist`, `motion-systems-specialist`, `photo-shoot-director`,
  `presentation-designer-slides-decks`, `print--asset-design-specialist`,
  `social-media-graphics-specialist`, `style-analyst`, `thumbnail--cover-designer`,
  `sops/SOP-DIU-601.md`, `sops/SOP-GIP-01-PROMPT-ANATOMY.md`): the "GIP Prompt-Band Compliance"
  band-selection guidance is corrected fleet-wide — `text_bearing_long` is now scoped to GPT-Image 2
  T2I/I2I copy-bearing deliverables, `text_bearing_medium` is named as the band for the mandatory
  Ideogram V3 DESIGN quote-card/text-led route, and `medium` is now explicitly scoped
  non-text-bearing (Seedream only). `SOP-GIP-01-PROMPT-ANATOMY.md`'s band table gained the new row
  and its library-version pin bumped to `prompt-bands.json v2`. Role-library `_index.json`
  content_sha/content_version restamped via `hash-content-manifest.py` for all 18 touched
  artifacts; `--check` passes clean.

### Version
- **Skill 45 independent line:** skill-version.txt 1.3.3 → 1.3.4; SKILL.md frontmatter version
  1.3.3 → 1.3.4 (must match the frontmatter-version-guard).

## [v1.3.3] - 2026-07-12 - P3-05: GIP prompt-band floor wired into 15 graphics role docs, CLI-level fail-first prover, social-media-designs _RULES.md enriched

### Added
- **`scripts/test_prompt_band_cli.py`** — real CLI-level (subprocess) fail-first tests for `diu_validator.py prompt-band`, exercising the exact P3-05 QC break-it probes: a 300-char "logo pls" prompt refused (exit 3, `AF-GIP-PROMPT-FLOOR`); a ~6,000-char, <150-distinct-word prompt refused (exit 6, `AF-GIP-PROMPT-QUALITY`, density-specific message quoted); a genuinely compliant `text_bearing_long` prompt passes (exit 0); and a fail-first cross-check that both refusals disappear against a permissive fixture bands file (proving the refusals are caused by the shipped floor numbers, not a coincidental unrelated failure).
- **`library/social-media-designs/_RULES.md`** enriched from a 26-line stub: added Skill 35's pixel-exact spec table (previously only in `35-social-media-planner/references/playbook.md`), the mandatory brand-safety clause (verbatim from playbook.md Section 18 rule 5), and the Ideogram-for-text routing rationale tied explicitly to Skill 35's every-image-carries-text-overlay design (closes the "one shared category file is a 26-line stub" finding — Skill 35 and Skill 45 previously described the same deliverable with no single source of truth).

### Changed
- **Wired the GIP prompt-band gate into the WORKFLOW, not just the tool** (P3-05 step 3): `generation-operator.md` SOP 9.4 preflight checklist item 1 now runs the `diu_validator.py prompt-band` MIN-floor + quality gate BEFORE the endpoint's own MAX-cap check (previously MAX-cap-only, per the P3-05 root-cause finding G1 — the floor existed as config but nothing in the role docs told an agent to run it). 14 additional prompt-authoring roles (`ad-creative-specialist`, `ai-image-generator-specialist`, `book-cover-designer`, `deck-systems-specialist`, `email-designer`, `infographic-specialist`, `photo-shoot-director`, `presentation-designer-slides-decks`, `print--asset-design-specialist`, `style-analyst`, `thumbnail--cover-designer`, `course-slide-designer`, `brand-identity-specialist-logo-color-type`, `motion-systems-specialist`) gained a "GIP Prompt-Band Compliance" section requiring the gate before generation and SOP-GIP-02 vision QC after, mirroring the presentation department's `build_deck.py` floor exactly. `social-media-graphics-specialist.md` gained an explicit pre-generation Gate 0 (it already had the post-generation SOP-GIP-02 gate). `qc-specialist--graphics.md` and `asset-provenance-librarian.md` already carried this wiring pre-fix.
- Role-library `_index.json` content_sha/content_version restamped via `hash-content-manifest.py` for all 16 touched role docs; `--check` passes clean.

## [v1.3.1] - 2026-07-08 - fix: fail-closed consent/minor/PII gate, sales interlock, funnel-category install, gate self-tests (OPENCLAW-FIX-SPEC L18)

### Added
- **Coded fail-closed consent gate** — `diu_validator.py consent-check --identity-file IDENTITY.md` (SK1-55). Real-person likeness generation was gated only by prose in PHOTO-SHOOT-SOP §1; an agent could proceed past it. The new subcommand reads the client's IDENTITY.md and HARD-FAILS (exit 4, `AF-DIU-CONSENT`) on unconfirmed/undated consent, a subject not attested an adult (Minors = HARD NO), an unprotected biometric store, or an absent IDENTITY file. PHOTO-SHOOT-SOP §1/§3 and INSTRUCTIONS job 4 now require it first; the IDENTITY schema declares machine-readable `Consent:`/`Consent date:`/`Minor:`/`Storage protection:` fields and mandates encrypted-at-rest biometric storage.
- **QC gate self-tests** — `qc-design-intelligence-library.sh` now exercises `diu_validator.py` on fixtures (route-check webinar/sales/funnel→2, brand→0; prompt-caps over→3; consent-check adult→0, minor/no-consent/no-protection/missing→4), so a regression in any gate fails QC (SK1-56). Previously no test exercised any gate.

### Changed
- **Routing interlock now catches bare "sales" decks** (SK1-54): `_INTERLOCK_TERMS` gained `sales` — SKILL.md names sales decks as NOT owned by Skill 45, but `route-check --deck-kind "sales deck"` previously returned 0 (routable). Now exit 2.
- **funnel-page-designs category install + doc drift fixed** (SK1-57): the 10th category (`funnel-page-designs`, present on disk + in INDEX.md and the QC) was omitted from INSTALL.md's rsync block, Step-4 dir loop, and Step-6 verify loop — so the installer never seeded it on-box. Added it to all three, to the SKILL.md ships-tree, and corrected the "19 library files" citations to **20**; bumped MODEL-SPECS.md header 1.3→1.4 to match its own changelog.

## [v1.3.0] - 2026-07-05 - fix: coded enforcement gates, QC clobber test, embedding honesty, twin dedup (T-45-design-intelligence)

### Added
- **`scripts/diu_validator.py`** (Python stdlib, zero third-party deps) — the binding gates were prose-only; this makes three MECHANICAL (mirrors Skill 47's deterministic-gate pattern): [FIX-XC-03h]
  - `prompt-caps` — enforces SHORT ≤500 / MEDIUM ≤2,800 / LONG ≤19,000 char caps (MODEL-SPECS tier table); over-cap = hard exit 3 (`AF-DIU-PROMPT-CAP`).
  - `route-check` — the SOP-DIU-611 §D.1 routing interlock as code: audience/webinar/funnel/virtual-event decks cannot run on the Rotation Engine (exit 2, `AF-DIU-ROUTING-INTERLOCK`).
  - `fidelity` — TEST-PROTOCOL §5 receipt (avg ≥4.0, no dim <3, zero hard-rule violations) appended to `working/checkpoints/diu_fidelity_receipts.json`, plus a per-(card,dimension) 3-strike counter → CDO escalation (exit 5, `AF-DIU-3-STRIKE`).
  - SKILL.md gains a "Binding enforcement — coded gates" section + a `scripts/` inventory entry.

### Changed
- **QC (`qc-design-intelligence-library.sh`):** added an INDEX clobber-safety test — seeds a sentinel INDEX.md in a temp home, re-runs the documented `cp -n` seed (INSTALL.md Step 4), and asserts the populated copy survives byte-for-byte; corrected the `_system` protocol-file count to `-maxdepth 1` (the nested `_system/templates/NAMED-STYLES.md` seed template is not a protocol file) so the total resolves to the documented **19**; version banner now reads `skill-version.txt`. SKILL.md/CHANGELOG "16 library files" corrected to 19. [FIX-S36-29]
- **Semantic embedding search marked NOT YET AVAILABLE** (INSTRUCTIONS.md, CORE_UPDATES.md, SKILL.md read-order): the `index-style-cards-embedding.sh` script ships nowhere, so the activation command, `.embedding-index.json` references, and the Registrar embedding-refresh duty are removed; INDEX.md lookup is documented as the available surface until the index ships. [FIX-XC-11c]

### Removed / de-duplicated (in `23-ai-workforce-blueprint/`)
- **Deleted 7 byte-identical non-`SOP--` role-SOP twins** under `templates/role-library/graphics/sops/` (chief-design-officer, deck-systems-specialist, fidelity-tester, generation-operator, healer-graphics, photo-shoot-director, style-analyst) — the `SOP--` variant is canonical. Re-pointed references in `deck-systems-specialist.md`, `SOP-DIU-502.md`, and this CHANGELOG; surgically re-stamped `_index.json` (dropped the 7 duplicate `sops[]` entries + re-hashed the 3 edited artifacts) and verified with `hash-content-manifest.py --check`. [FIX-S36-30 ii]
- **Wired the DIU production lifecycle onto the Command Center board** (CDO SOP 9.12, reusing Skill 48's fail-soft `cc_board.py`): Gate 4 lives in the **review** column, and the `review → done` transition is the auditable evidence Gate 4 occurred — closing the "Gate 4 skippable with no evidence" gap. [FIX-S36-30 i]

### Version
- **Skill 45 independent line:** skill-version.txt 1.2.3 → 1.3.0; SKILL.md frontmatter version 1.2.3 → 1.3.0 (must match the frontmatter-version-guard).

---

## [v1.2.1] - 2026-06-14 - fix: negative-prompting long-budget cap-lift note

### Changed
- **`library/_system/NEGATIVE-PROMPTING-SOP.md` (v1.0 to v1.1):** documented the long-budget exception to the "10 strongest" inline-negative cap. On a LONG-tier GPT-Image 2 prompt (the up-to-19,000-character budget, for example the Presentations slide-image-creator path, slide-image-creator SOP 9.8), the 10-strongest cap is LIFTED: with that much room the full defect-mapped negative block fits and prompt pollution is not a concern at this length, so every required negative class is stated rather than a top-ten selection. The cap still applies on SHORT and MEDIUM prompts and the small-budget endpoints (Seedream). The positive-twin pairing rule and the no-contradiction audit still apply with full force when the cap is lifted. This is the design-library half of the v12.7.1 image-prompt hardening that wires this negative system into the Presentations prompt-writer.

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
  - SOP--style-analyst-sops.md, SOP--deck-systems-specialist-sops.md, SOP--generation-operator-sops.md, SOP--photo-shoot-director-sops.md, SOP--fidelity-tester-sops.md (the byte-identical non-prefixed twins were removed; the `SOP--` variant is canonical)
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
