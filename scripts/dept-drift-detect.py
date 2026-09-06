#!/usr/bin/env python3
"""
dept-drift-detect.py — MATERIALIZED-DEPARTMENT DRIFT DETECTOR (FIX-DELIVERY-06).

*** READ-ONLY. This tool NEVER writes to, creates, or deletes anything inside a
*** department. It opens files for reading and prints a report. There is no
*** --apply, no --fix, and no write path anywhere in this file, by design.

────────────────────────────────────────────────────────────────────────────
THE DEFECT
────────────────────────────────────────────────────────────────────────────
Deploying a skill does not re-materialize a department that already exists.
Proven live: after deploying skill 23 at v24.2.2 the skill tree matched the
release tag EXACTLY (0 differing code files) while 36 files in the
already-provisioned department were stale — some old enough to still name
`~/.clawdbot`, the PRE-RENAME product name, whose directory does not exist.
The department's SOUL.md was missing a whole doctrine block and its SOPs cited
retired role numbering.

docs/SHARED-CORE-FILES.md covers only AGENTS.md / TOOLS.md / USER.md, which
link_shared_core_files() re-copies from CANON_DIR on every roll
(update-skills.sh:1788). A department's own SOUL.md, BUILDER-PROMPT.md, role
how-to.md files and sops/ are covered by NOTHING and simply rot.

────────────────────────────────────────────────────────────────────────────
WHY THIS IS A DETECTOR AND NOT A RE-MATERIALIZER
────────────────────────────────────────────────────────────────────────────
A department is NOT a pure copy of its template. On a live box, 219 of 670
box-only lines were legitimately the operator's:

  * TOOLS.md carries skill-wired blocks written by six different wire.sh
    scripts, in TWO marker dialects that both occur live:
        <!-- BEGIN skill-41 tools -->            ... <!-- END skill-41 tools -->
        <!-- BEGIN skill:07-kie-setup:tools -->  ... <!-- END skill:07-kie-setup:tools -->
  * IDENTITY.md carries <!-- PRESERVED FROM ... --> blocks that
    docs/SHARED-CORE-FILES.md says are "only ever added to, never
    overwritten". Three safety lines inside one existed NOWHERE ELSE on the
    box. These blocks have NO end marker — they are appended, so the preserved
    region runs from the first PRESERVED marker to end-of-file.

Blindly re-copying the template would destroy all of it. So this tool reports
and classifies; a human decides. Any future auto-repair must consume this
classification, never a naive file copy.

────────────────────────────────────────────────────────────────────────────
CLASSIFICATION (per file, per line)
────────────────────────────────────────────────────────────────────────────
  stale_template     Template content the box does not have. The template moved
                     ahead and the box never received it. THIS is the drift.
  preserved_wired    Box content inside a skill-wired or PRESERVED block. Must
                     never be overwritten. Never counted as stale.
  provisioner_subst  A template line carrying {{TOKEN}} placeholders whose box
                     counterpart is the same line with the tokens filled in
                     (post-build-role-workspaces.py's job). Expected, not drift.
  local_authored     Box-only content that is NOT inside a marker block and is
                     NOT explained by token substitution. Unclassified local
                     authorship — treat as the operator's until proven
                     otherwise. Never counted as stale.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --dept <dir>       materialized department directory (required)
  --library <dir>    role-library department template dir (required)
  --json             machine-readable report
  --show <n>         show up to n sample stale lines per file (default 3)
  --fail-on-stale    exit 1 when any file has stale_template lines (for CI /
                     doctor-style callers). Default exit is 0 unless the tool
                     could not run.

EXIT CODES
  0  ran successfully (and, with --fail-on-stale, found no stale content)
  1  --fail-on-stale was given and at least one file is behind its template
  2  could not run (missing dept or library dir)
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# Skill-wired blocks. BOTH dialects observed live on Trevor's box.
_WIRED_BEGIN = re.compile(r"<!--\s*BEGIN\s+skill[:\-][^>]*-->", re.I)
_WIRED_END = re.compile(r"<!--\s*END\s+skill[:\-][^>]*-->", re.I)
# Append-only preserved blocks (no end marker — region runs to EOF).
_PRESERVED = re.compile(r"<!--\s*PRESERVED\s+FROM\b[^>]*-->", re.I)
_TOKEN = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Files that are box-shared, not department-owned: link_shared_core_files()
# re-copies these from CANON_DIR every roll, so comparing them to a role-library
# template would report drift that is by-design (see docs/SHARED-CORE-FILES.md).
_SHARED_CORE = {"AGENTS.md", "USER.md"}

# Never compared: caches, backups, per-agent runtime state.
_SKIP_NAMES = {"MEMORY.md", "HEARTBEAT.md", "DREAMS.md", ".DS_Store"}
_SKIP_DIR_PARTS = {"__pycache__", ".git", ".pytest_cache"}


def _is_skippable(rel: Path) -> bool:
    if any(part in _SKIP_DIR_PARTS for part in rel.parts):
        return True
    name = rel.name
    if name in _SKIP_NAMES or name in _SHARED_CORE:
        return True
    if ".bak" in name or name.endswith(".pyc") or ".preserved-" in name:
        return True
    return False


def protected_line_indices(lines):
    """Indices of box lines inside a skill-wired block or the PRESERVED tail.

    Wired blocks are BEGIN/END delimited. PRESERVED blocks have no end marker
    (docs/SHARED-CORE-FILES.md: 'only ever added to'), so from the FIRST
    PRESERVED marker onward every line is protected.
    """
    protected = set()
    in_wired = False
    preserved_from = None
    for i, ln in enumerate(lines):
        if _PRESERVED.search(ln) and preserved_from is None:
            preserved_from = i
        if _WIRED_BEGIN.search(ln):
            in_wired = True
        if in_wired:
            protected.add(i)
        if _WIRED_END.search(ln):
            in_wired = False
    if in_wired:
        # Unterminated wired block: protect to EOF rather than risk calling an
        # operator's block "local_authored" on a malformed marker.
        protected.update(range(len(lines)))
    if preserved_from is not None:
        protected.update(range(preserved_from, len(lines)))
    return protected


def token_regex(template_line: str):
    """Regex matching a template line with every {{TOKEN}} filled by any value."""
    parts = _TOKEN.split(template_line)
    # ".*?" not ".+?": a token filled with an EMPTY value (observed live —
    # how-to-use-this-department.md has "**Generated for:** " with nothing after
    # it) is still a provisioner substitution, which is what this classifies. An
    # empty fill is a provisioning-data problem, not template drift, and calling
    # it stale would overstate how far behind the department actually is.
    return re.compile("^" + ".*?".join(re.escape(p) for p in parts) + "$")


def classify_file(tpl_text: str, box_text: str):
    tpl_lines = tpl_text.splitlines()
    box_lines = box_text.splitlines()
    protected = protected_line_indices(box_lines)

    stale, local, subst, preserved = [], [], [], []
    globally_matched = set()  # box lines already claimed by a global token match
    sm = difflib.SequenceMatcher(None, tpl_lines, box_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        tpl_chunk = [(i, tpl_lines[i]) for i in range(i1, i2)]
        box_chunk = [(j, box_lines[j]) for j in range(j1, j2)]

        # Pair up template lines that are token-substituted versions of box lines.
        # The candidate search is GLOBAL over the box file, not limited to this
        # diff chunk: difflib frequently aligns a token line and its filled
        # counterpart into different opcodes (e.g. "**Generated for:**
        # {{COMPANY_NAME}}" vs "**Generated for:** BlackCEO"), and a chunk-local
        # search would then misreport an ordinary provisioner substitution as
        # stale template content.
        matched_box = set()
        remaining_tpl = []
        for i, tline in tpl_chunk:
            if _TOKEN.search(tline):
                rx = token_regex(tline)
                hit = next((j for j, bline in box_chunk
                            if j not in matched_box and rx.match(bline)), None)
                if hit is None:
                    hit = next((j for j in range(len(box_lines))
                                if j not in globally_matched and rx.match(box_lines[j])), None)
                    if hit is not None:
                        globally_matched.add(hit)
                if hit is not None:
                    matched_box.add(hit)
                    subst.append({"template_line": i + 1, "text": tline.strip()[:200]})
                    continue
            remaining_tpl.append((i, tline))

        for i, tline in remaining_tpl:
            if tline.strip():
                stale.append({"template_line": i + 1, "text": tline.strip()[:200]})
        for j, bline in box_chunk:
            if j in matched_box or not bline.strip():
                continue
            if j in protected:
                preserved.append({"box_line": j + 1, "text": bline.strip()[:200]})
            else:
                local.append({"box_line": j + 1, "text": bline.strip()[:200]})

    return {"stale_template": stale, "local_authored": local,
            "provisioner_subst": subst, "preserved_wired": preserved}


def build_pairs(library: Path, dept: Path):
    """(relative label, template file, box file, present) for everything comparable.

    Two mappings, both real:
      1. same relative path (SOUL.md, BUILDER-PROMPT.md, sops/*.md, scripts/**)
      2. a library role `<slug>.md` -> the dept's `NN-<slug>/how-to.md`
         (create_role_workspaces.py writes the role dir as NN-<clean-slug>/ with a
         token-filled how-to.md).
    """
    pairs = []
    # role slug -> dept role dir, discovered from the box (numbering is the box's)
    role_dirs = {}
    for d in sorted(dept.iterdir()):
        if d.is_dir():
            m = re.match(r"^(\d+)-(.+)$", d.name)
            if m:
                role_dirs.setdefault(m.group(2), []).append(d)

    for tpl in sorted(library.rglob("*")):
        if not tpl.is_file():
            continue
        rel = tpl.relative_to(library)
        if _is_skippable(rel):
            continue
        same = dept / rel
        if same.is_file():
            pairs.append((str(rel), tpl, same, True))
            continue
        # role mapping: top-level <slug>.md -> NN-<slug>/how-to.md
        if len(rel.parts) == 1 and rel.suffix == ".md":
            slug = rel.stem
            for rd in role_dirs.get(slug, []):
                how = rd / "how-to.md"
                if how.is_file():
                    pairs.append((f"{rel} -> {rd.name}/how-to.md", tpl, how, True))
                    break
            else:
                pairs.append((str(rel), tpl, same, False))
            continue
        pairs.append((str(rel), tpl, same, False))
    return pairs


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="READ-ONLY drift report for a materialized department vs its role-library template.")
    ap.add_argument("--dept", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show", type=int, default=3)
    ap.add_argument("--fail-on-stale", action="store_true")
    args = ap.parse_args(argv)

    dept, library = Path(args.dept), Path(args.library)
    if not dept.is_dir():
        print(f"FATAL: department dir not found: {dept}", file=sys.stderr)
        return 2
    if not library.is_dir():
        print(f"FATAL: library template dir not found: {library}", file=sys.stderr)
        return 2

    files, missing = [], []
    for label, tpl, box, present in build_pairs(library, dept):
        if not present:
            missing.append(label)
            continue
        try:
            tpl_text = tpl.read_text(errors="replace")
            box_text = box.read_text(errors="replace")
        except OSError as e:
            files.append({"file": label, "error": str(e)})
            continue
        if tpl_text == box_text:
            continue
        r = classify_file(tpl_text, box_text)
        if not any(r.values()):
            continue
        files.append({
            "file": label,
            "box_path": str(box),
            "stale_template": len(r["stale_template"]),
            "local_authored": len(r["local_authored"]),
            "provisioner_subst": len(r["provisioner_subst"]),
            "preserved_wired": len(r["preserved_wired"]),
            "stale_samples": r["stale_template"][:args.show],
        })

    stale_files = [f for f in files if f.get("stale_template")]
    report = {
        "dept": str(dept),
        "library": str(library),
        "files_compared": len(files),
        "files_behind_template": len(stale_files),
        "files_missing_from_dept": len(missing),
        "totals": {
            k: sum(f.get(k, 0) for f in files)
            for k in ("stale_template", "local_authored", "provisioner_subst", "preserved_wired")
        },
        "files": files,
        "missing_from_dept": missing,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("== MATERIALIZED-DEPARTMENT DRIFT REPORT (READ-ONLY) ==")
        print(f"   department : {dept}")
        print(f"   template   : {library}")
        print(f"   files differing from template : {len(files)}")
        print(f"   files BEHIND the template     : {len(stale_files)}")
        print(f"   template files absent on box  : {len(missing)}")
        t = report["totals"]
        print("\n   line classification across all differing files:")
        print(f"     stale_template     (box is behind)      : {t['stale_template']}")
        print(f"     preserved_wired    (must NOT overwrite) : {t['preserved_wired']}")
        print(f"     provisioner_subst  (token fill, normal) : {t['provisioner_subst']}")
        print(f"     local_authored     (box-only, keep)     : {t['local_authored']}")
        if stale_files:
            print("\n   FILES BEHIND THEIR TEMPLATE (stale / preserved / local / subst):")
            for f in sorted(stale_files, key=lambda x: -x["stale_template"]):
                print(f"     {f['stale_template']:5d} / {f['preserved_wired']:3d} / "
                      f"{f['local_authored']:3d} / {f['provisioner_subst']:3d}   {f['file']}")
                for s in f["stale_samples"]:
                    print(f"             + {s['text'][:110]}")
        protected_files = [f for f in files if f.get("preserved_wired")]
        if protected_files:
            print("\n   FILES WITH PROTECTED BLOCKS (never auto-overwrite these):")
            for f in protected_files:
                print(f"     {f['preserved_wired']:5d} protected line(s)   {f['file']}")
        print("\n   NOTE: this tool made no changes. It has no write path.")

    if args.fail_on_stale and stale_files:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
