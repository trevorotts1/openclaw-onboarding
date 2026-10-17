"""PowerPoint presentation adapter for motion components (MG-035).

WHAT THIS MODULE IS, PLAINLY

The existing PowerPoint assembly path (assemble_pptx in the
presentation crew's build_deck.py) embeds PICTURES ONLY: it places a
full-bleed image per slide and has no video mechanism at all.
Integration map entry P04 is corrected on exactly this point:
add_movie does not exist in that codebase, and the governed
add_motion_media function that will embed motion media through
python-pptx inside build_deck.py is MG-036's deliverable, not this
one. This adapter therefore builds the embed at the OOXML package
level, inside this module, without editing build_deck.py.

The package structure written here is the structure python-pptx's
add_movie writes (verified byte-for-byte at the element level
against python-pptx 1.0.2, the library the existing path uses): the
MP4 as a media part under ppt/media/, TWO relationships to it from
the video slide (the officeDocument video relationship consumed by
a:videoFile, and the Microsoft media relationship consumed by the
p14:media extension), the poster PNG as the slide picture's blip
(so the slide shows the readable poster state whenever the video is
not playing, including in PDF export), and a media timing node
whose start condition carries the declared playback start
(indefinite for on_click, 0 for automatic). One deviation from the
library's output: the MP4 part is declared video/mp4 in
[Content_Types].xml where python-pptx writes video/unknown.

When MG-036 lands, add_motion_media replaces this module's producer
mechanism: the same parts and relationships, created by python-pptx
inside the deck pipeline, with the poster and the static fallback
slide kept as separate governed outputs exactly as here (P04: the
poster and PDF fallback stay separate). Decks produced before and
after that replacement carry the same package shape.

PLATFORM TRUTH: this module proves embed integrity structurally
(verify_deck unzips a deck anywhere and shows the media part is the
packaged bytes). Playback inside Microsoft PowerPoint is UNVERIFIED
on every platform from this Linux build box; nothing here simulates
or claims it.

The deck shape mirrors assemble_pptx: the default Office template
furniture (the trimmed copies under scripts/pptx_template/ are the
parts the existing path's Presentation() emits, reduced to the one
Blank layout the assembly uses), 10 x 5.625 inch slides, a full-bleed
picture per slide. Slide 1 is the video slide; slide 2 is the static
fallback slide carrying the poster state for PDF export and
nonplaying environments.

CLI:
    python3 scripts/powerpoint_adapter.py build --mp4 M --poster P \
        --fallback F --playback-json FILE --out DECK.pptx \
        [--title T]
    python3 scripts/powerpoint_adapter.py verify --deck DECK.pptx \
        [--expect-mp4-sha256 H] [--expect-fallback-sha256 H]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "pptx_template"

SLIDE_CX = 9144000   # 10 inches in EMU, build_deck SLIDE_WIDTH_IN
SLIDE_CY = 5143500   # 5.625 inches in EMU, build_deck SLIDE_HEIGHT_IN

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
}

EXIT_BY_CATEGORY = {
    "MG_INPUT_MISSING": 3,
    "MG_DELIVERY_FAILED": 7,
    "MG_HASH_MISMATCH": 9,
}


class AdapterError(Exception):
    """A named adapter refusal with a Section 16.9 category."""

    def __init__(self, code: str, category: str, message: str,
                 details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.category = category
        self.message = message
        self.details = details or {}


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _xml_decl() -> str:
    return "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"


def _rels_xml(rels: list[tuple[str, str, str]]) -> str:
    body = "".join(
        '<Relationship Id="%s" Type="%s" Target="%s"/>' % (i, t, g)
        for i, t, g in rels)
    return (_xml_decl()
            + '<Relationships xmlns="%s">%s</Relationships>'
            % (NS["rel"], body))


RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RT_MEDIA = "http://schemas.microsoft.com/office/2007/relationships/media"

# ---------------------------------------------------------------------------
# Slide XML
# ---------------------------------------------------------------------------

def _sp_tree_open() -> str:
    return (
        '<p:cSld><p:spTree>'
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
        '</p:nvGrpSpPr><p:grpSpPr/>')


def _full_bleed_spPr() -> str:
    return (
        '<p:spPr><a:xfrm><a:off x="0" y="0"/>'
        '<a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        % (SLIDE_CX, SLIDE_CY))


def video_slide_xml(mp4_name: str, playback: dict) -> str:
    """The video slide, element-identical to python-pptx add_movie
    output, with the media node's start condition and repeat set
    from the package's declared playback metadata."""
    start = playback.get("start", "on_click")
    delay = "indefinite" if start == "on_click" else "0"
    repeat = (' repeatCount="indefinite"'
              if playback.get("repeat") == "loop" else "")
    return (
        _xml_decl()
        + '<p:sld xmlns:a="%s" xmlns:p="%s" xmlns:r="%s">'
        % (NS["a"], NS["p"], NS["r"])
        + _sp_tree_open()
        + '<p:pic><p:nvPicPr>'
        + '<p:cNvPr id="2" name="%s">'
          '<a:hlinkClick r:id="" action="ppaction://media"/></p:cNvPr>'
        % mp4_name
        + '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        + '<p:nvPr><a:videoFile r:link="rId3"/>'
        + '<p:extLst><p:ext uri="{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9230}">'
        + '<p14:media xmlns:p14="%s" r:embed="rId2"/></p:ext></p:extLst>'
        % NS["p14"]
        + '</p:nvPr></p:nvPicPr>'
        + '<p:blipFill><a:blip r:embed="rId4"/>'
          '<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        + _full_bleed_spPr()
        + '</p:pic></p:spTree></p:cSld>'
        + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
        + '<p:timing><p:tnLst><p:par>'
          '<p:cTn id="1" dur="indefinite" restart="never" '
          'nodeType="tmRoot"><p:childTnLst>'
          '<p:video><p:cMediaNode vol="80000">'
          '<p:cTn id="2" fill="hold" display="0"%s>'
          '<p:stCondLst><p:cond delay="%s"/></p:stCondLst></p:cTn>'
          '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl>'
          '</p:cMediaNode></p:video>'
          '</p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>'
        % (repeat, delay)
        + '</p:sld>')


def picture_slide_xml(name: str, descr: str) -> str:
    """A full-bleed picture slide, the shape assemble_pptx produces
    for every slide it builds."""
    return (
        _xml_decl()
        + '<p:sld xmlns:a="%s" xmlns:p="%s" xmlns:r="%s">'
        % (NS["a"], NS["p"], NS["r"])
        + _sp_tree_open()
        + '<p:pic><p:nvPicPr>'
        + '<p:cNvPr id="2" name="%s" descr="%s"/>' % (name, descr)
        + '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        + '<p:nvPr/></p:nvPicPr>'
        + '<p:blipFill><a:blip r:embed="rId2"/>'
          '<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        + _full_bleed_spPr()
        + '</p:pic></p:spTree></p:cSld>'
        + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
        + '</p:sld>')


def presentation_xml() -> str:
    levels = []
    for i in range(9):
        mar = i * 457200
        levels.append(
            '<a:lvl%dpPr marL="%d" algn="l" defTabSz="457200" rtl="0" '
            'eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
            '<a:defRPr sz="1800" kern="1200">'
            '<a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
            '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/>'
            '<a:cs typeface="+mn-cs"/></a:defRPr></a:lvl%dpPr>'
            % (i + 1, mar, i + 1))
    return (
        _xml_decl()
        + '<p:presentation xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" '
          'saveSubsetFonts="1" autoCompressPictures="0">'
        % (NS["a"], NS["r"], NS["p"])
        + '<p:sldMasterIdLst>'
          '<p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        + '<p:sldIdLst>'
          '<p:sldId id="256" r:id="rId2"/>'
          '<p:sldId id="257" r:id="rId3"/></p:sldIdLst>'
        + '<p:sldSz cx="%d" cy="%d" type="screen16x9"/>'
        % (SLIDE_CX, SLIDE_CY)
        + '<p:notesSz cx="6858000" cy="9144000"/>'
        + '<p:defaultTextStyle><a:defPPr>'
          '<a:defRPr lang="en-US"/></a:defPPr>'
        + "".join(levels)
        + '</p:defaultTextStyle></p:presentation>')


def content_types_xml() -> str:
    return (
        _xml_decl()
        + '<Types xmlns="%s">' % NS["ct"]
        + '<Default Extension="rels" ContentType="application/vnd.'
          'openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + '<Default Extension="png" ContentType="image/png"/>'
        + '<Default Extension="mp4" ContentType="video/mp4"/>'
        + '<Override PartName="/docProps/app.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.'
          'extended-properties+xml"/>'
        + '<Override PartName="/docProps/core.xml" ContentType="'
          'application/vnd.openxmlformats-package.core-properties+xml"/>'
        + '<Override PartName="/ppt/presProps.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.'
          'presentationml.presProps+xml"/>'
        + '<Override PartName="/ppt/presentation.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.'
          'presentationml.presentation.main+xml"/>'
        + '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.'
          'presentationml.slideLayout+xml"/>'
        + '<Override PartName="/ppt/slideMasters/slideMaster1.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.'
          'presentationml.slideMaster+xml"/>'
        + '<Override PartName="/ppt/slides/slide1.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.'
          'presentationml.slide+xml"/>'
        + '<Override PartName="/ppt/slides/slide2.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.'
          'presentationml.slide+xml"/>'
        + '<Override PartName="/ppt/theme/theme1.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.theme+xml"/>'
        + '<Override PartName="/ppt/viewProps.xml" ContentType="'
          'application/vnd.openxmlformats-officedocument.'
          'presentationml.viewProps+xml"/>'
        + '</Types>')


def core_props_xml(title: str, created: str) -> str:
    return (
        _xml_decl()
        + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.'
          'org/package/2006/metadata/core-properties" '
          'xmlns:dc="http://purl.org/dc/elements/1.1/" '
          'xmlns:dcterms="http://purl.org/dc/terms/" '
          'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        + '<dc:title>%s</dc:title>' % title
        + '<dc:creator>Skill 72 MG-035 powerpoint adapter</dc:creator>'
        + '<cp:lastModifiedBy>Skill 72 MG-035 powerpoint adapter'
          '</cp:lastModifiedBy>'
        + '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
        % created
        + '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
        % created
        + '</cp:coreProperties>')


def app_props_xml() -> str:
    return (
        _xml_decl()
        + '<Properties xmlns="http://schemas.openxmlformats.org/office'
          'Document/2006/extended-properties">'
        + '<Application>Skill 72 presentation adapter (MG-035)'
          '</Application>'
        + '<PresentationFormat>On-screen Show (16:9)</PresentationFormat>'
        + '<Slides>2</Slides>'
        + '<Company>BlackCEO</Company>'
        + '</Properties>')


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_deck(mp4_path: Path, poster_path: Path, fallback_path: Path,
               playback: dict, out_path: Path,
               title: str = "Motion component") -> dict:
    """Build the two-slide deck: video slide + static fallback slide.

    Writes atomically (sibling temp file, then os.replace), the same
    save discipline as assemble_pptx. Returns the deck record.
    """
    mp4_path, poster_path, fallback_path = (
        Path(mp4_path), Path(poster_path), Path(fallback_path))
    for label, path in (("mp4", mp4_path), ("poster", poster_path),
                        ("fallback", fallback_path)):
        if not path.exists():
            raise AdapterError(
                "PPTX_INPUT_MISSING", "MG_INPUT_MISSING",
                "the %s input %s does not exist" % (label, path))
    for name in ("slideMaster1.xml", "slideLayout1.xml", "theme1.xml",
                 "presProps.xml", "viewProps.xml"):
        if not (TEMPLATE_DIR / name).exists():
            raise AdapterError(
                "PPTX_TEMPLATE_MISSING", "MG_INPUT_MISSING",
                "adapter template part %s is missing from %s"
                % (name, TEMPLATE_DIR))
    mp4_bytes = mp4_path.read_bytes()
    poster_bytes = poster_path.read_bytes()
    fallback_bytes = fallback_path.read_bytes()
    mp4_name = mp4_path.name
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts: list[tuple[str, bytes, int]] = []

    def add(name: str, data, compress: int = zipfile.ZIP_DEFLATED):
        if isinstance(data, str):
            data = data.encode("utf-8")
        parts.append((name, data, compress))

    add("[Content_Types].xml", content_types_xml())
    add("_rels/.rels", _rels_xml([
        ("rId1", RT + "/officeDocument", "ppt/presentation.xml"),
        ("rId2", "http://schemas.openxmlformats.org/package/2006/"
                 "relationships/metadata/core-properties",
         "docProps/core.xml"),
        ("rId3", RT + "/extended-properties", "docProps/app.xml"),
    ]))
    add("docProps/core.xml", core_props_xml(title, created))
    add("docProps/app.xml", app_props_xml())
    add("ppt/presentation.xml", presentation_xml())
    add("ppt/_rels/presentation.xml.rels", _rels_xml([
        ("rId1", RT + "/slideMaster", "slideMasters/slideMaster1.xml"),
        ("rId2", RT + "/slide", "slides/slide1.xml"),
        ("rId3", RT + "/slide", "slides/slide2.xml"),
        ("rId4", RT + "/presProps", "presProps.xml"),
        ("rId5", RT + "/viewProps", "viewProps.xml"),
    ]))
    add("ppt/presProps.xml",
        (TEMPLATE_DIR / "presProps.xml").read_bytes())
    add("ppt/viewProps.xml",
        (TEMPLATE_DIR / "viewProps.xml").read_bytes())
    add("ppt/slideMasters/slideMaster1.xml",
        (TEMPLATE_DIR / "slideMaster1.xml").read_bytes())
    add("ppt/slideMasters/_rels/slideMaster1.xml.rels", _rels_xml([
        ("rId1", RT + "/slideLayout", "../slideLayouts/slideLayout1.xml"),
        ("rId2", RT + "/theme", "../theme/theme1.xml"),
    ]))
    add("ppt/slideLayouts/slideLayout1.xml",
        (TEMPLATE_DIR / "slideLayout1.xml").read_bytes())
    add("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _rels_xml([
        ("rId1", RT + "/slideMaster", "../slideMasters/slideMaster1.xml"),
    ]))
    add("ppt/theme/theme1.xml",
        (TEMPLATE_DIR / "theme1.xml").read_bytes())
    add("ppt/slides/slide1.xml", video_slide_xml(mp4_name, playback))
    add("ppt/slides/_rels/slide1.xml.rels", _rels_xml([
        ("rId1", RT + "/slideLayout", "../slideLayouts/slideLayout1.xml"),
        ("rId2", RT_MEDIA, "../media/media1.mp4"),
        ("rId3", RT + "/video", "../media/media1.mp4"),
        ("rId4", RT + "/image", "../media/image1.png"),
    ]))
    add("ppt/slides/slide2.xml", picture_slide_xml(
        "Static fallback",
        "Static fallback slide: the poster's readable final state, "
        "for PDF export and nonplaying environments"))
    add("ppt/slides/_rels/slide2.xml.rels", _rels_xml([
        ("rId1", RT + "/slideLayout", "../slideLayouts/slideLayout1.xml"),
        ("rId2", RT + "/image", "../media/image2.png"),
    ]))
    add("ppt/media/media1.mp4", mp4_bytes, zipfile.ZIP_STORED)
    add("ppt/media/image1.png", poster_bytes, zipfile.ZIP_STORED)
    add("ppt/media/image2.png", fallback_bytes, zipfile.ZIP_STORED)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.parent / (".%s.%d.tmp" % (out_path.name, os.getpid()))
    with zipfile.ZipFile(tmp_path, "w") as zf:
        for name, data, compress in parts:
            zf.writestr(name, data, compress_type=compress)
    os.replace(tmp_path, out_path)
    data = out_path.read_bytes()
    return {
        "path": str(out_path),
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
        "slides": 2,
        "slide_size_emu": [SLIDE_CX, SLIDE_CY],
        "media_part": "ppt/media/media1.mp4",
        "media_sha256": _sha256_bytes(mp4_bytes),
        "poster_part": "ppt/media/image1.png",
        "poster_sha256": _sha256_bytes(poster_bytes),
        "fallback_part": "ppt/media/image2.png",
        "fallback_sha256": _sha256_bytes(fallback_bytes),
        "playback_written": {
            "start": playback.get("start"),
            "repeat": playback.get("repeat"),
            "mechanism": (
                "a:videoFile link + p14:media embed + hlinkClick "
                "ppaction://media; media timing node start condition "
                + ("indefinite (click)" if playback.get("start")
                   == "on_click" else "0 (automatic)")
                + ("; repeatCount indefinite on the media node"
                   if playback.get("repeat") == "loop" else "")),
        },
    }


# ---------------------------------------------------------------------------
# Verify (the moved-deck proof)
# ---------------------------------------------------------------------------

def _parse_rels(zf: zipfile.ZipFile, name: str) -> dict:
    root = ET.fromstring(zf.read(name))
    rels = {}
    for rel in root.findall("rel:Relationship", NS):
        rels[rel.get("Id")] = {
            "type": rel.get("Type"),
            "target": rel.get("Target"),
            "target_mode": rel.get("TargetMode"),
        }
    return rels


def _resolve(base_dir: str, target: str) -> str:
    parts = []
    for piece in (base_dir + "/" + target).split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            parts.pop()
        else:
            parts.append(piece)
    return "/".join(parts)


def _probe_media(data: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".mp4",
                                     delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames",
             "-show_streams", "-show_format", "-of", "json", tmp_path],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise AdapterError(
                "PPTX_DECK_MEDIA_UNREADABLE", "MG_DELIVERY_FAILED",
                "ffprobe cannot parse the deck's media part: %s"
                % proc.stderr.strip()[-300:])
        doc = json.loads(proc.stdout)
        video = next((s for s in doc.get("streams", [])
                      if s.get("codec_type") == "video"), None)
        if video is None:
            raise AdapterError(
                "PPTX_DECK_MEDIA_UNREADABLE", "MG_DELIVERY_FAILED",
                "the deck's media part carries no video stream")
        frames = video.get("nb_read_frames") or video.get("nb_frames")
        return {
            "codec": video.get("codec_name"),
            "pixel_format": video.get("pix_fmt"),
            "width": video.get("width"),
            "height": video.get("height"),
            "frames": int(frames) if frames else None,
            "duration_seconds": float(doc["format"]["duration"]),
        }
    finally:
        os.unlink(tmp_path)


def verify_deck(deck_path: Path,
                expect_mp4_sha256: str | None = None,
                expect_fallback_sha256: str | None = None) -> dict:
    """Structural embed proof for a deck at any path.

    Unzips the deck, follows the video slide's relationships to the
    media part, and shows the media is INSIDE the file (no external
    targets), byte-identical to the expected artifact when a hash is
    given, and parseable by ffprobe. Also proves the poster is the
    video slide's picture and the fallback slide carries its image.
    This is the proof that a moved or copied deck still carries its
    media; PowerPoint playback itself stays UNVERIFIED.
    """
    deck_path = Path(deck_path)
    if not deck_path.exists():
        raise AdapterError(
            "PPTX_INPUT_MISSING", "MG_INPUT_MISSING",
            "no deck at %s" % deck_path)
    try:
        zf = zipfile.ZipFile(deck_path)
    except zipfile.BadZipFile as err:
        raise AdapterError(
            "PPTX_DECK_INVALID", "MG_DELIVERY_FAILED",
            "%s is not a readable OOXML package: %s" % (deck_path, err))
    names = set(zf.namelist())
    for required in ("[Content_Types].xml", "ppt/presentation.xml",
                     "ppt/slides/slide1.xml",
                     "ppt/slides/_rels/slide1.xml.rels"):
        if required not in names:
            raise AdapterError(
                "PPTX_DECK_INVALID", "MG_DELIVERY_FAILED",
                "deck is missing required part %s" % required)
    types_root = ET.fromstring(zf.read("[Content_Types].xml"))
    mp4_declared = any(
        d.get("Extension") == "mp4" for d in types_root.findall(
            "ct:Default", NS)) or any(
        (o.get("PartName") or "").endswith(".mp4")
        for o in types_root.findall("ct:Override", NS))

    slide1 = ET.fromstring(zf.read("ppt/slides/slide1.xml"))
    rels1 = _parse_rels(zf, "ppt/slides/_rels/slide1.xml.rels")
    external = [rid for rid, r in rels1.items()
                if r["target_mode"] == "External"]
    video_file = slide1.find(".//a:videoFile", NS)
    p14_media = slide1.find(".//p14:media", NS)
    blip = slide1.find(".//a:blip", NS)
    if video_file is None or p14_media is None or blip is None:
        raise AdapterError(
            "PPTX_DECK_INVALID", "MG_DELIVERY_FAILED",
            "the video slide lacks a:videoFile, p14:media, or the "
            "poster blip; it is not a media embed")
    link_id = video_file.get("{%s}link" % NS["r"])
    embed_id = p14_media.get("{%s}embed" % NS["r"])
    poster_id = blip.get("{%s}embed" % NS["r"])
    for label, rid in (("videoFile link", link_id),
                       ("p14 media embed", embed_id),
                       ("poster blip", poster_id)):
        if rid not in rels1:
            raise AdapterError(
                "PPTX_DECK_INVALID", "MG_DELIVERY_FAILED",
                "the slide's %s references %s, which has no "
                "relationship" % (label, rid))
    media_part = _resolve("ppt/slides", rels1[embed_id]["target"])
    video_part = _resolve("ppt/slides", rels1[link_id]["target"])
    poster_part = _resolve("ppt/slides", rels1[poster_id]["target"])
    if media_part != video_part:
        raise AdapterError(
            "PPTX_DECK_INVALID", "MG_DELIVERY_FAILED",
            "a:videoFile and p14:media point at different parts "
            "(%s vs %s)" % (video_part, media_part))
    if media_part not in names or poster_part not in names:
        raise AdapterError(
            "PPTX_DECK_INVALID", "MG_DELIVERY_FAILED",
            "the media or poster part is not inside the deck file")
    media_bytes = zf.read(media_part)
    media_sha = _sha256_bytes(media_bytes)
    poster_sha = _sha256_bytes(zf.read(poster_part))

    fallback = None
    if "ppt/slides/slide2.xml" in names:
        rels2 = _parse_rels(zf, "ppt/slides/_rels/slide2.xml.rels")
        image_rels = [r for r in rels2.values()
                      if r["type"] == RT + "/image"]
        if image_rels:
            fb_part = _resolve("ppt/slides", image_rels[0]["target"])
            fb_sha = _sha256_bytes(zf.read(fb_part))
            fallback = {"part": fb_part, "sha256": fb_sha}
            if (expect_fallback_sha256
                    and fb_sha != expect_fallback_sha256):
                raise AdapterError(
                    "PPTX_DECK_FALLBACK_MISMATCH", "MG_HASH_MISMATCH",
                    "the fallback slide's image hashes to %s, not "
                    "the packaged fallback %s"
                    % (fb_sha, expect_fallback_sha256))
    if expect_mp4_sha256 and media_sha != expect_mp4_sha256:
        raise AdapterError(
            "PPTX_DECK_MEDIA_MISMATCH", "MG_HASH_MISMATCH",
            "the deck's embedded media hashes to %s, not the "
            "packaged artifact %s" % (media_sha, expect_mp4_sha256))
    return {
        "deck": str(deck_path),
        "deck_sha256": _sha256_bytes(deck_path.read_bytes()),
        "content_types_declare_mp4": mp4_declared,
        "external_relationships_on_video_slide": external,
        "all_relationships_internal": not external,
        "media_part": media_part,
        "media_bytes": len(media_bytes),
        "media_sha256": media_sha,
        "media_matches_packaged_artifact": (
            None if expect_mp4_sha256 is None
            else media_sha == expect_mp4_sha256),
        "media_probe": _probe_media(media_bytes),
        "poster_part": poster_part,
        "poster_sha256": poster_sha,
        "poster_is_video_slide_image": poster_id in rels1,
        "fallback_slide": fallback,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify a PowerPoint deck with an "
                    "embedded motion component (MG-035).")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--mp4", required=True)
    b.add_argument("--poster", required=True)
    b.add_argument("--fallback", required=True)
    b.add_argument("--playback-json", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--title", default="Motion component")
    v = sub.add_parser("verify")
    v.add_argument("--deck", required=True)
    v.add_argument("--expect-mp4-sha256")
    v.add_argument("--expect-fallback-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            playback = json.loads(
                Path(args.playback_json).read_text(encoding="utf-8"))
            record = build_deck(
                Path(args.mp4), Path(args.poster), Path(args.fallback),
                playback, Path(args.out), title=args.title)
        else:
            record = verify_deck(
                Path(args.deck), args.expect_mp4_sha256,
                args.expect_fallback_sha256)
    except AdapterError as err:
        print(json.dumps({
            "status": "error", "code": err.code,
            "category": err.category, "message": err.message,
            "details": err.details}, indent=1))
        return EXIT_BY_CATEGORY.get(err.category, 7)
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
