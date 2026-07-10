#!/usr/bin/env bash
# 61-loop-protection-system/scripts/scan-no-secrets.sh
# ----------------------------------------------------------------------------
# MERGE-GATE STATIC SCAN #1 of 4 for Loop Protection System (Skill 61),
# adapted verbatim from Skill 59's four-scanner merge-gate family per Skill 61
# SKILL.md's "Reuse before rebuild" table (same static-scan mechanics, same
# 0/1/2/3/4 exit contract, same value-free doctrine). Proves NO secret VALUE is
# present anywhere in the scanned tree -- the static enforcement of Skill 61
# doctrine point 3: "NEVER print, echo, grep, or paste a secret VALUE.
# Credentials are reported by LABEL and POSTURE only (SET / NOT SET /
# signed-in / signed-out). A leaked-secret finding reports file:line and CLASS
# only; the value is never reproduced, not even partially." This IS a product
# enforcement tool: pattern matching is the mechanism, by design (the doctrine
# that forbids grep-for-judgment is about human reasoning, not about the
# guardrail's own detector).
#
# WHAT IT CATCHES (high-precision provider-key SHAPES, on by default):
#   provider_sk    sk- / sk-proj- / sk-ant- / sk-or-v1- vendor API-key shapes
#                  (any leaked provider key is a secret, so all are detected)
#   caf_pit        Convert and Flow private integration token (pit-...)
#   google_api     AIza... Google API keys
#   aws_akid       AKIA... AWS access-key ids
#   slack_token    xoxb/xoxp/... Slack tokens
#   github_pat     ghp_/gho_/github_pat_ GitHub tokens
#   private_key    -----BEGIN ... PRIVATE KEY----- PEM blocks
#   jwt            eyJ....eyJ....sig JSON Web Tokens
#   bearer_literal a literal token in an Authorization: Bearer header (the exact
#                  hardcoded-bearer-token defect class the scanner family retires)
# WITH --strict it ALSO runs a fuzzy class:
#   assign_secret  a secret-named variable assigned a hardcoded quoted literal
#                  (api_key/secret/token/password/... = "….16+ chars…")
#
# DOCTRINE (binding):
#   * A matched secret VALUE is NEVER printed. Findings report file:line and the
#     matched CLASS only. Output is operator/CI-facing (operator-verbose is fine;
#     "move in silence" is a CLIENT-facing rule) and never carries a value.
#   * A Google Drive folder / Shared-Drive root id is PER-CLIENT delivery CONFIG
#     (BlackCEO hosts one Shared Drive per client; the id is resolved per box from
#     the GOOGLE_DRIVE_ROOT_FOLDER label), neither a secret nor client PII. No single
#     operator root id is pinned here (per-client Shared-Drive model, 2026-07-09): a
#     bare Drive-id shape carries none of the provider-key prefixes below, so it never
#     matches a secret class in the first place.
#   * Values referenced BY LABEL (env var / os.getenv / process.env / ${VAR}) or
#     written as placeholders (<...>, {{...}}, XXXX, REDACTED, EXAMPLE, ...) are
#     allowed; only a hardcoded literal VALUE fails.
#   * The four merge-gate scanners themselves are enforcement tooling whose
#     pattern DEFINITIONS are allowed (exactly as a runtime provider-deny guard
#     exempts its own deny regexes); they are excluded from the scanned set.
#
# SCOPE (choose one):
#   (default)      the engine skill dir (this script's parent) -- the skill's home
#   --changed      only files changed vs the base ref (BEST for a branch merge
#                  gate: high signal, zero pre-existing fleet noise)
#   --fleet        the whole git top-level (a fleet-wide pass)
#   --root DIR     an explicit directory
#
# EXIT CODES (Skill 61 merge-gate house convention, mirrored from Skill 59's
# four-scanner family; guard family = "0 clean; 4 violation"):
#   0  clean (no secret value found)   1  unexpected error
#   2  usage error                     3  dependency unavailable (git for --changed)
#   4  VIOLATION: at least one secret value detected
#   (5 read-back mismatch: not used by a static scan)
# ----------------------------------------------------------------------------
set -uo pipefail

EX_CLEAN=0; EX_ERR=1; EX_USAGE=2; EX_DEP=3; EX_VIOLATION=4

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ENGINE_DIR="$(cd "$SELF_DIR/.." && pwd)"

TAG="[scan-no-secrets]"

SELFTEST_TMP=""
_cleanup_selftest() { [ -n "${SELFTEST_TMP:-}" ] && rm -rf "$SELFTEST_TMP"; return 0; }
trap _cleanup_selftest EXIT

# ---- the four merge-gate scanner basenames (self-exclusion) ----------------
SELF_NAMES="scan-no-secrets.sh scan-no-json-exports.sh scan-no-client-identifiers.sh guard-no-anthropic-runtime.py"

# ---- options ---------------------------------------------------------------
OPT_ROOT=""
OPT_SCOPE="engine"     # engine | changed | fleet | root
OPT_BASE="origin/main"
OPT_STRICT=0
OPT_JSON=0
OPT_INCLUDE_SELF="${SCAN_INCLUDE_SELF:-0}"
OPT_ALL_FILES="${SCAN_ALL_FILES:-0}"

usage() {
    cat <<EOF
$TAG merge-gate scan: no secret VALUE anywhere in the tree.
Usage: scan-no-secrets.sh [SCOPE] [options]
  (no scope)        scan the engine skill dir ($ENGINE_DIR)
  --changed         scan only files changed vs --base (default origin/main)
  --fleet           scan the whole git top-level
  --root DIR        scan an explicit directory
  --base REF        base ref for --changed (default origin/main)
  --strict          also run the fuzzy assign_secret class
  --json            emit machine-readable findings (file:line:class only)
  --self-test       plant a violation, confirm detection, and exit
  -h | --help       this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --changed)   OPT_SCOPE="changed"; shift ;;
        --fleet)     OPT_SCOPE="fleet"; shift ;;
        --root)      OPT_SCOPE="root"; OPT_ROOT="${2:-}"; shift 2 ;;
        --base)      OPT_BASE="${2:-}"; shift 2 ;;
        --strict)    OPT_STRICT=1; shift ;;
        --json)      OPT_JSON=1; shift ;;
        --self-test) OPT_SELFTEST=1; shift ;;
        -h|--help)   usage; exit $EX_CLEAN ;;
        *) echo "$TAG usage error: unknown argument: $1" >&2; usage >&2; exit $EX_USAGE ;;
    esac
done

# ---- patterns (ERE; portable to BSD grep -E) -------------------------------
# name<TAB>pattern ; grep -iE for assign_secret only (marked with a leading '!').
strong_patterns() {
    cat <<'PATTERNS'
provider_sk	sk-(proj-|ant-|or-v1-)?[A-Za-z0-9_-]{20,}
caf_pit	pit-[A-Za-z0-9]{20,}
google_api	AIza[0-9A-Za-z_-]{35}
aws_akid	AKIA[0-9A-Z]{16}
slack_token	xox[abprs]-[0-9A-Za-z-]{10,}
github_pat	(gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{50,})
private_key	-----BEGIN [A-Z ]*PRIVATE KEY-----
jwt	eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}
bearer_literal	[Aa]uthorization["' ]*[:=][ "']*[Bb]earer[ ]+[A-Za-z0-9._-]{20,}
PATTERNS
}
# fuzzy class (only with --strict); scanned case-insensitively
assign_secret_pattern='(api[_-]?key|secret|token|password|passwd|pwd|client[_-]?secret|access[_-]?key|auth[_-]?token)["'"'"' ]*[:=][ ]*["'"'"'][^"'"'"']{16,}["'"'"']'

# A token with an ascending consecutive-codepoint run (>=7: abcdefg / 0123456)
# or a single-char repeat (>=6: AAAAAA) is a SYNTHETIC detector example, never a
# real high-entropy key. This mirrors caf_credential_gate._has_sequential_run and
# is exactly how the sibling enforcement scripts mark their own test fixtures.
_has_lowentropy_run() {
    local t="$1"
    local n=${#t}
    local i a b run=1 rep=1
    [ "$n" -lt 6 ] && return 1
    for ((i=1;i<n;i++)); do
        printf -v a '%d' "'${t:i-1:1}" 2>/dev/null || return 1
        printf -v b '%d' "'${t:i:1}" 2>/dev/null || return 1
        if [ $((b-a)) -eq 1 ]; then run=$((run+1)); [ $run -ge 7 ] && return 0; else run=1; fi
        if [ "$b" -eq "$a" ]; then rep=$((rep+1)); [ $rep -ge 6 ] && return 0; else rep=1; fi
    done
    return 1
}

# ---- allow-list: is this matched LINE a false positive? --------------------
# $1 = full matched line (kept in-process, NEVER printed), $2 = class,
# $3 = the class pattern (to extract the matched token), $4 = ci flag
is_allowlisted() {
    local line="$1" class="$2" pattern="$3" ci="$4"
    # NOTE: no single operator Drive root id is pinned (per-client Shared-Drive model).
    # A bare Google Drive folder id carries no provider-key prefix, so it never matches
    # a secret class here in the first place -- nothing to allowlist.
    # explicit placeholder / synthetic markers anywhere on the line
    if printf '%s' "$line" | grep -qiE '(<[A-Za-z0-9_.-]+>|\{\{|\}\}|%[A-Za-z0-9_]+%|xxxx|redacted|placeholder|changeme|your[-_]?(api[-_]?)?key|dummy|example|sample|fake[-_]?|synthetic|not[-_]?a[-_]?real|unit[-_]?test|no[-_]?secret)'; then
        return 0
    fi
    if [ "$class" = "assign_secret" ]; then
        # references BY LABEL are not a value
        if printf '%s' "$line" | grep -qiE '(os\.environ|os\.getenv|getenv|process\.env|env\[|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|by label|not set\b|"set"|read_secret|load_secret|from_env|secretmanager)'; then
            return 0
        fi
        # a real secret VALUE is a COMPLETE quoted token with NO space and a 16+
        # contiguous alphanumeric run. Prose values (spaces) and dictionary-hyphen
        # values (no 16-run) are neither -- and a long camelCase identifier buried
        # inside a prose value is not its own quoted value, so it never trips this.
        local dq sq qre q hit=0
        dq='"'; sq="'"
        qre="${dq}[^${dq}]{16,}${dq}|${sq}[^${sq}]{16,}${sq}"
        while IFS= read -r q; do
            [ -z "$q" ] && continue
            case "$q" in *" "*) continue ;; esac
            printf '%s' "$q" | grep -qE '[A-Za-z0-9]{16,}' && { hit=1; break; }
        done < <(printf '%s' "$line" | grep -oE "$qre")
        [ "$hit" -eq 1 ] && return 1
        return 0
    fi
    # strong provider classes: allow a synthetic low-entropy example token.
    # private_key (a raw PEM header) is NEVER entropy-allowed.
    if [ "$class" != "private_key" ]; then
        local tok; tok="$(printf '%s' "$line" | grep -oiE "$pattern" | head -1)"
        if [ -n "$tok" ] && _has_lowentropy_run "$tok"; then return 0; fi
    fi
    return 1
}

# ---- enumerate the files to scan into a NUL list ($1 = out file) -----------
FILES_LIST=""
enumerate() {
    local root="$1" out="$2"
    : > "$out"
    if [ "$OPT_SCOPE" = "changed" ]; then
        local top; top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)" || return $EX_DEP
        git -C "$top" rev-parse --verify "$OPT_BASE" >/dev/null 2>&1 || {
            echo "$TAG dependency unavailable: base ref '$OPT_BASE' not present (fetch it)" >&2; return $EX_DEP; }
        # changed vs base (committed) plus anything uncommitted, NUL-safe
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

# ---- true if a path is one of the four scanners (self-exclusion) -----------
is_self() {
    [ "$OPT_INCLUDE_SELF" -eq 1 ] && return 1
    local b; b="$(basename "$1")"
    case " $SELF_NAMES " in *" $b "*) return 0 ;; esac
    return 1
}

# ---- run one class over the file list, collecting redacted findings --------
# writes "path:line:class" lines to the findings accumulator ($FINDINGS_FILE)
scan_class() {
    local class="$1" pattern="$2" ci="$3" listfile="$4"
    [ -s "$listfile" ] || return 0
    local gflags="-InHE"
    [ "$ci" = "1" ] && gflags="-InHEi"
    local raw
    raw="$(xargs -0 grep $gflags -e "$pattern" < "$listfile" 2>/dev/null || true)"
    [ -z "$raw" ] && return 0
    # each raw line: path:lineno:content  (content kept local, never emitted)
    while IFS= read -r m; do
        [ -z "$m" ] && continue
        local path="${m%%:*}" rest="${m#*:}"
        local lineno="${rest%%:*}" content="${rest#*:}"
        is_self "$path" && continue
        is_allowlisted "$content" "$class" "$pattern" "$ci" && continue
        printf '%s:%s:%s\n' "$path" "$lineno" "$class" >> "$FINDINGS_FILE"
    done <<< "$raw"
    return 0
}

FINDINGS_FILE=""
run_scan() {
    local root="$1"
    [ -e "$root" ] || { echo "$TAG usage error: no such path: $root" >&2; return $EX_USAGE; }
    local listfile; listfile="$(mktemp "${TMPDIR:-/tmp}/scan-secrets-list.XXXXXX")"
    FINDINGS_FILE="$(mktemp "${TMPDIR:-/tmp}/scan-secrets-find.XXXXXX")"
    : > "$FINDINGS_FILE"
    local rc; enumerate "$root" "$listfile"; rc=$?
    if [ $rc -ne 0 ]; then rm -f "$listfile" "$FINDINGS_FILE"; return $rc; fi

    local name pat
    while IFS="$(printf '\t')" read -r name pat; do
        [ -z "$name" ] && continue
        scan_class "$name" "$pat" 0 "$listfile"
    done < <(strong_patterns)
    if [ "$OPT_STRICT" -eq 1 ]; then
        scan_class "assign_secret" "$assign_secret_pattern" 1 "$listfile"
    fi

    # dedup findings
    local n=0
    if [ -s "$FINDINGS_FILE" ]; then
        sort -u "$FINDINGS_FILE" -o "$FINDINGS_FILE"
        n="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
    fi

    if [ "$OPT_JSON" -eq 1 ]; then
        printf '{"scan":"no-secrets","root":"%s","violations":%s,"findings":[' "$root" "$n"
        local first=1 line
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            local p="${line%%:*}" r="${line#*:}"; local l="${r%%:*}" c="${r##*:}"
            [ $first -eq 1 ] || printf ','
            printf '{"file":"%s","line":%s,"class":"%s"}' "$p" "$l" "$c"; first=0
        done < "$FINDINGS_FILE"
        printf ']}\n'
    else
        if [ "$n" -eq 0 ]; then
            echo "$TAG CLEAN: no secret value found under $root"
        else
            echo "$TAG VIOLATION: $n hardcoded secret value(s) detected (value REDACTED):" >&2
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

# ---- self-test: force-observe BOTH a clean pass and a real detection -------
self_test() {
    echo "$TAG self-test: planting a synthetic secret and confirming detection"
    local td; td="$(mktemp -d "${TMPDIR:-/tmp}/scan-secrets-selftest.XXXXXX")"
    SELFTEST_TMP="$td"
    local save_scope="$OPT_SCOPE"; OPT_SCOPE="root"; OPT_ALL_FILES=1

    # CLEAN dir: a label reference, a placeholder, and a PER-CLIENT Drive root id
    # (a Shared-Drive id literal carries no provider-key prefix, so it is never a
    # secret -- proves the per-client model needs no operator-id pin to stay clean).
    mkdir -p "$td/clean"
    {
        echo 'api_key = os.getenv("PROVIDER_API_KEY")   # by label only'
        echo 'authorization = "Bearer <TOKEN_PLACEHOLDER>"'
        echo 'drive_root_folder = "0AKp8Qw3Rt5Yu8Io2Pk4Lz1Vt6Bn0Cy7"   # per-client Shared Drive id, delivery config'
    } > "$td/clean/config.py"
    OPT_STRICT=1
    if run_scan "$td/clean" >/dev/null 2>&1; then
        echo "  clean case: PASS (exit 0)"
    else
        echo "$TAG self-test FAIL: clean tree was flagged" >&2; OPT_SCOPE="$save_scope"; return $EX_ERR
    fi

    # DETECT dir: a synthetic HIGH-ENTROPY OpenAI-shaped key (no ascending/repeat
    # run, so it reads as a real leak, not a detector example) built at runtime,
    # plus a raw PEM header (always flagged).
    mkdir -p "$td/dirty"
    local fake_sk="sk-9f3Kx7Qm2Lp8Rt4Wv6Bn1Zc5Hd0Js3GyQwEr"
    {
        printf 'OPENAI_API_KEY = "%s"\n' "$fake_sk"
        echo '-----BEGIN RSA PRIVATE KEY-----'
    } > "$td/dirty/leak.py"
    local out rc
    out="$(run_scan "$td/dirty" 2>&1)"; rc=$?
    OPT_SCOPE="$save_scope"
    if [ $rc -eq $EX_VIOLATION ]; then
        # prove the value itself did not leak into output
        if printf '%s' "$out" | grep -q "$fake_sk"; then
            echo "$TAG self-test FAIL: the secret VALUE leaked into output" >&2; return $EX_ERR
        fi
        echo "  detect case: PASS (exit 4, value redacted)"
        echo "$TAG self-test: PASS"
        return $EX_CLEAN
    fi
    echo "$TAG self-test FAIL: planted secret not detected (exit $rc)" >&2
    return $EX_ERR
}

# ---- main ------------------------------------------------------------------
main() {
    if [ "${OPT_SELFTEST:-0}" = "1" ]; then self_test; return $?; fi
    local root
    case "$OPT_SCOPE" in
        engine)  root="$ENGINE_DIR" ;;
        fleet)   root="$(git -C "$ENGINE_DIR" rev-parse --show-toplevel 2>/dev/null)" \
                     || { echo "$TAG dependency unavailable: --fleet needs a git tree" >&2; return $EX_DEP; } ;;
        changed) root="$ENGINE_DIR" ;;   # enumerate() resolves the top-level itself
        root)    root="$OPT_ROOT"; [ -n "$root" ] || { echo "$TAG usage error: --root needs a DIR" >&2; return $EX_USAGE; } ;;
        *)       root="$ENGINE_DIR" ;;
    esac
    run_scan "$root"
}

main
exit $?
