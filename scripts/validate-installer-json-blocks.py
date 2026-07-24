#!/usr/bin/env python3
"""validate-installer-json-blocks.py — U103 static gate.

WHY THIS EXISTS
---------------
Several skill INSTALL.md files instruct the agent to merge a ```json config
block into a live file. When that block is NOT valid JSON (a bare `"key": {...}`
fragment with no outer braces, or a `{...}` ellipsis placeholder), the agent
either fails outright ("Illegal trailing comma" / "Extra data") or repairs by
improvising — silently diverging from the documented config. This gate parses
every ```json block in every installer doc and fails if any block does not parse.

WHAT IT ENFORCES
----------------
Every fenced ```json block in the scanned installer docs must be parseable by a
strict JSON parser. A block that is a config-merge fragment (no outer braces) or
contains a `{...}` ellipsis placeholder fails, because the agent cannot merge
what it cannot parse.

FAIL-VISIBLY CONTRACT
---------------------
Exit 0  → every ```json block in every scanned installer parses.
Exit 1  → one or more blocks fail to parse (each listed with file + approx line).
Exit 2  → a scanned file is missing / unreadable. Never a pass.

USAGE
-----
  scripts/validate-installer-json-blocks.py            # scan the installer docs
  scripts/validate-installer-json-blocks.py --self-test # prove both directions
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Installer docs that carry ```json config-merge blocks the agent must parse.
INSTALLER_DOCS = (
    "12-openrouter-setup/INSTALL.md",
    "31-upgraded-memory-system/INSTALL.md",
    "23-ai-workforce-blueprint/INSTALL.md",
)

JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def block_line_offsets(text: str) -> list[int]:
    """Return the 1-based line number where each ```json fence opens, in order."""
    offsets: list[int] = []
    for m in re.finditer(r"```json", text):
        offsets.append(text.count("\n", 0, m.start()) + 1)
    return offsets


def scan_file(path: pathlib.Path) -> tuple[list[str], list[str]]:
    """Return (problems, blockers) for one installer doc."""
    if not path.is_file():
        return [], [f"CANNOT RUN: installer doc not found at {path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], [f"CANNOT RUN: cannot read {path} ({exc})"]

    problems: list[str] = []
    fences = block_line_offsets(text)
    for idx, block in enumerate(JSON_BLOCK_RE.findall(text)):
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            line = fences[idx] if idx < len(fences) else "?"
            problems.append(f"{path}:~{line}: ```json block does not parse — {exc.msg}")
    return problems, []


def run_scan(root: pathlib.Path) -> tuple[int, list[str], list[str]]:
    """Scan all installer docs. Returns (exit_code, problems, notes)."""
    problems: list[str] = []
    blockers: list[str] = []
    notes: list[str] = []
    scanned = 0
    for rel in INSTALLER_DOCS:
        p = root / rel
        file_problems, file_blockers = scan_file(p)
        if file_blockers:
            blockers.extend(file_blockers)
            continue
        scanned += 1
        problems.extend(file_problems)
    notes.append(f"installer docs scanned: {scanned}/{len(INSTALLER_DOCS)}")
    if blockers:
        return 2, blockers + problems, notes
    if problems:
        return 1, problems, notes
    return 0, [], notes


def self_test() -> int:
    """Prove the gate fails on a non-parseable block and passes on a clean tree
    (mutation proof)."""
    script = pathlib.Path(__file__).resolve()
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        clean = pathlib.Path(tmp)
        # Build a minimal installer doc with a VALID json block.
        doc_dir = clean / "12-openrouter-setup"
        doc_dir.mkdir(parents=True)
        (doc_dir / "INSTALL.md").write_text(
            "# Install\n\n```json\n{\n  \"env\": { \"KEY\": \"x\" }\n}\n```\n",
            encoding="utf-8",
        )
        # Provide the other two docs as empty-but-present so the scan can run.
        for rel in INSTALLER_DOCS[1:]:
            (clean / rel).parent.mkdir(parents=True, exist_ok=True)
            (clean / rel).write_text("# Install\n\nNo json blocks.\n", encoding="utf-8")

        code, problems, _ = run_scan(clean)
        if code != 0:
            failures.append(f"DIRECTION 1 (clean tree must PASS) got exit {code}: {problems[:3]}")
        else:
            print("  ✓ direction 1 — clean installer docs pass (exit 0)")

        # Mutation: replace the valid block with a bare fragment (no outer braces).
        (doc_dir / "INSTALL.md").write_text(
            "# Install\n\n```json\n\"env\": {\n  \"KEY\": \"x\"\n}\n```\n",
            encoding="utf-8",
        )
        code, problems, _ = run_scan(clean)
        if code != 1 or not any("does not parse" in p for p in problems):
            failures.append(
                f"DIRECTION 2 (bare fragment must FAIL) got exit {code}, problems={problems[:3]}"
            )
        else:
            print(f"  ✓ direction 2 — bare json fragment fails (exit 1): {problems[0]}")

        # Mutation: a `{...}` ellipsis placeholder must also fail.
        (doc_dir / "INSTALL.md").write_text(
            "# Install\n\n```json\n{\n  \"top_3\": [{...}]\n}\n```\n",
            encoding="utf-8",
        )
        code, problems, _ = run_scan(clean)
        if code != 1:
            failures.append(
                f"DIRECTION 3 ({{...}} ellipsis must FAIL) got exit {code}, problems={problems[:3]}"
            )
        else:
            print(f"  ✓ direction 3 — {{...}} ellipsis placeholder fails (exit 1): {problems[0]}")

    # End-to-end against the real repo (only meaningful once the docs are fixed).
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    print(f"  · direction 4 — real repo exit {proc.returncode} "
          f"({'PASS' if proc.returncode == 0 else 'still has invalid blocks — expected before fix'})")

    if failures:
        print("\nSELF-TEST FAILED")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("\nSELF-TEST PASSED (3 directions + real-repo probe)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()

    code, problems, notes = run_scan(REPO_ROOT)
    print("installer JSON-block gate (U103)")
    for note in notes:
        print(f"  · {note}")
    if code == 0:
        print("✅ every ```json config block in the installer docs parses")
        return 0
    header = (
        "❌ GATE COULD NOT RUN — reporting as a failure, never as a pass"
        if code == 2
        else "❌ installer ```json block(s) do not parse"
    )
    print(header)
    for problem in problems:
        print(f"  ✗ {problem}")
    return code


if __name__ == "__main__":
    sys.exit(main())
