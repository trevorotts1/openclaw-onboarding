# Animation Contract: Skill 72

This is the exact contract every scene animation file must satisfy. Hand these rules to the model writing the animation code. The frame driver (`scripts/render.js`) depends on every one of them.

## The one hard requirement

Every scene file MUST expose:

```js
window.__setTime = function (t) { /* ... */ };
```

`t` is time in seconds as a float, from 0 to the scene duration. Calling `window.__setTime(t)` sets every animated element's style as a **pure function of t**. The driver seeks to `t = frame / fps`, calls `__setTime(t)`, waits one animation frame, then screenshots. Same t must always produce the same pixels.

## Forbidden

1. **No CSS transitions or CSS animations.** All motion is set imperatively inside `__setTime`. A transition would make the screenshot depend on wall-clock time, which breaks determinism.
2. **No setTimeout, setInterval, or requestAnimationFrame-driven motion.** The driver controls time; the page must not advance itself.
3. **No unseeded randomness.** If a scene needs randomness (particle scatter, texture), use a seeded PRNG keyed off t or the frame number so the same t always renders identically.
4. **No network fetches during the timeline.** Load all fonts, images, and assets before frame 0. The driver waits for `document.fonts.ready` and network idle once, then starts seeking.
5. **No layout that depends on viewport size at screenshot time.** The driver sets the viewport to the manifest resolution before loading. Use fixed pixel geometry or fractions of the known stage size.
6. **No GPU-layer tricks.** `translate3d`, `translateZ(0)`, and `will-change` make the browser cache a raster layer, so the same t can paint differently depending on which frame came before. Fake depth in 2D (skew, scale, shadow) or draw it on a canvas.

## Motion grammar

Motion must follow `references/motion-grammar.md`: springs only, using the named presets (`weighty`, `panel`, `snap`, `drift`); visual hits scheduled 2 frames before the beat so they read on it; masked-word typography rules; the banned-cliche list. Run `scripts/lint-grammar.py` on every scene file before the preview gate. The linter flags violations; it never auto-fixes.

## Required structure

- One HTML file per scene, self-contained (inline CSS and JS, or local relative assets inside the video folder).
- A `<div id="stage">` sized exactly to the manifest resolution; the driver screenshots the stage element.
- `window.__sceneDuration` set to the scene duration in seconds (must match the manifest; the driver asserts this).
- `window.__setTime(0)` must render the correct first frame with no prior calls.

## Determinism checklist for the animation author

- [ ] Scrubbing t from 0 to duration forward and backward shows the same frames at the same t values.
- [ ] Two consecutive full renders produce byte-identical PNG sequences.
- [ ] `scripts/verify-determinism.js` passes: probe frames rendered cold match the same frames rendered after seeking elsewhere (no pixel drift).
- [ ] No element keeps moving after its last keyframe (frozen end states are explicit).
- [ ] Text is set from the approved script; no lorem ipsum survives into a preview.

## Resolution and frame rate

The manifest sets these per run. Defaults: 1920x1080 at 30fps for final, 960x540 at 15fps for previews. The animation must be resolution-independent: build the stage at the manifest resolution, never assume 1920x1080.
