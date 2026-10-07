# tests/install-rollback-proof — W4-04-U1

Clean install + version migration + rollback proof on **scratch copies of both
distributions** (unit W4-04-U1, SWARM-PLAN W4-04). Stdlib only; no network, no
paid dispatch, no provider calls. Nothing outside this folder is written: the
two distribution sources and their git history are read-only, and every run
lives in `/tmp/<box-slug>-W4-04-U1-*` scratch removed by the test that owns it.

## Run

```sh
bash run_install_rollback.sh        # table + non-zero exit on any failure
python3 release_check.py --box <dir>   # verifier alone, against a box
```

Exit `0` = every step PASS, `1` = at least one FAIL, `2` = resolve/tooling
failure (nothing was compared).

## Acceptance

| Clause | Where it is proved |
|---|---|
| **Clean install passes release_check** | `test_fresh_install.py` builds a fresh box holding both distributions and runs `release_check.py` → exit `0`, verdict `PASS`, zero FAIL rows. Re-run by the driver after the receipts exist with `--require-receipts` → `receipts/release-check.json`. |
| **Migration receipt** | `receipts/migration.json` — baseline `v1.0.0` install upgraded to the current release on a scratch copy, both distributions, local run state preserved, release_check `1 → 0`. |
| **Rollback receipt** | `receipts/rollback.json` — after a real migration the install tree is restored byte-identical to the pre-migration snapshot, version stamp back to `v1.0.0`, registry entry gone, run state untouched, release_check reports exactly the baseline failures again. |

Receipts carry `schema: blackceo.install-rollback-proof/v1`, `unit_id:
W4-04-U1`, `covered: [openclaw, nine]`, the full `checks` list, and
`verdict`. `receipts/fresh-box-install.json` and
`receipts/release-check.json` are the verifier's own receipts
(`blackceo.release-check/v1`). `evidence/negative-control-stale-install.json`
is an **expected FAIL** — the control that proves the verifier discriminates.

## Box layout the verifier expects

```
<box>/openclaw-onboarding/75-drama-song-ad-factory/    distribution A (OpenClaw)
<box>/999-setup/.claude/skills/drama-song-ad-factory/  distribution B (Claude-Nine / Claude Code)
<box>/999-setup/CONTROL/bundled-skills.txt             999 install manifest
<box>/999-setup/THIRD_PARTY_NOTICES.md                 notices shipped with B
```

Overrides: `DSAF_OPENCLAW_SKILL`, `DSAF_999_SKILL`, `DSAF_ONBOARDING_REPO`,
`DSAF_NINE_REPO`, `BOX_SLUG` (temp prefix, default `local`), `W404_BOX`
(box path the driver owns).

## release_check families

| Family | What it checks |
|---|---|
| `resolve` | Both install roots, the 999 install manifest and the notices file exist. A **content** gap (missing SKILL.md, unregistered skill) is deliberately not a resolve failure — it must surface as a named manifest FAIL. |
| `manifest-comparison` | Every required file per side (A: SKILL.md, `skill-version.txt`, DEPENDENCY-MANIFEST, notices, contracts, entrypoint; B: SKILL.md, VERSION, CHANGELOG, INSTRUCTIONS, references, adapters, both shipped tests, contracts, entrypoint), the 999 registry entry, both version stamps, and **byte-identical `scripts/core/` across the two distributions** (tree sha256 + identical relative path list). |
| `clean-helper-install` | The **installed copy** is what runs: 7 core modules import from each side's box path, `factory.py intake` returns `ok` / `complete-brief-zero-questions` from both, `preflight` without approval returns `rejected` / `approval-missing` (rc 4, names-only), `ffmpeg` resolves. |
| `supported-versions` | Python at or above the declared floor, envelope `schema_version` pinned to `blackceo.intake-preflight/envelope/v1` on both sides, `tool_version` present. |
| `test-receipts` | B's shipped tests are executed from the box (`test_cli_smoke.py`, `test_parity_layout.py` with `DSAF_CANONICAL_CORE` pointing at distribution A inside the box). |
| `migration-rollback-receipts` | `migration.json` + `rollback.json` exist, parse, carry this unit's schema and id, `verdict: PASS`, and cover both distributions. Absent → UNDETERMINED; with `--require-receipts` → FAIL. |

`UNDETERMINED` is never counted as a pass; the summary prints
`pass/fail/undetermined` separately.

## Migration baseline — real recorded releases, not invented versions

Both baselines are read (read-only) from git history of the two home repos:

| Side | Baseline commit | What it is | Target |
|---|---|---|---|
| A `openclaw-onboarding/75-drama-song-ad-factory` | `f2b99f292…` | `skill-version.txt` = **v1.0.0**, `SKILL.md` not yet shipped | repo `HEAD` = **v2.3.0** (adds `SKILL.md`, updates the stamp) |
| B `999-setup` install manifest | `8203088…` | `CONTROL/bundled-skills.txt` has **no** `drama-song-ad-factory` entry — the exact gap `core/release_scaffolds/DEPENDENCY-MANIFEST.md` records ("source presence alone is not proof of automatic installation", directive 2.4) | repo `HEAD` (registered) |

The B skill folder is byte-identical between those two commits, so the B
migration delta is the registry alone; the receipt records
`nine_changed: []` rather than pretending the package changed.

## Negative controls (proven on this box, 2026-10-06)

1. **Stale install** — a box whose A `SKILL.md` is deleted and whose registry
   entry is stripped → `release_check` exit `1`, verdict `FAIL`, naming
   `A ships SKILL.md` and `999 registry lists drama-song-ad-factory`
   (`evidence/negative-control-stale-install.json`).
2. **Pre-migration baseline** — the same two failures are what the migration
   itself starts from, so `receipts/migration.json` records
   `release_check_exit: 1` before and `0` after.
3. **Absent receipts** — pointed at an empty receipts dir, `release_check`
   exits `0` with both rows UNDETERMINED and **zero PASS rows** (asserted by
   `test_fresh_install.py` on every run, independent of repo state).
4. **Rollback identity** — `receipts/rollback.json` asserts
   `fails_after == fails_baseline`, so a rollback that landed somewhere
   adjacent instead of on the baseline would fail the run.

## Known limits (stated, not hidden)

- The distribution-root `release_check.py` named in
  `core/release_scaffolds/DEPENDENCY-MANIFEST.md` is **still not built** —
  `docs/operating-and-recovery/OPERATING.md` lists it under NOT IMPLEMENTED.
  This folder ships the verifier the clean-install / migration / rollback
  proof runs; it is a test-lane artifact, not a shipped CLI subcommand.
- **Distribution A ships no test files** (`75-drama-song-ad-factory/tests/`
  is empty on this box, verified) → its test-receipt row is UNDETERMINED,
  never a pass. B's two shipped tests are executed and must pass.
- `faster-whisper` is **proven absent** here
  (`import faster_whisper` → `ModuleNotFoundError`, rc 1); its pin is
  deferred to W5-02 per DEPENDENCY-MANIFEST, so the row is UNDETERMINED, not
  a pass. `ffmpeg` is a hard gate and resolves on this box.
- The Python floor (`>= 3.10`) is **declared by this verifier**; the real
  pin lands with W5-02.
- Tree digests compare path + content only; mode bits are not part of the
  digest (nothing in either distribution is executed directly — every
  entrypoint runs as `python3 <path>`).
- Migration/rollback here is **distribution version** migration on scratch
  copies. There is no column-level schema migration in this tree
  (`state_store.py` only gates on `db_version` and tells you to migrate
  first); this unit does not invent one.

## Evidence discipline

- This unit **never writes** `evidence/W4-04/W4-04-U1.verdict.json` — that
  belongs to the independent judge (no self-approval).
- The build root is not a git repository, so there is no commit to attach;
  the folder itself is the artifact.
- Lane logs: `swarm-plans/lanes/W4-04-U1-lane/`.
- Scratch hygiene: `/tmp/<box-slug>-W4-04-U1-*` only, removed per test and by
  the driver (`W404_BOX` deleted at the end of every run).
