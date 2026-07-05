#!/usr/bin/env bash
# qc-assert-no-secret-printing-grep.sh  (FIX-XC-07)
#
# Deterministic shipped gate: fails any SECRET-PATTERN grep in the shipped
# cross-skill 36+38 SOP docs that lacks an existence-only flag (-q / -l / -L or
# their long forms). A bare `grep -iE 'GHL_API_KEY|...' "$SECRETS_ENV"` prints the
# MATCHED LINE — i.e. the secret's VALUE — into transcripts/logs. Existence-only
# forms (`grep -qE ... && echo SET`) or filename-only forms (`grep -l`) never do.
#
# The check inspects the grep PATTERN only (the first non-flag argument), NOT the
# file argument — so reading a NON-secret value like `grep '^BATCH_MODEL=' "$SECRETS_ENV"`
# (a model id, out of a file whose NAME contains "SECRET") is correctly NOT flagged.
#
# This is a DETERMINISTIC static invariant (permitted as a shipped gate); the
# campaign's QC quality judgments remain LLM-review. Scope is the two skill dirs
# this rule guards so it never false-fails on other skills' unrelated files.
#
# Usage: qc-assert-no-secret-printing-grep.sh [REPO_ROOT]
# Exit:  0 = clean, 1 = at least one secret-printing grep found.
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

python3 - "$REPO_ROOT" <<'PY'
import os, re, sys

REPO_ROOT = sys.argv[1]
TARGETS = ["36-ghl-mcp-setup", "38-conversational-ai-system"]

# A grep whose PATTERN names one of these secret tokens would print the secret's
# VALUE unless it is existence-only (-q) or filename-only (-l/-L). Location IDs and
# bare provider names (GHL/GOHIGH/LEADCONN) are NOT secrets and are excluded.
SECRET_RE = re.compile(
    r'API_KEY|TOKEN|PRIVATE_INTEGRATION|(?<![A-Za-z])PIT(?![A-Za-z])|SECRET|PASSWORD|BEARER'
)

# Match a grep invocation: grep <flag-tokens...> <pattern>. The pattern is the
# first non-flag argument, quoted ('..'/"..") or bare.
GREP_RE = re.compile(
    r'''\bgrep\b\s+((?:-\S+\s+)*)(?:'([^']*)'|"([^"]*)"|(\S+))'''
)

# A value-STRIPPING pipe stage before the grep makes the grep names-only (it can
# never see a value), so `printenv | cut -d= -f1 | grep -E 'API_KEY|TOKEN'` is safe.
STRIP_RE = re.compile(
    r"""cut\s+-d\s*'?=|-F\s*'?=|sed\s+[^|]*s/=|grep\s+-o\S*\s+['"]?\^\[A-Z_\]"""
)

def existence_only(flags: str) -> bool:
    # long forms
    if re.search(r'--(quiet|silent|files-with-matches|files-without-match)', flags):
        return True
    # short-flag clusters carrying q / l / L (e.g. -q, -qE, -rilE, -L)
    for tok in flags.split():
        if tok.startswith('-') and not tok.startswith('--'):
            if any(c in tok[1:] for c in 'qlL'):
                return True
    return False

violations = []
for d in TARGETS:
    root = os.path.join(REPO_ROOT, d)
    if not os.path.isdir(root):
        continue
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not (fn.endswith('.md') or fn.endswith('.sh')):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for m in GREP_RE.finditer(line):
                    flags = m.group(1) or ''
                    pattern = m.group(2) or m.group(3) or m.group(4) or ''
                    if not SECRET_RE.search(pattern):
                        continue
                    if existence_only(flags):
                        continue
                    # Safe if an earlier pipe stage already stripped values to names.
                    if STRIP_RE.search(line[:m.start()]):
                        continue
                    violations.append((os.path.relpath(path, REPO_ROOT), i, line.rstrip()))

if violations:
    for f, ln, txt in violations:
        print(f"  ✗ {f}:{ln} secret-pattern grep lacks -q/-l/-L (prints the value):")
        print(f"      {txt.strip()}")
    sys.exit(1)
print("✓ No secret-printing greps in 36/38 shipped SOPs (every secret-pattern grep is existence-only)")
PY
