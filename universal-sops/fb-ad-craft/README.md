# Fb Ad Craft SOP Cluster (`universal-sops/fb-ad-craft/`)

The SHARED, cross-department execution playbook for this craft. It does NOT re-implement the skill; the authoritative machine spine lives in the numbered skill folder. The SOP/manifest files in this directory govern the procedure; the Intent-triggers header below (generated from the skill-department map) states which plain-language client intents route here.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/fb-ad-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **48** facebook-ad-generator | "make me Facebook ads" · "make me Instagram ads" · "10 ad variations" · "a batch of ad creatives" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->
