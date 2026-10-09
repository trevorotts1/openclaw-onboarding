#!/usr/bin/env python3
"""U9-t2: the PENDING-vs-burn contract of U11's one call site.

``final_assembler.assembler.excerpt_overlay_stage(plan)`` is the ONE place an
excerpt overlay is handed to a render step. While ``final_assembler/
captions_burn.py`` is absent it must report PENDING and burn nothing; the
moment U9's module is on the tree the same call must go through U9's
``overlay_excerpt`` and report burned. This suite pins both halves of that
switch, plus the states where NEITHER may happen (no overlay in the plan,
no lines in the overlay).

Checks (states of the same function):
  (a) no ``excerpt_overlay`` key            -> no row, not pending;
  (b) overlay with zero lines               -> no row, not pending;
  (c) module ABSENT                         -> pending True, reason
      BOOK_OVERLAY_UNAVAILABLE, burned False, artifact named;
  (d) module PRESENT                        -> pending False, burned True,
      and U9's overlay_excerpt is what did it (one seam, never two);
  (e) both branches keep speaking through the SAME hook name.

TOUCH NOTHING ON DISK: state (c) is produced by patching ``os.path.isfile``
for the burn path only, for the length of the probe -- this worktree is
shared with the code lane, so the module file is never renamed, moved or
written. The patch is restored in a ``finally``.

Loud skip (never a silent pass) when U11's call site is not on the tree yet
(it ships on unit/FU-U11): such a run prints what it could NOT check.

stdlib only, zero network, zero paid calls, no ffmpeg.

Run: python3 core/final_assembler/test_pending_vs_burn_u9t.py
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

FAILS = []
RAN = 0

HOOK = "captions_burn.overlay_excerpt"
BURN = os.path.join(HERE, "captions_burn.py")
EXCERPT = ["She kept the kitchn spotless", "for thirty years."]


def check(name, cond, detail=""):
    global RAN
    RAN += 1
    detail = detail if isinstance(detail, str) else repr(detail)
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        " (%s)" % detail if not cond else ""))
    if not cond:
        FAILS.append(name)
        # Under pytest a printed FAIL would be a silent green: fail there too.
        if "pytest" in sys.modules:
            import pytest
            pytest.fail("%s (%s)" % (name, detail), pytrace=False)


def _skip(msg):
    """A real skip: pytest must never count an unrun check as passed."""
    print("skip: %s" % msg)
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(msg)


def _need_stage():
    """The U11 call site, or a skip that pytest can see."""
    stage = _stage()
    if stage is None:
        _skip("U11's assembler.excerpt_overlay_stage is not on this tree "
              "(unit/FU-U11 / merged tree carries it)")
    return stage


def _need_module():
    if not os.path.isfile(BURN):
        _skip("captions_burn.py is not on this tree yet (pre-U9 state)")
    return os.path.isfile(BURN)


def _stage():
    """Import the stage fresh, so its file-existence probe re-runs."""
    for name in ("final_assembler.assembler", "assembler"):
        sys.modules.pop(name, None)
    try:
        mod = importlib.import_module("final_assembler.assembler")
    except ImportError as exc:
        print("skip (assembler unavailable): %s" % exc)
        return None
    if not hasattr(mod, "excerpt_overlay_stage"):
        print("skip (U11 not on this tree): assembler.excerpt_overlay_stage "
              "-- asserted on unit/FU-U11 and on the merged tree")
        return None
    return mod


class _ModuleAbsent:
    """Make the stage's own isfile probe say "no captions_burn.py"."""

    def __enter__(self):
        self._real = os.path.isfile

        def fake(path, *a, **kw):
            if os.path.abspath(str(path)) == BURN:
                return False
            return self._real(path, *a, **kw)

        os.path.isfile = fake
        return self

    def __exit__(self, *exc):
        os.path.isfile = self._real
        return False


def _plan(lines=EXCERPT, provenance="provided"):
    return {"excerpt_overlay": {"lines": list(lines),
                                "provenance": provenance}}


def test_no_overlay_is_not_pending():
    stage = _need_stage()
    if stage is None:
        return
    for label, plan in (("an empty plan", {}),
                        ("an overlay with no lines",
                         {"excerpt_overlay": {"lines": []}})):
        out = stage.excerpt_overlay_stage(plan)
        check("%s -> no row, not pending" % label,
              out == {"rows": [], "pending": False, "reason_code": None},
              out)
    out = stage.excerpt_overlay_stage({"excerpt_overlay": {"lines": []}})
    check("an overlay with no lines is never reported pending",
          out["pending"] is False and out.get("reason_code") is None, out)


def test_absent_module_reports_pending():
    """State C: U9's file absent -> PENDING, and NOTHING is burned."""
    stage = _need_stage()
    if stage is None:
        return
    if not os.path.isfile(BURN):
        # The pre-U9 state is the LIVE state here: assert it directly.
        out = stage.excerpt_overlay_stage(_plan())
        check("module absent (live) -> pending is True",
              out["pending"] is True, out)
        check("module absent (live) -> reason BOOK_OVERLAY_UNAVAILABLE",
              out.get("reason_code") == "BOOK_OVERLAY_UNAVAILABLE",
              out.get("reason_code"))
        row = out["rows"][0]
        check("pending row names U9's hook and burned nothing",
              row.get("hook") == HOOK and row.get("burned") is False, row)
        return
    with _ModuleAbsent():
        # Probe inside the patch: the stage sees a tree with no U9 module.
        if os.path.isfile(BURN):
            check("the isfile patch hides the module from the probe",
                  False, BURN)
            return
        out = stage.excerpt_overlay_stage(_plan())
    check("module absent -> pending is True", out["pending"] is True, out)
    check("module absent -> reason BOOK_OVERLAY_UNAVAILABLE",
          out.get("reason_code") == "BOOK_OVERLAY_UNAVAILABLE",
          out.get("reason_code"))
    row = out["rows"][0]
    check("the pending row names U9's hook", row.get("hook") == HOOK,
          row.get("hook"))
    check("the pending row burned nothing", row.get("burned") is False,
          row.get("burned"))
    check("the pending row names the artifact U9 must land",
          str(row.get("artifact", "")).endswith("captions_burn.py")
          and row.get("artifact_present") is False, row)
    check("a pending receipt is never a completed burn",
          out["pending"] is True and row.get("burned") is False,
          (out["pending"], row.get("burned")))
    # The patch is gone: the live state is the burned one again.
    check("the probe is restored after the pending branch",
          os.path.isfile(BURN) is True, BURN)


def test_present_module_burns_through_u9():
    """State D: U9's module present -> the ONE seam calls U9's entry point."""
    if not _need_module():
        return
    stage = _need_stage()
    if stage is None:
        return
    out = stage.excerpt_overlay_stage(_plan())
    check("module present -> pending is False", out["pending"] is False, out)
    check("module present -> no BOOK_OVERLAY_UNAVAILABLE",
          out.get("reason_code") in (None, ""),
          out.get("reason_code"))
    row = out["rows"][0]
    check("the burned row carries U9's hook", row.get("hook") == HOOK,
          row.get("hook"))
    check("the burned row reports burned True", row.get("burned") is True,
          row.get("burned"))
    check("the burned row counts the lines it took",
          row.get("lines") == len(EXCERPT), row.get("lines"))


def test_u9_entry_point_is_the_one_that_ran():
    """The burn must come from overlay_excerpt, not a second writer."""
    if not _need_module():
        return
    stage = _need_stage()
    if stage is None:
        return
    import final_assembler.captions_burn as CB
    seen = []
    real = CB.overlay_excerpt

    def spy(lines, provenance=None, **kw):
        seen.append((list(lines), provenance))
        return real(lines, provenance=provenance, **kw)

    CB.overlay_excerpt = spy
    try:
        stage.excerpt_overlay_stage(_plan())
        check("the stage reached U9's overlay_excerpt",
              seen == [(EXCERPT, "provided")], seen)
    finally:
        CB.overlay_excerpt = real


def test_hook_name_is_the_same_on_both_sides():
    stage = _need_stage()
    if stage is None:
        return
    live = stage.excerpt_overlay_stage(_plan())
    if not live["rows"]:
        check("the stage returned a row for an excerpt overlay", False, live)
        return
    check("live state reports the hook string",
          live["rows"][0].get("hook") == HOOK, live["rows"][0])
    if not os.path.isfile(BURN):
        # Pre-U9 tree: the LIVE side is the pending side -- assert that.
        check("pre-U9: the live side is pending, never a silent burn",
              live["pending"] is True
              and live["rows"][0].get("burned") is False,
              (live["pending"], live["rows"][0]))
        return
    with _ModuleAbsent():
        out2 = stage.excerpt_overlay_stage(_plan())
    check("pending state reports the same hook string",
          out2["rows"][0].get("hook") == HOOK, out2["rows"][0])
    check("both states agree on the hook, and differ only in burned",
          live["rows"][0].get("hook") == out2["rows"][0].get("hook")
          and live["rows"][0].get("burned") is True
          and out2["rows"][0].get("burned") is False,
          (live["rows"][0], out2["rows"][0]))


def main():
    for fn in (test_no_overlay_is_not_pending,
               test_absent_module_reports_pending,
               test_present_module_burns_through_u9,
               test_u9_entry_point_is_the_one_that_ran,
               test_hook_name_is_the_same_on_both_sides):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d check(s) ran, %d failed" % (RAN, len(FAILS)))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    if RAN == 0:
        print("SKIPPED (U11 stage absent): the pending-vs-burn contract was "
              "NOT verified on this tree -- asserted on unit/FU-U11 and on "
              "the merged tree. This file is NOT evidence for it here.")
        return 0
    print("all U9-t2 pending-vs-burn checks passed (%d)" % RAN)
    return 0


if __name__ == "__main__":
    sys.exit(main())