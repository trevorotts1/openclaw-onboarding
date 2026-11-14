#!/usr/bin/env python3
"""BU-81 acceptance test: the build writes build-handoff.md, never the
interview handoff.

MASTER_FILES_DIR points at a scratch folder that already holds a
company-discovery/interview-handoff.md with known bytes. After importing
build-workforce.py, create_handoff("A", ["x"], [], 90) must leave those bytes
untouched, must create build-handoff.md beside them, and must not create
anything under HOME.

Exit 0 = the guard passes; non-zero = it failed. Hermetic: scratch folders only.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "build-workforce.py"

KNOWN = (
    "# Interview Handoff\n"
    "status: in_progress\n"
    "next_question_number: 4\n"
    "BU-81 known bytes: do not rewrite\n"
)


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory() as home:
        scratch_path = Path(scratch)
        home_path = Path(home)

        os.environ["MASTER_FILES_DIR"] = str(scratch_path)
        os.environ["OPENCLAW_PLATFORM"] = "mac"
        os.environ["HOME"] = str(home_path)

        discovery = scratch_path / "company-discovery"
        discovery.mkdir(parents=True, exist_ok=True)
        interview_handoff = discovery / "interview-handoff.md"
        interview_handoff.write_text(KNOWN, encoding="utf-8")
        before = interview_handoff.read_bytes()

        spec = importlib.util.spec_from_file_location("build_workforce_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        module.create_handoff("A", ["x"], [], 90)

        after = interview_handoff.read_bytes()
        if after != before:
            print("FAIL: create_handoff rewrote interview-handoff.md")
            print(f"  before: {before!r}")
            print(f"  after:  {after!r}")
            return 1

        build_handoff = discovery / "build-handoff.md"
        if not build_handoff.is_file():
            print(f"FAIL: build-handoff.md was not created at {build_handoff}")
            return 1

        text = build_handoff.read_text(encoding="utf-8")
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if first_line != "# Build Handoff":
            print(f"FAIL: build-handoff.md title line is {first_line!r}, expected '# Build Handoff'")
            return 1
        if "## Option Selected: A" not in text:
            print("FAIL: build-handoff.md does not record the selected option")
            return 1

        strays = sorted(p.relative_to(home_path).as_posix() for p in home_path.rglob("*"))
        if strays:
            print(f"FAIL: create_handoff created files under HOME: {strays}")
            return 1

    print("PASS: create_handoff writes build-handoff.md and leaves interview-handoff.md byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
