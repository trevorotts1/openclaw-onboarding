---
name: signature-funnel
description: Builds a Trevor Otts Signature Funnel — the SACRED 12-section Hero copy system, per-section long-form image prompts sized to the model's own character budget (95 to 100 percent of its maximum, never below 80 percent), GHL media + funnel build, and a configurable 3/5/7-step funnel (Main -> Checkout -> Upsell-1 -> Downsell-1 -> Upsell-2 -> Downsell-2 -> Thank-You with accept/decline branching). Gates the sacred method with fail-closed deterministic provers: the intake gate, the 12-section copy contract (per-section char/word bands, six page profiles), the image-prompt two-floor gate (length and structure), and a no-pitch (clean thank-you) + image-provenance gate. A canonical fail-closed entry (deps/version/dept-map/hash-pin/bypass-scan/operator key) drives a no-skip orchestrator that issues a signed PROCESS-CERTIFICATE only on all-phases-pass. Delegates image generation to Skill 66 (model policy) then Skill 74 (the one approved KIE transport) and the media hosting (P4) and funnel/page build (P7) to the delivery rail the brief names, which proves them with signed receipts. Client runtime uses the client's own providers, never Anthropic.
version: v2.1.56
---

# Signature Funnel (Skill 49)

## RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING

**READ THIS ENTIRE FILE BEFORE TOUCHING ANYTHING ELSE.**

Read this entire document from top to bottom before executing a single step.
Then read every SOP this skill declares, in full, in this order:
`universal-sops/funnel-craft/SOP-FUNNEL-01-INTAKE.md`,
`universal-sops/funnel-craft/SOP-FUNNEL-02-COPY.md`,
`universal-sops/funnel-craft/SOP-FUNNEL-03-PROMPTS-IMAGES.md`,
`universal-sops/funnel-craft/SOP-FUNNEL-04-BUILD.md`,
`universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md`.

The methodology + enforcement layer for the Trevor Otts **Signature Funnel** — the 12-section Hero
landing page plus its upsell / downsell / OTO2 chain and thank-you page, built as a configurable
3/5/7-step GHL funnel. This skill owns the **IP and the gates**; existing engines own execution:
**Skill 66** (model policy) then **Skill 74** (the one approved KIE transport) generate the images, and the
**delivery rail named in the brief** (`delivery_rail`) hosts the media and builds the funnel/pages, then signs
one receipt line per hosted image and per built page. It never hand-rolls a Kie call or a GHL REST call, and
it never imports or names the rail's code.

> The method captured in `MASTERDOC.md` is **SACRED** — never floored, reordered, or reinterpreted.
> Every band below is machine-enforced by a fail-closed prover, never advisory. The provers measure
> STRIPPED text and IGNORE any self-reported count.

## Reading rule (BINDING — applies before any step of this skill runs)

**READ EVERYTHING BEFORE YOU TOUCH ANYTHING.** Read this entire file from top to bottom before executing
a single step. This is the reading rule the whole skill family follows; it governs this
skill and every skill on its delivery path, and it is not optional.

**Read each declared dependency WHOLE.** Every file this skill names — `MASTERDOC.md`, the scripts in the
phase spine, `structure/funnel_structure.json`, `structure/page_types.json`, the SOPs in
`universal-sops/funnel-craft/` — must be read from top to bottom before you act on it. Read order is not
completeness: knowing WHICH file comes first is not knowing WHAT it says. A dependency you have not read
whole is a dependency you cannot claim to have followed.

**GREPPING IS NOT READING.** A search hit is a pointer, never knowledge: open the file and read it whole.
"No grepping allowed." (`50-email-engine/SOURCE-EMAIL-CORPUS.md:25`). Do not skim, do not read only the
lines a search returned, and never act on a file you have not read end to end. If you catch yourself
searching for the answer instead of reading the source, stop and read the source.

## What this skill produces / owns

- `MASTERDOC.md` — the anonymized canonical funnel IP (12 section names + bands, upsell/downsell/OTO2
  derivation, the Thank-You spec, the 3/5/7 matrix, the image band + Signature Grade Block).
- `FUNNEL-MANIFEST.json` — the P0..P10 phase spine (produces_artifact + `_chk_sf_*` wrappers), the 99
  `AF-FUN-*` autofail codes (trigger / enforced_by / py_symbol), and the front-door/delegation contract.
- `intake/sf-intake-questions.json` — the Q1–Q17 intake spec + the runtime brief contract.
- `structure/funnel_structure.json` — the SACRED 12-section contract the copy prover loads.
- `prompts/funnel-copy-prompts.md` — the BAKED, provider-agnostic copy + image prompts (client models
  at runtime, never Anthropic).
- `scripts/prove_sf_intake.py`, `prove_sf_copy.py`, `prove_sf_prompt_floor.py`, `prove_sf_graph.py`,
  `prove_sf_build.py`, `prove_sf_no_pitch.py`, `prove_sf_cert.py` — the seven fail-closed deterministic provers (stdlib only; exit 0/2/3).
- `scripts/kie74_receipt.py` — turns a Skill 74 result into run evidence and defines what the bypass scan allow-lists.
- `run_signature_funnel.py` — the no-skip orchestrator state machine.
- `scripts/legacy_downsell_images.py` — desktop wireframes, mobile wireframes and the visual mockup for EVERY page of a 3/5/7-step funnel (sales page, upsell, `upsell-2`, `downsell`, `downsell-2` in the 7-step, thank-you), run from the P1 copy ledger through Skill 71's own pipeline. Only the design-only checkout is left to `checkout_wrapper.py`, and the receipt says so. Launch mode has one downsell by design; its wrapper is `downsell_wrapper.py`.
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
microcopy; its wireframes and mockups come from `scripts/checkout_wrapper.py`, the design-only
checkout adapter over Skill 71's five-section checkout role spec). Derived pages exclude Sections 8–11 and replace Section 12 with the renumbered Section 8
("7 Reasons To Commit To Your ____ Future" for upsells; "When Time Runs Out" for downsells).

## How it runs — THROUGH the canonical front door only

```
bash 49-signature-funnel/signature-funnel-entry.sh --run-dir <RUN_DIR>
```

The entry shell runs its fail-closed guards (deps → version → dept-map → hash-pin → bypass-scan → model-tier),
then starts `run_signature_funnel.py`, the deterministic no-skip state machine. The certificate HMAC is keyed
by the operator key (ENF-16); a caller-supplied nonce is refused:

```
P0 Intake      -> prove_sf_intake.py         (locked brief)
P1 Copy        -> prove_sf_copy.py           (SACRED 12-section bands, all profiles; a page type the locked 3/5/7 size requires but the ledger lacks = AF-FUN-SECTION-MISSING)
P2 Prompts     -> prove_sf_prompt_floor.py   (two-floor gate; length budget per kie-common-rules rule 12)
P3 Images      -> Skill 66 policy -> Skill 74 transport (text-to-image default + reference_images hook;
                                              record each result with scripts/kie74_receipt.py)
P4 Media       -> delivery-rail receipt (P4)    (brief.delivery_rail signs one P4-MEDIA line per ledger image; the ledger URL must equal its hosted_url; AF-FUN-DELEG-MEDIA)
P5 HTML        -> per-page fragment assembly    (pages/<profile>.fragment.html per matrix page, PARSED for the profile's data-section markers: 12 main, 8 derived, TY-1..TY-3 thank-you; AF-FUN-HTML-FRAGMENT / AF-FUN-HTML-SECTIONS)
P6 Compose     -> prove_sf_graph.py              (funnel_graph.json vs MASTERDOC §3: nodes/branch/reachability)
P7 Build       -> delivery-rail receipt (P7)     (build_receipt.json: QC >= 8.5 + preview URL per page, read against the rail's signed P7-BUILD lines: see below; prove_sf_build.py)
                                                  FIRST: the visual gate (--visual-only): desktop wireframe + mobile wireframe + visual mockup + final mockups per page, else AF-FUN-VISUAL-PHASE
P8 Derive      -> derived_pages.json ledger      (U1/D1/U2/D2/TY derived-page set; AF-FUN-DERIVE-LEDGER)
P9 Certify     -> prove_sf_no_pitch.py + prove_sf_cert.py  (signed PROCESS-CERTIFICATE)
P10 Email      -> optional handoff to the Email Skill project (10 promo emails)
```

A failing gate aborts the run and **no certificate is written** — an incomplete or non-compliant funnel
can never reach Complete. Writing your own per-run driver (a hand-rolled GHL REST call, a mail sender, a
raw Kie `createTask`, a copied KIE client script) is the ungoverned path and is refused by the entry shell's bypass-scan
(`AF-FUN-CANONICAL-BYPASS`), as is any reference from this tree to a sibling skill it must not touch
(`front_door.FORBIDDEN_SIBLING_REFS`). A direct `python3 run_signature_funnel.py` without the operator key (or with
a caller-supplied nonce) dies `AF-FUN-FRONT-DOOR`.

## Wireframes and mockups for every page — a GATED PHASE, not a prose step

The visual stage is a mandatory step of the orchestrator and a named gate, so it can never be skipped
silently: `_run_visual_stage` invokes the tool, with `--out-dir <RUN_DIR>/page-images`, when the locked brief sets
`visual_stage` to `auto` or `required` (refusing with the exact command when `brief.visual` lacks `skill71_root`,
`brand_file` or `brand_owner`). It runs only AFTER P0, P1 and P2-PROMPTS have passed (it can spend with `--allow-paid`,
so never before the prompt gate), and P7-BUILD runs the standalone visual gate **first** — `python3 scripts/prove_sf_build.py
--visual-only --run-dir <RUN_DIR> --funnel-size <n>` — so a run with no visual set fails as
`AF-FUN-VISUAL-PHASE` before any FAB or QC seam is consulted.

Run the tool: `python3 scripts/legacy_downsell_images.py --ledger <RUN_DIR>/copy_ledger.json --skill71-root <71 dir> --brand-file <brand.json> --brand-owner <client> --out-dir <RUN_DIR>/page-images`. It draws only through Skill 71's one admission door, `scripts/run_governed_stage.py`, never the executor itself: the stage gate's `check` runs before every stage, a paid dispatch is refused when it fails, and a stub run on a run with no gate state is refused (`AF-71-UNGATED`) outside a test harness. So a real or placeholder draw needs the page's earlier stages (intake, copy, font-action-plan) closed by the gate-driven process first. It builds every page the funnel size carries (7-step: `main`, `upsell`, `downsell`, `upsell-2`, `downsell-2`, `thank-you`; 5-step: the same without `downsell-2`; 3-step: `main`, `upsell`, `thank-you`), plus the design-only `checkout` of a 7-step funnel when the owner stages the approved five-section checkout manuscript with `--checkout-manuscript <file>` (the legacy copy ledger has no checkout copy, so without it the receipt lists `checkout` as not built and names the flag; the real order form stays the native Skill 06 form). The provider DEFAULTS to `kie` and needs `--allow-paid`; the offline `stub` is opt-in only and needs the owner's approval as a Command Center record, `--stub-approved-by <approval id>` (kind `stub_render`, bound to the sha256 of the run's `copy_ledger.json`): the tool verifies it before anything is drawn and the receipt carries the verified record; free text is refused, and P7 verifies the record again (`AF-FUN-BUILD-VISUAL-STUB`). Each page is checked against `structure/page_types.json`; a page missing its images is refused. It writes `page-images-receipt.json`. Before each page is drawn it gives every section that `structure/funnel_structure.json` image_coverage requires an image for (main 6, 7, 11 and every upsell band among them) a slot in the page's own production request, renumbers the `IMG-NNN` ids in section order, and writes `desktop-wireframe/section-plan.json`, `desktop-wireframe/image-inventory.json` and `mobile-tablet/section-plan.json` from that request, so the P7 slot-set check (`AF-FUN-VISUAL-SLOTSET`) reads real files. The image inventory, generation, Design Board and final mockups stay client-gated downstream of it.

That `<RUN_DIR>/page-images` folder is the funnel's **visual direction**, and P7 refuses to clear without it: every page of the funnel size (the design-only `checkout` may be named in the receipt's `not_built` instead) needs its `desktop-wireframe`, `mobile-tablet`, `visual-mockup` **and `final-mockups`** `stage-executor-record.json` with images, matching the receipt's sha256 (`AF-FUN-BUILD-VISUAL`). `final-mockups` is drawn by the client-gated Skill 71 path after Design Board approval, not by this tool, and the build gate requires it. The exact commands, per page folder `<PAGE>` = `<RUN_DIR>/page-images/<slug>`: the client approves the page's Design Board with `python3 <71 dir>/scripts/design_board.py approve <PAGE> --by <client identity> --evidence <platform message record>`; then build the stage request (`python3 <71 dir>/scripts/build_production_request.py ... --stage final-mockups --out <PAGE>/production-request-final-mockups.json`, the same arguments as the earlier stage requests) and draw it with `python3 <71 dir>/scripts/run_governed_stage.py <PAGE> --request production-request-final-mockups.json --stage final-mockups --provider kie --allow-paid` (the executor refuses it until the board approval is recorded). Once that stage has closed for every page, run `python3 scripts/legacy_downsell_images.py --record-final-mockups --out-dir <RUN_DIR>/page-images`: it draws nothing and spends nothing, reads each page's closed `final-mockups/stage-executor-record.json`, merges `{record, sha256, images}` into `page-images-receipt.json`, and exits 2 naming any page without a record with images (the receipt is then left unchanged); it only verifies that the record exists in each page folder, it never draws. Without that merge the receipt carries no `final-mockups` sha256 and P7-BUILD refuses. A funnel with copy and prompt ledgers but no wireframes or mockups cannot be certified.

## What P7 reads: tool evidence, never the receipt's word

The copy ledger and `build_receipt.json` are written by the run's own agent, so `prove_sf_build.py` also reads what the tools wrote under the run dir (`--run-dir`, default the receipt's folder):

- `pages/<profile>.fragment.html` is parsed for the profile's `data-section` markers, in order, each around real text, plus a `data-page="<profile>"` (or `data-stage`) root marker. A fragment holding only `x` fails (`AF-FUN-HTML-SECTIONS`).
- `delegation_receipts.jsonl` holds the delivery rail's `P7-BUILD` lines: one per page type, each written by the rail through `delegation_receipt.record` and signed with the operator key (`preview_url`, `PASS`, `checks`, `dom_sha256`, `screenshot_sha256`; shape in `schema/delivery-rail-receipt.schema.json`, id `sf-delivery-rail-receipt/v1`). P7 requires them signed (`delegation_receipt.require_rail`: an absent, unsigned, forged, other-run or self-authored store fails) and recomputes the QC score as 10 x passing pages / total lines. A receipt that says `qc_score` 9.0 with no signed lines, a recomputed score under 8.5, or a receipt score above the recomputed one fails (`AF-FUN-BUILD-QC-RECORD`).
- Every receipt `preview_url` must be a URL a passing rail line recorded (`AF-FUN-BUILD-PREVIEW-UNBOUND`).
- The brief names the rail in its required `delivery_rail` field (a free string; Skill 49 never resolves it to code).

`prove_sf_build.write_valid_run_evidence(run_dir, size)` writes a passing set of all three for tests and the golden sample (the lines come from the provider stub, signed with a fixture operator key); it is a fixture, not a substitute for a real rail.

## Fail-closed provers (exit 0 pass / 2 violation / 3 fail-closed)

- **`prove_sf_intake.py`** — funnel_type, required answers (size-gated), size ∈ {3,5,7}, offer ledger,
  representation-never-assumed, truth gate, brief locked.
- **`prove_sf_copy.py`** — the SACRED 12-section contract across all six profiles; stripped char/word
  bands; the replacement Section 8 name + 7-item count; the Thank-You TY-1/TY-2/TY-3 bands; and
  page-set completeness: the ledger must carry every page type the locked funnel size requires
  (size from `--funnel-size`, else the brief.json beside the ledger; the checkout carries no ledger copy).
- **`prove_sf_build.py`** — the build receipt (QC >= 8.5, a preview URL per page, the full page set) read
  against the evidence above: parsed fragments, the QC recomputed from the delivery rail's signed P7
  receipts, and the wireframe + mockup set for every page.
- **`prove_sf_prompt_floor.py`** — stripped-length gate (the prompt length budget is `07-kie-setup/references/kie-common-rules.md` rule 12; `universal-sops/funnel-craft/SOP-FUNNEL-03-PROMPTS-IMAGES.md` states how the prover and `prompt-budget --check` combine) + distinct-word density + Signature
  Grade Block + negative block + em-dash ban + typography discipline.
- **`prove_sf_no_pitch.py`** — the thank-you page carries no offer name / price / sale CTA, and every
  image has a real Kie taskId and the hosted URL the delivery rail's signed P4 receipt recorded (fail-closed
  on empty offer ledger / no thank-you page / no images).
- **`prove_sf_cert.py`** — the signed PROCESS-CERTIFICATE: contiguous phase order, all pass, valid HMAC.

Each prover ships a `--self-test` with VALID + VIOLATION fixtures; run everything with `bash verify.sh`.

## Delegation seams (never forked)

- Images → **Skill 66** (policy: model, N43 ratio rules) then **Skill 74** `kie_live_adapter.py` (validate, preflight, prompt-budget, `submit --mode active`, save immediately; 16:9 and 3:4 slots; text-to-image default + a reference hook that
  uses the image field the live schema names).
- Media hosting (P4) and funnel/step/page build + HTML injection (P7) → the **delivery rail** named in
  `brief.delivery_rail`. Skill 49 does not call it: the rail writes signed receipts into the run
  (`delegation_receipt.record`, schema `schema/delivery-rail-receipt.schema.json`) and P4 and P7 certify only on
  them (`delegation_receipt.require_rail`).
- 10 promo emails → the **Email Skill project** (post-downsell handoff, P10).

## Thank-you fulfillment map (bound before replay)

`scripts/translate_thank_you_result.py` binds the S44/F03/F05 fulfillment map to the
purchase before Skill 82's validators see it: `manifest.provenance.map_sha256` must
equal the map's current bytes, the map must carry a version plus this purchase's
tenant/launch/revision, and every entitlement it names must be one the purchase paid
for. Only then is the entitlement-keyed mapping passed into `validate_thank_you`, which
restores the exact paid+granted equality. A map supplied without a digest is recorded
as unbound; a bound map that is stale, foreign or names an unpurchased entitlement is
refused by name. A thank-you visit is never fulfillment evidence.

## KIE image route (the only approved path)

Every image request in a run follows `universal-sops/funnel-craft/SOP-FUNNEL-03-PROMPTS-IMAGES.md` section 3:
Skill 66 picks the model (GPT Image default = newest generation via `latest-family`, N43 ratio rules), then
Skill 74 runs `validate`, `preflight` (price x 1.30), `prompt-budget --check`, `submit --mode active`, `wait`
and `save` immediately. After each success, `python3 scripts/kie74_receipt.py --run-dir <RUN_DIR> --phase
P3-IMAGES --result <result.json>` stores the adapter result under `<RUN_DIR>/receipts/kie74/` and appends the
provider receipt. The entry shell's bypass scan allow-lists exactly those files; a hand-written createTask,
a copied adapter or an old KIE client script anywhere else in the run dir is `AF-FUN-CANONICAL-BYPASS`.
No price, model id, endpoint or rate figure is written in this skill (rules 2, 3, 7, 10): ask Skill 74.

## Discoverability, routing, and labeling

- **Routing:** a signature funnel request routes here through the department map intent triggers
  (`repo-integration/skill-department-map-entry.json`, mirrored by the `signature-funnel` row of
  `23-ai-workforce-blueprint/skill-department-map.json`). The front door refuses when that row is missing
  (`front_door.step_departmap`), so this skill is routable without any sibling skill's registry.
- **Doors (roles):** the web-development and marketing **Signature Funnel Specialist** roles, plus
  Section-8 tool rows on the funnel-strategist / funnel-builder / landing-page specialists. The five
  SOPs (read every one in full): `universal-sops/funnel-craft/SOP-FUNNEL-01-INTAKE.md`,
  `universal-sops/funnel-craft/SOP-FUNNEL-02-COPY.md`,
  `universal-sops/funnel-craft/SOP-FUNNEL-03-PROMPTS-IMAGES.md`,
  `universal-sops/funnel-craft/SOP-FUNNEL-04-BUILD.md`,
  `universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md`.
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
  It uses the SAME delivery-rail receipt contract and the SAME labeling
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
- A delivery rail, named in the brief, that hosts the media and builds the funnel/pages and signs the P4/P7
  receipts (`schema/delivery-rail-receipt.schema.json`).
- Skill 66 (KIE image policy) and Skill 74 (KIE live adapter) — the only approved KIE path.
