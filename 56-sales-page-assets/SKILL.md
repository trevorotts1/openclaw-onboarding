---
name: sales-page-assets
description: Builds a Trevor Otts Direct-Response sales-page asset stack from one Ultimate AI Sales Page Writer survey — the DR sibling of Skill 49 (absorbs the n8n "All In One Sales Page Assets" funnel family). Produces the 8-section main page (A/B + countdown timer), the Trevor Otts 9-section upsell (A/B personas), a downsell recovery page, the Sovereign Architect high-ticket long-form page (6,500-7,100 words), 40-80-word bump copy with a checkbox close, and a slice-covered image plan. Gates every framework with fail-closed deterministic provers (intake, image-slice coverage, main-8, upsell-9, high-ticket band, bump band, media provenance + per-stage coverage, build-bundle labels + Skill 6 manifest contract) plus a signed PROCESS-CERTIFICATE. A canonical fail-closed entry (deps/version/hash-pin/bypass-scan/0600-nonce) drives a no-skip orchestrator. Delegates image generation to Skill 47 (or the client's own image provider) and ALL GHL media + build to Skill 6; routes the bump copy to the Skill 44 order-bump seam. OWNS the <client>__<funnel>__<stage>__<type>__vNN labeling grammar (reciprocal with Skill 49). Client runtime uses the client's own providers, never Anthropic.
version: 1.2.0
---

# Sales Page Assets (Skill 56)

The methodology + enforcement layer for the Trevor Otts **Direct-Response** funnel — the 8-section
main sales page, the 9-section upsell, the downsell recovery page, the Sovereign Architect high-ticket
long-form page, and the order-bump copy, produced from one **"Ultimate AI Sales Page Writer"** survey
submission. This is the **Direct-Response sibling of the Signature Funnel (Skill 49)**: two funnel copy
engines sharing one delivery rail (Skill 6) and one labeling grammar. This skill owns the **IP and the
gates**; existing engines own execution: **Skill 47** (or the client's own image provider) generates
images, **Skill 6** creates the GHL media folder, uploads, and builds the funnel/pages, and **Skill 44**
wires the bump order-form. It never hand-rolls an image call, a GHL REST call, ImgBB re-hosting, or a
mail sender.

> The frameworks captured in `MASTERDOC.md` are the Direct-Response IP. Every section count and word
> band below is machine-enforced by a fail-closed prover, never advisory. The provers measure STRIPPED
> text and IGNORE any self-reported count.

## What this skill produces / owns

- `MASTERDOC.md` — the anonymized Direct-Response IP (8-section main, 9-section upsell, downsell,
  Sovereign Architect high-ticket, bump, image-slice map, the two-track deliverable, the labeling grammar).
- `SALESPAGE-MANIFEST.json` — the P0..P9 phase spine (produces_artifact + `_chk_sp_*` wrappers), the
  `AF-SP56-*` autofail codes (trigger / enforced_by / py_symbol), and the front-door/delegation contract.
- `intake/spa-intake.schema.json` — the fleet-clean 12-field intake contract (legacy embedded-space keys repaired).
- `structure/sales_page_structure.json` — the canonical section/band definitions the provers load.
- `structure/labeling-grammar.json` — the `<client>__<funnel>__<stage>__<type>__vNN<variant>` grammar (56 OWNS it).
- `templates/funnel-manifest.schema.json` — the Track-2 build-bundle handoff contract Skill 6 reads.
- `prompts/` — the BAKED, provider-agnostic copy + image prompts (all 14 legacy prompts neutralized:
  zero Anthropic ids, credential seams -> env placeholders, prior-client content generalized).
- `scripts/prove_sp_*.py` — the eight fail-closed deterministic provers (stdlib only; exit 0/2/3).
- `run_sales_page_assets.py` — the no-skip orchestrator state machine.
- `sales-page-assets-entry.sh` — the canonical fail-closed front door.
- `verify.sh` — the read-only self-verification gate.

## The frameworks in one screen (machine-gated)

| Asset | Framework | Prover | Band / rule |
|---|---|---|---|
| Main page A/B | Advanced Sales Page Creation Instructions | `prove_sp_main_structure.py` | 8 sections in order, both variants, countdown timer |
| Upsell A/B | Trevor Otts 9-Section Framework | `prove_sp_upsell_structure.py` | 9 sections in exact order, both variants |
| Downsell | post-rejection emotional-recovery page | (9-section reuse) | graceful-concession frame |
| High-ticket | The Sovereign Architect (~22 sections) | `prove_sp_highticket_band.py` | 6,500-7,100 stripped words |
| Bump copy | order-bump / bump-sale | `prove_sp_bump_band.py` | 40-80 body words + `[X] Yes, add this to my order` close |
| Image plan | N prompts, slice map | `prove_sp_image_plan.py` | every stage slice non-empty (default N>=12) |
| Build bundle | Skill 6 funnel-manifest | `prove_sp_bundle.py` | labels parse the grammar; ZHC; SEO; thank-you; bump->Skill 44 |

Main-8: header (notification banner) -> hero -> problem/solution -> benefits -> product-details ->
credibility -> final-cta -> footer. Upsell-9 (Trevor Otts): hook (acknowledge purchase) -> pain-1 ->
pain-2 -> pain-3 -> hope -> solution -> value-stack -> logical-justification (founder credibility) ->
identity-challenge close.

## How it runs — THROUGH the canonical front door only

```
bash 56-sales-page-assets/sales-page-assets-entry.sh --run-dir <RUN_DIR>
```

The entry shell runs five fail-closed guards (deps -> version -> hash-pin -> bypass-scan -> run-scoped
0600 nonce), then hands the nonce to `run_sales_page_assets.py`, the deterministic no-skip state machine:

```
P0 Intake       -> prove_sp_intake.py          (locked 12-field brief)
P1 Image plan   -> prove_sp_image_plan.py       (N prompts; every stage slice non-empty)
P2 Images       -> Skill 47 kie_image.py / client image provider
P3 Copy x7      -> prove_sp_main_structure.py + prove_sp_upsell_structure.py
                   + prove_sp_highticket_band.py + prove_sp_bump_band.py   (the copy suite)
P4 Media        -> Skill 6 ghl_media.py          (media folder + upload; ImgBB removed)
P5 Fragments    -> deterministic sanitize/fragment-ize (NOT an LLM pass)
P6 Docs         -> Track 1 client-editable Google Docs (client Drive folder)
P7 Bundle       -> prove_sp_bundle.py            (Track 2 build bundle + funnel-manifest)
P8 Deliver      -> email folder link (productionized subject)
P9 Handoff      -> Skill 6 ghl_rest_canvas.py build (+ Skill 44 bump seam) -> signed PROCESS-CERTIFICATE
```

A failing gate aborts the run and **no certificate is written** — an incomplete or non-compliant asset
stack can never reach Complete. Writing your own per-run driver (a hand-rolled GHL REST call, an ImgBB
upload, a raw image createTask, a mail sender, an `api.anthropic.com` call) is the ungoverned path and is
refused by the entry shell's bypass-scan (`AF-SP56-CANONICAL-BYPASS`). A direct
`python3 run_sales_page_assets.py` without the front-door nonce dies `AF-SP56-FRONT-DOOR`.

## Fail-closed provers (exit 0 pass / 2 violation / 3 fail-closed)

- **`prove_sp_intake.py`** — funnel_type, the 12 required answers, image_prompt_count 1-20, offer ledger,
  client/funnel kebab slugs, brief locked.
- **`prove_sp_image_plan.py`** — contiguous prompt set; every stage (main/upsell-1/downsell-1/high-ticket)
  gets >= 1 image (closes the legacy default-4 slice bug).
- **`prove_sp_main_structure.py`** — the 8-section main structure in order, both A/B variants, countdown timer.
- **`prove_sp_upsell_structure.py`** — the 9-section Trevor Otts upsell in exact order, both A/B variants.
- **`prove_sp_highticket_band.py`** — the Sovereign Architect 6,500-7,100 stripped-word band.
- **`prove_sp_bump_band.py`** — 40-80 body words ending with the checkbox close line.
- **`prove_sp_bundle.py`** — every asset key parses the grammar (no model names, R1); ZHC prefix; SEO block;
  fragment/method/copy-token per page; thank-you present; bump routes to the Skill 44 seam.
- **`prove_sp_cert.py`** — the signed PROCESS-CERTIFICATE: contiguous phase order, all pass, valid HMAC.

Each prover ships a `--self-test` with VALID + VIOLATION fixtures; run everything with `bash verify.sh`.

## Delegation seams (never forked)

- Images -> **Skill 47** `kie_image.py` OR the client's OWN image provider (the operator OpenAI Assistant / ImgBB account are NOT shipped).
- GHL media folder + upload -> **Skill 6** `ghl_media.py` (ImgBB removed from the client path).
- GHL funnel/step/page build + HTML injection -> **Skill 6** `ghl_rest_canvas.py` / `ghl_builder.py`.
- Bump order-bump element on a GHL order form -> **Skill 44** (grocery-shopping rule; P4->P5 board handoff).
- 10 promo emails -> the **Email Skill project** (post-downsell handoff, out of scope here).

## Two-track deliverable (the Skill 6 handoff)

- **Track 1 — client track:** the labeled Google Docs in the client's Drive folder (human-editable review copy).
- **Track 2 — build track:** the machine-consumable build bundle Skill 6 reads (`funnel-manifest.json` +
  `pages/*.fragment.html` + `copy/` + `images/` CDN map + `copy-tokens/`). If the client edits Track 1,
  the bundle is regenerated from the approved Docs (version bump, R2) before install.

## Discoverability, routing, and labeling

- **Routing (STEP-0):** a survey-triggered "sales page assets" / direct-response A/B stack request routes
  here through the shared **STEP-0 funnel-engine selector** in Skill 6
  (`06-ghl-install-pages/funnel-engines/registry.json`) — Skill 49 is the first registered engine; this
  skill registers the 2nd entry. Skill 6 remains the ONE GHL delivery rail.
- **Doors (roles):** funnel/marketing direct-response copy + funnel-builder roles, and the web-development
  deployment role riding Skill 6 (same three-department exposure pattern as Skill 49).
- **Shared procedure (56 OWNS it):** the `universal-sops/sales-page-craft/` SOP cluster (README +
  `SOP-SALESPAGE-01-DR-ASSET-STACK.md`) is the cross-department `universal-sops` face of this engine —
  the sibling of Skill 49's `universal-sops/funnel-craft/`. Skill 56 OWNS `sales-page-craft`, which
  EXTENDS `funnel-craft` for the common funnel build + certify steps (Skill 6 is the ONE delivery rail
  for both engines); it does not fork or duplicate the funnel-craft procedure.
- **Labeling grammar (56 OWNS it; reciprocal with Skill 49):** every asset is labeled
  `<client>__<funnel>__<stage>__<type>__vNN<variant>` (`stage` in {main, checkout, bump, upsell-1,
  downsell-1, upsell-2, downsell-2, high-ticket, thank-you}, `type` in {copy, page, img-NN, funnel,
  email-NN, brief, manifest, cert}). Model provenance lives in `funnel-manifest.json` metadata, never in a
  label (rule R1). Pinned in `MASTERDOC.md` §8 + `structure/labeling-grammar.json`.

## Client-provider rule (binding)

On a client box the skill uses the **client's own configured providers and keys** — never the operator's,
never Anthropic model ids. The legacy engine's Anthropic main-page leg is re-pointed to the client's own
provider; the six GPT-4.1 sanitizer passes + the missing bump clean pass are replaced by one deterministic
Python fragment-strip (the cheapest model is no model). A/B variants come from two client models OR two
persona prompts on one client model — never an Anthropic/Gemini split as in the legacy engine. The BAKED
prompts are provider-agnostic; the provers are deterministic and use no model at runtime, so this skill is
provider-neutral by construction. Per-box capability must be proven before fleet rollout.

## Prerequisites

- Skill 06 (GHL install pages) — the media + funnel/page build rail.
- Skill 47 (Kie image adapter) — `kie_image.py` (or the client's own image provider).
- Skill 44 (Convert & Flow operator) — the order-bump order-form seam.
