#!/usr/bin/env bash
# 60-zhc-early-warning-system/scripts/scan-no-client-identifiers.sh
# ----------------------------------------------------------------------------
# MERGE-GATE STATIC SCAN #3 of 4 for Skill 60 (ZHC Early Warning System),
# adapted verbatim from Skill 59's four-scanner merge-gate family per Skill 60
# SKILL.md's "Reuse before rebuild" table (same static-scan mechanics, same
# 0/1/2/3/4 exit contract, same value-free doctrine). Proves NO client
# identifier or client personally identifiable information (PII) is present in
# the scanned tree -- enforces Skill 60 doctrine point 5, "NEVER commingle
# clients," and the fleet-wide "zero client PII in any repo" rule. This IS a
# product enforcement tool: pattern matching is the mechanism, by design.
#
# WHAT IT CATCHES:
#   email          an email literal whose domain is NOT an allowed infra/fleet/
#                  example domain (a hardcoded recipient is the exact legacy
#                  "hardcoded test inbox" defect this scanner family kills)
#   phone          a FORMATTED phone number (3-3-4 with separators / parens /
#                  leading +). Bare digit runs are NOT flagged, so Telegram
#                  numeric chat ids (which are CONFIGURATION) never trip it.
#   denylist#k     (optional) a fixed client token from an out-of-tree denylist
#                  file -- the PII-safe way to run the fleet-wide client-name
#                  grep. Reported by INDEX; the token is never printed.
#
# DOCTRINE: a matched email / phone / client token is PII and is NEVER printed.
# Findings report file:line and the CLASS only. Output is operator/CI-facing.
# A Google Drive folder / Shared-Drive root id is per-CLIENT delivery CONFIG (not an
# email/phone, so it never matches a PII class); no single operator root id is pinned
# (per-client Shared-Drive model). The denylist file is never committed and its
# contents are never echoed. The four scanners self-exclude.
#
# ALLOWED DOMAINS (never client PII): example.com/org/net, test, localhost,
# invalid, *.local, and infra/fleet: github.com, gitlab.com, google.com,
# googleapis.com, openai.com, openrouter.ai, w3.org, schema.org, blackceo.com,
# blackceoautomations.com, zerohumanworkforce.com. Extend with --allow-domain.
#
# SCOPE: (default) engine skill dir | --changed vs base | --fleet top-level | --root DIR
# Env/flag: CLIENT_IDENTIFIERS_FILE / --denylist FILE (out-of-tree client tokens)
# EXIT CODES (Skill 60 merge-gate; guard family, mirrored from Skill 59's
#   four-scanner family): 0 clean; 1 error; 2 usage; 3 dep (git for --changed,
#   or an unreadable denylist file); 4 VIOLATION (a client identifier present).
# ----------------------------------------------------------------------------
set -uo pipefail

EX_CLEAN=0; EX_ERR=1; EX_USAGE=2; EX_DEP=3; EX_VIOLATION=4

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ENGINE_DIR="$(cd "$SELF_DIR/.." && pwd)"
TAG="[scan-no-client-identifiers]"
SELF_NAMES="scan-no-secrets.sh scan-no-json-exports.sh scan-no-client-identifiers.sh guard-no-anthropic-runtime.py"

SELFTEST_TMP=""
_cleanup_selftest() { [ -n "${SELFTEST_TMP:-}" ] && rm -rf "$SELFTEST_TMP"; return 0; }
trap _cleanup_selftest EXIT

OPT_ROOT=""; OPT_SCOPE="engine"; OPT_BASE="origin/main"; OPT_JSON=0
OPT_INCLUDE_SELF="${SCAN_INCLUDE_SELF:-0}"; OPT_ALL_FILES="${SCAN_ALL_FILES:-0}"
DENYLIST_FILE="${CLIENT_IDENTIFIERS_FILE:-}"
EXTRA_ALLOW_DOMAINS=""

# Reserved documentation/test TLDs (RFC 6761/2606: .test .example .invalid
# .localhost) can NEVER be a real client domain -> always allowed. Plus infra/
# fleet/example domains.
ALLOW_DOMAINS_RE='(\.(test|example|invalid|localhost)$|example\.(com|org|net)|(^|@)(localhost|test|invalid)|\.local|github\.com|gitlab\.com|google\.com|googleapis\.com|gstatic\.com|openai\.com|openrouter\.ai|w3\.org|schema\.org|blackceo\.com|blackceoautomations\.com|zerohumanworkforce\.com)'

usage() {
    cat <<EOF
$TAG merge-gate scan: no client identifier / PII in the tree.
Usage: scan-no-client-identifiers.sh [SCOPE] [options]
  (no scope) engine dir | --changed | --fleet | --root DIR
  --base REF          base for --changed (default origin/main)
  --denylist FILE     out-of-tree fixed client tokens (name never printed)
  --allow-domain D    add an allowed email domain (repeatable)
  --json              machine-readable findings (file:line:class only)
  --self-test         plant a client identifier, confirm detection, exit
  -h|--help           this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --changed) OPT_SCOPE="changed"; shift ;;
        --fleet)   OPT_SCOPE="fleet"; shift ;;
        --root)    OPT_SCOPE="root"; OPT_ROOT="${2:-}"; shift 2 ;;
        --base)    OPT_BASE="${2:-}"; shift 2 ;;
        --denylist) DENYLIST_FILE="${2:-}"; shift 2 ;;
        --allow-domain) EXTRA_ALLOW_DOMAINS="$EXTRA_ALLOW_DOMAINS ${2:-}"; shift 2 ;;
        --json)    OPT_JSON=1; shift ;;
        --self-test) OPT_SELFTEST=1; shift ;;
        -h|--help) usage; exit $EX_CLEAN ;;
        *) echo "$TAG usage error: unknown argument: $1" >&2; usage >&2; exit $EX_USAGE ;;
    esac
done

EMAIL_RE='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
# formatted phone: optional +cc, then (NNN) or NNN, a separator, NNN, a separator, NNNN
PHONE_RE='(\+[0-9]{1,3}[ .-]?)?(\([0-9]{3}\)|[0-9]{3})[ .-][0-9]{3}[ .-][0-9]{4}'

is_self() {
    [ "$OPT_INCLUDE_SELF" -eq 1 ] && return 1
    local b; b="$(basename "$1")"
    case " $SELF_NAMES " in *" $b "*) return 0 ;; esac
    return 1
}

# is this matched LINE allowed? $1=line $2=class
is_allowlisted() {
    local line="$1" class="$2"
    # No single operator Drive root id is pinned (per-client Shared-Drive model); a
    # Drive folder id is not an email/phone, so it never matches a PII class anyway.
    if printf '%s' "$line" | grep -qiE '(<[A-Za-z0-9_.@-]+>|\{\{|placeholder|example|redacted|xxxx|dummy|sample|noreply|no-reply)'; then
        return 0
    fi
    if [ "$class" = "email" ]; then
        # allow if EVERY email on the line is in an allowed domain
        local emails allowed=1 e
        emails="$(printf '%s' "$line" | grep -oiE "$EMAIL_RE" || true)"
        [ -z "$emails" ] && return 0
        while IFS= read -r e; do
            [ -z "$e" ] && continue
            if printf '%s' "$e" | grep -qiE "$ALLOW_DOMAINS_RE"; then continue; fi
            local d ok=0
            for d in $EXTRA_ALLOW_DOMAINS; do
                [ -n "$d" ] && printf '%s' "$e" | grep -qiE "@${d//./\\.}$" && { ok=1; break; }
            done
            [ $ok -eq 1 ] || allowed=0
        done <<< "$emails"
        [ $allowed -eq 1 ] && return 0
    fi
    if [ "$class" = "phone" ]; then
        # 555-01xx is the reserved fictitious range; allow it
        printf '%s' "$line" | grep -qE '555[ .-]?01[0-9][0-9]' && return 0
    fi
    return 1
}

enumerate() {
    local root="$1" out="$2"; : > "$out"
    if [ "$OPT_SCOPE" = "changed" ]; then
        local top; top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)" || return $EX_DEP
        git -C "$top" rev-parse --verify "$OPT_BASE" >/dev/null 2>&1 || {
            echo "$TAG dependency unavailable: base ref '$OPT_BASE' not present (fetch it)" >&2; return $EX_DEP; }
        { git -C "$top" diff --name-only -z "$OPT_BASE" 2>/dev/null
          git -C "$top" diff --name-only -z 2>/dev/null
          git -C "$top" ls-files -z --others --exclude-standard 2>/dev/null; } \
        | while IFS= read -r -d '' f; do [ -f "$top/$f" ] && printf '%s\0' "$top/$f"; done >> "$out"
        return 0
    fi
    if [ "$OPT_ALL_FILES" -eq 0 ] && git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local top; top="$(git -C "$root" rev-parse --show-toplevel)"
        { git -C "$top" ls-files -z -- "$root" 2>/dev/null
          git -C "$top" ls-files -z --others --exclude-standard -- "$root" 2>/dev/null; } \
        | while IFS= read -r -d '' f; do [ -f "$top/$f" ] && printf '%s\0' "$top/$f"; done >> "$out"
    else
        find "$root" \( -name .git -o -name __pycache__ -o -name node_modules \
            -o -name .build-state -o -name .build-checkout \) -prune -o -type f -print0 >> "$out"
    fi
    return 0
}

FINDINGS_FILE=""
scan_class() {   # $1 class $2 pattern $3 listfile
    local class="$1" pattern="$2" listfile="$3"
    [ -s "$listfile" ] || return 0
    local raw; raw="$(xargs -0 grep -InHE -e "$pattern" < "$listfile" 2>/dev/null || true)"
    [ -z "$raw" ] && return 0
    while IFS= read -r m; do
        [ -z "$m" ] && continue
        local path="${m%%:*}" rest="${m#*:}"; local lineno="${rest%%:*}" content="${rest#*:}"
        is_self "$path" && continue
        is_allowlisted "$content" "$class" && continue
        printf '%s:%s:%s\n' "$path" "$lineno" "$class" >> "$FINDINGS_FILE"
    done <<< "$raw"
    return 0
}

scan_denylist() {   # $1 listfile ; returns EX_DEP if file unreadable
    [ -n "$DENYLIST_FILE" ] || return 0
    [ -r "$DENYLIST_FILE" ] || { echo "$TAG dependency unavailable: denylist file unreadable: $DENYLIST_FILE" >&2; return $EX_DEP; }
    local listfile="$1" idx=0 tok
    while IFS= read -r tok; do
        case "$tok" in ''|\#*) idx=$((idx+1)); continue ;; esac
        local raw; raw="$(xargs -0 grep -InHF -e "$tok" < "$listfile" 2>/dev/null || true)"
        if [ -n "$raw" ]; then
            while IFS= read -r m; do
                [ -z "$m" ] && continue
                local path="${m%%:*}" rest="${m#*:}"; local lineno="${rest%%:*}"
                is_self "$path" && continue
                printf '%s:%s:denylist#%s\n' "$path" "$lineno" "$idx" >> "$FINDINGS_FILE"
            done <<< "$raw"
        fi
        idx=$((idx+1))
    done < "$DENYLIST_FILE"
    return 0
}

run_scan() {
    local root="$1"
    [ -e "$root" ] || { echo "$TAG usage error: no such path: $root" >&2; return $EX_USAGE; }
    local listfile; listfile="$(mktemp "${TMPDIR:-/tmp}/scan-clientid-list.XXXXXX")"
    FINDINGS_FILE="$(mktemp "${TMPDIR:-/tmp}/scan-clientid-find.XXXXXX")"; : > "$FINDINGS_FILE"
    local rc; enumerate "$root" "$listfile"; rc=$?
    if [ $rc -ne 0 ]; then rm -f "$listfile" "$FINDINGS_FILE"; return $rc; fi

    scan_class "email" "$EMAIL_RE" "$listfile"
    scan_class "phone" "$PHONE_RE" "$listfile"
    scan_denylist "$listfile"; local drc=$?
    if [ $drc -eq $EX_DEP ]; then rm -f "$listfile" "$FINDINGS_FILE"; return $EX_DEP; fi

    local n=0
    if [ -s "$FINDINGS_FILE" ]; then
        sort -u "$FINDINGS_FILE" -o "$FINDINGS_FILE"; n="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
    fi

    if [ "$OPT_JSON" -eq 1 ]; then
        printf '{"scan":"no-client-identifiers","root":"%s","violations":%s,"findings":[' "$root" "$n"
        local first=1 line
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            local p="${line%%:*}" r="${line#*:}"; local l="${r%%:*}" c="${r##*:}"
            [ $first -eq 1 ] || printf ','; printf '{"file":"%s","line":%s,"class":"%s"}' "$p" "$l" "$c"; first=0
        done < "$FINDINGS_FILE"
        printf ']}\n'
    else
        if [ "$n" -eq 0 ]; then echo "$TAG CLEAN: no client identifier under $root"
        else
            echo "$TAG VIOLATION: $n client identifier(s) detected (value REDACTED):" >&2
            local line
            while IFS= read -r line; do
                [ -z "$line" ] && continue
                local p="${line%%:*}" r="${line#*:}"; local l="${r%%:*}" c="${r##*:}"
                echo "  $p:$l  [$c]" >&2
            done < "$FINDINGS_FILE"
        fi
    fi
    rm -f "$listfile" "$FINDINGS_FILE"
    [ "$n" -eq 0 ] && return $EX_CLEAN || return $EX_VIOLATION
}

self_test() {
    echo "$TAG self-test: planting a client identifier and confirming detection"
    local td; td="$(mktemp -d "${TMPDIR:-/tmp}/scan-clientid-selftest.XXXXXX")"
    SELFTEST_TMP="$td"
    local save_scope="$OPT_SCOPE"; OPT_SCOPE="root"; OPT_ALL_FILES=1

    # CLEAN: allowed infra/example emails + a placeholder + Telegram numeric id
    mkdir -p "$td/clean"
    { echo 'support = "help@example.com"   # example domain, allowed'
      echo 'remote  = "git@github.com"      # infra, allowed'
      echo 'recipient = "<PARTICIPANT_EMAIL>"  # placeholder, allowed'
      echo 'telegram_chat_id = 1234567890   # bare digits = configuration, not PII'; } > "$td/clean/config.py"
    if run_scan "$td/clean" >/dev/null 2>&1; then echo "  clean case: PASS (exit 0)"
    else echo "$TAG self-test FAIL: clean tree flagged" >&2; OPT_SCOPE="$save_scope"; return $EX_ERR; fi

    # DETECT (email): a synthetic client email on a non-allowed domain, built at runtime
    mkdir -p "$td/dirty"
    local dom; dom="northwind-$(printf 'client').co"
    printf 'hardcoded_recipient = "j.roe@%s"\n' "$dom" > "$td/dirty/leak.py"
    local out rc
    out="$(run_scan "$td/dirty" 2>&1)"; rc=$?
    if [ $rc -ne $EX_VIOLATION ] || ! printf '%s' "$out" | grep -q 'email'; then
        echo "$TAG self-test FAIL: planted email not detected (exit $rc)" >&2; OPT_SCOPE="$save_scope"; return $EX_ERR
    fi
    if printf '%s' "$out" | grep -q "j.roe@$dom"; then
        echo "$TAG self-test FAIL: the PII value leaked into output" >&2; OPT_SCOPE="$save_scope"; return $EX_ERR
    fi
    echo "  detect(email): PASS (exit 4, value redacted)"

    # DETECT (denylist): an out-of-tree token, matched by index, never printed
    local dlf="$td/denylist.txt"; printf '%s\n' "AcmeCo" > "$dlf"
    printf 'client_name = "AcmeCo Holdings"\n' > "$td/dirty2.py"; mkdir -p "$td/dl"; mv "$td/dirty2.py" "$td/dl/dirty2.py"
    local save_dl="$DENYLIST_FILE"; DENYLIST_FILE="$dlf"
    out="$(run_scan "$td/dl" 2>&1)"; rc=$?
    DENYLIST_FILE="$save_dl"; OPT_SCOPE="$save_scope"
    if [ $rc -eq $EX_VIOLATION ] && printf '%s' "$out" | grep -q 'denylist#' && ! printf '%s' "$out" | grep -q 'AcmeCo'; then
        echo "  detect(denylist): PASS (exit 4, token by index only)"
        echo "$TAG self-test: PASS"; return $EX_CLEAN
    fi
    echo "$TAG self-test FAIL: denylist path (exit $rc)" >&2
    return $EX_ERR
}

main() {
    if [ "${OPT_SELFTEST:-0}" = "1" ]; then self_test; return $?; fi
    local root
    case "$OPT_SCOPE" in
        engine)  root="$ENGINE_DIR" ;;
        fleet)   root="$(git -C "$ENGINE_DIR" rev-parse --show-toplevel 2>/dev/null)" \
                     || { echo "$TAG dependency unavailable: --fleet needs a git tree" >&2; return $EX_DEP; } ;;
        changed) root="$ENGINE_DIR" ;;
        root)    root="$OPT_ROOT"; [ -n "$root" ] || { echo "$TAG usage error: --root needs a DIR" >&2; return $EX_USAGE; } ;;
        *)       root="$ENGINE_DIR" ;;
    esac
    run_scan "$root"
}

main
exit $?
