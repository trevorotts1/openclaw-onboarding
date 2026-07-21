# Changelog - Agent Browser (Vercel)

All notable changes to this skill wrapper are documented here.

---

## [v6.6.3] - July 21, 2026 (T0-25 / T0-26: install the pin, and prove the fill actually filled)

### Fixed
- **The documented install now reads the version pin and installs that exact version (T0-25).** `INSTALL.md` Step 2 ran a bare `npm install -g agent-browser`, with no reference to `agent-browser-cli.pin` and no step comparing the installed version to it — the pin was read only by `qc-agent-browser.sh` and the pin-bump script, never by the install procedure. On any day the registry default is not the pinned release, a fresh install silently placed an UNPROVEN release on the box while the documented procedure reported the installation good — and `qc-agent-browser.sh` then hard-FAILED that box for a version mismatch the install itself had introduced. Step 2 now reads the pin and installs `agent-browser@$AB_PIN`, refusing to fall back to an unpinned install if the pin file cannot be read, and a new Step 3b compares the installed version to the pin and says explicitly not to re-pin to whatever happens to be installed. This adds no new gate: the installed-vs-pin hard assertion already existed in `qc-agent-browser.sh`; landing fresh installs ON the pin strictly reduces the failures it reports.

### Changed
- **The conformance battery's fill leg is now READ-BACK verified, and the bundled stub can break silently (T0-26).** Leg 4 checked only the invocation's exit status and never read the input value back, while the bundled clean stub echoed `FILLED` and exited 0 without mutating anything — and `backstop-conformance.test.sh` expected that stub to PASS every leg. A tool that accepts the fill and silently does nothing was therefore indistinguishable from a working one, in the very battery that exists to prove the capability Skill 44's Tier-4 fallback and Skill 6's `browser_manager.sh` depend on. Leg 4 now writes a per-run nonce value and reads it back with `get value`, failing when the field does not hold what was written. The stub performs a real mutation and gains a `fill_noop` break mode — accepts the argv, reports success, mutates nothing — which the suite now asserts MUST fail. Measured: against the pre-fix library the `fill_noop` stub passed the whole battery (rc=0); against the fixed library it fails naming the read-back. Verified no false failure on a healthy box: the full battery against the real pinned CLI (agent-browser 0.27.0) passes all five legs, rc=0.

- **The P3-06 stub CLI performs a real fill too (`scripts/tests/lib-stub-agent-browser.sh`).** That stub had no `fill` verb at all (it fell through to a bare `exit 0`) and its snapshot returned only a heading, so the battery's ref picker selected a non-fillable element. Once leg 4 read the value back, `qc-agent-browser.sh`'s own P3-06 regression run failed on a stub that was never meant to be simulating a broken CLI. The stub's snapshot now includes a textbox, and it implements `fill` (real, keyed mutation) and `get`. The deliberate no-op remains exercised by `build_conformance_stub`'s `fill_noop` break mode, so the leg still bites.

## [v6.6.2] - July 16, 2026 (merge-train fix: GK-27 tripwire wrongly hard-failed staged/installed runs)

### Fixed
- **GK-27 lattice-citation tripwire no longer hard-fails outside a full repo checkout.** The check resolves its repo root as `SKILL_DIR`'s parent, which is only the real repo root (with a `docs/` sibling) when `qc-agent-browser.sh` runs from a plain checkout. Run against a STAGED or INSTALLED copy of just this skill directory — including the P3-06 regression fixtures' `cp -R` staging, and a real `~/.openclaw/skills/03-agent-browser/` install — `docs/tools/check_lattice_citation.py` itself is absent, so the gate hard-FAILed every such run permanently, not merely reporting drift. Surfaced when a preceding, unrelated `QC static invariants` step (the Skill-23 how-to-use-department guide) that had been failing on 7 consecutive main commits was fixed, unmasking this second failure in the same job (the earlier failure had short-circuited the job before the Skill 03 P3-06 regression steps ever ran). Now WARN-only SKIPS when the checker script isn't found (staged/installed context), and still hard-asserts exactly as before when it is (a plain repo checkout) — same "absent skips cleanly" convention as the neighboring GK-28/U90 on-box drift gate. `qc-agent-browser-reaper-assert.test.sh`'s "well-behaved close" fixture (and the other two P3-06 regression suites) now PASS again.

## [v6.6.1] - July 16, 2026 (GK-27/U89)

### Added
- **Relationship lattice pointer + citation tripwire.** SKILL.md gained a one-line pointer to the new `docs/CONTENT-CONVERSATION-LATTICE.md` (the canonical Skill 6/44/35/38/3 content↔conversation relationship map). `qc-agent-browser.sh` now asserts that pointer is present AND that this skill's own owned edge citation — its backstop-consumer acknowledgment in `scripts/lib-backstop-conformance.sh` ("Skill 44's Tier-4 fallback and Skill 6's browser_manager.sh assume...") — still matches real, unchanged ground truth (`docs/tools/check_lattice_citation.py`, drift tripwire; fail-first proof in `docs/tools/test_check_lattice_citation.py`). No behavior change to agent-browser itself.

### Fixed
- **Regenerated `agent-browser.skill`** via `scripts/pack-agent-browser-skill.sh` to pick up the SKILL.md pointer line above (the P3-06 archive drift gate correctly caught the stale packaged copy).

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
