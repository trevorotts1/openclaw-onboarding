#!/usr/bin/env python3
"""W4-04-U1 family 1 — fresh-box simulation: clean install of BOTH
distributions, then release_check must pass.

Owns no long-lived state: the box is either the driver's W404_BOX (kept for
the final --require-receipts run) or a scratch this test removes itself.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

check = _lib.check


def release_check(box, require_receipts=False, receipt=None, receipts_dir=None):
    return _lib.run_release_check(box, require_receipts=require_receipts,
                                  receipt=receipt, receipts_dir=receipts_dir)


def main():
    env_box = os.environ.get("W404_BOX")
    box = Path(env_box) if env_box else _lib.mktmp("box")
    owns_box = env_box is None
    broken = None
    noreceipts = None
    try:
        # --- clean install of both distributions into the fresh box ---
        _lib.build_fresh_box(box)
        check("fresh box built", box.is_dir(), str(box))
        p = _lib.box_paths(box)
        check("box holds distribution A", (p["a"] / "SKILL.md").is_file(),
              str(p["a"]))
        check("box holds distribution B", (p["b"] / "SKILL.md").is_file(),
              str(p["b"]))
        check("box holds 999 install manifest", p["registry"].is_file(),
              str(p["registry"]))

        receipt_path = _lib.RECEIPTS / "fresh-box-install.json"
        rc, data, out, err = release_check(box, receipt=str(receipt_path))
        check("release_check exit 0 on clean install", rc == 0,
              "rc=%s %s" % (rc, (err or out).strip()[-400:]))
        check("release_check verdict PASS", isinstance(data, dict)
              and data.get("verdict") == "PASS",
              str(data.get("verdict") if isinstance(data, dict) else data))
        if isinstance(data, dict):
            counts = data.get("counts", {})
            check("no FAIL rows on clean install", counts.get("fail") == 0,
                  json.dumps(counts))
            check("clean install reached every family",
                  set(data.get("families", {})) == {
                      "resolve", "manifest-comparison",
                      "clean-helper-install", "supported-versions",
                      "test-receipts", "migration-rollback-receipts"},
                  ",".join(sorted(data.get("families", {}))))
            # An absent receipt is UNDETERMINED, never a pass; a present one
            # must actually validate (schema/unit/verdict/covered sides).
            mig = data["families"]["migration-rollback-receipts"]
            for row in mig["checks"]:
                fname = row["check"].split()[-1]
                if (_lib.RECEIPTS / fname).is_file():
                    check("present receipt %s validates" % fname,
                          row["status"] == "pass", json.dumps(row))
                else:
                    check("absent receipt %s is UNDETERMINED, never PASS"
                          % fname,
                          row["status"] == "undetermined", json.dumps(row))
            und = data["families"]["test-receipts"]
            a_rows = [r for r in und["checks"] if r["check"] == "A test receipts"]
            check("distribution A ships no tests -> UNDETERMINED",
                  bool(a_rows) and a_rows[0]["status"] == "undetermined",
                  json.dumps(a_rows))

        # Deterministic proof of the absent-receipt branch: point release_check
        # at an empty receipts dir. Absent receipts are UNDETERMINED (never
        # PASS) and are not a failure on their own.
        noreceipts = _lib.mktmp("noreceipts")
        rc3, rec3, out3, err3 = release_check(box, receipts_dir=noreceipts)
        check("empty receipts dir still exits 0", rc3 == 0,
              "rc=%s %s" % (rc3, (err3 or out3).strip()[-300:]))
        rows3 = (rec3 or {}).get("families", {}).get(
            "migration-rollback-receipts", {}).get("checks", [])
        check("absent receipts reported UNDETERMINED",
              len(rows3) == 2 and all(r["status"] == "undetermined"
                                      for r in rows3),
              json.dumps(rows3))
        check("absent receipts never reported PASS",
              not any(r["status"] == "pass" for r in rows3),
              json.dumps(rows3))

        # --- negative control: a deliberately stale install must FAIL ---
        # Proves release_check discriminates (a check that never fails
        # proves nothing).
        broken = _lib.mktmp("broken")
        shutil.copytree(box, broken, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        bp = _lib.box_paths(broken)
        (bp["a"] / "SKILL.md").unlink()
        reg_text = bp["registry"].read_text().replace(_lib.DEPT_SLUG + "\n", "")
        bp["registry"].write_text(reg_text)

        # Expected-FAIL control goes to evidence/, not receipts/, so the
        # receipts directory only ever holds acceptance-facing verdicts.
        _lib.EVIDENCE.mkdir(parents=True, exist_ok=True)
        bad_receipt = _lib.EVIDENCE / "negative-control-stale-install.json"
        rc2, data2, out2, err2 = release_check(broken,
                                                receipt=str(bad_receipt))
        check("stale install fails release_check", rc2 == 1,
              "rc=%s %s" % (rc2, (err2 or out2).strip()[-400:]))
        check("stale install verdict FAIL", isinstance(data2, dict)
              and data2.get("verdict") == "FAIL",
              str(data2.get("verdict") if isinstance(data2, dict) else data2))
        if isinstance(data2, dict):
            fails = [r["check"] for fam in data2["families"].values()
                     for r in fam["checks"] if r["status"] == "fail"]
            check("negative control names the missing SKILL.md",
                  any("A ships SKILL.md" == f for f in fails),
                  json.dumps(fails))
            check("negative control names the registry gap",
                  any("999 registry lists" in f for f in fails),
                  json.dumps(fails))

        print("FRESH_INSTALL_OK box=%s" % box)
        return 0
    finally:
        if broken:
            _lib.rm_tmp(broken)
        if noreceipts:
            _lib.rm_tmp(noreceipts)
        if owns_box:
            _lib.rm_tmp(box)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # tooling failure, never a silent pass
        print("tooling-failure: %s" % exc, file=sys.stderr)
        sys.exit(2)
