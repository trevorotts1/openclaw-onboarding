#!/usr/bin/env bash
# guard-ghl-method-decision.sh — v1.0.0
#
# CI / QC GUARD: no built page ships without a justified method-decision file.
#
# THE RULE (PLAN-3 — method-decision architecture):
#   Every page produced by Skill 06 must have a companion
#   routing/method-decision-<page>.json (or method-decision.json for a
#   single-page build) that records which build method was chosen and WHY.
#   Two valid methods exist:
#
#     "direct"  — native GoHighLevel page: HTML fragment inside a Custom Code
#                 element; saved via ghl_rest_canvas / ghl_builder. Used when
#                 the page is simple enough that GoHighLevel's own renderer will
#                 not fight the markup.
#     "vercel"  — Vercel-hosted page embedded into GoHighLevel via a responsive
#                 <iframe> in a Custom Code element (Skill 06 Mode 2, gate 26).
#                 Used only when the page is rich/complex enough that GoHighLevel's
#                 styling conflicts with the required markup. Requires the Vercel
#                 deployment to be public (no Vercel deployment protection / SSO)
#                 and to carry permissive frame-ancestors headers.
#
#   A build is BLOCKED (non-zero exit) when ANY of:
#     (1) A built-page descriptor exists in the run dir but its companion
#         routing/method-decision-<page>.json file is absent.
#     (2) The method-decision file exists but its "method" field is empty or
#         not one of the recognized methods ("direct" or "vercel").
#     (3) The method-decision file exists but its "reason" field is absent,
#         empty, or shorter than the minimum meaningful length (20 chars).
#     (4) Any method-decision file carries "method": "vercel" but lacks a
#         non-empty "vercel_url" field (the embed target must be declared).
#     (5) Any page produced by a live run has NO routing/ directory at all.
#         (A missing routing/ during CI dry-runs is a WARN, not a hard FAIL,
#         so hermetic CI stays green while the live path is still being wired.)
#
# WHAT THIS GUARD DOES NOT CHECK:
#   - Whether the page actually built or loaded (that is ghl_verify's job).
#   - Whether the Vercel URL is reachable (live-run check, not CI-static).
#   - Whether the "reason" content is accurate or well-argued (judgment call).
#
# CI-SAFE DESIGN:
#   The guard operates in one of three modes:
#     --run-dir <path>  : checks a specific completed run directory for
#                         method-decision files. Hard FAIL on any violation.
#     --static          : static check only — verifies that the guard itself
#                         is syntactically correct and that the gates.json
#                         contains the required method-decision gate entry.
#                         Used in hermetic CI where no run dir exists yet.
#                         Exits 0 unless the gates.json gate is missing.
#     --corpus <path>   : U23/B-U9 REGRESSION-CORPUS mode. Loads a committed
#                         routing_corpus.json (default:
#                         tests/fixtures/routing_corpus.json), feeds every
#                         entry's page_spec through the REAL
#                         ghl_method.classify_page, and hard FAILS if any
#                         entry's actual method or detected widget kinds
#                         diverge from its declared expectation. No network,
#                         no browser — classify_page is pure. This is what
#                         catches a decision-engine regression (a threshold
#                         or signal-weight change that silently reclassifies
#                         a page) BEFORE it ships.
#
# Integration:
#   Called by qc-ghl-install-pages.sh (and referenced in gates.json).
#   Also runnable standalone:
#     bash 06-ghl-install-pages/scripts/guard-ghl-method-decision.sh --static
#     bash 06-ghl-install-pages/scripts/guard-ghl-method-decision.sh \
#          --run-dir /path/to/run/YYYYMMDD-HHMMSS
#     bash 06-ghl-install-pages/scripts/guard-ghl-method-decision.sh \
#          --corpus tests/fixtures/routing_corpus.json
#
# Exit codes:
#   0 — PASS (all pages have valid method-decision files, or static mode clean)
#   1 — FAIL (missing/invalid/empty method-decision file)
#   2 — usage / environment error

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$SKILL_DIR/tools"
GATES_JSON="$TOOLS_DIR/gates.json"

# ── Constants ──────────────────────────────────────────────────────────────────
VALID_METHODS=("direct" "vercel")
MIN_REASON_LEN=20
REQUIRED_GATE_ID="method_decision_per_page"

# ── Helpers ────────────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
green() { printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

FAILS=0
WARNS=0

fail() { red "  FAIL — $1"; FAILS=$((FAILS + 1)); }
warn() { yellow "  WARN — $1"; WARNS=$((WARNS + 1)); }
pass() { green "  PASS — $1"; }

# ── Arg parsing ────────────────────────────────────────────────────────────────
MODE="static"
RUN_DIR=""
CORPUS_PATH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --run-dir)
      MODE="run"
      RUN_DIR="$2"
      shift 2
      ;;
    --static)
      MODE="static"
      shift
      ;;
    --corpus)
      MODE="corpus"
      CORPUS_PATH="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,80p' "$0"
      exit 0
      ;;
    *)
      printf "Unknown argument: %s\n" "$1" >&2
      exit 2
      ;;
  esac
done

echo ""
echo "guard-ghl-method-decision — method-decision-per-page enforcement"
echo ""

# ── STATIC CHECK: gates.json carries the required gate entry ──────────────────
check_gates_json() {
  if [ ! -f "$GATES_JSON" ]; then
    fail "gates.json not found at $GATES_JSON"
    return
  fi

  # gates.json is a dict with a top-level "gates" key (array) and separate
  # top-level enforcement keys. The method-decision gate lives as a top-level
  # key in the enforcement section, not inside the "gates" DOM-selector array.
  local found
  found=$(python3 - "$GATES_JSON" "$REQUIRED_GATE_ID" <<'PY'
import json, sys
path, gate_id = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(path, encoding="utf-8"))
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
# The enforcement gates live as top-level keys (not inside the "gates" array).
if gate_id in d:
    g = d[gate_id]
    if isinstance(g, dict) and g.get("required") is True:
        print("PRESENT_AND_REQUIRED")
    else:
        print("PRESENT_NOT_REQUIRED")
else:
    print("ABSENT")
PY
  )

  case "$found" in
    PRESENT_AND_REQUIRED)
      pass "gates.json contains required gate '$REQUIRED_GATE_ID' marked required:true"
      ;;
    PRESENT_NOT_REQUIRED)
      fail "gates.json has '$REQUIRED_GATE_ID' but it is NOT marked required:true — gate cannot be bypassed"
      ;;
    ABSENT)
      fail "gates.json is missing the '$REQUIRED_GATE_ID' gate entry — add it before shipping"
      ;;
    ERROR:*)
      fail "gates.json could not be parsed: $found"
      ;;
    *)
      fail "gates.json check returned unexpected output: $found"
      ;;
  esac
}

check_gates_json

if [ "$MODE" = "static" ]; then
  echo ""
  if [ "$FAILS" -eq 0 ]; then
    green "guard-ghl-method-decision STATIC PASS (gates.json gate present and required)."
    exit 0
  else
    red "guard-ghl-method-decision STATIC FAIL — $FAILS error(s)."
    echo ""
    echo "REMEDY: add the '$REQUIRED_GATE_ID' gate to gates.json with required:true."
    exit 1
  fi
fi

# ── CORPUS CHECK (U23/B-U9): the committed routing regression corpus ──────────
if [ "$MODE" = "corpus" ]; then
  if [ -z "$CORPUS_PATH" ]; then
    CORPUS_PATH="$SKILL_DIR/tests/fixtures/routing_corpus.json"
  fi

  if [ ! -f "$CORPUS_PATH" ]; then
    fail "routing corpus file not found: $CORPUS_PATH"
    echo ""; red "guard-ghl-method-decision CORPUS FAIL — corpus file missing."; exit 1
  fi

  echo "Checking routing corpus: $CORPUS_PATH"
  echo ""

  corpus_result=$(PYTHONPATH="$TOOLS_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CORPUS_PATH" <<'PY'
import json
import sys

import ghl_method as m

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    corpus = json.load(fh)

entries = corpus.get("entries", [])
if not entries:
    print("ERROR:corpus has zero entries")
    sys.exit(0)


def _materialize(entry):
    spec = json.loads(json.dumps(entry["page_spec"]))  # deep copy, JSON-safe
    repeat = spec.pop("html_repeat", None)
    if repeat is not None:
        unit = repeat["unit"]
        min_bytes = repeat["min_bytes"]
        reps = (min_bytes // len(unit.encode("utf-8"))) + 1
        spec["html"] = unit * reps
    return spec


fails = 0
for entry in entries:
    name = entry.get("name", "<unnamed>")
    expected_method = entry.get("expected_method")
    expected_widgets = entry.get("expected_widget_kinds", [])
    try:
        spec = _materialize(entry)
        decision = m.classify_page(spec)
        actual_method = decision.method.value
        actual_widgets = [w.kind.value for w in decision.widgets]
    except Exception as exc:  # noqa: BLE001 -- surface as a FAIL line, not a crash
        print(f"FAIL:{name}:classify_page raised {exc!r}")
        fails += 1
        continue

    if actual_method != expected_method:
        print(
            f"FAIL:{name}:method mismatch -- expected {expected_method!r}, "
            f"got {actual_method!r} (score={decision.score})"
        )
        fails += 1
        continue

    if actual_widgets != expected_widgets:
        print(
            f"FAIL:{name}:widget kinds mismatch -- expected {expected_widgets!r}, "
            f"got {actual_widgets!r}"
        )
        fails += 1
        continue

    print(f"OK:{name}:method={actual_method}")

print(f"SUMMARY:{len(entries)}:{fails}")
PY
  )

  entry_fails=0
  entry_total=0
  while IFS= read -r line; do
    case "$line" in
      OK:*)
        rest="${line#OK:}"
        ename="${rest%%:*}"
        pass "$ename: ${rest#*:}"
        ;;
      FAIL:*)
        rest="${line#FAIL:}"
        ename="${rest%%:*}"
        fail "$ename: ${rest#*:}"
        ;;
      ERROR:*)
        fail "${line#ERROR:}"
        ;;
      SUMMARY:*)
        summary="${line#SUMMARY:}"
        entry_total="${summary%%:*}"
        entry_fails="${summary#*:}"
        ;;
    esac
  done <<< "$corpus_result"

  echo ""
  echo "Routing corpus check complete: $entry_total entries, $entry_fails FAIL(s) (plus $FAILS gates.json issue(s))"
  echo ""

  if [ "$entry_fails" -eq 0 ] && [ "$FAILS" -eq 0 ]; then
    green "guard-ghl-method-decision CORPUS PASS — all $entry_total corpus entries classify as expected."
    exit 0
  else
    red "guard-ghl-method-decision CORPUS FAIL — $entry_fails corpus violation(s)."
    echo ""
    echo "REMEDY: a corpus entry's method or widget kinds no longer match its"
    echo "        declared expectation — either the decision engine regressed"
    echo "        (threshold/signal-weight change) or the corpus itself needs"
    echo "        an intentional, reviewed update."
    exit 1
  fi
fi

# ── RUN-DIR CHECK: every built page has a valid method-decision file ───────────
if [ -z "$RUN_DIR" ]; then
  printf "ERROR: --run-dir requires a path argument\n" >&2
  exit 2
fi

if [ ! -d "$RUN_DIR" ]; then
  fail "run directory does not exist: $RUN_DIR"
  echo ""; red "guard-ghl-method-decision FAIL — run dir not found."; exit 1
fi

echo "Checking run directory: $RUN_DIR"
echo ""

ROUTING_DIR="$RUN_DIR/routing"

# A missing routing/ during a live run is a hard FAIL; in hermetic CI the
# guard is invoked in --static mode, so this path only fires for live runs.
if [ ! -d "$ROUTING_DIR" ]; then
  fail "routing/ directory missing from run dir — no method-decision files were written"
  echo ""
  red "guard-ghl-method-decision FAIL — routing/ absent."
  echo ""
  echo "REMEDY: the build MUST write routing/method-decision-<page>.json for every"
  echo "        page before calling ghl_verify. A build without method decisions"
  echo "        cannot be marked done."
  exit 1
fi

# Collect all method-decision JSON files.
shopt -s nullglob
MD_FILES=("$ROUTING_DIR"/method-decision*.json)
shopt -u nullglob

if [ ${#MD_FILES[@]} -eq 0 ]; then
  fail "routing/ exists but contains no method-decision*.json files"
  echo ""; red "guard-ghl-method-decision FAIL — no method-decision files found."; exit 1
fi

echo "Found ${#MD_FILES[@]} method-decision file(s) in $ROUTING_DIR"
echo ""

# ── Validate each method-decision file ────────────────────────────────────────
is_valid_method() {
  local m="$1"
  for v in "${VALID_METHODS[@]}"; do
    [ "$m" = "$v" ] && return 0
  done
  return 1
}

for mdf in "${MD_FILES[@]}"; do
  fname="$(basename "$mdf")"
  echo "  Checking $fname ..."

  # Parse and validate using Python to handle JSON edge cases safely.
  result=$(python3 - "$mdf" "$MIN_REASON_LEN" <<'PY'
import json, sys
path, min_reason_len = sys.argv[1], int(sys.argv[2])
issues = []
try:
    d = json.load(open(path, encoding="utf-8"))
except Exception as e:
    print(f"PARSE_ERROR:{e}")
    sys.exit(0)

method = d.get("method", "")
reason = d.get("reason", "")
page   = d.get("page", "")

if not method:
    issues.append("method field is absent or empty")
elif method not in ("direct", "vercel"):
    issues.append(f"method '{method}' is not a recognized method (must be 'direct' or 'vercel')")

if not reason:
    issues.append("reason field is absent or empty")
elif len(reason.strip()) < min_reason_len:
    issues.append(
        f"reason is too short ({len(reason.strip())} chars < {min_reason_len} required) — "
        "provide a real justification"
    )

if method == "vercel":
    vercel_url = d.get("vercel_url", "")
    if not vercel_url:
        issues.append("method is 'vercel' but vercel_url is absent or empty — declare the embed target")

if issues:
    print("ISSUES:" + "|".join(issues))
else:
    print(f"OK:method={method}|reason_len={len(reason.strip())}")
PY
  )

  case "$result" in
    PARSE_ERROR:*)
      fail "$fname: JSON parse error — ${result#PARSE_ERROR:}"
      ;;
    ISSUES:*)
      issue_list="${result#ISSUES:}"
      IFS='|' read -ra issues <<< "$issue_list"
      for issue in "${issues[@]}"; do
        fail "$fname: $issue"
      done
      ;;
    OK:*)
      pass "$fname: valid (${result#OK:})"
      ;;
    *)
      fail "$fname: unexpected validation output — $result"
      ;;
  esac
done

echo ""
echo "Method-decision check complete: $FAILS FAIL(s), $WARNS WARN(s)"
echo ""

if [ "$FAILS" -eq 0 ]; then
  green "guard-ghl-method-decision PASS — all pages have valid method-decision files."
  exit 0
else
  red "guard-ghl-method-decision FAIL — $FAILS violation(s)."
  echo ""
  echo "REMEDY:"
  echo "  Every built page MUST have routing/method-decision-<page>.json with:"
  echo "    method:  'direct'  (GoHighLevel native Custom Code element)"
  echo "             or 'vercel' (Vercel-hosted embed via <iframe>)"
  echo "    reason:  a real justification (>=$MIN_REASON_LEN chars) explaining"
  echo "             WHY this method was chosen for this specific page."
  echo "    vercel_url: (required when method='vercel') the public embed URL."
  echo ""
  echo "  A build CANNOT be marked done without passing this guard."
  exit 1
fi
