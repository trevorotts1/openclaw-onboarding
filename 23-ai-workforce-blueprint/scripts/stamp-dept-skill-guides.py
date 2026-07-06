#!/usr/bin/env python3
"""
stamp-dept-skill-guides.py — Layer-B (owner-facing) generator/validator
(PRD Departments-That-Use-Skills §5.2, Wave 1.3a).

Reads the ONE source of truth `skill-department-map.json` (Layer D) and stamps a
marker-guarded **"Skills This Department Can Operate For You"** block into every
OWNING department's owner-facing guide
`templates/role-library/<dept>/how-to-use-this-department.md`.

WHY: the role how-to.md carries the specialist-facing "Skills You Operate" block
(stamp-skills-you-operate.py); this is its OWNER-facing twin — so the owner guide
and the SKILL_INTENT_ROUTING_REFLEX_V1 front-door reflex speak the SAME plain
language. An owner who reads "make me some ads" in this guide and the CEO's reflex
route the same intent to the same department. GENERATED/VALIDATED from the map so
the owner guide can never silently desync (mirrors N38 six-source discipline).

Each block lists, for the client-facing skills THIS department owns per the map,
the plain-language intent phrasings ("if you say something like…") mapped to what
the department will do — NO skill numbers-as-jargon required of the owner, NO
on-box paths (owner-facing: plain language only, per TYP).

The block is marker-guarded (`<!-- DEPT_SKILLS_V1 -->` … `<!-- END … -->`) so
stamping is idempotent and byte-stable across re-runs, and contains NO canonical
`{{UPPER_TOKEN}}` fill tokens (the guides carry {{COMPANY_NAME}}/{{GENERATION_DATE}}
elsewhere, but this block adds none). NOTE: how-to-use-this-department.md is NOT
tracked by hash-content-manifest.py (it is a build-time-rendered guide, not a
hashed role/SOP/persona artifact) — editing it needs NO content-hash re-stamp.

USAGE
    python3 stamp-dept-skill-guides.py            # stamp/refresh all owning dept guides
    python3 stamp-dept-skill-guides.py --dry-run   # report what would change, write nothing
    python3 stamp-dept-skill-guides.py --check      # assert every owning dept guide carries a
                                                    # CURRENT block (rc 8 on drift); writes nothing

EXIT CODES
    0  all owning dept guides carry a current, correct block
    8  --check found a missing/stale block (drift)
    2  could not load the map
"""
import argparse
import json
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPT_DIR)                     # 23-ai-workforce-blueprint/
_MAP_PATH = os.path.join(_SKILL_DIR, "skill-department-map.json")
_LIBRARY_DIR = os.path.join(_SKILL_DIR, "templates", "role-library")

START = "<!-- DEPT_SKILLS_V1 -->"
END = "<!-- END DEPT_SKILLS_V1 -->"

# Strip the block AND any blank line(s) hugging it, so a re-stamp is byte-stable.
_BLOCK_RE = re.compile(
    r"\n*" + re.escape(START) + r".*?" + re.escape(END) + r"[ \t]*\n*",
    re.DOTALL,
)
# Insert immediately BEFORE the "## 5." section ("What to Expect Back"), so the
# capabilities (Section 4 specialists + this skills block) sit together ahead of
# the process sections. Every guide carries this heading (verified).
_SEC5_RE = re.compile(r"^##\s*5\.", re.MULTILINE)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def owning_depts_skills(m):
    """dept_slug -> list of client-facing skill entries that dept owns (dedup)."""
    depts = {}
    for s in m["skills"]:
        if not s.get("client_facing"):
            continue
        seen = set()
        for r in s.get("roles", []):
            d = r["dept"]
            if d in seen:
                continue
            seen.add(d)
            depts.setdefault(d, [])
            if s not in depts[d]:
                depts[d].append(s)
    return depts


def _first_sentence(text):
    text = (text or "").strip()
    # split on the first period that ends a clause; keep it short + plain.
    m = re.search(r"^(.*?[.:])(\s|$)", text)
    frag = m.group(1) if m else text
    return frag.rstrip(" .:").strip()


def _say_phrases(skill, limit=4):
    trg = [t for t in skill.get("intent_triggers", []) if t][:limit]
    return " · ".join(f'"{t}"' for t in trg) if trg else "(a request in this area)"


def build_block(skills):
    """Render the owner-facing Skills block for one department's skills."""
    skills = sorted(skills, key=lambda s: int(s["skill"]))
    lines = [
        START,
        "## Skills This Department Can Operate For You 🛠️",
        "",
        "You never have to know these by name or type a command. Just say what you "
        "want in plain English, and this department reaches for the right pre-built "
        "engine (\"skill\") for you automatically. These are the ones it can run on "
        "your behalf:",
        "",
        "| If you say something like… | This department will… |",
        "|---|---|",
    ]
    for s in skills:
        lines.append(f"| {_say_phrases(s)} | {_first_sentence(s['description'])} |")
    lines += [
        "",
        "You do not have to get the routing right or name the skill. The "
        "plain-language ask is enough. See `universal-sops/native-skill-invocation.md` "
        "for how your specialists reach for these from your intent.",
        END,
    ]
    return "\n".join(lines)


def stamp_text(text, block):
    """Return (new_text, changed). Idempotent + byte-stable: strip any existing
    block (normalizing the join to a single blank line), then insert fresh
    immediately before the "## 5." heading (or append at EOF as a fallback)."""
    base = _BLOCK_RE.sub("\n\n", text)
    m5 = _SEC5_RE.search(base)
    if m5:
        pos = m5.start()
        new = base[:pos] + block + "\n\n" + base[pos:]
        return new, (new != text)
    new = base.rstrip("\n") + "\n\n" + block + "\n"
    return new, (new != text)


def _guide_path(dept):
    return os.path.join(_LIBRARY_DIR, dept, "how-to-use-this-department.md")


def check_all(map_path=_MAP_PATH, library_dir=_LIBRARY_DIR):
    """Assert every owning department's guide carries a CURRENT block.
    Returns (drift, n_depts). Reused by qc-assert-repo-consistency.py."""
    m = load_json(map_path)
    depts = owning_depts_skills(m)
    drift = []
    for dept, skills in sorted(depts.items()):
        path = os.path.join(library_dir, dept, "how-to-use-this-department.md")
        if not os.path.isfile(path):
            drift.append(f"{dept}/how-to-use-this-department.md: file missing on disk")
            continue
        text = open(path, encoding="utf-8").read()
        _, changed = stamp_text(text, build_block(skills))
        if changed:
            drift.append(f"{dept}/how-to-use-this-department.md: DEPT_SKILLS block missing or stale")
    return drift, len(depts)


def main(argv):
    ap = argparse.ArgumentParser(description="Stamp/validate owner-facing dept skill guides from the map.")
    ap.add_argument("--check", action="store_true", help="assert current; write nothing; rc 8 on drift")
    ap.add_argument("--dry-run", action="store_true", help="report changes; write nothing")
    args = ap.parse_args(argv)

    try:
        m = load_json(_MAP_PATH)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: could not load map: {e}", file=sys.stderr)
        return 2

    depts = owning_depts_skills(m)
    changed_files = []
    drift = []

    for dept, skills in sorted(depts.items()):
        path = _guide_path(dept)
        rel = os.path.relpath(path, _SKILL_DIR)
        if not os.path.isfile(path):
            drift.append(f"{rel}: file missing on disk")
            continue
        text = open(path, encoding="utf-8").read()
        new, changed = stamp_text(text, build_block(skills))
        if changed:
            changed_files.append(rel)
            if args.check:
                drift.append(f"{rel}: DEPT_SKILLS block missing or stale")
            elif not args.dry_run:
                open(path, "w", encoding="utf-8").write(new)

    if args.check:
        if drift:
            print(f"FAIL — {len(drift)} dept guide(s) with missing/stale DEPT_SKILLS block:")
            for d in drift:
                print("  x " + d)
            return 8
        print(f"OK — all {len(depts)} owning dept guides carry a current DEPT_SKILLS block.")
        return 0

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {len(changed_files)} of {len(depts)} owning dept guide file(s).")
    for f in changed_files:
        print("  ~ " + f)
    if drift:
        print("\nWARNINGS:")
        for d in drift:
            print("  ! " + d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
