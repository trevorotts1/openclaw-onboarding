# Example V2 jobs, one per delivery mode

These four folders are validated starting points for new Skill 72 jobs, one
for each delivery mode. Each is a complete serialized V2 job package
(manifest, storyboard, assets, design, timeline, scenes, dataset, and, for
the VSL modes, the parent handoff) derived from the normative Section 16
fixtures in `tests/fixtures/modes/`. The intake test
(`tests/unit/test_intake.py`) validates every one of them with the shipped
contract validator, so an example that stops validating fails the test
suite.

| Folder | Mode | Canvas | Audio | Parent |
|---|---|---|---|---|
| `powerpoint_graphic/` | PowerPoint graphic | 1920x1080 (16:9) | `none` (silent) | none |
| `vsl_desktop/` | Desktop VSL insert | 1920x1080 (16:9) | `inherited` from the parent | `parent-handoff.json` |
| `vsl_mobile/` | Mobile VSL insert | 1080x1920 (9:16), recomposed portrait layout | `inherited` from the parent | `parent-handoff.json` |
| `standalone_video/` | Standalone video | 1920x1080 (16:9) | `none` in this example | none |

## The visual reference suite

`reference-suite/` is a different kind of example: the shipped visual
reference suite for the whole build (Directive MG-044, test T25). It
collects the Section 8 reference sequence, one fully evidenced
example per delivery mode above (poster, clip, MG-033 review record,
MG-034 QC record, and the records of the producer that made it), the
component example index for the registered catalog, the Section 17.4
reference registry (VREF-01 to VREF-05), and the negative exemplars
that must keep failing their gates. Its calibration status is stated
in its own README and registry: CALIBRATION_PENDING and
ENGINEERING_FIXTURE_ONLY, with VREF-04 BLOCKED_ASSET. Nothing in the
suite is owner approved, and its scores are provisional rubric scores
with their evidence attached, never owner approval.

## How to use an example

1. Copy the folder for your mode into the job's storage location and rename
   the job (`job_id`, `company_id`, and the VSL parent identifiers).
2. Replace the dataset, design, and scene copy with the job's approved
   production material.
3. Re-validate before anything renders:

   ```bash
   python3 scripts/motion_contracts.py validate <job-dir>
   ```

   The validator exits 0 only when the job produces zero findings.

## Honest limits

- The chart data is illustrative (the dataset says so in its source note)
  and the design is an engineering fixture whose calibration status is
  `engineering_fixture_not_owner_approved`. Neither is client evidence or
  an approved design.
- The examples run in the `fixture` execution context with the
  `fixture_only` approval policy, exactly like the normative fixtures they
  derive from. A production job sets `execution_context` to `production`
  and `approval_policy` to `owner_or_existing_authorized_reviewer`; the
  schema and the validator enforce that pairing.
- Schema-valid is the floor, not the finish: it is not asset-ready,
  approved, rendered, or delivered (directive Section 5.2).
- The originals in `tests/fixtures/modes/` are the normative fixtures.
  Never edit them to make an example pass; fix the example.
