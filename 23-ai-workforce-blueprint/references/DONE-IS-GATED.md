# DONE-IS-GATED — Department Status Contract

**A department is `status:done` ONLY when ALL of the following are true:**

1. `roleLibraryFilled == true` — every role how-to.md is substantive (>= 7KB, no [PENDING], all DMAIC headers present), as verified by `verify-library-gate.sh`.
2. `sopLibraryFilled == true` — the SOP library is substantive (>= 7KB per SOP, no stubs), as verified by `verify-library-gate.sh`.
3. `trioFilled == true` — trio structure (if applicable to this dept), as verified by `verify-library-gate.sh`.
4. `wiringStatus == "done"` — the department agent is registered in `openclaw.json` agents.list, its workspace path resolves on disk, it has a Director/Head/Lead/Architect entry-point role, and connection points are satisfied. Verified by `verify-wiring.sh`.

**A box is `content_verified` ONLY when:**
- The on-box skill content digest (per-skill file-set hash) matches the recorded content manifest for the stamped version (`.onboarding-content-manifest.json`).
- The recorded version in the manifest matches `.onboarding-version`.
- Both are written by `update-skills.sh` after the A3 content gate passes.

## Writers of these proxies and the gate each must call

| Proxy write | Writer (file:approx-line) | Gate required before write |
|---|---|---|
| `.onboarding-version` stamp | `update-skills.sh` ~1407 | A3 content-gate (skill-content-hash.sh: src==dest) |
| `content_verified` | `check-updates.sh` ~144 | A4: reads `.onboarding-content-manifest.json`, recomputes on-box manifest |
| `force-update.sh ok:true` | `force-update.sh` ~212 | A5: now labeled `trigger-fired`, NOT `applied` |
| `status:"done"` per dept | `refresh-build-state-from-index.py` ~204,218 | C2: `roleLibraryFilled AND sopLibraryFilled AND wiringStatus==done` |
| ledger `status:"done"` (converge) | `sync-extensions.sh` ~542 | C3: both `verify-library-gate.sh` + `verify-wiring.sh` must pass |
| `buildCompletedAt` (HOP-4) | `resume-workforce-build.sh` | All depts `status:done` + `wiring_dirty==0` + `library_dirty==0` |

## Enforcement memory

This document is doctrine propagated into the repo. The enforcement is in the CODE above, not in this doc alone. The QC meta-gate (`tests/test-ungated-claim-points.sh`) greps for any new ungated writer and fails CI if one appears.

A rule not auto-failed at a QC gate does not exist.
