# Cross-distribution parity contract

One canonical methodology, two distributions (directive 2.3 / 2.4). This
file states what must be identical, what may differ, where the source of
truth is, and how parity is proven.

## Must be identical across both distributions

- creative doctrine (twelve-stage arc, hard creative rules, lyrics-as-copy,
  no lip-sync default, product-reveal timing)
- project / run schema and contract versions
- provider abstraction and hierarchy (KIE first, not KIE lock-in)
- stage names and the enforced flow
- retry, repair and QC logic
- failure semantics and exit codes
- campaign artifact contract
- licensing and provenance decisions

## May differ

- runtime adapter guidance only (`adapters/claude-nine/` vs
  `adapters/claude-code/`, and the OpenClaw runtime notes)
- integration wiring for the host runtime (board/department hooks), through
  the shared control layer, never around it

## Source of truth and packaging

| Item | Path |
|---|---|
| Canonical core (this build tree) | `<build>/onboarding/75-drama-song-ad-factory/scripts/core/` |
| Packaged copy here | `.claude/skills/drama-song-ad-factory/scripts/core/` |
| CLI entrypoint (both distributions) | `scripts/core/intake_preflight/factory.py` |

The packaged copy exists so a clean 999 install receives the actual control
code it invokes (directive 2.4): a bare reference to an onboarding skill does
not install anything. Do not hand-edit the copy — regenerate it from the
canonical source, then re-run parity.

Canonical-core ownership and the release mechanism are recorded in
`ARCHITECTURE-DECISIONS.md` per directive 2.4; when that file names a
different authoritative path, update the table above and the parity test's
default in the same change.

## How parity is proven

```bash
python3 tests/test_parity_layout.py
```

- Canonical tree present -> byte-for-byte comparison of every file in
  `scripts/core/` (excluding `__pycache__` / `*.pyc`). Any difference is a
  lockstep FAIL; fix by re-copying, not by editing the copy.
- Canonical tree absent (clean client install) -> the test prints
  `PARITY UNDETERMINED` and exits 0. Undetermined is not a pass; record it
  as such.

The same fixtures and CLI envelopes must produce equivalent behavior in a
clean OpenClaw installation and here; neither runtime may bypass a shared
guard.

## Re-sync procedure

1. Re-copy `scripts/core/` from the canonical path above.
2. `python3 tests/test_cli_smoke.py && python3 tests/test_parity_layout.py`
3. Bump `VERSION`, add a `CHANGELOG.md` entry naming what changed.
4. Record contract-version bumps (campaign / artifact / qc / acceptance
   profile) — a contract change re-qualifies consumers and needs migration
   and rollback notes in the release manifest.
