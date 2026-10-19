#!/usr/bin/env python3
"""Skill 71 stage executor: the missing image-generation execution path.

Why this exists. scripts/shared_page_service.py ADMITS a page and
scripts/stage_gate.py CHECKS a run; neither generates an image. This
script is the production command the service's documented
`--pipeline-command` seam expects, and the command a swarm_runner
`--worker-cmd "python3 scripts/stage_executor.py {run_dir} --stage
{stage} --item {item}"` worker can run for one generation item. It
executes the four image stages (desktop-wireframe, mobile-tablet,
visual-mockup, final-mockups) by calling the approved transport
(Skill 74 `kie_live_adapter.py`) once per image and writing the
returned files into the stage folders.

What it never does. It never closes a stage, never writes a gate
receipt, never writes REPORT.md, and never reports a stage complete.
Admission (write_intake), checking and closing (stage_gate) stay where
they are: the gate's validators and reviewers still run against these
artifacts. A record written here is named
`stage-executor-record.json` so it can never be mistaken for the
contract's `generation-record.json`.

Providers:
  stub  (default) never touches the network. Writes deterministic
        placeholder PNGs so the whole path is provable without a paid
        call, and stamps every record provider="stub".
  kie   the real path. Shells to Skill 74:
        `run --request <req> --save-dir <dir> --mode active`.
        Refuses unless BOTH --allow-paid is passed and KIE_API_KEY is
        set. The key value is never read into output.

What the switch is: `--provider kie --allow-paid` plus a client-owned
KIE_API_KEY in the environment. Everything else is inert.

Input: <run_dir>/production-request.json (see
references/generation-execution.md). Sections drive the jobs; each
later stage attaches the actual PNGs the earlier stages wrote as
input references, never a pathname in prose.

Usage:
  python3 scripts/stage_executor.py <run_dir> [--request FILE]
      [--stages a,b,c] [--provider stub|kie] [--allow-paid]
      [--kie-adapter PATH] [--overwrite]

  # one item, as a swarm_runner worker command (generic-shell runtime):
  python3 scripts/stage_executor.py <run_dir> --stage image-generation-qc
      --item IMG-001 [--provider stub|kie] [--allow-paid]

  # the page's Design Board (SPF021): runs alone, after the image chain, before final-mockups
  python3 scripts/stage_executor.py <run_dir> --stages design-board [--preflight]

The final-mockups stage refuses to start until the page's design board has a current recorded
client approval (scripts/design_board.py gate; references/design-board.md). The board itself
refuses to start until every image slot of the page has its real file.

Exit codes: 0 every requested stage produced its images; 1 a named
failure or refusal; 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circle_image  # noqa: E402  design styles B and C: circle slots
import design_style  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_use  # noqa: E402  SPF022: reference images are structure only
import brand_colors  # noqa: E402  SPF019: client brand colors gate
import hypersaturation  # noqa: E402  SPF020: page color system + image grade, client colors
import composition  # noqa: E402  the composition library (treatments, typed references)
STITCH = SKILL_ROOT / "scripts" / "stitch_sections.py"
HYBRID_BOARD = SKILL_ROOT / "scripts" / "build_hybrid_board.py"
OVERVIEW_BOARD = SKILL_ROOT / "scripts" / "build_overview_board.py"
COMBINE = SKILL_ROOT / "scripts" / "combine_review_pdf.py"
DEFAULT_REQUEST = "production-request.json"
RECORD = "stage-executor-record.json"
BOARD_STAGE = "design-board"  # SPF021: one client-approved board per page, after the images, before final-mockups

STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups")
# per stage: list of (output template, width, height-hint)
LAYOUT = {
    "desktop-wireframe": [("section-{n:02d}.png", 1440, 760)],
    "mobile-tablet": [("section-{n:02d}.png", 390, 1080)],
    "visual-mockup": [("desktop/part-{n:02d}.png", 1440, 760),
                      ("mobile/part-{n:02d}.png", 390, 1080)],
    "final-mockups": [("desktop/part-{n:02d}.png", 1440, 760),
                      ("mobile/part-{n:02d}.png", 390, 1080)],
}

RATIO_ENUM = ("1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16",
              "21:9", "27:16", "16:27", "9:8", "8:9")
RATIO_DEFAULT = {
    "desktop-wireframe": "16:9",
    "mobile-tablet": "9:16",
    "visual-mockup": "3:4",
    "final-mockups": "3:4",
}
# Prose the request builder pasted INTO the verbatim copy is not copy.
COPY_PADDING = (
    "Preserve the measured band order",
    "Hold the type scale",
    "Keep the authority band",
    "Keep the gold hairline rules",
    "Keep the ivory ground warm",
    "Set the eyebrow in rust",
    "Let the hero carry the script overlay",
    "Keep small text crisp",
    "Render the sheet flat",
)
ABS_PATH = re.compile(r"(?:/Users|/Volumes)/[^\s`'\"]+")
# Cross-client names come from the bundled visual-standards manifest, never
# from one hardcoded client: any basename token that is not generic names a
# project this run must not talk about.
GENERIC_REF_TOKENS = {
    "chatgpt", "wireframe", "wireframes", "mockup", "mockups", "desktop",
    "mobile", "tablet", "hybrid", "board", "mashup", "slice", "part",
    "full", "page", "sheet", "reference", "png", "jpg", "jpeg",
}
MANIFEST = SKILL_ROOT / "assets" / "visual-standards" / "manifest.json"

def _manifest_filenames():
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    names = []
    for entry in data.get("files") or []:
        name = str((entry or {}).get("file") or "").rsplit("/", 1)[-1].strip()
        if name:
            names.append(name)
    return names

def cross_client_names():
    """Project names other than the current run's, derived generically from
    the visual-standards manifest basenames (no hardcoded client)."""
    found = set()
    for name in _manifest_filenames():
        tokens = []
        for token in re.split(r"[-_.]+", name.rsplit(".", 1)[0].lower()):
            token = re.sub(r"\d+$", "", token)
            if not token or token.isdigit() or token in GENERIC_REF_TOKENS:
                continue
            tokens.append(token)
        if tokens:
            found.add(" ".join(tokens))
    return sorted(found, key=len, reverse=True)

def _cross_client_regex():
    names = cross_client_names()
    if not names:
        return None
    parts = [r"\b" + r"[\s-]+".join(re.escape(t) for t in n.split()) + r"\b"
             for n in names]
    return re.compile("|".join(parts), re.I)

def _ref_filename_regex():
    names = _manifest_filenames()
    if not names:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.I)

REF_NAME = _ref_filename_regex()
CROSS_CLIENT = _cross_client_regex()
# A full-page dimension pair (WxH with x, X or a multiplication sign) is
# reference provenance, never a target: every frame is one section slice.
DIM_PAIR = re.compile(r"\b\d{2,5}\s*[xX\u00d7]\s*\d{2,5}\b")
# Any sentence that names a tier verdict: "MD as Tier H", "Ref Tier H",
# "AA Tier H", and the standalone shapes "Tier H (flat, sparse)" and
# "Tier R (layered, photo-dense)" that carry no preceding token at all.
TIER_CLASS = re.compile(r"\bTier\s+[A-Z]\b")
SENTENCE_SPLIT = re.compile(r"((?<=[.!?])\s+)")
LEFTOVER = re.compile(r"\{[a-z_]+\}")
DOUBLE_BRACE = re.compile(r"\{\{(\w+)\}\}")
LEAK_LINE = re.compile(
    r"(?i)(/Users/|/Volumes/|\bSHA-256\b|\bBundled path\b|\bReviewed download\b|"
    r"\bEvidence copy\b|Drive folder|crops saved in|Measured with PIL|\balias M4\b|"
    r"^\s*Bytes:\s|"
    r"^\s*[-\s]*Pixels:\s*\d+\s*[x×]\s*\d+|"
    r"^\s*[-\s]*Raster:\s*\d+\s*[x×]\s*\d+|"
    r"(?<!\d)(?:724|2171|2172)(?!\d)|\braster_(?:width|height)\b)")
MAX_LABEL_WORDS = 8
TERMINAL = (".", "!", "?", '"', "”", "'", "’", ")", "]", "…")


def png_size(path: Path):
    """(width, height) from the PNG IHDR, or None; no Pillow dependency."""
    try:
        with Path(path).open("rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def nearest_ratio(width: int, height: int) -> str:
    """Nearest ratio the GPT Image route offers (its enum has no 1:3 or 3:1)."""
    if width <= 0 or height <= 0:
        return RATIO_DEFAULT["visual-mockup"]
    want = width / height

    def distance(label):
        a, b = label.split(":")
        return abs(int(a) / int(b) - want)

    return min(RATIO_ENUM, key=distance)


def _platform(stage: str, template: str) -> str:
    if stage == "mobile-tablet":
        return "mobile"
    if stage == "desktop-wireframe":
        return "desktop"
    return "mobile" if template.startswith("mobile") else "desktop"


def prior_slices(stage: str, run_dir: Path, index: int, template: str):
    """The matching slice of each earlier stage for THIS section only.

    The executor used to attach every earlier slice to every job. A model
    handed all twelve slices draws a whole page and leaves the rest blank;
    it must see the same-index wireframe (and, at final mockups, the
    same-index visual mockup) and nothing else.
    """
    earlier = STAGES[:STAGES.index(stage)]
    want = _platform(stage, template)
    picks = []
    for platform in (want, "desktop" if want == "mobile" else "mobile"):
        for name in earlier:
            for pattern, _w, _h in LAYOUT[name]:
                if _platform(name, pattern) != platform:
                    continue
                candidate = run_dir / name / pattern.format(n=index)
                if candidate.is_file() and candidate not in picks:
                    picks.append(candidate)
    return picks


sys.path.insert(0, str(Path(__file__).resolve().parent))
import wireframe_spec  # noqa: E402  SPF016: wireframe style reference + build-spec prompt


def style_refs(stage: str, request: dict, strict: bool = False) -> list:
    """The one wireframe style reference a desktop or mobile wireframe job
    attaches (chosen by stage and form), first in attach order; [] for the
    other stages. A request that still lists the greyscale sheet is refused."""
    try:
        return wireframe_spec.reference_urls(stage, request, strict)
    except wireframe_spec.SpecError as exc:
        raise ExecutorError(str(exc))


def wireframe_body(stage: str, section: dict, index: int, width: int,
                   request: dict, body: str) -> str:
    """Prepend the annotated build-spec block to a wireframe stage's prose,
    after refusing prose that asks for a colourless sheet."""
    if stage not in wireframe_spec.WIREFRAME_STAGES:
        return body
    try:
        wireframe_spec.refuse_colourless_prose(stage, body)
        block = wireframe_spec.prompt_block(
            stage, section, index, len(request.get("sections") or []), width, request)
    except wireframe_spec.SpecError as exc:
        raise ExecutorError(str(exc))
    if not (request.get("stage_prompts") or {}).get(stage):
        # The generic fallback prose adds nothing to the build spec except the
        # request's one-line style direction, which may be the only place a
        # client colour is written.
        style = sanitize_prompt(str(request.get("style") or "")).strip()
        return f"{block}\n\nSTYLE DIRECTION - {style}" if style else block
    return f"{block}\n\n{body}".strip()


def require_brand_line(stage: str, prompt: str) -> None:
    """A paid wireframe job needs the client's palette in its prompt. The build
    spec says every colour comes from the BRAND COLORS line (scripts/brand_colors.py,
    sigpage-brand-colors / R69, a required prerequisite of this change); without
    that line the prompt points at a colour source that is not there."""
    if stage in wireframe_spec.WIREFRAME_STAGES and not any(
            line.startswith("BRAND COLORS") for line in prompt.splitlines()):
        raise ExecutorError(
            f"{stage}: the composed prompt has no BRAND COLORS line, so the sheet would go "
            "out with no client palette. Resolve the client's brand colors first "
            "(scripts/brand_colors.py, R69 sigpage-brand-colors)")


def target_ratio(stage: str, template: str, section: dict, run_dir: Path,
                 index: int) -> str:
    """Per-section, per-platform ratio: the pixel-mate's, never one 3:4 for all."""
    for candidate in prior_slices(stage, run_dir, index, template):
        size = png_size(candidate)
        if not size:
            continue
        width, height = size
        if _platform(stage, template) == "mobile" and width > height:
            continue  # never carry a landscape mobile slice forward
        return nearest_ratio(width, height)
    # A circle slot is generated 1:1 for its mask; that is the slot's ratio, never the
    # section slice's, so the slice ratio comes from the first non-circle slot.
    flat = [s for s in section.get("slots") or [] if design_style.slot_shape(s) != "circle"]
    slot = (flat or [{}])[0]
    ratio = slot.get("aspect_ratio")
    if ratio and ratio != "auto":
        try:
            a, b = (int(part) for part in ratio.split(":"))
        except (TypeError, ValueError):
            a = b = 0
        if _platform(stage, template) == "mobile" and a > b:
            return RATIO_DEFAULT["mobile-tablet"]
        return ratio
    return RATIO_DEFAULT.get(stage, "3:4")


def _sentence_leaks(sentence: str) -> bool:
    if CROSS_CLIENT and CROSS_CLIENT.search(sentence):
        return True
    if DIM_PAIR.search(sentence):
        return True
    if TIER_CLASS.search(sentence):
        return True
    return False

def _line_leaks(line: str) -> bool:
    if CROSS_CLIENT and CROSS_CLIENT.search(line):
        return True
    return bool(DIM_PAIR.search(line))

def sanitize_prompt(text: str) -> str:
    """Strip provenance a model must not see: local paths, reference
    filenames, hashes, the reference raster's absolute pixel size,
    cross-client project names, tier verdicts on a reference sheet, and
    full-page dimension pairs.

    The cross-client names are derived generically from the bundled
    visual-standards manifest basenames, so no single client is hardcoded
    and every reference sheet in the manifest is covered. Current-client
    content (names, tokens, rules) is left untouched.
    """
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if LEAK_LINE.search(line):
            continue
        if stripped.startswith(("File:", "Selection:", "Unit:", "Builder:", "Date:")):
            continue
        parts = SENTENCE_SPLIT.split(line)
        line = "".join(part for part in parts if not _sentence_leaks(part)).strip()
        if not line or _line_leaks(line):
            continue
        kept.append(line)
    cleaned = "\n".join(kept)
    if REF_NAME:
        cleaned = REF_NAME.sub("the reference sheet", cleaned)
    cleaned = ABS_PATH.sub("the reference sheet", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def prompt_budget(model: str | None):
    """The model's recorded band: hard maximum, 80% floor, 95% target.

    The policy file is the authority; a model with no recorded maximum has
    no band (None), exactly like the skill's validator.
    """
    try:
        policy = json.loads((SKILL_ROOT / "references" / "prompt-budget-policy.json")
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    band = policy.get("band") or {}
    try:
        floor_pct = int(band.get("floor_pct") or 80)
    except (TypeError, ValueError):
        floor_pct = 80
    target_pct = 95
    match = re.match(r"\s*(\d+)", str(band.get("target_pct") or ""))
    if match:
        target_pct = int(match.group(1))
    for entry in policy.get("models") or []:
        match = entry.get("match")
        if not (model and match and str(match) in model and entry.get("unit") == "chars"):
            continue
        try:
            cap = int(entry.get("max_chars"))
        except (TypeError, ValueError):
            return None
        return {"max_chars": cap,
                "floor_chars": cap * floor_pct // 100,
                "target_chars": cap * target_pct // 100}
    return None

def prompt_cap(model: str | None):
    """Back-compat alias: the model's hard maximum, or None."""
    budget = prompt_budget(model)
    return budget["max_chars"] if budget else None

def _cta_label(value) -> str:
    if isinstance(value, dict):
        value = value.get("label")
    return str(value or "").strip().rstrip(".")

def _copy_source_candidates(run_dir: Path, request: dict) -> list[Path]:
    """Every place a run keeps its copy source, in authority order.

    Real layouts differ: the request may name the file at the top level or
    only under metadata, and the file itself may sit under <run_dir>/inputs/
    (the real run-003 layout) rather than the run root.
    """
    candidates = []
    metadata = request.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    for name in (request.get("copy_source"), metadata.get("copy_source")):
        if not str(name or "").strip():
            continue
        path = Path(str(name))
        candidates.append(path if path.is_absolute() else run_dir / path)
    candidates.append(run_dir / "inputs" / "copy.json")
    candidates.append(run_dir / "copy.json")
    return candidates

def copy_source_ctas(run_dir: Path, request: dict) -> dict:
    """Per-section CTA labels from the run's own copy source.

    First existing file wins: the request's top-level copy_source, then
    metadata.copy_source, then <run_dir>/inputs/copy.json, then
    <run_dir>/copy.json. A section's label is keyed by the canonical
    copy-source id, never by the request's band label.
    """
    for path in _copy_source_candidates(run_dir, request):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out = {}
        for section in data.get("sections") or []:
            if not isinstance(section, dict) or not section.get("id"):
                continue
            label = _cta_label(section.get("cta"))
            if label:
                out[str(section["id"])] = label
        return out
    return {}

def copy_contract(section: dict) -> str:
    """The verbatim copy goes FIRST, so attention cannot drift to prose."""
    copy = str(section.get("copy") or "").strip()
    if not copy:
        return ""
    label = section.get("section_id")
    for phrase in COPY_PADDING:
        if phrase in copy:
            raise ExecutorError(
                f"section {label}: verbatim copy carries style padding "
                f"({phrase!r}); rebuild the request with the client's full copy "
                "(no production prose inside the copy block)")
    if copy.endswith("...") or copy[-1] not in TERMINAL:
        raise ExecutorError(
            f"section {label}: verbatim copy ends mid-sentence "
            f"({copy[-56:]!r}); rebuild the request with the full section copy")
    cta = _cta_label(section.get("cta")) or _cta_label(section.get("_copy_source_cta"))
    if not cta:
        match = re.search(r"\bCTA:\s*([^\n]+)", copy)
        if match:
            cta = match.group(1).strip().rstrip(".")
    if not cta and section.get("cta_required"):
        raise ExecutorError(
            f"section {label}: the stage contract requires a CTA label and none "
            "resolved from the section payload or the run's copy source")
    lines = ["VERBATIM COPY — print exactly these strings, character for "
             "character. Do not paraphrase, shorten, reorder, or add text. "
             "Spell every word exactly: do not invent, drop, double, or substitute "
             "characters anywhere:",
             copy]
    # Chip labels and the founder's signature are names, not sentences: the builder
    # lists them apart so the truncated-prose guard above keeps reading prose only.
    labels = [str(x).strip() for x in section.get("labels") or [] if str(x).strip()]
    for text in labels:
        if len(text.split()) > MAX_LABEL_WORDS:
            raise ExecutorError(
                f"section {label}: label {text[:56]!r} is longer than {MAX_LABEL_WORDS} words; "
                "a label is a chip or a signature, so unfinished prose belongs in the copy block")
    if labels:
        lines.append("LABELS — print exactly, one per line, as designed labels: " +
                     " | ".join(f'"{x}"' for x in labels))
    if cta:
        lines.append(f'CTA LABEL — print exactly: "{cta}"')
    return "\n".join(lines)

def negative_block(stage: str | None = None) -> str:
    """The skill's own defect-class negative block, applied at the wire.

    Stage aware: a wireframe stage prints annotations (section number and
    name, type specs, IMG labels with pixel size, ratio and treatment), so its
    block permits exactly those and nothing else; every other stage keeps the
    strict no-extra-text rule.
    """
    tail = ("Do not print any text that is not in the verbatim copy above; no "
            "placeholder tokens, no agent notes, no lorem, no bracketed markers, "
            "no captions, watermarks, or production labels.")
    if stage in composition.WIREFRAME_STAGES:
        tail = ("Do not print any text that is not in the verbatim copy above or in "
                "the wireframe annotations allowed in the composition contract "
                "(section number and name, type specs, slot labels with pixel size, "
                "ratio and treatment, behavior notes); no placeholder tokens, no "
                "agent notes, no lorem, no bracketed markers, no watermarks.")
    return (
        "NEGATIVE BLOCK — do not duplicate a section number, do not print the "
        "same number twice, do not skip a number. Do not mis-number the 7 steps: "
        "exactly 7 badges reading 1, 2, 3, 4, 5, 6, 7 once each, and exactly 7 "
        "step labels. Do not garble any label, mug slogan, or caption: no "
        "\"BIGNEFIT\", \"BTEP 7\", \"DISCIFIONAL\", \"FREIDOM\", "
        "\"Folow Gnlume Sno Home\", \"widhh\", and no invented, dropped, "
        "doubled, or substituted characters anywhere. " + tail)


def frame_contract(width: int, ratio: str) -> str:
    return (
        "FRAME CONTRACT — this image is ONE section slice, not a full page. "
        f"Fill the entire {width}px-wide frame edge to edge at aspect ratio {ratio}. "
        "Draw the section across the full height of the canvas: no blank bands, no "
        "empty lower region, no letterboxing, no collage of other sections. Do not "
        "reproduce the reference sheet's full-page height or any other section.")


class ExecutorError(Exception):
    """A named failure; the message is printed and the run stops."""


def require_brand_colors(run_dir: Path) -> str:
    """Fail closed: no image stage starts without the client's resolved brand colors.
    Returns the color block every wireframe and mockup prompt carries."""
    res = brand_colors.resolve(run_dir)
    if not res.ok:
        raise ExecutorError(brand_colors.failure(run_dir))
    return res.block()


SPEC_DIR = SKILL_ROOT / "references" / "copy-specs"


def canon_section_id(value) -> str:
    """Canonical copy-spec section id: "S02A", "02A", "2a" -> "2A"."""
    text = str(value).strip().upper()
    text = re.sub(r"^S(?=\d)", "", text)
    match = re.fullmatch(r"0*(\d+)([A-Z]?)", text)
    return f"{int(match.group(1))}{match.group(2)}" if match else text


def declared_copy_version(run_dir: Path, request: dict):
    """The selected form: request, then request metadata, then intake.json."""
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    values = [request.get("copy_version"), metadata.get("copy_version")]
    try:
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        values.append(intake.get("copy_version"))
    except (OSError, ValueError, AttributeError):
        pass
    for value in values:
        if value:
            return str(value)
    return None


def allowed_section_sequences(spec: dict) -> list:
    """The spec sequence, plus each optional-children expansion (5 -> 5A,5B,5C)."""
    base = list(spec["sequence"])
    out = [base]
    for parent, child in (spec.get("containment", {}).get("child_sections") or {}).items():
        if parent in base and child.get("ids"):
            i = base.index(parent)
            out.append(base[:i] + list(child["ids"]) + base[i + 1:])
    return out


def check_section_count(run_dir: Path, request: dict, paid: bool = False):
    """Fail closed unless the request carries one section per canonical copy
    section of the selected form (Standard 12, Long-Form 15), in order.

    Never band-compressed: a request that merges sections to fit fewer images
    is refused by name before any prompt is composed or any call is made.
    """
    version = declared_copy_version(run_dir, request)
    if not version:
        if paid:
            raise ExecutorError(
                "the production request does not declare copy_version (request "
                "copy_version, metadata.copy_version, or <run_dir>/intake.json); a "
                "paid run needs the selected form so the section count can be checked")
        print("NOTE section_count: no copy_version declared; the section-count "
              "check was skipped (it is mandatory for a paid run)", file=sys.stderr)
        return None
    spec_path = SPEC_DIR / f"{version}-v6.json"
    if not spec_path.is_file():
        raise ExecutorError(
            f"copy_version {version!r} is not one of standard, long-form "
            f"(no spec at {spec_path.name})")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    ids = [canon_section_id(s["section_id"]) for s in request["sections"]]
    allowed = allowed_section_sequences(spec)
    if ids not in allowed:
        want = allowed[0]
        raise ExecutorError(
            f"section count: the request has {len(ids)} sections {ids} but the "
            f"{version} copy has {len(want)} canonical sections {want}; missing "
            f"{[i for i in want if i not in ids]}, unexpected "
            f"{[i for i in ids if i not in want]}. One request section per canonical "
            "copy section, in order; never band-compress sections")
    sources, absent = [], []
    for path in _copy_source_candidates(run_dir, request):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sources.append(("copy source", [canon_section_id(s["id"]) for s in data.get("sections") or []
                                        if isinstance(s, dict) and s.get("id")]))
        break
    else:
        absent.append("copy source file not found")
    manifest = run_dir / "copy" / "copy-manifest.json"
    if not manifest.is_file():
        absent.append(f"copy manifest absent at {manifest}")
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from validate_wireframe import manifest_section_ids  # the wireframe gate's own reader
        try:
            sources.append(("copy manifest", [canon_section_id(i) for i in manifest_section_ids(
                json.loads(manifest.read_text(encoding="utf-8")))]))
        except (OSError, ValueError):
            pass
    for label, source_ids in sources:
        if source_ids and source_ids != ids:
            raise ExecutorError(
                f"section count: the request has {len(ids)} sections {ids} but its {label} "
                f"has {len(source_ids)} sections {source_ids}; they must match one to one")
    return version, ids, [label for label, _ in sources] + absent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def style_id_for(run_dir: Path, request: dict):
    """The run's design style letter: the request's own wins, else intake.json's, else None
    (older runs and test runs carry none). An unknown letter is refused."""
    style_id = request.get("design_style")
    if not style_id:
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            intake = {}
        style_id = intake.get("design_style") if isinstance(intake, dict) else None
    if style_id and style_id not in design_style.STYLE_IDS:
        raise ExecutorError(f"design_style {style_id!r} is not one of {list(design_style.STYLE_IDS)}")
    return style_id


def resolve_design_style(run_dir: Path, request: dict) -> None:
    """Carry the client's design style (A, B or C) into the request and refuse slot
    shapes the style does not allow."""
    style_id = style_id_for(run_dir, request)
    if not style_id:
        return
    request["design_style"] = style_id
    slots = [slot for sec in request.get("sections") or [] if isinstance(sec, dict)
             for slot in sec.get("slots") or [] if isinstance(slot, dict)]
    failures = design_style.slot_failures(style_id, slots)
    if failures:
        raise ExecutorError("design style slot shapes refused: " + "; ".join(failures))


def load_request(run_dir: Path, name: str, paid: bool = False) -> dict:
    path = run_dir / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExecutorError(f"cannot read production request {path}: {exc}")
    except ValueError as exc:
        raise ExecutorError(f"production request is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ExecutorError("production request must be a JSON object")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ExecutorError("production request needs a non-empty 'sections' array")
    data["_hypersat"] = hypersaturation.roles_for_run(run_dir)
    if data["_hypersat"] is None:
        print("WARN hypersaturation: no resolved client palette; mockup and image stages will refuse "
              "until the client's brand colors are resolved (scripts/brand_colors.py)", file=sys.stderr)
    resolve_design_style(run_dir, data)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    if not (data.get("copy_version") or metadata.get("copy_version")):
        # The run's form is an intake decision (artifact-contracts.md, Intake);
        # a request that does not repeat it is read against intake.json.
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
            if isinstance(intake, dict) and intake.get("copy_version"):
                data["copy_version"] = intake["copy_version"]
        except (OSError, ValueError):
            pass
    for i, s in enumerate(sections):
        if not isinstance(s, dict) or not s.get("section_id"):
            raise ExecutorError(f"sections[{i}] needs section_id")
    data["_section_check"] = check_section_count(run_dir, data, paid)
    ctas = copy_source_ctas(run_dir, data)
    required = bool(data.get("cta_required"))
    for i, s in enumerate(sections):
        s.setdefault("section_name", s["section_id"])
        inline = _cta_label(s.get("cta"))
        source = ctas.get(str(s["section_id"]))
        if inline:
            # Band layouts re-key canonical copy ids, so a raw-id hit is not
            # authority: the builder's mapping-derived inline label wins.
            if source and source != inline:
                print(f"NOTE cta_namespace section {s['section_id']}: raw-id "
                      f"copy value {source} differs from mapping-derived inline "
                      f"{inline}; inline (canonical via band mapping) retained",
                      file=sys.stderr)
        elif source:
            # Copy-source layouts leave cta null; resolve from the run's copy.
            s["cta"] = source
        if required:
            s.setdefault("cta_required", True)
    # the run's brand file, read once: composition cues and light-field colors
    data["_composition_brand"] = composition.load_brand(run_dir)
    return data


def render_template(template: str, values: dict, stage: str) -> str:
    """Render one request template, then fail closed on any leftover token.

    build_requests.py escapes literal braces as {{section_number}} so the
    request stays a JSON-safe format string. str.format() alone turns those
    into {section_number} and the placeholder reaches the model; substitute
    the double-brace form first, then refuse if anything token-shaped is
    still in the rendered body, before any provider call.
    """
    missing = sorted({m.group(1) for m in DOUBLE_BRACE.finditer(template)
                      if m.group(1) not in values})
    if missing:
        raise ExecutorError(
            f"stage_prompts[{stage!r}] has an unknown placeholder: {missing[0]!r}")
    protected = DOUBLE_BRACE.sub(
        lambda m: str(values[m.group(1)]).replace("{", "{{").replace("}", "}}"),
        template)
    try:
        body = protected.format(**values)
    except (KeyError, IndexError, ValueError) as exc:
        raise ExecutorError(
            f"stage_prompts[{stage!r}] has an unknown placeholder: {exc}")
    leftover = LEFTOVER.search(body)
    if leftover:
        raise ExecutorError(
            f"stage_prompts[{stage!r}] still carries the placeholder "
            f"{leftover.group(0)!r} after rendering; refusing before any provider call")
    return body

def request_cues(request: dict) -> dict:
    """The brand's composition cues for this run (empty when it declares none)."""
    return composition.composition_cues(request.get("_composition_brand") or composition.load_brand())


def resolve_composition(section: dict, index: int, request: dict) -> dict:
    """This section's composition record: declared slot treatments, else the
    section role's default, rotated against the neighbouring sections."""
    sections = request.get("sections")
    if (isinstance(sections, list) and 0 < index <= len(sections)
            and sections[index - 1].get("section_id") == section.get("section_id")):
        return composition.assign_treatments(sections, request_cues(request))[index - 1]
    return composition.assign_treatments([section], request_cues(request))[0]


def section_typed_references(stage: str, width: int, resolved: dict, section: dict) -> list:
    """Hosted reference rows (by type) for one job; [] when the catalog has none."""
    platform = "mobile" if width <= 768 else "desktop"
    used = [e["treatment"] for e in resolved.get("slots") or []]
    return composition.typed_references(stage, platform, section.get("section_id"), used)


def stage_prompt(stage: str, section: dict, index: int, width: int,
                 request: dict, ratio: str | None = None,
                 with_sizes: bool = False, strict_floor: bool = False,
                 typed_refs: list | None = None):
    slots = section.get("slots") or []
    resolved = resolve_composition(section, index, request)
    by_slot = {id(e["slot"]): e["treatment"] for e in resolved["slots"]}
    slot_words = "; ".join(
        (f"{s.get('slot_id', 'slot')} {s.get('aspect_ratio', '')} {s.get('art_direction', '')}".strip()
         + " " + composition.slot_words(s, by_slot.get(id(s), "split")))
        for s in slots) or "no image slots"
    values = {
        "stage": stage,
        "section_number": str(index),
        "section_total": str(len(request.get("sections") or [])),
        "section_name": section.get("section_name") or section["section_id"],
        "copy": section.get("copy") or "",
        "slots": slot_words,
        "layout": str(section.get("layout") or ""),
        "width": str(width),
        "ratio": ratio or "",
        "style": request.get("style") or "",
    }
    template = (request.get("stage_prompts") or {}).get(stage)
    if template:
        body = render_template(template, values, stage)
    else:
        body = (f"{stage} build spec, section {index} '{values['section_name']}' "
                f"at {width}px page width. Copy: {values['copy']}. "
                f"Image slots: {slot_words}. {values['style']}").strip()
    copy = str(section.get("copy") or "").strip()
    # Lift the verbatim copy out of the template body BEFORE sanitising: the sanitiser
    # drops blank lines, so a multi-paragraph copy would no longer match and would
    # print twice (once in the verbatim block, once in the body).
    if copy and copy in body:
        body = body.replace(copy, "", 1)
    body = sanitize_prompt(body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    body = wireframe_body(stage, section, index, width, request, body)
    copy_block = copy_contract(section)
    frame_block = frame_contract(width, ratio or "")
    neg_block = negative_block(stage)
    ref_block = reference_use.reference_block(request.get("references"),
                                              request.get("reference_roles"))
    color_block = str(request.get("_brand_block") or "")
    roles = request.get("_hypersat")
    if stage in hypersaturation.MOCKUP_STAGES:
        # Hypersaturation is built in, never optional: no palette, or prose that names another
        # palette, refuses the prompt instead of sending it without (or against) the blocks.
        if not roles:
            raise ExecutorError(
                f"{stage} section {index}: no resolved client palette, so the page color system and "
                "image color grade cannot be built; resolve the client's brand colors first")
        foreign = hypersaturation.foreign_hexes(body, roles)
        if foreign:
            raise ExecutorError(
                f"{stage} section {index}: design prose names colors outside the client palette "
                f"({', '.join(foreign)}); remove them or use the client's own hex values, the "
                "PAGE COLOR SYSTEM block carries the palette")
    page_color, image_grade = hypersaturation.stage_blocks(stage, index, section, roles)
    style_blk = (design_style.style_block(request["design_style"], stage, slots)
                 if request.get("design_style") else "")
    comp_block = composition.block(stage, resolved, typed_refs)
    blocks = [b for b in (copy_block, color_block, page_color, image_grade, ref_block,
                          frame_block, comp_block, neg_block, style_blk) if b]
    budget = prompt_budget(request.get("model"))
    sizes = {
        "chars": 0,
        "copy_chars": len(copy_block),
        "contract_chars": (len(frame_block) + len(neg_block) + len(ref_block)
                           + len(color_block) + len(page_color) + len(image_grade)
                           + len(style_blk) + len(comp_block)),
        "hypersaturation_chars": len(page_color) + len(image_grade),
        "composition_chars": len(comp_block),
        "prose_chars": len(body),
        "floor_chars": budget["floor_chars"] if budget else None,
        "target_chars": budget["target_chars"] if budget else None,
        "max_chars": budget["max_chars"] if budget else None,
    }
    if budget:
        # Per-section budget: copy and the contract blocks are reserved
        # first; design-rules prose may only use what is left.
        reserved = len("\n\n".join(blocks))
        prose_budget = budget["max_chars"] - reserved
        if prose_budget <= 0:
            raise ExecutorError(
                f"{stage} section {index}: the copy and contract blocks alone are "
                f"{reserved} chars, over the {budget['max_chars']}-char model maximum; "
                "cut design prose, never the verbatim copy")
        if len(body) > prose_budget:
            raise ExecutorError(
                f"{stage} section {index}: design prose is {len(body)} chars, over its "
                f"{prose_budget}-char section budget ({budget['max_chars']}-char model "
                f"maximum minus {reserved} chars reserved for copy and contract); "
                "cut design prose, never the verbatim copy")
    prompt = "\n\n".join(blocks + [body]).strip()
    sizes["chars"] = len(prompt)
    if budget:
        deficit = budget["floor_chars"] - len(prompt)
        if len(prompt) > budget["max_chars"]:
            raise ExecutorError(
                f"{stage} section {index}: prompt is {len(prompt)} chars, over the "
                f"{budget['max_chars']}-char model maximum; cut design prose, never "
                "the verbatim copy")
        if deficit > 0:
            message = (f"{stage} section {index}: {len(prompt)} chars, {deficit} below the "
                       f"{budget['floor_chars']}-char floor ({budget['target_chars']}-char "
                       "target); add genuine specification")
            if strict_floor:  # owner Decision 1: under the floor fails the prompt stage
                raise ExecutorError(f"prompt budget: {message}")
            print(f"WARN prompt_budget {message}", file=sys.stderr)
    return (prompt, sizes) if with_sizes else prompt

def build_input(job: dict, request: dict) -> dict:
    exact = bool(job.get("exact_references"))
    if exact:  # the design board: exactly the job's attachments (client logo, the page's images)
        refs = [str(r) for r in job["references"]]
    else:
        refs = list(dict.fromkeys(str(r) for r in (job.get("style_refs") or []) +
                                  (request.get("references") or []) + job["references"]))
    base = {"prompt": job["prompt"], "input_urls": refs}
    if job.get("ratio"):
        base["aspect_ratio"] = job["ratio"]
    extra = request.get("input_extra")
    if isinstance(extra, dict):
        base.update(extra)
    if exact:  # a request-level extra can never add a picture to the board either
        base["input_urls"] = refs
    return base


def stub_png(path: Path, width: int, height: int, label: str) -> None:
    from PIL import Image, ImageDraw  # the repo's existing image dependency
    seed = hashlib.sha256(label.encode("utf-8")).digest()
    ink = (seed[0] % 80, seed[1] % 80, seed[2] % 80)
    accent = (40 + seed[3] % 120, 40 + seed[4] % 120, 40 + seed[5] % 120)
    img = Image.new("RGB", (width, height), (248, 246, 242))
    d = ImageDraw.Draw(img)
    margin = max(16, width // 24)
    d.rectangle([margin, margin, width - margin, margin + height // 8], outline=ink, width=3)
    d.text((margin + 12, margin + 12), f"STUB - {label}", fill=ink)
    y = margin + height // 8 + margin
    while y < height - margin:
        d.rectangle([margin, y, width - margin, y + max(8, height // 40)], fill=accent)
        y += max(24, height // 20)
    d.rectangle([margin, height - margin - height // 10, width // 3, height - margin],
                outline=ink, width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


class StubProvider:
    name = "stub"
    mode = "stub"

    def generate(self, job: dict, request: dict) -> dict:
        stub_png(job["out"], job["width"], job["height"], job["label"])
        return {"provider": "stub", "mode": "stub", "model": request.get("model") or "stub-model",
                "saved_paths": [str(job["out"])]}


class KieProvider:
    name = "kie"
    mode = "active"

    def __init__(self, adapter: Path, run_dir: Path):
        self.adapter = adapter
        self.run_dir = run_dir
        self.receipts = run_dir / "receipts" / "kie74"

    def generate(self, job: dict, request: dict) -> dict:
        model = request.get("model")
        if not model:
            raise ExecutorError("--provider kie needs 'model' in the production request")
        slug = f"{job['stage']}-{job['index']:02d}-{len(job['out'].parts)}"
        req_dir = self.run_dir / "generation-requests" / job["stage"]
        req_dir.mkdir(parents=True, exist_ok=True)
        req_path = req_dir / f"{slug}.json"
        out_dir = req_dir / "saved" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        req = {"model": model, "input": build_input(job, request)}
        req_path.write_text(json.dumps(req, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(self.adapter), "run", "--request", str(req_path),
             "--save-dir", str(out_dir), "--mode", "active"],
            capture_output=True, text=True)
        raw = (proc.stdout or "").strip().splitlines()
        try:
            result = json.loads(raw[-1]) if raw else {}
        except ValueError:
            raise ExecutorError(
                f"Skill 74 returned no JSON for {job['out']}: {(proc.stderr or '')[:300]}")
        if result.get("state") != "success" or not result.get("saved_paths"):
            raise ExecutorError(
                f"Skill 74 did not save {job['out']}: state={result.get('state')!r} "
                f"error={(result.get('error') or {}).get('msg', '')[:200]}")
        source = Path(result["saved_paths"][0])
        if not source.is_file():
            raise ExecutorError(f"Skill 74 reported {source} but it is not on disk")
        job["out"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, job["out"])
        self.receipts.mkdir(parents=True, exist_ok=True)
        receipt = {"adapter": "74-kie-live-adapter", "mode": "active", "model": model,
                   "task_id": result.get("task_id"), "saved_paths": [str(job["out"])],
                   "file": str(job["out"].relative_to(self.run_dir)),
                   "at": now_iso(), "adapter_result": result}
        (self.receipts / f"{slug}.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"provider": "kie", "mode": "active", "model": model,
                "task_id": result.get("task_id"), "saved_paths": [str(job["out"])]}


def find_adapter(explicit: str | None) -> Path:
    candidates = [explicit, os.environ.get("SKILL71_KIE_ADAPTER")]
    candidates += [
        str(SKILL_ROOT.parent / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py"),
        str(Path.home() / "openclaw-onboarding" / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    raise ExecutorError(
        "Skill 74 adapter not found; pass --kie-adapter PATH or set SKILL71_KIE_ADAPTER")


def make_provider(args, run_dir: Path):
    if args.provider == "stub":
        return StubProvider()
    if not args.allow_paid:
        raise ExecutorError(
            "refusing the paid route: pass --allow-paid after the spend cap is approved "
            "(no API call was made)")
    if not os.environ.get("KIE_API_KEY"):
        raise ExecutorError(
            "refusing the paid route: KIE_API_KEY is not set in this environment "
            "(no API call was made)")
    return KieProvider(find_adapter(args.kie_adapter), run_dir)


def compose(stage: str, run_dir: Path, provider, expect: int | None = None) -> dict:
    """Run the existing deterministic composers when their inputs exist.

    No composer is invented here: stitch_sections.py,
    build_hybrid_board.py and combine_review_pdf.py are the repo's own
    pinned steps. The stitcher and board refuse to run from inputs that
    do not pass their validation; the review-PDF step validates its own
    output and deletes a PDF that fails. Stub mode never composes: a
    placeholder is not an approved input.
    """
    if provider.name != "kie":
        return {"status": "skipped", "reason": "stub provider writes placeholders only"}
    stage_dir = run_dir / stage
    result = {"status": "not_applicable"}
    if stage in ("desktop-wireframe", "mobile-tablet"):
        if not (stage_dir / "production-record.json").is_file():
            result = {"status": "skipped", "reason": "no production-record.json to stitch from"}
        else:
            proc = subprocess.run([sys.executable, str(STITCH), str(stage_dir)],
                                  capture_output=True, text=True, cwd=str(SKILL_ROOT))
            result = {"status": "pass" if proc.returncode == 0 else "fail",
                      "command": f"stitch_sections.py {stage_dir}",
                      "exit": proc.returncode,
                      "output": (proc.stdout + proc.stderr).strip()[:600]}
    elif stage == "final-mockups":
        if not (run_dir / "final-mockups" / "hybrid-board.json").is_file():
            result = {"status": "skipped", "reason": "no hybrid-board.json to compose from"}
        else:
            proc = subprocess.run([sys.executable, str(HYBRID_BOARD), str(run_dir)],
                                  capture_output=True, text=True, cwd=str(SKILL_ROOT))
            result = {"status": "pass" if proc.returncode == 0 else "fail",
                      "command": f"build_hybrid_board.py {run_dir}",
                      "exit": proc.returncode,
                      "output": (proc.stdout + proc.stderr).strip()[:600]}
    # The client never receives loose section images: once the stage's
    # sections exist, they are combined, in section order, into the stage's
    # desktop and mobile review PDFs (review-pdfs/), validator-gated.
    cmd = [sys.executable, str(COMBINE), str(run_dir), "--stage", stage]
    if expect:
        cmd += ["--expect", str(expect)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
    result["review_pdf"] = {"status": "pass" if proc.returncode == 0 else "fail",
                            "command": f"combine_review_pdf.py {run_dir} --stage {stage}",
                            "exit": proc.returncode,
                            "output": (proc.stdout + proc.stderr).strip()[:600]}
    return result


def reference_bleed(out: Path, request: dict, provider):
    """QC leg: did the delivered image reproduce the reference's palette or
    brand text? None when no reference was attached or the image is a stub
    placeholder. Recorded, never gating here: the stage gate reads it."""
    if provider.name == "stub" or not request.get("references"):
        return None
    return reference_use.check(out, request["references"], request.get("client_palette") or ())


def record_bleed(entry: dict, out: Path, request: dict, provider, stage: str) -> None:
    """Attach the bleed result to a delivered-image record (run_stage and
    run_item both route here, so every delivered image gets the same check)."""
    bleed = reference_bleed(out, request, provider)
    if bleed:
        entry["reference_bleed"] = bleed
        if bleed["status"] != "PASS":
            print(f"WARN reference_bleed {stage} {out.name}: "
                  f"{json.dumps(bleed, sort_keys=True)[:400]}")


def overview_boards(stage: str, run_dir: Path, provider, request_name: str,
                    expect: int | None = None) -> dict:
    """Second client deliverable next to the review PDFs: the combined
    overview boards (desktop, mobile, and the combined desktop + mobile board),
    all sections on one image each (references/overview-board.md).
    Pure Pillow, no provider call; fails closed on a missing section. Stub
    mode never composes, same as compose()."""
    if provider.name != "kie":
        return {"status": "skipped", "reason": "stub provider writes placeholders only"}
    cmd = [sys.executable, str(OVERVIEW_BOARD), str(run_dir), "--stage", stage,
           "--request", request_name]
    if expect:
        cmd += ["--expect", str(expect)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
    return {"status": "pass" if proc.returncode == 0 else "fail",
            "command": f"build_overview_board.py {run_dir} --stage {stage}",
            "exit": proc.returncode,
            "output": (proc.stdout + proc.stderr).strip()[:600]}


def run_stage(stage: str, run_dir: Path, request: dict, provider,
              request_name: str = DEFAULT_REQUEST) -> dict:
    if stage not in LAYOUT:
        raise ExecutorError(f"unknown stage {stage!r}; expected one of {list(STAGES)}")
    sections = request["sections"]
    targets = LAYOUT[stage]
    records = []
    for index, section in enumerate(sections, start=1):
        for template, width, height in targets:
            out = run_dir / stage / template.format(n=index)
            ratio = target_ratio(stage, template, section, run_dir, index)
            style = style_refs(stage, request, provider.name == "kie")
            refs = prior_slices(stage, run_dir, index, template)
            typed = section_typed_references(
                stage, width, resolve_composition(section, index, request), section)
            prompt, prompt_sizes = stage_prompt(
                stage, section, index, width, request, ratio, with_sizes=True,
                strict_floor=provider.name == "kie", typed_refs=typed)
            if provider.name == "kie":
                require_brand_line(stage, prompt)
            job = {
                "stage": stage, "index": index, "section": section,
                "out": out, "width": width, "height": height,
                "label": f"{stage} section {index:02d} {width}px",
                "ratio": ratio,
                "references": [str(p) for p in refs] + [r["url"] for r in typed],
                "typed_references": [{"id": r.get("id"), "type": r.get("type"), "sha256": r.get("sha256")}
                                     for r in typed],
                "style_refs": style,
                "prompt": prompt, "prompt_sizes": prompt_sizes,
            }
            result = provider.generate(job, request)
            actual = png_size(out)
            entry = {
                "section_id": section["section_id"],
                "section_number": index,
                "file": str(out.relative_to(run_dir)),
                "width": width,
                "requested_ratio": ratio,
                "actual_pixels": list(actual) if actual else None,
                "sha256": sha256(out),
                "prompt_sha256": hashlib.sha256(job["prompt"].encode("utf-8")).hexdigest(),
                "prompt_sizes": job.get("prompt_sizes"),
                "model": result.get("model"),
                "provider": result.get("provider"),
                "mode": result.get("mode"),
                "task_id": result.get("task_id"),
                "inputs": build_input(job, request)["input_urls"],
                "typed_references": job["typed_references"],
                "treatments": [e["treatment"] for e in resolve_composition(
                    section, index, request)["slots"]],
            }
            record_bleed(entry, out, request, provider, stage)
            if actual:
                a, b = ratio.split(":")
                want = int(a) / int(b)
                got = actual[0] / actual[1]
                if abs(got - want) / want > 0.02:
                    entry["geometry_mismatch"] = (
                        f"requested {ratio}, delivered {actual[0]}x{actual[1]}")
                    print(f"WARN geometry_mismatch {stage} {out.name}: "
                          f"{entry['geometry_mismatch']}")
            records.append(entry)
    composition = compose(stage, run_dir, provider, len(sections))
    composition["overview_boards"] = overview_boards(
        stage, run_dir, provider, request_name, len(sections))
    record = {
        "stage": stage,
        "provider": provider.name,
        "mode": provider.mode,
        "model": request.get("model") or ("stub-model" if provider.name == "stub" else None),
        "generated_at": now_iso(),
        "note": "this record is not a gate receipt and cannot close a stage",
        "images": records,
        "composition": composition,
    }
    path = run_dir / stage / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def load_board_request(run_dir: Path, name: str) -> dict:
    """The production request as the board needs it: sections and slots, no copy rules."""
    try:
        data = json.loads((run_dir / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExecutorError(f"cannot read production request {run_dir / name}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise ExecutorError("production request needs a 'sections' array")
    return data


def design_board_module():
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    try:
        import design_board
    finally:
        sys.path.pop(0)
    return design_board


def require_board_approval(run_dir: Path, request_name: str) -> None:
    """Fail closed: final-mockups does not start for a page whose design board has no current
    recorded client approval (references/design-board.md)."""
    failures = design_board_module().gate_failures(run_dir, request_name)
    if failures:
        raise ExecutorError("; ".join(failures))


def board_job(run_dir: Path, request: dict):
    """(plan, job) for the page's design board: one image, the client logo and the page's
    section images as references, the contract and palette in the prompt."""
    board = design_board_module()
    try:
        plan = board.plan(run_dir, request)
        prompt, sizes = board.compose_prompt(plan, request, run_dir)
    except board.BoardError as exc:
        raise ExecutorError(str(exc))
    width, height = board.BOARD_PX
    job = {"stage": BOARD_STAGE, "index": 1, "section": {"section_id": plan["role"]},
           "out": run_dir / board.BOARD_FILE, "width": width, "height": height,
           "label": f"{BOARD_STAGE} {plan['role']}", "ratio": board.BOARD_RATIO,
           "references": board.references(plan, run_dir), "exact_references": True,
           "prompt": prompt, "prompt_sizes": sizes}
    return plan, job


def run_board(run_dir: Path, request: dict, provider, overwrite: bool) -> dict:
    board = design_board_module()
    plan, job = board_job(run_dir, request)
    if job["out"].exists() and not overwrite:
        raise ExecutorError(f"{job['out']} exists; pass --overwrite to remake the board "
                            "(a remade board needs a fresh client approval)")
    board.build_overflow_sheet(plan, run_dir)  # real images that do not fit the attachments
    result = provider.generate(job, request)
    try:
        revision = int(board.load_record(run_dir).get("revision", 0)) + 1
    except board.BoardError:
        revision = 1
    record = board.write_record(run_dir, plan, job["prompt"], result, revision)
    print(f"GENERATED {BOARD_STAGE} {board.BOARD_FILE} sha256={record['board']['sha256']}")
    return record


def inventory_slot(run_dir: Path, item: str) -> dict:
    """The item's entry in desktop-wireframe/image-inventory.json, or {} when absent."""
    path = run_dir / "desktop-wireframe" / "image-inventory.json"
    if not path.is_file():
        return {}
    try:
        return circle_image.inventory_entry(path, item)
    except (OSError, ValueError) as exc:
        raise ExecutorError(f"cannot read {path}: {exc}")


def mask_circle_slot(out: Path, run_dir: Path, stage: str, slot: dict) -> dict:
    """Mask a generated square to a circle PNG in place (RGBA, transparent outside),
    keep the raw square under <stage>/raw-square/, and fail unless the result passes
    the shape check. Runs before the delivered file is hashed for the record."""
    raw = run_dir / stage / "raw-square" / out.name
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, raw)
    try:
        from PIL import Image
        with Image.open(raw) as src:
            masked = circle_image.make_circle(
                src, None, circle_image.parse_focus(slot.get("crop_focal")), slot.get("ring"))
    except (OSError, ValueError) as exc:
        raise ExecutorError(f"circle mask failed for {out.name}: {exc}")
    masked.save(out, format="PNG")
    stats = circle_image.alpha_stats(out)
    failures = circle_image.shape_failures(stats)
    if failures:
        raise ExecutorError(f"{out.name} failed the circle shape check after masking: "
                            + "; ".join(failures))
    return {"raw_file": str(raw.relative_to(run_dir)), "raw_sha256": sha256(raw),
            "ring": slot.get("ring"), "alpha": stats}


def with_photo_rules(prompt: str, item: str, request: dict) -> str:
    """Append the slot's treatment photo rules (copy space, crop-safe framing,
    universal negative) to an item prompt when the request carries the slot
    and the prompt does not already hold them. Refuses rather than overflow."""
    sections = request.get("sections") if isinstance(request, dict) else None
    if not isinstance(sections, list):
        return prompt
    resolved = composition.assign_treatments(sections, request_cues(request))
    for entry in resolved:
        for rec in entry["slots"]:
            if str(rec["slot"].get("slot_id")) != item:
                continue
            if rec["treatment"] == "split":
                return prompt
            try:
                rules = composition.photo_rules(
                    rec["slot"], rec["treatment"], request.get("_composition_brand") or composition.load_brand())
            except ValueError as exc:
                raise ExecutorError(f"{item}: {exc}; refusing before any provider call")
            if rules in prompt:
                return prompt
            merged = prompt + "\n\n" + rules
            budget = prompt_budget(request.get("model"))
            if budget and len(merged) > budget["max_chars"]:
                raise ExecutorError(
                    f"{item}: the {rec['treatment']} photo rules add {len(rules)} chars and push "
                    f"the prompt to {len(merged)}, over the {budget['max_chars']}-char model "
                    "maximum; cut design prose in the item prompt, never the verbatim copy")
            return merged
    return prompt


def run_item(run_dir: Path, stage: str, item: str, request: dict, provider,
             overwrite: bool) -> dict:
    prompt_path = run_dir / "image-inventory-prompts" / f"{item}.txt"
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ExecutorError(f"cannot read the item prompt {prompt_path}: {exc}")
    if not prompt:
        raise ExecutorError(f"the item prompt {prompt_path} is empty")
    prompt = with_photo_rules(prompt, item, request)
    ref_block = reference_use.reference_block(request.get("references"),
                                              request.get("reference_roles"))
    roles = request.get("_hypersat") or hypersaturation.roles_for_run(run_dir)
    if not roles:
        raise ExecutorError(f"item {item}: no resolved client palette, so the image color grade "
                            "cannot be added; resolve the client's brand colors first")
    foreign = hypersaturation.foreign_hexes(prompt, roles)
    if foreign:
        raise ExecutorError(f"item {item}: prompt names colors outside the client palette "
                            f"({', '.join(foreign)}); remove them or use the client's own hex values")
    graded = hypersaturation.item_prompt(prompt, roles)
    if ref_block:
        graded = f"{ref_block}\n\n{graded}"
    if graded != prompt:
        cap = prompt_cap(request.get("model"))
        if cap and len(graded) > cap:
            raise ExecutorError(
                f"item {item}: prompt with the reference contract and image color grade is "
                f"{len(graded)} chars, over the {cap}-char model maximum; cut item prose, "
                "never the contract or the grade")
        prompt = graded
    digits = "".join(ch for ch in item if ch.isdigit())
    if not digits:
        raise ExecutorError(f"item id {item!r} carries no number; cannot derive the delivered name")
    out = run_dir / stage / f"Image-{int(digits):02d}.png"
    if out.exists() and not overwrite:
        raise ExecutorError(f"{out} exists; pass --overwrite to replace it")
    slot = inventory_slot(run_dir, item)
    circle = circle_image.entry_shape(slot) == "circle"
    # The inventory, not the request, decides which slots are circles, so the style is
    # checked against the whole inventory here (the request path never sees these slots).
    style_id = style_id_for(run_dir, request)
    inventory = run_dir / "desktop-wireframe" / "image-inventory.json"
    if style_id and inventory.is_file():
        try:
            failures = design_style.slot_failures(style_id, design_style.inventory_slots(inventory))
        except (OSError, ValueError) as exc:
            raise ExecutorError(f"cannot read {inventory}: {exc}")
        if failures:
            raise ExecutorError(f"design style slot shapes refused for {item}: " + "; ".join(failures))
    if circle and design_style.circle_clause().split(":")[0].lower() not in prompt.lower():
        raise ExecutorError(
            f"{item} is a circle slot but its prompt lacks the circle clause "
            f"(design_style.circle_clause(): 'CIRCLE CROP SAFE FRAME ...'); author it into the prompt "
            "within the model's band, never as a silent edit here")
    job = {"stage": stage, "index": int(digits), "section": {"section_id": item},
           "out": out, "width": 1024 if circle else 1440, "height": 1024 if circle else 760,
           "label": f"{item} {stage}",
           "ratio": "1:1" if circle else request.get("item_ratio"), "references": [],
           "prompt": prompt}
    result = provider.generate(job, request)
    circle_record = mask_circle_slot(out, run_dir, stage, slot) if circle else None
    entry = {"stage": stage, "item": item, "file": str(out.relative_to(run_dir)),
             "sha256": sha256(out), "provider": result.get("provider"),
             "mode": result.get("mode"), "model": result.get("model"),
             "task_id": result.get("task_id"), "at": now_iso()}
    record_bleed(entry, out, request, provider, stage)
    if circle_record:
        entry["circle"] = circle_record
    record_path = run_dir / stage / RECORD
    record = {"stage": stage, "provider": provider.name, "mode": provider.mode,
              "model": request.get("model") or ("stub-model" if provider.name == "stub" else None),
              "note": "this record is not a gate receipt and cannot close a stage",
              "items": []}
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    record.setdefault("items", [])
    record["items"] = [e for e in record["items"] if e.get("item") != item] + [entry]
    record["generated_at"] = now_iso()
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"GENERATED {stage} {entry['file']} sha256={entry['sha256']}")
    return entry


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Execute Skill 71's four image stages through the approved "
                    "transport, or one generation item as a runner worker command.")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--request", default=DEFAULT_REQUEST,
                   help=f"production request filename inside the run dir (default {DEFAULT_REQUEST})")
    p.add_argument("--stages", default=",".join(STAGES),
                   help="comma-separated subset, in contract order")
    p.add_argument("--provider", choices=["stub", "kie"], default="stub")
    p.add_argument("--allow-paid", action="store_true",
                   help="required for --provider kie; confirms the spend cap is approved")
    p.add_argument("--kie-adapter", default=None)
    p.add_argument("--item", default=None,
                   help="generate exactly one image-inventory item (swarm worker mode)")
    p.add_argument("--stage", default=None,
                   help="stage for --item; defaults to image-generation-qc")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--preflight", action="store_true",
                   help="compose and validate every prompt with no provider call "
                        "and no file write")
    args = p.parse_args(argv)

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"FAIL: run dir {run_dir} does not exist")
        return 2
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    for stage in stages:
        if stage not in STAGES and stage != BOARD_STAGE:
            print(f"FAIL: unknown stage {stage!r}; expected one of {[BOARD_STAGE, *STAGES]}")
            return 2
    board_requested = BOARD_STAGE in stages
    stages = [s for s in stages if s != BOARD_STAGE]
    try:
        if board_requested and (stages or args.item):
            raise ExecutorError("run the design board on its own: the client approves it before "
                                "the final-mockups stage starts")
        if board_requested:
            request = load_board_request(run_dir, args.request)
            if args.preflight:
                plan, job = board_job(run_dir, request)
                sz = job["prompt_sizes"]
                print(f"PREFLIGHT {BOARD_STAGE} {plan['role']} ratio={job['ratio']} "
                      f"chars={sz['chars']} floor={sz['floor_chars']} max={sz['max_chars']} "
                      f"refs={len(job['references'])} slots={len(plan['slots'])} "
                      f"required_blocks={','.join(plan['expected']['required_blocks'])}")
                print(f"PREFLIGHT_COLORS {BOARD_STAGE} {plan['role']} "
                      + " ".join(f"{x['name']}={x['hex']}" for x in plan["palette"]))
                return 0
            record = run_board(run_dir, request, make_provider(args, run_dir), args.overwrite)
            print(f"STAGE {BOARD_STAGE} images=1 provider={record['generation']['provider']} "
                  f"mode={record['generation']['mode']} record={design_board_module().RECORD_FILE}")
            return 0
        brand_block = require_brand_colors(run_dir)
        if "final-mockups" in stages and not args.item:  # before any call: a refused run spends nothing
            require_board_approval(run_dir, args.request)
        if args.preflight:
            request = load_request(run_dir, args.request)
            request["_brand_block"] = brand_block
            check = request.get("_section_check")
            if check:
                print(f"PREFLIGHT_SECTIONS copy_version={check[0]} "
                      f"sections={len(check[1])} canonical_ids={','.join(check[1])} "
                      f"checked_against={'; '.join(check[2]) or 'request only'}")
            refused = 0
            refs = list(dict.fromkeys(str(r) for r in request.get("references") or []))
            known = [r for r in refs if reference_use.lookup(r)]
            print(f"PREFLIGHT_REFERENCES total={len(refs)} library={len(known)} "
                  f"not_in_library={len(refs) - len(known)} "
                  f"roles={request.get('reference_roles') or '-'}")
            for stage in stages:
                for index, section in enumerate(request["sections"], start=1):
                    cta = _cta_label(section.get("cta")) or "-"
                    print(f"PREFLIGHT_CTA {stage} {section['section_id']} -> {cta}")
                    for template, width, _height in LAYOUT[stage]:
                        name = template.format(n=index)
                        try:
                            ratio = target_ratio(stage, template, section, run_dir, index)
                            resolved = resolve_composition(section, index, request)
                            typed = section_typed_references(stage, width, resolved, section)
                            prompt, sizes = stage_prompt(
                                stage, section, index, width, request, ratio,
                                with_sizes=True, strict_floor=True, typed_refs=typed)
                            refs = style_refs(stage, request) + prior_slices(
                                stage, run_dir, index, template)
                        except ExecutorError as exc:
                            refused += 1
                            print(f"PREFLIGHT {stage} {name} REFUSED: {exc}")
                            continue
                        for line in prompt.splitlines():
                            if line.startswith("BRAND COLORS"):
                                print(f"PREFLIGHT_COLORS {stage} {name} {line}")
                        if sizes.get("hypersaturation_chars"):
                            print(f"PREFLIGHT_HYPERSAT {stage} {name} "
                                  f"ground={hypersaturation.ground_for(index, section)} "
                                  f"chars={sizes['hypersaturation_chars']}")
                        print(f"PREFLIGHT {stage} {name} ratio={ratio} "
                              f"chars={sizes['chars']} copy={sizes['copy_chars']} "
                              f"contract={sizes['contract_chars']} "
                              f"prose={sizes['prose_chars']} "
                              f"floor={sizes['floor_chars']} "
                              f"target={sizes['target_chars']} "
                              f"max={sizes['max_chars']} refs={len(refs)} "
                              f"composition={sizes['composition_chars']} "
                              f"treatments={','.join(e['treatment'] for e in resolved['slots']) or '-'} "
                              f"typed_refs={','.join(r.get('type', '?') for r in typed) or '-'}")
                        if stage in wireframe_spec.WIREFRAME_STAGES:
                            print(f"PREFLIGHT_WIREFRAME_REFS {stage} {name} "
                                  f"form={wireframe_spec.form_of(request)} "
                                  f"{wireframe_spec.describe_refs(refs)}")
            return 1 if refused else 0
        provider = make_provider(args, run_dir)
        if args.item:
            request = (load_request(run_dir, args.request, paid=args.provider == "kie")
                       if (run_dir / args.request).is_file() else {})
            entry = run_item(run_dir, args.stage or "image-generation-qc",
                             args.item, request, provider, args.overwrite)
            print(f"ITEM {entry['item']} {entry['file']} provider={entry['provider']} "
                  f"mode={entry['mode']}")
            return 0
        request = load_request(run_dir, args.request, paid=args.provider == "kie")
        request["_brand_block"] = brand_block
        for stage in stages:
            record = run_stage(stage, run_dir, request, provider, args.request)
            files = len(record["images"])
            print(f"STAGE {stage} images={files} provider={record['provider']} "
                  f"mode={record['mode']} record={stage}/{RECORD}")
            for image in record["images"]:
                print(f"GENERATED {stage} {image['file']} sha256={image['sha256']}")
            comp = record["composition"]
            print(f"COMPOSE {stage} status={comp.get('status')}"
                  + (f" reason={comp.get('reason')}" if comp.get("reason") else ""))
            board = comp.get("overview_boards")
            if board:
                print(f"OVERVIEW_BOARD {stage} status={board['status']}"
                      + (f"\n{board['output']}" if board.get("output") else ""))
                if board["status"] == "fail":
                    print(f"FAIL: {stage} overview boards did not build; the client set is not ready")
            pdf = comp.get("review_pdf")
            if pdf:
                print(f"REVIEW_PDF {stage} status={pdf['status']}\n{pdf['output']}")
                if pdf["status"] == "fail":
                    print(f"FAIL: {stage} review PDFs did not pass the validator; the client set is not ready")
                    return 1
        return 0
    except ExecutorError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
