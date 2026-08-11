#!/usr/bin/env bash
# post-change-agent-health-assert.sh — v1.0.0
#
# PURPOSE
#   Prove an agent can still EXECUTE A TOOL after a config-touching change.
#   VALIDITY IS NOT CAPABILITY. An incident produced six distinct faults
#   across a fleet of ~38 boxes, and every one was invisible to every existing
#   check: config validation returned VALID on a box whose every tool call was
#   failing; gateway health returned 200; the process was up. None of those
#   checks ever asked the agent to actually DO anything. This script closes
#   that specific gap. It runs one real, non-channel-bound agent turn, hands
#   the agent a freshly generated sentinel it cannot already know (the
#   sentinel lives only inside a private file this script wrote — it is never
#   present in the prompt text), and requires the agent to retrieve that
#   sentinel with a REAL TOOL CALL (reading the file) and hand it back
#   verbatim. A model that merely replies with SOMETHING — a greeting, an
#   apology, a hallucinated guess, an empty string — cannot produce the exact
#   sentinel without actually having executed the read. That is the proof.
#
# WHY "NO ERROR" IS NEVER ACCEPTED AS SUCCESS
#   Operating rule: never accept "no error" as proof; prove a success. A run
#   that produces no output and no error is judged UNDETERMINED here, never
#   PASS (see EXIT CODES). Contrast scripts/smoke-test-provider-capabilities.sh
#   S3, which accepts ANY non-empty reply ("reply"/"content"/"message"/etc.)
#   as passing — adequate for a provider-connectivity smoke test, but not
#   proof of tool-call capability, which is the specific thing a config-
#   touching change can silently break. This script demands the one thing
#   that cannot be faked: the sentinel that only a successful tool call
#   can produce.
#
# ⚠️ SAFETY, ABSOLUTE — THIS SCRIPT MUST NEVER BE ABLE TO MESSAGE A CLIENT
#   The `openclaw agent` command this script runs is assembled from a fixed,
#   hardcoded argument list inside main() below. This script never accepts
#   pass-through CLI flags from its own invocation — its argument parser only
#   recognizes --dry-run, --agent, --timeout, --self-test, --help, and refuses
#   (exit 4) anything else — so there is no way to smuggle an extra flag in
#   via this script's own argv. `openclaw agent --message <text> --json` runs
#   a genuine agent turn through the Gateway and returns the reply WITHOUT
#   delivering to any channel: no --deliver, no --channel, no --to, no
#   --announce ever appear in the composed command, on purpose. This is the
#   same probe transport already verified and used by
#   scripts/smoke-test-provider-capabilities.sh's S3 check (which moved to
#   this exact command when the legacy `--channel internal` loopback was
#   removed in OpenClaw >= 2026.6.0).
#
#   Belt AND suspenders: before executing (or printing, in --dry-run) the
#   composed command, assert_safe_command() scans every element of the
#   composed argv for the substrings `--deliver`, `--channel`, `--to`, and
#   `--announce` (case-insensitive) and REFUSES TO RUN (exit 3) if any is
#   present — even though nothing in this script ever adds them. That
#   assertion exists so that a future edit which accidentally introduces one
#   of those flags fails LOUD instead of quietly turning a health probe into
#   a client delivery.
#
# CALL SITE (documented, not wired in here — wiring is a separate reviewed change)
#   Intended to run:
#     1. Immediately after any config-touching roll's own config-validation
#        check on that box.
#     2. As the FINAL step of the roll script itself (e.g. update-skills.sh),
#        once that wiring change is reviewed and merged separately.
#   A roll that passes config validation but FAILS this assert must be
#   treated as NOT DONE for that box — validity is not capability.
#
# EXIT CODES
#   0  PASS         — sentinel returned verbatim; the agent can execute tools.
#   1  FAIL         — the agent turn ran and replied, but the sentinel was
#                      NOT in the reply (tool call failed, wrong file, model
#                      refused, etc.). The agent is not proven healthy.
#   2  UNDETERMINED — the harness itself could not produce a judgeable
#                      result: `openclaw` CLI not on PATH, could not create
#                      the sentinel temp file, or the turn produced zero
#                      output. NEVER treated as PASS.
#   3  REFUSED      — safety gate tripped: a forbidden delivery-shaped flag
#                      was found in the composed command. Nothing was run.
#   4  MISUSE       — bad invocation of this script itself (unknown flag,
#                      missing --agent value, non-integer --timeout).
#
# USAGE
#   bash scripts/post-change-agent-health-assert.sh [--dry-run] [--agent <id>]
#        [--timeout <seconds>]
#   bash scripts/post-change-agent-health-assert.sh --self-test
#
#   --dry-run          Print the exact command that WOULD be executed and
#                       exit 0. Nothing is run, nothing is written to disk —
#                       even the sentinel file path shown is generated with
#                       `mktemp -u` (name only, file never created). Safe to
#                       use for review. Default: OFF.
#   --agent <id>        Target a specific agent id (passed through as
#                       `openclaw agent --agent <id>`). Optional; omitted by
#                       default to use the CLI's own default agent.
#   --timeout <secs>    Seconds to allow the agent turn. Default: 30.
#   --self-test         Exercise the sentinel PASS/FAIL/UNDETERMINED judging
#                       logic against fake responses. No gateway call, no
#                       `openclaw` invocation. Returns 0 if all three judged
#                       correctly, 1 otherwise.
#   --help, -h          Print this usage block and exit 0.

set -uo pipefail

TAG="[post-change-agent-health-assert]"

# ─── forbidden-flag pattern the safety gate scans for (case-insensitive) ──────
FORBIDDEN_FLAG_PATTERN='--deliver|--channel|--to|--announce'

usage() {
  sed -n '2,89p' "${BASH_SOURCE[0]}"
}

# ─── judge_response — the core proof logic, kept as a standalone function ────
# so --self-test can exercise it directly against fake text with no gateway
# call at all.
#
#   $1 = captured output of the agent turn (stdout+stderr combined, may be "")
#   $2 = the sentinel that must appear verbatim
#
# Returns (as the function's exit status):
#   0  PASS         — sentinel found verbatim in the output
#   1  FAIL         — output is non-empty but the sentinel is NOT present
#   2  UNDETERMINED — output is empty; nothing to judge
judge_response() {
  local out="$1" sentinel="$2"
  if [ -z "$out" ]; then
    return 2
  fi
  if printf '%s' "$out" | grep -qF -- "$sentinel"; then
    return 0
  fi
  return 1
}

# ─── assert_safe_command — the absolute safety gate ───────────────────────────
# $@ = the fully composed argv, as separate elements (not a joined string, so
# a flag hiding inside another element's text cannot slip past word-splitting
# tricks). Prints and refuses (return 3) if any element matches the forbidden
# pattern.
assert_safe_command() {
  local arg
  for arg in "$@"; do
    if printf '%s' "$arg" | grep -qiE -- "$FORBIDDEN_FLAG_PATTERN"; then
      echo "$TAG REFUSED: composed command contains a forbidden delivery-shaped flag ('$arg'). This script must never be able to message a client. Aborting before execution." >&2
      return 3
    fi
  done
  return 0
}

# ─── gen_sentinel — unique, unguessable, alnum/dash only (safe for grep -F) ──
gen_sentinel() {
  local rand=""
  if command -v openssl >/dev/null 2>&1; then
    rand="$(openssl rand -hex 8 2>/dev/null || true)"
  fi
  if [ -z "$rand" ]; then
    rand="$$-${RANDOM}${RANDOM}"
  fi
  printf 'LFX-HEALTH-%s-%s' "$(date +%s)" "$rand"
}

# ─── self_test — proves judge_response distinguishes PASS/FAIL/UNDETERMINED ──
# Entirely offline: no `openclaw`, no gateway, no network, no temp files.
self_test() {
  local sentinel="LFX-HEALTH-SELFTEST-DEADBEEF01"
  local fake_pass fake_fail rc

  fake_pass='{"reply":"tool output: LFX-HEALTH-SELFTEST-DEADBEEF01"}'
  judge_response "$fake_pass" "$sentinel"; rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "SELF-TEST FAIL — judge_response returned $rc (expected 0/PASS) for a response containing the sentinel" >&2
    return 1
  fi
  echo "SELF-TEST: fake response WITH sentinel judged PASS (exit 0) — correct"

  fake_fail='{"reply":"I could not access that file right now."}'
  judge_response "$fake_fail" "$sentinel"; rc=$?
  if [ "$rc" -ne 1 ]; then
    echo "SELF-TEST FAIL — judge_response returned $rc (expected 1/FAIL) for a response WITHOUT the sentinel" >&2
    return 1
  fi
  echo "SELF-TEST: fake response WITHOUT sentinel judged FAIL (exit 1) — correct"

  judge_response "" "$sentinel"; rc=$?
  if [ "$rc" -ne 2 ]; then
    echo "SELF-TEST FAIL — judge_response returned $rc (expected 2/UNDETERMINED) for empty output" >&2
    return 1
  fi
  echo "SELF-TEST: empty output judged UNDETERMINED (exit 2) — correct, never PASS"

  echo "SELF-TEST PASS — sentinel judge distinguishes PASS/FAIL/UNDETERMINED correctly"
  return 0
}

main() {
  local dry_run=0 agent_id="" timeout_secs=30

  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      --agent)
        agent_id="${2:-}"
        if [ -z "$agent_id" ]; then
          echo "$TAG MISUSE: --agent requires a value" >&2
          exit 4
        fi
        shift 2
        ;;
      --timeout)
        timeout_secs="${2:-}"
        if ! [[ "$timeout_secs" =~ ^[0-9]+$ ]] || [ "$timeout_secs" -le 0 ]; then
          echo "$TAG MISUSE: --timeout requires a positive integer (got: ${2:-<missing>})" >&2
          exit 4
        fi
        shift 2
        ;;
      --self-test) self_test; exit $? ;;
      --help|-h) usage; exit 0 ;;
      *)
        echo "$TAG MISUSE: unknown argument: $1" >&2
        exit 4
        ;;
    esac
  done

  if ! command -v openclaw >/dev/null 2>&1; then
    echo "$TAG UNDETERMINED: 'openclaw' CLI not found on PATH — cannot run the health probe on this box." >&2
    exit 2
  fi

  local sentinel sentinel_file prompt
  sentinel="$(gen_sentinel)"

  if [ "$dry_run" -eq 1 ]; then
    # -u = generate a unique NAME only; no file is created. Zero side effects
    # in --dry-run, on purpose — the preview must be safe to run by anyone.
    sentinel_file="$(mktemp -u "${TMPDIR:-/tmp}/oc-health-sentinel.XXXXXX")"
  else
    sentinel_file="$(mktemp "${TMPDIR:-/tmp}/oc-health-sentinel.XXXXXX")" || {
      echo "$TAG UNDETERMINED: could not create the sentinel temp file — cannot run the health probe." >&2
      exit 2
    }
    chmod 600 "$sentinel_file"
    printf '%s\n' "$sentinel" > "$sentinel_file"
    # Best-effort cleanup; a leftover sentinel file is not a secret and not
    # harmful, but there is no reason to leave it behind.
    trap 'rm -f "$sentinel_file"' EXIT
  fi

  prompt="AUTOMATED POST-CHANGE HEALTH PROBE (not a conversation; this reply is never delivered to any channel). Use a file-read tool to read the exact contents of the local file at this path: ${sentinel_file} — then reply with ONLY the exact text you read from that file, verbatim, and nothing else. Do not summarize, do not add commentary, do not wrap it in markdown, do not guess the contents — actually read the file."

  local cmd=(openclaw agent)
  if [ -n "$agent_id" ]; then
    cmd+=(--agent "$agent_id")
  fi
  cmd+=(--message "$prompt" --json --timeout "$timeout_secs")

  if ! assert_safe_command "${cmd[@]}"; then
    exit 3
  fi

  if [ "$dry_run" -eq 1 ]; then
    echo "$TAG DRY-RUN — sentinel (would be written to $sentinel_file, not yet created): $sentinel"
    echo "$TAG DRY-RUN — would execute:"
    printf '  '
    printf '%q ' "${cmd[@]}"
    printf '\n'
    echo "$TAG DRY-RUN — nothing was executed and nothing was written to disk. This is a preview only, not a health verdict."
    exit 0
  fi

  echo "$TAG running post-change health probe (timeout ${timeout_secs}s)..."
  local out rc
  out="$("${cmd[@]}" 2>&1)"
  judge_response "$out" "$sentinel"
  rc=$?

  case "$rc" in
    0)
      echo "$TAG PASS — sentinel returned verbatim; the agent can execute tools after this change."
      exit 0
      ;;
    1)
      echo "$TAG FAIL — the agent turn ran and replied, but the sentinel was NOT present. This box's agent is not proven able to execute tools. Output (first 3 lines): $(printf '%s' "$out" | head -3 | tr '\n' ' ')" >&2
      exit 1
      ;;
    2)
      echo "$TAG UNDETERMINED — the agent turn produced no output at all; cannot judge PASS or FAIL. Treat as unproven, not healthy." >&2
      exit 2
      ;;
  esac
}

main "$@"
