#!/usr/bin/env bash
# shared-utils/agents-doctrine-blocks.sh
# ─────────────────────────────────────────────────────────────────────────────
# Shared helper: the canonical BODY text for the two AGENTS.md doctrine blocks
# the update path stamps into every box's active AGENTS.md, plus idempotent
# stampers guarded by HTML-comment markers (same convention as
# apply-fleet-standards.sh: ROLE_DISCIPLINE_V1 / PLATFORM_FACTS_V1 / etc.).
#
# Source this file (do NOT execute it directly) then call:
#
#   stamp_full_context_handoff  <AGENTS_FILE>      # FULL_CONTEXT_HANDOFF_V1
#   stamp_reporting_contract    <AGENTS_FILE>      # REPORTING_CONTRACT_V1
#   stamp_agents_doctrine_blocks <AGENTS_FILE>     # both, in order
#
# Each stamper is idempotent (no-op when its marker is already present) and
# ADDITIVE — it only appends its block; it never edits or deletes existing
# AGENTS.md content. Returns 0 on success/no-op, 1 only on a write failure.
#
# To inspect a body without writing a file (for tests / diffing):
#   emit_full_context_handoff_block
#   emit_reporting_contract_block
#
# Marker constants are exported so a caller (update-skills.sh / install.sh) can
# grep for prior presence with the exact same string the stamper writes.
#
# Callers: update-skills.sh (post-extract doctrine pass), install.sh,
#          apply-fleet-standards.sh.
# ─────────────────────────────────────────────────────────────────────────────

# Idempotency markers — the exact strings the stampers write and grep for.
FULL_CONTEXT_HANDOFF_MARKER="<!-- FULL_CONTEXT_HANDOFF_V1 -->"
REPORTING_CONTRACT_MARKER="<!-- REPORTING_CONTRACT_V1 -->"
export FULL_CONTEXT_HANDOFF_MARKER REPORTING_CONTRACT_MARKER

# ---------------------------------------------------------------------------
# emit_full_context_handoff_block
#
# Prints (stdout) the FULL CONTEXT HANDOFF doctrine block, marker first.
# This is the canonical BODY — keep all wording changes here so every entry
# point stamps identical text.
# ---------------------------------------------------------------------------
emit_full_context_handoff_block() {
    cat <<'FCHEOF'
<!-- FULL_CONTEXT_HANDOFF_V1 -->
## FULL CONTEXT HANDOFF (survive session + weekly limits — non-negotiable)

You wake up fresh every session and a session can be clipped mid-task at any
moment (context limit, weekly limit, crash). Work that lives only in your head
dies with the session. So you keep a DURABLE, GROUND-TRUTH handoff current at all
times — never "I'll write it at the end."

**Write a full-context handoff at every milestone AND before any expected limit.**
A milestone is any merge, deploy, rollout, fix verified, or a sub-task finished.

The handoff is ONE file the next session reads FIRST, and it must answer, in
plain language, with zero guessing required:

1. **GOAL** — the one outcome currently being driven (the owner's actual ask).
2. **DONE** — what is finished AND independently verified (not just attempted).
3. **IN-FLIGHT** — what is running right now, where, and how to check on it
   (PID / job id / file path / dashboard URL).
4. **NEXT** — the single concrete next action, specific enough to execute blind.
5. **BLOCKERS** — what is waiting on the owner, a credential, an asset, or a
   decision (name the exact missing input).
6. **STATE LOCATION** — where the live state actually lives (ledger file, build
   state json, queue file) so the resume reads ground truth, not a stale claim.

Rules that make the handoff trustworthy:

- **Ground truth over memory.** Capture state from the system (file mtimes, job
  status, build-state json, git/version) — never from "I remember I did X."
- **Never write "done" for unverified work.** If it was not independently
  checked, it is IN-FLIGHT, not DONE.
- **Overwrite the live snapshot, append the history.** Keep one current snapshot
  file (overwritten each update) plus an append-only changelog line per
  milestone so nothing is silently lost.
- **On any resume after a clip: read the handoff FIRST, then continue.** Do not
  restart work that was already verified-done; do not abandon in-flight work.

This is how multi-session and long-autonomous work survives. Treat the handoff as
part of the task, not an afterthought.

---

FCHEOF
}

# ---------------------------------------------------------------------------
# emit_reporting_contract_block
#
# Prints (stdout) the HONEST REPORTING CONTRACT doctrine block, marker first.
# ---------------------------------------------------------------------------
emit_reporting_contract_block() {
    cat <<'RCEOF'
<!-- REPORTING_CONTRACT_V1 -->
## HONEST REPORTING CONTRACT (no false "done", no silence)

The owner cannot see what you are doing. Silence reads as "stuck" and a false
"done" destroys trust. So you REPORT — proactively, unprompted, and honestly —
using exactly three states:

- **DONE** — finished AND independently verified. "Done" means the end-to-end
  outcome the owner asked for actually happened and you confirmed it from ground
  truth (ran the gate, opened the file, hit the endpoint). Never report DONE on
  an attempt, an intention, or a sub-agent's unverified claim.
- **RUNNING** — actively in progress. Say what is running, where, and when you
  will check back. Post a RUNNING update at the start of long work and at each
  meaningful step — do NOT go silent for long stretches.
- **BLOCKED** — cannot proceed without a specific input. Name the exact missing
  thing (credential, asset, decision, access) and what unblocks it. A BLOCKED
  report is never a failure — it is the fastest path to getting unblocked.

Discipline:

1. **Post status unprompted.** Don't wait to be asked "is it done yet?" Lead with
   the state (DONE / RUNNING / BLOCKED), then the one-line detail.
2. **Verify before you claim DONE — as a SEPARATE step.** Verification is its own
   gate: independently confirm the result. If you cannot confirm it, it is not
   DONE.
3. **Never quote a sub-agent's claim back as fact.** A sub-agent saying "done" is
   a HYPOTHESIS until you verify it yourself.
4. **Report every sub-agent / parallel job.** When you fan work out, report and
   verify each strand; never let one silently drop.
5. **Match effort to reporting.** Big or long-running work gets more RUNNING
   checkpoints, not fewer.

Under-reporting and false-done are the two failures that erode trust fastest.
When in doubt: report more, and only ever call it DONE once it is verified.

---

RCEOF
}

# ---------------------------------------------------------------------------
# _adb_stamp_block <agents_file> <marker> <emitter_fn> <label>
#
# Internal: idempotently append <emitter_fn> output to <agents_file> unless
# <marker> is already present. Creates the file (and parent dir) if absent.
# ---------------------------------------------------------------------------
_adb_stamp_block() {
    local _file="$1" _marker="$2" _emit="$3" _label="$4"

    if [ -z "$_file" ]; then
        echo "  [agents-doctrine] no AGENTS.md path given for $_label — skipping" >&2
        return 0
    fi

    local _dir
    _dir="$(dirname "$_file")"
    [ -d "$_dir" ] || mkdir -p "$_dir" 2>/dev/null || {
        echo "  [agents-doctrine] cannot create dir $_dir for $_label — skipping" >&2
        return 1
    }
    [ -e "$_file" ] || touch "$_file" 2>/dev/null || {
        echo "  [agents-doctrine] cannot create $_file for $_label — skipping" >&2
        return 1
    }

    if grep -qF "$_marker" "$_file" 2>/dev/null; then
        echo "  [agents-doctrine] $_label already present in $_file — no-op"
        return 0
    fi

    # Ensure a blank-line separator before the appended block (only if the file
    # is non-empty and does not already end in a blank line).
    if [ -s "$_file" ] && [ -n "$(tail -c 1 "$_file" 2>/dev/null)" ]; then
        printf '\n' >> "$_file" 2>/dev/null || return 1
    fi

    if "$_emit" >> "$_file" 2>/dev/null; then
        echo "  [agents-doctrine] $_label stamped into $_file"
        return 0
    fi
    echo "  [agents-doctrine] FAILED to stamp $_label into $_file" >&2
    return 1
}

# ---------------------------------------------------------------------------
# stamp_full_context_handoff <AGENTS_FILE>
# ---------------------------------------------------------------------------
stamp_full_context_handoff() {
    _adb_stamp_block "$1" "$FULL_CONTEXT_HANDOFF_MARKER" \
        emit_full_context_handoff_block "FULL CONTEXT HANDOFF"
}

# ---------------------------------------------------------------------------
# stamp_reporting_contract <AGENTS_FILE>
# ---------------------------------------------------------------------------
stamp_reporting_contract() {
    _adb_stamp_block "$1" "$REPORTING_CONTRACT_MARKER" \
        emit_reporting_contract_block "HONEST REPORTING CONTRACT"
}

# ---------------------------------------------------------------------------
# stamp_agents_doctrine_blocks <AGENTS_FILE>
#
# Convenience: stamp both blocks in canonical order. Returns non-zero if EITHER
# stamp fails to write (a no-op from an already-present marker is success).
# ---------------------------------------------------------------------------
stamp_agents_doctrine_blocks() {
    local _file="$1" _rc=0
    stamp_full_context_handoff "$_file" || _rc=1
    stamp_reporting_contract   "$_file" || _rc=1
    return "$_rc"
}
