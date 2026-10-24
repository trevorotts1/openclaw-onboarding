#!/usr/bin/env python3
import argparse
import os
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
DEFAULT_ROOTS = {
    "claude-code": [Path.home() / ".claude" / "skills"],
    "codex": [Path.home() / ".agents" / "skills", Path.home() / ".codex" / "skills"],
}


def within(path, root):
    try:
        return os.path.commonpath([str(path), str(root)]) == str(root)
    except ValueError:
        return False


def is_this_skill(target):
    if target.is_symlink() or not target.is_dir():
        return False
    skill_md = target / "SKILL.md"
    if not skill_md.is_file():
        return False
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if SKILL_NAME not in text:
        return False
    return (target / "VERSION").is_file() or (target / "skill-version.txt").is_file()


def registry_sources(source):
    src_dir = source.parent / REGISTRY_REL
    missing = [name for name in REGISTRY_FILES if not (src_dir / name).is_file()]
    return src_dir, missing


def install_registry(root, registry, dry_run):
    src_dir, missing = registry
    if missing:
        print(f"FAIL: canonical registry missing at {src_dir}: {', '.join(missing)}")
        return 1
    ok = True
    for name in REGISTRY_FILES:
        src = src_dir / name
        dst = root / REGISTRY_REL / name
        parent = dst.parent
        escapes = (not within(dst, root)
                   or (parent.exists() and not within(parent.resolve() / dst.name,
                                                      root.resolve())))
        if escapes:
            print(f"FAIL: registry destination escapes the skills root: {dst}")
            ok = False
            continue
        if dry_run:
            print(f"PLAN registry write: {src} -> {dst}")
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            print(f"PASS: registry written: {dst}")
        except OSError as exc:
            print(f"FAIL: could not write registry to {dst}: {exc}")
            ok = False
    return 0 if ok else 1


def replace_copy(root, target, source):
    token = uuid.uuid4().hex[:12]
    staged = root / f".{SKILL_NAME}.new-{token}"
    aside = root / f".{SKILL_NAME}.old-{token}"
    try:
        shutil.copytree(source, staged)
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
        if target.is_symlink():
            print("FAIL: target is a symlink; --update replaces real copy directories only.")
            return 1
        if not target.exists():
            print("FAIL: --update needs an existing copy target; use --mode copy for a fresh install.")
            return 1
        if not is_this_skill(target):
            print(f"FAIL: {target} is not a {SKILL_NAME} installation "
                  f"(SKILL.md naming the skill plus VERSION or skill-version.txt is required).")
            return 1
        if not within(target, root):
            print(f"FAIL: target escapes the requested skills root: {target}")
            return 1
        if dry_run:
            print(f"PLAN: replace the copy at {target} from {source}")
            install_registry(root, registry, dry_run=True)
            print("PASS: dry run only; no filesystem change was made.")
            return 0
        rc = replace_copy(root, target, source)
        if rc != 0:
            return rc
        return install_registry(root, registry, dry_run=False)

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
    shutil.copytree(source, target)
    print("PASS: copy created. This copy must be updated intentionally when the canonical skill changes.")
    return install_registry(root, registry, dry_run=False)


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
        rc = install_one(root, source, mode, args.dry_run, registry, update=args.update)
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
