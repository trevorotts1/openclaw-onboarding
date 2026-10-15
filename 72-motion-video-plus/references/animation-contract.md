# Animation Contract: Skill 72

This is the exact contract every scene animation file must satisfy. Hand these rules to the model writing the animation code. The frame driver (`scripts/render.js`) depends on every one of them.

## The one hard requirement

Every scene file MUST expose:

```js
window.__setTime = function (t) { /* ... */ };
```

`t` is time in seconds as a float, from 0 to the scene duration. Calling `window.__setTime(t)` sets every animated element's style as a **pure function of t**. The driver seeks to `t = frame / fps`, calls `__setTime(t)`, waits one animation frame, then screenshots. Same t must always produce the same pixels.

## Forbidden

These six rules bind legacy `__setTime` scene files, the format this contract specifies. They are this engine's determinism rules, not global laws of the skill: every engine keeps the same invariant (motion as a pure function of the frame clock) with its own rule set, summarized under Engine render rules below.

1. **No CSS transitions or CSS animations.** All motion is set imperatively inside `__setTime`. A transition would make the screenshot depend on wall-clock time, which breaks determinism.
2. **No setTimeout, setInterval, or requestAnimationFrame-driven motion.** The driver controls time; the page must not advance itself.
3. **No unseeded randomness.** If a scene needs randomness (particle scatter, texture), use a seeded PRNG keyed off t or the frame number so the same t always renders identically.
4. **No network fetches during the timeline.** Load all fonts, images, and assets before frame 0. The driver waits for `document.fonts.ready` and network idle once, then starts seeking.
5. **No layout that depends on viewport size at screenshot time.** The driver sets the viewport to the manifest resolution before loading. Use fixed pixel geometry or fractions of the known stage size.
6. **No GPU-layer tricks in legacy `__setTime` files.** `translate3d`, `translateZ(0)`, and `will-change` make the browser cache a raster layer, so the same t can paint differently depending on which frame came before. Stage depth instead with `perspective` and `rotateX` / `rotateY` transforms, with 2D cues (scale, skew, shadow, layered parallax), on a canvas, or in a genuine 3D scene, as the scene's choreography declares.

## Motion grammar

Motion must follow `references/motion-grammar.md`: motion is chosen by intent. Every scene file declares `window.__choreography` with one intent and its behaviors from `references/choreography-vocabulary.json`, and the scene's motion stays inside that intent's permitted behaviors. Event alignment is authored on the shared compiled timeline at cue timestamps; there is no universal early shift of visual hits. Run `scripts/lint-grammar.py` on every scene file before the preview gate. The linter flags violations; it never auto-fixes.

## Engine render rules

Deterministic, frame-driven evaluation is mandatory on every engine. What each engine forbids beyond that invariant is that engine's rule, stated here per engine rather than as a global ban. The adapter references carry each engine's full rule set.

- **Legacy `__setTime` scenes (this contract):** the six Forbidden rules above. Depth is staged with `perspective` and rotate transforms, 2D cues, canvas, or a genuine 3D scene; GPU-layer caching tricks (`translate3d`, `translateZ(0)`, `will-change`) are forbidden because the seek-and-screenshot driver can paint a cached raster inconsistently.
- **Remotion:** motion is derived from the frame clock (frame-driven interpolation and spring values computed from the current frame). Wall-clock-driven motion and CSS transitions are out, because a frame must be a pure function of its frame number. 3D transforms are permitted where the scene's choreography declares depth.
- **Hyperframes:** motion lives in registered, seekable timelines that the renderer steps deterministically. Unregistered wall-clock animation is out, for the same purity reason. Transforms permitted by the registered timeline are allowed where the choreography declares them.

## Required structure

- One HTML file per scene, self-contained (inline CSS and JS, or local relative assets inside the video folder).
- A `<div id="stage">` sized exactly to the manifest resolution; the driver screenshots the stage element.
- `window.__sceneDuration` set to the scene duration in seconds (must match the manifest; the driver asserts this).
- `window.__choreography` set to the scene's choreography declaration: one intent, its behaviors, and `data_marks: true` when the scene animates data marks, per `references/motion-grammar.md`. The linter requires this declaration.
- `window.__setTime(0)` must render the correct first frame with no prior calls.

## Determinism checklist for the animation author

- [ ] Scrubbing t from 0 to duration forward and backward shows the same frames at the same t values.
- [ ] Two consecutive full renders produce byte-identical PNG sequences.
- [ ] `scripts/verify-determinism.js` passes: probe frames rendered cold match the same frames rendered after seeking elsewhere (no pixel drift).
- [ ] No element keeps moving after its last keyframe (frozen end states are explicit).
- [ ] Text is set from the approved script; no lorem ipsum survives into a preview.

## Resolution and frame rate

The manifest sets these per run. Default final: 1920x1080 at 30fps. Previews follow the shipped preview model (`references/preview-and-review.md`): the scale derives from the manifest canvas at the manifest fps, not the legacy renderer's default scale of 0.5, and aspect is preserved; `--rough` is the only reduced-fps mode and its artifacts are labeled `rough_layout_only`. There is no forced preview size or frame rate. The animation must be resolution-independent: build the stage at the manifest resolution, never assume 1920x1080.
