#!/usr/bin/env bash
# 05-validate-target.sh — Skill 40
# DRY-PROBE validator for a Tier-1 (or Tier-3) target BEFORE any live run.
# Given a target slug, it: (1) loads the config, (2) checks robots.txt allows
# the search path, (3) confirms a real tos_url is present, (4) does a single
# HEAD/GET to confirm the portal responds, (5) EVALUATES every configured result
# selector against a real saved results page, and (6) on a full pass, persists a
# content-bound validation attestation into the config.
# It NEVER scrapes records and NEVER fabricates anything. A failing probe means
# the target must be treated as a Tier-4 honest gap until fixed.
#
# SK1-30 / T0-53 — WHAT CHANGED AND WHY:
#   The selector check used to be `[ "$SELECTORS_N" -gt 0 ]` — a COUNT of keys in
#   the config's `selectors` object, and a WARN (not a failure) when it was zero.
#   templates/tier3-config.template.json ships that object populated with four
#   `<css-selector-...>` placeholders, so an UNEDITED template counted four
#   selectors and reached "VALIDATION PASS — safe to use as a live tier target".
#   The live run then extracted records with selectors that had never been
#   evaluated against a page. Placeholder/empty selectors are now FAILURES, and
#   every selector is evaluated against a real document by scripts/selector-probe.py.
#
# SK1-30 / T2-34 — the attestation:
#   A passing validation used to write NOTHING, while the template carries
#   "validated": false and the router only serves a config with validated:true.
#   Either the target was never usable, or the flag was set BY HAND — in which
#   case it attested to nothing. A pass now writes validated:true together with a
#   timestamp and a SHA-256 over the exact fields that were validated, so the
#   attestation is bound to the configuration that passed and is invalidated the
#   moment that configuration changes.
#
# The selector document is an OPERATOR-SUPPLIED saved results page. There is no
# way to prove a result-row selector works against a page that has no results,
# so this is required rather than guessed. When it is absent the run reports
# INCOMPLETE and exits non-zero — a check that cannot run is never a pass.
#
# Usage: ./05-validate-target.sh <slug> [--fixture <saved-results-page.html>]
#        ./05-validate-target.sh --tier3 <path-to-operator-config.json> [--fixture <page.html>]
#   Fixture may also come from SKILL40_VALIDATE_FIXTURE or the config's
#   "selector_fixture" field.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIER1_DIR="$SKILL_ROOT/references/tier1-counties"
LIB="$SCRIPT_DIR/lib-records.sh"
PROBE="$SCRIPT_DIR/selector-probe.py"
P="[skill 40][validate]"

command -v jq >/dev/null 2>&1 || { echo "$P BLOCKED: jq required"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "$P BLOCKED: curl required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "$P BLOCKED: python3 required (selector evaluation)"; exit 1; }
[ -f "$PROBE" ] || { echo "$P BLOCKED: selector probe missing at $PROBE"; exit 1; }

CONFIG=""
FIXTURE="${SKILL40_VALIDATE_FIXTURE:-}"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tier3)   CONFIG="${2:-}"; shift 2 ;;
    --fixture) FIXTURE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

if [ -n "$CONFIG" ]; then
  [ -f "$CONFIG" ] || { echo "$P BLOCKED: tier3 config not found: $CONFIG"; exit 1; }
else
  SLUG="${ARGS[0]:-}"
  [ -n "$SLUG" ] || { echo "$P usage: $0 <slug> [--fixture <page.html>] | --tier3 <config.json> [--fixture <page.html>]"; exit 2; }
  CONFIG="$TIER1_DIR/$SLUG.json"
  [ -f "$CONFIG" ] || { echo "$P BLOCKED: no Tier-1 config for slug '$SLUG' at $CONFIG"; exit 1; }
fi

jq -e . "$CONFIG" >/dev/null 2>&1 || { echo "$P BLOCKED: invalid JSON: $CONFIG"; exit 1; }

CONFIG_DIR="$(cd "$(dirname "$CONFIG")" && pwd)"
BASE="$(jq -r '.portal_url // .base_url // empty' "$CONFIG")"
SEARCH_PATH="$(jq -r '.search_path // "/"' "$CONFIG")"
TOS="$(jq -r '.tos_url // empty' "$CONFIG")"
SLUG="$(jq -r '.slug // "unknown"' "$CONFIG")"

if [ -z "$FIXTURE" ]; then
  FIXTURE="$(jq -r '.selector_fixture // empty' "$CONFIG")"
  [ -n "$FIXTURE" ] && case "$FIXTURE" in /*) ;; *) FIXTURE="$CONFIG_DIR/$FIXTURE" ;; esac
fi

FAIL=0
echo "$P validating target: $SLUG"
echo "$P    portal: ${BASE:-<none>}  path: $SEARCH_PATH"

# ── 1. portal + ToS (a placeholder is not a reference) ───────────────────────
[ -n "$BASE" ] || { echo "$P    [FAIL] no portal_url/base_url in config"; FAIL=1; }
if [ -n "$BASE" ] && ! bash "$LIB" tos_valid "$TOS"; then
  echo "$P    [FAIL] tos_url missing or a placeholder ('${TOS:-<none>}') — the operator must reference a REAL Terms of Service before live use"
  FAIL=1
elif [ -n "$BASE" ]; then
  echo "$P    [PASS] tos_url is a real reference ($TOS)"
fi

# ── 2. selectors: no placeholders, and every one evaluated against a document ─
SEL_KEYS="$(jq -r '(.selectors // {}) | keys_unsorted[]' "$CONFIG" 2>/dev/null || true)"
if [ -z "$SEL_KEYS" ]; then
  echo "$P    [FAIL] no result selectors configured — a target with no selectors extracts nothing"
  FAIL=1
else
  SEL_LIST=()
  PLACEHOLDER=0
  while IFS= read -r k; do
    [ -n "$k" ] || continue
    v="$(jq -r --arg k "$k" '.selectors[$k] // empty' "$CONFIG")"
    if [ -z "$v" ]; then
      echo "$P    [FAIL] selector '$k' is empty"
      PLACEHOLDER=1; continue
    fi
    case "$v" in
      *"<"*|*OPERATOR_FILLS*|*"css-selector"*|*"how-to-fill"*)
        echo "$P    [FAIL] selector '$k' is still the template placeholder: $v"
        PLACEHOLDER=1; continue ;;
    esac
    SEL_LIST+=("$v")
  done <<< "$SEL_KEYS"
  [ "$PLACEHOLDER" -eq 1 ] && FAIL=1

  if [ "$PLACEHOLDER" -eq 0 ]; then
    if [ -z "$FIXTURE" ] || [ ! -f "$FIXTURE" ]; then
      echo "$P    [FAIL] INCOMPLETE — no saved results page to evaluate the selectors against."
      echo "$P           Save one real results page from $BASE$SEARCH_PATH and re-run with"
      echo "$P           --fixture <page.html> (or set SKILL40_VALIDATE_FIXTURE, or add"
      echo "$P           \"selector_fixture\" to the config). Counting selector keys is not"
      echo "$P           evidence that a selector matches anything."
      FAIL=1
    else
      echo "$P    evaluating ${#SEL_LIST[@]} selector(s) against $(basename "$FIXTURE")"
      if PROBE_OUT="$(python3 "$PROBE" "$FIXTURE" "${SEL_LIST[@]}" 2>&1)"; then
        while IFS= read -r line; do echo "$P    [PASS] selector $line"; done <<< "$PROBE_OUT"
      else
        while IFS= read -r line; do echo "$P    [FAIL] selector $line"; done <<< "$PROBE_OUT"
        echo "$P    [FAIL] one or more selectors did not match the saved results page (or could not be evaluated)"
        FAIL=1
      fi
    fi
  fi
fi

# ── 3. robots.txt (binding) + a liveness probe ───────────────────────────────
if [ -n "$BASE" ]; then
  if bash "$LIB" robots_ok "$BASE" "$SEARCH_PATH"; then
    echo "$P    [PASS] robots.txt allows $SEARCH_PATH"
  else
    echo "$P    [FAIL] robots.txt DISALLOWS $SEARCH_PATH — this target is a Tier-4 honest gap (never override robots)"
    FAIL=1
  fi
  # Light liveness probe (HEAD; never a record scrape).
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 15 -I "${BASE%/}$SEARCH_PATH" 2>/dev/null || echo "000")"
  if [ "$code" = "200" ] || [ "$code" = "301" ] || [ "$code" = "302" ] || [ "$code" = "403" ]; then
    echo "$P    [INFO] portal responded HTTP $code (liveness only; not a scrape)"
  else
    echo "$P    [WARN] portal liveness probe returned HTTP $code — confirm the URL before live use"
  fi
fi

echo
if [ "$FAIL" -eq 0 ]; then
  # ── 4. persist the content-bound attestation (T2-34) ───────────────────────
  # Written ONLY after every behavioural check above has passed, atomically, and
  # bound by hash to the exact fields that were validated.
  HASH="$(bash "$LIB" config_fields_hash "$CONFIG")" || HASH=""
  if [ -z "$HASH" ]; then
    echo "$P    [FAIL] could not compute the validated-fields hash — refusing to write an attestation that binds to nothing"
    echo "$P VALIDATION FAIL for $SLUG — treat as a Tier-4 HONEST GAP until fixed."
    exit 1
  fi
  TMP="$CONFIG.validating.$$"
  if jq --arg h "$HASH" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg fx "$(basename "${FIXTURE:-none}")" \
        '. + {validated:true, validation:{validated_at:$ts, fields_sha256:$h, selector_fixture:$fx, validator:"05-validate-target.sh"}}' \
        "$CONFIG" > "$TMP" 2>/dev/null && jq -e . "$TMP" >/dev/null 2>&1; then
    mv -f "$TMP" "$CONFIG" || { rm -f "$TMP"; echo "$P    [FAIL] could not persist the attestation to $CONFIG"; exit 1; }
    echo "$P    [PASS] attestation written: validated=true, fields_sha256=$HASH"
  else
    rm -f "$TMP" 2>/dev/null || true
    echo "$P    [FAIL] could not write the validation attestation to $CONFIG"
    echo "$P VALIDATION FAIL for $SLUG — treat as a Tier-4 HONEST GAP until fixed."
    exit 1
  fi
  echo "$P VALIDATION PASS for $SLUG — safe to use as a live tier target (subject to ToS acknowledgement + cost caps)."
  exit 0
else
  echo "$P VALIDATION FAIL for $SLUG — treat as a Tier-4 HONEST GAP until fixed. NEVER fabricate records for it."
  exit 1
fi
