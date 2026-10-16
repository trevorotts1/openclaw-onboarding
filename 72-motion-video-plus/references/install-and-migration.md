# Installation and migration reference (Skill 72, MG-041)

This document records what installation and upgrade surface already existed
in this repository (discovery), the separation rules that keep client-owned
data safe during an upgrade, and the exact semantics of the upgrade
transaction in `scripts/migrate_install.py` and the runtime rollback in
`shared-utils/motion-render-runtime/rollback.sh`.

## Discovery: what existed before MG-041

- **The skill tree.** Skill 72 is repository-native at
  `72-motion-video-plus/` inside `openclaw-onboarding` and is installed and
  updated by the repository's existing mechanism. `INSTALL.md` states the
  rule plainly: "Do not invent a second installer just for this skill."
  `scripts/migrate_install.py` is therefore not an installer. Delivery of a
  new tree still happens through the repository mechanism and runtime
  provisioning still happens through `provision.sh`. The tool is the
  guarded transaction wrapped around that swap for installations that
  already hold client work.
- **The root updater.** `update-skills.sh` syncs each numbered skill by
  removing the installed tree and copying the release tree in its place.
  The removal is guarded: the tree is scanned before removal, and a tree
  that cannot be fully removed is refused whole and left untouched.
  `shared-utils/` is synced by merging contents, so generated state such as
  `shared-utils/motion-render-runtime/.runtime/` survives an update. A
  content recheck compares per-skill digests and falls through to the full
  sync on any drift. There is no Skill-72-specific code in `install.sh`,
  `update-skills.sh`, `check-updates.sh`, or `force-update.sh` (verified by
  search). **Integration point, named but not edited by MG-041:** the
  per-skill remove-and-copy sync for `72-motion-video-plus` inside
  `update-skills.sh` is where `prepare` should run before the sync and
  `promote` after it. Another crew owns the updater's behavior; the batch
  reconciles the wiring.
- **The shared runtime provisioner (MG-003).**
  `shared-utils/motion-render-runtime/provision.sh` installs the pinned
  engines (Remotion 4.0.535, HyperFrames 0.8.155, GSAP 3.15.0, React
  19.3.0, TypeScript 5.9.3) with `npm ci` from the committed lockfile into
  `.runtime/staging-*`, runs a real launch-and-render readiness probe
  (`probe.mjs`), and only then promotes atomically: the staging directory
  becomes `.runtime/versions/<lock-hash>` and the `.runtime/current`
  symlink flips via a temporary symlink plus rename. A failed or
  interrupted run discards staging and leaves the previously verified
  runtime active. `.runtime/runtime-lock.json` mirrors the active
  version's probe record (`result: "pass"` plus per-engine records) and is
  the proof that a version may serve renders. Before MG-041 there was no
  explicit rollback command for the pointer; `rollback.sh` fills that gap
  without changing pinned versions or the lock format.
- **Job manifest migration (MG-007).** `scripts/migrate_manifest.py`
  migrates one V1 job manifest into a new V2 scaffold beside the original.
  It never modifies its input, refuses to run without `--mode` and
  `--company-id` (exit 2, needs input), refuses VSL modes because a parent
  job is never invented, and validates the migrated manifest against the
  full V2 contracts definition. That is job-level migration; MG-041 adds
  the installation-level transaction around it.
- **Storage conventions.** Job packages live outside the skill tree under
  a storage root: `~/Downloads/openclaw-master-files/motion-videos/` on a
  Mac, a persistent volume such as `/data/motion-videos` on a Docker VPS,
  never ephemeral container storage. V1 manifests carry a `storage_root`
  field.
- **Foundation ordering.** `install.sh` identifies
  `01-teach-yourself-protocol` as the Wave 1 foundation every other skill
  depends on, and states the source-of-truth rule that `INSTALL.md`
  outranks generic install patterns for a skill's own install contract.

## Separation rules: system code vs client-owned data

An upgrade replaces system code only. The transaction classifies every
file in the installed tree before anything moves:

- **Protected prefixes** inside the skill tree are always client-owned:
  `client-data/`, `brand/`, `style-cards/`, `jobs/`, `renders/`,
  `history/`. Assets, brand profiles, style cards, renders, and histories
  are never overwritten by an upgrade.
- **Unknown-file rule:** any installed file the new source tree does not
  ship is treated as client-owned. Operator notes and local additions
  survive by default; the tool must prove a file is system code before it
  may replace it.
- **Documented commands are system surface, never client data.** A
  documented command the release no longer ships is *superseded*: its hash
  is recorded in the journal, the full pre-upgrade backup preserves it
  byte-exact, and promote installs a compatibility wrapper at its path
  (see the wrapper contract below). It is never silently kept live and
  never mistaken for a client file.
- **Conflicts:** if a protected path is also shipped by the new tree, the
  system file wins the live path and the client copy is preserved beside
  it at `<path>.client-preserved`. Nothing the client wrote is deleted.
- **Storage root:** the tool snapshots a sha256 of every file under the
  storage root at prepare and re-verifies it at promote. The only writes
  it ever makes there are additive V2 migration scaffolds beside V1 jobs.
  A storage change during promotion fails the promotion and rolls back.

Client files are copied (never moved) into the transaction vault at
prepare and restored hash-verified at promote. A restore hash mismatch
fails the promotion and rolls the whole upgrade back.

## The upgrade transaction

State lives under `<skills-root>/.skill72-upgrade/`:

- `transactions/<txn-id>/journal.json`: the transaction journal, written
  atomically (temporary file, fsync, previous copy kept as
  `journal.json.prev`, the MG-027 convention). It records the storage
  snapshot, client file hashes, conflicts, superseded commands, findings,
  migration results, and the runtime pointer before and after.
- `transactions/<txn-id>/vault/`: copies of client-owned files.
- `transactions/<txn-id>/backup-skill/`: full copy of the pre-upgrade
  tree, the rollback source of last resort.
- `transactions/<txn-id>/staging-skill/`: the staged new tree.
- `transactions/<txn-id>/retired-skill/`: the old tree after a successful
  swap; `failed-skill/` holds the new tree after a failed promotion, kept
  for inspection. Nothing is deleted by a rollback.
- `transactions/<txn-id>/runtime-lock-before.json`: the active runtime
  lock record as it was before the upgrade.
- `transactions/<txn-id>/receipt.json` and
  `.skill72-upgrade/last-receipt.json`: the outcome receipt.

Commands (stdout is exactly one JSON document):

- `discover`: inventory only. Installed version and identity, runtime
  pointer and per-version lock results, jobs under the storage root
  classified V1 or V2, protected client files, live and stale render
  records.
- `prepare`: refuses while a render is active; snapshots storage; vaults
  client files; backs up the tree; stages the new tree; runs readiness on
  the staged tree; verifies any staged runtime version; optionally
  migrates V1 job manifests.
- `promote`: executes a prepared transaction (see below).
- `upgrade`: `prepare` plus `promote` in one call, one receipt.
- `rollback`: rolls back the latest transaction (or `--txn <id>`).
  Rolling back a merely prepared transaction aborts it. Rollback is
  idempotent: a second rollback exits 0 with status `rolled_back`.
- `status`: prints the last receipt.

### Promotion semantics

1. If a render became active after prepare, promotion is refused (exit 3,
   `MG_INSTALL_RENDER_ACTIVE`) and the transaction stays prepared.
2. The skill tree swap is two renames on one filesystem: live tree to
   `retired-skill/`, staged tree into place.
3. A staged runtime version is copied into `.runtime/versions/<id>` and
   the `.runtime/current` pointer flips atomically (temporary symlink
   plus `os.replace`); `.runtime/runtime-lock.json` is refreshed from the
   new version's record the same way. If `<id>` already exists with a
   different lock record, promotion fails with
   `MG_INSTALL_RUNTIME_VERSION_CONFLICT` rather than overwriting a
   verified version.
4. Client files are restored and hash-verified; conflicts land at
   `<path>.client-preserved`.
5. Compatibility wrappers are installed for removed documented commands.
6. Post-verify: readiness on the live tree, every documented command
   present (real file or wrapper), storage snapshot unchanged, pointer
   where the journal says it should be.
7. Any failure after the swap undoes everything: the new tree moves to
   `failed-skill/`, the retired tree moves back, the pointer flips back,
   and `runtime-lock-before.json` is restored. The receipt reports
   `rolled_back` (exit 5), or `rollback_failed` (exit 6) if the undo
   itself fails. Job data is never deleted by any path.

Re-running `upgrade` against an already-current tree is an idempotent
re-sync: the journal records `MG_INSTALL_ALREADY_CURRENT`, client hashes
are unchanged, and the receipt reports the same version on both sides.

### Readiness gates

Readiness mirrors `verify.sh` in-process, on the staged tree before
promotion and on the live tree after it: required files present, SKILL.md
identity matches the installed skill name, SKILL.md and
`skill-version.txt` in version lockstep, Python sources compile, JSON
parses, `bash -n` on shell scripts, `node --check` on JavaScript, and a
scan for the em dash byte sequence (binary suffixes skipped). A staged
runtime version is ready only when its `runtime-lock.json` parses with
`result: "pass"` and both mandatory engines (Remotion and HyperFrames)
recorded `pass`. Any readiness failure at prepare exits 4 with
`MG_INSTALL_READINESS_FAILED` and promotes nothing: the installed tree
and the runtime pointer are byte-identical to before.

A documented command missing from the release is *not* a readiness
failure. Prepare records it (`MG_INSTALL_COMMAND_REMOVED_IN_RELEASE`) and
promote answers it with a wrapper. Readiness judges whether the new tree
is sound, not whether it kept every old path.

## Runtime pointer semantics and rollback.sh

- `.runtime/current` is a symlink to `versions/<id>`. Promotion only ever
  moves the pointer; a render already running keeps the version directory
  it resolved at launch, so a legacy job finishes on its pinned runtime.
- `shared-utils/motion-render-runtime/rollback.sh [version-id]` flips the
  pointer back. With no argument it targets the newest (by modification
  time) verified version other than the current one. It refuses, exit 1
  with the pointer untouched, when: the target directory is missing; the
  target's `runtime-lock.json` is missing or does not record `pass` for
  the mandatory engines; an active-renders record names a live process;
  or node is unavailable. The flip is atomic (temporary symlink plus
  `mv -Tf`), `.runtime/runtime-lock.json` is refreshed from the target,
  nothing is deleted, and running it while already on the target exits 0.
- `MOTION_RUNTIME_HOME` overrides the runtime home (default: the script's
  own directory) so operators can verify a staged copy and tests can use
  a fixture runtime.

## Active renders and the no-network rule

Render activity is recorded by convention at
`<runtime>/.runtime/active-renders.json`:
`{"renders": [{"job_id": ..., "pid": ..., "started_at": ...}]}`. A record
blocks prepare and promote only while its pid is alive
(`os.kill(pid, 0)`). Dead-pid records are stale: `discover` reports them
and they never block. The refusal is a named finding, never a silent
deferral, and the running render is not signalled, reniced, or otherwise
touched. The migration tool makes no network calls at all: no
network-dependent upgrade path exists that could start during a render.

## Job manifest migration during an upgrade

With `--migrate-jobs --mode <mode> --company-id <id>`, prepare runs the
source tree's `migrate_manifest.py` for each V1 job. Without `--mode` and
`--company-id` the tool exits 2 with `MG_INSTALL_NEEDS_INPUT`, the same
never-guess rule the migrator itself enforces. Each source manifest's
sha256 is checked before and after; a change aborts prepare with
`MG_INSTALL_MANIFEST_SOURCE_MODIFIED`. A migrator failure aborts prepare
with `MG_INSTALL_JOB_MIGRATION_FAILED` and promotes nothing; the job stays
on the V1 path. Manifests are migrated into new revisions beside the
originals, never edited in place.

## Wrapper and error contract

`DOCUMENTED_COMMANDS` in `scripts/migrate_install.py` is the registry of
the skill's documented command surface (18 entries: `verify.sh` and the
`scripts/` entry points), each with its kind and its supported
replacement text. When a release removes one, promote installs a
same-language wrapper at the old path. Running it prints to stderr:

```
MG_INSTALL_COMMAND_REMOVED: <path> was removed by the Skill 72 upgrade. Supported replacement: <replacement>. This wrapper was installed by scripts/migrate_install.py so the old command fails clearly instead of breaking silently.
```

and exits 3. Old commands never break bare: they either keep working,
work through a wrapper that names the replacement, or fail with this
named error.

Exit codes: 0 success; 2 usage or missing operator input; 3 refused, a
render is active; 4 readiness failed, nothing promoted; 5 promotion
failed and was rolled back; 6 rollback itself failed.

Named findings: `MG_INSTALL_RENDER_ACTIVE`,
`MG_INSTALL_READINESS_FAILED`, `MG_INSTALL_RUNTIME_NOT_READY`,
`MG_INSTALL_RUNTIME_VERSION_CONFLICT`,
`MG_INSTALL_MANIFEST_SOURCE_MODIFIED`,
`MG_INSTALL_JOB_MIGRATION_FAILED`, `MG_INSTALL_CLIENT_FILE_CONFLICT`,
`MG_INSTALL_COMMAND_REMOVED_IN_RELEASE`, `MG_INSTALL_COMMAND_WRAPPED`,
`MG_INSTALL_COMMAND_REMOVED` (wrapper output),
`MG_INSTALL_ALREADY_CURRENT`, `MG_INSTALL_PROMOTE_FAILED_ROLLED_BACK`,
`MG_INSTALL_NEEDS_INPUT`, `MG_INSTALL_INPUT_MISSING`,
`MG_INSTALL_SKILL_MISSING`, `MG_INSTALL_NO_TRANSACTION`,
`MG_INSTALL_TXN_STATE`.

## Fixture, tests, and the MG-048 handoff

- Fixture: `tests/fixtures/install/`. `populated/` holds an installed
  1.0.0 tree with client files inside it (brand bible, style card, client
  notes, an operator file, a render draft), a runtime with
  `versions/lock-aaaa1111` (active) and `versions/lock-bbbb2222`, and a
  storage root with one V1 job (`job-legacy-01`) and one V2 job
  (`job-v2-01`). `release/` holds the 1.1.0 tree and runtime versions
  `lock-cccc3333` (probe pass) and `lock-dddd4444` (probe fail). Fixture
  system files are small stand-ins except the real `migrate_manifest.py`,
  `motion_contracts.py`, both schemas, and the example job packages, which
  are committed copies of the shipping files.
- Tests: `tests/unit/test_migration_install.py` (7 tests: discovery,
  upgrade twice with client checksums, legacy replay plus V2 job
  creation, readiness failure, promotion rollback, active-render refusal,
  removed-command wrapper, manual rollback) and
  `tests/unit/test_runtime_rollback.py` (5 tests against a fixture
  runtime). The evidence record is regenerated at
  `tests/evidence/mg041/record.json` on every run.
- MG-048's installed-state migration check can consume the fixture as-is:
  copy `tests/fixtures/install/populated/` and run `discover` against it.
  Rollback semantics it may rely on: the pointer flips only to versions
  whose lock records pass; version directories are never deleted;
  receipts land at `.skill72-upgrade/last-receipt.json` and per
  transaction at `transactions/<txn-id>/receipt.json`; journal states are
  `prepared`, `promoted`, `rolled_back`, `readiness_failed`, `aborted`.

## Honest limits

- The legacy-replay proof in the tests is the installed migrator running
  on a copy of the V1 job plus full contract validation of the migrated
  manifest. A full legacy render needs the playwright/Chromium legacy
  path and is outside this item's fixture.
- The provisioner's apt step was not exercised in the build environment
  (provisioning ran with `MOTION_RUNTIME_SKIP_APT=1`); the probe's real
  browser launch is the hard gate and it passed.
