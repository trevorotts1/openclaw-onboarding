# Anthology Writer — Intake Template (one contributor / one chapter)

Fill ONE of these per contributor. The four required fields must be present and
non-empty before any authoring runs. **Do not put any API key / token / secret in
this file** — provider keys are resolved per box from the client's own OpenClaw
config, never through intake (`AF-AW-INTAKE-CREDENTIAL`).

```json
{
  "anthology_title": "<the book this chapter belongs to>",
  "first_name": "<contributor first name>",
  "last_name": "<contributor last name>",
  "chapter_premise": "<what this chapter is about and the turn it makes>",
  "ideal_avatar": "<the contributor's ideal-reader / avatar description>",
  "niche": "<the contributor's niche>",
  "primary_goal": "<the contributor's primary goal>",
  "personal_stories": [
    "<short distinctive phrase for a real lived moment>",
    "<another real anchor>"
  ],
  "subtitle_hint": "N/A",
  "target_reader": "<who this chapter is for>",
  "tone_influences": ["<figure 1>", "<figure 2>", "<figure 3>", "<figure 4>"]
}
```

- `personal_stories` may be the literal string `"N/A"` if the contributor has no
  personal story; then the placement gate is vacuously satisfied.
- `tone_influences` may contain `"N/A"` slots — resolved deterministically by the
  shared tone-core F4.3 selector (`tone_persona_autopick.py` → `persona_for_job.py`),
  never by prompt-level self-pick; every pick is logged.
