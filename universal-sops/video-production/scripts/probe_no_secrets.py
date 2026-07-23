#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_no_secrets.py — fail-closed secret/URL leakage scanner for the Personal Video
Creator cluster (universal-sops/video-production). Scans the project tree (prompts,
manifests, logs, captions) for accidental API keys, voice IDs, bearer tokens, or signed
URLs and HARD-FAILS (AF-PVC-SECRET-LEAK) on any hit. Secrets resolve via SecretRef only —
the plaintext value must transit no file that could be shared or committed.

stdlib only. Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3

# High-signal patterns. Deliberately conservative to avoid false positives on prose.
PATTERNS = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer_token", re.compile(r"\bbearer\s+[A-Za-z0-9._\-]{20,}", re.I)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("generic_api_key", re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}")),
    ("signed_url", re.compile(r"(?i)\bhttps?://[^\s'\"]*?(signature|expires|x-amz-signature|x-goog-signature|token)=[^\s'\"]+")),
    ("fish_voice_id", re.compile(r"(?i)\bvoice[_-]?id\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}")),
]

# Files/dirs never scanned (binary + the private asset dirs themselves hold the real assets,
# but their *names* and any sidecar text must still be clean — we scan text files only).
SCAN_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt", ".csv", ".srt", ".vtt", ".log"}
SKIP_DIRS = {"source_photos", "rejected", ".git"}


def scan_file(path: Path) -> List[Tuple[str, str, int]]:
    hits: List[Tuple[str, str, int]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in PATTERNS:
            if rx.search(line):
                hits.append((name, str(path), lineno))
    return hits


def verify(root: Path) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        scanned += 1
        for name, fpath, lineno in scan_file(path):
            violations.append(("AF-PVC-SECRET-LEAK",
                               f"{fpath}:{lineno} matches '{name}' — redact before sharing/committing"))
    return violations, [f"scanned {scanned} text file(s) under {root}"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: no API keys, voice IDs, tokens, or signed URLs found in the project tree.")
        return
    print(f"FAIL: {len(violations)} secret/URL leakage hit(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "clean.md").write_text("# Prompt\nUse the reference image. fish_reference_id: STORE_AS_SECRET_REFERENCE\n")
        (dp / "clean.yaml").write_text("voice:\n  fish_reference_id: STORE_AS_SECRET_REFERENCE\n")
        v, _ = verify(dp)
        if v:
            ok = False
            print(f"SELF-TEST FAIL: clean tree -> {v}")
        else:
            print("SELF-TEST ok: clean -> PASS")

        (dp / "leak.md").write_text("openai key = sk-ABCDEFGHIJKLMNOPQRSTUVWX123456\n")
        v, _ = verify(dp)
        if {c for c, _ in v} != {"AF-PVC-SECRET-LEAK"}:
            ok = False
            print(f"SELF-TEST FAIL: openai leak -> {v}")
        else:
            print("SELF-TEST ok: openai leak -> AF-PVC-SECRET-LEAK")
        (dp / "leak.md").unlink()

        (dp / "url.md").write_text("see https://cdn.example.com/img.png?x-amz-signature=abcdef123456&expires=99\n")
        v, _ = verify(dp)
        if {c for c, _ in v} != {"AF-PVC-SECRET-LEAK"}:
            ok = False
            print(f"SELF-TEST FAIL: signed url -> {v}")
        else:
            print("SELF-TEST ok: signed url -> AF-PVC-SECRET-LEAK")
        (dp / "url.md").unlink()

        (dp / "vid.yaml").write_text("voice_id: abc123XYZ9\n")
        v, _ = verify(dp)
        if {c for c, _ in v} != {"AF-PVC-SECRET-LEAK"}:
            ok = False
            print(f"SELF-TEST FAIL: voice id -> {v}")
        else:
            print("SELF-TEST ok: voice id -> AF-PVC-SECRET-LEAK")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed secret/URL leakage scanner.")
    ap.add_argument("--project-dir", help="project root to scan")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not args.project_dir:
        print("USAGE ERROR: pass --project-dir <root> (or --self-test).")
        return EXIT_FAILCLOSED
    root = Path(args.project_dir)
    if not root.is_dir():
        print(f"USAGE/IO ERROR: {root} is not a directory.")
        return EXIT_FAILCLOSED
    violations, notes = verify(root)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
