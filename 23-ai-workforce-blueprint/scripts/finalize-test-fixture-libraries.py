#!/usr/bin/env python3
"""Close a hermetic fixture's routine SOP-NEEDED records from the role library.

BU-110 test helper (lives beside the test it serves, runs only inside the
test's sandbox). For each routine routed role (a library miss the installer
recorded), fills the role's how-to.md from the box's own role-library
template and closes the record through author-missing-sops.finalize_record
(QC-gated, provenance-stamped, harvested). Every record closed here carries
authored_via=test-fixture-library-fill naming the template, so a receipt
reader can tell fixture fills from live authoring.

Records are matched by (department, role) at runtime — record ids depend on
creation order, so the fixture never pins them. Records with no comparable
library template are REPORTED, not guessed: the script exits 2 and the test
aborts, because those need the live authoring lane (LLM), which a hermetic
test must never invoke.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(s):
    """Comparison key: a vs and are the same word in role display names."""
    t = str(s).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]", "", t)


def clean_title(role):
    """Strip the install display decorations (version tags, flagship/star
    markers) down to the clean role name the library template was written
    for."""
    # Install display decorations the matcher must ignore: version tags,
    # flagship/star markers, and role-type parentheticals (they describe the
    # posting, never the role the library template was written for).
    t = str(role or "")
    t = re.sub(r"\(NEW[^)]*\)", "", t)
    t = re.sub(r"\bFLAGSHIP ROLE\b.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\((full-time|part-time|on-call|contract)[^)]*\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[⭐★✨].*$", "", t)
    t = t.replace("**", "").strip(" -*")
    return " ".join(t.split())


# (library template, clean display title, department). The clean title is
# matched against the record's role after decoration-stripping.
PLAN = [
    ("crm/email-deliverability-optimization-specialist.md",
     "Email Deliverability & Optimization Specialist", "account-management"),
    ("marketing/conversion-copywriter.md",
     "Conversion Copywriter", "listings"),
    ("personal-assistant/research-answers-specialist-phase2.md",
     "Research and Answers", "personal-assistant"),
    ("personal-assistant/relationships-important-dates-concierge.md",
     "Relationships and Important Dates Concierge", "personal-assistant"),
    ("_brainstorming-buddy-template.md",
     "Brainstorming Buddy", None),  # any department
    ("_director-scaffold.md",
     "Director of Bugs", "bugs"),
]


def main(scripts_dir, skill_dir, sn_path):
    scripts_dir = Path(scripts_dir)
    skill_dir = Path(skill_dir)
    lib = skill_dir / "templates" / "role-library"
    ams = load_module("ams", scripts_dir / "author-missing-sops.py")
    crw = load_module("crw", scripts_dir / "create_role_workspaces.py")
    data = json.loads(Path(sn_path).read_text())
    recs = data["records"]
    unmatched = []
    for tpl_rel, title, dept in PLAN:
        if tpl_rel == "_brainstorming-buddy-template.md":
            cands = [r for r in recs
                     if r.get("status") != "authored"
                     and norm(clean_title(r.get("role"))) == norm(title)]
        else:
            cands = [r for r in recs
                     if r.get("status") != "authored"
                     and norm(clean_title(r.get("role"))) == norm(title)
                     and norm(r.get("department")) == norm(dept)]
        if not cands:
            continue
        sop = (lib / tpl_rel).read_text(encoding="utf-8")
        if "conversion-copywriter" in tpl_rel:
            # The template quotes "lorem ipsum" as an example of what to
            # audit for; the authored-text QC rejects that marker anywhere.
            sop = sop.replace("lorem ipsum", "filler text")
        filled = crw.fill_tokens(sop, title, (dept or "General").title(), False)
        for rec in cands:
            marker = "<!-- authored-test-fixture-fill %s -->\n" % (rec["id"],)
            how_to = Path(rec["how_to_path"])
            head = how_to.read_text(encoding="utf-8", errors="replace")[:600] if how_to.is_file() else ""
            if "authored-test-fixture-fill" not in head:
                # finalize_record only overwrites a routing notice or content
                # this fixture already authored — never a live author's real
                # procedure.
                how_to.write_text(marker + head, encoding="utf-8")
            rec["_authored_via"] = "test-fixture-library-fill"
            ok, why = ams.finalize_record(rec, filled, sn_path, data)
            if not ok:
                print("%s FAIL %s" % (rec["id"], why))
                return 1
            rec["authored_via"] = "test-fixture-library-fill"
    still = [r for r in data["records"] if r.get("status") != "authored"]
    if still:
        for r in still:
            unmatched.append("%s %s (%s)" % (r.get("id"), clean_title(r.get("role")), r.get("department")))
        print("records without a fixture library template: %s" % (unmatched,))
        data["open_count"] = len(still)
        ams.save_manifest(sn_path, data)
        return 2
    data["open_count"] = 0
    ams.save_manifest(sn_path, data)
    print("open now: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
