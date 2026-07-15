#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_site.py — Skill 62 (Cinematic and Web Funnel Engine), build unit U15.

The P11-SITE-BUILD producer CWFE-MANIFEST.json names ("Next.js project and
build receipt"; canonical path `scripts/build_site.py` per spec Section 15).
Materializes `templates/nextjs-app/` + `templates/components/` into a
concrete, per-project Next.js/TypeScript site directory, injects the locked
P3 content-manifest.json's approved copy and the P4 scene-plan.json's visual
journey as a generated data module, copies the resolved P9/P10 scene media
in, runs the real install/lint/typecheck/build toolchain against it, and
writes `build-receipt.json` (structure/build-receipt.schema.json).

This module is the PRODUCER. `scripts/prove_site.py` is the P11 phase gate —
it never trusts this module's own bookkeeping, it independently re-derives
every pass/fail decision from the materialized site_dir on disk (the same
double-check pattern every other prove_*.py in this skill already uses).

Spec Section 17.5 (site gate) enumerates what a generated site must pass:
"install, lint, typecheck, unit tests, production build, routes, media
references, no placeholders, no hardcoded secrets, no broken imports." This
module runs/produces evidence for all of those except "unit tests" (the
generated site ships no component tests of its own in this unit — there is
nothing project-specific to test yet since content/journey are the only
per-project inputs and both are schema-gated upstream by P3/P4's own
provers); "no broken imports" is covered by the real `next build` step,
which cannot succeed with an unresolved import.

Security posture (spec Section 20):
  - `sanitize_slug()` is an ALLOWLIST transform (keep [a-z0-9-] only), not a
    blocklist — a malicious/traversal slug like "../../etc/passwd" cannot
    survive it by construction, it collapses to "etc-passwd".
  - every subprocess call uses an argument array, never `shell=True` /
    string interpolation into a shell.
  - `_sanitize_copy_fragment()` strips <script>/<style> tags, `on*=` event
    handler attributes, and `javascript:`-scheme URLs out of every approved
    copy fragment before it is embedded into the generated data module —
    defense-in-depth on top of the fragments already being locked/approved
    upstream, not a substitute for that gate.
  - no secret value is ever read, embedded, or logged by this module; the
    generated site takes no provider credentials at all (spec 13's site
    runtime is a static/browser artifact, not a server needing secrets).

stdlib only for orchestration (ADR-5); `ffmpeg`/`node`/`npm` are invoked as
external tools via subprocess argument arrays, exactly like every other
build unit that shells out to a real binary (ffmpeg policy, kie adapters).

Exit codes: 0 = build-receipt.json written with status "pass"; 1 = written
with status "failed" (a real failure was captured and recorded, not
swallowed); 2 = usage error (bad CLI args, missing required upstream
artifacts) before any receipt could be meaningfully written.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"
_TEMPLATES_DIR = _SKILL_DIR / "templates"
_NEXTJS_TEMPLATE_DIR = _TEMPLATES_DIR / "nextjs-app"
_COMPONENTS_TEMPLATE_DIR = _TEMPLATES_DIR / "components"
_FIXTURE_DIR = _SKILL_DIR / "tests" / "fixtures" / "site-fixture"

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402
import resolve_content_engine as rce  # noqa: E402

EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2

SCHEMA_VERSION = "1.0.0"
DEFAULT_TOOLCHAIN_TIMEOUT_SECONDS = 600

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

PLACEHOLDER_MARKERS = (
    "lorem ipsum",
    "todo:",
    "fixme",
    "xxx-replace",
    "{{",
    "}}",
    "__cwfe_project_slug__",
)

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"pit-[A-Za-z0-9\-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{20,}"),
    re.compile(r"""["']?(api|secret|access|client)[_-]?(key|token)["']?\s*[:=]\s*["'][A-Za-z0-9\-_]{16,}["']""", re.IGNORECASE),
]


class SiteBuildError(Exception):
    """Raised for a usage/precondition failure (missing upstream artifact,
    invalid slug, missing scene media). Distinct from a toolchain failure
    (bad lint/typecheck/build), which is captured and recorded in the
    receipt rather than raised."""


# ---------------------------------------------------------------------------
# Slug sanitization (spec 20 "sanitize all generated paths and slugs";
# spec 19.4 break-it case "malicious client slug/path traversal")
# ---------------------------------------------------------------------------
def sanitize_slug(raw: str) -> str:
    """Allowlist transform: keep only [a-z0-9-], collapse repeats, trim
    leading/trailing hyphens, cap length. A path-traversal payload like
    "../../../etc/passwd" cannot survive this — every '.', '/', and space
    is discarded, never reinterpreted, so there is no blocklist to bypass."""
    lowered = raw.strip().lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    truncated = collapsed[:63].strip("-")
    if not truncated or not SLUG_PATTERN.match(truncated):
        raise SiteBuildError(
            f"project slug sanitizes to an empty/invalid value from input {raw!r} — refusing to build"
        )
    return truncated


# ---------------------------------------------------------------------------
# Copy fragment sanitization (defense-in-depth on top of the P3 lock)
# ---------------------------------------------------------------------------
class _FragmentSanitizer(HTMLParser):
    _DROPPED_TAGS = {"script", "style"}
    _URL_ATTRS = {"href", "src", "action", "formaction"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._out: List[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._emit_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._emit_tag(tag, attrs, self_closing=True)

    def _emit_tag(self, tag: str, attrs: List[Tuple[str, Optional[str]]], *, self_closing: bool) -> None:
        if tag in self._DROPPED_TAGS:
            if not self_closing:
                self._drop_depth += 1
            return
        if self._drop_depth > 0:
            return
        safe_attrs: List[str] = []
        for name, value in attrs:
            lname = name.lower()
            if lname.startswith("on"):
                continue  # event handlers (onclick=, onerror=, ...)
            if lname in self._URL_ATTRS and value is not None:
                stripped = value.strip().lower()
                if stripped.startswith("javascript:") or stripped.startswith("data:text/html"):
                    continue
            if value is None:
                safe_attrs.append(name)
            else:
                # html.escape(..., quote=True) escapes embedded `"` (and `'`,
                # `<`, `>`, `&`) so a source value that itself contains a
                # double-quote (e.g. from a single-quoted source attribute,
                # `title='x" onmouseover="...'`) cannot break out of the
                # `name="value"` wrapper re-serialized below and smuggle a
                # live attribute (event handler) past the on*= strip above.
                safe_attrs.append(f'{name}="{html.escape(value, quote=True)}"')
        attr_str = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        self._out.append(f"<{tag}{attr_str}{' /' if self_closing else ''}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._DROPPED_TAGS:
            if self._drop_depth > 0:
                self._drop_depth -= 1
            return
        if self._drop_depth > 0:
            return
        self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._drop_depth == 0:
            self._out.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._drop_depth == 0:
            self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._drop_depth == 0:
            self._out.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if self._drop_depth == 0:
            self._out.append(f"<!--{data}-->")

    def result(self) -> str:
        return "".join(self._out)


def sanitize_copy_fragment(html: str) -> str:
    """Strips <script>/<style> content, on*= event-handler attributes, and
    javascript:/data:text/html URL schemes out of an approved copy fragment.
    Defense-in-depth: the fragment is already locked/approved upstream
    (ADR-10, P3's content_hash lock); this never rewrites approved wording,
    it only removes executable payload classes a fragment should never
    legitimately contain."""
    parser = _FragmentSanitizer()
    parser.feed(html)
    parser.close()
    return parser.result()


# ---------------------------------------------------------------------------
# Upstream artifact loading (P3 content-manifest, P4 scene-plan)
# ---------------------------------------------------------------------------
def load_locked_content_manifest(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "content-manifest.json"
    if not path.is_file():
        raise SiteBuildError(f"content-manifest.json not found at {path} — P3-CONTENT must run first")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((_STRUCTURE_DIR / "content-manifest.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(manifest, schema)
    if errors:
        raise SiteBuildError("content-manifest.json failed schema validation: " + "; ".join(errors))
    ok, reason = rce.verify_locked_manifest(manifest)
    if not ok:
        raise SiteBuildError(f"content-manifest.json failed lock verification: {reason}")
    return manifest


def load_scene_plan(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "journey" / "scene-plan.json"
    if not path.is_file():
        raise SiteBuildError(f"journey/scene-plan.json not found at {path} — P4-JOURNEY must run first")
    plan = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((_STRUCTURE_DIR / "scene-plan.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(plan, schema)
    if errors:
        raise SiteBuildError("journey/scene-plan.json failed schema validation: " + "; ".join(errors))
    if not plan.get("scenes"):
        raise SiteBuildError("scene-plan.json has no scenes")
    return plan


def read_copy_sections(manifest: Dict[str, Any]) -> List[Dict[str, str]]:
    """Pairs content-manifest.json's `section_order[i]` with
    `approved_copy_paths[i]` by position — the same implicit index
    correspondence the schema's own two parallel arrays already carry (both
    are populated together by the same content pipeline in the same order).
    Reads and sanitizes each fragment; never rewrites the underlying text."""
    section_order: List[str] = manifest.get("section_order") or []
    copy_paths: List[str] = manifest.get("approved_copy_paths") or []
    if not copy_paths:
        raise SiteBuildError("content-manifest.json has no approved_copy_paths")
    if section_order and len(section_order) != len(copy_paths):
        raise SiteBuildError(
            f"section_order has {len(section_order)} entries but approved_copy_paths has "
            f"{len(copy_paths)} — cannot pair them positionally"
        )
    ids = section_order or [f"section-{i}" for i in range(len(copy_paths))]
    sections: List[Dict[str, str]] = []
    for section_id, raw_path in zip(ids, copy_paths):
        path = Path(raw_path)
        if not path.is_file():
            raise SiteBuildError(f"approved_copy_paths entry does not exist on disk: {raw_path}")
        raw_html = path.read_text(encoding="utf-8")
        sections.append({"id": section_id, "html": sanitize_copy_fragment(raw_html)})
    return sections


# ---------------------------------------------------------------------------
# Scene media resolution (spec 17.5 "media references"; 17.4 "non-empty
# files")
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SceneMedia:
    scene_id: str
    video_src: Path
    poster_src: Path
    video_sha256: str
    poster_sha256: str
    video_bytes: int
    poster_bytes: int


def resolve_scene_media(scene_plan: Dict[str, Any], media_dir: Path) -> List[SceneMedia]:
    if not media_dir.is_dir():
        raise SiteBuildError(f"media directory not found: {media_dir}")
    missing: List[str] = []
    empty: List[str] = []
    resolved: List[SceneMedia] = []
    for scene in scene_plan["scenes"]:
        scene_id = scene["scene_id"]
        video_path = media_dir / f"{scene_id}.mp4"
        poster_path = media_dir / f"{scene_id}.jpg"
        if not video_path.is_file() or not poster_path.is_file():
            missing.append(scene_id)
            continue
        video_bytes = video_path.stat().st_size
        poster_bytes = poster_path.stat().st_size
        if video_bytes == 0 or poster_bytes == 0:
            empty.append(scene_id)
            continue
        resolved.append(
            SceneMedia(
                scene_id=scene_id,
                video_src=video_path,
                poster_src=poster_path,
                video_sha256=_sha256_file(video_path),
                poster_sha256=_sha256_file(poster_path),
                video_bytes=video_bytes,
                poster_bytes=poster_bytes,
            )
        )
    if missing:
        raise SiteBuildError(f"missing scene media (expected {{scene_id}}.mp4/.jpg) for: {', '.join(missing)}")
    if empty:
        raise SiteBuildError(f"zero-byte scene media for: {', '.join(empty)}")
    return resolved


# ---------------------------------------------------------------------------
# Template materialization
# ---------------------------------------------------------------------------
def _dir_hash(root: Path) -> str:
    """Deterministic sha256 over every file's relative path + content under
    root, sorted — a stable fingerprint of the exact template snapshot a
    site was generated from (build-receipt.json's template_source)."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(path.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def materialize_template(site_dir: Path) -> Tuple[str, str]:
    if site_dir.exists():
        shutil.rmtree(site_dir)
    shutil.copytree(_NEXTJS_TEMPLATE_DIR, site_dir)
    shutil.copytree(_COMPONENTS_TEMPLATE_DIR, site_dir / "components")
    return _dir_hash(_NEXTJS_TEMPLATE_DIR), _dir_hash(_COMPONENTS_TEMPLATE_DIR)


def write_project_slug(site_dir: Path, slug: str) -> None:
    pkg_path = site_dir / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    pkg["name"] = slug
    pkg_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")


def copy_scene_media(site_dir: Path, scenes: List[SceneMedia]) -> None:
    media_out = site_dir / "public" / "media"
    media_out.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        shutil.copy2(scene.video_src, media_out / f"{scene.scene_id}.mp4")
        shutil.copy2(scene.poster_src, media_out / f"{scene.scene_id}.jpg")


def write_site_data(
    site_dir: Path,
    *,
    project_id: str,
    architecture: str,
    scene_plan: Dict[str, Any],
    scene_media: List[SceneMedia],
    sections: List[Dict[str, str]],
    manifest: Dict[str, Any],
) -> None:
    media_by_id = {s.scene_id: s for s in scene_media}
    scenes_data = []
    for scene in scene_plan["scenes"]:
        media = media_by_id[scene["scene_id"]]
        scenes_data.append(
            {
                "sceneId": scene["scene_id"],
                "pageSection": scene["page_section"],
                "videoSrc": f"/media/{scene['scene_id']}.mp4",
                "posterSrc": f"/media/{scene['scene_id']}.jpg",
                "durationSeconds": scene["duration_seconds"],
                "crop": {
                    "desktop": scene["crop_rules"]["desktop"],
                    "mobile": scene["crop_rules"]["mobile"],
                },
                "camera": {
                    "motionDirection": scene["camera"]["motion_direction"],
                    "motionSpeed": scene["camera"]["motion_speed"],
                },
                "ctaRelationship": scene["cta_relationship"],
                "videoSha256": media.video_sha256,
                "posterSha256": media.poster_sha256,
            }
        )

    title = manifest.get("copy_qc_receipt", {}).get("title") or project_id.replace("-", " ").title()
    site_data = {
        "meta": {
            "projectId": project_id,
            "title": title,
            "description": f"Cinematic scroll-scrub funnel for {title}.",
            "architecture": architecture,
        },
        "scenes": scenes_data,
        "sections": sections,
        "ctaMap": manifest.get("cta_map", {}),
        "embed": {"allowedAncestors": []},
    }

    lib_dir = site_dir / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    ts_source = (
        '// GENERATED by scripts/build_site.py — do not hand-edit. Regenerate by '
        "re-running the P11 site build against the locked content-manifest.json + "
        "journey/scene-plan.json this file was built from.\n"
        'import type { SiteData } from "@/components/types";\n\n'
        f"export const SITE_DATA: SiteData = {json.dumps(site_data, indent=2)};\n"
    )
    (lib_dir / "site-data.generated.ts").write_text(ts_source, encoding="utf-8")


# ---------------------------------------------------------------------------
# Toolchain execution
# ---------------------------------------------------------------------------
def _run_step(cmd: List[str], cwd: Path, timeout: int) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        output = f"TIMEOUT after {timeout}s: {exc}"
    duration = time.monotonic() - started
    return {"ran": True, "exit_code": exit_code, "duration_seconds": round(duration, 3), "_output": output}


def run_toolchain(site_dir: Path, *, skip: bool, timeout: int) -> Dict[str, Any]:
    empty_step = {"ran": False, "exit_code": None, "duration_seconds": 0.0}
    if skip:
        return {
            "install": dict(empty_step),
            "lint": dict(empty_step),
            "typecheck": dict(empty_step),
            "build": dict(empty_step),
            "_outputs": {},
        }

    outputs: Dict[str, str] = {}
    install = _run_step(["npm", "install", "--no-audit", "--no-fund"], site_dir, timeout)
    outputs["install"] = install.pop("_output")

    if install["exit_code"] != 0:
        return {
            "install": install,
            "lint": dict(empty_step),
            "typecheck": dict(empty_step),
            "build": dict(empty_step),
            "_outputs": outputs,
        }

    lint = _run_step(["npm", "run", "lint"], site_dir, timeout)
    outputs["lint"] = lint.pop("_output")
    typecheck = _run_step(["npm", "run", "typecheck"], site_dir, timeout)
    outputs["typecheck"] = typecheck.pop("_output")
    build = _run_step(["npm", "run", "build"], site_dir, timeout)
    outputs["build"] = build.pop("_output")

    return {"install": install, "lint": lint, "typecheck": typecheck, "build": build, "_outputs": outputs}


# ---------------------------------------------------------------------------
# Placeholder / secret scans (spec 17.5)
# ---------------------------------------------------------------------------
def scan_placeholders(site_dir: Path) -> Tuple[bool, List[str]]:
    matches: List[str] = []
    for path in (site_dir / "lib").glob("*.generated.ts"):
        text = path.read_text(encoding="utf-8").lower()
        for marker in PLACEHOLDER_MARKERS:
            if marker in text:
                matches.append(f"{path.name}: contains {marker!r}")
    return (len(matches) == 0, matches)


def scan_secrets(site_dir: Path) -> Tuple[bool, List[str]]:
    matches: List[str] = []
    candidates = list((site_dir / "lib").glob("*.generated.ts")) + [
        site_dir / "package.json",
        site_dir / "next.config.ts",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                matches.append(f"{path.name}: matched {pattern.pattern}")
    return (len(matches) == 0, matches)


def discover_routes(site_dir: Path) -> List[str]:
    expected = ["app/layout.tsx", "app/page.tsx"]
    return [rel for rel in expected if (site_dir / rel).is_file()]


# ---------------------------------------------------------------------------
# Receipt persistence
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Orchestration entry point
# ---------------------------------------------------------------------------
@dataclass
class BuildResult:
    receipt: Dict[str, Any]
    site_dir: Path
    toolchain_outputs: Dict[str, str] = field(default_factory=dict)


def build_site(
    run_dir: Path,
    *,
    site_dir: Optional[Path] = None,
    media_dir: Optional[Path] = None,
    project_slug: Optional[str] = None,
    skip_toolchain: bool = False,
    toolchain_timeout: int = DEFAULT_TOOLCHAIN_TIMEOUT_SECONDS,
) -> BuildResult:
    manifest = load_locked_content_manifest(run_dir)
    scene_plan = load_scene_plan(run_dir)
    sections = read_copy_sections(manifest)

    resolved_media_dir = media_dir if media_dir is not None else (run_dir / "media")
    scene_media = resolve_scene_media(scene_plan, resolved_media_dir)

    slug = sanitize_slug(project_slug or manifest["project_id"])
    resolved_site_dir = site_dir if site_dir is not None else (run_dir / "site")

    nextjs_hash, components_hash = materialize_template(resolved_site_dir)
    write_project_slug(resolved_site_dir, slug)
    copy_scene_media(resolved_site_dir, scene_media)
    write_site_data(
        resolved_site_dir,
        project_id=manifest["project_id"],
        architecture=scene_plan["architecture"],
        scene_plan=scene_plan,
        scene_media=scene_media,
        sections=sections,
        manifest=manifest,
    )

    toolchain = run_toolchain(resolved_site_dir, skip=skip_toolchain, timeout=toolchain_timeout)
    outputs = toolchain.pop("_outputs")

    no_placeholders, placeholder_matches = scan_placeholders(resolved_site_dir)
    no_secrets, secret_matches = scan_secrets(resolved_site_dir)
    routes = discover_routes(resolved_site_dir)
    routes_ok = set(routes) == {"app/layout.tsx", "app/page.tsx"}
    media_refs_ok = all((resolved_site_dir / "public" / "media" / f"{s.scene_id}.mp4").is_file() for s in scene_media)

    # A skipped toolchain can never count as "pass" — the site gate (spec
    # 17.5) requires install/lint/typecheck/build to have actually run and
    # succeeded. --skip-toolchain exists purely so offline unit tests can
    # exercise the materialization/data-generation/scan logic quickly; it
    # must fail closed rather than silently certifying an unverified build.
    toolchain_ok = (not skip_toolchain) and all(
        toolchain[step]["exit_code"] == 0 for step in ("install", "lint", "typecheck", "build")
    )
    overall_ok = toolchain_ok and no_placeholders and no_secrets and routes_ok and media_refs_ok

    receipt: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": manifest["project_id"],
        "project_slug": slug,
        "site_dir": str(resolved_site_dir),
        "template_source": {"nextjs_app_hash": nextjs_hash, "components_hash": components_hash},
        "content_hash": manifest["content_hash"],
        "scenes": [
            {
                "scene_id": s.scene_id,
                "video_path": f"public/media/{s.scene_id}.mp4",
                "poster_path": f"public/media/{s.scene_id}.jpg",
                "video_sha256": s.video_sha256,
                "poster_sha256": s.poster_sha256,
                "video_bytes": s.video_bytes,
                "poster_bytes": s.poster_bytes,
            }
            for s in scene_media
        ],
        "sections": [s["id"] for s in sections],
        "routes": routes,
        "steps": toolchain,
        "checks": {
            "no_placeholders": no_placeholders,
            "no_hardcoded_secrets": no_secrets,
            "media_references_resolve": media_refs_ok,
        },
        "status": "pass" if overall_ok else "failed",
        "created_at": _now(),
    }

    schema = json.loads((_STRUCTURE_DIR / "build-receipt.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        raise SiteBuildError("generated build-receipt.json failed its own schema: " + "; ".join(errors))

    _atomic_write_json(run_dir / "build-receipt.json", receipt)

    if not overall_ok:
        details = []
        if not toolchain_ok:
            if skip_toolchain:
                details.append("toolchain skipped (--skip-toolchain) — cannot count as a pass")
            for step in ("install", "lint", "typecheck", "build"):
                if toolchain[step]["ran"] and toolchain[step]["exit_code"] != 0:
                    details.append(f"{step} exit={toolchain[step]['exit_code']}")
        if not no_placeholders:
            details.append(f"placeholders: {placeholder_matches}")
        if not no_secrets:
            details.append(f"secrets: {secret_matches}")
        if not routes_ok:
            details.append(f"routes missing, found: {routes}")
        if not media_refs_ok:
            details.append("media references did not resolve on disk")
        raise SiteBuildError("site build failed: " + "; ".join(details))

    return BuildResult(receipt=receipt, site_dir=resolved_site_dir, toolchain_outputs=outputs)


def _self_test() -> bool:
    sys.path.insert(0, str(_FIXTURE_DIR))
    import make_fixture  # noqa: E402  (fixture-local module)

    with tempfile.TemporaryDirectory(prefix="cwfe-build-site-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        make_fixture.write_fixture_run_dir(run_dir)
        try:
            result = build_site(run_dir, skip_toolchain=False, toolchain_timeout=300)
        except SiteBuildError as exc:
            print(f"RESULT: FAIL — {exc}")
            return False
        ok = (
            result.receipt["status"] == "pass"
            and (result.site_dir / "public" / "media" / "hero-open.mp4").is_file()
            and (result.site_dir / "lib" / "site-data.generated.ts").is_file()
            and (result.site_dir / ".next").is_dir()
        )
        print(json.dumps(result.receipt, indent=2, sort_keys=True))
        print("RESULT:", "PASS" if ok else "FAIL")
        return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, help="Project run_dir containing content-manifest.json + journey/scene-plan.json")
    parser.add_argument("--out", type=Path, default=None, help="Target site directory (default: <run-dir>/site)")
    parser.add_argument("--media-dir", type=Path, default=None, help="Directory of {scene_id}.mp4/.jpg (default: <run-dir>/media)")
    parser.add_argument("--project-slug", default=None, help="Override the sanitized project slug (default: derived from project_id)")
    parser.add_argument("--fixture", action="store_true", help="Populate --run-dir with the deterministic U15 fixture before building")
    parser.add_argument("--skip-toolchain", action="store_true", help="Skip npm install/lint/typecheck/build (fast, offline unit-test mode)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TOOLCHAIN_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return EXIT_OK if ok else EXIT_BUILD_FAILED

    if not args.run_dir:
        parser.error("--run-dir is required (or use --self-test)")
        return EXIT_USAGE

    if args.fixture:
        sys.path.insert(0, str(_FIXTURE_DIR))
        import make_fixture  # noqa: E402

        make_fixture.write_fixture_run_dir(args.run_dir, args.media_dir)

    try:
        result = build_site(
            args.run_dir,
            site_dir=args.out,
            media_dir=args.media_dir,
            project_slug=args.project_slug,
            skip_toolchain=args.skip_toolchain,
            toolchain_timeout=args.timeout,
        )
    except SiteBuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return EXIT_BUILD_FAILED

    print(json.dumps(result.receipt, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
