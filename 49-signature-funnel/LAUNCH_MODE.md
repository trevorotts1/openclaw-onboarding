# Skill 49 — `signature_launch` mode

Skill 49 organizes the launch; the other skills build each piece.

Skill 49 has two modes. The mode is chosen explicitly on every new run;
nothing silently switches.

| Mode | What it is |
|---|---|
| `legacy_signature_funnel` | The historical pipeline: SACRED 12-section hero, derived U1/D1/U2/D2/thank-you pages, 3/5/7-step funnels, the locked-brief intake (`intake/sf-intake-questions.json`), fail-closed provers, signed PROCESS-CERTIFICATE. Behavior is unchanged; its golden fixtures are the regression contract (acceptance A34). |
| `signature_launch` | The launch coordinator added by the Signature Launch build: guided intake and plan approval first, a deterministic route graph compiled from the approved plan, then one idempotent page request per role dispatched to the specialist skills (71 landing, 78 product selection, 79 checkout, 80 upsell 1 and upsell 2 as separate invocations, 81 downsell, 82 thank-you). The bump is a component on checkout, never a page. The route has one downsell node (owner route law); a second downsell is a design page the client opts into (`--extra-page downsell_2`) that rides on the downsell request, and the 7-step Signature Funnel carries `downsell-2` (`scripts/legacy_downsell_images.py` gives it wireframes and mockups). |

## Entry

```bash
# legacy (default, unchanged)
bash signature-funnel-entry.sh --run-dir <RUN_DIR>

# launch mode (explicit)
bash signature-funnel-entry.sh --mode signature_launch --run-dir <RUN_DIR>
```

A launch run dir holds `launch.json` (the approved launch record),
`approval.json` (the plan-approval record), and `launch-request.json`
(`mode`, client/worker identity refs, copy profile, write target, any
scoped approvals). The legacy path refuses a launch-mode run dir rather
than running it through the old pipeline. The entry script is not a
pinned enforcement file; no pinned file changed for launch mode, so the
hash-pin still verifies the untouched legacy core.

## Launch-mode toolchain (`scripts/`)

| Script | Job |
|---|---|
| `launch_intake.py` | Guided interview state machine (doc 03): durable session, per-field provenance ledger, deterministic recommendation rules, plan assembly, plain-language summary, pause/resume. Question bank: `intake/launch-questions.json`. |
| `validate_launch_plan.py` | Domain-law plan validator plus `assert_plan_build_approved`, the plan-approval gate (hash binding, client identity, no worker self-approval, revocation/expiry, separate approval types). |
| `compile_launch_route.py` | Deterministic route compiler/validator/resolver. One source produces `route-graph.json`, a readable route table, and machine test cases. Graph hash = SHA-256 of the emitted file bytes. |
| `dispatch_launch.py` | Turns an approved plan into specialist page requests (idempotent dispatch keys), optionally executing them through consumer adapters (`launch-adapters.example.json`). Emission is not execution: the manifest says `emitted_not_executed` until a consumer really answers with a valid result. |
| `page_set.py` | The pages of a funnel, for any shape (single offer, multiple options, **folded levels**, free entry, legacy 3/5/7). One ordered entry per page from `structure/page_types.json`: signature landing page, signature sales page, order page, order form / checkout, upsell 1 and 2, downsell 1 and 2, thank-you. Each carries its page identity (role + page kind + role instance), its client-facing label, the skill and wrapper that build it, and the design files it must end with (desktop and mobile wireframes and mockups, review PDFs, overview boards). Which landing pages the funnel gets is the client's intake choice; when they did not choose, the recommended set is used and listed as **to confirm**. Dispatch hands that set to the landing bridge (`--landing-pages {landing_pages}`), which refuses a config that builds a different set, so a funnel planned with two landing pages is never delivered with one. Also reads and checks the shared image inputs file (`--image-inputs`) every wrapper takes, and proves a run folder holds every deliverable: a free stub run is reported as images only, render pending, never as complete. |
| `launch_plan.py` | The FULL launch plan beside the pages: turns the assembled launch record plus the intake answer ledger into one document in the shared launch-plan contract (`shared-utils/signature_launch_contract/launch-plan.schema.json`) — `pages`, `email_sequences` (Skill 50), `text_sets`, `automations` (Skill 44), `conversation_ai{requested,mode}`, `launch_calendar` and `a2p_ready`, every unit with its `waits_for`. Families and templates follow spec §3.3; every email, text and automation is `draft_only`, `build_rail` is the U-GHL-PROBE answer (Skill 44 engine), failed payment appears only with payment plans, the AI reply workflow only when the bot was requested, and texts only for an email + text launch, within the cap of 5 promotional sets. A missing launch date, doors time, timezone or AI mode blocks the plan by name — no deadline, price or bot job is invented. `launch_intake.assemble_plan` attaches it to the session (`launch_plan`, `launch_plan_missing`) and the client summary names the emails, texts, automations and AI choice; `launch_intake.py --launch-plan [--out plan.json]` prints or writes it for the dispatcher. |
| `page_swarm.py` | Builds the pages side by side. Every page runs side by side, the landing lane (sales page and opt-in page) with the rest, `--parallel auto` workers at a time (the Skill 71 runner profile: Mac 6, Hostinger 8, Contabo 4; `--parallel 1` is one page at a time, same results). Paid image starts take tokens from the shared KIE limiter (20 per 10 seconds, retries included) and a per-launch spend ledger (`spend-ledger.json`) stops new paid work at the image cap. One page failing never stops the others; results come back in page order. No page waits for another: the look they share is the one image inputs file, and `visual-bible.json` is only the record of what the landing run drew, written when the swarm ends. |
| `checkout_wrapper.py` | The design-only adapter for the `checkout` role: Skill 71's shared image service builds the order form page's desktop and mobile wireframes and mockups on the five-section checkout role spec (never the native form, which stays Skill 06's). Staged inputs: the approved checkout manuscript, the run's measured design system as `{work_dir}/design-prose-checkout.json` (required: `--design-prose`, a JSON object with `notes`, `traits`, `rules_md` and `rules_json` keys as `build_production_request.py` reads it; without it the default image-model prompt band refuses every checkout section below the 16000-char floor and the wrapper exits 2), brand file, brand owner, image cap and design style. Stub provider by default. |
| `collect_launch_receipts.py` | Aggregates page results into a launch checkpoint: request echo required, self-review never counts as independent review, weakest proof class reported. |
| `legacy_adapter.py` | Migrates a legacy LOCKED brief into a launch-mode draft (status `collecting`, no plan approval — the legacy lock is not one), with a mapping report that names every unmapped field (notably the second downsell, which has no launch counterpart). Legacy files are never edited. |

## Every page gets its designs

A launch is not finished for a page until that page has desktop and mobile wireframes and desktop and
mobile mockups, clearly labelled (for example `DOWNSELL 2 · DESKTOP WIREFRAME`). The page list and the
files each page must end with live in `structure/page_types.json`; `scripts/page_set.py` plans them for
the funnel's shape and checks a run folder against them. What a wrapper returns lists every one of those
files (section images, review PDFs, overview boards), not only the copy. The checkout page gets designs
only: the real order form stays the native Convert and Flow form installed by Skill 06 (CR-S49-003).
A funnel with levels folded into its signature page (`folded_levels`, for example the three levels of
7FigurePreneur) has no selection page; its sales page closes on a levels panel with one card per level,
each leading to the native order form. Skill 71's request builder reads the level count from the run's
`launch.json` (the main offers of a `folded_levels` launch) and stamps it into the production request, so
the wireframes close on that panel in a real run, not only in a hand-built request.

The legacy 3, 5 and 7 step funnel gets the same: `scripts/legacy_downsell_images.py` (name kept) draws the
wireframes and mockups of every page of the funnel size from the P1 copy ledger (sales page, upsell 1
and 2, downsell 1 and 2, thank-you), checks each against `structure/page_types.json`, and names the
checkout as design-only: it draws it too when given `--checkout-manuscript <the approved five-section checkout manuscript>` (the ledger has no checkout copy and `checkout_wrapper.py` needs a launch request legacy mode lacks), and otherwise says so in the receipt.

## Contracts

Canonical schemas live in `shared-utils/signature_launch/domain/`
(launch, offer, route-graph, approval, page-request, page-result,
progress, purchase-event v1.1); the skill carries its own copies of the
launch and route-graph schemas under `schema/`. Money is integer minor
units; an unknown price is `null` with status `unknown`, never zero. A
recommendation is a proposal state, never an approval; approval binds to
the exact plan hash and revision.

## What launch mode does not do

It does not process payments, send email, call image providers over
HTTP, or handle browser credentials. Native products/prices/orders are
S44/S06/S79 surfaces; email is S50's plan consumed by S44; images follow
the S63 policy and the selected provider's receipts. The launch DAG —
approved domain/brand → copy/profile → approved local artifacts → S44
provisioning → S06 native install → S44 workflow wiring → integrated
test → activation approval — is enforced by the dispatch write targets
and scoped approvals, not by this skill reaching into other systems.
