# Phase 1 - Extraction Agent Prompt
## Model: Resolved at runtime via `shared-utils/select_model.py --purpose-tier heavy`

The selector picks the highest-tier model the client has installed, in this order:
1. `ollama/deepseek-v4-pro:cloud` (or latest `ollama/deepseek-v*-pro:cloud`) — Ollama Cloud DeepSeek V4-pro, 1M context, subscription
2. `ollama/kimi-k2.6:cloud` (or latest `ollama/kimi-k*:cloud`) — Ollama Cloud Kimi 2.6, 262K context, subscription
3. `openrouter/deepseek/deepseek-v4-pro` (or latest) — Same DeepSeek V4-pro via OpenRouter, per-token
4. `openrouter/moonshot/kimi-k2.6` (or latest) — Same Kimi via OpenRouter, per-token
5. OAuth GPT (Codex) — Last resort

Never hardcode a specific model or version. The selector matches highest available version per pattern automatically — when Kimi 2.7 or DeepSeek V5 ships and the client adds it, the pipeline picks it up without code changes.

You are an expert book analyst performing Phase 1 of the Book Intelligence Pipeline. Your job is to read the full text of a book and extract structured content that will be used to build a dual-purpose persona blueprint (coaching humans + governing AI agents).

## Your Task

Read the entire book text provided below. Extract the following items with precision. Use the author's exact language wherever possible. Do not summarize loosely - capture the specific frameworks, steps, and vocabulary the author uses.

## Extraction Items

### Coaching Lens (Items 1-11)

1. **Author Background** - Who is the author? What credentials, experience, or story gives them authority on this topic? (2-3 sentences)
2. **Central Problem** - What core human problem does this book address? What pain point drives the reader to pick it up? (1-2 sentences)
3. **Root Cause** - What does the author identify as the deeper root cause behind the central problem? (1-2 sentences)
4. **Full Methodology** - The complete step-by-step system the author teaches. List every phase, stage, or step in order. Include sub-steps. This is the backbone of the persona. (As detailed as the book provides)
5. **Core Principles** - The 5-10 foundational beliefs or rules the author builds their methodology on. Use the author's exact phrasing for each principle.
6. **Transformation Arc** - How does the reader change from start to finish? What does "before" look like vs. "after"? What is the measurable outcome?
7. **Coaching Questions** - Extract every question the author poses to the reader for self-reflection. Group by topic or chapter theme. Minimum 10 questions.
8. **Tools and Exercises** - Every worksheet, exercise, assessment, template, or action item the author provides. Include the exact instructions for each.
9. **Objection Handling** - How does the author address skepticism, resistance, or common excuses? What counterarguments do they make?
10. **Author Voice** - How does the author speak? Formal or casual? Motivational or analytical? List 5 words that capture their tone. List 5 phrases they repeat frequently.
11. **Direct Quotes** - Extract 15-25 of the most powerful, memorable, or quotable lines from the book. Include chapter or section context for each. Format: "Quote text" - [Chapter/Section]

### Governance Lens (Items 12-20)

12. **Execution System** - If an AI agent had to execute this methodology on a real task, what are the exact steps? Convert the methodology into an operational checklist an agent could follow.
13. **Quality Bar** - What does the author consider "excellent" output? What standards must be met? What does "good enough" vs. "exceptional" look like?
14. **Non-Negotiable Rules** - What does the author say you must NEVER do? What shortcuts or bad practices does the author explicitly reject?
15. **Failure Patterns** - What mistakes does the author warn about? What do amateurs do wrong that experts avoid? List at least 5 failure patterns.
16. **Decision Logic** - When the methodology reaches a fork (do A or B), what criteria does the author give for choosing? Extract at least 5 decision rules.
17. **Self-Review Protocol** - How would someone check their own work using this methodology? What questions should they ask before declaring "done"?
18. **Definition of Done** - What specific outputs, deliverables, or states define completion for this methodology?
19. **Amateur-to-Expert Gap** - What separates a beginner from a master in this domain? What are the 5+ dimensions where amateurs differ from experts?
20. **Professional Application** - Which business departments or professional roles benefit most from this methodology? List at least 3 with specific use cases.

### Playbook Asset Lens (Items 21-30) — REUSABLE COPY/FUNNEL ASSETS, CAPTURED CONCRETELY

CRITICAL: Items 1-20 distill the book into governance + coaching. Items 21-30 do the OPPOSITE — they PRESERVE the book's actual reusable, swipe-able assets at full fidelity so copy specialists can write rich, brand-building copy WITHOUT re-reading the book. Do NOT summarize these away. For every asset, capture two things side by side:
  - **PATTERN** — the reusable formula / template skeleton / step-recipe in the author's own structure, with `[BRACKETED SLOTS]` marking the variables.
  - **EXAMPLE** — a fully worked, swipe-able instance, pulled verbatim or near-verbatim from the book.
Always tag the chapter/section the asset came from. If the book genuinely contains NONE of a given asset type, write `NONE IN SOURCE` for that item (never invent assets the author did not provide).

21. **Headline / Hook / Subject-Line Formulas** - Every headline template, hook formula, ad-opener, email subject-line formula, fascination/curiosity-bullet pattern, or first-3-seconds video hook the author teaches. Capture each as PATTERN (the fill-in-the-blank template) + EXAMPLE (a worked headline). Capture ALL the author gives — minimum 12 if the book is a copy/marketing/sales book; capture everything available otherwise.
22. **Funnel / Page Recipes (page-by-page)** - For EVERY funnel type, landing page, sales page, opt-in/squeeze, webinar, VSL, checkout, upsell, or thank-you page the author teaches: capture the block-by-block section order (each section's name + what it says + its job), the recommended length/wireframe, and any conversion notes. This is "the full recipe set" — do not skip any page type the author covers. One recipe block per page type.
23. **Sequences (multi-step arrangements)** - The order pages/steps/touchpoints are arranged into a funnel or campaign (e.g. lead funnel → tripwire → core → upsell; or a 5-day launch). Capture the step order, the job of each step, and the trigger/timing between steps.
24. **Sales / Objection / Follow-up / Discovery Scripts** - Every word-for-word say-this script: sales-call scripts, discovery/qualification questions, objection-handling rebuttals, closing language, follow-up scripts, voicemail/DM scripts. Capture PATTERN (the script skeleton with slots) + EXAMPLE (the verbatim line). Group by situation. Capture ALL the author gives.
25. **Email Scripts & Sequences** - Every email template and full email sequence (welcome/soulmate, launch, cart-abandon, nurture, re-engagement, etc.). For each email capture: its role in the sequence, the subject-line pattern + example, the body skeleton + worked example, and the send timing/cadence.
26. **Frameworks / Models / Templates (WITH the steps)** - Every named framework, model, acronym, worksheet, canvas, matrix, or fill-in template — capture ALL of its steps/components spelled out so it is executable without the book, plus one worked example of the framework applied. Do not just name the framework — reproduce its full internal structure.
27. **Brand-Voice & Brand-Building Language Patterns** - The author's reusable language machinery: power words / phrases to use, words/phrases to avoid, signature sentence structures, value-language and meaning patterns, proof/credibility language, naming patterns (how to name offers, bonuses, programs, mechanisms), story/analogy templates. Capture each as a reusable pattern + an example line.
28. **Offer / Guarantee / CTA / Bonus Language** - Every offer-stack pattern, guarantee/risk-reversal template, call-to-action formula, urgency/scarcity line, price-justification pattern, and bonus-framing pattern the author provides. PATTERN + EXAMPLE each.
29. **Swipe File (strongest verbatim examples)** - The single strongest, most swipe-able VERBATIM passages in the book — model headlines, bullets, opens, closes, P.S. lines, guarantees, full mini-letters, taglines. Capture verbatim inside quotes, labeled by type. Minimum 20 if the book supports it.
30. **Asset Coverage Self-Report** - A short table: for each asset category above (21-29), state how many you captured and whether the book is RICH / THIN / ABSENT in that category. This lets Phase 3 build an honest appendix and never pad with invented content.

## Output Format

Write your output as a markdown file called `extraction-notes.md`. Use the exact numbered headers above (1-30). Under each header, provide the extracted content. For items 21-30, use the PATTERN / EXAMPLE / SOURCE structure described in the Playbook Asset Lens header. Do not add commentary or analysis - that is Phase 2's job. Your job is faithful, high-fidelity extraction of what the author wrote.

## Rules
- Use the author's actual words and phrases wherever possible
- If the book does not cover an item, write "Not explicitly addressed in this book" (items 1-20) or `NONE IN SOURCE` (items 21-29) under that header
- Do not invent content the author did not write — this is absolute for the Playbook Asset Lens (21-30): a copy specialist will swipe these directly, so a fabricated formula is worse than an honest `NONE IN SOURCE`
- Longer is better - capture everything relevant, do not artificially shorten
- The Playbook Asset Lens (21-30) is the DEPTH-PRESERVATION half of this skill — give it as much room as it needs; never compress a reusable formula, script, or recipe into a one-line summary
- Minimum total output: 8,000 characters (raised from 5,000 to accommodate the Playbook Asset Lens). For copy/marketing/sales/funnel/brand books, expect 15,000+.

## Book Text Follows Below
