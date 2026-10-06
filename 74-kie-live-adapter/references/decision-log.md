# Decision log (deviations from the architecture memo)

Each entry: decision, evidence, files, why safer, rollback, tests.

## D1. Backend is native-live, not a wrapper around the vendor skill
- Evidence: the vendor kie-models and kie-chat-agents packages contain only SKILL.md and references/en.md (4 unique files, no scripts). See vendor-research.md.
- Files: scripts/kie_live_adapter.py.
- Safer: no third-party code runs on a box; the contract is documented text we implement and test.
- Rollback: delete the folder. Tests: test_adapter_contract.py.

## D2. A live catalog exists; the memo assumed none
- Evidence: GET /api/v1/models returned the catalog on 2026-10-05 (vendor-research.md, row 1).
- Files: scripts/kie_live_adapter.py (discover), references/adapter-contract.md.
- Safer: discovery is real, cached and rate-spaced instead of a static list.
- Rollback: mode off. Tests: Catalog tests.

## D3. Default mode is shadow
- Evidence: the architecture requires no duplicate generation and no double charge while static paths still exist.
- Files: scripts/kie_live_adapter.py (mode), SKILL.md.
- Safer: paid dispatch needs an explicit active setting.
- Rollback: KIE_LIVE_ADAPTER_MODE=off. Tests: test_shadow_mode.py.

## D4. Credit balance uses /api/v1/chat/credit
- Evidence: /api/v1/account/balance returned 404 when probed; /chat/credit is in the vendor reference. Skills 07 and 68 disagree today.
- Files: scripts/kie_live_adapter.py. Safer: one probed endpoint. Rollback: none needed. Tests: Health, Http.

## D5. Fingerprint is taken from the canonical .agents/skills copy
- Evidence: the installer copied the skills into about 55 agent directories; one rewrites SKILL.md in its own format, so scanning every directory reports false drift.
- Files: scripts/vendor_skill_probe.sh, vendor-approval.json. Safer: no false alarms that would train people to ignore the probe. Rollback: delete the probe. Tests: probe printed MATCH on 2026-10-05.

## D6. Hermetic QC with a separate live script
- Evidence: fleet verification runs qc-<folder>.sh on ordinary boxes that may have no key or network.
- Files: qc-74-kie-live-adapter.sh, scripts/live_smoke.sh. Safer: QC cannot spend credits or fail on a flaky network. Rollback: none. Tests: the QC script itself.

## D7. Mode file read-only, outside the skill folder
- Evidence: a per-skill content hash would change if runtime writes landed inside the skill folder, withholding the version stamp.
- Files: scripts/kie_live_adapter.py. Safer: all state in ~/.openclaw/cache/kie-live-adapter. Rollback: delete that directory. Tests: QC folder-unchanged check; test_no_chat_agent_mutation.py.

## D8. Key lookup uses the shared resolver
- Evidence: repo rule: one secret-name canon (shared-utils/secret_names.json). The adapter does not restate aliases.
- Files: scripts/kie_live_adapter.py (_repo_resolver). Safer: same placeholder rejection as the rest of the fleet. Rollback: set KIE_API_KEY in the environment. Tests: test_resolver_used_when_env_empty.

## D9. No .skill package
- Evidence: skill 73 (minimal legal skill) ships none; the gates do not require one for new skills.
- Safer: fewer stale copies. Rollback: n/a.

## D10. QC script named qc-74-kie-live-adapter.sh
- Evidence: the install verifier looks for qc-<folder>.sh first. Task text said qc-kie-live-adapter.sh; the coordinator corrected it.

## D11. Registry entry shape
- The department map uses the key dept_owner (not owner). Skill 74 copies the 66, 67, 68 shape: client_facing false, dept_owner openclaw-maintenance, empty triggers.
