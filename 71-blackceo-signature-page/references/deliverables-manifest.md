# The Deliverables Manifest (Item 34)

A run ends with a folder someone else can pick up cold: the page, its
assets, its copy, its reports, its hand-offs, its receipts, and a
provenance record tying the delivered page to the exact code, deploy, and
funnel it came from. `scripts/check_deliverables.py` verifies the folder;
`scripts/stage_gate.py report` refuses to generate a final REPORT.md for a
completed run while the checker fails.

## The fixed layout

```
deliverables/
  manifest.json          the generated index: every file, nothing else
  provenance.json        where the page came from (identifiers only)
  page/                  the delivered page code (the run's final HTML)
  assets/                the images and media the page uses
  copy/                  the approved copy the page was built from
  reports/               REPORT.md and REPORT.json
  handoffs/              automation-handoff.json, funnel-completion.json,
                         and the playbook documents the wiring used
  receipts/              the run's stage receipts
```

`manifest.json` is generated, never hand-edited:
`{"run_id": ..., "generated_at": ..., "files": ["page/index.html", ...]}`
with paths relative to `deliverables/`.

## What the checker enforces

- Every manifest entry is present on disk.
- Every file under `deliverables/` is listed in the manifest. An unlisted
  file fails BY NAME: a deliverables folder contains exactly what its
  manifest says, nothing more.
- No junk: browser profiles and session directories, temporary files,
  stray screenshots outside the stages' named evidence sets, dependency
  folders, and VCS internals are forbidden anywhere in the folder.
- No credential material: filenames or content carrying the Amendment 4
  credential names (the GHL Private Integration Token, the Firebase
  refresh token) or private-key material fail outright. Provenance and
  receipts record identifiers and presence booleans, never values.
- Exit 0 only on a clean, complete folder. REPORT.md carries the line
  `Deliverables: complete (N files, manifest verified)` only when the
  checker passes.

## Provenance

```json
{
  "run_id": "...",
  "github": {"owner": "...", "repo": "...", "branch": "...", "commit_sha": "..."},
  "vercel": {"project_id": "...", "deployment_id": "...", "url": "..."},
  "ghl": {"location_id": "...", "funnel_id": "..."}
}
```

Page code lives in the operator's OWN GitHub repo (never borrowed across
accounts) and Vercel deploys from that repo under the operator's own
account. Three bindings are verified against each other, and any mismatch
fails publish-verify BY NAME:

1. the embed URL in Item 32's step binding equals the verified deployment
   URL in the deploy receipt (Row 7's `vercel_deploy`), both recorded in
   `provenance.json`;
2. Item 5's publish-verify fetch hits that exact URL;
3. the fetched page carries the build marker (an HTML comment or meta tag
   with the run ID and commit SHA) matching `provenance.json`.
