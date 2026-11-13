#!/usr/bin/env python3
"""Sync engine for the Presentations department, onboarding to 999 (PD-035).

Direction is onboarding to 999, always. The sync vendors the department into
one 999 skill tree (`.claude/skills/signature-presentation/`) from six
onboarding sources, all byte copies:

  - S51 whole tree (`51-signature-presentation/`) at the destination root;
  - the department's `scripts/` (minus `tests/`), `intake/` (minus
    `interview-app/`) and `sops/`, over the same root;
  - the roster role files, `BUILDER-PROMPT.md`, `TOOLS.md`, `00-START-HERE.md`
    and `connection-manifest.json` from the department root;
  - the three presentation clusters under `universal-sops/`;
  - `shared-utils/kie_prompt_enforcer.py`, `prompt_policy.py` and
    `kie_prompt_gates.json`.

It writes `VENDORED.md` at the destination root with the source commit, the
file count and the tree digest, in the shape 999 `23-ai-workforce-blueprint/
VENDORED.md` uses: SHA-256 over the newline-terminated, path-sorted lines
`<file sha256>  <relative path>`.

`--check` re-derives the plan from the onboarding sources and proves the
vendored bytes still match the digest recorded in `VENDORED.md`: 0 when they
do, 1 when one byte of a copied file changed, one is missing, or a source tree
moved after the sync. Files in the 999 tree that the plan does not name (the
999-only front door and wrapper, later units) are not part of the vendor set
and do not affect the digest.

The roster is not restated here: it is parsed out of the department's own
`00-START-HERE.md` role table, the page `scripts/tests/
test_fix77_roster_uniqueness.py` already holds unique, so the sync and the
roster cannot disagree.

One source path collides across two sources: `scripts/blend_voice_governance.py`
exists in S51 and in the department with different bytes. The department's copy
is kept, because `scripts/presentation_job/persona.py` resolves that file
department-first (`<dept>/scripts/` is candidate one, the S51 tree is the
fallback for a standalone skill install); the S51 variant is not copied and is
named in `VENDORED.md`. The sync refuses any other collision rather than
picking a winner.

Exit codes: 0 synced and the digest is recorded (dry run: 0; check: in sync),
1 refused or check failed, 2 usage or config error.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEST_REL = Path(".claude/skills/signature-presentation")
S51_REL = Path("51-signature-presentation")
DEPT_REL = Path("23-ai-workforce-blueprint/templates/role-library/presentations")
CLUSTERS = ("presentation-design-system", "presentation-image-library",
            "presentation-slide-craft")
SHARED = ("kie_prompt_enforcer.py", "prompt_policy.py", "kie_prompt_gates.json")
DEPT_ROOT_DOCS = ("BUILDER-PROMPT.md", "TOOLS.md", "00-START-HERE.md",
                  "connection-manifest.json")
ROSTER_SOURCE = "00-START-HERE.md"
ROSTER_COUNT = 34
# dest relative path -> the source whose bytes win. See the module docstring.
SUPERSEDED = {"scripts/blend_voice_governance.py": "department"}
VENDORED = "VENDORED.md"
# dest relative paths named by the unit text in their own right; the cluster copy
# already carries the ruleset, so this is an assertion, not a second copy.
REQUIRED = ("scripts/build_deck.py", "scripts/run_signature_deck.py",
            "scripts/blend_voice_governance.py", "00-START-HERE.md",
            "TOOLS.md", "BUILDER-PROMPT.md", "connection-manifest.json",
            "universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md")
ROSTER_ROW_RE = re.compile(r"^\|\s*ROLE-[0-9]+[A-Z]?\s*\|[^|]*\|[^|]*\|\s*([^|\s]+\.md)\s*\|")


class Refused(Exception):
    pass


def roster(dept: Path) -> list:
    """The 34 role files, read from the department's own roster table."""
    page = dept / ROSTER_SOURCE
    if not page.is_file():
        raise Refused(f"roster source missing: {page}")
    names = [m.group(1) for m in map(ROSTER_ROW_RE.match, page.read_text(encoding="utf-8").splitlines()) if m]
    if len(names) != ROSTER_COUNT or len(set(names)) != ROSTER_COUNT:
        raise Refused(f"roster in {page} lists {len(names)} file(s) "
                      f"({len(set(names))} unique), expected {ROSTER_COUNT} unique")
    for n in names:
        if not (dept / n).is_file():
            raise Refused(f"roster names a role file that does not exist: {dept / n}")
    return names


def walk(root: Path, skip=()):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(str(rel) == str(s) or str(rel).startswith(str(s) + "/") for s in skip):
            continue
        if "__pycache__" in rel.parts:
            continue
        yield rel


def plan(onb: Path):
    """{dest relative posix path: source Path}, every source proven to exist."""
    s51 = onb / S51_REL
    dept = onb / DEPT_REL
    for d in (s51, dept):
        if not d.is_dir():
            raise Refused(f"source tree missing: {d}")
    rows = {}       # dest rel -> source Path
    origin = {}     # dest rel -> source label

    def add(src_root: Path, label: str, rels, dest_prefix=""):
        for rel in rels:
            src = src_root / rel
            if not src.is_file():
                raise Refused(f"declared source missing: {src}")
            dest = (Path(dest_prefix) / rel).as_posix() if dest_prefix else rel.as_posix()
            if dest in rows:
                winner = SUPERSEDED.get(dest)
                if winner is None or winner != label:
                    raise Refused(f"two sources claim {dest} with different bytes "
                                  f"({origin[dest]} and {label}); refusing to pick a winner")
            rows[dest] = src
            origin[dest] = label

    add(s51, "S51", walk(s51))
    add(dept / "scripts", "department",
        walk(dept / "scripts", skip=(Path("tests"),)), dest_prefix="scripts")
    add(dept / "intake", "department",
        walk(dept / "intake", skip=(Path("interview-app"),)), dest_prefix="intake")
    add(dept / "sops", "department", walk(dept / "sops"), dest_prefix="sops")
    add(dept, "department", [Path(n) for n in roster(dept)])
    add(dept, "department", [Path(n) for n in DEPT_ROOT_DOCS])
    for c in CLUSTERS:
        add(onb / "universal-sops" / c, f"universal-sops/{c}",
            walk(onb / "universal-sops" / c), dest_prefix=f"universal-sops/{c}")
    add(onb / "shared-utils", "shared-utils", [Path(f) for f in SHARED],
        dest_prefix="shared-utils")
    for r in REQUIRED:
        if r not in rows:
            raise Refused(f"required file not in the plan: {r}")
    return rows


def digest(items) -> str:
    """SHA-256 over newline-terminated, path-sorted '<sha>  <path>' lines."""
    return hashlib.sha256("".join(f"{h}  {p}\n" for p, h in items).encode()).hexdigest()


def file_rows(rows, root: Path):
    return [(dest, hashlib.sha256((root / dest).read_bytes()).hexdigest())
            for dest in sorted(rows)]


def plan_rows(rows):
    """The bytes the sync intends, keyed by destination path."""
    return [(dest, hashlib.sha256(rows[dest].read_bytes()).hexdigest())
            for dest in sorted(rows)]


def source_commit(onb: Path, override=None):
    if override:
        return override, "given on the command line"
    try:
        proc = subprocess.run(["git", "-C", str(onb), "rev-parse", "HEAD"],
                              text=True, capture_output=True)
        ref = subprocess.run(["git", "-C", str(onb), "rev-parse", "--abbrev-ref", "HEAD"],
                             text=True, capture_output=True)
    except OSError as exc:
        raise Refused(f"cannot read the source commit ({exc}); pass --source-commit") from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise Refused("cannot read the source commit; pass --source-commit")
    return proc.stdout.strip(), (ref.stdout.strip() if ref.returncode == 0 else "unknown")


def vendored_text(onb: Path, rows, sha: str, ref: str) -> str:
    rel = plan_rows(rows)
    return "\n".join([
        "# Vendored: Presentations department (signature-presentation)",
        "",
        "`" + DEST_REL.as_posix() + "/` is a copy of the onboarding Presentations",
        "department, made by `scripts/sync_presentations_to_999.py`. Every file is a",
        "byte copy. Do not edit it here: a local edit is drift, and `--check` fails",
        "on it. Refresh by re-running the sync from the source commit below.",
        "",
        "- Source repo: `trevorotts1/openclaw-onboarding`",
        f"- Source ref: `{ref}`",
        f"- Source commit: `{sha}`",
        f"- Source version (S51 `skill-version.txt`): `{(onb / S51_REL / 'skill-version.txt').read_text(encoding='utf-8').strip()}`",
        "- Sources copied (byte for byte):",
        f"  - `{S51_REL.as_posix()}/` — the whole S51 tree, at this root",
        f"  - `{DEPT_REL.as_posix()}/scripts/` (excluding `tests/`)",
        f"  - `{DEPT_REL.as_posix()}/intake/` (excluding `interview-app/`)",
        f"  - `{DEPT_REL.as_posix()}/sops/`",
        f"  - `{DEPT_REL.as_posix()}/` — the {ROSTER_COUNT} roster role files (read from its own",
        f"    `{ROSTER_SOURCE}` roster table), `BUILDER-PROMPT.md`, `TOOLS.md`,",
        "    `00-START-HERE.md`, `connection-manifest.json`",
        "  - `universal-sops/presentation-design-system/`, `presentation-image-library/`,",
        "    `presentation-slide-craft/` (the master QC ruleset included)",
        "  - `shared-utils/kie_prompt_enforcer.py`, `prompt_policy.py`, `kie_prompt_gates.json`",
        f"- Files vendored: {len(rows)}",
        f"- Tree digest: `sha256:{digest([(p, h) for p, h in rel])}`",
        "",
        "The digest is the generator's: SHA-256 over the newline-terminated,",
        "path-sorted lines `<file sha256>  <relative path>`, relative to this root.",
        f"`{VENDORED}` itself is not part of it. `--check` re-derives the plan from the",
        "onboarding sources and fails on one changed byte, a missing file, or a source",
        "tree that moved after this snapshot.",
        "",
        f"One source file is superseded, not copied: `{S51_REL.as_posix()}/scripts/"
        "blend_voice_governance.py`. Its bytes differ from the department's copy of the",
        "same path, which is kept because `scripts/presentation_job/persona.py` resolves",
        "`<dept>/scripts/blend_voice_governance.py` first and the S51 tree only as the",
        "fallback for a standalone skill install. Any other path collision refuses the",
        "sync instead of picking a winner.",
        "",
        "Not vendored, because the unit text names neither: the department's",
        "`IDENTITY.md`, `SOUL.md`, `how-to-use-this-department.md`,",
        "`DEPARTMENT-COUNTS-CANONICAL.md`, `DECISION-2026-10-14-KIE-COMPLETION-POLLING.md`,",
        "`retired-doctrine-patterns.json`, `test_retired_roles.py` and the rest of its",
        "root, plus `scripts/tests/` and `intake/interview-app/`.",
        "",
    ]).replace("- Per-source counts: \n", "")


def recorded(dest: Path):
    path = dest / VENDORED
    if not path.is_file():
        raise Refused(f"{path} is missing; run the sync first")
    text = path.read_text(encoding="utf-8")
    count = re.search(r"^- Files vendored: (\d+)$", text, re.M)
    tree = re.search(r"^- Tree digest: `sha256:([0-9a-f]{64})`$", text, re.M)
    sha = re.search(r"^- Source commit: `([0-9a-f]{40})`$", text, re.M)
    if not (count and tree and sha):
        raise Refused(f"{path} does not carry the expected count/digest/commit lines")
    return int(count.group(1)), tree.group(1), sha.group(1)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Vendor the Presentations department from onboarding into 999 (PD-035).")
    ap.add_argument("--onb-root", "--onboarding", dest="onb", type=Path, required=True)
    ap.add_argument("--nine-root", "--nine", dest="nine", type=Path, required=True)
    ap.add_argument("--check", action="store_true",
                    help="verify the vendored tree against VENDORED.md; write nothing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--source-commit", help="override the recorded source commit")
    args = ap.parse_args(argv)
    onb, nine, dest = args.onb, args.nine, args.nine / DEST_REL
    if not onb.is_dir() or not nine.is_dir():
        print(f"REFUSED: root missing (onboarding: {onb}, 999: {nine})")
        return 2

    try:
        rows = plan(onb)
        if args.check:
            count, tree, sha = recorded(dest)
            missing = [p for p in sorted(rows) if not (dest / p).is_file()]
            for p in missing:
                print(f"MISSING {p}")
            expected = dict(plan_rows(rows))
            actual = file_rows(rows, dest) if not missing else []
            bad = len(missing)
            for p, h in actual:
                if expected[p] != h:
                    print(f"CHANGED {p}")
                    bad += 1
            if len(rows) != count:
                print(f"CHECK FAILED: the plan has {len(rows)} file(s), VENDORED.md records {count}")
                bad += 1
            got = digest(actual) if actual else None
            if got != tree:
                print(f"CHECK FAILED: tree digest {f'sha256:{got}' if got else 'not computed (files missing)'}"
                      f" != recorded sha256:{tree}")
                bad += 1
            source_now, _ = source_commit(onb)
            if source_now != sha:
                print(f"SOURCE MOVED: onboarding is at {source_now}, VENDORED.md records {sha}; re-run the sync")
                bad += 1
            if bad:
                print(f"CHECK FAILED: {bad} divergence(s) from {dest / VENDORED}")
                return 1
            print(f"CHECK OK: {len(actual)} file(s), tree digest sha256:{tree}")
            return 0

        log = []
        for p, src in sorted(rows.items()):
            dst = dest / p
            data = src.read_bytes()
            if dst.is_file() and dst.read_bytes() == data:
                continue
            log.append(f"copy {src} -> {dst}")
            if not args.dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                shutil.copymode(src, dst)
        for line in log:
            print(("DRY " if args.dry_run else "") + line)
        print(f"{'would copy' if args.dry_run else 'copied'}: {len(log)} file(s), "
              f"{len(rows)} in the vendor set")
        if args.dry_run:
            return 0
        sha, ref = source_commit(onb, args.source_commit)
        (dest / VENDORED).write_text(vendored_text(onb, rows, sha, ref), encoding="utf-8")
        print(f"wrote {dest / VENDORED}")
        print("SYNC DONE, DIGEST RECORDED")
        return 0
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
