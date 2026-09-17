# Changelog - 58 Podcast Production Engine (58-podcast-production-engine)

## [1.0.3] - 2026-09-17 - activation train: the engine now turns itself on, and the GHL contract points at a surface that answers

Four defects that together meant a fully provisioned box could accept an intake and never produce an episode.

### Activation never ran on any client box (ISSUE-01)
- `provision-podcast-client.sh` verified each activation helper by re-running it as `$helper --check <the same install args>`. Neither shipped helper has ever accepted `--check`; both reject an unknown flag with exit 2. Every provision therefore died at `activation:department` with exit 22 AFTER the department install had already succeeded, so the fleet guarantee (provision implies processor active) was never actually met.
- `activation_step` now takes install arguments and verify arguments separately, split by a `--` separator, and refuses to report a piece ACTIVE when no verify surface was declared. The department step runs `--client-slug <slug> --prime-session` and is verified with `install-podcast-department.sh --verify --client-slug <slug>`; the hook step is verified with the new `register-podcast-hook.sh --verify --client-slug <slug>`.
- `PODCAST_CLIENT_SLUG` is exported once at provision so the helpers' documented env fallback is real.
- New `scripts/tests/test_activation_step_contract.sh` drives the real `activation_step` against fake helpers that reject `--check` exactly as the shipped ones do. It fails 8 assertions against the pre-fix code.

### Nothing on a client box ever ACTIVATED the engine (ISSUE-01)
- `install.sh` only copied the activation files; `update-skills.sh` had no podcast branch at all, and its per-skill wiring loop runs `wire.sh` / `install.sh` / `scripts/install.sh` / `setup-*.sh`, none of which this skill shipped. New `wire.sh` is that entry point: it resolves the client slug (env, else the slug already recorded in the box's registered intake route, else `PODCAST_INTAKE_ROUTE_ID`) and the intake secret, runs the department installer, the hook registrar and `guard-activation-health.py`, refuses to run as root, and never restarts the gateway. With no podcast client on the box it prints a loud WARN naming SOP-PODCAST-07 and exits 0. `install.sh` gained a matching guarded call.

### The queued flow had no trigger, and the shipped GHL contract could not reach one (ISSUE-02, ISSUE-03)
- `register-podcast-hook.sh` now also writes a GATEWAY HOOK MAPPING: `hooks.mappings[]` id `podcast-intake-<slug>`, `match.path` `podcast-intake-<slug>`, `action: agent`, `agentId` the podcast agent, `sessionKey podcast:intake:<slug>`, `sessionMode: persistent`, `wakeMode: now`, `deliver: false`, `allowUnsafeExternalContent: false`, plus a deterministic `messageTemplate` that runs the intake handler in `trigger-flow` mode and then the step driver. That mapping is what converts an inbound survey POST into a podcast agent turn; the plugin route never did, because it accepts only the `{"action":"create_flow"}` envelope.
- The whole request body reaches the template as `{{.}}`, verified against the installed platform's resolver. `{{payload}}` renders empty; there is no whole-body alias.
- The registrar enables the hooks ingress, and when the box has no `hooks.token` it points it at the SAME env label as the route SecretRef (`${PODCAST_INTAKE_HOOK_SECRET}`), so onboarding manages one secret for both surfaces. An existing token owned by another integration is never overwritten. It adds the `hook:` session-key prefix when `hooks.defaultSessionKey` is unset, which the installed gateway requires or it refuses to start. The mapping is prepended so a pre-existing catch-all mapping cannot shadow it, and it fails closed when `hooks.enabled` is explicitly false or the secret label is unset.
- The GHL snapshot contract now matches: custom value 4 is `https://SET-AT-PROVISIONING/hooks/podcast-intake-<client-slug>` and custom value 5 travels as the `Authorization: Bearer` HEADER. The gateway reads the token from `Authorization: Bearer` or `x-openclaw-token` and nowhere else, so the old "header if supported, else payload field" fallback does not work for this endpoint and is documented as such. SOP-PODCAST-02 sections 2.2 and 2.8, `webhook-design.md` sections 1, 7 and 8, `scripts/webhook/README.md`, `route-template.json5` and the SKILL.md trigger contradiction were all corrected to the same contract.
- New assertions in `scripts/tests/test_register_podcast_hook.sh` cover the mapping fields, the template, the token custody rules, `--verify`, and symmetric removal.

### Dead scheduler slice pruned (ISSUE-03)
- Deleted `SCHEDULER.md`, `scripts/podcast_scheduler_runner.sh`, `scripts/install-podcast-scheduler.sh`, `config/launchd/com.openclaw.podcast-scheduler.plist.template`, the repo `config/cron.d/podcast-scheduler` entry and `tests/unit/podcast-scheduler.test.sh`. They polled for a `podcast_controller.py` that exists nowhere in this engine.
- `guard-cron-inventory.py` no longer RECOGNIZES a `podcast-scheduler` cron as a lawful box tick. It contradicted `guard-activation-health.py`, which has always failed a cron naming either dead daemon. A cron naming `podcast-scheduler` or `podcast-controller` is now reported as `AF-PPE-POLLER` and counts against the per-client census.
- `revoke-podcast-client.sh` no longer calls a scheduler installer that does not ship; step 9d scans for dead-daemon cron residue instead.

### Podcast SOPs reach the Command Center library (ISSUE-12)
- `32-command-center-setup/scripts/ingest-sop-library.py --craft-clusters` ingests `universal-sops/<cluster>/SOP-*.md` into the SOP library, mapping `podcast-craft` to department `podcast`. Idempotent by slug, no download, no embedding call, no cost. Carried by `update-skills.sh` step U6c1b, which runs unconditionally, so an already-populated box gets the rows too. `ingest-sop-library.sh` is deliberately NOT touched: its already-populated skip gate is contractually a no-write path and `tests/unit/sop-library-update-path-ingest.test.sh` asserts the database is left byte-identical there.

### Also
- `scripts/provision-podcast-client.sh` gained the bash 3.2 re-exec guard.

## [1.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
