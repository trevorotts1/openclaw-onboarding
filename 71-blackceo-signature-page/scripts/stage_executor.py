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

SKILL_ROOT = Path(__file__).resolve().parents[1]
STITCH = SKILL_ROOT / "scripts" / "stitch_sections.py"
HYBRID_BOARD = SKILL_ROOT / "scripts" / "build_hybrid_board.py"
DEFAULT_REQUEST = "production-request.json"
RECORD = "stage-executor-record.json"

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
    "Keep the photography square-cornered",
    "Keep the gold hairline rules",
    "Keep the ivory ground warm",
    "Set the eyebrow in rust",
    "Let the hero carry the script overlay",
    "Keep small text crisp",
    "Render the sheet flat",
)
ABS_PATH = re.compile(r"(?:/Users|/Volumes)/[^\s`'\"]+")
REF_NAME = re.compile(
    r"\b(?:chatgpt-(?:mockup|wireframe)-\d+|set-for-life-[a-z0-9-]+)\.png\b", re.I)
LEAK_LINE = re.compile(
    r"(?i)(/Users/|/Volumes/|\bSHA-256\b|\bBundled path\b|\bReviewed download\b|"
    r"\bEvidence copy\b|Drive folder|crops saved in|Measured with PIL|\balias M4\b|"
    r"^\s*Bytes:\s|"
    r"^\s*[-\s]*Pixels:\s*\d+\s*[x×]\s*\d+|"
    r"^\s*[-\s]*Raster:\s*\d+\s*[x×]\s*\d+|"
    r"(?<!\d)(?:724|2171|2172)(?!\d)|\braster_(?:width|height)\b)")
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
    slot = (section.get("slots") or [{}])[0]
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


def sanitize_prompt(text: str) -> str:
    """Strip provenance a model must not see: local paths, reference
    filenames, hashes, and the reference raster's absolute pixel size.

    The measured 724x2172 raster was being copied verbatim into every
    prompt; the model reproduced that 1:3 canvas and left blank bands.
    Design ratios and tokens stay; the provenance disappears.
    """
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if LEAK_LINE.search(line):
            continue
        if stripped.startswith(("File:", "Selection:", "Unit:", "Builder:", "Date:")):
            continue
        kept.append(line)
    cleaned = REF_NAME.sub("the reference sheet", "\n".join(kept))
    cleaned = ABS_PATH.sub("the reference sheet", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def prompt_cap(model: str | None):
    try:
        policy = json.loads((SKILL_ROOT / "references" / "prompt-budget-policy.json")
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in policy.get("models") or []:
        match = entry.get("match")
        if model and match and str(match) in model and entry.get("unit") == "chars":
            return entry.get("max_chars")
    return None


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
    cta = str(section.get("cta") or "").strip()
    if not cta:
        match = re.search(r"\bCTA:\s*([^\n]+)", copy)
        if match:
            cta = match.group(1).strip().rstrip(".")
    lines = ["VERBATIM COPY — print exactly these strings, character for "
             "character. Do not paraphrase, shorten, reorder, or add text. "
             "Spell every word exactly: do not invent, drop, double, or substitute "
             "characters anywhere:",
             copy]
    if cta:
        lines.append(f'CTA LABEL — print exactly: "{cta}"')
    return "\n".join(lines)


def negative_block() -> str:
    """The skill's own defect-class negative block, applied at the wire."""
    return (
        "NEGATIVE BLOCK — do not duplicate a section number, do not print the "
        "same number twice, do not skip a number. Do not mis-number the 7 steps: "
        "exactly 7 badges reading 1, 2, 3, 4, 5, 6, 7 once each, and exactly 7 "
        "step labels. Do not garble any label, mug slogan, or caption: no "
        "\"BIGNEFIT\", \"BTEP 7\", \"DISCIFIONAL\", \"FREIDOM\", "
        "\"Folow Gnlume Sno Home\", \"widhh\", and no invented, dropped, "
        "doubled, or substituted characters anywhere. Do not print any text that "
        "is not in the verbatim copy above; no placeholder tokens, no agent "
        "notes, no lorem, no bracketed markers, no captions, watermarks, or "
        "production labels.")


def frame_contract(width: int, ratio: str) -> str:
    return (
        "FRAME CONTRACT — this image is ONE section slice, not a full page. "
        f"Fill the entire {width}px-wide frame edge to edge at aspect ratio {ratio}. "
        "Draw the section across the full height of the canvas: no blank bands, no "
        "empty lower region, no letterboxing, no collage of other sections. Do not "
        "reproduce the reference sheet's full-page height or any other section.")


class ExecutorError(Exception):
    """A named failure; the message is printed and the run stops."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_request(run_dir: Path, name: str) -> dict:
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
    for i, s in enumerate(sections):
        if not isinstance(s, dict) or not s.get("section_id"):
            raise ExecutorError(f"sections[{i}] needs section_id")
        s.setdefault("section_name", s["section_id"])
    return data


def stage_prompt(stage: str, section: dict, index: int, width: int,
                 request: dict, ratio: str | None = None) -> str:
    slots = section.get("slots") or []
    slot_words = "; ".join(
        f"{s.get('slot_id', 'slot')} {s.get('aspect_ratio', '')} {s.get('art_direction', '')}".strip()
        for s in slots) or "no image slots"
    values = {
        "stage": stage,
        "section_number": str(index),
        "section_name": section.get("section_name") or section["section_id"],
        "copy": section.get("copy") or "",
        "slots": slot_words,
        "width": str(width),
        "ratio": ratio or "",
        "style": request.get("style") or "",
    }
    template = (request.get("stage_prompts") or {}).get(stage)
    if template:
        try:
            body = template.format(**values)
        except (KeyError, IndexError) as exc:
            raise ExecutorError(
                f"stage_prompts[{stage!r}] has an unknown placeholder: {exc}")
    else:
        body = (f"{stage} build spec, section {index} '{values['section_name']}' "
                f"at {width}px page width. Copy: {values['copy']}. "
                f"Image slots: {slot_words}. {values['style']}").strip()
    copy = str(section.get("copy") or "").strip()
    body = sanitize_prompt(body)
    if copy and copy in body:
        body = re.sub(r"\n{3,}", "\n\n", body.replace(copy, "", 1)).strip()
    blocks = [b for b in (copy_contract(section),
                          frame_contract(width, ratio or ""),
                          negative_block()) if b]
    prompt = "\n\n".join(blocks + [body]).strip()
    cap = prompt_cap(request.get("model"))
    if cap and len(prompt) > cap:
        raise ExecutorError(
            f"{stage} section {index}: prompt is {len(prompt)} chars, over the "
            f"{cap}-char model maximum; cut design prose, never the verbatim copy")
    return prompt


def build_input(job: dict, request: dict) -> dict:
    refs = list(dict.fromkeys(str(r) for r in (request.get("references") or []) +
                              job["references"]))
    base = {"prompt": job["prompt"], "input_urls": refs}
    if job.get("ratio"):
        base["aspect_ratio"] = job["ratio"]
    extra = request.get("input_extra")
    if isinstance(extra, dict):
        base.update(extra)
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


def compose(stage: str, run_dir: Path, provider) -> dict:
    """Run the existing deterministic composers when their inputs exist.

    No composer is invented here: stitch_sections.py and
    build_hybrid_board.py are the repo's own pinned steps, and both
    refuse to run from inputs that do not pass their validation. Stub
    mode never composes: a placeholder is not an approved input.
    """
    if provider.name != "kie":
        return {"status": "skipped", "reason": "stub provider writes placeholders only"}
    stage_dir = run_dir / stage
    if stage in ("desktop-wireframe", "mobile-tablet"):
        if not (stage_dir / "production-record.json").is_file():
            return {"status": "skipped", "reason": "no production-record.json to stitch from"}
        proc = subprocess.run([sys.executable, str(STITCH), str(stage_dir)],
                              capture_output=True, text=True, cwd=str(SKILL_ROOT))
        return {"status": "pass" if proc.returncode == 0 else "fail",
                "command": f"stitch_sections.py {stage_dir}",
                "exit": proc.returncode,
                "output": (proc.stdout + proc.stderr).strip()[:600]}
    if stage == "final-mockups":
        if not (run_dir / "final-mockups" / "hybrid-board.json").is_file():
            return {"status": "skipped", "reason": "no hybrid-board.json to compose from"}
        proc = subprocess.run([sys.executable, str(HYBRID_BOARD), str(run_dir)],
                              capture_output=True, text=True, cwd=str(SKILL_ROOT))
        return {"status": "pass" if proc.returncode == 0 else "fail",
                "command": f"build_hybrid_board.py {run_dir}",
                "exit": proc.returncode,
                "output": (proc.stdout + proc.stderr).strip()[:600]}
    return {"status": "not_applicable"}


def run_stage(stage: str, run_dir: Path, request: dict, provider) -> dict:
    if stage not in LAYOUT:
        raise ExecutorError(f"unknown stage {stage!r}; expected one of {list(STAGES)}")
    sections = request["sections"]
    targets = LAYOUT[stage]
    records = []
    for index, section in enumerate(sections, start=1):
        for template, width, height in targets:
            out = run_dir / stage / template.format(n=index)
            ratio = target_ratio(stage, template, section, run_dir, index)
            refs = prior_slices(stage, run_dir, index, template)
            job = {
                "stage": stage, "index": index, "section": section,
                "out": out, "width": width, "height": height,
                "label": f"{stage} section {index:02d} {width}px",
                "ratio": ratio,
                "references": [str(p) for p in refs],
                "prompt": stage_prompt(stage, section, index, width, request, ratio),
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
                "model": result.get("model"),
                "provider": result.get("provider"),
                "mode": result.get("mode"),
                "task_id": result.get("task_id"),
                "inputs": job["references"],
            }
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
    composition = compose(stage, run_dir, provider)
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


def run_item(run_dir: Path, stage: str, item: str, request: dict, provider,
             overwrite: bool) -> dict:
    prompt_path = run_dir / "image-inventory-prompts" / f"{item}.txt"
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ExecutorError(f"cannot read the item prompt {prompt_path}: {exc}")
    if not prompt:
        raise ExecutorError(f"the item prompt {prompt_path} is empty")
    digits = "".join(ch for ch in item if ch.isdigit())
    if not digits:
        raise ExecutorError(f"item id {item!r} carries no number; cannot derive the delivered name")
    out = run_dir / stage / f"Image-{int(digits):02d}.png"
    if out.exists() and not overwrite:
        raise ExecutorError(f"{out} exists; pass --overwrite to replace it")
    job = {"stage": stage, "index": int(digits), "section": {"section_id": item},
           "out": out, "width": 1440, "height": 760, "label": f"{item} {stage}",
           "ratio": request.get("item_ratio"), "references": [],
           "prompt": prompt}
    result = provider.generate(job, request)
    entry = {"stage": stage, "item": item, "file": str(out.relative_to(run_dir)),
             "sha256": sha256(out), "provider": result.get("provider"),
             "mode": result.get("mode"), "model": result.get("model"),
             "task_id": result.get("task_id"), "at": now_iso()}
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
        if stage not in STAGES:
            print(f"FAIL: unknown stage {stage!r}; expected one of {list(STAGES)}")
            return 2
    try:
        if args.preflight:
            request = load_request(run_dir, args.request)
            for stage in stages:
                for index, section in enumerate(request["sections"], start=1):
                    for template, width, _height in LAYOUT[stage]:
                        ratio = target_ratio(stage, template, section, run_dir, index)
                        prompt = stage_prompt(stage, section, index, width,
                                              request, ratio)
                        refs = prior_slices(stage, run_dir, index, template)
                        print(f"PREFLIGHT {stage} {template.format(n=index)} "
                              f"ratio={ratio} chars={len(prompt)} refs={len(refs)}")
            return 0
        provider = make_provider(args, run_dir)
        if args.item:
            request = load_request(run_dir, args.request) if (run_dir / args.request).is_file() else {}
            entry = run_item(run_dir, args.stage or "image-generation-qc",
                             args.item, request, provider, args.overwrite)
            print(f"ITEM {entry['item']} {entry['file']} provider={entry['provider']} "
                  f"mode={entry['mode']}")
            return 0
        request = load_request(run_dir, args.request)
        for stage in stages:
            record = run_stage(stage, run_dir, request, provider)
            files = len(record["images"])
            print(f"STAGE {stage} images={files} provider={record['provider']} "
                  f"mode={record['mode']} record={stage}/{RECORD}")
            for image in record["images"]:
                print(f"GENERATED {stage} {image['file']} sha256={image['sha256']}")
            comp = record["composition"]
            print(f"COMPOSE {stage} status={comp.get('status')}"
                  + (f" reason={comp.get('reason')}" if comp.get("reason") else ""))
        return 0
    except ExecutorError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
