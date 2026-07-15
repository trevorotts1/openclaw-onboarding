# QC Contract — Cinematic and Web Funnel Engine (Skill 62)

Two separate QC planes apply to this skill (spec Section 18). This file documents both,
and records what has actually been checked for this build unit.

## 1. Engine-build QC (judges the skill implementation itself)

Governed by the binding rulebook:
`/Users/blackceomacmini/Downloads/PROMPT-QC-INSTRUCTIONS.md`.

Non-negotiable rules:

- the builder never grades its own work;
- a separate judge, a different model where possible;
- evidence (quoted primary source, real command output) next to every score;
- an adversarial break-it pass;
- fail closed on placeholders, dead tests, leaks, or unverifiable claims;
- minimum earned score 8.5, with a repair-and-rescore loop below that;
- the full engine only reaches merge-ready when every mandatory checklist unit is
  verified done, not pending/in-progress/failed.

## 2. Generated-website QC (judges every project this engine produces)

Every deployed cinematic site independently proves: approved content unchanged, visual
story matches the brief, every scene clip loads and scrubs, every seam passes calibrated
checks, fast forward/reverse scroll works, no black/white flash, no clipped text, mobile
layout acceptable, reduced-motion version complete, forms/calendars/payments/CTAs work,
tracking events fire, no console errors, no broken links, SEO metadata present,
accessibility gate passes, performance budgets pass, preview/production tied to a known
commit, output survives restart/redeploy. An engine-build QC pass does NOT imply any
generated site passes — that is a separate, per-project certificate.

## 3. What has actually been verified for THIS unit (U2 — skeleton)

Offline checks run and their exact results:

```text
$ bash cinematic-web-funnel-entry.sh --self-test
```
Result: see the checkResults reported by the build unit that ran it — this file records
the checks that exist, not a live-updated log (the ledger/session-log carries the live
per-unit evidence trail).

Checks the skeleton's `--self-test` performs:

1. `python3` present on `PATH`.
2. `skill-version.txt` non-empty and its value's major version agrees with the top-level
   `version:` in `SKILL.md` frontmatter (the same invariant the repository-wide
   `scripts/qc-assert-skill-frontmatter-version.sh` drift gate enforces — this skill was
   also verified against that shared gate directly, not only its own self-test).
3. `CWFE-MANIFEST.json` parses as valid JSON, contains exactly 17 phases with contiguous
   `order` 0..16 and ids `P0-ENVIRONMENT`..`P16-CERTIFY`, and every phase + cross-cutting
   entry has a unique `af_code`.
4. Direct invocation of `run_cinematic_web_funnel.py` without `--nonce`, or with a
   `--nonce` that does not match the front door's run-scoped nonce file, is rejected
   (`AF-CWFE-FRONT-DOOR`) — proving ADR-6 fail-closed behavior.
5. A full pipeline walk against an empty run directory correctly stops at `P0-ENVIRONMENT`
   with `GATE-SCRIPT-MISSING` (no gate scripts exist yet) and does NOT emit a certificate.

## 4. Explicitly NOT covered by this unit's QC

Any check that requires a phase gate script, a provider adapter, a schema, the Next.js
template, GHL/Vercel integration, or the test suite in `tests/` — none of those exist
yet. Marking this unit "done" means the skeleton mechanics are real and self-test-green,
not that the engine can produce a certified site. The independent judge for this unit
should verify exactly that claim and no more.
