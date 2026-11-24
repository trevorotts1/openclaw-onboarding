#!/usr/bin/env python3
"""Pytest checks for the look lock (row N-29, section 3B.2). Stdlib only.

Run: pytest scripts/core/style_defaults/test_look_lock_n29.py
$0 spend, no network. Each ``test_*`` is one behaviour the lock must hold; the
build stages no proof run.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

from style_defaults import look_lock as LL  # noqa: E402


def _built_lock():
    return LL.build_lock("lifelike-3d", chosen_by="run owner",
                         chosen_at="2026-11-23T14:00:00-05:00",
                         character_bible_fingerprint="abc123")


def _raises(code, fn, *args):
    try:
        fn(*args)
    except LL.LookLockError as exc:
        assert exc.code == code, exc.code
        return
    raise AssertionError("did not refuse with %s" % code)


def test_lock_starts_at_version_1_and_copies_every_block():
    lock = _built_lock()
    assert lock["version"] == 1, lock["version"]
    assert all(lock["style_blocks"].get(k) for k in LL.COPIED_BLOCKS), \
        list(lock["style_blocks"])


def test_lock_carries_banned_words_and_records_who_and_when():
    lock = _built_lock()
    assert lock["banned_words"]
    assert lock["chosen_by"] == "run owner" and lock["chosen_at"]


def test_fingerprint_verifies_and_tamper_changes_it():
    lock = _built_lock()
    assert LL.verify_fingerprint(lock)
    tampered = dict(lock)
    tampered["banned_words"] = list(lock["banned_words"]) + ["zzz"]
    assert LL.lock_fingerprint(tampered) != lock["fingerprint"]


def test_a_record_is_current_at_the_lock_version_and_stale_below_it():
    lock = _built_lock()
    assert LL.is_current(1, lock)
    assert LL.is_stale(0, lock)


def test_write_read_rotate_and_version_regress():
    lock = _built_lock()
    with tempfile.TemporaryDirectory() as run:
        path = LL.write_lock(run, lock)
        assert path.endswith(os.path.join("control", "look-lock.json")), path
        assert LL.read_lock_for_run(run) == lock
        rotated = LL.rotate(lock, chosen_by="run owner",
                            chosen_at="2026-11-23T15:00:00-05:00")
        assert rotated["version"] == 2, rotated["version"]
        LL.write_lock(run, rotated)
        _raises("LOOK_LOCK_VERSION_REGRESS", LL.write_lock, run, lock)


def test_no_lock_refuses_making():
    with tempfile.TemporaryDirectory() as bare:
        _raises("LOOK_LOCK_MISSING", LL.require_lock, bare)


def test_locked_block_is_exempt_but_banned_words_outside_are_caught():
    lock = _built_lock()
    h3 = lock["style_blocks"]["h3_block"]
    assert LL.banned_word_hits(h3, lock["banned_words"], exempt=h3) == []
    outside = "the same frame, photoreal skin, shot on a DSLR"
    hits = LL.banned_word_hits(outside, lock["banned_words"], exempt=h3)
    assert "photoreal" in hits and "DSLR" in hits, hits


def test_lock_still_matches_its_mode_file():
    assert LL.verify_still_matches(_built_lock())


def test_hybrid_lock_verifies_each_mode_it_switches_between():
    lock = LL.build_lock("canvas-to-3d", chosen_by="run owner",
                         chosen_at="2026-11-23T14:00:00-05:00",
                         mode_id="lifelike-3d")
    assert lock["modes"] == ["lifelike-3d", "painted-2d"], lock["modes"]
    assert LL.verify_still_matches(lock)


def test_a_derived_look_keeps_the_palette_it_rendered_with():
    lock = LL.build_lock("golden-realism", chosen_by="run owner",
                         chosen_at="2026-11-23T14:00:00-05:00")
    assert lock["palette"] == LL.mode_style_blocks("golden-realism")["palette"]
    assert "{palette}" not in lock["style_blocks"]["h3_block"]
