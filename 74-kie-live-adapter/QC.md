# QC - Skill 74 KIE Live Adapter

## Hermetic gate (runs anywhere, no network, no key)

`bash qc-74-kie-live-adapter.sh` must exit 0. It checks the file set, JSON validity, version agreement (skill-version.txt v1.1.2 and SKILL.md version 1.1.2), registry JSON validity, shell syntax, no file named model-map.json, runs the unit tests (fake transport, plus a localhost stub for the no-mutation test), and proves the skill folder is byte-identical afterwards.

Unit test files in tests/: test_adapter_contract.py, test_shadow_mode.py, test_no_chat_agent_mutation.py, test_registry_commands.py (price, preflight, prompt-budget, validate fallback, latest-family, success-rate, callBackUrl, mode override, registry build with a fake transport).

## Opt-in live check (not part of the gate)

`bash scripts/live_smoke.sh` runs free calls only. `--paid` adds exactly one image job (gpt-image-2-5-sunburst-text-to-image, 1K). Operator account only.

Live smoke status (v1.0.0 release): PENDING. Reason: KIE_API_KEY was NOT-SET in the build environment, and the build rules forbid reading secret files to find it. Run `bash scripts/live_smoke.sh` on an operator box and record the result in references/vendor-research.md.

## v1.1.0 live smoke (recorded)

One paid run in active mode on the operator account: task aaff13916b2be113fc4abf6b1787e9a1, gpt-image-2-5-sunburst-text-to-image, 1K, prompt 19,387 characters (96.9 percent of the 20,000 max), credits_consumed 6.0, balance 3043.03 to 3037.03, saved a valid 1254 x 1254 PNG. Registry built live: 218 models (217 readable schemas). Details in references/vendor-research.md.

## Vendor drift probe (operator or probe box only)

`bash scripts/vendor_skill_probe.sh` installs KIE's official skills into a throwaway HOME and prints MATCH or DRIFT against vendor-approval.json. Result at release: MATCH, tree hash 3871a627...09ac.

## Pass criteria

- qc-74-kie-live-adapter.sh exit 0
- wire.sh twice: second run reports no change
- Shadow mode never calls createTask (test_shadow_mode.py)
- The key never appears in output, receipts or cache (test_no_chat_agent_mutation.py)
