# SOP-FUNNEL-04: GHL MEDIA + FUNNEL BUILD (DELEGATED to the delivery rail named in the brief)

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Master authority:** `49-signature-funnel/MASTERDOC.md` §3 (3/5/7 matrix + branching) + §6 (delegation seams)
**Owning role:** Signature Funnel Specialist (authoring) → **the delivery rail named in `brief.delivery_rail` (delivery)**
**Stage:** P4-MEDIA · P5-HTML · P6-COMPOSE · P7-BUILD
**Produces:** hosted media + signed P4 receipts, HTML fragments, the built funnel + preview URLs + signed P7 receipts

---

## 0. WHY THIS SOP EXISTS

Skill 49 AUTHORS copy and images; it does NOT hand-roll GHL, and it does not import the code of any
other skill to do it. **The delivery rail named in the brief's `delivery_rail` field is the ONE delivery rail**
(a free string; Skill 49 never resolves it to code). Every media upload and every page/funnel build is
DELEGATED to it, and the rail PROVES each step by writing operator-key-signed receipt lines into the run
(`delegation_receipt.record`; shape `49-signature-funnel/schema/delivery-rail-receipt.schema.json`, id
`sf-delivery-rail-receipt/v1`). P4 and P7 do not pass on a missing, unsigned or forged receipt. A
hand-rolled GHL REST call is the ungoverned path and is refused (AF-FUN-CANONICAL-BYPASS).

## 1. P4 — MEDIA FOLDER + UPLOAD (the delivery rail's `P4-MEDIA` receipt)

The rail hosts every PNG (one media folder per funnel with per-page sub-folders) and records ONE signed
`P4-MEDIA` line per ledger image, carrying the `hosted_url` it produced (AF-FUN-DELEG-MEDIA when the ledger
URL differs). EVERY `<img>` URL in the media ledger MUST equal the hosted URL its receipt recorded
(AF-FUN-IMG-HOST at P9) — a raw Kie URL or a local path in a fragment fails the gate.

## 2. P5 — HTML FRAGMENT ASSEMBLY

Assemble one fragment-safe body per page (Main / Checkout / U1 / D1 / U2 / D2 / Thank-You). Fragments
respect the delivery rail's fragment + reachability invariants; images reference the hosted media URLs from P4.

## 3. P6 — 3/5/7 STEP GRAPH + BRANCHING

Compose the funnel per the chosen size (see the matrix). Branching (GHL one-click upsell): payment
captured ONCE at the order form; each downsell sits immediately after its upsell; an upsell's decline
falls through to its downsell, its accept jumps past it; **every path terminates at Thank-You** — nobody
ends a purchase on an offer page.

- **3-step:** Main → Upsell 1 → Thank-You.
- **5-step:** Main → Upsell 1 → Downsell 1 → Upsell 2 → Thank-You.
- **7-step:** Main → Checkout → Upsell 1 → Downsell 1 → Upsell 2 → Downsell 2 → Thank-You.

## 4. P7 — GHL FUNNEL/PAGE BUILD (the delivery rail's `P7-BUILD` receipts)

The rail builds the funnel + pages and injects the fragments, then records ONE signed `P7-BUILD` line per
page type (`preview_url`, `PASS`, `checks`, `dom_sha256`, `screenshot_sha256`). `prove_sf_build.py`
recomputes the score as 10 x passing / total from those lines; the build must clear the rail's fragment +
reachability invariants and the **funnel-build QC ≥ 8.5** gate before the pipeline advances
(AF-FUN-BUILD-QC-RECORD / AF-FUN-BUILD-PREVIEW-UNBOUND).

## 5. LABELING

Label every media object, fragment, and preview with the shared grammar
`<client>__<funnel>__<stage>__<type>__vNN` (stages: main / checkout / upsell1 / downsell1 / upsell2 /
downsell2 / thankyou; types: copy / prompt / image / html / preview). This is the reciprocal grammar
shared with Skill 56.

## 6. NO PUBLISH HERE

P7 ends at **preview URLs** — going live is an explicit human approval at P9 (see SOP-FUNNEL-05). The
build never auto-publishes.
