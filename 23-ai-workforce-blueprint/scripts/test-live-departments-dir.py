#!/usr/bin/env python3
"""test-live-departments-dir.py — acceptance test for BU-103 (WF-124).

resolve_live_departments_dir() is the ONE answer to "where do this company's
departments live". The fixtures are the four real box shapes:

  A. complete workspace tree with dept agents registered on it, plus a sparse
     second company tree recorded as companyRoot (the box of
     test_skill23_build_nondestructive.py): the AGENTS decide -> workspace tree.
  B. launch layout: only <companyRoot>/departments exists, no agents.
  C. both trees, no agents; the state's three slugs live in the company tree,
     one of them in the workspace tree: the highest score wins.
  D. nothing exists: (None, "none").

Run: python3 test-live-departments-dir.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _qc_paths import resolve_live_departments_dir  # noqa: E402

PASS = 0
FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS: {label}")
        PASS += 1
    else:
        print(f"  FAIL: {label}: got {got!r} want {want!r}")
        FAIL += 1


def mkdepts(root, *slugs):
    for slug in slugs:
        (Path(root) / slug).mkdir(parents=True, exist_ok=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(os.path.realpath(tmp))

        # ---- Fixture A: agents on a complete tree beat a sparse companyRoot ----
        print("=== A: registered dept agents decide the tree ===")
        home = tmp / "a"
        oc = home / ".openclaw"
        ws = oc / "workspace"
        live = ws / "departments"
        mkdepts(live, "marketing", "sales")
        for d in ("marketing", "sales"):
            (live / d / "SOUL.md").write_text("complete\n")
        sparse = home / "Downloads" / "openclaw-master-files" / "zero-human-company" / "acme" / "departments"
        mkdepts(sparse, "marketing", "sales", "support")
        state_a = {"interviewComplete": True,
                   "companyRoot": str(sparse.parent), "companySlug": "acme"}
        (ws / ".workforce-build-state.json").write_text(json.dumps(state_a))
        cfg_a = oc / "openclaw.json"
        cfg_a.write_text(json.dumps({"agents": {"entries": {
            "main": {"workspace": str(ws)},
            "dept-marketing": {"workspace": str(live / "marketing")},
            "dept-sales": {"workspace": str(live / "sales")},
            "dept-support": {"workspace": str(home / "deleted" / "support")},
        }}}))
        got_a = resolve_live_departments_dir(state_a, ws)
        check("A folder is the workspace tree", got_a[0], live.resolve())
        check("A reason is agents", got_a[1], "agents")

        # ---- Fixture B: launch layout, company tree only, no agents ----
        print("=== B: launch layout resolves the company tree ===")
        home_b = tmp / "b"
        (home_b / ".openclaw" / "workspace").mkdir(parents=True)
        company_b = home_b / "zero-human-company" / "acme"
        mkdepts(company_b / "departments", "marketing", "sales", "support")
        state_b = {"companyRoot": str(company_b), "companySlug": "acme",
                   "departments": [{"slug": "marketing", "status": "done"},
                                   {"slug": "sales", "status": "done"},
                                   {"slug": "support", "status": "done"}]}
        got_b = resolve_live_departments_dir(state_b, home_b / ".openclaw" / "workspace")
        check("B folder is the company tree", got_b[0], (company_b / "departments").resolve())

        # ---- Fixture C: both trees, no agents, the state's slugs decide ----
        print("=== C: the tree holding the state's departments wins ===")
        home_c = tmp / "c"
        ws_c = home_c / ".openclaw" / "workspace"
        mkdepts(ws_c / "departments", "marketing")
        company_c = home_c / "zero-human-company" / "acme" / "departments"
        mkdepts(company_c, "marketing", "sales", "support")
        state_c = {"companyRoot": str(company_c.parent), "companySlug": "acme",
                   "departments": [{"slug": "marketing"}, {"slug": "sales"},
                                   {"slug": "support"}]}
        got_c = resolve_live_departments_dir(state_c, ws_c)
        check("C folder is the company tree", got_c[0], company_c.resolve())

        # ---- Fixture D: nothing exists ----
        print("=== D: nothing exists ===")
        got_d = resolve_live_departments_dir({}, tmp / "d" / "nothing" / "workspace")
        check("D result", got_d, (None, "none"))

    print()
    print(f"passed={PASS} failed={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
