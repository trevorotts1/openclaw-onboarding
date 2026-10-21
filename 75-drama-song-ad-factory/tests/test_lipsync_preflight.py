#!/usr/bin/env python3
"""Offline check for scripts/lipsync_preflight.py: the three states and the exits.

No network, no pip, no installs: _judge and main() are driven with stubs, and a
temp file stands in for the model. Run either way:

    python3 tests/test_lipsync_preflight.py
    python3 -m pytest tests/test_lipsync_preflight.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
import tempfile
import types

SPEC = (pathlib.Path(__file__).resolve().parent.parent
        / "scripts" / "lipsync_preflight.py")


def _load():
    spec = importlib.util.spec_from_file_location("lipsync_preflight", SPEC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ifm(good):
    return types.SimpleNamespace(
        MODEL_NAME="face_landmarker.task", MODEL_BYTES=16, MODEL_URL="https://example/x",
        INSTALL_COMMAND="install", is_good=lambda p: good and os.path.isfile(p))


def test_judge_three_states():
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nope.task")
        assert mod._judge(_ifm(True), missing, "t")[0] == "MISSING"
        bad = os.path.join(tmp, "bad.task")
        with open(bad, "wb") as f:
            f.write(b"x")
        assert mod._judge(_ifm(False), bad, "t")[0] == "PRESENT-BUT-BROKEN"
        good = os.path.join(tmp, "good.task")
        with open(good, "wb") as f:
            f.write(b"x")
        assert mod._judge(_ifm(True), good, "t")[0] == "PRESENT"


def _run(mod, states):
    mod.module_state = lambda name: states["module"]
    mod.model_state = lambda: states["model"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mod.main(["--check"])
    return rc, out.getvalue()


def test_exit_zero_when_all_present():
    mod = _load()
    rc, text = _run(mod, {"module": ("PRESENT", "1.0"), "model": ("PRESENT", "p")})
    assert rc == 0, rc
    assert "repair" not in text, text
    assert text.count("PRESENT") == 4, text


def test_exit_two_and_repair_line_when_missing():
    mod = _load()
    rc, text = _run(mod, {"module": ("MISSING", "not importable"),
                          "model": ("PRESENT-BUT-BROKEN", "bad")})
    assert rc == 2, rc
    assert "repair all:" in text, text
    assert "--repair" in text, text


if __name__ == "__main__":
    test_judge_three_states()
    test_exit_zero_when_all_present()
    test_exit_two_and_repair_line_when_missing()
    print("ok: lipsync_preflight three states, exit 0 on present, exit 2 on not")
