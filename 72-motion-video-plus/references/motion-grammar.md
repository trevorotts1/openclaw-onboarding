# Motion Grammar: Skill 72

This is the design constitution for every animation the skill produces. The model writing animation code reads this file along with `references/animation-contract.md` and the brand bible. The pipeline is proven; this file is what keeps the pipeline from producing generic-looking video. `scripts/lint-grammar.py` checks animation files against the machine-checkable parts of this grammar.

## Banned cliches

Never ship any of these. They are the fastest way to make a video look cheap:

1. A centered title sitting on a gradient background.
2. Everything fading in. Opacity fades are not entrances.
3. Glow effects on interface chrome or type.
4. Generic particle bursts to suggest excitement.
5. Crossfades used as transitions between shots.
6. Corner labels, frame borders, or vignette overlays as decoration.
7. Spins, glitches, or light leaks used without a story reason.
8. Bounce easing on interface elements (bounce belongs to mascots and toys, never to UI or type).

## Motion: springs only, with named presets

All motion uses spring physics, computed inside `window.__setTime(t)` as a pure function of t. No easing curves, no linear tweens. Use these four presets and name them in code comments so the intent is reviewable:

| Preset | Use for | Stiffness | Damping | Feel |
|---|---|---|---|---|
| `weighty` | Display type, logo lockups, camera moves | 170 | 22 | Heavy, confident, settles once |
| `panel` | Cards, panels, containers | 230 | 26 | Solid, quick, no overshoot |
| `snap` | Buttons, pills, indicators, small pops | 330 | 25 | Fast, crisp, tiny overshoot allowed |
| `drift` | Ambient background motion, held shots | 55 | 14 | Slow, barely-there, never distracting |

A spring helper takes `(t, target, preset)` and returns the eased value. Settle means the value is within 0.5 percent of target and stays there; nothing keeps creeping after its last keyframe.

Enter patterns (pick per element, vary across a video): rise through a mask; grow out of an anchor (scale 0.85 to 1.0 with opacity snapping in within 4 frames); type-on; skeleton to content build; card rise. Exit patterns: lift back through the mask; get covered by the incoming element; get pushed past camera; collapse into its replacement; hard cut. A pure opacity fade is never an enter or an exit. Only small eyebrow or sub lines may fade, and only over 6 frames or fewer.

## Hits lead the beat

Every visual hit that pairs with a sound lands slightly BEFORE the beat, so it reads exactly on the beat to the viewer. Schedule visual hits 2 frames early at 30fps (about 66 ms). The audio stays exactly on the measured beat grid in `beats.json`. Never shift audio to match picture; always shift picture to meet audio.

## Masked-word typography

1. Words enter by rising through a mask, never by fading in.
2. Masked words start at least 140 percent of their cap height below the mask edge, so no glyph tops peek through on the first frame.
3. Swaps are sequential: the outgoing line is fully gone before the incoming line lands. At most one frame of overlap is allowed, and in that frame the outgoing line must be at least 95 percent gone.
4. No caret or cursor survives after its line leaves.
5. Anything that must be read is at least 28 px tall at 1080p, left aligned, sentence case, in the brand's real typeface.

## Safe zones

**9:16 vertical:** keep key content out of the top 14 percent (platform header), the bottom 20 percent (captions and controls), and the right 12 percent (action rail). Compose inside what remains; do not just center-crop the 16:9 frame.

**16:9 horizontal:** keep titles, logos, and calls to action inside a centered 90 percent safe area. Nothing important touches the frame edge.

## Rhythm

1. Something new happens on screen every 2 to 4 seconds. Nothing holds longer than one bar of the score without a new element arriving.
2. The hook reads in the first 2 seconds. Frame 0 is never empty or black.
3. Hard cuts land on bar lines. Inner events land on beats or half beats from `beats.json`, never on hard-coded seconds.
4. Every held shot keeps micro-motion: a slow push of 1.00 to 1.03, or a gentle drift. A static held shot reads as a frozen render.
5. The end card holds 2 seconds at most and is never fully static.
