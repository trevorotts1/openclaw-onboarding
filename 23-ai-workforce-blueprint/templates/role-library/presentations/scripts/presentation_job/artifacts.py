"""Validity predicates for banked artifacts.
Each returns (ok: bool, reason: str). Pure functions -- no engine imports.
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
    try: json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc: return False, f"{path} is not valid JSON: {exc}"
    return True, ""

def validate_image(path: Path, recorded_sha=None, render_manifest=None) -> Tuple[bool, str]:
    ok, reason = _exists_is_file(path)
    if not ok: return ok, reason
    data = path.read_bytes()
    if len(data) < 8: return False, f"{path} is too short to be a PNG ({len(data)} bytes)"
    PNG_SIG = b"\x89PNG\r\n\x1a\n"
    if data[:8] != PNG_SIG: return False, f"{path} does not start with PNG signature"
    pos, found = 8, False
    while pos + 8 <= len(data):
        cl = struct.unpack(">I", data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] == b"IEND": found = True
        pos += 12 + cl
    if not found: return False, f"{path} is missing terminal IEND chunk (truncated PNG)"
    if recorded_sha is not None:
        actual = hashlib.sha256(data).hexdigest()
        if actual != recorded_sha: return False, f"{path} sha256 {actual[:12]} != recorded {recorded_sha[:12]}"
    if render_manifest is not None and render_manifest:
        for k in render_manifest:
            if str(path).endswith(str(k)) or Path(k).name == path.name:
                tid = render_manifest[k]
                norm = tid.strip().lower() if isinstance(tid, str) else tid
                if norm in _BAD_TASK_IDS: return False, f"{path} task id {tid!r} is not a real kie task id"
                break
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
    except (zipfile.BadZipFile, OSError) as exc: return False, f"{path} is not a readable zip: {exc}"
    return True, ""

def _sha_check(path: Path, rel_path: str, recorded_sha: Optional[str]) -> Tuple[bool, str]:
    if recorded_sha is not None:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != recorded_sha: return False, f"{rel_path} sha256 {actual[:12]} != recorded {recorded_sha[:12]}"
    return True, ""

def render_manifest_for(run_dir: Path, rel_path: str) -> Dict[str, Any]:
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not pm.is_file(): return {}
    try: obj = json.loads(pm.read_text(encoding="utf-8"))
    except: return {}
    if not isinstance(obj, dict): return {}
    phases = obj.get("phases")
    if not isinstance(phases, list): return {}
    recs = [p for p in phases if isinstance(p, dict) and p.get("phase") == "render"]
    if not recs: return {}
    slides = recs[-1].get("slides")
    if not isinstance(slides, list): return {}
    result = {}
    for e in slides:
        if not isinstance(e, dict): continue
        sn = e.get("slide")
        if sn is not None: result[f"renders/slide-{int(sn):03d}.png"] = str(e.get("taskId", ""))
    return result

_PROMPT_FLOOR = 9000

def validate_artifact(run_dir: Path, rel_path: str, manifest: Any,
                      recorded_sha: Optional[str] = None) -> Tuple[bool, str]:
    path = run_dir / rel_path
    if fnmatch.fnmatch(rel_path, "renders/slide-*.png"):
        rm = render_manifest_for(run_dir, rel_path)
        if not rm: return False, f"{rel_path} has no process_manifest.json checkpoint - cannot prove provenance"
        return validate_image(path, recorded_sha=recorded_sha, render_manifest=rm)
    deliverables = getattr(manifest, "deliverables", None) or []
    bn = Path(rel_path).name
    for d in deliverables:
        fn = d.get("filename", "")
        if fn == bn or fn.endswith("/" + bn):
            min_b = int(d.get("min_bytes", 1))
            ext = Path(fn).suffix.lower()
            if ext == ".pptx": return validate_pptx(path, min_b)
            if ext == ".pdf": return validate_pdf(path, min_b)
            if ext == ".png":
                ok, r = _exists_is_file(path)
                if not ok: return ok, r
                ok, r = _check_floor(path, min_b)
                if not ok: return ok, r
                ok, r = _sha_check(path, rel_path, recorded_sha)
                if not ok: return ok, r
                return True, ""
            if ext in (".md", ".html", ".mp3"):
                ok, r = validate_text(path, min_b)
                if not ok: return ok, r
                ok, r = _sha_check(path, rel_path, recorded_sha)
                if not ok: return ok, r
                return True, ""
            return validate_text(path, min_b)
    ext = Path(rel_path).suffix.lower()
    if ext == ".txt": return validate_text(path, _PROMPT_FLOOR)
    if ext == ".json": return validate_json(path, min_bytes=2)
    return False, f"no validity predicate for {rel_path} - refusing to reuse it"
