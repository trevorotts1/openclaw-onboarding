# camera_shot_rules — DEL-16 camera rules (PKG-07-U2)

The shot-planner rules layer: the camera vocabulary every shot brief
carries, and the rules the plan must pass. The same rules run for music and
for dialogue or narration alike — one vocabulary, one gate, one set of
reason codes.

Stdlib only. Nothing here reads outside the skill folder. The optional
enrichment source is this skill's own `references/camera-vocabulary.json`
(PKG-07-U1); when it is absent the built-in vocabulary below is complete on
its own.

## Planning ranges, not measured standards

Every pacing percentage and clip-length number in this package is a
**planning range, not a measured standard**. They are planning aids the
rules check against; they are not measured results and must never be
presented as such. The numbers:

| Planning range | Value |
|---|---|
| Default clip length | about 4 to 6 seconds |
| Extreme wide clip length | about 6.5 to 9.0 seconds |
| Extreme close clip length | about 2.0 to 3.5 seconds |
| Medium share of a narrative plan | 50% to 70% |
| Close-up share cap | 35% of coverage |
| Long-video threshold | 2 minutes and up |

Shot length shrinks as shots get closer: about eight seconds for extreme
wides down to about two and a half seconds for extreme close-ups. Medium
shots dominate narrative film; over-used close-ups hurt the sense of space.
Close-ups at most thirty-five percent of coverage. At most two identical
framings in a row. Every scene starts on an establishing wide. Videos of
two minutes or more carry at least five shot types and three angles.

## The rules, in the order they run

1. **One camera move per clip** and clips of about four to six seconds
   (planning range, not a measured standard; the per-framing ladder above
   is authoritative when the framing is not medium).
2. **Whip pans and fast orbits are built as an edit transition between two
   clips.** They fail in AI models as a single generated move and are never
   one; a transition of those kinds must bridge two real, different clips.
3. **Text and logos are added in post.** They live on the brief's
   `text_overlay_post` / `logo_overlay_post` fields and never enter the
   generation prompt.
4. **Prompt with the phrase "shallow depth of field" rather than an f-stop
   number** — lens and f-stop words act as style cues. The lens and
   aperture live in the brief's structured fields only; prompts with an
   f-stop or a millimeter number are refused.
5. **Shot length shrinks as shots get closer** (the ladder in the table).
6. **Medium shots dominate narrative film**; over-used close-ups hurt the
   sense of space.
7. **Close-ups at most thirty-five percent of coverage** (planning range,
   not a measured standard).
8. **At most two identical framings in a row.**
9. **Every scene starts on an establishing wide.**
10. **Videos of two minutes or more carry at least five shot types and three
    angles.**
11. **Lens and aperture matched to emotion** — an 85 mm wide-open lens on
    an intimate beat, a 24 mm stopped-down lens on an epic one.
12. **Coverage spans master, medium, close-up, reverse, insert and
    cutaway**, with the one-hundred-eighty-degree rule, eyelines, scene
    geometry, shot-reverse-shot, motivated camera moves, rack focus, depth
    of field, golden-hour or low-key lighting choices and screen-direction
    continuity.

## The vocabulary every brief carries

- **Framings:** establishing wide, extreme wide, wide, medium, medium
  close, close, extreme close, insert, detail.
- **Angles:** eye, low, high, bird's-eye, dutch.
- **Camera moves:** static, pan, tilt, dolly-in, dolly-out, tracking,
  pedestal, zoom, handheld, crane, orbit, push-in, pull-back, rack-focus
  (static through crane moves; one per clip).
- **Edit transitions (never a generated move):** whip-pan, fast-orbit.
- **Lenses:** 24, 35, 50, 85 millimeter.
- **Apertures:** f/1.4 through f/16, from wide open to stopped down.
- **Coverage roles:** master, medium, close_up, reverse, insert, cutaway.
- **Lighting:** golden-hour, low-key, daylight, night, studio-soft,
  overcast.
- **Eyelines:** screen-left, screen-right, center. **Camera sides:** a, b
  (the line). **Screen directions:** left, right.
- **Content modes:** music, dialogue, narration.

## Usage

```python
from camera_shot_rules import build_shot_brief, run_rule_checks

brief = build_shot_brief(
    shot_id="s1", framing="establishing_wide", angle="low",
    camera_move="dolly-in", lens_mm=24, f_number=8.0,
    emotion="epic", content_mode="music",
    camera_motivation="open the world")
result = run_rule_checks([brief])
assert result["outcome"] == "ok", result["reasons"]
```

CLI (same envelope and exit-code map as the control CLI: ok 0, error 1,
waiting 2, parked 3, rejected 4):

```bash
python3 scripts/camera_shot_rules/cli.py vocabulary
python3 scripts/camera_shot_rules/cli.py plan  --specs specs.json
python3 scripts/camera_shot_rules/cli.py check --plan plan.json
```

## Tests

```bash
python3 scripts/camera_shot_rules/test_del16_rules.py
```

The suite covers every rule above with a positive and a negative case, for
music and for dialogue or narration. A check that cannot discriminate a
good plan from a bad one fails the suite.
