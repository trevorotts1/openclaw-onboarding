# Changelog - 30 Fish Audio Api Reference (30-fish-audio-api-reference)

## [7.1.1] - 2026-11-15 - Client voice approval and one production model policy

- Remove stale S2.1 default/fallback instructions left by the Drama-3 migration.
- Add `production-policy.json` and a guarded check/TTS helper. Default to Drama-3;
  honor explicit paid S2.1 selection and reject unsupported/free models.
- Require a separately owner-approved voice fingerprint bound to `MC_COMPANY_ID`.
  Missing, wrong or foreign voices fail. Never auto-approve from runtime settings.
- Read only the selected installation's canonical stores without executing dotenv;
  repair stale QC paths and distinguish offline checks from live/listening proof.
- Command Center vendors the policy with a fingerprint and reads the same local
  approval record. Its separate PR sends the model header and blocks voice fallback.
- Migration: existing installations need independent approval before readiness.
  No client configuration, deployment pin or fleet installation changed here.
- Headless regression tests cover voices, tenant binding, models, secret redaction,
  canonical stores and mocked production requests. No paid/live provider calls.

## [7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
