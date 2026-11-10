#!/usr/bin/env python3
"""G-14 (fix plan section 6, plan-wide): every fix ships with a test that FAILS before the
change and passes after.

This index is the enforcement of that law. It reads tests/unit/ghl-fixplan-unowned-18.evidence.json
and asserts, for all 18 unowned requirements from SCOPE-LEDGER.md section 5:

  * the id is present exactly once, with a verdict of built-on-branch or already-present-on-main;
  * the entry names an artifact anchor (file:line) that resolves to a real file;
  * the entry names a test that EXISTS;
  * the entry carries captured fail-before evidence (or, for already-present-on-main, an
    explicit statement of why no fail-before run can exist);
  * no id is narrowed away: the full 18 are counted.

It does not run the tests (that is the CI runner's job and each test is also runnable alone);
it proves the SET is complete and each item is backed by a real artifact.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = Path(__file__).resolve().parent / "ghl-fixplan-unowned-18.evidence.json"
EXPECTED = ["G-%d" % i for i in range(1, 19)]
VERDICTS = {"built-on-branch", "already-present-on-main"}


def main() -> int:
    fails = []
    if not INDEX.is_file():
        print("FAIL G-14: %s is missing" % INDEX)
        return 1
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    except ValueError as exc:
        print("FAIL G-14: the index is not valid JSON: %s" % exc)
        return 1

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        print("FAIL G-14: the index carries no 'items' array")
        return 1

    seen = {}
    for entry in items:
        if not isinstance(entry, dict):
            fails.append("an index entry is not an object")
            continue
        gid = entry.get("id")
        if gid in seen:
            fails.append("%s appears more than once" % gid)
            continue
        seen[gid] = entry

    missing = [g for g in EXPECTED if g not in seen]
    extra = [g for g in seen if g not in EXPECTED]
    if missing:
        fails.append("the index does not address: %s" % ", ".join(missing))
    if extra:
        fails.append("the index carries unknown id(s): %s" % ", ".join(extra))

    for gid in EXPECTED:
        entry = seen.get(gid)
        if not entry:
            continue
        if entry.get("verdict") not in VERDICTS:
            fails.append("%s has an unknown verdict %r" % (gid, entry.get("verdict")))
        anchor = str(entry.get("anchor") or "")
        if not anchor:
            fails.append("%s names no artifact anchor" % gid)
        else:
            for rel in re.findall(r"[0-9A-Za-z_./-]+\.(?:py|json|md|sh|yml)", anchor):
                if not (ROOT / rel).is_file():
                    fails.append("%s anchors a file that does not exist: %s" % (gid, rel))
        test = str(entry.get("test") or "")
        if not test or not (ROOT / test).is_file():
            fails.append("%s names no existing test file (%r)" % (gid, test))
        evidence = entry.get("fail_before")
        if not isinstance(evidence, list) or not evidence:
            fails.append("%s carries no captured fail-before evidence" % gid)
        if not str(entry.get("pass_after") or "").strip():
            fails.append("%s carries no pass-after evidence" % gid)

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    built = sum(1 for g in EXPECTED if seen[g].get("verdict") == "built-on-branch")
    present = len(EXPECTED) - built
    print("PASS G-14: all %d unowned requirements carry a verdict, a resolvable artifact anchor, "
          "a test that exists, and captured fail-before evidence (%d built-on-branch, %d "
          "already-present-on-main)" % (len(EXPECTED), built, present))
    return 0


if __name__ == "__main__":
    sys.exit(main())
