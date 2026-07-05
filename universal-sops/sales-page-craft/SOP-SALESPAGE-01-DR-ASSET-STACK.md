# SOP-SALESPAGE-01: BUILD THE DIRECT-RESPONSE SALES PAGE ASSET STACK

**Cluster:** Sales-Page-Craft Rules (`universal-sops/sales-page-craft/`) — EXTENDS `universal-sops/funnel-craft/` (Skill 49) for the common build + certify steps
**Master authority:** `56-sales-page-assets/SALESPAGE-MANIFEST.json` (phase spine + the `autofail_codes` table) + `56-sales-page-assets/MASTERDOC.md` (the SACRED Direct-Response IP)
**Owning department:** Web Development (delivery door) + Marketing (offer/campaign door)
**Owning roles:** Sales Page Assets Specialist (web-development drives the entry; marketing frames the offer + follow-up), routed by the STEP-0 funnel-engine selector as the SECOND registered engine
**Canonical entry:** `56-sales-page-assets/sales-page-assets-entry.sh`
**Stages:** P0-INTAKE -> P1-IMAGE-PLAN -> P2-IMAGES -> P3-COPY(x7) -> P4-MEDIA -> P5-FRAGMENTS -> P6-DOCS -> P7-BUNDLE -> P8-DELIVER -> P9-HANDOFF
**Gates this SOP satisfies:** AF-SP56-INTAKE-*, AF-SP56-IMGPLAN-*, AF-SP56-MAIN-*, AF-SP56-UPSELL-*, AF-SP56-HIGHTICKET-*, AF-SP56-BUMP-*, AF-SP56-BUNDLE-*, AF-SP56-CERT-*, AF-SP56-FRONT-DOOR, AF-SP56-CANONICAL-BYPASS, AF-SP56-HASH-PIN, AF-SP56-PROCESS-INTEGRITY

---

## 0. WHAT THIS ARTIFACT IS

The Direct-Response **Sales Page Asset Stack** is the Trevor Otts DR funnel copy + image family — the
sibling of the SACRED 12-section Signature Funnel (Skill 49). From one "Ultimate AI Sales Page Writer"
survey it produces seven copy assets + a slice-covered image plan:

1. **Main page A/B** — the 8-section main sales page (header/notification-banner -> hero ->
   problem/solution -> benefits -> product-details -> credibility -> final-cta -> footer), both variants,
   each with a countdown timer.
2. **Upsell A/B** — the Trevor Otts 9-section upsell (hook -> pain-1 -> pain-2 -> pain-3 -> hope ->
   solution -> value-stack -> logical-justification -> identity-challenge close), both variants.
3. **Downsell** — a post-rejection emotional-recovery page (graceful-concession frame, 9-section reuse).
4. **High-ticket** — the Sovereign Architect long-form page, **6,500–7,100 stripped words**.
5. **Order-bump** — **40–80 body words** ending `[X] Yes, add this to my order`.
6. **Image plan** — N prompts (default >= 12) with every stage slice non-empty.

Both tracks ship: Track 1 (client-editable Google Docs in the client Drive folder) and Track 2 (the
Skill-6 build bundle: `funnel-manifest.json` + `pages/*.fragment.html` + `copy/` + `images/` CDN map +
`copy-tokens/`), plus a signed `PROCESS-CERTIFICATE.json`. GHL build + preview is Skill 6's; the bump is
Skill 44's.

## 1. WHEN TO BUILD IT

Build it when a client needs the Direct-Response asset stack for one offer — a "sales page assets" /
"direct-response sales page" / VSL / upsell-downsell A/B request. If the request is for the SACRED
12-section signature funnel ("signature funnel" / "signature landing page"), that is **Skill 49
(Signature Funnel)**, not this skill. Routing disambiguation (STEP-0 selector `anti_signals`): a
direct-response 8-section main / order-bump / high-ticket stack -> Skill 56; a 12-section Hero signature
funnel -> Skill 49. The two are siblings on one delivery rail (Skill 6) and one labeling grammar (56
owns it), and are NEVER merged.

## 2. THE 12-FIELD INTAKE (P0, one block, turn-gated)

Ask the "Ultimate AI Sales Page Writer" intake in a SINGLE message, never one-question-per-turn. Capture
the offer ledger (offer name(s)), the `image_prompt_count` (int in 1–20), the client/funnel kebab slugs,
and the required answers, then LOCK `brief.json`. Never fabricate an intake answer — client words only;
return the gap list and STOP if a required field is missing. A self-attested "intake complete" flag is
never trusted: `prove_sp_intake.py` reads the actual fields (any missing / empty required field =
`AF-SP56-INTAKE-MISSING`; a non-kebab slug = `AF-SP56-INTAKE-SLUG`; an unlocked brief =
`AF-SP56-INTAKE-UNLOCKED`).

## 3. THE GATE CONTRACT (P1–P9 — enforcement, not description)

Every stage is deterministic and fail-closed. A violating artifact is NOT built, NOT delivered, NOT
certified. Bands are MEASURED on the STRIPPED text; a model's self-reported count is never trusted.

### Step 0 — Copywriter-persona grounding (MANDATORY, fail-closed — FIX-XC-02a)

Before any asset copy is written: select the copy persona against the CLIENT's providers with
`python3 23-ai-workforce-blueprint/scripts/persona-selector-v2.py --task "<asset> sales-page <ICP>" --department marketing`,
log `selected_persona: <registered-slug>` + `selector_ran: true` to `persona-selection-log.md` in the
run dir, and load the matched persona-blueprint's **Section 4 "Agent Governance Framework"** via the
seam in `56-sales-page-assets/prompts/PROMPT-SEAMS.md` (`{{PERSONA_TASK_MODE}}` / `{{SELECTED_PERSONA_ID}}`).
`prove_sp_intake.py` fails closed with **AF-SP56-INTAKE-PERSONA-LOG** when the log is absent or names no
registered slug (mirrors FAB-QC D4) — no grounding, no generation.

| Stage | Gate | Rule |
|---|---|---|
| P0-INTAKE | `AF-SP56-INTAKE-PERSONA-LOG` | persona-selection-log present in the run dir AND names a registered persona slug (copywriter-persona Step-0 grounding). Fail-closed. |
| P1-IMAGE-PLAN | `AF-SP56-IMGPLAN-SLICE-EMPTY` | every stage (main / upsell-1 / downsell-1 / high-ticket) has >= 1 image (closes the legacy default-4 bug); contiguous prompt indices; no empty prompt text. |
| P3-COPY | `AF-SP56-MAIN-SECTION-*` / `AF-SP56-MAIN-NO-COUNTDOWN` | the 8-section main present + IN ORDER, both A/B variants, each with a countdown timer. |
| P3-COPY | `AF-SP56-UPSELL-SECTION-*` | the 9-section Trevor Otts upsell present + IN the exact order, both A/B variants. |
| P3-COPY | `AF-SP56-HIGHTICKET-FLOOR` / `-CEILING` | high-ticket measured stripped word count within 6,500–7,100. |
| P3-COPY | `AF-SP56-BUMP-FLOOR` / `-CEILING` / `-NO-CHECKBOX` | bump 40–80 body words ending with the `[X] Yes, add this to my order` checkbox close. |
| P4-MEDIA | `AF-SP56-BUNDLE-*` (host) | images on the GHL media host (delegated to Skill 6 `ghl_media.py`; ImgBB removed from the client path). |
| P7-BUNDLE | `AF-SP56-BUNDLE-LABEL-GRAMMAR` | every asset key / run_id parses the grammar and carries NO model name (rule R1). |
| P7-BUNDLE | `AF-SP56-BUNDLE-ZHC` / `-FRAGMENT` / `-METHOD` / `-COPYTOKENS` / `-SEO` / `-THANKYOU` | ZHC UPPERCASE container prefix; per-page fragment + method + copy-tokens; SEO block complete; thank-you step present. |
| P7-BUNDLE | `AF-SP56-BUNDLE-BUMP-ROUTE` | the bump routes to the Skill 44 seam as COPY (route `SKILL44_WIDGET`), never hand-wired. |
| P9 / run | `AF-SP56-CERT-PHASE-GAP` / `AF-SP56-PROCESS-INTEGRITY` | a signed certificate requires a full P0->P9 pass, no phase skips, valid HMAC. |
| entry | `AF-SP56-CANONICAL-BYPASS` / `AF-SP56-FRONT-DOOR` / `AF-SP56-HASH-PIN` | no hand-rolled GHL REST / ImgBB / raw image createTask / mail sender in the run dir; the enforcement core matches its pinned head; the orchestrator refuses without the front-door nonce. |
| entry | `AF-SP56-MODEL-TIER` / `AF-SP56-MODEL-NOANTHROPIC` | the entry shell resolves the CLIENT's own execution-tier authoring model (role=content), records `routing/model-content-receipt.json`, and `prove_sp_cert.py --model-receipt` gates it fail-closed — execution/content tier required, Anthropic hard-banned by provider field (FIX-XC-09e). |

**Rework loop:** a QC failure returns the exact `AF-SP56-*` code; a bounded re-author loop (verifier !=
author) re-authors then re-proves the WHOLE affected asset. The ONLY deterministic repair is the P5
fragment-strip (sanitize/fragment-ize, not an LLM pass). After the bounded attempts, hard-escalate to the
operator — never silent-pass, never floor/cap a band to make a gate green.

## 4. RUN IT — THROUGH THE ONE ENTRY

```
bash 56-sales-page-assets/sales-page-assets-entry.sh --run-dir <RUN_DIR>
```

The entry runs five fail-closed guards (DEPS -> VERSION -> HASH-PIN -> BYPASS-SCAN -> run-scoped 0600
nonce) and dispatches `run_sales_page_assets.py`, which walks P0 -> P9 with no phase skips. Writing and
running a hand-rolled GHL REST call, an ImgBB re-host, a raw image `createTask`, or a mail sender in the
run dir is the ungoverned path and is FORBIDDEN (`AF-SP56-CANONICAL-BYPASS`). A `python3
run_sales_page_assets.py` without the front-door nonce dies `AF-SP56-FRONT-DOOR`.

## 5. DELIVER (P6 + P8 + P9)

Track 1 is the labeled Google Docs (7 copy assets) in the client's Drive folder for human review/edit; if
the client edits Track 1, the Track-2 bundle is regenerated from the approved Docs (version bump) before
install. Track 2 is the Skill-6 build bundle. P8 sends the folder link with the productionized subject
"Your <funnel> sales page assets are ready". P9 hands off to Skill 6 (`ghl_rest_canvas.py` /
`ghl_builder.py`) for the GHL funnel/page build (+ the Skill 44 bump order-form seam), confirms
funnel-build QC >= 8.5, and mints the signed `PROCESS-CERTIFICATE.json`. Publish only after EXPLICIT
HUMAN APPROVAL. **No signed certificate = not done.**

## 6. VERIFY BEFORE CLAIMING DONE

End-to-end proof is from the CLIENT outcome, not the builder's claim: the preview URLs load, the images
are on the GHL media host, the bump renders on the order form (via Skill 44), and the certificate chain is
intact. Self-verify the skill with:

```
bash 56-sales-page-assets/verify.sh
```

It runs each prover's `--self-test`, reproduces the golden `golden-momentum` bundle, proves every broken
variant is rejected with its distinct `AF-SP56-*` code, checks the provider-purity + secret scans, and
re-verifies the signed certificate — idempotent and read-only. Any nonzero exit = fix the INPUT and
re-run; never guess a missing field, never floor/cap a band, never author around a prover.
