# Skill 44 — Automation Template Library

The **28 proven email / SMS / multichannel automation sequences** Skill 44 reuses BEFORE wiring a
GoHighLevel workflow from scratch. This is the Skill-44 counterpart of the Skill-6 funnel template
library (`06-ghl-install-pages/funnel-templates/`), and the two are paired by the funnel→automation
link map in `_links/`.

## Categories (28 templates)

| Category | Count | What lives here |
|----------|------:|-----------------|
| `welcome-indoctrination/` | 3 | Soap Opera, new-subscriber indoctrination, attractive-character bonding |
| `sales-close-sequences/` | 7 | The 3 Closes, scarcity/deadline close, abandoned-cart recovery, soap-opera (sales-close variant), Seinfeld daily |
| `engagement-broadcast/` | 7 | Daily Seinfeld, re-engagement/win-back, newsletter/value broadcasts |
| `funnel-specific-followups/` | 6 | Webinar reminder/replay, application/booking nurture, free-plus-shipping OTO recovery, membership |
| `multichannel-automation/` | 5 | Post-opt-in multichannel stack, SMS/WhatsApp/DM, behavioral retargeting, branching |

> Note: `soap-opera-sequence` exists in BOTH `welcome-indoctrination/` and `sales-close-sequences/`
> (different copy/intent). The matcher and link map resolve it by the **qualified `group/id` key** —
> never by bare id — so the correct variant is always selected (regression-locked in
> `tests/test_automation_matcher.py`).

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
