# Quality dashboard: fixture-powerpoint-graphic

- Artifact mode: powerpoint_graphic
- Artifact: shared-utils/motion-render-runtime/.runtime/mg032-tests/render-c05/renders/remotion/final.mp4 (MG-032 worktree scratch) (sha256 1d151ffb42d0f95e...)
- Reference: VREF-02
- Reference calibration state: **ENGINEERING_FIXTURE_ONLY**
- **PROVISIONAL SCORES.** This reference is not owner-calibrated, so every score below is provisional. A score of 10 cannot be awarded against this reference. A passing gate is a technical result, never the owner's artistic approval.
- Rounds recorded: 1 of 5 correction rounds
- Latest verdict: another_round

## Score history

| Round | visual_storytelling | asset_relevance | typography_readability | composition | motion_clarity | data_proof_integrity | destination_fit | finishing | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 6 | 7 | 7 | 6 | 9 | 9 | 8 | 7 | another_round |

## Latest round detail

### visual_storytelling
- Score: 6 of 10
- Compared with the reference: Against VREF-02's own terms the framing promise is kept exactly: the Section 17.2 frame-0 state (context and labels composed, no false data) and the proof state both match the reference definition. Departure is ambition, not fidelity: the piece is one beat with no development, contrast, or payoff beyond the reveal, which is fixture-grade storytelling by design.
- Evidence (frame): [demo/frames/f0.png](demo/frames/f0.png): Frame 0: the headline 'Compare the three groups', the three category labels, and the values are all composed before any bar exists; the promise of the piece is readable in the first frame.
- Evidence (frame): [demo/frames/f45.png](demo/frames/f45.png): Frame 45 (proof state): the bars are mid-reveal in the same ratio as the values, so the single statement the piece makes is enacted, not just announced.
- Evidence (sheet): [demo/sheets/fixture-powerpoint-graphic__samples__p01.png](demo/sheets/fixture-powerpoint-graphic__samples__p01.png): The bundle's sample sheet covers the full 180 frames; there is exactly one beat and one idea in the whole timeline.

### asset_relevance
- Score: 7 of 10
- Compared with the reference: The reference is a data-beat fixture, so relevance is judged on the chart itself: it is exactly the asset the beat calls for, and nothing off-brief is present. There is no human or product imagery to judge because the fixture beat has none; relevance is total but trivially so, which caps what this dimension can prove here.
- Evidence (frame): [demo/frames/f179.png](demo/frames/f179.png): Frame 179: the only visual asset on screen is the bar chart, which is the subject of the beat; no stock imagery, decoration, or unrelated prop appears anywhere in the 180 frames.
- Evidence (document): [../mg006/measurements.json](../mg006/measurements.json): The MG-006 measurements record the design provenance: fixture palette (background #F7F4EE, ink #192A38, accent #C04A26) and the fixture font record, so every visual element on screen is accounted for.

### typography_readability
- Score: 7 of 10
- Compared with the reference: Preserves the reference type behavior where it matters most: the headline size and the label clarity match the Section 17.2 proof material at both geometries. Departs in the two recorded defects: values get no emphasis over labels, and the portrait label wrap is uncomposed.
- Evidence (frame): [demo/frames/f45.png](demo/frames/f45.png): Frame 45 at full resolution: the 112 px headline is commanding and the labels and values are crisp; nothing the viewer must read is small or low contrast against the #F7F4EE field.
- Evidence (frame): [../mg006/still-portrait-f45.png](../mg006/still-portrait-f45.png): Portrait frame 45 from the MG-006 suite: the headline wraps cleanly to two lines, but each category label also wraps ('Group' over 'A'), and the values sit at the far right edge.

### composition
- Score: 6 of 10
- Compared with the reference: The grid, margins, and row rhythm match the reference exactly, and the frame identity is stable across all states, which the reference requires. The departure is the reference's own known weakness, recorded rather than excused: the fixed value column strands the figures and leaves the right-center field unoccupied at 16:9.
- Evidence (frame): [demo/frames/f45.png](demo/frames/f45.png): Frame 45: bars occupy the left half at widths 240/360/600 while the values sit at the right edge; the middle-right of the frame is empty field, and the eye must travel from each bar end across that field to its figure.
- Evidence (frame): [demo/frames/f179.png](demo/frames/f179.png): Frame 179 (hold state): even at full reveal only Group C's value sits near its bar end; Groups A and B keep the same stranded values, so the emptiness is structural, not a mid-animation artifact.

### motion_clarity
- Score: 9 of 10
- Compared with the reference: This is the dimension the reference exists to define, and the artifact meets the definition exactly: the Section 17.2 proof widths [240, 360, 600] at frame 45 and the hold behavior at frames 150 to 179 are reproduced under an independent evaluator, not the renderer's own account. The score stops at 9: the evidence covers one linear reveal family, and the reference is not owner-calibrated.
- Evidence (proof_record): [demo/proof-record.json](demo/proof-record.json): MG-032 proof record, verdict pass: bar widths agree three ways (spec derivation, component geometry, decoded raster) at frames 0, 45, 75, and 179, and a 60-frame full-fps clip over the reveal interval is bound to the record.
- Evidence (proof_record): [demo/proof-record.json](demo/proof-record.json): The same proof record measures context change outside the subject regions at 0.04 mean absolute difference between frames 0 and 75: essentially zero decorative motion, so the movement the viewer sees is the subject itself.

### data_proof_integrity
- Score: 9 of 10
- Compared with the reference: Integrity against the reference is exact: the arithmetic the reference specifies (proportional widths, explicit pivotal denominator, half-reveal proof point) is what the raster shows, verified by decoded pixels rather than the scene's own claims. No departure found. The score stops at 9 because the reference is an engineering fixture, not owner-calibrated.
- Evidence (proof_record): [demo/proof-record.json](demo/proof-record.json): Proof record assertions: expected, geometry-measured, and raster-measured widths are identical at every checkpoint ([0,0,0], [240,360,600], [480,720,1200], [480,720,1200]).
- Evidence (document): [../mg006/measurements.json](../mg006/measurements.json): The MG-006 record for the same job family: values 12, 18, 30 map to final widths 480, 720, 1200 at exactly 40 px per unit, the dataset sum is denominated by the explicit pivotal value 30, and frame 45 is exactly half reveal (progress 0.5).
- Evidence (frame): [demo/frames/f0.png](demo/frames/f0.png): Frame 0 inspected directly: widths are zero and the printed values are the true final values presented as the comparison's terms; no bar, sum, or implication at frame 0 overstates the data.

### destination_fit
- Score: 8 of 10
- Compared with the reference: Landscape fit is exact against the mode geometry the reference defines, and the portrait variant of the same job is a true recomposition, which the reference requires. The recorded defect is about this bundle's evidence completeness, disclosed rather than hidden: destination-size frames for this exact render were not in its bundle.
- Evidence (coverage_record): [demo/coverage.json](demo/coverage.json): Coverage record: the artifact is 1920x1080, 180 frames, 100 percent of the runtime accounted as covered with zero omitted frames, matching the powerpoint_graphic landscape geometry.
- Evidence (frame): [../mg006/still-portrait-f45.png](../mg006/still-portrait-f45.png): Portrait frame 45 from the MG-006 suite (same job, portrait mode variant): genuinely recomposed geometry (plot x 200, width 740, rows restacked), not a scaled or cropped landscape frame.

### finishing
- Score: 7 of 10
- Compared with the reference: Against the reference's finishing bar the piece is clean and honestly labeled, including its fixture disclosure. It is also deliberately plain: one accent, no brand lockup, no end treatment. That plainness is correct for an engineering fixture and would be unfinished for a client piece; the score reflects the fixture context the reference defines.
- Evidence (frame): [demo/frames/f179.png](demo/frames/f179.png): Frame 179: edges are clean, the hold state is stable, no placeholder, debug mark, or stray element appears, and the 'Illustrative example' disclosure is printed on the piece itself.
- Evidence (metrics_record): [demo/metrics.json](demo/metrics.json): Metrics record: loudness is null because this artifact has no audio stream; the powerpoint_graphic fixture is silent by design, so no sound judgment is signed in this review.

## Defect ledger (worst first)

| Defect | Severity | Dimension | First seen | Status | Cause |
|---|---|---|---|---|---|
| COMP-1 | major | composition | round 1 | OPEN | A single fixed value column at the frame's right edge serves every row in every state, instead of values anchored to the marks they describe. |
| TYPO-1 | minor | typography_readability | round 1 | OPEN | One type style serves both the category labels and the data figures; no emphasis treatment distinguishes the numbers the piece exists to show. |
| TYPO-2 | minor | typography_readability | round 1 | OPEN | The portrait label column width (200 px plot offset) cannot fit 'Group A' on one line at the label size, so the label wraps mid-phrase. |
| DEST-1 | minor | destination_fit | round 1 | OPEN | The MG-032 evaluation harness built this bundle without destination variants; destination-size sampling was not part of its bundle policy. |

## Remediation order (worst cause first)

1. COMP-1
2. DEST-1
3. TYPO-1
4. TYPO-2

Review history is append-only. Scores against a reference that is not OWNER_APPROVED are provisional and are never presented as the owner's artistic approval.
