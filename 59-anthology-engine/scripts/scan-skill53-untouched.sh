#!/usr/bin/env bash
# 59-anthology-engine/scripts/scan-skill53-untouched.sh
# ----------------------------------------------------------------------------
# MERGE-GATE STATIC SCAN #4 of 4 (Unit W2.8). Proves Skill 53 (the book-writer)
# is UNTOUCHED: no file under its directory differs from the base ref. Skill 53
# is NOT deprecated and NOT touched -- executing the stale "deprecate BookWriter"
# directive is a scored build failure (SPEC Section 14 / sibling boundary;
# CHECKLIST Part C item 5; WAVE-PLAN W2.8 + Wave 6 checks). The ONLY sanctioned
# retirement is the legacy n8n stack, never this skill.
#
# MECHANISM: a READ-ONLY git diff of the Skill 53 path between the base ref
# (default origin/main) and the branch working tree, PLUS any new untracked file
# under the path. ANY added / modified / deleted / renamed file is a violation.
# It also guards the silent-pass hole: if the path is absent from BOTH the base
# and the working tree it reports a dependency error rather than a false clean.
#
# This scanner performs NO write git operation on the build checkout (no commit,
# branch, push, or fetch) -- only read-only diff/ls-tree/ls-files/rev-parse. Its
# self-test builds a THROWAWAY git repo in a mktemp dir (a fixture, never the
# build checkout) to force-observe both a clean pass and a real detection.
#
# DOCTRINE: changed PATHS (skill file names, not PII) are printed so the operator
# can see what was touched; file CONTENTS are never shown.
#
# OPTIONS:
#   --base REF   base ref to diff against (default origin/main)
#   --path P     the Skill 53 dir relative to the repo root (default 53-book-writer)
#   --repo DIR   repo root (default: the git top-level containing this script)
#   --json       machine-readable result
#   --self-test  build a throwaway repo, confirm detection, exit
#   -h|--help    this help
#
# EXIT CODES (SPEC 3.4 house convention; guard family "0 clean; 4 violation"):
#   0  clean (Skill 53 byte-for-byte identical to base)
#   1  unexpected error
#   2  usage error
#   3  dependency unavailable (git missing / not a git repo / base ref absent /
#      path absent from both base and worktree)
#   4  VIOLATION: at least one Skill 53 file differs from base
# ----------------------------------------------------------------------------
set -uo pipefail

EX_CLEAN=0; EX_ERR=1; EX_USAGE=2; EX_DEP=3; EX_VIOLATION=4

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TAG="[scan-skill53-untouched]"

SELFTEST_TMP=""
_cleanup_selftest() { [ -n "${SELFTEST_TMP:-}" ] && rm -rf "$SELFTEST_TMP"; return 0; }
trap _cleanup_selftest EXIT

OPT_BASE="origin/main"
OPT_PATH="53-book-writer"
OPT_REPO=""
OPT_JSON=0

usage() {
    cat <<EOF
$TAG merge-gate scan: Skill 53 (book-writer) UNTOUCHED vs the base ref.
Usage: scan-skill53-untouched.sh [options]
  --base REF   base ref (default origin/main)
  --path P     Skill 53 dir (default 53-book-writer)
  --repo DIR   repo root (default: git top-level of this script)
  --json       machine-readable result
  --self-test  throwaway-repo self-test, then exit
  -h|--help    this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --base) OPT_BASE="${2:-}"; shift 2 ;;
        --path) OPT_PATH="${2:-}"; shift 2 ;;
        --repo) OPT_REPO="${2:-}"; shift 2 ;;
        --json) OPT_JSON=1; shift ;;
        --self-test) OPT_SELFTEST=1; shift ;;
        -h|--help) usage; exit $EX_CLEAN ;;
        *) echo "$TAG usage error: unknown argument: $1" >&2; usage >&2; exit $EX_USAGE ;;
    esac
done

# Core check. $1=repo root, $2=base ref, $3=path. Echoes findings; returns code.
check_untouched() {
    local top="$1" base="$2" path="$3"

    command -v git >/dev/null 2>&1 || { echo "$TAG dependency unavailable: git not installed" >&2; return $EX_DEP; }
    top="$(git -C "$top" rev-parse --show-toplevel 2>/dev/null)" || {
        echo "$TAG dependency unavailable: not a git repository: $1" >&2; return $EX_DEP; }
    git -C "$top" rev-parse --verify "$base" >/dev/null 2>&1 || {
        echo "$TAG dependency unavailable: base ref '$base' not present (fetch it; do not merge blind)" >&2; return $EX_DEP; }

    local base_has changes untracked
    base_has="$(git -C "$top" ls-tree -r --name-only "$base" -- "$path" 2>/dev/null | head -1)"
    changes="$(git -C "$top" diff --name-status "$base" -- "$path" 2>/dev/null)"
    untracked="$(git -C "$top" ls-files --others --exclude-standard -- "$path" 2>/dev/null)"

    # Guard the silent-pass hole: path must exist somewhere.
    if [ -z "$base_has" ]; then
        if [ -n "$changes$untracked" ] || [ -d "$top/$path" ]; then
            # present now but not in base -> a wholesale ADD is a touch
            :
        else
            echo "$TAG dependency unavailable: '$path' not found in base ('$base') or worktree; cannot verify" >&2
            return $EX_DEP
        fi
    fi

    if [ -z "$changes" ] && [ -z "$untracked" ] && [ -n "$base_has" ]; then
        if [ "$OPT_JSON" -eq 1 ]; then
            printf '{"scan":"skill53-untouched","base":"%s","path":"%s","clean":true,"changes":[]}\n' "$base" "$path"
        else
            echo "$TAG CLEAN: '$path' is byte-for-byte identical to '$base' (no add/modify/delete/rename)"
        fi
        return $EX_CLEAN
    fi

    # VIOLATION
    if [ "$OPT_JSON" -eq 1 ]; then
        printf '{"scan":"skill53-untouched","base":"%s","path":"%s","clean":false,"changes":[' "$base" "$path"
        local first=1 st nm line
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            st="$(printf '%s' "$line" | awk '{print $1}')"; nm="$(printf '%s' "$line" | cut -f2-)"
            [ $first -eq 1 ] || printf ','; printf '{"status":"%s","file":"%s"}' "$st" "$nm"; first=0
        done <<< "$changes"
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            [ $first -eq 1 ] || printf ','; printf '{"status":"A?","file":"%s"}' "$line"; first=0
        done <<< "$untracked"
        printf ']}\n'
    else
        echo "$TAG VIOLATION: Skill 53 has been TOUCHED (SPEC 14 sibling boundary): " >&2
        [ -n "$changes" ] && while IFS= read -r line; do [ -n "$line" ] && echo "  $line" >&2; done <<< "$changes"
        [ -n "$untracked" ] && while IFS= read -r line; do [ -n "$line" ] && echo "  A?	$line (untracked)" >&2; done <<< "$untracked"
    fi
    return $EX_VIOLATION
}

self_test() {
    echo "$TAG self-test: building a throwaway repo to force-observe detection"
    command -v git >/dev/null 2>&1 || { echo "$TAG self-test: git unavailable" >&2; return $EX_DEP; }
    local td; td="$(mktemp -d "${TMPDIR:-/tmp}/scan-s53-selftest.XXXXXX")"
    SELFTEST_TMP="$td"
    # Isolate from any global/system git config, identity, hooks, signing.
    local G=(git -C "$td" -c user.email=selftest@example.com -c user.name=selftest -c commit.gpgsign=false -c init.defaultBranch=main)
    export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_TERMINAL_PROMPT=0

    "${G[@]}" init -q "$td" >/dev/null 2>&1 || { git -c init.defaultBranch=main init -q "$td" >/dev/null 2>&1; }
    mkdir -p "$td/53-book-writer" "$td/59-anthology-engine"
    printf 'the untouched book-writer\n' > "$td/53-book-writer/SKILL.md"
    printf 'engine v1\n' > "$td/59-anthology-engine/marker.txt"
    "${G[@]}" add -A >/dev/null 2>&1
    "${G[@]}" commit -qm base >/dev/null 2>&1
    local base_sha; base_sha="$("${G[@]}" rev-parse HEAD 2>/dev/null)"

    # CLEAN: change ONLY the engine, leave Skill 53 alone
    printf 'engine v2\n' > "$td/59-anthology-engine/marker.txt"
    "${G[@]}" add -A >/dev/null 2>&1; "${G[@]}" commit -qm engine-change >/dev/null 2>&1
    local out rc
    out="$(OPT_JSON=0; check_untouched "$td" "$base_sha" "53-book-writer" 2>&1)"; rc=$?
    if [ $rc -ne $EX_CLEAN ]; then
        echo "$TAG self-test FAIL: untouched Skill 53 wrongly flagged (exit $rc)" >&2
        printf '%s\n' "$out" >&2; return $EX_ERR
    fi
    echo "  clean case: PASS (exit 0, Skill 53 identical while engine changed)"

    # DETECT: now touch Skill 53
    printf 'the DEPRECATED book-writer (illegal edit)\n' >> "$td/53-book-writer/SKILL.md"
    out="$(check_untouched "$td" "$base_sha" "53-book-writer" 2>&1)"; rc=$?
    if [ $rc -ne $EX_VIOLATION ]; then
        echo "$TAG self-test FAIL: a touched Skill 53 was not detected (exit $rc)" >&2
        printf '%s\n' "$out" >&2; return $EX_ERR
    fi
    if ! printf '%s' "$out" | grep -q '53-book-writer/SKILL.md'; then
        echo "$TAG self-test FAIL: violation did not name the touched file" >&2; return $EX_ERR
    fi
    echo "  detect(modify): PASS (exit 4, named the touched file)"

    # DETECT: an untracked NEW file under the path is also a touch
    "${G[@]}" checkout -q -- 53-book-writer/SKILL.md >/dev/null 2>&1
    printf 'sneaked in\n' > "$td/53-book-writer/EXTRA.md"
    out="$(check_untouched "$td" "$base_sha" "53-book-writer" 2>&1)"; rc=$?
    if [ $rc -eq $EX_VIOLATION ] && printf '%s' "$out" | grep -q 'EXTRA.md'; then
        echo "  detect(untracked-add): PASS (exit 4)"
        echo "$TAG self-test: PASS"; return $EX_CLEAN
    fi
    echo "$TAG self-test FAIL: untracked add not detected (exit $rc)" >&2
    return $EX_ERR
}

main() {
    if [ "${OPT_SELFTEST:-0}" = "1" ]; then self_test; return $?; fi
    local repo="$OPT_REPO"
    [ -n "$repo" ] || repo="$SELF_DIR"
    check_untouched "$repo" "$OPT_BASE" "$OPT_PATH"
}

main
exit $?
