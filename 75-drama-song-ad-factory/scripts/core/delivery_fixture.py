"""Test helper: tiny real mp4 files for the delivery-audio gate tests.

make_video(path, acodec) writes a 1 s mp4 with a 440 Hz tone. The default is
a file that passes check_delivery_audio (AAC-LC, 48 kHz, faststart); pass
acodec="libmp3lame" for the MP3-in-MP4 file the gate must refuse.
"""
import shutil
import subprocess

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def make_video(path, acodec="aac", faststart=True, rate=48000, secs=1):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
           "color=c=black:s=64x64:d=%d:r=10" % secs, "-f", "lavfi", "-i",
           "sine=f=440:r=%d:d=%d" % (rate, secs), "-t", str(secs), "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-c:a", acodec, "-strict", "-2"]
    if acodec == "aac":
        cmd += ["-profile:a", "aac_low", "-ar", str(rate)]
    if faststart:
        cmd += ["-movflags", "+faststart"]
    subprocess.run(cmd + [str(path)], check=True)
    return str(path)
