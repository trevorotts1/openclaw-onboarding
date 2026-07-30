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

    qc-assert-chmod600-real.py --is-write-reference <file>
    exit 0  -- file contains a genuine WRITE reference to secrets/.env
              (Gate 4's trigger condition -- see is_secrets_env_write_
              reference() below for the full design and its limitations)
    exit 1  -- no write reference found (mention/read/assert/source only
              -- Gate 4 does not even check this file's chmod coverage)
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


# ---------------------------------------------------------------------------
# --is-write-reference -- Gate 4's TRIGGER condition (2026-07-30, PR
# fix/chmod600-trigger-narrowing).
#
# WHY THIS EXISTS: Gate 4 used to fire has_real_chmod_600() on any .sh file
# that merely *mentioned* `secrets/.env` or `SECRETS_ENV_FILE` anywhere --
# a comment, a `grep`/`source` read, a QC `assert` on the file's mode, a
# doc string, a test fixture path. An audit of the 98 .sh files matching
# that mention-only trigger found 62 blocked, and only 3 of them were
# genuine writers of the secrets file; the other 59 never write it at all
# (read-only sourcing, credential-presence checks, QC assertions, dead
# boilerplate from a shared `resolve_platform_paths()` snippet, doc/test
# text). This silently froze scripts/update-skills.sh at v21.4.2 for 14
# releases and would have frozen dozens more the moment anyone touched
# them. See the PR description for the full 62-file classification.
#
# is_secrets_env_write_reference() narrows the trigger to files that
# actually WRITE the secrets store: a write-like shell construct (`>`,
# `>>`, `tee`, `touch`, `cp`, `mv`, or an in-place `sed -i`) whose target
# names or aliases the secrets file, on the same logical line (backslash
# line-continuations are joined first). "Names or aliases" is resolved
# per-file, two ways, since no single check covers every real writer found
# in this repo's corpus:
#   1. NAME family -- the variable name itself matches the convention this
#      repo actually uses for the secrets-env FILE (SECRETS_ENV,
#      SECRETS_ENV_FILE, OC_SECRETS, OC_SECRETS_ENV, _OC_SECRETS_ENV,
#      _PF_SECRETS_STORE, bare SECRETS). Needed for cases like
#      shared-utils/provision-persona-index.sh's wire_ghl_funnel_catalog(),
#      where the write target is a function parameter
#      (`local _OC_SECRETS_ENV="$2"`) that never holds a literal path
#      textually in this file -- the caller supplies it.
#      A plain `secret` (case-insensitive) substring match was tried and
#      REJECTED: it also fires on unrelated OAuth-style names
#      (CLIENT_SECRET_VAR, client_secret) and on directory-scoped names
#      whose contents are a DIFFERENT file
#      (platform/mac/power-resilience/lib-power-resilience.sh's
#      PR_SECRETS_DIR, which holds per-tunnel `*.token` files, not
#      secrets/.env) -- both caused false triggers on files the ORIGINAL
#      mention-based trigger never touched at all.
#   2. VALUE trace -- an assignment elsewhere in the file whose RHS
#      textually contains a secrets/.env (or secrets.env) path literal,
#      with a few passes of transitive closure (a var assigned from
#      another already-known secret var). Needed for arbitrarily-named
#      variables that still hold a literal secrets path in this file (this
#      repo doesn't currently have a case reachable outside a heredoc, but
#      the mechanism is real and independently verified against a
#      synthetic fixture -- see PR description proof #1/#2).
#
# KNOWN LIMITATIONS (same "grep-replacement, not a shell interpreter"
# spirit as strip_non_executable() above):
#   - Same-logical-line heuristic. A write construct whose target was
#     assigned the secrets path on an EARLIER, disjoint line through a
#     generically-named local (not caught by either mechanism above) will
#     be missed. Audited against the full 98-file secrets/.env corpus on
#     2026-07-30: every real writer found (shared-utils/
#     provision-persona-index.sh, 31-upgraded-memory-system/scripts/
#     activate-memory-stack.sh, 58-podcast-production-engine/scripts/
#     {revoke,provision}-podcast-client.sh) names or aliases the secrets
#     file on the same logical line as its write construct, so this holds
#     for the audited corpus without a miss.
#   - Box-provisioning logic embedded in a heredoc payload that is shipped
#     to and executed on a REMOTE box (e.g. scripts/fleet-roll/
#     podbean-publish-provision-roll.sh's `emit_box_script`) is invisible
#     here, same as it already is to has_real_chmod_600() above -- heredoc
#     bodies are blanked by strip_non_executable() for both checks
#     consistently (a write and its chmod inside the same heredoc are
#     either both visible or both inert; they are never compared
#     inconsistently). Auditing generated remote-script text is out of
#     scope for a local pre-commit grep-replacement.
#   - `>`/`>>` only counts as a real redirect when immediately preceded by
#     a shell word-boundary (start-of-line, whitespace, or one of
#     `;&|(){}`) -- this deliberately excludes a digit-prefixed fd
#     redirect (`2>/dev/null`), the `->` prose arrow used throughout this
#     repo's log/pass/fail messages, and the `<value>` placeholder idiom
#     (e.g. `fix "add KEY=<value> to $SECRETS_ENV"`) where the closing `>`
#     is glued to a word character. A compact, no-space redirect
#     (`cmd>file`) would be missed; none was found in this repo's corpus.
# ---------------------------------------------------------------------------

SECRETS_PATH_RE = re.compile(r"secrets/\.env|secrets\.env")

SECRET_VAR_NAME_RE = re.compile(
    r"SECRETS_ENV|OC_SECRETS|_PF_SECRETS_STORE|\bSECRETS\b"
)

# NAME=VALUE scanner over the whole cleaned file text (not anchored to line
# start), so it also catches multiple pairs on one line -- e.g. the
# `export SECRETS_ENV="..." WORKSPACE="..." SKILLS_DIR_DEFAULT="..."`
# boilerplate repeated across ~20 qc-*.sh files in this repo.
#
# The quoted-value alternatives account for an asymmetry in
# strip_non_executable() above: it blanks an OPENING quote mark to a
# single space but leaves the CLOSING quote mark as a literal `"`/`'`.
# A real bash assignment never has whitespace between `=` and its value,
# so a space immediately after `=` in the cleaned text unambiguously means
# "this was a quote" -- safe to match on.
ASSIGN_RE = re.compile(
    r"(?:^|[\s;&|(){}])"
    r"([A-Za-z_][A-Za-z0-9_]*)="
    r"("
    r' (?:[^"\\]|\\.)*"'   # was "..."  (opening blanked to space, closing literal)
    r"| [^']*'"             # was '...'  (opening blanked to space, closing literal)
    r"|[^\s;&|)}]*"         # bare unquoted token
    r")"
)

# A `>`/`>>` only counts as a real shell redirect if the character right
# before it is a genuine shell word-boundary (start-of-line, whitespace, or
# one of `;&|(){}`) -- see the KNOWN LIMITATIONS note above for why.
_BOUNDARY = r"(?:^|(?<=[\s;&|(){}]))"
WRITE_OP_RE = re.compile(
    _BOUNDARY + r">{1,2}(?!\s*&\d)"
    r"|\btee\b"
    r"|\btouch\b"
    r"|\bcp\b"
    r"|\bmv\b"
    r"|\bsed\b[^\n]*(-i\b|--in-place)"
)


def _var_ref_pattern(name: str) -> "re.Pattern":
    return re.compile(r"\$\{?" + re.escape(name) + r"\b")


def find_secret_vars(cleaned_text: str) -> set:
    """Discover the set of variable names that hold (or alias) a secrets
    file path in this cleaned file text. See the module-level comment
    above for the two discovery mechanisms and why both are needed."""
    names = set()
    for m in ASSIGN_RE.finditer(cleaned_text):
        name = m.group(1)
        if SECRET_VAR_NAME_RE.search(name):
            names.add(name)
    if re.search(r"\bSECRETS_ENV_FILE\b", cleaned_text):
        names.add("SECRETS_ENV_FILE")

    for _ in range(4):
        changed = False
        for m in ASSIGN_RE.finditer(cleaned_text):
            name, value = m.group(1), m.group(2)
            if name in names:
                continue
            if SECRETS_PATH_RE.search(value):
                names.add(name)
                changed = True
                continue
            for known in list(names):
                if re.search(r"\$\{?" + re.escape(known) + r"\b", value):
                    names.add(name)
                    changed = True
                    break
        if not changed:
            break
    return names


def _join_continuations(text: str):
    """Join trailing-backslash line continuations into one logical line,
    so a write operator split across a continued line is still seen on
    the same logical line as an earlier secrets-name reference."""
    raw_lines = text.split("\n")
    logical = []
    buf = ""
    for line in raw_lines:
        if buf:
            line = buf + " " + line.lstrip()
            buf = ""
        if line.endswith("\\") and not line.endswith("\\\\"):
            buf = line[:-1]
            continue
        logical.append(line)
    if buf:
        logical.append(buf)
    return logical


def is_secrets_env_write_reference(path: str) -> bool:
    with open(path, "r", errors="replace") as fh:
        text = fh.read()
    cleaned = strip_non_executable(text)
    secret_vars = find_secret_vars(cleaned)
    var_res = [_var_ref_pattern(n) for n in secret_vars]
    for line in _join_continuations(cleaned):
        if not WRITE_OP_RE.search(line):
            continue
        if SECRETS_PATH_RE.search(line):
            return True
        for vr in var_res:
            if vr.search(line):
                return True
    return False


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--is-write-reference":
        args = args[1:]
        if len(args) != 1:
            print(
                "usage: qc-assert-chmod600-real.py --is-write-reference <file>",
                file=sys.stderr,
            )
            sys.exit(2)
        sys.exit(0 if is_secrets_env_write_reference(args[0]) else 1)

    if len(args) != 1:
        print("usage: qc-assert-chmod600-real.py <file>", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if has_real_chmod_600(args[0]) else 1)
