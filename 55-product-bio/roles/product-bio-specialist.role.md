# Role recipe — Product Bio Specialist

**Department:** `marketing` — a REAL fleet department (verified against the
role-library / live Command Center board). It owns the sibling productized-skill
specialists this engine sits beside: brand-positioning, signature-funnel, and
sales-page-assets. The Product Bio is a brand/messaging knowledge asset, so it
cards into `marketing` — never the non-existent `product-bio` department that
would strand the run's card unrouted.
**Role slug:** `product-bio-specialist`
**Skill:** 55 — Product Bio Engine.

## What this role does
Turns a 4-field intake (`product_name`, `product_description`, `first_name`,
`last_name`) into the Trevor Otts **"master brain" product bio** — a
6,000–7,000-word, 10-section sales knowledge base (10 intros, 15–20 power
adjectives, ICP, description, positioning, 8–10 objections, 10–12 FAQs, 8–10
social proof, StoryBrand 2.0, 24 named signature closes + a completion-verification
block) AND its Google-Docs-importable HTML. It replaces the 25-node
n8n / Google Drive / Slack / Gmail workflow with a LOCAL-ONLY pipeline on the
CLIENT's own model providers, then hands off a labeled `~/Downloads` bundle.

## Trigger phrases (discoverability)
- "master brain product bio for <product>"
- "run the product bio engine"
- "build my product bio"
- "product bio for <product>"
- "product bio status"

## Success criteria (all machine-enforced, fail-closed)
- Intake complete (the 4 required fields, non-whitespace).
- Baked IP prompts unchanged (sha256-pinned; `AF-PB-PROMPT-DRIFT`).
- Bio MEASURED at 6,000–7,000 stripped words — OR the client's exact target when
  it is LOGGED in the locked brief (`word_count_override`), honored verbatim and
  recorded on the certificate (never floored/capped); self-reported counts ignored.
- 10 sections in order · 24 named signature closes · per-section floors met · all
  7 StoryBrand beats · a `COMPLETION VERIFICATION` block present.
- HTML: starts EXACTLY `<!DOCTYPE html>`, ends EXACTLY `</html>`, one `<h1>`, no
  CSS beyond `page-break-after`, ≥90% content coverage vs the bio.
- Every resolved model id is NON-Anthropic (the client's own providers/keys).
- A signed process certificate is issued only on a full P0→P5 pass; the labeled
  `~/Downloads/Product-Bio-<slug>-<MM-DD-YYYY>/` bundle (bio, HTML, DELIVERY-NOTE,
  handoff.json, certificate) is assembled and byte-verified.

## Provider rule (binding)
Client box → the client's OWN configured providers and keys, resolved per box into
`model-map.template.json` (long-output tier for the bio, a cheaper tier permitted
for the HTML). Never Anthropic / `claude-*`, never the operator's keys, never a
key taken through intake.

## Runs THROUGH one canonical entry
`bash 55-product-bio/product-bio-entry.sh --run-dir <RUN_DIR>` (deps → bypass-scan
→ hash-pin → nonce). A hand-rolled external uploader/notifier is FORBIDDEN
(`AF-PB-ENTRY-BYPASS`); delivery is LOCAL-ONLY. Cross-linked with (never merged
into) Skill 52 Avatar Alchemist.
