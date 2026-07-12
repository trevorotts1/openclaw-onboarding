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

# Departments whose how-to-use guide is authored as a static seed file rather
# than rendered from the specialist index. These departments exist in the role
# library and MUST have a guide committed (the --check gate enforces this), but
# their roster is either entirely internal-hygiene roles (healer) or a routing
# layer rather than a client-facing specialist pool (master-orchestrator), so
# the renderer's output is degenerate. Their guides are ported from the
# feat/how-to-use-this-department-docs branch where they were hand-crafted to
# be accurate and owner-facing. --check verifies EXISTENCE only for these depts.
#
# rescue-rangers is the same class: it is an OPERATOR-ONLY terminal-escalation
# department (never client-facing, carries no intent triggers), and its folder
# holds department scaffolding files (CHANGELOG-RESCUE-DEPT.md,
# RELAY-BRAIN-PATCH.md, connection-manifest.json, etc.) alongside the five real
# role files. The generic renderer has no way to tell those scaffolding files
# apart from role files, so it parses their section headings as if they were
# specialist names (e.g. "Rescue Rangers Department - Build Log") and produces
# a client-facing template that misdescribes an operator-only department -
# degenerate output, same failure mode as healer/master-orchestrator. The
# committed guide is hand-crafted to accurately describe the escalation path,
# the real 5-role roster, and the OPERATOR-ONLY scope.
STATIC_SEED_DEPTS = {
    "healer",
    "master-orchestrator",
    "rescue-rangers",
}


def _dept_folders():
    out = []
    for entry in sorted(os.listdir(ROLE_LIBRARY)):
        full = os.path.join(ROLE_LIBRARY, entry)
        if not os.path.isdir(full):
            continue
        if entry.startswith("_") or entry.startswith("."):
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
            # Static-seed departments: existence check only. Their guides are
            # hand-crafted (the renderer produces degenerate specialist sections
            # for them) and must not be overwritten by --write. A committed file
            # is considered current as long as it is present and non-empty.
            if dept in STATIC_SEED_DEPTS:
                with open(path) as f:
                    content = f.read()
                if not content.strip():
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
        all_depts = _dept_folders()
        static_count = sum(1 for d in all_depts if d in STATIC_SEED_DEPTS)
        rendered_count = len(all_depts) - static_count
        print(f"OK: all {len(all_depts)} departments have a current "
              f"{DOC_NAME} ({rendered_count} rendered, "
              f"{static_count} static-seed).")
        return 0

    written = 0
    for dept in depts:
        if dept in STATIC_SEED_DEPTS:
            path = os.path.join(ROLE_LIBRARY, dept, DOC_NAME)
            if os.path.isfile(path):
                print(f"[how-to-use] skipping static-seed dept {dept} "
                      f"(hand-crafted guide already present)")
            else:
                print(f"[how-to-use] WARNING: static-seed dept {dept} has no "
                      f"guide -- seed it from feat/how-to-use-this-department-docs "
                      f"or author one; renderer produces degenerate output for it.",
                      file=sys.stderr)
            continue
        path, _ = _write_one(dept, meta_table)
        print(f"[how-to-use] wrote {path}")
        written += 1
    print(f"\n[how-to-use] {written} department guide(s) written.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
