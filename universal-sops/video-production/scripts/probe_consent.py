#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_consent.py — fail-closed likeness + voice consent gate for the Personal Video
Creator cluster (universal-sops/video-production). No generation call may precede a pass.

Reads 00_admin/project_manifest.yaml (consent_verified) and/or 00_admin/CONSENT.md and
HARD-FAILS (AF-PVC-CONSENT) unless likeness AND voice authorization are both attested.
A self-attested flag in the manifest is only trusted when CONSENT.md also carries the
two authorization markers (never trust a bare boolean). stdlib only (mini-YAML flattener
with a PyYAML fast-path). Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3

LIKENESS_MARKERS = ("authorized use of their likeness", "likeness", "authorized use of likeness",
                    "likeness authorized", "use of their likeness")
VOICE_MARKERS = ("voice cloning", "cloned voice", "fish audio voice model", "voice model",
                 "voice authorized", "authorized voice")


def _mini_yaml_flatten(text: str) -> Dict[str, str]:
    """Flatten a simple indentation-nested YAML subset to dotted keys -> scalar strings.
    Sufficient for the manifest's key-presence / boolean checks. Lists are skipped."""
    flat: Dict[str, str] = {}
    stack: List[Tuple[int, str]] = []  # (indent, key)
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if line.startswith("- "):
            continue
        if ":" not in line:
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


def _load_manifest(path: Path) -> Dict[str, str]:
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
            elif isinstance(d, list):
                pass
            return out
        return _flatten(data)
    except Exception:
        return _mini_yaml_flatten(text)


def verify(manifest_path: Path | None, consent_path: Path | None) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    manifest: Dict[str, str] = {}
    if manifest_path and manifest_path.exists():
        manifest = _load_manifest(manifest_path)
        notes.append(f"read manifest {manifest_path}")
    consent_text = ""
    if consent_path and consent_path.exists():
        consent_text = consent_path.read_text(encoding="utf-8", errors="replace").lower()
        notes.append(f"read consent {consent_path}")

    if not manifest and not consent_text:
        violations.append(("AF-PVC-CONSENT", "neither project_manifest.yaml nor CONSENT.md found"))
        return violations, notes

    flag = manifest.get("project.consent_verified", "").strip().lower()
    if flag != "true":
        violations.append(("AF-PVC-CONSENT",
                           "project.consent_verified is not 'true' in project_manifest.yaml"))

    has_likeness = any(m in consent_text for m in LIKENESS_MARKERS)
    has_voice = any(m in consent_text for m in VOICE_MARKERS)
    if not has_likeness:
        violations.append(("AF-PVC-CONSENT", "CONSENT.md does not attest authorized use of likeness"))
    if not has_voice:
        violations.append(("AF-PVC-CONSENT", "CONSENT.md does not attest voice cloning / voice model authorization"))

    return violations, notes


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: likeness + voice consent verified.")
        return
    print(f"FAIL: {len(violations)} consent violation(s) — no generation call may proceed.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


_VALID_CONSENT = ("# Consent\nSubject: Jane Doe. The subject gave authorized use of their likeness "
                  "for this campaign. The subject authorized voice cloning of their Fish Audio voice model. "
                  "Commercial use approved.")


def run_self_test() -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        # valid
        (dp / "project_manifest.yaml").write_text("project:\n  consent_verified: true\n  subject_name: Jane\n")
        (dp / "CONSENT.md").write_text(_VALID_CONSENT)
        v, _ = verify(dp / "project_manifest.yaml", dp / "CONSENT.md")
        if v:
            ok = False
            print(f"SELF-TEST FAIL: valid fixture -> {v}")
        else:
            print("SELF-TEST ok: valid -> PASS")
        # flag false
        (dp / "project_manifest.yaml").write_text("project:\n  consent_verified: false\n")
        v, _ = verify(dp / "project_manifest.yaml", dp / "CONSENT.md")
        if {c for c, _ in v} != {"AF-PVC-CONSENT"}:
            ok = False
            print(f"SELF-TEST FAIL: flag-false -> {v}")
        else:
            print("SELF-TEST ok: flag-false -> AF-PVC-CONSENT")
        # no voice marker
        (dp / "project_manifest.yaml").write_text("project:\n  consent_verified: true\n")
        (dp / "CONSENT.md").write_text("# Consent\nSubject gave authorized use of their likeness only.")
        v, _ = verify(dp / "project_manifest.yaml", dp / "CONSENT.md")
        if not any("voice" in m for _, m in v):
            ok = False
            print(f"SELF-TEST FAIL: no-voice -> {v}")
        else:
            print("SELF-TEST ok: no-voice -> AF-PVC-CONSENT")
        # missing files
        v, _ = verify(dp / "nope.yaml", dp / "nope.md")
        if {c for c, _ in v} != {"AF-PVC-CONSENT"}:
            ok = False
            print(f"SELF-TEST FAIL: missing -> {v}")
        else:
            print("SELF-TEST ok: missing -> AF-PVC-CONSENT")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed likeness + voice consent gate.")
    ap.add_argument("--manifest", help="path to 00_admin/project_manifest.yaml")
    ap.add_argument("--consent", help="path to 00_admin/CONSENT.md")
    ap.add_argument("--project-dir", help="project root (derives 00_admin/...)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    manifest_path = consent_path = None
    if args.project_dir:
        root = Path(args.project_dir)
        manifest_path = root / "00_admin" / "project_manifest.yaml"
        consent_path = root / "00_admin" / "CONSENT.md"
    if args.manifest:
        manifest_path = Path(args.manifest)
    if args.consent:
        consent_path = Path(args.consent)
    if not manifest_path and not consent_path:
        print("USAGE ERROR: pass --project-dir <root> or --manifest/--consent (or --self-test).")
        return EXIT_FAILCLOSED

    violations, notes = verify(manifest_path, consent_path)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
