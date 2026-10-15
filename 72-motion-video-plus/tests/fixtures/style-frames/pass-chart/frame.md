# Style frames: fixture-style-chart, scene bar-01

Fixture job (execution_context: fixture, approval_policy: fixture_only).
These stills are engineering material for the style-frame gate. They were
drawn locally with PIL from this job's own design.json tokens and the
scene's Section 17.2 proof states. No paid generation was used. The
design approval on this job was issued by the fixture test issuer and is
diagnostic evidence only; nothing here is owner-approved. Reference state
for this scene's comparison fixture: ENGINEERING_FIXTURE_ONLY (VREF-02).

Frame records (kind, file, state):

| kind | file | state |
| --- | --- | --- |
| `first` | style-frames/bar-01-first.png | frame 0 composition |
| `key_proof` | style-frames/bar-01-key_proof.png | frame 45 half-reveal proof |
| `final` | style-frames/bar-01-final.png | frame 150 settled state |

## First frame (`first`)

Rationale. The opening composition carries the headline, the three row
labels, the plot axis, and the disclosure, and nothing else. No bar and
no value is drawn, following the Section 17.2 rule that early frames
must not show false data. The viewer learns the question and the groups
before any number exists, and the empty plot reserves the exact space
the bars will occupy, so the reveal reads as growth inside a settled
frame rather than a layout change.

## Key-proof frame (`key_proof`)

Rationale. This is the frame 45 proof state: bars at 240, 360, and
600 px against the 1200 px plot, exactly half of the final 480, 720, and
1200 px. Values are printed at their final size and position from this
state onward, so the half-reveal already proves the settled type
hierarchy: headline first, labels second, bars third, values fourth,
disclosure last. If the composition fails anywhere, it fails here,
before animation work is spent on it.

## Final frame (`final`)

Rationale. The settled state. Bars at full scale, values right-aligned
on a shared edge clear of the longest bar, the disclosure in the same
position it held in the first frame. The reading order is unchanged from
the key-proof frame; only the bar lengths moved. That stability is the
point of approving stills first: the motion adds emphasis, never new
layout.

## Critique against the named reference

Reference: VREF-02, the C05 comparison fixture (directive Section
17.3), as realized in the verified MG-006 Remotion render of this same
scene (tests/evidence/mg006, still-landscape-f150.png and the decoded
proof frames behind it).

- Stronger: these stills hold the composition at full print size with
  no motion and no video decode in between, so type hierarchy, label
  spacing, and the value alignment edge can be judged exactly. The
  disclosure also sits in one fixed position across all three states;
  in the moving render it is only verifiable at the frames someone
  happens to pause on.
- Weaker: flat locally drawn stills cannot prove what the MG-006
  render proved with decoded frames: the reveal timing, the exact
  frame where each width lands, or text behavior inside the real
  runtime. The type is Liberation Sans drawn by PIL, standing in for
  the job's fixture-sans font inside the renderer, so letterforms here
  are representative, not the shipped rendering.
- Different: the first frame withholds values entirely, where a
  marketing still for the same chart would usually print the numbers
  from the start. That is a deliberate honesty choice from Section
  17.2, not a missing element: a number appears only when the bar that
  earns it is on screen.

No numeric fidelity score is recorded here, on purpose. The critique
above is the review artifact; scoring in Skill 45's own terms belongs
to a style card produced through the Design Intelligence bridge when a
real reference is analyzed.
