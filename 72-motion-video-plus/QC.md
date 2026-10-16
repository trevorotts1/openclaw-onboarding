# Skill 72 QC

## Package / install QC

- Folder is exactly `72-motion-video-plus/` in the onboarding repo.
- `SKILL.md` top-level version equals `skill-version.txt`.
- Required references exist: the entrypoints and layer references
  named in `references/authority-map.md`, including
  `references/status-and-delivery.md`.
- `bash verify.sh` exits 0. It checks the shipped example manifest
  against the preserved V1 schema (`references/legacy-manifest-schema.json`),
  the V2 manifest wrapper's `$ref` into
  `references/contracts-v2.schema.json`, and every shipped V2 mode
  fixture manifest against the resolved V2 manifest definition.
- `python3 scripts/check_authority.py` exits 0: no dead paths from
  the entrypoints, no obsolete production promises in the
  reconciled documents, the four modes and the status-and-delivery
  pointer present where they belong, and the department-map mirrors
  in step.
- No em dashes anywhere in the skill files.
- Skill 72 is present in `skill-department-map.json` as client-facing,
  with a description identical to
  `repo-integration/skill-department-map-entry.json`.
- Primary owner is `video` / `video-editor`.
- Repo stamper/hash/repo-consistency gates pass after integration.

## Runtime QC (per run)

- Package validation gate: `scripts/motion_contracts.py validate`
  reports zero findings before any render is claimed.
- Preflight ran and its worker/segment recommendation was followed.
- Preview gate: previews at the composition's actual aspect and
  full fps under `references/preview-and-review.md` (a reduced-fps
  artifact is labeled `rough_layout_only` and never satisfies the
  motion gate), with the approvals the job's `approval_policy`
  requires recorded against exact content revisions
  (`references/approvals-and-gates.md`).
- Where the job is narrated, `scripts/tts.py` served-model check
  passed for every chunk (or the operator explicitly accepted
  `--allow-unverified`), and the measured durations in
  `durations.json` are the ones the timeline was compiled from.
  Silent and inherited-audio jobs record their no-narration result
  instead; no TTS check is owed for them.
- Review gate: the MG-031 bundle for the artifact carries coverage
  verdict `complete` (covered plus omitted runtime accounts for
  exactly 100 percent), and the MG-033 review records validate on
  write with no self-approval and no claimed 10 against an
  uncalibrated reference.
- `scripts/qc.sh` exits 0: the MG-034 technical QC report (references/technical-qc.md) passes every mandatory check against the compiled plan: dimensions, fps, decoded frame count, compiled duration, stream inventory, mode-aware audio (loudness only where an independent final mix exists, final spoken content present), intent-aware black/freeze sweeps (plan-approved holds and dark beats are not defects; unapproved ones fail by name), alpha against the declared delivery profile, assets and fonts complete, and a complete MG-031 review receipt bound to the artifact's sha256. Any tool failure, missing evidence, or mandatory check that did not run fails the gate by name.
- Delivery gate: the status layer's `deliver()` re-measures every
  mandatory artifact and writes the delivery receipt
  (`references/status-and-delivery.md`) only when nothing mandatory
  is missing. PowerPoint packages carry the platform truth:
  playback inside Microsoft PowerPoint is UNVERIFIED on every
  platform; embed structure and hashes are what is proven.
- Contact sheet reviewed by a human (the 30-second review) on the
  legacy path, where the contact sheet is the review surface.
- `scripts/sweep-chromium.sh` ran on the legacy path; no orphaned headless browsers remain.
- Frame PNGs deleted; the mode's deliverables, animation sources,
  and job records kept in the job folder under the resolved storage
  root.

## Design QC

- Bright, human look: no dark-style designs, no generic AI-polished look.
- Real brand assets and real typography on screen.
- Where the brief includes narration, its delivery matches the brand bible voice notes.
- Music bed is continuous across the whole video with no seams at joins, where the mode's audio plan includes one.
