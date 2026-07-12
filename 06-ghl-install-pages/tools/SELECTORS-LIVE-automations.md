# SELECTORS-LIVE-automations.md — GoHighLevel Automations (Workflow) builder

**Consumed by:** `06-ghl-install-pages/tools/ghl_workflow_builder.py` (the Skill 6
GATED, MANAGED workflow-build path — the Tier-4 backstop Skill 44 routes to when
the Firebase token is unread/misconfigured; see
`44-convert-and-flow-operator/SKILL.md` → "Workflow BUILD and EDIT" and
`36-ghl-mcp-setup/GHL-LOOKUP-SOP.md` RULE 6).

**Gate registry of record:** `06-ghl-install-pages/tools/gates.json` →
`automations_builder_gates`. This file is the human-readable companion; the JSON
is what the harness reads.

---

## Doctrine (why this file looks unfinished on purpose)

Skill 6's law: **NO invented CSS is shipped as fact.** A selector is only recorded
here as `captured` after it is confirmed against a LIVE snapshot of the GoHighLevel
Automations UI. Until that live-capture pass runs (on the operator's own GHL
location), every step below ships **`status: runtime`** — the harness resolves it
at run time via an accessibility **role/name / visible-text find hint**, exactly
the same mechanism the existing runtime gates in `gates.json` use. A runtime find
hint is NOT a fabricated CSS selector; it is a search seed the agent confirms
against the real DOM before acting.

This is the same two-phase pattern every other Skill 6 builder followed
(`SELECTORS-LIVE-funnel.md`, `-page.md`, `-pipeline.md`, `-form.md`, `-course.md`,
`-community.md`, `-survey.md` were all runtime-first, then hardened by a live
capture). The **harness is complete and unit-tested now**
(`tests/test_ghl_workflow_builder.py`, `--selftest`); only the **captured
selectors** are the operator-box follow-on.

- `_capture_status` in the JSON: **`pending_live_capture`**.
- The harness **refuses** (`MissingGateError`) if a required step is absent — it
  never freehand-navigates.
- Every browser action routes through the `browser_manager.sh` **singleton
  gateway** (one session, lock=1, TTL, guaranteed teardown, reaper backstop). The
  builder never spawns agent-browser directly (guarded by
  `scripts/guard-agent-browser-managed.sh`).

---

## Navigation

| Field | Value | Status |
|---|---|---|
| Route template | `/v2/location/{location_id}/automation/workflows` | runtime-unverified — confirm at capture time |

## Build steps (in order)

| # | Gate name | What it acts on | Runtime find hint | Status |
|---|---|---|---|---|
| 1 | `open_automations` | Workflows list view | nav to route, then `find role heading name 'Workflows'` | runtime |
| 2 | `create_workflow` | Create Workflow button | `find role button name 'Create Workflow'` (or `'+ Create Workflow'`) | runtime |
| 3 | `start_from_scratch` | Start-from-scratch template option | `find role button name 'Start from Scratch'` / `find text 'Start from scratch'` | runtime |
| 4 | `name_workflow` | Editable workflow-title field | `find role textbox name 'Workflow name'` / `'Untitled Workflow'` | runtime |
| 5 | `add_trigger` | Add New Trigger button | `find role button name 'Add New Trigger'` / `find text 'Add Trigger'` | runtime |
| 6 | `choose_trigger_type` | Trigger-type picker item | `find role option name {trigger_type}` / `find text {trigger_type}` | runtime |
| 7 | `save_trigger` | Save Trigger button | `find role button name 'Save Trigger'` (or `'Save'`) | runtime |
| 8 | `add_action` | Add-action node on canvas | `find role button name 'Add your first Action'` / `'Add Action'` | runtime |
| 9 | `choose_action_type` | Action-type picker item | `find role option name {action_type}` / `find text {action_type}` | runtime |
| 10 | `save_action` | Save Action button | `find role button name 'Save Action'` (or `'Save'`) | runtime |
| 11 | `save_workflow` | Top-right Save (persist draft) | `find role button name 'Save'` | runtime |
| 12 | `read_workflow_id` | Built workflow id read-back | `eval location.href` → parse `/workflows/(?:builder/)?<id>` | runtime |

`{trigger_type}` / `{action_type}` are substituted from the build spec (e.g.
`Contact Created`, `Send Email`).

---

## Live-capture follow-on (operator box)

When the live-capture pass runs on the operator's own GHL location:

1. Open a managed session (`bash tools/browser_manager.sh ensure`), navigate to the
   Automations builder, and snapshot each step's node.
2. Replace the `find` hint with the confirmed node and set `status: captured` for
   that step in `gates.json` → `automations_builder_gates.steps`.
3. Record the confirmed selector + a screenshot reference in this file's table
   (flip the Status cell to `captured`).
4. Set `_capture_status` to `captured` once all required steps are confirmed.

Never fabricate a `captured` selector ahead of that pass.
