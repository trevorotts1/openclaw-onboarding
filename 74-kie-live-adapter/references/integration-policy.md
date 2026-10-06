# Integration policy

## Trust states for the vendor package and for any discovered model

| State | Meaning | What is allowed |
|---|---|---|
| PINNED | An operator or department pinned this model (for example the fleet image pin). | Used exactly as pinned. The adapter passes it through and never overrides it. |
| APPROVED | Reviewed by a human; fingerprint recorded in vendor-approval.json. | Canary probe compares against it. |
| DISCOVERED | Seen in the live catalog, not reviewed. | Listed by `discover`. Never auto-routed. A human or a department manifest must choose it. |
| BLOCKED | A human refused it. | Never used. |
| UNKNOWN-DRIFT | The live catalog, a schema, or the vendor package changed since the last receipt or approval. | Treated as unreviewed. Static skills 66, 67, 68 keep working; the drift receipt is the work item. |

A model or schema moves from DISCOVERED or UNKNOWN-DRIFT to a decision only through a person. The adapter records, it does not decide.

## Ownership boundaries

- Skills 66, 67, 68 own model choice, prompt rules and visual QC. Skill 74 owns mechanics: discover, validate, upload, submit, poll, save.
- Skill 07 owns the account and credential setup. Skill 46 owns callback relay.
- The caller owns fallback. The adapter never picks a different model.
- AGENTS.md fleet pins are not edited by this skill.
- The Presentations department keeps its own canonical render path. Skill 74 is never placed in or imported from a deck run directory.
- KIE is not registered in provider_adapters.py (chat only).
- The vendor package (kie-models, kie-chat-agents) is instruction text. It is never a runtime dependency and never installed on client boxes. Only vendor_skill_probe.sh installs it, into a throwaway HOME, on a canary.

## Rollout

Ship in shadow. An operator may set active on one box after live_smoke.sh passes. Fleet-wide active is a separate decision.
