"""W1-agnes-core-U9 acceptance: chained segments, beat-aligned scene changes,
crossfades and one soundtrack (SPEC A5.2a).

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/agnes_transitions
     (also runnable directly: python3 test_agnes_transitions.py)

stdlib only. No Agnes call, no KIE call, no network, no key. The one ffmpeg
round-trip test builds its own clips with lavfi in a temp folder and is skipped
where ffmpeg is absent; every other test injects a fake runner/probe.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

try:
    import pytest
except ModuleNotFoundError:
    # CI's "Skill 75 empty-home test suite" runs `python3 <this file>` with a
    # fresh empty HOME BEFORE the pytest step installs pytest, so a bare
    # module-level `import pytest` is a red build there (skill 75 rule: no
    # module-level pytest import under scripts/core -- the same guard
    # agnes_quota/test_agnes_quota.py carries). This suite's tests use
    # pytest.raises / pytest.approx / pytest.mark, so a direct run is only
    # meaningful under pytest; the required "Skill 75 pytest collection +
    # run" step installs pytest and runs every test below for real.
    if __name__ != "__main__":
        raise
    print("note: pytest not installed - agnes_transitions suite runs under "
          "python3 -m pytest (Skill 75 pytest collection + run step)")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)
from agnes_transitions import agnes_transitions as T  # noqa: E402

#: 6 segments x 10 s, the trial A / Test D shape. Clips measure 10.125 s because
#: Agnes delivers that extra eighth of a second (SPEC A5.1), which is what the
#: crossfades are built out of.
SEG_DUR = 10.125
SEGMENTS = [{"segment_id": "S%d" % (i + 1), "start_s": float(i * 10),
             "end_s": float(i * 10 + 10), "clip": "seg%d.mp4" % (i + 1)}
            for i in range(6)]
#: The blueprint only opens a scene on the Hero Shift, so the change lands at 30 s.
BLUEPRINT = {"beats": [
    {"beat": "ordinary_world", "start_s": 0.0, "end_s": 10.0},
    {"beat": "pain_deepens", "start_s": 10.0, "end_s": 20.0},
    {"beat": "wound_deepens", "start_s": 20.0, "end_s": 30.0},
    {"beat": "Hero Shift", "start_s": 30.0, "end_s": 40.0},   # the scene change
    {"beat": "climb", "start_s": 40.0, "end_s": 50.0},
    {"beat": "vindication", "start_s": 50.0, "end_s": 60.0},
]}


def _clips(n=6):
    return [{"src": "seg%d.mp4" % (i + 1), "dur": SEG_DUR} for i in range(n)]


def _frames(n, luma=128, ramp=0):
    """n grey 32x32 frames as raw bytes; ramp steps the luma per frame."""
    out = b""
    for i in range(n):
        v = max(0, min(255, int(luma + ramp * i)))
        out += bytes([v]) * (T.JOIN_SAMPLE_W * T.JOIN_SAMPLE_W)
    return out


def _audio(seconds=1.0, level=8000):
    """s16le mono samples at `level` (a steady tone-ish constant)."""
    return struct.pack("<h", level) * int(seconds * 8000)


# --- 1 + 2: chain_plan -------------------------------------------------------

def test_chain_plan_two_scenes_change_at_hero_shift():
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    assert plan["ok"], plan
    chains = plan["chains"]
    # 6 segments in 2 chains, the split exactly on the Hero Shift boundary
    assert [len(c["segments"]) for c in chains] == [3, 3]
    assert chains[0]["scene"] == "scene_open"
    assert chains[1]["scene"] == "hero_shift"
    assert chains[1]["start_s"] == 30.0
    assert chains[1]["segments"][0]["segment_id"] == "S4"

    joins = plan["joins"]
    assert len(joins) == 5
    at = [j["at_s"] for j in joins]
    assert at == [10.0, 20.0, 30.0, 40.0, 50.0], at
    # one scene change, at the Hero Shift; the other four are intra-scene
    assert [j["scene_change"] for j in joins] == [False, False, True, False, False]
    # Test D: 0.2 s fade inside a scene, 0.4 s directional push at a scene change
    assert [j["xfade_s"] for j in joins] == [0.2, 0.2, 0.4, 0.2, 0.2]
    assert [j["transition"] for j in joins] == ["fade", "fade", "slideleft",
                                                "fade", "fade"]


def test_chain_plan_music_cue_is_a_boundary_and_off_beat_is_refused():
    # a music cue is allowed to open a scene (SPEC A5.2a item 2)
    cue = {"beats": [{"beat": "ordinary_world", "start_s": 0.0},
                     {"beat": "climb", "start_s": 30.0, "music_cue": True}]}
    plan = T.chain_plan(SEGMENTS, cue)
    assert plan["ok"] and len(plan["chains"]) == 2, plan

    # an explicit scene change that sits on no beat and no music cue is refused
    off = [dict(s) for s in SEGMENTS]
    off[4]["scene"] = "flashback"          # S5 changes scene on "climb" - no beat
    plan = T.chain_plan(off, BLUEPRINT)
    assert not plan["ok"] and plan["reason_code"] == "AGNES_SCENE_CHANGE_OFF_BEAT", plan

    # a timeline that runs backwards or overlaps is refused, never silently joined
    bad = [dict(s) for s in SEGMENTS]
    bad[2]["start_s"] = 15.0
    plan = T.chain_plan(bad, BLUEPRINT)
    assert not plan["ok"] and plan["reason_code"] == "AGNES_SEGMENTS_NOT_MONOTONIC", plan


# --- 4: join_argv ------------------------------------------------------------

def test_join_argv_five_xfades_every_input_muted_song_is_the_only_audio():
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    argv = T.join_argv(_clips(), styles=plan["joins"], song="song.m4a",
                       output="master.mp4")

    # 5 xfades, one per join
    fc = argv[argv.index("-filter_complex") + 1]
    assert fc.count("xfade=transition=") == 5, fc
    assert fc.count("slideleft") == 1 and fc.count("fade:duration") == 4, fc
    assert "xfade=transition=slideleft:duration=0.400000:offset=29.575000" in fc, fc
    # 24 fps and the crop-in fill to the chosen shape on every input
    assert fc.count("fps=24,") == 6 and fc.count("scale=720:1280") == 6, fc

    # `-an` on every Agnes input, and the song is the single audio map
    inputs = [i for i, a in enumerate(argv) if a == "-i"]
    assert len(inputs) == 7                                  # 6 clips + the song
    for i in inputs[:6]:
        assert argv[i - 1] == "-an", argv[i - 1:i + 2]
    assert argv.count("-an") == 6                            # one per Agnes input
    assert argv.count("-map") == 2
    maps = [argv[i + 1] for i, a in enumerate(argv) if a == "-map"]
    assert maps == ["[vout]", "[aout]"], maps
    assert argv.index("[aout]") > inputs[-1]                 # the song, after the clips
    assert "-c:a" in argv and argv[argv.index("-c:a") + 1] == "aac"
    assert "+faststart" in argv
    assert argv[-1] == "master.mp4"
    # xfade offsets: each join starts one overlap before the output's current end
    for offset in ("9.925000", "19.850000", "29.575000", "39.500000", "49.425000"):
        assert "offset=%s" % offset in fc, (offset, fc)


def test_join_argv_no_song_is_silent_and_one_clip_needs_no_xfade():
    argv = T.join_argv(_clips(1))
    assert "xfade" not in argv[argv.index("-filter_complex") + 1]
    assert argv.count("-an") == 2                            # the clip + the output
    assert argv.count("-map") == 1                           # the video, and nothing else
    # a plain cut (0 s) loses no frames: concat, not xfade
    argv = T.join_argv(_clips(2), xfade_s=0.0)
    fc = argv[argv.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=0" in fc and "xfade" not in fc, fc


def test_join_argv_refuses_a_style_list_of_the_wrong_length():
    with pytest.raises(ValueError):
        T.join_argv(_clips(3), styles=[{}])
    with pytest.raises(ValueError):
        T.join_argv([])


# --- 5: lipsync_offsets ------------------------------------------------------

def test_lipsync_window_at_23s_shifts_by_the_crossfade_overlaps():
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    windows = [{"line_id": "L1", "start_s": 23.0, "end_s": 25.0},
               {"line_id": "L2", "start_s": 4.0, "end_s": 6.0}]
    out = T.lipsync_offsets(windows, plan["joins"])
    # two intra-scene joins (0.2 s each) are before 23 s -> the window moves 0.4 s
    assert out[0]["start_s"] == pytest.approx(22.6), out[0]
    assert out[0]["end_s"] == pytest.approx(24.6), out[0]
    assert out[0]["shift_s"] == pytest.approx(0.4), out[0]
    assert out[1]["shift_s"] == 0.0 and out[1]["start_s"] == 4.0, out[1]
    # the join AT the window's start counts (a window starting on a join is after it)
    assert T.lipsync_offsets([{"start_s": 10.0, "end_s": 12.0}], plan["joins"])[0][
        "shift_s"] == pytest.approx(0.2)
    # bare-number joins take the caller's default
    assert T.lipsync_offsets([{"start_s": 50.0, "end_s": 51.0}], [10, 20, 40],
                             xfade_s=0.3)[0]["shift_s"] == pytest.approx(0.9)


# --- 6: check_joins ----------------------------------------------------------

def _probe_of(bad_join=None, jump_join=None, silent_join=None, scene_change=()):
    """A fake window sampler: healthy grey footage except at the named joins."""
    def probe(path, start_s, dur_s):
        join = int(round(start_s + dur_s / 2.0 - 0.001))
        return {
            "video": _frames(8, luma=0 if join == bad_join else 128,
                             ramp=90 if join == jump_join else 0),
            "audio": b"" if join == silent_join else _audio(),
        }
    return probe


def test_black_frame_at_a_join_fails_check_joins():
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    joins = plan["joins"]
    good = T.check_joins("master.mp4", joins, probe=_probe_of())
    assert good["ok"], good
    assert all(r["ok"] and r["min_luma"] > T.BLACK_LUMA for r in good["joins"]), good

    bad = T.check_joins("master.mp4", joins, probe=_probe_of(bad_join=30))
    assert not bad["ok"], bad
    row = [r for r in bad["joins"] if r["at_s"] == 30.0][0]
    assert row["reasons"] == ["JOIN_BLACK_FRAME"], row
    # only that join fails; the other four stay clean
    assert [r["at_s"] for r in bad["joins"] if not r["ok"]] == [30.0], bad


def test_intra_scene_jump_fails_but_a_motivated_scene_change_does_not():
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    jumps = T.check_joins("master.mp4", plan["joins"], probe=_probe_of(jump_join=10))
    assert not jumps["ok"]
    row = [r for r in jumps["joins"] if r["at_s"] == 10.0][0]
    assert row["reasons"] == ["JOIN_JUMP"] and row["jump_max"] > T.JOIN_JUMP_LIMIT, row

    same_jump_at_the_hero_shift = T.check_joins("master.mp4", plan["joins"],
                                                probe=_probe_of(jump_join=30))
    assert same_jump_at_the_hero_shift["ok"], same_jump_at_the_hero_shift


def test_missing_or_silent_audio_at_a_join_fails():
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    silent = T.check_joins("master.mp4", plan["joins"],
                           probe=_probe_of(silent_join=40.0))
    assert not silent["ok"]
    row = [r for r in silent["joins"] if r["at_s"] == 40.0][0]
    assert row["reasons"] == ["JOIN_AUDIO_GAP"], row     # no samples at all
    flat = T.check_joins("master.mp4", plan["joins"][:1],
                         probe=lambda p, s, d: {"video": _frames(8), "audio": _audio(1.0, 0)})
    assert not flat["ok"] and flat["joins"][0]["reasons"] == ["JOIN_AUDIO_SILENT"], flat


# --- 3: last_frame -----------------------------------------------------------

def test_last_frame_seeks_one_frame_before_the_end():
    seen = []
    path = T.last_frame("clip1.mp4", "f.png", probe=lambda p: 10.125,
                        runner=lambda argv: seen.append(argv))
    assert path == "f.png"
    argv = seen[0]
    assert isinstance(argv, list), argv                  # an array, never a shell string
    assert argv[:3] == ["ffmpeg", "-y", "-ss"] and float(argv[3]) == pytest.approx(10.125 - 1.0 / 24, abs=0.001)
    assert argv[argv.index("-frames:v") + 1] == "1" and argv[argv.index("-update") + 1] == "1"
    assert argv[-1] == "f.png" and "clip1.mp4" in argv


# --- 2: submit_order ---------------------------------------------------------

def test_submit_order_two_chains_in_parallel_segments_in_order():
    import threading
    plan = T.chain_plan(SEGMENTS, BLUEPRINT)
    lock = threading.Lock()
    gate = threading.Barrier(len(plan["chains"]))
    first_of_chain = {c["segments"][0]["segment_id"] for c in plan["chains"]}
    live, peak, calls = [0], [0], []

    def runner(seg):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            calls.append(seg["segment_id"])
        if seg["segment_id"] in first_of_chain:
            # Each chain parks here on its FIRST segment, so the barrier only
            # releases once both are inside submit_order at the same time.
            # That is the parallelism, proven deterministically: a sleep race
            # reports a busy box as a serial run.
            gate.wait(timeout=10)
        time.sleep(0.02)
        with lock:
            live[0] -= 1
        return seg["segment_id"] + ".mp4"

    rows = T.submit_order(plan["chains"], runner, max_chains=2)
    assert [r["chain_id"] for r in rows] == ["chain1", "chain2"], rows
    assert rows[0]["segments"] == ["S1.mp4", "S2.mp4", "S3.mp4"], rows[0]
    assert rows[1]["segments"] == ["S4.mp4", "S5.mp4", "S6.mp4"], rows[1]
    assert peak[0] == 2 and len(calls) == 6, (peak[0], calls)

    # one chain's segments never overlap
    def serial_runner(seg):
        time.sleep(0.01)
        return seg["segment_id"]

    rows = T.submit_order(plan["chains"], serial_runner, max_chains=1)
    assert [r["segments"] for r in rows] == [["S1", "S2", "S3"], ["S4", "S5", "S6"]]

    # a chain that raises is reported, never swallowed
    def boom(seg):
        if seg["segment_id"] == "S5":
            raise OSError("vendor 503")
        return seg["segment_id"]

    with pytest.raises(RuntimeError, match="AGNES_CHAIN_FAILED"):
        T.submit_order(plan["chains"], boom)


# --- the one real ffmpeg round-trip (no network, no spend) -------------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                    reason="ffmpeg not installed")
def test_join_renders_one_video_and_the_song_as_the_only_audio():
    tmp = tempfile.mkdtemp(prefix="lane-W1-agnes-core-U9-join-")
    try:
        clips, song = [], os.path.join(tmp, "song.m4a")
        for i, colour in enumerate(("red", "green", "blue")):
            path = os.path.join(tmp, "clip%d.mp4" % i)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                            "-i", "color=c=%s:s=320x568:d=1" % colour,
                            "-f", "lavfi", "-i", "sine=f=%d:d=1" % (220 * (i + 1)),
                            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", path], check=True, capture_output=True)
            clips.append({"src": path, "dur": 1.0})
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "sine=f=440:d=3", "-c:a", "aac", song],
                       check=True, capture_output=True)

        out = os.path.join(tmp, "joined.mp4")
        argv = T.join_argv(clips, styles=[{"xfade_s": 0.2, "transition": "fade"},
                                          {"xfade_s": 0.4, "scene_change": True}],
                           song=song, output=out)
        subprocess.run(argv, check=True, capture_output=True)

        streams = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", out], check=True, capture_output=True,
            text=True).stdout.split()
        assert streams == ["video", "audio"], streams          # one audio: the song
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", out], check=True, capture_output=True,
            text=True).stdout.strip())
        assert dur == pytest.approx(3.0 - 0.2 - 0.4, abs=0.2), dur

        # the join check passes on the real render and finds no black frame
        joins = [{"at_s": 1.0, "xfade_s": 0.2, "scene_change": False},
                 {"at_s": 1.8, "xfade_s": 0.4, "scene_change": True}]
        assert T.check_joins(out, joins)["ok"], T.check_joins(out, joins)
        # last_frame extracts a real PNG out of it
        png = os.path.join(tmp, "last.png")
        T.last_frame(out, png)
        assert os.path.getsize(png) > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_directly():
    failed = 0
    for name in sorted(n for n in globals() if n.startswith("test_")):
        try:
            globals()[name]()
            print("  ok   %s" % name)
        except Exception as exc:                            # noqa: BLE001
            failed += 1
            print("  FAIL %s: %r" % (name, exc))
    print("agnes_transitions: %s" % ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_directly())
