#!/usr/bin/env python3
"""assert-install-doc-consistency.py — F1.5 docs-consistency guard.

Anti-staleness check for the human-facing install prose. INSTALL.md used to carry
hardcoded "48 personas / ~7,615 chunks" text long after the canonical SET had
grown, which caused fixed defects to be re-litigated ("the book personas are
MISSING"). This guard makes the prose count drift a CI failure instead.

Rule (per the persona-matching analysis, F1.5):
  every "<N> persona(s)" / "<N>-persona" count CLAIM in INSTALL.md must agree with
  INDEX-MANIFEST.json's `persona_count`.

Tolerance for the re-baseline seam: the manifest count and the docs are bumped by
DIFFERENT trains (the manifest by the SET re-baseline; the docs here). A single-step
lag is therefore expected transiently and is reported as a NOTICE, not a failure.
Any drift larger than that (the real staleness bug — e.g. 48 vs 82) FAILS.

Only PERSONA counts are asserted. Row/chunk counts are intentionally NOT hard-checked
here (the SHA256 gate already pins the asset bytes, and INSTALL.md legitimately cites
the historical per-paragraph row count for context).

Exit 0 = consistent (possibly with a NOTICE); exit 1 = stale/inconsistent.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Manifest and docs are bumped by different trains; allow a one-step transient lag.
SEAM_TOLERANCE = 1

# "82 personas", "82-persona", "all 82 personas", "with 82 personas" → 82.
# Requires an integer immediately before "persona(s)"; "coaching-personas",
# "persona-blueprint.md", "Section 4" etc. never match (no leading integer).
_PERSONA_COUNT_RE = re.compile(r"(\d+)\s*-?\s*personas?\b", re.IGNORECASE)


def _repo_root() -> Path:
    # shared-utils/prebuilt-index/<this> → repo root is three levels up.
    return Path(__file__).resolve().parents[2]


def extract_persona_counts(install_text: str) -> "list[tuple[int, str]]":
    """Return [(count, context_line), ...] for every persona-count claim."""
    out = []
    for line in install_text.splitlines():
        for m in _PERSONA_COUNT_RE.finditer(line):
            out.append((int(m.group(1)), line.strip()))
    return out


def main(argv=None) -> int:
    root = _repo_root()
    ap = argparse.ArgumentParser(description="F1.5 INSTALL.md ↔ manifest persona-count consistency guard")
    ap.add_argument(
        "--install",
        default=str(root / "22-book-to-persona-coaching-leadership-system" / "INSTALL.md"),
        help="path to INSTALL.md",
    )
    ap.add_argument(
        "--manifest",
        default=str(root / "shared-utils" / "prebuilt-index" / "INDEX-MANIFEST.json"),
        help="path to INDEX-MANIFEST.json",
    )
    args = ap.parse_args(argv)

    install_path = Path(args.install)
    manifest_path = Path(args.manifest)

    fails = []
    notices = []

    if not manifest_path.is_file():
        print(f"FAIL: manifest not found: {manifest_path}")
        return 1
    if not install_path.is_file():
        print(f"FAIL: INSTALL.md not found: {install_path}")
        return 1

    manifest = json.loads(manifest_path.read_text())
    man_count = int(manifest.get("persona_count", -1))
    if man_count < 0:
        print(f"FAIL: manifest has no usable persona_count: {manifest_path}")
        return 1

    claims = extract_persona_counts(install_path.read_text())
    print(f"manifest.persona_count = {man_count}")
    print(f"INSTALL.md persona-count claims: {sorted({c for c, _ in claims})}")

    if not claims:
        # No hardcoded persona count in prose is an acceptable outcome ("drop
        # hardcoded counts from prose" — the analysis's alternative remedy).
        print("PASS: INSTALL.md hardcodes no persona count (nothing to drift).")
        return 0

    for count, ctx in claims:
        delta = count - man_count
        if delta == 0:
            continue
        if abs(delta) <= SEAM_TOLERANCE:
            notices.append(
                f"INSTALL.md says {count} personas, manifest says {man_count} "
                f"(±{abs(delta)} — re-baseline seam, allowed): {ctx!r}"
            )
        else:
            fails.append(
                f"INSTALL.md says {count} personas but manifest says {man_count} "
                f"(drift {delta:+d} > ±{SEAM_TOLERANCE}) — STALE prose: {ctx!r}"
            )

    for n in notices:
        print(f"NOTICE: {n}")
    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        print(
            "\nFix: update INSTALL.md's persona count to match "
            "shared-utils/prebuilt-index/INDEX-MANIFEST.json (persona_count), "
            "or drop the hardcoded count from prose."
        )
        return 1

    print("\nPASS: INSTALL.md persona counts agree with the manifest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
