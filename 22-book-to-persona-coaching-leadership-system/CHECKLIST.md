# CHECKLIST.md - Book Intelligence Pipeline Build Checklist

## Pre-Flight Check (BEFORE starting any persona build)

Run these checks before every pipeline start. Do not proceed if any check fails.

```
[ ] Python 3.8+ installed (run: python3 --version)
[ ] All pip dependencies installed (run verify command in INSTALL.md Step 2b)
[ ] GOOGLE_API_KEY set (run: grep GOOGLE_API_KEY secrets/.env)
[ ] Calibre installed - ebook-convert available (run: ebook-convert --version)
[ ] At least one book file available (PDF, EPUB, MOBI, AZW3 in books/ folder)
[ ] Ollama Cloud configured (`OLLAMA_API_KEY` or `models.providers.ollama.apiKey` in openclaw.json) — PRIMARY. OpenRouter (`OPENROUTER_API_KEY`) only as fallback.
```

**Quick dependency verification:**
```bash
python3 -c "import google.genai, numpy, pdfplumber, pypdf, ebooklib, aiohttp, bs4, mobi, lxml; print('ALL PASS')"
```

---

## Pre-Run Checklist (run before every pipeline start)

- [ ] TYP complete - all 7 .md files read in this session
- [ ] Google GenAI installed (`python3 -c "import google.genai"`)
- [ ] pdfplumber installed (`python3 -c "import pdfplumber; print('OK')"`)
- [ ] Master files folder located or confirmed
- [ ] PDF file exists and is readable
- [ ] `OLLAMA_API_KEY` set (Tier 1 + 2 primary — Ollama Cloud Kimi / DeepSeek-pro)
- [ ] `OPENROUTER_API_KEY` set (Tier 3 + 4 fallback only)
- [ ] Codex OAuth token valid and not expired (Tier 5 fallback)

---

## Phase 1 - Extraction Checklist (Smart Model Selection)

- [ ] Book text extracted to .txt file (check file exists and is not empty)
- [ ] Sub-agent spawned with the model returned by `shared-utils/select_model.py --skill book-to-persona --purpose "Phase 1 extraction" --format id` (Tier 1-4 result, or owner-provided if Tier 5)
- [ ] Selector did NOT return an Anthropic model (it's filtered at every tier)
- [ ] Sub-agent received: extraction prompt + full book text
- [ ] Output file exists: extraction-notes.md in persona folder
- [ ] Output is over 8,000 characters (not truncated; 15,000+ for copy/marketing books)
- [ ] All 30 extraction sections present (check section headers)
- [ ] All THREE lenses covered: coaching (1-11), governance (12-20), and Playbook Asset Lens (21-30)
- [ ] Playbook Asset Lens items 21-30 use the PATTERN + EXAMPLE + SOURCE structure (not summaries)
- [ ] Asset categories with no source material are marked `NONE IN SOURCE` (not fabricated)
- [ ] Direct quotes marked with quotation marks
- [ ] No placeholder text ("to be completed", "[insert]", etc.)

---

## Phase 2 - Analysis Checklist (Smart Model Selection)

- [ ] extraction-notes.md exists and is complete before Phase 2 starts
- [ ] Sub-agent spawned with the model returned by `select_model.py` for Phase 2 (same Kimi-first chain as Phase 1)
- [ ] Output file exists: analysis-notes.md in persona folder
- [ ] Output is over 5,000 characters
- [ ] All 13 analytical dimensions present
- [ ] Amateur-to-Expert Gap has minimum 5 dimensions (this is the most critical analytical section)
- [ ] Decision logic has minimum 8 rules
- [ ] Failure patterns are categorized (not just listed)
- [ ] The single most important insight is present
- [ ] Dimension 13 (Playbook Asset Inventory) present with the Asset Coverage Map (13A) and Patternized Catalog (13B)

---

## Phase 3 - Synthesis Checklist (GPT-5.3 Codex / Kimi fallback)

- [ ] Both extraction-notes.md and analysis-notes.md exist before Phase 3 starts
- [ ] Sub-agent spawned - check which model was used (Codex or fallback)
- [ ] Output file exists: persona-blueprint.md in persona folder
- [ ] Output is over 10,000 characters (a complete blueprint is much larger)
- [ ] Header block present with version, date, QC status
- [ ] All 14 sections present (check each section header)
- [ ] Section 3 (Coaching Framework) has specific questions - not just descriptions
- [ ] Section 4 (Agent Governance) - 4A, 4B, 4C, 4D all present
- [ ] Section 4A has minimum 5 non-negotiable rules
- [ ] Section 4A has minimum 8 decision logic rows
- [ ] Section 4B pre-delivery checklist is yes/no questions
- [ ] Section 4C has Amateur vs Expert table
- [ ] Section 7 (Triggers) has minimum 15 keyword triggers
- [ ] Section 9 (Quotes) - direct quotes marked with attribution
- [ ] Author name NOT used outside attribution-flagged quotes
- [ ] Zero placeholder text anywhere
- [ ] Section 14 (Routing) has scope limits and red flags
- [ ] Blueprint cross-references PLAYBOOK-APPENDIX.md where frameworks/templates/scripts are named (not summarized away)

---

## Phase 3b - Playbook Appendix Checklist (MANDATORY companion — depth preservation)

- [ ] persona-blueprint.md exists before Phase 3b runs
- [ ] Output file exists: PLAYBOOK-APPENDIX.md in persona folder (alongside the blueprint)
- [ ] Header block present + `companion_to: persona-blueprint.md`
- [ ] All 8 sections A-H present (HARD gate — orchestrator fails loud if missing)
- [ ] Section H Asset Coverage Map present (the honesty ledger — HARD gate)
- [ ] Output is over 6,000 characters HARD floor; 12,000+ soft target for copy/marketing/funnel books
- [ ] Every asset uses the Pattern + Worked example + Source capture convention (no bare summaries)
- [ ] Section A (formulas) ≥ 12, Section C (scripts) ≥ 10, Section F (brand-voice patterns) ≥ 15, Section G (swipe) ≥ 20 — for asset-rich books
- [ ] Section B carries the FULL recipe set (every page/funnel type the book teaches); Section E the FULL framework set
- [ ] Thin/non-commercial books mark absent categories ABSENT in the Coverage Map (NO fabrication)
- [ ] pipeline-status.json shows phase3b: COMPLETE (or COMPLETE_WITH_WARNINGS for a legitimately thin book)
- [ ] Zero placeholder text ("TODO", "[insert]", "to be completed")

---

## Gemini Multimodal Indexing Checklist

- [ ] coaching-personas collection exists (`python3 ~/.openclaw/scripts/gemini-indexer.py --status`)
- [ ] `python3 ~/.openclaw/scripts/gemini-indexer.py` run after persona saved
- [ ] `# Handled by gemini-indexer.py` run to generate vector embeddings
- [ ] Test query returns relevant results: `python3 ~/.openclaw/scripts/gemini-search.py "[book topic]"`
- [ ] At minimum 3 test queries return accurate chunks

---

## Completion Criteria

A book is DONE when ALL of these are true:
1. extraction-notes.md exists and passes Phase 1 checklist
2. analysis-notes.md exists and passes Phase 2 checklist
3. persona-blueprint.md exists and passes Phase 3 checklist
4. PLAYBOOK-APPENDIX.md exists and passes Phase 3b checklist
5. Gemini Engine indexed and test queries return accurate results
6. pipeline-status.json shows phase3: COMPLETE AND phase3b: COMPLETE (or COMPLETE_WITH_WARNINGS) for this book
