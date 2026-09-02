'''Per-artifact validity predicates for checkpoint resume.

Pure functions with no engine imports -- testable in isolation.
Each returns ``(ok: bool, reason: str)``.

Predicate order is contract: (1) exists/is-file, (2) clears byte floor,
(3) sha256 matches recorded value. Returns on first failure so the reason
string names which of the three it was.
'''

from __future__ import annotations

import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from delivery_gate import _BAD_TASK_IDS  # type: ignore[import-not-resolved]
except ImportError:
    _BAD_TASK_IDS = frozenset({None, "", "native", "placeholder", "none", "null", "n/a"})

_PROMPT_FLOOR = 9000

# FIX 3 (MASTER Part 8): one presenter-guide floor, scaled, everywhere.
# The banked validator below used to re-derive the scaled floor inline
# (max(min_bytes*n//34, 8192)) with its own slide-count read -- a third
# divergent copy of the floor formula. It now delegates to the single
# helper `presentation_job/deliverable_floors.py` exports:
#     guide_floor(n) = max(1600 * n, 12000)   (W02-B3's module)
# The import is guarded so this module keeps working standalone (and
# before the W02 branch lands in this tree); the fallback computes the
# IDENTICAL formula from the same source, so behaviour never differs.
try:
    try:
        from .deliverable_floors import guide_floor  # type: ignore[import-not-resolved]
    except ImportError:
        from deliverable_floors import guide_floor  # type: ignore[no-redef]
except ImportError:  # pragma: no cover - merge-order safety only
    def guide_floor(n_slides: int) -> int:
        """Local fallback identical to deliverable_floors.guide_floor.

        Keeps artifacts.py importable standalone until (or in case) the
        W02 deliverable_floors.py module is present in this tree.
        """
        return max(1600 * int(n_slides), 12000)


def validate_text(path: Path, min_bytes: int) -> Tuple[bool, str]:
    if not path.is_file():
        return False, f"{path} does not exist or is not a file"
    size = path.stat().st_size
    if size < min_bytes:
        return False, f"{path} is {size} bytes, below the {min_bytes}-byte floor"
    return True, f"{path} ok ({size} bytes, floor {min_bytes})"


def validate_json(path: Path, min_bytes: int = 2) -> Tuple[bool, str]:
    ok, why = validate_text(path, min_bytes)
    if not ok:
        return False, why
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"{path} is not valid JSON: {exc}"
    return True, f"{path} ok (valid JSON, {path.stat().st_size} bytes)"


def validate_image(path: Path, recorded_sha: Optional[str] = None,
                   render_manifest: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
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
            found = True; break
        pos += 12 + cl
    if not found:
        return False, f"{path} is a truncated PNG (missing IEND chunk -- {size} bytes)"
    if recorded_sha is not None:
        actual = hashlib.sha256(data).hexdigest()
        if actual != recorded_sha:
            return False, (f"{path} sha256 mismatch: "
                           f"recorded {recorded_sha[:12]}..., actual {actual[:12]}...")
    if render_manifest is not None:
        path_str = str(path)
        keys = [k for k in render_manifest if path_str.endswith(k) or Path(k).name == path.name]
        if not keys:
            return False, f"{path} has no task id in render manifest"
        tid = render_manifest[keys[0]]
        norm = tid.strip().lower() if isinstance(tid, str) else tid
        if norm in _BAD_TASK_IDS:
            return False, (f"{path} task id {tid!r} is not a real kie task id "
                           f"(found in delivery_gate._BAD_TASK_IDS)")
    return True, f"{path} ok (valid PNG, {size} bytes)"


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
    return True, f"{path} ok (valid PDF, {path.stat().st_size} bytes)"


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
    return True, f"{path} ok (valid PPTX/zip, {path.stat().st_size} bytes)"


def slide_name(ordinal: int) -> str:
    """FIX 108 (MASTER Part 8): the ONE slide-name convention — two digits.

    ``slide_name(7) == "slide-07"``; every producer of a slide filename
    (the renderer's image field, the render manifest map, the banked-render
    validator) resolves names through this helper so no code path can drift
    back to a 3-digit spelling. Ordinals 100+ need no padding (slide-100 is
    already the canonical spelling for both widths), matching the canonical
    prompt-name families in build_deck.py.
    """
    n = int(ordinal)
    return f"slide-{n:02d}" if n < 100 else f"slide-{n}"


def render_manifest_for(run_dir: Path, rel_path: str) -> Dict[str, str]:
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
    recs = [p for p in phases if isinstance(p, dict) and p.get("phase") == "render"]
    if not recs:
        return {}
    slides = recs[-1].get("slides")
    if not isinstance(slides, list):
        return {}
    result: Dict[str, str] = {}
    for s in slides:
        if not isinstance(s, dict):
            continue
        sn = s.get("slide")
        if sn is not None:
            # FIX 108 (extends F58, SMOKE-1 2026-09-01): the renderer's `image`
            # field is authoritative and always spells the canonical TWO-digit
            # name (slide-01.png … slide-12.png, built through build_deck's
            # slide_name()); this map keys through the identical helper so
            # producer and consumer can never diverge again. When a manifest
            # entry carries no `image` field (or a legacy one), BOTH width
            # spellings of the same ordinal are keyed to the same task id:
            # ordinals 1-99 written by pre-FIX-108 renderers exist on disk as
            # slide-00N.png, and the banked validator matches by basename, so
            # omitting the 3-digit key would re-flag those runs invalid on
            # resume — the exact defect this fix removes. Both keys resolve to
            # the SAME ordinal and the SAME taskId, so revalidation accepts the
            # banked render instead of re-baking it through Kie (the PROOF:
            # three consecutive resumes make zero Kie submissions).
            img = s.get("image")
            base = Path(str(img)).name if img else None
            if base and base.startswith("slide-") and base.endswith(".png"):
                result[f"renders/{base}"] = str(s.get("taskId", ""))
            else:
                result[f"renders/{slide_name(int(sn))}.png"] = str(s.get("taskId", ""))
                _three = f"renders/slide-{int(sn):03d}.png"
                result.setdefault(_three, str(s.get("taskId", "")))
    return result


def validate_artifact(run_dir: Path, rel_path: str, manifest: Any,
                      recorded_sha: Optional[str] = None) -> Tuple[bool, str]:
    path = run_dir / rel_path
    if re.match(r"renders/slide-\d+\.png$", rel_path):
        rm = render_manifest_for(run_dir, rel_path)
        if not rm:
            return False, (f"{rel_path} has no process_manifest.json checkpoint "
                           "-- cannot prove provenance")
        return validate_image(path, recorded_sha=recorded_sha, render_manifest=rm)

    deliverables = getattr(manifest, "deliverables", None) or []
    bn = Path(rel_path).name
    for d in deliverables:
        fn = (d.get("filename", "") if isinstance(d, dict) else getattr(d, "filename", ""))
        if fn == bn or fn.endswith("/" + bn):
            min_b = (int(d.get("min_bytes", 1)) if isinstance(d, dict) else getattr(d, "min_bytes", 1))
            # FIX 3 (MASTER Part 8): one scaled guide floor from ONE helper.
            # F43d (SMOKE-1, 2026-09-01) first un-broke this banked-revalidation
            # path (run_phase -> _revalidate_banked read the UNSCALED deliverable
            # spec, so a 12-slide deck's PRESENTER-GUIDE.pdf -- 21,749B of correct
            # content, just fewer slides -- was flagged banked_invalid on EVERY
            # resume and P8.2-GUIDE re-ran each cycle) by scaling inline:
            # max(min_bytes*n//34, 8192), slide count from working/copy/slides*.json.
            # That was a second divergent copy of the floor formula. The banked
            # validator now delegates to the same single helper the guide writer,
            # build_deck and deliverables.py use: deliverable_floors.guide_floor(n).
            # The unscaled spec floor is kept only as the 34-slide reference
            # ceiling that min_b still represents; the enforced floor is
            # guide_floor(n) for every PRESENTER-GUIDE.pdf / -FINAL.pdf row.
            if fn.endswith(("PRESENTER-GUIDE.pdf", "-FINAL.pdf")) or bn in ("PRESENTER-GUIDE.pdf",):
                _ext = Path(fn).suffix.lower()
                if _ext == ".pdf" and min_b >= 51_200:
                    _n = 0
                    try:
                        for _cand in sorted((run_dir / "working/copy").glob("slides*.json")):
                            _data = json.loads(_cand.read_text(encoding="utf-8", errors="replace"))
                            if isinstance(_data, list):
                                _n = len(_data)
                            elif isinstance(_data, dict) and _data.get("slides"):
                                _n = len(_data["slides"])
                            if _n:
                                break
                    except Exception:  # noqa: BLE001 — fall back to the fixed floor
                        pass
                    if _n:
                        min_b = max(guide_floor(_n), 8192)
            ext = Path(fn).suffix.lower()
            if ext == ".pptx": return validate_pptx(path, min_b)
            if ext == ".pdf": return validate_pdf(path, min_b)
            if ext in (".md", ".html", ".mp3"):
                ok, why = validate_text(path, min_b)
                if not ok:
                    return False, why
                if recorded_sha is not None:
                    # F15: hashlib is already imported at module level (top of
                    # this file). A local `import hashlib` here previously made
                    # `hashlib` a LOCAL name for the entire validate_artifact()
                    # function body (Python scoping: any assignment/import to a
                    # name anywhere in a function makes it local throughout),
                    # which raised UnboundLocalError the moment another branch
                    # of this same function referenced module-level `hashlib`
                    # without first passing through this exact line. Removing
                    # the redundant local import restores the module-level
                    # binding for the whole function; behaviour here is
                    # unchanged (hashlib.sha256 resolves exactly as before).
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                    if actual != recorded_sha:
                        return False, (f"{rel_path} sha256 mismatch: "
                                       f"recorded {recorded_sha[:12]}..., actual {actual[:12]}...")
                return True, why
            if ext == ".png": return validate_image(path, recorded_sha=recorded_sha)
            return validate_text(path, min_b)

    if re.match(r"working/prompts/slide-\d+\.txt$", rel_path):
        return validate_text(path, _PROMPT_FLOOR)
    ext = Path(rel_path).suffix.lower()
    if ext == ".json" and (rel_path.startswith("working/qc/") or rel_path == "working/copy/intake.json"):
        return validate_json(path, min_bytes=2)

    # F15: most phases bank an INTERMEDIATE working-set artifact (a research
    # brief, an intake transcript, an arc/structure spec, ...) that is none
    # of the above -- not a slide render, not a registered client
    # deliverable, not a slide prompt .txt, not a working/qc|copy/intake.json
    # file. Before this branch, every one of those fell through to the
    # catch-all refusal below UNCONDITIONALLY, even when the file was
    # present, untouched, and byte-identical to what was banked at phase
    # completion. Live evidence (state.json, run pres-wave-e-zhc-1787175621):
    # every banked_invalid entry across 10 "done" phases carried the exact
    # string "no validity predicate ... refusing to reuse it", and the
    # flagged file's on-disk sha256 matched the recorded sha256 exactly
    # (e.g. working/research/brief-generated.md -> f52f25f5...). That is a
    # coverage gap in this predicate table, not evidence of corruption.
    #
    # The fix extends coverage rather than removing the gate: a sha256 was
    # already recorded for this artifact at bank time (phases.py always
    # populates ps["sha256"] alongside ps["artifacts"]), so when one is
    # supplied here this branch verifies the file exists, is non-empty, AND
    # its actual sha256 matches the recorded one byte-for-byte -- a missing
    # or corrupted file still fails, exactly as before. Only when NO
    # recorded_sha is supplied (an artifact banked with no hash at all, or a
    # caller -- like the existing mystery.bin test -- that never had one to
    # begin with) does this fall through to the unconditional refusal, so a
    # genuinely unclassifiable/unverifiable artifact still refuses to reuse.
    if recorded_sha is not None:
        if not path.is_file():
            return False, f"{path} does not exist or is not a file"
        try:
            data = path.read_bytes()
        except OSError as exc:
            return False, f"{path} unreadable: {exc}"
        if not data:
            return False, f"{path} is empty (0 bytes)"
        actual = hashlib.sha256(data).hexdigest()
        if actual != recorded_sha:
            return False, (f"{rel_path} sha256 mismatch: "
                           f"recorded {recorded_sha[:12]}..., actual {actual[:12]}...")
        return True, (f"{path} ok (sha256 match, {len(data)} bytes -- "
                      "no per-type predicate, verified by recorded hash)")

    return False, f"no validity predicate for {rel_path} -- refusing to reuse it"
