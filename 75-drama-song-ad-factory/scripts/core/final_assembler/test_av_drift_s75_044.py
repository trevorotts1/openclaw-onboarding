#!/usr/bin/env python3
"""S75-044: audio and video durations are measured per stream.

The old verify step probed the container's single format duration twice and
compared it with itself, so AV_DRIFT could never fire. These checks prove the
two streams are now measured separately:

  1. a file whose audio stream is 1.0 s shorter than its video stream fails
     with AV_DRIFT; an aligned file does not.
  2. a stream that reports no duration is measured from its packet
     timestamps instead.

Fixtures are built with local ffmpeg at test time (nothing binary committed).
Stdlib only, zero paid calls, no network, no browser.
Run: python3 -B scripts/core/final_assembler/test_av_drift_s75_044.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A          # noqa: E402

FPS = 30
FRAME = 1.0 / FPS
FAILS = []
HAVE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _media(path, video_s, audio_s):
    """H.264 video and AAC audio of independent lengths, muxed in one mp4."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i",
        "testsrc2=size=320x240:rate=%d:duration=%g" % (FPS, video_s),
        "-f", "lavfi", "-i", "sine=frequency=440:duration=%g" % audio_s,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        path], check=True, capture_output=True)


def test_short_audio_raises_av_drift(tmp):
    """Audio 1.0 s shorter than video: both streams measured, AV_DRIFT."""
    path = os.path.join(tmp, "short-audio.mp4")
    _media(path, 3.0, 2.0)
    vdur = A.probe_stream_duration(path, "v:0")
    adur, code = A.check_av_drift(path, vdur, FRAME, timeout=60)
    check("video stream measures ~3.0 s", abs(vdur - 3.0) < 0.15, vdur)
    check("audio stream measures ~2.0 s", abs(adur - 2.0) < 0.15, adur)
    check("the two durations are measured separately", abs(vdur - adur) > 0.9,
          "video=%r audio=%r" % (vdur, adur))
    check("short audio raises AV_DRIFT", code == "AV_DRIFT", code)


def test_aligned_file_passes(tmp):
    """Equal-length streams: neither AV_DRIFT nor a probe failure."""
    path = os.path.join(tmp, "aligned.mp4")
    _media(path, 3.0, 3.0)
    vdur = A.probe_stream_duration(path, "v:0")
    adur, code = A.check_av_drift(path, vdur, FRAME, timeout=60)
    check("aligned audio measures ~3.0 s", abs(adur - 3.0) < 0.15, adur)
    check("aligned file does not raise AV_DRIFT", code is None, code)
    check("aligned file is within one frame",
          abs(adur - vdur) <= FRAME + 1e-3, "video=%r audio=%r" % (vdur, adur))


class _FakeProc(object):
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def test_packet_timestamp_fallback():
    """A stream that reports no duration is measured from its packets."""
    real_run = A.subprocess.run
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        if "stream=duration" in cmd:
            return _FakeProc('{"streams": [{"duration": "N/A"}]}')
        return _FakeProc(
            '{"packets": ['
            '{"pts_time": "0.000000", "duration_time": "1.000000"},'
            '{"pts_time": "1.000000", "duration_time": "1.000000"},'
            '{"pts_time": "2.000000", "duration_time": "1.000000"}]}')

    A.subprocess.run = fake
    try:
        dur = A.probe_stream_duration("synthetic.mp4", "a:0")
    finally:
        A.subprocess.run = real_run
    check("fallback runs the stream probe, then the packet probe",
          len(calls) == 2 and "stream=duration" in calls[0]
          and "packet=pts_time,duration_time" in calls[1], len(calls))
    check("fallback returns the last packet end",
          abs(dur - 3.0) < 1e-6, dur)


def main():
    test_packet_timestamp_fallback()
    if not HAVE:
        print("skip: ffmpeg/ffprobe not installed; live media checks skipped")
    else:
        tmp = tempfile.mkdtemp(prefix="w75-av-drift-")
        try:
            test_short_audio_raises_av_drift(tmp)
            test_aligned_file_passes(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("%s" % ("%d check(s) failed" % len(FAILS) if FAILS
                  else "all S75-044 checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
