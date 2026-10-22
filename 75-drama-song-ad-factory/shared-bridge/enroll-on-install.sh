#!/usr/bin/env bash
# enroll-on-install.sh — register THIS box with Drama Studio, once, at install time.
#
# WHY IT EXISTS
#   shared-bridge/studio_bridge.py refuses BOTH `link` and `poll` until the box
#   holds a machine key ("no machine key; run enroll first"), and the only thing
#   that creates that key is `studio_bridge.py enroll`, which needs env
#   DS_ENROLLMENT_SECRET. Until now no installer step called it, so a client's
#   personal studio link could never resolve on an OpenClaw box. This is that
#   step, and install.sh / update-skills.sh both call it.
#
# RULES IT KEEPS
#   * The secret is READ, never printed, never written to a file, never logged,
#     never passed on a command line (`ps` shows argv, not the child's env). It
#     travels in exactly one place: the python child's environment.
#   * No secret -> skip. A client box must still install cleanly when the
#     operator has not injected a studio secret yet: one plain line to stderr,
#     exit 0, nothing written, nothing touched. The optional Studio capability
#     is then recorded as `disabled` (chat intake works without Studio) — the
#     box is never auto-enrolled just to silence logs (SPEC 9.3).
#   * A COMPLETE enrolment receipt already present -> do nothing and say so
#     (enrol is once per box), exit 0. Key presence alone is NOT that check:
#     the receipt is key + URL in one consistent state root with private
#     permissions (D24).
#   * An interrupted/key-only/stray-root record is RECOVERED in place through
#     `enroll --resume`: the valid key is preserved and adopted, the missing
#     machine.url is restored, permissions are tightened — never a second
#     identity, never a discarded key. No HTTP call happens on that path.
#   * Every other refusal -> one warning line, exit 0. The installers call this
#     bare under `set -e`; a studio that is down must never fail a client
#     install, and a failed enroll is simply retried on the next update pass.
#
# STATE ROOT: resolved through the bridge's own `state-dir` — the ONE platform
# contract (mac/Hostinger $HOME/.drama-studio; Contabo
# /home/node/.openclaw/.drama-studio). Never restated here.
#
# SECRET RESOLUTION — the same order the onboarding installer already trusts
#   1. the live process environment (`install.sh` search_env_var_mac source 1).
#   2. the canonical env files, in the order install.sh's Tier-1 walker lists
#      them, plus the VPS container store build_env_locations() reports.
#   install.sh additionally walks all of $HOME for stray .env files (its Tier
#   2); that walk is deliberately not repeated here — the operator's documented
#   stores are all covered and a second walk on a client box costs time for a
#   secret that only the operator injects.
#
# Usage: bash enroll-on-install.sh        # no arguments, by design
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
BRIDGE="$HERE/studio_bridge.py"

# ---- secret resolution (value never leaves this function's caller variable) --
resolve_secret() {
    # 1. live process environment first — the same precedence the installer uses.
    if [ -n "${DS_ENROLLMENT_SECRET:-}" ]; then
        printf '%s' "$DS_ENROLLMENT_SECRET"
        return 0
    fi

    # 2. canonical env files, installer order first-hit-wins. `grep -m1` stops at
    #    the first assignment; the whole line is captured into a variable and
    #    never echoed, so the value cannot reach the transcript.
    local f line
    for f in \
        "${HOME}/.openclaw/secrets/.env" \
        "${HOME}/.openclaw/secrets/secrets.env" \
        "${HOME}/.openclaw/.env" \
        "${HOME}/.openclaw/env" \
        "${HOME}/clawd/secrets/.env" \
        "${HOME}/clawd/.env" \
        "${HOME}/.config/openclaw/secrets.env" \
        "${HOME}/.config/openclaw/.env" \
        "${HOME}/.config/clawd/.env" \
        "${HOME}/.env" \
        "/data/.openclaw/secrets/.env"; do
        [ -f "$f" ] || continue
        # -a: a stray binary byte must not turn a real hit into "Binary file matches".
        line=$(grep -a -m1 -E '^[[:space:]]*(export[[:space:]]+)?DS_ENROLLMENT_SECRET[[:space:]]*=' "$f" 2>/dev/null) || continue
        [ -n "$line" ] || continue
        line="${line#*=}"
        # strip one layer of matching quotes the way a sourced .env would
        case "$line" in
            \"*\") line="${line#\"}"; line="${line%\"}" ;;
            \'*\') line="${line#\'}"; line="${line%\'}" ;;
        esac
        [ -n "$line" ] || continue
        printf '%s' "$line"
        return 0
    done
    return 1
}

# ---- 1. refuse to run without the bridge itself ------------------------------
if [ ! -f "$BRIDGE" ]; then
    echo "warn: drama-studio enroll skipped: bridge not found ($BRIDGE)" >&2
    exit 0
fi
PYTHON="$(command -v python3 2>/dev/null || true)"
if [ -z "$PYTHON" ]; then
    echo "warn: drama-studio enroll skipped: python3 not on PATH" >&2
    exit 0
fi

# The ONE persistent state-root contract (D24), from the bridge itself.
STATE="$("$PYTHON" "$BRIDGE" state-dir 2>/dev/null | head -n 1)"
[ -n "$STATE" ] || STATE="${DRAMA_STUDIO_STATE:-${HOME:-}/.drama-studio}"

# ---- 2. a COMPLETE receipt means we are already enrolled ---------------------
# Checked here, not left to the bridge, so the already-enrolled case is a clean
# exit 0 instead of a refusal the installers would have to special-case. Key
# presence alone is NOT the check (D24): `enroll --resume` validates key + URL
# in one consistent root with private permissions, and repairs an interrupted
# or key-only record in place — locally, never re-enrolling, never dropping a
# valid key.
if [ -f "$STATE/machine.key" ] || [ -f "${HOME:-}/.drama-studio/machine.key" ]; then
    OUT=""
    RC=0
    OUT="$("$PYTHON" "$BRIDGE" enroll --resume 2>&1)" || RC=$?
    if [ "$RC" -eq 0 ]; then
        if printf '%s' "$OUT" | grep -q '"recovered": true'; then
            echo "drama-studio: enrollment receipt recovered at $STATE (valid key preserved, no re-enrol)"
        else
            echo "drama-studio: already enrolled (machine key present); enroll is once per box"
        fi
        exit 0
    fi
    CODE=$(printf '%s' "$OUT" | sed -n 's/.*"code"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    echo "warn: drama-studio receipt could not be validated${CODE:+ ($CODE)} — the operator can repair it by hand. Install continues." >&2
    exit 0
fi

# ---- 3. no secret -> skip, leave the box untouched ---------------------------
# The optional capability is recorded as `disabled` so the idle poller stays
# quiet instead of failing every tick (SPEC 9.3). Chat intake needs nothing here.
SECRET="$(resolve_secret || true)"
if [ -z "$SECRET" ]; then
    "$PYTHON" "$BRIDGE" capability --record disabled >/dev/null 2>&1 || true
    echo "skipped: DS_ENROLLMENT_SECRET not set" >&2
    exit 0
fi

# ---- 4. enroll ----------------------------------------------------------------
# The secret is handed to the child as ENVIRONMENT ONLY. It is never part of
# argv, so it cannot appear in `ps`, a process listing or a shell history. The
# child's own stdout is captured and NOT echoed: the studio is a remote server
# and could echo anything back, so only locally-known facts are printed.
OUT=""
RC=0
OUT="$(DS_ENROLLMENT_SECRET="$SECRET" "$PYTHON" "$BRIDGE" enroll 2>&1)" || RC=$?
SECRET=""

if [ "$RC" -eq 0 ]; then
    echo "drama-studio: enrolled this box (machine key written to $STATE/machine.key)"
    exit 0
fi

# Refused. Surface only the refusal CODE — an identifier, never a payload. The
# operator DID inject a secret, so the capability is needs-enrollment: the
# next pass retries, and the optional poller stays quiet meanwhile.
"$PYTHON" "$BRIDGE" capability --record needs-enrollment >/dev/null 2>&1 || true
CODE=$(printf '%s' "$OUT" | sed -n 's/.*"code"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
echo "warn: drama-studio enroll refused${CODE:+ ($CODE)} — this box is not enrolled; the operator can enroll it by hand. Install continues." >&2
exit 0
