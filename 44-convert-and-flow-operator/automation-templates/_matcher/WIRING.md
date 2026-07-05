# Wiring — Flexible Automation Matcher + Funnel↔Automation Link Map

Three integration surfaces. Everything below is FLEXIBLE: a template/sequence is a GUIDE
and a RESOURCE, never a rule. `imposes_on_user` is always `false`; `override_allowed` is
always `true`; the matcher NEVER blocks a build.

## Artifacts (shipped skill files — paths are relative to the skill root)
- `automation-templates/_matcher/flex.py` — shared intent-mode + decision core.
- `automation-templates/_matcher/automation_matcher.py` — Skill-44 flexible matcher
  (`match_automation`, `step0_match`, `expand_funnel_to_automations`, `save_new_template`).
- `automation-templates/_matcher/cli.py` — `--build-index | --match | --expand | --selftest`.
- `automation-templates/_links/funnel-to-automation.json` — 38-funnel → automation link map.
- `funnel-templates/_matcher/funnel_matcher.py` — Skill-6 matcher, NOW flexibility-retrofitted.
- Patches: `automation-templates/_patches/skill6-funnel-matcher-flexibility.patch`,
  `automation-templates/_patches/skill44-instructions-step0-flexible-match.patch`.

---

## (A) Skill-44 STEP 0 — flexible match runs before PLAN MODE
**Where:** `44-convert-and-flow-operator/INSTRUCTIONS.md`, new **Step 0.4 — Flexible Template
Match**, inserted immediately before **Step 0.5 — PLAN MODE**.
(Patch: `skill44-instructions-step0-flexible-match.patch` — applies cleanly, +49 lines.)

**Code entrypoint** (vendor `automation_matcher.py` + `flex.py` → `44-.../tools/`):
```python
import automation_matcher as am
decision = am.step0_match(
    task, evidence_root,
    catalog_root=os.environ["CAF_AUTOMATION_CATALOG"],          # automation-templates/
    link_map_path=os.environ.get("CAF_FUNNEL_AUTOMATION_LINKS"),# _links/funnel-to-automation.json
)
# decision["intent_mode"]  -> EXPLICIT_USER_SPEC | UNSURE_WANTS_SUGGESTION | HANDS_OFF_DO_IT_ALL
# decision["decision"]     -> HONOR_USER | SUGGEST_TEMPLATE | USE_TEMPLATE | CREATE_NEW
# task is mutated: HONOR_USER->template_reference; SUGGEST->suggested_template+await_confirm;
#                  USE->workflow_plan; (CREATE_NEW->builder makes net-new, then save_new_template)
```
PLAN MODE (Step 0.5) then honors the decision: SUGGEST awaits confirm; HONOR_USER builds the
user's spec with the template as reference only; USE builds from the template; CREATE_NEW plans
net-new. Env-gated: with no catalog set and no injected matcher, Step 0.4 is a no-op (skip).

## (B) Skill-6 funnel instantiation → triggers Skill-44 to build the LINKED automations
**Where:** `06-ghl-install-pages/tools/funnel_matcher.py` `step0_match()` (flexibility patch).
When a funnel is identified (USE_TEMPLATE, or `task['funnel_template_id']`) and
`GHL_FUNNEL_AUTOMATION_LINKS` is set, `step0_match` calls `linked_automations(funnel_id, ...)`
and attaches the RECOMMENDED follow-ups to `task['linked_automations']` — **minus**
`task['automation_overrides']`. Example (verified): instantiating `webinar-funnel` (HANDS_OFF)
yields pages + `linked_automations` = [webinar-registration-reminder-replay-stack (primary),
indoctrination-multichannel-preframe, perfect-webinar-stack-close, soap-opera-sequence].

**Handoff call-site (the COMPLETE-FUNNEL trigger)** — in
`06-ghl-install-pages/tools/v2_dispatcher.py` `dispatch_one()`, AFTER a funnel build reaches
`STATE_VERIFIED`, enqueue one Skill-44 build per linked automation with `build_now: true`:
```python
for a in (task.get("linked_automations") or {}).get("automations", []):
    if a.get("build_now"):
        enqueue_skill44_build({                       # -> am.step0_match on the Skill-44 side
            "type": "automation",
            "automation_id": a["automation_id"],
            "category": a["category"],
            "funnel_template_id": task.get("funnel_template_id"),
            "intent_mode": task.get("intent_mode"),    # HANDS_OFF builds; EXPLICIT = reference only
            "location_id": task["location_id"],
        })
```
Each enqueued automation still runs Skill-44 Step 0.4 → PLAN MODE → Step 9 QC. Recommended,
never mandatory; user-overridden automations are already dropped (`build_now: false`).

---

## Honest status — wired vs ship-agent step
- **BUILT + TESTED (this agent):** `flex.py` (8/8), `automation_matcher.py` + `cli.py` (9/9
  match cases + 38/38 funnel-expansion), the link map (38/38, all ids validated on disk), the
  Skill-6 `funnel_matcher.py` flexibility retrofit (13/13 match quality preserved + flex
  invariants), and both patches (apply cleanly, dry-run verified).
- **SHIP-AGENT STEP (patches/anchors provided, not committed here):**
  1. `git apply` the two patches.
  2. Vendor `automation_matcher.py` + `flex.py` → `44-convert-and-flow-operator/tools/`, and
     `funnel_matcher.py` (+ the funnel catalog) → `06-ghl-install-pages/tools/` (the repo
     `tools/` does NOT yet contain `funnel_matcher.py`).
  3. Add the `dispatch_one()` complete-funnel handoff call-site in (B) — the canonical
     `v2_dispatcher.py` `dispatch_one()` does NOT yet call any step0 matcher (the README in
     `funnel-templates/_matcher` describes a `step0_matcher` kwarg that is NOT present in the
     committed dispatcher — treat that as the spec for this call-site, not as done).
  4. Set env on the dept agent: `CAF_AUTOMATION_CATALOG`, `CAF_FUNNEL_AUTOMATION_LINKS`,
     `GHL_FUNNEL_CATALOG`, `GHL_FUNNEL_AUTOMATION_LINKS`.
