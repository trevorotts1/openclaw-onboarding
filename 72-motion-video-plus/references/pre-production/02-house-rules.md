# Pre-production 02: House rules

The rules every later step relies on. Read them, then read `references/motion-grammar.md` for the full design constitution.

## Render contract

- Every scene is a pure function of time: `window.__setTime(t)` paints frame t, in any order, cold or after any other frame.
- No CSS transitions, no CSS animations, no setTimeout, no setInterval, no requestAnimationFrame-driven motion, no state carried between frames. Seeded randomness only, never `Math.random`.
- No GPU-layer tricks (`translate3d`, `translateZ(0)`, `will-change`): a composited layer caches its raster, so the same t can paint differently depending on the previous frame. Fake depth in 2D (skew, scale, shadow) or draw it on canvas.

## Look

- The banned-cliche list in `references/motion-grammar.md` applies to every frame.
- One display typeface and one UI typeface: the brand's real files.
- One accent color unless the brief says otherwise.
- Something new happens on screen every 2 to 4 seconds.

## Sound

- The score and the UI sounds are synthesized in code by default (`scripts/synth-score.py`, `scripts/synth-sfx.py`). A supplied track is the only exception.
- Hits sit on the measured beat grid (`beats.json`). The final mix lands at -14 LUFS integrated, true peak at or under -1 dBTP.

## Loop before showing anything

1. Render the preview cut and the critique bundle, and look at them.
2. A fresh critic scores the 8 criteria in `references/critique-protocol.md`.
3. Fix the 3 worst problems. Repeat for at least 3 rounds, until every score is 8 or higher.
4. Only then does the full-quality render start.
