#!/usr/bin/env python3
"""U92 (X/U-X2) — Docs-language CI guard.

Guards the operator-banned coded term that U91 verified scrubbed out of
MASTER SPEC v2 (the term is defined once, in full, in that document's
LANGUAGE CONFORMANCE header — never spelled out here in prose; it lives
only in scripts/docs-language-allowlist.json's "term" key, where a denylist
scanner has no choice but to hold the literal string it matches).

SCOPE: only lines ADDED by the current diff, in documentation files
(*.md, *.mdx, *.rst, *.txt), are scanned. This is deliberate:

  * Pre-existing occurrences already living in the repo (CHANGELOG.md
    history, HEARTBEAT.md doctrine prose, the Skill 60/61 "law 8" wording,
    role-library templates, Skill 58 goldens — ~141 files at the pinned
    commit per MASTER SPEC v2 X.1.3) are NOT this guard's job. Git history
    and released CHANGELOG entries are never rewritten (standing doctrine).
    Renaming/rewording that existing footprint is U30 (four Skill-6 files)
    and U93 (the rest, plus live doctrine text) — separate units.
  * This guard's only job is to stop the word from growing anywhere else
    in docs, starting now: it fails the build the moment a NEW line in a
    changed doc file introduces a fresh, unexplained occurrence.

ALLOWLIST (scripts/docs-language-allowlist.json), three carve-outs:
  (a) history           — the exact added line (stripped) already existed
                           verbatim, pre-diff, somewhere in the doc-file
                           corpus at the merge-base commit. A line
                           resurfacing because a file was moved, split, or
                           a paragraph above it was reflowed is not NEW
                           writing, even though the diff algorithm marks it
                           as an added line.
  (b) vendor_literals    — literal, third-party-owned strings (e.g. an npm
                           pre-release distribution tag) that legitimately
                           contain the term. Subtracted from the line
                           before the remaining text is checked.
  (c) legacy_filenames   — the exact legacy filenames named in MASTER SPEC
                           v2 X.1.3 that still carry the term until U30/U93
                           land. Citing one by name in prose is allowed;
                           subtracted the same way as vendor literals.

Exit codes: 0 = clean (or nothing to check). 1 = one or more new banned-term
occurrences found (see stdout). 2 = usage/environment error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

DEFAULT_DOC_GLOBS = ("*.md", "*.mdx", "*.rst", "*.txt")
DEFAULT_ALLOWLIST = Path(__file__).resolve().parent / "docs-language-allowlist.json"

# Git's well-known empty-tree object id (same in every repo — it's the SHA-1
# of a tree with zero entries). Diffing a ref against this gives every file
# tracked at that ref as an "added" line, WITH glob pathspecs honored — used
# instead of `git ls-tree -- '*.md'`, which silently drops bare (non-rooted)
# glob pathspecs and returns zero matches even for files that exist (a real,
# reproduced quirk of `ls-tree`'s pathspec matcher; `git diff`/`git ls-files`
# both handle the same glob correctly).
_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


class Occurrence(NamedTuple):
    path: str
    line_no: int
    text: str


class Allowlist:
    def __init__(self, data: dict):
        self.term: str = data["term"]
        self.term_re = re.compile(re.escape(self.term), re.IGNORECASE)
        self.legacy_filenames = [
            e["path"] for e in data.get("legacy_filenames", {}).get("entries", [])
        ]
        self.vendor_literals = [
            e for e in data.get("vendor_literals", {}).get("entries", [])
        ]

    @classmethod
    def load(cls, path: Path) -> "Allowlist":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def _covered_spans(self, line: str) -> list[tuple[int, int]]:
        """Character spans on `line` explained by a legacy filename or
        vendor literal (case-insensitive substring match)."""
        spans: list[tuple[int, int]] = []
        for literal in (*self.legacy_filenames, *self.vendor_literals):
            if not literal:
                continue
            lit_lower = literal.lower()
            line_lower = line.lower()
            start = 0
            while True:
                idx = line_lower.find(lit_lower, start)
                if idx == -1:
                    break
                spans.append((idx, idx + len(literal)))
                start = idx + 1
        return spans

    def uncovered_matches(self, line: str) -> list[re.Match]:
        """Term occurrences on `line` NOT explained by (b) or (c)."""
        spans = self._covered_spans(line)
        out = []
        for m in self.term_re.finditer(line):
            if not any(s <= m.start() and m.end() <= e for s, e in spans):
                out.append(m)
        return out


def run_git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {res.returncode}): {res.stderr.strip()}"
        )
    return res.stdout


def ref_exists(ref: str, cwd: Path) -> bool:
    res = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode == 0


def resolve_base_ref(explicit: str | None, event_name: str | None,
                      base_branch_env: str | None, cwd: Path) -> str | None:
    """Mirrors this repo's existing skill-version-bump-guard convention
    (.github/workflows/version-consistency.yml G3): PR -> merge-base with
    the target branch; push -> the previous commit; nothing resolvable ->
    None (caller treats as "nothing to check")."""
    if explicit:
        if not ref_exists(explicit, cwd):
            raise RuntimeError(f"--base-ref {explicit!r} does not resolve in this repo")
        return explicit

    if event_name == "pull_request" and base_branch_env:
        candidate = f"origin/{base_branch_env}"
        if ref_exists(candidate, cwd):
            try:
                return run_git(["merge-base", "HEAD", candidate], cwd).strip()
            except RuntimeError:
                pass

    if ref_exists("HEAD^1", cwd):
        return "HEAD^1"

    for candidate in ("origin/main", "main"):
        if ref_exists(candidate, cwd):
            return candidate

    return None


def list_changed_doc_files(base_ref: str, cwd: Path, doc_globs: Iterable[str]) -> list[str]:
    out = run_git(
        ["diff", "--name-only", "--diff-filter=ACMR", base_ref, "HEAD", "--", *doc_globs],
        cwd,
    )
    return [line for line in out.splitlines() if line]


def iter_added_lines(base_ref: str, cwd: Path, files: list[str]):
    """Yield (path, line_no_in_new_file, content) for every '+' line in a
    zero-context unified diff of `files` between base_ref and HEAD."""
    if not files:
        return
    diff_text = run_git(
        ["diff", "--no-color", "-U0", base_ref, "HEAD", "--", *files], cwd
    )
    current_file: str | None = None
    line_no: int | None = None
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            current_file = None
            line_no = None
            continue
        if raw.startswith("+++ "):
            target = raw[4:]
            current_file = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            continue
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if m:
                line_no = int(m.group("start"))
            continue
        if current_file is None or line_no is None:
            continue
        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        if raw.startswith("+"):
            yield current_file, line_no, raw[1:]
            line_no += 1
        elif raw.startswith("-"):
            continue  # removed lines never advance the new-file counter
        else:
            line_no += 1  # context line (only possible if U>0 was used)


def build_historical_term_lines(base_ref: str, cwd: Path, doc_globs: Iterable[str],
                                 allowlist: Allowlist) -> set[str]:
    """Every stripped line, across every tracked doc file at base_ref, that
    already contains the term — the corpus checked for carve-out (a)."""
    try:
        tree_out = run_git(
            ["diff", "--name-only", _EMPTY_TREE_SHA, base_ref, "--", *doc_globs], cwd
        )
    except RuntimeError:
        return set()
    lines: set[str] = set()
    for path in tree_out.splitlines():
        if not path:
            continue
        show = subprocess.run(
            ["git", "show", f"{base_ref}:{path}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if show.returncode != 0:
            continue
        for ln in show.stdout.splitlines():
            if allowlist.term_re.search(ln):
                lines.add(ln.strip())
    return lines


def scan(cwd: Path, base_ref_arg: str | None, allowlist_path: Path,
          doc_globs: tuple[str, ...], event_name: str | None,
          base_branch_env: str | None) -> tuple[int, list[Occurrence]]:
    allowlist = Allowlist.load(allowlist_path)

    base_ref = resolve_base_ref(base_ref_arg, event_name, base_branch_env, cwd)
    if base_ref is None:
        print("check-docs-language: no base ref resolvable (first commit / shallow "
              "clone with no history) — nothing to check, PASS.")
        return 0, []

    changed = list_changed_doc_files(base_ref, cwd, doc_globs)
    if not changed:
        print(f"check-docs-language: 0 changed doc files vs {base_ref} — PASS.")
        return 0, []

    historical = build_historical_term_lines(base_ref, cwd, doc_globs, allowlist)

    findings: list[Occurrence] = []
    for path, line_no, text in iter_added_lines(base_ref, cwd, changed):
        if not allowlist.term_re.search(text):
            continue
        if text.strip() in historical:
            continue  # carve-out (a): not truly new, already in history
        if allowlist.uncovered_matches(text):
            findings.append(Occurrence(path, line_no, text))

    if findings:
        print(f"check-docs-language: {len(findings)} NEW unexplained occurrence(s) "
              f"of the retired term vs {base_ref}:\n")
        for f in findings:
            print(f"  {f.path}:{f.line_no}: {f.text.strip()}")
        print(
            "\nFix: reword using the standard replacement vocabulary "
            "(MASTER SPEC v2 LANGUAGE CONFORMANCE / X.1.2), or if this is a "
            "legitimate citation of one of the six legacy filenames or a "
            "third-party vendor literal, add it to "
            "scripts/docs-language-allowlist.json instead of inlining it."
        )
        return 1, findings

    print(f"check-docs-language: {len(changed)} changed doc file(s) vs {base_ref} — "
          f"0 new unexplained occurrences — PASS.")
    return 0, []


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default=None,
                         help="Explicit ref/sha to diff against (overrides auto-detection).")
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST),
                         help="Path to the allowlist JSON file.")
    parser.add_argument("--doc-glob", action="append", default=None,
                         help="Doc pathspec glob (repeatable). Default: *.md *.mdx *.rst *.txt")
    parser.add_argument("--repo-root", default=".", help="Repo working directory.")
    args = parser.parse_args(argv)

    cwd = Path(args.repo_root).resolve()
    doc_globs = tuple(args.doc_glob) if args.doc_glob else DEFAULT_DOC_GLOBS

    try:
        code, _ = scan(
            cwd=cwd,
            base_ref_arg=args.base_ref,
            allowlist_path=Path(args.allowlist),
            doc_globs=doc_globs,
            event_name=os.environ.get("GITHUB_EVENT_NAME"),
            base_branch_env=os.environ.get("GITHUB_BASE_REF"),
        )
    except RuntimeError as exc:
        print(f"check-docs-language: ERROR: {exc}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
