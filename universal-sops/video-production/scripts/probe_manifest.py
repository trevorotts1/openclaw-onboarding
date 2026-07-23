#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_manifest.py — fail-closed project_manifest.yaml validator for the Personal Video
Creator cluster (universal-sops/video-production). Confirms the required fields are present
and non-empty AND enforces the SecretRef discipline: voice.fish_reference_id must be the
literal 'STORE_AS_SECRET_REFERENCE' (resolved from FISH_VOICE_REFERENCE_ID at call time),
never an inlined voice id. HARD-FAILS AF-PVC-MANIFEST.

stdlib only (mini-YAML flattener with a PyYAML fast-path). Exit 0 pass, 2 violation, 3 usage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3

REQUIRED_FIELDS = [
    "project.id", "project.title", "project.subject_name", "project.intended_use",
    "project.orientation", "project.width", "project.height", "project.fps",
    "project.language",
    "models.image_provider", "models.video_model", "models.voice_model",
    "models.lip_sync_model_default",
    "voice.fish_reference_id", "voice.sample_rate",
    "production_limits.agnes_max_frames", "production_limits.lip_sync_tolerance_frames",
    "command_center.department_slug",
]

SECRETREF_FIELDS = {"voice.fish_reference_id": "STORE_AS_SECRET_REFERENCE"}


def _mini_yaml_flatten(text: str) -> Dict[str, str]:
    flat: Dict[str, str] = {}
    stack: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if line.startswith("- ") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.split("#", 1)[0].strip().strip('"').strip("'")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        dotted = ".".join([k for _, k in stack] + [key])
        if val != "":
            flat[dotted] = val
        stack.append((indent, key))
    return flat


def _load(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)

        def _flatten(d, prefix=""):
            out = {}
            if isinstance(d, dict):
                for k, v in d.items():
                    p = f"{prefix}.{k}" if prefix else str(k)
                    if isinstance(v, (dict, list)):
                        out.update(_flatten(v, p))
                    else:
                        out[p] = "" if v is None else str(v)
            return out
        return _flatten(data)
    except Exception:
        return _mini_yaml_flatten(text)


def verify(manifest: Dict[str, str]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    for field in REQUIRED_FIELDS:
        if not manifest.get(field, "").strip():
            violations.append(("AF-PVC-MANIFEST", f"required field '{field}' is missing or empty"))
    for field, expected in SECRETREF_FIELDS.items():
        val = manifest.get(field, "").strip()
        if val and val != expected:
            violations.append(("AF-PVC-MANIFEST",
                               f"'{field}' must be '{expected}' (SecretRef), got an inlined value — "
                               "resolve the real id from FISH_VOICE_REFERENCE_ID at call time"))
    slug = manifest.get("command_center.department_slug", "").strip()
    if slug and slug != "video":
        violations.append(("AF-PVC-MANIFEST",
                           f"command_center.department_slug must be 'video', got '{slug}'"))
    return violations, [f"validated {len(REQUIRED_FIELDS)} required fields + SecretRef discipline"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: project_manifest.yaml is complete and SecretRef-clean.")
        return
    print(f"FAIL: {len(violations)} manifest violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


_VALID = """project:
  id: "PVC-20260723-ACME"
  title: "Founder intro"
  subject_name: "Jane Doe"
  intended_use: "social"
  orientation: "9:16"
  width: 1080
  height: 1920
  fps: 24
  language: "en-US"
models:
  image_provider: "gpt-image-2"
  video_model: "agnes-video-v2.0"
  voice_model: "s2.1-pro"
  lip_sync_model_default: "lipsync-2-pro"
voice:
  fish_reference_id: "STORE_AS_SECRET_REFERENCE"
  sample_rate: 48000
production_limits:
  agnes_max_frames: 441
  lip_sync_tolerance_frames: 2
command_center:
  department_slug: "video"
"""


def run_self_test() -> int:
    ok = True
    v, _ = verify(_load_str(_VALID))
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid -> {v}")
    else:
        print("SELF-TEST ok: valid -> PASS")

    missing = _load_str(_VALID.replace('  title: "Founder intro"\n', ""))
    v, _ = verify(missing)
    if {c for c, _ in v} != {"AF-PVC-MANIFEST"}:
        ok = False
        print(f"SELF-TEST FAIL: missing-title -> {v}")
    else:
        print("SELF-TEST ok: missing-title -> AF-PVC-MANIFEST")

    inlined = _load_str(_VALID.replace("STORE_AS_SECRET_REFERENCE", "voice_abc123XYZ"))
    v, _ = verify(inlined)
    if not any("SecretRef" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: inlined-voice-id -> {v}")
    else:
        print("SELF-TEST ok: inlined-voice-id -> AF-PVC-MANIFEST")

    wrongslug = _load_str(_VALID.replace('department_slug: "video"', 'department_slug: "marketing"'))
    v, _ = verify(wrongslug)
    if not any("department_slug" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: wrong-slug -> {v}")
    else:
        print("SELF-TEST ok: wrong-slug -> AF-PVC-MANIFEST")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def _load_str(text: str) -> Dict[str, str]:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)

        def _flatten(d, prefix=""):
            out = {}
            if isinstance(d, dict):
                for k, v in d.items():
                    p = f"{prefix}.{k}" if prefix else str(k)
                    if isinstance(v, (dict, list)):
                        out.update(_flatten(v, p))
                    else:
                        out[p] = "" if v is None else str(v)
            return out
        return _flatten(data)
    except Exception:
        return _mini_yaml_flatten(text)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed project_manifest.yaml validator.")
    ap.add_argument("--manifest", help="path to project_manifest.yaml")
    ap.add_argument("--project-dir", help="project root (derives 00_admin/project_manifest.yaml)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    path = None
    if args.manifest:
        path = Path(args.manifest)
    elif args.project_dir:
        path = Path(args.project_dir) / "00_admin" / "project_manifest.yaml"
    if not path or not path.exists():
        print(f"USAGE/IO ERROR: manifest not found ({path}). Pass --manifest/--project-dir or --self-test.")
        return EXIT_FAILCLOSED
    violations, notes = verify(_load(path))
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
