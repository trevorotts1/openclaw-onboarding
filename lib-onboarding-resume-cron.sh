#!/usr/bin/env bash
# ============================================================
# lib-onboarding-resume-cron.sh — shared onboarding-resume cron installer
# ------------------------------------------------------------
# v17.0.21 — single canonical definition of install_onboarding_resume_cron(),
# SOURCED by BOTH install.sh (fresh install, Step 13b) and update-skills.sh
# (roll/update that writes the UPDATE-PENDING flag). Previously this function
# lived ONLY inline in install.sh, so a fleet HOT-PATCH via update-skills.sh
# added new skills + wrote the activation flag but installed NO resume cron —
# roll-time activation was never self-healing. This lib gives both entry points
# the SAME battle-tested installer with no copy-paste drift.
#
# WHAT THE CRON DOES
#   The onboarding-resume cron is a */30 SILENT main-session self-ping. Every
#   30 min, while any skill is still pending|downloaded|wired|qc-failed, it
#   re-dispatches the activation+verification prompt into the agent's OWN main
#   session (runtime-compatible flags via _oc_cron_silent_main: `--session main
#   --system-event` on 2026.6.11+, `--session-target main --message` on older
#   CLIs, + --light-context). It NEVER stops on a
#   self-declared "done" — only on a real gate-pass. All of the boundedness
#   (MAX_RUNS_BEFORE_ESCALATE, 402/429 backoff, Rescue-Rangers escalation to the
#   OPERATOR, and HARD self-delete) lives in scripts/resume-onboarding.sh, which
#   the prompt invokes; the cron self-removes on gate-pass. This installer only
#   REGISTERS that cron.
#
# SILENT INVARIANT (enforced by tests/unit/cron-owner-chat-guard.test.sh)
#   The cron registration carries NO --channel telegram / --to / --announce. It
#   is a main-session agent-message cron — it can NEVER auto-deliver to a
#   client chat. Owner-facing status is surfaced only by the agent's own
#   deliberate `message send`, and operator escalation is handled by the bounded
#   resume-onboarding.sh (operator / Rescue Rangers), never a client push.
#
# IDEMPOTENT
#   If an onboarding-resume cron already exists it is LEFT IN PLACE (no stacking).
#
# DEPENDENCIES (all resolved defensively so the lib works from either caller):
#   openclaw CLI, python3-free; reads $ONBOARDING_DIR / $OC_PERSISTENT_SCRIPTS_DIR
#   / $OC_CONFIG to locate the resume prompt+script (survives update-skills.sh's
#   temp-clone cleanup), $TELEGRAM_DEFAULT_AGENT_CACHED (optional), $LOG_FILE
#   (optional). step/success/warn/note and _cron_create_positional are used if
#   the caller already defines them; otherwise minimal fallbacks are provided.
# ============================================================

# Re-source guard.
[ -n "${__ONBOARDING_RESUME_CRON_LIB_SOURCED:-}" ] && return 0
__ONBOARDING_RESUME_CRON_LIB_SOURCED=1

# ── Minimal UI-helper fallbacks (install.sh already defines richer ones; these
#    only fill in for update-skills.sh, which logs with plain echo). Guarded so
#    a caller's own helpers always win. ─────────────────────────────────────────
command -v step    >/dev/null 2>&1 || step()    { echo ""; echo "  $1"; }
command -v success >/dev/null 2>&1 || success() { echo "  ✓ $1"; }
command -v note    >/dev/null 2>&1 || note()    { echo "  ℹ️  $1"; }
command -v warn    >/dev/null 2>&1 || warn()    { echo "  ⚠️  $1"; }

# ── Cron-create positional-form fallback (2026.6.8 flag drift). Guarded: if the
#    caller (install.sh) already defines it, that copy wins. ────────────────────
command -v _cron_create_positional >/dev/null 2>&1 || _cron_create_positional() {
    local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5" _lc="${6:-}"
    local _args=( "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --session main )
    [ -n "$_tz" ] && _args+=( --tz "$_tz" )
    [ "$_lc" = "lc" ] && _args+=( --light-context )
    local _out="" _rc=0
    _out=$(openclaw cron create "${_args[@]}" 2>&1) || _rc=$?
    echo "$_out" >> "${LOG_FILE:-/dev/null}"
    return "$_rc"
}

# ── Runtime-compatible SILENT main-session cron registration. ──────────────────
# (fix/cron-flag-skew — updater↔runtime cron-flag skew.)
# The silent main-session agent-cron shape changed across OpenClaw CLI builds:
#   • 2026.5.x / 2026.6.8 : `--session-target main --message "<prompt>"`
#   • 2026.6.11+          : `--session-target` was REMOVED and main-session jobs
#     now REQUIRE `--system-event` (a `--message` main job is rejected with
#     "Main jobs require --system-event"), so the accepted form is
#     `--session main --system-event "<prompt>"`.
# A rolled box on 2026.6.11 silently failed to install its self-heal cron because
# the installer only ever emitted `--session-target main --message`.
#
# We feature-probe `openclaw cron add --help` to pick the form the INSTALLED
# runtime advertises, then fall through the OTHER known-good forms so a mis-probe
# still recovers, and finally degrade to a SILENT isolated agent-message job
# (`--message "<prompt>" --no-deliver`) so a cron ALWAYS lands under the name
# (the QC self-heal loop only checks the name). Every path is silent (no
# --channel/--to/--announce) and NONE hard-fails the caller. A rejected form
# creates nothing (the CLI validates before insert), so the ordered attempts are
# safe and idempotent under --name. Guarded so a caller's own copy wins.
#   $1 name  $2 agent  $3 cron-expr  $4 tz  $5 prompt ; $6.. = extra passthrough
#            flags (e.g. --light-context --thinking high --exact --description …)
# Returns 0 if a create succeeded, 1 only if every form failed.
command -v _oc_cron_silent_main >/dev/null 2>&1 || _oc_cron_silent_main() {
    local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5"; shift 5
    local _extra=( "$@" )
    local _n=${#_extra[@]}
    local _base=( --name "$_name" --agent "$_agent" --cron "$_expr" --tz "$_tz" )
    local _help _modern=0
    _help="$(openclaw cron add --help 2>&1 || true)"
    printf '%s' "$_help" | grep -qE '^[[:space:]]*--session[[:space:]<]' && _modern=1
    local _order _k
    if [ "$_modern" = "1" ]; then _order="modern old"; else _order="old modern"; fi
    for _k in $_order; do
        if [ "$_k" = "modern" ]; then
            # 2026.6.11+ : main-session jobs REQUIRE --system-event (not --message).
            [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
            openclaw cron create "${_base[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
        else
            # 2026.6.8 / 2026.5.x : --session-target main + --message.
            [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
            openclaw cron create "${_base[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
        fi
    done
    # docs-canonical positional form (2026.6.8): schedule + prompt positional.
    openclaw cron create "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --tz "$_tz" --session main >/dev/null 2>&1 && return 0
    # Last resort — SILENT isolated agent-message job so a cron still lands under
    # this name (self-heal loop keeps working); --no-deliver keeps it OFF the client chat.
    openclaw cron create "${_base[@]}" --message "$_prompt" --no-deliver >/dev/null 2>&1 && return 0
    return 1
}

# ------------------------------------------------------------
# _resolve_resume_prompt_file — echo the first readable resume-onboarding-prompt.txt.
#   Candidate order tolerates BOTH callers:
#     install.sh    → $ONBOARDING_DIR is the live pulled tree (pre-cleanup).
#     update-skills → the tree is wiped before the flag write, so prefer the
#                     PERSISTENT copies ($OC_PERSISTENT_SCRIPTS_DIR / $OC_CONFIG).
# ------------------------------------------------------------
_resolve_resume_prompt_file() {
    local _self_dir c
    _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
    for c in \
        "${ONBOARDING_DIR:-}/scripts/resume-onboarding-prompt.txt" \
        "${OC_PERSISTENT_SCRIPTS_DIR:-}/resume-onboarding-prompt.txt" \
        "${OC_CONFIG:-}/scripts/resume-onboarding-prompt.txt" \
        "${_self_dir:+$_self_dir/scripts/resume-onboarding-prompt.txt}"; do
        [ -n "$c" ] && [ -f "$c" ] && { printf '%s' "$c"; return 0; }
    done
    return 1
}

# ------------------------------------------------------------
# install_onboarding_resume_cron
#   Register the */30 SILENT main-session onboarding-resume cron. Idempotent;
#   never messages a client. Returns 0 always (best-effort; never aborts a
#   caller running under set -euo pipefail).
# ------------------------------------------------------------
install_onboarding_resume_cron() {
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping onboarding-resume cron. Re-run update-skills.sh later."
        return 0
    fi
    # IDEMPOTENT: if one already exists, leave it in place (never stack a duplicate).
    if openclaw cron list 2>/dev/null | grep -qi "onboarding-resume"; then
        success "onboarding-resume cron already installed"
        return 0
    fi

    local RESUME_PROMPT_FILE
    RESUME_PROMPT_FILE="$(_resolve_resume_prompt_file || true)"
    if [ -z "$RESUME_PROMPT_FILE" ] || [ ! -f "$RESUME_PROMPT_FILE" ]; then
        warn "resume-onboarding-prompt.txt not found — onboarding-resume cron skipped (older bundle?)"
        return 0
    fi
    # Make the shell guard executable wherever it landed (best-effort).
    chmod +x "${ONBOARDING_DIR:-}/scripts/resume-onboarding.sh" 2>/dev/null || true
    chmod +x "${OC_PERSISTENT_SCRIPTS_DIR:-}/resume-onboarding.sh" 2>/dev/null || true
    chmod +x "${OC_CONFIG:-}/scripts/resume-onboarding.sh" 2>/dev/null || true

    # ── SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons) ──────────────
    # onboarding-resume is a MAINTENANCE self-ping (re-run the onboarding
    # activation + QC gate while any skill is still pending). It must be a SILENT
    # main-session agent-message cron (no --channel/--to/--announce). The gate
    # runs in the agent's own context (log-only); the agent surfaces owner-facing
    # status only via its own deliberate `message send`. No owner target needed →
    # no operator-ID strand, and NEVER an auto-push to a client chat.
    local CHANNEL_AGENT="main"
    if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
        CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
    fi

    local PROMPT_CONTENT
    PROMPT_CONTENT=$(cat "$RESUME_PROMPT_FILE")

    # Register the SILENT main-session resume cron with the form the INSTALLED
    # runtime accepts — 2026.6.11+ needs `--session main --system-event`, older
    # builds use `--session-target main --message`. _oc_cron_silent_main probes
    # `openclaw cron add --help` and falls through every known-good form, so a
    # rolled box on ANY CLI build lands the cron. Interval stays */30 (bounded-
    # resume-cron guard); silent (no --channel/--to/--announce).
    if _oc_cron_silent_main "onboarding-resume" "$CHANNEL_AGENT" "*/30 * * * *" "America/New_York" "$PROMPT_CONTENT" --light-context; then
        success "onboarding-resume cron installed — every 30 min, SILENT main-session (no client auto-announce); interview gate + backoff in scripts/resume-onboarding.sh"
        return 0
    fi

    warn "onboarding-resume cron creation failed. Manual install (SILENT — no client auto-announce):"
    warn "  openclaw cron create --name onboarding-resume --agent $CHANNEL_AGENT \\"
    warn "    --cron '*/30 * * * *' --tz America/New_York \\"
    warn "    --session main --system-event \"\$(cat $RESUME_PROMPT_FILE)\"   # older CLIs: --session-target main --message"
    return 0
}
