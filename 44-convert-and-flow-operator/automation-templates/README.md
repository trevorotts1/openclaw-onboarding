# Skill 44 — Automation Template Library

Skill 44 contains **49 template-shaped JSON files across two families**: 28 editorial sequence templates in the five legacy category directories, plus 21 launch-family build specs (`launch-a/` 11, `launch-ai/` 1, `launch-b/` 4, `launch-c/` 4, `launch-text/` 1). The `automation_template_count` field in `_links/funnel-to-automation.json` is **generated from disk** by `_links/_build_link_map.py` and must never be hand-edited.

This is the Skill-44 counterpart of the Skill-6 funnel template library (`06-ghl-install-pages/funnel-templates/`), and the two are paired by the funnel→automation link map in `_links/`.

## Editorial library (28 templates)

| Category | Count | What lives here |
|----------|------:|-----------------|
| `welcome-indoctrination/` | 3 | Soap Opera, new-subscriber indoctrination, attractive-character bonding |
| `sales-close-sequences/` | 7 | The 3 Closes, scarcity/deadline close, abandoned-cart recovery, soap-opera (sales-close variant), Seinfeld daily |
| `engagement-broadcast/` | 7 | Daily Seinfeld, re-engagement/win-back, newsletter/value broadcasts |
| `funnel-specific-followups/` | 6 | Webinar reminder/replay, application/booking nurture, free-plus-shipping OTO recovery, membership |
| `multichannel-automation/` | 5 | Post-opt-in multichannel stack, SMS/WhatsApp/DM, behavioral retargeting, branching |

The 21 launch-family build specs are documented separately in `launch-a/`, `launch-ai/`, `launch-b/`, `launch-c/`, and `launch-text/`.

> Note: `soap-opera-sequence` exists in BOTH `welcome-indoctrination/` and `sales-close-sequences/`
> (different copy/intent). The matcher and link map resolve it by the **qualified `group/id` key** —
> never by bare id — so the correct variant is always selected (regression-locked in
> `tests/test_automation_matcher.py`).

## Machine-readable template schema (schema_version 2.0.0)

Every template carries `schema_version: "2.0.0"` and `kind: "single_message" | "sequence_stack"`.

A template that the matcher may offer as buildable MUST carry a `build_graph` array of nodes shaped as `{"id","type","after"?,"branches"?,"attributes"}`:

- `type` must be `trigger` or an engine `VERIFIED_ACTION`.
- Exactly one `trigger` node must exist, and it must have no `after`.
- Every value in `after` and `branches` must resolve to a node ID in the same graph.

Today, 12 templates carry a graph. The generated list lives in `_matcher/buildable-templates.json`. The remaining 37 templates are prose-only and are **NOT buildable** until a graph is authored.

Validate templates with `_schema/apply_template_schema.py --check`. The validator exits non-zero when a template lacks `schema_version` or `kind`, or when a graph is malformed.

## STEP 0.4 — Flexible Template Match (how it is used)

Before PLAN MODE, Skill 44 runs the matcher (`INSTRUCTIONS.md` Step 0.4):

```bash
python3 _matcher/cli.py --match "<outcome + channel + audience>" --json     # reads _matcher/catalog-index.json
python3 _matcher/cli.py --build-index                                       # rebuild the lexical index (portable)
python3 _matcher/cli.py --expand <funnel_template_id>                       # expand a funnel's linked follow-ups
```

- Shared matcher core: `_matcher/flex.py` (intent-mode detection + decision mapping — the SAME core
  the Skill-6 funnel matcher mirrors).
- Matcher: `_matcher/automation_matcher.py`. Committed lexical index: `_matcher/catalog-index.json`
  (portable — relative paths, no operator-local path).
- **Flexibility = guide-not-rule:** EXPLICIT user spec → build THAT (template = optional reference);
  UNSURE → suggest + await confirm; HANDS-OFF → build from the template; nothing fits → CREATE_NEW +
  `save_new_template`. Never imposes; never blocks a build.

## `_links/` — funnel→automation map (the complete-funnel handoff)

- `funnel-to-automation.json` — **canonical (v2)**, `links[]` array, generator-backed by
  `_build_link_map.py`. Maps every one of the 38 funnel templates to its recommended primary +
  secondary + graduation follow-up automations, keyed by `funnel_template_id`. Read by both matchers
  and the CLIs.
- `funnel-to-automation-link-map.json` — **DEPRECATED (v1)**, category-keyed, human-readable only.
  Not read by any code; a parity test keeps its coverage in sync with v2.

## Activation on a box

The matcher is env-gated (DARK by default). `tools/engine/wire-ghl-env.sh` exports
`CAF_AUTOMATION_CATALOG` / `CAF_AUTOMATION_INDEX` / `CAF_FUNNEL_AUTOMATION_LINKS` (and the Skill-6
`GHL_FUNNEL_*` vars) onto the persistent dept agent. Sample-match to confirm.

## Build-quality gate

Every built workflow is held to **WF-1..21 PASS + FAB-QC ≥ 8.5**. The FAB-QC overlay
(`shared-utils/fab_qc.py`, rubric `universal-sops/funnel-automation-build-quality-rubric.md`) is run
by `qc-built-workflow.sh <wf-id> --fab` (INSTRUCTIONS Step 9.3c) and scores template fidelity, copy
substance, render/soundness, persona grounding, flexibility honored, and funnel↔automation link
integrity.
