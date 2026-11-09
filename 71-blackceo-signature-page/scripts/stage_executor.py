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

The ceiling and the receipts (IMG-21, IMG-06). The kie route also needs intake.json
`image_cap` (the approved picture ceiling). Each paid render is reserved in
<run_dir>/image-spend-ledger.json before the call and refused once the cap is used, so
the Design Board, the final mockups and every QC retry count; a direct run of a NEXT
command spends nothing past it. Each delivered image gets receipts/kie74/<task_id>.json
written here (never by hand): the adapter result plus a binding of task id, sha256 of
the saved bytes and the measured credits_before/credits_after. receipt_gate_problems()
re-hashes the PNGs; shared_page_service.py applies it to every production run.

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
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl  # ponytail: POSIX lock; without it (Windows) the ceiling is still checked, just not race-proof
except ImportError:
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circle_image  # noqa: E402  design styles B and C: circle slots
import design_style  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sibling_skill  # noqa: E402  the ONE sibling-skill resolver (either directory convention)
import reference_use  # noqa: E402  SPF022: reference images are structure only
import brand_colors  # noqa: E402  SPF019: client brand colors gate
import hypersaturation  # noqa: E402  SPF020: page color system + image grade, client colors
import composition  # noqa: E402  the composition library (treatments, typed references)
import copy_forms  # noqa: E402  the one registry of copy forms (standard, long-form, product-selection)
import role_spec  # noqa: E402  per-page-role section structure (checkout and any later role)
import page_role  # noqa: E402  page types with their own wireframe wording (thank-you): sections, layout, style references
STITCH = SKILL_ROOT / "scripts" / "stitch_sections.py"
HYBRID_BOARD = SKILL_ROOT / "scripts" / "build_hybrid_board.py"
OVERVIEW_BOARD = SKILL_ROOT / "scripts" / "build_overview_board.py"
COMBINE = SKILL_ROOT / "scripts" / "combine_review_pdf.py"
DEFAULT_REQUEST = "production-request.json"
RECORD = "stage-executor-record.json"
BOARD_STAGE = "design-board"  # SPF021: one client-approved board per page, after the images, before final-mockups
GATE = SKILL_ROOT / "scripts" / "stage_gate.py"  # the one authority for whether a stage may start

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


GENERATED_IMAGES_DIR = "image-generation-qc"
GENERATED_IMAGE_RE = re.compile(r"^Image-(\d+)\.png$")

def planned_slot_ids(run_dir: Path, index: int):
    """The slot ids the wireframe section plan assigns to section ``index`` (1-based).

    ``None`` when no section plan is on record: the caller then cannot know which
    generated file belongs to this section.
    """
    path = run_dir / "desktop-wireframe" / "section-plan.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(plan, list) or not 0 < index <= len(plan):
        return None
    section = plan[index - 1]
    if not isinstance(section, dict):
        return None
    ids = [s for s in section.get("image_slot_ids") or [] if isinstance(s, str) and s.strip()]
    return ids or None

def generated_image_refs(run_dir: Path, index: int):
    """The image-generation-qc files this section's planned slots name.

    The stage contract promises real photography composited into every slot
    (references/stage-contract.json). The generated, QC'd images are that
    photography: before this they were never handed to final-mockups, so a job
    could only draw the pictures its prompt prose happened to describe and the
    client got a mockup with two images in a twelve-slot page.
    """
    directory = run_dir / GENERATED_IMAGES_DIR
    if not directory.is_dir():
        return []
    files = sorted(p for p in directory.iterdir()
                   if p.is_file() and GENERATED_IMAGE_RE.match(p.name))
    if not files:
        return []
    planned = planned_slot_ids(run_dir, index)
    if planned is None:  # no plan on record: every generated photo is this page's raw material
        return files
    wanted = set()
    for slot_id in planned:
        m = re.search(r"(\d+)\s*$", slot_id)
        if m:
            wanted.add(int(m.group(1)))
    return [p for p in files if int(GENERATED_IMAGE_RE.match(p.name).group(1)) in wanted]

def prior_slices(stage: str, run_dir: Path, index: int, template: str):
    """The matching slice of each earlier stage for THIS section only.

    The executor used to attach every earlier slice to every job. A model
    handed all twelve slices draws a whole page and leaves the rest blank;
    it must see the same-index wireframe (and, at final mockups, the
    same-index visual mockup) and nothing else. final-mockups also receives
    this section's generated images (image-generation-qc), which are the
    real photography the mockup composites into its slots.
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
    if stage == "final-mockups":
        for candidate in generated_image_refs(run_dir, index):
            if candidate not in picks:
                picks.append(candidate)
    return picks


sys.path.insert(0, str(Path(__file__).resolve().parent))
import wireframe_spec  # noqa: E402  SPF016: wireframe style reference + build-spec prompt
import page_kinds  # noqa: E402  SPF030: signature sales page vs signature landing (opt-in) page


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

def _prompt_policy():
    """The ONE canonical prompt policy (shared-utils/prompt_policy.py)."""
    global _POLICY
    try:
        return _POLICY
    except NameError:
        pass
    _POLICY = None
    roots = [SKILL_ROOT.parent / "shared-utils"]
    if os.environ.get("OPENCLAW_SKILLS_DIR"):
        roots.append(Path(os.environ["OPENCLAW_SKILLS_DIR"]) / "shared-utils")
    roots += [Path.home() / ".openclaw" / "skills" / "shared-utils",
              Path("/data/.openclaw/skills/shared-utils")]
    for d in roots:
        if (d / "prompt_policy.py").is_file():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            try:
                import prompt_policy
                _POLICY = prompt_policy
            except Exception:
                _POLICY = None
            break
    return _POLICY


def policy_band_numbers(max_chars):
    """Owner rule 12 band from the one policy service: target 95 percent, hard floor 80 percent."""
    m = int(max_chars)
    pol = _prompt_policy()
    if pol is not None:
        band = dict(pol.band_numbers(m))
        band.setdefault("hard_floor", -(-m * 80 // 100))
        return band
    floor = -(-m * 95 // 100)
    return {"max": m, "floor": floor, "target_min": floor, "target_max": m,
            "hard_floor": -(-m * 80 // 100)}


def prompt_budget(model: str | None):
    """The model's recorded rule 12 band: maximum, 95 percent target, 80 percent hard floor.

    The policy file records WHICH maximum governs this route; the band arithmetic comes
    from the one policy service. A model with no recorded maximum has no band (None), and
    the paid boundary then refuses a pass rather than inventing one.
    """
    try:
        policy = json.loads((SKILL_ROOT / "references" / "prompt-budget-policy.json")
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        policy = {"models": []}
    for entry in policy.get("models") or []:
        match = entry.get("match")
        if not (model and match and str(match) in model and entry.get("unit") == "chars"):
            continue
        try:
            cap = int(entry.get("max_chars"))
        except (TypeError, ValueError):
            return None
        band = policy_band_numbers(cap)
        return {"max_chars": cap, "floor_chars": band["floor"],
                "hard_floor_chars": band["hard_floor"],
                "target_chars": band["target_min"],
                "source": "prompt-budget-policy:%s" % entry.get("cap_status", "UNKNOWN")}
    if model and "gpt-image-2-6" in model:
        # Fail to the law, never to 32,000: owner ruling 2026-11-08 caps every
        # 2.6 route at 20,000 even if the policy file lookup misses.
        return {"max_chars": 20000, "floor_chars": 19000, "hard_floor_chars": 16000,
                "target_chars": 19000,
                "source": "Owner ruling 2026-11-08 fallback: 20,000 (66-kie-image/models.json owner_prompt_cap_chars)."}
    return None

def prompt_cap(model: str | None):
    """Back-compat alias: the model's hard maximum, or None."""
    budget = prompt_budget(model)
    return budget["max_chars"] if budget else None

def _cta_label(value) -> str:
    if isinstance(value, dict):
        value = value.get("label")
    return str(value or "").strip().rstrip(".")

def cta_labels(section: dict) -> list:
    """Every button label a section carries: one `cta`, or `cta_labels` (one button per package
    card on product-selection; the utility actions side by side on the thank-you page, whose
    `cta_layout` is "utility")."""
    many = [str(x).strip().rstrip(".") for x in section.get("cta_labels") or [] if str(x).strip()]
    return many or ([_cta_label(section.get("cta"))] if _cta_label(section.get("cta")) else [])

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

def copy_contract(section: dict, closing: str = "") -> str:
    """The verbatim copy goes FIRST, so attention cannot drift to prose.
    `closing` is the page kind's closing-band button label (SPF030), printed as
    its own verbatim line when the section has no CTA of its own."""
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
    if not cta and len(cta_labels(section)) > 1:
        cta = "per card"
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
    many = cta_labels(section)
    if len(many) > 1:
        # The treatment belongs to the page type: a package page repeats one button per card,
        # a utility page (thank-you) keeps its actions side by side or one per access card, as
        # the spec's own `cta.note` states (the first action filled, the rest outlined).
        if section.get("cta_layout") == "utility":
            note = str(section.get("cta_note") or "").strip().rstrip(".")
            if not note:  # the spec states the treatment; a guessed one is a defect
                raise ExecutorError(
                    f"section {label}: the utility actions carry no declared treatment "
                    "(cta_note); rebuild the request from the spec, never a guessed treatment")
            treatment = note[0].lower() + note[1:] + "; "
            lead = ("CTA LABELS — utility actions on this page, each its own button, "
                    + treatment + "each printed exactly: ")
        else:
            lead = "CTA LABELS — one button per package card, in card order, each printed exactly: "
        lines.append(lead + " | ".join(f'"{x}"' for x in many))
    elif cta:
        lines.append(f'CTA LABEL — print exactly: "{cta}"')
    elif closing:
        lines.append(f'CLOSING BUTTON LABEL — print exactly: "{closing}"')
    return "\n".join(lines)

def steps_in_spec(spec) -> dict | None:
    """The numbered-steps band of a page spec, or None when the page carries no steps band.

    Read from the governing spec's own metadata (references/copy-specs/**, the same files the
    section-count check reads): a section marked `steps: true` or carrying `step_rules.step_count`.
    The Standard's section 11 declares seven steps, the thank-you page's section 4 four to six,
    and the checkout, upsell, downsell and product-selection specs declare none at all.
    """
    for entry in (spec or {}).get("sections") or []:
        if not isinstance(entry, dict):
            continue
        rules = entry.get("step_rules") if isinstance(entry.get("step_rules"), dict) else {}
        count = rules.get("step_count") if isinstance(rules.get("step_count"), dict) else {}
        if entry.get("steps") or count:
            return {"section_id": entry.get("id"), "name": entry.get("name"),
                    "count": count.get("default"), "min": count.get("min"),
                    "max": count.get("max"), "kind": count.get("kind")}
    return None


def _step_rule(band: dict | None, page_spec: dict | None, default_count: int | None = None) -> str:
    """The negative block's steps sentence for THIS page, or '' when the page has no steps band.

    A page type with its own wording (the thank-you page) keeps its band's range; every other page
    reads its governing spec's count; a page whose structure has no steps band gets no steps rule.
    The main sales skeleton's seven badges are never ordered onto a role that does not carry them
    (a five-section checkout, an eight-band upsell, a thank-you page's four to six). `default_count`
    is the count to use when the wire carries neither a band nor a spec: the Standard landing
    skeleton has always carried seven, and dropping that default silently removed the step rule
    from every landing prompt built without a role spec.
    """
    if page_spec:
        band = band if band and band.get("max") else steps_in_spec(page_spec)
        if band and band.get("min") and band.get("max"):
            return (f"Do not mis-number the steps: the badges read 1, 2, 3 and on up to the last step "
                    f"once each ({band['min']} to {band['max']} steps), with one step label per badge "
                    "and no badge the copy does not carry. ")
        if band:
            try:
                count = int(band.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                return _counted_step_rule(count)
            return ("Do not mis-number the steps: the badges read 1, 2, 3 and on up to the last step "
                    "once each, with one step label per badge and no badge the copy does not carry. ")
        return ""  # the page's own structure carries no steps band: order no badges at all
    try:
        count = int((band or {}).get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    # No page spec resolved (the landing skeleton and every legacy caller): keep the rule the
    # negative block has always carried. The seven badges are the main sales skeleton's own.
    # Both sides kept that seven: the branch hardcoded it, main threads it through default_count.
    # Caller passes default_count=7 for landing forms and 0 for no-steps forms, so both land here.
    if count < 1:
        # Legacy callers pass no default: the landing skeleton has always carried seven.
        # Explicit default_count=0 (a form with no numbered-steps shape) keeps no rule.
        count = 7 if default_count is None else int(default_count or 0)
    if count < 1:
        return ""
    return _counted_step_rule(count)


def _counted_step_rule(count: int) -> str:
    """The negative block's counted steps sentence: exactly N badges reading 1..N, once each."""
    return (f"Do not mis-number the {count} steps: exactly {count} badges reading "
            + ", ".join(str(i) for i in range(1, count + 1))
            + f" once each, and exactly {count} step labels. ")


def role_structure_block(stage: str, section: dict, request: dict, width: int) -> str:
    """The page type's ACTUAL section structure for one mockup slice.

    The wireframe stages carry the page type's full build spec already (wireframe_spec reads the
    same role files). The mockup stages were drawn from the landing skeleton: PAGE TYPE STRUCTURE
    was composed only for page types whose spec carries a `layout` block, so a checkout, upsell or
    downsell mockup was never told which page type's structure it draws. This reads the role spec
    Skill 71 already routes to (references/copy-specs/roles/<role>.json, stamped into the request
    by load_request) and names that section's own structure. It names identity and composition
    only: the section's layout prose is the builder's job, and repeating it here would put the
    same sentences in every slice (the padding rule refuses repeated n-gram blocks).
    """
    block = page_role.layout_block(stage, section, request, width)
    if block:
        return block
    if stage not in hypersaturation.MOCKUP_STAGES:
        return ""
    spec = request.get("_role_spec")
    if not isinstance(spec, dict):
        return ""
    sid = canon_section_id(section.get("section_id"))
    entry = role_spec.section(spec, sid)
    if not isinstance(entry, dict) or not entry:
        return ""
    page = str(spec.get("page_role") or "page").replace("_", " ")
    # One short line, unique per section: the section id and its composition role are the only
    # tokens that differ between slices, so no 8-word run can repeat across the page's prompts
    # (the padding rule refuses repeated n-gram blocks).
    return (f"PAGE TYPE STRUCTURE — {page} page, section {sid} "
            f"({entry.get('composition_role') or 'page block'}); not a landing section.")


def negative_block(stage: str | None = None, steps: bool = True, page_spec: dict | None = None,
                   step_rule: str | None = None) -> str:
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
    if step_rule is None:
        # No rule supplied by the caller: derive it from the page's own structure, keeping the
        # legacy seven-step default when the wire carries no role spec at all.
        step_rule = _step_rule(None, page_spec, default_count=7 if steps else 0)
    return (
        "NEGATIVE BLOCK — do not duplicate a section number, do not print the "
        "same number twice, do not skip a number. " + step_rule + "Do not garble any label, mug slogan, or caption: no "
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


def stage_start_check(run_dir: Path, stage: str, item: str | None = None) -> tuple[int, str]:
    """Skill 71's own start check for one stage, or for one item of an itemized stage.

    The gate is the only authority for whether a stage may start: it verifies the stage's whole
    transitive dependency chain is closed with matching artifact hashes, the stage's
    requires_artifacts exist, the client's brand colours are resolved, and, for an item, that the
    item's own dependency (its prompt, for image-generation-qc) is closed. This calls the gate;
    it never re-implements or relaxes a rule. Before this, a direct run of this command began a
    stage the run had not reached: final mockups before the page's images, generation before its
    prompts, a mockup before the board the client approved.
    """
    verb = "check-item" if item else "check"
    argv = [sys.executable, str(GATE), verb, str(run_dir), stage] + ([str(item)] if item else [])
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def require_stage_start(run_dir: Path, stage: str, provider: str, item: str | None = None) -> dict:
    """The gate's verdict on this execution, and the refusal where one is owed.

    A paid run always refuses: it would spend money on a stage the run has not reached. A stub run
    on a gate-driven run (one that carries private/state.json) refuses too, because that run claims
    to be a gated pipeline and is held to the gate. A stub run on a bare fixture with no gate state
    still proves the wire end to end; it records the gate's own lines as status
    "ungated_fixture" in every record it writes, so its placeholders can never be read as a gated
    stage. Nothing here writes a receipt: the verdict travels in this command's own record.
    """
    rc, text = stage_start_check(run_dir, stage, item)
    verdict = {"status": "pass", "stage": stage, "checked": "item" if item else "stage",
               "gate_exit": rc, "detail": text}
    if item:
        verdict["item"] = item
    if rc == 0:
        return verdict
    where = f"{stage} item {item}" if item else f"stage {stage}"
    if provider == "kie" or (Path(run_dir) / "private" / "state.json").is_file():
        first = next((line for line in text.splitlines() if line.startswith("- ")), text or "no output")
        first = first.lstrip("- ").strip()
        # the gate already names the stage ("stage X cannot start: ..."); keep its reason only
        first = re.sub(rf"^(?:stage|item) .*? cannot start:\s*", "", first)
        raise ExecutorError(f"{where} cannot start: {first} "
                            "(stage_gate.py check refused it; no provider call was made)")
    print(f"WARN start_check {where}: the run carries no gate state, so this is an ungated "
          f"fixture; the gate's refusal is recorded, never hidden: "
          f"{next((l for l in text.splitlines() if l.startswith('- ')), text)[:200]}", file=sys.stderr)
    verdict["status"] = "ungated_fixture"
    return verdict


def require_brand_colors(run_dir: Path) -> str:
    """Fail closed: no image stage starts without the client's resolved brand colors.
    Returns the color block every wireframe and mockup prompt carries."""
    res = brand_colors.resolve(run_dir)
    if not res.ok:
        raise ExecutorError(brand_colors.failure(run_dir))
    return res.block()


SPEC_DIR = copy_forms.SPEC_DIR
SPEC_FILES = copy_forms.SPEC_FILES


def canon_section_id(value) -> str:
    """Canonical copy-spec section id: "S02A", "02A", "2a" -> "2A"."""
    text = str(value).strip().upper()
    text = re.sub(r"^S(?=\d)", "", text)
    match = re.fullmatch(r"0*(\d+)([A-Z]?)", text)
    return f"{int(match.group(1))}{match.group(2)}" if match else text


def request_form(request: dict):
    """The request's own form (copy_version or metadata.copy_version) as a registered form, else None."""
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    return copy_forms.norm(request.get("copy_version") or metadata.get("copy_version"))


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


def allowed_section_sequences(spec: dict, request=None) -> list:
    """The sequence the spec accepts: its own, plus each optional-children expansion
    (5 -> 5A,5B,5C). page_role.allowed_sequences is the one resolver; the request
    builder reads the same function, so the two never disagree."""
    return page_role.allowed_sequences(spec, request)


STRUCTURES_FILE = SKILL_ROOT / "references" / "page-structures.json"


def page_structure(role):
    """The canonical section structure of a non-landing page role
    (references/page-structures.json), or None: the landing page and any role
    without an entry keep the landing copy-spec behaviour."""
    if not role or role == "landing":
        return None
    try:
        data = json.loads(STRUCTURES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExecutorError(f"cannot read {STRUCTURES_FILE.name}: {exc}")
    entry = (data.get("roles") or {}).get(role)
    return entry if isinstance(entry, dict) else None


def page_role_for(run_dir: Path, request: dict) -> str:
    """The page role of this run: the request's own page_role, else the run's
    declared role (intake launch.page_role, else the page-request.json that
    scripts/shared_page_service.py stages), else landing."""
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    for value in (request.get("page_role"), metadata.get("page_role")):
        if value:
            return str(value)
    return page_role.declared_role(run_dir, request)  # also reads a role form's copy_version


def check_band_layout_tags(role, ids, request):
    """A role with a declared layout (references/page-structures.json layouts.<role>, the upsell
    bands) must carry, section for section, the layout_tag that layout declares: every upsell band
    is drawn from its declared layout, never from the heading. Roles without a layout are unchanged."""
    try:
        data = json.loads(STRUCTURES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExecutorError(f"cannot read {STRUCTURES_FILE.name}: {exc}")
    layout = (data.get("layouts") or {}).get(role)
    if not isinstance(layout, dict):
        return
    by_id = {canon_section_id(s["id"]): s["layout_tag"] for s in layout.get("sections") or []}
    for i, section_id in enumerate(ids):
        want, got = by_id.get(section_id), request["sections"][i].get("layout_tag")
        if got != want:
            raise ExecutorError(
                f"band layout: section {section_id} of {role} carries layout_tag {got!r} but "
                f"references/page-structures.json layouts.{role} declares {want!r}; every upsell band "
                "is drawn from its declared layout")


def check_section_count(run_dir: Path, request: dict, paid: bool = False):
    """Fail closed unless the request carries one section per canonical section of
    the page it builds, in order: the selected form's copy sections (Standard 12,
    Long-Form 15, Product Selection 5, Upsell 8, Thank-You 5) for a landing or registered-form run, or the
    page role's own sequence (references/copy-specs/roles/<role>.json, checkout 5)
    for a run whose page_role has one. A non-landing page role with an entry in
    references/page-structures.json is checked against that entry's sequence
    instead (Downsell 8). An upsell role also carries the layout_tag its declared band layout
    names for each section (check_band_layout_tags).

    Never band-compressed: a request that merges sections to fit fewer images
    is refused by name before any prompt is composed or any call is made.
    """
    role = page_role_for(run_dir, request)
    structure = page_structure(role)
    rspec = None if structure else role_spec.for_request(run_dir, request)
    version = structure["copy_version"] if structure else declared_copy_version(run_dir, request)
    if structure:
        spec, label = structure, f"{structure['label']} page ({role})"
    elif rspec:
        version = version or rspec["form"]  # the form only picks the style reference sheet
        if version not in role_spec.FORMS:
            raise ExecutorError(
                f"copy_version {version!r} is not one of standard, long-form (the form label "
                f"of the {rspec['page_role']} page's style reference)")
        spec, label = rspec, f"{rspec['page_role']} page"
    else:
        pspec = page_role.spec_for_role(role)
        # copy_forms.form_for_role is the one registry of page role -> form (it reads a form's
        # plural `page_roles` too), so this guard sees every page type, not only the specs
        # page_role.spec_for_role knows (it needs wireframe.form_label).
        want_form = copy_forms.form_for_role(role) if role != page_role.LANDING_ROLE else None
        if pspec and not version:
            version = pspec["copy_version"]  # a role page needs no landing copy_version
        if not version and want_form:
            version = want_form  # a registered page type is checked from its own role, paid or not
        if not version:
            if paid:
                raise ExecutorError(
                    "the production request does not declare copy_version (request "
                    "copy_version, metadata.copy_version, or <run_dir>/intake.json); a "
                    "paid run needs the selected form so the section count can be checked")
            print("NOTE section_count: no copy_version declared; the section-count "
                  "check was skipped (it is mandatory for a paid run)", file=sys.stderr)
            return None
        if version not in SPEC_FILES:
            raise ExecutorError(
                f"copy_version {version!r} is not one of {', '.join(copy_forms.FORMS)} "
                "(no copy spec for it in references/copy-specs/)")
        spec = json.loads(copy_forms.spec_path(version).read_text(encoding="utf-8"))
        if want_form and want_form != version:
            raise ExecutorError(
                f"page role {role!r} and copy_version {version!r} disagree: {version!r} is "
                f"another page type's canonical form and {role!r} is built from the "
                f"{want_form!r} form; declare the page's own form (a page type is never "
                "forced into another's sections)")
        if not want_form and version not in copy_forms.LANDING_FORMS:
            raise ExecutorError(
                f"page role {role!r} and copy_version {version!r} disagree: {version!r} is a "
                f"page type's own form and {role!r} is a landing page, which takes standard "
                "or long-form (a page type is never forced into another's sections)")
        try:  # SPF030: a declared page kind may only use the copy forms it allows (a landing-role page)
            kind = page_kinds.declared(run_dir, request)
            if kind:
                page_kinds.check(kind, version)
        except page_kinds.KindError as exc:
            raise ExecutorError(f"page kind: {exc}")
        label = f"{version} copy"
    ids = [canon_section_id(s["section_id"]) for s in request["sections"]]
    # The page's own numbered-steps band travels with the request, so every prompt stage orders
    # exactly the steps this page's structure declares (and none at all on a page without one).
    request["_step_band"] = steps_in_spec(spec)
    allowed = allowed_section_sequences(spec, request)
    if ids not in allowed:
        want = allowed[0]
        raise ExecutorError(
            f"section count: the request has {len(ids)} sections {ids} but the "
            f"{label} has {len(want)} canonical sections {want}; missing "
            f"{[i for i in want if i not in ids]}, unexpected "
            f"{[i for i in ids if i not in want]}. One request section per canonical "
            "copy section, in order; never band-compress sections")
    check_band_layout_tags(role, ids, request)
    sources, absent = [], []
    for path in _copy_source_candidates(run_dir, request):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # a section is keyed by `id`, or by `number` (the upsell copy, Skill 80)
        sources.append(("copy source", [canon_section_id(s.get("id") or s["number"]) for s in data.get("sections") or []
                                        if isinstance(s, dict) and (s.get("id") or s.get("number"))]))
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
    role = page_role_for(run_dir, data)
    if role != "landing":
        data["page_role"] = role  # wireframe_spec reads the page profile from it
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
    data["_role_spec"] = role_spec.for_request(run_dir, data)  # None for a landing run
    data["page_kind"] = None  # SPF030: only a landing-role page is a sales or opt-in page
    if role == page_role.LANDING_ROLE and not data["_role_spec"]:
        try:
            data["page_kind"] = page_kinds.declared(run_dir, data)
        except page_kinds.KindError as exc:
            raise ExecutorError(str(exc))
        if data["page_kind"] is None:
            print("NOTE page_kind: not declared (request, metadata or intake.json); the pages "
                  "carry no sales/opt-in label. Production intake requires it "
                  "(scripts/write_intake.py --page-kind)", file=sys.stderr)
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


def section_typed_references(stage: str, width: int, resolved: dict, section: dict,
                             request_form=None, request: dict | None = None) -> list:
    """Hosted reference rows (by type) for one job; [] when the catalog has none.
    The structural sheets in the catalog are landing sections keyed by landing ids, so a
    page with its own role spec never matches one by number (structure only)."""
    platform = "mobile" if width <= 768 else "desktop"
    used = [e["treatment"] for e in resolved.get("slots") or []]
    # a page-type section ("2" of the thank-you page) is not landing section 2: it matches no
    # landing sheet, only the per-treatment examples
    sid = None if (section.get("composition_role") or (request or {}).get("_role_spec")
                   or page_role.request_spec(request or {})) else section.get("section_id")
    return composition.typed_references(stage, platform, sid, used, form=request_form)


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
    kind = request.get("page_kind")
    closing = None  # SPF030: the closing band's button label, last slice of a page-kind run
    if kind and (stage in hypersaturation.MOCKUP_STAGES or stage in wireframe_spec.WIREFRAME_STAGES):
        try:
            closing = page_kinds.closing_label(kind, section, request.get("sections"),
                                               index, len(request.get("sections") or []))
        except page_kinds.KindError as exc:
            raise ExecutorError(str(exc))
    if kind and stage in hypersaturation.MOCKUP_STAGES:
        try:
            body = f"{page_kinds.mockup_line(kind, closing, levels=request.get('folded_levels'))}\n\n{body}"
        except page_kinds.KindError as exc:
            raise ExecutorError(str(exc))
    copy_block = copy_contract(section, closing or "")
    frame_block = frame_contract(width, ratio or "")
    page_spec = page_role.request_spec(request)
    steps_ok = request_form(request) not in copy_forms.NO_STEPS_FORMS
    neg_block = negative_block(stage, steps=steps_ok, page_spec=page_spec,
                               # Both sides agreed: landing forms default to seven, no-steps forms
                               # (product selection) get no rule. Branch gated with "" for those;
                               # main threads default_count=0. Same outcome, explicit default wins.
                               step_rule=_step_rule(request.get("_step_band"), page_spec,
                                                    default_count=(7 if steps_ok else 0)))
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
    role_block = role_structure_block(stage, section, request, width)
    named = (("COPY", copy_block), ("BRAND COLORS", color_block), ("PAGE COLOR SYSTEM", page_color),
             ("IMAGE GRADE", image_grade), ("REFERENCE ROLES", ref_block), ("FRAME CONTRACT", frame_block),
             ("COMPOSITION", comp_block), ("PAGE TYPE STRUCTURE", role_block), ("NEGATIVE", neg_block),
             ("DESIGN STYLE", style_blk))
    blocks = [b for _, b in named if b]
    budget = prompt_budget(request.get("model"))
    sizes = {
        "chars": 0,
        "copy_chars": len(copy_block),
        "contract_chars": (len(frame_block) + len(neg_block) + len(ref_block)
                           + len(color_block) + len(page_color) + len(image_grade)
                           + len(style_blk) + len(comp_block) + len(role_block)),
        "blocks": [n for n, b in named if b] + (["BODY"] if body else []),
        "hypersaturation_chars": len(page_color) + len(image_grade),
        "composition_chars": len(comp_block),
        "prose_chars": len(body),
        "floor_chars": budget["floor_chars"] if budget else None,
        "hard_floor_chars": budget["hard_floor_chars"] if budget else None,
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
        hard_floor, target = budget["hard_floor_chars"], budget["target_chars"]
        if len(prompt) > budget["max_chars"]:
            raise ExecutorError(
                f"{stage} section {index}: prompt is {len(prompt)} chars, over the "
                f"{budget['max_chars']}-char model maximum; cut design prose, never "
                "the verbatim copy")
        deficit = target - len(prompt)
        if deficit > 0:
            below_floor = hard_floor - len(prompt)
            if below_floor > 0:
                # Owner rule 12 / Decision 1 (2026-10-15): below the 80 percent floor is the
                # hard reject. The PAID KIE path refuses it; a local compose (no paid call)
                # records it, and the paid-submit boundary refuses the payload anyway.
                message = (f"{stage} section {index}: {len(prompt)} chars, {below_floor} below "
                           f"the {hard_floor}-char 80 percent floor: add genuine specification "
                           f"to reach {hard_floor}, and {deficit} chars to reach the "
                           f"{target}-char target; never repetition or whitespace")
                if strict_floor:
                    raise ExecutorError(f"prompt budget: {message}")
                print(f"WARN prompt_budget {message}", file=sys.stderr)
            else:
                # 80 to below 95 percent PASSES with a warn-and-expand ADD, on every path.
                message = (f"{stage} section {index}: {len(prompt)} chars, {deficit} below the "
                           f"{target}-char target; add genuine specification, never repetition "
                           "or whitespace (warn and expand)")
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
        if "prompt" in extra:
            # F18: a later override may not silently replace the measured prompt. It is
            # REJECTED unless the caller asks for full revalidation, and then it must pass
            # the band before it is used.
            pol = _prompt_policy()
            if pol is None:
                raise ExecutorError(
                    "input_extra carries a prompt and shared-utils/prompt_policy.py is "
                    "missing; the override cannot be revalidated, so the render is refused "
                    "(no API call was made)")
            budget = prompt_budget(request.get("model")) or {}
            gate = pol.apply_input_extra(
                {"prompt": base["prompt"]}, extra, prompt_key="prompt",
                model=request.get("model"), max_chars=budget.get("max_chars"),
                max_source=budget.get("source"),
                revalidate=bool(request.get("input_extra_revalidate")))
            if not gate["ok"]:
                raise ExecutorError(
                    "input_extra would replace the prompt after composition and measurement, "
                    "so the request sent would not be the one reviewed or counted: %s"
                    % "; ".join(gate["problems"]))
            base.update(gate["params"])
            base.update({k: v for k, v in extra.items() if k != "prompt"})
        else:
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
        delivered = True
        if job.get("identity") and job.get("run_dir"):
            delivered = promote_attempt(job["run_dir"], job)
        return {"provider": "stub", "mode": "stub", "model": request.get("model") or "stub-model",
                "saved_paths": [str(job.get("final") or job["out"])], "delivered": delivered}


# Graphics hook (SOP-GIP-02): every wireframe and mockup section carries baked text, so a model that
# cannot render readable text is refused before any spend. Ids are matched as substrings, the same
# way prompt_budget matches its policy rows; the classes follow Skill 35's non-text model list and
# the GIP band file's "non-text-bearing (Seedream only)" routing.
NON_TEXT_MODELS = ("nano-banana", "seedream")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def require_text_capable(model: str) -> None:
    lowered = str(model or "").lower()
    for family in NON_TEXT_MODELS:
        if family in lowered:
            raise ExecutorError(
                f"model {model!r} cannot render readable text ({family} class); wireframe and mockup "
                f"sections carry baked text, so pick a text-capable model (no API call was made)")


def require_png(path: Path) -> None:
    """The delivered section is a real PNG, whatever the provider saved it as."""
    with open(path, "rb") as fh:
        head = fh.read(len(PNG_MAGIC))
    if head != PNG_MAGIC:
        raise ExecutorError(
            f"{path.name} is not a PNG (the provider saved another format); sections are delivered as "
            f"PNG, so this one is refused instead of being renamed")


LEDGER = "image-spend-ledger.json"  # per-run, one entry per paid render (reserved, then confirmed)

# Durable image-job lifecycle (F21). Seven identity fields name a request so it can never
# collide across runs, plan revisions, page instances, viewports, stages, slots or attempts;
# the ledger states keep accepted/uncertain paid work RESERVED until it is reconciled.
IMAGE_JOBS = "image-jobs"          # <run>/image-jobs/<target-slug>/{requests,current.json,attempt-NNN.json}
ATTEMPT_DIR = ".attempts"          # <stage>/.attempts/<target-slug>/<file>: staging, never the artifact
STALE_DIR = "stale"                # a superseded output is moved here, never deleted
JOB_STATES = ("reserved", "accepted", "uncertain", "settled", "refunded", "released")
HELD_STATES = ("reserved", "accepted", "uncertain")   # in flight OR unresolved: still the client's money
CAP_STATES = HELD_STATES + ("settled",)                # the only rows that count against image_cap
# Errors the provider returns BEFORE it accepts a job: nothing was queued, so nothing was spent.
DEFINITIVE_REJECT = frozenset({
    "validation_failed", "bad_request", "bad_file", "bad_url", "bad_response",
    "host_not_allowed", "unsupported_model", "model_not_found", "bad_model",
})


def image_ceiling(run_dir: Path) -> int:
    """The approved picture ceiling: intake.json image_cap. A paid run with no recorded ceiling is
    refused, so a direct run of a NEXT command can never spend past what the client approved."""
    try:
        cap = json.loads((run_dir / "intake.json").read_text(encoding="utf-8")).get("image_cap")
    except (OSError, ValueError, AttributeError):
        cap = None
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise ExecutorError(
            "refusing the paid route: intake.json carries no approved image_cap (a whole number, 0 or "
            "more), so there is no ceiling to spend against (no API call was made)")
    return cap


def _ledger_edit(run_dir: Path, edit):
    """Apply edit(calls) to the run's ledger under an exclusive lock; returns edit's result."""
    path = run_dir / LEDGER
    with open(path, "a+", encoding="utf-8") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        text = fh.read()
        try:
            calls = json.loads(text)["calls"] if text.strip() else []
        except (ValueError, KeyError, TypeError):
            raise ExecutorError(f"{LEDGER} is unreadable; refusing to spend against a broken ledger")
        out = edit(calls)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"calls": calls}, indent=2, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return out


def row_state(call: dict) -> str:
    """The lifecycle state of one ledger row. Rows written before this change carried only
    `status` (reserved|done); they still read correctly."""
    state = str(call.get("state") or "").strip()
    return state if state in JOB_STATES else ("settled" if call.get("status") == "done" else "reserved")


def counts_against_cap(call: dict) -> bool:
    return row_state(call) in CAP_STATES


def _same_identity(call, key) -> bool:
    return bool(key) and str((call.get("identity") or {}).get("key") or "") == str(key)


BASE_IDENTITY_FIELDS = ("run", "plan_revision", "page_instance", "viewport", "stage", "slot")


def _same_target(call, identity) -> bool:
    """The same LOGICAL job: the six base fields, attempt EXCLUDED.

    A retry always claims a fresh attempt, so a guard keyed on the seven-field request key
    never fires for the one case it exists for — resubmitting a job whose earlier attempt is
    still accepted or uncertain. The scope is exactly what the refusal message states.
    """
    if not identity:
        return False
    got = call.get("identity") or {}
    return all(str(got.get(f) or "") == str(identity.get(f) or "")
               for f in BASE_IDENTITY_FIELDS)


def held_rows(run_dir: Path, key: str | None = None) -> list:
    """Paid work that is in flight or unresolved (reserved, accepted, uncertain)."""
    try:
        calls = json.loads((run_dir / LEDGER).read_text(encoding="utf-8")).get("calls") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [c for c in calls if isinstance(c, dict) and row_state(c) in HELD_STATES
            and (key is None or _same_identity(c, key))]


def _transition(run_dir: Path, rid: str, want: str, **fields) -> dict:
    """Move one reservation to `want`, merging fields, under the ledger lock."""
    def edit(calls):
        for call in calls:
            if call.get("id") != rid:
                continue
            call.update(fields)
            call["state"] = want
            call["status"] = "done" if want == "settled" else want
            return dict(call)
        raise ExecutorError(f"{LEDGER} has no reservation {rid}; refusing to invent one")
    return _ledger_edit(run_dir, edit)


def reserve_render(run_dir: Path, cap: int, label: str, identity: dict | None = None,
                   attempt: int = 1, request_sha256: str | None = None) -> str:
    """Count one paid render against the ceiling BEFORE the call (parallel workers cannot
    overshoot); a crash leaves the reservation in place, which fails closed.

    Refused while an earlier job for the SAME logical target (run, plan revision, page,
    viewport, stage, slot — the attempt is the retry, not the job) is accepted or
    uncertain: an unresolved submit is never proof that resubmitting is free."""
    rid = uuid.uuid4().hex

    def edit(calls):
        for call in calls:
            if _same_target(call, identity) and row_state(call) in ("accepted", "uncertain"):
                raise ExecutorError(
                    f"{label}: this exact job is {row_state(call)!r} "
                    f"(task_id={call.get('task_id')!r}); reconcile it before issuing another paid "
                    "job for the same run, plan revision, page, viewport, stage and slot")
        used = sum(1 for call in calls if counts_against_cap(call))
        if used >= cap:
            raise ExecutorError(
                f"image ceiling reached: {used} of {cap} approved paid renders are already used in "
                f"this run ({LEDGER}); no API call was made for {label}")
        row = {"id": rid, "label": label, "state": "reserved", "status": "reserved",
               "at": now_iso(), "attempt": int(attempt)}
        if identity:
            row["identity"] = identity
        if request_sha256:
            row["request_sha256"] = request_sha256
        calls.append(row)
    _ledger_edit(run_dir, edit)
    return rid


def settle_render(run_dir: Path, rid: str, **fields) -> None:
    """Back-compat: fields confirm the render; no fields release a reservation that provably
    never reached the provider. The paid path uses mark_accepted/mark_settled/mark_uncertain."""
    _transition(run_dir, rid, "settled" if fields else "released", **fields)


def mark_accepted(run_dir: Path, rid: str, task_id, request_sha256: str | None = None) -> dict:
    """Persist the provider job id and the submitted request hash BEFORE the wait.

    From here the job is paid work: the reservation stays held whatever the wait, the
    local save or a crash does afterwards.
    """
    fields = {"accepted_at": now_iso()}
    if task_id not in (None, ""):
        fields["task_id"] = str(task_id)
    if request_sha256:
        fields["request_sha256"] = request_sha256
    return _transition(run_dir, rid, "accepted", **fields)


def mark_uncertain(run_dir: Path, rid: str, reason: str, **fields) -> dict:
    """Accepted-but-unresolved paid work: KEEP the reservation and record why."""
    return _transition(run_dir, rid, "uncertain", reason=reason, uncertain_at=now_iso(), **fields)


def mark_refunded(run_dir: Path, rid: str, reason: str, **fields) -> dict:
    """The provider itself reported a failed job with zero credits consumed: nothing was spent."""
    return _transition(run_dir, rid, "refunded", reason=reason, refunded_at=now_iso(), **fields)


def mark_released(run_dir: Path, rid: str, reason: str, **fields) -> dict:
    """Released only when it is PROVEN no remote job was accepted (a pre-acceptance rejection)."""
    return _transition(run_dir, rid, "released", reason=reason, released_at=now_iso(), **fields)


# ---------------------------------------------------------------------------
# Durable request identity + per-attempt immutable results (F21)
# ---------------------------------------------------------------------------
def read_json_file(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def atomic_write_json(path: Path, data) -> None:
    """Write one JSON file so a reader never sees a half file (temp + fsync + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class _jobs_lock:
    """One exclusive lock for attempt allocation and the current-attempt pointer."""

    def __init__(self, run_dir: Path):
        path = Path(run_dir) / IMAGE_JOBS / ".lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path, "a+", encoding="utf-8")
        if fcntl:
            fcntl.flock(self.fh, fcntl.LOCK_EX)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fh.close()
        return False


def run_identity(run_dir: Path) -> str:
    """The run this request belongs to: intake/job run_id, else the run directory's name."""
    for name in ("intake.json", "job.json"):
        data = read_json_file(Path(run_dir) / name)
        for key in ("run_id", "job_id", "slug"):
            if str(data.get(key) or "").strip():
                return str(data[key]).strip()
    return Path(run_dir).resolve().name


def plan_revision(run_dir: Path, request: dict) -> str:
    """A digest of the plan's own decisions: the request minus executor-private keys, plus
    the copy source and the slot inventory the prompts are read from. A dependency that
    changed (copy, slots, request) changes this and invalidates every earlier output."""
    public = {k: v for k, v in (request or {}).items() if not str(k).startswith("_")}
    h = hashlib.sha256(json.dumps(public, sort_keys=True, default=str).encode("utf-8"))
    for rel in ("copy/copy-manifest.json", "desktop-wireframe/image-inventory.json"):
        path = Path(run_dir) / rel
        if path.is_file():
            h.update(rel.encode("utf-8"))
            h.update(sha256(path).encode("utf-8"))
    return h.hexdigest()


def page_instance(run_dir: Path, request: dict) -> str:
    """Which page of the run this request builds: role + declared kind."""
    try:
        role = str((request or {}).get("page_role") or page_role.declared_role(run_dir, request)
                   or page_role.LANDING_ROLE)
    except Exception:  # noqa: BLE001  a malformed request must not hide the role in the name
        role = str((request or {}).get("page_role") or "unknown")
    return f"{role}:{(request or {}).get('page_kind') or 'undeclared'}"


def base_identity(run_dir: Path, request: dict, *, stage: str, slot: str,
                  viewport: str) -> dict:
    """The six identity fields that are known before an attempt is allocated."""
    return {
        "run": run_identity(run_dir),
        "plan_revision": plan_revision(run_dir, request),
        "page_instance": page_instance(run_dir, request),
        "viewport": str(viewport),
        "stage": str(stage),
        "slot": str(slot),
    }


def _target_slug(ident: dict) -> str:
    """Readable, collision-free folder name for one job target (attempt excluded)."""
    slot = re.sub(r"[^A-Za-z0-9._-]+", "-", str(ident.get("slot") or "slot")).strip("-") or "slot"
    if len(slot) > 32:
        slot = slot[:32]
    key = hashlib.sha256(json.dumps({k: ident.get(k) for k in
                                     ("run", "plan_revision", "page_instance", "viewport",
                                      "stage", "slot")}, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{ident.get('stage')}-{slot}-{ident.get('viewport')}-{key[:12]}"


def allocate_attempt(run_dir: Path, ident: dict) -> dict:
    """Reserve the next attempt number for this target under an exclusive lock and return the
    complete identity (with `attempt` and its `key`). The number is CLAIMED on disk at
    allocation, so a rejected or crashed attempt can never have its number reissued."""
    with _jobs_lock(run_dir):
        target = Path(run_dir) / IMAGE_JOBS / _target_slug(ident)
        target.mkdir(parents=True, exist_ok=True)
        seen = []
        for path in list(target.glob("attempt-*.json")) + list(target.glob("attempt-*.claim")):
            match = re.match(r"attempt-(\d+)\.(?:json|claim)$", path.name)
            if match:
                seen.append(int(match.group(1)))
        pointer = read_json_file(target / "current.json")
        attempt = max(seen + [int(pointer.get("attempt") or 0)]) + 1
        full = dict(ident, attempt=attempt)
        full["key"] = hashlib.sha256(json.dumps(full, sort_keys=True).encode("utf-8")).hexdigest()
        (target / f"attempt-{attempt:03d}.claim").write_text(
            json.dumps({"identity": full, "claimed_at": now_iso()}, sort_keys=True) + "\n",
            encoding="utf-8")
        return full


def identity_path(run_dir: Path, ident: dict) -> Path:
    """The attempt's own immutable record file."""
    return (Path(run_dir) / IMAGE_JOBS / _target_slug(ident)
            / f"attempt-{int(ident['attempt']):03d}.json")


def current_pointer_path(run_dir: Path, ident: dict) -> Path:
    return Path(run_dir) / IMAGE_JOBS / _target_slug(ident) / "current.json"


def attempt_is_current(run_dir: Path, ident: dict) -> bool:
    """True when no LATER attempt has already taken the current pointer."""
    pointer = read_json_file(current_pointer_path(run_dir, ident))
    return int(pointer.get("attempt") or 0) <= int(ident["attempt"])


def advance_current(run_dir: Path, ident: dict, record: dict) -> bool:
    """Point the target at this attempt; a slower OLDER attempt can never take it back."""
    with _jobs_lock(run_dir):
        path = current_pointer_path(run_dir, ident)
        pointer = read_json_file(path)
        if int(pointer.get("attempt") or 0) > int(ident["attempt"]):
            return False
        atomic_write_json(path, {"attempt": int(ident["attempt"]), "key": ident["key"],
                                 "at": now_iso(), "record": record})
    return True


def write_attempt_result(run_dir: Path, ident: dict, entry: dict) -> Path:
    """Persist one attempt's immutable result. A different identity never overwrites another
    identity's file; the same identity merges into its own attempt file."""
    path = identity_path(run_dir, ident)
    existing = read_json_file(path)
    if existing and (existing.get("identity") or {}).get("key") not in (None, ident["key"]):
        path = path.with_name(path.name.replace(".json", f"-{ident['key'][:8]}.json"))
    payload = dict(existing, **entry)
    payload["identity"] = ident
    payload.setdefault("attempt_at", now_iso())
    atomic_write_json(path, payload)
    return path


def promote_attempt(run_dir: Path, job: dict, source: Path | None = None) -> bool:
    """Copy this attempt's bytes to the delivered artifact ONLY while the attempt is current.

    An older attempt that finishes late is recorded historically and never replaces the
    artifact or the current pointer. The currency check, the copy and the pointer advance
    are ONE critical section: a check made before a newer attempt advanced the pointer must
    not licence a copy afterwards, or the artifact and the pointer would disagree.
    """
    ident = job["identity"]
    final = Path(job.get("final") or job["out"])
    source = Path(source or job["out"])
    if final.resolve() == source.resolve():
        advance_current(run_dir, ident, {"file": str(final.relative_to(run_dir)),
                                         "sha256": sha256(final)})
        return True
    with _jobs_lock(run_dir):
        if not attempt_is_current(run_dir, ident):
            return False
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_name(f"{final.name}.a{int(ident['attempt']):03d}.part")
        shutil.copyfile(source, tmp)
        os.replace(tmp, final)
        atomic_write_json(current_pointer_path(run_dir, ident),
                          {"attempt": int(ident["attempt"]), "key": ident["key"],
                           "at": now_iso(),
                           "record": {"file": str(final.relative_to(run_dir)),
                                      "sha256": sha256(final)}})
    return True


def reusable_record(run_dir: Path, ident: dict, out: Path) -> dict | None:
    """The newest settled attempt for THIS identity (same run, plan revision, page, viewport,
    stage and slot) whose delivered file still hashes — resume without a paid call."""
    target = Path(run_dir) / IMAGE_JOBS / _target_slug(ident)
    if not target.is_dir():
        return None
    best = None
    for path in sorted(target.glob("attempt-*.json")):
        rec = read_json_file(path)
        got = rec.get("identity") or {}
        if rec.get("state") not in (None, "settled"):
            continue
        if any(got.get(field) != ident.get(field) for field in
               ("run", "plan_revision", "page_instance", "viewport", "stage", "slot")):
            continue
        rel = rec.get("file")
        if not rel or not (Path(run_dir) / rel).is_file():
            continue
        if sha256(Path(run_dir) / rel) != rec.get("sha256"):
            continue
        if best is None or int(got.get("attempt") or 0) > int((best.get("identity") or {}).get("attempt") or 0):
            best = rec
    return best


def stale_output(run_dir: Path, stage: str, out: Path) -> Path | None:
    """Move a superseded output aside (never delete) so a re-render cannot be mistaken for it."""
    out = Path(out)
    if not out.is_file():
        return None
    digest = sha256(out)[:8]
    dest = Path(run_dir) / stage / STALE_DIR / f"{out.stem}.{digest}{out.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(out), str(dest))
    return dest


def _stage_record_edit(run_dir: Path, stage: str, edit):
    """Read-modify-write of one stage record under an exclusive lock and an atomic replace:
    concurrent desktop/mobile/page jobs can no longer lose each other's entries."""
    path = Path(run_dir) / stage / RECORD
    # LND-002: the lock lives under image-jobs/, NEVER beside the record and NEVER under
    # private/. A zero-byte lock file inside the stage folder is scanned as an artifact and
    # fails the package with AF-LAUNCH-PKG-ARTIFACT-EMPTY; private/ belongs to the gate, and the
    # executor must never create it (test_stub_writes_four_stages_and_no_receipts).
    lock = Path(run_dir) / IMAGE_JOBS / ".locks" / f"{stage}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+", encoding="utf-8") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        data = read_json_file(path)
        if not data:
            data = {"stage": stage, "note": "this record is not a gate receipt and cannot close a stage"}
        data.setdefault("stage", stage)
        edit(data)
        data["generated_at"] = now_iso()
        atomic_write_json(path, data)
        return data


def _kie74_receipt():
    """Skill 49's kie74_receipt.py, the one writer and checker of transport receipts (a sibling skill).

    Resolved by SLUG through sibling_skill.skill_dir_for, so the same code runs in the
    onboarding repository (`49-signature-funnel/`) and in a 999 package
    (`.claude/skills/signature-funnel/`). Nothing spells the number and nothing looks in
    the operator's home: an installation carries its own skills.
    """
    path = sibling_skill.skill_file("signature-funnel", "scripts", "kie74_receipt.py",
                                    skill_root=SKILL_ROOT)
    if path is None or not path.is_file():
        raise ExecutorError(
            "Skill 49's scripts/kie74_receipt.py was not found beside this skill "
            f"(searched {', '.join(str(b) for b in sibling_skill.search_bases(SKILL_ROOT))} "
            "for signature-funnel/SKILL.md): transport receipts cannot be written or "
            "checked without it")
    saved = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("kie74_receipt_skill49", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = saved
    return mod


def _json_out(text: str) -> dict:
    """The adapter prints one JSON object (indented); fall back to its last line."""
    for candidate in (text.strip(), (text.strip().splitlines() or [""])[-1]):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def receipt_gate_problems(run_dir: Path) -> list:
    """The production gate: every image the executor delivered must be bound to a provider task by a
    transport receipt whose PNG bytes re-hash; an absent receipt store fails."""
    delivered, claims_provider = [], False
    for rec in sorted(run_dir.glob(f"*/{RECORD}")):
        try:
            data = json.loads(rec.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [f"{rec.relative_to(run_dir)} is unreadable"]
        entries = [e for e in (data.get("images") or []) + (data.get("items") or [])
                   if isinstance(e, dict) and e.get("file")]
        delivered += [e["file"] for e in entries]
        claims_provider |= any((x.get("provider"), x.get("mode")) != ("stub", "stub") for x in [data] + entries)
    if delivered and not claims_provider and not (run_dir / LEDGER).exists() \
            and not (run_dir / "receipts" / "kie74").exists():
        return []  # stub placeholders only: nothing claims a provider, nothing was spent, nothing to bind
    problems =_kie74_receipt().store_problems(run_dir, delivered)
    try:  # the ledger can never show more paid renders than the approved ceiling
        calls = json.loads((run_dir / LEDGER).read_text(encoding="utf-8"))["calls"]
        used = sum(1 for c in calls if isinstance(c, dict) and counts_against_cap(c))
        cap = image_ceiling(run_dir)
        if used > cap:
            problems.append(f"{LEDGER} shows {used} paid renders, over the approved image_cap {cap}")
    except (OSError, ValueError, KeyError, TypeError, ExecutorError):
        pass  # no ledger: nothing was spent here; a missing receipt store is already a problem above
    return problems


class _AdapterTransport:
    """Skill 74 as the ONE paid transport, driven one subcommand at a time.

    Nothing here re-implements submit/wait/save: the executor calls the adapter's own
    `submit`, `wait` and `save` so the provider job id can be persisted BETWEEN submit and
    wait. `transport=` on KieProvider is a seam for the module's own runnable check only;
    production leaves it None.
    """

    def __init__(self, adapter: Path):
        self.adapter = adapter

    def _call(self, *args) -> dict:
        proc = subprocess.run([sys.executable, str(self.adapter), *args],
                              capture_output=True, text=True)
        out = _json_out(proc.stdout)
        if not out:
            raise ExecutorError(
                f"Skill 74 returned no JSON for {args[0]}: "
                f"{(proc.stderr or proc.stdout or '')[:300]}")
        return out

    def credits(self) -> float:
        value = (self._call("credits", "--mode", "active").get("data") or {}).get("credits")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExecutorError("Skill 74 returned no numeric credit balance; a receipt cannot bind the "
                                "spend, so the render is refused (no paid render was made)")
        return value

    def submit(self, req_path: Path) -> dict:
        return self._call("submit", "--request", str(req_path), "--mode", "active")

    def wait(self, task_id, timeout=None) -> dict:
        args = ["wait", "--task-id", str(task_id)]
        if timeout:
            args += ["--timeout", str(timeout)]
        return self._call(*args)

    def save(self, task_id, out_dir, info=None) -> dict:
        args = ["save", "--task-id", str(task_id), "--save-dir", str(out_dir)]
        if info is not None:
            args += ["--info", json.dumps(info, sort_keys=True)]
        return self._call(*args)


def drive_paid_job(run_dir: Path, job: dict, request: dict, transport, *,
                   cap: int, label: str) -> dict:
    """One paid render with the provider job id persisted BEFORE the wait (F21 steps 2-4).

    reserved -> accepted -> settled | uncertain | refunded | released. The reservation is
    released only when the provider provably never accepted a job; a wait failure, a local
    save failure or a crash leaves it accepted/uncertain and HELD.
    """
    model = request.get("model")
    require_text_capable(model)
    ident = job["identity"]
    target = Path(run_dir) / IMAGE_JOBS / _target_slug(ident)
    req_dir = target / "requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    req_path = req_dir / f"request-a{int(ident['attempt']):03d}.json"
    req = {"model": model, "input": build_input(job, request)}
    # F18 (kept from main): freeze the FINAL prompt and bind the payload that will actually be
    # sent. A payload whose prompt is not the frozen one never reaches the paid call.
    pol = _prompt_policy()
    if pol is None:
        raise ExecutorError(
            "shared-utils/prompt_policy.py is missing: the paid prompt band cannot be "
            "enforced, so the render is refused (no API call was made)")
    budget = prompt_budget(model) or {}
    frozen = pol.freeze(job["prompt"], model=model,
                        max_chars=budget.get("max_chars"),
                        max_source=budget.get("source"), job_id=ident["key"][:16])
    gate = pol.assert_payload(req, frozen=frozen)
    if not gate["ok"]:
        raise ExecutorError(
            "prompt policy refused the payload before any paid call: %s"
            % "; ".join(gate["problems"]))
    # FREEZE: what is written and sent is the counted, hashed string. Otherwise the provider
    # received the raw text (fence, surrounding whitespace, NFD) while the receipt and the
    # review named a hash of the normalized text.
    req["input"]["prompt"] = gate["prompt"]
    # The gate above measured the COMPOSED payload, so its payload_sha256 names the pre-freeze
    # request. The receipt must name the payload the transport receives, so the frozen payload
    # is asserted again AFTER the freeze and THAT hash is recorded.
    gate = pol.assert_payload(req, frozen=frozen)
    if not gate["ok"]:
        raise ExecutorError(
            "prompt policy refused the frozen payload before any paid call: %s"
            % "; ".join(gate["problems"]))
    payload = json.dumps(req, indent=2, sort_keys=True) + "\n"
    req_path.write_text(payload, encoding="utf-8")
    (req_dir / f"{req_path.stem}.policy.json").write_text(
        json.dumps({"prompt_policy": frozen,
                    "payload": {"status": gate["status"],
                                "payload_sha256": gate["payload_sha256"]}},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    request_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    before = transport.credits()
    rid = reserve_render(run_dir, cap, label, identity=ident,
                         attempt=ident["attempt"], request_sha256=request_sha256)

    try:
        submitted = transport.submit(req_path)
    except ExecutorError as exc:
        mark_uncertain(run_dir, rid, f"submit outcome unknown: {exc}"[:400])
        raise
    state = str(submitted.get("state") or "")
    code = str((submitted.get("error") or {}).get("code") or "")
    if state in ("skipped", "validated"):
        mark_released(run_dir, rid, f"adapter did not dispatch (state {state!r}); nothing was spent")
        raise ExecutorError(f"Skill 74 did not dispatch the job for {label} (state {state!r})")
    if state in ("fail", "running"):
        if code in DEFINITIVE_REJECT:
            mark_released(run_dir, rid, f"provider rejected the request before accepting it ({code})")
        else:
            mark_uncertain(run_dir, rid, f"submit ended in {state!r} ({code or 'no code'}): an "
                                         "uncertain submission is not proof nothing was charged",
                           submit_error=(submitted.get("error") or {}))
        raise ExecutorError(
            f"Skill 74 did not accept {label}: state={state!r} "
            f"error={(submitted.get('error') or {}).get('msg', '')[:200]}")
    if state not in ("queued", "success"):
        mark_uncertain(run_dir, rid, f"submit returned an unexpected state {state!r}")
        raise ExecutorError(f"Skill 74 returned state {state!r} for {label}; the submission is uncertain")

    task_id = str(submitted.get("task_id") or "")
    if state == "success":  # a SYNC result: there is no task to poll, the payload is the result
        task_id = task_id or ("sync-" + hashlib.sha256(request_sha256.encode()).hexdigest()[:16])
        mark_accepted(run_dir, rid, task_id, request_sha256)   # BEFORE any wait/save
        saved = transport.save(task_id, target / "saved", info=submitted)
        waited = submitted
    else:  # queued
        if not task_id:
            # taskId null: the provider may have accepted a job we cannot name. Never free.
            mark_uncertain(run_dir, rid, "submit returned no provider task id (taskId null): an "
                                         "UNCERTAIN submission, not a free retry")
            raise ExecutorError(
                f"Skill 74 returned no task id for {label}: the submission is uncertain, so the "
                "reservation stays held and no second paid job may be issued for this identity")
        mark_accepted(run_dir, rid, task_id, request_sha256)   # ← persisted BEFORE the wait
        waited = transport.wait(task_id)
        if str(waited.get("state") or "") != "success":
            used = waited.get("credits_consumed")
            zero = isinstance(used, (int, float)) and not isinstance(used, bool) and used == 0
            if str(waited.get("state")) == "fail" and zero:
                mark_refunded(run_dir, rid, "provider reported a failed job with zero credits consumed",
                              task_id=task_id)
            else:
                mark_uncertain(run_dir, rid,
                               f"wait ended in state {waited.get('state')!r}: accepted or ambiguous "
                               "paid work stays reserved", task_id=task_id)
            raise ExecutorError(
                f"Skill 74 did not finish {label}: state={waited.get('state')!r} "
                f"error={(waited.get('error') or {}).get('msg', '')[:200]}")
        saved = transport.save(task_id, target / "saved")

    paths = [p for p in saved.get("saved_paths") or [] if isinstance(p, str)]
    if str(saved.get("state") or "") != "success" or not paths:
        mark_uncertain(run_dir, rid, "the provider accepted the job but the local save did not "
                                     "complete", task_id=task_id)
        raise ExecutorError(
            f"Skill 74 accepted {label} (task {task_id}) but did not save it: the reservation "
            "stays held until the saved bytes are reconciled")
    source = Path(paths[0])
    if not source.is_file():
        mark_uncertain(run_dir, rid, "save reported a path that is not on disk", task_id=task_id)
        raise ExecutorError(f"Skill 74 reported {source} for {label} but it is not on disk")
    try:
        require_png(source)
    except ExecutorError as exc:
        mark_uncertain(run_dir, rid, str(exc)[:400], task_id=task_id)
        raise

    after = transport.credits()
    final = Path(job.get("final") or job["out"])
    delivered = promote_attempt(run_dir, job, source)
    rel_source = str(source.relative_to(run_dir)) if run_dir in source.parents else str(source)
    if not delivered:
        _transition(run_dir, rid, "settled", task_id=task_id, historical=True,
                    attempt_file=rel_source, sha256=sha256(source),
                    credits_before=before, credits_after=after,
                    reason="a later attempt already owns the artifact")
        write_attempt_result(run_dir, ident, {
            "stage": ident["stage"], "slot": ident["slot"], "attempt": ident["attempt"],
            "state": "historical", "historical": True, "file": rel_source,
            "sha256": sha256(source), "task_id": task_id, "provider": "kie", "mode": "active",
            "reason": "a later attempt already owns this artifact"})
        return {"provider": "kie", "mode": "active", "model": model, "task_id": task_id,
                "saved_paths": [rel_source], "historical": True, "delivered": False}
    rel = str(final.relative_to(run_dir))
    result = dict(saved)
    result["saved_paths"] = [str(source)]
    result["task_id"] = task_id
    receipt = _kie74_receipt().write_bound_receipt(run_dir, result, rel, before, after)
    _transition(run_dir, rid, "settled", task_id=task_id, file=rel, sha256=sha256(final),
                credits_before=before, credits_after=after)
    write_attempt_result(run_dir, ident, {
        "stage": ident["stage"], "slot": ident["slot"], "attempt": ident["attempt"],
        "state": "settled", "file": rel, "sha256": sha256(final), "task_id": task_id,
        "provider": "kie", "mode": "active", "request_sha256": request_sha256,
        "credits_before": before, "credits_after": after})
    return {"provider": "kie", "mode": "active", "model": model, "receipt": str(receipt),
            "task_id": task_id, "saved_paths": [str(final)], "delivered": True}


def reconcile_uncertain(run_dir: Path, transport=None) -> list:
    """Resolve accepted/uncertain rows BEFORE any new paid job for the run.

    A job the provider reports successful is saved and settled (no second charge); one it
    reports failed with zero credits consumed is refunded; a row with no task id, and any
    answer that proves nothing, stays uncertain and held.
    """
    outcomes = []
    for row in held_rows(run_dir):
        if row_state(row) not in ("accepted", "uncertain"):
            continue
        task_id = str(row.get("task_id") or "")
        if not task_id:
            outcomes.append({"id": row["id"], "state": "uncertain",
                             "reason": "no provider task id: an UNKNOWN submission, never assumed free"})
            continue
        if transport is None:
            outcomes.append({"id": row["id"], "state": row_state(row), "task_id": task_id,
                             "reason": "no transport probe available"})
            continue
        try:
            info = transport.wait(task_id)
        except ExecutorError as exc:
            outcomes.append({"id": row["id"], "state": "uncertain",
                             "reason": f"probe failed: {exc}"[:200], "task_id": task_id})
            continue
        state = str(info.get("state") or "")
        if state == "success":
            out_dir = Path(run_dir) / IMAGE_JOBS / "reconciled" / re.sub(r"[^A-Za-z0-9_-]", "", task_id)[:60]
            saved = transport.save(task_id, out_dir)
            paths = [p for p in saved.get("saved_paths") or [] if isinstance(p, str)]
            final = Path(run_dir) / str(row.get("label") or "")
            if (str(saved.get("state") or "") == "success" and paths and Path(paths[0]).is_file()
                    and str(row.get("label") or "")):
                final.parent.mkdir(parents=True, exist_ok=True)
                tmp = final.with_name(final.name + ".reconciled.part")
                shutil.copyfile(Path(paths[0]), tmp)
                os.replace(tmp, final)
                _transition(run_dir, row["id"], "settled", task_id=task_id,
                            file=str(row["label"]), sha256=sha256(final),
                            reconciled_at=now_iso(), credits_consumed=info.get("credits_consumed"))
                outcomes.append({"id": row["id"], "state": "settled", "task_id": task_id,
                                 "file": str(row["label"])})
                continue
            outcomes.append({"id": row["id"], "state": "uncertain", "task_id": task_id,
                             "reason": "provider reports success but the bytes were not saved"})
            continue
        if state == "fail":
            used = info.get("credits_consumed")
            if isinstance(used, (int, float)) and not isinstance(used, bool) and used == 0:
                mark_refunded(run_dir, row["id"],
                              "reconciled: provider reported fail with zero credits consumed",
                              task_id=task_id)
                outcomes.append({"id": row["id"], "state": "refunded", "task_id": task_id})
            else:
                outcomes.append({"id": row["id"], "state": "uncertain", "task_id": task_id,
                                 "reason": "provider fail without a proven zero charge"})
            continue
        outcomes.append({"id": row["id"], "state": "uncertain", "task_id": task_id,
                         "reason": f"provider still reports {state!r}"})
    return outcomes


class KieProvider:
    name = "kie"
    mode = "active"

    def __init__(self, adapter: Path, run_dir: Path, transport=None):
        self.adapter = adapter
        self.run_dir = run_dir
        self.transport = transport or _AdapterTransport(adapter)

    def credits(self) -> float:
        return self.transport.credits()

    def generate(self, job: dict, request: dict) -> dict:
        model = request.get("model")
        if not model:
            raise ExecutorError("--provider kie needs 'model' in the production request")
        return drive_paid_job(self.run_dir, job, request, self.transport,
                              cap=image_ceiling(self.run_dir),
                              label=str(Path(job.get("final") or job["out"]).relative_to(self.run_dir)))


def find_adapter(explicit: str | None) -> Path:
    """The Skill 74 transport: an explicit path, the env override, then the sibling tree.

    The sibling is resolved by SLUG (sibling_skill), so a 999 package named
    `.claude/skills/kie-live-adapter` and an onboarding checkout named
    `74-kie-live-adapter` both resolve. The old fallback to a second repository under
    the operator's home is gone: an installation that needs Skill 74 carries it.
    """
    candidates = [explicit, os.environ.get("SKILL71_KIE_ADAPTER")]
    sibling = sibling_skill.skill_file("kie-live-adapter", "scripts", "kie_live_adapter.py",
                                       skill_root=SKILL_ROOT)
    if sibling is not None:
        candidates.append(str(sibling))
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    raise ExecutorError(
        "Skill 74 adapter not found beside this skill; pass --kie-adapter PATH or set "
        "SKILL71_KIE_ADAPTER (searched "
        f"{', '.join(str(b) for b in sibling_skill.search_bases(SKILL_ROOT))})")


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
    image_ceiling(run_dir)  # no ceiling, no paid run: refused before anything is written
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
              request_name: str = DEFAULT_REQUEST, overwrite: bool = False) -> dict:
    if stage not in LAYOUT:
        raise ExecutorError(f"unknown stage {stage!r}; expected one of {list(STAGES)}")
    start = require_stage_start(run_dir, stage, provider.name)  # the gate's verdict, before any call
    sections = request["sections"]
    targets = LAYOUT[stage]
    records = []
    for index, section in enumerate(sections, start=1):
        for template, width, height in targets:
            slot = template.format(n=index)
            out = run_dir / stage / slot
            ratio = target_ratio(stage, template, section, run_dir, index)
            style = style_refs(stage, request, provider.name == "kie")
            refs = prior_slices(stage, run_dir, index, template)
            typed = section_typed_references(
                stage, width, resolve_composition(section, index, request), section,
                request_form(request), request)
            prompt, prompt_sizes = stage_prompt(
                stage, section, index, width, request, ratio, with_sizes=True,
                strict_floor=provider.name == "kie", typed_refs=typed)
            if provider.name == "kie":
                require_brand_line(stage, prompt)
            base = base_identity(run_dir, request, stage=stage, slot=slot,
                                 viewport=f"{width}x{height}")
            if not overwrite:
                existing = reusable_record(run_dir, base, out)
                if existing is not None:
                    entry = dict(existing, reused=True, provider=provider.name, mode=provider.mode)
                    records.append(entry)
                    print(f"REUSED {stage} {entry.get('file')} sha256={entry.get('sha256')} "
                          f"attempt={entry.get('attempt')} (inputs unchanged)")
                    continue
            ident = allocate_attempt(run_dir, base)
            staged = run_dir / stage / ATTEMPT_DIR / _target_slug(ident) / slot
            job = {
                "stage": stage, "index": index, "section": section,
                "out": staged, "final": out, "run_dir": run_dir,
                "width": width, "height": height, "slot": slot, "identity": ident,
                "label": f"{stage} section {index:02d} {width}px",
                "ratio": ratio,
                "references": [str(p) for p in refs] + [r["url"] for r in typed],
                "typed_references": [{"id": r.get("id"), "type": r.get("type"), "sha256": r.get("sha256")}
                                     for r in typed],
                "style_refs": style,
                "prompt": prompt, "prompt_sizes": prompt_sizes,
            }
            result = provider.generate(job, request)
            if result.get("delivered") is None and Path(job["out"]).is_file():
                result["delivered"] = promote_attempt(run_dir, job)  # a provider that does not promote itself
            if result.get("delivered", True) is False:
                entry = {"stage": stage, "section_id": section["section_id"],
                         "section_number": index, "slot": slot, "attempt": ident["attempt"],
                         "identity": ident, "historical": True,
                         "file": (result.get("saved_paths") or [None])[0],
                         "provider": result.get("provider"), "mode": result.get("mode"),
                         "task_id": result.get("task_id"),
                         "reason": "a later attempt already owns this artifact"}
                write_attempt_result(run_dir, ident, entry)
                print(f"HISTORICAL {stage} {slot} attempt={ident['attempt']} "
                      "did not replace the current artifact")
                continue
            if not out.is_file():
                raise ExecutorError(f"{out} was not delivered; the attempt cannot be recorded")
            actual = png_size(out)
            entry = {
                "section_id": section["section_id"],
                "section_number": index,
                "file": str(out.relative_to(run_dir)),
                "slot": slot,
                "attempt": ident["attempt"],
                "identity": ident,
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
            write_attempt_result(run_dir, ident, dict(entry, state="settled"))
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
        "start_check": start,
        "note": "this record is not a gate receipt and cannot close a stage",
        "images": records,
        "composition": composition,
    }

    def merge(data):
        # Both sides' record keys survive: main's generated_at and S1's start_check are as much
        # part of the stage record as F21's provider/mode/model/composition.
        data.update({k: record[k] for k in ("provider", "mode", "model", "generated_at",
                                            "start_check", "note", "composition")})
        merged = {e.get("file"): e for e in (data.get("images") or [])
                  if isinstance(e, dict) and e.get("file")}
        for entry in records:
            if entry.get("file"):
                merged[entry["file"]] = entry
        data["images"] = [merged[k] for k in sorted(merged)]

    return _stage_record_edit(run_dir, stage, merge)


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
    base = base_identity(run_dir, request, stage=BOARD_STAGE, slot="board",
                         viewport=f"{job['width']}x{job['height']}")
    if not overwrite:
        existing = reusable_record(run_dir, base, job["out"])
        if existing is not None:
            print(f"REUSED {BOARD_STAGE} {existing.get('file')} "
                  f"sha256={existing.get('sha256')} (inputs unchanged)")
            return board.load_record(run_dir)
    job.update(identity=allocate_attempt(run_dir, base), run_dir=run_dir, final=job["out"],
               slot="board")
    board.build_overflow_sheet(plan, run_dir)  # real images that do not fit the attachments
    result = provider.generate(job, request)
    try:
        revision = int(board.load_record(run_dir).get("revision", 0)) + 1
    except board.BoardError:
        revision = 1
    record = board.write_record(run_dir, plan, job["prompt"], result, revision)
    write_attempt_result(run_dir, job["identity"],
                         {"stage": BOARD_STAGE, "slot": "board", "state": "settled",
                          "file": str(job["out"].relative_to(run_dir)),
                          "sha256": sha256(job["out"]), "task_id": result.get("task_id"),
                          "provider": result.get("provider"), "mode": result.get("mode")})
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
    start = require_stage_start(run_dir, stage, provider.name, item)  # the item gate, before any read
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
    slot = inventory_slot(run_dir, item)
    circle = circle_image.entry_shape(slot) == "circle"
    width, height = (1024, 1024) if circle else (1440, 760)
    base = base_identity(run_dir, request, stage=stage, slot=item,
                         viewport=f"{width}x{height}")
    if not overwrite:
        existing = reusable_record(run_dir, base, out)
        if existing is not None:
            print(f"REUSED {stage} {item} {existing.get('file')} "
                  f"sha256={existing.get('sha256')} attempt={existing.get('attempt')} "
                  "(inputs unchanged)")
            return existing
    if out.exists() and not overwrite:
        moved = stale_output(run_dir, stage, out)
        print(f"STALE {stage} {item} moved to {moved.relative_to(run_dir)} "
              "(no verified output for the current plan revision)")
    ident = allocate_attempt(run_dir, base)
    staged = run_dir / stage / ATTEMPT_DIR / _target_slug(ident) / out.name
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
           "out": staged, "final": out, "run_dir": run_dir, "slot": item, "identity": ident,
           "width": width, "height": height,
           "label": f"{item} {stage}",
           "ratio": "1:1" if circle else request.get("item_ratio"), "references": [],
           "prompt": prompt}
    result = provider.generate(job, request)
    if result.get("delivered") is None and Path(job["out"]).is_file():
        result["delivered"] = promote_attempt(run_dir, job)  # a provider that does not promote itself
    entry = {"stage": stage, "item": item, "slot": item, "attempt": ident["attempt"],
             "identity": ident, "file": str(out.relative_to(run_dir)),
             "provider": result.get("provider"), "mode": result.get("mode"),
             "model": result.get("model"), "task_id": result.get("task_id"), "at": now_iso(),
             "start_check": start}
    if result.get("delivered", True) is False:
        entry.update(historical=True, status="historical",
                     file=(result.get("saved_paths") or [None])[0],
                     reason="a later attempt already owns this artifact")
        write_attempt_result(run_dir, ident, entry)
        print(f"HISTORICAL {stage} {item} attempt={ident['attempt']} "
              "did not replace the current artifact")
        return entry
    circle_record = mask_circle_slot(out, run_dir, stage, slot) if circle else None
    if circle_record and result.get("receipt"):  # the receipt keeps the provider's bytes; the mask is derived
        try:
            _kie74_receipt().rebind_derived(Path(result["receipt"]), run_dir, circle_record["raw_file"],
                                            str(out.relative_to(run_dir)))
        except ValueError as exc:
            raise ExecutorError(f"transport receipt cannot follow the circle mask of {out.name}: {exc}")
    entry["sha256"] = sha256(out)
    entry["start_check"] = start  # S1's gate verdict travels on every item record
    record_bleed(entry, out, request, provider, stage)
    if circle_record:
        entry["circle"] = circle_record
    write_attempt_result(run_dir, ident, dict(entry, state="settled"))

    def merge(data):
        data["provider"] = provider.name
        data["mode"] = provider.mode
        data["model"] = request.get("model") or ("stub-model" if provider.name == "stub" else None)
        # main's record shape survives the F21 merge: the note and the timestamp it always wrote.
        data["note"] = "this record is not a gate receipt and cannot close a stage"
        data["generated_at"] = now_iso()
        data.setdefault("items", [])
        data.setdefault("history", [])
        data["items"] = [e for e in data["items"]
                         if isinstance(e, dict) and e.get("item") != item] + [entry]
        data["items"].sort(key=lambda e: str(e.get("item") or ""))

    _stage_record_edit(run_dir, stage, merge)
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
            kind = request.get("page_kind")
            print(f"PREFLIGHT_PAGE page_role={page_kinds.data()['page_role']} "
                  f"page_kind={kind or 'undeclared'}"
                  + (f" label={page_kinds.entry(kind)['tag']!r} "
                     f"action={page_kinds.entry(kind)['action']} "
                     f"canonical_sequence_len={len(page_kinds.sequence(kind, check[0]))}"
                     if kind and check else ""))
            if check:
                print(f"PREFLIGHT_SECTIONS copy_version={check[0]} "
                      f"sections={len(check[1])} canonical_ids={','.join(check[1])} "
                      f"page_role={request.get('page_role') or 'landing'} "
                      f"checked_against={'; '.join(check[2]) or 'request only'}")
            refused = 0
            refs = list(dict.fromkeys(str(r) for r in request.get("references") or []))
            known = [r for r in refs if reference_use.lookup(r)]
            print(f"PREFLIGHT_REFERENCES total={len(refs)} library={len(known)} "
                  f"not_in_library={len(refs) - len(known)} "
                  f"roles={request.get('reference_roles') or '-'}")
            for stage in stages:
                for index, section in enumerate(request["sections"], start=1):
                    cta = " | ".join(cta_labels(section)) or "-"
                    print(f"PREFLIGHT_CTA {stage} {section['section_id']} -> {cta}")
                    for template, width, _height in LAYOUT[stage]:
                        name = template.format(n=index)
                        try:
                            ratio = target_ratio(stage, template, section, run_dir, index)
                            resolved = resolve_composition(section, index, request)
                            typed = section_typed_references(stage, width, resolved, section,
                                                             request_form(request), request)
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
                        print(f"PREFLIGHT_BLOCKS {stage} {name} "
                              f"page_role={page_role.declared_role(run_dir, request)} "
                              f"blocks={','.join(sizes['blocks'])}")
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
        if provider.name == "kie":
            # F21 step 2: an unresolved submit is reconciled BEFORE a new paid job is issued.
            for outcome in reconcile_uncertain(run_dir, provider.transport):
                print(f"RECONCILE {outcome.get('id')} state={outcome.get('state')} "
                      f"task={outcome.get('task_id') or '-'} {outcome.get('reason') or ''}".rstrip())
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
            record = run_stage(stage, run_dir, request, provider, args.request, args.overwrite)
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


def _self_check() -> int:
    """The F21 lifecycle's own runnable check: identity, accepted-before-wait, held
    reservations, historical late attempts and resume. No network, no paid call."""
    fails = []
    png = PNG_MAGIC + b"\x00" * 48
    ADAPTER_NAME = "74-kie-live-adapter"

    class FakeTransport:
        """A stand-in for Skill 74 in this check only; production always shells the adapter."""

        def __init__(self, task_id="sbw-selftask-1", balances=(100.0, 99.0), wait=None, save=None):
            self.task_id, self.balances, self.i = task_id, list(balances), 0
            self.calls, self._wait, self._save = [], wait, save

        def credits(self):
            value = self.balances[min(self.i, len(self.balances) - 1)]
            self.i += 1
            return value

        def submit(self, req_path):
            self.calls.append("submit")
            return {"state": "queued", "task_id": self.task_id, "adapter_mode": "active"}

        def wait(self, task_id, timeout=None):
            self.calls.append("wait")
            if self._wait:
                return self._wait(task_id)
            return {"state": "success", "task_id": task_id}

        def save(self, task_id, out_dir, info=None):
            self.calls.append("save")
            if self._save:
                return self._save(task_id, out_dir)
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            dest = Path(out_dir) / f"{task_id}.png"
            dest.write_bytes(png + str(task_id).encode("utf-8"))
            return {"state": "success", "task_id": task_id, "saved_paths": [str(dest)],
                    "adapter": ADAPTER_NAME, "adapter_mode": "active", "backend": "native-live",
                    "provider": "kie", "model_id": "selftest-model", "result_urls": []}

    def fresh(root, name="run-selfcheck"):
        d = Path(root) / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "intake.json").write_text(json.dumps({"run_id": name, "image_cap": 6}))
        return d

    def ledger(run):
        return json.loads((run / LEDGER).read_text(encoding="utf-8"))["calls"]

    def job_for(run, request, stage, slot, width, height):
        base = base_identity(run, request, stage=stage, slot=slot, viewport=f"{width}x{height}")
        ident = allocate_attempt(run, base)
        # F18 (kept from main): the paid boundary freezes and re-checks the prompt against the
        # model's recorded band, so this fixture uses an in-band prompt. The check then measures
        # the F21 lifecycle, not the prompt band.
        return {"stage": stage, "slot": slot, "index": 1, "width": width, "height": height,
                "out": run / stage / ATTEMPT_DIR / _target_slug(ident) / Path(slot).name,
                "final": run / stage / slot, "run_dir": run, "identity": ident,
                "label": slot, "prompt": "x" * 19500, "references": []}

    request = {"model": "gpt-image-2-6/sunburst-text-to-image", "sections": []}

    # A — the identity carries all seven fields and two viewports never collide.
    with tempfile.TemporaryDirectory() as t:
        run = fresh(t)
        desk = job_for(run, request, "desktop-wireframe", "section-01.png", 1440, 760)
        mob = job_for(run, request, "mobile-tablet", "section-01.png", 390, 1080)
        for field in ("run", "plan_revision", "page_instance", "viewport", "stage", "slot", "attempt"):
            if field not in desk["identity"]:
                fails.append(f"A identity: {field} is missing from the request identity")
        if desk["identity"]["key"] == mob["identity"]["key"]:
            fails.append("A identity: two viewports produced the same request key")
        if _target_slug(desk["identity"]) == _target_slug(mob["identity"]):
            fails.append("A identity: two viewports produced the same request folder")

        # B — the job id is persisted BEFORE the wait; a failed wait KEEPS the reservation.
        seen = {}

        def wait_probe(task_id):
            rows = ledger(run)
            seen["states"] = [row_state(r) for r in rows
                              if r.get("identity", {}).get("key") == desk["identity"]["key"]]
            return {"state": "fail", "task_id": task_id, "credits_consumed": 3}

        probe = FakeTransport(wait=wait_probe)
        try:
            drive_paid_job(run, desk, request, probe, cap=6, label="section-01.png")
            fails.append("B accepted: a failed wait did not stop the job")
        except ExecutorError:
            pass
        if seen.get("states") != ["accepted"]:
            fails.append(f"B accepted: at wait time the reservation was {seen.get('states')}, "
                         "not ['accepted'] (the job id must be persisted before the wait)")
        row = [r for r in ledger(run) if r["identity"]["key"] == desk["identity"]["key"]][0]
        if row_state(row) != "uncertain":
            fails.append(f"B held: a paid failure became {row_state(row)!r}, not 'uncertain'")
        if not row.get("task_id") or not row.get("request_sha256"):
            fails.append("B held: the row carries no task_id/request_sha256")
        try:
            reserve_render(run, 6, "again", identity=desk["identity"], attempt=1)
            fails.append("B second job: another paid job was allowed while the first is held")
        except ExecutorError:
            pass

        # C — an interrupted local save also keeps the reservation.
        other = job_for(run, request, "mobile-tablet", "section-01.png", 390, 1080)
        broke = FakeTransport(task_id="sbw-selftask-2",
                              save=lambda tid, out: {"state": "fail", "task_id": tid,
                                                     "error": {"code": "network"}})
        try:
            drive_paid_job(run, other, request, broke, cap=6, label="section-01.png")
            fails.append("C save: a failed save did not stop the job")
        except ExecutorError:
            pass
        row = [r for r in ledger(run) if r["identity"]["key"] == other["identity"]["key"]][0]
        if row_state(row) != "uncertain":
            fails.append(f"C save: an interrupted save became {row_state(row)!r}, not 'uncertain'")

    # D — a definitive rejection is the ONLY release; a late old attempt never overwrites.
    with tempfile.TemporaryDirectory() as t:
        run = fresh(t)
        first = job_for(run, request, "desktop-wireframe", "section-01.png", 1440, 760)
        rejected = FakeTransport()
        rejected.submit = lambda p: (rejected.calls.append("submit"),
                                     {"state": "fail", "error": {"code": "validation_failed"}})[1]
        try:
            drive_paid_job(run, first, request, rejected, cap=6, label="section-01.png")
            fails.append("D release: a rejected request was not stopped")
        except ExecutorError:
            pass
        row = [r for r in ledger(run) if r["identity"]["key"] == first["identity"]["key"]][0]
        if row_state(row) != "released":
            fails.append(f"D release: a pre-acceptance rejection became {row_state(row)!r}")

        newer = job_for(run, request, "desktop-wireframe", "section-01.png", 1440, 760)
        drive_paid_job(run, newer, request, FakeTransport(task_id="sbw-selftask-new"),
                       cap=6, label="section-01.png")
        current = sha256(newer["final"])
        drive_paid_job(run, first, request, FakeTransport(task_id="sbw-selftask-old"),
                       cap=6, label="section-01.png")
        if sha256(first["final"]) != current:
            fails.append("D late attempt: the older attempt overwrote the current artifact")
        if read_json_file(current_pointer_path(run, first["identity"]))["attempt"] != newer["identity"]["attempt"]:
            fails.append("D late attempt: the older attempt took the current pointer back")

    # E — resume reuses a verified output; a changed dependency invalidates it.
    with tempfile.TemporaryDirectory() as t:
        run = fresh(t)
        (run / "copy").mkdir()
        (run / "copy" / "copy-manifest.json").write_text(json.dumps({"sections": ["1"]}))
        one = job_for(run, request, "desktop-wireframe", "section-01.png", 1440, 760)
        drive_paid_job(run, one, request, FakeTransport(task_id="sbw-selftask-r1"),
                       cap=6, label="section-01.png")
        again = base_identity(run, request, stage="desktop-wireframe", slot="section-01.png",
                              viewport="1440x760")
        if reusable_record(run, again, one["final"]) is None:
            fails.append("E resume: a verified intact output was not offered for reuse")
        (run / "copy" / "copy-manifest.json").write_text(json.dumps({"sections": ["1", "2"]}))
        changed = base_identity(run, request, stage="desktop-wireframe", slot="section-01.png",
                                viewport="1440x760")
        if changed["plan_revision"] == again["plan_revision"]:
            fails.append("E stale: a changed copy source did not change the plan revision")
        if reusable_record(run, changed, one["final"]) is not None:
            fails.append("E stale: an output was reused after its copy source changed")
        moved = stale_output(run, "desktop-wireframe", one["final"])
        if not moved or not moved.is_file() or one["final"].exists():
            fails.append("E stale: the superseded output was not moved aside")

    if fails:
        print("stage_executor F21 lifecycle self-check -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("stage_executor F21 lifecycle self-check -> PASS (identity 7 fields + viewport split, "
          "job id persisted before wait, failed wait/save keep the reservation, second paid job "
          "refused while held, release only on pre-acceptance rejection, late old attempt "
          "historical, resume reuses verified output and invalidates on a changed dependency)")
    return 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(_self_check())
    sys.exit(main())
