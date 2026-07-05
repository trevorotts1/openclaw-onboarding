# Starter Page Prompt (MAIN sales page — 8 sections, A/B)

> BAKED for Skill 56 (Sales Page Assets) — PROVIDER-AGNOSTIC. Runtime uses the CLIENT's OWN
> configured providers/keys (NEVER Anthropic, NEVER the operator's accounts). Credential seams:
> `${CLIENT_TEXT_API_KEY}` / `${CLIENT_IMAGE_API_KEY}` (see prompts/PROMPT-SEAMS.md). Intake seams:
> `${INTAKE.*}`. Prior-client example HTML + image-host/Drive URLs + Airtable/webhook infra ids removed;
> model names generalized. The SACRED frameworks + word/section bands are preserved and are
> machine-enforced by the Skill 56 provers.

> COPY AND CODE ARE TWO SEPARATE STEPS (FIX-XC-04c). One completion must NEVER author copy AND a
> full HTML page at the same time — that is how the DR structure and the per-section word floors
> got lost. STEP A emits an approved, per-section `copy_ledger.json` FIRST (measured against the
> SACRED bands by `prove_sp_main_structure.py`); STEP B renders that ALREADY-APPROVED copy into HTML
> and authors NO new copy. Do the steps in order; never merge them.

---

## The MAIN page section spec (SACRED — the "Advanced Sales Page Creation" 8-section structure)

Author BOTH variants (`a` and `b`). Variant `a` and variant `b` are two distinct angles on the SAME
offer (e.g. a proof-led angle vs. a story-led angle) — never the same copy twice. Every section is
mandatory, in THIS order. `word_min` is the SACRED stripped-word floor per section; the prover
MEASURES the copy and rejects anything under-band (AF-SP56-MAIN-SECTION-BAND) — under-length is as
much a failure as skipping the section. Write to the TOP of each band, not the floor.

| # | section id       | word_min | intent (what this section must accomplish) |
|---|------------------|----------|--------------------------------------------|
| 1 | header           | 18 | Attention-grabbing notification banner / headline: the single biggest promise or pattern-interrupt, in the reader's own language. |
| 2 | hero             | 35 | Above-the-fold hero: name the dream outcome, who it is for, and the primary CTA promise. Earn the scroll. |
| 3 | problem-solution | 35 | Agitate the specific problem the reader lives with, then pivot to the mechanism/solution that resolves it. |
| 4 | benefits         | 30 | The core transformation as concrete, felt benefits (not features) — what life looks like after. |
| 5 | product-details  | 35 | What the offer actually IS: deliverables, format, what they get, how it works. Make it tangible. |
| 6 | credibility      | 30 | Proof: testimonials, results, founder credibility, social proof that de-risks the decision. |
| 7 | final-cta        | 30 | The closing call to action with urgency (the countdown timer lives here) and a risk-reversal. |
| 8 | footer           | 18 | Footer: guarantee restatement, legal/utility links, and a final one-line reassurance. |

A mandated **countdown timer** must be present on the page (set `has_countdown_timer: true` on each
MAIN asset, or embed real countdown JS in the rendered fragment). Voice, offer names, brand color, and
proof all come from `${INTAKE.*}` — never invent facts the intake did not provide.

---

## STEP A — COPY ONLY (emit copy_ledger.json; write NO HTML)

### System
You are an expert direct-response sales-page copywriter. You write ONLY structured copy in this step.
You do not write HTML, CSS, or JavaScript here. You return machine-readable JSON only.

### User
Using the offer, audience, brand voice, proof, and CTA link from `${INTAKE.*}`, write the MAIN sales
page copy for BOTH variants `a` and `b`, section by section, following the 8-section spec above. For
every section, write to the TOP of its word band with genuine, specific, non-repetitive copy (no
filler, no padding, no placeholder text, no mid-phrase cutoffs).

Return ONE JSON object shaped EXACTLY like this (no commentary before or after):

    {
      "funnel_type": "sales_page_assets",
      "assets": [
        {
          "stage": "main", "variant": "a", "type": "page",
          "asset_key": "${INTAKE.client_slug}__${INTAKE.funnel_slug}__main__page__v01a",
          "has_countdown_timer": true,
          "sections": [
            {"order": 1, "name": "Attention-Grabbing Header", "copy": "..."},
            {"order": 2, "name": "Hero Section",              "copy": "..."},
            {"order": 3, "name": "Problem & Solution",        "copy": "..."},
            {"order": 4, "name": "Benefits Section",          "copy": "..."},
            {"order": 5, "name": "Product Details",           "copy": "..."},
            {"order": 6, "name": "Credibility Section",       "copy": "..."},
            {"order": 7, "name": "Final Call to Action",      "copy": "..."},
            {"order": 8, "name": "Footer",                    "copy": "..."}
          ]
        },
        { "stage": "main", "variant": "b", "type": "page", "has_countdown_timer": true, "sections": [ ...same 8 sections, a DIFFERENT angle... ] }
      ]
    }

This JSON is written to `copy_ledger.json` and gated by `prove_sp_main_structure.py` (8 sections in
order, both variants, per-section word floors, countdown). It only advances to STEP B once it PASSES.
DO NOT emit HTML in this step.

---

## STEP B — RENDER ONLY (inject the APPROVED copy into HTML; author NO new copy)

Run this step ONLY after the STEP-A `copy_ledger.json` has passed its prover. Your input is the
APPROVED copy — use it VERBATIM. You are a front-end engineer, not a copywriter, in this step: do not
rewrite, shorten, expand, or invent copy. If a section reads thin, STOP and return to STEP A; never
"fix" copy inside the render.

Important Formatting Instructions (so the code functions when pasted into the platform code-snippet area):

- Do not use backtick characters in your output.
- Avoid using triple backtick characters anywhere in your output.
- Never include the character sequence of three backticks, with or without a language tag.

### System
You are an expert front-end engineer building a responsive, high-converting sales page in clean,
valid HTML5. You render approved copy; you never author copy.

### User
Build the complete HTML page for one MAIN variant, injecting the approved section copy from
`copy_ledger.json` in the exact 8-section order. Requirements:

1. **Complete HTML only** — begin with the DOCTYPE, include full HEAD and BODY, all valid HTML/CSS/JS.
   No commentary before or after the code. Pure HTML output only.
2. **Embed all assets** — all CSS in a style tag in the head; all JS in script tags at the end of the
   body; embed every image using the GHL-CDN URLs provided; use the logo from `${INTAKE.brand_logo}`.
3. **Use the approved copy verbatim** — one rendered section per copy_ledger section, in order. Author
   nothing new.
4. **Responsive** — mobile-first with appropriate breakpoints; touch-friendly interactive elements.
5. **Visual design** — use `${INTAKE.primary_brand_color}` for CTAs and key headlines; clear visual
   hierarchy; balanced typography (never 3 boxes in one row and 1 in the next); adequate whitespace;
   readable contrast (never white text on a white background). Avoid breaking a word across lines.
6. **Functionality** — a working countdown timer for urgency; ALL CTA buttons centered and linking to
   the exact CTA URL from the intake; make every CTA prominent.

The HTML is inserted directly into the Go High Level code-snippet area without modification, so it
must be complete, valid, and ready to use.

NOTE: when choosing font color, size, and style, keep background/foreground contrast within standard
readability guidelines.
