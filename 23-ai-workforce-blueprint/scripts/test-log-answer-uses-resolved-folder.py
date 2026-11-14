#!/usr/bin/env python3
"""BU-63 acceptance test: answers logged by the build module land in the
folder the build reads.

MASTER_FILES_DIR points at a scratch folder and HOME is an empty folder with
no ~/Downloads. After importing build-workforce.py, log_answer("q", "a") must
write under <scratch>/company-discovery/ and must not create anything under
HOME (the old code re-scanned ~/Downloads and fell back to a HOME path).

Exit 0 = the guard passes; non-zero = it failed. Hermetic: scratch folders
only; nothing may escape them.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "build-workforce.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory() as home:
        scratch_path = Path(scratch)
        home_path = Path(home)

        os.environ["MASTER_FILES_DIR"] = str(scratch_path)
        os.environ["OPENCLAW_PLATFORM"] = "mac"
        os.environ["HOME"] = str(home_path)

        spec = importlib.util.spec_from_file_location("build_workforce_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        if module.MASTER_FILES != str(scratch_path):
            print(f"FAIL: resolver folder was not kept: {module.MASTER_FILES}")
            return 1

        module.log_answer("q", "a")

        answers = scratch_path / "company-discovery" / "workforce-interview-answers.md"
        if not answers.is_file():
            print(f"FAIL: answer file missing at {answers}")
            return 1
        if "**A:** a" not in answers.read_text(encoding="utf-8"):
            print("FAIL: answer not written to the resolved folder's file")
            return 1

        strays = sorted(p.relative_to(home_path).as_posix() for p in home_path.rglob("*"))
        if strays:
            print(f"FAIL: log_answer created files under HOME: {strays}")
            return 1

    print("PASS: log_answer writes under MASTER_FILES_DIR/company-discovery and leaves HOME untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
