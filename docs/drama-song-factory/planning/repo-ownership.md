# Repo ownership — BlackCEO internal repos

Live inspection 2026-10-06 ~11:30 -0400. Method per repo: `git fetch origin main`, then `git log origin/main -1 --format=%H`. No repo modified.

## 1. Repo table

| Repo | Default branch | origin/main HEAD sha | Inspected tip subject | Local clone |
|---|---|---|---|---|
| trevorotts1/openclaw-onboarding | main (`refs/remotes/origin/HEAD` -> `origin/main`) | `f7504fe727d984493ddd3a036c8cc303315382ce` (2026-10-06 09:18:17 -0400, Merge PR #1550 batch/auto-merge) | Merge pull request #1550 | `~/openclaw-onboarding` CLONED (`~/openclaw-onboarding`, remote `https://github.com/trevorotts1/openclaw-onboarding.git`) |
| trevorotts1/blackceo-command-center | main (`refs/remotes/origin/HEAD` -> `origin/main`) | `f20edec080e9c5167de577b6ae6290f85db972c6` (2026-10-06 11:12:55 -0400, Merge PR #483) | Merge pull request #483 fix/persona-company-unresolved-house-voice | `~/blackceo-command-center` CLONED (`~/blackceo-command-center`, remote `https://github.com/trevorotts1/blackceo-command-center.git`) |
| trevorotts1/999-setup | main (`refs/remotes/origin/HEAD` -> `origin/main`) | `2992a444ca5544fba864631e1a9570147a071e42` (2026-10-05 20:21:03 -0400, Merge PR #26) | Merge pull request #26 sync/blackceo-signature-page-1.1.0-fix | `~/drama-song-factory-build/999-setup` CLONED (remote `https://github.com/trevorotts1/999-setup.git`) |

## 2. Numbered skill slot scan (`~/openclaw-onboarding`, dirs `[0-9]*` at repo root)

Slots 1–74 contiguous, no gaps (verified numeric sequence). Suffix `-ARCHIVED` occupies slots 11, 13, 21 but numbers stay taken.

Three highest numbered skill dirs:
- `72-motion-video-plus`
- `73-diagnose-explain-fix`
- `74-kie-live-adapter`

Next free slot: **75**.

## 3. CI guards (`.github/workflows/`)

Onboarding: 150 `*.yml` files (plus one archived `qmd-bounded-timeout-guard.yml.ARCHIVED-20260723`, not counted):
ad-pipeline-lockstep, agent-browser-lifecycle-guard, anthology-shared-run-dir-guard, auto-tag-on-merge, backup-prune-after-verify-guard, binding-pair-guard, board-join-chain-guard, book-routing-receipt-guard, both-paths-delivery-guard, bounded-resume-cron-guard, browser-session-truth-guard, capacity-dual-key-heal-guard, cc-app-dir-resolution-guard, cc-company-id-registry-repair-guard, cc-update-only-credential-and-git-sync-guard, cc-watchdog-cron-guard, ceo-fallback-execution-guard, ceo-tools-root-schema-guard, checker-false-fail-guards, cinematic-forge-delivery-guard, claim-provenance-advisory, class-kit-gate, closeout-watchdog-guard, command-center-runtime-config-update-guard, config-injection-shapes-guard, content-pipeline-fail-closed-guard, core-updates-wiring-guard, cron-announce-fail-closed-guard, cron-owner-chat-guard, cron-template-delivery-guard, department-runtime-parity-guard, design-library-and-credential-disclosure-guards, docs-language-guard, documented-entrypoints-and-archived-tombstones-guard, embedded-python-syntax-guard, embedding-integrity-guard, fail-closed-doctrine-gate, fleet-roll-handoff-guard, fleet-standing-fail-open-guard, fleet-validation-harness-guard, floor-wipe-fix-guard, full-env-dump-guard, full-funnel-pipeline, funnel-automation-libraries-guard, ghl-activation-resilience-guard, ghl-auth-fallback-guard, ghl-mcp-supervised-guard, ghl-token-only-guard, gip-band-routing-reconciliation-guard, gws-credential-preservation-guard, hardening-and-fleet-standards-exec-guard, hook-enforcement-parity-guard, installer-contracts-guard, interview-launch-contract, kie-prompt-enforcer-guard, lean-bootstrap-guard, ledger-truth-gate, legacy-agents-list-gate, library-lockstep, memory-activator-guard, memory-cache-prune-guard, memory-corpus-guard, model-selector-guard, no-backup-copies-guard, onboarding-reliability-contracts, one-front-door-full-path-guard, owner-sends-hold-guard, pending-sops-runner-guard, persona-blend-match-quality-guard, persona-set-asset-consistency-guard, persona-task-mode-wiring-guard, phase-6i-reachability-guard, podbean-publish-provisioning-guard, podcast-engine-fail-closed-guard, power-resilience-guard, prebuilt-index-section-tagged-guard, prereqs-declaration-guard, prereqs-schema-guard, presentation-deck-intake-driver-workspace-guard, presentation-deps-gate, presentation-intake-conversation-guard, presentation-intake-miniapp-guard, presentation-intelligence-engines-workspace-guard, presentation-release-matrix, presentation-schedules-guard, presentation-type-contract-guard, presentations-drift-gates, presentations-lockstep, prove-zhe-cc-db-agents-entries-guard, provisioning-completeness-gate-guard, qc-departments-tree-guard, qc-static, qc-summary-provenance-guard, records-pipeline-fail-closed-guard, refresh-stale-roles-retirement-guard, release-ceremony-batching-guard, rescue-rangers-rr015-gates, rescue-rangers-rr023-gates, rescue-rangers-rr025-rr026-gates, rescue-rangers-rr027-gates, rescue-rangers-rr028-gates, rescue-rangers-rr029-notifications, rescue-rangers-rr030-gates, rescue-rangers-rr031-gates, resolve-oc-root-guard, retired-artifacts-ledger-guard, role-workspace-root-collapse-guard, roll-converges-gateway-watchdog-guard, routing-mode-switch-guard, run-retries-ceiling-guard, script-defect-classes-guard, silent-success-guards, single-update-skills-entrypoint-guard, skill-frontmatter-version-guard, skill-manifest-reaper-guard, skill-version-newline-guard, skill23-provisioning-tests, skill23-role-floor-guard, skill38-agents-md-content-version-gate, skill44-e2e, skill44-install-path, social-cron-migration-guard, social-planner-suite-guard, status-writer-resolution-defects-guard, stuck-build-park-guard, tag-ancestry-guard, tag-on-main-guard, toolsearch-directory-guard, type-f-census-guard, u10-anti-copy-guard, u108-department-optout-guard, u11-winner-harvest, u111-any-content-blend-guard, u114-no-exemption-blend-governance-conformance-guard, u116-comms-audience-trigger-guard, u14-blueprint-section-map-guard, u53-crown-executor-single-path-guard, u59-devils-advocate-guard, u98-blend-governs-product-voice-engines-guard, unify-backup-retention-guard, unwired-checks-guard, updater-skill-box-state-guard, updater-traps-1-and-3-guard, updater-write-preflight-guard, vercel-github-archive-guard, version-consistency, video-pipeline-lockstep, wave-list-integrity-guard, wire-no-match-guard, workforce-build-pipeline-guard (all `.yml` suffix).

999-setup: 3 files:
check-docs-fresh.yml, hook-skill-tests.yml, kaizen-tests.yml.

(Command-center workflows, for reference, 12 files: agent-identity-guardrail.yml, auto-tag-on-merge.yml, config-guard.yml, department-optout-wiring-guard.yml, dependency-audit.yml, openclaw-contract-guard.yml, qc-cc.yml, raw-status-writer-guard.yml, report-back-invariant.yml, silent-terminal-stop-guard.yml, update-main-convergence-guard.yml, version-consistency.yml.)

## 4. Changes since audit commits (count only, `git log --oneline <audit>..origin/main`)

- Onboarding: audit `5edc0183514ca5fa980640396d9d3a2f0950181f` (2026-10-06 00:39:50 -0400, Merge PR #1512) → HEAD `f7504fe727d984493ddd3a036c8cc303315382ce` = **228** commits.
- 999-setup: audit `2992a444ca5544fba864631e1a9570147a071e42` (2026-10-05 20:21:03 -0400, Merge PR #26) → HEAD `2992a444ca5544fba864631e1a9570147a071e42` = **0** commits (HEAD equals audit sha).
- Command-center: audit `a657c7b55cd1b1a64b3750c6d9afee6bef34402c` (2026-10-05 16:22:55 -0400, release/R01-cc merge wave) → HEAD `f20edec080e9c5167de577b6ae6290f85db972c6` = **5** commits:
  - `f20edec08` Merge PR #483 fix/persona-company-unresolved-house-voice
  - `a89e5d5fc` fix(persona-backfill): never zero dispatch_attempts on release (PD-TEST-063)
  - `caa5bfceb` fix(persona): pin house voice when task company context unresolved
  - `5aee2627c` Merge PR #482 fix/persona-backfill-triad-deadlock
  - `04a2d2abe` fix(persona-backfill): heal triad-parked persona-less cards (gate/sweep deadlock)
