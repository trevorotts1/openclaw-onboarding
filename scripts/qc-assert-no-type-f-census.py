#!/usr/bin/env python3
"""
qc-assert-no-type-f-census.py — detect `-type f` census invocations missing `-type l`.

Rule 3.1: a census that asks only `-type f` silently skips symlinks. A symlink to a
file IS a file for counting purposes. Use `( -type f -o -type l )` instead.

This guard ships in WARN-MODE: it reports every violation and exits 0.
Use `--enforce` to exit 1 when violations exist (wired to nothing yet — Rule 3.5
stage 1).

Depth caps are a SEPARATE blind spot that this guard does NOT check. The worked
example is qc-system-integrity.sh:153-154 — those two lines are correct on the type
flag (paired f + l census) and wrong on the depth cap (-maxdepth 2). This guard
exempts them via the adjacent-pair rule, not via the allowlist.

Enumerates with `git ls-files -z` (tracked files only), NEVER `find -type f` — using
the flag this guard exists to ban would make the guard commit its own violation.

Usage: python3 scripts/qc-assert-no-type-f-census.py [--enforce] [--report-json]
"""

import argparse
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWLIST_PATH = os.path.join(REPO_ROOT, "scripts",
                              "qc-assert-no-type-f-census.allowlist")

# ── regexes ────────────────────────────────────────────────────────────────────
# -type<ws>f where f is NOT followed by [A-Za-z]
F_RE = re.compile(rb"-type[\s]+f(?![A-Za-z])")
# Companion -type l on the same line
L_RE = re.compile(rb"-type[\s]+l(?![A-Za-z])")
# Safe terminal actions: -delete, -print -quit, -quit, head -1 | grep -q .
SAFE_RE = re.compile(
    rb"(?:-delete|(?:-print[ \t]+)?-quit|head[ \t]+-1[ \t]*\|[ \t]*grep[ \t]+-q[ \t]+\.)"
)
BINARY_SIG = b"\x50\x4b\x03\x04"


# ── helpers ────────────────────────────────────────────────────────────────────

def is_binary(filepath: str) -> bool:
    try:
        with open(filepath, "rb") as fh:
            return fh.read(4)[:4] == BINARY_SIG[:4]
    except OSError:
        return False


def tracked_files() -> list[str]:
    """git ls-files -z; falls back to os.walk (excluding .git)."""
    try:
        r = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT,
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            files = [f for f in r.stdout.split("\0") if f]
            files.sort()
            return files
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    # Fallback — never `find -type f`
    files = []
    for dp, dns, fns in os.walk(REPO_ROOT):
        dns[:] = [d for d in dns if d != ".git"]
        for fn in fns:
            files.append(os.path.relpath(os.path.join(dp, fn), REPO_ROOT))
    files.sort()
    return files


def load_allowlist() -> dict[tuple[str, int], tuple[str, str]]:
    """{(relpath, lineno): (classification, reason)}.
    File format: path:line | classification | YYYY-MM-DD reason
    Lines starting with # are comments."""
    entries: dict[tuple[str, int], tuple[str, str]] = {}
    if not os.path.isfile(ALLOWLIST_PATH):
        return entries
    with open(ALLOWLIST_PATH, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) < 3:
                continue
            coord, cls, reason = parts
            if ":" in coord:
                pp, lp = coord.rsplit(":", 1)
                try:
                    entries[(pp, int(lp))] = (cls, reason)
                except ValueError:
                    continue
    return entries


def heredoc_ranges(lines: list[str]) -> set[int]:
    """0-based indices of lines inside heredocs (<<'M' ... M or <<M ... M).

    Uses negative lookbehind (Python requires fixed-width) — we use '(?<!<)'
    to avoid matching bash here-strings (<<<)."""
    out: set[int] = set()
    hd_re = re.compile(r"(?<![<])<<[ \t]*'?(\w+)'?")
    i = 0
    while i < len(lines):
        m = hd_re.search(lines[i])
        if m:
            marker = m.group(1)
            end_re = re.compile(r"^\s*" + re.escape(marker) + r"\s*$")
            for j in range(i + 1, len(lines)):
                if end_re.match(lines[j]):
                    for k in range(i + 1, j):
                        out.add(k)
                    i = j
                    break
            else:
                for k in range(i + 1, len(lines)):
                    out.add(k)
                break
        i += 1
    return out


def is_comment(line: str) -> bool:
    return line.strip().startswith("#")


def has_safe_action(line: str) -> bool:
    return bool(SAFE_RE.search(line.encode("utf-8", errors="replace")))


def has_type_l(line: str) -> bool:
    return bool(L_RE.search(line.encode("utf-8", errors="replace")))


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Detect -type f without companion -type l")
    ap.add_argument("--enforce", action="store_true",
                    help="Exit 1 when violations exist")
    ap.add_argument("--report-json", action="store_true",
                    help="Emit machine-readable JSON report")
    args = ap.parse_args()

    files = tracked_files()
    allowlist = load_allowlist()

    # Per-scan state
    raw: list[tuple[str, int, str, bool]] = []  # (relpath, lineno, text, binary)
    fh_heredoc: dict[str, set[int]] = {}        # {relpath: {0-based heredoc indices}}
    fh_typel: dict[str, set[int]] = {}          # {relpath: {1-based line nums with -type l}}

    for relpath in files:
        full = os.path.join(REPO_ROOT, relpath)
        if not os.path.isfile(full):
            continue

        binflag = is_binary(full)

        try:
            if binflag:
                with open(full, "rb") as fh:
                    raw_b = fh.read()
                lb = raw_b.split(b"\n")
                ls = [bl.decode("utf-8", errors="replace") for bl in lb]
            else:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    rs = fh.read()
                ls = rs.split("\n")
                lb = [l.encode("utf-8", errors="replace") for l in ls]
        except OSError:
            continue

        if not binflag:
            fh_heredoc[relpath] = heredoc_ranges(ls)

        # Record lines with -type l (for adjacent-pair matching)
        tl_set: set[int] = set()
        for i, b in enumerate(lb):
            if L_RE.search(b):
                tl_set.add(i + 1)  # 1-based
        fh_typel[relpath] = tl_set

        # Find -type f matches
        for i, (s, b) in enumerate(zip(ls, lb)):
            if F_RE.search(b):
                raw.append((relpath, i + 1, s.rstrip(), binflag))

    M = len(raw)
    N = len(files)

    # Build adjacent-pair exemption set
    adj: set[tuple[str, int]] = set()
    for rp, ln, _txt, _bin in raw:
        tl = fh_typel.get(rp, set())
        if (ln - 1) in tl or (ln + 1) in tl:
            adj.add((rp, ln))

    # Classify every match
    cats: dict[str, list[tuple[str, int, str]]] = {
        "C": [], "B": [], "S": [], "P": [], "A": [], "V": [],
    }

    for rp, ln, txt, binflag in raw:
        # B: binary — count FIRST before any other exemption
        if binflag:
            cats["B"].append((rp, ln, txt))
            continue

        # C: comment or heredoc
        if is_comment(txt):
            cats["C"].append((rp, ln, txt))
            continue
        if rp in fh_heredoc and (ln - 1) in fh_heredoc[rp]:
            cats["C"].append((rp, ln, txt))
            continue

        # S: safe-action
        if has_safe_action(txt):
            cats["S"].append((rp, ln, txt))
            continue

        # P: paired with -type l (same-line, or adjacent-pair)
        if has_type_l(txt):
            cats["P"].append((rp, ln, txt))
            continue
        if (rp, ln) in adj:
            cats["P"].append((rp, ln, txt))
            continue

        # A: allowlisted
        if (rp, ln) in allowlist:
            cats["A"].append((rp, ln, txt))
            continue

        # V: violation
        cats["V"].append((rp, ln, txt))

    C = len(cats["C"]); B = len(cats["B"]); S = len(cats["S"])
    P = len(cats["P"]); A = len(cats["A"]); V = len(cats["V"])

    chk = (M - C - B - S - P - A == V)
    chk_str = (
        f"M - C - B - S - P - A = V  "
        f"({M} - {C} - {B} - {S} - {P} - {A} = {V})"
    )

    # ── JSON report ─────────────────────────────────────────────────────────
    if args.report_json:
        report = {
            "scanned": N,
            "matching": M,
            "comment_heredoc": C,
            "binary": B,
            "safe_action": S,
            "paired_type_l": P,
            "allowlisted": A,
            "violations": V,
            "checksum": chk_str,
            "checksum_ok": chk,
            "violations": [f"{rp}:{ln}" for rp, ln, _ in cats["V"]],
            "line_lists": {
                k: [f"{rp}:{ln}" for rp, ln, _ in v]
                for k, v in cats.items()
            },
        }
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if (args.enforce and V > 0) else 0

    # ── Human-readable output ───────────────────────────────────────────────
    print(f"scanned {N}; matching {M}; comment/heredoc {C}; binary {B}; "
          f"safe-action {S}; paired-with-`-type l` {P}; allowlisted {A}; "
          f"violations {V}")
    print(f"  {chk_str}", end="")
    if not chk:
        print("  <- CHECKSUM FAILURE - an exemption is missing or miscounted")
    else:
        print("")

    if V > 0:
        print(f"\n{V} violation(s) - a census must enumerate symlinks too: "
              f"use \\( -type f -o -type l \\)\n"
              f"  (a symlink to a file IS a file for counting purposes)\n"
              f"  Depth caps are a separate blind spot this guard does NOT check. "
              f"qc-system-integrity.sh:153-154 is correct on the type flag "
              f"(paired f+l census) and wrong on depth - removing -maxdepth 2 "
              f"is that card's work.")
        for rp, ln, txt in cats["V"]:
            print(f"  ! {rp}:{ln}")
            print(f"      {txt}")
    elif M > 0:
        print(f"\nOK All {M} matching lines are exempt (comment/heredoc, "
              f"binary, safe-action, paired, or allowlisted) - no violations")
    else:
        print(f"\nOK No -type f census invocations found "
              f"(scanned {N} tracked files)")

    return 1 if (args.enforce and V > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
