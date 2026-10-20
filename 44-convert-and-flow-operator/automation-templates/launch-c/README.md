# Launch C — Onboarding + Review/Referral

Lane AC-1 (WF-AUTO-C) files for spec §3.3 family **Onboarding + review/referral**.

| File | Workflow | Trigger | Ends at |
|---|---|---|---|
| `onboarding-first-hour-day-week.json` / `.md` | LC — Onboarding: First Hour, Day 1, Week 1 | Tag Added `purchase-onboard-ready` | `review-eligible` or `onboard-help-needed` |
| `review-referral-ask.json` / `.md` | LC — Review Ask → Referral Ask | Tag Added `review-eligible` | `referral-asked` or `advocacy-closed-no-ask` |

**Template start:** `membership-stick-retention` (Phase A onboarding + advocacy cut; membership-only mechanics excluded).
**Build rail:** Skill 44 engine — per `launch-ghl-probe/GHL-CAPABILITY-NOTE.md`. Purchase trigger is not auto-built; the lane uses a Tag Added trigger set by the post-sale family (patch-trigger only as fallback). `review_request` is a verified action. **Draft only.**

**Contract mapping:** `family: onboarding_review`, `unit_id: auto_onboarding_review`, `template: membership-stick-retention`, `build_rail: skill44_engine`, `draft_only: true`, `waits_for: [auto_post_sale, email_welcome_access, page_thank_you]`.

**Integrator-only lines these files need (not edited by this lane):**
- `44-convert-and-flow-operator/automation-templates/README.md` — a launch-lane note pointing at `launch-a/`, `launch-b/`, `launch-c/` (the 28-template count stays 28; launch lanes are separate).
- `44-convert-and-flow-operator/SKILL.md`, `CHANGELOG.md`, `skill-version.txt` — release bookkeeping after integration.
- `_matcher/catalog-index.json` and `_links/funnel-to-automation.json` — unchanged unless the integrator chooses to index launch lanes; these files are not launch templates in the 28-template library.

**Guards:** no sends, no live switch, no client account touched; purchase stops promotional messaging; SMS opt-in with STOP; review ask unfiltered and unincentivised; referral asks use real terms or a named introduction.

---

# launch-c — Skill 50 plan reader

Reads the launch plan (U-CONTRACT) and the **Skill 50 P4 DRAFT-ONLY build plans**
into one **automation-build** document for the automation lanes (WF-AUTO-*).

- Input contracts: `shared-utils/signature_launch_contract/launch-plan.schema.json`
  and `50-email-engine/schema/build-plan.schema.json` — never redefined here.
- Output contract: `launch-c/automation-build.schema.json`.
- Deterministic, stdlib-only, model-free. No provider call, no send, no publish.

```
python3 launch-c/plan_reader.py \
  --launch-plan plan.json \
  --build-plan email_pre_launch.json --build-plan email_main_launch.json \
  --out working/automation-builds.json
```

`--sequence-map map.json` (optional) pins a build plan to a launch email sequence:
`{"email_pre_launch": "path/to/build-plan.json"}`.

Without a map a build plan is bound by `_meta.sequence_id` /
`_meta.source_ids.sequence_id`, then by file stem, then by the single sequence id
its workflow keys, names or tags name. Two candidates = invalid input, not a guess.

## What it emits

One `builds[]` entry per launch-plan automation unit: the plan's `id`, `family`,
`template`, `build_rail`, `trigger`, `waits_for` and `draft_only` unchanged, plus
the Skill 50 workflows bound to the email sequences it waits on (steps passed
through verbatim), and a `state`:

- `ready` — every email sequence it waits on has a bound build plan.
- `blocked` — `blocked_by` names the sequences still missing. Never upgraded by
  assumption; re-run once the Skill 50 deploy plan lands.

A build plan that matches no sequence is reported in
`unused_build_plan_workflows`, never dropped.

## Fail-closed rules

- Launch plan: version `1.0.0`, unique unit ids, resolvable `waits_for`, no cycle,
  canonical `family` / `build_rail`, every unit `draft_only: true`.
- Build plan: `folder` present; every workflow `status == "draft"` (a published
  workflow is refused); `_meta.draft_only` / `_meta.deploy_mode` must be draft;
  steps are `email` (subject, body, html, fromName) or `wait` (startAfter) only.
- Credential-shaped keys anywhere in a plan are refused; sender configuration is
  a named `*_ref` only.
- Exit `0` ok / `2` invalid input / `3` IO.

## Checks

```
python3 launch-c/tests/test_plan_reader.py     # behavior tests (contract fixtures)
python3 launch-c/plan_reader.py --selftest     # built-in refusal checks
```

Fixtures are the four contract fixtures in
`shared-utils/signature_launch_contract/fixtures/` plus five small Skill 50 build
plans under `launch-c/fixtures/`. Nothing in a plan authorizes a send or a live
switch-on: every email and automation stays **draft**.
