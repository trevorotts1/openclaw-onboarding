# Changelog - Agent Browser (Vercel)

All notable changes to this skill wrapper are documented here.

---

## [v6.6.0] - July 15, 2026 (GK-28/U90)

### Added
- **On-box source-of-truth drift gate.** SKILL.md defers to
  `~/clawd/skills/agent-browser/SKILL.md` as "the source of truth" WHEN
  PRESENT, but nothing ever checked whether that box-local copy had silently
  changed (NOT-FOUND, GK-28 audit). Since that file lives outside this repo
  there is nothing to byte-diff it against on-disk — instead
  `scripts/lib-onbox-drift.sh` + `scripts/pin-onbox-source-of-truth.sh`
  capture a PINNED sha256 baseline (`references/onbox-agent-browser-skillmd.pin`,
  ships as `UNCAPTURED` until an operator explicitly pins one) and
  `qc-agent-browser.sh` re-hashes the live file on every run. FAIL-CLOSED: an
  on-box copy that exists with no baseline pinned yet is a hard QC FAIL, not
  a silent pass. Deliberately drifting a pinned on-box copy also FAILS QC,
  naming it — the wrapper and the machine copy can no longer silently
  diverge. Proven by `scripts/tests/onbox-drift-gate.test.sh`.
- **CLI version pin.** The `agent-browser` NPM PACKAGE version was never
  pinned anywhere in this skill (the archive covers the WRAPPER docs only,
  P3-06) — a fresh `npm install -g agent-browser` could silently land any
  current registry release. `agent-browser-cli.pin` + `CLI-VERSION-PIN.md`
  now record a known-good, PROVEN version (**0.27.0** — proven live on the
  operator's own box 2026-07-15; agrees with
  `06-ghl-install-pages/tools/ghl_ab_executor.py`'s independent
  `PINNED_AGENT_BROWSER = "0.27.0"`). `qc-agent-browser.sh` FAILS if the
  installed CLI version does not match the pin, naming both. The ONLY
  sanctioned way to change the pin is `scripts/bump-agent-browser-cli-pin.sh`
  (updates the `.pin` file AND `CLI-VERSION-PIN.md`'s dated bump-log row
  atomically, mirroring `../scripts/bump-version.sh`'s single-source-of-truth
  pattern). Proven by `scripts/tests/cli-version-pin.test.sh`.
- **Backstop conformance battery.** Skill 44's Tier-4 fallback and Skill 6's
  `browser_manager.sh` assume agent-browser gives them ref-based click/fill,
  snapshot stability, and a guaranteed session close — nothing tested those
  assumptions from the CONSUMER side (NOT-FOUND, GK-28 audit).
  `scripts/lib-backstop-conformance.sh`'s `run_conformance_battery` drives
  the exact five operations those consumers script — open, ref-based
  snapshot, snapshot-ref STABILITY across repeated calls, fill-by-ref
  (positional `fill @eN value`, the argv shape `ghl_ab_executor.py`
  independently verified live against agent-browser 0.27.0), and guaranteed
  close (leaked-process read-back via the same scoped-Chromium scan the
  Step-4 smoke test uses) — against a bundled offline fixture
  (`scripts/tests/fixtures/conformance-fixture.html`, no network dependency).
  Wired into `qc-agent-browser.sh` as a new section (runs the real CLI when
  on PATH, same `--headed false` + ambient-refuse discipline as Step-4).
  `scripts/tests/backstop-conformance.test.sh` proves the battery is
  fail-closed: breaking any ONE of the five capabilities (a fixture stub)
  fails that specific leg, one at a time.

### Changed
- Extracted the scoped-Chromium-process scan (`_scoped_chrome_pids` /
  `_new_pids`) out of `qc-agent-browser.sh`'s Step-4 section into
  `scripts/lib-scoped-chrome-scan.sh` so the Step-4 smoke test and the new
  conformance battery's "guaranteed close" leg share ONE implementation
  instead of a second ad-hoc copy — the exact kind of drift-prone
  duplication the P3-06 CHANGELOG entry above already warns against.
- `scripts/tests/lib-stub-agent-browser.sh`'s shared stub CLI now strips an
  optional leading `--headed <bool>` global flag before verb dispatch,
  regardless of which verb follows (previously only recognized ahead of
  `open`, silently no-op'ing `--headed false snapshot`/`close`/`fill` — both
  real calling conventions exist in this repo: INSTALL.md's Step-4 example
  prefixes only `open`, while `browser_manager.sh`'s `AB()` prefixes EVERY
  verb). Also redirects the stub's backgrounded stand-in process's FDs to
  `/dev/null` (a command-substitution pipe otherwise blocks on that
  process's stdout/stderr never closing — the exact hang this unit's own
  battery wiring surfaced during build).
- `scripts/tests/qc-agent-browser-reaper-assert.test.sh`'s cleanup now also
  sweeps all scoped stub stand-ins by pattern
  (`kill_all_agent_browser_chrome_stubs`), not just the single tracked
  pidfile — needed because a qc run now performs TWO open/close cycles
  (Step-4 + the conformance battery) against one shared stub pidfile, and a
  deliberately-leaked fixture from the first cycle can otherwise be
  clobbered out of that pidfile by the second cycle's own `open`.

---

## [v6.5.9] - July 12, 2026 (P3-06)

### Fixed
- **Stale bundled archive, regenerated + made impossible to drift again.** `agent-browser.skill` was hand-packaged with no regeneration step and no drift check, so it silently shipped a STALE copy of `INSTALL.md` (missing the N24 TYP citation, the mandatory `--headed false` requirement, the guaranteed-close `trap ... EXIT` subshell, the "Lifecycle hygiene" section, and the entire "GATEWAY RESTART PROTOCOL" block) and a STALE `CORE_UPDATES.md`, right next to current loose files. Added `scripts/pack-agent-browser-skill.sh` — the ONLY sanctioned way to produce/update the archive from now on (`--check` mode, wired into CI). Regenerated the archive from the current on-disk source. Two regenerations of unchanged source, on the same box/toolchain, now produce a byte-identical archive: the initial version normalized every FILE's mtime before zipping but left the `agent-browser/` directory's own zip-entry mtime at a live build-time value, so `--check` (and the packer's own determinism) could still drift on that one directory-entry byte even with zero content changes — fixed by normalizing the directory entry's mtime too, and proven by `scripts/tests/pack-agent-browser-skill.test.sh`'s two-independent-regenerations assertion, which failed reproducibly before this fix.
- **`qc-agent-browser.sh` drift gate.** Now unzips `agent-browser.skill` and diffs `INSTALL.md`/`SKILL.md`/`CHANGELOG.md`/`CORE_UPDATES.md` inside it against the on-disk copies — ANY mismatch is a hard QC FAIL naming the differing file (`scripts/lib-archive-diff.sh`, shared by the packer's `--check` and the QC gate).
- **Step-4 smoke test is now ASSERTED, not implied.** `qc-agent-browser.sh` re-extracts the exact fenced Step-4 code block live from `INSTALL.md` (the guaranteed-close trap, `--headed false`) and prints the command + flags it actually ran as evidence. An ambient `AGENT_BROWSER_HEADED` signal that would force a visible window is refused (exit-75 class, matching Skill 06's D6 convention) before the smoke test ever runs.
- **Post-smoke-test session state upgraded from `warn_only` to `assert`.** A Chromium process this run's own smoke test spawned and left alive after `agent-browser close` ran now FAILS QC (was: no check at all). A scoped session that predates the QC run stays `warn_only` (not this skill's fault). QC.md gained explicit line items for all three.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Added wrapper skill to ensure agent-browser is installed and available as the preferred browser automation tool.
