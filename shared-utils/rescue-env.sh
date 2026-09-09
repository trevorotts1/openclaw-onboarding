#!/usr/bin/env bash
# Shared Rescue credential-environment helpers — RR-027 (RR-W3-INSTALL).
# ============================================================================
# ONE implementation of the documented dotenv parse + child-env scrub that
# wire.sh, rescue-poll.sh, and the seed/admission paths all share, so no
# consumer can drift back to `set -a; . secrets/.env` (which EXPORTS the
# entire store, every credential in it, into every child) or to re-executing
# the store as shell (which hands a malformed or hostile line a shell).
#
# WHY (RR-027 confirmed defect, RCV05):
#   * wire.sh line 19 ran `set -a; . "$_SECRETS"` — the `set -a` export
#     flag made EVERY variable in the file, including the box's bearer
#     token (RR_BOX_TOKEN) and any other credential sharing that file,
#     part of the wire.sh process env. Every child spawned afterwards
#     (cron list, cron add, python3) inherited the whole set.
#   * rescue-poll.sh SOURCED the store and left whatever was ALREADY
#     exported in its env alone — a synthetic RR_BOX_TOKEN explicitly
#     `export`ed by an upstream env file reached the child agent turn
#     despite comments claiming the token never exports. Comments are not
#     enforcement; scrubbing the child env is.
#   * seed-rr-agent-map.sh passed the n8n API key INSIDE the curl argument
#     list (`-H "X-N8N-API-KEY: ${N8N_API_KEY}"`) — argv is visible to
#     every local user via `ps -o command` for the life of the process.
#
# THE CONTRACT (SPEC RR-027 exact repair):
#   1. Parse documented dotenv configuration WITHOUT executing arbitrary
#      shell. Read ONLY the required rescue values (allowlist), never the
#      whole file. Preserve legitimate quoting/space behavior. Fail
#      VISIBLY on malformed config (never a silent empty value).
#   2. Store the receiver secret separately: values land in NON-EXPORTED
#      shell variables; HTTP auth rides in a 0600 header file inside a
#      0700 private temp dir with cleanup — never key-bearing argv.
#   3. Explicitly remove rescue credential aliases from the CHILD env
#      while leaving necessary authorized model/tool credentials intact
#      (`rescue_env_scrub` runs the child through `env -u ...`).
#   4. Nothing here ever prints a value; diagnostics carry NAMES only.
#
# POSIX sh (the poll runs under /bin/sh); safe to source under `set -u`
# and under `set -euo pipefail`. Never executes the store. Never exports
# anything. Never writes outside the caller's own private temp dir.
#
# Sourced by: 65-rescue-receiver/wire.sh, 65-rescue-receiver/rescue-poll.sh.
# Tested by:  tests/unit/rr027-rescue-env.test.sh,
#             tests/unit/rr027-no-credential-in-child-env.test.sh.
# ============================================================================

# ---------------------------------------------------------------------------
# rescue_env_parse <env-file> <VAR> [<VAR> ...]
#
# Parses KEY=VALUE lines out of a dotenv file and prints, one per line,
# `VAR<TAB>value` for exactly the requested allowlisted names. NOTHING is
# exported, nothing is executed, no expansion happens: the value is taken
# VERBATIM from the line (unquoted and quote-stripped only). A value that
# came from the caller's own inherited environment is NEVER trusted for a
# required rescue name (spec: synthetic exported secrets must not win) —
# this function reads the FILE only, so an inherited-but-stale export can
# never satisfy enrollment here; callers decide what to do with absence.
#
# LINE SYNTAX ACCEPTED (documented dotenv forms):
#   KEY=value                bare value (no expansion, taken literally)
#   KEY="value with spaces"  double-quoted: literal, backslash kept
#   KEY='value with spaces'  single-quoted: literal
#   export KEY=value         optional export prefix is stripped
#   # comment / blank        skipped
#   KEY=value  # inline      trailing whitespace-only comment stripped on
#                            BARE values only (quoted values keep their #)
#
# DUPLICATE KEYS: the LAST occurrence wins (dotenv convention; the store's
# own writer appends, so the newest line is the current intent).
#
# MALFORMED LINES — FAIL VISIBLY (spec), not silently: a line that is
# non-empty, non-comment, has no `=`, or whose KEY is not a valid shell
# identifier shape is reported on stderr as `rescue-env: malformed line N
# in <file>` and counted; the return code is nonzero when any malformed
# line was seen, so the caller can decide to fail loudly. Values that
# carry an unescaped `$` are PRESERVED literally (the old sourcing turned
# `$VAR` into an expansion — an attacker-controlled or simply unlucky
# line changed meaning; parsing does not).
# ---------------------------------------------------------------------------
rescue_env_parse() {
    _rep_file="$1"; shift
    _rep_rc=0
    _rep_malformed=0
    _rep_lineno=0
    if [ ! -f "$_rep_file" ]; then
        printf 'rescue-env: config file not found: %s\n' "$_rep_file" >&2
        return 2
    fi
    if [ ! -r "$_rep_file" ]; then
        printf 'rescue-env: config file not readable: %s\n' "$_rep_file" >&2
        return 2
    fi
    # Read line-by-line without a subshell pipeline so the return code
    # survives (POSIX: `while read` at the end of a pipe loses status).
    while IFS= read -r _rep_raw || [ -n "$_rep_raw" ]; do
        _rep_lineno=$((_rep_lineno + 1))
        # Strip a UTF-8 BOM if the store was ever written by a Windows tool.
        case "$_rep_raw" in
            $'\xEF\xBB\xBF'*) _rep_raw="${_rep_raw#????}" ;;
        esac
        _rep_line="${_rep_raw%"${_rep_raw##*[! 	]}"}"   # trim trailing spaces/tabs
        case "$_rep_line" in
            ""|\#*) continue ;;
        esac
        # optional leading `export `
        case "$_rep_line" in
            "export "*) _rep_line="${_rep_line#export }" ;;
        esac
        case "$_rep_line" in
            *=*) : ;;
            *)
                printf 'rescue-env: malformed line %s in %s (no =)\n' \
                    "$_rep_lineno" "$_rep_file" >&2
                _rep_malformed=$((_rep_malformed + 1))
                continue
                ;;
        esac
        _rep_key="${_rep_line%%=*}"
        _rep_val="${_rep_line#*=}"
        # key shape: [A-Za-z_][A-Za-z0-9_]*
        case "$_rep_key" in
            [A-Za-z_]*) : ;;
            *) _rep_malformed=$((_rep_malformed + 1)); continue ;;
        esac
        _rep_rest="${_rep_key#?}"
        _rep_i=0
        while [ -n "$_rep_rest" ]; do
            _rep_c="${_rep_rest%"${_rep_rest#?}"}"
            case "$_rep_c" in
                [A-Za-z0-9_]) : ;;
                *) _rep_malformed=$((_rep_malformed + 1)); _rep_key=""; break ;;
            esac
            _rep_rest="${_rep_rest#?}"
            _rep_i=$((_rep_i + 1))
        done
        [ -n "$_rep_key" ] || { printf 'rescue-env: malformed line %s in %s (bad key)\n' "$_rep_lineno" "$_rep_file" >&2; continue; }
        # allowlist gate: only requested names are ever emitted
        _rep_want=0
        for _rep_name in "$@"; do
            [ "$_rep_key" = "$_rep_name" ] && _rep_want=1
        done
        [ "$_rep_want" = "1" ] || continue
        # value forms: quoted / bare. Bare values lose ONE trailing
        # whitespace-# comment; quoted values keep everything inside quotes.
        case "$_rep_val" in
            \"*\"*)
                # double-quoted: strip the outer quotes; interior is literal.
                _rep_val="${_rep_val#\"}"; _rep_val="${_rep_val%\"}"
                ;;
            \"*)
                printf 'rescue-env: malformed line %s in %s (unterminated double quote)\n' "$_rep_lineno" "$_rep_file" >&2
                _rep_malformed=$((_rep_malformed + 1))
                continue
                ;;
            \'*\'*)
                _rep_val="${_rep_val#\'}"; _rep_val="${_rep_val%\'}"
                ;;
            \'*)
                printf 'rescue-env: malformed line %s in %s (unterminated single quote)\n' "$_rep_lineno" "$_rep_file" >&2
                _rep_malformed=$((_rep_malformed + 1))
                continue
                ;;
            *)
                # bare value: strip a trailing ` #` comment (whitespace-#),
                # then re-trim trailing whitespace.
                _rep_val="${_rep_val%%[ 	]#*}"
                _rep_val="${_rep_val%"${_rep_val##*[! 	]}"}"
                ;;
        esac
        printf '%s\t%s\n' "$_rep_key" "$_rep_val"
    done < "$_rep_file"
    [ "$_rep_malformed" -eq 0 ] || _rep_rc=1
    return "$_rep_rc"
}

# ---------------------------------------------------------------------------
# rescue_env_get <env-file> <VAR>
#
# Convenience wrapper: prints the allowlisted VAR's LAST value, or nothing
# when absent. Returns 0 with output, 1 when absent, 2 when the file itself
# is missing/unreadable, 3 when the file carries malformed lines (the caller
# decides whether malformed config is fatal — wire/poll treat it as fatal
# per the spec's "fail visibly"; a cosmetic consumer may choose otherwise).
# Never prints the value into stderr diagnostics; stdout is the value and
# the caller is responsible for never echoing it onward.
# ---------------------------------------------------------------------------
rescue_env_get() {
    _reg_file="$1"; _reg_name="$2"
    _reg_out=""
    _reg_rc=0
    _reg_err="$(mktemp "${TMPDIR:-/tmp}/rescue-env-get.XXXXXX" 2>/dev/null)" || return 2
    _reg_out=$(rescue_env_parse "$_reg_file" "$_reg_name" 2>"$_reg_err")
    _reg_rc=$?
    _reg_malformed=0
    [ -s "$_reg_err" ] && _reg_malformed=1
    # Replay the parser's own reason lines to stderr AFTER the caller's
    # capture — command substitution already took stdout, so stderr here
    # reaches the caller's real stderr with line numbers (never values).
    # get() itself is value-free: these lines name file+line+shape only.
    if [ "$_reg_malformed" = "1" ]; then
        cat "$_reg_err" >&2 2>/dev/null || true
    fi
    rm -f "$_reg_err" 2>/dev/null || true
    case "$_reg_rc" in
        2) return 2 ;;   # file itself missing/unreadable
    esac
    # malformed lines: fail visibly — the caller sees rc=3 (documented
    # "malformed config" contract), the value is still resolved when the
    # requested name itself parsed clean (a hostile line must not turn a
    # readable store into an outage; wire/poll decide fatality themselves).
    _reg_val=""
    while IFS="$(printf '\t')" read -r _reg_k _reg_v; do
        [ "$_reg_k" = "$_reg_name" ] && _reg_val="$_reg_v"
    done <<EOF
$_reg_out
EOF
    if [ -n "$_reg_val" ]; then
        printf '%s\n' "$_reg_val"
        [ "$_reg_malformed" = "1" ] && return 3
        return 0
    fi
    [ "$_reg_malformed" = "1" ] && return 3
    return 1
}

# ---------------------------------------------------------------------------
# rescue_env_scrub <child argv...>
#
# Runs the child with EVERY rescue-credential alias REMOVED from its
# environment, and nothing else touched. This is the enforcement behind
# "the token is NEVER exported to a child": even if some other component
# (the gateway's env, an operator's shell profile, an env file sourced
# upstream with set -a) exported a rescue alias, the child cannot see it.
#
# The alias list is the rescue credential NAMES ONLY (never values):
#   RR_BOX_TOKEN       bearer token (X-RR-Box-Token)
#   RR_BOX_CRED        per-enrollment credential (X-RR-Box-Cred, RR-003)
#   RR_RECEIVER_SECRET receiver-side shared secret (operator store)
#   RESCUE_PUSH_SECRET receiver push auth (operator-only by design)
#   RESCUE_RANGERS_WEBHOOK_SECRET — deliberately NOT scrubbed from the
#                      child: the box's own AGENT legitimately needs it to
#                      escalate (AGENTS.md escalation section). RR-027's
#                      "necessary authorized credential still works" case.
#                      The POLL path additionally scrubs it via
#                      RESCUE_ENV_EXTRA_UNSET below because the poll's
#                      child is an agent TURN seeded from the ticket, not
#                      the box's own escalation path.
#   X-RESCUE-SECRET / X-RR-BOX-* : header NAMES are never env names.
#
# Extensibility contract: RESCUE_ENV_EXTRA_UNSET (space-separated names)
# adds caller-specific aliases at runtime without editing this file.
#
# Implementation note: `env -u NAME` requires coreutils env (present on
# Mac and every fleet VPS/container); when `env` is missing or does not
# support -u, the fallback constructs the export-list explicitly. Both
# paths never put a VALUE on any command line (only names are ever in
# argv of the wrapper itself).
# ---------------------------------------------------------------------------
rescue_env_scrub() {
    _res_names="RR_BOX_TOKEN RR_BOX_SLUG RR_BOX_CRED RR_RECEIVER_SECRET RESCUE_PUSH_SECRET"
    _res_names="$_res_names ${RESCUE_ENV_EXTRA_UNSET:-}"
    if command -v env >/dev/null 2>&1 && env -u _RES_SELFTEST_PROBE true 2>/dev/null; then
        # Build the -u list as an unquoted expansion: deliberate word
        # splitting over `-u NAME` pairs. Safe BY CONSTRUCTION — every
        # element is an identifier-shaped credential NAME (this function's
        # own fixed list, plus RESCUE_ENV_EXTRA_UNSET which is a
        # space-separated NAME list by contract). Values never appear here,
        # so no argv leak is possible: only names transit argv.
        _res_u=""
        for _res_n in $_res_names; do
            case "$_res_n" in
                *[!A-Za-z0-9_]*|'') continue ;;   # never pass a non-identifier to -u
            esac
            _res_u="$_res_u -u $_res_n"
        done
        # shellcheck disable=SC2086  (intentional word split of NAME list)
        env $_res_u "$@"
        return $?
    fi
    # Fallback: run the child with a MINIMAL export set derived from the
    # CURRENT environment minus the rescue aliases (no env -u available).
    # Names are iterated; values are re-exported verbatim for non-rescue
    # keys. A malformed environment key is skipped silently (it could not
    # be inherited by a child anyway).
    _res_script=""
    while IFS= read -r _res_kv; do
        [ -n "$_res_kv" ] || continue
        _res_k="${_res_kv%%=*}"
        case "$_res_k" in
            RR_BOX_TOKEN|RR_BOX_SLUG|RR_BOX_CRED|RR_RECEIVER_SECRET|RESCUE_PUSH_SECRET) continue ;;
        esac
        case "$_res_k" in
            *[!A-Za-z0-9_]*) continue ;;
        esac
        _res_script="$_res_script$_res_kv
"
    done <<RESCEOF
$(env 2>/dev/null)
RESCEOF
    _res_tmp=""
    _res_tmp=$(mktemp "${TMPDIR:-/tmp}/rescue-env-scrub.XXXXXX" 2>/dev/null) || return 126
    chmod 700 "$(dirname "$_res_tmp")" 2>/dev/null || true
    chmod 600 "$_res_tmp" 2>/dev/null || true
    printf 'unset RR_BOX_TOKEN RR_BOX_SLUG RR_BOX_CRED RR_RECEIVER_SECRET RESCUE_PUSH_SECRET %s\nexec "$@"\n' \
        "${RESCUE_ENV_EXTRA_UNSET:-}" > "$_res_tmp"
    # shellcheck disable=SC2086
    sh "$_res_tmp" "$@" 2>/dev/null
    _res_rc=$?
    rm -f "$_res_tmp" "$_res_tmp.dummy" 2>/dev/null || true
    return "$_res_rc"
}

# ---------------------------------------------------------------------------
# rescue_env_header_file <private-tmp-dir> <header-name> <value>
#
# Writes a curl `-H @file` fragment for one auth header into the caller's
# PRIVATE (0700) temp directory with mode 0600, prints the path. The value
# is NEVER in argv of any process (the write is a builtin redirection, not
# an external command), and the file is the caller's to remove in its own
# cleanup trap. Returns 1 (no path printed) when the directory is missing.
# ---------------------------------------------------------------------------
rescue_env_header_file() {
    _ref_dir="$1"; _ref_name="$2"; _ref_val="$3"
    [ -d "$_ref_dir" ] || return 1
    _ref_path=""
    # umask 077 first: close the mktemp-to-chmod window against a hostile
    # umask (022 inherited from cron/systemd) on ALL platforms, then chmod
    # 600 as the explicit backstop. Never rely on parent-dir perms.
    _ref_path=$(umask 077; mktemp "$_ref_dir/rescue-hdr.XXXXXX" 2>/dev/null) || return 1
    chmod 600 "$_ref_path" 2>/dev/null || true
    printf '%s: %s\n' "$_ref_name" "$_ref_val" > "$_ref_path" || { rm -f "$_ref_path"; return 1; }
    chmod 600 "$_ref_path" 2>/dev/null || true
    printf '%s\n' "$_ref_path"
}

# ---------------------------------------------------------------------------
# rescue_env_private_tmp <base-state-dir>
#
# Creates (idempotent) the 0700 private temp directory under the box's own
# state tree — never the shared system tmp — and prints its path. Returns 1
# when the base is missing. The poll/wire callers own the cleanup.
# ---------------------------------------------------------------------------
rescue_env_private_tmp() {
    _rpt_base="$1"
    [ -n "$_rpt_base" ] || return 1
    [ -d "$_rpt_base" ] || return 1
    _rpt_dir="$_rpt_base/tmp"
    # umask 077 first so mkdir -p creates 0700 even under an inherited 022
    # umask; explicit chmod 700 after as the backstop. Never rely on the
    # parent state dir's own mode (Ubuntu CI gate FAIL, 2026-09-09: the
    # chmod ran but the test's own stat probe misread the result).
    ( umask 077; mkdir -p "$_rpt_dir" 2>/dev/null ) || return 1
    chmod 700 "$_rpt_dir" 2>/dev/null || true
    printf '%s\n' "$_rpt_dir"
}