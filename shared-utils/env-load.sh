#!/usr/bin/env bash
# env-load.sh — read a KEY=VALUE file WITHOUT sourcing it.
#
# WHY: `set -a; . "$file"; set +a` hands a client-owned file to the SHELL.
# Every line runs. A stray backtick, `$(...)`, or a bare word executes; a
# malformed line is echoed to the log on its way to failing, which is how a
# secrets file leaks into a receipt. And `. file` cannot represent a key the
# shell will not accept: `9R_GATEWAY_KEY=...` is a syntax error, so the WHOLE
# file stops loading at that line and every later key silently goes missing.
#
# This parses instead: only `^[A-Za-z_][A-Za-z0-9_]*=` lines become variables.
# Anything else is skipped and COUNTED, never printed -- the count tells an
# operator the file has junk without putting the junk in the log.
#
# Usage:
#   . shared-utils/env-load.sh
#   env_load /path/to/.env            # export every valid assignment
#   env_load_quiet /path/to/.env      # same, no summary line
#
# Returns 0 when the file was read (even with skipped lines), 1 when it does
# not exist or is unreadable. ENV_LOAD_SKIPPED holds the skipped-line count.

# shellcheck shell=bash

env_load_quiet() {
    local file="$1" line key val
    ENV_LOAD_SKIPPED=0
    ENV_LOAD_LOADED=0
    [ -n "$file" ] && [ -f "$file" ] && [ -r "$file" ] || return 1

    # `read -r` keeps backslashes literal; the `|| [ -n "$line" ]` tail picks up
    # a final line with no trailing newline.
    while IFS= read -r line || [ -n "$line" ]; do
        # strip a UTF-8 BOM on the first line, and leading whitespace
        line="${line#$'\xef\xbb\xbf'}"
        line="${line#"${line%%[![:space:]]*}"}"
        case "$line" in
            ''|'#'*) continue ;;
        esac
        # optional `export ` prefix
        case "$line" in
            'export '*) line="${line#export }" ;;
        esac
        key="${line%%=*}"
        # An identifier, or nothing. Never eval, never print the offending line.
        case "$key" in
            [A-Za-z_]*) ;;
            *) ENV_LOAD_SKIPPED=$((ENV_LOAD_SKIPPED + 1)); continue ;;
        esac
        case "$key" in
            *[!A-Za-z0-9_]*) ENV_LOAD_SKIPPED=$((ENV_LOAD_SKIPPED + 1)); continue ;;
        esac
        [ "$key" = "$line" ] && { ENV_LOAD_SKIPPED=$((ENV_LOAD_SKIPPED + 1)); continue; }

        val="${line#*=}"
        # strip one matching pair of surrounding quotes
        case "$val" in
            \"*\") val="${val#\"}"; val="${val%\"}" ;;
            \'*\') val="${val#\'}"; val="${val%\'}" ;;
        esac
        export "$key=$val"
        ENV_LOAD_LOADED=$((ENV_LOAD_LOADED + 1))
    done < "$file"
    return 0
}

env_load() {
    env_load_quiet "$1" || return 1
    if [ "${ENV_LOAD_SKIPPED:-0}" -gt 0 ]; then
        # Name the COUNT and the file, never the content.
        echo "  [env-load] $(basename "$1"): ${ENV_LOAD_LOADED} value(s) loaded, ${ENV_LOAD_SKIPPED} line(s) skipped (not KEY=VALUE, or KEY is not a shell identifier)" >&2
    fi
    return 0
}

# env_valid_key NAME — 0 when NAME is a usable shell identifier.
# Writers of .env lines call this BEFORE writing: a key like `9R_GATEWAY_KEY`
# cannot be exported and breaks `. file` for every line after it.
env_valid_key() {
    case "$1" in
        ''|[!A-Za-z_]*) return 1 ;;
        *[!A-Za-z0-9_]*) return 1 ;;
        *) return 0 ;;
    esac
}

# Runnable self-check: bash shared-utils/env-load.sh
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    _t="$(mktemp)"
    cat > "$_t" <<'EOF'
# comment
GOOD=1
export EXPORTED=two
QUOTED="three four"
SINGLE='five'
9R_GATEWAY_KEY=badkey
not an assignment
WITH-DASH=nope
EMPTY=
TRAILING=six
EOF
    env_load_quiet "$_t"
    _fail=0
    [ "$GOOD" = "1" ]            || { echo "FAIL GOOD=$GOOD"; _fail=1; }
    [ "$EXPORTED" = "two" ]      || { echo "FAIL EXPORTED=$EXPORTED"; _fail=1; }
    [ "$QUOTED" = "three four" ] || { echo "FAIL QUOTED=$QUOTED"; _fail=1; }
    [ "$SINGLE" = "five" ]       || { echo "FAIL SINGLE=$SINGLE"; _fail=1; }
    [ "${EMPTY-unset}" = "" ]    || { echo "FAIL EMPTY unset"; _fail=1; }
    [ "$TRAILING" = "six" ]      || { echo "FAIL TRAILING=$TRAILING (a bad key must not stop the file)"; _fail=1; }
    [ "$ENV_LOAD_SKIPPED" = "3" ] || { echo "FAIL skipped=$ENV_LOAD_SKIPPED expected 3"; _fail=1; }
    env_valid_key GOOD           || { echo "FAIL env_valid_key GOOD"; _fail=1; }
    env_valid_key 9R_GATEWAY_KEY && { echo "FAIL env_valid_key accepted 9R_GATEWAY_KEY"; _fail=1; }
    env_valid_key WITH-DASH      && { echo "FAIL env_valid_key accepted WITH-DASH"; _fail=1; }
    env_load_quiet /nonexistent/file && { echo "FAIL missing file returned 0"; _fail=1; }
    rm -f "$_t"
    [ "$_fail" = "0" ] && echo "env-load: all self-checks pass"
    exit "$_fail"
fi
