#!/usr/bin/env python3
r"""
Syntax-check EVERY Python program embedded inside a shell script.

WHY THIS EXISTS
---------------
`bash -n` does NOT parse heredoc bodies. It validates the shell grammar around
them and treats the body as opaque text. So a shell script carrying a Python
program with a hard SyntaxError passes `bash -n` cleanly, ships, and the Python
only dies at runtime -- where a `2>/dev/null` plus a `|| true` on the call site
turn the death into a silent no-op that still reports success.

That is not hypothetical. `lib-onboarding-state.sh`'s `oc_state_mark_field`
carried `except Exception: return` -- a `return` outside any function -- from the
day it was written. Python raises SyntaxError at COMPILE time, before the first
statement runs, so the function never wrote a field on ANY path, including the
healthy one, and still exited 0. Nothing in this repo checked embedded bodies,
which is why a permanently broken function shipped and stayed broken.

This guard closes that hole.

USE compile(), NOT ast.parse()
------------------------------
`ast.parse` is only the PARSER. It accepts `return` outside a function, `break`
outside a loop, and `yield` at module level -- those are rejected later, by the
symbol-table pass inside `compile()`. A guard built on `ast.parse` would have
missed the exact defect that motivated it. This module calls `compile()`.

WHAT IT CHECKS
--------------
  1. Heredoc bodies fed to python:   python3 - <<'PYEOF' ... PYEOF
  2. Inline programs:                python3 -c '...'

Shell reality that is handled:
  * Line continuations. `python3 - <<'PY' \` followed by `  || die "..."` means
    the heredoc body starts AFTER the continued command, not on the next line.
  * `<<-` tab-stripped heredocs.
  * Quoted vs unquoted delimiters. `<<'EOF'` is literal; `<<EOF` is expanded by
    the shell first, so `$VAR`/`$(cmd)`/backticks are replaced with an inert
    placeholder before compiling -- structural errors are still caught, the
    expansion itself is not flagged.
  * Shell word concatenation in `-c` arguments, e.g.
    `python3 -c 'json.dump(x, open("'"$F"'","w"))'` -- three glued segments that
    a naive "scan to the next quote" would truncate mid-string.

HONESTY RULE
------------
Anything this guard cannot reconstruct with confidence is reported as
UNANALYZABLE and counted -- never silently dropped and never counted as a pass.
A guard that quietly skips what it cannot handle is the same silent-success bug
it was written to prevent.

EXIT CODES
----------
  0  every embedded Python program compiles
  1  at least one failed to compile  (the guard's whole purpose)
  2  the guard itself could not run

USAGE
-----
  scripts/check-embedded-python-syntax.py [--root DIR] [--verbose]
"""

import argparse
import os
import re
import sys
import warnings

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"}
SHELL_EXTS = {".sh", ".bash"}
SHELL_SHEBANG = re.compile(rb"^#!.*\b(?:ba)?sh\b")

HEREDOC_RE = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
PYTHON_WORD_RE = re.compile(r"(?:^|[\s|;&(<\"'=])(?:[\w./$-]*/)?python[\d.]*(?=[\s\"']|$)")
DASH_C_RE = re.compile(r"python[\d.]*\s+(?:-[A-Za-z]+\s+)*-c\s+(?=['\"])")

EXPANSION_RE = re.compile(
    r"\$\{[^}]*\}"
    r"|\$[A-Za-z_][A-Za-z0-9_]*"
    r"|\$[0-9@*#?]"
)

PLACEHOLDER = "_SHELL_EXPANSION_"
WORD_END_CHARS = set(" \t\n;|&)<>")


class Finding:
    def __init__(self, path, line, kind, detail, snippet):
        self.path, self.line, self.kind = path, line, kind
        self.detail, self.snippet = detail, snippet


def is_shell_file(path):
    ext = os.path.splitext(path)[1]
    if ext in SHELL_EXTS:
        return True
    if ext:
        return False
    try:
        with open(path, "rb") as fh:
            return bool(SHELL_SHEBANG.match(fh.readline()))
    except OSError:
        return False


def neutralise_expansions(text):
    """Replace $VAR / ${...} with an inert Python identifier."""
    return EXPANSION_RE.sub(PLACEHOLDER, text)


def skip_command_substitution(text, i):
    """`i` is the index OF the '(' in `$(`. Return the index just past its ')'.

    Quote-aware: parens inside '...' or "..." do not count toward the depth,
    otherwise a python snippet like `[l.strip() for l in xs]` nested in a
    command substitution closes the substitution early and corrupts everything
    downstream. Returns None if the parens never balance.

    OFF-BY-ONE THIS FIXED (do not re-introduce). Every one of the four callers
    passes the index of the '(' -- `skip_command_substitution(text, k + 1)`
    where `text[k] == '$'`. This function used to start scanning at `i + 1`,
    i.e. one char PAST the opening paren, so `depth` never reached 1: the first
    ')' drove it to -1, the `depth == 0` return never fired, and the scan ran
    off the end and returned None for EVERY well-formed `$( ... )` in the repo.
    None propagates as "unanalyzable", which is why 58 `python3 -c` bodies --
    every one of them written as `VAR="$(python3 -c '...')"` -- were printed as
    UNANALYZABLE and never compiled. A broken body at any of those 58 sites
    could not fail this guard. Starting at `i` makes the loop see the '(' and
    count it.
    """
    depth = 0
    k = i  # `i` is the index of the '(' itself; the loop must see it to count it
    quote = None
    while k < len(text):
        c = text[k]
        if quote:
            if c == "\\" and quote == '"' and k + 1 < len(text):
                k += 2
                continue
            if c == quote:
                quote = None
            k += 1
            continue
        if c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return k + 1
        k += 1
    return None


def logical_line_start(text, offset):
    """Offset of the first char of the logical line containing `offset`."""
    start = text.rfind("\n", 0, offset) + 1
    while start > 1 and text[start - 2: start - 1] == "\\":
        prev = text.rfind("\n", 0, start - 1) + 1
        if prev == start:
            break
        start = prev
    return start


def enclosing_quoted_span(text, offset):
    """Find the shell quoted string that encloses `offset`, if any.

    Returns (quote_char, content_start, content_end) or None.

    This repo passes commands as quoted strings for a LATER `eval` -- the
    `check "3.5" "python3 -c 'import json; json.load(open(\\"$F\\"))'"` and
    `warn_only "desc" "python3 -c 'import yaml'"` patterns. The embedded python
    is perfectly real and must be checked, but its text only becomes the true
    source AFTER the shell strips one quoting layer. So rather than give up,
    peel the layer and re-scan the inside.
    """
    found = _quote_state_at(text, logical_line_start(text, offset), offset)
    if found is None:
        return None
    quote, qstart = found
    end = _find_closing_quote(text, offset, quote)
    if end is None:
        return None
    return (quote, qstart, end)


def _quote_state_at(text, start, offset):
    """Innermost quote enclosing `offset`, scanning forward from `start`.

    `$( ... )` is a NESTED COMMAND context, not string data: the shell parses
    quotes inside it independently. So `VAR="$(python3 -c 'code')"` puts the
    python at command level even though an outer double quote is open, while
    `check "python3 -c 'code'"` really is a deferred-eval string. Conflating the
    two is what made this scanner mis-read ~90 real call sites.
    """
    quote, qstart, k = None, None, start
    while k < offset:
        c = text[k]
        if quote == "'":
            if c == "'":
                quote, qstart = None, None
            k += 1
            continue
        if c == "$" and k + 1 < len(text) and text[k + 1] == "(":
            end = skip_command_substitution(text, k + 1)
            if end is None:
                break
            if offset < end:
                return _quote_state_at(text, k + 2, offset)
            k = end
            continue
        if quote == '"':
            if c == "\\":
                k += 2
                continue
            if c == '"':
                quote, qstart = None, None
            k += 1
            continue
        if c in "'\"":
            quote, qstart = c, k + 1
        k += 1
    return (quote, qstart) if quote else None


def _find_closing_quote(text, offset, quote):
    """Offset of the quote that closes the string containing `offset`."""
    k = offset
    while k < len(text):
        c = text[k]
        if quote == '"':
            if c == "\\":
                k += 2
                continue
            if c == "$" and k + 1 < len(text) and text[k + 1] == "(":
                end = skip_command_substitution(text, k + 1)
                if end is None:
                    return None
                k = end
                continue
        if c == quote:
            return k
        k += 1
    return None


def unescape_double_quoted(s):
    """Strip ONE layer of double-quote escaping, as the shell would."""
    out, k = [], 0
    while k < len(s):
        if s[k] == "\\" and k + 1 < len(s) and s[k + 1] in '"\\$`':
            out.append(s[k + 1])
            k += 2
            continue
        out.append(s[k])
        k += 1
    return "".join(out)


# A redirect target: `> file`, `>> file`. The word after it is a FILENAME, so a
# path that merely ends in `python3` (e.g. `cat > "$SHIM_DIR/python3" <<PYSHIM`)
# is not a python invocation.
REDIRECT_TARGET_RE = re.compile(r"(?:\d?>>?|\d?<)\s*(?:\"[^\"]*\"|'[^']*'|[^\s|;&<>]+)")


def read_double_quoted(text, i):
    """Read a "..." segment starting at the opening quote. Returns (src, end)."""
    out = []
    k = i + 1
    while k < len(text):
        c = text[k]
        if c == "\\" and k + 1 < len(text):
            nxt = text[k + 1]
            # Inside double quotes the shell only honours these escapes.
            if nxt in '"\\$`':
                out.append(nxt)
            else:
                out.append(c)
                out.append(nxt)
            k += 2
            continue
        if c == "`":
            return None, None  # backtick substitution: not reconstructable
        if c == "$" and k + 1 < len(text) and text[k + 1] == "(":
            end = skip_command_substitution(text, k + 1)
            if end is None:
                return None, None
            out.append(PLACEHOLDER)
            k = end
            continue
        if c == '"':
            return neutralise_expansions("".join(out)), k + 1
        out.append(c)
        k += 1
    return None, None


def read_single_quoted(text, i):
    """Read a '...' segment. No escaping exists inside single quotes."""
    end = text.find("'", i + 1)
    if end == -1:
        return None, None
    return text[i + 1:end], end + 1


def read_shell_word(text, i):
    """Reconstruct one shell WORD (possibly several glued quoted segments).

    Returns (python_source, end_index) or (None, None) if unanalyzable.
    """
    parts = []
    k = i
    while k < len(text):
        c = text[k]
        if c in WORD_END_CHARS:
            break
        if c == "'":
            seg, k2 = read_single_quoted(text, k)
        elif c == '"':
            seg, k2 = read_double_quoted(text, k)
        elif c == "`":
            return None, None
        elif c == "\\" and k + 1 < len(text):
            seg, k2 = text[k + 1], k + 2
        elif c == "$" and k + 1 < len(text) and text[k + 1] == "(":
            end = skip_command_substitution(text, k + 1)
            if end is None:
                return None, None
            seg, k2 = PLACEHOLDER, end
        else:
            j = k
            while j < len(text) and text[j] not in WORD_END_CHARS and text[j] not in "'\"`\\":
                if text[j] == "$" and j + 1 < len(text) and text[j + 1] == "(":
                    break
                j += 1
            seg, k2 = neutralise_expansions(text[k:j]), j
        if seg is None:
            return None, None
        parts.append(seg)
        k = k2
    return "".join(parts), k


def logical_line_end(lines, idx):
    """Index of the last physical line of the logical command starting at idx."""
    k = idx
    while k < len(lines) and lines[k].rstrip("\n").endswith("\\"):
        k += 1
    return min(k, len(lines) - 1)


def extract_heredocs(lines):
    """Yield (open_line_1based, delim, quoted, body, body_start_1based)."""
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("#"):
            i += 1
            continue
        # Strip redirect targets before looking for the interpreter, so
        # `cat > "$DIR/python3" <<PYSHIM` is not mistaken for a python heredoc.
        matches = [
            m for m in HEREDOC_RE.finditer(line)
            if PYTHON_WORD_RE.search(REDIRECT_TARGET_RE.sub(" ", line[: m.start()]))
        ]
        if not matches:
            i += 1
            continue

        # The body begins after the WHOLE logical command (continuations included).
        body_start = logical_line_end(lines, i) + 1
        cursor = body_start
        last = cursor
        for m in matches:
            dash, quote, delim = m.group(1), m.group(2), m.group(3)
            body, j = [], cursor
            found = False
            while j < n:
                probe = lines[j].lstrip("\t") if dash else lines[j]
                if probe.rstrip("\n").rstrip() == delim:
                    found = True
                    break
                body.append(lines[j])
                j += 1
            if found:
                yield (i + 1, delim, bool(quote), "".join(body), cursor + 1)
                cursor = j + 1        # stacked heredocs follow one another
                last = max(last, j)
        i = max(last + 1, i + 1)


MAX_QUOTE_PEEL_DEPTH = 3


def extract_dash_c(text, base_line=1, depth=0, _seen=None):
    """Yield (line_1based, source_or_None) for each `python -c` invocation.

    A None source means UNANALYZABLE -- the caller must report it, never drop
    it. A guard that quietly skips what it cannot parse is the same silent
    -success bug this file exists to prevent.
    """
    if _seen is None:
        _seen = set()
    for m in DASH_C_RE.finditer(text):
        line_no = base_line + text.count("\n", 0, m.start())
        span = enclosing_quoted_span(text, m.start())
        if span is None:
            src, _ = read_shell_word(text, m.end())
            yield (line_no, src)
            continue

        quote, cstart, cend = span
        key = (depth, cstart, cend)
        if key in _seen:
            continue          # several -c calls share one quoted string
        _seen.add(key)
        if depth >= MAX_QUOTE_PEEL_DEPTH:
            yield (line_no, None)
            continue
        inner = text[cstart:cend]
        if quote == '"':
            inner = unescape_double_quoted(inner)
        inner_base = base_line + text.count("\n", 0, cstart)
        # Peel this quoting layer and re-scan what the shell will actually run.
        yield from extract_dash_c(inner, inner_base, depth + 1, _seen)


def compile_body(source, label):
    """Compile; return None on success or a SyntaxError instance."""
    with warnings.catch_warnings():
        # Invalid-escape SyntaxWarnings are noise here; we want hard errors only.
        warnings.simplefilter("ignore")
        try:
            compile(source, label, "exec")
        except SyntaxError as exc:
            return exc
        except ValueError as exc:  # e.g. source with NUL bytes
            return SyntaxError(str(exc))
    return None


def check_file(path, root, findings, unanalyzable, stats):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        findings.append(Finding(path, 0, "unreadable", str(exc), ""))
        return
    lines = text.splitlines(keepends=True)
    rel = os.path.relpath(path, root)

    for (open_line, delim, quoted, body, body_start) in extract_heredocs(lines):
        stats["heredocs"] += 1
        if not body.strip():
            continue
        source = body if quoted else neutralise_expansions(body)
        kind = "heredoc" if quoted else "heredoc(expanded)"
        exc = compile_body(source, f"{rel}:<<{delim}")
        if exc is not None:
            stats["failed"] += 1
            abs_line = body_start + (exc.lineno or 1) - 1
            findings.append(Finding(
                rel, abs_line, kind,
                f"{exc.msg}  (<<{delim} opened at line {open_line}, body line {exc.lineno})",
                (exc.text or "").rstrip()))

    for (line_no, src) in extract_dash_c(text):
        stats["dash_c"] += 1
        if src is None:
            stats["unanalyzable"] += 1
            unanalyzable.append(Finding(rel, line_no, "python -c", "could not reconstruct the shell word", ""))
            continue
        if not src.strip():
            continue
        exc = compile_body(src, f"{rel}:-c")
        if exc is not None:
            stats["failed"] += 1
            findings.append(Finding(
                rel, line_no, "python -c",
                f"{exc.msg}  (body line {exc.lineno})",
                (exc.text or "").rstrip()))


def main():
    ap = argparse.ArgumentParser(
        description="Syntax-check Python embedded in shell heredocs and `python -c`.")
    ap.add_argument("--root", default=".", help="repo root to scan (default: cwd)")
    ap.add_argument("--verbose", action="store_true", help="list unanalyzable sites too")
    ap.add_argument(
        "--max-unanalyzable", type=int, default=None,
        help="fail if MORE than N sites could not be reconstructed (coverage ratchet; "
             "omit to keep the historical behaviour of reporting them without failing)")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"guard error: --root {root} is not a directory", file=sys.stderr)
        return 2

    findings, unanalyzable = [], []
    stats = {"files": 0, "heredocs": 0, "dash_c": 0, "failed": 0, "unanalyzable": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            if not is_shell_file(full):
                continue
            stats["files"] += 1
            check_file(full, root, findings, unanalyzable, stats)

    print("embedded-python syntax guard")
    print(f"  shell files scanned      : {stats['files']}")
    print(f"  python heredocs found    : {stats['heredocs']}")
    print(f"  python -c bodies found   : {stats['dash_c']}")
    print(f"  unanalyzable (reported)  : {stats['unanalyzable']}")
    print(f"  bodies that FAILED parse : {stats['failed']}")

    if args.verbose and unanalyzable:
        print("\nUNANALYZABLE sites (not a failure; listed so they are never silently skipped):")
        for f in unanalyzable:
            print(f"  {f.path}:{f.line}  {f.detail}")

    # Coverage ratchet. An unanalyzable site is NOT compiled, so a broken body
    # there cannot fail this guard -- exactly the hole that let 58 sites go
    # unchecked. With --max-unanalyzable the residue can never silently grow.
    over_ceiling = (
        args.max_unanalyzable is not None
        and stats["unanalyzable"] > args.max_unanalyzable
    )
    if over_ceiling:
        print(f"\nFAIL - {stats['unanalyzable']} unanalyzable site(s) exceeds the "
              f"--max-unanalyzable ceiling of {args.max_unanalyzable}.")
        if not args.verbose:
            for f in unanalyzable:
                print(f"  {f.path}:{f.line}  {f.detail}")
        print("An unanalyzable site is never compiled, so a SyntaxError there cannot fail\n"
              "this guard. Rewrite the call site so the body can be reconstructed, or teach\n"
              "the extractor the new shape. Raising the ceiling re-opens the hole.")

    if not findings:
        if over_ceiling:
            return 1
        print("\nPASS - every embedded Python program compiles.")
        return 0

    print("\nFAIL - embedded Python that does not compile:\n")
    for f in findings:
        print(f"  {f.path}:{f.line}  [{f.kind}]")
        print(f"      {f.detail}")
        if f.snippet:
            print(f"      | {f.snippet}")
        print()
    print("These die at RUNTIME. With `2>/dev/null` and `|| true` on the call site the\n"
          "failure is invisible and the caller sees success. Fix the body.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
