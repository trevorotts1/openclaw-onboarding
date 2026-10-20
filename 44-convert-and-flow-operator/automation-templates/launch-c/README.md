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
