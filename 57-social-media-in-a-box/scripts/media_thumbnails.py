#!/usr/bin/env python3
"""media_thumbnails.py — F38 media upload / FFmpeg thumbnail adapter for
Skill 57 (Social Media in a Box).

For every produced video this adapter:
  1. extracts a poster frame with FFmpeg: ffmpeg -ss 0 -i in.mp4 -frames:v 1
     (first frame; an approved thumbnail may be passed with --poster instead),
  2. records the upload-with-video contract: the poster is uploaded to the
     client's GHL Media Library ALONGSIDE the video (same medias/upload-file
     path as SKILL.md's Media Delivery Contract) so both URLs are permanent
     CDN links,
  3. emits the sheet evidence row the planner writeback consumes: poster URL,
     duration (ffprobe), ratio, version, QC state, captions flag and the
     client-bound "Watch video" link,
  4. NEVER uploads client drafts to public YouTube. The only YouTube-related
     behavior is a smart-chip note when the PUBLISHED destination is YouTube —
     drafts get the private CC player route, never a public upload.

Watch video link: the client-bound Command Center player route
  {cc_base_url}/social/media/{assetId}
built from --cc-base-url + --asset-id. It is written as a trusted HYPERLINK
formula by the planner writeback (the poster cell is =IMAGE of the poster CDN
URL); this adapter emits the components, not untrusted sheet formulas.

Usage:
  python3 57-social-media-in-a-box/scripts/media_thumbnails.py --video in.mp4 \
      --asset-id a1b2 --cc-base-url https://cc.example.com \
      --out working/media/evidence.json
  python3 ... --video in.mp4 --poster approved.png --duration 25.0 --ratio 9:16 \
      --published-url https://youtube.com/watch?v=... --youtube-smart-chip

Exit 0 = evidence written; exit 2 = FFmpeg missing/failed (NOT VERIFIED note
when ffmpeg is absent — a skip is never reported as success).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def ffprobe_duration(video: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, timeout=60)
        if out.returncode == 0 and out.stdout.strip():
            return round(float(out.stdout.strip()), 1)
    except (OSError, ValueError):
        return None
    return None


def extract_poster(video: Path, out_png: Path) -> bool:
    """ffmpeg -ss 0 -i in.mp4 -frames:v 1 — first frame as the poster."""
    if shutil.which("ffmpeg") is None:
        return False
    try:
        proc = subprocess.run(
            ["ffmpeg", "-ss", "0", "-i", str(video), "-frames:v", "1",
             "-y", str(out_png)],
            capture_output=True, text=True, timeout=120)
        return proc.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def video_ratio(video: Path) -> str | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(video)],
            capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            dims = json.loads(out.stdout or "{}").get("streams", [{}])[0]
            w, h = dims.get("width"), dims.get("height")
            if w and h:
                if w > h:
                    return "16:9" if abs(w / h - 16 / 9) < 0.05 else f"{w}:{h}"
                if h > w:
                    return "9:16" if abs(h / w - 16 / 9) < 0.05 else f"{w}:{h}"
                return "1:1"
    except (OSError, ValueError):
        return None
    return None


def safe_url(url: str) -> bool:
    """The writeback only accepts https URLs without quotes/control chars."""
    return bool(re.match(r"^https://", url or "")) and not re.search(r'["\'\\\x00-\x1f]', url or "")


def build_watch_url(cc_base_url: str, asset_id: str) -> str:
    return f"{cc_base_url.rstrip('/')}/social/media/{asset_id}"


def main():
    parser = argparse.ArgumentParser(description="F38 poster extraction + video evidence row")
    parser.add_argument("--video", required=True, help="path to the produced video")
    parser.add_argument("--poster", help="approved thumbnail to use instead of FFmpeg extraction")
    parser.add_argument("--asset-id", required=True, help="company-bound CC media asset id")
    parser.add_argument("--cc-base-url", required=True, help="Command Center base URL (player route host)")
    parser.add_argument("--duration", type=float, help="override duration seconds (else ffprobe)")
    parser.add_argument("--ratio", help="override ratio (else ffprobe)")
    parser.add_argument("--version", default="r1", help="content revision/version label")
    parser.add_argument("--qc-state", default="QC Review")
    parser.add_argument("--captions", action="store_true", help="video carries captions")
    parser.add_argument("--published-url", help="ACTUAL published destination URL (after posting)")
    parser.add_argument("--youtube", action="store_true",
                        help="published destination is YouTube (adds smart-chip note)")
    parser.add_argument("--poster-cdn-url", help="permanent CDN URL of the uploaded poster")
    parser.add_argument("--out", required=True, help="path to write the evidence JSON")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"FAIL: video not found: {video}", file=sys.stderr)
        return 2

    poster = Path(args.poster) if args.poster else None
    poster_generated = False
    not_verified_note = None
    if poster is None:
        poster = video.with_suffix(".poster.png")
        if extract_poster(video, poster):
            poster_generated = True
        else:
            if shutil.which("ffmpeg") is None:
                not_verified_note = ("NOT VERIFIED: ffmpeg not available on this box — "
                                     "poster frame was NOT generated. Provide --poster "
                                     "(approved thumbnail) or install ffmpeg; the sheet row "
                                     "must not claim a rendered thumbnail without one.")
            else:
                not_verified_note = ("NOT VERIFIED: ffmpeg failed to extract a poster frame "
                                     "from this video. Provide --poster (approved thumbnail); "
                                     "the sheet row must not claim a rendered thumbnail without one.")
    duration = args.duration if args.duration is not None else ffprobe_duration(video)
    ratio = args.ratio or video_ratio(video) or "unknown"

    watch_url = build_watch_url(args.cc_base_url, args.asset_id)
    published_url = args.published_url if (args.published_url and safe_url(args.published_url)) else None
    poster_cdn = args.poster_cdn_url if (args.poster_cdn_url and safe_url(args.poster_cdn_url)) else None

    notes = []
    if args.youtube and published_url:
        # YouTube smart-chip note ONLY when applicable — and only for the
        # PUBLISHED destination. Drafts never go to public YouTube.
        notes.append("YouTube smart-chip preview applies to the PUBLISHED link only; "
                     "draft review stays on the client-bound player.")
    if not published_url:
        notes.append("No published URL yet — published_url stays separate from the "
                     "draft player link and is filled after posting.")

    evidence = {
        "contract": "F38 video evidence row",
        "video": str(video),
        "poster": str(poster) if poster.exists() or (poster and args.poster) else None,
        "poster_generated_by_ffmpeg": poster_generated,
        "poster_upload_contract": ("upload the poster to the client's GHL Media Library "
                                   "ALONGSIDE the video (medias/upload-file, permanent CDN URL) — "
                                   "never a raw Telegram attachment"),
        "poster_cdn_url": poster_cdn,
        "asset_id": args.asset_id,
        "duration_seconds": duration,
        "ratio": ratio,
        "version": args.version,
        "qc_state": args.qc_state,
        "captions": bool(args.captions),
        "watch_url": watch_url,
        "watch_url_contract": ("client-bound CC player route /social/media/{assetId}; "
                               "the planner writeback renders it as a trusted HYPERLINK "
                               "labeled 'Watch video' next to the poster image"),
        "published_url": published_url,
        "youtube_smart_chip": bool(args.youtube and published_url),
        "draft_public_youtube_upload": False,
        "notes": notes,
        "not_verified": not_verified_note,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(evidence, f, indent=2)
    print(f"video evidence written to {out}")
    if not_verified_note:
        print(not_verified_note, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())