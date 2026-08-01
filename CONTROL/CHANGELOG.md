
## v21.4.8 — 2026-07-29T13:11:52Z
- U011: Process engine
- U015: Announce, heal, escalate
- U023: Fail-closed render guards
- U045: Mute landmine
- U055: Correct stale model
- U056: Ban search flag
- U057: Ban env dump

## v21.4.9 — 2026-07-29T13:37:54Z
- U013: Fail-closed gates

## v21.4.10 — 2026-07-29T14:49:33Z
- U006: Stop guessing scripts
- U027: Slide content mandatory
- U049: Retire no-vision QC
- U070: Slide craft standards

## v21.4.11 — 2026-07-29T14:56:00Z
- U019: The teleprompter becomes the sixth client-package file (D02, ratified 2026-07-26)
  - `presenter-teleprompter.html` joins the AF-DH1 whitelist, the manifest's
    `client_package_files` (5 -> 6 keys), and SOP-PITCH-05. The department's own
    instructions promised the client a teleprompter; the delivery package was a fixed
    list of five that excluded it. That contradiction is closed.
  - Shipped as STAGE 1 of the warn-mode rollout, not stage 3: `teleprompter_html` sits in
    `CLIENT_PACKAGE_WARN_ONLY`, so every already-delivered five-file package still passes
    with a printed warning instead of being rejected on sight. Hard enforcement is a
    separate, later unit.
  - `manifest_version` 29 -> 30, with `MIN_MANIFEST_VERSION` moved to the same value.
    `MANIFEST-SOURCE.txt` is created NEW beside the canonical manifest, stamping its
    sha256. **From this commit onward a stale stamp is EXIT_MANIFEST_MISMATCH (exit 7) on
    every engine invocation — U049 and U051 must each re-cut `content_sha256=` in their own
    commit.** The two box manifest copies are handed to U004 and must land before or with
    the fleet roll, never after this code.
- Housekeeping in the same batch (disclosed, not silent):
  - Version markers: this ripple used `scripts/bump-version.sh`, the repo's own tool,
    rather than hand-editing. That repaired pre-existing drift — 8 of the 10 drift-checked
    markers were stranded at v21.4.2/v21.4.3 while `/version` and `install.sh` had been
    hand-rolled to v21.4.10 by earlier ripples. All 10 now agree at v21.4.11, plus 5
    further script-owned markers the tool also rolls. ONE marker is deliberately NOT
    rolled and stays at v21.4.2: `update-skills.sh`. The repo's own pre-commit gate
    (.githooks/pre-commit section 4) blocks any commit that stages a `.sh` file which
    writes `secrets/.env` without a `chmod 600` call, and `update-skills.sh` has 4 such
    writes and no chmod — a PRE-EXISTING gap on main, unrelated to U019. Earlier ripples
    never tripped it because they hand-edited only `/version` and `install.sh` and never
    staged this file. Fixing it is a token-exposure change to a fleet-critical installer
    and belongs to its own unit, not to this ripple; the hook was never bypassed.
  - `QUALITY-CONTROL/tickets/U012.md`: an operator machine path that pre-existed on main
    was redacted (path string only; U012's verdict, scores and evidence are byte-identical).
    It was tripping `scripts/qc-assert-no-client-names.sh`, which is repo-wide and not
    diff-scoped, and therefore blocked EVERY commit to this repository.

## v21.4.16 — 2026-07-29T18:16:10Z
- U008: Merge the 22 duplicated role folders down to one each — PASS 8.80 (round 9), operator
  waived post-fix re-judge 2026-07-29 for the round-10 one-file fix (hardcoded operator path
  replaced with `OPENCLAW_WORKSPACE`, matching `51-signature-presentation/verify.sh`).
- U073: Make the repository's commit hook actually run — PASS gate 8.6, operator waived
  post-fix re-judge 2026-07-29 for the round-2 one-line chmod-600 false-positive wording fix
  (`secrets/.env` mention reworded; guard NOT weakened). Stale-based branch, three merge
  conflicts resolved: kept HEAD's `presentation_job.py` 5-line shim, kept HEAD's current
  `manifest_version` (31 by merge time — main advanced past the `30` noted when the fix was
  made), combined both sides' `.githooks/pre-commit` header gate-listing comments (no
  functional change).
- U028: Generalise checkpoint and resume; checkpoint before the paid call — PASS (round 9
  repair), operator waived post-fix re-judge 2026-07-29. Round 8's fail-closed findings (D.2,
  D.11.8 — U014's 24 tests for `presentation_job/artifacts.py` were silently deleted because
  the card's `Touches:` block wrongly marked `tests/test_checkpoint.py` as `NEW`) are resolved:
  U014's 24 tests and U028's own 25 are merged into one 49-test file, zero name collisions,
  mutation-proven both ways. `SPEC/units/U028.md`'s `Touches:` entry corrected `NEW` → `MODIFY`.
- Gate suite (`pytest tests/ -q` from
  `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/`): fresh baseline at
  `origin/main` tip `9dbe2d5a` measured **6 failed / 224 passed / 13 skipped**; after landing
  all three units, **6 failed / 249 passed / 13 skipped** — identical 6 pre-existing failing
  test names, +25 passed (U028's own net-new test count), zero regressions.
- Version bump via `scripts/bump-version.sh v21.4.16` — all 9 script-rolled markers agree;
  `update-skills.sh`'s own `ONBOARDING_VERSION` deliberately left at `v21.4.2` (same precedent
  as every prior ripple): the repo's pre-commit hook blocks any staged `.sh` file that writes
  `secrets/.env` without a `chmod 600` call in the same file, and `update-skills.sh` has such
  writes with no chmod — a pre-existing gap, not introduced here, hook never bypassed.
