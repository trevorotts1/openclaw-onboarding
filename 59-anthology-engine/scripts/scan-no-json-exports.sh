#!/usr/bin/env bash
# 59-anthology-engine/scripts/scan-no-json-exports.sh
# ----------------------------------------------------------------------------
# MERGE-GATE STATIC SCAN #2 of 4 (Unit W2.8). Proves NONE of the nine legacy
# n8n JSON exports (or the prompt CSV), in whole, in part, or in fixture form,
# is present in the scanned tree. Enforces AF-AE-EXPORT-LEAK (ENGINE-MANIFEST,
# py_symbol "scan"; CHECKLIST Part C item 2; SPEC 3.4 / Section 14 / W0.3+W2.8).
# This IS a product enforcement tool: pattern matching is the mechanism.
#
# WHY STRUCTURAL, NOT NAME-ONLY: one real export basename carries a CLIENT NAME,
# so this scanner NEVER hardcodes a PII-bearing basename. It detects an export by
# its n8n JSON SIGNATURE (renames cannot evade it), by generic (non-PII) workflow
# basenames, by the legacy key-field content markers, and -- when the operator
# points it at the out-of-tree reference dir -- by exact sha256 of the real files
# and by their basenames (reported by INDEX, never by their possibly-PII names).
#
# DETECTION CLASSES:
#   struct_n8n     a file with the n8n workflow JSON shape ("connections" plus an
#                  n8n node marker: n8n-nodes-base. / @n8n/n8n-nodes- / "pinData")
#   export_name    a GENERIC (non-PII) export basename: {Avatar,Chapter,Tone,
#                  Outline,Chapter Re-Writer,Title Writer} Agent.json, Single
#                  Chapter Cover Image Gen*.json
#   prompt_csv     a *Prompt*.csv, or any .csv carrying the [UNCHANGED] placeholder
#   ref_name       (only if EXPORTS_REF_DIR exists) a repo file whose basename equals
#                  a real export's basename -- reported by index, name never printed
#   ref_sha256     (only if EXPORTS_REF_DIR + a sha tool) a repo file byte-identical
#                  to a real export -- reported by index
#
# DIVISION OF LABOR (deliberately NOT flagged here, to avoid false positives on the
# engine's OWN defensive code): a leaked credential VALUE is caught by
# scan-no-secrets.sh; a leaked prompt FRAGMENT is caught by guard-prompt-pins.py.
# A bare legacy FIELD NAME (e.g. Openrouter_Api_Key) legitimately appears in the
# engine's credential-rejection lists and intake fixtures, so it is NOT a signal
# here; an actual export always carries the n8n JSON skeleton, which struct_n8n
# catches "in whole or in part".
#
# DOCTRINE: export CONTENTS and KEYS are NEVER read into output. Findings print the
# offending REPO PATH (operator/CI-facing, so the operator can delete it) and the
# detection class only. The reference dir is enumerated for names/hashes at runtime
# and never printed. The four scanners self-exclude (their markers are definitions).
#
# EXPORTS_REF_DIR default: "$HOME/Downloads/anthology project"
# (the operator's out-of-tree exports). Absent in CI -- structural detection still
# fully protects.
#
# SCOPE: (default) engine skill dir | --changed vs base | --fleet top-level | --root DIR
# EXIT CODES (SPEC 3.4; guard family): 0 clean; 1 error; 2 usage; 3 dep (git for
#   --changed); 4 VIOLATION (an export or fragment is present).
# ----------------------------------------------------------------------------
set -uo pipefail

EX_CLEAN=0; EX_ERR=1; EX_USAGE=2; EX_DEP=3; EX_VIOLATION=4

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ENGINE_DIR="$(cd "$SELF_DIR/.." && pwd)"
TAG="[scan-no-json-exports]"
SELF_NAMES="scan-no-secrets.sh scan-no-json-exports.sh scan-no-client-identifiers.sh scan-skill53-untouched.sh"

SELFTEST_TMP=""
_cleanup_selftest() { [ -n "${SELFTEST_TMP:-}" ] && rm -rf "$SELFTEST_TMP"; return 0; }
trap _cleanup_selftest EXIT

OPT_ROOT=""; OPT_SCOPE="engine"; OPT_BASE="origin/main"; OPT_JSON=0
OPT_INCLUDE_SELF="${SCAN_INCLUDE_SELF:-0}"; OPT_ALL_FILES="${SCAN_ALL_FILES:-0}"
EXPORTS_REF_DIR="${EXPORTS_REF_DIR:-$HOME/Downloads/anthology project}"

usage() {
    cat <<EOF
$TAG merge-gate scan: none of the nine n8n JSON exports / prompt CSV in the tree.
Usage: scan-no-json-exports.sh [SCOPE] [options]
  (no scope) engine dir | --changed | --fleet | --root DIR
  --base REF   base for --changed (default origin/main)
  --json       machine-readable findings (path + class only)
  --self-test  plant a synthetic export, confirm detection, exit
  -h|--help    this help
Env: EXPORTS_REF_DIR (out-of-tree exports; adds exact-name/sha256 detection)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --changed) OPT_SCOPE="changed"; shift ;;
        --fleet)   OPT_SCOPE="fleet"; shift ;;
        --root)    OPT_SCOPE="root"; OPT_ROOT="${2:-}"; shift 2 ;;
        --base)    OPT_BASE="${2:-}"; shift 2 ;;
        --json)    OPT_JSON=1; shift ;;
        --self-test) OPT_SELFTEST=1; shift ;;
        -h|--help) usage; exit $EX_CLEAN ;;
        *) echo "$TAG usage error: unknown argument: $1" >&2; usage >&2; exit $EX_USAGE ;;
    esac
done

# generic, non-PII export basenames (each also caught structurally)
GENERIC_NAMES='Avatar Agent.json|Chapter Agent.json|Tone Agent.json|Outline Agent.json|Chapter Re-Writer Agent.json|Title Writer Agent.json|Single Chapter Cover Image Gen'

sha256_of() {   # $1 = file ; prints hash or nothing
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
    fi
}

is_self() {
    [ "$OPT_INCLUDE_SELF" -eq 1 ] && return 1
    local b; b="$(basename "$1")"
    case " $SELF_NAMES " in *" $b "*) return 0 ;; esac
    return 1
}

# The engine's OWN sanctioned n8n workflow assets (config/n8n/*.workflow.json) are a
# DELIBERATE product deliverable -- the Anthology Drive CREDENTIAL BROKER that keeps
# Trevor's Google creds inside n8n -- NOT one of the nine retired legacy exports. They
# are exempt from struct_n8n by their exact sanctioned path + suffix; a legacy export
# never lives at this exact path/suffix, and its CONTENT is still covered by
# scan-no-secrets.sh and guard-no-anthropic-runtime.py. Nothing else is exempted.
is_sanctioned_n8n() {
    case "$1" in
        */config/n8n/*.workflow.json) return 0 ;;
    esac
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
record() { printf '%s\t%s\n' "$1" "$2" >> "$FINDINGS_FILE"; }   # path <TAB> class

run_scan() {
    local root="$1"
    [ -e "$root" ] || { echo "$TAG usage error: no such path: $root" >&2; return $EX_USAGE; }
    local listfile; listfile="$(mktemp "${TMPDIR:-/tmp}/scan-exports-list.XXXXXX")"
    FINDINGS_FILE="$(mktemp "${TMPDIR:-/tmp}/scan-exports-find.XXXXXX")"; : > "$FINDINGS_FILE"
    local rc; enumerate "$root" "$listfile"; rc=$?
    if [ $rc -ne 0 ]; then rm -f "$listfile" "$FINDINGS_FILE"; return $rc; fi

    # Pre-compute reference names/hashes ONCE (never printed).
    local have_ref=0; local -a REF_HASH=(); local -a REF_BASE=()
    if [ -d "$EXPORTS_REF_DIR" ]; then
        have_ref=1
        local rf
        while IFS= read -r rf; do
            [ -f "$EXPORTS_REF_DIR/$rf" ] || continue
            REF_BASE+=("$rf")
            REF_HASH+=("$(sha256_of "$EXPORTS_REF_DIR/$rf")")
        done < <(ls -1 "$EXPORTS_REF_DIR" 2>/dev/null)
    fi

    # Iterate files once; apply all classes.
    local f
    while IFS= read -r -d '' f; do
        is_self "$f" && continue
        local b; b="$(basename "$f")"

        # export_name (generic, non-PII)
        if printf '%s' "$b" | grep -qE "^($GENERIC_NAMES)"; then record "$f" "export_name"; fi

        # prompt_csv
        case "$b" in
            *.csv)
                if printf '%s' "$b" | grep -qiE 'prompt'; then record "$f" "prompt_csv"
                elif grep -qF '[UNCHANGED]' "$f" 2>/dev/null; then record "$f" "prompt_csv"; fi ;;
        esac

        # struct_n8n: n8n node marker AND "connections" (except the engine's OWN
        # sanctioned config/n8n/*.workflow.json broker asset -- see is_sanctioned_n8n)
        if ! is_sanctioned_n8n "$f" \
           && grep -IqE 'n8n-nodes-base\.|@n8n/n8n-nodes-|"pinData"' "$f" 2>/dev/null \
           && grep -Iq '"connections"' "$f" 2>/dev/null; then
            record "$f" "struct_n8n"
        fi

        # reference-based exact matching (names/hashes precomputed, never printed)
        if [ "$have_ref" -eq 1 ]; then
            local i
            for i in "${!REF_BASE[@]}"; do
                if [ "$b" = "${REF_BASE[$i]}" ]; then record "$f" "ref_name#$i"; fi
            done
            local fh; fh="$(sha256_of "$f")"
            if [ -n "$fh" ]; then
                for i in "${!REF_HASH[@]}"; do
                    [ -n "${REF_HASH[$i]}" ] && [ "$fh" = "${REF_HASH[$i]}" ] && record "$f" "ref_sha256#$i"
                done
            fi
        fi
    done < "$listfile"

    local n=0
    if [ -s "$FINDINGS_FILE" ]; then
        sort -u "$FINDINGS_FILE" -o "$FINDINGS_FILE"
        n="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
    fi

    if [ "$OPT_JSON" -eq 1 ]; then
        printf '{"scan":"no-json-exports","root":"%s","violations":%s,"findings":[' "$root" "$n"
        local first=1 p c line
        while IFS="$(printf '\t')" read -r p c; do
            [ -z "$p" ] && continue
            [ $first -eq 1 ] || printf ','; printf '{"file":"%s","class":"%s"}' "$p" "$c"; first=0
        done < "$FINDINGS_FILE"
        printf ']}\n'
    else
        if [ "$n" -eq 0 ]; then echo "$TAG CLEAN: no n8n export or prompt CSV under $root"
        else
            echo "$TAG VIOLATION: $n export artifact(s) present (contents NOT shown):" >&2
            local p c
            while IFS="$(printf '\t')" read -r p c; do
                [ -z "$p" ] && continue; echo "  $p  [$c]" >&2
            done < "$FINDINGS_FILE"
        fi
    fi
    rm -f "$listfile" "$FINDINGS_FILE"
    [ "$n" -eq 0 ] && return $EX_CLEAN || return $EX_VIOLATION
}

self_test() {
    echo "$TAG self-test: planting a synthetic n8n export and confirming detection"
    local td; td="$(mktemp -d "${TMPDIR:-/tmp}/scan-exports-selftest.XXXXXX")"
    SELFTEST_TMP="$td"
    local save_scope="$OPT_SCOPE"; OPT_SCOPE="root"; OPT_ALL_FILES=1
    local save_ref="$EXPORTS_REF_DIR"; EXPORTS_REF_DIR="$td/nonexistent-ref"  # isolate from real exports

    # CLEAN: a normal skill file that merely MENTIONS n8n in prose (must NOT flag)
    mkdir -p "$td/clean"
    { echo '# This skill RETIRES the legacy n8n stack; no export ships here.'
      echo 'The old Gmail sendAndWait gates are replaced by gate_engine.py.'; } > "$td/clean/SKILL.md"
    if run_scan "$td/clean" >/dev/null 2>&1; then echo "  clean case: PASS (exit 0)"
    else echo "$TAG self-test FAIL: clean prose flagged" >&2; OPT_SCOPE="$save_scope"; EXPORTS_REF_DIR="$save_ref"; return $EX_ERR; fi

    # DETECT: a synthetic n8n workflow JSON (structure only, no real content/keys)
    mkdir -p "$td/dirty"
    cat > "$td/dirty/Some Renamed Workflow.json" <<'JSON'
{ "nodes": [ { "type": "n8n-nodes-base.gmail", "parameters": { "operation": "sendAndWait" } } ],
  "connections": {}, "pinData": {} }
JSON
    local out rc
    out="$(run_scan "$td/dirty" 2>&1)"; rc=$?
    if ! { [ $rc -eq $EX_VIOLATION ] && printf '%s' "$out" | grep -q 'struct_n8n'; }; then
        OPT_SCOPE="$save_scope"; EXPORTS_REF_DIR="$save_ref"
        echo "$TAG self-test FAIL: planted export not detected (exit $rc)" >&2
        return $EX_ERR
    fi
    echo "  detect case: PASS (exit 4, struct_n8n on a renamed export)"

    # SANCTIONED: the engine's OWN config/n8n/*.workflow.json broker asset (real n8n
    # shape) must NOT flag, while a legacy-shaped file OUTSIDE that path still does.
    mkdir -p "$td/sanctioned/config/n8n"
    cat > "$td/sanctioned/config/n8n/anthology-drive-broker.workflow.json" <<'JSON'
{ "name": "Anthology Drive Broker",
  "nodes": [ { "type": "n8n-nodes-base.webhook", "parameters": {} } ],
  "connections": {}, "pinData": {} }
JSON
    out="$(run_scan "$td/sanctioned" 2>&1)"; rc=$?
    OPT_SCOPE="$save_scope"; EXPORTS_REF_DIR="$save_ref"
    if [ $rc -eq $EX_CLEAN ]; then
        echo "  sanctioned case: PASS (exit 0, config/n8n/*.workflow.json exempt)"
        echo "$TAG self-test: PASS"; return $EX_CLEAN
    fi
    echo "$TAG self-test FAIL: sanctioned broker workflow was flagged (exit $rc): $out" >&2
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
