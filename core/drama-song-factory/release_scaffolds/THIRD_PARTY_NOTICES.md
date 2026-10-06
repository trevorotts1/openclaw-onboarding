# Third-party notices — drama-song-ad-factory

Scaffold (W1-07). Full attribution text is completed at release time (W5-02)
after license reverification at implementation time per directive section 8.
Nothing below clears vendored assets or transitive dependencies — inspect
before incorporation.

Source of donor table:
`planning/donor-selections.md` (verified 2026-10-06 via GitHub REST API only,
no donor repo cloned).

## Donor table (all 9)

| # | Repository | Default branch | HEAD SHA (verified) | License (SPDX) | Use |
|---|---|---|---|---|---|
| 1 | `ChrisChen667788/wind-comic` | `main` | `ca24db3ff59ceb2b4c8a520fa06a0d2fc793c398` | MIT | adapt (Character DNA, Style Bible, checkpoints, vision QC) |
| 2 | `holy-templar/drama-song-ad` | `main` | `6206a6db31d5659da4e62a11157e41418d5647b0` | MIT | adapt methodology, concept-level |
| 3 | `cxbxmxcx/commercial-creator` | `main` | `ea6a8a8c46b42a308a3e39138b520f0e92553055` | MIT | adapt (artifact graph, job ledger, shot review) |
| 4 | `HITsz-TMG/VideoClaw` | `main` | `16c1ce0b553e30eff90ff1274e8a8a63c1d548a3` | MIT | adapt (stage retention, resume, pipeline shape) |
| 5 | `A-cat-with-carrots/OnlyShot` | `main` | `75c57f2fff6e2b3ab14004ce635a445e416c9b27` | MIT | concept-only (SOP, failure intelligence) |
| 6 | `harry0703/MoneyPrinterTurbo` | `main` | `68eb5a68b93cfe338198b3dfb151f6d5ec2fe4e5` | MIT | study-only (adapter shape, batch, subtitles) |
| 7 | `FireRedTeam/FireRed-OpenStoryline` | `main` | `c9e945215586f45c12a61c1951ee9a8e9c43a027` | Apache-2.0 | study-only (post-production patterns) |
| 8 | `calesthio/OpenMontage` | `main` | `9327439db69021ab4b0e2776729bf3b58fdb5a87` | AGPL-3.0 | STUDY-ONLY, hard boundary — no AGPL source copied without an explicit license decision |
| 9 | `HBAI-Ltd/Toonflow-app` | `master` | `72a895c26aab3f54c5a914517615362208fa6008` | MIT | study-only (canvas/project model, plugins) |

Repo-endpoint and license-endpoint SPDX agree on all 9 (donor-selections.md).
Toonflow default branch is `master`, not `main`.

## License gate summary

- MIT x7 (donors 1–6, 9): adapt with notices preserved here; never obscure provenance.
- Apache-2.0 x1 (donor 7): study; preserve attribution below if adapted.
- AGPL-3.0 x1 (donor 8): study-only, hard boundary.

## Notices

### MIT donors (1–6, 9)

Each ships the standard MIT notice with its own copyright holders, taken from
that repo's LICENSE file at the inspected commit at release time:

```text
MIT License — <owner/repo> @ <commit>
Copyright holders: <copy verbatim from that repo's LICENSE file>
Permission is hereby granted, free of charge, ... (full text preserved)
```

Applies to: wind-comic, drama-song-ad, commercial-creator, VideoClaw,
OnlyShot, MoneyPrinterTurbo, Toonflow-app — only to the extent code is
copied or adapted. Concept-only / study-only use needs no license text but
provenance stays recorded in `LICENSE-PROVENANCE.md` / `DONOR-MATRIX.md`.

### Apache-2.0 donor (7, FireRed-OpenStoryline)

If adapted, preserve the Apache-2.0 attribution and NOTICE obligations:

```text
Licensed under the Apache License, Version 2.0 — FireRedTeam/FireRed-OpenStoryline @ c9e9452...
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
```

### AGPL-3.0 donor (8, OpenMontage)

No AGPL source in either distribution. Study concepts only. Any future use
requires an explicit license decision first.

## Rejected behaviors (must not ship)

- Wind Comic null/nonblocking audits and aggregate acceptance of failed shots
  must not qualify mandatory QC (donor-selections.md section 1).
- Commercial Creator timeout auto-requeue must not resubmit uncertain paid
  work; use reserved/submitted/unknown/reconciled ledger states (section 3).
