# Style-frame fixtures (MG-010)

Two fixture jobs prove the style-frame design gate
(scripts/check_style_frames.py):

- `pass-chart/`: a chart scene (bar-01, the C05 comparison scene) in
  mode powerpoint_graphic. Style frames follow the Section 17.2 proof
  states: first (frame 0, no bars, no values), key_proof (frame 45,
  half reveal, widths 240/360/600), final (frame 150, full widths
  480/720/1200).
- `pass-image-led/`: an image-led scene (hero-01) in mode
  standalone_video. The intended asset is a bright flat illustration
  drawn locally with PIL (media/mentor-desk.png). It depicts no real
  person and is not a photograph.

Provenance and honesty rules for this directory:

- Every PNG was rendered locally from the job's own design tokens with
  PIL and Liberation Sans. No paid generation, no network assets.
- Approvals were issued by `fixture-test-issuer` under fixture context
  and are diagnostic evidence only. No approval here names a real
  person, and none claims owner approval. The chart reference (VREF-02)
  is ENGINEERING_FIXTURE_ONLY; the image-led reference (VREF-01) is
  CALIBRATION_PENDING.
- Each job carries design.json (canonical token record),
  style-frames.json (per-frame design records: typography hierarchy,
  focal point, crop, layout, colors, reading order), frame.md
  (rationale and reference-specific critique per frame), and
  approvals.json (the design approval binding the exact frame hashes
  and the design revision).
- The `animation/` placeholder in each job exists so the gate can
  prove ordering: the record sequence puts style frames (1, 2, 3)
  before animation artifacts (10).
