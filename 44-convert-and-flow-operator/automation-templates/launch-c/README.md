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

- `ready` — every declared dependency and required output is satisfied.
- `blocked` — `blocked_by` names what is missing or invalid. Never upgraded by
  assumption; re-run once the Skill 50 deploy plan lands.

## L07 compiler output

The launch calendar is validated and normalized (`calendar`), then compiled into
schedule nodes (`schedule`): absolute nodes pinned to the calendar phases and
relative nodes pinned to enrollment. Policy:

- **Past time** — a promotional node at/before `--now` is suppressed, never sent.
- **Close time** — a promotional node at/after `doors_close_at` is suppressed;
  the last doors-closing send lands 60 s before close. Relative (enrollment)
  phases carry a runtime `suppress_after` guard instead.
- **Entitled access** — `welcome_access` is transactional and never suppressed
  by a purchase or by the close window.

Each build carries the eligibility rules, lifecycle stop/suppression rules and
sender configuration REFERENCES from the Skill 50 plan (`eligibility`,
`lifecycle`, `sender`), a stable `unit_key` (`<launch_id>/<automation_id>`), the
`expected_graph_hash`, and `required_outputs`. The provider compiler
(`tools/engine/.../workflow_builder.py`) turns those into native step
conditions and workflow settings, journals every phase, and reads the saved
graph back before claiming success.

A build plan that matches no sequence is reported in
`unused_build_plan_workflows`, never dropped.

## Fail-closed rules

- Launch calendar: valid IANA `timezone`; every instant carries the zone's
  offset at that wall time; a DST gap is refused, a DST overlap must name one
  fold; strict `doors_open_at < launch_at < doors_close_at` and strict
  `black_friday` order.
- Launch plan: version `1.0.0`, unique unit ids, resolvable `waits_for`, no cycle,
  canonical `family` / `build_rail`, every unit `draft_only: true`, sequence
  phases ordered pre_launch < main_launch < doors_closing.
- Dependencies: a dependency on a page with no approved URL, a text set missing
  its guard fields, an unknown/blocked upstream unit, or an email-count mismatch
  between the launch plan and the bound build plan BLOCKS the build.
- Guards: a promotional build whose lifecycle omits unsubscribe/purchase
  suppression is blocked and the provider compiler refuses it.
- Build plan: `folder` present; every workflow `status == "draft"` (a published
  workflow is refused); `_meta.draft_only` / `_meta.deploy_mode` must be draft;
  steps are `email` (subject, body, html, fromName) or `wait` (startAfter) only.
- Credential-shaped keys anywhere in a plan are refused; sender configuration is
  a named `*_ref` only.
- Exit `0` ok / `2` invalid input / `3` IO.

## Checks

```
python3 launch-c/tests/test_plan_reader.py              # behavior tests (contract fixtures)
python3 launch-c/tests/test_plan_reader_l07_schedule.py  # calendar / schedule / dependency tests
python3 launch-c/plan_reader.py --selftest             # built-in refusal checks
python3 tools/engine/tests/test_workflow_builder_l07.py  # provider compile / journal / readback
```

Fixtures are the four contract fixtures in
`shared-utils/signature_launch_contract/fixtures/` plus five small Skill 50 build
plans under `launch-c/fixtures/`. Nothing in a plan authorizes a send or a live
switch-on: every email and automation stays **draft**.
