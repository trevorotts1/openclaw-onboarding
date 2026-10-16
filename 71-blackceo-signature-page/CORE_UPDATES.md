# Core Updates — Skill 71

Skill 71 uses the onboarding repo's **native skill invocation** mechanism rather than manually pasting a second hard-coded skill list into workspace core files.

Canonical binding:

`23-ai-workforce-blueprint/skill-department-map.json`

After adding the Skill 71 entry, run the repo's canonical stamper and fleet-standard generators described in `REPO-INTEGRATION.md`. Do not hand-edit the generated `SKILLS_YOU_OPERATE_V1` block.

No secret values belong in AGENTS.md, TOOLS.md, MEMORY.md, or this skill.

## Cross-repo authoring rule (Item 27)

This skill lives in two repos: the onboarding repo (this copy) and the
999-setup repo (the Claude Code harness edition). The onboarding copy
is the single source of truth. Author changes HERE, then propagate to
999 with `scripts/sync-skill71-to-999.sh` from the onboarding repo
root. Never author neutral content in the 999 copy: the parity checker
(`scripts/check-skill71-parity.py`, classes in
`repo-integration/skill71-sync-allowlist.json`) fails on byte drift,
and the sync refuses while drift would be overwritten silently.

The only files authored on the 999 side are the adapter-class files
named in the allowlist (harness bindings such as SKILL.md's route
section, `references/kie-generation-route.md`, the browser engine
contract, runner profiles, external authorities) and the 999-only
modules (`scripts/kie_transport.py`, `scripts/agnes_route.py`,
`scripts/vercel_deploy.py`, `references/kie-policy-999.json`, the
last of which the sync generates, never hand-edits).
