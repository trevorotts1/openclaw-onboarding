#!/usr/bin/env python3
"""DEL-14 (unit PKG-05-U1): the still-fill path is crop-in, and only crop-in.

Two kinds of assertion, both required:

  CODE      the filter this package and the final assembler emit carries
            a cover-then-crop and none of the four banned shapes -- no
            stretch (a bare `scale=W:H`), no letterbox (`pad=`), no blur
            fill (`gblur`/`boxblur`/`blur=`) and no duplicated blurred
            strip (`hstack`/`vstack`/`tblend`/`overlay`).

  OUTPUT    a real ffmpeg render of a sharp checkerboard source through
            the assembler's own chain comes out full height (1080x1920)
            with a plain top, measured off the pixels: the top band
            carries the source's own detail. Three negative controls --
            blur fill, letterbox and a duplicated blurred strip -- render
            to the same size and are REJECTED by the same measurement,
            which is what proves the measurement can tell them apart.

Stdlib + ffmpeg/ffprobe. Zero paid calls, no network. When ffmpeg is not
installed the render half reports SKIP with a stated reason (it never
reports a pass it did not earn); the code half still runs.

Run: python3 scripts/video_still_fill/test_video_still_fill.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
CORE = os.path.join(SCRIPTS, "core")
for _p in (SCRIPTS, CORE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import video_still_fill as V        # noqa: E402
import final_assembler.assembler as A   # noqa: E402

FAILS = []
SKIPS = []

#: The shapes DEL-14 bans, as they would appear in a filter graph.
BANNED = {
    "blur fill": re.compile(r"(?<![a-z])(?:g?blur|avgblur|boxblur|smartblur)"
                            r"=|blur=", re.I),
    "letterbox pad": re.compile(r"(?<![a-z])pad="),
    "duplicated strip": re.compile(r"(?<![a-z])(?:hstack|vstack|tblend|overlay)="),
}
#: A stretch is `scale=W:H` WITHOUT the cover key next to it. The key is
#: what makes the scale proportional, so its absence -- not the presence of
#: a colon -- is the defect.
SCALE = re.compile(r"(?<![a-z])scale=(-?\d+):(-?\d+)((?::[^,\[\];]*)*)")
#: A cover-then-crop is the only shape that reaches full height honestly.
COVER_CROP = re.compile(
    r"scale=\d+:\d+:force_original_aspect_ratio=increase"
    r".*crop=w=\d+:h=\d+:x=0:y=0", re.I)


def stretches(chain):
    """Every `scale=W:H` in `chain` that is not a cover scale."""
    bad = []
    for m in SCALE.finditer(chain):
        if "force_original_aspect_ratio=" not in (m.group(3) or ""):
            bad.append(m.group(0))
    return bad


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def skip(name, why):
    print("SKIP: %s (%s)" % (name, why))
    SKIPS.append(name)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception as exc:            # noqa: BLE001 - any refusal counts
        return exc
    return None


# --- fixtures ---------------------------------------------------------------

def checker_ppm(path, w=1920, h=1080, cell=8):
    """Sharp black/white checkerboard: maximum local detail everywhere a
    crop-in keeps the source, maximum contrast against any synthesized
    flat band."""
    white = bytes(bytearray(255 if ((x // cell) % 2 == 0) else 0
                            for x in range(w)))
    black = bytes(bytearray(0 if ((x // cell) % 2 == 0) else 255
                            for x in range(w)))
    with open(path, "wb") as fh:
        fh.write(b"P6\n%d %d\n255\n" % (w, h))
        for y in range(h):
            fh.write(white if (y // cell) % 2 == 0 else black)


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def ffmpeg_available():
    return (shutil.which("ffmpeg") is not None
            and shutil.which("ffprobe") is not None)


# --- code inspection --------------------------------------------------------

def test_filter_shape_is_crop_in():
    chain = V.cover_crop_filter(1080, 1920)
    check("cover filter scales up to cover then crops",
          bool(COVER_CROP.search(chain)), chain)
    for label, pat in BANNED.items():
        check("cover filter carries no %s" % label, not pat.search(chain),
              "%s in %s" % (label, chain))
    check("cover filter is never a stretch",
          not stretches(chain), str(stretches(chain)))
    check("cover filter ends on setsar=1 (concat/xfade join)",
          chain.endswith("setsar=1"), chain)
    check("plain-top anchor is y=0 (source's own top rows)",
          "y=0" in chain, chain)


def test_still_clip_path_is_the_same_path():
    chain = V.still_clip_filter(1080, 1920)
    check("still clip uses the same crop-in filter",
          chain == V.cover_crop_filter(1080, 1920), chain)
    argv = V.still_clip_argv("still.png", "out.mp4", duration_s=2.0)
    joined = " ".join(argv)
    check("still clip argv is an array ending on the output",
          argv[-1] == "out.mp4" and argv[0].endswith("ffmpeg"), str(argv[:4]))
    check("still clip argv drives a looped still",
          "-loop" in argv and "-i" in argv, joined)
    vf = argv[argv.index("-vf") + 1]
    for label, pat in BANNED.items():
        check("still clip vf carries no %s" % label, not pat.search(vf), vf)
    check("still clip vf is never a stretch",
          not stretches(vf), str(stretches(vf)))


def test_geometry_fails_closed():
    check("geometry accepts a real canvas",
          V.geometry(1080, 1920) == (1080, 1920))
    for bad in ((0, 1920), (-4, 1920), (1080.5, 1920), (True, 1920),
                ("1080", 1920), (1080, None), (None, None)):
        exc = raises(V.geometry, *bad)
        check("geometry refuses %r" % (bad,),
              isinstance(exc, V.StillFillError), str(exc))


def test_assembler_uses_the_path():
    plan = {"fps": 30, "width": 1080, "height": 1920, "total_dur": 2.0,
            "segments": [{"src": "clip.mp4", "snapped_dur": 2.0,
                          "transition": "none", "source_fps": 30.0}]}
    argv = A.build_argv(plan, "out.mp4")
    fc = argv[argv.index("-filter_complex") + 1]
    check("assembler chain is cover-then-crop", bool(COVER_CROP.search(fc)),
          fc)
    check("assembler chain still joins on setsar", "setsar=1" in fc, fc)
    for label, pat in BANNED.items():
        check("assembler chain carries no %s" % label, not pat.search(fc),
              "%s in %s" % (label, fc))
    check("assembler chain is never a stretch",
          not stretches(fc), str(stretches(fc)))


def test_assembler_refuses_an_uncoverable_canvas():
    def load(width, height):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                       "width": width, "height": height, "song_path": None,
                       "segments": [{"src": "a.mp4", "dur": 2.0}]}, fh)
            path = fh.name
        try:
            return A.load_timeline(path)
        finally:
            os.unlink(path)
    ok = raises(load, 1080, 1920)
    check("load_timeline accepts a coverable canvas", ok is None, str(ok))
    for bad in ((0, 1920), (-1, 1920), (1080.5, 1920), (None, 1920)):
        exc = raises(load, *bad)
        check("load_timeline refuses canvas %r" % (bad,),
              isinstance(exc, ValueError)
              and "TIMELINE_BAD_SIZE" in str(exc), str(exc))


# --- output inspection (real ffmpeg) ---------------------------------------

def test_crop_in_render_is_full_height_with_a_plain_top(tmp):
    src = os.path.join(tmp, "checker.ppm")
    checker_ppm(src)
    out = os.path.join(tmp, "cropin.mp4")
    argv = V.still_clip_argv(src, out, duration_s=0.5)
    res = run(argv)
    check("crop-in render exits 0", res.returncode == 0,
          (res.stderr or "")[-400:])
    if res.returncode != 0:
        return
    check("crop-in output probes to the full 9x16 canvas",
          V.is_full_height(out, 1080, 1920), str(V.probe_size(out)))
    m = V.frame_metrics(out)
    check("crop-in top band carries the source's own detail",
          m["top_max"] > V.FLAT_BAND_MAX_FLOOR
          and m["ratio"] >= V.PLAIN_TOP_RATIO_FLOOR,
          "top_max=%s ratio=%.3f" % (m["top_max"], m["ratio"]))
    check("crop-in is judged a plain top", V.is_plain_top(out),
          json.dumps(m))


def test_negative_controls_are_rejected(tmp):
    """Three banned shapes render to the same canvas and fail the SAME
    measurement the crop-in path passes -- proof the measurement
    discriminates, not proof that anything renders."""
    src = os.path.join(tmp, "checker.ppm")
    checker_ppm(src)
    controls = {
        "blur fill": (
            "[0:v]split[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
            "gblur=sigma=40,crop=1080:1920[bg];"
            "[b]scale=-2:960[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"),
        "letterbox pad": (
            "[0:v]scale=1080:-2[fg];"
            "[fg]pad=1080:1920:0:(1920-ih)/2:color=black,setsar=1[v]"),
        "duplicated blurred strip": (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920:0:0,split[a][b];"
            "[a]crop=1080:40:0:0,scale=1080:400,gblur=sigma=30[strip];"
            "[b]crop=1080:1520:0:40[body];"
            "[strip][body]vstack=inputs=2,setsar=1[v]"),
    }
    for label, graph in controls.items():
        # the code detectors have to bite this graph too, or the output
        # measurement below would be the only thing standing between a
        # deliverable and a fill.
        trips = [lab for lab, pat in BANNED.items() if pat.search(graph)]
        if stretches(graph):
            trips.append("stretch")
        check("%s control trips a code detector" % label, bool(trips),
              "graph=%s" % graph)
        out = os.path.join(tmp, re.sub(r"\W+", "_", label) + ".mp4")
        res = run(["ffmpeg", "-v", "error", "-y", "-loop", "1",
                   "-framerate", "30", "-t", "0.5", "-i", src,
                   "-filter_complex", graph, "-map", "[v]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-preset", "ultrafast", out])
        check("%s control renders (otherwise the control proves nothing)"
              % label, res.returncode == 0, (res.stderr or "")[-400:])
        if res.returncode != 0:
            continue
        check("%s control reaches the canvas (size is not the failure)"
              % label, V.is_full_height(out, 1080, 1920),
              str(V.probe_size(out)))
        m = V.frame_metrics(out)
        check("%s control is NOT a plain top" % label,
              not V.is_plain_top(out),
              "top_max=%s ratio=%.3f" % (m["top_max"], m["ratio"]))


def main():
    tmp = tempfile.mkdtemp(prefix="pkg05u1-still-fill-")
    try:
        test_filter_shape_is_crop_in()
        test_still_clip_path_is_the_same_path()
        test_geometry_fails_closed()
        test_assembler_uses_the_path()
        test_assembler_refuses_an_uncoverable_canvas()
        if ffmpeg_available():
            test_crop_in_render_is_full_height_with_a_plain_top(tmp)
            test_negative_controls_are_rejected(tmp)
        else:
            skip("output inspection", "ffmpeg/ffprobe not installed")
        print("----")
        if SKIPS:
            print("skipped: %d (%s)" % (len(SKIPS), "; ".join(SKIPS)))
        print("checks failed: %d" % len(FAILS))
        if FAILS:
            for f in FAILS:
                print("  FAILED: %s" % f)
        return 1 if FAILS else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
