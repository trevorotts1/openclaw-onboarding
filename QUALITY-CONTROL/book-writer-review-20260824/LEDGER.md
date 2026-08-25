# LEDGER — Book Writer review → fix wave — 2026-08-24

Backups taken BEFORE any fix write:
- Skill 53 full copy: `backups/53-book-writer-pre-fix/` (2.0MB)
- CC repo untouched except two named files; git branch fix/eintr-guard-sync-departments preserved.

## Fix assignments (in flight)

| Agent | Files owned | Items |
|---|---|---|
| fix-engine | run_book_writer.py, book-writer-entry.sh, golden gate-receipts/RUN-LEDGER updates | F01/F03/F05/F06(golden receipts)/R-T2/R-T6/R-T7/R-T8/R-T11/R-P9/R-P15(delivery-side)/R-K1(evidence_root ×3)/R-K2/R-K7 |
| fix-provers | scripts/prove_bw_*.py, _bw_common.py, verify.sh, BOOK-WRITER-MANIFEST.json autofail map only | R-P1..R-P14, R-P18, R-P21, R-CF1(mc_board→pin set), R-CF3(webhook pattern), F02(deep-walk), F04(extensions) |
| fix-docs-board | SKILL.md/INSTRUCTIONS.md/WIRING-SPEC.md/MASTERDOC.md handoff claims, manifest gates_order+stage44 note, mc_board.py slug-clear + cert passthrough, CC presentations-cert-gate.ts + middleware.ts + deep-checks.ts docstring | F09, R-C1, R-C2, R-C3(partial), R-C4, R-C5(note), R-C7(note), R-K3(CC side), R-K5, R-K6, R-K8/K9 notes, R-CF5 |

## Central (me, after agents land)

- [ ] Verify every claimed edit against live files
- [ ] Re-mint ENGINE-PIN.sha256 (mc_board.py now pinned; new hash framing if adopted)
- [ ] Full battery: verify.sh, make_broken.py 18/18, all prover self-tests, golden cert idempotency
- [ ] Sonnet QC pass over the whole diff
- [ ] Residual fixes from QC until clean
- [ ] Release stamping: version bump (1.2.2→1.3.0) across skill-version.txt/SKILL.md/manifest/WIRING-SPEC, README, CHANGELOGs (skill-level; root repo CHANGELOG via release step), annotated git tag
- [ ] Batch merge scoped to book-writer paths (+ 2 CC files)

## Flagged for TREVOR (no GO yet — byte-locked shared IP)

1. prompts/04-tone-style-1/user.md:12 contains the raw "pick a well-known person" instruction that tone-core-manifest F4.3 forbids; na_autopick declared true on stages 04-07 with zero consumers in 53. Fix requires coordinated 52/53/54 re-pin.
2. Same file typo "to modeo" → "to model" (same coordinated edit).
3. Undetermined: whether n8n factories 4d50PNmVOyE9GJWz / KF6PCxzSzKWeOwN6 still fire on live main.blackceoautomations.com.
4. R-C5 extension: writing-rails.md + na_autopick_resolver declared in tone-core-manifest, never baked into 53 — bake-or-drop decision.
