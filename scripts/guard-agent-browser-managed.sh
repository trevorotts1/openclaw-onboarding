#!/usr/bin/env bash
# guard-agent-browser-managed.sh — v13.8.10
#
# CI / QC GUARD for the SINGLETON POOLED BROWSER doctrine (Skill 06).
#
# THE DOCTRINE (the canonical sentinel that MUST be present in the docs):
#   SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
#   reaper backstop.
#
# WHY (verified live damage, operator box, 2026-06-23): 22 orphan
#   ~/.agent-browser/*.engine (357M, ZERO .pid) because the 06 tools used a fresh
#   per-iteration session name and had ZERO teardown. The fix is a single
#   mandatory gateway (browser_manager.sh / .py). This guard FAILS the build if a
#   regression slips past it — so the leak can never silently return.
#
# WHAT THIS GUARD ENFORCES (fails the build / QC on any violation):
#   (1) MANAGED-ONLY — no tracked *.sh / *.py UNDER 06-ghl-install-pages/
#       (EXCLUDING browser_manager.sh itself + the reaper) may invoke
#       `agent-browser ... (open|eval|click|fill|type|snapshot|wait|find)` or a
#       bare `AB --session` UNLESS it is routed through the manager (the bm_*/AB()
#       helpers inside browser_manager.sh, or browser_cmd/agent_browser_eval_cmd
#       in the python emitters). Comments / docstrings / quoted echo prose are
#       stripped first so doc text never false-positives.
#       (1c) Python argv-LIST form — an AST pass ALSO catches the
#       `subprocess.run(["agent-browser", ...])` / Popen / os.exec* / os.system
#       spawn form. strip_python erases the string token, so the shell-string
#       regex above is blind to it; the AST pass flags `agent-browser` as a spawn
#       argv element (NOT docstrings, `argv[0] == "agent-browser"` assertions, or
#       a `path / "agent-browser"`), closing the documented evasion residual.
#   (2) GATEWAY INTEGRITY — browser_manager.sh MUST keep its
#       `trap _bm_teardown EXIT` AND the lock acquire AND the close / state clear
#       teardown (teardown can never be silently removed).
#   (3) NO PER-RUN SESSION NAMES — no 06-* doc may reintroduce a unique
#       per-iteration session pattern (e.g. `--session ...-diag`,
#       `--session ghl-...-$(date`, `--session ...-clone`).
#   (4) DOCTRINE SENTINEL — present verbatim in SKILL.md /
#       ghl-browser-builder-full.md / CORE_UPDATES.md.
#   (5) HEADLESS-ONLY (D6) — the backup/Playwright path must NEVER open a visible
#       window. Fails on `headless = False|0` or a bare Playwright `launch(`
#       (NOT launch_persistent_context / launchPersistentContext) in any tracked
#       *.py/*.sh under 06, AND inside any CODE-LANGUAGE fence (```python /
#       ```bash …) in any 06 *.md. Bare ``` prose blocks (e.g. CORE_UPDATES.md
#       copy-paste content that legitimately says "NEVER launch()") are NOT code
#       and are skipped — closing the doc-prose-only enforcement gap without false
#       positives.
#
# Modeled on: scripts/guard-ghl-token-only.sh (same arg parse / comment stripping
#   / self-exclusion / exit conventions).
#
# Exit codes:
#   0  — PASS
#   1  — FAIL (prints file:line)
#   2  — usage / environment error
#
# Usage:
#   bash scripts/guard-agent-browser-managed.sh
#   bash scripts/guard-agent-browser-managed.sh --repo-root /path/to/repo

set -uo pipefail

# Version marker (kept in sync by scripts/bump-version.sh):
GUARD_AGENT_BROWSER_MANAGED_VERSION="v19.9.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,46p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$REPO_ROOT/06-ghl-install-pages"
TOOLS_DIR="$SKILL_DIR/tools"
MANAGER_SH="$TOOLS_DIR/browser_manager.sh"
MANAGER_PY="$TOOLS_DIR/browser_manager.py"
REAPER_SH="$REPO_ROOT/scripts/agent-browser-reaper.sh"

# ── The canonical doctrine sentinel (MUST appear verbatim) ────────────────────
SENTINEL='SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop'

REQUIRED_SENTINEL_DOCS=(
  "$SKILL_DIR/SKILL.md"
  "$SKILL_DIR/ghl-browser-builder-full.md"
  "$SKILL_DIR/CORE_UPDATES.md"
)

# ── Files that are EXEMPT from the managed-only scan (they ARE the gateway) ────
# Match by absolute path.
is_exempt() {
  case "$1" in
    "$MANAGER_SH"|"$MANAGER_PY"|"$REAPER_SH") return 0 ;;
    *) return 1 ;;
  esac
}

red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

FAILS=0

echo ""
echo "═══ guard-agent-browser-managed — SINGLETON POOLED BROWSER doctrine (Skill 06) ═══"
echo ""

# ── 0. The gateway files must exist ───────────────────────────────────────────
for f in "$MANAGER_SH" "$MANAGER_PY" "$REAPER_SH"; do
  if [ ! -f "$f" ]; then
    red "  ✗ FAIL — gateway/reaper file missing: ${f#$REPO_ROOT/}"
    FAILS=$((FAILS + 1))
  fi
done
if [ "$FAILS" -gt 0 ]; then
  echo ""; red "guard-agent-browser-managed FAILED — gateway not found."; exit 1
fi

# ── Comment / string strippers (same approach as guard-ghl-token-only.sh) ─────
strip_python() {
  python3 - "$1" <<'PY'
import io, sys, tokenize
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    src = fh.read()
lines = src.splitlines()
n = len(lines)
grid = [list(line) for line in lines]
def erase(start, end):
    (sr, sc), (er, ec) = start, end
    for r in range(sr, er + 1):
        idx = r - 1
        if idx < 0 or idx >= n:
            continue
        row = grid[idx]
        c0 = sc if r == sr else 0
        c1 = ec if r == er else len(row)
        for c in range(c0, min(c1, len(row))):
            row[c] = " "
# Erase comments + ALL string content. On Python 3.12+ an f-string is NOT a single
# STRING token — it is FSTRING_START/FSTRING_MIDDLE/FSTRING_END, so the literal
# TEXT of an f-string (e.g. an f"headless=False …" assert message) would otherwise
# survive stripping and false-positive. Erase the f-string text tokens too; the
# replacement-field `{expr}` tokens are NAME/OP and stay (they are real code).
_ERASE = {tokenize.COMMENT, tokenize.STRING}
for _name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
    _t = getattr(tokenize, _name, None)
    if _t is not None:
        _ERASE.add(_t)
try:
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in _ERASE:
            erase(tok.start, tok.end)
except (tokenize.TokenError, IndentationError, SyntaxError):
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE-PYTHON agent-browser open\n")
    sys.exit(0)
for i in range(n):
    sys.stdout.write("%d:%s\n" % (i + 1, "".join(grid[i])))
PY
}

# ── Python argv-LIST spawn scanner (closes the documented residual) ───────────
# strip_python ERASES every STRING token, so the shell-string regex in
# scan_managed cannot see `agent-browser` when it lives INSIDE a Python list/
# tuple passed to subprocess — e.g.
#     subprocess.run(["agent-browser", "--session", s, "open", url])
#     subprocess.Popen(("agent-browser", ...))
#     os.execvp("agent-browser", ["agent-browser", ...])
# That argv-list form is a RAW spawn outside browser_manager and used to slip the
# guard. This AST pass catches it precisely. It flags a violation ONLY when an
# `agent-browser` string literal is an ARGUMENT (positional or inside a list/
# tuple argument) of a process-SPAWN primitive — so it does NOT false-positive on
# docstrings, `argv[0] == "agent-browser"` test assertions, the emitter's
# returned strings, or a Path like `bindir / "agent-browser"`.
# Prints `line:colN raw agent-browser spawn ...` for each hit (0 hits => silent).
scan_python_argv_spawn() {
  python3 - "$1" <<'PY'
import ast, sys
path = sys.argv[1]
try:
    tree = ast.parse(open(path, encoding="utf-8").read())
except (SyntaxError, ValueError):
    # An unparseable .py is itself suspicious — fail loud so it cannot hide a spawn.
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE-PYTHON argv-spawn scan\n")
    sys.exit(0)

# Process-spawn primitives whose argv may launch the agent-browser BINARY.
SPAWN = {
    "run", "call", "check_call", "check_output", "Popen", "getoutput", "getstatusoutput",
    "system",
    "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe",
    "spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe",
}

def _is_ab_literal(node):
    """A str constant that IS the agent-browser binary token (bare or as the
    head of a command string), not merely some prose containing the word."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        v = node.value
        return v == "agent-browser" or v.startswith("agent-browser ") or v.startswith("agent-browser\t")
    return False

def _call_name(func):
    # Return the (dotted) callable name's terminal attribute/name, e.g.
    # subprocess.run -> "run", os.execvp -> "execvp", run -> "run".
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None

hits = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    name = _call_name(node.func)
    if name not in SPAWN:
        continue
    # Inspect each positional arg: the binary may be the first string arg
    # (os.system("agent-browser ..."), execvp("agent-browser", ...)) OR an
    # element of a list/tuple argv ([... "agent-browser" ...]).
    for arg in node.args:
        if _is_ab_literal(arg):
            hits.append((node.lineno, getattr(node, "col_offset", 0)))
            break
        if isinstance(arg, (ast.List, ast.Tuple)):
            if any(_is_ab_literal(el) for el in arg.elts):
                hits.append((node.lineno, getattr(node, "col_offset", 0)))
                break

for ln, col in hits:
    sys.stdout.write("%d: raw agent-browser spawn (argv-list, col %d) outside browser_manager\n" % (ln, col))
PY
}

strip_bash() {
  # Blank full-line + inline # comments. Heuristic (does not parse heredocs),
  # which is fine: the inject script's only raw agent-browser reference is the
  # final NEXT-hint, which is a quoted echo string (excluded below).
  awk '
  {
    line = $0
    if (line ~ /^[[:space:]]*#/) { print NR ":"; next }
    sub(/[[:space:]]#.*$/, "", line)
    print NR ":" line
  }' "$1"
}

# A line is a quoted-echo (documentation prose), not an executable call, if its
# code content begins with echo/printf — we skip those (they are NEXT hints).
is_echo_prose() {
  printf '%s' "$1" | grep -Eq '^[[:space:]]*(echo|printf)\b'
}

# BANNED form A — the literal agent-browser BINARY driving an action verb. This
# is ALWAYS a raw launch unless it is the sanctioned routing (ALLOW_RE) or a
# quoted echo. Banned in EVERY non-gateway file.
BANNED_RAW_RE='agent-browser([[:space:]]+--headed[[:space:]]+(false|true))?([[:space:]]+--session[[:space:]]+[^[:space:]]+)?[[:space:]]+(open|eval|click|fill|type|snapshot|wait|find)\b'

# BANNED form B — a bare `AB --session` wrapper CALL. This is the managed wrapper
# ONLY when the file SOURCES browser_manager.sh (which defines the lock-asserting
# AB()). In a file that does NOT source the manager, an `AB --session` is an
# unmanaged wrapper of unknown provenance → VIOLATION.
BANNED_AB_RE='(^|[[:space:]])AB[[:space:]]+--session\b'

# ALLOW: lines that ARE the legitimate managed routing / definition.
#   - bash: the `AB()` definition, `bm_` functions, the browser_manager source.
#   - python: browser_cmd / agent_browser_eval_cmd / the headless prefix.
ALLOW_RE='(AB\(\)|bm_|browser_manager|browser_cmd|agent_browser_eval_cmd|AGENT_BROWSER_HEADLESS_PREFIX|emit_teardown_step)'

scan_managed() {
  local file="$1" stripper="$2"
  local rel="${file#$REPO_ROOT/}"
  local hits=0 codeln lineno code
  # File-level fact: does this file SOURCE the manager? If so, a bare
  # `AB --session` IS the sanctioned lock-asserting wrapper (form B is allowed).
  local sources_mgr=0
  if grep -Eq '^[[:space:]]*(source|\.)[[:space:]].*browser_manager\.sh' "$file" 2>/dev/null; then
    sources_mgr=1
  fi
  while IFS= read -r codeln; do
    lineno="${codeln%%:*}"
    code="${codeln#*:}"
    [ -z "$code" ] && continue
    # Always-banned: the literal binary driving a verb (unless routed / echo).
    if printf '%s' "$code" | grep -Eq "$BANNED_RAW_RE"; then
      if printf '%s' "$code" | grep -Eq "$ALLOW_RE"; then : ; \
      elif is_echo_prose "$code"; then : ; \
      else
        red "  ✗ FAIL — $rel:$lineno raw agent-browser launch outside browser_manager.sh:"
        echo "          $(printf '%s' "$code" | sed 's/^[[:space:]]*//' | cut -c1-120)"
        hits=$((hits + 1))
        continue
      fi
    fi
    # Conditionally-banned: `AB --session` only when the file does NOT source the
    # manager (then the wrapper provenance is unknown / unmanaged).
    if [ "$sources_mgr" = "0" ] && printf '%s' "$code" | grep -Eq "$BANNED_AB_RE"; then
      if printf '%s' "$code" | grep -Eq "$ALLOW_RE"; then continue; fi
      if is_echo_prose "$code"; then continue; fi
      red "  ✗ FAIL — $rel:$lineno bare 'AB --session' but file does not source browser_manager.sh:"
      echo "          $(printf '%s' "$code" | sed 's/^[[:space:]]*//' | cut -c1-120)"
      hits=$((hits + 1))
    fi
  done < <("$stripper" "$file")
  return "$hits"
}

# ── 1. MANAGED-ONLY scan across tracked 06 *.sh / *.py (excluding the gateway) ─
echo "── (1) managed-only: no raw agent-browser launch outside the gateway ──"
managed_fail=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  is_exempt "$f" && continue
  case "$f" in
    *.py)
      scan_managed "$f" strip_python || managed_fail=$((managed_fail + $?))
      # Form C — AST pass that catches the argv-LIST spawn form the shell-string
      # regex cannot see (strip_python erases the string token). A raw
      # subprocess.run(["agent-browser", ...]) outside the manager fails here.
      rel="${f#$REPO_ROOT/}"
      while IFS= read -r m; do
        [ -z "$m" ] && continue
        red "  ✗ FAIL — $rel:${m%%:*} ${m#*: }"
        managed_fail=$((managed_fail + 1))
      done < <(scan_python_argv_spawn "$f")
      ;;
    *.sh) scan_managed "$f" strip_bash   || managed_fail=$((managed_fail + $?)) ;;
  esac
done < <(find "$SKILL_DIR" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null)
if [ "$managed_fail" -eq 0 ]; then
  green "  ✓ PASS — all agent-browser calls under 06 route through the manager."
else
  FAILS=$((FAILS + managed_fail))
fi

# ── 2. GATEWAY INTEGRITY — teardown trap + lock + close/state-clear present ───
echo ""
echo "── (2) gateway integrity: teardown trap + lock + close/state-clear ──"
gi_fail=0
check_present() {
  local pat="$1" label="$2"
  if grep -Eq "$pat" "$MANAGER_SH"; then
    green "  ✓ PASS — $label present in browser_manager.sh"
  else
    red "  ✗ FAIL — $label MISSING from browser_manager.sh (teardown/lock can never be silently removed)"
    gi_fail=$((gi_fail + 1))
  fi
}
check_present 'trap[[:space:]]+_bm_teardown[[:space:]]+EXIT' "trap _bm_teardown EXIT"
check_present '(flock|mkdir[[:space:]]+"\$LOCKDIR/ab\.lock\.d")' "lock acquire (flock or atomic-mkdir)"
check_present 'close[[:space:]]+--session' "close --session teardown"
check_present 'state[[:space:]]+clear' "state clear teardown"
check_present 'bm_breaker_check' "circuit-breaker (bm_breaker_check)"
FAILS=$((FAILS + gi_fail))

# ── 3. NO PER-RUN SESSION NAMES in 06 docs ────────────────────────────────────
echo ""
echo "── (3) no per-iteration session names reintroduced in 06 docs ──"
perrun_fail=0
# These regexes are the exact multipliers verified live (-diag/-clone) + a
# date-stamped session. Match against doc text (md).
PERRUN_RES=(
  '--session[[:space:]]+[^[:space:]]*-diag'
  '--session[[:space:]]+ghl-[^[:space:]]*-\$\(date'
  '--session[[:space:]]+[^[:space:]]*-clone'
)
while IFS= read -r doc; do
  [ -f "$doc" ] || continue
  for re in "${PERRUN_RES[@]}"; do
    # `-e -- "$re"` so a pattern that begins with `--` (e.g. `--session…`) is
    # never mistaken for a grep option (portable across BSD/GNU/ugrep).
    if grep -nE -e "$re" "$doc" >/dev/null 2>&1; then
      while IFS= read -r m; do
        red "  ✗ FAIL — ${doc#$REPO_ROOT/}:${m%%:*} reintroduces a per-iteration session name"
        perrun_fail=$((perrun_fail + 1))
      done < <(grep -nE -e "$re" "$doc")
    fi
  done
done < <(find "$SKILL_DIR" -type f -name '*.md' 2>/dev/null)
if [ "$perrun_fail" -eq 0 ]; then
  green "  ✓ PASS — no per-iteration session pattern in any 06 doc."
else
  FAILS=$((FAILS + perrun_fail))
fi

# ── 4. DOCTRINE SENTINEL present in every required doc ────────────────────────
echo ""
echo "── (4) doctrine sentinel present verbatim ──"
for doc in "${REQUIRED_SENTINEL_DOCS[@]}"; do
  rel="${doc#$REPO_ROOT/}"
  if [ ! -f "$doc" ]; then
    red "  ✗ FAIL — required doc missing: $rel"
    FAILS=$((FAILS + 1)); continue
  fi
  if grep -Fq "$SENTINEL" "$doc"; then
    green "  ✓ PASS — sentinel present in $rel"
  else
    red "  ✗ FAIL — doctrine sentinel MISSING from $rel"
    echo "          expected verbatim: $SENTINEL"
    FAILS=$((FAILS + 1))
  fi
done

# ── 5. HEADLESS-ONLY (D6) — no headless=False / bare Playwright launch() ───────
# The backup/Playwright fallback path must NEVER open a visible window. Until now
# this was DOC-PROSE only (the guard only knew the agent-browser binary). This
# section makes a visible-window regression a BUILD FAILURE.
echo ""
echo "── (5) headless-only: no headless=False / bare launch() (D6 — no visible window) ──"
headless_fail=0

# A real headless-off assignment (False or 0), NOT `headless=True`.
HEADLESS_FALSE_RE='headless[[:space:]]*=[[:space:]]*([Ff]alse|0)([^A-Za-z0-9_]|$)'
# A bare Playwright launch(. `(^|[^A-Za-z_])launch\(` matches `chromium.launch(` /
# `.launch(` but NOT `launch_persistent_context(` / `launchPersistentContext(`
# (the char after `launch` there is `_`/`P`, never `(`).
BARE_LAUNCH_RE='(^|[^A-Za-z_])launch\('

# Code-file scan: reuse the stripped-line strippers (comments/strings erased), so
# only REAL code lines are tested (a docstring "no chromium.launch" never trips).
scan_headless_code() {
  local file="$1" stripper="$2"
  local rel="${file#$REPO_ROOT/}"
  local hits=0 codeln lineno code
  while IFS= read -r codeln; do
    lineno="${codeln%%:*}"
    code="${codeln#*:}"
    [ -z "$code" ] && continue
    if printf '%s' "$code" | grep -Eq "$HEADLESS_FALSE_RE"; then
      red "  ✗ FAIL — $rel:$lineno headless=False / headless off (D6 forbids a visible window):"
      echo "          $(printf '%s' "$code" | sed 's/^[[:space:]]*//' | cut -c1-120)"
      hits=$((hits + 1))
    fi
    if printf '%s' "$code" | grep -Eq "$BARE_LAUNCH_RE"; then
      red "  ✗ FAIL — $rel:$lineno bare Playwright launch() (use launch_persistent_context, headless=True):"
      echo "          $(printf '%s' "$code" | sed 's/^[[:space:]]*//' | cut -c1-120)"
      hits=$((hits + 1))
    fi
  done < <("$stripper" "$file")
  return "$hits"
}

while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in
    *.py) scan_headless_code "$f" strip_python || headless_fail=$((headless_fail + $?)) ;;
    *.sh) scan_headless_code "$f" strip_bash   || headless_fail=$((headless_fail + $?)) ;;
  esac
done < <(find "$SKILL_DIR" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null)

# Markdown CODE-FENCE scan (Python is already a guard dependency). Only enters
# fences opened with a code-language tag (```python / ```bash / …); bare ``` prose
# blocks are skipped (they hold copy-paste doctrine that says "NEVER launch()").
while IFS= read -r m; do
  [ -z "$m" ] && continue
  red "  ✗ FAIL — $m"
  headless_fail=$((headless_fail + 1))
done < <(python3 - "$SKILL_DIR" "$REPO_ROOT" <<'PY'
import os, re, sys
root, repo_root = sys.argv[1], sys.argv[2]
HEADLESS_RE = re.compile(r"headless\s*=\s*(False|0)\b")
LAUNCH_RE = re.compile(r"(?<![A-Za-z_])launch\s*\(")
EXCLUDE_RE = re.compile(r"launch_persistent_context|launchPersistentContext")
CODE_LANGS = ("python", "py", "python3", "bash", "sh", "shell")
FENCE_RE = re.compile(r"(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+-]*)")
def scan(path, rel):
    in_fence = False; fch = None; out = []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for i, line in enumerate(fh, 1):
            m = FENCE_RE.match(line.lstrip())
            if m:
                ch = m.group(1)[0]; lang = (m.group(2) or "").lower()
                if not in_fence:
                    if lang in CODE_LANGS:
                        in_fence = True; fch = ch
                elif ch == fch and lang == "":
                    in_fence = False; fch = None
                continue
            if not in_fence:
                continue
            if HEADLESS_RE.search(line):
                out.append("%s:%d headless=False inside a code fence (D6 forbids a visible window): %s"
                           % (rel, i, line.strip()[:100]))
            for mm in LAUNCH_RE.finditer(line):
                seg = line[max(0, mm.start()-30):mm.end()+10]
                if EXCLUDE_RE.search(seg):
                    continue
                out.append("%s:%d bare Playwright launch() inside a code fence (use launch_persistent_context, headless=True): %s"
                           % (rel, i, line.strip()[:100]))
    return out
for dirpath, _, files in os.walk(root):
    for fn in sorted(files):
        if fn.endswith(".md"):
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, repo_root)
            for h in scan(p, rel):
                sys.stdout.write(h + "\n")
PY
)
if [ "$headless_fail" -eq 0 ]; then
  green "  ✓ PASS — no headless=False / bare launch() in 06 code or code-fenced docs."
else
  FAILS=$((FAILS + headless_fail))
fi

echo ""
if [ "$FAILS" -eq 0 ]; then
  green "guard-agent-browser-managed PASS — singleton gateway intact (managed-only, teardown+lock+breaker present, no per-run names, sentinel present, headless-only enforced)."
  exit 0
else
  red "guard-agent-browser-managed FAILED — $FAILS violation(s)."
  echo ""
  echo "REMEDY:"
  echo "  - Route EVERY agent-browser call under 06 through tools/browser_manager.sh"
  echo "    (bm_ensure + the lock-asserting AB()) or, in python, through"
  echo "    ghl_builder.browser_cmd / ghl_rest_canvas.agent_browser_eval_cmd inside"
  echo "    a browser_manager.browser_session() bracket."
  echo "  - Keep browser_manager.sh's trap _bm_teardown EXIT + lock + close +"
  echo "    state clear + circuit-breaker — they can never be removed."
  echo "  - Never invent a per-iteration session name; use the ONE canonical"
  echo "    bm_session_name. Restore the doctrine sentinel to the docs."
  exit 1
fi
