# SPEC NOTE (RETIRED): the Gauntlet VSL design and its R+20 gate rule

**Status: RETIRED, preserved as a spec note only (FIX-PLAN Item 23, 2026-10-14;
owner input OI-3 default).** This document keeps the design's history and its
one reusable idea. It has NO authority: nothing in the live pipeline implements
it, no SOP may cite it as the current design, and its values must never
re-appear as live instructions (Guard B, `retired-doctrine-patterns.json`,
patterns `vsl-gauntlet-*`). The ONE live VSL design is the Wave C executor
(`scripts/vsl_builder.py`, phase `P-U-VSL-BUILD`) plus the PRES-011 install
phases; the standing doctrine is `VSL-BUILDER-SOP.md`, and the standing gate
rule is stated in that SOP's section 4. The retired source files themselves
are preserved byte-identical in `presentations/archive/vsl-gauntlet/`.

## What the retired design was

A page-assembly design from the GAUNTLET-LOOP DESIGN-OPUS document (cited in
its files as sections 6.1-6.5 and 10.3), in which the served VSL page would be
assembled from agent-authored parts and proven against a written structure
contract:

- A five-section page structure (hook, story, revelation, offer, close), each
  section with a word-count floor, checked IN ORDER against a declared
  HTML/video-metadata ledger by a fail-closed prover.
- TWO page variants (a and b) in ledger mode.
- A gate overlay spliced into the page at runtime, embedding the real Skill 44
  gate form (a static mock form was an automatic fail), pausing the video and
  blocking seek until the viewer submitted.
- A sourced-research gate in front of the copy: at least 3 named sources with
  URLs, every claim carrying a source marker.
- A gate timestamp derived from the talk's first big revelation (the retired
  R+20 rule, below).

## The R+20 gate rule (RETIRED, preserved verbatim in substance)

The retired model (`gate_time_model.py`, preserved in the archive) computed
the viewer-gate timestamp as (RETIRED formula, preserved for the record):

    gate_time = clamp(R + 20s, 180s, 480s)

where R is the timestamp of the talk's first big revelation: the revelation
slide's `audio_start` in the webinar slide-to-time mapping (the model's
`revelation_seconds`, resolved from the revelation slide's entry in
`working/checkpoints/webinar_timing.json`). The 20 seconds let the revelation
land and breathe before the ask. Flagged fallbacks, all fail-closed in
posture: if the revelation is unknown but the duration D is known, use
min(0.9 * D, 480); if both are unknown, use 480 (the latest, safest point in
the band). A gate computed from a flagged fallback is a gate whose reason is
unknown, and any future revival of this rule must surface that flag rather
than present the timestamp as derived.

Why it is retired rather than adopted: no run artifact identifies which slide
is the revelation slide. The timing track carries only slide numbers and
audio windows; the speech format marks only slide headers and planned
`SECONDS:` values. R is therefore unobtainable from run data, and the rule
could only ever have executed through its own flagged fallbacks. The landed
rule (window midpoint, `VSL-BUILDER-SOP.md` section 4) computes from data
every run has. If a future pipeline ever records a revelation marker in the
run's own artifacts, this note is the spec to revive the rule from, through a
new plan item, never by quietly editing the SOP.

## What survives from the design

- The [180s, 480s] gate band itself: the landed midpoint rule uses the same
  window.
- The sourced-research discipline as craft guidance for the VSL copy phases
  (the agent research phase still produces sourced notes; its retired prover
  no longer gates them).
- The "a static mock gate form is not a gate" principle: the live gate form
  is the Skill 44 form object installed by `P-U-FORM-GATE` under
  `scripts/vsl-gate-form-spec.json`, proven by the installer's receipt
  validation, not by page markup claims.
