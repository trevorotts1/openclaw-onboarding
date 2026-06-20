# DEPARTMENT CLASS-KIT TEMPLATE — Build Manifest (v1.0)

> **What this is.** A literal, copy-ready manifest a build agent follows to produce ONE department's complete class kit and its Notion sub-page, to gold-standard equivalence. It is derived from the verified Presentations Department gold kit + gold Notion page (page id `3846798f-3b7c-8014-a00c-ddc7c57decdd`). Every count, filename, and structure rule below mirrors that exemplar. Substitute the target department name and content; **keep the structure, file set, counts, and embedding rules identical.**
>
> **Naming convention.** Throughout, replace `<DEPT>` with the human department name (e.g. "Marketing"), `<Dept-Slug>` with the hyphenated slug used in filenames (e.g. `Marketing-Dept`), and `<N>` with the actual role count for THIS department. The gold kit had 24 roles; your department may differ — every "24 roles" reference scales to `<N>`, and you produce **one micro-infographic per role** plus the fixed concept infographics.
>
> **READ-ONLY discipline.** The gold kit and gold Notion page are reference only — never edit them.

---

## 0. THE NON-NEGOTIABLE ACCEPTANCE GATE (read first)

A kit is **NOT done** until ALL of these are true. This is the literal enforcement gate — the same checks that caught the 33 failures (text-only Notion pages with zero embedded artifacts). Mirror it exactly.

- [ ] **Every file in the manifest below physically exists on disk** at the kit root (file exists check, non-zero bytes).
- [ ] **The primary deck PPTX contains ≥ 20 slides** (gold = 60). Verify literally:
  `unzip -l <Dept-Slug>-LIGHT-<N>.pptx | grep -cE 'ppt/slides/slide[0-9]+\.xml'` must print a number ≥ 20.
- [ ] **Slide PNG count == deck slide count** and **prompt-file count == slide count** (each slide has a render + a verbatim prompt).
- [ ] **The Notion sub-page has the embedded artifacts — NOT text-only.** It must contain, as real Notion `image`/`file` blocks with live `src`/`url`: the full deck slide images, the editable `.pptx` file block, all micro-infographic images, all 4 cheatsheet images, and all reference PDF `file` blocks. **Artifact-block count (image+file) on the page must be > 0** — a page with `image+file+pdf+embed = 0` is an automatic FAIL (this is exactly what the 33 failed pages looked like: 7 H1 sections of text + placeholder callouts saying "embedded here in Phase 1", with zero real artifacts).
- [ ] **No placeholder/deferral language** in any artifact section. Callouts must not say "go here", "Add the PowerPoint file", "will be added", "queued for Phase 1b", "embedded here as public-URL". If a section promises an artifact, the artifact block is present.
- [ ] **Notion page is the gold 4-H1 structure** (NOT the failed 7-section skeleton). See §B. The failed pages used `Overview → Roles → SOP Library → Workflow → Visuals → Signature Presentation → Outputs` (7 H1). The gold/required structure is exactly 4 numbered H1 sections.
- [ ] **Brand/light styling enforced** on every rendered asset (light background mandatory; see §C). No dark-background renders.
- [ ] **Deluxe reference exists** as both PDF and HTML source; 8 numbered module PDFs exist.

> **Independent-verify rule:** the build agent runs these checks AND a separate verifier re-runs the literal `unzip … | grep -c` and the Notion artifact-block count, quoting the raw numbers. Never report "done" without the raw counts.

---

## A. THE FILE MANIFEST — exact files to produce

Kit root: `/Users/blackceomacmini/Downloads/<Dept-Slug>-Class-Kit/`

Folders to create: kit root, `renders-light/`, `micro-infographics/` (with `micro-infographics/working/`).

### A.0 — Master index (1 file)
- [ ] `00-DELIVERY-PACKAGE-INDEX.md` — the manifest/README for the kit. Tabulates every artifact with "what it is / when to use", and states the recommended teaching/sharing order: **deck → speech → teleprompter → deluxe reference → 8 topic PDFs → 4 cheatsheets → brand spec → render prompts.** Include the self-stated package summary line (1 primary deck, 1 speech + 1 teleprompter, N PNGs + N prompts, 10 PDFs, 4 cheatsheets, `<N>`+fixed micro-infographics, brand + prompt files).

### A.1 — Class docs: 8 topic modules, each `.html` source AND `.pdf` deliverable (16 files)
Each `.html` is the source that generates the matching `.pdf`. Both ship. Filenames are exact:

| # | Stem (produce `.html` + `.pdf`) | Title | Content |
|---|---|---|---|
| 01 | `01-Getting-Started` | Getting Started | How to trigger the department, intake gathered, run up to the approval gate. First read. (~3pp) |
| 02 | `02-The-<N>-Roles` | The `<N>` Roles | All `<N>` specialist roles across the department's clusters. |
| 03 | `03-The-SOP-Rulebook` | The SOP Rulebook | The doctrine SOPs in their families — each rule + why it exists. |
| 04 | `04-The-4-Presentation-Types` | The 4 Output/Presentation Types | The department's 4 deliverable types, compared side-by-side, with a choose-the-type guide. |
| 05 | `05-The-Build-Pipeline` | The Build Pipeline (Order of Events) | Ordered end-to-end flow, each artifact built by a named specialist and graded at a gate. |
| 06 | `06-The-Quality-Gates` | The Quality Gates | The 5 independent QC functions + the 8.5 scoring threshold deciding whether work ships. |
| 07 | `07-The-Final-Package` | The Final Package | The complete bundle handed to the client + completeness/cleanliness gates. |
| 08 | `08-Intelligence-Engines` | The Intelligence Engines & Craft Doctrine | The 9 intelligence engines, each wired to its gate, plus the craft doctrine. (~5pp) |

> Naming note: keep `04-The-4-Presentation-Types` verbatim if the department ships presentation-style outputs (gold used it); otherwise the title may read "The 4 Output Types" but the FILENAME stays `04-The-4-Presentation-Types.pdf/.html` so the Notion section-3 list matches the gold artifact bar.

### A.2 — Master reference: all-in-one class guide (3 files)
- [ ] `<Dept>-Department-Class-Reference.pdf` — **compact ~12-page** all-in-one reference (short-class handout).
- [ ] `<Dept>-Department-Class-Reference-DELUXE.pdf` — **full ~44-page** "The Complete Class Guide" (primary leave-behind / digital study guide). All modules in one document.
- [ ] `<Dept>-Department-Class-Reference-DELUXE.html` — HTML source for the deluxe PDF (table of contents + 10 sections). (No standalone HTML for the compact version.)

### A.3 — Deck: training slides (PPTX)
- [ ] `<Dept-Slug>-LIGHT-<N>.pptx` — **PRIMARY deck, ≥ 20 slides (target 60).** Light-background, presentation-ready, 2K rendered images baked in. This is the gate-checked deck. Filename pattern mirrors gold `HOWTO-Presentation-Dept-LIGHT-60.pptx`.
- [ ] *(optional)* `How-To-Use-The-<Dept>-Department.pptx` — earlier short draft (archive reference only; gold had a 15-slide draft).

### A.4 — Renders: one PNG + one PROMPT per slide (`renders-light/`)
For a deck of `S` slides (S ≥ 20):
- [ ] `slide-01.png … slide-<S>.png` — 2K light-background slide renders. **Count == S.** Pull any single slide for email/Telegram/GHL/social.
- [ ] `slide-01-PROMPT.txt … slide-<S>-PROMPT.txt` — verbatim Kie.ai prompt per slide for re-render/variants. **Count == S.**
- [ ] render/build scripts (`.py`/`.sh`) used to generate the renders.
- [ ] `kie_task_ids.json` — Kie.ai task-ID audit log.

### A.5 — Speech / teleprompter (2 files)
- [ ] `<Dept-Slug>-<N>-SPEECH.md` — full **word-for-word speaker script for all slides**, with per-slide word/time markers (gold ≈ 3,083 words ≈ 25:42 at 120 wpm).
- [ ] `<Dept-Slug>-<N>-teleprompter.html` — browser-based **auto-scrolling teleprompter app** for hands-free live/recording delivery.

### A.6 — Cheatsheets: 4 portrait posters (4 PNG + 4 PROMPT = 8 files)
Portrait 2K, print/share, daily reference. Exact set:
- [ ] `cheatsheet-1-roles.png` (+ `cheatsheet-1-roles-PROMPT.txt`) — all `<N>` roles / clusters.
- [ ] `cheatsheet-2-sops.png` (+ `-PROMPT.txt`) — SOP rulebook families.
- [ ] `cheatsheet-3-types.png` (+ `-PROMPT.txt`) — the 4 output/presentation types + decision guide.
- [ ] `cheatsheet-4-pipeline.png` (+ `-PROMPT.txt`) — build phases + 5 QC gates vertical flowchart.

### A.7 — Micro-infographics: one per role + fixed concept set (`micro-infographics/`)
16:9 2K. Each PNG has a 1:1 paired `-PROMPT.txt`. Produce **one micro-infographic per role** PLUS the fixed concept infographics below. Gold had 24 total (the fixed set + per-role/cluster). Use this canonical ordered set, scaled to `<N>` roles:
- [ ] `01-what-it-is.png` / `-PROMPT.txt`
- [ ] `02-getting-started.png`
- [ ] `03-approval-gate.png`
- [ ] `04-pipeline-glance.png`
- [ ] `05-phase-research.png`, `06-phase-copy.png`, `07-phase-design.png`, `08-phase-prompts.png`, `09-phase-render.png`, `10-phase-finish.png` (the 6 phases)
- [ ] one per **role** (gold grouped these as 8 clusters: direction, strategy, copy, image, qc, assembly, speech, coaching — produce one micro per role of THIS department)
- [ ] `19-sop-slidecraft.png`, `20-sop-design.png`, `21-sop-pitch.png`, `22-sop-image.png` (4 SOP families)
- [ ] `23-types.png` (the 4 output types)
- [ ] `24-final-package.png`
- [ ] `working/kie_task_ids.json` — task-id log.

> Every micro PNG must have its `-PROMPT.txt` (1:1). Count check: `ls micro-infographics/*.png | wc -l` == `ls micro-infographics/*-PROMPT.txt | wc -l`.

### A.8 — Brand + render-prompt source (2 files)
- [ ] `BRAND-COLOR-SPEC.md` — canonical brand spec (palette, rules, full reusable Kie.ai style directive, aspect/resolution quick-reference). See §C for the literal content.
- [ ] `<N>-SLIDE-RENDER-PROMPTS.md` — all verbatim slide prompts (the recovered originals) for re-rendering/variants/new decks.

### A — Totals the kit must hit (gold parity)
- 10 PDFs (8 modules + compact + DELUXE)
- 9 HTML sources (8 module `.html` + DELUXE `.html`)
- 1 primary PPTX (deck slide count ≥ 20, target 60) [+ optional archived draft]
- 1 speech `.md` + 1 teleprompter `.html`
- `S` slide PNGs + `S` slide prompts (S == deck slide count)
- 4 cheatsheet PNGs + 4 cheatsheet prompts
- (`<N>` per-role + fixed concept) micro PNGs + matching prompts (1:1)
- 1 `BRAND-COLOR-SPEC.md` + 1 `<N>-SLIDE-RENDER-PROMPTS.md`
- **Every rendered asset has a matching verbatim prompt file** (slides + 4 cheatsheets + all micros).

---

## B. THE NOTION SUB-PAGE — exact ordered structure + where each artifact embeds

> **Page model (from the verified gold page).** ONE self-contained page. Everything is **inline blocks** — no child_page, no child_database, no tables, no numbered_list_item, no column layout, no `embed`/`bookmark`/`video`/`pdf`-block (PDFs are `file` blocks). Heavy media is hidden behind **toggles** so the page stays scannable. Block types used: heading_1, heading_2, heading_3, paragraph, callout, toggle, bulleted_list_item, image, file, divider.

> **DO NOT** build the failed 7-section skeleton (`Overview → Roles → SOP Library → Workflow → Visuals → Signature Presentation → Outputs`). That layout is the failure signature. Build the **4-H1** structure below.

Build the page in this exact order:

### Top matter
1. **callout** — department one-liner.
2. **paragraph** ×2 — intro.
3. **divider**.

### H1 "1. The Deck — In Order"
- **paragraph** (intro).
- **toggle** titled `Open the full <N>-slide deck (slide 01 → <S>)` containing, IN ORDER:
  - **image** ×S — the deck slide renders, captioned `Slide 01` … `Slide <S>` (upload/host `renders-light/slide-NN.png`).
  - **file** ×1 — the editable deck, captioned "The full editable PowerPoint (`<S>` slides, NN MB)." (the `<Dept-Slug>-LIGHT-<N>.pptx`).
- **divider**.

### H1 "2. Infographics — In Logical Flow"
- **paragraph** (intro).
- **toggle** titled `Open the micro-infographics (logical order)` containing all micro-infographic **image** blocks, captioned `What It Is`, `Getting Started`, the phases, the per-role/cluster set, the SOP set, `Types`, `Final Package` (mirror the gold caption flow).
- **heading_3** "The 4 One-Page Cheatsheets".
- **toggle** titled `Open the 4 cheatsheets` containing 4 **image** blocks captioned `Cheatsheet 1 - The Roles`, `Cheatsheet 2 - The SOPs`, `Cheatsheet 3 - The Presentation Types`, `Cheatsheet 4 - The Build Pipeline`.
- **divider**.

### H1 "3. The Reference PDFs"
- **paragraph** (intro).
- **file** ×9, listed flat (NOT in a toggle): the 8 numbered module PDFs + the DELUXE all-in-one:
  `01-Getting-Started.pdf`, `02-The-<N>-Roles.pdf`, `03-The-SOP-Rulebook.pdf`, `04-The-4-Presentation-Types.pdf`, `05-The-Build-Pipeline.pdf`, `06-The-Quality-Gates.pdf`, `07-The-Final-Package.pdf`, `08-Intelligence-Engines.pdf`, and `<Dept>-Department-Class-Reference-DELUXE.pdf` (caption "DELUXE - All-in-One Class Reference").
- **divider**.

### H1 "4. The Full Breakdown" (all-text; H2 → paragraph → toggle/bullets)
- **H2 "The <N> Roles"** → paragraph → **toggle** "Open all `<N>` roles + QC sub-specialists" containing H3 cluster headings, each with bulleted role entries (`ROLE-NN - description`).
- **H2 "The SOP Library"** → paragraph → **toggle** "Open the doctrine SOP library" with bulleted SOP entries (SOP-* families).
- **H2 "The 4 Presentation Types"** → 4 **bulleted_list_item** (the 4 types).
- **H2 "The Build Pipeline"** → paragraph → **toggle** "Open the full build pipeline" with the ordered bulleted steps (Step -2 → Delivery).
- **H2 "The Quality Gates"** → **callout** (shared auto-fail-then-scored rule) → 5 **bulleted_list_item** (Gate 1 Copy QC → Gate 5 Speech QC).
- **H2 "The Intelligence Engines"** → paragraph → **toggle** "Open the 9 intelligence engines" with 9 bulleted engines (Facial, Lighting, Typography, Story, World, Pricing, Hook, Recap, Product).
- **H2 "The Final Package"** → paragraph → 7 **bulleted_list_item** deliverables (PPTX, Deck PDF, Presenter's Guide, Word-for-Word Speech, Audio Demo MP3, Teleprompter Web App, QC Report).

### Closing
- **divider**.
- **callout** — "Generic department documentation — the `<DEPT>` Department for zero-human companies…".

### B — Notion structural rules (must all hold)
1. Single self-contained page; everything inline; no sub-pages/databases/tables.
2. Opens callout + 2 paragraphs; closes divider + "generic documentation" callout.
3. Exactly **4 numbered H1 sections**, separated by dividers: (1) The Deck, (2) Infographics, (3) The Reference PDFs, (4) The Full Breakdown.
4. Heavy media behind toggles (deck, infographics, cheatsheets, roles, SOP library, pipeline, engines).
5. Artifact bar present as REAL blocks: **1 editable `.pptx` file + S deck-slide images + all micro-infographic images + 4 cheatsheet images + 9 PDF file blocks (8 numbered + 1 DELUXE).**
6. PDFs are `file` blocks (not `pdf` blocks); no `embed`/`bookmark`/`video`.
7. Section 4 is all-text per the H2 layout above.

### B — Notion embedding map (artifact → where it lands)
| Kit artifact | Notion block type | Location |
|---|---|---|
| `renders-light/slide-NN.png` (×S) | image, caption `Slide NN` | §1 deck toggle |
| `<Dept-Slug>-LIGHT-<N>.pptx` | file | §1 deck toggle (after slides) |
| `micro-infographics/*.png` | image | §2 infographics toggle |
| `cheatsheet-1..4-*.png` | image, caption `Cheatsheet N - …` | §2 cheatsheets toggle |
| `01..08-*.pdf` + DELUXE.pdf | file (×9, flat) | §3 |
| speech / teleprompter / compact reference | (not embedded as blocks in gold; referenced in §4 Final Package text) | §4 text |

> **Uploading:** images/files must be hosted (Notion file upload or public URL) so the block carries a live `src`/`url`. A block with no `src` = FAIL. Never use local-Mac paths.

---

## C. BRAND / LIGHT STYLING RULES (BRAND-COLOR-SPEC.md content + render rules)

Light is **mandatory** on every rendered asset. No dark backgrounds anywhere. Write `BRAND-COLOR-SPEC.md` with this canonical content:

**Palette (5-color kit):**
- Background `#FBFBF9` / `#FFFFFF`
- Navy `#14233F` (ink only)
- Teal `#1F9D9A` (accent)
- Gold `#C8963E` (precious / sparing)
- Slate `#3A4A63`

**Poster variant (cheatsheets):** warm-white `#F8F7F4`, navy `#1A2744`, teal `#1C8A8A`, gold `#C9A84C`, gray `#E8E8E2`.

**Rules:**
- Light backgrounds mandatory — never dark.
- Navy = ink only; Gold = precious, used sparingly; Teal = accent.
- 60–85% white space.
- Geometric sans-serif type; serif only on hero/title slides.
- Include in the file: the full reusable Kie.ai **gpt-image-2 style directive** for 16:9 slides and portrait posters, plus an aspect/resolution quick-reference.

**Aspect/resolution quick-reference:**
- Slides & micro-infographics: 16:9, 2K.
- Cheatsheets: portrait, 2K.

> Apply this directive verbatim as the style preamble in every slide/micro/cheatsheet `-PROMPT.txt`, so renders are visually consistent and pass the light-background gate.

---

## D. BUILD ORDER (recommended sequence for the build agent)

1. Write `BRAND-COLOR-SPEC.md` (defines the style directive every prompt reuses).
2. Draft the 8 module `.html` sources + DELUXE `.html`; generate the 10 PDFs (8 modules + compact + DELUXE).
3. Author the deck (≥ 20 slides, target 60); write `<N>-SLIDE-RENDER-PROMPTS.md` and the per-slide `slide-NN-PROMPT.txt`.
4. Render slides → `renders-light/slide-NN.png`; bake into `<Dept-Slug>-LIGHT-<N>.pptx`. Log `kie_task_ids.json`.
5. Write the speech `.md` and teleprompter `.html`.
6. Render 4 cheatsheets (+ prompts) and all micro-infographics (+ prompts, 1:1).
7. Write `00-DELIVERY-PACKAGE-INDEX.md`.
8. Build the Notion page per §B; upload/host every artifact; embed as real blocks.
9. Run the §0 acceptance gate; have a separate verifier re-run the raw `unzip…|grep -c` slide count and the Notion artifact-block count. Report the raw numbers.

---

## E. FINAL ACCEPTANCE CHECKLIST (paste-ready — identical to the enforcement gate)

- [ ] `00-DELIVERY-PACKAGE-INDEX.md` exists.
- [ ] 8 module `.html` + 8 module `.pdf` exist (16 files).
- [ ] compact reference PDF + DELUXE PDF + DELUXE HTML exist (3 files).
- [ ] `<Dept-Slug>-LIGHT-<N>.pptx` exists AND `unzip -l … | grep -cE 'ppt/slides/slide[0-9]+\.xml'` ≥ 20.
- [ ] `renders-light/`: slide PNG count == deck slide count == slide PROMPT count; `kie_task_ids.json` present.
- [ ] speech `.md` + teleprompter `.html` exist.
- [ ] 4 cheatsheet PNGs + 4 cheatsheet PROMPTs exist.
- [ ] `micro-infographics/`: PNG count == PROMPT count (1:1); covers one-per-role + fixed concept set; `working/kie_task_ids.json` present.
- [ ] `BRAND-COLOR-SPEC.md` + `<N>-SLIDE-RENDER-PROMPTS.md` exist.
- [ ] Notion page = exactly 4 numbered H1 sections (NOT the 7-section failed skeleton).
- [ ] Notion page artifact-block count (image+file) > 0 AND contains: all S slide images, the `.pptx` file block, all micro images, all 4 cheatsheet images, all 9 PDF file blocks — each with a live `src`/`url`.
- [ ] Zero placeholder/deferral language in any artifact section ("go here", "Add the PowerPoint", "will be added", "Phase 1b", "embedded here as public-URL").
- [ ] All renders light-background; brand palette applied.
- [ ] Raw counts quoted by an independent verifier before "done".
