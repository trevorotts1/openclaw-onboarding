# distribution-parity

Shared-fixture parity suite over **both** distributions of the drama-song ad
factory (unit W3-06-U1).

| Side | Distribution | Resolved path (this box) |
|---|---|---|
| A | OpenClaw (`onboarding/75-drama-song-ad-factory`) | `~/openclaw-onboarding/75-drama-song-ad-factory` |
| B | Claude-Nine / Claude Code (`999-setup/.claude/skills/drama-song-ad-factory`) | `<build>/999-setup/.claude/skills/drama-song-ad-factory` |
| C | build-tree staging copy of A (optional third witness) | `<build>/onboarding/75-drama-song-ad-factory` |

## Run

```bash
bash tests/distribution-parity/run_parity.sh
```

Exit `0` = every family PASS, `1` = at least one family FAIL, `2` =
resolve/tooling failure (nothing was compared).

## Families

| Family | What it proves |
|---|---|
| `cli-exit-codes` | One shared fixture set runs through **both** entrypoints; exit codes, `outcome` and `reason_code` are equal across distributions and equal to the `EXIT` map the shipped code defines; envelopes are structurally identical. Also asserts `intake_preflight/__init__.py` and `factory.py` carry the same `EXIT` map (the script-invocation path uses `factory.py`'s literal). |
| `envelope-schema-version` | Every envelope in every scenario carries `blackceo.intake-preflight/envelope/v1`, the same 10-key shape, and the shipped `SCHEMA_VERSION` constant matches. |
| `acceptance-qc-byte-parity` | `scripts/core/acceptance-profile.json` and `scripts/core/contracts/qc-schema.json` are byte-identical across distributions (and against the staging copy when present). |
| `core-sha256-parity` | Every file under `scripts/core/` (excluding `__pycache__` / `*.pyc`) has an identical relative path, identical bytes and an identical tree sha256 in both distributions. |
| `department-wiring-equality` | Shipped `department-wiring/` artifacts are equal across distributions; `skill-department-map.json` carries the slug entry; every department declaration a distribution ships agrees with that canonical entry; the two distributions do not contradict each other. |
| `skillmd-contract-equivalence` | SKILL.md contract clauses are equivalent between the OpenClaw twin (2026-10-06, `v2.3.0`) and the Claude-Nine/Claude Code skill: frontmatter identity, version self-consistency, twin identification, envelope schema_version, control entrypoint, exit-code tables vs shipped code, twelve-stage doctrine, provider skills 66/67/68, twin cross-references. |

`department-wiring-equality` reports one sub-check as **UNDETERMINED** when only
one distribution declares owning-department wiring. Undetermined is recorded,
never counted as a pass (`parity-contract.md` lists host-runtime department
hooks under "may differ").

## Shared fixtures (`fixtures/`)

Same files, both distributions, fixed `--run-id` so envelopes compare
structurally. Expectations below were verified live against the shipped code.

| Fixture | Command | Expected |
|---|---|---|
| `complete-brief.json` | `intake` | exit `0`, `ok` / `complete-brief-zero-questions` |
| `thin-brief.json` | `intake` | exit `2`, `waiting` / `missing-essentials` |
| `injection-brief.json` | `intake` | exit `4`, `rejected` / `untrusted-injection-blocked` |
| `resume-brief.json` + `resume-state.json` | `intake --resume-file` | exit `3`, `parked` / `resume-approval-invalidated` |
| *(none — CLI flags)* | `preflight --root <tmp>` | exit `4`, `rejected` / `approval-missing` |
| *(none — CLI flags)* | `preflight --schema-version parity.evil/v1` | exit `1`, `error` / `schema-untrusted` |

The five exit codes the code defines (`ok 0, error 1, waiting 2, parked 3,
rejected 4`) are all exercised.

## Overrides

| Env | Meaning |
|---|---|
| `DSAF_OPENCLAW_SKILL` | path to distribution A (authoritative; wrong path is exit 2) |
| `DSAF_999_SKILL` | path to distribution B (authoritative; wrong path is exit 2) |
| `DSAF_STAGING_SKILL` | path to distribution C |
| `DSAF_DEPT_MAP` | path to `skill-department-map.json` |
| `BOX_SLUG` | prefix for temp files (`<box>-W3-06-U1-*`) |

## Negative controls (proven on this box, 2026-10-06)

The suite was run against deliberately broken copies to prove it discriminates:

1. **Byte drift** — append a line to `qc_gate.py`, delete
   `acceptance-profile.json`, set the SKILL.md `error` row to `9` →
   `acceptance-qc-byte-parity` FAIL, `core-sha256-parity` FAIL,
   `skillmd-contract-equivalence` FAIL; other families unchanged.
2. **Behavioral drift** — set `factory.py`'s literal
   `EXIT["waiting"] = 7` → `cli-exit-codes` FAIL on the internal map mismatch
   *and* on the live `thin-brief` exit code, `core-sha256-parity` FAIL.
3. **Resolve failure** — `DSAF_OPENCLAW_SKILL=/nonexistent/path` →
   `resolve-failure: ... has no SKILL.md`, exit 2, nothing compared.

stdlib only, no framework, no network.
