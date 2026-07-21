# Changelog - back-yourself-up-protocol

All notable changes to this skill wrapper are documented here.

---

## [v6.5.7] - July 21, 2026 (T2-08 / T0-24: prune only after the replacement verifies)

### Fixed
- **Backup rotation no longer deletes the oldest backup before the replacement exists (T2-08).** "Step 2: Rotate Old Backups" ran *before* the new backup directory was created — the destructive step went first, and verification did not happen until Step 16. Any failure in the copy, disk or verification steps in between left ONE verified restore point instead of the promised two, during exactly the failure window backups exist to cover. Rotation is now the LAST step and is only reachable after verification has passed; it also refuses to delete the backup just created.
- **Every copy's exit status is captured, and a missing critical file fails the run (T0-24).** The copy steps redirected stderr to the null device and captured no exit status, so failed copies from absent sources, permissions or a full disk were invisible; the verification step printed a warning for a missing critical file and reported completion anyway. Copies are now split into required and if-present forms: an absent optional source is noted and fine, but a source that EXISTS and fails to copy is a recorded failure — precisely the case the old redirect discarded. Any recorded failure, or any missing critical file, exits non-zero, leaves the incomplete backup in place for inspection, and deletes nothing.

### Added
- **`scripts/full-backup.sh` — the executable form of the procedure.** The procedure was prose an agent transcribed by hand, so neither defect could be tested and neither could fail. The document remains the human narrative and now points at the script. `tests/unit/full-backup-prune-after-verify.test.sh` exercises it in both directions, and includes a fail-first control that reproduces the pre-fix procedure and asserts the suite's two load-bearing legs still discriminate against it.

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

