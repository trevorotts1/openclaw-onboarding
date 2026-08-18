"""Three-valued result type for anything that inspects state and must report a
verdict: gates, health scans, transports, sync/manifest checks.

WHY THIS EXISTS (Root Cause 2, CONTROL/ROOT-CAUSE-ARCHITECTURE.md):
every gate and transport in this codebase used to return exactly two values
(True/False, an exit code from {0, N}, a plain list that is empty on both
"checked, clean" and "could not check"). That leaves "I could not determine
this" with nowhere to live, so it silently collapses into whichever of the
two values reads as a pass. Proven instances: a sweep that reported success
when it scanned zero runs; a notify transport that swallowed a message it
could not encode; a security gate whose duplicate-file detector went dark
when both its import fallbacks failed and returned `[]` -- indistinguishable
from "checked, no duplicates". None of these needed an adversary. They are
pure epistemics: the type had no slot for "unknown".

CheckResult gives that slot a name. PASS and FAIL are for a check that
actually ran to completion. UNDETERMINED is for a check that could not run
at all (missing dependency, unreadable file, exhausted fallback chain,
ambiguous transport outcome, zero inputs scanned) -- it is a THIRD thing,
not a synonym for either.

CheckResult.__bool__ is disabled on purpose. `if result:` is exactly the
idiom that lets UNDETERMINED get silently coerced to whatever a particular
enum member's truthiness happens to be; every call site is forced to write
`result is CheckResult.PASS` (or `.ok`, see below) and therefore forced to
have an actual opinion about UNDETERMINED.

WHICH SIDE UNDETERMINED LANDS ON IS CALLER-SPECIFIC. There is no safe
default -- it must be decided at each call site, and the decision documented
there, not here:
  - security / completeness gate  -> UNDETERMINED behaves like FAIL (refuse
    to pass something you could not actually check).
  - health / status report        -> UNDETERMINED is reported AS
    UNDETERMINED, out loud, never silently folded into "healthy".
  - message / alert transport     -> UNDETERMINED behaves like "not yet
    delivered": keep retrying, never discard. Losing an alert is the
    failure this project exists to eliminate.

CONVERTED so far (see call sites for the acceptance proof of each):
  - presentation_job/gates.py       Gates._canonical_prompt_dir_problems
  - presentation_job/report.py      dispatch3 / Reporter.to_requester
  - presentation_job/watchdog.py    watchdog() scanned==0 case

NOT YET CONVERTED -- open work, deliberately left for a follow-up pass
(do not assume these are safe; each is a live UNKNOWABLE==PASS collapse
found and execution-proved by the same sweep that produced this module):
  - delivery_gate.py: inspect_pptx_artifact treats a corrupted/unreadable
    slide-XML zip entry as "no overlay text found" (reads as PASS).
  - sync_check.py / manifest_assert.py / manifest_source.py: five blind
    spots beyond the already-fixed "whole phase entry removed" case.
  - phase_verifiers.py: nine UNKNOWABLE==PASS instances across seven of
    its 40 verify() functions.
  - presentation_job/cc_board.py: patch_phase()/post_activity() derive
    success from HTTP status alone (`ok = st == 200`) with no body check.
  - presentation_job/curate.py + fix_bundle_complete.py wiring: a
    documented-safe second layer is never wired into one of the two
    production entry points (run_signature_deck.py).
"""

from __future__ import annotations

import enum
from typing import Iterable


class CheckResult(enum.Enum):
    """PASS / FAIL / UNDETERMINED. See module docstring for the doctrine."""

    PASS = "pass"
    FAIL = "fail"
    UNDETERMINED = "undetermined"

    def __bool__(self) -> bool:  # pragma: no cover - defensive, meant to raise
        raise TypeError(
            "CheckResult has no truthiness. `if result:` is exactly the "
            "two-value collapse this type exists to prevent -- it would "
            "silently decide, on your behalf, which side UNDETERMINED lands "
            "on. Compare explicitly: `result is CheckResult.PASS`, or use "
            "`.ok` only once you've actually read this call site's doctrine."
        )

    @property
    def ok(self) -> bool:
        """True only for a confirmed PASS. Both FAIL and UNDETERMINED are
        `False` here -- this is the narrow escape hatch for a caller that
        truly has only a binary decision to make AND has already decided,
        deliberately, that UNDETERMINED goes with FAIL at this call site
        (e.g. a security gate). Do not reach for this on a health report or
        a transport -- those two need UNDETERMINED to stay a distinct,
        visible state, not collapse into `not ok`."""
        return self is CheckResult.PASS

    @classmethod
    def worst_of(cls, results: Iterable["CheckResult"]) -> "CheckResult":
        """Aggregate many results into one. FAIL beats UNDETERMINED beats
        PASS. An EMPTY input is UNDETERMINED, never PASS -- zero evidence is
        not evidence of a pass. This generalizes the pattern already proven
        in state.py/sweep.py (EXIT_SWEEP_NO_RUNS: scanned 0 run dirs is
        UNDETERMINED, not a clean sweep)."""
        worst = cls.PASS
        seen_any = False
        for r in results:
            seen_any = True
            if r is cls.FAIL:
                return cls.FAIL
            if r is cls.UNDETERMINED:
                worst = cls.UNDETERMINED
        if not seen_any:
            return cls.UNDETERMINED
        return worst

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"CheckResult.{self.name}"
