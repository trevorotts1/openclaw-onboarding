---
name: signature-funnel
description: Builds a Trevor Otts Signature Funnel — the SACRED 12-section Hero copy system, per-section 5,000-19,000-char gpt-image-2 prompts, GHL media + funnel build, and a configurable 3/5/7-step funnel (Main -> Checkout -> Upsell-1 -> Downsell-1 -> Upsell-2 -> Downsell-2 -> Thank-You with accept/decline branching). Gates the sacred method with fail-closed deterministic provers: the intake gate, the 12-section copy contract (per-section char/word bands, six page profiles), the 5,000-19,000-char image-prompt two-floor gate, and a no-pitch (clean thank-you) + image-provenance gate. A canonical fail-closed entry (deps/bypass-scan/hash-pin/0600-nonce) drives a no-skip orchestrator that issues a signed PROCESS-CERTIFICATE only on all-phases-pass. Delegates image generation to Skill 47 (kie_image.py) and ALL GHL media + build to Skill 6. Client runtime uses the client's own providers, never Anthropic.
version: 1.2.0
---

# Signature Funnel (Skill 49)

The methodology + enforcement layer for the Trevor Otts **Signature Funnel** — the 12-section Hero
landing page plus its upsell / downsell / OTO2 chain and thank-you page, built as a configurable
3/5/7-step GHL funnel. This skill owns the **IP and the gates**; existing engines own execution:
**Skill 47** generates the images, **Skill 6** creates the GHL media folder, uploads, and builds the
funnel/pages. It never hand-rolls a Kie call or a GHL REST call.

> The method captured in `MASTERDOC.md` is **SACRED** — never floored, reordered, or reinterpreted.
> Every band below is machine-enforced by a fail-closed prover, never advisory. The provers measure
> STRIPPED text and IGNORE any self-reported count.

## What this skill produces / owns

- `MASTERDOC.md` — the anonymized canonical funnel IP (12 section names + bands, upsell/downsell/OTO2
  derivation, the Thank-You spec, the 3/5/7 matrix, the image band + Signature Grade Block).
- `FUNNEL-MANIFEST.json` — the P0..P10 phase spine (produces_artifact + `_chk_sf_*` wrappers), the 68
  `AF-FUN-*` autofail codes (trigger / enforced_by / py_symbol), and the front-door/delegation contract.
- `intake/sf-intake-questions.json` — the Q1–Q17 intake spec + the runtime brief contract.
- `structure/funnel_structure.json` — the SACRED 12-section contract the copy prover loads.
- `prompts/funnel-copy-prompts.md` — the BAKED, provider-agnostic copy + image prompts (client models
  at runtime, never Anthropic).
- `scripts/prove_sf_intake.py`, `prove_sf_copy.py`, `prove_sf_prompt_floor.py`, `prove_sf_no_pitch.py`,
  `prove_sf_cert.py` — the five fail-closed deterministic provers (stdlib only; exit 0/2/3).
- `run_signature_funnel.py` — the no-skip orchestrator state machine.
- `signature-funnel-entry.sh` — the canonical fail-closed front door.
- `verify.sh` — the read-only self-verification gate.

## The 12-section system in one screen (SACRED)

| Sec | Name | Band | Rule |
|---|---|---|---|
| 1 | The Big Bold Claim | 180–225 chars | product title present; labeled CTA |
| 2–4 | The Big Bold Pain 1/2/3 | 180–225 chars | 2nd person; NO questions; labeled CTA |
| 5 | The Big Bold Why | 18–30 words | starts "That's the reason why…"; CTA; write to the top of the band |
| 6 | The Big Bold Who | 18–30 words | 3–6 personas; **NO CTA**; write to the top of the band |
| 7 | The Big Bold What | 70–120 words | 5–10 bullets |
| 8–9 | The Big Bold Benefit 1/2 | 18–30 words | **NO CTA button**; write to the top of the band |
| 10 | The Big Bold Benefit 3 | 18–30 words | inspirational CTA button; write to the top of the band |
| 11 | The Big How To | 100–150 words; NO button | 5–10 steps; steps 1–6 89–116 chars; step 7 ≤170; share/email-bonus/founder-text/community steps |
| 12 | The Big Bold Heartfelt Message | 100–150 words | 6 labeled parts; part 2 starts "I used to be just like you…" |

Six page profiles: `main`, `upsell`, `downsell`, `upsell-2`, `downsell-2`, `thank-you` (+ `checkout`
microcopy). Derived pages exclude Sections 8–11 and replace Section 12 with the renumbered Section 8
("7 Reasons To Commit To Your ____ Future" for upsells; "When Time Runs Out" for downsells).

## How it runs — THROUGH the canonical front door only

```
bash 49-signature-funnel/signature-funnel-entry.sh --run-dir <RUN_DIR>
```

The entry shell runs five fail-closed guards (deps → version → hash-pin → bypass-scan → run-scoped
0600 nonce), then hands the nonce to `run_signature_funnel.py`, the deterministic no-skip state machine:

```
P0 Intake      -> prove_sf_intake.py         (locked brief)
P1 Copy        -> prove_sf_copy.py           (SACRED 12-section bands, all profiles)
P2 Prompts     -> prove_sf_prompt_floor.py   (5,000-19,000-char two-floor gate)
P3 Images      -> Skill 47 kie_image.py      (text-to-image default + reference_images hook)
P4 Media       -> Skill 6 ghl_media.py       (media folder + upload)
P5 HTML        -> per-page fragment assembly    (pages/<profile>.fragment.html per matrix page; AF-FUN-HTML-FRAGMENT)
P6 Compose     -> prove_sf_graph.py              (funnel_graph.json vs MASTERDOC §3: nodes/branch/reachability)
P7 Build       -> prove_sf_build.py              (build_receipt.json: QC >= 8.5 + preview URL per page)
P8 Derive      -> derived_pages.json ledger      (U1/D1/U2/D2/TY derived-page set; AF-FUN-DERIVE-LEDGER)
P9 Certify     -> prove_sf_no_pitch.py + prove_sf_cert.py  (signed PROCESS-CERTIFICATE)
P10 Email      -> optional handoff to the Email Skill project (10 promo emails)
```

A failing gate aborts the run and **no certificate is written** — an incomplete or non-compliant funnel
can never reach Complete. Writing your own per-run driver (a hand-rolled GHL REST call, a mail sender, a
raw Kie `createTask`) is the ungoverned path and is refused by the entry shell's bypass-scan
(`AF-FUN-CANONICAL-BYPASS`). A direct `python3 run_signature_funnel.py` without the front-door nonce dies
`AF-FUN-FRONT-DOOR`.

## Fail-closed provers (exit 0 pass / 2 violation / 3 fail-closed)

- **`prove_sf_intake.py`** — funnel_type, required answers (size-gated), size ∈ {3,5,7}, offer ledger,
  representation-never-assumed, truth gate, brief locked.
- **`prove_sf_copy.py`** — the SACRED 12-section contract across all six profiles; stripped char/word
  bands; the replacement Section 8 name + 7-item count; the Thank-You TY-1/TY-2/TY-3 bands.
- **`prove_sf_prompt_floor.py`** — 5,000–19,000 stripped chars + distinct-word density + Signature
  Grade Block + negative block + em-dash ban + typography discipline.
- **`prove_sf_no_pitch.py`** — the thank-you page carries no offer name / price / sale CTA, and every
  image has a real Kie taskId resolving to a GHL media host (fail-closed on empty offer ledger / no
  thank-you page / no images).
- **`prove_sf_cert.py`** — the signed PROCESS-CERTIFICATE: contiguous phase order, all pass, valid HMAC.

Each prover ships a `--self-test` with VALID + VIOLATION fixtures; run everything with `bash verify.sh`.

## Delegation seams (never forked)

- Images → **Skill 47** `kie_image.py` (16:9 & 2K defaults; text-to-image default + `image_input`
  reference hook).
- GHL media folder + upload → **Skill 6** `ghl_media.py`.
- GHL funnel/step/page build + HTML injection → **Skill 6** `ghl_rest_canvas.py` / `ghl_builder.py`.
- 10 promo emails → the **Email Skill project** (post-downsell handoff, P10).

## Discoverability, routing, and labeling

- **Routing (STEP-0):** a "signature funnel" / "signature landing page" request routes here through the
  shared **STEP-0 funnel-engine selector** in Skill 6 — `06-ghl-install-pages/funnel-engines/registry.json`
  (this skill is the first registered engine) + `tools/funnel_engine_selector.py`. `NO_ENGINE_MATCH`
  falls through to the template-first funnel matcher. Skill 56 (Sales-Page-Assets) is the 2nd
  registered entry (the Direct-Response sibling). Skill 6 remains the ONE GHL delivery rail.
- **Doors (roles):** the web-development and marketing **Signature Funnel Specialist** roles, plus
  Section-8 tool rows on the funnel-strategist / funnel-builder / landing-page specialists. Shared
  procedure cluster: `universal-sops/funnel-craft/`.
- **Deliverable labeling grammar (reciprocal with Skill 56):** every copy doc / prompt / PNG / HTML
  fragment / preview is labeled `<client>__<funnel>__<stage>__<type>__vNN`
  (`stage ∈ {main,checkout,upsell1,downsell1,upsell2,downsell2,thankyou}`,
  `type ∈ {copy,prompt,image,html,preview}`). Pinned in `MASTERDOC.md` §8; **Skill 56 has landed** and
  now OWNS the shared grammar, adopting this identical field order and extending the `stage`/`type` enums
  (see `MASTERDOC.md` §8).
- **Direct-Response sibling (Skill 56):** `56-sales-page-assets/` is the live **Direct-Response sibling**
  of this skill — the DR sales-page / VSL asset stack (8-section main A/B + countdown, the 9-section
  upsell, the downsell, the Sovereign Architect high-ticket long-form, the bump copy, and the
  slice-covered image plan), with its own eight fail-closed model-free provers and its own P0..P9 spine.
  It rides the SAME STEP-0 selector, the SAME ONE GHL delivery rail (Skill 6), and the SAME labeling
  grammar (56 OWNS it); its `universal-sops/sales-page-craft/` cluster EXTENDS this skill's
  `universal-sops/funnel-craft/` without forking it. Route a SACRED 12-section funnel here; route a
  direct-response A/B sales-page stack to Skill 56 — do NOT drive the DR stack through the Skill-49
  provers.

## Client-provider rule (binding)

On a client box the skill uses the **client's own configured providers and keys** — never the
operator's, never Anthropic model ids. The BAKED prompts are provider-agnostic; the runtime tiers the
client's own chain (strongest → copy + QC verify; mid → image prompts / HTML / JSON; cheapest →
catalog / poll). The provers are deterministic and use no model at runtime, so this skill is
provider-neutral by construction.

## Prerequisites

- Skill 07 (Kie.ai setup) — the render provider for the image step.
- Skill 06 (GHL install pages) — the media + funnel/page build rail.
- Skill 47 (Kie image adapter) — `kie_image.py`.
