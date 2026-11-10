#!/usr/bin/env python3
"""G-18 (fix plan "already correct — do not regress"): Skill 71's freeze gate refuses BEFORE
any spend.

stage_executor.drive_paid_job freezes the FINAL prompt and asserts the payload before the paid
call; an out-of-band prompt raises ExecutorError and the transport is never invoked. No unit
verified it, so a later edit could move the check after the spend.

PASSES on origin/main too. This test makes the property CHECKED from now on.
"""
import importlib.machinery
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SE = ROOT / "71-blackceo-signature-page" / "scripts" / "stage_executor.py"
MODEL = "gpt-image-2-6/sunburst-text-to-image"


def load():
    loader = importlib.machinery.SourceFileLoader("se_g18", str(SE))
    spec = importlib.util.spec_from_loader("se_g18", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SpyTransport:
    """Counts every call. Any call means money was (or could have been) spent."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*a, **k):
            self.calls.append((name, a, k))
            raise AssertionError("transport called: %s" % name)
        return _call


def main() -> int:
    fails = []
    se = load()
    if not hasattr(se, "drive_paid_job"):
        print("FAIL G-18: drive_paid_job is missing")
        return 1

    with tempfile.TemporaryDirectory(prefix="bld002-g18-") as d:
        rd = Path(d)
        transport = SpyTransport()
        job = {"identity": {"attempt": 1, "key": "k" * 16},
               "prompt": "way too short", "stage": "final-mockups", "index": 1,
               "section": {"section_id": "1"}, "out": rd / "out.png",
               "final": rd / "final.png", "run_dir": rd, "width": 1024, "height": 1024,
               "slot": "desktop/part-01.png", "references": [], "typed_references": []}
        request = {"model": MODEL}
        raised = None
        try:
            se.drive_paid_job(rd, job, request, transport, cap=5, label="g18")
        except AssertionError as exc:  # the spy was reached: the gate did not stop the spend
            fails.append("G-18: the transport ran before the prompt gate refused (%s)" % exc)
        except Exception as exc:  # noqa: BLE001  (ExecutorError expected)
            raised = exc
        if raised is not None:
            text = str(raised)
            if "prompt policy refused the payload" not in text and "frozen prompt" not in text:
                fails.append("G-18: refused for an unexpected reason: %s" % text[:300])
        if transport.calls:
            fails.append("G-18: the transport was called %d time(s) before the gate refused"
                         % len(transport.calls))

    src = SE.read_text(encoding="utf-8")
    if "prompt policy refused the payload before any paid call" not in src:
        fails.append("G-18: the pre-spend refusal is no longer in drive_paid_job")

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-18: an out-of-band prompt is refused before any paid call; the transport "
          "is never reached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
