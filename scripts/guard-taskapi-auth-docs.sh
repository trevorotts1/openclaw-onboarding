#!/usr/bin/env bash
# guard-taskapi-auth-docs.sh — v1.0.0
#
# CI / QC GUARD for the COMMAND CENTER TASK-API WRITE-BACK AUTH DOCTRINE.
#
# THE DOCTRINE: dispatched department/persona agents finish work and write the
# result back to the Command Center task API:
#   POST  {missionControlUrl}/api/tasks/{id}/activities
#   POST  {missionControlUrl}/api/tasks/{id}/deliverables
#   PATCH {missionControlUrl}/api/tasks/{id}            (status -> review, etc.)
#   POST  {missionControlUrl}/api/tasks/{id}/events
#   POST  {missionControlUrl}/api/tasks/{id}/return-to-orchestrator
# The Command Center is FAIL-CLOSED: every EXTERNAL /api/* caller must send
# `Authorization: Bearer $MC_API_TOKEN` or it is rejected 401 — the finished
# task freezes `in_progress` until a stale sweep blocks it. EXCEPTION:
# `POST /api/tasks/ingest` uses a DIFFERENT scheme (HMAC `x-webhook-signature`
# over WEBHOOK_SECRET) and must NEVER carry a Bearer line.
#
# WHAT THIS GUARD ENFORCES: every tracked write-back API EXAMPLE (a POST/PATCH
# invocation line an agent would read and copy) must carry an `Authorization` /
# `Bearer` mention in its surrounding block — either the enclosing ``` fenced
# code block, or a small window around a bare (non-fenced) example line.
#
# WHAT COUNTS AS A CANDIDATE EXAMPLE LINE:
#   A literal `POST` or `PATCH` token followed (within a few tokens — allowing
#   connector words like "to"/"via") by a token containing `api/tasks/`, whose
#   trailing path segment is one of activities/deliverables/events/
#   return-to-orchestrator (POST or PATCH), OR — for PATCH only — the bare
#   `.../api/tasks/{id}` status-change form (no further path segment).
#
# WHAT IS EXEMPT (never a candidate, never fails the build):
#   (a) `/api/tasks/ingest` — the HMAC-signed create path. A block whose ONLY
#       task-API call is `ingest` naturally has zero candidates.
#   (b) CHANGELOG.md files (historical record, not a live example to copy).
#   (c) A server SOURCE-PATH citation — the path's first segment is a Next.js
#       dynamic-route bracket (`[id]`) rather than a doc-style `{id}`/`<id>`
#       placeholder (e.g. `src/app/api/tasks/[id]/route.ts`), or the token
#       contains `route.ts` — a code-path citation, not an invocation example.
#   (d) A WRAPPER-FUNCTION call site — the token right after POST/PATCH is a
#       QUOTED string (`"..."` / `'...'`) and the verb is NOT part of a
#       `curl -X POST/PATCH "..."` invocation. This repo's `_api()` / `cc_call()`
#       / `_post_json()` helpers (06-ghl-install-pages/tools/cc_board.py,
#       36/37/38 cc-task.sh, 35-social-media-planner run-publishing-cycle.sh)
#       already inject the Authorization header INSIDE the shared helper, far
#       from the call site — a local window would false-positive on real,
#       already-authenticated code. A raw `curl -X POST "url"` is NOT exempted
#       by this rule (the URL is quoted there too, but curl idiom is excluded
#       from the quote-exemption) — its own -H Authorization must still be
#       within the window.
#   (e) A .py/.sh file that DELEGATES its write-backs to the shared, already-
#       authenticated board client (`_cc_board` / `cc_board` / `_post_json` /
#       `mc_route`) — the header is injected inside that helper, so a docstring
#       or prose mention of the DELEGATED endpoint here has nothing to leave
#       unauthenticated (e.g. ghl_survey_builder.py → _cc_board._post_json()).
#
# Exit codes:
#   0  — PASS (every candidate write-back example has an Authorization/Bearer
#        mention in its surrounding block/window)
#   1  — FAIL (one or more candidate examples have none) — prints file:line
#   2  — usage / environment error
#
# Usage:
#   bash scripts/guard-taskapi-auth-docs.sh
#   bash scripts/guard-taskapi-auth-docs.sh --repo-root /path/to/repo

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,70p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "guard-taskapi-auth-docs: git not found" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "guard-taskapi-auth-docs: python3 not found" >&2; exit 2; }

cd "$REPO_ROOT"

red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }

echo ""
echo "═══ guard-taskapi-auth-docs — Command Center write-back auth doctrine ═══"
echo ""

# Narrow the tracked .md/.sh/.py set down to files that even mention the task
# API at all, before handing them to the precise python scanner (speed only —
# a file with zero "/api/tasks/" occurrences can never contain a candidate).
# Deliberately a `while read` loop, NOT `xargs` — BSD xargs (macOS) aborts the
# whole run silently on a filename containing a quote/backslash, which would
# make this guard fail OPEN (silently scan zero files) rather than fail closed.
CANDIDATE_FILES=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if grep -q "/api/tasks/" "$f" 2>/dev/null; then
    CANDIDATE_FILES="${CANDIDATE_FILES}${f}"$'\n'
  fi
done < <(git ls-files -- '*.md' '*.sh' '*.py')

if [ -z "$CANDIDATE_FILES" ]; then
  green "guard-taskapi-auth-docs PASS — no tracked .md/.sh/.py file mentions /api/tasks/."
  exit 0
fi

# The candidate file list is passed via a temp file, NOT piped stdin — `python3 -
# <<'PY'` already claims stdin as the SCRIPT source, so piped data on the same fd
# would never reach an in-script sys.stdin.read() (it gets consumed/shadowed by
# the heredoc). A real file avoids that trap entirely.
TMP_LIST="$(mktemp "${TMPDIR:-/tmp}/guard-taskapi-auth-docs.XXXXXX")"
trap 'rm -f "$TMP_LIST"' EXIT
printf '%s' "$CANDIDATE_FILES" > "$TMP_LIST"

RESULT="$(python3 - "$REPO_ROOT" "$TMP_LIST" <<'PY'
import re, sys, os

repo_root = sys.argv[1]
list_path = sys.argv[2]
with open(list_path, encoding="utf-8") as fh:
    files = [l.strip() for l in fh if l.strip()]

SELF = "scripts/guard-taskapi-auth-docs.sh"
SUFFIXES = {"activities", "deliverables", "events", "return-to-orchestrator"}

# (e) DELEGATION exemption (.py/.sh only): a file that routes its write-backs
# through the shared, already-authenticated board client (_cc_board / cc_board /
# _post_json / mc_route) is auth-aware even if the word "Bearer" only lives
# INSIDE that helper module. This keeps a docstring/prose mention of a DELEGATED
# endpoint from false-failing — e.g. ghl_survey_builder.py's
# _board_register_deliverable() describes "POST … /deliverables" but actually
# calls _cc_board._post_json(), which injects the header. The call site never
# hand-crafts the request, so there is nothing to leave unauthenticated.
DELEGATION_RE = re.compile(r'\b(_cc_board|cc_board|_post_json|mc_route)\b')

VERB_RE = re.compile(r'\b(POST|PATCH)\b')
TRAIL_PUNCT = '`\'"),.:;|]}*'

def strip_trail(tok):
    return tok.rstrip(TRAIL_PUNCT)

def strip_lead_quote(tok):
    # Only used to test "is this token a quoted string" — do not mutate tok.
    return tok[:1] in ('"', "'")

def fence_ranges(lines):
    """Return list of (start_idx, end_idx) 0-based inclusive index ranges for
    ``` fenced code blocks (handles nested-looking runs by simple toggle)."""
    ranges = []
    open_at = None
    for i, line in enumerate(lines):
        if line.strip().startswith('```'):
            if open_at is None:
                open_at = i
            else:
                ranges.append((open_at, i))
                open_at = None
    if open_at is not None:
        # Unterminated fence — treat the rest of the file as the block so we
        # never silently ignore a dangling example (fail-safe, not fail-open).
        ranges.append((open_at, len(lines) - 1))
    return ranges

def block_for_line(idx, ranges):
    for (s, e) in ranges:
        if s <= idx <= e:
            return (s, e)
    return None

def has_auth_mention(text):
    # Require the specific word "Bearer" (the CC write-back scheme is ALWAYS
    # "Authorization: Bearer $MC_API_TOKEN" in this repo — "Bearer" is the
    # unambiguous, specific signal). Deliberately NOT a bare "Authorization"
    # substring search: that false-passes a block whose only "Authorization"
    # text is prose describing its own ABSENCE (e.g. "test — no Authorization
    # header", or an error message) — exactly the shape a real 401-trap
    # write-up tends to contain, and exactly what the plant-test below proves.
    return bool(re.search(r'\bBearer\b', text, re.IGNORECASE))

BEFORE_WINDOW = 3
AFTER_WINDOW = 10

fails = []
scanned = 0

for relpath in files:
    if relpath == SELF:
        continue
    base = os.path.basename(relpath)
    if base == "CHANGELOG.md":
        continue
    path = os.path.join(repo_root, relpath)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        continue
    lines = raw.split('\n')
    ranges = fence_ranges(lines)
    scanned += 1

    for idx, line in enumerate(lines):
        for vm in VERB_RE.finditer(line):
            verb = vm.group(1)
            rest = line[vm.end():]
            # Look ahead up to 6 whitespace-delimited tokens for one that
            # contains "api/tasks/" (allows connector words like "to"/"via").
            toks = rest.split()
            url_tok = None
            for t in toks[:6]:
                if 'api/tasks/' in t:
                    url_tok = t
                    break
            if url_tok is None:
                continue

            # (d) wrapper-function call exemption: quoted arg, not curl -X.
            if strip_lead_quote(url_tok):
                before = line[:vm.start()].rstrip()
                if not (before.endswith('-X') or before.endswith('-X ')):
                    continue

            # Isolate the path after "api/tasks/" in this token.
            pos = url_tok.index('api/tasks/')
            path_after = strip_trail(url_tok[pos + len('api/tasks/'):])
            if not path_after:
                continue
            segs = path_after.split('/')
            first_seg = segs[0]

            # (a) ingest — HMAC path, never a candidate.
            if first_seg.rstrip('`\'"') .lower().startswith('ingest'):
                continue

            # (c) server source-path citation: Next.js bracket segment or an
            # explicit route.ts file reference.
            if first_seg.startswith('[') or 'route.ts' in url_tok:
                continue

            rest_segs = [s for s in segs[1:] if s]
            last_seg = strip_trail(rest_segs[-1]) if rest_segs else None

            is_candidate = False
            if verb == 'POST' and last_seg in SUFFIXES:
                is_candidate = True
            elif verb == 'PATCH' and (last_seg in SUFFIXES or not rest_segs):
                is_candidate = True

            if not is_candidate:
                continue

            blk = block_for_line(idx, ranges)
            if blk is not None:
                s, e = blk
                window_text = '\n'.join(lines[s:e + 1])
            elif relpath.endswith('.py') or relpath.endswith('.sh'):
                # .py/.sh implementation files document auth ONCE (a module
                # docstring's "AUTH PARITY" section, a shared _api()/cc_call()/
                # _post_json() helper) rather than repeating it beside every
                # call site or log-tag string literal — a tight local window
                # would false-positive on real, already-authenticated code
                # (e.g. templates/role-library/presentations/scripts/cc_board.py
                # documents Authorization at the top of the file and implements
                # it in a shared _request() ~150 lines from any given call).
                # A raw markdown-style example (### the .md case below) has no
                # such module-wide contract, so it keeps the tight window.
                window_text = raw
            else:
                s = max(0, idx - BEFORE_WINDOW)
                e = min(len(lines) - 1, idx + AFTER_WINDOW)
                window_text = '\n'.join(lines[s:e + 1])

            auth_ok = has_auth_mention(window_text)
            if not auth_ok and (relpath.endswith('.py') or relpath.endswith('.sh')):
                # (e) delegates to the shared authenticated board client → auth-aware.
                if DELEGATION_RE.search(raw):
                    auth_ok = True
            if not auth_ok:
                fails.append((relpath, idx + 1, line.strip()[:160]))

for relpath, lineno, snippet in fails:
    print(f"FAIL\t{relpath}:{lineno}\t{snippet}")

print(f"SCANNED\t{scanned}")
print(f"FAILCOUNT\t{len(fails)}")
PY
)"

FAILCOUNT="$(printf '%s\n' "$RESULT" | awk -F'\t' '$1=="FAILCOUNT"{print $2}')"
SCANNED="$(printf '%s\n' "$RESULT" | awk -F'\t' '$1=="SCANNED"{print $2}')"

if [ -z "$FAILCOUNT" ]; then
  red "guard-taskapi-auth-docs FAILED — python scanner produced no result (internal error)."
  exit 2
fi

if [ "$FAILCOUNT" -gt 0 ]; then
  echo "Flagged write-back examples with no Authorization/Bearer mention nearby:"
  echo ""
  printf '%s\n' "$RESULT" | awk -F'\t' '$1=="FAIL"{printf "  ✗ %s\n      %s\n", $2, $3}'
  echo ""
  red "guard-taskapi-auth-docs FAILED — $FAILCOUNT unauthenticated write-back example(s) across $SCANNED scanned file(s)."
  echo ""
  echo "REMEDY: add \`Authorization: Bearer \$MC_API_TOKEN\` directly under the"
  echo "POST/PATCH line inside its fenced code block (never on an /api/tasks/ingest"
  echo "call — that path is HMAC-signed, not Bearer), plus a short blockquote note"
  echo "explaining the 401 trap. See 23-ai-workforce-blueprint/templates/role-library/"
  echo "presentations/SOUL.md or universal-sops/CLIENT-WEBINAR-DECK-SOP.md for the"
  echo "canonical style. Never use \$OPENCLAW_GATEWAY_TOKEN here — it 401s this API."
  exit 1
fi

green "guard-taskapi-auth-docs PASS — all $SCANNED scanned file(s) with a /api/tasks/ mention carry Authorization/Bearer on every non-ingest write-back example."
exit 0
