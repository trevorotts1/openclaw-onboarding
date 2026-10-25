# Dispatch, designs and delivery (Skill 83, lane 83)

What `python3 -m launcher_core.cli dispatch` does, what it asks the client, what it will not do, and what
the package must hold before it counts as delivered. SKILL.md and DECISIONS-PENDING.md point here; they are
edited by the turn-on workflow, so this file carries the new behavior until that merges.

## One command, every page

```
python3 -m launcher_core.cli dispatch --intake intake.json --out RUN \
    --approval approval.json --client CLIENT_ID --worker WORKER_ID \
    (--adapters adapters.json | --adapter-inputs inputs.json) [--parallel N] [--landing-pages landing,sales] [--extra-page downsell_2]
python3 -m launcher_core.cli assemble --intake intake.json --pieces RUN/pieces --out PACKAGE
python3 -m launcher_core.cli check --manifest PACKAGE/package-manifest.json --root PACKAGE
```

1. The validated intake becomes a Skill 49 launch record (`launcher_core/launch_bridge.py`). Every offer,
   price and level is copied from the intake; nothing is invented. Skill 49's own validator must accept it.
2. The client's recorded approval is carried to Skill 49's gate unchanged. A worker cannot approve its own
   plan, and a plan that changed after approval is refused.
3. Skill 49 dispatches one request per page. `assemble` reads the result files the bridge lays in
   `RUN/pieces/<role>.json` (and `<slot>.json` for a second page of a role, such as `downsell_2`).
   `--extra-page downsell_2` is the client's opt-in to a second downsell: Skill 49 builds it beside `downsell_1`
   (it rides on that page's request), the bridge lays its result in `pieces/downsell_2.json`, and the package
   names it `downsell-2_...` with the same required design set as every other page.
4. Skill 49's page set is the plan. `--landing-pages landing,sales` is the client's choice of landing pages;
   without it Skill 49's recommended set is used and `landing_pages` is listed under "to confirm" in the
   client summary. The landing build answers every planned landing page in one result, and the bridge lays
   one piece per page: `pieces/landing.json` and, when both are planned, `pieces/sales.json` (the signature
   sales page, `sales-page_...` files). A planned page with no file of its own is refused by name, and
   `assemble` refuses a plan for both landing pages that has no sales piece. `dispatch-report.json` carries
   `page_labels` and `landing_pages` so the summary names every page.
5. With `--adapter-inputs` the bridge builds the real adapter commands itself. It needs `checkout_manuscript`
   (the order form page's copy, so its wireframes and mockups can be drawn) and refuses plainly without it.
   Two image-input files are written: `image_inputs.json` holds only the shared contract keys (Skill 49's
   wrappers refuse any other key) and `order-page-inputs.json` holds the same values in the shape Skill 78 reads.
6. `assemble` requires every page's designs by default. `--allow-no-designs` exists for old-style plan-only
   packages and is recorded in the manifest as `designs_required: false`.

## Build order and parallel lanes

Every page is independent: the look they share travels in the image inputs file, so no page waits for another.
With workers, Skill 49 starts every page together, the landing page too (`lane_plan.phase_1_alone` is empty and
`phase_2_together` holds every page). Built one at a time (`--parallel 1`, or a Skill 49 with no parallel mode),
the landing page goes first and the report says so. `--parallel N` (default: the runner profile's worker
count, the same as Skill 49's own `auto`) is passed to Skill 49's dispatch when
that dispatcher has a `parallel` argument; if it does not yet, the report says `serial (...)` instead of
claiming parallel. The plan is always reported: `dispatch-report.json` -> `lane_plan`.

## The client's questions (the guided interview)

The client interview runs on the shared guided intake (`shared-utils/client_intake/`, the same
question bank and answers file every harness uses) in Black Friday mode. `python3 -m
launcher_core.cli questions --answers answers.json` prints the ONE next applicable question as
data — plain text, why we ask, at most three choices plus "I'm not sure, help me", every
per-option explanation, nested help examples, the safe default and its flag — and the run's
computed length estimate over the applicable questions only. One question at a time, never a
batch, never the raw bank.

The seasonal questions come first and are part of this same interview: promotion dates, the
offer (any discount or bonus), real limitations, existing vs new buyers, and delivery and
follow-up. The three picture questions (look A/B/C, image service, picture ceiling) are part
of it too — they are not the whole interview. The client's assistance preference (A "set it up
for me to review", B "help me choose", C "I know what I want") is asked first and can change
mid-flow. "I don't know" is a help request: it opens coaching and is never recorded as an
answer. A harness asks each question its own way (a structured picker in Claude Code or
claude-nine, a numbered chat message in OpenClaw) and records the same answers in the one
answers file; the intake's recorded picture choices land in `image_plan`. Copy never invents
urgency or scarcity — real dates and real limits only.

The intake carries an optional `image_plan`; its shape check and resolution (defaults, the
never-default money and ownership rules) are unchanged below.

| Choice | If the client does not know | Never defaulted |
| --- | --- | --- |
| design style (A Block, B Circle, C Hybrid) | Style A, flagged "to confirm" | |
| image service | the standard service (kie), flagged | an unbuilt service (agnes, other) is refused by name |
| picture ceiling | a practice run only: a free ceiling, flagged | a real run: the ceiling and the written approval to spend |
| brand file and owner | stops with plain help (three palettes, or colors from the logo or website) | always required |

Every default is recorded in `to_confirm` with a reason and a one-line way to change it, travels into the
manifest and receipt, and is read out at delivery by `launch_bridge.summary_lines`.

Design style note for the integrator: Skill 71's `write_intake.py` accepts only `client_choice` and
`recommended_accepted` as the style source and its gate `gate:intake_design_style` closes only on those. The
bridge records `design_style_source: "default_to_confirm"` for a defaulted style; the intake lane must add
that value to Skill 71 before a production run can close with it.

## What the package must hold (AF-LAUNCH-PAGE-DESIGNS)

For every page, desktop and mobile wireframe sections and review PDF, desktop and mobile mockup sections and
review PDF, and an overview board, each file labeled with its own page (`upsell-1_DESKTOP_WIREFRAMES.pdf`).
The required set is read from `49-signature-funnel/structure/page_types.json` when that file exists, else the
built-in set above (the check reports which). Placeholder pictures fail a package that is not `test_only`.
The design board and the final mockups are recorded as `awaiting_client_approval` until the client approves.

## Graphics department hooks

`launcher_core/graphics_hooks.py` writes the SOP-GIP-02 image QC request and the SOP-GIP-03 delivery record.
It never uploads or publishes; with no live hosted link it records the missing capability. Skill 71 carries
the AF-G1..AF-G8 list as data, the independent reviewer model rule, the text read-back and logo accuracy
checks, and the text-capable model and PNG rule (see `71-blackceo-signature-page/references/qc-contract.md`).

## Out of scope (recorded follow-ups)

The package ends at approved local files. Skill 44, 50 and 06 install steps, live link checks, SOP-DIU-602,
607 and 610 wiring, the SOP-07 and Skill 06 registry registration of Skill 83, the Command Center launch
view, and the 999 package parity gap are not built here. SKILL.md's Entry now lists `dispatch` and
`questions` beside the other commands, matching `launcher_core/cli.py`, and its "It does not build pages"
line remains true: this skill composes the page-results Skills 71, 78, 79, 80, 81 and 82 return, it does
not author them. A wording drift is left in SKILL.md's Entry — it spells `--landing-pages <file>` where
`cli.py` takes a comma list (`landing,sales`) — and the turn-on workflow owns SKILL.md, so this file is
authoritative until that branch merges.
