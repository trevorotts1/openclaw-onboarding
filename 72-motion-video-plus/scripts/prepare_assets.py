"""Asset preparation layer for Skill 72 Motion Graphics V2 (MG-011).

The contracts layer (scripts/motion_contracts.py) validates the serialized
shape of a job. This module resolves the job's asset manifest to actual
bytes before any scene coding or rendering starts (directive Section 16.8:
SCHEMA_VALID -> prepare assets -> INPUTS_READY). For every asset declared
in assets.json it verifies:

- the local file exists and stays inside the job directory;
- the file's real sha256 equals the recorded sha256 (a changed image
  changes the hash and invalidates every scene that uses the asset);
- the real raster dimensions, read from the file bytes with stdlib
  parsers only (PNG, JPEG, GIF, WebP headers; SVG attributes);
- the detected media type agrees with the declared manifest kind;
- the usage rules of Section 16.6 rule 7: embed_original bytes must be
  the recorded original (a redrawn logo fails the hash check, it is never
  silently accepted), approved_derivative assets must name their source
  asset and an approval record, and reference_only assets must never be
  embedded by a scene or storyboard beat.

The shipped assets schema (references/contracts-v2.schema.json, $defs
assets) carries id, path, sha256, kind, usage, rights_ref and
focal_point. It does not yet carry dimensions, provenance source,
rights status, intended role, crop constraints, protected regions,
permitted edits, per-asset placement, an explicit required flag, or
derivative linkage. Until the schema grows those fields, they are
recorded in the preparation-layer sidecar asset-provenance.json in the
job directory, keyed by asset id, and enforced here. See
references/asset-intake.md for the field list and the schema-gap note.

Missing required assets are targeted blockers: the report names the
asset and the scenes waiting on it, while independent assets still
verify. Missing optional assets (declared but referenced by no scene or
beat and not marked required in the sidecar) are warnings only.

Exit codes follow directive Section 16.9: 0 ready, 2 contract problems
(MG_SCHEMA_INVALID), 3 required input missing (MG_INPUT_MISSING),
4 approval missing (MG_APPROVAL_REQUIRED), 9 integrity failure
(MG_HASH_MISMATCH, MG_SECURITY_VIOLATION). When several classes exist,
the first blocking class wins in the order security, validation,
dependency, authority.

CLI:
    python3 scripts/prepare_assets.py prepare <job_dir> [--report PATH]

Prints one JSON preparation report to stdout. With --report, the same
report is also persisted atomically at PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motion_contracts  # noqa: E402

SCHEMA_INVALID = "MG_SCHEMA_INVALID"
INPUT_MISSING = "MG_INPUT_MISSING"
APPROVAL_REQUIRED = "MG_APPROVAL_REQUIRED"
HASH_MISMATCH = "MG_HASH_MISMATCH"
SECURITY_VIOLATION = "MG_SECURITY_VIOLATION"

# Blocking order (Section 16.9): security stops immediately, then
# validation, then dependency, then authority.
CATEGORY_RANK = {
    SECURITY_VIOLATION: 0,
    HASH_MISMATCH: 0,
    SCHEMA_INVALID: 1,
    INPUT_MISSING: 2,
    APPROVAL_REQUIRED: 3,
}
CATEGORY_EXIT = {
    SECURITY_VIOLATION: 9,
    HASH_MISMATCH: 9,
    SCHEMA_INVALID: 2,
    INPUT_MISSING: 3,
    APPROVAL_REQUIRED: 4,
}

SIDECAR_NAME = "asset-provenance.json"

# Media types the byte sniffers can prove, per manifest kind. Kinds whose
# containers are not sniffed (video, audio, font beyond magic bytes) are
# reported as unverified rather than guessed.
IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
KIND_MEDIA_TYPES = {
    "image": IMAGE_MEDIA_TYPES,
    "svg": {"image/svg+xml"},
    "font": {"font/ttf", "font/otf", "font/woff", "font/woff2"},
    "video": {"video/mp4", "video/webm"},
    "audio": {"audio/wav", "audio/mpeg"},
}


def _finding(category: str, path: str, message: str) -> dict:
    return {"category": category, "path": path, "message": message}


def _load_json(path: Path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Stdlib byte sniffing: media type and raster dimensions.
# ---------------------------------------------------------------------------

def _png_dimensions(data: bytes):
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return {"width": width, "height": height}


def _jpeg_dimensions(data: bytes):
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            pos += 2
            continue
        if marker == 0xDA:  # start of scan: dimensions would have appeared already
            return None
        length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
        if length < 2 or pos + 2 + length > len(data):
            return None
        if marker in sof_markers:
            if length < 7:
                return None
            height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
            return {"width": width, "height": height}
        pos += 2 + length
    return None


def _gif_dimensions(data: bytes):
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return {"width": width, "height": height}


def _webp_dimensions(data: bytes):
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    if data[12:16] == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return {"width": width, "height": height}
    return None


def _svg_dimensions(data: bytes):
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    stripped = text.lstrip()
    if not (stripped.startswith("<svg") or stripped.startswith("<?xml")):
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    tag = root.tag.rsplit("}", 1)[-1]
    if tag != "svg":
        return None
    width = root.get("width")
    height = root.get("height")
    if width and height:
        try:
            return {"width": int(float(width)), "height": int(float(height))}
        except ValueError:
            pass
    viewbox = root.get("viewBox")
    if viewbox:
        parts = viewbox.replace(",", " ").split()
        if len(parts) == 4:
            try:
                return {"width": int(float(parts[2])), "height": int(float(parts[3]))}
            except ValueError:
                return None
    return None


def sniff_media(data: bytes) -> tuple[str | None, dict | None]:
    """Return (media_type, dimensions) detected from raw bytes.

    Either value is None when the bytes do not prove it. Detection never
    guesses: an unrecognized payload returns (None, None).
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", _png_dimensions(data)
    if data[:2] == b"\xff\xd8":
        return "image/jpeg", _jpeg_dimensions(data)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", _gif_dimensions(data)
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp", _webp_dimensions(data)
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WAVE":
        return "audio/wav", None
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm", None
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4", None
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return "audio/mpeg", None
    if data[:4] == b"\x00\x01\x00\x00":
        return "font/ttf", None
    if data[:4] == b"OTTO":
        return "font/otf", None
    if data[:4] == b"wOFF":
        return "font/woff", None
    if data[:4] == b"wOF2":
        return "font/woff2", None
    stripped = data.lstrip()
    if stripped.startswith(b"<svg") or stripped.startswith(b"<?xml"):
        svg_dims = _svg_dimensions(data)
        if svg_dims is not None or b"<svg" in data[:1024]:
            return "image/svg+xml", svg_dims
    return None, None


# ---------------------------------------------------------------------------
# Job reading helpers.
# ---------------------------------------------------------------------------

def _collect_references(job_dir: Path) -> dict[str, list[str]]:
    """Map asset id -> sorted list of scene ids that reference it.

    References come from scene files (asset_ids) and storyboard beats
    (asset_ids, attributed to the beat's scene_id). Files that fail to
    parse are ignored here; shape validation is the contracts layer's
    job and is reported through assets.json schema findings only.
    """
    references: dict[str, set[str]] = {}

    def note(asset_ids, scene_id):
        if not isinstance(asset_ids, list) or not isinstance(scene_id, str):
            return
        for asset_id in asset_ids:
            if isinstance(asset_id, str):
                references.setdefault(asset_id, set()).add(scene_id)

    scenes_dir = job_dir / "scenes"
    if scenes_dir.is_dir():
        for scene_path in sorted(scenes_dir.glob("*.json")):
            try:
                scene = _load_json(scene_path)
            except (ValueError, OSError):
                continue
            if isinstance(scene, dict):
                note(scene.get("asset_ids"), scene.get("id"))
    storyboard_path = job_dir / "storyboard.json"
    if storyboard_path.is_file():
        try:
            storyboard = _load_json(storyboard_path)
        except (ValueError, OSError):
            storyboard = None
        if isinstance(storyboard, dict) and isinstance(storyboard.get("beats"), list):
            for beat in storyboard["beats"]:
                if isinstance(beat, dict):
                    note(beat.get("asset_ids"), beat.get("scene_id"))
    return {asset_id: sorted(ids) for asset_id, ids in references.items()}


def _load_sidecar(job_dir: Path, findings: list[dict], warnings: list[dict]) -> dict:
    """Load asset-provenance.json. Absence is recorded, not fatal."""
    path = job_dir / SIDECAR_NAME
    if not path.is_file():
        return {}
    try:
        doc = _load_json(path)
    except (ValueError, OSError) as exc:
        findings.append(
            _finding(SCHEMA_INVALID, SIDECAR_NAME, f"{SIDECAR_NAME} is not parseable JSON: {exc}")
        )
        return {}
    if not isinstance(doc, dict) or not isinstance(doc.get("assets", {}), dict):
        findings.append(
            _finding(
                SCHEMA_INVALID,
                SIDECAR_NAME,
                f"{SIDECAR_NAME} must be a JSON object with an 'assets' object keyed by asset id",
            )
        )
        return {}
    entries = doc.get("assets", {})
    return {k: v for k, v in entries.items() if isinstance(v, dict)}


# ---------------------------------------------------------------------------
# Preparation.
# ---------------------------------------------------------------------------

def prepare_job(job_dir) -> dict:
    """Resolve every declared asset in a job directory to verified bytes.

    Returns the preparation report dict described in the module docstring.
    """
    job_dir = Path(job_dir)
    findings: list[dict] = []
    warnings: list[dict] = []
    asset_reports: list[dict] = []
    blockers: list[dict] = []
    invalidated: set[str] = set()

    if not job_dir.is_dir():
        findings.append(
            _finding(SCHEMA_INVALID, str(job_dir), f"job directory {job_dir} does not exist")
        )
        return _report(job_dir, findings, warnings, asset_reports, blockers, invalidated, [])

    assets_path = job_dir / "assets.json"
    if not assets_path.is_file():
        findings.append(
            _finding(INPUT_MISSING, "assets.json", "required job artifact assets.json is missing")
        )
        return _report(job_dir, findings, warnings, asset_reports, blockers, invalidated, [])
    try:
        assets_doc = _load_json(assets_path)
    except (ValueError, OSError) as exc:
        findings.append(
            _finding(SCHEMA_INVALID, "assets.json", f"assets.json is not parseable JSON: {exc}")
        )
        return _report(job_dir, findings, warnings, asset_reports, blockers, invalidated, [])

    if isinstance(assets_doc, dict):
        for error in motion_contracts.validate_document(assets_doc, "assets"):
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    f"assets.json#{error['path']}",
                    f"assets.json fails assets schema: {error['message']}",
                )
            )
    else:
        findings.append(
            _finding(SCHEMA_INVALID, "assets.json", "assets.json is not a JSON object")
        )
        return _report(job_dir, findings, warnings, asset_reports, blockers, invalidated, [])

    declared = assets_doc.get("assets") if isinstance(assets_doc.get("assets"), list) else []
    references = _collect_references(job_dir)
    sidecar = _load_sidecar(job_dir, findings, warnings)
    declared_ids = [a.get("id") for a in declared if isinstance(a, dict)]
    declared_id_set = {i for i in declared_ids if isinstance(i, str)}

    for asset_id in sorted(sidecar):
        if asset_id not in declared_id_set:
            warnings.append(
                _finding(
                    SCHEMA_INVALID,
                    SIDECAR_NAME,
                    f"provenance sidecar names asset {asset_id!r} which is not declared in assets.json",
                )
            )

    # Scenes referencing undeclared assets cannot be resolved at all.
    for asset_id in sorted(references):
        if asset_id not in declared_id_set:
            findings.append(
                _finding(
                    INPUT_MISSING,
                    f"assets:{asset_id}",
                    f"scenes {references[asset_id]} reference asset {asset_id!r} which is "
                    "not declared in assets.json; its bytes cannot be resolved",
                )
            )
            blockers.append(
                {
                    "asset_id": asset_id,
                    "category": INPUT_MISSING,
                    "reason": "referenced by scenes but not declared in assets.json",
                    "waiting_scenes": references[asset_id],
                }
            )

    seen_ids: set[str] = set()
    for asset in declared:
        if not isinstance(asset, dict):
            continue
        asset_id = asset.get("id")
        if not isinstance(asset_id, str):
            continue
        if asset_id in seen_ids:
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    f"assets.json:{asset_id}",
                    f"duplicate asset id {asset_id!r} in assets.json",
                )
            )
        seen_ids.add(asset_id)

        entry = sidecar.get(asset_id, {})
        referenced_by = references.get(asset_id, [])
        required = bool(referenced_by) or entry.get("required") is True
        provenance_gaps = [
            field
            for field in ("source", "rights_status", "role")
            if not isinstance(entry.get(field), str) or not entry.get(field)
        ]

        report = {
            "id": asset_id,
            "path": asset.get("path"),
            "kind": asset.get("kind"),
            "usage": asset.get("usage"),
            "status": "declared",
            "required": required,
            "referenced_by": referenced_by,
            "embeddable": asset.get("usage") in ("embed_original", "approved_derivative"),
            "sha256_recorded": asset.get("sha256"),
            "sha256_actual": None,
            "media_type_detected": None,
            "dimensions": None,
            "provenance_gaps": provenance_gaps,
            "invalidated_scenes": [],
        }
        asset_reports.append(report)

        # --- Usage rule: reference_only must never be embedded.
        if asset.get("usage") == "reference_only" and referenced_by:
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    f"assets.json:{asset_id}",
                    f"reference_only asset {asset_id!r} is embedded by scenes "
                    f"{referenced_by}; reference_only assets cannot become published content",
                )
            )
            report["status"] = "reference_only_misused"

        # --- Usage rule: an original cannot declare a derivation.
        if asset.get("usage") == "embed_original" and entry.get("derived_from"):
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    f"assets.json:{asset_id}",
                    f"asset {asset_id!r} is declared embed_original but its provenance "
                    "record claims a derivation; classify it approved_derivative instead",
                )
            )

        # --- Resolve the file bytes.
        rel_path = asset.get("path")
        file_bytes = None
        if isinstance(rel_path, str):
            resolved = (job_dir / rel_path).resolve()
            if job_dir.resolve() not in resolved.parents and resolved != job_dir.resolve():
                findings.append(
                    _finding(
                        SECURITY_VIOLATION,
                        f"assets.json:{asset_id}",
                        f"asset {asset_id!r} path {rel_path!r} resolves outside the job directory",
                    )
                )
                report["status"] = "path_escape"
            elif not resolved.is_file():
                if required:
                    findings.append(
                        _finding(
                            INPUT_MISSING,
                            f"assets.json:{asset_id}",
                            f"required asset {asset_id!r} file {rel_path!r} is missing; "
                            f"scenes {referenced_by} are blocked on it",
                        )
                    )
                    blockers.append(
                        {
                            "asset_id": asset_id,
                            "category": INPUT_MISSING,
                            "reason": f"declared file {rel_path!r} is missing",
                            "waiting_scenes": referenced_by,
                        }
                    )
                    report["status"] = "missing"
                else:
                    warnings.append(
                        _finding(
                            INPUT_MISSING,
                            f"assets.json:{asset_id}",
                            f"optional asset {asset_id!r} file {rel_path!r} is missing; "
                            "no scene references it, so independent work continues",
                        )
                    )
                    report["status"] = "missing_optional"
            else:
                try:
                    file_bytes = resolved.read_bytes()
                except OSError as exc:
                    findings.append(
                        _finding(
                            INPUT_MISSING,
                            f"assets.json:{asset_id}",
                            f"asset {asset_id!r} file {rel_path!r} cannot be read: {exc}",
                        )
                    )
                    report["status"] = "unreadable"

        if file_bytes is not None:
            actual_hash = sha256_bytes(file_bytes)
            report["sha256_actual"] = actual_hash
            media_type, dimensions = sniff_media(file_bytes)
            report["media_type_detected"] = media_type
            report["dimensions"] = dimensions

            # --- Hash integrity: the bytes must be the recorded bytes.
            if asset.get("sha256") != actual_hash:
                findings.append(
                    _finding(
                        HASH_MISMATCH,
                        f"assets.json:{asset_id}",
                        f"asset {asset_id!r} bytes hash to {actual_hash}, not the recorded "
                        f"{asset.get('sha256')}; the image changed after its hash was "
                        "recorded, so dependent previews are invalidated and the new "
                        "bytes are not silently accepted",
                    )
                )
                report["status"] = "hash_mismatch"
                report["invalidated_scenes"] = list(referenced_by)
                invalidated.update(referenced_by)

            # --- Media type must agree with the declared kind.
            kind = asset.get("kind")
            allowed = KIND_MEDIA_TYPES.get(kind, set())
            if media_type is None:
                warnings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"assets.json:{asset_id}",
                        f"asset {asset_id!r} media type could not be proven from its "
                        "bytes; detection is unverified, not assumed",
                    )
                )
            elif media_type not in allowed:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"assets.json:{asset_id}",
                        f"asset {asset_id!r} is declared kind {kind!r} but its bytes "
                        f"are {media_type}",
                    )
                )
                if report["status"] == "declared":
                    report["status"] = "media_type_mismatch"

            # --- Sidecar declarations must agree with the measured bytes.
            declared_media = entry.get("media_type")
            if isinstance(declared_media, str) and media_type is not None and declared_media != media_type:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"{SIDECAR_NAME}:{asset_id}",
                        f"provenance for asset {asset_id!r} declares media type "
                        f"{declared_media!r} but the bytes are {media_type}",
                    )
                )
            declared_dims = entry.get("dimensions")
            if isinstance(declared_dims, dict) and dimensions is not None:
                if (
                    declared_dims.get("width") != dimensions["width"]
                    or declared_dims.get("height") != dimensions["height"]
                ):
                    findings.append(
                        _finding(
                            SCHEMA_INVALID,
                            f"{SIDECAR_NAME}:{asset_id}",
                            f"provenance for asset {asset_id!r} declares dimensions "
                            f"{declared_dims.get('width')}x{declared_dims.get('height')} "
                            f"but the bytes measure {dimensions['width']}x{dimensions['height']}",
                        )
                    )

            if report["status"] == "declared":
                report["status"] = "verified"

        # --- Usage rule: a derivative must prove its approval.
        if asset.get("usage") == "approved_derivative":
            derived_from = entry.get("derived_from")
            approval_ref = entry.get("approval_ref")
            problems = []
            if not isinstance(derived_from, str) or not derived_from:
                problems.append("no source asset is named (provenance derived_from)")
            elif derived_from not in declared_id_set:
                problems.append(f"named source asset {derived_from!r} is not declared in assets.json")
            elif derived_from == asset_id:
                problems.append("an asset cannot be its own source")
            if not isinstance(approval_ref, str) or not approval_ref:
                problems.append("no approval record is named (provenance approval_ref)")
            if problems:
                findings.append(
                    _finding(
                        APPROVAL_REQUIRED,
                        f"assets.json:{asset_id}",
                        f"approved_derivative asset {asset_id!r} is unapproved: "
                        + "; ".join(problems),
                    )
                )
                report["status"] = "unapproved_derivative"
                if referenced_by:
                    blockers.append(
                        {
                            "asset_id": asset_id,
                            "category": APPROVAL_REQUIRED,
                            "reason": "derivative approval is not proven: " + "; ".join(problems),
                            "waiting_scenes": referenced_by,
                        }
                    )
            elif report["status"] == "verified":
                report["status"] = "verified_derivative"

    font_requirements = assets_doc.get("font_requirements")
    fonts_report = []
    if isinstance(font_requirements, list):
        for req in font_requirements:
            if isinstance(req, dict):
                fonts_report.append(
                    {
                        "id": req.get("id"),
                        "family_alias": req.get("family_alias"),
                        "status": "deferred_to_runtime_registry",
                    }
                )

    return _report(
        job_dir, findings, warnings, asset_reports, blockers, invalidated, fonts_report
    )


def _report(job_dir, findings, warnings, asset_reports, blockers, invalidated, fonts_report) -> dict:
    findings = sorted(findings, key=lambda f: CATEGORY_RANK.get(f["category"], 99))
    first = findings[0]["category"] if findings else None
    exit_code = CATEGORY_EXIT[first] if first else 0
    state = {
        None: "INPUTS_READY",
        SCHEMA_INVALID: "CONTRACT_INVALID",
        INPUT_MISSING: "INPUT_MISSING",
        APPROVAL_REQUIRED: "APPROVAL_REQUIRED",
        HASH_MISMATCH: "INTEGRITY_FAILURE",
        SECURITY_VIOLATION: "INTEGRITY_FAILURE",
    }[first]
    return {
        "job_dir": str(job_dir),
        "ready": not findings,
        "state": state,
        "exit_code": exit_code,
        "first_error_category": first,
        "findings": findings,
        "warnings": warnings,
        "assets": asset_reports,
        "blockers": blockers,
        "invalidated_scenes": sorted(invalidated),
        "font_requirements": fonts_report,
    }


def _persist_report(report: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a Skill 72 V2 job's assets to verified bytes (MG-011)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser(
        "prepare", help="Prepare and verify every declared asset in a job directory."
    )
    prepare_parser.add_argument("job_dir", help="Path to the job directory.")
    prepare_parser.add_argument(
        "--report",
        help="Also persist the same JSON report atomically at this path.",
        default=None,
    )
    args = parser.parse_args(argv)

    if args.command == "prepare":
        report = prepare_job(Path(args.job_dir))
        if args.report:
            _persist_report(report, Path(args.report))
        print(json.dumps(report, indent=2))
        return int(report["exit_code"])
    return 2


if __name__ == "__main__":
    sys.exit(main())
