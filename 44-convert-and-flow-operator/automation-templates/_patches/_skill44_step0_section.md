## Step 0.4 — Flexible Template Match (intent-mode routing — runs BEFORE PLAN MODE)

**Trigger:** any time the intent is to build an AUTOMATION / follow-up workflow (the same
trigger as Step 0.5 PLAN MODE). Read-only ops skip this.

**Why:** the 28-template automation library (welcome-indoctrination, engagement-broadcast,
sales-close-sequences, funnel-specific-followups, multichannel-automation) is a RESOURCE, not
a mandate. Before PLAN MODE, classify the request and let the matcher pick the RIGHT posture so
a template NEVER dominates the client's own desire.

**CORE PRINCIPLE — FLEXIBILITY:** every template/persona/sequence is a GUIDE and a RESOURCE,
NEVER a rule or a requirement. It assists; it never dominates.

**Run the matcher** (`tools/automation_matcher.py`, stdlib-only, no network):

```bash
export CAF_AUTOMATION_CATALOG=/path/to/automation-templates          # the library root
export CAF_FUNNEL_AUTOMATION_LINKS=/path/to/_links/funnel-to-automation.json
python3 tools/automation_matcher.py            # importable; step0_match(task, evidence_root)
```

It detects the **INTENT MODE** and returns a **DECISION** that PLAN MODE then honors:

| Intent mode | Signal | Decision | What PLAN MODE does |
|---|---|---|---|
| `EXPLICIT_USER_SPEC` | user gave their own steps / "use my", "exactly", "do not change" | `HONOR_USER` | Build the user's spec. The matched template is an **optional reference only** — never imposed/overridden onto their choice. |
| `UNSURE_WANTS_SUGGESTION` | "not sure", "what do you recommend", "which one" (and the default when unclear) | `SUGGEST_TEMPLATE` | **Suggest** the proven template + WHY, then **await confirm**. Do NOT build yet. |
| `HANDS_OFF_DO_IT_ALL` | "just do it", "build the whole thing", "your call", "turnkey" | `USE_TEMPLATE` | Build the whole automation from the template. |
| (any) nothing fits | best confidence < threshold | `CREATE_NEW` | Build net-new, then `save_new_template()` so the library grows. |

**Invariants (enforced in code):** `imposes_on_user` is ALWAYS `false`; `override_allowed` is
ALWAYS `true`; the matcher NEVER blocks a build. Every output is overridable, mixable,
customizable, ignorable. The decision + intent mode + matched template + score are LOGGED to
`<evidence_root>/routing/automation-decisions.jsonl`.

**COMPLETE-FUNNEL handoff (Skill 6 → Skill 44):** when this build was triggered by instantiating
a **Skill-6 funnel template** (the task carries `funnel_template_id`, or Skill 6 handed over
`linked_automations`), Step 0.4 also expands the funnel's RECOMMENDED follow-ups from
`funnel-to-automation.json` (primary + secondary + graduation) — **minus any the user overrode**
(`automation_overrides`). Each surviving link with `build_now: true` becomes its own Skill-44
build (each still goes through PLAN MODE + Step 9 QC). Recommended, never mandatory.

**Only after Step 0.4 has set the intent mode + decision may you proceed to Step 0.5 PLAN MODE.**
For `SUGGEST_TEMPLATE` you must get the client's confirm first; for `HONOR_USER` you build their
spec (template is reference only); for `USE_TEMPLATE`/`CREATE_NEW` you proceed to plan the build.

---
