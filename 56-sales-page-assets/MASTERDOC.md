# MASTERDOC — Trevor Otts Direct-Response Sales Page Assets (anonymized)

> Canonical IP of the **Trevor Otts** Direct-Response funnel method — the sibling of the Signature
> Funnel (Skill 49). Every **section name**, every **section order**, and every **word/character band**
> below is machine-enforced by a fail-closed prover, never advisory. This is the spec the
> `56-sales-page-assets` skill honors exactly.
>
> **Anonymization note:** the METHOD is reproduced faithfully; no client, brand, program name, URL,
> founder name, or private page HTML ships in this repo. The "Trevor Otts" attribution is the method's
> author/brand and is kept intentionally. All examples use fictional slugs (`jane-doe`, `glow-method`).
> The legacy engine embedded a real prior-client page as a few-shot example, three inline plaintext
> secrets, and an Anthropic main-page leg — ALL removed/neutralized here (see §7).

---

## 0. What the engine is

A survey-driven asset factory: one **"Ultimate AI Sales Page Writer"** survey submission ->
per-client Drive folder -> N AI images -> **seven direct-response copy/page assets** -> two-track
delivery (editable Google Docs + a machine build bundle) -> Skill 6 build -> preview + human approval ->
publish, with the bump copy wired by Skill 44. The five product-description inputs map 1:1 to the classic
OTO funnel stages: **front-end (main) -> bump -> upsell -> downsell -> high-ticket ascension.**

The IP layer (frameworks/prompts) is **fleet-shared**; the provider layer is **per-client** (client
providers only, never Anthropic).

---

## 1. THE SEVEN ASSETS (machine-gated frameworks)

### 1.1 Main sales page — Version A + Version B (8-SECTION structure)
The "Advanced Sales Page Creation Instructions" 8-section conversion structure, in order:

| # | Section | Notes |
|---|---|---|
| 1 | **Attention-Grabbing Header** | blinking notification banner acknowledging the visitor's prior action; brand logo |
| 2 | **Hero Section (above the fold)** | headline + sub-headline + high-impact image + initial CTA |
| 3 | **Problem & Solution** | articulate the pain; introduce the product as the solution; secondary CTA |
| 4 | **Benefits** | 3-5 core benefits in "you" language + supporting visuals |
| 5 | **Product Details** | what it is, key features as means to benefits, value justification, another CTA |
| 6 | **Credibility** | generated testimonials / social proof, trust indicators, objection answers |
| 7 | **Final Call to Action** | recap value, prominent CTA, risk-reversal, what-happens-next |
| 8 | **Footer** | brand logo, copyright, legal disclaimers |

- **Mandatory countdown timer** (JavaScript) — enforced (`AF-SP56-MAIN-NO-COUNTDOWN`).
- **Both A/B variants required.** Version A = the 8-section + countdown baseline (classifies
  `SIMPLE -> DIRECT`). Version B = a full rewrite with a 10-second page-loader countdown, a
  scroll-triggered animated value counter, synchronized 11-minute timers, Apple-inspired design (may
  classify `ADVANCED -> VERCEL_EMBED`). The label says the variant (`v01a`/`v01b`), NEVER the model (R1).
- Enforced by `prove_sp_main_structure.py`: 8 sections in order, both variants, countdown present.

### 1.2 Upsell page — Version A + Version B (Trevor Otts 9-SECTION Framework)
The upsell capitalizes on post-purchase psychology. Nine sections, in EXACT order:

1. **Hook** — acknowledge the purchase + introduce the upgrade opportunity
2. **Pain 1** — first pain point of the incomplete solution
3. **Pain 2** — second pain point amplification
4. **Pain 3** — third pain point with urgency
5. **Hope** — hope introduction
6. **Solution** — solution positioning
7. **Value Stack** — value-stacking presentation
8. **Logical Justification** — with founder credibility
9. **Identity Challenge** — the close

- **Both A/B variants required.** Variant A = conversion-copywriter + web-developer persona. Variant B =
  the "Emotional Hijacking Expert" persona (pattern interrupts, social-proof saturation, psychological
  urgency) over the SAME 9 sections.
- Enforced by `prove_sp_upsell_structure.py`: 9 sections in Trevor Otts order, both variants.

### 1.3 Downsell page (post-rejection emotional recovery)
Same 9-section spine, **graceful-concession frame**: honor the "no", reduce the barrier (smaller/lighter/
staged offer). Empathetic, typography-first, minimalist "personal letter" design. Two variants a/b.

### 1.4 High-ticket long-form page ("The Sovereign Architect")
A ~22-section long-form ascension page for **$1,000-$25,000+** offers: paradigm-shift open, 3 case
studies, objection destruction, bonus stack, P.S. pattern interrupt.
- **SACRED word band: 6,500-7,100 stripped words** — enforced by `prove_sp_highticket_band.py`
  (`AF-SP56-HIGHTICKET-FLOOR` / `-CEILING`). Padding to hit the floor is caught by the content-authenticity
  QC grade (no 6+ word phrase repeated >~3x; no vocab-list dumps — HANDOFF systemic fix #8).

### 1.5 Bump-sale copy (order bump)
40-80 words of plain order-bump text, psychological order: **pattern interrupt -> social proof ->
emotional gut punch -> scarcity/urgency -> no-brainer close**, ENDING with the checkbox line
`[X] Yes, add this to my order`.
- **SACRED band: 40-80 body words + checkbox close** — enforced by `prove_sp_bump_band.py` (the body
  count EXCLUDES the checkbox line; the legacy engine's examples count 72/68/76 body words). This is the
  one legacy asset written WITHOUT a sanitizer pass; here it is machine-gated.
- The bump is COPY, not a page — it routes to the **Skill 44** order-bump seam, not a Skill 6 page.

### 1.6 Thank-you page (gap closed vs the legacy engine)
The legacy workflow generated NO post-purchase page. Every funnel Skill 6 builds MUST terminate on a
thank-you step: celebrate the decision, no offer CTA, utility buttons only. Source: a new profile OR
borrow Skill 49's v2 Part 5 thank-you profile (PRD O-4). Enforced by `prove_sp_bundle.py`
(`AF-SP56-BUNDLE-THANKYOU`).

---

## 2. THE IMAGE SYSTEM (slice coverage machine-gated)

- **N image prompts** (default RAISED to **12**, max 20). Templates 1-4 fixed (two audience portraits,
  one no-people environment shot, one action-taker portrait); 5-20 in tangible (A) / intangible (B)
  variants chosen from Brand + Product info.
- **Slice map:** `main [0:4]` · `upsell-1 [4:8]` · `downsell-1 [8:10]` · `high-ticket [10:]`. The legacy
  default of 4 left the upsell/downsell/high-ticket slices EMPTY; `prove_sp_image_plan.py` fails closed
  (`AF-SP56-IMGPLAN-SLICE-EMPTY`) unless every stage gets >= 1 image.
- **Generation** delegates to **Skill 47** (`kie_image.py`) or the client's OWN image provider. Images are
  **re-hosted via Skill 6 `ghl_media.py`** (ImgBB removed); every `<img>` must resolve to the GHL media host.

---

## 3. THE TWO-TRACK DELIVERABLE (the Skill 6 handoff)

- **Track 1 (client):** labeled Google Docs in the client Drive folder — human-editable review copy.
- **Track 2 (build):** the machine bundle Skill 6 reads:

```
<client>__<funnel>__run-<YYYYMMDD>-<seq>/
├── funnel-manifest.json          ← THE handoff artifact (templates/funnel-manifest.schema.json)
├── pages/  …__main__page__v01a.fragment.html · …__main__page__v01b.fragment.html
│         …__upsell-1__page__v01a/b · …__downsell-1__page__v01 · …__high-ticket__page__v01
│         …__thank-you__page__v01
├── copy/   …__bump__copy__v01.md          ← 40-80-word bump text (NOT a page — Skill 44 seam)
├── images/                                ← originals + the GHL-media CDN URL map
└── copy-tokens/                           ← per-page approved-phrase lists for verify
```

Adapter obligations before handoff: fragment-ize (naked fragments, not full documents), rewrite image
URLs to the GHL CDN, let Skill 6's Phase-5 classifier decide DIRECT vs VERCEL_EMBED per page, route the
bump to Skill 44, include the thank-you step. Publish only after **explicit human approval**.

---

## 4. THE OTO FUNNEL MAP (the five product-description inputs)

| Input | Stage | Asset |
|---|---|---|
| `product_info` | front-end (main) | main page A/B |
| `bump_desc` | bump | bump copy (Skill 44 seam) |
| `upsell_desc` | upsell-1 | upsell page A/B |
| `downsell_desc` | downsell-1 | downsell page |
| `high_ticket_desc` | high-ticket | Sovereign Architect long-form |

---

## 5. QC GATES (where the pipeline fails closed)
1. P0 — intake gate (`prove_sp_intake.py`); locked 12-field brief before generation.
2. P1 — image-slice coverage (`prove_sp_image_plan.py`); every stage gets >= 1 image.
3. P3 — the copy suite (main-8, upsell-9, high-ticket band, bump band); any violation = hard AF.
4. P4 — every `<img>` resolves to the GHL media host (Skill 6).
5. P7 — build-bundle labels + Skill 6 manifest contract (`prove_sp_bundle.py`).
6. P9 — signed `PROCESS-CERTIFICATE.json` (`prove_sp_cert.py`); no cert = `AF-SP56-PROCESS-INTEGRITY`.
7. Publish guard — preview URL + labeled `~/Downloads/` bundle; going live is an explicit human approval.
8. **Content authenticity (finalize QC, HANDOFF fix #8):** goldens graded >= 8.5 for real authored copy —
   no 6+ word phrase repeated >~3x, no mid-phrase cutoffs, image prompts genuinely authored.

---

## 6. Delegation seams (never forked)
- **Images ->** Skill 47 `kie_image.py` OR the client's own image provider.
- **GHL media folder + upload ->** Skill 6 `ghl_media.py` (ImgBB removed).
- **GHL funnel/step/page build + HTML injection ->** Skill 6 `ghl_rest_canvas.py` / `ghl_builder.py`.
- **Bump order-bump element ->** Skill 44 (order form + product object first).
- **10 promo emails ->** the Email Skill project (post-downsell handoff).

---

## 7. FLEETIZATION — what was removed/neutralized from the legacy engine (binding)
1. ⛔ **Anthropic main-page leg REMOVED.** The legacy `Claude Copy` node called the Anthropic messages
   endpoint (a `claude-*` sonnet model). Re-pointed to the client's own provider; the JSON-body-formatter step that only
   existed to build the raw Anthropic HTTP request is deleted (its 8-section spec lives in `MASTERDOC` §1.1
   + the baked prompts). ZERO `api.anthropic.com` / `claude-*` references anywhere in the shipped skill.
2. ⛔ **Three inline plaintext secrets NEUTRALIZED to env placeholders.** The legacy engine hardcoded an
   Anthropic key (`x-api-key`), an OpenAI bearer (`Authorization`), and an ImgBB key. The literal values
   live ONLY in the never-copied `source/raw-workflow-export.json`; the shipped prompts reference client
   credentials as env placeholders (`${CLIENT_TEXT_API_KEY}`, `${CLIENT_IMAGE_API_KEY}`), and ImgBB is
   removed entirely (Skill 6 `ghl_media.py`). See `prompts/PROMPT-SEAMS.md`.
3. ⚠️ **Prior-client content GENERALIZED.** The legacy main-page prompts embedded a real prior client's
   full page HTML (brand, logo, founder name, ImgBB image URLs) as a few-shot example — removed and
   replaced with fictional, brand-agnostic guidance.
4. ⚠️ **Image-slice math fixed** (default N raised to 12; every stage slice non-empty — `prove_sp_image_plan.py`).
5. ⚠️ **Test artifacts removed** (the leftover "File Trevor BR Test" email subject -> "Your <funnel> sales
   page assets are ready"; the two survey field keys with embedded spaces repaired in the intake schema —
   renamed on the GHL + consumer sides together at cutover, PRD O-3).
6. ⚠️ **Sanitizers determinized** — the six GPT-4.1 clean passes + the missing bump clean pass become one
   deterministic Python fragment-strip (P5).

---

## 8. Deliverable labeling grammar (Skill 56 OWNS it — reciprocal with Skill 49)

```
<client>__<funnel>__<stage>__<type>__v<NN><variant>
```

- `<client>` — client/brand slug (lowercase kebab; RUNTIME ONLY — never a real client name in this
  fleet-wide repo, only on the client box). `<funnel>` — the OFFER slug.
- `<stage>` — one of `main` · `checkout` · `bump` · `upsell-1` · `downsell-1` · `upsell-2` · `downsell-2` ·
  `high-ticket` · `thank-you` (shared with Skill 49's 3/5/7 matrix, rule R6).
- `<type>` — one of `copy` · `page` · `img-NN` · `funnel` · `email-NN` · `brief` · `manifest` · `cert`.
- `vNN` — 2-digit version, bumped per regeneration run. `<variant>` — lowercase letter, ONLY for true A/B
  twins of the same stage (`v01a`/`v01b`).

Double-underscore (`__`) is the field separator. Example:
`jane-doe__glow-method__upsell-1__page__v01b.fragment.html`.

**Binding rules:** R1 NO model names in labels (model provenance -> `funnel-manifest.json` metadata only);
R2 version vs variant; R3 one key, every surface; R4 ZHC prefix on every GHL container (UPPERCASE); R5
client slugs are runtime data; R6 stages are shared across both engines.

**Reciprocal pin:** this grammar is SHARED with **Skill 49 (Signature Funnel)**. Skill 49's `MASTERDOC.md`
§8 pins the forward-ref back to this section (`stage`/`type` enums extended as needed). One grammar, both
engines, one namespace — do not diverge. Machine-enforced by `prove_sp_bundle.py` against
`structure/labeling-grammar.json`.

---

## 9. Client-provider rule (binding)
On a client box the skill uses the **client's OWN configured providers and keys** — never the operator's,
never Anthropic model ids. The skill tiers the client's own chain (strongest -> the 7 copy assets + QC;
mid -> image prompts / HTML / JSON; cheapest -> catalog / poll). A/B variants come from two client models
OR two persona prompts on one client model. This skill is provider-neutral by construction; the provers are
deterministic and use no model at runtime. Per-box capability must be proven before fleet rollout.
