"""DEL-08: ONE cover image (thumbnail) per delivered ad.

A delivery folder ships one strong still of the character with the ad's
title on it -- the picture a platform, a client or an editor actually
grabs. It is built at the END of the run out of assets the run already
made, so it costs nothing and invents nothing:

  * the FRAME comes from the run's own frame selection --
    ``$RUN/storyboard/stills.json``, the one approved still per shot that
    the storyboard approval package already sent to the client, picked in
    shot-list order by :func:`select_frame`;
  * the TITLE is the approved script's title (``$RUN/creative/script.json``,
    the same file ``script_approval.stage`` reads), falling back to the
    brief's title -- never an invented one;
  * the storyboard gate must be open (``approval_runner.gate_open``): an
    unapproved still is not a frame selection and may not be shipped;
  * the render is one ffmpeg pass through ``load_governor.run_ffmpeg``,
    the heavy-local-job governor every other local ffmpeg in this skill
    uses -- scale/crop to the cover size, one title-safe band, the title
    on it.

Exactly ONE image lands in the delivery folder (``<safe ad name>-cover.png``,
named with the reuse of ``song_files.safe_name``). ``write_cover_docs`` merges
it into ``delivery-receipt.json`` and ``README.md`` the way the song files do
(markers, never clobbering other content) and ``check_cover_image`` is the
delivery QC gate (PASS / FAIL / UNAVAILABLE, fail closed: a receipt, a hash
and MEASURED pixel dimensions, never a claim).

Default size 1280x720 -- the 16:9 thumbnail every platform accepts.

The title travels as ``drawtext=textfile=...:expansion=none``, so a title is
data: no filter-graph escaping and no ``%{...}`` expansion can ever touch it.
``build_cover_argv`` returns DATA; nothing here spawns a process until the
caller asks, so a test never spends a frame.

stdlib + ffmpeg only, no network, no spend, no operator path.
Run: python3 -m unittest delivery_variants.test_cover_image_dl08
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import load_governor as _LG                       # heavy local ffmpeg governor
# Absolute (not relative) so this file also runs as its own CLI, the way the
# runbook documents: python3 .../delivery_variants/cover_image.py <cmd>
from delivery_variants.manifests import sha256_file
from delivery_variants.song_files import (
    README_NAME,
    RECEIPT_NAME,
    safe_name,
)

TOOL_NAME = "cover_image"
TOOL_VERSION = "1.0.0"
CHECK_NAME = "cover_image"

#: DEL-08 "sensible default dimensions": the 16:9 thumbnail.
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 720
MIN_EDGE, MAX_EDGE = 16, 7680

BAND_COLOUR = "black@0.55"     # the title band over the still
TEXT_COLOUR = "#ffffff"
BAND_FRACTION = 0.16           # band height as a fraction of the cover
FONT_FRACTION = 0.07           # base font size as a fraction of the height
TITLE_SHRINK = 1.8             # fontsize <= TITLE_SHRINK * width / len(title)

_BEGIN, _END = "<!-- cover-image:begin -->", "<!-- cover-image:end -->"

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"

# Refusal codes (fail closed, never a silent pass).
NO_FRAME = "COVER_NO_FRAME"                       # no still on disk
NO_TITLE = "COVER_NO_TITLE"                       # no title anywhere
NOT_APPROVED = "COVER_STORYBOARD_NOT_APPROVED"    # gate not open
BAD_INPUT = "COVER_BAD_INPUT"
FONT_UNAVAILABLE = "COVER_FONT_UNAVAILABLE"
FONT_MISSING = "COVER_FONT_MISSING"
RENDER_FAILED = "COVER_RENDER_FAILED"
NO_DRAWTEXT = "COVER_DRAWTEXT_UNAVAILABLE"

#: The run files this unit reads (all inside ``$RUN``, none outside it).
STILLS = os.path.join("storyboard", "stills.json")
SHOT_LIST = os.path.join("storyboard", "shot-list.json")
CONTRACTS = os.path.join("storyboard", "contracts.json")
BRIEF = "brief.json"

#: System fonts, first hit wins. No operator/build path ever appears here
#: (scripts/qc-operator-path-leak.sh scans non-test core files).
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class CoverImageError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def safe_component(ad_name):
    """The delivery file stem -- same reuse as the song files (DEL-08)."""
    return safe_name(ad_name)


def cover_file_name(ad_name):
    """The ONE image file this unit writes into the delivery folder."""
    return "%s-cover.png" % safe_component(ad_name)


# --------------------------------------------------------------- selection ---
def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def title_of(run_dir):
    """The ad's title: the approved script's, else the brief's.

    The script path constant is imported from ``script_approval.stage`` --
    the same file that sends the script to the client, so a cover can never
    carry a title the client never approved. Raises COVER_NO_TITLE when
    neither file carries a non-empty title (fail closed: no invented words).
    """
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    from script_approval.stage import SCRIPT   # noqa: PLC0415

    for path, key in ((os.path.join(run_dir, SCRIPT), "title"),
                      (os.path.join(run_dir, BRIEF), "title")):
        doc = _read_json(path)
        if isinstance(doc, dict):
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise CoverImageError(NO_TITLE,
                          "neither %s nor %s carries a non-empty title"
                          % (SCRIPT, BRIEF))


def load_frames(run_dir):
    """The run's frame selection: (shots, contracts, stills), resolved.

    Same three storyboard files and the same relative-path rule the
    storyboard approval runner uses; an unresolved path is dropped from
    ``stills`` rather than shipped as a broken frame.
    """
    base = os.path.join(run_dir, "storyboard")
    env = _read_json(os.path.join(base, os.path.basename(SHOT_LIST)), [])
    shots = env.get("shots") if isinstance(env, dict) else env
    contracts = _read_json(os.path.join(base, os.path.basename(CONTRACTS)), {})
    raw = _read_json(os.path.join(base, os.path.basename(STILLS)), {})
    if not isinstance(raw, dict):
        raw = {}
    stills = {}
    for shot_id, path in raw.items():
        if not isinstance(path, str) or not path:
            continue
        full = path if os.path.isabs(path) else os.path.join(run_dir, path)
        stills[shot_id] = full
    if not isinstance(shots, list):
        shots = []
    if not isinstance(contracts, dict):
        contracts = {}
    return shots, contracts, stills


def _rank(shot, contract):
    """One integer: bigger wins. Face first, character second, then time.

    2 = the contract shows the character's face (visible_emotion),
    1 = the shot carries the character (character_ids non-empty),
    0 = an ordinary shot.
    """
    if isinstance(contract, dict) and str(contract.get("visible_emotion") or "").strip():
        return 2
    ids = shot.get("character_ids")
    if isinstance(ids, (list, tuple)) and ids:
        return 1
    return 0


def select_frame(stills, shots=None, contracts=None):
    """The ONE frame to build the cover from -- the run's frame selection.

    Walks the shot list in song order (``song_start`` then ``shot_id``),
    keeps only shots whose still is a non-empty file on disk, and returns
    the highest-ranked one: face visible > character present > earliest.
    Ties never depend on dict order.

    Raises ``COVER_NO_FRAME`` when nothing on disk qualifies.
    """
    if not isinstance(stills, dict) or not stills:
        raise CoverImageError(NO_FRAME, "the run has no storyboard stills")
    contracts = contracts if isinstance(contracts, dict) else {}
    order = [s for s in (shots or []) if isinstance(s, dict) and s.get("shot_id")]
    listed = {str(s.get("shot_id")) for s in order}
    # a still the shot list never named is still a frame: try it last
    order += [{"shot_id": sid} for sid in sorted(stills) if sid not in listed]
    order = sorted(order, key=lambda s: (s.get("song_start")
                                         if isinstance(s.get("song_start"), (int, float))
                                         else float("inf"), str(s.get("shot_id"))))

    best = None
    for shot in order:
        sid = shot.get("shot_id")
        path = stills.get(sid)
        if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
            continue
        rank = _rank(shot, contracts.get(sid))
        if best is None or rank > best[0]:
            best = (rank, {"shot_id": sid, "path": path,
                           "why": "face-visible" if rank == 2
                                  else ("character" if rank == 1 else "first-shot")})
    if best is None:
        raise CoverImageError(NO_FRAME,
                              "none of the %d selected frame(s) is a non-empty "
                              "file on disk" % len(stills))
    return best[1]


def require_storyboard_approved(run_dir):
    """The frame selection is only a frame selection once it is approved."""
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    from storyboard_director import approval_runner   # noqa: PLC0415

    if not approval_runner.gate_open(run_dir):
        raise CoverImageError(NOT_APPROVED,
                              "storyboard gate is not open; the stills were "
                              "never approved (approval_runner.gate_open)")


# ------------------------------------------------------------------ render ---
def has_filter(name, ffmpeg="ffmpeg"):
    """Measured: does THIS ffmpeg build ship the filter? Never assumed.

    A cover without ``drawtext`` cannot carry its title, and a title that is
    not on the cover is not a cover -- so the caller must know before it
    spends a render. Timeout / missing binary / unreadable output is False
    (fail closed), never a guess.
    """
    if not re.fullmatch(r"[a-zA-Z0-9_]+", str(name or "")):
        return False
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    text = (proc.stdout or "") + (proc.stderr or "")
    return bool(re.search(r"\s%s\b" % re.escape(name), text))


def resolve_font(explicit=None):
    """A font file to draw the title with; fail closed when none exists."""
    if explicit:
        if not str(explicit).strip() or not os.path.isfile(str(explicit)):
            raise CoverImageError(FONT_MISSING, "font file not found: %r" % explicit)
        return str(explicit)
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise CoverImageError(FONT_UNAVAILABLE,
                          "no system font found (%s); pass --font" % ", ".join(FONT_CANDIDATES))


def _edge(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise CoverImageError(BAD_INPUT, "%s must be an int, got %r" % (label, value))
    if not (MIN_EDGE <= value <= MAX_EDGE):
        raise CoverImageError(BAD_INPUT, "%s must be between %d and %d px, got %d"
                              % (label, MIN_EDGE, MAX_EDGE, value))
    return value


def _clean_title(title):
    if not isinstance(title, str) or not title.strip():
        raise CoverImageError(NO_TITLE, "the title is empty")
    text = title.strip()
    if any(ord(c) < 32 for c in text):
        raise CoverImageError(BAD_INPUT, "the title carries control characters")
    return text


def cover_geometry(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, title=""):
    """Band + font geometry as data (reuses delivery_variants.variants).

    The title sits inside the SAME title-safe inset the aspect-variant
    engine uses, so a cover and its video variant agree on safe copy.
    """
    from delivery_variants import variants   # noqa: PLC0415

    w, h = _edge(width, "width"), _edge(height, "height")
    safe = variants.safe_area(w, h, variants.SAFE_TITLE_INSET)
    band_h = max(int(h * BAND_FRACTION), 32)
    band_y = h - band_h
    fontsize = max(14, int(h * FONT_FRACTION))
    chars = len(_clean_title(title))
    if chars:
        fontsize = max(14, min(fontsize, int(TITLE_SHRINK * w / chars)))
    text_x = safe["x"]
    text_y = band_y + max(0, (band_h - int(fontsize * 1.25)) // 2)
    return {"width": w, "height": h,
            "band": {"x": 0, "y": band_y, "w": w, "h": band_h},
            "text_x": text_x, "text_y": text_y, "fontsize": fontsize,
            "title_safe": safe}


def build_cover_argv(frame, out, title_file, width=DEFAULT_WIDTH,
                     height=DEFAULT_HEIGHT, fontfile=None, ffmpeg="ffmpeg"):
    """One ffmpeg argv: still -> cover size -> title band -> single PNG.

    DATA ONLY: no process is spawned here. The title is passed as
    ``textfile=`` with ``expansion=none`` so it is never parsed as filter
    syntax (a title containing ``:``, ``,`` or ``%{}`` stays literal text).
    """
    if not isinstance(frame, str) or not frame:
        raise CoverImageError(BAD_INPUT, "frame path required")
    if not isinstance(out, str) or not out:
        raise CoverImageError(BAD_INPUT, "output path required")
    if not isinstance(title_file, str) or not title_file:
        raise CoverImageError(BAD_INPUT, "title file required")
    geom = cover_geometry(width, height, _read_title_file(title_file))
    font = resolve_font(fontfile)
    w, h, band, fs = geom["width"], geom["height"], geom["band"], geom["fontsize"]
    chain = [
        "scale=%d:%d:force_original_aspect_ratio=increase" % (w, h),
        "crop=%d:%d" % (w, h),
        "drawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=fill"
        % (band["x"], band["y"], band["w"], band["h"], BAND_COLOUR),
        ("drawtext=fontfile=%s:textfile=%s:expansion=none:fontcolor=%s"
         ":fontsize=%d:x=%d:y=%d" % (font, title_file, TEXT_COLOUR, fs,
                                     geom["text_x"], geom["text_y"])),
    ]
    return [ffmpeg, "-y", "-v", "error", "-i", frame, "-vf", ",".join(chain),
            "-frames:v", "1", out]


def _read_title_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CoverImageError(BAD_INPUT, "cannot read the title file: %s" % exc)


def png_size(path):
    """Measured (width, height) from the PNG's own IHDR. Raises when unreadable."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError as exc:
        raise CoverImageError(BAD_INPUT, "cannot read %s: %s" % (path, exc))
    if len(head) < 24 or not head.startswith(_PNG_SIG) or head[12:16] != b"IHDR":
        raise CoverImageError(BAD_INPUT, "%s is not a readable PNG" % path)
    return struct.unpack(">II", head[16:24])


# ------------------------------------------------------------------- build ---
def build_cover(run_dir, delivery_dir, ad_name, *, width=DEFAULT_WIDTH,
                height=DEFAULT_HEIGHT, fontfile=None, runner=None,
                ffmpeg="ffmpeg"):
    """Build the ONE cover image into the delivery folder, end of run.

    Reads the run's frame selection and title, renders through
    ``load_governor.run_ffmpeg`` (the shared heavy-local-job governor) and
    returns the receipt row: file, measured pixels, sha256 and the source
    frame. ``runner`` overrides the process launcher (tests); the argv is
    still built by :func:`build_cover_argv`.
    """
    import tempfile   # noqa: PLC0415

    require_storyboard_approved(run_dir)
    if runner is None and not has_filter("drawtext", ffmpeg):
        raise CoverImageError(NO_DRAWTEXT,
                              "this ffmpeg build has no drawtext filter, so "
                              "the title cannot be put on the cover; install "
                              "ffmpeg with freetype support")
    shots, contracts, stills = load_frames(run_dir)
    picked = select_frame(stills, shots, contracts)
    title = _clean_title(title_of(run_dir))

    out_dir = Path(delivery_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / cover_file_name(ad_name)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(title)
        title_file = fh.name
    try:
        argv = build_cover_argv(picked["path"], str(out), title_file,
                                width=width, height=height, fontfile=fontfile,
                                ffmpeg=ffmpeg)
        runner_fn = runner or _LG.run_ffmpeg
        try:
            proc = runner_fn(argv, "cover-image")
            rc = getattr(proc, "returncode", 0)
        except OSError as exc:
            raise CoverImageError(RENDER_FAILED, "ffmpeg could not run: %s" % exc)
        if rc:
            raise CoverImageError(RENDER_FAILED, "ffmpeg exited %s" % rc)
    finally:
        try:
            os.unlink(title_file)
        except OSError:
            pass

    if not out.is_file() or out.stat().st_size <= 0:
        raise CoverImageError(RENDER_FAILED, "%s was not written" % out.name)
    w, h = png_size(out)
    geom = cover_geometry(width, height, title)
    if (w, h) != (geom["width"], geom["height"]):
        raise CoverImageError(RENDER_FAILED,
                              "%s came out %dx%d, asked for %dx%d"
                              % (out.name, w, h, geom["width"], geom["height"]))
    return {"check": CHECK_NAME, "file": out.name, "title": title,
            "width": w, "height": h, "fontsize": geom["fontsize"],
            "shot_id": picked["shot_id"],
            "source_frame": os.path.basename(picked["path"]),
            "frame_selection": picked["why"],
            "sha256": sha256_file(out),
            "source_stills": STILLS, "source_title": "creative/script.json"}


def write_cover_docs(delivery_dir, row):
    """List the cover in delivery-receipt.json and README.md (merge, never
    clobber other receipt/README content; the block is written once)."""
    if not isinstance(row, dict) or not row.get("file"):
        raise CoverImageError(BAD_INPUT, "a cover receipt row with a file is required")
    d = Path(delivery_dir)
    rp = d / RECEIPT_NAME
    receipt = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    if not isinstance(receipt, dict):
        raise CoverImageError(BAD_INPUT, "%s is not an object" % RECEIPT_NAME)
    receipt["cover_image"] = row
    rp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")
    lines = [_BEGIN, "## The cover image (thumbnail)", "",
             "- `%s` - %d x %d, title \"%s\", from shot `%s` (%s)."
             % (row["file"], row.get("width", 0), row.get("height", 0),
                row.get("title", ""), row.get("shot_id", "?"),
                row.get("frame_selection", "frame selection")),
             _END]
    block = "\n".join(lines) + "\n"
    rd = d / README_NAME
    text = rd.read_text(encoding="utf-8") if rd.is_file() else "# Delivery\n\n"
    if _BEGIN in text and _END in text:
        text = re.sub(re.escape(_BEGIN) + r".*?" + re.escape(_END) + r"\n?",
                      lambda _m: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    rd.write_text(text, encoding="utf-8")


def check_cover_image(delivery_dir, ad_name, width=DEFAULT_WIDTH,
                      height=DEFAULT_HEIGHT):
    """QC: (PASS|FAIL|UNAVAILABLE, detail). Fail closed on every gap.

    A PASS needs the exact expected file name, a receipt row, a README
    listing, a sha256 that still matches the bytes, and MEASURED pixel
    dimensions from the PNG's own IHDR -- never the row's own claim.
    """
    d = Path(delivery_dir)
    name = cover_file_name(ad_name)
    try:
        receipt = json.loads((d / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot list the cover" % RECEIPT_NAME)
    row = receipt.get("cover_image")
    if not isinstance(row, dict):
        return (FAIL, "%s carries no cover_image row" % RECEIPT_NAME)
    if row.get("file") != name:
        return (FAIL, "receipt lists %r, expected %r" % (row.get("file"), name))
    path = d / name
    if not path.is_file() or path.stat().st_size <= 0:
        return (FAIL, "delivery missing the cover image %s" % name)
    if row.get("sha256") != sha256_file(path):
        return (FAIL, "%s does not match its receipt sha256" % name)
    if not isinstance(row.get("title"), str) or not row["title"].strip():
        return (FAIL, "the receipt carries no title")
    readme = (d / README_NAME).read_text(encoding="utf-8") \
        if (d / README_NAME).is_file() else ""
    if name not in readme:
        return (FAIL, "%s not listed in %s" % (name, README_NAME))
    try:
        w, h = png_size(path)
    except CoverImageError as exc:
        return (UNAVAILABLE, str(exc))
    if (w, h) != (_edge(width, "width"), _edge(height, "height")):
        return (FAIL, "%s measures %dx%d, expected %dx%d"
                % (name, w, h, width, height))
    return (PASS, "%s: %dx%d, sha256 and README listing verified"
            % (name, w, h))


def _cli(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if a[:1] == ["build"]:
        p = argparse.ArgumentParser(prog="cover_image",
                                    description="DEL-08: the one cover image")
        p.add_argument("--run", required=True)
        p.add_argument("--delivery", required=True)
        p.add_argument("--ad-name", required=True)
        p.add_argument("--width", type=int, default=DEFAULT_WIDTH)
        p.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
        p.add_argument("--font", default=None)
        p.add_argument("--ffmpeg", default="ffmpeg",
                       help="the ffmpeg binary to render with (must ship the "
                            "drawtext filter)")
        ns = p.parse_args(a[1:])
        try:
            row = build_cover(ns.run, ns.delivery, ns.ad_name,
                              width=ns.width, height=ns.height,
                              fontfile=ns.font, ffmpeg=ns.ffmpeg)
            write_cover_docs(ns.delivery, row)
        except CoverImageError as exc:
            print(json.dumps({"outcome": "error", "reason_code": exc.code,
                              "detail": exc.message}))
            return 1
        print(json.dumps({"outcome": "ok", **row}))
        return 0
    if a[:1] == ["check"] and len(a) == 3:
        verdict, detail = check_cover_image(a[1], a[2])
        print(json.dumps({"check": CHECK_NAME, "verdict": verdict, "detail": detail}))
        return 0 if verdict == PASS else 5
    print("usage: cover_image.py build --run <run> --delivery <dir> "
          "--ad-name <name> [--width N] [--height N] [--font FILE] "
          "[--ffmpeg BIN]\n"
          "       cover_image.py check <delivery_dir> <ad_name>")
    return 1



def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: stage this item's canonical files.

    The one naming scheme lives in delivery_package.contract (``NN - Label.ext``
    per item number). This adapter stages the item's files under those exact
    canonical names via contract.produce_item, so the packaging call copies
    them verbatim and the folder gate opens them unchanged. Signature is the
    packaging contract: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package.contract import produce_item
    staging = Path(run_dir) / "_package" / item.key
    return produce_item(item, staging)


if __name__ == "__main__":
    raise SystemExit(_cli())
