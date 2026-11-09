#!/usr/bin/env python3
"""FIX-11 step 5 / FIX-10 invariant — single-root deployment assertion.

WHY THIS EXISTS
  Two skill roots can be present on one box (canonical `.openclaw/skills` and a
  shadow `.agents/skills` beside it). The loader then picks one, the two trees
  can carry different versions and different bytes, and every diagnosis made
  against one root may not describe the other. The repository-side remedy is
  an assertion the deployment runs: for every skill the release ships, there
  must be EXACTLY ONE installed tree, and its version must equal the version
  the release declares.

WHAT IT CHECKS (read-only; it never deletes, moves, symlinks or copies)
  1. Every skill directory the release ships (`<release>/<NN-name>/`, not
     `*ARCHIVED*`) is resolved to its installed trees across every root given,
     PLUS the `.agents/skills` shadow derived from each root. Skill identity is
     the name with its leading `NN-` numeric prefix removed, so the canonical
     `83-black-friday-launcher` and the shadow `black-friday-launcher` are one
     skill and collide.
  2. Two or more installed trees for one skill  -> FAIL, naming every path.
  3. Installed version != released version      -> FAIL, naming both versions.
     The version is `<tree>/skill-version.txt`; a missing file is reported as
     an unknown installed version, never as a pass.
  4. Exactly one tree at the released version   -> PASS for that skill.

USAGE
  assert-skill-single-tree.py --release DIR [--root DIR]... [--only CSV]

  --release  Release source tree (the extracted bundle whose numbered skill
             directories declare the release). Required.
  --root     Installed skills root. Repeatable. Default: $HOME/.openclaw/skills.
             For every root, `<root>/../../.agents/skills` is checked as well
             (the shadow beside it). A root that does not exist is skipped, so
             an absent shadow is simply the healthy case.
  --only     Comma-separated numeric skill prefixes, mirroring the updater's
             --only filter. Unset = every skill in the release.
  --skip     Comma-separated skill names this run deliberately did NOT install
             (the updater's operator-approved preserve paths, e.g. the Skill 75
             refuse gate). A skipped skill is reported as SKIP and its VERSION is
             not compared -- the run makes no deployment claim for it. A
             DUPLICATE tree under a skipped skill still FAILS: two installs of
             one skill are never acceptable, whatever the reason for the skip.

EXIT CODES
  0  assertion holds for every in-scope skill
  1  assertion failed (duplicate tree, or version not equal to the release)
  2  TOOLING-FAILURE — no verdict is possible (bad/missing --release, unreadable
     release version, no existing root, duplicate root spellings). Exit 2 is
     never folded into 0 or 1.
"""
import argparse
import os
import re
import sys

_NUMERIC_PREFIX = re.compile(r"^[0-9]+-")


def base_name(name):
    """`83-black-friday-launcher` -> `black-friday-launcher`."""
    return _NUMERIC_PREFIX.sub("", name)


def read_version(tree):
    p = os.path.join(tree, "skill-version.txt")
    try:
        with open(p, encoding="utf-8") as fh:
            value = fh.read().strip()
    except OSError:
        return None
    return value or None


def release_skills(release, only):
    """Ordered list of (release_dir_name, released_version_or_None)."""
    out = []
    try:
        entries = sorted(os.listdir(release))
    except OSError as exc:
        raise RuntimeError("cannot list release directory %s: %s" % (release, exc))
    for name in entries:
        path = os.path.join(release, name)
        if not os.path.isdir(path):
            continue
        if not _NUMERIC_PREFIX.match(name):
            continue
        if "ARCHIVED" in name:
            continue
        if only and name.split("-", 1)[0] not in only:
            continue
        out.append((name, read_version(path)))
    return out


def installed_trees(roots, target_base):
    """Every installed directory across roots whose base name matches."""
    found = []
    for root in roots:
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            continue
        for name in entries:
            path = os.path.join(root, name)
            if not os.path.isdir(path):
                continue
            if base_name(name) == target_base:
                found.append(path)
    return found


def derive_shadow_roots(roots):
    """`<home>/.openclaw/skills` -> `<home>/.agents/skills` (the shadow beside it)."""
    out = []
    for root in roots:
        home = os.path.dirname(os.path.dirname(os.path.abspath(root)))
        shadow = os.path.join(home, ".agents", "skills")
        if shadow not in out and shadow not in roots:
            out.append(shadow)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Assert one installed tree per skill, at the released version."
    )
    ap.add_argument("--release", required=True)
    ap.add_argument("--root", action="append", default=[])
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    args = ap.parse_args(argv)

    only = {p.strip() for p in args.only.split(",") if p.strip()}
    skip = {p.strip() for p in args.skip.split(",") if p.strip()}
    roots = args.root or [os.path.join(os.path.expanduser("~"), ".openclaw", "skills")]

    problems = []
    tooling = []

    if not os.path.isdir(args.release):
        tooling.append("--release is not a directory: %s" % args.release)
        for line in tooling:
            print("TOOLING-FAILURE: %s" % line, file=sys.stderr)
        return 2

    existing = [r for r in roots if os.path.isdir(r)]
    if not existing:
        tooling.append(
            "no installed skills root exists among: %s" % ", ".join(roots)
        )

    # Canonical spelling of every root we will inspect. A symlinked alias of a
    # root would otherwise report one tree twice as "two installations".
    seen = {}
    for root in existing + derive_shadow_roots(existing):
        if not os.path.isdir(root):
            continue
        real = os.path.realpath(root)
        if real in seen:
            continue
        seen[real] = root
    scanned = list(seen.values())

    try:
        skills = release_skills(args.release, only)
    except RuntimeError as exc:
        tooling.append(str(exc))
        skills = []

    if not skills:
        tooling.append(
            "no skill directories matched in the release (%s); refusing to report a pass"
            % args.release
        )

    passed = 0
    duplicate = 0
    mismatch = 0
    skipped = 0

    for release_dir, released in skills:
        target = base_name(release_dir)
        if released is None:
            tooling.append(
                "release declares no skill-version.txt for %s; cannot compare a version"
                % release_dir
            )
            continue
        trees = installed_trees(scanned, target)
        if len(trees) > 1:
            duplicate += 1
            problems.append(
                "FAIL: DUPLICATE-INSTALLED-TREE skill=%s count=%d paths=%s"
                % (target, len(trees), " | ".join(trees))
            )
            continue
        if not trees:
            if release_dir in skip or target in skip:
                skipped += 1
                print("SKIP: %s — not installed by this run (operator-approved preserve)" % release_dir)
                continue
            mismatch += 1
            problems.append(
                "FAIL: VERSION-MISMATCH skill=%s path=<not installed> installed=<absent> release=%s"
                % (release_dir, released)
            )
            continue
        tree = trees[0]
        installed = read_version(tree)
        if (release_dir in skip or target in skip):
            skipped += 1
            print("SKIP: %s — version not compared (operator-approved preserve)" % release_dir)
            continue
        if installed != released:
            mismatch += 1
            problems.append(
                "FAIL: VERSION-MISMATCH skill=%s path=%s installed=%s release=%s"
                % (
                    release_dir,
                    tree,
                    installed if installed is not None else "<no skill-version.txt>",
                    released,
                )
            )
            continue
        passed += 1

    for line in problems:
        print(line)

    for line in tooling:
        print("TOOLING-FAILURE: %s" % line, file=sys.stderr)

    print(
        "SUMMARY: skills=%d roots=%d passed=%d skipped=%d duplicate=%d mismatch=%d tooling_failures=%d"
        % (len(skills), len(scanned), passed, skipped, duplicate, mismatch, len(tooling))
    )

    if tooling:
        return 2
    if problems:
        return 1
    print(
        "OK: %d skills — exactly one installed tree each, at the released version"
        % passed
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
