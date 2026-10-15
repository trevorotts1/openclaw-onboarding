# Council of Wise Elders (77): Changelog

## Unreleased: final packaging (CWE-039)

No version change: versions are taken at merge time only. This entry
records the final packaging of the complete package whose runtime and
nine advisor packs landed in their own units after the v1.0.0
scaffold.

- Runtime and packs: the deliberation runtime, the standalone CLI,
  and all nine advisor packs ship in this package. Every pack's
  qualification is bibliographic_only (CWE-042); config/advisors.json
  pack_status now reads built_bibliographic_only for all nine seats.
- Distributable archive: scripts/build-bundles.mjs now generates
  council-of-wise-elders.skill at packaging. The archived Brunson
  pack copy has the private_scope items removed and prose references
  to them scrubbed (CWE-012 acceptance condition 3); the source tree
  retains the private-scope record.
- Install path: scripts/install-runtime.mjs performs the real
  isolated pinned install plus build (INSTALL.md Step 4), and
  INSTALL.md Step 9 states the live-acceptance terms for the built
  package, including the INSTALLED_NOT_LIVE_VERIFIED record when no
  live run is authorized.
- Housekeeping: the Wave 6 roster comment in lib-onboarding-state.sh
  and the structural test banner no longer describe the package as a
  scaffold with an unbuilt runtime.

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
