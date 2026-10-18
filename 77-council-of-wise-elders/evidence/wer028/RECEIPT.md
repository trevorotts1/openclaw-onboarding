# WER-028 — Final Integration Verification and Release Receipt (repair)

- Unit: W16-U001 — REPAIR of the W14-U001 receipt
- Verifier model: deepseek-chain
- Repair window (UTC): 2026-10-18T23:31:10Z – 2026-10-18T23:35:00Z
- Mode: READ-ONLY across trevorotts1/openclaw-onboarding, trevorotts1/blackceo-command-center and trevorotts1/999-setup. The only written path is `77-council-of-wise-elders/evidence/wer028/`.
- No push, no branch on any remote, no tag, no release, no merge, no client box, no credential read, no `pm2 jlist` / `pm2 describe`.
- All operator home paths below are written as `<operator-home>`.

## Verdict

**RELEASE NOT CERTIFIED.** The two artifacts W14 recorded as in flight are now merged and proven present on current main (B-1 resolved). A new blocker, B-8, is recorded: the Skill 77 `manifest.json` and the `council-of-wise-elders.skill` archive on main were generated from a worktree that contained 16 untracked `evidence/wer028/raw/` files. Manifest parity fails, and both release checkers — `scripts/doctor.mjs` and `scripts/verify-cohort-parity.mjs` — exit 1 at the current head. Repair scope forbids rewriting generated source artifacts, so this receipt records the defect instead of papering over it.

Discipline applied throughout: **capture first, state second.** Every number below is quoted from a file in `raw/` whose own capture timestamp precedes the claim. No later green state is narrated unless it was captured.

## What this repair changed, and the two QC grounds it closes

1. **Fabricated provenance (W14).** W14 cited per-repository protection captures under `raw/` and never wrote those files. This repair actually captured all three repositories' protection state with `gh api … 2>&1`, including the 999-setup HTTP 404, before writing any prose. Files on disk: `raw/protection-openclaw-onboarding.json`, `raw/protection-blackceo-command-center.json`, `raw/protection-999-setup.json`, plus `raw/protection-captures.txt` (per-repo exit code and capture time).
2. **Claim without an artifact at that state (W14).** W14 asserted "39 pass of 39, queried 23:14:40Z" while its stored capture showed 38 success + 1 in progress. This repair captured check runs at current main **first**, and states exactly what those captures hold: onboarding 42 success of 42, all completed, captured 2026-10-18T23:31:45Z; command-center 34 of 34, captured 23:31:46Z; 999-setup 0, captured 23:31:47Z. No gate was in progress at capture time; if one had been, it would be named as in progress here.

## 0. Exact heads used (live, read-only)

| Repository | Ref | SHA | Committer date | How read |
|---|---|---|---|---|
| trevorotts1/openclaw-onboarding | `main` | `39e74434810d9c110f2c6ac506386c832f7b6fb5` | 2026-10-18T23:20:50Z | `gh api repos/trevorotts1/openclaw-onboarding/commits/main` exit 0 |
| trevorotts1/blackceo-command-center | `main` | `800b076907122bd080e774024e6da7b66fb67a73` | 2026-10-18T18:13:36Z | `gh api repos/trevorotts1/blackceo-command-center/commits/main` exit 0 |
| trevorotts1/999-setup | `main` | `a156e4dfb7db831b32b47416cc751d8e803636a1` | 2026-10-18T21:40:30Z | `gh api repos/trevorotts1/999-setup/commits/main` exit 0 |
| openclaw-onboarding | pre-session baseline | `b16266d9d` | — | named by the WER-028 contract |
| blackceo-command-center | pre-session baseline | `ef703e083ed5c839d81fc882a7032623244f1c41` | — | last `main` commit at/before the onboarding baseline timestamp |
| 999-setup | vendored Skill 77 snapshot | `b25d8419a2abb593262d19ffb513197c04ef843f` | — | recorded inside the vendored `manifest.json` |

PR #2280 (`batch/wer026-runner`, head `efb72e94c1d26e33878595d72845d7808f3fc93d`) read with `gh pr view 2280`: `state=MERGED`, `mergeCommit=39e74434810d9c110f2c6ac506386c832f7b6fb5`, `mergedAt=2026-10-18T23:20:50Z`. This is the merge that advanced main from W14's final head `61049cd2` to `39e7443`.

All onboarding reads were taken from a lane clone checked out at `39e7443`; the manifest and archive checks used `git archive 39e7443:77-council-of-wise-elders` extracted to a lane scratch directory.

## 1. Cohort presence on the live main heads

Proof method: `git rev-parse <sha>:<path>` (a tree id for a directory, a blob id for a file; rc=128 means absent). Capture: `raw/cohort-presence-main.txt`, captured 2026-10-18T23:32:08Z.

### openclaw-onboarding (`77-council-of-wise-elders/` at `39e7443`)

| Path | Verdict | Tree/blob proof |
|---|---|---|
| `scripts/supervisor/runner.mjs` | **PRESENT (was absent in W14)** | `592a618f1861177cd4c4f46e876bb7e8ee149f08` (mode 100755, 38,541 bytes) |
| `scripts/supervisor/runner.test.mjs` | PRESENT | `888d4cf7ae886a97ed89602e6fb22f0115d85b8d` |
| `scripts/supervisor/` | PRESENT, 35 files | `5edb5427d63691bf8390e5fd1e62e15da4db1f77` |
| `evidence/wer026/host/` | **PRESENT (was absent in W14)**, 30 files | `e50fc6a8eac5cdd93c50207a65b559efc110b229` |
| `evidence/wer026/local/` | PRESENT, 34 files | `f7dd0f17f5faf791c73c7bd6501291a74e10ba7b` |
| `evidence/wer026/journey/` | PRESENT, 85 files | `0d314bd526a83541d92088231df0f226baadc093` |
| `runtime/src/service/` | PRESENT | `687ca21d97c21023b5f76d788978addbf62c5909` |
| `runtime/src/platform/` | PRESENT | `1e7f380c6f61af3fed6a462ac0ead988e0aa2460` |
| `runtime/src/platform/windows.ts` | PRESENT | `0f06d011a0b9b0975fe2066db4615e8dabd0137d` |
| `runtime/src/remote/` | PRESENT | `9ba555fd37d737b4b59424fe8d5ca9c82551f160` |
| `scripts/verify-cohort-parity.mjs` | PRESENT | `bc37ab535f3c5b9fa6ddb4886ffb114e37529baf` |

Full per-file listing of the supervisor directory and the host acceptance tree, with blob ids and byte sizes: `raw/supervisor-listing-main.txt`, captured 2026-10-18T23:34:01Z (exit 0).

### trevorotts1/blackceo-command-center (`800b0769`)

| Path | Verdict | Blob/tree proof |
|---|---|---|
| `src/lib/council/engine.ts` | PRESENT | `d669970c7d67b6ddfaf71af05cd5a186349a107f` |
| `src/lib/council/intents/` | PRESENT | `7ffbab63d831c8685cc4e63210337899688a6cd8` |
| `src/lib/council/kanban/` | PRESENT | `5364d8328c05afe795a6c7b8d69ea0fee393c7e0` |

### trevorotts1/999-setup (`a156e4d`)

| Path | Verdict | Blob/tree proof |
|---|---|---|
| `scripts/council-runtime-install.sh` | PRESENT | `f29d75d578ceeffa7a9ef70752710f5988152e8e` |
| `scripts/council-runtime-install.ps1` | PRESENT | `b7eeb4d301f023c2bdb3051dd23e293f096b82f8` |
| `launchers/macos/` | PRESENT | `a444f5dab73d4706c4e919430776262fe01bdd20` |
| `launchers/windows/` | PRESENT | `0a263f390c7555a521b2ea035e2dc4866d268c44` |
| PR #240 files (`launchers/windows/*`, `scripts/council-runtime-install.ps1`) | PRESENT | blob ids in `raw/setup-pr240-paths.txt` |

Cross-repo presence and byte-level capture: `raw/cross-repo-checks.txt`, captured 2026-10-18T23:33:24Z.

## 2. Version / manifest / archive parity (onboarding `main` `39e7443`)

Four version markers, all equal to **1.0.15** (capture `raw/version-markers.txt`, 2026-10-18T23:33:53Z, all reads rc=0):

| Marker | Value |
|---|---|
| `skill-version.txt` | `v1.0.15` |
| sibling `version` | `1.0.15` |
| `SKILL.md` frontmatter `version:` | `1.0.15` |
| newest `CHANGELOG.md` entry | `## v1.0.15: runnable supervisor driver and live crash/restart acceptance (WER-026)` |

**Manifest aggregate — recomputed and compared (FAIL).** Recomputed with the exact `scripts/build-bundles.mjs` algorithm (sorted relative paths, per-file SHA-256, aggregate over `"<sha256>  <path>"` lines plus a trailing newline; `manifest.json`, `*.skill`, `runtime/dist` and `runtime/node_modules` excluded) over a `git archive` extraction of `39e7443:77-council-of-wise-elders`:

| Quantity | Recorded | Recomputed |
|---|---|---|
| `file_count` | 585 | **569** |
| `aggregate_sha256` | `e19d41a24881da28d9b317a8fc6bf6f9ad62f49c28a9911b561ad9a0b7ede61f` | **`06d8b2107cd1cfcd5eaee23d278be46b1beb363fa0cc1ec7091bdcd8a278bbf0`** |

The tracked tree has 571 entries under `77-council-of-wise-elders` (569 countable after excluding `manifest.json` and the `.skill`). The manifest lists 16 paths that are **not tracked anywhere in the tree** — every one under `evidence/wer028/raw/` (exact list in `raw/manifest-parity.txt`, 2026-10-18T23:33:57Z). There are zero tree-only paths. The 16 names are exactly W14's uncommitted raw evidence files; the generated artifact was built from a worktree that still contained them.

Manifest `source_commit` is `e0a34cdaf0252737829ede0e9b4f262f9bacd188`, the branch commit the generated artefacts were built from; the merge commit on main is `39e7443`. That generated-artifact relationship is normal — the contamination above is not.

Archive: recorded `archive.sha256` = `d70a0da03e7e8b397f84154b274d855cb3570b1cc1e169214f609e6011330db5`; actual `shasum -a 256 council-of-wise-elders.skill` = `d70a0da03e7e8b397f84154b274d855cb3570b1cc1e169214f609e6011330db5` (match). **`unzip -l` shows 586 entries, of which 16 are the same `council-of-wise-elders/evidence/wer028/raw/*` files** — the distributable leaks the QC evidence that produced it.

Both checkers, run against the `39e7443` tree extraction (captured 2026-10-18T23:34:20Z):

| Command | Exit code | Last line |
|---|---|---|
| `node scripts/doctor.mjs` | **1** | `DOCTOR: FAIL (1 failing check(s))` — `FAIL manifest drift: computed 06d8b210… over 569 files, manifest says e19d41a2… over 585` |
| `node scripts/verify-cohort-parity.mjs` | **1** | `COHORT PARITY: FAIL (1 failing check(s))` — `FAIL skill content changed without moving skill-version.txt: evidence/wer028/raw/…` |

Doctor's other checks pass (nine profile labels, 183 JSON files parsed, no council state files, archive hash matches). One doctor sub-check is always SKIPPED outside a git checkout (Skill 76 source-tree check); that check was reproduced separately in section 4. Raw: `raw/doctor.log`, `raw/parity.log`.

## 3. Required checks on the exact current main heads

Branch protection was captured **before** the prose was written. `gh api repos/trevorotts1/<repo>/branches/main/protection`, stdout+stderr captured, exit code recorded per repo (`raw/protection-captures.txt`, captured 2026-10-18T23:31:35Z):

| Repository | Captured state | File | Exit code |
|---|---|---|---|
| openclaw-onboarding | `enforce_admins=true`; `required_status_checks` absent; `required_pull_request_reviews` absent; force pushes and deletions disallowed | `raw/protection-openclaw-onboarding.json` | 0 |
| blackceo-command-center | `enforce_admins=true`; `required_status_checks` absent; `required_pull_request_reviews` absent; force pushes and deletions disallowed | `raw/protection-blackceo-command-center.json` | 0 |
| 999-setup | HTTP 404 `{"message":"Branch not protected", …}` | `raw/protection-999-setup.json` | 1 |

No required contexts exist, so the check-run state below is the true state of each head, not a merge-policy gate. Counts are over the check runs attached to the exact head SHA in the stored capture:

| Repository | Head SHA | total | pass | fail | in progress | skipped | neutral | captured (UTC) | Capture file |
|---|---|---|---|---|---|---|---|---|---|
| openclaw-onboarding | `39e7443…` | 42 | 42 | 0 | 0 | 0 | 0 | 2026-10-18T23:31:45Z | `raw/check-runs-openclaw-onboarding.json` |
| blackceo-command-center | `800b0769…` | 34 | 34 | 0 | 0 | 0 | 0 | 2026-10-18T23:31:46Z | `raw/check-runs-blackceo-command-center.json` |
| 999-setup | `a156e4df…` | 0 | 0 | 0 | 0 | 0 | 0 | 2026-10-18T23:31:47Z | `raw/check-runs-999-setup.json` |

All 76 existing runs have `status=completed` at capture time; zero in progress, zero skipped, zero neutral. No skipped check is counted as approval anywhere. Capture log with head SHAs and exit codes: `raw/check-runs-captures.txt`.

## 4. Malcom's ownership intact (carried forward, re-confirmed at `39e7443`)

Capture: `raw/malcom-baseline-diff.txt`, 2026-10-18T23:33:11Z.

### 4a. Onboarding — Skill 22 book/persona paths vs pre-session baseline `b16266d9d`

`git diff --name-status b16266d9d..39e7443 -- 22-book-to-persona-coaching-leadership-system/` (exit 0) returns 5 modified files (`INSTALL.md`, `persona-categories.json`, `personas/_section-map.json`, `scripts/build-section-map.py`, `skill-version.txt`) and 6 added persona blueprints (Oprah ×2, Les Brown ×2, Russell Brunson ×2). **No deletion.** `--numstat` on `persona-categories.json`: `280	1`. Exact output in the capture.

Post-registration proof: `git diff --name-status aa4e83a1b..39e7443 -- 22-book-to-persona-coaching-leadership-system/ 77-council-of-wise-elders/advisors/ 77-council-of-wise-elders/scripts/register-skill22-personas.mjs` → **empty output, exit 0**; `git merge-base --is-ancestor aa4e83a1b 39e7443` → exit 0. Nothing moved after Malcom's last registration commit.

### 4b. Command-center — nine portrait assets vs pre-session baseline `ef703e08`

`git diff --name-status ef703e08…HEAD --` over the portrait-owned paths: **75 additions, 0 modifications, 0 deletions**, exit 0 (exact list `raw/cc-portrait-diff.txt`, 2026-10-18T23:33:xxZ). Post-portrait proof: `git diff --name-status 44cfac57f..HEAD -- <same paths>` → **empty output, exit 0**.

Manifest validation at `800b0769`: `seat_count=9`, `entries=9`, `variants=27`; all 27 variant SHA-256 digests and byte lengths recomputed from the files: `bad=0`, `PORTRAIT MANIFEST: PASS` (`raw/cc-portrait-validation.txt`).

### 4c. Skill 76 untouched

- `git diff --stat b16266d9d..39e7443 -- 76-local-embedder` → empty, exit 0.
- Tree ids identical: `b16266d9d:76-local-embedder` = `39e7443:76-local-embedder` = `35e3b3d2cf2a8bb05a82177f60bc270353b68e17`.

### 4d. Literal acceptance reading

The contract's literal test is "an empty diff is the pass". Against the named pre-session baseline the diffs are not empty (11 entries on Skill 22; 75 additions in the CC portrait set). They contain **no deletion**, and on the command-center side **no modification**, of any pre-existing Malcom asset; on the onboarding side the modifications are Malcom's own registration commits. Recorded as blocker B-5 rather than claimed as an empty-diff pass.

## 5. Shared seam compatibility (re-confirmed at current heads)

Capture: `raw/seams.txt`, 2026-10-18T23:33:17Z. Heads: onboarding `39e7443`, command-center `800b0769`, 999-setup `a156e4d`.

| Seam | Onboarding declaration | Counterpart declaration | Verdict |
|---|---|---|---|
| Durable producer / queue canonical contract | `CONTRACT_PACKAGE_VERSION = 'wise-elders.core/1.0.0'` (:57); `wise-elders.operation-receipt/v1` (:772) | identical literals at the same lines | **MATCH.** Files byte-identical: both `sha256 67246fc1533f041d7ac5e7f902a52a1da90e0f84165940a3c76dc8797418d4ae`; `diff -q` exit 0 |
| Route snapshot (pinned selection) | `wise-elders.route-selection/v1` in `runtime/src/providers/selection.ts` and `runtime/src/cli/local-host.ts` | `wise-elders.route-selection/v1` in `src/lib/council/explicit-selection.ts` | **MATCH** |
| Service identity schema | `SERVICE_IDENTITY_SCHEMA = 'wise-elders.service-identity/v1'` (`runtime/src/service/types.ts:18`) | none — grep rc=1 in both other repos | **SINGLE-SIDED — B-6** |
| Platform handoff schema | `HANDOFF_SCHEMA = 'wise-elders.platform-handoff/v1'` (`runtime/src/platform/types.ts:35`) | none — grep rc=1 in both other repos | **SINGLE-SIDED — B-6** |
| Access audience pin | `audience` is a config field (`runtime/src/remote/types.ts:71,117`) | command-center verifies Access through its tenant middleware; no shared literal | **NO SHARED CONSTANT — B-6** |
| 999-setup → runtime entry (`run-council.mjs serve --host --port`, `GET /api/health`) | **not implemented**: `api/health` grep over `runtime/src` rc=1; `'serve'` grep over `runtime/src/cli` rc=1; dispatcher raises `Unknown command` (`runtime/src/cli/dispatcher.ts:793`) | `launchers/macos/blackceo-council-desktop:96,168`; `launchers/windows/blackceo-council-desktop.mjs` | **MISMATCH — B-2** |
| Installer → generated host wrapper signature | canonical template `runtime/src/bridges/claude-nine.ts:207` renders `createClaudeNineHost(options = {}, nativeResolver)` (call at :218) | `scripts/council-runtime-install.sh:240` calls `createClaudeNineHost(bundleNativeResolver, { ...opts, skillRoot })` | **MISMATCH — B-3** |
| Vendored Skill 77 bundle | onboarding main `v1.0.15` (recorded 585 files; recomputed 569 — see §2) | 999-setup vendored `.claude/skills/council-of-wise-elders`: `v1.0.0`, 310 files, aggregate `0c11a84d…`, source commit `b25d8419…` | **MISMATCH — B-4** |

Negative checks all carry same-instrument controls (grep rc: 0=match, 1=no match, 2=error). A probe that names a non-existent directory returns rc=2 and is **not** used as absence evidence; the absence claims above use rc=1 with a matching control at rc=0. Raw: `raw/negative-checks.txt` (2026-10-18T23:34:12Z), `raw/cross-repo-checks.txt`.

The launcher test suites (`RESULT PASS` recorded by W14 for the macOS and Windows-simulation suites; **not re-executed by this repair**) drive stub listeners and a fake entry point. The scope lines were re-read at `a156e4d` and are unchanged: `test-council-desktop-macos.sh:34` writes `$T/stub.cjs`, `:51` writes `$T/fake-run-council.cjs`, and `windows-launcher-simulation.mjs:153` is "simulated end-to-end against stub listeners". They do not close B-2. Raw: `raw/launcher-tests-scope.txt`.

## 6. Deferred — never claimed

None of the following is proven by this receipt, and no line of it may be read as claiming so:

1. **Windows host.** WER-027 (v1.0.13, plus the Windows launcher PR #240 in 999-setup) is engineered and statically verified only. Precise blocker: *Windows execution of the platform observer, the `.ps1` installer and the PowerShell/CMD launchers has never run on a Windows host; static tests and byte inspection are the whole of the evidence.*
2. **Real VPS / container deployment.** Precise blocker: *the cohort has not been installed or exercised on any remote host, container or VPS; only local repository state was inspected.*
3. **Real phone or tablet reaching the Cloudflare origin.** Precise blocker: *no mobile browser has reached the authenticated Council origin; the remote Access topology is declared in code and was never exercised from a phone or tablet.*
4. **Production worker claiming a real `council_run` against the live Command Center database.** Not attempted; mutating production data is not authorized. Precise blocker: *no production worker has claimed a real council_run against the live Command Center database; the durable job path is proven only by repository code and CI.*
5. **Live launchd acceptance of the supervisor runner.** The runner and its crash/restart acceptance are merged on main (PR #2280) and proven present in §1. Precise blocker: *live launchd acceptance — the runner under a real launchd job on a host — is being performed in a separate lane, and no launchd acceptance is claimed here.*
6. **Service identity, platform handoff and Access audience cross-repo equality** (B-6). Precise blocker: *no counterpart declaration exists in the other repository, so equality is unexercised and unproven.*
7. **Installed end-to-end journey through the 999-setup launchers.** Blocked by B-2/B-3/B-4 and never attempted. Precise blocker: *the launcher entry point and the installer wrapper call do not match the canonical runtime on main, so no installed journey could run.*

## 7. Blockers

- **B-1 — RESOLVED.** PR #2280 merged 2026-10-18T23:20:50Z as `39e7443`; `runner.mjs` (blob `592a618f…`) and `evidence/wer026/host/` (tree `e50fc6a8…`, 30 files) are present on main with blob/tree proof.
- **B-2 — launcher entry contract unimplemented.** 999-setup launches `run-council.mjs serve --host <h> --port <p>` and polls `GET /api/health`; the onboarding runtime has no `serve` command and no `/api/health` route (greps rc=1 with controls rc=0; dispatcher raises `Unknown command`). Absent in both the v1.0.15 main tree and the v1.0.0 vendored tree.
- **B-3 — wrapper signature mismatch.** `scripts/council-runtime-install.sh:240` passes `(resolver, options)`; the canonical template on main renders `(options, resolver)`.
- **B-4 — vendored bundle cohort drift.** 999-setup vendors Skill 77 `v1.0.0` (310 files, aggregate `0c11a84d…`) against onboarding main `v1.0.15` (585 recorded / 569 recomputed files, see B-8).
- **B-5 — Malcom baseline diff is not empty.** Exact diffs and attribution in §4; no deletion of any pre-existing asset, and nothing moved after Malcom's last registration commit.
- **B-6 — single-sided seams.** `wise-elders.service-identity/v1` and `wise-elders.platform-handoff/v1` have no counterpart declaration in either other repository; the Access audience is configuration, not a shared constant.
- **B-7 — head movement.** `origin/main` advanced from `61049cd2` (W14 final, v1.0.14) to `39e7443` (PR #2280 merge, v1.0.15) after this wave started. Every assertion here was read at `39e7443`; no W14 count is reused.
- **B-8 — generated artifact contamination (new).** `manifest.json` on `39e7443` lists 16 `evidence/wer028/raw/` paths that are absent from the tracked tree: recorded 585 files / `e19d41a2…`, recomputed 569 / `06d8b210…`. `council-of-wise-elders.skill` contains the same 16 evidence files (586 archive entries). `node scripts/doctor.mjs` exit 1 and `node scripts/verify-cohort-parity.mjs` exit 1 at `39e7443`. Cause: `scripts/build-bundles.mjs` walked a worktree that still held W14's untracked evidence directory. Fixing it requires regenerating the two generated source artifacts with `scripts/build-bundles.mjs` after the evidence directory is tracked or excluded — outside this repair's write scope.

## 8. Acceptance checklist

| Acceptance clause | Result |
|---|---|
| Every artifact cited in `RECEIPT.md` exists on disk | YES — raw index below; every citation resolves to a file in `raw/` |
| Every check-count claim matches a stored capture whose mtime precedes the cited time | YES — see §3 table, one capture file per row |
| In-progress gates named as in-progress at capture time | N/A at capture — all 76 runs `completed`; stated as captured, no later state narrated |
| Branch-protection state for all three repos backed by stored captures, including the 999-setup 404 | YES — `raw/protection-openclaw-onboarding.json`, `raw/protection-blackceo-command-center.json`, `raw/protection-999-setup.json`, plus `raw/protection-captures.txt` |
| `runner.mjs` and `evidence/wer026/host/` verified present on current main with blob proof | YES — §1, `592a618f…` / `e50fc6a8…` |
| Four version markers asserted equal at current main | YES — all `1.0.15` |
| Recomputed manifest aggregate compared to recorded | **YES — COMPARED AND FAILING**: 569 / `06d8b210…` vs 585 / `e19d41a2…` (B-8) |
| Doctor and cohort-parity exit codes recorded | YES — 1 / `DOCTOR: FAIL`, 1 / `COHORT PARITY: FAIL` |
| Required-check state on current heads, SKIPPED separated | YES — §3 (0 skipped, 0 in progress, 42/34/0 pass) |
| Malcom baseline diff shown empty or reported as blocker | REPORTED AS B-5 with exact output |
| Each cross-repo seam constant compared on both sides | YES — §5 |
| Deferred list names every unproven item in blocker form | YES — §6, including the merged-runner / separate-lane launchd note |
| No source file modified, no push, no tag, no release, no merge | YES — §9 |
| Repaired receipt passes the two QC grounds | YES — real protection captures; counts anchored to their own captures |

## 9. Repository hygiene at completion

- Files written (all inside the owned directory): `RECEIPT.md`, `receipt.json`, `raw/*`.
- `git status --porcelain` in the lane checkout shows exactly one entry: `?? 77-council-of-wise-elders/evidence/wer028/`. Nothing outside the owned directory is modified; no source file was touched.
- Commit created locally on branch `unit/W16-U001-wer028-receipt`, based on `39e7443`, containing only the owned directory. **No push, no tag, no release, no merge.** Exact commit sha and post-commit `git status` / `diff --stat` are reported to the workflow harness; `receipt.json` intentionally does not self-approve.
- No worktree, branch or `/tmp` lane folder was removed: this work is not merged and released on `origin/main`, so the hygiene cleanup preconditions are not met.

## 10. Raw evidence index (every cited file)

All text captures had the operator home prefix replaced with `<operator-home>`; no other byte was altered. Timestamps are inside each file unless noted.

| File | What it proves | Captured (UTC) |
|---|---|---|
| `raw/protection-openclaw-onboarding.json` | protection object, `required_status_checks` absent | 2026-10-18T23:31:35Z |
| `raw/protection-blackceo-command-center.json` | protection object, `required_status_checks` absent | 2026-10-18T23:31:35Z |
| `raw/protection-999-setup.json` | HTTP 404 `Branch not protected` with stderr | 2026-10-18T23:31:35Z |
| `raw/protection-captures.txt` | per-repo exit code, bytes, capture time | 2026-10-18T23:31:35Z |
| `raw/check-runs-openclaw-onboarding.json` | 42 runs, all `success`/`completed`, head `39e7443` | 2026-10-18T23:31:45Z |
| `raw/check-runs-blackceo-command-center.json` | 34 runs, all `success`/`completed`, head `800b0769` | 2026-10-18T23:31:46Z |
| `raw/check-runs-999-setup.json` | 0 runs, head `a156e4df` | 2026-10-18T23:31:47Z |
| `raw/check-runs-captures.txt` | per-repo head SHA, exit codes, capture time | 2026-10-18T23:31:47Z |
| `raw/cohort-presence-main.txt` | all cohort paths and blob/tree ids at `39e7443` | 2026-10-18T23:32:08Z |
| `raw/cross-repo-checks.txt` | CC/999-setup presence, B-2/B-3/B-4 probes, vendored identity | 2026-10-18T23:33:24Z |
| `raw/version-markers.txt` | four version markers + recorded manifest values | 2026-10-18T23:33:53Z |
| `raw/manifest-parity.txt` | recorded vs recomputed aggregate, 16 manifest-only paths, archive hash and leaked-entry count | 2026-10-18T23:33:57Z |
| `raw/doctor.log` | `DOCTOR: FAIL`, exit 1, full check list | 2026-10-18T23:34:20Z |
| `raw/parity.log` | `COHORT PARITY: FAIL`, exit 1, failing check | 2026-10-18T23:34:20Z |
| `raw/supervisor-listing-main.txt` | supervisor tree (35 files) and host evidence tree (30 files) with blob ids | 2026-10-18T23:34:01Z |
| `raw/malcom-baseline-diff.txt` | Skill 22 diff vs baseline, numstat, post-registration empty diff, Skill 76 identity | 2026-10-18T23:33:11Z |
| `raw/cc-portrait-diff.txt` | 75 additions / 0 mod / 0 del; post-portrait diff empty | 2026-10-18T23:33:49Z |
| `raw/cc-portrait-validation.txt` | seat_count 9, entries 9, variants 27, bad=0 | 2026-10-18T23:33:43Z |
| `raw/seams.txt` | contract byte identity, route literal, single-sided greps with controls | 2026-10-18T23:33:17Z |
| `raw/negative-checks.txt` | absence probes with same-instrument controls | 2026-10-18T23:34:12Z |
| `raw/launcher-tests-scope.txt` | stub-listener scope lines re-read at `a156e4d` | 2026-10-18T23:34:17Z |
| `raw/setup-pr240-paths.txt` | 999-setup windows launcher + installer blob ids at `a156e4d` | 2026-10-18T23:34:23Z |
| `raw/queried-at.txt` | capture windows for protection and check-run reads | 2026-10-18T23:34Z |

## 11. Reproduction commands (read-only)

```bash
# heads
gh api repos/trevorotts1/openclaw-onboarding/commits/main --jq .sha
gh api repos/trevorotts1/blackceo-command-center/commits/main --jq .sha
gh api repos/trevorotts1/999-setup/commits/main --jq .sha
gh pr view 2280 --repo trevorotts1/openclaw-onboarding --json state,mergedAt,mergeCommit,headRefOid

# branch protection (capture stdout+stderr; 999-setup returns 404)
gh api repos/trevorotts1/openclaw-onboarding/branches/main/protection
gh api repos/trevorotts1/blackceo-command-center/branches/main/protection
gh api repos/trevorotts1/999-setup/branches/main/protection

# check runs on the exact heads
gh api "repos/trevorotts1/openclaw-onboarding/commits/39e74434810d9c110f2c6ac506386c832f7b6fb5/check-runs?per_page=100&filter=latest" --paginate --slurp
gh api "repos/trevorotts1/blackceo-command-center/commits/800b076907122bd080e774024e6da7b66fb67a73/check-runs?per_page=100&filter=latest" --paginate --slurp
gh api "repos/trevorotts1/999-setup/commits/a156e4dfb7db831b32b47416cc751d8e803636a1/check-runs?per_page=100&filter=latest" --paginate --slurp

# presence (tree/blob proof; rc=128 = absent)
git rev-parse 39e7443:77-council-of-wise-elders/scripts/supervisor/runner.mjs
git rev-parse 39e7443:77-council-of-wise-elders/evidence/wer026/host
git rev-parse HEAD:src/lib/council/engine.ts                 # CC clone
git rev-parse HEAD:scripts/council-runtime-install.sh        # 999-setup clone

# version / manifest / archive (against a git archive of 39e7443)
node scripts/doctor.mjs                                      # exit 1 at 39e7443
node scripts/verify-cohort-parity.mjs                        # exit 1 at 39e7443
shasum -a 256 council-of-wise-elders.skill
unzip -l council-of-wise-elders.skill | grep -c wer028       # 16 leaked entries

# Malcom baseline
git diff --name-status b16266d9d..39e7443 -- 22-book-to-persona-coaching-leadership-system/
git diff --name-status aa4e83a1b..39e7443 -- 22-book-to-persona-coaching-leadership-system/ 77-council-of-wise-elders/advisors/
git diff --name-status ef703e08..HEAD -- public/portraits public/council/portraits src/components/council/council-portrait-manifest.ts
git diff --name-status 44cfac57f..HEAD -- public/portraits public/council/portraits

# seams
diff -q <onb>/runtime/src/contracts/schemas.ts <cc>/src/lib/council/contracts/schemas.ts
```
