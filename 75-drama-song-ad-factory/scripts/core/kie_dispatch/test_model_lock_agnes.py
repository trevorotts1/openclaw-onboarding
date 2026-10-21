#!/usr/bin/env python3
"""W1-agnes-core-U8: the delivery gate accepts Agnes flash clips.

SPEC A10 - with Agnes = Yes the delivery gate accepts the Agnes flash clips and
the locked backup model, nothing else: the paid `agnes-video-2.5` and the
retired `agnes-video-v2.0` still fail `VIDEO_MODEL_MISMATCH`. The default
(`agnes_chosen=False`) keeps today's plain-F14 verdict, and
`ALLOWED_VIDEO_MODELS` is untouched.

stdlib only. Zero paid calls: no Agnes, no KIE - these are pure function calls.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/kie_dispatch/test_model_lock_agnes.py
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

ML = importlib.import_module("kie_dispatch.model_lock")

FLASH = "agnes-video-2.5-flash"
BACKUP = ML.DEFAULT_VIDEO_MODEL          # minimax-h3/*


def _bad(clip_models, locked=BACKUP, agnes=True):
    """Delivery verdict for a flat list of clip model ids."""
    return ML.check_video_model_delivery(
        {"clips": [{"model": m} for m in clip_models]},
        locked, agnes_chosen=agnes)


def test_flash_and_locked_backup_pass():
    assert _bad([FLASH, FLASH]) == []
    assert _bad([FLASH, BACKUP]) == []
    # the locked backup model alone still passes on an Agnes run
    assert _bad([BACKUP]) == []


def test_paid_and_retired_agnes_models_fail():
    for model in ("agnes-video-2.5", "agnes-video-v2.0"):
        out = _bad([model])
        assert len(out) == 1, (model, out)
        assert out[0].startswith("VIDEO_MODEL_MISMATCH"), out[0]
        assert model in out[0], out[0]


def test_agnes_run_names_the_locked_backup_on_failure():
    out = _bad([FLASH, "agnes-video-2.5"])
    assert len(out) == 1, out
    assert "locked video model is %r" % BACKUP in out[0], out[0]


def test_wrong_kie_model_fails_even_when_agnes_chosen():
    # a menu model that is not the locked backup is still a mismatch
    out = _bad([FLASH, "bytedance/seedance-2-mini"])
    assert len(out) == 1, out
    assert "bytedance/seedance-2-mini" in out[0], out[0]


def test_flash_rejected_without_the_agnes_choice():
    assert _bad([FLASH], agnes=False) != []
    assert _bad([FLASH], agnes=False)[0].startswith("VIDEO_MODEL_MISMATCH")


def test_default_gate_unchanged():
    """Plain-F14 verdict, byte for byte, with and without the keyword."""
    locked_ok = [{"model": "hailuo/02-image-to-video-pro"},
                 {"model": "hailuo/02-image-to-video-standard"}]
    assert ML.check_video_model_delivery({"clips": locked_ok}, BACKUP) == []
    assert ML.check_video_model_delivery({"clips": locked_ok}, BACKUP,
                                         agnes_chosen=False) == []
    mismatch = [{"model": "hailuo/02-image-to-video-pro"},
                {"model": "bytedance/seedance-2-mini"}]
    plain = ML.check_video_model_delivery({"clips": mismatch}, BACKUP)
    agnes = ML.check_video_model_delivery({"clips": mismatch}, BACKUP,
                                          agnes_chosen=False)
    assert plain == agnes and len(plain) == 1, (plain, agnes)


def test_clip_with_no_model_stays_fail_closed():
    out = ML.check_video_model_delivery(
        {"clips": [{"id": "c1"}, {"model": FLASH}]}, BACKUP,
        agnes_chosen=True)
    assert len(out) == 1, out
    assert "records no model" in out[0], out[0]


def test_empty_receipt_is_clean_in_both_modes():
    assert ML.check_video_model_delivery({}, None) == []
    assert ML.check_video_model_delivery({}, None, agnes_chosen=True) == []


def test_flash_is_not_a_menu_model():
    """ALLOWED_VIDEO_MODELS unchanged; the Agnes id never joins the menu list."""
    assert FLASH not in ML.ALLOWED_VIDEO_MODELS
    assert "agnes-video-2.5" not in ML.ALLOWED_VIDEO_MODELS
    assert "agnes-video-v2.0" not in ML.ALLOWED_VIDEO_MODELS
    assert ML.AGNES_FLASH_MODEL == FLASH
