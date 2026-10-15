# Style frames: fixture-style-image-led, scene hero-01

Fixture job (execution_context: fixture, approval_policy: fixture_only).
These stills are engineering material for the style-frame gate. The
intended asset, media/mentor-desk.png, is a bright flat illustration
drawn locally with PIL for this fixture. It depicts no real person and
is not a photograph. A production job would name its approved
photograph in assets.json instead, under the consent-first rule in
references/design-intelligence-bridge.md. No paid generation was used.
The design approval on this job was issued by the fixture test issuer
and is diagnostic evidence only; nothing here is owner-approved.
Reference state for this scene's comparison reference:
CALIBRATION_PENDING (VREF-01).

Frame records (kind, file, state):

| kind | file | state |
| --- | --- | --- |
| `first` | style-frames/hero-01-first.png | tight crop, subject only |
| `key_proof` | style-frames/hero-01-key_proof.png | headline landed, focal proof |
| `final` | style-frames/hero-01-final.png | full room, settled composition |

## First frame (`first`)

Rationale. The scene opens on a tight crop of the asset (source rect
x 380, y 240, 460 by 560) centered on the mentor, with only the kicker
and the accent rule at left. The headline is withheld until the crop
opens, so the first thing approved here is the subject itself: present,
well lit in the drawing's flat daylight, and large enough that the
reveal has somewhere real to go. The focal point sits on the mentor's
face (normalized 0.433, 0.36 in the source asset) and does not move in
any later frame.

## Key-proof frame (`key_proof`)

Rationale. The crop widens (source rect x 240, y 140, 760 by 700) and
the headline lands at its final size and position, with the supporting
line under it. An accent ring marks the focal subject in the panel.
The ring is a review device, not part of the design: it makes the
focal claim checkable in a still, so a reviewer can confirm the eye
lands where the record says it lands. This is the frame the design
approval most depends on, because it proves subject, crop, and type
hierarchy in a single composition.

## Final frame (`final`)

Rationale. The full asset sits in the panel (880, 140, 920 by 800) and
the composition settles: kicker, headline, supporting line, image,
disclosure, in that reading order. The marker ring is gone. The
disclosure along the bottom names what the image is (a locally drawn
fixture illustration with no real person depicted), because a style
frame that hides its own provenance would teach the wrong habit for
production frames, where the equivalent line names the approved asset
and its consent basis.

## Critique against the named reference

Reference: VREF-01, the image-led statement (directive Section 17.3):
a dominant crop with a protected subject area, a large short headline,
and a mask reveal, held at CALIBRATION_PENDING until the owner reviews
real exemplars.

- Stronger: the crop sequence is honest about the reveal. The first
  frame is a true tight crop of the source, not the final frame scaled
  down, so the focal discipline VREF-01 asks for can be judged frame
  by frame, and the focal point is one fixed coordinate a reviewer can
  verify rather than an impression.
- Weaker: the asset is a flat illustration, so these frames cannot
  prove the crop against photographic detail: real skin, real text on
  real objects, or the way a photograph's depth interacts with a mask
  edge. They also cannot speak to consent, likeness, or photographic
  truth, which are exactly the properties that matter most for a
  real-person image-led scene. Read these frames as layout and gate
  evidence, never as evidence that VREF-01 is satisfied.
- Different: the key-proof frame carries the accent marker ring on the
  focal subject, a device VREF-01 does not call for. It exists so the
  focal claim survives as a checkable fact in a still; the final frame
  drops it, and a production job following VREF-01 would prove the
  same claim through its decoded proof frames instead.

No numeric fidelity score is recorded here, on purpose. Scoring in
Skill 45's own terms belongs to a style card produced through the
Design Intelligence bridge when a real reference is analyzed; this
fixture's asset is a drawing, and scoring it against a photographic
reference would manufacture precision that does not exist.
