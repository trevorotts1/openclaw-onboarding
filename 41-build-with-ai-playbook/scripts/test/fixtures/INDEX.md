# Seeded-defect fixtures -- Skill 41 v1.3.0 L3 Big-Brother core

These are the section-6 seeded-defect fixtures the Big-Brother QC core (the autonomous,
human-last reviewer) MUST catch before a Build-With-AI workflow is published. Each file is a
static JSON snapshot of a "built workflow" -- there are **no credentials, no live URLs, and no
real contact data** anywhere in this folder. Every value is fabricated test data.

L3 (`scripts/test/L3-seeded-defect.sh`) runs the scanner (`hf_bigbrother_scan` in
`lib-harness.sh`) against each fixture and asserts:

1. The CLEAN fixture produces **zero** defects (positive control -- catches a scanner that
   over-flags).
2. Each DEFECT fixture produces **exactly** its `expect_defects` set (catches a scanner that
   under-flags or mis-classifies).

| Fixture | Defect code | What the core must catch |
|---|---|---|
| `clean-workflow.json` | (none) | A fully correct workflow -- must scan clean |
| `defect-D1-missing-dependency.json` | `D1_MISSING_DEPENDENCY` | Tag/field/value referenced but never created (dependency-first rule) |
| `defect-D2-unfiltered-trigger.json` | `D2_UNFILTERED_TRIGGER` | Trigger with empty filters and no explicit allow-everyone |
| `defect-D3-no-none-branch.json` | `D3_NO_NONE_BRANCH` | If/Else with branches but no None/fallback branch |
| `defect-D4-missing-zhc-prefix.json` | `D4_MISSING_ZHC_PREFIX` | Agent-created tag/field missing the ZHC-/ZHC_ prefix |
| `defect-D5-refire-unguarded.json` | `D5_REFIRE_UNGUARDED` | Repeat-capable trigger with no re-fire guard |
| `defect-D6-webhook-full-url.json` | `D6_WEBHOOK_FULL_URL` | Webhook storing a full URL containing a token/secret |
| `defect-D7-pii-in-log.json` | `D7_PII_IN_LOG` | Event line carrying raw PII (email/phone/key) |

Each defect code maps 1:1 to the protective rule it defends: dependency-first (D1),
trigger filters (D2), If/Else None branch (D3), ZHC prefix (D4), re-fire guard (D5), webhook
URL-domain-only logging (D6), and the f52 PII discipline (D7).

If you add a new protective rule to Skill 41, add a matching `defect-DN-*.json` here AND a
detector clause in `hf_bigbrother_scan` -- the fixture is the proof the rule is enforced, not
just described.
