# RETIRED: the Gauntlet VSL design (archived 2026-10-14, FIX-PLAN Item 23)

This folder holds the preserved files of the RETIRED Gauntlet VSL page design
(the "GAUNTLET-LOOP DESIGN-OPUS" VSL variant). It is an archive, not a live
part of the pipeline:

- Nothing in the live tree invokes, imports, or executes these files.
- They carry no authority. Do not build to them, do not cite them as the
  current design, and do not re-introduce their rules as live instructions
  (Guard B, `presentations/retired-doctrine-patterns.json`, lints the retired
  values so they cannot creep back silently).
- The ONE live VSL design is the Wave C executor: `scripts/vsl_builder.py`
  builds the page (phase `P-U-VSL-BUILD`), and `P-U-GHL-VSL` installs it via
  `scripts/ghl_external_installer.py` (PRES-011). The standing doctrine is
  `sops/VSL-BUILDER-SOP.md`.
- The design's one idea worth keeping, the revelation-based gate rule, is
  preserved as a labeled spec note in `sops/VSL-GAUNTLET-SPEC-NOTE.md`
  (history kept, authority removed).

## Contents (moved byte-identical from `scripts/`, git renames, no edits)

- `gate_time_model.py`: the retired gate-time model (the R+20 rule and its
  flagged fallbacks), with its offline self-test.
- `prove_vsl_copy_structure.py`: the retired fail-closed prover for the
  Gauntlet page-structure contract (section order, word floors, a/b variants,
  "real form" gate check).
- `prove_vsl_research.py`: the retired fail-closed prover for VSL web-research
  notes provenance.
- `vsl_gate_overlay.js`: the retired browser overlay controller that was to
  splice the Skill 44 gate form embed into the assembled page at the gate
  timestamp.
- `structure/vsl_structure.json`: the retired page-structure contract the
  provers enforced.

Why retired: the landed executor never implemented this design. The builder
generates its own copy and hero, assembles the whole page itself, and derives
the gate timestamp from the webinar timing track by the window-midpoint rule;
no run artifact identifies a "revelation slide", so the R+20 rule could only
ever have run on its own flagged fallbacks. Two designs stood on paper; one
stood in code. FIX-PLAN Item 23 (owner input OI-3 default) retired this one.
The full 18-contradiction checklist and verdicts ship with that change's
manifest.
