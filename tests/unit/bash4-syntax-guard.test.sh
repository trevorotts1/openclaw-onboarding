#!/usr/bin/env bash
# tests/unit/bash4-syntax-guard.test.sh
# -----------------------------------------------------------------------------
# ISSUE-14 regression lock: every shell script that uses bash-4-only syntax must
# carry the _OC_BASH_REEXEC guard.
#
# THE BUG THIS LOCKS. macOS ships GNU bash 3.2.57 at /bin/bash and will never
# ship a newer one (bash 4 went GPLv3). Associative arrays (`declare -A`),
# `mapfile`/`readarray`, and the case modifiers `${v,,}` / `${v^^}` are all
# bash 4.0+. A `#!/usr/bin/env bash` shebang does NOT save a script either:
# launchd and cron run with a PATH that usually has no Homebrew bin directory,
# so `env bash` resolves straight back to /bin/bash 3.2.
#
# It fails SILENTLY, which is why it survived. Under bash 3.2:
#     declare -A RESULTS   -> "declare: -A: invalid option", rc 2
#     mapfile -t X < <(..) -> "mapfile: command not found", rc 127
#     "${s,,}"             -> "bad substitution", rc 1
# and in universal-sops/video-production/scripts/run_all_probes.sh the broken
# `declare -A` still let the script exit 0 -- a receipt written from a scalar
# that every caller read as success.
#
# WHAT THIS TEST PROVES.
#   T1  the scanner is not vacuous: an UNGUARDED bash-4 fixture is FLAGGED
#   T2  the scanner is not a red light: the SAME fixture WITH the guard PASSES
#   T3  no false positives: bash-4 syntax in a COMMENT is never flagged
#       (most of this repo's scripts carry "no `declare -A` here" notes, and
#       flagging those would make the guard useless noise)
#   T4  no false positives: bash-4 syntax inside a HEREDOC body is not flagged
#       (deliberate bad fixtures live there, e.g. the p304 conformance probe)
#   T5  the real repo is clean: every *.sh using bash-4 syntax in live code
#       carries the guard
#
# Hermetic: its own mktemp -d sandbox for the fixtures, read-only over the
# checkout. No ~/.openclaw, no network, no fleet box.
# Itself bash 3.2-safe: no associative arrays, no mapfile, no case modifiers.
# Exit 0 = all pass.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCANNER=""

PASS=0
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
hdr() { printf '\n== %s ==\n' "$1"; }

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# -----------------------------------------------------------------------------
# The scanner. Written out to the sandbox so both the fixture self-tests and the
# real repo sweep run the SAME code -- a guard whose self-test exercises a
# different implementation than the real check proves nothing.
#
# It strips comments and quoted-string bodies (keeping ${...} expansions inside
# double quotes, since that is where ${v,,} lives) and skips heredoc bodies,
# then matches bash-4-only constructs against what is left.
# -----------------------------------------------------------------------------
SCANNER="$SANDBOX/scan_bash4.py"
cat > "$SCANNER" <<'PYEOF'
import os
import re
import sys

PATTERNS = [
    ("declare -A", re.compile(r"\bdeclare\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*A[A-Za-z]*\b")),
    ("typeset -A", re.compile(r"\btypeset\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*A[A-Za-z]*\b")),
    ("mapfile", re.compile(r"(?<![\w./-])mapfile(?![\w-])")),
    ("readarray", re.compile(r"(?<![\w./-])readarray(?![\w-])")),
    ("${v,,}", re.compile(r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?,")),
    ("${v^^}", re.compile(r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\^")),
    ("[[ -v", re.compile(r"\[\[\s+(?:!\s+)?-v\s")),
    ("&>>", re.compile(r"&>>")),
    ("local -n", re.compile(r"\blocal\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*n[A-Za-z]*\s")),
    ("declare -n", re.compile(r"\bdeclare\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*n[A-Za-z]*\s")),
]

GUARD_TOKEN = "_OC_BASH_REEXEC"
HEREDOC_OPEN = re.compile(r"<<-?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1")


def split_code(line):
    """Return (code_with_strings_blanked, index_where_a_comment_started_or_len)."""
    out = []
    i = 0
    n = len(line)
    quote = None
    while i < n:
        c = line[i]
        if quote is None:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == "#" and (not out or out[-1] in " \t;|&(){}"):
                return "".join(out), i
            if c == '"' or c == "'":
                quote = c
                out.append(" ")
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if quote == "'":
            if c == "'":
                quote = None
            out.append(" ")
            i += 1
            continue
        # inside a double quote: keep ${...}, blank everything else
        if c == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if c == '"':
            quote = None
            out.append(" ")
            i += 1
            continue
        if c == "$" and i + 1 < n and line[i + 1] == "{":
            j = line.find("}", i)
            if j == -1:
                out.append(" ")
                i += 1
                continue
            out.append(line[i:j + 1])
            i = j + 1
            continue
        out.append(" ")
        i += 1
    return "".join(out), n


def scan_file(path):
    """Return a list of (lineno, construct, raw_line) for live bash-4 code."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return []
    hits = []
    heredoc_tag = None
    for idx, raw in enumerate(lines, 1):
        if heredoc_tag is not None:
            if raw.strip() == heredoc_tag:
                heredoc_tag = None
            continue
        code, comment_at = split_code(raw)
        for name, rx in PATTERNS:
            if rx.search(code):
                hits.append((idx, name, raw.strip()[:120]))
                break
        opener = HEREDOC_OPEN.search(raw[:comment_at])
        if opener and "<<<" not in raw[:comment_at]:
            heredoc_tag = opener.group(2)
    return hits


def main():
    root = sys.argv[1]
    verbose = "--verbose" in sys.argv[2:]
    violations = []
    scanned = 0
    using_bash4 = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in sorted(filenames):
            if not fn.endswith(".sh"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            scanned += 1
            hits = scan_file(path)
            if not hits:
                continue
            using_bash4 += 1
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                text = ""
            if GUARD_TOKEN not in text:
                violations.append((rel, hits))
            elif verbose:
                print("  guarded: %s (%s)" % (rel, ", ".join(h[1] for h in hits)))

    print("scanned %d .sh files; %d use bash-4 syntax in live code" % (scanned, using_bash4))
    if violations:
        print("")
        print("UNGUARDED bash-4 syntax (add the _OC_BASH_REEXEC re-exec guard after the shebang):")
        for rel, hits in violations:
            for lineno, name, snippet in hits:
                print("  %s:%d  [%s]  %s" % (rel, lineno, name, snippet))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF

python3 -m py_compile "$SCANNER" || { echo "FATAL: the scanner itself does not compile"; exit 2; }

# The exact guard every flagged script must carry.
GUARD_TEXT='# bash >= 4 required (associative arrays / mapfile / case modifiers); macOS ships 3.2 at /bin/bash.
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ] && [ -z "${_OC_BASH_REEXEC:-}" ]; then
  for _oc_b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    [ -x "$_oc_b" ] && _OC_BASH_REEXEC=1 exec "$_oc_b" "$0" "$@"
  done
  echo "FATAL: bash >= 4 required (macOS ships 3.2): brew install bash" >&2; exit 3
fi'

# -----------------------------------------------------------------------------
hdr "T1 -- an UNGUARDED bash-4 script is FLAGGED (anti-vacuity)"
FIX1="$SANDBOX/t1"; mkdir -p "$FIX1"
cat > "$FIX1/unguarded.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
declare -A TALLY
TALLY[one]=1
SH
if python3 "$SCANNER" "$FIX1" > "$SANDBOX/t1.out" 2>&1; then
  bad "T1: scanner PASSED an unguarded 'declare -A' script -- the guard is vacuous"
  sed 's/^/      /' "$SANDBOX/t1.out"
else
  if grep -q "unguarded.sh:3" "$SANDBOX/t1.out"; then
    ok "T1: unguarded 'declare -A' flagged at the right line"
  else
    bad "T1: flagged, but not at unguarded.sh:3"
    sed 's/^/      /' "$SANDBOX/t1.out"
  fi
fi

# -----------------------------------------------------------------------------
hdr "T2 -- the SAME script WITH the guard PASSES (anti-red-light)"
FIX2="$SANDBOX/t2"; mkdir -p "$FIX2"
{
  echo '#!/usr/bin/env bash'
  printf '%s\n' "$GUARD_TEXT"
  echo 'set -euo pipefail'
  echo 'declare -A TALLY'
  echo 'TALLY[one]=1'
} > "$FIX2/guarded.sh"
if python3 "$SCANNER" "$FIX2" > "$SANDBOX/t2.out" 2>&1; then
  ok "T2: the guarded twin passes"
else
  bad "T2: FALSE POSITIVE -- the guarded twin was still flagged"
  sed 's/^/      /' "$SANDBOX/t2.out"
fi

# -----------------------------------------------------------------------------
hdr "T3 -- bash-4 syntax in a COMMENT is never flagged"
FIX3="$SANDBOX/t3"; mkdir -p "$FIX3"
cat > "$FIX3/commented.sh" <<'SH'
#!/usr/bin/env bash
# PORTABILITY: bash 3.2 safe -- no declare -A, no mapfile, no ${var,,} here.
#   A prior version used `mapfile -t x` and died on stock macOS bash.
set -euo pipefail
echo "hello"   # no readarray either
SH
if python3 "$SCANNER" "$FIX3" > "$SANDBOX/t3.out" 2>&1; then
  ok "T3: portability notes in comments are not flagged"
else
  bad "T3: FALSE POSITIVE -- a comment mentioning bash-4 syntax was flagged"
  sed 's/^/      /' "$SANDBOX/t3.out"
fi

# -----------------------------------------------------------------------------
hdr "T4 -- bash-4 syntax inside a HEREDOC body is not flagged"
FIX4="$SANDBOX/t4"; mkdir -p "$FIX4"
cat > "$FIX4/heredoc.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
make_unsafe_fixture() {
  cat > "$1" <<'INNER'
#!/usr/bin/env bash
mapfile -t page_specs < <(echo)
declare -A FIXTURE
INNER
}
make_unsafe_fixture /dev/null
SH
if python3 "$SCANNER" "$FIX4" > "$SANDBOX/t4.out" 2>&1; then
  ok "T4: deliberate bad fixtures inside heredocs are not flagged"
else
  bad "T4: FALSE POSITIVE -- a heredoc body was treated as live code"
  sed 's/^/      /' "$SANDBOX/t4.out"
fi

# -----------------------------------------------------------------------------
hdr "T5 -- the real repo is clean"
if python3 "$SCANNER" "$REPO_ROOT" > "$SANDBOX/t5.out" 2>&1; then
  ok "T5: $(head -1 "$SANDBOX/t5.out")"
else
  bad "T5: unguarded bash-4 syntax found on this tree"
  sed 's/^/      /' "$SANDBOX/t5.out"
fi

# -----------------------------------------------------------------------------
printf '\n----------------------------------------\n'
printf 'bash4-syntax-guard: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
