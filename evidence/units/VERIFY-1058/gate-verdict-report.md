# VERIFY-1058 — independent adversarial QC of the merged selected-tree gate

Lane: VERIFY-1058 (read-only on product trees; no repo file edited)
Verdict: **FAIL** (acceptance row 3 fails on the real operator copies; zero of the nine
attempt-1 bypasses survive)

## 1. What was verified

| Fact | Proven value |
|---|---|
| Onboarding origin/main | `75a5a26a6bf7298eb4e3e1adcd7465ea4c6ec7c2` (PR #2578) |
| Unit head in task | `13b44bcdfc45c15cf3c51acae38b4091bc81cdfa`, ancestor of origin/main (rc 0) |
| Batch merge | `4d76e5126` (unit into batch), `1d99dd6a4` (origin/main into batch) |
| Merge fidelity | gate, manifest-tree, build-bundles, test, manifest.json, skill-version.txt blobs at `13b44bcd` == origin/main |
| Shipped version | `skill-version.txt` = **v1.0.59** (not v1.0.58 as the row states) |
| Verification worktree | `<portable-drive>/swarm-contract/w77s/lanes/VERIFY1058` (symlink to `.../w77s/worktrees/VERIFY1058`, HEAD `75a5a26a6`, clean) |

Row 1 is met on substance (contains the merged attempt-2 unit head) but not on its
literal version token: the attempt-2 commit stamps **v1.0.59**. `e786ab20e` is the
attempt-1 commit that carries v1.0.58. The row's "v1.0.58" label is stale, not a gate
defect.

## 2. Acceptance row 3 — real operator copies — **FAILS (rc 1)**

```
node 77-council-of-wise-elders/scripts/selected-tree-gate.mjs \
  --skill-dir <operator-home>/.openclaw/skills/77-council-of-wise-elders \
  --agent-selected <operator-home>/.agents/skills/council-of-wise-elders \
  --agent-source test --home <operator-home>
```

Exit 1. Refusals:

```
✗ ERROR: ... both claim 1.0.57 but their trees differ (...) : an update that wrote any other file must not report success
✗ ERROR: SAME-RELEASE PROOF REFUSED: the maintained manifest records no distribution contract
         (distribution {kinds, files, runtime_dist, added_paths}), so it cannot witness a distribution of itself
SELECTED-TREE: FAIL selected=<operator-home>/.agents/skills/council-of-wise-elders via=agent-resolver (test) copies=4
```

Root cause: both real copies are **v1.0.57**, released before `manifest.distribution`
existed. Verified by parsing both manifests: `has_distribution=false` on the maintained
copy; the `.agents` copy is a real 999 distribution (`canonical_aggregate_sha256`
`5cd4642d…`, reconciliation record present) but the witness side cannot describe it.
The gate is fail-closed here by design; the row's premise (operator box already carrying
the release under test) is not true on this box.

## 3. Legitimate-acceptance path — proven sound

A faithful 1.0.59 distribution was built in scratch from the release's **own generated
archive** (`council-of-wise-elders.skill`, sha256 `eeb537fc…`, matching
`manifest.archive.sha256`), anchored to the real canonical manifest
(`aggregate 3b0de855…`, 788 files, 336 built runtime files):

```
node .../selected-tree-gate.mjs --skill-dir <worktree>/77-council-of-wise-elders \
  --agent-selected <fixture> --agent-source "VERIFY-1058 adversarial" --home <fixture-home>
→ rc 0
⚠️ SAME RELEASE: distribution ... is the 999 packaging of canonical aggregate 3b0de855…,
   proven by manifest recomputation (788 recorded files and 336 built files matched)
SELECTED-TREE: OK
```

Observed real content differences (declared and held): 4 Brunson pack files.

## 4. Nine attempt-1 bypasses, re-run against the MERGED gate

Every fixture was built independently in
`<portable-drive>/swarm-contract/w77s/scratch/lanes/VERIFY-1058-selected-tree-gate/work/`
from the real 1.0.59 archive + canonical manifest; the gate was executed as the CLI so
each run proves a `SELECTED-TREE:` line. Harness: `harness.mjs`; logs `run2.log`.

| # | Reproduction | rc | Specific refusal |
|---|---|---|---|
| 1 | Impostor tree sharing ZERO files, self-stamped manifest, copies `canonical_aggregate_sha256` | 1 | `SAME-RELEASE PROOF REFUSED: … does not carry the distribution the release records (CHANGELOG.md (missing); …)` |
| 2 | Extra executable `tools/evil-runner.mjs` outside runtime/dist after regenerating the manifest | 1 | `… carries tools/evil-runner.mjs, which the release neither records nor declares as an added distribution path` |
| 3 | Modified `runtime/dist/export-skill22.mjs` payload | 1 | `… ships runtime/dist/export-skill22.mjs as sha256 3425f278…, but the release built 5f519fcf…: a modified build is not the release's build` |
| 4 | Entry replaced by adding `runtime/dist/evil-entry.mjs` and rewriting `manifest.runtime_entry` | 1 | `… ships runtime/dist/evil-entry.mjs, which the release's recorded build does not contain: an executable the release never built cannot be accepted` |
| 5 | `DISTRIBUTION-RECONCILIATION.json` lying (names a byte-identical file as a difference) | 1 | `SAME-RELEASE PROOF REFUSED: it records CHANGELOG.md as a distribution difference, but that file is byte-identical to the canonical copy` |
| 6 | Arbitrary `hash_method` (`"MD5 whatever the vendor felt like"`) | 1 | `… records hash_method "…", which this gate cannot recompute` |
| 7 | Out-of-tree symlink `advisors/leak.json → /etc/hosts` | 1 | `… cannot be verified: advisors/leak.json is a symlink — a vendored tree must ship regular files…` |
| 8 | Unverified `.skill` archive riding along | 1 | `… carries the archive council-of-wise-elders.skill (sha256 e4956c61…) but the release generated eeb537fc…: an unverifiable archive is not a distribution artifact` |
| 9a | Dangling symlink `advisors/dangling.json → ./does-not-exist.json` | 1 | clean refusal, `SELECTED-TREE: FAIL`, no ENOENT, no stack |
| 9b | Unreadable file (`chmod 000 CHANGELOG.md`) | 1 | `… cannot be verified: CHANGELOG.md unreadable (EACCES: …)`, `SELECTED-TREE: FAIL`, no crash |

**Surviving bypasses: 0/9.** Every run printed a `SELECTED-TREE:` summary and none
produced a stack trace.

## 5. Acceptance row 4 — test suite

```
node --test 77-council-of-wise-elders/scripts/tests/selected-tree-gate.test.mjs
→ rc 0, tests 48, pass 48, fail 0
```
(log: `tests.log`)

## 6. Why FAIL and not PASS

- Zero bypasses survived; the same-release proof is sound and the legitimate 1.0.59
  distribution is accepted.
- Acceptance row 3, as written, does not pass on this box (rc 1). The operator copies
  are v1.0.57 and the maintained manifest carries no `distribution` contract, so the
  merged gate cannot accept that distribution as the same release. This is a box-state
  vs row-premise mismatch, not a bypass — but it is a failed acceptance row, so PASS
  cannot be claimed.
- Acceptance row 1's "skill-version.txt v1.0.58" is stale; the merged tree stamps
  v1.0.59 at the named unit head.

Recommended resolution (owner decision): either roll the operator copies to the
1.0.59 release (and, per the 999 pattern, vendor it) and re-run row 3, or restate row 3
against a witness that carries `manifest.distribution`. No code change is indicated by
this lane: no bypass survived, and the ONLY failure is the stale witness.

## 7. Constraints honoured

Read-only on both repos (worktree `git status --porcelain` = empty); all fixtures under
the lane scratch; no grep, no process listing, no secrets, no paid calls, no live
convene, no helpers/background shells, no `--force`/`-D`/`reset --hard`/`AUTO_SYNC`/
`--no-verify`.

## Artifacts

- `<portable-drive>/swarm-contract/w77s/scratch/lanes/VERIFY-1058-selected-tree-gate/harness.mjs`
- `<portable-drive>/swarm-contract/w77s/scratch/lanes/VERIFY-1058-selected-tree-gate/run2.log`
- `<portable-drive>/swarm-contract/w77s/scratch/lanes/VERIFY-1058-selected-tree-gate/tests.log`
