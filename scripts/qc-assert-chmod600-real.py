#!/usr/bin/env python3
"""
qc-assert-chmod600-real.py -- comment/heredoc/quote-aware check for a REAL
`chmod 600` invocation in a shell script.

Closes the "comment bypass" in .githooks/pre-commit Gate 4 (chmod-600
coverage on secrets/.env writers). The old gate was a raw
`grep -E 'chmod[[:space:]]+600'` over the WHOLE file -- so a script that
writes secrets/.env and never actually chmods it could satisfy the gate
with nothing but a comment like `# remember to chmod 600` or a printed
instruction string, and the commit would go through with the file left
world-readable.

Usage:
    qc-assert-chmod600-real.py <file>
    exit 0  -- a real chmod 600 invocation was found (gate PASSES)
    exit 1  -- no real chmod 600 invocation found (gate BLOCKS)
    exit 2  -- usage error

WHAT COUNTS AS REAL (kept identical in strictness to the old regex --
`chmod` then 1+ space/tab then literal `600`, same-line only -- just
evaluated against cleaned, non-executable-stripped text instead of the
raw file):
  - a bare command:                    chmod 600 "$F"
  - flag-free, in real conditional/compound code:
                                        [ -f "$F" ] && chmod 600 "$F"
  - a trailing comment on the SAME line as a real chmod (the command part
    before the `#` is real, so it still counts):
                                        chmod 600 "$F"   # secure it

WHAT THIS DOES NOT COUNT AS REAL (the gate still BLOCKS on these):
  - whole-line comments:               # chmod 600 the file
  - inline text after a real `#`:      do_thing()   # then chmod 600 it
  - heredoc BODIES (any << / <<- delimiter, quoted or unquoted), including
    the `: <<'COMMENT' ... COMMENT` block-comment idiom -- heredoc payload
    text is data handed to a command's stdin, never parsed/executed as
    shell code, so a chmod 600 that only appears inside one is exactly as
    inert as one inside a comment
NOTE ON QUOTED STRINGS: quote state (single/double) IS tracked, but only
to correctly recognize comment-starts and heredoc-openers that appear
inside a string (a `#` or `<<` inside quotes must NOT be treated as real
comment/heredoc syntax, or real code later on the same line would be
wrongly dropped). Quoted text itself is left visible to the chmod-600
search rather than blanked out, matching the old gate's behavior of not
caring about quoting at all. This is a deliberate, tested trade-off: this
repo has several `qc-*.sh` scripts that only ASSERT the secrets file's
mode is 600 (e.g. `assert "Secrets file chmod 600" "[ \"$(stat -f %A ...)\"
= '600' ]"`) without ever calling chmod themselves -- the permission is
set by the writer script elsewhere, they only verify it. Blanking quoted
text would flip these already-compliant, non-writing QC scripts from
PASS to FAIL, reproducing the exact update-skills.sh-style freeze this
fix must not cause. Comments and heredoc bodies ARE still blanked (see
above) because those are the two bypass vectors named in the ask; quoted
strings are not.

COMMENT-START HEURISTIC: a `#` is only treated as starting a comment when
it begins a shell "word" -- i.e. it is the first non-whitespace character
on the line, or immediately preceded by whitespace or one of `;&|(){}`.
This deliberately does NOT fire inside parameter expansions like
`${VAR#pattern}` / `${VAR##pattern}` or the `$#` positional-count
variable, which would otherwise be misread as comments and truncate real
code later on the same line.

KNOWN LIMITATIONS (deliberately not solved here; verified absent from
every secrets/.env-referencing .sh file in this repo as of 2026-07-30):
  - Backslash-escaping inside double quotes is approximated: any
    backslash-X pair inside a double-quoted string is treated as escaping
    X. This is looser than real bash (which only escapes a handful of
    characters: dollar, backslash, double-quote, backtick, newline) but
    errs on the side of NOT losing real code, never on the side of
    hiding a real chmod.
  - Arithmetic bit-shift (`$(( x << y ))`) is not specially recognized and
    could, in principle, be misread as a heredoc opener. No script in this
    repo's secrets/.env corpus uses `<<` for anything other than heredocs
    or `<<<` here-strings (checked by hand before shipping this).
  - This checks that the chmod 600 TOKEN PAIR is genuine executable text.
    It does not trace data flow to confirm the chmod's argument is in fact
    the secrets file being written (true data-flow analysis is out of
    scope for a pre-commit grep-replacement).
"""
import re
import sys

BOUNDARY_CHARS = set(" \t;&|(){}")


def strip_non_executable(text: str) -> str:
    """Return `text` with comments and heredoc bodies blanked out (each
    removed character replaced by a single space, so line structure and
    column offsets are preserved). Quote state is tracked internally (so
    a `#` or `<<` inside a string is never mistaken for real comment/
    heredoc syntax) but quoted characters themselves are passed through
    unchanged -- see the module docstring for why."""
    lines = text.split("\n")
    result_lines = []
    # Queue of (terminator, strip_leading_tabs) heredocs opened on lines
    # not yet closed, consumed in the order they were opened.
    pending_heredocs = []

    for raw_line in lines:
        if pending_heredocs:
            terminator, strip_tabs = pending_heredocs[0]
            check_line = raw_line.lstrip("\t") if strip_tabs else raw_line
            if check_line == terminator:
                pending_heredocs.pop(0)
            # Either the terminator line or a body line: contributes
            # nothing executable either way.
            result_lines.append("")
            continue

        cleaned = []
        state = "normal"  # normal | squote | dquote
        line_heredocs = []
        m = len(raw_line)
        j = 0
        prev_boundary = True  # start-of-line counts as a boundary
        while j < m:
            c = raw_line[j]
            if state == "normal":
                if c == "\\" and j + 1 < m:
                    cleaned.append("  ")
                    j += 2
                    prev_boundary = False
                    continue
                if c == "'":
                    state = "squote"
                    cleaned.append(" ")
                    j += 1
                    prev_boundary = False
                    continue
                if c == '"':
                    state = "dquote"
                    cleaned.append(" ")
                    j += 1
                    prev_boundary = False
                    continue
                if c == "#":
                    if prev_boundary:
                        break  # real comment start: rest of line dropped
                    cleaned.append(c)
                    j += 1
                    prev_boundary = False
                    continue
                if c == "<" and j + 1 < m and raw_line[j + 1] == "<":
                    if j + 2 < m and raw_line[j + 2] == "<":
                        # here-string `<<<` -- not a heredoc opener
                        cleaned.append("   ")
                        j += 3
                        prev_boundary = False
                        continue
                    k = j + 2
                    strip_tabs = False
                    if k < m and raw_line[k] == "-":
                        strip_tabs = True
                        k += 1
                    while k < m and raw_line[k] == " ":
                        k += 1
                    quote_char = None
                    if k < m and raw_line[k] in ("'", '"'):
                        quote_char = raw_line[k]
                        k += 1
                    word_start = k
                    while k < m and (raw_line[k].isalnum() or raw_line[k] == "_"):
                        k += 1
                    word = raw_line[word_start:k]
                    if word:
                        if quote_char and k < m and raw_line[k] == quote_char:
                            k += 1
                        line_heredocs.append((word, strip_tabs))
                        cleaned.append(" " * (k - j))
                        j = k
                        prev_boundary = False
                        continue
                    # `<<` not followed by a recognizable heredoc word
                    # (e.g. arithmetic shift) -- pass through literally.
                    cleaned.append("<<")
                    j += 2
                    prev_boundary = False
                    continue
                cleaned.append(c)
                prev_boundary = c in BOUNDARY_CHARS
                j += 1
            elif state == "squote":
                # Pass quoted text through unchanged (see module docstring:
                # quote state is tracked for correctness, not to hide the
                # text from the match).
                cleaned.append(c)
                if c == "'":
                    state = "normal"
                j += 1
                prev_boundary = False
            elif state == "dquote":
                if c == "\\" and j + 1 < m:
                    cleaned.append(raw_line[j:j + 2])
                    j += 2
                    prev_boundary = False
                    continue
                cleaned.append(c)
                if c == '"':
                    state = "normal"
                j += 1
                prev_boundary = False

        result_lines.append("".join(cleaned))
        if line_heredocs:
            pending_heredocs.extend(line_heredocs)

    return "\n".join(result_lines)


# Same strictness as the old gate: `chmod` + 1-or-more spaces/tabs +
# literal `600`, matched within a single line (grep never matched across
# lines either, since it processes line by line).
CHMOD_600_RE = re.compile(r"chmod[ \t]+600")


def has_real_chmod_600(path: str) -> bool:
    with open(path, "r", errors="replace") as fh:
        text = fh.read()
    cleaned = strip_non_executable(text)
    return CHMOD_600_RE.search(cleaned) is not None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: qc-assert-chmod600-real.py <file>", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if has_real_chmod_600(sys.argv[1]) else 1)
