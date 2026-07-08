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
