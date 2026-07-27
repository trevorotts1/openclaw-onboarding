"""Per-artifact validity predicates for checkpoint resume.

Pure functions with no engine imports -- testable in isolation.
Each returns ``(ok: bool, reason: str)``.

Predicate order is contract: (1) exists/is-file, (2) clears byte floor,
(3) sha256 matches recorded value. Returns on first failure so the reason
string names which of the three it was.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from delivery_gate import _BAD_TASK_IDS
except ImportError:
    # delivery_gate.py:160 -- source of truth
    _BAD_TASK_IDS = frozenset({None, "", "native", "placeholder", "none", "null", "n/a"})

_PROMPT_FLOOR = 9000


def validate_text(path: Path, min_bytes: int) -> Tuple[bool, str]:
    if not path.is_file():
        return False, f"{path} does not exist or is not a file"
    size = path.stat().st_size
    if size < min_bytes:
        return False, f"{path} is {size} bytes, below the {min_bytes}-byte floor"
    return True, ""


def validate_json(path: Path, min_bytes: int = 2) -> Tuple[bool, str]:
    ok, why = validate_text(path, min_bytes)
    if not ok:
        return False, why
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"{path} is not valid JSON: {exc}"
    return True, ""


def validate_image(path: Path, recorded_sha: Optional[str] = None,
                   render_manifest: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    if not path.is_file():
        return False, f"{path} does not exist or is not a file"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return False, f"{path} unreadable: {exc}"
    size = len(data)
    if size < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return False, f"{path} is not a PNG (invalid header)"
    pos = 8
    found = False
    while pos + 8 <= size:
        cl = struct.unpack(">I", data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] == b"IEND":
            found = True
            break
        pos += 12 + cl
    if not found:
        return False, f"{path} is a truncated PNG (missing IEND chunk -- {size} bytes)"
    if recorded_sha is not None:
        actual = hashlib.sha256(data).hexdigest()
        if actual != recorded_sha:
            return False, f"{path}: sha256 recorded {recorded_sha[:12]}..., actual {actual[:12]}..."
    if render_manifest is not None:
        keys = [k for k in render_manifest if path.name == Path(k).name]
        if not keys:
            return False, f"{path} has no task id in render manifest -- cannot verify provenance"
        tid = render_manifest[keys[0]]
        if tid in _BAD_TASK_IDS:
            return False, f"{path}: task id {tid!r} is in _BAD_TASK_IDS -- not a real kie bake"
    return True, ""


def validate_pdf(path: Path, min_bytes: int) -> Tuple[bool, str]:
    ok, why = validate_text(path, min_bytes)
    if not ok:
        return False, why
    try:
        data = path.read_bytes()
    except OSError as exc:
        return False, f"{path} unreadable: {exc}"
    if not data.startswith(b"%PDF-"):
        return False, f"{path} is not a PDF (missing %PDF- header)"
    if b"%%EOF" not in data[-1024:]:
        return False, f"{path} is a truncated PDF (missing %%EOF trailer)"
    return True, ""


def validate_pptx(path: Path, min_bytes: int) -> Tuple[bool, str]:
    ok, why = validate_text(path, min_bytes)
    if not ok:
        return False, why
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            if not zf.namelist():
                return False, f"{path} is an empty zip"
    except (zipfile.BadZipFile, OSError) as exc:
        return False, f"{path} is not a valid PPTX (zip open failed): {exc}"
    return True, ""


def render_manifest_for(run_dir: Path, rel_path: str) -> Dict[str, str]:
    """Read the run's own working/checkpoints/process_manifest.json.

    Returns {rel_path: taskId} for the slide matching the parsed slide number,
    or {} if the checkpoint file is absent or has no matching entry.
    """
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not pm.is_file():
        return {}
    try:
        obj = json.loads(pm.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(obj, dict):
        return {}
    phases = obj.get("phases")
    if not isinstance(phases, list):
        return {}
    render_records = [p for p in phases if isinstance(p, dict) and p.get("phase") == "render"]
    if not render_records:
        return {}
    slides = render_records[-1].get("slides")
    if not isinstance(slides, list):
        return {}
    result: Dict[str, str] = {}
    for s in slides:
        if not isinstance(s, dict):
            continue
        sn = s.get("slide")
        if sn is not None:
            result[f"renders/slide-{int(sn):03d}.png"] = str(s.get("taskId", ""))
    return result


def validate_artifact(run_dir: Path, rel_path: str, manifest: Any,
                      recorded_sha: Optional[str] = None) -> Tuple[bool, str]:
    """Pick a predicate for the artifact at run_dir/rel_path and run it.

    Dispatch order:
      1. renders/slide-*.png -> validate_image (by path pattern, NOT extension)
      2. Manifest deliverables_required basename match -> floor from manifest
      3. Known extension families -> hard-coded floor
      4. Refuse (fail-closed)
    """
    path = run_dir / rel_path

    # Branch 1: P4-RENDER's artifact family -- by PATH PATTERN, not extension
    if re.match(r"renders/slide-\d+\.png$", rel_path):
        rm = render_manifest_for(run_dir, rel_path)
        return validate_image(path, recorded_sha=recorded_sha, render_manifest=rm)

    # Branch 2: Deliverable table from the manifest
    deliverables = getattr(manifest, "deliverables", None)
    if deliverables is None and hasattr(manifest, "raw"):
        deliverables = manifest.raw.get("deliverables_required", [])
    if deliverables:
        bn = Path(rel_path).name
        for d in deliverables:
            fn = (d.get("filename", "") if isinstance(d, dict) else getattr(d, "filename", ""))
            if fn == bn or fn.endswith("/" + bn):
                min_b = (int(d.get("min_bytes", 1)) if isinstance(d, dict)
                         else getattr(d, "min_bytes", 1))
                ext = Path(fn).suffix.lower()
                if ext == ".pptx":
                    return validate_pptx(path, min_b)
                if ext == ".pdf":
                    return validate_pdf(path, min_b)
                if ext in (".md", ".html", ".mp3"):
                    return validate_text(path, min_b)
                if ext == ".png":
                    return validate_image(path, recorded_sha=recorded_sha)
                return validate_text(path, min_b)

    # Branch 3: Known extension families
    #   working/prompts/slide-*.txt -> validate_text(min_bytes=9000)
    #     9000 = PROMPT_CHAR_FLOOR. Source of truth:
    #       presentations/scripts/build_deck.py:325
    #       presentations/scripts/prompt_gate.py:89
    #       presentation-render/render_deck.py:84
    if re.match(r"^working/prompts/slide-\d+\.txt$", rel_path):
        return validate_text(path, _PROMPT_FLOOR)

    # working/qc/*.json, working/copy/intake.json -> validate_json(min_bytes=2)
    ext_l = Path(rel_path).suffix.lower()
    if ext_l == ".json" and (re.match(r"^working/qc/.*\.json$", rel_path)
                              or rel_path == "working/copy/intake.json"):
        return validate_json(path, min_bytes=2)

    # Branch 4: Refuse -- fail-closed
    return False, f"no validity predicate for {rel_path} -- refusing to reuse it"
