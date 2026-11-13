# PD-018a — Build Report

- Unit: PD-018a (Severe, logic, Critical-first prerequisite of PD-048b)
- Lane / branch: FL04 / `pd/fl04-manifest`
- Base head before this unit: `e0bef34c8` (PD-307m build report). Working tree clean at that head; no other unit's hunks were present or disturbed.
- Commit: `b78085f9e238edfbd28052580e330d70028af176`
- Remote proof: `git ls-remote origin refs/heads/pd/fl04-manifest` -> `b78085f9e238edfbd28052580e330d70028af176   refs/heads/pd/fl04-manifest`
- Time: 8:24 PM Eastern, Nov 12, 2026

## What changed

1. `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`
   - Every one of the 56 phases now carries `client_label` (2 to 6 plain words) and `client_visible` (boolean), inserted directly after `name`.
   - `client_visible` is `true` on the lowest-`order` phase of each of the 18 reported steps and `false` on the rest ("first only"): 18 true, 38 false.
   - Every `client_report.start_template` / `done_template` token changed from `{name}` to `{client_label}` (`{k}`, `{N}`, `{eta}` unchanged).
   - `manifest_version` deliberately NOT bumped: builder rule 7 says the batch engine bumps once per batch, and a one-sided bump would desync `MIN_MANIFEST_VERSION` at `presentation_job/manifest.py:1018` and `manifest_assert.py:63` plus the client_package equality tests, which are outside this lane. Version remains 75 on both sides of the floor.
2. `universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt` — restamped `content_sha256=f2cbe73bad203f672c68e8d025e1c19e5db29d846db7a8337f9fc976466aa31a`, `generated=2026-11-13T01:24:40Z` (sha256 of the new manifest bytes, same format the installer writes).
3. `universal-sops/_content-manifest.json` — restamped by the repository hasher (manifest sha/bytes rows).
4. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py` — two assertions made false by the token switch updated for a true reason:
   - `test_counted_phase_substitutes_real_k_n_name` now pins the `{k}`/`{N}` substitution (`Step 1 of 46 — ... — starting|complete`) and proves no raw token (`{k}`/`{N}`/`{name}`/`{client_label}`) leaks. The label value itself is filled by PD-018b (lane FL05, `_render_client_report_msg`), which the spec assigns that change to.
   - `test_name_field_used_not_bare_phase_id` now asserts the template carries `{client_label}` and not `{name}`, and that the rendered message carries neither the phase id nor a brace.
   - No test deleted, no threshold lowered.

## Regeneration (repository tooling, never hand-edited output)

```
$ python3 -I scripts/ci/phase_doc_sync.py --check
phase_doc_sync: manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json -> manifest_version 75, 56 phases
PHASE_DOC_SYNC_PASS: every phase table and version marker matches manifest_version 75 (56 phases).
rc=0

$ python3 -I scripts/hash-universal-sops-manifest.py --check
PASS: universal-sops content manifest clean (116 files, all sha256 match)
rc=0
```

`phase_doc_sync.py --write` ran after the manifest edit and reported every generated region `unchanged` (no phase id, order, name or version/count moved, so the START-HERE block, SOP-SLIDE-05, DEPARTMENT-COUNTS-CANONICAL and the role version markers are byte-identical). `hash-universal-sops-manifest.py` wrote the restamp, then `--check` returned rc=0 above.

## Manifest acceptance data (parsed-JSON loop, builder evidence only; QC owns the verdict)

- phases: 56; `client_visible: true`: 18
- templates containing `{name}`: 0; templates containing `{client_label}`: 56
- Label validation loop (empty / parenthesis / slash / dot / `P-` / `AF-` / word count outside 2..6 / `{name}` token): 0 violations
- Visible labels in order: Reading your material; Researching your topic; Confirming your answers; Planning the story; Building your sales page; Building your checkout page; Building your video sales page; Writing your slides; Designing the look; Making 3 style samples; Waiting for your style pick; Creating your slide images; Quality check; Assembling your presentation; Building your speaker kit; Writing your speech; Recording audio and video; Final checks and delivery.

## Excluded / not done

- Builders do not run test suites or acceptance commands (builder rule 9). No test was run here; QC runs A1.
- No live action, no network, no client box. All temp files under `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`; scratch under `.../scratchpads/PD-018a`.
