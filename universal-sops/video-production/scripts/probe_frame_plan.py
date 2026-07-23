#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_frame_plan.py — fail-closed Agnes frame-plan validator for the Personal Video
Creator cluster (universal-sops/video-production). For every TALKING_HEAD scene in
04_storyboard/scene_manifest.yaml, confirms:
  * agnes.num_frames_requested satisfies the 8n+1 rule            -> AF-PVC-FRAMEPLAN
  * agnes.num_frames_requested <= agnes_max_frames (default 441)  -> AF-PVC-FRAMEPLAN
  * required_video_duration covers spoken_duration + handles      -> AF-PVC-FRAMEPLAN
  * the implied clip duration (num_frames / fps) >= required_video_duration - 0.05s
                                                                   -> AF-PVC-FRAMEPLAN
stdlib only (mini-YAML with a PyYAML fast-path). Exit 0 pass, 2 violation, 3 usage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3
DEFAULT_MAX_FRAMES = 441
DEFAULT_FPS = 24
DUR_TOL = 0.05


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except Exception:
        return None


def _scenes(manifest: Any) -> List[Dict[str, Any]]:
    if isinstance(manifest, dict):
        s = manifest.get("scenes")
        if isinstance(s, list):
            return [x for x in s if isinstance(x, dict)]
    return []


def verify(manifest: Any, max_frames: int = DEFAULT_MAX_FRAMES,
           fps: int = DEFAULT_FPS) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    scenes = _scenes(manifest)
    if not scenes:
        violations.append(("AF-PVC-FRAMEPLAN", "scene_manifest.yaml carries no 'scenes' list"))
        return violations, []

    talking = 0
    for sc in scenes:
        sid = sc.get("id", "?")
        stype = str(sc.get("type", "")).upper()
        if stype != "TALKING_HEAD":
            continue
        talking += 1
        agnes = sc.get("agnes") or {}
        nf = agnes.get("num_frames_requested")
        scene_fps = float(agnes.get("fps") or fps)
        spoken = float(sc.get("spoken_duration") or 0)
        pre = float(sc.get("pre_handle") or 0)
        post = float(sc.get("post_handle") or 0)
        required = float(sc.get("required_video_duration") or 0)

        if nf is None:
            violations.append(("AF-PVC-FRAMEPLAN", f"{sid}: agnes.num_frames_requested missing"))
            continue
        nf = int(nf)
        if (nf - 1) % 8 != 0:
            violations.append(("AF-PVC-FRAMEPLAN", f"{sid}: num_frames {nf} violates the 8n+1 rule"))
        if nf > max_frames:
            violations.append(("AF-PVC-FRAMEPLAN", f"{sid}: num_frames {nf} > max {max_frames}"))

        need = spoken + pre + post
        if required and required + DUR_TOL < need:
            violations.append(("AF-PVC-FRAMEPLAN",
                               f"{sid}: required_video_duration {required:.3f}s < spoken {spoken:.3f} + handles "
                               f"{pre:.3f}+{post:.3f} = {need:.3f}s"))
        implied = nf / scene_fps if scene_fps else 0
        target = required or need
        if implied + DUR_TOL < target:
            violations.append(("AF-PVC-FRAMEPLAN",
                               f"{sid}: implied clip duration {implied:.3f}s ({nf} frames @ {scene_fps:g}fps) "
                               f"< required {target:.3f}s"))

    return violations, [f"checked {talking} TALKING_HEAD scene(s) against the 8n+1 / <={max_frames} frame plan"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: every talking-head frame plan satisfies 8n+1, <= max frames, and covers its audio + handles.")
        return
    print(f"FAIL: {len(violations)} frame-plan violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


_VALID = {
    "scenes": [
        {"id": "scene_001", "type": "TALKING_HEAD", "spoken_duration": 8.740,
         "pre_handle": 0.250, "post_handle": 0.300, "required_video_duration": 9.290,
         "agnes": {"fps": 24, "num_frames_requested": 225}},
        {"id": "scene_002", "type": "BROLL_GENERATED", "spoken_duration": 6.160},
    ]
}


def run_self_test() -> int:
    import copy
    ok = True
    v, _ = verify(_VALID)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid -> {v}")
    else:
        print("SELF-TEST ok: valid -> PASS")

    bad_rule = copy.deepcopy(_VALID)
    bad_rule["scenes"][0]["agnes"]["num_frames_requested"] = 224
    v, _ = verify(bad_rule)
    if not any("8n+1" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: bad-8n+1 -> {v}")
    else:
        print("SELF-TEST ok: bad-8n+1 -> AF-PVC-FRAMEPLAN")

    too_many = copy.deepcopy(_VALID)
    too_many["scenes"][0]["agnes"]["num_frames_requested"] = 449
    v, _ = verify(too_many)
    if not any("> max" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: too-many-frames -> {v}")
    else:
        print("SELF-TEST ok: too-many-frames -> AF-PVC-FRAMEPLAN")

    too_short = copy.deepcopy(_VALID)
    too_short["scenes"][0]["agnes"]["num_frames_requested"] = 121  # ~5.04s < 9.29s required
    v, _ = verify(too_short)
    if not any("implied clip duration" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: too-short-clip -> {v}")
    else:
        print("SELF-TEST ok: too-short-clip -> AF-PVC-FRAMEPLAN")

    v, _ = verify({"scenes": []})
    if {c for c, _ in v} != {"AF-PVC-FRAMEPLAN"}:
        ok = False
        print(f"SELF-TEST FAIL: empty -> {v}")
    else:
        print("SELF-TEST ok: empty -> AF-PVC-FRAMEPLAN")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Agnes frame-plan validator.")
    ap.add_argument("--manifest", help="path to 04_storyboard/scene_manifest.yaml")
    ap.add_argument("--project-dir", help="project root")
    ap.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    path = None
    if args.manifest:
        path = Path(args.manifest)
    elif args.project_dir:
        path = Path(args.project_dir) / "04_storyboard" / "scene_manifest.yaml"
    if not path or not path.exists():
        print(f"USAGE/IO ERROR: scene_manifest.yaml not found ({path}).")
        return EXIT_FAILCLOSED
    manifest = _load_yaml(path)
    if manifest is None:
        print(f"USAGE/IO ERROR: cannot parse {path} (PyYAML unavailable or invalid YAML).")
        return EXIT_FAILCLOSED
    violations, notes = verify(manifest, args.max_frames, args.fps)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
