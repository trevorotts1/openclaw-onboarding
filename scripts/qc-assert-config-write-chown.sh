#!/usr/bin/env bash
# qc-assert-config-write-chown.sh — v1.0.0
#
# STATIC QC INVARIANT: fails the build when a repo script writes openclaw.json
# as root but carries no matching ownership restore.
#
# EVIDENCE THIS PREVENTS: one root-run config write left openclaw.json owned
# root:root 0600 while the gateway runs as uid 1000. Result: EACCES, the live
# config reload died, the plugin/command registry never loaded, subcommands
# ceased to exist, and a config-touching scheduled job failed 24/24 (100%,
# hourly). The gateway reported healthy throughout — a root-owned config file
# is invisible to a process-liveness check, so nothing else caught it.
#
# THE RULE: any repo script that writes openclaw.json (directly or through a
# tracked path variable) must ALSO carry one of:
#   (a) a `chown` call restoring the gateway user (owner:group form — e.g.
#       `chown 1000:1000 ...`, `chown "$OC_UID:$OC_GID" ...`,
#       `chown "$OC_USER:$OC_USER" ...`) anywhere in the same script, or
#   (b) a `trap ... EXIT|ERR|...` that performs that same restore — PREFERRED
#       over (a): a trailing chown placed after the write is SKIPPED on any
#       early `exit`/error path between the write and that line, so the file
#       can be left root-owned by the very failure this gate exists to catch.
#       A trap-based restore runs regardless of how the script leaves.
#   (c) an explicit, per-instance opt-out: a comment
#         # QC-ALLOW-NO-CHOWN: <reason>
#       on the line IMMEDIATELY ABOVE the write (a non-empty reason is
#       required — a bare marker is not accepted).
#
# WHAT COUNTS AS "WRITES openclaw.json" (per write, not per file):
#   - `openclaw config set ...` / `openclaw config patch ...`
#   - shell redirection (`>` / `>>`) whose target resolves to a path ending
#     in `openclaw.json` — either the literal string, or a variable this
#     script assigned from such a path (bash `VAR=".../openclaw.json"`, a
#     python heredoc invoked as `python3 - "$VAR" <<'PYEOF'` making
#     `sys.argv[1]` an alias, or a python `VAR = Path(sys.argv[1])` /
#     `VAR = sys.argv[1]` re-alias one hop deep)
#   - a python rewrite: `.write_text(`, `.write(`, or `json.dump(` on a line
#     that also references the config path (literal or a tracked alias, per
#     the same alias-tracking above)
#   - a `jq` rewrite of it, or a temp-file-then-`mv` swap onto it
#
# This is a line-based heuristic over the SHIPPED SCRIPTS (like the other
# static gates in this family), not a full data-flow analyzer. Alias tracking
# is bounded (bash var -> python argv/env alias -> one further python
# re-assignment) because that is the depth the repo's own config-writing
# scripts actually use (see scripts/apply-fleet-standards.sh's
# `OC_CONFIG` -> `python3 - "$OC_CONFIG" <<PYEOF` -> `cfg_path = Path(sys.argv[1])`
# -> `cfg_path.write_text(...)` chain). A write reached through deeper or more
# exotic indirection can evade detection; the opt-out marker exists for the
# inverse case (a flagged line that is provably safe), not this one.
#
# SELF-EXCLUSION: this script's own basename is excluded from the scan. Its
# header/help/remedy text quotes the very literals it scans for ("openclaw
# config set", "chown", "openclaw.json") as documentation, not as a write.
#
# Must NOT false-FAIL on read-only scripts: `openclaw config get`, a plain
# `cat`/`jq` READ of openclaw.json, or a python heredoc that only
# `json.loads(...)`/`.read_text()`s the config, never trip this gate.
#
# BASELINE MODE — adopting this gate into a codebase with pre-existing debt:
#   A gate that is RED on the day it lands either blocks all unrelated work or
#   gets bypassed with --no-verify, and within a week everyone ignores it —
#   the same failure mode as a test that fails for a property of its host,
#   not a real defect. So this gate ships with a baseline: pre-existing
#   findings are recorded once and treated as known debt (INFO, non-blocking)
#   from then on, while any NEW unguarded write — the exact fault class this
#   gate exists to catch — still fails the build immediately, INCLUDING a new
#   occurrence of a line whose text is otherwise identical to one already
#   baselined in the same file (see COUNT-AWARE BASELINE below).
#
#   --write-baseline  Scan the repo and (over)write every current would-be-
#                      FAIL finding, WITH ITS OCCURRENCE COUNT, to
#                      tests/fixtures/qc-assert-config-write-chown/baseline.txt,
#                      one stable key per line, sorted. Always exits 0 (or 2
#                      on a genuine usage error) — this is a maintenance
#                      operation, not a pass/fail check. Re-run it any time
#                      debt is deliberately paid down, or a duplicate line is
#                      deliberately added, so the recorded count tracks
#                      reality again.
#
#   (default)          Scan the repo, load the baseline, and for each key
#                      compare the OBSERVED occurrence count in the repo
#                      today against the BASELINED count recorded for that
#                      key:
#                        - observed == baselined -> INFO (known debt), no
#                          failure.
#                        - observed >  baselined -> FAIL, exit 1 — this is a
#                          genuinely new unguarded write, even when its text
#                          is identical to an already-baselined line in the
#                          same file. The message states both numbers, e.g.
#                          "3 occurrence(s), baseline allows 2".
#                        - observed <  baselined -> INFO "partially
#                          resolved", exit 0. Fixing something must never
#                          break the build.
#                        - key absent from the baseline entirely -> FAIL,
#                          exit 1 (a brand-new finding — unchanged from
#                          pre-count-aware behavior).
#                        - a baseline entry the scan can no longer produce at
#                          all (observed count 0) -> INFO "baseline entry
#                          resolved", suggests re-running --write-baseline.
#                          Never fails.
#                      If the baseline file is missing, this is NOT a silent
#                      pass: prints UNDETERMINED and exits 3, so an absent
#                      instrument never reads as a clean sweep.
#
#   --strict           Ignore the baseline entirely; every unguarded write is
#                      a FAIL, exactly like the gate's pre-baseline behavior.
#                      Use to see the full remaining debt, or to flip the
#                      gate fully strict once the baseline is empty.
#
#   Baseline key format (COUNT-AWARE):
#     "<repo-relative-file>::<normalized matched line><TAB><count>"
#   — the offending line's own text (comment-stripped, whitespace-collapsed,
#   trimmed) is the key, NOT a raw line number, followed by a tab and the
#   number of times that exact normalized line occurred in that file at
#   baseline time. A line number is the first thing to shift when anyone
#   edits above a finding; the offending line's own text is not, so this key
#   survives unrelated line-number drift elsewhere in the file as well as
#   reasonably possible for a line-based heuristic. See
#   tests/fixtures/qc-assert-config-write-chown/baseline.txt for the exact
#   generated format.
#
#   BACKWARD COMPATIBILITY: a baseline entry written before this count-aware
#   format existed has no <TAB><count> field. It is read as count=1 — not
#   unbounded, not skipped, not a crash — and this gate prints one INFO
#   advising a re-run of --write-baseline to upgrade the file. Treating a
#   missing count as unbounded here would silently reopen the exact bypass
#   this format exists to close.
#
#   COUNT-AWARE BASELINE — the bug this closes: a content key alone (no
#   count) collapses every IDENTICAL literal line in one file onto a single
#   baseline entry, so the baseline could record "this file has this kind of
#   unguarded write" but not HOW MANY. Confirmed against this repo before
#   this fix: scripts/test-ceo-tool-gate.sh alone produces 9 identical
#   occurrences of one such line, which the raw scan counts as 9 findings
#   but a count-less baseline recorded as 1 key — meaning a 10th identical
#   line (a genuinely new unguarded write) would have been silently accepted
#   as already-known debt. The count field closes this: default mode now
#   fails as soon as the OBSERVED count for a key exceeds the BASELINED
#   count, regardless of whether the excess line's text happens to match an
#   existing baselined line verbatim. Residual limitation: when the observed
#   count exceeds the baselined count, every occurrence of that key is
#   identical text by construction, so this gate cannot say WHICH specific
#   physical line is "the new one" — only that the total has grown beyond
#   what was baselined, which is exactly the information needed to fail the
#   build. --strict bypasses the baseline entirely and still catches every
#   individual occurrence when that matters.
#
# Exit codes:
#   0  — PASS: no key's observed count exceeds its baselined count (a lower
#        observed count, a fully resolved baseline entry, and a key absent
#        from the scan are all exit 0); in --write-baseline mode, the
#        baseline was written successfully
#   1  — FAIL: at least one key's observed count exceeds its baselined count,
#        or is absent from the baseline entirely, or --strict was passed and
#        any unguarded write was found — block the build
#   2  — usage error
#   3  — UNDETERMINED: default mode was requested but the baseline file is
#        absent — this NEVER collapses into exit 0; run --write-baseline
#        first
#
# Usage:
#   bash scripts/qc-assert-config-write-chown.sh
#   bash scripts/qc-assert-config-write-chown.sh --quiet
#   bash scripts/qc-assert-config-write-chown.sh --repo-root /path/to/repo
#   bash scripts/qc-assert-config-write-chown.sh --write-baseline
#   bash scripts/qc-assert-config-write-chown.sh --strict
#
# Wired in:
#   Not yet wired into scripts/qc-system-integrity.sh — this is a new gate;
#   wiring it in is a separate change.

set -uo pipefail

QUIET=0
WRITE_BASELINE=0
STRICT=0
SELF_NAME="$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --write-baseline) WRITE_BASELINE=1; shift ;;
    --strict) STRICT=1; shift ;;
    -h|--help)
      sed -n '1,171p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-config-write-chown] PASS  %s\n' "$*"; }
_fail() { printf '[qc-config-write-chown] FAIL  %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-config-write-chown] INFO  %s\n' "$*"; }
_undetermined() { printf '[qc-config-write-chown] UNDETERMINED  %s\n' "$*" >&2; }

# Shared baseline-file header, used by every --write-baseline call site so
# the documented format can never drift from what is actually written.
_write_baseline_header() {
  echo "# qc-assert-config-write-chown baseline"
  echo "# Generated by: bash scripts/qc-assert-config-write-chown.sh --write-baseline"
  echo "# Format: one entry per line:"
  echo "#   <repo-relative-file>::<normalized matched line><TAB><count>"
  echo "# normalized = comment-stripped, whitespace-collapsed, trimmed."
  echo "# <count> = number of times this exact normalized line occurred in"
  echo "#   this file when --write-baseline was run. Default mode FAILS a"
  echo "#   key whose OBSERVED count exceeds this <count> (a new occurrence"
  echo "#   of an already-baselined line), and treats a lower observed count"
  echo "#   as partially-resolved debt (non-blocking, never fails)."
  echo "# Comparison ignores line numbers so an entry survives unrelated"
  echo "# line-number drift elsewhere in the file."
  echo "# Backward compatibility: a line with no <TAB><count> field (written"
  echo "#   before this count-aware format existed) is read as count=1."
  echo "# Regenerate after fixing debt: bash scripts/qc-assert-config-write-chown.sh --write-baseline"
}

if [ ! -d "$REPO_ROOT" ]; then
  echo "[qc-config-write-chown] usage error: --repo-root '$REPO_ROOT' is not a directory" >&2
  exit 2
fi

if [ "$WRITE_BASELINE" = "1" ] && [ "$STRICT" = "1" ]; then
  echo "[qc-config-write-chown] usage error: --write-baseline and --strict are mutually exclusive" >&2
  exit 2
fi

BASELINE_FILE="$REPO_ROOT/tests/fixtures/qc-assert-config-write-chown/baseline.txt"

# In default mode (neither --write-baseline nor --strict) the baseline file
# is the instrument this gate reads. Its absence must NEVER read as a clean
# sweep — check this BEFORE doing any scan work, and exit 3 (UNDETERMINED),
# matching the convention in scripts/qc-assert-provider-timeouts.sh.
if [ "$WRITE_BASELINE" = "0" ] && [ "$STRICT" = "0" ] && [ ! -f "$BASELINE_FILE" ]; then
  _undetermined "baseline file not found: $BASELINE_FILE — default mode DID NOT determine pass/fail; no finding was classified as known-debt or new. Create it once with: bash ${BASH_SOURCE[0]} --write-baseline (or pass --strict to run without a baseline)."
  exit 3
fi

# ─── File enumeration ────────────────────────────────────────────────────────
# Literal per spec: scripts/*.sh and repo-root *.sh (non-recursive). Self is
# excluded (see header SELF-EXCLUSION note above).
FILES=()
for f in "$REPO_ROOT"/scripts/*.sh "$REPO_ROOT"/*.sh; do
  [ -f "$f" ] || continue
  [ "$(basename "$f")" = "$SELF_NAME" ] && continue
  FILES+=("$f")
done

if [ "${#FILES[@]}" -eq 0 ]; then
  if [ "$WRITE_BASELINE" = "1" ]; then
    mkdir -p "$(dirname "$BASELINE_FILE")"
    { _write_baseline_header; } > "$BASELINE_FILE"
    _pass "no scripts/*.sh or repo-root *.sh files found under $REPO_ROOT — wrote empty baseline to $BASELINE_FILE (0 entries)."
    exit 0
  fi
  _info "no scripts/*.sh or repo-root *.sh files found under $REPO_ROOT — nothing to scan."
  _pass "no config-writing scripts to check."
  exit 0
fi

# ─── Single-pass analysis (one python3 call over every candidate file) ───────
# The python source is written to a temp file first, THEN run via a plain
# `python3 "$file" ...` command substitution — never a heredoc directly
# inside `$(...)`. bash 3.2 (macOS stock /bin/bash) has a real parser bug
# where an unbalanced/multi-line `(` inside a heredoc BODY that is nested
# inside `$(...)` throws off its paren-matching scan for the outer command
# substitution ("unexpected EOF while looking for matching `"'" at parse
# time, before the script ever runs) — confirmed by bisecting this exact
# heredoc's body under `/bin/bash -n` (GNU bash 3.2.57, arm64-apple-darwin).
# A heredoc that is NOT nested inside `$(...)` does not trigger it, hence
# this two-step: write, then invoke.
QC_PY_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/qc-config-write-chown-analysis.XXXXXX.py")"
cat > "$QC_PY_SCRIPT" <<'PYEOF'
import re
import sys

repo_root = sys.argv[1]
files = sys.argv[2:]

RE_ASSIGN = re.compile(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*.*openclaw\.json')
RE_PY_HEREDOC_ARG = re.compile(r'python3\s+-\s+.*<<')
RE_PY_ALIAS = re.compile(
    r'^\s*([A-Za-z_]\w*)\s*=\s*(?:Path\()?\s*(sys\.argv\[1\]|os\.environ(?:\.get)?\([^)]*\))\)?'
)
RE_CHOWN_OWNER = re.compile(r'\bchown\s+"?[\w${}.\-]+:[\w${}.\-]+"?')
RE_TRAP_INLINE = re.compile(
    r'\btrap\s+[\'"][^\'"]*chown\s+"?[\w${}.\-]+:[\w${}.\-]+"?[^\'"]*[\'"]\s+\S*(EXIT|ERR|INT|TERM|HUP)'
)
RE_TRAP_FUNC = re.compile(r'\btrap\s+([A-Za-z_]\w*)\s+\S*(EXIT|ERR|INT|TERM|HUP)')
RE_FUNC_DEF = re.compile(r'^\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\)\s*\{')
RE_OPTOUT = re.compile(r'^\s*#\s*QC-ALLOW-NO-CHOWN:\s*\S')

CONTENT_VERBS = ('.write_text(', '.write(', 'json.dump(', 'jq ')


def strip_comment(line):
    # Same convention the rest of this gate family uses (code_has/code_has_f in
    # qc-assert-ghl-mcp-supervised.sh): drop everything from the first '#'
    # onward. A literal '#' inside a string is mishandled the same way every
    # sibling gate already accepts.
    idx = line.find('#')
    return line if idx == -1 else line[:idx]


def find_func_body_has_chown(lines_code, func_name):
    depth = 0
    in_func = False
    for line in lines_code:
        if not in_func:
            m = RE_FUNC_DEF.match(line)
            if m and m.group(1) == func_name:
                in_func = True
                depth = line.count('{') - line.count('}')
            continue
        if RE_CHOWN_OWNER.search(line):
            return True
        depth += line.count('{') - line.count('}')
        if depth <= 0:
            break
    return False


def rel(path):
    if path.startswith(repo_root + '/'):
        return path[len(repo_root) + 1:]
    return path


for path in files:
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            raw_lines = fh.read().splitlines()
    except OSError as e:
        print(f'INFO||0|could not read {path}: {e}')
        continue

    code_lines = [strip_comment(l) for l in raw_lines]

    # ── Pass 1: bash/python vars assigned a literal openclaw.json path ───────
    tracked = set()
    for cl in code_lines:
        m = RE_ASSIGN.match(cl)
        if m:
            tracked.add(m.group(1))

    # ── argv alias: python3 - "$VAR" <<... makes sys.argv[1] an alias ────────
    argv_alias = False
    for cl in code_lines:
        if RE_PY_HEREDOC_ARG.search(cl):
            for t in tracked:
                if ('$' + t) in cl or ('${' + t + '}') in cl:
                    argv_alias = True
                    break
    if argv_alias:
        tracked.add('sys.argv[1]')

    # ── one further python re-alias hop: VAR = Path(sys.argv[1]) / VAR = X ──
    ref_tokens = set(tracked)
    for cl in code_lines:
        m = RE_PY_ALIAS.match(cl)
        if m:
            lhs, rhs = m.group(1), m.group(2)
            if rhs in ref_tokens or any(t in rhs for t in tracked):
                ref_tokens.add(lhs)

    def line_has_config_ref(line):
        if 'openclaw.json' in line:
            return True
        for t in ref_tokens:
            if t == 'sys.argv[1]':
                if t in line:
                    return True
            elif re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', line):
                return True
        return False

    # ── file-level chown / trap-chown presence ────────────────────────────────
    plain_chown = any(RE_CHOWN_OWNER.search(cl) for cl in code_lines)
    trap_chown = any(RE_TRAP_INLINE.search(cl) for cl in code_lines)
    if not trap_chown:
        for cl in code_lines:
            m = RE_TRAP_FUNC.search(cl)
            if m and find_func_body_has_chown(code_lines, m.group(1)):
                trap_chown = True
                break

    # ── find write lines ───────────────────────────────────────────────────
    for i, cl in enumerate(code_lines):
        lineno = i + 1
        hit = False
        reason = ''
        if re.search(r'\bopenclaw\s+config\s+set\b', cl):
            hit, reason = True, "runs 'openclaw config set'"
        elif re.search(r'\bopenclaw\s+config\s+patch\b', cl):
            hit, reason = True, "runs 'openclaw config patch'"
        else:
            # target-based: redirection / mv
            for m in re.finditer(r'(?<!\d)(>{1,2})\s*([^\s|&;]+)', cl):
                target = m.group(2).strip('\'"')
                if line_has_config_ref(target) or 'openclaw.json' in target:
                    hit, reason = True, f"redirects ({m.group(1)}) into a path resolving to openclaw.json"
                    break
            if not hit:
                m = re.search(r'\bmv\s+.*\s([^\s|&;]+)\s*$', cl)
                if m:
                    target = m.group(1).strip('\'"')
                    if line_has_config_ref(target):
                        hit, reason = True, "mv's a temp file onto openclaw.json"
            if not hit:
                for verb in CONTENT_VERBS:
                    if verb in cl and line_has_config_ref(cl):
                        hit, reason = True, f"rewrites openclaw.json via '{verb.rstrip(chr(40))}'"
                        break

        if not hit:
            continue

        # opt-out marker must be on the ORIGINAL line immediately above
        optout = False
        if lineno - 2 >= 0 and lineno - 2 < len(raw_lines):
            if RE_OPTOUT.match(raw_lines[lineno - 2]):
                optout = True

        if optout:
            print(f'INFO|{rel(path)}|{lineno}|opt-out marker honored ({reason})')
        elif trap_chown:
            print(f'INFO|{rel(path)}|{lineno}|satisfied by a trap-based chown restore ({reason})')
        elif plain_chown:
            print(f'INFO|{rel(path)}|{lineno}|satisfied by a chown restore elsewhere in the file ({reason}) — prefer a trap (a trailing chown is skipped on an early exit/error path)')
        else:
            # Baseline key material: the offending line's own text, comment-
            # stripped (cl, not raw_lines[i]) and whitespace-collapsed, so the
            # key is stable across re-indentation and trailing-comment edits
            # and does not require a line number to stay valid.
            norm_snippet = re.sub(r'\s+', ' ', cl).strip()
            print(f'FAIL|{rel(path)}|{lineno}|{reason}, and no chown restore, no trap-based restore, and no # QC-ALLOW-NO-CHOWN marker on the preceding line|{norm_snippet}')
PYEOF
ANALYSIS="$(python3 "$QC_PY_SCRIPT" "$REPO_ROOT" "${FILES[@]}")"
PY_RC=$?
rm -f "$QC_PY_SCRIPT"
if [ "$PY_RC" -ne 0 ]; then
  echo "[qc-config-write-chown] usage error: python3 analysis failed (rc=$PY_RC)" >&2
  exit 2
fi

# ─── Baseline set-up ──────────────────────────────────────────────────────────
# bash 3.2 (macOS system /bin/bash) has no associative arrays, so all set
# membership AND key->count lookups below are done with sort/uniq/awk over
# plain temp files, not `declare -A`. This must run unmodified on the stock
# Mac shell. A key->count lookup (not just set membership) needs more than
# grep -Fxq can give us, so lookups use `awk -F'\t' 'BEGIN{k=ENVIRON[...]}
# $1==k'` (see _baseline_count_for / _observed_count_for below for why the
# key is passed via ENVIRON and NOT `awk -v k="$1"` — the two are NOT
# interchangeable here) — still a single pass over a flat file and still
# plain string equality (never a regex match against attacker-shaped key
# text), just extended to return the paired count field, not only yes/no.
TMP_KEYS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/qc-config-write-chown.XXXXXX")"
trap 'rm -rf "$TMP_KEYS_DIR"' EXIT

CURRENT_FAIL_KEYS="$TMP_KEYS_DIR/current-fail-keys.txt"
: > "$CURRENT_FAIL_KEYS"

BASELINE_KEYS=""
BASELINE_COUNTS_FILE=""
if [ "$WRITE_BASELINE" = "0" ] && [ "$STRICT" = "0" ]; then
  # Existence was already verified above; re-read here (default mode only).
  BASELINE_KEYS="$TMP_KEYS_DIR/baseline-keys.txt"
  grep -v '^[[:space:]]*#' "$BASELINE_FILE" 2>/dev/null | grep -v '^[[:space:]]*$' > "$BASELINE_KEYS" || true

  # Normalize every baseline line to "<key><TAB><count>". A line already in
  # that format passes through unchanged; a legacy line (written before the
  # count-aware format existed) has no tab at all and is read as count=1 —
  # never unbounded, never skipped, never a crash — with one INFO advising a
  # --write-baseline re-run to upgrade the file to the new format.
  BASELINE_COUNTS_FILE="$TMP_KEYS_DIR/baseline-counts.txt"
  : > "$BASELINE_COUNTS_FILE"
  TAB="$(printf '\t')"
  LEGACY_COUNT=0
  while IFS= read -r bline; do
    [ -z "$bline" ] && continue
    case "$bline" in
      *"$TAB"*)
        printf '%s\n' "$bline" >> "$BASELINE_COUNTS_FILE"
        ;;
      *)
        printf '%s\t1\n' "$bline" >> "$BASELINE_COUNTS_FILE"
        LEGACY_COUNT=$((LEGACY_COUNT + 1))
        ;;
    esac
  done < "$BASELINE_KEYS"
  if [ "$LEGACY_COUNT" -gt 0 ]; then
    _info "$LEGACY_COUNT legacy baseline entrie(s) have no <TAB><count> field (pre-count-aware format) — each read as count=1. Run --write-baseline to upgrade $BASELINE_FILE to the count-aware format."
  fi
fi

# Look up the baselined count for key "$1". Prints the count if the key is
# present, prints nothing (empty) if absent. Exact string equality on the
# whole key field — never a substring or regex match — so a key that is a
# prefix of another key can never collide with it.
#
# The key is passed via ENVIRON, NOT `awk -v k="$1"`. This is deliberate,
# not stylistic: POSIX awk backslash-escape-processes the VALUE of a `-v`
# assignment (so a key containing a literal two-character `\n` — extremely
# common in this repo's baseline, e.g. a python `.write_text(... + "\n")`
# line — gets silently rewritten to a real newline before comparison,
# while the SAME text read as $1 from the data file is never escape-
# processed, so `$1 == k` then compares a literal-backslash-n key against
# a real-newline one and never matches). A `-v`-based lookup was tried
# first here and reproducibly failed on exactly that key against this
# repo's own real baseline before this was caught. `ENVIRON[...]` reads
# the process environment, which awk does NOT escape-process, so both
# sides of the comparison see the identical literal bytes.
_baseline_count_for() {
  QC_LOOKUP_KEY="$1" awk -F'\t' 'BEGIN { k = ENVIRON["QC_LOOKUP_KEY"] } $1 == k { print $2; exit }' "$BASELINE_COUNTS_FILE" 2>/dev/null
}

# Look up the OBSERVED count for key "$1" from OBS_COUNTS_FILE (built below,
# after the first pass over ANALYSIS). Same exact-match discipline (and the
# same ENVIRON-not--v reasoning) as _baseline_count_for above. Prints 0,
# never empty, so callers can always do a numeric comparison.
_observed_count_for() {
  local v
  v="$(QC_LOOKUP_KEY="$1" awk -F'\t' 'BEGIN { k = ENVIRON["QC_LOOKUP_KEY"] } $1 == k { print $2; exit }' "$OBS_COUNTS_FILE" 2>/dev/null)"
  [ -z "$v" ] && v=0
  printf '%s' "$v"
}

NEW_VIOLATIONS=0
KNOWN_DEBT=0

# ─── Pass 1: print INFO findings inline (unaffected by baseline counts); for
# FAIL findings, only record the key (for --write-baseline / --strict this is
# also where the decision is made and printed, since neither mode needs a
# per-key observed-vs-baselined count comparison — --write-baseline is
# recording counts, not comparing them, and --strict ignores the baseline
# entirely). Default mode DEFERS its FAIL/INFO decision to pass 2 below,
# because that decision needs the TOTAL observed count per key, which is not
# known until every occurrence has been seen. ────────────────────────────────
while IFS='|' read -r kind file lineno rest; do
  [ -z "$kind" ] && continue
  case "$kind" in
    INFO)
      _info "$file:$lineno $rest"
      ;;
    FAIL)
      # rest = "<reason>|<normalized snippet>" — reason never contains '|',
      # so the first '|' is exactly the reason/snippet boundary; everything
      # after it (including any further '|' from e.g. a shell `||`) is the
      # snippet, kept intact.
      reason="${rest%%|*}"
      snippet="${rest#*|}"
      key="${file}::${snippet}"
      printf '%s\n' "$key" >> "$CURRENT_FAIL_KEYS"

      if [ "$WRITE_BASELINE" = "1" ]; then
        _info "$file:$lineno $reason [recording to baseline]"
      elif [ "$STRICT" = "1" ]; then
        _fail "$file:$lineno $reason"
        NEW_VIOLATIONS=$((NEW_VIOLATIONS + 1))
      fi
      # default mode: no print here -- pass 2 below handles it.
      ;;
  esac
done <<< "$ANALYSIS"

# ─── OBSERVED counts: one line per unique key, "<key><TAB><count>", sorted.
# `uniq -c` requires sorted input to group correctly; the trailing `sort`
# re-sorts by key (not by the count `uniq -c` prefixes each line with) so the
# result matches the baseline file's own key-sorted order. ────────────────────
OBS_COUNTS_FILE="$TMP_KEYS_DIR/obs-counts.txt"
: > "$OBS_COUNTS_FILE"
if [ -s "$CURRENT_FAIL_KEYS" ]; then
  sort "$CURRENT_FAIL_KEYS" | uniq -c \
    | awk '{c=$1; sub(/^[ \t]*[0-9]+[ \t]+/, ""); print $0 "\t" c}' \
    | sort > "$OBS_COUNTS_FILE"
fi

# ─── --write-baseline: write the file and exit ───────────────────────────────
if [ "$WRITE_BASELINE" = "1" ]; then
  mkdir -p "$(dirname "$BASELINE_FILE")"
  {
    _write_baseline_header
    if [ -s "$OBS_COUNTS_FILE" ]; then
      cat "$OBS_COUNTS_FILE"
    fi
  } > "$BASELINE_FILE"
  COUNT=0
  if [ -s "$OBS_COUNTS_FILE" ]; then
    COUNT="$(wc -l < "$OBS_COUNTS_FILE" | tr -d ' ')"
  fi
  _pass "wrote $COUNT finding(s) to baseline: $BASELINE_FILE"
  exit 0
fi

# ─── Pass 2 (default mode only): count-aware FAIL/INFO decision per key ─────
# For each FAIL occurrence, in the same file-scan order as pass 1: track how
# many occurrences of THIS key have been seen so far (occ_index, via the same
# sort+grep -Fx temp-file discipline as everywhere else in this gate — append
# then count). A key absent from the baseline entirely is always a FAIL (the
# brand-new-write case, unchanged from pre-count-aware behavior). A key
# present in the baseline is a FAIL only for the occurrences beyond the
# baselined count (occ_index > baselined count) -- since occ_index can never
# exceed the total observed count for its key, "occ_index > baselined count"
# can only be true when observed > baselined, i.e. exactly the new-occurrence
# case this gate exists to catch.
if [ "$WRITE_BASELINE" = "0" ] && [ "$STRICT" = "0" ]; then
  SEEN_SO_FAR="$TMP_KEYS_DIR/seen-so-far.txt"
  : > "$SEEN_SO_FAR"

  while IFS='|' read -r kind file lineno rest; do
    [ "$kind" = "FAIL" ] || continue
    reason="${rest%%|*}"
    snippet="${rest#*|}"
    key="${file}::${snippet}"

    printf '%s\n' "$key" >> "$SEEN_SO_FAR"
    occ_index="$(grep -Fxc -- "$key" "$SEEN_SO_FAR")"

    baselined="$(_baseline_count_for "$key")"
    observed="$(_observed_count_for "$key")"

    if [ -z "$baselined" ]; then
      _fail "$file:$lineno $reason [NEW VIOLATION — not in baseline]"
      NEW_VIOLATIONS=$((NEW_VIOLATIONS + 1))
    elif [ "$occ_index" -le "$baselined" ]; then
      if [ "$observed" -lt "$baselined" ]; then
        _info "$file:$lineno $reason [KNOWN DEBT — baselined, non-blocking; partially resolved: $observed occurrence(s) observed, baseline allowed $baselined]"
      else
        _info "$file:$lineno $reason [KNOWN DEBT — baselined, non-blocking]"
      fi
      KNOWN_DEBT=$((KNOWN_DEBT + 1))
    else
      _fail "$file:$lineno $reason [NEW VIOLATION — $observed occurrence(s), baseline allows $baselined]"
      NEW_VIOLATIONS=$((NEW_VIOLATIONS + 1))
    fi
  done <<< "$ANALYSIS"
fi

# ─── default mode only: report baseline entries the scan can no longer find
# AT ALL (observed count 0). A key whose count merely DECREASED (but is still
# > 0) was already reported inline above as "partially resolved" -- reporting
# it again here as fully "resolved" would be double counting the same fix. ──
RESOLVED=0
if [ "$STRICT" = "0" ] && [ -f "$BASELINE_COUNTS_FILE" ]; then
  while IFS=$'\t' read -r bkey bcount; do
    [ -z "$bkey" ] && continue
    if [ "$(_observed_count_for "$bkey")" -eq 0 ]; then
      _info "baseline entry resolved (scan no longer finds it): $bkey — fixing something must never break the build; re-run --write-baseline to drop this entry."
      RESOLVED=$((RESOLVED + 1))
    fi
  done < "$BASELINE_COUNTS_FILE"
fi

if [ "$NEW_VIOLATIONS" -gt 0 ]; then
  _fail "$NEW_VIOLATIONS NEW config write(s) with no ownership restore (not covered by the baseline) — a root-run write leaves openclaw.json root-owned, the gateway (uid 1000) gets EACCES on reload, and every config-touching feature goes silently dark while the gateway itself still reports healthy."
  echo "REMEDY: add a trap-based restore (survives early exit/error paths) — e.g.:" >&2
  echo '    trap '"'"'chown "$OC_UID:$OC_GID" "$OC_CONFIG" 2>/dev/null || true'"'"' EXIT' >&2
  echo "  A trailing 'chown ... \"\$OC_CONFIG\"' after the write also satisfies this gate, but" >&2
  echo "  is skipped on any early exit between the write and that line — trap is preferred." >&2
  echo "  If the write is provably safe without a chown, add:" >&2
  echo "    # QC-ALLOW-NO-CHOWN: <reason>" >&2
  echo "  on the line immediately above the write." >&2
  echo "  If this is pre-existing debt you are deliberately not fixing right now," >&2
  echo "  that is what --write-baseline is for — a NEW write should be fixed, not baselined." >&2
  exit 1
fi

if [ "$KNOWN_DEBT" -gt 0 ]; then
  _info "$KNOWN_DEBT known-debt finding(s) baselined (non-blocking). Run --strict to see them all fail, or fix them and re-run --write-baseline to shrink the baseline."
fi

_pass "no NEW config write is missing an ownership restore ($KNOWN_DEBT known-debt finding(s) baselined, $RESOLVED baseline entry/entries resolved)."
exit 0
