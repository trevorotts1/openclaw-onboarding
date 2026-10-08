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

State: one JSON file (default `~/.openclaw/data/skill35/drama-song-style.json`),
atomic write, corrupt/missing file falls back to the D24 defaults (Lifelike 3D /
Soul Ballad / All Suno / 60 seconds).

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
