# Motion Grammar: Skill 72

This is the design constitution for every animation the skill produces. The model writing animation code reads this file along with `references/animation-contract.md` and the brand bible. The pipeline is proven; this file is what keeps the pipeline from producing generic-looking video. `scripts/lint-grammar.py` checks animation files against the machine-checkable parts of this grammar.

Motion is chosen by meaning, not by habit and not by ban list. Every scene declares one intent and a small set of behaviors in its `window.__choreography` block, and the linter checks the declaration against the vocabulary mirrored in `references/choreography-vocabulary.json`. This document is the human source of that vocabulary; the JSON is its machine-readable mirror, and the unit tests fail when the two drift apart. A scene whose only event is text appearing is a planning failure, not a choreography choice: motion serves the story beats, and most explanatory beats are carried by images, charts, diagrams, and demonstrations, with type in a supporting role.

## Intents

Pick the intent from the story beat the scene serves. One scene carries one intent.

| Intent | The beat it serves | Permitted behaviors |
|---|---|---|
| `continuous_data_change` | A chart, counter, or measured quantity develops over time and the viewer reads the values as they change | linear, eased, mask, hold |
| `decisive_reveal` | A subject, claim, or product detail lands once, clearly, and stays readable | mask, eased, spring, hard_cut, hold |
| `spatial_travel` | A subject moves through a space or layout, and the movement itself explains a relationship, a journey, or a mechanism | eased, spring, depth, mask, hard_cut, hold |
| `emotional_dissolve` | One shot or state gives way to another for feeling: a memory, a passage of time, a softening between testimonial beats | dissolve, eased, mask, hold |
| `stable_explanation` | A presenter, diagram, or composed frame explains while staying essentially still, so reading is never interrupted by motion | hold, hard_cut, eased, mask |

Notes per intent:

- `continuous_data_change`: spring is not permitted. A spring that overshoots a data mark misstates the value (see Data marks). A container around the chart may spring; the marks themselves may not.
- `decisive_reveal`: the reveal is the event, and it ends in a hold long enough to read. Overshooting spring forms suit physical, playful subjects; they never carry essential text or data.
- `spatial_travel`: a camera move alone does not prove anything. The traveling subject must carry the meaning.
- `emotional_dissolve`: the only intent that permits dissolve. A dissolve is a chosen emotional beat, never the default join between every pair of shots.
- `stable_explanation`: stillness is the point. Call-to-action frames use this intent so the ask gets its full reading time.

## Behaviors

| Behavior | What it is | When it earns its place |
|---|---|---|
| `linear` | Constant-rate interpolation between two states | Data marks and measured change; the value at every frame is the true interpolated value |
| `eased` | Non-linear interpolation with an easing curve that does not overshoot the target | Travel, reveals, and pushes that should feel weighted without lying about values |
| `spring` | Spring physics toward a target, using the named presets below | Physical subjects, containers, playful pops; never on data marks |
| `hard_cut` | An instantaneous change of state or framing at a frame boundary | Decisive changes, beat hits, swaps inside a stable explanation |
| `dissolve` | A controlled opacity crossfade between two states or shots, computed from the frame clock | Emotional beats, only under `emotional_dissolve` |
| `mask` | A reveal or concealment through a mask or clip path | Entrances where the subject itself should appear, masked-word typography, wipes that reveal a plot or a place |
| `depth` | Motion staged in depth: perspective, layered parallax, or a genuine 3D scene | Spatial stories; the scene design record states whether the depth is 2.5D layered composition or genuine 3D, per the compositing rules |
| `hold` | A deliberate still interval; the frame is composed and readable | Reading time, presenter beats, call-to-action frames, the beat after a reveal |

## Springs

Springs are one behavior among eight, not the whole grammar. Where a spring is the right choice, use these four named presets and name them in code so the choice is reviewable:

| Preset | Use for | Stiffness | Damping | Feel |
|---|---|---|---|---|
| `weighty` | Display type, logo lockups, camera moves | 170 | 22 | Heavy, confident, settles once |
| `panel` | Cards, panels, containers | 230 | 26 | Solid, quick, no overshoot |
| `snap` | Buttons, pills, indicators, small pops | 330 | 25 | Fast, crisp, tiny overshoot allowed |
| `drift` | Ambient background motion, held shots | 55 | 14 | Slow, barely-there, never distracting |

A spring helper takes `(t, target, preset)` and returns the current value as a pure function of t. Settle means the value is within 0.5 percent of target and stays there; nothing keeps creeping after its last keyframe. The `snap` preset overshoots by design, which is exactly why springs stay off data marks.

## Data marks

Data marks never overshoot. When a scene animates data marks (chart bars, line points, counters, any element whose position or size encodes a value), spring is never applied to the marks themselves, because an overshooting spring temporarily states a value the data does not contain. Marks interpolate linearly or with a non-overshooting ease, on the data scale, and stop at the true value. Containers, labels, and non-data subjects in the same scene may spring. This section states the choreography side of the chart contracts; the data side lives with the chart rules.

## Coherence

A sequence speaks a small vocabulary, not the whole catalog. The limits, mirrored in `references/choreography-vocabulary.json`:

- One intent per scene.
- Per scene: at most 3 behaviors in one scene, declared in its `window.__choreography` block.
- Per sequence: at most 5 distinct behaviors across a whole sequence.

The linter enforces the two per-scene numbers; the sequence number is review doctrine for the planner and the orchestrator. A scene that reaches for every behavior at once has no vocabulary; it has noise, and it fails creative review even if each effect is well made.

## Event alignment

Events align on the shared timeline, nowhere else. The timeline compiler resolves global and scene-local times once, into integer half-open frame intervals, and every cue (a visual hit, a word, a beat from `beats.json`) is authored at its compiled timestamp on that timeline. There is no universal early shift: an earlier version of this grammar scheduled every visual hit 2 frames before its beat, and that rule is gone. If a hit reads late or early in review, fix that cue's authored timestamp, not the whole timeline. Audio is never shifted to match picture. Verify alignment two ways before a scene passes: perceptually, by watching the rendered scene, and by cue timestamps, by checking the compiled cues against the frame the event actually lands on.

## Holds and reading time

A hold is a first-class behavior, chosen on purpose. Purposeful stillness gives the viewer time to read, to feel a beat land, and to act on a call to action. Call-to-action frames hold for their full authored reading time in the timeline; nothing cuts them short to keep a pace quota. A hold is composed stillness, not an empty frame: the frame is designed, lit, and readable for its whole duration. Micro-motion inside a hold (a slow push of 1.00 to 1.03, a gentle drift) is allowed when it serves the scene and the declared intent permits it; it is never required to rescue a hold from looking still. Stillness that reads as a frozen render is a composition problem, fixed in the frame design, not by adding motion.

## Art direction: bright and human

The owner's default is bright, real, and human: natural light, real people, honest color, scenes that look lived in rather than rendered. That default is art direction, not a mandate that every scene be flat white minimalism. A scene may be warm, saturated, photographic, layered, or staged in genuine depth when the story calls for it. What the default forbids is the generic look: dark, moody, over-polished, unmistakably machine-made. When a scene departs from bright and human, the departure is a story choice recorded in the scene's design notes, not an accident of a template.

## Enter and exit patterns

Pick per element, under the scene's declared intent, and vary across a video: rise through a mask; grow out of an anchor (scale 0.85 to 1.0); type-on; skeleton to content build; card rise; a hard cut on the beat. Exit patterns: lift back through the mask; get covered by the incoming element; get pushed past camera; collapse into a replacement; hard cut. Opacity has honest jobs in this grammar: it is the dissolve behavior under `emotional_dissolve`, and small eyebrow or sub lines may fade over 6 frames or fewer. What fails review is the fade used as the universal entrance for everything, because a fade chosen by default carries no meaning. The same logic retires the old blanket rules on crossfades and playful overshoot: a crossfade is right when the intent is emotional, wrong as the join between every pair of shots; an overshooting pop is right on a mascot, a toy, or a playful product moment, wrong on essential text and data.

## Banned cliches

Never ship any of these. They are the fastest way to make a video look cheap:

1. A centered title sitting on a gradient background.
2. Glow effects on interface chrome or type.
3. Generic particle bursts to suggest excitement.
4. Corner labels, frame borders, or vignette overlays as decoration.
5. Spins, glitches, or light leaks used without a story reason.
6. Random effects with no declared intent: any motion the scene cannot justify by its story beat.
7. Every effect at once: a scene or sequence that blows past the coherence limits to show range.

## Masked-word typography

1. Words enter by rising through a mask, never by fading in.
2. Masked words start at least 140 percent of their cap height below the mask edge, so no glyph tops peek through on the first frame.
3. Swaps are sequential: the outgoing line is fully gone before the incoming line lands. At most one frame of overlap is allowed, and in that frame the outgoing line must be at least 95 percent gone.
4. No caret or cursor survives after its line leaves.
5. Readability sizing follows the role-based type hierarchy in the design tokens (display, headline, body, caption roles), not a single universal pixel floor. Text is left aligned, sentence case, in the brand's real typeface.

## Safe zones

**9:16 vertical:** keep key content out of the top 14 percent (platform header), the bottom 20 percent (captions and controls), and the right 12 percent (action rail). Compose inside what remains; do not just center-crop the 16:9 frame.

**16:9 horizontal:** keep titles, logos, and calls to action inside a centered 90 percent safe area. Nothing important touches the frame edge.

## Pacing

1. In energetic sequences, something new happens on screen every 2 to 4 seconds. A declared hold is exempt by design: its stillness is the event.
2. The hook reads in the first 2 seconds. Frame 0 is never empty or black.
3. Hard cuts land on bar lines. Inner events land on beats or half beats from `beats.json`, never on hard-coded seconds.
4. The end card is a deliberate hold, usually a call to action under `stable_explanation`, timed in the timeline for its full reading time.
