#!/usr/bin/env python3
"""decision-engine-mode.py — the persisted configured-mode store's referee.

A62 clause 4 (spec 3.6, line 373): "Preserve explicit client `off`, `legacy`,
and `shadow` settings through updates; a release default cannot overwrite
them." UND-062 settled that clause UNSATISFIED-BY-CONSTRUCTION: there was no
store of a mode value anywhere on a box, so install/update had nothing to
preserve and `modes.preserve_explicit_mode()` had zero production callers.
This script is the missing caller AND the missing store contract.

The store is ONE file, one word, first line — the same shape as the two
switches already sitting next to it (`bootstrap-pointer.conf`,
`bootstrap-compact.conf`):

    $OC_CONFIG/decision-engine-mode.conf      one of: auto shadow legacy off

Resolution order (first match wins):

  1. $OPENCLAW_DECISION_ENGINE_MODE     (env, highest — operator/automation)
  2. $OC_CONFIG/decision-engine-mode.conf
  3. none stored -> the release default (`auto`) already built into every
     consumer (`fallback.select` / `ladder.run` read
     `cfg.get("configuredMode", "auto")`)

WHY THIS SCRIPT WRITES NOTHING, EVER, ON THE PRESERVE PATH
  The installer/updater must be able to prove the clause holds. The cheapest
  way to prove "the release default cannot overwrite an explicit setting" is
  to have no writer at all: nothing an install or an update does touches this
  file, so an explicit value is preserved BY CONSTRUCTION rather than by a
  merge that could regress. What that construction lacks — and what v21.5.0's
  config/ delivery proved a coincidence-of-a-glob lacks — is a RECEIPT. So the
  installers CALL this script and it prints what the box will actually run,
  loudly, using the same authority the decision core uses
  (`decision_engine.modes.preserve_explicit_mode`) rather than a second
  implementation of the merge that could disagree with it.

  A corrupt/unknown value is NEVER reset and NEVER rewritten — silently
  reverting a client's `off` (the emergency JEV kill switch) to `auto` is the
  single worst outcome in this spec. It fails LOUD instead, and the installer
  continues (a mode-store typo must not block a whole fleet roll) with the
  consequence spelled out line by line.

EXIT
  0 = receipt printed (PRESERVED / DEFAULT / env override)
  1 = stored value is not a valid mode — CORRUPT, nothing written, caller warns
  2 = usage or the canonical modes module could not be located (fail-closed:
      an unproven receipt must never be reported as a pass)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

STORE_NAME = "decision-engine-mode.conf"
ENV_NAME = "OPENCLAW_DECISION_ENGINE_MODE"
RELEASE_DEFAULT = "auto"

USAGE = ("usage: decision-engine-mode.py --shared-utils DIR "
         "[--oc-config DIR] [--print|--assert-preserved]")


def _load_modes(shared_utils: Path):
    """Import the ONE mode authority. Fail-closed if it is not there."""
    sys.path.insert(0, str(shared_utils))
    try:
        from decision_engine import modes as _modes  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"decision-engine-mode: cannot load the canonical modes module "
              f"from {shared_utils}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    return _modes


def resolve(oc_config: Path, modes):
    """(mode, source, raw) — source is 'env' | 'file' | 'default'."""
    env_raw = os.environ.get(ENV_NAME)
    if env_raw is not None and env_raw.strip():
        return env_raw.strip(), "env", env_raw
    store = oc_config / STORE_NAME
    if store.is_file():
        try:
            raw = store.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        first = (raw.splitlines() or [""])[0].strip()
        return first, "file", raw
    return RELEASE_DEFAULT, "default", ""


def main(argv) -> int:
    shared_utils = None
    oc_config = None
    do_print = False
    do_assert = False
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--shared-utils" and rest:
            shared_utils = rest.pop(0)
        elif arg == "--oc-config" and rest:
            oc_config = rest.pop(0)
        elif arg == "--print":
            do_print = True
        elif arg == "--assert-preserved":
            do_assert = True
        else:
            print(USAGE, file=sys.stderr)
            return 2
    if shared_utils is None or not (do_print or do_assert):
        print(USAGE, file=sys.stderr)
        return 2

    modes = _load_modes(Path(shared_utils))
    if modes is None:
        return 2

    root = Path(oc_config or os.environ.get("OC_CONFIG")
                or (Path.home() / ".openclaw"))
    store = root / STORE_NAME
    mode, source, _raw = resolve(root, modes)

    if mode not in modes.MODES:
        print(f"  ✗ decision-engine mode store is CORRUPT: {store} holds "
              f"{mode!r}, not one of {list(modes.MODES)}.", file=sys.stderr)
        print("    CONSEQUENCE: the decision core will refuse this value "
              "(modes._check_mode raises) rather than pick a mode for you.",
              file=sys.stderr)
        print(f"    ACTION: write one of {'|'.join(modes.MODES)} as the first "
              f"line of {store}, or delete the file to accept the release "
              f"default ({RELEASE_DEFAULT}). Nothing was written by this run.",
              file=sys.stderr)
        return 1

    if do_print:
        print(mode)
        return 0

    if source == "env":
        print(f"  OK decision-engine mode {mode!r} from ${ENV_NAME} "
              f"(release default cannot move it)")
        return 0

    if source == "default":
        print(f"  -- no explicit decision-engine mode stored ({store} absent); "
              f"the release default {RELEASE_DEFAULT!r} applies")
        print("     To pin off/legacy/shadow so no release default can move it, "
              f"write one word to {store}")
        return 0

    # THE CONTRACT: the stored explicit choice survives. Proven by asking the
    # SAME authority the decision core uses, not by re-implementing the merge.
    kept = modes.preserve_explicit_mode(RELEASE_DEFAULT, mode,
                                        stored_explicit=True)
    if kept != mode:
        print(f"  ✗ decision-engine mode {mode!r} would be overwritten by "
              f"the release default ({kept!r}) — preserve_explicit_mode "
              f"disagrees with the store.", file=sys.stderr)
        return 1
    print(f"  OK explicit decision-engine mode {mode!r} preserved "
          f"(stored in {store}; release default {RELEASE_DEFAULT!r} cannot "
          f"overwrite it)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
