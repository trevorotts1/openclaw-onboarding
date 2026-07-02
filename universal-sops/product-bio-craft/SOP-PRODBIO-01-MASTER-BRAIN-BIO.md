# SOP-PRODBIO-01: BUILD THE MASTER-BRAIN PRODUCT BIO

**Cluster:** Product-Bio-Craft Rules (`universal-sops/product-bio-craft/`)
**Master authority:** `55-product-bio/PRODUCT-BIO-MANIFEST.json` (phase spine + the `autofails` table) + `55-product-bio/MASTERDOC.md` (the SACRED IP)
**Owning department:** Marketing
**Owning roles:** Conversion Copywriter (drives the entry), routed by the Chief Marketing Officer
**Canonical entry:** `55-product-bio/product-bio-entry.sh`
**Stages:** P0-INTAKE -> P1-FIDELITY -> P2-BIO-AUTHOR -> P3-BIO-QC -> P4-HTML-AUTHOR -> P5-HTML-QC -> P6-DELIVER
**Gates this SOP satisfies:** AF-PB-INTAKE-MISSING, AF-PB-PROMPT-DRIFT, AF-PB-WORDCOUNT, AF-PB-VERIFY-BLOCK, AF-PB-SECTION, AF-PB-CLOSES, AF-PB-COUNTS, AF-PB-HTML-ENVELOPE, AF-PB-HTML-H1, AF-PB-HTML-CSS, AF-PB-HTML-LOSS, AF-PB-STAGE-SKIPPED, AF-PB-PROCESS-INTEGRITY, AF-PB-ENTRY-BYPASS, AF-PB-HASH-PIN, AF-PB-ANTHROPIC

---

## 0. WHAT THIS ARTIFACT IS

The master-brain **Product Bio** is a 6,000–7,000-word, 10-section sales knowledge base that powers
AI chatbots and human sales teams. Its 10 mandatory sections, in order:

1. Product Name + 10 intros
2. 15–20 power adjectives
3. Who It's Best For (ICP)
4. Product Description
5. Positioning + competitive replacements
6. 8–10 objections
7. 10–12 FAQs
8. 8–10 social-proof statements
9. StoryBrand 2.0 narrative (all 7 beats)
10. Signature Closes — **24** distinct named voice styles

...plus the mandatory `COMPLETION VERIFICATION` block. The engine also emits a second artifact: a
Google-Docs-importable HTML rendering of the bio. Both ship as a labeled LOCAL bundle in
`~/Downloads/Product-Bio-<slug>-<MM-DD-YYYY>/` with a signed `PROCESS-CERTIFICATE.json`.

## 1. WHEN TO BUILD IT

Build it when a client needs the standalone "master brain" for one product/offer — the sales
knowledge base a chatbot or a human closer reads from. If the request is for a full
brand-intelligence package (avatar, brand voice, and a bundled bio), that is **Skill 52 (Avatar
Alchemist)**, not this skill. Routing disambiguation: standalone master-brain bio -> Skill 55;
brand-intelligence package (its embedded bio ships with it) -> Skill 52. The two are cross-linked and
NEVER merged.

## 2. THE 4-FIELD INTAKE (P0, one block, turn-gated)

Ask the intake in a SINGLE message, never one-question-per-turn. Only four fields are REQUIRED — they
are the only inputs the baked IP consumes (`55-product-bio/assets/intake-schema.json`):

| Field | What it is |
|---|---|
| `product_name` | Exact product name (+ optional tagline/positioning). |
| `product_description` | What the product is/does + the transformation it delivers. |
| `first_name` + `last_name` | Founder/owner name (feeds the bio + the deliverable label). |

Optional, captured for handoff parity only (dormant in the LLM path): `client_folder_name` (label
override), `email`, `phone`. Never fabricate an intake answer — client words only; return the gap list
and STOP if a required field is missing. Write `working/intake.json`. A self-attested "intake
complete" flag is never trusted: `prove_pb_intake.py` reads the actual fields (any missing / empty /
whitespace required field = `AF-PB-INTAKE-MISSING`).

## 3. THE GATE CONTRACT (P1–P6 — enforcement, not description)

Every stage is deterministic and fail-closed. A violating artifact is NOT converted, NOT delivered,
NOT certified. Bands are MEASURED on the STRIPPED text; a model's self-reported count is never trusted.

| Stage | Gate | Rule |
|---|---|---|
| P1-FIDELITY | `AF-PB-PROMPT-DRIFT` | sha256 of each baked prompt asset == its recorded pin; the IP cannot silently drift. |
| P3-BIO-QC | `AF-PB-WORDCOUNT` | measured stripped word count within 6,000–7,000 (self-report ignored; padding inert). |
| P3-BIO-QC | `AF-PB-VERIFY-BLOCK` | the `COMPLETION VERIFICATION` block is present. |
| P3-BIO-QC | `AF-PB-SECTION` | the 10 mandatory sections present and IN ORDER. |
| P3-BIO-QC | `AF-PB-CLOSES` | exactly **24** distinct named signature-close styles (PRD O3). |
| P3-BIO-QC | `AF-PB-COUNTS` | 10 intros / 15–20 adjectives / 8–10 objections / 10–12 FAQs / 8–10 social-proof / all 7 StoryBrand beats. |
| P5-HTML-QC | `AF-PB-HTML-ENVELOPE` | starts EXACTLY `<!DOCTYPE html>`, ends EXACTLY `</html>` (after the one logged auto-trim). |
| P5-HTML-QC | `AF-PB-HTML-H1` | exactly one `<h1>`. |
| P5-HTML-QC | `AF-PB-HTML-CSS` | nothing beyond `page-break-after`. |
| P5-HTML-QC | `AF-PB-HTML-LOSS` | >= 90% normalized-token coverage vs the source bio. |
| P6 / run | `AF-PB-STAGE-SKIPPED` / `AF-PB-PROCESS-INTEGRITY` | a signed certificate requires a full P0->P5 pass, no phase skips. |
| entry | `AF-PB-ENTRY-BYPASS` / `AF-PB-HASH-PIN` | no hand-rolled Drive/Slack/Gmail/n8n uploader in the run dir; the enforcement pair matches its pinned head. |
| verify | `AF-PB-ANTHROPIC` | no `claude-*` / `anthropic` id in the shipped skill or the resolved client-path model map. |

**Rework loop:** a bio-QC failure returns the exact `AF-PB-*` code; a bounded re-author loop (<= 3
attempts, verifier != author) re-authors then re-proves the WHOLE artifact. HTML envelope auto-trim
(strip pre/post commentary) is the ONLY permitted HTML repair and is logged, then re-proven. After 3
attempts, hard-escalate to the operator — never silent-pass.

## 4. RUN IT — THROUGH THE ONE ENTRY

```
bash 55-product-bio/product-bio-entry.sh --run-dir <RUN_DIR>
```

The entry runs three fail-closed gates (DEPS -> BYPASS-SCAN -> VERSION/HASH-PIN), mints a run-scoped
nonce, and dispatches `run_product_bio.py`, which walks P0 -> P6 with no phase skips. Writing and
running a hand-rolled uploader/notifier is the ungoverned path and is FORBIDDEN (`AF-PB-ENTRY-BYPASS`).
A gate may be skipped ONLY by a logged owner approval token in
`<run-dir>/working/checkpoints/process_manifest.json` — never silently.

## 5. DELIVER (P6, local-only)

The deliverable bundle is `~/Downloads/Product-Bio-<slug>-<MM-DD-YYYY>/`:
`Product-Bio-<slug>.md`, `Product-Bio-<slug>.html` (Google-Docs-importable), `DELIVERY-NOTE.md`,
`handoff.json`, and `PROCESS-CERTIFICATE.json`. NO n8n / Google Drive / Slack / Gmail / Airtable. Any
push notification is per-client config through the client's own OpenClaw gateway (never bypassed),
client-silent by default. **No signed certificate = not done.**

## 6. VERIFY BEFORE CLAIMING DONE

End-to-end proof is from the CLIENT outcome, not the builder's claim: the bundle opens, the HTML
imports into Google Docs cleanly, and the certificate chain is intact. Self-verify the skill with:

```
bash 55-product-bio/verify.sh
```

It runs each prover's `--self-test`, reproduces the golden bundle, proves every attack fixture is
rejected with its distinct AF code, re-checks the prompt-fidelity pins, and runs the no-Anthropic scan
— idempotent and read-only. Any nonzero exit = fix and re-run; never guess a missing field or waive a
floor.
