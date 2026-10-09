"""FU-U14: one batch zip per client when a book/batch campaign finishes.

Trevor: the mp3 is part of the deliverable, so a batch ships the songs too.
build_batch_zip() writes one zip per client: one folder per author holding
the captioned ad, the clean master and the song mp3 (exactly those three
files), plus a README.md listing every file with its duration, resolution
and banner link. Missing file = BatchZipError, fail closed.
Both videos pass delivery_audio.check_delivery_audio() (AAC-LC 48 kHz,
faststart) or the zip is refused. stdlib + ffprobe/ffmpeg, no network.
"""
from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
from delivery_audio import check_delivery_audio  # noqa: E402

TOOL_NAME = "batch_zip"
TOOL_VERSION = "1.0.0"

README_NAME = "README.md"
PER_AD_FILES = 3        # captioned ad + clean master + song mp3


class BatchZipError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def safe_component(text):
    """One safe path component (author / title) for a zip folder name."""
    name = re.sub(r"[^\w\-]+", "-", (text or "").strip()).strip("-")
    if not name:
        raise BatchZipError("BAD_INPUT", "author/title required")
    return name


def folder_name(author, title, seen):
    """One folder per ad: "<Author>_<Title>", "_2" on a repeated pair.

    seen: the folder names already handed out (mutated by the caller).
    """
    base = "%s_%s" % (safe_component(author), safe_component(title))
    name, n = base, 1
    while name in seen:
        n += 1
        name = "%s_%d" % (base, n)
    seen.add(name)
    return name


def _ad_paths(ad):
    """The three delivered files of one ad, fail closed on anything missing."""
    pairs = (("captioned", ad.get("captioned")),
             ("clean master", ad.get("clean_master")),
             ("song mp3", ad.get("song_mp3")))
    out = []
    for label, p in pairs:
        if p is None:
            raise BatchZipError("AD_INCOMPLETE",
                                "%s has no %s path"
                                % (ad.get("title", "?"), label))
        path = Path(p)
        if not path.is_file() or path.stat().st_size == 0:
            raise BatchZipError("AD_INCOMPLETE",
                                "%s missing the %s (%s)"
                                % (ad.get("title", "?"), label, path))
        if label != "song mp3":     # both videos: AAC-LC 48 kHz faststart or refuse
            g = check_delivery_audio(path)
            if not g["ok"]:
                raise BatchZipError(g["reason_code"], "%s %s: %s"
                                    % (ad.get("title", "?"), label, g["reason"]))
        out.append((label, path))
    if len(out) != PER_AD_FILES:
        raise BatchZipError("AD_INCOMPLETE", "one ad must carry 3 files")
    return out


def build_batch_zip(client, ads, out_path):
    """One client zip: a folder per ad (3 files) + README (banner + numbers).

    ads: [{"author", "title", "captioned", "clean_master", "song_mp3",
           "duration_s", "resolution", "banner"}]
    Returns {"zip", "folders", "files", "readme"}.
    """
    if not ads:
        raise BatchZipError("BAD_INPUT", "no ads to zip")
    rows, seen = [], set()
    for ad in ads:
        folder = folder_name(ad.get("author", ""), ad.get("title", ""), seen)
        rows.append((folder, ad, _ad_paths(ad)))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    readme = _readme(client, rows)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(README_NAME, readme)
        for folder, _ad, files in rows:
            for _label, path in files:
                z.write(path, "%s/%s" % (folder, path.name))
    return {"zip": str(out), "folders": [f for f, _a, _p in rows],
            "files": sum(len(p) for _f, _a, p in rows), "readme": README_NAME}


def _readme(client, rows):
    lines = ["# %s — batch delivery" % client, "",
             "Each folder holds the captioned ad, the clean master and the "
             "song mp3 (320 kbps) — the songs are yours to release as an "
             "album.", "",
             "| folder | file | duration | resolution |", "|---|---|---|---|"]
    for folder, ad, files in rows:
        dur = ad.get("duration_s")
        res = ad.get("resolution") or "UNMEASURED"
        dur_s = "%.1f s" % float(dur) if isinstance(dur, (int, float)) \
            else "UNMEASURED"
        for label, path in files:
            lines.append("| %s | %s (%s) | %s | %s |"
                         % (folder, path.name, label, dur_s, res))
    lines += ["", "Banner link (all ads): %s" % (rows[0][1].get("banner")
                                                 or "UNMEASURED"), ""]
    return "\n".join(lines)


def main(argv=None):
    import argparse
    import json
    p = argparse.ArgumentParser(
        prog="batch_zip",
        description="FU-U14: one client zip (folder per ad + README)")
    p.add_argument("manifest", help="JSON: {client, ads:[...], out}")
    ns = p.parse_args(argv)
    try:
        with open(ns.manifest, encoding="utf-8") as f:
            spec = json.load(f)
        res = build_batch_zip(spec["client"], spec["ads"], spec["out"])
    except (OSError, ValueError, KeyError, BatchZipError) as e:
        print(json.dumps({"outcome": "error",
                          "reason_code": "BATCH_ZIP_FAILED",
                          "detail": str(e)}))
        return 1
    print(json.dumps({"outcome": "ok", **res}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
