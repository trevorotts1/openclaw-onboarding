# Storyboard planner fixtures (MG-009)

Each directory is one planner-gate case for `scripts/validate_storyboard.py`:

- `storyboard.json`: a canonical contracts-v2 storyboard.
- `planner.json`: the MG-009 planner record for that storyboard (see
  `references/visual-storytelling.md` for the record contract).
- `assets.json`, `data/*.json`, `scenes/*.json`: the minimal job context the
  planner layer resolves references against.

Scene files here are planner excerpts: they carry only `id` and
`semantic_motion_assertions`, the two things the planner layer consumes.
Full scene specs live in the mode fixtures under `tests/fixtures/modes/`
(for example the registered C05 spec at
`tests/fixtures/modes/powerpoint_graphic/scenes/bar-01.json`), and full
scene-spec validation remains the job of `scripts/motion_contracts.py`.

| Fixture | Expected result |
|---|---|
| `pass-image-led` | Passes: two literal-evidence image beats plus a non-explanatory emphasis card |
| `pass-chart` | Passes: two chart beats bound to bar-width assertions plus one excepted explanatory typography beat (coverage 2 of 3) |
| `pass-mechanism` | Passes: one mechanism beat and one diagram beat bound to subject-identity assertions on the same work item |
| `fail-text-only` | Fails with `MG_PLANNER_COVERAGE` only: three explanatory typography beats, each carrying an exception rationale |
| `fail-typography-evasion` | Fails with `MG_PLANNER_COVERAGE` only: one real chart plus three excepted typography beats (coverage 1 of 4, needs 3) |
| `fail-unrelated-assertion` | Fails with `MG_PLANNER_ASSERTION_SUBJECT_MISMATCH` only: the beat binds an assertion about the background gradient |
| `fail-missing-proof-state` | Fails with `MG_SCHEMA_INVALID` only: the beat omits `proof_state` |
| `fail-literal-evidence-missing` | Fails with `MG_PLANNER_EVIDENCE_UNRESOLVED` only: the beat claims a studio photograph the job does not contain |
