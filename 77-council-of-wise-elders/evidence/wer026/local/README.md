# WER-026 acceptance slice A — local, no host service

Unit: W11-U001
Source: trevorotts1/openclaw-onboarding
Base: main @ 53d772a996835c783927f900cb6a6880948e60a3 (post-#2269)
Branch: unit/W11-U001
Worktree: <operator-home>/.claude/state/council-elders/lanes/W11-U001-lane/repo
Host: operator Mac Mini, darwin arm64, Node v24.21.0, npm 11.19.0

No repository source file was changed. The only additions are files under
77-council-of-wise-elders/evidence/wer026/local/.

## Stage results

| Stage | Result | Exit |
|---|---|---|
| 1a. isolated install | PASS | 0 |
| 1b. verify staged release | PASS | 0 |
| 1c. repeat install is a no-op | PASS (prefix byte-identical) | 0 |
| 1d. second build update | PASS (pointer moved) | 0 |
| 1e. previous release usable | PASS | 0 |
| 1f. rollback | PASS (prior release live again) | 0 |
| 2. unrelated-directory invocation | PASS (identical output to repo cwd) | 0 |
| 3. real bounded model probe | BLOCKED_ENVIRONMENT | 3 |
| 4. no service / no daemon | PASS (none registered, none running) | — |

## 1. Install, repeat, update, rollback — real runs

Isolated prefix: `<lane>/prefix` (never the default install location).
Isolated data: `<lane>/prefix/data` (outside release trees, proven in active.json).

Commands are relative to `<lane>`.

Install:
```
node repo/77-council-of-wise-elders/scripts/install-runtime.mjs \
  --root repo/77-council-of-wise-elders --prefix prefix --data-dir prefix/data --json
```
exit 0. Release `rel-7bdc0b6e3565`.
Source manifest: 227 protected files, sha256
7bdc0b6e356588056b0a36102f0743bc0d9ff88499f6d201235be07f3c45e9a7.
Artifact receipt: 300 generated files, sha256
32ee825c36716c74e90ba51e3bd69e6d19f35de279323846e6e943a63601e0f4.
Active pointer: `<lane>/prefix/active.json`.

Verify:
```
node repo/77-council-of-wise-elders/scripts/install-runtime.mjs \
  --prefix prefix --verify-release prefix/releases/rel-7bdc0b6e3565
```
exit 0, `PASS verify-release: rel-7bdc0b6e3565`.

Repeat install (same command as install) exit 0:
`NOOP: release rel-7bdc0b6e3565 already matches ... and verifies; nothing changed`.
A sha256 manifest of every file under `prefix` was taken before and after; the
diff is empty (0 bytes) and shasum diff exited 0. See logs/02-*.

Second build (scratch source only, not repository source): the runtime source
was copied to `<lane>/src-b/runtime` and a marker export appended to
`src-b/runtime/src/index.ts` (sha256
0605015108fe6136f255902f90e1b344096b855f6c85bec8cb6448f99e1f93a6).

Update:
```
node repo/77-council-of-wise-elders/scripts/install-runtime.mjs \
  --runtime-dir <lane>/src-b/runtime --prefix prefix --data-dir prefix/data --json
```
exit 0. New release `rel-a1ab77dff250`; active.json moved to it and records
`previousReleaseId: rel-7bdc0b6e3565`. New source sha256
a1ab77dff250d015f10270015127fe9f4e824dbb831d692aff2269a493350c11, new artifact
sha256 0dcf02be9e1800204151ad8344d4f32cbd2c12c8c7f7fdf38c47c05bf8e4aabb.

Previous release stays usable after the update:
- `--verify-release prefix/releases/rel-7bdc0b6e3565` exit 0.
- `node prefix/releases/rel-7bdc0b6e3565/dist/blackceo-council.mjs doctor --json
  --data-dir <lane>/doctor-old-data` exit 0.
- The new release's doctor exit 0 as well.
- The old binary's sha256 is unchanged from before the update.

Rollback:
```
node repo/77-council-of-wise-elders/scripts/install-runtime.mjs --prefix prefix --rollback
```
exit 0: `PASS rollback: active release is now rel-7bdc0b6e3565 (previous
rel-a1ab77dff250 preserved)`. active.json points at the prior release again;
both release directories remain on disk; the rolled-back CLI runs (doctor exit 0).

## 2. Harness from an unrelated directory

From an empty `/tmp/operator-W11-U001-cwd` (cwd unrelated to the repository and
to the release tree):
```
node <prefix>/releases/rel-7bdc0b6e3565/dist/blackceo-council.mjs models --json
```
exit 0. Same command run with cwd set to the repository root produced
byte-identical output (`diff` exit 0, empty). `doctor --json` also exit 0 from
the unrelated cwd. The installed bundle resolves its own assets from its module
location, not from the caller's cwd.

## 3. Model probe — BLOCKED_ENVIRONMENT

Family: operator-owned configured harness route (`claude-nine-configured`,
Claude Code / Claude-Nine harness). Route discovery from the installed runtime
reports this route composed; it is Trevor's own route, not a client route.
No key or credential value was read, printed, or placed in this receipt.

The shipped dispatcher refuses live route probing before any route, grant or
transport is touched:
```
cd /tmp/operator-W11-U001-cwd
node <prefix>/releases/rel-7bdc0b6e3565/dist/blackceo-council.mjs probe --json
```
exit 3:
```
{"ok":false,"error":{"code":"COUNCIL_FEATURE_NOT_READY",
 "message":"Live route probing is not available in this build yet. It is owned
 by CWE-009, CWE-010, and CWE-049, and this foundation does not simulate it."...}}
```
`runtime/src/cli/model-probe.ts` is a library sequencer; grep of the merged tree
shows it is referenced only by its own test file, and no production composition
wires it into the CLI or local host. The standalone grant approval path also
requires a controlling terminal and refuses headless approval. Therefore no
legitimate end-to-end probe can be run in this headless acceptance session.

This is recorded as BLOCKED_ENVIRONMENT, not a pass. No probe call was made, no
fixture or mock was substituted, and nothing claims a provider response.

## 4. No service, no daemon, no host state

- No system service was registered and no launchd job was loaded. `launchctl
  list` has 616 entries; grep for `council|wise-elders` returns rc 1 (none).
  Control: `launchctl list | grep -c com.apple` returns 515, proving the
  instrument reads the real list.
- `ps -Ao pid,command | grep -E 'blackceo-council|install-runtime|council-of-wise-elders' | grep -v grep`
  returns nothing, rc 1. Control: the same ps pipeline for node processes
  returns pre-existing host processes (Codex, 9router, OpenClaw), proving the
  instrument sees processes.
- Only the lane prefix and lane scratch were written. No Command Center
  database, client box, or client credential was touched.
- Scratch removed after evidence capture: `/tmp/operator-W11-U001-cwd`,
  `/tmp/operator-W11-U001-data`, and the lane-local doctor data directories.
  The guard removes the lane itself after the run.

## Observed, not scored

The offline `doctor --json` command exits 0 from every installed release but
reports `readiness.compiled_cli: "missing"` and `live_route:
"composed_not_probed"`. That is the doctor's own readiness model reading an
installed release tree (which has no SKILL.md sibling), not a failure of the
install, update, rollback or invocation stages proven above. Recorded here so
the observation is not lost; no source change was made for it.

## DEFERRED (not claimed)

- The two scheduled sweeps.
- Supervisor crash/restart recovery.
- A browser session URL.
- A production worker claiming a real council_run.

These need host authority and are not part of this slice.

## Evidence index

- `logs/01-install.log`, `logs/01-hashes.txt` — first install and artifact hashes
- `logs/02-install-repeat.log`, `logs/02-prefix-before.txt`,
  `logs/02-prefix-after.txt`, `logs/02-prefix-diff.txt` — repeat-install no-op
- `logs/03-install-update.log`, `logs/03-active-before-update.json`,
  `logs/03-old-binary-hash.txt` — second build and pointer move
- `logs/04-old-verify.log`, `logs/04-old-doctor.json`,
  `logs/04-new-doctor.json` — previous release usable after update
- `logs/05-rollback.log`, `logs/05-active-before-rollback.json`,
  `logs/05-rollback-doctor.json`, `active/active-after-rollback.json` — rollback
- `logs/06-*` — unrelated-directory invocation and cwd-independence diff
- `logs/07-probe.log` — BLOCKED_ENVIRONMENT evidence (exit 3)
- `logs/08-process-service-checks.txt` — ps and launchctl proofs with controls
- `logs/09-post-cleanup-checks.txt` — post-cleanup proof (no /tmp lane paths, no
  council processes, launchctl rc 1, only the worktree remains in the lane)
- `active/` and `receipts/` — active.json snapshots, release receipts, ROLLBACK.md
- `receipt.json` — machine-readable summary
