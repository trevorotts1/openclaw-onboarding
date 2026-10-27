#!/usr/bin/env python3
"""tests/unit/funnel-automation-library-drift-guard.test.py

REGRESSION GUARD — the automation library drift check was one-sided.

scripts/check-funnel-automation-library-drift.py compared the disk set against the
committed index SET and then pinned only `len(disk) != 51`. A set difference cannot
see loss that is symmetric: delete a template file AND its index row and the two
sets still agree, so nothing fires. The guard also printed a stale hardcoded count
(``automation(28)``) in its success line while the library held 51.

THE FIX: one named constant, ``EXPECTED_TEMPLATE_COUNT``, checked against BOTH the
committed index length and the file count the guard computes on disk, and the
success line prints the constant instead of a literal.

WHAT THIS FILE PROVES (hermetic: the guard's inputs are staged into a tempdir and
the guard is run there with --repo-root; nothing outside the tempdir is written,
no network):

  T1  an untouched copy                          -> exit 0, success line carries the pin
  T2  one template file AND its index row gone   -> exit 1, count drift on BOTH sides
  T3  restored                                   -> exit 0
  T4  one template file gone, index untouched    -> exit 1, message names the phantom

Run: python3 tests/unit/funnel-automation-library-drift-guard.test.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUARD_REL = Path("scripts") / "check-funnel-automation-library-drift.py"
AUTO_REL = Path("44-convert-and-flow-operator") / "automation-templates"
AUTO_INDEX_REL = AUTO_REL / "_matcher" / "catalog-index.json"

# The guard reads exactly these; everything else in the repo is irrelevant to it.
STAGED = [
    Path("scripts"),
    AUTO_REL,
    Path("06-ghl-install-pages") / "funnel-templates",
    Path("06-ghl-install-pages") / "tools",
    Path("shared-utils"),
    Path("22-book-to-persona-coaching-leadership-system") / "persona-categories.json",
]

PASSN = 0
FAILN = 0


def pass_(m):
    global PASSN
    PASSN += 1
    print("  PASS: %s" % m)


def fail_(m, extra=""):
    global FAILN
    FAILN += 1
    print("  FAIL: %s" % m)
    if extra:
        print("        %s" % extra)


def check(cond, msg, extra=""):
    if cond:
        pass_(msg)
    else:
        fail_(msg, extra)


def stage(tmp: Path) -> Path:
    root = tmp / "repo"
    for rel in STAGED:
        src = REPO_ROOT / rel
        dst = root / rel
        assert src.exists(), "missing guard input in the checkout: %s" % src
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    return root


def run_guard(root: Path):
    r = subprocess.run(
        [sys.executable, str(root / GUARD_REL), "--repo-root", str(root)],
        capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="funnel-automation-drift-"))
    try:
        root = stage(tmp)
        guard_const = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys;"
             "s=importlib.util.spec_from_file_location('g',sys.argv[1]);"
             "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
             "print(m.EXPECTED_TEMPLATE_COUNT)", str(root / GUARD_REL)],
            capture_output=True, text=True, timeout=60)
        pin = guard_const.stdout.strip()
        if guard_const.returncode == 0 and pin.isdigit():
            pass_("EXPECTED_TEMPLATE_COUNT is a single named integer constant (%s)" % pin)
        else:
            fail_("EXPECTED_TEMPLATE_COUNT not readable as an integer",
                  guard_const.stderr.strip()[:300])
            return 1

        # ---- T1: clean copy -------------------------------------------------
        rc, out = run_guard(root)
        if rc == 0:
            pass_("T1 clean copy exits 0")
        else:
            fail_("T1 clean copy should exit 0", "rc=%s\n%s" % (rc, out[:1500]))
        if ("automation(%s)" % pin) in out:
            pass_("T1 success line prints the pinned count, not a literal")
        else:
            fail_("T1 success line does not print automation(%s)" % pin, out[:600])

        # Pick a live template + its index row.
        index_path = root / AUTO_INDEX_REL
        index_before = index_path.read_text(encoding="utf-8")
        entry = json.loads(index_before)["templates"][0]
        victim = root / AUTO_REL / entry["group"] / ("%s.json" % entry["id"])
        if victim.is_file():
            pass_("T2 fixture: real template file selected (%s/%s)" % (entry["group"], entry["id"]))
        else:
            fail_("T2 fixture: template file for index row 0 is missing", str(victim))
            return 1
        victim_bytes = victim.read_bytes()

        # ---- T2: symmetric loss — file AND index row ------------------------
        victim.unlink()
        dropped = json.loads(index_before)
        dropped["templates"] = [t for t in dropped["templates"]
                                if not (t["group"] == entry["group"] and t["id"] == entry["id"])]
        dropped["templateCount"] = len(dropped["templates"])
        index_path.write_text(json.dumps(dropped, indent=2), encoding="utf-8")

        rc, out = run_guard(root)
        if rc == 1:
            pass_("T2 file + its index row deleted -> exit 1")
        else:
            fail_("T2 symmetric loss was NOT caught", "rc=%s\n%s" % (rc, out[:1500]))
        try:
            expected_int = int(pin) - 1
        except ValueError:
            expected_int = -1
        if "count drift" in out and str(expected_int) in out:
            pass_("T2 message names count drift with the observed count (%s)" % expected_int)
        else:
            fail_("T2 message does not name count drift + observed count", out[:1500])
        if "expected %s automation index entries" % pin in out:
            pass_("T2 index length checked against the pin (the one-sided gap)")
        else:
            fail_("T2 index length not checked against the pin", out[:1500])

        # ---- T3: restore ----------------------------------------------------
        victim.write_bytes(victim_bytes)
        index_path.write_text(index_before, encoding="utf-8")
        rc, out = run_guard(root)
        if rc == 0:
            pass_("T3 restored tree exits 0")
        else:
            fail_("T3 restored tree should exit 0", "rc=%s\n%s" % (rc, out[:1500]))

        # ---- T4: file-only loss -> phantom --------------------------------
        victim.unlink()
        rc, out = run_guard(root)
        if rc == 1:
            pass_("T4 file-only delete -> exit 1")
        else:
            fail_("T4 file-only delete was not caught", "rc=%s\n%s" % (rc, out[:1500]))
        if "phantoms" in out and entry["id"] in out:
            pass_("T4 message names the phantom id (%s)" % entry["id"])
        else:
            fail_("T4 message does not name the phantom", out[:1500])

        # leave the tempdir's tree as staged; removal happens in finally
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== %d passed, %d failed ===" % (PASSN, FAILN))
    return 1 if FAILN else 0


if __name__ == "__main__":
    sys.exit(main())
