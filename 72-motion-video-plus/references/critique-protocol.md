# Critique Protocol: Skill 72

A fresh critic reviews every video before the full render. Fresh means a separate agent that did NOT write the animation. If no separate agent is available, the operator runs the critique themselves but keeps the critic's voice: evidence first, no defending the code. Judge only what is on screen and in the speakers, never intentions or code.

## Inputs

The animation author hands the critic:

- The director's brief and the brand bible (what was promised).
- The review bundle from `scripts/critique-bundle.sh`: a per-beat contact sheet (one frame per beat), a 2fps contact strip of the full preview, a phone-size strip (360 px wide), a 9:16 safe-zone check image, and `metrics.json` (durations, frame counts, loudness readings).
- The previous round's review log, if any. The critic checks that last round's fixes actually landed; a problem noted last round that is still visible cannot score higher than it did last round.

When a moment is ambiguous, the critic asks for a still (`node scripts/render.js --still <t>`) or a clip (`node scripts/render.js --cliprange <a,b>`) instead of guessing.

## The 8 criteria

Score each 1 to 10. A score of 8 means shippable to a demanding client. Every score below 8 needs evidence: timestamps, frame numbers, or metric values. No score is given without evidence.

| # | Criterion | A 10 looks like | Automatic cap |
|---|---|---|---|
| 1 | Hook (first 2 seconds) | Frame 0 already reads. The promise of the video lands by 1.5 seconds. A scroller would stop. | Frame 0 empty or near blank: max 6 |
| 2 | Readability at small sizes | Every must-read line reads in the 360 px phone strip, and the call to action is the most legible thing on screen. | CTA illegible at 360 px: max 6. Key text inside 9:16 keep-out zones: max 7 |
| 3 | Motion quality | Springs with weight, overlap and follow-through. Nothing snaps or pops in. Nothing fades as an enter or exit. Fast moves show clean arcs in the strip views. | A fade used as a transition: max 6. A visible pop or jump in a strip: max 7 |
| 4 | Pacing and variety | Something new every 2 to 4 seconds. Shot sizes and transition types vary. The build accelerates toward the logo or final card. | Any gap over 4 seconds, or a static run over 2 seconds outside the end card: max 7 |
| 5 | Brand accuracy | Real product UI and the real logo. Exact brand colors, one accent, the real typefaces. None of the reference material's content copied. | Invented UI where real UI exists, a wrong font, or a second accent color: max 6 |
| 6 | Sound sync | Every hit lands with its picture within 45 ms. Whooshes peak on landings. Loudness reads -14 LUFS within half a unit, true peak at or under -1 dBTP. The voiceover matches the on-screen words. | Hits off by more than 80 ms, or loudness off target: max 6 |
| 7 | Composition across formats | Each aspect ratio is composed deliberately, not cropped. No dead zones. Type never sits centered on an empty field. | A 9:16 frame with a third of the frame empty for more than a second: max 7 |
| 8 | Polish | No blank frames, no double-exposed captions at swaps, no stray carets, no glyph slivers at masks, no orphaned captions, no type leaking outside its window. | Any blank frame mid-video, or a double-exposed caption: max 7 |

## Known failure modes: check each one explicitly

1. Frame 0 is empty or black; the first word only reads at frame 3 or later.
2. The sound hits early: the visual needs several frames to become readable after the sound.
3. The end card goes static for more than 1.5 seconds.
4. The CTA or URL is tiny at 360 px wide.
5. A scene cuts in over an unfinished wipe, so the outgoing scene vanishes early or flickers.
6. Flat depth: cards read as stickers on a flat background.
7. Empty zones in 9:16: a container empty for a beat, or the bottom third empty.
8. Double-exposed captions at swaps: the outgoing line is still visible when the incoming line lands.
9. A caret lingers after its line leaves.
10. The first frame of a slam shows glyph tops through the mask padding.
11. An exiting caption leaves before its scene moves, orphaning the sub-caption.
12. Blank frames in handoffs: mid-motion, or after a wipe before the next element has size.
13. Type from another scene leaks outside its window.
14. Type crosses busy UI while the camera moves.
15. A hold longer than one bar with nothing new happening.
16. A banned-look violation from `references/motion-grammar.md`.

## Rounds and the gate

Minimum 3 rounds. After each round the critic writes the review log (see below), the animation author fixes the 3 worst problems, and a new preview renders. The gate opens only when every criterion scores 8 or higher AND at least 3 rounds have run. There is no skipping the gate: a video that has not passed critique does not render at full quality.

## Review log format

Append one block per round to `review/review-log.md`:

```
## Round N: <what was reviewed, e.g. preview cut v3, scenes 1-6>

| Criterion | Score | Evidence |
|---|---|---|
| Hook (first 2 seconds) | 7 | Frame 0 shows the headline at 30 percent rise; reads at 0.2s |
| ... (all 8 rows) ... |

3 worst problems (ranked by damage, each with timestamp and cause):
1. ...
2. ...
3. ...

Fixes for round N+1 (concrete and testable: what changes, where, how to verify):
1. ...
2. ...

Verdict: SHIP (every score 8+ and round 3 or later) or ANOTHER ROUND
```

Scores must be earned. A problem the critic noted last round that is still visible keeps its old score or goes lower, never higher.
