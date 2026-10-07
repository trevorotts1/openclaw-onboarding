# distribution-parity-extended

Extended parity suite over the **two packaged distributions** of the drama-song
ad factory (unit PKG-01-U1). Enumerates every packaged skill folder, classifies
every packaged file, and diffs every packaged module + doc — **zero byte drift
between distributions**.

| Side | Distribution | Resolved path (this box) |
|---|---|---|
| A | OpenClaw (`75-drama-song-ad-factory`) | `~/openclaw-onboarding/75-drama-song-ad-factory` |
| B | Claude-Nine / Claude Code (`999-setup/.claude/skills/drama-song-ad-factory`) | `<build>/999-setup/.claude/skills/drama-song-ad-factory` |
| C | canonical build-tree staging (witness) | `<build>/onboarding/75-drama-song-ad-factory` |

## Run

```bash
bash tests/distribution-parity-extended/run_extended_parity.sh
```

Exit `0` = every family PASS, `1` = at least one family FAIL, `2` =
resolve/tooling failure (nothing was compared).

## Families

| Family | What it proves |
|---|---|
| `packaged-inventory` | Every file in every packaged folder is enumerated and classified (core-module / doc / test); both required distributions resolve and are non-empty; no symlink anywhere in a packaged folder (symlinks break clean installs); paths carried by 2+ distributions are byte-compared candidates, distribution-unique paths are recorded **UNDETERMINED — no twin to compare, never a pass**. |
| `module-parity` | `scripts/core/` of A vs B: identical file set, identical per-file sha256, identical tree sha256 (15 files, `73a166e24c16a0b3…` at last green run). A and B must both be **subsets of the canonical staging tree with identical bytes** (the packaged copies derive from canonical, never hand-edited). Canonical-only modules (packaging currency of the staging tree vs the packaged skill) are recorded **UNDETERMINED**, with the two gates that own that question named in the note. |
| `shared-doc-byte-parity` | Every doc (`.md` / `.txt` / `.json` / `VERSION`) carried by **both packaged distributions (A and B)** is byte-identical. `SKILL.md` is excluded here by design: `references/parity-contract.md` makes it a runtime doc compared by contract clauses, not bytes — it is checked in `skillmd-doc-contract`. Canonical staging C is **not** one of the two packaged repos, so its docs are out of scope for this family (only its `scripts/core/` is compared, in `module-parity`); staging docs are packaging-work territory and change while packaging units are in flight. |
| `skillmd-doc-contract` | A/B `SKILL.md` exist and are non-empty; frontmatter names the slug; envelope schema documented on both sides; exit-code tables equal to each other **and** to the shipped `EXIT` maps of both distributions; `EXIT` maps equal across distributions; twelve-stage doctrine declared in both; each names its twin. Full clause equivalence beyond these gates belongs to `tests/distribution-parity` family `skillmd-contract-equivalence`. |
| `packaged-claims` | Falsifiable claims in B's `CHANGELOG.md`: the core-file count must match both packaged trees (drift = FAIL). The claimed tree sha256 is compared against the observed digests; the claim states no hashing formula and the string was not reproducible under any tested layout (both git-style separators, at packaging commit `8203088` included), so it is recorded **UNDETERMINED — recorded, never a pass**. The byte-identity the claim describes is proven directly by `module-parity`. |

`SUMMARY` reports `N sub-check UNDETERMINED (not a pass)` — undetermined is
never counted as a pass (`negative-result contract`).

## Scope boundary (why this suite is green while two others are not)

This unit compares the **two packaged distributions** against each other
(acceptance: "zero byte drift between distributions"). Two gates outside this
lane currently FAIL on the *same* tree for a different question — packaging
currency of the canonical staging tree (it carries 52+ core modules the
packaged distributions do not ship):

1. `tests/distribution-parity` family `core-sha256-parity` (staging witness set
   equality) — rc 1 on last run.
2. B's own `tests/test_parity_layout.py` ("packaged core file set matches
   canonical") — rc 1 on last run.

Both facts are recorded, not hidden: `module-parity` prints canonical-only
module counts as UNDETERMINED with those two gates named as owners. Evidence:
`swarm-plans/pkg/lanes/PKG-01-U1-lane/pkg-01-u1-context-other-gates.txt`.

## Overrides

| Env | Meaning |
|---|---|
| `DSAFX_OPENCLAW_SKILL` | path to distribution A (authoritative; wrong path is exit 2) |
| `DSAFX_999_SKILL` | path to distribution B (authoritative; wrong path is exit 2) |
| `DSAFX_CANON_SKILL` | path to canonical staging C (authoritative; wrong path is exit 2) |
| `DTS_BUILD_ROOT` | alternate build root when the suite runs from a repo checkout |
| `BOX_SLUG` | prefix for temp files (`<box>-PKG-01-U1-*`) |

## Negative controls (proven live on this box, 2026-10-07, box=TrevelynsMini2)

Known-good control on the live trees: rc 0 (5/5 PASS, 68 UNDETERMINED).
All mutations ran on `/tmp/TrevelynsMini2-PKG-01-U1-nc-*` copies; the real
distributions were never touched; temp copies removed afterwards (0 remaining).

| # | Injection | Result |
|---|---|---|
| NC1 | append a line to `scripts/core/qc_gate.py` in a B copy | rc 1 — `module-parity` FAIL (per-file + tree sha differ) |
| NC2 | delete `scripts/core/timing_guard.py` from a B copy | rc 1 — `module-parity` FAIL (set + tree) **and** `packaged-claims` FAIL (count claim 15 vs observed 14) |
| NC3 | copy B's `CHANGELOG.md` into an A copy and append a line (doc becomes shared across A/B with different bytes) | rc 1 — `shared-doc-byte-parity` FAIL (mirror image: plant A's `DEPENDENCY-MANIFEST.md` on a B copy with an appended line → same family FAIL) |
| NC4 | change the `error` exit-table row `1`→`9` in a B copy `SKILL.md` | rc 1 — `skillmd-doc-contract` FAIL (tables differ across distributions) |
| NC5 | plant a symlink under `references/` in a B copy | rc 1 — `packaged-inventory` FAIL (symlink in packaged folder) |
| NC6 | `DSAFX_OPENCLAW_SKILL=/nonexistent/PKG-01-U1` | rc 2 — `resolve-failure: … has no SKILL.md + scripts/core/`, nothing compared |

Evidence: `swarm-plans/pkg/lanes/PKG-01-U1-lane/pkg-01-u1-negative-controls.txt`
and `pkg-01-u1-run-green.txt`.

stdlib only, no framework, no network.
