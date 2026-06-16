#!/usr/bin/env python3
"""
generate_how_to_use_docs.py - write a "How to Use This Department" guide into
EVERY department in templates/role-library/.

These committed artifacts are the canonical, fully-tokenized templates: company
fields stay as {{COMPANY_NAME}} / {{GENERATION_DATE}} so there are NO client
names in the repo. The specialist content is derived from each department's REAL
roles (suggested-roles markdown), so each guide matches the specialists that
actually exist in that department.

At build time, build-workforce.py imports how_to_use_department.render_how_to_use
and writes a personalized copy (company tokens filled) into each client's
departments/<dept>/ folder.

Usage:
  python3 generate_how_to_use_docs.py            # write all departments
  python3 generate_how_to_use_docs.py --check     # verify all present + current
  python3 generate_how_to_use_docs.py <dept>      # write one department
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROLE_LIBRARY = os.path.join(SKILL_DIR, "templates", "role-library")
DOC_NAME = "how-to-use-this-department.md"

sys.path.insert(0, HERE)
import how_to_use_department as htu  # noqa: E402

# Department folders that are internal scaffolding, not client-facing
# departments, so they do not get a client-facing how-to-use guide.
SKIP_FOLDERS = {
    "master-orchestrator",  # the CEO/router is not a "department" the client uses
    "healer",               # internal hygiene mechanism, never client-surfaced
}


def _dept_folders():
    out = []
    for entry in sorted(os.listdir(ROLE_LIBRARY)):
        full = os.path.join(ROLE_LIBRARY, entry)
        if not os.path.isdir(full):
            continue
        if entry.startswith("_") or entry.startswith("."):
            continue
        if entry in SKIP_FOLDERS:
            continue
        out.append(entry)
    return out


def _write_one(dept, meta_table):
    md = htu.render_how_to_use(dept, meta_table=meta_table)
    path = os.path.join(ROLE_LIBRARY, dept, DOC_NAME)
    with open(path, "w") as f:
        f.write(md)
    return path, md


def main(argv):
    check = "--check" in argv
    positional = [a for a in argv if not a.startswith("--")]
    meta_table = htu._dept_metadata()

    depts = [positional[0]] if positional else _dept_folders()

    if check:
        missing = []
        stale = []
        for dept in _dept_folders():
            path = os.path.join(ROLE_LIBRARY, dept, DOC_NAME)
            if not os.path.isfile(path):
                missing.append(dept)
                continue
            expected = htu.render_how_to_use(dept, meta_table=meta_table)
            with open(path) as f:
                actual = f.read()
            if actual != expected:
                stale.append(dept)
        if missing or stale:
            if missing:
                print("MISSING how-to-use-this-department.md:", file=sys.stderr)
                for d in missing:
                    print(f"  - {d}", file=sys.stderr)
            if stale:
                print("STALE (regenerate needed):", file=sys.stderr)
                for d in stale:
                    print(f"  - {d}", file=sys.stderr)
            print("\nFIX: python3 23-ai-workforce-blueprint/scripts/"
                  "generate_how_to_use_docs.py", file=sys.stderr)
            return 1
        print(f"OK: all {len(_dept_folders())} departments have a current "
              f"{DOC_NAME}.")
        return 0

    written = 0
    for dept in depts:
        path, _ = _write_one(dept, meta_table)
        print(f"[how-to-use] wrote {path}")
        written += 1
    print(f"\n[how-to-use] {written} department guide(s) written.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
