
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
