# SELECTORS — PIPELINE builder (Convert and Flow / Go High Level)

**Status: RESEARCH-SEEDED — NOT LIVE-LOCKED.** Derived 2026-07-07 from the
official HighLevel support portal ("Step-by-Step Guide: Creating Pipelines",
"Getting Started - Setup Pipelines and Opportunities"). NO live selector-lock
run has captured this surface yet — every anchor below is a documented-flow
seed that `ghl_pipeline_builder.py` binds AT RUNTIME by pattern and verifies
positively. The first live run against a test sub-account must upgrade this
file to LOCKED status with observed anchors + confidences (the same process
that produced SELECTORS-LIVE-form.md).

> ⚠️ Convert and Flow = Go High Level = GHL.
> ⛔ There is NO public API for pipeline/stage creation (confirmed against the
> real v2 AND v3 OpenAPI specs, 2026-07-07). `GET /opportunities/pipelines`
> (Skill 44 `caf opportunities pipelines`) is the only public read surface —
> use it AFTER the browser build to capture the new `pipelineId`/`stageId`s.
> Opportunity CRUD itself stays on Skill 44's API path (proven).

## 1. Route (RUNTIME SNAPSHOT-GATED)

| Surface | Seed (docs-derived) |
|---|---|
| Pipelines management | Opportunities (left rail) → **Pipelines** (top nav). SPA seed: `/v2/location/<LOC>/opportunities/pipelines`; fallback: router-push `/v2/location/<LOC>/opportunities/list` then click `Pipelines`. |

Landing proof = a visible control matching `/Create\s+[Nn]ew\s+[Pp]ipeline/`
(the docs themselves alternate between "Create new pipeline" and "Create New
Pipeline", so the walk binds the EXACT label it actually sees and clicks
role=button + `--exact` on THAT string).

## 2. Create-pipeline dialog (docs-derived; runtime-capture)

| Target | Seed | Walk behavior |
|---|---|---|
| Pipeline Name | input labeled/placeholder **"Pipeline Name"** (unique per sub-account — GHL rejects duplicates) | `find label|placeholder … fill`; fallback `keyboard type` into the dialog's focused input; **POSITIVELY verified**: the typed name must render or `PL3.name` STOPs. |
| Stage Name rows | first row may be pre-seeded; **"Add stage"** (pattern `/Add\s+[Ss]tage/`) appends a row which takes focus | fill row 1 by label; else runtime-bind "Add stage" → click → `keyboard type`; **each stage name must render** or `PL4.stage:<name>` STOPs. |
| Save | **"Save"** button | role=button `--exact`, rc-checked. |
| Won / Lost | **automatic** — GHL creates the terminal stages itself | the THINK layer STRIPS any manual Won/Lost from the requested stages. |

## 3. Post-save verification (positive, v18.1.5 doctrine)

The saved pipeline must appear in the RENDERED Pipelines list: leaf-text count
(`textContent`-exact leaf nodes) for the planned name must be **>= 1**, on
a poll deadline. A dialog echo or the a11y snapshot alone is never accepted.
Then capture the ids via Skill 44 (`caf opportunities pipelines`).

**Name modes (v18.1.12):** default = the fleet `ZHC ` container prefix
(`ensure_zhc_name`). `--exact-name` = the name is used BYTE-EXACT, for callers
that bind the created pipeline by name through the read API afterwards — the
Anthology Engine (Skill 59 `anthology_registry.py provision-pipeline`) invokes
this walk with `--exact-name "Anthology Engine"` and its 9 standard stages
(Intake, Avatar, Tone, Title, Outline, Chapter, Cover, Delivered, Assembled),
then re-reads `GET /opportunities/pipelines` and binds ONLY what that read
surface shows.

## 4. Stage management (docs-derived; NOT yet walked)

Within the pipeline editor: reorder via up/down arrows; reporting visibility
via funnel + pie-chart icon toggles; per-stage delete via trash icon (deleting
a stage prompts for a destination stage for existing opportunities); stage
color options. These are documented but NOT yet implemented/walked — extend the
walk only with live evidence.

## 5. Whole-pipeline DELETE (runtime-capture — UNDOCUMENTED)

The official portal does not document the whole-pipeline delete flow. The
cleanup walk (`_delete_pipeline`) therefore:

1. requires EXACTLY ONE rendered row for the ZHC test name (leaf-count gate);
2. opens the pipeline row, then only clicks a delete affordance it can COUNT
   to exactly one on screen (candidates: `Delete` / `Delete Pipeline` /
   `Delete pipeline`); ambiguous (>1) or unlocatable (0/unknown) → honest
   not-deleted + OPERATOR REVIEW flag — never a blind click on a real account;
3. confirms via a uniquely-countable button (`Delete`/`Confirm`/`Yes`);
4. POSITIVELY verifies: polls the re-landed list to ZERO rendered leaf matches
   (present→delete→absent proof; unknown counts never read as gone).

First live run: capture the REAL delete affordance (label/role/menu shape) and
lock it here.

## 6. Test-asset labeling

Any pipeline created as a live test MUST carry the ZHC test convention (e.g.
`ZHC TEST - OpenClaw Skill6 Verification - DO NOT USE`) and MUST be deleted with
the positive proof above — never left behind on a client account.

## 7. FIRST LIVE RUN (2026-07-08) — landing STOP + the fix applied

**Status: still RESEARCH-SEEDED.** The first real walk against a live
sub-account authenticated, router-pushed to the real
`/v2/location/<loc>/opportunities/pipelines` route, and confirmed **ZERO
iframes** on the surface (so this was NOT a cross-origin capture miss — the
same class of bug the form builder fought all night). It then STOPped
honestly at `PL1.land`: no control matching `/Create\s+[Nn]ew\s+[Pp]ipeline/`
was ever visible.

### What we actually found (code inspection — certain)

The landing check (`_land_on_pipelines`) took `fb._wait_text_polling(session,
"Pipeline")` — a wait for the generic word "Pipeline", satisfied instantly by
the screen's OWN header/breadcrumb regardless of whether the create control
had hydrated — then called `_snapshot()` **exactly once** and regex-searched
that single opaque result for the create control. No poll, no retry. This is
the identical single-shot-race bug class the sibling `ghl_form_builder.py`
already killed on 2026-07-07 (v18.1.2, `_wait_text_polling` for F2's
create-modal wait; v18.1.11, the `_reveal_row_actions` hover-poll) — GHL's SPA
screens have repeatedly proven to render header chrome before data-dependent
action controls finish hydrating.

### What real research found (docs — as confirmed as documentation gets)

Re-fetched 2026-07-08 directly from GHL's own support portal (not a
paraphrase — see citations):

- **help.gohighlevel.com — "Step-by-Step Guide: Creating Pipelines"**
  (`/support/solutions/articles/155000001985-step-by-step-guide-creating-pipelines`):
  exact button text **"Create new pipeline"**, top-right corner of the
  Opportunities ▸ Pipelines screen. No plan/limit gating mentioned.
- **help.gohighlevel.com — "Getting Started - Setup Pipelines and
  Opportunities"**
  (`/support/solutions/articles/155000005062-getting-started-setup-pipelines-and-opportunities`):
  same flow — Opportunities → Pipelines → **"Create New Pipeline"** → fill →
  Save. No plan/limit gating mentioned.
- **help.leadconnectorhq.com — "How to Create and Manage Opportunity
  Pipelines"**
  (`/support/solutions/articles/155000005356-creating-and-managing-opportunity-pipelines`):
  confirms the same navigation (Opportunities → Pipelines → create/edit/
  delete) but does NOT quote an exact button string — less specific than the
  two GHL articles above, not a contradiction.
- **GHL's own changelog-adjacent material** (multiple independent search
  hits returning the same verbatim line) states: *"The Pipelines page now
  uses the HighRise design system for a faster and more intuitive
  experience... you can enable this update from Sub-account → Labs... no
  core functionality changed... all existing pipeline-based automations and
  triggers continue to function normally."* This confirms GHL recently
  shipped a **new frontend implementation** of this exact screen (opt-in via
  Labs, rolling out), while explicitly claiming the button semantics/wording
  did NOT change.
- A community mention (third-party blog, not official) describes an
  **alternate** path: a pipeline-selector dropdown at the top of the
  **Opportunities LIST** page with a **"+ New Pipeline"** option. This is a
  DIFFERENT screen than the Pipelines management screen this walk already
  correctly lands on (confirmed by the zero-iframe, correct-route evidence
  above) — not applicable here unless a future run needs a different
  navigation path entirely.
- No source (official or community) documents pipeline creation being nested
  inside a menu/kebab on the Pipelines management screen itself, and no
  source documents a plan/limit gate on pipeline creation.

### Diagnosis (evidence-based, NOT confirmed live)

The strongest-evidenced hypothesis is **(b) a render race**: GHL's own docs
say the button wording is unchanged, but the screen's underlying
implementation recently changed (HighRise redesign) — exactly the kind of
change that can shift WHEN the create affordance hydrates relative to the
page chrome, without changing WHAT it says. Hypothesis (a) label drift is
weakly supported (docs consistently show "Create new pipeline" as current).
Hypothesis (c) dropdown-nesting is weakly supported (only found for a
DIFFERENT screen, not this one). Hypothesis (d) plan/limit gating has no
supporting evidence in any source checked.

**Honesty check:** GHL's own docs can lag the live product by days, and
HighRise is described as an opt-in-via-Labs rollout — so it is possible the
specific sub-account under test is on a UI variant not yet reflected in any
indexed documentation. This fix does NOT independently confirm that
possibility away; it addresses the CONCRETE bug the code proved (a real
single-snapshot race) and turns any FUTURE miss into actionable evidence
instead of a bare "not found".

### The fix applied (`ghl_pipeline_builder.py`)

- `_poll_for_create_pipeline_label()`: polls `_snapshot()` + the
  `CREATE_PIPELINE_RE` match on our OWN monotonic deadline (same
  poll-with-deadline doctrine as `ghl_form_builder._wait_text_polling` /
  `_capture_form_id` / this file's own `_save_and_verify` leaf-count poll) —
  never trusts one opaque single-shot snapshot again. Always makes at least
  one attempt.
- `_diagnose_missing_create_control()`: on a genuine deadline miss, lists
  every distinct `pipeline`-mentioning text window actually seen in the
  FINAL polled snapshot (deduped, capped at 12), flags any UNCONFIRMED
  alternate-wording hint that matched (`+ Add Pipeline`, `+ New Pipeline`,
  `Add Pipeline`, `New Pipeline` — evidence only, NEVER auto-clicked), and
  flags any possible plan/limit-gating text (`upgrade`, `limit reached`,
  `maximum number`, `plan limit` — evidence only). A second failure now
  explains exactly what the screen showed and why every candidate was
  rejected, instead of repeating a bare "not found".
- `_land_on_pipelines()` STOP message now names the exact poll window used
  and folds in the rich diagnostic + the existing `_capture_entry_diag`
  (top-frame path + iframe srcs) evidence.

**This is still NOT a live-locked fix.** Route, label pattern, and dialog
flow remain RUNTIME-BOUND and RESEARCH-SEEDED. The next live run is the real
test: if it lands cleanly, promote §1/§2 above to LOCKED with the observed
anchor; if it STOPs again, the new diagnostic text is the next concrete
piece of evidence to act on — not another guess.
