#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_site.py — the P11-SITE-BUILD phase gate declared in CWFE-MANIFEST.json
(`"gate": "scripts/prove_site.py"`, `"py_symbol": "prove_site.evaluate"`,
`"af_code"` not separately named — P11 has no cross-cutting AF code of its
own, it is a normal per-phase gate).

Spec Section 17.5 ("site gate"): "Validate install, lint, typecheck, unit
tests, production build, routes, media references, no placeholders, no
hardcoded secrets, and no broken imports."

Like every other prove_*.py in this skill, this module NEVER trusts
scripts/build_site.py's own build-receipt.json as the verdict — it treats
the receipt as evidence/provenance only and independently re-derives every
pass/fail decision from the materialized site_dir on disk:

  - route files, scene media, and package.json's slug are re-read from disk,
    not from the receipt's claims about them;
  - every scene's video/poster sha256 is RECOMPUTED and compared against the
    receipt's recorded value (catches a doctored receipt or silent media
    drift);
  - placeholder/secret scans are RE-RUN against the live files, not read as
    a boolean off the receipt;
  - lint, typecheck, and the production build are RE-RUN from scratch
    against site_dir (reusing its already-installed node_modules — no
    network re-fetch needed for this part). This is what makes the "fail-
    closed on a broken build" requirement mechanical rather than a policy
    statement: a build-receipt.json hand-edited to claim `"status": "pass"`
    while the actual generated code no longer builds is caught here,
    because this module does not read that field to decide anything — it
    reruns `next build` itself and looks at the real exit code.

Exit 0 = PASS, 2 = FAIL, 3 = usage error. stdlib only for orchestration
(ADR-5); `npm`/`npx` invoked via subprocess argument arrays exactly like
scripts/build_site.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402
import build_site as bs  # noqa: E402  (reuses scan_placeholders/scan_secrets — same detectors, independently invoked against disk, not the receipt's booleans)

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

EXPECTED_ROUTES = ["app/layout.tsx", "app/page.tsx"]
TOOLCHAIN_STEP_TIMEOUT_SECONDS = 300


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_receipt(run_dir: Path, reasons: List[str]) -> Dict[str, Any]:
    path = run_dir / "build-receipt.json"
    if not path.is_file():
        reasons.append(f"build-receipt.json not found at {path} — P11-SITE-BUILD must run first")
        return {}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        reasons.append(f"build-receipt.json is not valid JSON: {exc}")
        return {}
    schema = json.loads((_STRUCTURE_DIR / "build-receipt.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        reasons.append("build-receipt.json failed schema validation: " + "; ".join(errors))
        return {}
    return receipt


def _check_routes(site_dir: Path, reasons: List[str]) -> None:
    for rel in EXPECTED_ROUTES:
        if not (site_dir / rel).is_file():
            reasons.append(f"expected route file missing on disk: {rel}")


def _check_slug(site_dir: Path, receipt: Dict[str, Any], reasons: List[str]) -> None:
    pkg_path = site_dir / "package.json"
    if not pkg_path.is_file():
        reasons.append("package.json missing from site_dir")
        return
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        reasons.append(f"package.json is not valid JSON: {exc}")
        return
    if pkg.get("name") != receipt.get("project_slug"):
        reasons.append(
            f"package.json name {pkg.get('name')!r} does not match receipt project_slug {receipt.get('project_slug')!r}"
        )


def _check_media(site_dir: Path, receipt: Dict[str, Any], reasons: List[str]) -> None:
    for scene in receipt.get("scenes", []):
        video_path = site_dir / scene["video_path"]
        poster_path = site_dir / scene["poster_path"]
        if not video_path.is_file():
            reasons.append(f"scene {scene['scene_id']}: video missing on disk at {scene['video_path']}")
            continue
        if not poster_path.is_file():
            reasons.append(f"scene {scene['scene_id']}: poster missing on disk at {scene['poster_path']}")
            continue
        if video_path.stat().st_size == 0:
            reasons.append(f"scene {scene['scene_id']}: video is zero-byte on disk")
        if poster_path.stat().st_size == 0:
            reasons.append(f"scene {scene['scene_id']}: poster is zero-byte on disk")
        actual_video_hash = _sha256_file(video_path)
        if actual_video_hash != scene["video_sha256"]:
            reasons.append(
                f"scene {scene['scene_id']}: video sha256 on disk ({actual_video_hash}) does not match "
                f"receipt ({scene['video_sha256']}) — media drift or a tampered receipt"
            )
        actual_poster_hash = _sha256_file(poster_path)
        if actual_poster_hash != scene["poster_sha256"]:
            reasons.append(
                f"scene {scene['scene_id']}: poster sha256 on disk ({actual_poster_hash}) does not match "
                f"receipt ({scene['poster_sha256']}) — media drift or a tampered receipt"
            )


def _check_placeholders_and_secrets(site_dir: Path, reasons: List[str]) -> None:
    ok_placeholders, placeholder_matches = bs.scan_placeholders(site_dir)
    if not ok_placeholders:
        reasons.append(f"placeholder scan found matches: {placeholder_matches}")
    ok_secrets, secret_matches = bs.scan_secrets(site_dir)
    if not ok_secrets:
        reasons.append(f"secret scan found matches: {secret_matches}")


def _rerun_step(cmd: List[str], cwd: Path, label: str, reasons: List[str]) -> None:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=TOOLCHAIN_STEP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        reasons.append(f"{label} timed out after {TOOLCHAIN_STEP_TIMEOUT_SECONDS}s during independent re-verification")
        return
    duration = time.monotonic() - started
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
        reasons.append(f"{label} FAILED on independent re-run (exit {proc.returncode}, {duration:.1f}s): {tail}")


def _independently_reverify_toolchain(site_dir: Path, reasons: List[str]) -> None:
    """Re-runs lint/typecheck/build from scratch against the materialized
    site_dir. Deliberately does NOT read build-receipt.json's own recorded
    step results — a doctored or stale receipt cannot force a PASS here."""
    if not (site_dir / "node_modules").is_dir():
        reasons.append(
            "site_dir has no node_modules — cannot independently re-verify lint/typecheck/build "
            "(run `npm install` in site_dir, or re-run scripts/build_site.py without --skip-toolchain)"
        )
        return
    _rerun_step(["npx", "eslint", "."], site_dir, "lint", reasons)
    _rerun_step(["npx", "tsc", "--noEmit"], site_dir, "typecheck", reasons)
    _rerun_step(["npx", "next", "build"], site_dir, "production build", reasons)


def evaluate(run_dir: Path, *, skip_toolchain_reverify: bool = False) -> Tuple[bool, str]:
    run_dir = Path(run_dir)
    reasons: List[str] = []

    receipt = _load_receipt(run_dir, reasons)
    if not receipt:
        return False, "; ".join(reasons)

    site_dir = Path(receipt["site_dir"])
    if not site_dir.is_dir():
        return False, f"receipt's site_dir does not exist on disk: {site_dir}"

    _check_routes(site_dir, reasons)
    _check_slug(site_dir, receipt, reasons)
    _check_media(site_dir, receipt, reasons)
    _check_placeholders_and_secrets(site_dir, reasons)

    if not skip_toolchain_reverify:
        _independently_reverify_toolchain(site_dir, reasons)

    if reasons:
        return False, "P11-SITE-BUILD FAIL: " + " | ".join(reasons)
    return True, "P11-SITE-BUILD PASS: routes present, slug matches, media hashes verified, no placeholders/secrets, lint+typecheck+build independently re-verified green"


def _self_test() -> bool:
    import tempfile

    _fixture_dir = _SKILL_DIR / "tests" / "fixtures" / "site-fixture"
    sys.path.insert(0, str(_fixture_dir))
    import make_fixture  # noqa: E402

    with tempfile.TemporaryDirectory(prefix="cwfe-prove-site-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        make_fixture.write_fixture_run_dir(run_dir)
        bs.build_site(run_dir, skip_toolchain=False, toolchain_timeout=300)

        passed, detail = evaluate(run_dir)
        print("good-build evaluate():", passed, "-", detail[:200])
        if not passed:
            print("RESULT: FAIL (expected PASS on an untouched good build)")
            return False

        # Fail-closed proof: corrupt the materialized site's page.tsx with a
        # real TypeScript syntax error, LEAVE build-receipt.json untouched
        # (still claiming "pass") to prove this gate does not trust it, and
        # confirm evaluate() independently reruns the build and fails.
        broken_page = site_dir_from_receipt(run_dir) / "app" / "page.tsx"
        original = broken_page.read_text(encoding="utf-8")
        broken_page.write_text(original + "\nconst __cwfe_broken = (;\n", encoding="utf-8")

        passed2, detail2 = evaluate(run_dir)
        print("broken-build evaluate():", passed2, "-", detail2[:400])
        broken_page.write_text(original, encoding="utf-8")  # restore for cleanliness
        if passed2:
            print("RESULT: FAIL (gate did not fail closed on a broken build)")
            return False

        print("RESULT: PASS")
        return True


def site_dir_from_receipt(run_dir: Path) -> Path:
    receipt = json.loads((run_dir / "build-receipt.json").read_text(encoding="utf-8"))
    return Path(receipt["site_dir"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument(
        "--skip-toolchain-reverify",
        action="store_true",
        help="Skip the independent lint/typecheck/build re-run (fast, offline unit-test mode only — "
        "never use this for a real phase-gate invocation, it weakens the fail-closed guarantee).",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return EXIT_OK if ok else EXIT_FAIL

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test)", file=sys.stderr)
        return EXIT_USAGE
    if not args.run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {args.run_dir}", file=sys.stderr)
        return EXIT_USAGE

    passed, detail = evaluate(args.run_dir, skip_toolchain_reverify=args.skip_toolchain_reverify)
    print(detail)
    return EXIT_OK if passed else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
