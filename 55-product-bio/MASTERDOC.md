# Product Bio Engine — MASTERDOC (the SACRED IP)

> The IP of this skill is **two verbatim system prompts** — the "Guru-Level
> Product Bio Architect" (chain 1) and the "Google Doc HTML Writer" (chain 2) —
> baked byte-identical and sha256-pinned in `assets/prompts/`. The structures,
> counts, names, and envelope rules below are **SACRED**: never floored,
> reordered, renamed, or reinterpreted. Every rule is machine-enforced by a
> fail-closed prover in `scripts/`, never advisory. **Enforcement, not
> description.** The model's SELF-REPORTED word count / close count is IGNORED —
> the provers MEASURE the stripped text.

Provenance: extracted verbatim from the n8n workflow "Product bio, October 26,
2026" (25 nodes) — the two `lc.chainLlm` system messages. The two prompts are
Trevor Otts (BlackCEO) IP and ship fleet-wide inside this skill; the repo carries
zero client names. The in-prompt brand exemplar in chain 1 ("The BlackCEO
Makeover Experience") is the owner's OWN brand (PRD O2), not a client's.

## The two baked prompt assets (the literal, sha-pinned IP)

| Asset | Chain | sha256 (pinned) | Enforced by |
|---|---|---|---|
| `assets/prompts/01-product-bio-writer.md` | 1 — bio authoring | `82b52e01…a8ed0d8` | `prove_pb_fidelity.py` (AF-PB-PROMPT-DRIFT) |
| `assets/prompts/02-google-doc-html-writer.md` | 2 — HTML formatting | `f015392a…3543b8fa` | `prove_pb_fidelity.py` (AF-PB-PROMPT-DRIFT) |

A single byte's drift in either asset flips the hash and fails the fidelity gate
closed. The prompts are provider-agnostic: they name `google/gemini-2.5-pro` (via
OpenRouter) as their source model — already non-Anthropic. At runtime the CLIENT
runs them on the CLIENT's OWN provider chain (`assets/model-map.template.json`);
**never** an Anthropic / `claude-*` id, **never** operator keys.

## Chain 1 — the master-brain product bio (system = prompt 01)

A 6,000–7,000-word, 10-section sales knowledge base — the "master brain" that
powers AI chatbots and human sales teams. ONE call; system message = prompt 01
verbatim; user prompt interpolates `product_name`, `product_description`,
`first_name`+`last_name` (the only four fields the IP consumes).

### The 10 mandatory sections (in order)

| # | Section | Sacred floor | AF code |
|---|---|---|---|
| 1 | Product Name | the name + **10** distinct introductions | AF-PB-SECTION / AF-PB-COUNTS |
| 2 | Power Adjectives | **15–20** power adjectives with explanations | AF-PB-SECTION / AF-PB-COUNTS |
| 3 | Who It's Best For | the ideal customer profile | AF-PB-SECTION |
| 4 | Product Description | comprehensive, transformative | AF-PB-SECTION |
| 5 | Product Positioning | positioning + competitive replacements | AF-PB-SECTION |
| 6 | Objections | **8–10** objections addressed | AF-PB-SECTION / AF-PB-COUNTS |
| 7 | FAQs | **10–12** FAQs | AF-PB-SECTION / AF-PB-COUNTS |
| 8 | Social Proof | **8–10** unattributed testimonial statements | AF-PB-SECTION / AF-PB-COUNTS |
| 9 | StoryBrand 2.0 | all **7** beats: Character, Problem, Guide, Plan, Call to Action, Avoid Failure, Success | AF-PB-SECTION / AF-PB-COUNTS |
| 10 | Signature Closes | **24** distinct named styles (see below) | AF-PB-SECTION / AF-PB-CLOSES |

Sections must appear **in this order** (matched on header lines only, never
prose). Missing or out-of-order ⇒ `AF-PB-SECTION`.

### The 24 signature-close styles (the tracker's law)

The prompt TEACHES 20 styles in its "Required Styles" section but the mandatory
tracker (prompt 01, lines 900–928) and the anti-truncation rule ("if an
instruction lists 24 signature styles, you MUST write all 24", line 947) demand
**24**. Per PRD **O3** the gate enforces the stricter, later law — **24 distinct
named styles**, verbatim and in order:

1. Michelle Obama · 2. TD Jakes · 3. Grant Cardone · 4. David Goggins ·
5. Simon Sinek · 6. Mel Robbins · 7. Brené Brown · 8. Dave Chappelle ·
9. Ali Wong · 10. Raymond Reddington · 11. Iyanla Vanzant · 12. Tony Robbins ·
13. Oprah · 14. Gary Vaynerchuk · 15. Daymond John · 16. Les Brown ·
17. John Maxwell · 18. Rachel Rodgers · 19. Dean Graziosi · 20. Hook Point ·
21. Sense of Urgency · 22. Luxury Positioning · 23. FOMO · 24. Challenger.

Fewer than 24 distinct styles ⇒ `AF-PB-CLOSES`.

### Word count + completion verification

- **6,000–7,000 words**, MEASURED on the stripped text (prompt 01 lines 952–953).
  Outside the band ⇒ `AF-PB-WORDCOUNT`. The model's self-reported count and any
  whitespace padding are inert — whitespace collapses before counting.
- The **`COMPLETION VERIFICATION`** block is mandatory at the very end (prompt 01
  line 992). Absent ⇒ `AF-PB-VERIFY-BLOCK`. (The block's numbers are NOT trusted;
  they exist as a courtesy, not as proof.)

### Client-exact override

The 6,000–7,000 band is the DEFAULT floor. If the client states an EXACT word
target, the client's number wins — logged and noted on the certificate, never
floored, capped, or substituted (fleet-wide absolute law).

## Chain 2 — the Google-Docs-importable HTML (system = prompt 02)

ONE call; system = prompt 02 verbatim; user = chain-1 output. The strict contract:

| Rule | Sacred requirement | AF code |
|---|---|---|
| Envelope | output starts EXACTLY `<!DOCTYPE html>` and ends EXACTLY `</html>`, zero commentary (prompt 02 lines 18/24/323–324). The ONE permitted repair is a logged auto-trim of surrounding commentary | AF-PB-HTML-ENVELOPE |
| One H1 | exactly one `<h1>` (prompt 02 line 269) | AF-PB-HTML-H1 |
| No custom CSS | nothing beyond `page-break-after` — no `<style>` block, no other inline style property (prompt 02 line 289) | AF-PB-HTML-CSS |
| No content loss | the HTML retains the bio's content (≥ 90% normalized-token coverage) — "Preservation is Mandatory" | AF-PB-HTML-LOSS |

The HTML file **is** the Google-Docs-importable artifact; a client drags it into
Drive if they want a Doc. The source workflow's Drive upload / `/copy` / delete
dance existed only because n8n needed Drive to render HTML — it is DROPPED here
(delivery is local-only).

## The pipeline (replaces the 25 n8n nodes 1:1)

`P0-INTAKE → P1-FIDELITY → P2-BIO-AUTHOR → P3-BIO-QC → P4-HTML-AUTHOR →
P5-HTML-QC → P6-DELIVER`, walked in order with **no phase skips** by
`run_product_bio.py` behind the front-door nonce minted by
`product-bio-entry.sh`. A full P0→P5 pass issues a signed
`PROCESS-CERTIFICATE.json` carrying the MEASURED counts. No certificate ⇒ not
done (`AF-PB-PROCESS-INTEGRITY`). Delivery is a labeled local bundle
(`~/Downloads/Product-Bio-<slug>-<MM-DD-YYYY>/`) — **no n8n, no Google Drive, no
Slack, no Gmail, no Airtable** at runtime.

## Relationship to Avatar Alchemist (Skill 52) — FLAGGED, never merged

Skill 52 carries a **different** "Product Bio" prompt (a "strategic product
messaging specialist" inside the brand-intelligence pipeline). This skill (55) is
the STANDALONE master-brain generator. **Do not merge or deduplicate the two
prompts.** A change to either product-bio prompt must flag the sibling skill for
review. Routing: standalone master-brain bio → Skill 55; brand-intelligence
package (its embedded bio comes with it) → Skill 52. (PRD §5, G6, O8.)
