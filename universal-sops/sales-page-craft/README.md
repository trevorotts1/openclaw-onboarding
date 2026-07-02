# Sales-Page-Craft SOP Cluster (`universal-sops/sales-page-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Sales Page
Assets engine (Skill 56)** — the Direct-Response sibling of the Signature Funnel (Skill 49) — end to
end: 12-field intake -> image plan (slice-covered) -> the 7 copy assets (8-section main A/B + countdown,
Trevor Otts 9-section upsell A/B, downsell, Sovereign Architect high-ticket, order-bump) -> GHL media
(delegated to Skill 6) -> deterministic fragments -> two-track delivery -> GHL build (Skill 6) + bump
(Skill 44) -> signed PROCESS-CERTIFICATE.

**Skill 56 OWNS this cluster.** It EXTENDS the shared `universal-sops/funnel-craft/` cluster (Skill 49)
for the common funnel build + certify steps and shares its labeling grammar — 56 owns the grammar,
reciprocal with 49. The two engines are siblings on ONE delivery rail (Skill 6) and ONE labeling
namespace; they are never merged.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The
authoritative machine spine lives in the skill:

- `56-sales-page-assets/SALESPAGE-MANIFEST.json` — the P0..P9 phase spine + every `AF-SP56-*` gate code
  (SINGLE SOURCE OF TRUTH; editing it is step (i) of any Sales Page Assets change).
- `56-sales-page-assets/scripts/prove_sp_intake.py`, `prove_sp_image_plan.py`, `prove_sp_main_structure.py`,
  `prove_sp_upsell_structure.py`, `prove_sp_highticket_band.py`, `prove_sp_bump_band.py`,
  `prove_sp_bundle.py`, `prove_sp_cert.py` — the eight fail-closed, model-free, stdlib-only floor provers
  (each with a built-in `--self-test` + golden/attack fixtures). They MEASURE the stripped text; a
  model's self-reported section/word count is NEVER trusted.
- `56-sales-page-assets/run_sales_page_assets.py` — the deterministic no-skip orchestrator
  (front-door-nonce gated by `sales-page-assets-entry.sh`); issues the signed PROCESS-CERTIFICATE only
  on a full P0->P9 pass.
- `56-sales-page-assets/sales-page-assets-entry.sh` — the ONE sanctioned entry (DEPS -> VERSION ->
  HASH-PIN -> BYPASS-SCAN -> run-scoped 0600 nonce), fail-closed.
- `56-sales-page-assets/MASTERDOC.md` — the SACRED Direct-Response IP + every rule tied to its `AF-SP56-*`
  code.
- `56-sales-page-assets/structure/sales_page_structure.json` — the section/band definitions the provers
  load; `structure/labeling-grammar.json` — the labeling grammar (56 OWNS it, reciprocal with Skill 49).
- `56-sales-page-assets/intake/spa-intake.schema.json` — the locked 12-field intake contract.

## The ONE way in

A Sales Page Assets stack is built by running, and ONLY by running, the canonical fail-closed entry
shell:

```
bash 56-sales-page-assets/sales-page-assets-entry.sh --run-dir <RUN_DIR>
```

Requests route to this engine through the shared **STEP-0 funnel-engine selector**
(`06-ghl-install-pages/funnel-engines/registry.json` + `tools/funnel_engine_selector.py`) — Skill 56 is
the SECOND registered engine (the Direct-Response family). A hand-rolled GHL REST call, an ImgBB
re-host, a raw image `createTask`, a mail sender, or a `python3 run_sales_page_assets.py` without the
front-door nonce is the ungoverned path and is refused (`AF-SP56-CANONICAL-BYPASS` / `AF-SP56-FRONT-DOOR`).

## Files

| File | What it governs |
|---|---|
| `SOP-SALESPAGE-01-DR-ASSET-STACK.md` | What the Direct-Response asset stack is, when to build it, the 12-field intake, and the full gate contract (P0->P9 + every `AF-SP56-*`). |

The auto-fail ruleset and phase manifest are NOT duplicated here — they live authoritatively in
`56-sales-page-assets/SALESPAGE-MANIFEST.json` (the phase spine + the `autofail_codes` table). This SOP
points at them so there is exactly one source of truth. The common funnel build + certify steps are the
shared `universal-sops/funnel-craft/` procedure (Skill 6 is the ONE delivery rail for both engines); this
cluster EXTENDS them with the Direct-Response asset shapes.

## SACRED law (from `56-sales-page-assets/MASTERDOC.md`)

- The section counts and word bands are SACRED — never floored, reordered, renamed, or reinterpreted.
  Every rule is machine-enforced by a fail-closed prover, never advisory. The provers MEASURE the
  STRIPPED text; a model's self-reported count is IGNORED; whitespace padding is inert.
- **Main page (A/B):** exactly **8 sections** in canonical order (header/notification-banner -> hero ->
  problem/solution -> benefits -> product-details -> credibility -> final-cta -> footer), both variants,
  each carrying the mandated countdown timer (`AF-SP56-MAIN-SECTION-*` / `AF-SP56-MAIN-NO-COUNTDOWN`).
- **Upsell (A/B):** exactly **9 sections** in the Trevor Otts order (hook -> pain-1 -> pain-2 -> pain-3
  -> hope -> solution -> value-stack -> logical-justification -> identity-challenge close), both variants
  (`AF-SP56-UPSELL-SECTION-*`).
- **High-ticket:** the Sovereign Architect long-form page measures **6,500–7,100 stripped words**
  (`AF-SP56-HIGHTICKET-FLOOR` / `-CEILING`).
- **Order-bump:** **40–80 body words** ending with the checkbox close line `[X] Yes, add this to my order`
  (`AF-SP56-BUMP-FLOOR` / `-CEILING` / `-NO-CHECKBOX`); the bump routes to the Skill 44 seam as COPY
  (route `SKILL44_WIDGET`, `AF-SP56-BUNDLE-BUMP-ROUTE`).
- **Image plan:** every stage (main / upsell-1 / downsell-1 / high-ticket) gets >= 1 image — the
  slice-coverage gate closes the legacy default-4 bug (`AF-SP56-IMGPLAN-SLICE-EMPTY`); default count
  raised to 12.
- **Build bundle:** every asset key parses the labeling grammar with NO model name (rule R1); ZHC
  UPPERCASE prefix on every GHL container (R4); SEO block; per-page fragment + method + copy-tokens;
  thank-you present (`AF-SP56-BUNDLE-*`).
- **Process integrity:** a signed certificate requires a full P0->P9 pass with no phase skips
  (`AF-SP56-CERT-PHASE-GAP` / `AF-SP56-PROCESS-INTEGRITY`).
- **Client-exact overrides win:** a client-stated exact subset/count is honored verbatim and logged on
  the certificate — never floored, capped, or substituted (fleet-wide absolute law).

## Deliverable labeling grammar (56 OWNS it — reciprocal with Skill 49)

Every deliverable (copy doc, image prompt, PNG, HTML fragment, funnel, certificate) is labeled:

```
<client>__<funnel>__<stage>__<type>__vNN<variant>
```

`stage ∈ {main, checkout, bump, upsell-1, downsell-1, upsell-2, downsell-2, high-ticket, thank-you}`;
`type ∈ {copy, page, img, funnel, email, brief, manifest, cert}`; `vNN` is a zero-padded version;
`<variant>` is a lowercase letter for true A/B twins. Model provenance lives in `funnel-manifest.json`
metadata, NEVER in a label (rule R1). Pinned in `56-sales-page-assets/structure/labeling-grammar.json`
+ `MASTERDOC.md` §8, reciprocally with `49-signature-funnel/MASTERDOC.md` §8 and the funnel-craft
cluster. Do not diverge the two engines' grammars.

## Relationship to Funnel-Craft (Skill 49) — extends, shares grammar, NEVER merged

Skill 49 (Signature Funnel) owns `universal-sops/funnel-craft/` and the SACRED 12-section signature
engine. Skill 56 (Sales Page Assets) is the STANDALONE Direct-Response engine (8-section main / 9-section
upsell / downsell / high-ticket / bump). **Do not merge or deduplicate the two engines.** They share the
labeling grammar and the ONE Skill-6 delivery rail; this cluster EXTENDS funnel-craft for the common
build/certify steps. Routing disambiguation: a "signature funnel" / "signature landing page" (12-section)
-> Skill 49; a "sales page assets" / "direct-response sales page" / VSL / upsell-downsell A/B stack ->
Skill 56. The STEP-0 selector's `anti_signals` separate the two.

## Command Center registration (operator action)

The Command Center surfaces this capability as ONE `sops` row so the Triad Rule auto-resolves a "sales
page assets" / "direct-response sales page" request to it. NO schema change (a job is a `tasks` row).
Because the mission-control repo is a separate submodule not reachable from the skill worktree,
inserting/refreshing the row is an OPERATOR action at CC install/update time — via
`32-command-center-setup/scripts/add-sop.sh` (or the dashboard `POST /api/sops/import-role-library`).
Suggested row:

- `slug`: `sales-page-assets-dr-asset-stack`
- `name`: `Sales Page Assets: build the Direct-Response asset stack`
- `department`: `web-development`
- `task_keywords`: `sales page assets, direct response, direct-response sales page, vsl, order bump,
  high-ticket long form, sovereign architect, 8-section main, 9-section upsell, downsell, countdown
  timer, a/b sales page, ultimate ai sales page writer`
- `success_criteria`: signed `PROCESS-CERTIFICATE.json` present (full P0->P9 pass); measured 8-section
  main A/B + countdown; Trevor Otts 9-section upsell A/B; downsell; 6,500–7,100-word high-ticket; 40–80-word
  bump + checkbox close; slice-covered image plan; labels parse the grammar; delivered via Skill 6 with
  the bump routed to Skill 44; publish human-approved.

## Flexibility = guide-not-rule

The engine is a GUIDE and a RESOURCE for how a department fulfils a Direct-Response sales-page request;
honor an explicit owner choice (e.g. only main + bump, or an exact word target, logged on the
certificate). But the SACRED bands above are enforced by the provers and are not opinions — a violation
is a hard, named `AF-SP56-*` auto-fail.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys. The copy
+ image-prompt authoring runs on the CLIENT's own configured provider chain (strongest tier for the 7
copy assets + QC verify; a mid tier for image prompts / HTML / JSON; a cheap tier for catalog / poll).
A/B variants come from two client models OR two persona prompts on one client model — never an
Anthropic/Gemini split. The deterministic gates (`prove_sp_*.py`, the funnel-engine selector) are
provider-neutral Python and run identically everywhere; `56-sales-page-assets/verify.sh` includes a
provider-purity scan (ZERO `api.anthropic.com` / `claude-*` ids in the shipped skill). Images delegate
to Skill 47 or the client's own image provider; ALL GHL media + build delegate to Skill 6; the bump
routes to Skill 44. Publishing is human-approved (preview URLs + a labeled `~/Downloads/` bundle).
