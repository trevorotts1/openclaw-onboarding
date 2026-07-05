# Changelog — Social Media in a Box (Skill 57)

## v0.2.3 — Wave-0 hardening (T-57-social-media)

Enforcement gaps found in the skills-analysis sweep, fixed at the root. No new
runtime provider, no client names, client providers only.

- **FIX-XC-03k** — `run_social_media.run()` no longer soft-passes an UNMAPPED phase
  checker. New `_run_checker()` fails CLOSED (a required gate can never be a silent
  no-op), mirroring 55's fixed pattern. Added `--self-test`: unmapped-checker
  fail-closed + a manifest-mapping drift guard (every `SOCIAL-MANIFEST.json` checker
  must be mapped) + the P-DELIVER golden/missing-source cases.
- **FIX-XC-08d** — `register-social-cron.sh` registers the weekly-theme cron as a
  SILENT trigger: feature-detected `--no-deliver` (with a no-flag retry + loud warn
  when the CLI lacks it) and a post-register delivery-mode assertion via `cron list`
  (announce/channel delivery is flagged as a silence-doctrine violation).
- **FIX-XC-09c** — `build_manifest.check_no_anthropic` adds an EXACT provider-FIELD
  test (`provider in {anthropic, claude}`): a bare `{provider:"anthropic"}` carrying
  a non-`claude-*` model id sailed past the regex; it now trips `AF-SM-NOANTHROPIC`.
- **FIX-XC-11h** — new **P-DELIVER** phase (the ONLY call site of the pinned
  `label_deliverables.py`): builds the labeled-deliverable manifest from the run's
  PASS artifacts and shells `label_deliverables.py --copy` FAIL-CLOSED
  (`AF-SM-DELIVER-MISSING`); records the deterministic logical dest root on the
  signed certificate. Physical copy target is `$SMIB_DELIVER_DEST` (tests/CI) else
  the `~/Downloads` convention. Added to the 8 publishing modes (before P6-MANIFEST).
- **FIX-S36-59** — `_chk_preflight` always passes `--report` (writes the Owner-Q&A
  source-of-truth `working/preflight/preflight_report.json`) and defaults to `--live`
  on a real client box; offline (dry-run) requires config `probes`, a logged owner
  offline token, or `SMIB_PREFLIGHT_OFFLINE`.
- **FIX-S36-60** — post-publish live GHL verify: `done` is claimed only after an
  INDEPENDENT GET of the live GHL post listing (client PIT) confirms each recorded
  post id (`working/publish/posted_ids.json`) is present — never the poster's own
  `publish_results.json`. `AF-SM-PUBLISH-UNVERIFIED`, fail-closed on a client box.
- **FIX-S36-61** — P7 now BUILDS the §4.4 de-dup snapshot from the SQLite ledger
  itself (this run's posts vs every other run's, + the live listing in `--live`)
  every run, instead of only when a `dedup.json` happened to exist; a corrupt/
  unreadable ledger fails CLOSED (`build_dedup_snapshot`).
- **FIX-S36-62** — `_run_script` captures the prover's stdout+stderr and re-prints
  them on FAILURE so the exact `AF-SM-*` code reaches the operator (the old DEVNULL
  redirects left only a bare `FAILED (exit 2)`).

Regenerated: `ENGINE-PIN.sha256` and the `week` / `day` / `brief` golden
certificates (the P-DELIVER gate changed those modes' gate sets).
