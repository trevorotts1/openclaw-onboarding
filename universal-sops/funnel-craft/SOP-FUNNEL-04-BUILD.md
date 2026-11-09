# SOP-FUNNEL-04: GHL MEDIA + FUNNEL BUILD (DELEGATED to Skill 6)

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Canonical GHL operations cluster:** cross-craft GHL procedures (meeting rooms, native AI, knowledge bases, widgets, Projects sync, workflow monitoring, marketing quizzes) live in the single `universal-sops/ghl-hybrid-operations/` cluster (its README is the index). This SOP is not duplicated there; do not fork a second `ghl-operations/` cluster.
**Master authority:** `49-signature-funnel/MASTERDOC.md` §3 (3/5/7 matrix + branching) + §6 (delegation seams)
**Owning role:** Signature Funnel Specialist (authoring) → **Skill 6 (delivery)**
**Stage:** P4-MEDIA · P5-HTML · P6-COMPOSE · P7-BUILD
**Produces:** GHL media folder + uploads, HTML fragments, the built funnel + preview URLs

---

## 0. WHY THIS SOP EXISTS

Skill 49 AUTHORS copy and images; it does NOT hand-roll GHL. **Skill 6 is the ONE GHL construction
rail.** Every page/funnel build and every visual authoring step is DELEGATED. Hand-rolled HTTP — a
call that does not go through the shared adapter and its registry row — is the ungoverned path and is
refused (AF-FUN-CANONICAL-BYPASS).

## 0A. PUBLIC OPERATIONS VERSUS VISUAL CONSTRUCTION

Select each step from its registry row (`44-convert-and-flow-operator/tools/engine/cli_anything/
gohighlevel/public/operations.py`) and the per-`(operation_id, tenant)` capability record:

| Step | Registry row | Class | Rule |
|---|---|---|---|
| Inventory funnels / pages / page count | `funnels.list`, `funnels.pages.list`, `funnels.pages.count` | `public_direct` | Use the governed read; a successful read proves the read only. |
| Create a redirect | `funnels.redirects.create` | `public_direct` | Governed write, issued through the shared adapter with a receipt. |
| Upload media / create media folder | `media.upload`, `media.folders.create` | `public_direct` | Governed writes; availability stays per-location evidence. |
| Build the funnel / steps / page canvas | `funnels.create`, `funnels.steps.create`, `funnels.pages.get`, `funnels.pages.autosave`, `funnels.pages.authoring` | `skill44_private` / `skill06_authoring` | Visual construction stays with Skill 6, exactly as this SOP already requires. |

Public inventory, redirect, and media operations are **not** a second construction rail: they never
replace Skill 6's page/funnel build, and they never authorize a competing builder. If a needed row is
`capability_gap`, report the gap rather than fabricating the step.

## 1. P4 — MEDIA FOLDER + UPLOAD (Skill 6 `ghl_media.py`)

One media folder per funnel with per-page sub-folders (`ensure_funnel_media_folders`), then
`upload_media` for every PNG. After upload, EVERY `<img>` in a page fragment MUST resolve to the GHL
media host (AF-FUN-IMG-HOST) — a raw Kie URL or a local path in a fragment fails the gate.

## 2. P5 — HTML FRAGMENT ASSEMBLY

Assemble one fragment-safe body per page (Main / Checkout / U1 / D1 / U2 / D2 / Thank-You). Fragments
respect the Skill-6 fragment + reachability invariants; images reference the GHL media URLs from P4.

## 3. P6 — 3/5/7 STEP GRAPH + BRANCHING

Compose the funnel per the chosen size (see the matrix). Branching (GHL one-click upsell): payment
captured ONCE at the order form; each downsell sits immediately after its upsell; an upsell's decline
falls through to its downsell, its accept jumps past it; **every path terminates at Thank-You** — nobody
ends a purchase on an offer page.

- **3-step:** Main → Upsell 1 → Thank-You.
- **5-step:** Main → Upsell 1 → Downsell 1 → Upsell 2 → Thank-You.
- **7-step:** Main → Checkout → Upsell 1 → Downsell 1 → Upsell 2 → Downsell 2 → Thank-You.

## 4. P7 — GHL FUNNEL/PAGE BUILD (Skill 6 `ghl_rest_canvas.py` / `ghl_builder.py`)

Build the funnel + pages and inject the fragments through Skill 6. The build must clear Skill 6's
fragment + reachability invariants and the **funnel-build QC ≥ 8.5** gate before the pipeline advances.

**Route receipts.** Emit one logical operation receipt per governed operation (stable key
`(company_id, location_id, run_id, operation_key)`, the actual selected route, a readback state, and
any attempts). Native full-width verification and the existing rendered-`<img>`/reachability gates stay
unchanged; the receipt records that they ran, it does not replace them.

## 5. LABELING

Label every media object, fragment, and preview with the shared grammar
`<client>__<funnel>__<stage>__<type>__vNN` (stages: main / checkout / upsell1 / downsell1 / upsell2 /
downsell2 / thankyou; types: copy / prompt / image / html / preview). This is the reciprocal grammar
shared with Skill 56.

## 6. NO PUBLISH HERE

P7 ends at **preview URLs** — going live is an explicit human approval at P9 (see SOP-FUNNEL-05). The
build never auto-publishes.
