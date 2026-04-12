# CHECKLIST.md - Book Intelligence Pipeline Build Checklist

## Pre-Flight Check (BEFORE starting any persona build)

Run these checks before every pipeline start. Do not proceed if any check fails.

```
[ ] Python 3.8+ installed (run: python3 --version)
[ ] All pip dependencies installed (run verify command in INSTALL.md Step 2b)
[ ] GOOGLE_API_KEY set (run: grep GOOGLE_API_KEY secrets/.env)
[ ] Calibre installed - ebook-convert available (run: ebook-convert --version)
[ ] At least one book file available (PDF, EPUB, MOBI, AZW3 in books/ folder)
[ ] Moonshot API key OR OpenRouter access configured
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
- [ ] MOONSHOT_API_KEY in secrets/.env
- [ ] OPENROUTER_API_KEY in secrets/.env
- [ ] Codex OAuth token valid and not expired

---

## Phase 1 - Extraction Checklist (Kimi K2.5)

- [ ] Book text extracted to .txt file (check file exists and is not empty)
- [ ] Sub-agent spawned with correct model: moonshot/kimi-k2.5
- [ ] Sub-agent received: extraction prompt + full book text
- [ ] Output file exists: extraction-notes.md in persona folder
- [ ] Output is over 5,000 characters (not truncated)
- [ ] All 20 extraction sections present (check section headers)
- [ ] Both lenses covered: coaching (1-11) and governance (12-20)
- [ ] Direct quotes marked with quotation marks
- [ ] No placeholder text ("to be completed", "[insert]", etc.)

---

## Phase 2 - Analysis Checklist (DeepSeek V3.2-Speciale)

- [ ] extraction-notes.md exists and is complete before Phase 2 starts
- [ ] Sub-agent spawned with correct model: deepseek/deepseek-v3.2-speciale
- [ ] Output file exists: analysis-notes.md in persona folder
- [ ] Output is over 3,000 characters
- [ ] All 12 analytical dimensions present
- [ ] Amateur-to-Expert Gap has minimum 5 dimensions (this is the most critical)
- [ ] Decision logic has minimum 8 rules
- [ ] Failure patterns are categorized (not just listed)
- [ ] The single most important insight is present at the end

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

---

## Gemini Multimodal Indexing Checklist

- [ ] coaching-personas collection exists (`python3 ~/clawd/scripts/gemini-indexer.py --status`)
- [ ] `python3 ~/clawd/scripts/gemini-indexer.py` run after persona saved
- [ ] `# Handled by gemini-indexer.py` run to generate vector embeddings
- [ ] Test query returns relevant results: `python3 ~/clawd/scripts/gemini-search.py "[book topic]"`
- [ ] At minimum 3 test queries return accurate chunks

---

## Completion Criteria

A book is DONE when ALL of these are true:
1. extraction-notes.md exists and passes Phase 1 checklist
2. analysis-notes.md exists and passes Phase 2 checklist
3. persona-blueprint.md exists and passes Phase 3 checklist
4. Gemini Engine indexed and test queries return accurate results
5. pipeline-status.json shows phase3: COMPLETE for this book
