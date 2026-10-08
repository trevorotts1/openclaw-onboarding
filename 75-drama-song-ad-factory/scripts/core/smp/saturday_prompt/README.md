# core/smp/saturday_prompt (SMP-W1-U3)

Saturday theme prompt line for the weekly drama song — Owner D27 / plan section
6.15, decision log 35 (2026-10-07).

## What it does

Adds exactly one line to the Skill 35 Saturday theme question:

    Drama song of the week: keep <current style> or change it?

Rules (plan 6.15): **no answer means keep** — the style persists across weeks.
A reply naming a style becomes the style shown on next Saturday's prompt. A
bare "change" with no replacement cannot be applied, so it keeps the current
style rather than inventing one.

State: **one JSON file**, imported from `initial_questions.DEFAULT_STYLE_PATH`
(`~/.openclaw/workspace/social-media-planner/drama-song-style.json`, or
`/data/.openclaw/...` on a box that has it — M8). It is the same flat record
the setup block writes and the weekly step reads, under the shared `length`
key, so a change made on Saturday is the style Sunday's run uses (H6).
Atomic write; a corrupt or missing file falls back to the D24 defaults
(Lifelike 3D / Soul Ballad / All Suno / 60 seconds). The fields this module
does not own — on/off, call to action, brief fields — are carried over from
what is already on disk, so Saturday only ever rewrites look, music, voice,
length and the phrase it shows.

## Scope

Prompt building and parsing only. No Skill 74 / Skill 75 call, no network, no
transport, no media, no operator paths — the weekly drama-song step (SMP-W1-U1)
owns production, and **Skill 74 is the only KIE path** (active mode only;
otherwise the planner skips the video and says why).

## Run the tests (mocked, zero paid calls)

```bash
python3 core/smp/saturday_prompt/test_saturday_prompt.py -v
# or
python3 -m unittest discover -s core/smp/saturday_prompt -p "test_*.py"
```

## CLI

```bash
python3 core/smp/saturday_prompt/saturday_prompt.py                  # print this week's prompt
python3 core/smp/saturday_prompt/saturday_prompt.py --apply --reply "change to Sketch to Life"
```

Ships only via the onboarding batch train.
