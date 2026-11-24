"""N-18: the full-watch log -- a contact sheet of the whole master, opened.

Delivery requires two things and this module produces both:

  1. a CONTACT SHEET of the whole master at one frame per second, rendered as
     one tiled picture a person can open and read top to bottom;
  2. a RECORD that the sheet was opened and looked at -- who, when, and the
     sheet's own digest, so a later sheet can never ride an older look.

Fail closed: no sheet, a sheet whose bytes no longer match the record, or a
record with no viewer is a refusal (``FULL_WATCH_*``). Nothing here claims a
person looked; it records the look that happened, and refuses to pass without
one.

Stdlib + ffmpeg/ffprobe through the load governor. Zero spend, no network.

Run: python3 scripts/core/delivery_checklist/full_watch.py check <run_dir>
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import load_governor as _LG                                   # noqa: E402
from delivery_variants.manifests import sha256_file           # noqa: E402
from delivery_variants.video_delivery import probe            # noqa: E402

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"
TOOL_NAME = "full_watch"
TOOL_VERSION = "1.0.0"

RECORD_PATH = os.path.join("control", "full-watch.json")
SHEET_NAME = "full-watch-sheet.png"

#: One frame per second (N-18), laid out in this many columns.
FRAMES_PER_SECOND = 1.0
COLUMNS = 8
TILE_PX = 160
RENDER_TIMEOUT_S = 600

SHEET_MISSING = "FULL_WATCH_SHEET_MISSING"
SHEET_STALE = "FULL_WATCH_SHEET_STALE"        # bytes differ from the record
NOT_OPENED = "FULL_WATCH_NOT_OPENED"          # no opening in the record
NO_VIEWER = "FULL_WATCH_NO_VIEWER"
FRAMES_SHORT = "FULL_WATCH_FRAMES_SHORT"      # fewer than one per second
RENDER_FAILED = "FULL_WATCH_RENDER_FAILED"
RECORD_MISSING = "FULL_WATCH_RECORD_MISSING"
BAD_INPUT = "FULL_WATCH_BAD_INPUT"


class FullWatchError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def expected_frames(duration_s, every_s=FRAMES_PER_SECOND):
    """How many tiles one frame per second owes for this master."""
    duration = float(duration_s)
    if not duration > 0 or not every_s > 0:
        raise ValueError("duration_s and every_s must be positive")
    return max(1, int(math.ceil(duration / every_s)))


def _ffmpeg_argv(args, ffmpeg="ffmpeg"):
    try:
        return _LG.ffmpeg_argv(args, ffmpeg=ffmpeg)
    except _LG.LoadGovernorError:
        return [ffmpeg] + [str(a) for a in args]


def build_contact_sheet(master, out_path, *, ffmpeg="ffmpeg", ffprobe="ffprobe",
                        columns=COLUMNS, tile_px=TILE_PX):
    """One tiled picture: one frame per second of the WHOLE master.

    Returns the sheet's path, tile count and digest. Raises FullWatchError on
    an unreadable master or a failed render -- a sheet nobody made is never
    reported as made.
    """
    master_path = Path(master)
    if not master_path.is_file() or master_path.stat().st_size == 0:
        raise FullWatchError(BAD_INPUT, "no master at %s" % master_path)
    try:
        geo = probe(str(master_path), ffprobe=ffprobe)
    except Exception as exc:                    # noqa: BLE001 - reported
        raise FullWatchError(BAD_INPUT,
                             "master cannot be measured: %s" % exc) from exc
    duration = float(geo.get("duration_s") or 0.0)
    frames = expected_frames(duration)
    cols = max(1, int(columns))
    rows = int(math.ceil(frames / float(cols)))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = ("fps=%g,scale=%d:-1,tile=%dx%d"
          % (FRAMES_PER_SECOND, int(tile_px), cols, rows))
    argv = _ffmpeg_argv(["-y", "-v", "error", "-i", str(master_path),
                         "-vf", vf, "-frames:v", "1", str(out)], ffmpeg=ffmpeg)
    try:
        proc = _LG.run_ffmpeg(argv, "full-watch-sheet", capture_output=True,
                              text=True, timeout=RENDER_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        raise FullWatchError(RENDER_FAILED, str(exc)) from exc
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        raise FullWatchError(RENDER_FAILED,
                             "ffmpeg exited %s: %s"
                             % (proc.returncode, (proc.stderr or "")[-300:]))
    return {"path": str(out), "frames": frames, "duration_s": duration,
            "columns": cols, "rows": rows, "sha256": sha256_file(out)}


def record_watch(run_dir, sheet, *, viewer, opened_at=None):
    """Write ``control/full-watch.json``: the sheet that was opened and by whom.

    ``viewer`` is the identity that opened the sheet (17.6: a person, not the
    maker). A missing viewer is refused -- an unopened sheet is not a watch.
    """
    if not isinstance(viewer, dict) or not str(viewer.get("identity") or "").strip():
        raise FullWatchError(NO_VIEWER, "viewer.identity is required")
    root = Path(run_dir)
    record = {"schema_version": 1, "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
              "contact_sheet": os.path.relpath(sheet["path"], str(root)),
              "sha256": sheet["sha256"], "frames": int(sheet["frames"]),
              "duration_s": round(float(sheet["duration_s"]), 3),
              "frames_per_second": FRAMES_PER_SECOND,
              "opened": True,
              "opened_at": opened_at or datetime.now(timezone.utc).isoformat(
                  timespec="seconds"),
              "viewer": viewer}
    target = root / RECORD_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return record


def check_full_watch(run_dir):
    """(PASS|FAIL|UNAVAILABLE, detail) for the run's full-watch log.

    The sheet must exist at the recorded path, its bytes must match the
    recorded digest, the record must say it was opened by a named viewer, and
    it must carry at least one tile per second of the master.
    """
    root = Path(run_dir)
    try:
        record = json.loads((root / RECORD_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; the master was never watched"
                % RECORD_PATH)
    if not isinstance(record, dict):
        return (FAIL, "%s is not an object" % RECORD_PATH)
    rel = record.get("contact_sheet")
    if not rel:
        return (FAIL, "%s names no contact sheet" % RECORD_PATH)
    sheet = root / rel
    if not sheet.is_file() or sheet.stat().st_size == 0:
        return (FAIL, "%s (%s) is missing" % (SHEET_MISSING, rel))
    if str(record.get("sha256") or "") != sha256_file(sheet):
        return (FAIL, "%s: %s no longer matches the record (a new master owes "
                      "a new look)" % (SHEET_STALE, rel))
    if record.get("opened") is not True:
        return (FAIL, "%s: the sheet was never opened" % NOT_OPENED)
    viewer = record.get("viewer") or {}
    if not isinstance(viewer, dict) or not str(viewer.get("identity") or "").strip():
        return (FAIL, "%s: no viewer identity recorded" % NO_VIEWER)
    duration = float(record.get("duration_s") or 0.0)
    if duration > 0 and int(record.get("frames") or 0) < expected_frames(duration):
        return (FAIL, "%s: %s tiles for %.1f s (one per second required)"
                % (FRAMES_SHORT, record.get("frames"), duration))
    return (PASS, "%s: %s tiles over %.1f s, opened by %s"
            % (rel, record.get("frames"), duration, viewer["identity"]))


def _selfcheck():
    """One runnable check: the tile maths and the fail-closed paths."""
    assert expected_frames(0.2) == 1
    assert expected_frames(10.0) == 10
    assert expected_frames(10.01) == 11
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        verdict, detail = check_full_watch(td)
        assert verdict == FAIL and "never watched" in detail, detail
        os.makedirs(os.path.join(td, "control"))
        with open(os.path.join(td, RECORD_PATH), "w", encoding="utf-8") as fh:
            json.dump({"contact_sheet": SHEET_NAME, "opened": True,
                       "viewer": {"identity": "reviewer"}, "frames": 5,
                       "duration_s": 5.0}, fh)
        verdict, detail = check_full_watch(td)
        assert verdict == FAIL and SHEET_MISSING in detail, detail
    return "ok"


def _cli(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "check":
        verdict, detail = check_full_watch(args[1])
        print(json.dumps({"check": TOOL_NAME, "verdict": verdict,
                          "detail": detail}))
        return 0 if verdict == PASS else 5
    print(json.dumps({"outcome": "error", "reason_code": BAD_INPUT,
                      "detail": "usage: full_watch.py check <run_dir>"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
