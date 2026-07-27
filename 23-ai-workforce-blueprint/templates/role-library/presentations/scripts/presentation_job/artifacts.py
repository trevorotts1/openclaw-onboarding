"""Validity predicates for banked artifacts.
Each returns (ok: bool, reason: str).  Pure functions -- no engine imports.
Checks in order: (1) exists/file, (2) byte floor, (3) sha256 match.
"""
from __future__ import annotations

import fnmatch, hashlib, json, struct, zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from delivery_gate import _BAD_TASK_IDS
except ImportError:
    _BAD_TASK_IDS = frozenset({None, "", "native", "placeholder", "none", "null", "n/a"})


def _exists_is_file(path: Path) -> Tuple[bool, str]:
    if not path.exists(): return False, f"{path} does not exist"
    if not path.is_file(): return False, f"{path} is not a file"
    return True, ""


def _check_floor(path: Path, min_bytes: int) -> Tuple[bool, str]:
    size = path.stat().st_size
    if size < min_bytes: return False, f"{path} is {size} bytes, below floor of {min_bytes}"
    return True, ""


def validate_text(path: Path, min_bytes: int) -> Tuple[bool, str]:
    ok, reason = _exists_is_file(path)
    if not ok: return ok, reason
    return _check_floor(path, min_bytes)


def validate_json(path: Path, min_bytes: int = 2) -> Tuple[bool, str]:
    ok, reason = validate_text(path, min_bytes)
    if not ok: return ok, reason
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"{path} is not valid JSON: {exc}"
    return True, ""


def validate_image(path: Path, recorded_sha: Optional[str] = None,
                   render_manifest: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    ok, reason = _exists_is_file(path)
    if not ok: return ok, reason
    data = path.read_bytes()
    if len(data) < 8: return False, f"{path} is too short to be a PNG ({len(data)} bytes)"
    PNG_SIG = b"\x89PNG\r\n\x1a\n"
    if data[:8] != PNG_SIG: return False, f"{path} does not start with PNG signature"
    pos, found_iend = 8, False
    while pos + 8 <= len(data):
        chunk_len = struct.unpack(">I", data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] == b"IEND": found_iend = True
        pos += 12 + chunk_len
    if not found_iend: return False, f"{path} is missing terminal IEND chunk (truncated PNG)"
    if recorded_sha is not None:
        actual = hashlib.sha256(data).hexdigest()
        if actual != recorded_sha: return False, f"{path} sha256 {actual[:12]} != recorded {recorded_sha[:12]}"
    if render_manifest:
        rkey = next((k for k in render_manifest if str(path).endswith(str(k)) or Path(k).name == path.name), None)
        if rkey is not None:
            task_id = render_manifest[rkey]
            norm = task_id.strip().lower() if isinstance(task_id, str) else task_id
            if norm in _BAD_TASK_IDS: return False, f"{path} task id {task_id!r} is not a real kie task id"
    return True, ""


def validate_pdf(path: Path, min_bytes: int) -> Tuple[bool, str]:
    ok, reason = validate_text(path, min_bytes)
    if not ok: return ok, reason
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"): return False, f"{path} does not start with %PDF- header"
    if b"%%EOF" not in data[-1024:]: return False, f"{path} is missing %%EOF trailer"
    return True, ""


def validate_pptx(path: Path, min_bytes: int) -> Tuple[bool, str]:
    ok, reason = validate_text(path, min_bytes)
    if not ok: return ok, reason
    if path.read_bytes()[:2] != b"PK": return False, f"{path} does not start with ZIP/PK signature"
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if not zf.namelist(): return False, f"{path} is an empty zip"
    except (zipfile.BadZipFile, OSError) as exc:
        return False, f"{path} is not a readable zip: {exc}"
    return True, ""


def render_manifest_for(run_dir: Path, rel_path: str) -> Dict[str, Any]:
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not pm.is_file(): return {}
    try:
        obj = json.loads(pm.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError): return {}
    if not isinstance(obj, dict): return {}
    phases = obj.get("phases")
    if not isinstance(phases, list): return {}
    recs = [p for p in phases if isinstance(p, dict) and p.get("phase") == "render"]
    if not recs: return {}
    slides = recs[-1].get("slides")
    if not isinstance(slides, list): return {}
    result: Dict[str, Any] = {}
    for entry in slides:
        if not isinstance(entry, dict): continue
        sn = entry.get("slide")
        if sn is not None:
            result[f"renders/slide-{int(sn):03d}.png"] = str(entry.get("taskId", ""))
    return result


_PROMPT_FLOOR = 9000


def validate_artifact(run_dir: Path, rel_path: str, manifest: Any,
                      recorded_sha: Optional[str] = None) -> Tuple[bool, str]:
    path = run_dir / rel_path
    if fnmatch.fnmatch(rel_path, "renders/slide-*.png"):
        rm = render_manifest_for(run_dir, rel_path)
        return validate_image(path, recorded_sha=recorded_sha, render_manifest=rm)
    deliverables = getattr(manifest, "deliverables", None) or []
    basename = Path(rel_path).name
    for d in deliverables:
        fn = d.get("filename", "")
        if fn == basename or fn.endswith("/" + basename):
            min_b = int(d.get("min_bytes", 1))
            ext = Path(fn).suffix.lower()
            if ext == ".pptx": return validate_pptx(path, min_b)
            if ext == ".pdf": return validate_pdf(path, min_b)
            if ext == ".png": return validate_image(path, recorded_sha=recorded_sha)
            if ext in (".md", ".html", ".mp3"): return validate_text(path, min_b)
            return validate_text(path, min_b)
    ext = Path(rel_path).suffix.lower()
    if ext == ".txt": return validate_text(path, _PROMPT_FLOOR)
    if ext == ".json": return validate_json(path, min_bytes=2)
    return False, f"no validity predicate for {rel_path} - refusing to reuse it"
