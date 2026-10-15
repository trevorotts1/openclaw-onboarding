# Skill 77 compatibility, preservation, and rollback (CWE-041)

This directory is the compatibility/release-integration deliverable for
Skill 77 (Council of Wise Elders), built under directive Sections 16,
26, and 27. It lives outside the canonical skill folder on purpose:
the skill tree at `77-council-of-wise-elders/` is a recorded release
identity (CWE-039/CWE-040), and nothing here changes a single byte of
it. These artifacts consume the accepted trees as they are.

## Contents

- `compatibility-manifest.json`: the cross-repo compatibility
  manifest (directive Section 27.1). It binds the accepted release
  cohort (openclaw-onboarding `4c5c690cc`, blackceo-command-center
  `f84c0a00`, 999-setup `7e973ad1`) by exact commit and content hash,
  states the shared wire contract (contract package version
  `wise-elders.core/1.0.0`, the per-surface schema versions, the
  endpoint registry contract) and persistence contract (installation
  profile, authority modes, store migration identity, the still
  unallocated Command Center migration placeholder), defines the
  negotiation rules N1 to N9 with their typed refusal codes and
  advisories, enumerates the non-atomic intermediate update states and
  how each is handled, and states the backup/restore/rollback rules
  and receipt fields.
- `negotiate.mjs`: the current release adapter. It derives a
  component descriptor from any of the three repository trees
  (versions, schema surfaces, tree identities computed with the
  canonical hash method, migration status, route groups), and it
  negotiates a skill/Command Center pair against the manifest.
  Negotiation is pure: no writes, no store opens, no session starts.
  A paired session may start only on a `compatible` or
  `compatible-portable` decision; a `not-ready` decision carries typed
  refusal codes and is final for that attempt. CLI:
  `node negotiate.mjs describe onb|cc|999 <root>`,
  `node negotiate.mjs check <skill.json> <cc.json>`,
  `node negotiate.mjs gate <skill.json> <cc.json>`,
  `node negotiate.mjs manifest` (exit 0 compatible, 3 not-ready,
  2 usage error).
- `descriptors/`: snapshots derived from the three accepted trees by
  `fixtures/derive-descriptors.mjs`. The negotiation battery
  re-derives them live and fails on any drift, so the snapshots cannot
  silently go stale.
- `fixtures/`: the acceptance batteries and their machinery.
  - `negotiation-matrix.test.mjs`: the version-negotiation matrix
    (accepted cohort both skill carriers, standalone, contract
    mismatch in both directions, schema-surface mismatch, registry
    mismatch, unrecorded tree, stale vendoring, version skew
    portable, peer ahead of cohort, authority clash, missing
    component, gate/negotiation agreement, live derivation).
  - `not-ready-t116.test.mjs`: T116. New skill plus incompatible
    older Command Center reports not-ready with typed codes and
    starts no shadow session; product leg proves a grantless start
    on the real runtime is refused with RUN_AUTHORIZATION_REQUIRED
    and leaves the session in DRAFT.
  - `stale-worker-t060.test.mjs`: T060. A stale worker holding a
    pre-upgrade state record is refused on both stores
    (COUNCIL_STATE_CONFLICT standalone, PERSISTENCE_STATE_CONFLICT
    canonical) with the stored record byte-identical afterwards and
    journal chains verifying; a session-state payload stamped with a
    pre-upgrade schema version fails contract validation.
  - `clean-install-t115.test.mjs`: T115. A pristine copy passes the
    product doctor and bundle verifier; dependencies are exact pins
    and the isolated install lands exactly those versions; the
    compiled core and CLI bundle exist; tree and archive hashes
    equal the accepted record; generated consumers match canonical
    source (Command Center generated contracts artifact, 999
    per-file canonical hash map, distribution aggregate).
  - `preservation.test.mjs`: sessions, history, verdicts, settings,
    and file inventory survive a tree upgrade (v1.0.1 copy) and a
    rollback to the accepted tree; authority modes recorded at
    install are never forked by a mismatched open.
  - `rollback.test.mjs`: a session caught mid-flight (gated
    transport, process killed) survives the rollback with its ID,
    state, checkpoints, and history intact, then resumes from its
    checkpoint spending exactly the remaining transport calls of an
    uninterrupted run; a data-directory backup/delete/restore round
    trip reproduces the inventory hash for hash.
  - `runtime-driver.mjs`: drives the real built runtime (installed
    isolated copies only) through the scenarios above.
  - `harness.mjs`: scratch, tree copy/install, driver, and
    inventory machinery. Tree B is the upgrade simulation: the
    accepted tree copied, its version bumped to v1.0.1 in the copy
    only, manifest and archive regenerated with the product's own
    bundle script, then installed with the product installer.
  - `run-all.mjs`: prepares both trees once, runs every battery with
    TAP logs captured to the evidence directory, and writes the
    reproducible evidence receipt (`evidence/receipt.json` here, full
    logs under `~/workspace/skill77/cwe-041/evidence/`).
  - `derive-descriptors.mjs`: refreshes or checks the descriptor
    snapshots against the real trees.

## Running

```sh
export TMPDIR=~/workspace/skill77/tmp-scratch
node fixtures/run-all.mjs            # full battery set plus receipt
node --test fixtures/negotiation-matrix.test.mjs   # any single battery
node fixtures/derive-descriptors.mjs --check       # snapshot freshness
```

`runtime_verified` stays false: every battery runs on fixtures and
local services only, and no live provider call is made anywhere in
this directory. The deterministic fixture transport is the product's
own test transport; it spends nothing.
