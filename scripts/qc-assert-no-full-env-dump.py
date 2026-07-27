#!/usr/bin/env python3
"""
qc-assert-no-full-env-dump.py — Ban `pm2 jlist` / `pm2 prettylist` / `pm2 --json`
and the Python list-form equivalents. Ships in warn-mode (Rule 3.5 stage 1).

Detects all four forms:
  shell:  pm2 jlist, pm2 prettylist, pm2 <...> --json
  Python list form: subprocess.run(["pm2", "jlist"], ...) — via syntax-tree walk

Reports a five-field denominator (Law 14 rule 6):
  scanned N tracked files; M matching lines; S classified safe; K allowlisted; V violations
  checksum: prose P + comment C + existence-only E + filtered F + allowlisted K = M

Exit: 0 in warn-mode (default), 1 under --enforce when V > 0.

Never scans outside git ls-files. Never echoes a full matched line from a
forbidden source — reports path:line and the matched command fragment only.
"""

import argparse
import ast
import json as json_mod
import os
import re
import subprocess
import sys


# -- Patterns ------------------------------------------------------------------

# Shell forms: pm2 jlist, pm2 prettylist, pm2 <anything> --json, bare --json
SHELL_RE = re.compile(r'pm2[ \t]+(jlist|prettylist|[A-Za-z0-9_-]+[ \t]+--json|--json)')

# For stripping leading whitespace
STRIP_RE = re.compile(r'^[ \t]*')

# Existence-only: the match is piped into grep -q/-l/-L (or long forms)
EXISTENCE_RE = re.compile(
    r'\|\s*grep\s+[^|]*(?:'
    r'(?<![A-Za-z0-9])-[A-Za-z]*[qlL][A-Za-z]*'
    r'|--(?:quiet|silent|files-with-matches|files-without-match)'
    r')'
)

# Filter function names to recognise as safe
FILTER_FN_RE = re.compile(r'filter_pm2|_filter|sanitize')

# JSON keys whose string values are prose, not violations
PROSE_JSON_KEYS = {'note', '_source', '_comment'}


# -- CLI -----------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description='Ban full pm2 environment dumps in tracked repository files.')
    p.add_argument('--enforce', action='store_true',
                   help='Exit 1 when violations > 0 (fail-closed, not wired yet)')
    p.add_argument('--report-json', action='store_true',
                   help='Emit machine-readable JSON summary to stdout')
    p.add_argument('repo_root', nargs='?', default=None,
                   help='Repository root (default: auto-detect via git)')
    return p.parse_args()


# -- Git helpers ----------------------------------------------------------------

def get_repo_root():
    try:
        return subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return os.getcwd()


def get_tracked_files(repo_root):
    """Return list of tracked files via git ls-files -z."""
    try:
        out = subprocess.run(
            ['git', 'ls-files', '-z'],
            capture_output=True, text=True, cwd=repo_root, check=True
        ).stdout
        return [f for f in out.split('\0') if f]
    except Exception:
        print("ERROR: git ls-files failed", file=sys.stderr)
        sys.exit(2)


# -- Binary detection -----------------------------------------------------------

def is_binary(filepath):
    """Read first 4 bytes; a .skill file is a zip archive (PK magic)."""
    try:
        with open(filepath, 'rb') as fh:
            return fh.read(4) == b'PK\x03\x04'
    except OSError:
        return True  # unreadable — skip


# -- Prose file detection -------------------------------------------------------

def is_prose_file(filepath):
    """True for .md files (changelog, doc, spec, ledger)."""
    return filepath.endswith('.md')


# -- JSON prose-key detection --------------------------------------------------

def is_json_prose_key(filepath, line, match_start):
    """True if the match falls inside a JSON string value whose key is
    note, _source, or _comment — the match is documentation, not code."""
    if not filepath.endswith('.json'):
        return False
    # Search backwards from the match position for a JSON key pattern
    prefix = line[:match_start]
    for key in PROSE_JSON_KEYS:
        pat = '"' + re.escape(key) + '"'
        idx = prefix.rfind(pat)
        if idx >= 0:
            # Verify there's a colon after the key (on the remaining prefix)
            after_key = prefix[idx + len(pat):]
            if re.match(r'\s*:\s*"', after_key):
                return True
    return False


# -- Comment / docstring detection ----------------------------------------------

def _get_python_docstring_lines(source):
    """Return set of line numbers that fall within Python docstring bodies.
    Handles function, class, and module docstrings."""
    doc_lines = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return doc_lines
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                val = body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    for ln in range(body[0].lineno, body[0].end_lineno + 1):
                        doc_lines.add(ln)
    return doc_lines


def is_comment_or_docstring(filepath, line, lineno, source=None):
    """Check if the match line is a shell comment, Python comment, or Python
    docstring."""
    stripped = STRIP_RE.sub('', line, count=1)
    # Python / shell comment
    if stripped.startswith('#'):
        return True
    # Python docstring (needs source for AST)
    if filepath.endswith('.py') and source is not None:
        doc_lines = _get_python_docstring_lines(source)
        if lineno in doc_lines:
            return True
    return False


# -- Existence-only detection --------------------------------------------------

def is_existence_only(line, match_end):
    """True if the matched command is immediately piped into grep -q/-l/-L
    (or long equivalents), so nothing is captured or printed."""
    after = line[match_end:]
    return bool(EXISTENCE_RE.search(after))


# -- Python list-form detection (AST walk) -------------------------------------

def detect_list_form(path, source):
    """Detect Python list-form pm2 jlist/prettylist invocations via AST walk.
    Returns list of line numbers for the *Call node* (not the list literal).

    A subprocess.run(["pm2", "jlist"], ...) is structurally invisible to a text
    regex, and the regex that matches the literal reports :620 on a call at :619.
    This function returns the call node's own lineno so the allowlist entry and
    the census agree on every line number.
    """
    hits = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            arg0 = node.args[0]
            if isinstance(arg0, ast.List):
                values = [e.value for e in arg0.elts
                          if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if values and values[0] == 'pm2' and any(
                        x in ('jlist', 'prettylist') for x in values):
                    hits.append(node.lineno)
    return hits


# -- Filtered detection (Python AST) --------------------------------------------

def _find_enclosing_function(tree, lineno):
    """Return the FunctionDef/AsyncFunctionDef node that contains lineno, or None."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= node.end_lineno:
                return node
    return None


def _function_calls_filter(node, filter_re=FILTER_FN_RE):
    """True if any call inside the function body matches the filter function regex."""
    for subnode in ast.walk(node):
        if isinstance(subnode, ast.Call):
            name = None
            if isinstance(subnode.func, ast.Name):
                name = subnode.func.id
            elif isinstance(subnode.func, ast.Attribute):
                name = subnode.func.attr
            if name and filter_re.search(name):
                return True
    return False


def is_list_form_filtered(path, source, lineno):
    """True if the list-form call at lineno is inside a function that also calls
    a recognised filter function (filter_pm2|_filter|sanitize)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    func = _find_enclosing_function(tree, lineno)
    if func is None:
        return False
    return _function_calls_filter(func)


# -- Allowlist ------------------------------------------------------------------

def load_allowlist(repo_root):
    """Parse scripts/qc-assert-no-full-env-dump.allowlist.
    Returns dict mapping 'path:line' -> classification string."""
    al_path = os.path.join(repo_root, 'scripts',
                           'qc-assert-no-full-env-dump.allowlist')
    allowlist = {}
    if not os.path.isfile(al_path):
        return allowlist
    with open(al_path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split('|', 2)]
            if len(parts) >= 2:
                allowlist[parts[0]] = parts[1]
    return allowlist


# -- Fragment extraction (never the full line) ----------------------------------

def match_fragment(line, match_start, match_end):
    """Return only the matched command fragment, never the full line.
    An adjacent field can carry a secret value."""
    return line[max(0, match_start - 10):match_end + 10].strip()


# -- Main scan ------------------------------------------------------------------

SELF_FILES = {
    'scripts/qc-assert-no-full-env-dump.py',
    'scripts/qc-assert-no-full-env-dump.allowlist',
    'scripts/tests/full-env-dump-guard.negative-fixture.sh',
    '.github/workflows/full-env-dump-guard.yml',
    '.githooks/pre-commit',
}


def scan(repo_root):
    """Run the full scan. Returns a dict of results."""
    # Classifications (the five classes)
    prose_hits = []         # .md files or JSON prose keys
    comment_hits = []        # comments / docstrings
    existence_hits = []      # piped to grep -q/-l/-L
    filtered_hits = []       # output passed through filter function
    allowlisted_hits = []    # in allowlist
    violation_hits = []      # unclassified — real risk, not exempted

    allowlist = load_allowlist(repo_root)
    files = get_tracked_files(repo_root)
    scanned = 0

    for f in files:
        if f in SELF_FILES:
            continue
        fpath = os.path.join(repo_root, f)
        if not os.path.isfile(fpath):
            continue
        if is_binary(fpath):
            continue
        scanned += 1

        # Read source once
        try:
            with open(fpath, 'rb') as fh:
                raw = fh.read()
        except OSError:
            continue

        # Decode for text analysis
        try:
            text = raw.decode('utf-8', errors='replace')
        except Exception:
            continue

        # Python source for AST operations (kept separately for parse safety)
        py_source = text if f.endswith('.py') else None

        # 1. Shell-form matches
        lines = text.split('\n')
        for i, line in enumerate(lines, 1):
            for m in SHELL_RE.finditer(line):
                match_start, match_end = m.start(), m.end()
                ref = f'{f}:{i}'

                # Classification cascade (first match wins, in priority order)
                classified = False

                # Prose files
                if is_prose_file(f):
                    prose_hits.append(ref)
                    classified = True
                    continue

                # JSON prose keys
                if is_json_prose_key(f, line, match_start):
                    prose_hits.append(ref)
                    classified = True
                    continue

                # Comments / docstrings
                if is_comment_or_docstring(f, line, i, source=py_source):
                    comment_hits.append(ref)
                    classified = True
                    continue

                # Existence-only (grep -q/-l/-L)
                if is_existence_only(line, match_end):
                    existence_hits.append(ref)
                    classified = True
                    continue

                # Allowlist
                if ref in allowlist:
                    allowlisted_hits.append(ref)
                    classified = True
                    continue

                # Unclassified shell hit → violation
                if not classified:
                    violation_hits.append(ref)

        # 2. Python list-form matches (AST walk)
        if f.endswith('.py') and py_source:
            list_lines = detect_list_form(f, py_source)
            for lineno in list_lines:
                ref = f'{f}:{lineno}'

                # Check filtered
                if is_list_form_filtered(f, py_source, lineno):
                    filtered_hits.append(ref)
                    continue

                # Allowlist
                if ref in allowlist:
                    allowlisted_hits.append(ref)
                    continue

                # Unclassified list-form hit → violation
                violation_hits.append(ref)

    # Deduplicate (a ref can appear in exactly one class by construction,
    # but be safe)
    return {
        'scanned': scanned,
        'prose': sorted(set(prose_hits)),
        'comment': sorted(set(comment_hits)),
        'existence_only': sorted(set(existence_hits)),
        'filtered': sorted(set(filtered_hits)),
        'allowlisted': sorted(set(allowlisted_hits)),
        'violations': sorted(set(violation_hits)),
    }


# -- Reporting ------------------------------------------------------------------

def checksum(res):
    """Build the checksum string: prose P + comment C + existence-only E
    + filtered F + allowlisted K = M."""
    P = len(res['prose'])
    C = len(res['comment'])
    E = len(res['existence_only'])
    F = len(res['filtered'])
    K = len(res['allowlisted'])
    M = P + C + E + F + K + len(res['violations'])
    return (f'{P} prose + {C} comment + {E} existence-only + '
            f'{F} filtered + {K} allowlisted = {M}')


def report_text(res):
    """Human-readable five-field report."""
    M = (len(res['prose']) + len(res['comment']) + len(res['existence_only']) +
         len(res['filtered']) + len(res['allowlisted']) + len(res['violations']))
    S = len(res['prose']) + len(res['comment']) + len(res['existence_only']) + len(res['filtered'])
    K = len(res['allowlisted'])
    V = len(res['violations'])

    lines = []
    lines.append(f"scanned {res['scanned']} tracked files; "
                 f"{M} matching lines; "
                 f"{S} classified safe; "
                 f"{K} allowlisted; "
                 f"{V} violations")
    lines.append(checksum(res))

    if res['violations']:
        lines.append('')
        lines.append('VIOLATIONS (unfiltered pm2 jlist / prettylist / --json):')
        for v in res['violations']:
            lines.append(f'  {v}')
        lines.append('')
        lines.append(
            'Reference pattern: 61-loop-protection-system/scripts/loop_common.py:164-172 '
            '(filter_pm2_record), asserted at :281. Report a process\'s presence by name '
            'only, never its value. Never capture a full process list into a shell variable.'
        )

    return '\n'.join(lines)


def report_json(res):
    """Machine-readable JSON summary."""
    M = (len(res['prose']) + len(res['comment']) + len(res['existence_only']) +
         len(res['filtered']) + len(res['allowlisted']) + len(res['violations']))
    S = len(res['prose']) + len(res['comment']) + len(res['existence_only']) + len(res['filtered'])

    return json_mod.dumps({
        'scanned': res['scanned'],
        'matching': M,
        'classified_safe': S,
        'allowlisted': len(res['allowlisted']),
        'violations': len(res['violations']),
        'checksum': checksum(res),
        'prose': res['prose'],
        'comment': res['comment'],
        'existence_only': res['existence_only'],
        'filtered': res['filtered'],
        'allowlisted_entries': res['allowlisted'],
        'violation_entries': res['violations'],
    }, indent=2)


# -- Main -----------------------------------------------------------------------

def main():
    args = parse_args()
    repo_root = args.repo_root or get_repo_root()
    os.chdir(repo_root)

    res = scan(repo_root)

    if args.report_json:
        print(report_json(res))
    else:
        print(report_text(res))

    V = len(res['violations'])
    if args.enforce and V > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
