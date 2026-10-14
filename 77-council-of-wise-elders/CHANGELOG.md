# Council of Wise Elders (77): Changelog

## v1.0.0: Initial canonical scaffold

- Adds the agentskills.io-conformant SKILL.md with the fixed nine-seat
  roster, the exact Section 7 profile label discipline, and the Section
  20.1 front-door phrases with existing-session control resolution.
- Ships the portable package structure: install guide in the literal
  installer-contract order, instructions, examples, core updates,
  prereqs, configuration defaults, references (protocol, scoring,
  source policy, model routing, report template, install matrix,
  troubleshooting), and QC rubric plus bundled QC scripts.
- Registers the skill with the onboarding installer: glob discovery
  counts the folder, the Wave 6 roster in lib-onboarding-state.sh gains
  an explicit entry, the skill-department-map gains the skill 77 entry,
  and the Council deliberation SOP registers in universal-sops.
- Update-flow safety: no council state is stored inside the skill
  folder, so wholesale folder replacement by the update sync cannot
  destroy sessions, briefs, verdicts, or client knowledge.
- Honest scope: the deliberation runtime (runtime/), the standalone
  CLI, the Skill 22 exporter, and the nine advisor knowledge packs are
  scaffolded and marked not-yet-built. They are owned by their own
  build units and are not simulated here. The front door reports the
  council as not ready until they land.
