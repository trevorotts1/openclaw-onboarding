# SYNC-MANIFEST — drama-song-ad-factory tree reconciliation (operator only)

> Consumed by the box roll: `sync-manifest.json` records every file of the canonical tree
> (`75-drama-song-ad-factory/`) against its packaged copy, and onboarding is canonical per
> `references/parity-contract.md`.

This page is the human-readable summary of `sync-manifest.json`. It is for the operator: the box
roll reads the JSON, nobody reads this file at run time.

## Sources measured

| side | repo | path | `origin/main` sha | head commit date |
|---|---|---|---|---|
| canonical | `trevorotts1/openclaw-onboarding` | `75-drama-song-ad-factory/` | `9f261888f5f2c97f94e1cfe3c16f366a6ff69fe3` | 2026-10-14 |
| packaged | `trevorotts1/999-setup` | `.claude/skills/drama-song-ad-factory/` | `84aa88407907327bd9b295d3a37d34047b3da992` | 2026-10-14 |

`cut_from: pending-wave1-merge`, `wave1_batch_merge_shas: []` — the wave-1 batch merge had not landed
when this was cut; the conductor restamps both fields when the batch lands.

## Method and control

Four throwaway clones, two independent pairs, nothing measured from an existing working tree:

```
git clone --depth 50 <canonical repo>  /tmp/swi6-onb     git clone --depth 50 <packaged repo> /tmp/swi6-999
git clone --depth 50 <canonical repo>  /tmp/swi6-onb2    git clone --depth 50 <packaged repo> /tmp/swi6-9992
```

Run 1 and run 2 produced byte-identical result JSON (`cmp` exit 0), so no count below is an artifact
of one clone. Independent control: `diff -r -q --exclude=__pycache__ --exclude='*.pyc'` over
`scripts/core/` of both clone pairs returned exit 0 with 0 lines of output. No client box was read
or written by this unit; everything above is from this Mac alone.

## The four measured counts

| count | value |
|---|---|
| canonical files | 729 |
| packaged files | 602 |
| differing (same path, different bytes) | 6 |
| one-sided (present on one side only) | 155 (141 canonical-only + 14 packaged-only) |

582 further paths are byte-identical on both sides; the JSON carries a record for all 743 paths in
the union of the two trees.

## The load-bearing finding: `scripts/core/` is in lockstep

| measure | canonical | packaged |
|---|---|---|
| files under `scripts/core/` | 496 | 496 |
| differing under `scripts/core/` | 0 | 0 |
| one-sided under `scripts/core/` | 0 | 0 |
| `diff -r` (both clone pairs) | exit 0, 0 lines | exit 0, 0 lines |

The four files the intake findings named as drifting are **byte-identical between the two repo
mains** — the 2026-10-10 character-bible fix is already in the canonical tree:

| file | sha256 (both sides) |
|---|---|
| `scripts/core/choice_card/intake_card/intake_card.py` | `6cc1a2c4071fb54f1d61b86f1e0b325655fa55261e51ebb96828a4f711657838` |
| `scripts/core/lip_sync/lip_gate/picture_gate.py` | `8335a13b208523ff7d873423b69048e247772b231e19c215fafacb0d3338877c` |
| `scripts/core/words_fit/words_fit.py` | `300ce955b1fb23f3d08800f4f777301e049c34615f4696466f04b2180d1dbac4` |
| `scripts/core/character_bible/character_bible.py` | `7338bbdc0aacc58346b21f4bd76c8c8991dc51ccd5c2233bad97f3b354c3ee0f` |

`scripts/core/character_bible/test_character_bible_del02.py` carrying `RefuseBeforeAnyWrite` is
present on the canonical side, so the fix is in code, not only in a note.

## Reconciling the box figures (466 / 471 / 16 differing)

The 466-versus-471 file counts, the 16 shared files with different bytes, and the four file names
above were measured **on a client box between its two installed copies**, each at whatever vintage it
last received — the intake findings record that one distribution there never received the roll while
the other was updated separately. Those figures are **not reproducible from the two repo mains**, and
this unit did not touch any box to check them: the claim is scoped to what the repos show.

What the repos show: one canonical tree, one packaged copy, a byte-identical control layer, and only
6 differing paths, all of them top-level documents. So the box numbers describe **install drift, not
repo-side drift**: both installed copies must be refreshed from merged main by the box roll (the SPEC
items 5(c) and 13), never reconciled against each other — which is exactly what this manifest is for.
The canonical changelog still does not carry the 2026-10-10 character-bible release note; that entry
is recorded below as `deferred` to the wave-1 batch workflow, because no unit edits a
`CHANGELOG.md`.

## The 6 differing files

| disposition | path | reason (short form; JSON has the full line) |
|---|---|---|
| `deferred` | `SKILL.md` | wave-1 units SWI-001 (canonical SKILL.md) and SWI-003 (packaged SKILL.md) own it; SWI-006 records the drift and edits nothing here |
| `deferred` | `CHANGELOG.md` | parallel release logs on different version series (v2.9.x vs v2.7.x); the packaged log has the 2026-10-10 character-bible note the canonical log lacks, while the fix itself is byte-identical on both sides; every `CHANGELOG.md` edit belongs to the wave-1 batch workflow |
| `canonical-wins` | `CORE_UPDATES.md` | distribution-specific core-update policy; shared parity rules already live in `parity-contract.md`; canonical newer (`871eab9` 2026-10-11 vs `688ad8f` 2026-10-08) |
| `canonical-wins` | `INSTALL.md` | distribution-specific install contract (canonical `install.sh` / OpenClaw skills dir vs the packaged bundled-skills mechanism); canonical newer (`65a7d7c` 2026-10-13 vs `6e5730e` 2026-10-08) |
| `canonical-wins` | `INSTRUCTIONS.md` | distribution-specific operating instructions; canonical carries the later studio-order work (`8b94b93` 2026-10-13 vs `55a3196` 2026-10-11) |
| `canonical-wins` | `PREREQS.json` | same prerequisites under distribution-specific ids (`skill-*` canonical vs `helper-*` packaged); both sides carry `python-mediapipe` and `face-landmarker-model`; canonical newer (`1f5e3ea` 2026-10-11 vs `2f87448` 2026-10-09) |

## Count per disposition (all 743 records)

| disposition | count |
|---|---|
| `identical` | 582 |
| `canonical-only` | 141 |
| `packaged-only` | 14 |
| `canonical-wins` | 4 |
| `deferred` | 2 |
| `packaged-ahead` | 0 |
| **total** | **743** |

The 141 canonical-only paths are the onboarding-only material the packaged copy does not ship
(`mini-app/` 78, `tests/` 21, `scripts/` 17, `shared-bridge/` 12, `timer-artifacts/` 8, plus 5 root
and `references/` files). The 14 packaged-only paths are the packaged distribution's own material:
`VERSION`, `adapters/claude-code/README.md`, `adapters/claude-nine/README.md`,
`assets/example-brief.json`, `references/studio-bridge-twin-receipt.md`,
`references/twin-sync-fingerprints.json`, `references/twin-sync-receipt.md`,
`tests/test_cli_smoke.py`, `tests/test_launcher_plain_claude.py`,
`tests/test_master_provenance_h12.py`, `tests/test_parity_layout.py`,
`tests/test_single_config_root.py`, `tests/test_studio_bridge_twin.py`, `tests/twin_sync_prove.py`.

## `packaged-ahead`: none — the upstream step copied nothing

No file carries a fix on the packaged side that the canonical side lacks. Every differing path is
either a distribution-specific document (canonical is newer or is the canonical direction per
`parity-contract.md`) or deferred under the unit ownership rule, and `scripts/core/` is byte-identical
both ways. So step 4 of the reconciliation upstreamed zero files, and the branch that carries this
manifest adds only these two files — that is the proof, not an omission.

## What the box roll must take from this

1. Refresh **both** installed copies (packaged and runtime) from merged main; do not reconcile them
   against each other, and never treat the older install as a source of fixes.
2. Read dispositions from `sync-manifest.json`; `canonical-wins` and `canonical-only` mean the
   canonical side wins, `packaged-only` means keep what the package ships, `deferred` means another
   wave-1 unit or the batch workflow owns the file, `identical` means no action.
3. Restamp `cut_from` and `wave1_batch_merge_shas` when the wave-1 batch merge lands.

## Scope of this branch

Only two new files: `75-drama-song-ad-factory/references/sync-manifest.json` and
`75-drama-song-ad-factory/references/sync-manifest.md`. Nothing under `SKILL.md`,
`scripts/core/choice_card/intake_card/`, `scripts/core/intake_preflight/factory.py` or
`scripts/core/research_engine/` was edited — those belong to wave-1 units SWI-001, SWI-002, SWI-003,
SWI-004 and SWI-005. No version bump, no changelog edit, no merge.
