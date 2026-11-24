#!/usr/bin/env python3
"""Pytest checks for the mode-file loader and the guide-drift guard.

Rows N-35 (banned words per look, every block required at load) and N-36
(guide line equals the mode file's client_wording). Stdlib only.

Run: pytest scripts/core/style_defaults/test_mode_files_n35_n36.py
$0 spend, no network.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

from style_defaults import client_wording as CW              # noqa: E402
from style_defaults import mode_files as MF                  # noqa: E402
from style_defaults.defaults import StyleDefaultsError        # noqa: E402


def _raises(code, fn, *args):
    try:
        fn(*args)
    except StyleDefaultsError as exc:
        assert exc.code == code, exc.code
        return
    raise AssertionError("did not refuse with %s" % code)


def test_all_six_mode_files_load():
    modes = MF.load_all_modes()
    assert len(modes) == 6, sorted(modes)
    assert "stylized-3d" in modes


def test_every_mode_carries_banned_words_and_client_wording():
    for mid, mode in sorted(MF.load_all_modes().items()):
        assert isinstance(mode.get("banned_words"), list) and mode["banned_words"], mid
        assert mode.get("client_wording"), mid


def test_banned_word_outside_the_block_refuses_and_the_block_is_exempt():
    l3d = MF.load_mode("lifelike-3d")
    h3 = l3d["h3_block"].replace("{palette}", l3d.get("palette_default", ""))
    _raises("STYLE_WORD_BANNED", MF.check_banned_words,
            "a soft frame, photoreal skin", l3d["banned_words"], h3)
    assert MF.check_banned_words(h3, l3d["banned_words"], h3) == h3


def test_mode_missing_a_block_fails_at_load():
    with tempfile.TemporaryDirectory() as tmp:
        src = MF.modes_dir()
        shutil.copytree(src, tmp, dirs_exist_ok=True)
        broken = json.loads((src / "realism.json").read_text(encoding="utf-8"))
        broken.pop("keyframe_clause")
        with open(os.path.join(tmp, "realism.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(broken))
        _raises("MODE_BLOCK_MISSING", MF.load_mode, "realism", tmp)


def test_client_wording_map_and_guide_drift_guard():
    assert CW.map_client_wording("something Pixar-like") == "stylized-3d"
    assert CW.map_client_wording("I want real people") == "realism"
    assert CW.map_client_wording("Lifelike 3D") == "lifelike-3d"
    assert CW.map_client_wording("something warm and happy") is None
    line = CW.client_wording_for("lifelike-3d")
    assert CW.check_guide_wording("lifelike-3d", line) == line
    _raises("CLIENT_WORDING_DRIFT", CW.check_guide_wording,
            "lifelike-3d", "realistic and cinematic")


def _guide(tmp, body):
    path = os.path.join(tmp, "CLIENT-GUIDE.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def test_guide_file_guard_reads_the_guide_and_refuses_drift():
    l3d = CW.client_wording_for("lifelike-3d")
    s3d = CW.client_wording_for("stylized-3d")
    with tempfile.TemporaryDirectory() as tmp:
        good = _guide(tmp, "## Step 9\n"
                      "- **Lifelike 3D.** %s Sample: https://example.test/a.mp4\n"
                      "- **Stylized 3D.** %s Sample coming soon.\n" % (l3d, s3d))
        assert CW.check_guide_file("lifelike-3d", good)
        assert CW.check_guide_file("stylized-3d", good)
        bad = _guide(tmp, "- **Lifelike 3D.** realistic and cinematic.\n")
        _raises("CLIENT_WORDING_DRIFT", CW.check_guide_file, "lifelike-3d", bad)
        _raises("GUIDE_LINE_MISSING", CW.check_guide_file, "stylized-3d", bad)
        _raises("GUIDE_UNREADABLE", CW.check_guide_file,
                "lifelike-3d", os.path.join(tmp, "absent.md"))
