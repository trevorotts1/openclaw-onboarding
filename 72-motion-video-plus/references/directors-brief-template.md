# Director's Brief Template

Copy this file to `<video-name>-brief.md` in the run folder and fill every section. Get the operator's approval before any animation code is written.

## One-liner

<One sentence, under 20 words: the viewer, the change, the feeling.>

## Objective

<What should the viewer think, feel, or do after watching? One paragraph.>

## Audience

<Who is watching, and what do they already believe?>

## Length and formats

- Target length: <e.g. 90 seconds>
- Primary format: <16:9 or 9:16>
- Secondary formats: <the other ratio, re-composed not cropped>

## Brand

- Brand bible: <path to the filled brand bible>
- Voice reference id: <Fish Audio reference id>
- Notes: <any brand constraints: clear space, disclaimers, claims>

## Reference grammar (if any)

- Reference: <title and where to find it>
- Grammar taken: <rhythm, transitions, camera, type behavior>
- Explicitly NOT taken: <its footage, logos, characters, copy, music>

## Voiceover script

<Final text, split per scene. Narration chunking is a transport concern handled at stage 6 (sentence-boundary packing under the per-request cap in `references/fish-audio-tts.md`; there is no per-scene character band, no minimum, and no padding). Never cut mid-sentence. No placeholders.>

## Story beats (planner output)

The plan comes from the visual-storytelling planner (see
`references/visual-storytelling.md`). Choose each beat's representation
before any animation code is written, and mirror the planner output here:
the storyboard artifact (`storyboard.json`) and the planner record
(`planner.json`) are the machine-readable sources of truth, and this
section is their human-readable approval surface. If a beat changes, update
the artifact, the record, and this section together, then re-run
`python3 scripts/validate_storyboard.py validate <job_dir>`.

Coverage (Section 1.1): <explanatory beats: N; information-bearing non-text
beats: M; required minimum: ceil(2N/3)>. A typography-only treatment for the
whole job is an owner decision with its approved rationale recorded here;
no single beat's exception declares it.

For each beat:

### Beat <beat id> (scene <scene id>)

- Idea: <the one idea this beat lands>
- Viewer question: <the question the beat answers>
- Representation: <chart / diagram / image-led comparison / spatial
  metaphor / real product demonstration / purposeful typography, chosen
  before code>
- Changing subject: <the actual image, object, chart, or diagram that
  changes; not automatically text>
- Visual verb: <accumulate / compare / connect / isolate / transform /
  reveal / traverse / expand / compress / reorganize / demonstrate>
- Initial state: <what the subject looks like when the beat opens>
- Transformation: <the observable change>
- Proof state: <the observable state that proves the claim, and the frame
  it is visible at>
- Final state: <what holds when the beat ends>
- Viewer takeaway: <what the viewer now understands>
- Evidence kind: <literal evidence (the actual asset or data) or
  illustrative metaphor; metaphor never borrows the language of evidence>
- Exact assets / data: <asset ids and dataset ids, or "none">
- Semantic assertions: <assertion ids declared in the scene file, each
  concerning this beat's changing subject>
- Component and engine: <component id, engine, and the short reason for the
  choice>
- Reading order: <elements in eye order; the first is the hero>
- Readable hold: <frames the final state holds for reading>
- Transition owner: <who owns the transition out of this beat>
- Typography exception rationale: <only for a text-dominant beat: the
  approved reason; the beat still counts as text for coverage>

## Style-frame approval

Style frames are approved stills, produced from the intended assets
before animation code is written (see "Style frames and the design gate"
in `references/visual-storytelling.md`). The owner selects a direction
from the stills and the `frame.md` rationale, not from animation code.
One block per representative scene:

### Scene <scene id>: style frames

- First frame: <path> (sha256: <exact frame hash>)
- Key-proof frame: <path> (sha256: <exact frame hash>)
- Final frame: <path> (sha256: <exact frame hash>)
- Design revision: <design revision digest over design.json and the
  frame design records, as reported by the gate>
- Named reference: <the reference the frame critique compares against>
- Critique summary: <stronger / weaker / different, in one or two lines
  each; the full critique lives in the job's frame.md. A bare score is
  not acceptable here>
- Approver: <name of the real approver. Leave blank until a real
  approver signs; fixture material never names a fixture issuer in
  this field and never claims owner approval>
- State: <CALIBRATION_PENDING / APPROVED / STALE. Fixture and exemplar
  material carries CALIBRATION_PENDING, which is the only honest
  pre-owner state; APPROVED requires the approval record in the job's
  approvals.json to name the exact frame hashes above and the current
  design revision; any design or frame change after approval moves the
  state to STALE and blocks promotion>
- Gate: `python3 scripts/check_style_frames.py check <job_dir>` must
  exit 0 before final animation authoring begins.

### Score and timing

- Tempo: <BPM for the synthesized score, default 120>
- Energy per scene: <e.g. scene 1 sparse, scene 2 builds, scene 3 full>
- Key hits: <moments where picture and sound must land together>

## Scenes

For each scene:

### Scene <id>: <title>

- Beat ids: <the planner beats this scene carries>
- Job (verb): <establish / prove / contrast / resolve>
- Visual: <what happens on screen, in plain words>
- Type on screen: <exact words, or "none">
- Semantic assertions declared: <assertion ids in the scene file, with the
  subject each one proves>
- Transition in: <how we arrive>
- Transition out: <how we leave>
- Duration: <set by audio-first timing after the voiceover lands>

## Sound

- Score: synthesized in code at the tempo above (default; a supplied track is the only exception).
- UI sounds: synthesized pops, clicks, whooshes, thumps, placed on the beat grid.
- Mix target: -14 LUFS integrated, true peak at or under -1 dBTP, music ducked under the voiceover.

## Deliverables

- <e.g. final 16:9 MP4, 9:16 cutdown, contact sheet, review log>
