# Install / Update Contract — BlackCEO Signature Page (Skill 71)

## Install model

This skill is repository-native. It is intended to live at:

`71-blackceo-signature-page/`

inside `openclaw-onboarding` and be installed/updated by the repository's existing install/update mechanism. Do not invent a second installer just for this skill.

## Required repository wiring

Follow `REPO-INTEGRATION.md`:

- add Skill 71 to `23-ai-workforce-blueprint/skill-department-map.json`;
- bind it to `web-development` / `landing-page-specialist`;
- add `universal-sops/signature-page-craft/README.md`;
- refresh generated `Skills You Operate` blocks with the canonical stamper;
- rehash content and run repo-consistency gates;
- update conflicting legacy routing so a plain landing-page request reaches Skill 71 rather than Skill 49.

## Skill-local verification

From this skill directory:

```bash
bash verify.sh
```

This checks package integrity, required references/assets, Python syntax, and a small deterministic validator sanity fixture.

This command is for install/update maintenance only. Normal runtime use does not begin by rerunning it.
