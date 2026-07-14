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
# SCAN ROOTS (AUD-20 / FLEET-FIX Area 2 / B.2, broadened 2026-07; P3-08 added a
# FOURTH hand-enumerated root, 2026-07-11, for 44-convert-and-flow-operator/'s
# pre-emptive Tier-4 coverage; P3-04 then widened AGAIN, 2026-07-12, to ALL
# skill directories): checks (1) MANAGED-ONLY and (5) HEADLESS-ONLY below used
# to scan only THREE hand-enumerated roots (06-ghl-install-pages/, 41-build-
# with-ai-playbook/, 03-agent-browser/) — any OTHER skill directory could plant
# an unmanaged `agent-browser open|eval|click|...` spawn and pass this guard
# SILENTLY. P3-08 (step 1) closed that gap for 44-convert-and-flow-operator/
# specifically — its SKILL.md/INSTRUCTIONS.md/qc-built-workflow.sh document a
# "Tier 4 agent-browser" workflow-build backstop that had NO implementation yet
# and NO CI protection, so 44 was added PRE-EMPTIVELY, ahead of any such code
# landing. AUD-25 (P3-04, this pass) generalizes that fix: the roots list is no
# longer a fixed enumeration at all — it is AUTO-DISCOVERED from every
# top-level `NN-*/` skill directory in the repo (see _discover_skill_dirs
# below), so 44-convert-and-flow-operator/ is covered BY CONSTRUCTION (P3-08's
# manual entry is now redundant with, and superseded by, auto-discovery — never
# a second, competing widening racing this one) and so is every future
# numbered skill directory, with zero further guard edits required. Checks
# (2)-(4) (gateway integrity, no per-run session names, doctrine sentinel)
# remain 06-SPECIFIC — that doctrine describes the Skill-06 browser_manager.sh
# gateway only and does not generalize.
#
# AUD-26 (P3-04 fix-loop, 2026-07-12) — PERFORMANCE: auto-discovery (AUD-25)
# widened the scan from 3 roots (~140 files) to every skill dir (~1,022 files).
# The original per-file design was TWO layers of per-file/per-line process
# spawning: (a) python3 (tokenize + AST) invoked per .py file per section, AND
# (b) — the dominant cost, only found by actually timing the widened scan —
# `printf | grep -Eq` invoked PER STRIPPED LINE, per regex, per section, for
# EVERY file. Across ~1,022 files averaging ~150 lines each that is on the
# order of a million short-lived process forks; a real timed run did not
# finish in 7+ minutes. Fixed below: the ENTIRE scan — stripping, the argv-
# spawn AST pass, AND every regex check (BANNED_RAW_RE / ALLOW_RE / echo-
# prose / BANNED_AB_RE / HEADLESS_FALSE_RE / BARE_LAUNCH_RE) for BOTH .py and
# .sh files — now runs inside ONE batched python3 process that emits the
# final, ready-to-print report text (identical wording/format to the old
# per-line bash output) directly to two cache files. Sections (1) and (5)
# below just `cat` those files — zero process spawns per file, per line, or
# per section, regardless of file count.
#
# WHAT THIS GUARD ENFORCES (fails the build / QC on any violation):
#   (1) MANAGED-ONLY — no tracked *.sh / *.py UNDER ANY of the scan roots
#       (EXCLUDING browser_manager.sh itself + the reaper) may invoke
#       `agent-browser ... (open|eval|click|fill|type|snapshot|wait|find)` or a
#       bare `AB --session` UNLESS it is routed through the manager (the bm_*/AB()
#       helpers inside browser_manager.sh, or browser_cmd/agent_browser_eval_cmd
#       in the python emitters). Comments / docstrings / quoted echo prose are
#       stripped first so doc text never false-positives.
#       (1c) Python argv-LIST form — an AST pass ALSO catches the
#       `subprocess.run(["agent-browser", ...])` / Popen / os.exec* / os.system
#       spawn form. Stripping erases the string token, so the shell-string
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
GUARD_AGENT_BROWSER_MANAGED_VERSION="v20.0.21"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,75p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$REPO_ROOT/06-ghl-install-pages"
TOOLS_DIR="$SKILL_DIR/tools"
MANAGER_SH="$TOOLS_DIR/browser_manager.sh"
MANAGER_PY="$TOOLS_DIR/browser_manager.py"
REAPER_SH="$REPO_ROOT/scripts/agent-browser-reaper.sh"

# ── AUD-25 (P3-04) — auto-discover EVERY top-level skill directory ───────────
# Supersedes P3-08's hand-enumerated 4th root (44-convert-and-flow-operator):
# auto-discovery already covers it by construction (it matches `NN-*`), so no
# manual entry for it is needed here.
# A skill directory is any immediate child of REPO_ROOT matching `NN-*` (two
# digits, a dash, then a name) — the repo's own numbering convention (01-… .
# 61-… as of v19.58.0). This replaces the old hand-enumerated 3-root array:
# a hand-enumerated list only ever covers roots someone remembered to add
# (that is exactly how 44-convert-and-flow-operator was missed before P3-08
# named it) — auto-discovery covers every skill directory that exists NOW and
# every one added LATER with zero further edits to this guard. Sorted for
# deterministic scan order / output.
_discover_skill_dirs() {
  find "$REPO_ROOT" -maxdepth 1 -mindepth 1 -type d -name '[0-9][0-9]-*' 2>/dev/null | sort
}

# ── AUD-20 / FLEET-FIX B.2, superseded by AUD-25 above — the roots checks (1)
# MANAGED-ONLY and (5) HEADLESS-ONLY scan. SKILL_DIR itself is still called out
# separately below (it always exists and drives the 06-specific gateway-
# integrity / per-run-session-name / doctrine-sentinel checks (2)-(4)) — that
# doctrine does not generalize to other skills. MANAGED_SCAN_ROOTS is now every
# discovered skill directory, deduplicated against SKILL_DIR.
# NOTE: `while read` (not `mapfile`/`readarray`) — the repo's Mac boxes run the
# system bash (3.2), which has neither builtin (Skill-6 spec §4 Mac-vs-VPS
# matrix, "bash 3.2" row); this loop form is bash-3.2-safe.
MANAGED_SCAN_ROOTS=("$SKILL_DIR")
while IFS= read -r _d; do
  [ -z "$_d" ] && continue
  [ "$_d" = "$SKILL_DIR" ] && continue
  MANAGED_SCAN_ROOTS+=("$_d")
done < <(_discover_skill_dirs)
unset _d

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

# ── AUD-26 — walk every scan root ONCE and run the ENTIRE checks (1)+(5) scan
# (comment/string stripping, the argv-spawn AST pass, AND every regex check)
# for every *.sh/*.py file in a SINGLE batched python3 process. The process
# writes two ready-to-print, ANSI-colored report files (identical wording to
# the old per-line bash output) plus two fail-count files — sections (1) and
# (5) below just `cat`/`read` those, with zero further process spawns.
SCAN_TMP="$(mktemp -d)"
_cleanup_scan_tmp() { rm -rf "$SCAN_TMP" 2>/dev/null; }
trap _cleanup_scan_tmp EXIT

ALL_SCAN_FILES="$SCAN_TMP/all_files.list"
: > "$ALL_SCAN_FILES"
for root in "${MANAGED_SCAN_ROOTS[@]}"; do
  find "$root" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null
done | sort -u > "$ALL_SCAN_FILES"

MANAGED_REPORT="$SCAN_TMP/managed_report.txt"
HEADLESS_REPORT="$SCAN_TMP/headless_report.txt"
MANAGED_FAIL_COUNT="$SCAN_TMP/managed_fail_count"
HEADLESS_FAIL_COUNT="$SCAN_TMP/headless_fail_count"

python3 - "$REPO_ROOT" "$MANAGER_SH" "$MANAGER_PY" "$REAPER_SH" \
         "$MANAGED_REPORT" "$HEADLESS_REPORT" "$MANAGED_FAIL_COUNT" "$HEADLESS_FAIL_COUNT" \
         "$ALL_SCAN_FILES" <<'PY'
import io, os, re, sys, tokenize, ast

# NOTE: the file LIST is passed as an argv PATH, deliberately NOT via a
# `< file` stdin redirect — `python3 - <<'PY' ... PY` already consumes stdin
# to read this script's OWN source (that is what the bare `-` argv means), so
# a `< file` redirect on the same invocation is silently overridden by the
# heredoc (proven: both target fd 0; the heredoc, appearing last, wins) and
# `sys.stdin` inside the running script would read EOF immediately — the scan
# would silently process ZERO files and "pass" every run vacuously. Caught by
# the negative-fixture tests (guard-agent-browser-managed-scan-roots.test.sh /
# -all-skill-dirs.test.sh) going from PASS to FAIL when a planted spawn
# stopped being caught. Fixed by opening the list file directly below.
(repo_root, manager_sh, manager_py, reaper_sh,
 managed_report_path, headless_report_path,
 managed_count_path, headless_count_path, all_scan_files_path) = sys.argv[1:10]

EXEMPT = {manager_sh, manager_py, reaper_sh}

RED = "\033[31m%s\033[0m"

def red(s):
    return RED % s

# ---------------------------------------------------------------------------
# Regexes — IDENTICAL semantics to the original bash BRE/ERE patterns (only
# [[:space:]] -> \s / [^[:space:]] -> \S translated for Python's `re`; every
# other token — alternation, quantifiers, \b word boundaries, character
# classes — is unchanged POSIX-ERE-compatible syntax valid in both engines).
# ---------------------------------------------------------------------------
BANNED_RAW_RE = re.compile(
    r"agent-browser(\s+--headed\s+(false|true))?(\s+--session\s+\S+)?\s+"
    r"(open|eval|click|fill|type|snapshot|wait|find)\b"
)
BANNED_AB_RE = re.compile(r"(^|\s)AB\s+--session\b")
ALLOW_RE = re.compile(
    r"(AB\(\)|bm_|browser_manager|browser_cmd|agent_browser_eval_cmd|"
    r"AGENT_BROWSER_HEADLESS_PREFIX|emit_teardown_step)"
)
ECHO_PROSE_RE = re.compile(r"^\s*(echo|printf)\b")
SOURCES_MGR_RE = re.compile(r"^\s*(source|\.)\s.*browser_manager\.sh", re.MULTILINE)
HEADLESS_FALSE_RE = re.compile(r"headless\s*=\s*([Ff]alse|0)([^A-Za-z0-9_]|$)")
BARE_LAUNCH_RE = re.compile(r"(^|[^A-Za-z_])launch\(")

# Process-spawn primitives whose argv may launch the agent-browser BINARY
# (identical set to the original scan_python_argv_spawn).
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
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def strip_python_source(src):
    """Erase comments + ALL string content (identical algorithm/semantics to
    the original per-file strip_python). On Python 3.12+ an f-string is NOT a
    single STRING token — erase its FSTRING_START/MIDDLE/END text tokens too
    so a literal f-string message can never survive stripping."""
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

    erase_types = {tokenize.COMMENT, tokenize.STRING}
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        t = getattr(tokenize, name, None)
        if t is not None:
            erase_types.add(t)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in erase_types:
                erase(tok.start, tok.end)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return [(0, "GUARD-ERROR-UNPARSEABLE-PYTHON agent-browser open")]
    return [(i + 1, "".join(grid[i])) for i in range(n)]


def strip_bash_source(src):
    """Blank full-line + inline # comments — identical heuristic to the
    original strip_bash (does not parse heredocs; fine per its own note)."""
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        if re.match(r"^\s*#", line):
            out.append((i, ""))
            continue
        code = re.sub(r"\s#.*$", "", line)
        out.append((i, code))
    return out


def argv_spawn_hits(src):
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return [(0, "raw agent-browser spawn — GUARD-ERROR-UNPARSEABLE-PYTHON argv-spawn scan")]
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name not in SPAWN:
            continue
        for arg in node.args:
            if _is_ab_literal(arg):
                hits.append((node.lineno, getattr(node, "col_offset", 0)))
                break
            if isinstance(arg, (ast.List, ast.Tuple)):
                if any(_is_ab_literal(el) for el in arg.elts):
                    hits.append((node.lineno, getattr(node, "col_offset", 0)))
                    break
    return [(ln, "raw agent-browser spawn (argv-list, col %d) outside browser_manager" % col)
            for ln, col in hits]


def snippet(code):
    # Mirrors `sed 's/^[[:space:]]*//' | cut -c1-120` (strip LEADING
    # whitespace only, then take the first 120 characters).
    return code.lstrip()[:120]


managed_out = []
headless_out = []
managed_fail = 0
headless_fail = 0

with open(all_scan_files_path, encoding="utf-8") as _fh:
    all_paths = [ln.rstrip("\n") for ln in _fh]

for path in all_paths:
    if not path:
        continue
    rel = os.path.relpath(path, repo_root)
    is_py = path.endswith(".py")
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        src = ""

    stripped = strip_python_source(src) if is_py else strip_bash_source(src)
    exempt = path in EXEMPT
    sources_mgr = bool(SOURCES_MGR_RE.search(src))

    # ── section (1) MANAGED-ONLY — skipped entirely for exempt gateway files,
    # matching the original `is_exempt "$f" && continue` short-circuit. ──────
    if not exempt:
        for lineno, code in stripped:
            if not code:
                continue
            if BANNED_RAW_RE.search(code):
                if ALLOW_RE.search(code) or ECHO_PROSE_RE.match(code):
                    pass
                else:
                    managed_out.append(red("  ✗ FAIL — %s:%d raw agent-browser launch outside browser_manager.sh:" % (rel, lineno)))
                    managed_out.append("          " + snippet(code))
                    managed_fail += 1
                    continue
            if not sources_mgr and BANNED_AB_RE.search(code):
                if ALLOW_RE.search(code) or ECHO_PROSE_RE.match(code):
                    continue
                managed_out.append(red("  ✗ FAIL — %s:%d bare 'AB --session' but file does not source browser_manager.sh:" % (rel, lineno)))
                managed_out.append("          " + snippet(code))
                managed_fail += 1

        if is_py:
            for lineno, msg in argv_spawn_hits(src):
                managed_out.append(red("  ✗ FAIL — %s:%d %s" % (rel, lineno, msg)))
                managed_fail += 1

    # ── section (5) HEADLESS-ONLY — NOT skipped for exempt files (D6 applies
    # to the gateway itself too), matching the original section (5) exactly. ─
    for lineno, code in stripped:
        if not code:
            continue
        if HEADLESS_FALSE_RE.search(code):
            headless_out.append(red("  ✗ FAIL — %s:%d headless=False / headless off (D6 forbids a visible window):" % (rel, lineno)))
            headless_out.append("          " + snippet(code))
            headless_fail += 1
        if BARE_LAUNCH_RE.search(code):
            headless_out.append(red("  ✗ FAIL — %s:%d bare Playwright launch() (use launch_persistent_context, headless=True):" % (rel, lineno)))
            headless_out.append("          " + snippet(code))
            headless_fail += 1

with open(managed_report_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(managed_out))
    if managed_out:
        fh.write("\n")
with open(headless_report_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(headless_out))
    if headless_out:
        fh.write("\n")
with open(managed_count_path, "w", encoding="utf-8") as fh:
    fh.write(str(managed_fail))
with open(headless_count_path, "w", encoding="utf-8") as fh:
    fh.write(str(headless_fail))
PY

# ── 1. MANAGED-ONLY scan across tracked *.sh / *.py in every scan root ────────
# (excluding the gateway itself) — see MANAGED_SCAN_ROOTS above (AUD-20).
echo "── (1) managed-only: no raw agent-browser launch outside the gateway ──"
echo "     scan roots: ${MANAGED_SCAN_ROOTS[*]#$REPO_ROOT/}"
managed_fail="$(cat "$MANAGED_FAIL_COUNT" 2>/dev/null || echo 0)"
[ -s "$MANAGED_REPORT" ] && cat "$MANAGED_REPORT"
if [ "$managed_fail" -eq 0 ]; then
  green "  ✓ PASS — all agent-browser calls in every scan root route through the manager."
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
echo "     scan roots: ${MANAGED_SCAN_ROOTS[*]#$REPO_ROOT/}"
headless_fail="$(cat "$HEADLESS_FAIL_COUNT" 2>/dev/null || echo 0)"
[ -s "$HEADLESS_REPORT" ] && cat "$HEADLESS_REPORT"

# Markdown CODE-FENCE scan (Python is already a guard dependency). Only enters
# fences opened with a code-language tag (```python / ```bash / …); bare ``` prose
# blocks are skipped (they hold copy-paste doctrine that says "NEVER launch()").
# Walks every MANAGED_SCAN_ROOTS entry (AUD-20), not just SKILL_DIR. This was
# already a SINGLE batched python3 call handling every .md file internally
# (os.walk) — no per-file spawn here, so AUD-26 does not need to touch it.
while IFS= read -r m; do
  [ -z "$m" ] && continue
  red "  ✗ FAIL — $m"
  headless_fail=$((headless_fail + 1))
done < <(python3 - "$REPO_ROOT" "${MANAGED_SCAN_ROOTS[@]}" <<'PY'
import os, re, sys
repo_root = sys.argv[1]
scan_roots = sys.argv[2:]
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
for root in scan_roots:
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
