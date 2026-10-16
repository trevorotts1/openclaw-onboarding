# Skill 72 visual reference suite (MG-044)

This folder is the shipped visual reference suite for the Motion
Graphics V2 build: the Section 8 reference sequence, one worked
example per delivery mode produced by the shipped mode producers, the
component example index for the registered catalog, and the negative
exemplars that must keep failing their gates. It exists so a reviewer
can see the intended quality level from real artifacts rendered by
the shipped pipeline, not from descriptions of them.

Calibration status, stated exactly as Directive Section 17.3
defines it: the references in this suite are CALIBRATION_PENDING and
ENGINEERING_FIXTURE_ONLY. No exemplar in this suite is owner
approved. The review scores recorded here come from the shipped
MG-033 rubric tooling applied by an engineering reviewer; they are
provisional and uncalibrated, and they are never owner approval.
VREF-04 (real product detail) is BLOCKED_ASSET until an actual
approved product screenshot exists; the product screen used by the
C02 example is a clearly labeled fictional fixture and is never
presented as real product proof.

## Layout

- `reference-registry.json`: the Section 17.4 registry for VREF-01
  to VREF-05, with the approval state of each reference, its source
  and frame files, clip hashes, per-dimension provisional scores
  where a review exists, and its known-bad counterpart.
- `sequence/`: the Section 8 reference sequence package: the
  storyboard mapping each beat to its component and evidence, the
  per-engine small complete job records, and the frames that prove
  each beat.
- `modes/`: one example per delivery mode (PowerPoint graphic, VSL
  desktop insert, VSL mobile insert, standalone program). Each mode
  folder carries the source package reference, its manifest, its
  dataset where the mode has one, a poster, the clip, an MG-033
  review record, and the MG-034 QC record the shipped tooling
  produced.
- `components/`: the component example index for the
  twelve-component catalog (C01 to C09 available with examples,
  C10 to C12 unavailable with reasons), tying each registered
  component to its proof frames, clips, and records.
- `negatives/`: the negative exemplars. Each one is staged
  deliberately, names the reason it fails, and carries the failing
  record from the actual gate that catches it (the MG-013 typography
  floor audit, the MG-032 fake-motion evaluation, the MG-038 mobile
  recomposition checks, and the storyboard representation coverage
  gate for the decorative-motion substitution).
- `evidence-index.json`: every artifact in this suite, the command
  that produced it, and its SHA-256. If an artifact is not in the
  index, it is not part of the suite.

## Honest limits

- All data in these examples is illustrative and labeled as such on
  the artifacts themselves.
- PowerPoint playback inside Microsoft PowerPoint is UNVERIFIED on
  this Linux build host; the MG-035 record states the same limit.
  What is verified is the package: the deck, its embedded media
  (byte-identical to the rendered component), the poster, and the
  fallback still.
- The desktop VSL insert package lane carries one recorded QC
  failure (a font alias finding in the insert package lane) with its
  diagnostic pass recorded beside it in `modes/vsl_desktop/`. It is
  included, not hidden: the assembled VSL plan lane passes.
- The standalone example is deliberately silent, per the Section 8
  standalone terms (own audio plan or deliberately silent). The
  narrated acceptance variant, including its final spoken phrase
  check, is covered by the MG-039 producer tests, not by this
  example.
