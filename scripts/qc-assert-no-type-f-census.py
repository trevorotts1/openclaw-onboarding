#!/usr/bin/env python3
"""
qc-assert-no-type-f-census.py  (U056)

Detects bare -type f in find invocations without a companion -type l.
A symlink to a file is a file for counting purposes — a bare -type f
census silently skips symlinks (spec-common Rule 3.1).

Enumerates via git ls-files -z (tracked files only), NEVER via find -type f
— the guard must not itself commit the violation it detects.

Warn-mode by default: prints every violation with a decomposable denominator
and exits 0.  Use --enforce to exit 1 when violations exist.
Use --report-json to emit a machine-readable decomposition.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# regexes
# ---------------------------------------------------------------------------

# Bare -type f — rejects -type framework / -type file (107->98 delta).
TYPE_F_RE = re.compile(rb'-type\s+f(?![a-zA-Z])')

# Companion -type l on the same line makes -type f safe.
COMPANION_TYPE_L_RE = re.compile(rb'-type\s+l(?![a-zA-Z])')

# Safe actions: -delete, -print -quit, -quit
SAFE_ACTION_RE = re.compile(rb'-(?:delete|print\b.*-quit\b|quit)\b')

# Heredoc start
HEREDOC_START_RE = re.compile(rb'<<\s*["\'](\w+)["\']')

# Triple-quoted docstrings
TRIPLE_QUOTE_START_RE = re.compile(rb'^\s*([\'"])\1\1\s*$')


def load_allowlist(path):
    entries = set()
    if not os.path.isfile(path):
        return entries
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            s = raw.strip()
            if not s or s.startswith('#'):
                continue
            parts = s.split('|', 1)
            coord = parts[0].strip()
            if ':' not in coord:
                continue
            fpath, ln_str = coord.rsplit(':', 1)
            try:
                entries.add((fpath.strip(), int(ln_str)))
            except ValueError:
                pass
    return entries


def _in_comment_or_heredoc(all_lines, idx):
    """State machine: heredocs, triple-quoted docstrings, #-comments."""
    in_block = False
    marker = None
    block_type = None

    for i, raw in enumerate(all_lines):
        stripped = raw.rstrip(b'\r\n')
        if i > idx:
            break
        if in_block:
            if block_type == 'heredoc' and stripped == marker:
                in_block = False
                marker = None
                block_type = None
            elif block_type == 'triple' and TRIPLE_QUOTE_START_RE.match(stripped):
                qc = marker[0:1]
                if stripped.startswith(qc + qc + qc):
                    in_block = False
                    marker = None
                    block_type = None
            if i == idx:
                return True
            continue
        tqm = TRIPLE_QUOTE_START_RE.match(stripped)
        if tqm:
            marker = stripped[:3]
            block_type = 'triple'
            in_block = True
            continue
        hm = HEREDOC_START_RE.search(stripped)
        if hm:
            marker = hm.group(1)
            block_type = 'heredoc'
            in_block = True
            continue
        if i == idx:
            return stripped.lstrip().startswith(b'#')
    return False


def _has_adjacent_type_l(lines, idx):
    """True if idx-1 or idx+1 carries -type l with matching -name predicates."""
    def _names(ln):
        return set(re.findall(rb'-name\s+("[^"]*"|\'[^\']*\'|\S+)', ln))
    names_this = _names(lines[idx])
    for off in (-1, 1):
        ni = idx + off
        if 0 <= ni < len(lines) and COMPANION_TYPE_L_RE.search(lines[ni]):
            if _names(lines[ni]) == names_this:
                return True
    return False


def classify_line(raw_lines, idx, is_binary):
    raw = raw_lines[idx]
    if is_binary:
        return 'binary'
    if _in_comment_or_heredoc(raw_lines, idx):
        return 'comment_heredoc'
    if COMPANION_TYPE_L_RE.search(raw):
        return 'paired'
    if _has_adjacent_type_l(raw_lines, idx):
        return 'paired'
    if SAFE_ACTION_RE.search(raw):
        return 'safe_action'
    return 'violation'


def main():
    ap = argparse.ArgumentParser(description='Ban type-f flag in find invocations without companion type-l')
    ap.add_argument('--enforce', action='store_true',
                    help='Exit 1 when violations exist (default: warn-mode, exit 0)')
    ap.add_argument('--report-json', action='store_true',
                    help='Emit machine-readable decomposition')
    args = ap.parse_args()

    repo_root = os.environ.get('QC_REPO_ROOT', '')
    if not repo_root:
        try:
            repo_root = subprocess.check_output(
                ['git', 'rev-parse', '--show-toplevel'],
                stderr=subprocess.DEVNULL, text=True).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            repo_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..'))

    allowlist = load_allowlist(
        os.path.join(repo_root, 'scripts',
                     'qc-assert-no-type-f-census.allowlist'))

    # Enumerate — NEVER find -type f.
    file_list = []
    try:
        out = subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=repo_root,
            stderr=subprocess.DEVNULL)
        file_list = out.decode('utf-8', errors='replace').split('\0')
    except (subprocess.CalledProcessError, FileNotFoundError):
        for d, _, fs in os.walk(repo_root):
            for fn in fs:
                file_list.append(os.path.relpath(os.path.join(d, fn), repo_root))
    file_list = [f for f in file_list if f]

    scanned = 0
    matching = 0
    comment_heredoc = []
    binary_entries = []
    safe_action = []
    paired = []
    allowlisted_entries = []
    violations = []

    for relpath in file_list:
        full = os.path.join(repo_root, relpath)
        if not os.path.isfile(full):
            continue
        scanned += 1

        is_bin = False
        try:
            with open(full, 'rb') as probe:
                h = probe.read(4)
            is_bin = (len(h) >= 2 and h[:2] == b'PK')
        except OSError:
            continue

        try:
            with open(full, 'rb') as fh:
                raw_lines = fh.readlines()
        except OSError:
            continue

        for i, raw in enumerate(raw_lines):
            if not TYPE_F_RE.search(raw):
                continue
            matching += 1
            line_no = i + 1
            text = raw.decode('utf-8', errors='replace').rstrip('\r\n')
            cls = classify_line(raw_lines, i, is_bin)
            entry = (relpath, line_no, text)

            if cls == 'binary':
                binary_entries.append(entry)
            elif cls == 'comment_heredoc':
                comment_heredoc.append(entry)
            elif cls == 'safe_action':
                safe_action.append(entry)
            elif cls == 'paired':
                paired.append(entry)
            elif (relpath, line_no) in allowlist:
                allowlisted_entries.append(entry)
            else:
                violations.append(entry)

    Cc = len(comment_heredoc)
    Bb = len(binary_entries)
    Ss = len(safe_action)
    Pp = len(paired)
    Aa = len(allowlisted_entries)
    Vv = len(violations)
    ok = (matching - Cc - Bb - Ss - Pp - Aa == Vv)

    print(
        f"scanned {scanned}; "
        f"matching {matching}; "
        f"comment/heredoc {Cc}; "
        f"binary {Bb}; "
        f"safe-action {Ss}; "
        f"paired-with-`-type l` {Pp}; "
        f"allowlisted {Aa}; "
        f"violations {Vv}"
    )
    print(
        f"M - C - B - S - P - A = V  ->  "
        f"{matching} - {Cc} - {Bb} - {Ss} - {Pp} - {Aa} = {Vv}"
        f"{'  OK' if ok else '  IMBALANCE'}"
    )

    if violations:
        print()
        for path, ln, txt in violations:
            print(f"  warned {path}:{ln}")
            print(f"      {txt.strip()}")
        print()
        print(
            "A census must enumerate symlinks too - a symlink to a file is a "
            "file for counting purposes.  Use \\\\( -type f -o -type l \\\\) to "
            "count both."
        )
        print("A line already carrying -type l is correct.")
        print(
            "Depth caps (e.g. -maxdepth) are a separate blind spot this guard "
            "does not check - see scripts/qc-system-integrity.sh:153-154 for "
            "a line that is correct on the type flag and wrong on depth."
        )

    if args.report_json:
        j = {
            "scanned": scanned, "matching": matching,
            "comment_heredoc": Cc, "binary": Bb,
            "safe_action": Ss, "paired_with_type_l": Pp,
            "allowlisted": Aa, "violations_count": Vv,
            "checksum_ok": ok,
            "comment_heredoc_entries": [
                {"path": p, "line": ln, "text": t}
                for p, ln, t in comment_heredoc],
            "binary_entries": [
                {"path": p, "line": ln, "text": t}
                for p, ln, t in binary_entries],
            "safe_action_entries": [
                {"path": p, "line": ln, "text": t}
                for p, ln, t in safe_action],
            "paired_entries": [
                {"path": p, "line": ln, "text": t}
                for p, ln, t in paired],
            "allowlisted_entries": [
                {"path": p, "line": ln, "text": t}
                for p, ln, t in allowlisted_entries],
            "violations": [
                {"path": p, "line": ln, "text": t}
                for p, ln, t in violations],
        }
        print()
        print(json.dumps(j, indent=2))

    if args.enforce and Vv > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
