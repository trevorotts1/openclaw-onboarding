#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

SKILL_NAME = "blackceo-signature-page"
# The authority artifact is read by launch_context._registry_policy_ids from
# skill_root.parent / "shared-utils/...", with allow_vendored=False.
REGISTRY_REL = Path("shared-utils") / "signature_launch" / "domain"
REGISTRY_FILES = ("prompt-policy-registry.json",
                  "prompt-policy-registry.schema.json")
# Files a genuine install of this skill always carries. --update replaces the
# whole tree, so identity is proven against these before anything is touched.
REQUIRED_FILES = (
    "scripts/stage_executor.py",
    "scripts/build_production_request.py",
    "references/stage-contract.json",
    "references/copy-specs/standard-v6.json",
)
VERSION_RE = re.compile(r"^\d+(?:\.\d+)+$")
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
DEFAULT_ROOTS = {
    "claude-code": [Path.home() / ".claude" / "skills"],
    "codex": [Path.home() / ".agents" / "skills", Path.home() / ".codex" / "skills"],
}


def within(path, root):
    try:
        return os.path.commonpath([str(path), str(root)]) == str(root)
    except ValueError:
        return False


def escapes_root(dst, root):
    """True when dst is outside root, is a symlink leaf, or sits under a symlinked ancestor."""
    if not within(dst, root):
        return True
    # Refuse a symlink leaf outright: copyfile would follow it and overwrite
    # whatever it points at, inside the root or far outside it.
    if dst.is_symlink():
        return True
    if not Path(root).exists():
        # An absent root holds nothing, so nothing inside it can be a symlink yet.
        return False
    resolved_root = Path(root).resolve()
    anchor = dst.parent
    while not (anchor.is_symlink() or anchor.exists()):
        if anchor.parent == anchor:
            break
        anchor = anchor.parent
    try:
        resolved = anchor.resolve()
    except OSError:
        return True
    return not within(resolved, resolved_root)


def frontmatter_name(skill_md):
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            value = line[len("name:"):].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value.strip()
    return None


def version_problem(target):
    seen = []
    for name in ("VERSION", "skill-version.txt"):
        path = target / name
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            seen.append(f"{name} is unreadable ({exc})")
            continue
        if VERSION_RE.match(raw):
            return None
        seen.append(f"{name} is {raw[:40]!r}, not a dotted version")
    if not seen:
        return "neither VERSION nor skill-version.txt exists"
    return "; ".join(seen)


def identity_problems(target):
    """Everything that disqualifies target as a real install of this skill."""
    if target.is_symlink():
        return ["target is a symlink"]
    if not target.is_dir():
        return ["target is not a directory"]
    problems = []
    skill_md = target / "SKILL.md"
    if not skill_md.is_file():
        problems.append("SKILL.md is missing")
    else:
        name = frontmatter_name(skill_md)
        if name is None:
            problems.append("SKILL.md has no YAML frontmatter name")
        elif name != SKILL_NAME:
            problems.append(f"SKILL.md frontmatter name is {name!r}, not {SKILL_NAME!r}")
    for rel in REQUIRED_FILES:
        if not (target / rel).is_file():
            problems.append(f"{rel} is missing")
    version = version_problem(target)
    if version:
        problems.append(version)
    return problems


def registry_sources(source):
    src_dir = source.parent / REGISTRY_REL
    missing = [name for name in REGISTRY_FILES if not (src_dir / name).is_file()]
    return src_dir, missing


def validate_registry(root, registry):
    """Plan every registry write without touching the filesystem.

    Returns (writes, failures); a non-empty failures list must abort before any
    mutation so a bad destination cannot leave a half-applied install.
    """
    src_dir, missing = registry
    if missing:
        return [], [f"canonical registry missing at {src_dir}: {', '.join(missing)}"]
    writes, failures = [], []
    for name in REGISTRY_FILES:
        src = src_dir / name
        dst = root / REGISTRY_REL / name
        if escapes_root(dst, root):
            failures.append(f"registry destination escapes the skills root or is a symlink: {dst}")
            continue
        writes.append((src, dst))
    return writes, failures


def copy_no_follow(src, dst):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dst, flags, 0o644)
    with open(src, "rb") as src_file, os.fdopen(fd, "wb") as dst_file:
        shutil.copyfileobj(src_file, dst_file)


def write_registry(writes):
    ok = True
    for src, dst in writes:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink():
                raise OSError("destination became a symlink; refusing to follow it")
            copy_no_follow(src, dst)
            print(f"PASS: registry written: {dst}")
        except OSError as exc:
            print(f"FAIL: could not write registry to {dst}: {exc}")
            ok = False
    return 0 if ok else 1


def install_registry(root, registry, dry_run):
    writes, failures = validate_registry(root, registry)
    for failure in failures:
        print(f"FAIL: {failure}")
    if dry_run:
        for src, dst in writes:
            print(f"PLAN registry write: {src} -> {dst}")
        return 1 if failures else 0
    if failures:
        return 1
    return write_registry(writes)


def replace_copy(root, target, source):
    token = uuid.uuid4().hex[:12]
    staged = root / f".{SKILL_NAME}.new-{token}"
    aside = root / f".{SKILL_NAME}.old-{token}"
    try:
        shutil.copytree(source, staged, ignore=COPY_IGNORE)
        os.replace(target, aside)
    except OSError as exc:
        shutil.rmtree(staged, ignore_errors=True)
        print(f"FAIL: could not stage the replacement: {exc}")
        return 1
    try:
        os.replace(staged, target)
    except OSError as exc:
        try:
            os.replace(aside, target)
            restored = "old copy restored"
        except OSError as restore_exc:
            restored = f"RESTORE FAILED, old copy is at {aside}: {restore_exc}"
        shutil.rmtree(staged, ignore_errors=True)
        print(f"FAIL: could not move the new copy into place: {exc}; {restored}")
        return 1
    shutil.rmtree(aside, ignore_errors=True)
    print(f"PASS: copy replaced from {source}.")
    return 0


def install_one(root, source, mode, dry_run, registry, update=False):
    target = root / SKILL_NAME
    print(f"Target: {target}")

    if update:
        if not within(target, root):
            print(f"FAIL: target escapes the requested skills root: {target}")
            return 1
        if target.is_symlink():
            print("FAIL: target is a symlink; --update replaces real copy directories only.")
            return 1
        if not target.exists():
            print("FAIL: --update needs an existing copy target; use --mode copy for a fresh install.")
            return 1
        problems = identity_problems(target)
        if problems:
            print(f"FAIL: {target} is not a {SKILL_NAME} installation; refusing to replace it "
                  f"(--update deletes and rewrites the whole tree):")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        # Validate every registry destination before the swap, so a destination
        # that cannot legally be written aborts with the tree untouched.
        writes, registry_failures = validate_registry(root, registry)
        for failure in registry_failures:
            print(f"FAIL: {failure}")
        if registry_failures:
            print("FAIL: --update refused before any change; the existing copy was not touched.")
            return 1
        if dry_run:
            print(f"PLAN: replace the copy at {target} from {source}")
            for src, dst in writes:
                print(f"PLAN registry write: {src} -> {dst}")
            print("PASS: dry run only; no filesystem change was made.")
            return 0
        rc = replace_copy(root, target, source)
        if rc != 0:
            return rc
        return write_registry(writes)

    if target.exists() or target.is_symlink():
        if target.is_symlink():
            try:
                existing = target.resolve()
            except Exception:
                existing = None
            if existing == source:
                print("PASS: target already links to the canonical skill folder.")
                return 0
        print("FAIL: target already exists and will not be overwritten.")
        return 1

    if dry_run:
        print("PASS: dry run only; target is free and no filesystem change was made.")
        if mode == "copy":
            install_registry(root, registry, dry_run=True)
        return 0

    root.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        target.symlink_to(source, target_is_directory=True)
        print("PASS: symlink created.")
        return 0
    writes, registry_failures = validate_registry(root, registry)
    for failure in registry_failures:
        print(f"FAIL: {failure}")
    if registry_failures:
        print("FAIL: refusing before any change; nothing was copied.")
        return 1
    shutil.copytree(source, target, ignore=COPY_IGNORE)
    print("PASS: copy created. This copy must be updated intentionally when the canonical skill changes.")
    return write_registry(writes)


def main():
    parser = argparse.ArgumentParser(description="Safely install/link the BlackCEO skill into local agent skills roots.")
    parser.add_argument("--runtime", required=True, choices=["claude-code", "codex", "claude-nine", "custom"])
    parser.add_argument("--target-root", type=Path, help="Verified runtime skills root. Required for claude-nine/custom.")
    parser.add_argument("--source", type=Path, help="Canonical skill folder. Defaults to the folder containing this script's parent.")
    parser.add_argument("--mode", choices=["symlink", "copy"], default=None)
    parser.add_argument("--update", action="store_true",
                        help="Replace an existing copy target of this skill, then refresh the shared registry.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mode = args.mode or ("copy" if args.update else "symlink")
    if args.update and mode != "copy":
        print("FAIL: --update replaces copy targets; do not combine it with --mode symlink.")
        return 1

    source = (args.source or Path(__file__).resolve().parents[1]).expanduser().resolve()
    if not (source / "SKILL.md").exists():
        print(f"FAIL: source is not a skill folder: {source}")
        return 1

    if args.target_root:
        roots = [args.target_root.expanduser().resolve()]
    else:
        roots = DEFAULT_ROOTS.get(args.runtime)
        if roots is None:
            print(f"FAIL: --target-root is required for runtime {args.runtime!r}.")
            return 1

    registry = registry_sources(source)
    if (args.update or mode == "copy") and registry[1]:
        # Refuse before any mutation: a skill installed without the registry
        # cannot verify a 1.1 prompt_policy_id citation.
        print(f"FAIL: canonical registry missing at {registry[0]}: {', '.join(registry[1])}; "
              f"searched only beside the skill folder.")
        return 1

    print(f"Source: {source}")
    print(f"Mode: {'update' if args.update else mode}")
    failures = 0
    attempted = 0
    for root in roots:
        # Order rule: Codex roots are linked only when the Codex runtime is present.
        # Never create an absent runtime root; report the skip instead of inventing it.
        if not args.target_root and args.runtime == "codex" and not (Path.home() / ".codex").exists():
            print(f"SKIP: {root} (Codex runtime not present at {Path.home() / '.codex'}).")
            continue
        attempted += 1
        try:
            rc = install_one(root, source, mode, args.dry_run, registry, update=args.update)
        except OSError as exc:
            # One unwritable root is a counted failure, not a traceback that
            # abandons every root after it.
            print(f"FAIL: {root}: {exc}")
            rc = 1
        if rc != 0:
            # Keep going: one conflicting root must not abandon the remaining roots.
            failures += 1
    if attempted == 0:
        print("FAIL: no applicable skills root for this runtime; nothing was linked.")
        return 1
    if failures:
        print(f"FAIL: {failures} of {attempted} skill roots were not linked.")
        return 1
    print(f"PASS: {attempted} skill root(s) handled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
