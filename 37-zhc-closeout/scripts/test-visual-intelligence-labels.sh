#!/usr/bin/env bash
# test-visual-intelligence-labels.sh
#
# BU-77 (WF-094, WF-095) -- generate-visual-intelligence.sh:
#   * infographic2Url is written from the entry labelled how-your-zhc-works,
#     never from a fixed index, so a failed image cannot shift it;
#   * the duplicate paid "workflow" image (infographic-2-prompt.md) is gone from
#     the queue, so its template is never sent.
#
# Strategy: Skill 74 (the one KIE transport) is stubbed at a temporary skills
# tree; the second image (what-is-zhc) fails on every attempt while the rest
# succeed, which is exactly the shift that broke the old index-based write.
# No network, no real key, no credits.
#
# EXIT CODES: 0 = all PASS, 1 = any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$SCRIPT_DIR/generate-visual-intelligence.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

[[ -f "$TARGET" ]] || { fail "generate-visual-intelligence.sh not found at $TARGET"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---- temporary skills tree: real skill 37 + stubbed skill 74 --------------
# kie74_locate() looks beside the script first, so the stub beside the copy wins
# over the real adapter in the checkout.
mkdir -p "$WORK/skills"
cp -R "$SKILL_DIR" "$WORK/skills/37-zhc-closeout"
mkdir -p "$WORK/skills/74-kie-live-adapter/scripts"
cat > "$WORK/skills/74-kie-live-adapter/scripts/kie_live_adapter.py" <<'PY'
#!/usr/bin/env python3
"""Stub KIE adapter: records every prompt; the marked image always fails."""
import json, os, sys

args = sys.argv[1:]
mode = args[0] if args else ""
LOG = os.environ["STUB_LOG"]
FAIL_MARKER = os.environ.get("STUB_FAIL_MARKER", "")


def opt(name, default=""):
    return args[args.index(name) + 1] if name in args else default


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")


def records():
    rows = []
    try:
        with open(LOG, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except (OSError, ValueError):
        pass
    return rows


if mode == "submit":
    try:
        with open(opt("--request"), encoding="utf-8") as fh:
            req = json.load(fh)
    except (OSError, ValueError):
        emit({"error": {"code": "bad_request", "msg": "stub: request file unreadable"}})
        sys.exit(0)
    prompt = (req.get("input") or {}).get("prompt", "")
    n = len(records()) + 1
    tid = "stub-task-%d" % n
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"task_id": tid, "model": req.get("model", ""),
                             "prompt": prompt, "url": "https://stub.example/img-%02d.png" % n}) + "\n")
    emit({"task_id": tid, "state": "ready"})
    sys.exit(0)

if mode == "wait":
    tid = opt("--task-id")
    row = next((r for r in records() if r.get("task_id") == tid), None)
    if row is None:
        emit({"error": {"code": "not_found", "msg": "stub: unknown task"}})
        sys.exit(0)
    if FAIL_MARKER and FAIL_MARKER in row.get("prompt", ""):
        emit({"state": "fail", "error": {"code": "stub_failure", "msg": "stub: simulated image failure"}})
        sys.exit(0)
    emit({"state": "success", "result_urls": [row["url"]]})
    sys.exit(0)

emit({"error": {"code": "unsupported", "msg": "stub: mode %s" % mode}})
sys.exit(0)
PY

# ---- first-line prefixes, read from the templates themselves --------------
first_line() { local line; IFS= read -r line < "$1"; printf '%s' "$line"; }
# The literal prefix of a template's first line, cut at its first placeholder.
prefix_before_placeholder() { local l; l="$(first_line "$1")"; printf '%s' "${l%%\{\{*}"; }

HOW_TEMPLATE="$SKILL_DIR/templates/img-how-your-zhc-works-prompt.md"
WHAT_TEMPLATE="$SKILL_DIR/templates/img-what-is-zhc-prompt.md"
WF_TEMPLATE="$SKILL_DIR/templates/infographic-2-prompt.md"

HOW_PREFIX="$(prefix_before_placeholder "$HOW_TEMPLATE")"
WHAT_PREFIX="$(prefix_before_placeholder "$WHAT_TEMPLATE")"
WF_PREFIX="$(prefix_before_placeholder "$WF_TEMPLATE")"

if [[ "${#HOW_PREFIX}" -lt 20 || "${#WHAT_PREFIX}" -lt 20 || "${#WF_PREFIX}" -lt 20 ]]; then
  fail "template prefixes too short to identify a prompt (how=${#HOW_PREFIX} what=${#WHAT_PREFIX} wf=${#WF_PREFIX})"
  echo; echo "PASS=$PASS  FAIL=$FAIL"; echo "SOME TESTS FAILED"; exit 1
fi

# ---- a fresh box and state ------------------------------------------------
HOME_DIR="$WORK/home"; mkdir -p "$HOME_DIR/.openclaw/workspace"
STATE="$HOME_DIR/.openclaw/workspace/.workforce-build-state.json"
STUB_LOG="$WORK/stub-calls.jsonl"; : > "$STUB_LOG"
jq -n '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",
        brandColor:"#123456"}' > "$STATE"

# ---- run (second image fails on every attempt) ----------------------------
STUB_LOG="$STUB_LOG" STUB_FAIL_MARKER="$WHAT_PREFIX" \
HOME="$HOME_DIR" ZHC_STATE_FILE="$STATE" ZHC_VISUAL_INTEL_CAP=10 \
  bash "$WORK/skills/37-zhc-closeout/scripts/generate-visual-intelligence.sh" \
  >"$WORK/run.out" 2>&1
RC=$?

if [[ "$RC" == "0" ]]; then
  pass "script exited 0 while the second image failed on every attempt"
else
  fail "script exited $RC (expected 0: the remaining images still form the set)"
  tail -8 "$WORK/run.out"
fi

# ---- assertions -----------------------------------------------------------
n_urls=$(jq -r '.visualIntelligenceUrls | length' "$STATE" 2>/dev/null)
if [[ "${n_urls:-0}" -ge 3 ]]; then
  pass "at least 3 image URLs written to state ($n_urls)"
else
  fail "fewer than 3 image URLs in state (${n_urls:-none})"
fi

how_url=$(jq -r --arg p "$HOW_PREFIX" 'select((.prompt // "") | contains($p)) | .url' "$STUB_LOG" 2>/dev/null | head -1)
state2=$(jq -r '.infographic2Url // empty' "$STATE" 2>/dev/null)
if [[ -n "$how_url" ]]; then
  pass "the stub was asked for how-your-zhc-works ($how_url)"
else
  fail "the stub was never asked for how-your-zhc-works"
fi
if [[ -n "$how_url" && "$state2" == "$how_url" ]]; then
  pass "infographic2Url is the URL returned for how-your-zhc-works (label lookup, not index)"
else
  fail "infographic2Url wrong: state='$state2' expected='$how_url'"
  jq -r '.prompt | .[0:60]' "$STUB_LOG" 2>/dev/null | nl -ba
fi

n_what=$(jq -r --arg p "$WHAT_PREFIX" 'select((.prompt // "") | contains($p)) | .url' "$STUB_LOG" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$n_what" -ge 2 ]]; then
  pass "the second image really failed and was retried ($n_what attempts)"
else
  fail "the second image was not exercised as a failure (attempts=$n_what)"
fi

wf_sent=$(jq -r --arg p "$WF_PREFIX" 'select((.prompt // "") | contains($p)) | .url' "$STUB_LOG" 2>/dev/null | head -1)
if [[ -z "$wf_sent" ]]; then
  pass "the stub was never called with the workflow template's first line (duplicate paid image is gone)"
else
  fail "the workflow template was still sent to the stub ($wf_sent)"
fi

echo
echo "================ RESULTS ================"
echo "PASS=$PASS  FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && { echo "ALL TESTS PASSED"; exit 0; } || { echo "SOME TESTS FAILED"; exit 1; }
