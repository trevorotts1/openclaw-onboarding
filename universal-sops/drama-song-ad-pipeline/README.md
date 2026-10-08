# Drama Song Ad Pipeline SOP Cluster (`universal-sops/drama-song-ad-pipeline/`)

The SHARED execution playbook face of **Skill 75 — the Drama Song Ad Factory**: a sung
direct-response story with music, storyboard, generated clips, assembly and delivery, driven
end to end through the shared Python control layer (intake, preflight, spend ledger, state
store, quality-check gates).

This cluster is the `universal-sops` face of the capability (parallel to
`video-pipeline-craft/`, `fb-ad-craft/`, `book-writer-craft/`). It does NOT re-implement the
engine. The authoritative machine spine lives in the skill folder:

- `75-drama-song-ad-factory/` — intake preflight, shared canonical core (state/ledger/qc
  timing/assembler/delivery), Command Center ad-campaigns integration, fault-boundary suite.
- The canonical 12-stage pipeline SOP lives in the video department roster at
  `23-ai-workforce-blueprint/templates/role-library/video/sops/SOP--drama-song-ad-pipeline.md`
  (installed on-box with the role-library materialization; manual H1).

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/drama-song-ad-pipeline/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **75** drama-song-ad-factory | "make me a drama song ad" · "produce a drama-song advertisement" · "song ad for my product" · "create a music-driven ad campaign" · "run a drama song factory job" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->
