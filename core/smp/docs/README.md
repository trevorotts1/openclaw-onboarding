# core/smp/docs — Skill 35 docs set for the weekly drama-song ad (plan 6.15)

**Unit:** SMP-W2-U3 · wave 2 of the Skill 35 social media planner integration
**Source:** owner decisions D27 / D35, 2026-10-07, plan section 6.15
**Builder receipt:** `run/smp-plan/lanes/SMP-W2-U3-lane/`
**Verdict:** written by the independent checker to
`run/smp-plan/evidence/SMP-W2/SMP-W2-U3.verdict.json` — this unit does not
self-approve.

## What this directory is

The complete Skill 35 docs set, **updated for the weekly planner
integration** and staged here for the onboarding batch train. These are the
source-of-truth copies; the batch train — never this unit — moves them into
`35-social-media-planner/` and `23-ai-workforce-blueprint/`.

| Staged file | Source it updates | What changed |
|---|---|---|
| `SKILL.md` | `35-social-media-planner/SKILL.md` | version 3.7.0; weekly drama song ad in the weekly content types and the owner Q&A; new **Weekly Drama Song Ad** section (module table, style state, KIE gate, length/routing, schema 1.3.0, zero paid calls) |
| `INSTRUCTIONS.md` | `35-social-media-planner/INSTRUCTIONS.md` | version 10.16.0; new **Weekly drama-song step** section: module table, where it runs, gate/length/routing rules, the Weekly Overview row |
| `INSTALL.md` | `35-social-media-planner/INSTALL.md` | version 2.1.0; new **Step 8.6** weekly drama-song setup + completion-checklist item; furnace rule preserved |
| `QC.md` | `35-social-media-planner/QC.md` | new **Weekly Drama Song Ad** content checklist; two documentation-integrity checks |
| `qc-skill35.sh` | `35-social-media-planner/qc-skill35.sh` | new **Section J** (13 static drama-song assertions); Sections A–I untouched |
| `qc-social-media-planner.sh` | `35-social-media-planner/qc-social-media-planner.sh` | comment now points at Section J; still a thin delegator |
| `scripts/weekly-batch.sh` | `35-social-media-planner/scripts/weekly-batch.sh` | version 10.16.0; `run_drama_song_step()` — one ad per batch, before the calendar gate, fail-soft |
| `scripts/run-publishing-cycle.sh` | `35-social-media-planner/scripts/run-publishing-cycle.sh` | version 10.16.0; `drama_song` block in `cycle-manifest.json`; schema 1.3.0 row-append note |
| `scripts/kie_media_plan.py` | `35-social-media-planner/scripts/kie_media_plan.py` | `drama_song` block in the printed media plan; docstring |
| `SOP--drama-song-ad-pipeline.md` | `23-ai-workforce-blueprint/templates/role-library/video/sops/SOP--drama-song-ad-pipeline.md` | **MOVED HERE → THERE (manual H1, unit W1-C-U2):** the SOP the skill already pointed at now ships where the skill pointed; `test_docs_set.py` asserts it at that canonical home, not as a staged copy in this directory |
| `test_docs_set.py` | — | mocked structural tests for this set (offline, zero paid calls) |

## The integration in one paragraph

Once a week the planner ships **one 9:16 drama song ad** cut from the week's
**Theme of the Week**. `scripts/weekly-batch.sh` invokes
`core/smp/weekly_step/` once per batch (never once per topic), which calls
Skill 75 **through Skill 74 in active mode only**; any other mode writes
`drama-song-skipped.json`, prints a plain-English client-facing reason and
exits 0 — **Skill 74 is the only KIE path, and there is never a fallback to a
private KIE client**. The planner cut ends by **59.0 s** (the 90-second option
lands in 88.0–95.0 s), 90 seconds posts only to Facebook Reels, Instagram
Reels, TikTok and LinkedIn, **Google Business Profile** is refused until a
limit is verified, and **Stories take the 15-second teaser only**. The saved
style lives in
`~/.openclaw/workspace/social-media-planner/drama-song-style.json`
(defaults Lifelike 3D / Soul Ballad / All Suno / 60 seconds), the Saturday line
adds `Drama song of the week: keep <style> or change it?`, and the week's row
lands on Weekly Overview schema **1.3.0** through
`social-planner-row-append` with style chosen, status, KIE cost, video link
and channels posted.

## Module ownership this set documents (never edits)

| Path | Unit |
|---|---|
| `core/smp/weekly_step/` | SMP-W1-U1 |
| `core/smp/initial_questions/` | SMP-W1-U2 |
| `core/smp/saturday_prompt/` | SMP-W1-U3 |
| `core/smp/length_routing/` | SMP-W1-U4 |
| `core/smp/stories_teaser/` | SMP-W1-U5 |
| `core/smp/sheet_schema_130/` | SMP-W2-U1 (sheet schema 1.3.0) |
| `core/smp/sheet_migration/` | SMP-W2-U2 (migration, row-append payload, validator) |
| `core/smp/docs/` | **SMP-W2-U3 — this unit** |

Exact sheet column names come from `config/sheet-template.schema.json`
(SMP-W2-U1). This set never invents a column name.

## Running the tests

```bash
python3 core/smp/docs/test_docs_set.py          # 0 = green, 1 = a check failed
python3 core/smp/docs/test_docs_set.py --list    # print every check
python3 core/smp/docs/test_docs_set.py --root <dir>   # run against another copy
```

Everything is offline: no network client is imported or spawned, no KIE call
is made, no media file is produced, and the shell fixtures run with `curl`,
`wget` and `nc` stubbed to fail so any network attempt fails the suite.

## Shipping

**Ships only via the onboarding batch train.** Nothing here is merged, no pull
request is opened and no file outside `core/smp/docs/` is touched. The
originals under `35-social-media-planner/` and
`23-ai-workforce-blueprint/` are not modified by this unit.
