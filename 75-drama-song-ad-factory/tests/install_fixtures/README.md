# Supported install fixtures — Skill 75 (S75-T33)

Ledger row: **Supported install fixtures 0/2, UNVERIFIED**.
This directory is the **authoring half**: two flavor fixtures plus a harness that
emulates each repository's own declared install path inside a throwaway sandbox.
The **execution half** — running each path against a finished package candidate —
is listed under *Still owed* below.

Nothing here runs `install.sh`, installs a package, or writes to a real config root.

## Flavors

| | ONB | N999 |
|---|---|---|
| Repository | `trevorotts1/openclaw-onboarding` | `trevorotts1/999-setup` |
| Fixture | `flavor-onb.json` | `flavor-n999.json` |
| Source | `75-drama-song-ad-factory/` | `.claude/skills/drama-song-ad-factory/` |
| Install entry | `install.sh` Step 5 | `AGENT_INSTALL.md` §5 |
| Destination | `$HOME/.openclaw/skills/75-drama-song-ad-factory` (default branch of `discover_skills_dir`, `install.sh:2332-2335`) | `$HOME/.claude/skills/drama-song-ad-factory` (`AGENT_INSTALL.md:127-128`) |
| Copy semantics | per item: `cp -r` dirs, `cp` files, seven identity `.md` files skipped (`install.sh:3989,3994-3996`) | whole skill directory |
| Co-install | `74-kie-live-adapter` (numbered skill, same copy loop) | `drama-studio` (the `shared-bridge` symlink target) + `74-kie-live-adapter` via `installer-registration/helper-deps.py` |
| Second root | none | `~/.claude-nine/skills` via `sync-nine-skills.sh` (symlink what is missing) |
| `shared-bridge` | real directory containing `studio_bridge.py` | symlink → `../drama-studio`, must survive as a symlink |
| Version markers | `skill-version.txt` = `SKILL.md` frontmatter `version` | `VERSION` = `skill-version.txt` = `SKILL.md` frontmatter `version` |
| Flavor-only dirs | — | `adapters/`, `assets/` |

Every citation above is also embedded in the fixture's `install_contract.evidence`.
The repository root `version` (`v27.1.65`) is the **onboarding bundle** marker, not a
skill marker, and is deliberately not compared.

**Why helper 74 is co-installed.** The installed `factory.py intake` resolves the KIE
model registry by walking up from the installed module for
`74-kie-live-adapter/references/kie-model-registry.json` (and the equivalent
`skills/`, `.claude/skills/`, `installer-registration/helpers/` relatives). With only
skill 75 installed the entrypoint returns `outcome=error`,
`reason_code=intake-failed`, `VIDEO_MODEL_UNRESOLVABLE`. That is a real
install-path dependency, so both fixtures declare the helper the way their own
installer delivers it. The full nine-helper set named by `DEPENDENCY-MANIFEST.md`
is exercised by the existing `tests/test_clean_install_discovery.py`; only the
registry-producing helper is required by these checks.

## Run

```bash
# one flavor, keeps nothing
python3 75-drama-song-ad-factory/tests/install_fixtures/harness.py \
  --flavor onb --candidate /path/to/openclaw-onboarding

# both flavors + negative controls; N999 candidate may come from the env
DSAF_N999_CANDIDATE=/path/to/999-setup python3 \
  75-drama-song-ad-factory/tests/install_fixtures/harness.py --self-check \
  --candidate-onb /path/to/openclaw-onboarding
```

Exit `0` every row ok · `1` any FAIL · `2` resolve/tooling failure (nothing ran,
never a silent pass). `--keep` preserves the sandbox and prints its path.

The test wrapper `75-drama-song-ad-factory/tests/test_install_fixtures.py` invokes
`--self-check` with the ONB candidate defaulting to the checkout it ships in.

## What the checks catch

Packaging breaks, not cosmetics:

1. **Entrypoint resolves** — the installed `scripts/core/intake_preflight/factory.py`
   runs from the installed copy and emits the pinned envelope
   (`outcome=waiting`, `reason_code=missing-essentials`, envelope schema, rc 2).
2. **Modules import from the installed copy, not the checkout** — the eight core
   modules are imported with `PYTHONPATH=<installed>/scripts/core` and
   `cwd` inside the sandbox; every `__file__` must resolve under the installed
   skill and none under the candidate repository. A shadowing checkout fails.
3. **Version markers agree with each other** — compared before and after install,
   so a copy that drops or truncates a marker fails.
4. **A symlink survives as a symlink** — N999's `shared-bridge` must still be a
   symlink with the exact relative target `../drama-studio`, and that target must
   resolve after install. A copy that dereferences it into a directory fails.
5. **The claude-nine mirror resolves** — the `~/.claude-nine/skills` entry is a
   symlink to the installed skill and still reaches `SKILL.md` through the
   nested `shared-bridge` link.
6. **Flavor-only shape** — `adapters/` and `assets/` are real directories for
   N999; `shared-bridge` is a real directory containing `studio_bridge.py` for ONB.

Four negative controls run on every `--self-check` and must go red to pass:
missing entrypoint, version drift, dereferenced symlink, and import-from-checkout.
They run against copies inside the same sandbox; no repository is modified.

## No-client guarantee — how it is demonstrated

1. **Guard by construction.** Every mutation in `harness.py` goes through
   `Sandbox.guard()`, which resolves the destination and raises unless it is the
   sandbox root or below it. Destinations are recorded and asserted after each run
   (`harness wrote only inside the sandbox`).
2. **Pinned child environment.** Subprocesses get `HOME`, `TMPDIR`, `XDG_*` and
   `CLAUDE_CONFIG_DIR` pointed inside the sandbox, `OC_*`/`OPENCLAW_*` stripped,
   `PYTHONPATH` set to the installed core, and `cwd` inside the sandbox — so the
   real factory CLI cannot resolve a real config root from its environment.
3. **Metadata sentinels.** Before and after, the harness stats
   `~/.openclaw`, `~/.claude/skills`, `~/.claude-nine/skills` and
   `~/.claude/settings.json` (mtime, inode, size, top-level entry count — never
   file contents, never names of client files). Any change fails
   `no-client: real client roots untouched`.
4. **No client input.** The harness takes one argument — a repository path. It
   reads no client identifier, credential, or client configuration.

Residual, stated honestly: the sentinels are metadata-level and sampled
before/after, not an OS write jail; a concurrent process that writes one of those
roots during a run turns the row red indistinguishably. There is no
`sandbox-exec`/namespace confinement, so a future candidate's own code that writes
an absolute path outside the sandbox would be *observed by the sentinels*, not
*blocked*.

## Sandbox location

- Single flavor: `$TMPDIR/s75t33-install-*` (printed), removed unless `--keep`.
- Self-check: `$TMPDIR/s75t33-selfcheck-*` (printed), removed unless `--keep`.

## Still owed — the execution half

The harness is candidate-agnostic; these facets cannot be tested until each
flavor has a finished package candidate:

- The built/downloaded package artifacts themselves: real GitHub tarball with the
  tag/ref `install.sh` fetches, and whatever `999-setup` ships as its installable
  distribution. This run used repository trees, not release artifacts.
- Running the real installers end to end: `install.sh` download → extract into
  `$OC_CONFIG/onboarding` → copy loop; `AGENT_INSTALL.md` agent-driven clone into
  `Documents`, backup-before-copy, `helper-deps.py` KIE helper install,
  `sync-nine-skills.sh --install`, hook installation.
- `discover_skills_dir` override branches (`OC_SKILLS_DIR`, `OPENCLAW_ROOT`,
  `OC_CONFIG`) and the Windows single-root case.
- `sync-nine-skills.sh` stale-version warning, dead-link pruning, and
  never-overwrite-real-directory behavior.
- Post-copy `verify.sh`, `PREREQS.json` checks, file modes/exec bits, and the
  skill's own QC score on the installed copy.
- Package-level integrity (checksums/signatures) if the release process adds them.
