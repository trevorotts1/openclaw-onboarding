#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_environment.py — fail-closed preflight for the Personal Video Creator cluster
(universal-sops/video-production). Verifies ffmpeg/ffprobe on PATH, that each required
SecretRef resolves in the LIVE process environment, and that .gitignore covers the private
asset dirs. HARD-FAILS AF-PVC-ENV before any paid call.

stdlib only. Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3

REQUIRED_BINARIES = ["ffmpeg", "ffprobe"]
REQUIRED_SECRETS = ["FISH_AUDIO_API_KEY", "SYNC_LABS_API_KEY", "FISH_VOICE_REFERENCE_ID"]
OPTIONAL_SECRETS = ["OPENAI_API_KEY", "KIE_API_KEY", "SUNO_CREDENTIAL"]
PROTECTED_PATTERNS = [".env", "*.secret", "source_photos", "fish_master_raw"]


def verify(gitignore: Path | None, require_secrets: bool = True) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    for b in REQUIRED_BINARIES:
        if shutil.which(b):
            notes.append(f"{b} found")
        else:
            violations.append(("AF-PVC-ENV", f"required binary '{b}' not found on PATH"))

    if require_secrets:
        for s in REQUIRED_SECRETS:
            if os.environ.get(s, "").strip():
                notes.append(f"SecretRef {s} resolves")
            else:
                violations.append(("AF-PVC-ENV", f"required SecretRef '{s}' is not set in the live environment"))

    if gitignore is not None:
        if not gitignore.exists():
            violations.append(("AF-PVC-ENV", f".gitignore not found at {gitignore} — private assets could be committed"))
        else:
            text = gitignore.read_text(encoding="utf-8", errors="replace")
            for pat in PROTECTED_PATTERNS:
                if pat not in text:
                    violations.append(("AF-PVC-ENV", f".gitignore does not cover '{pat}' — add it before any commit"))
            if all(p in text for p in PROTECTED_PATTERNS):
                notes.append(".gitignore covers private asset patterns")

    return violations, notes


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: environment preflight clean (binaries + SecretRefs + .gitignore).")
        return
    print(f"FAIL: {len(violations)} environment violation(s) — no paid call may proceed.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    import tempfile
    ok = True

    # Binaries: ffmpeg/ffprobe may or may not be on this box; assert the function at least
    # reports them deterministically. We assert the SecretRef + gitignore logic directly.
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        gi = dp / ".gitignore"
        gi.write_text(".env\n*.secret\n01_likeness/source_photos/\n03_audio/fish_master_raw.wav\n")
        saved = {k: os.environ.get(k) for k in REQUIRED_SECRETS}
        try:
            for k in REQUIRED_SECRETS:
                os.environ[k] = "test-value"
            v, _ = verify(gi, require_secrets=True)
            env_violations = [m for c, m in v if "binary" not in m]
            if env_violations:
                ok = False
                print(f"SELF-TEST FAIL: clean env+gitignore -> {env_violations}")
            else:
                print("SELF-TEST ok: clean env+gitignore -> PASS (ignoring binary presence)")

            os.environ.pop("FISH_AUDIO_API_KEY", None)
            v, _ = verify(gi, require_secrets=True)
            if not any("FISH_AUDIO_API_KEY" in m for _, m in v):
                ok = False
                print(f"SELF-TEST FAIL: missing-secret -> {v}")
            else:
                print("SELF-TEST ok: missing-secret -> AF-PVC-ENV")
        finally:
            for k, val in saved.items():
                if val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = val

        gi.write_text(".env\n")  # incomplete
        v, _ = verify(gi, require_secrets=False)
        if not any(".gitignore does not cover" in m for _, m in v):
            ok = False
            print(f"SELF-TEST FAIL: incomplete-gitignore -> {v}")
        else:
            print("SELF-TEST ok: incomplete-gitignore -> AF-PVC-ENV")

        v, _ = verify(dp / "nope.gitignore", require_secrets=False)
        if not any("not found" in m for _, m in v):
            ok = False
            print(f"SELF-TEST FAIL: no-gitignore -> {v}")
        else:
            print("SELF-TEST ok: no-gitignore -> AF-PVC-ENV")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed environment preflight.")
    ap.add_argument("--project-dir", help="project root (locates .gitignore)")
    ap.add_argument("--gitignore", help="explicit .gitignore path")
    ap.add_argument("--no-secrets", action="store_true", help="skip SecretRef checks (binary/gitignore only)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    gitignore = None
    if args.gitignore:
        gitignore = Path(args.gitignore)
    elif args.project_dir:
        gitignore = Path(args.project_dir) / ".gitignore"
    violations, notes = verify(gitignore, require_secrets=not args.no_secrets)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
