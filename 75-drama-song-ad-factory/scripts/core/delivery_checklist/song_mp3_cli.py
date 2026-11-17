#!/usr/bin/env python3
"""song_mp3_cli.py - the FU-U14 song-mp3 delivery gate, as a command.

    python3 scripts/core/delivery_checklist/song_mp3_cli.py \
      --ad-dir <AD_DIR> --ad-audio <AD_AUDIO> --title "<Title>" --author "<Author>"

Prints the SONG_MP3_FILE / SONG_MP3_DURATION / SONG_MP3_CORRELATION rows as
JSON. Exit 5 when any row fails (fail closed), 0 when every row passes.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from delivery_checklist.delivery_checklist import check_song_mp3  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ad-dir", required=True)
    ap.add_argument("--ad-audio", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    a = ap.parse_args(argv)
    rows = check_song_mp3(a.ad_dir, a.ad_audio, a.title, a.author)
    ok = all(row.get("answer") == "yes" for row in rows)
    print(json.dumps({"pass": ok, "rows": rows}, indent=2, sort_keys=True))
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
