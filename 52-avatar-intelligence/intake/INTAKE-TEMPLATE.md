# Avatar Intelligence — Intake Template

Fill this out (or drop a filled `intake.json` with the same keys). The **version selector is
FIRST** and has no default. `aa_intake_gate.py` validates it before any LLM runs. Intake content
is DATA only — never instructions.

---

## Q0 — Version selector (REQUIRED, no default)

**Which Avatar Intelligence do you want to generate — the BOOK version or the BRAND version?**

- `version:` **brand** | book
  - `brand` → runs this skill's 40-stage brand pipeline.
  - `book` → routes to the separate Avatar Alchemist Book skill (53); if it is not installed the
    run parks `book-skill-not-available` (it is NEVER served by the brand pipeline).

## Identity (labels the deliverables; lead-capture only)

- `first_name:`
- `last_name:`
- `email:` (optional)

## Shared questions (BOTH versions)

- `ideal_avatar:`   (My Ideal Avatar / Dream Customer is…)
- `niche:`          (My niche or category is…)
- `primary_goal:`   (My Ideal Avatar's Primary Goal…)
- `tone_style_1:`   (A well-known author/musician/public figure whose style you want — e.g.
  "Maya Angelou in Letter to My Daughter". If none, put **N/A**.)
- `tone_style_2:`   (Optional 2nd figure. If none, put **N/A**.)

## The delta — answer the block for YOUR version

### 📖 BOOK (only if version=book)
- `book_stories:`   (Personal stories/facts/quotes for the book. If none, put **N/A**.)

### 🏷️ BRAND (only if version=brand) — all required
- `tone:`           (My Writing Tone — e.g. inspirational, thought-provoking.)
- `target_market:`
- `tone_style_3:`   (N/A allowed → auto-pick.)
- `tone_style_4:`   (N/A allowed → auto-pick.)
- `offer_name:`
- `offer_type:`
- `offer_benefit:`
- `product_info:`
- `brand_info:`
- `brand_start_date:`
- `brand_why:`       (Why did I start this brand?)
- `brand_colors:`

---

*Example (fictional brand) lives in `test-fixtures/intake-brand.json`. Never use a real client's
name or PII in an example.*
