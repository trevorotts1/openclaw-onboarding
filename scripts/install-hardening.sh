#!/usr/bin/env bash
# install-hardening.sh (Mac) — defensive checks/fixes from 2-day forensics
# (2026-05-23 / 2026-05-24). Mac-applicable subset of the VPS bundle.
#
# Each function is independently safe (idempotent, no-op when already correct).
# All functions return 0 unconditionally — hardening is best-effort.
#
# Mac-applicable findings this script implements:
#   #13  hooks.token auto-generate when hooks.enabled is true without one
#   #16  brew (not apt) — guard any package-install assumption
#   #20  yt-dlp + whisper-cpp + ffmpeg backfill if missing (Skill 22)
set -uo pipefail

_oc_root() {
    if [[ -d "$HOME/.openclaw" ]]; then
        echo "$HOME/.openclaw"
    else
        echo ""
    fi
}

_log() { echo "[install-hardening] $*"; }

# ─── #13: hooks.token auto-generate ──────────────────────────────────────────
harden_hooks_token() {
    local oc_root
    oc_root="$(_oc_root)"
    [ -z "$oc_root" ] && return 0
    local cfg="$oc_root/openclaw.json"
    [ -f "$cfg" ] || return 0

    python3 - "$cfg" <<'PYEOF' || true
import json, sys, secrets, os
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception as e:
    print(f"[install-hardening] hooks.token check: cannot parse {p}: {e}", file=sys.stderr)
    sys.exit(0)
hooks = d.get("hooks") or {}
if not hooks.get("enabled"):
    sys.exit(0)
if hooks.get("token"):
    sys.exit(0)
hooks["token"] = secrets.token_hex(32)
d["hooks"] = hooks
tmp = p + ".tmp-hardening"
with open(tmp, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
os.replace(tmp, p)
print(f"[install-hardening] hooks.enabled=true but hooks.token was missing — generated one (64 hex chars).")
PYEOF
    return 0
}

# ─── #16: brew assumption guard ──────────────────────────────────────────────
# Mac uses Homebrew, NOT apt. If a previous install.sh edit accidentally
# called apt, we'd silently fail. This function asserts brew is the package
# manager and warns clearly if it's not.
harden_brew_check() {
    if [ "$(uname -s)" != "Darwin" ]; then return 0; fi
    if ! command -v brew >/dev/null 2>&1; then
        _log "WARNING: Homebrew not on PATH. Mac install assumes brew is the package manager."
        _log "WARNING: Install brew from https://brew.sh before running Skill 22 (book-to-persona)."
    fi
    return 0
}

# ─── #20: yt-dlp + whisper + ffmpeg backfill (Skill 22 dependency) ───────────
# These tools power the YouTube/local-video branch of Skill 22's
# add-persona-from-source.sh. They were not previously installed on Mac
# by default. Use brew (Mac) — never apt.
harden_skill22_media_tools() {
    if [ "$(uname -s)" != "Darwin" ]; then return 0; fi
    if ! command -v brew >/dev/null 2>&1; then return 0; fi

    local need=()
    command -v yt-dlp     >/dev/null 2>&1 || need+=(yt-dlp)
    command -v whisper-cpp >/dev/null 2>&1 || command -v whisper >/dev/null 2>&1 || need+=(whisper-cpp)
    command -v ffmpeg     >/dev/null 2>&1 || need+=(ffmpeg)

    if [ "${#need[@]}" -eq 0 ]; then
        return 0
    fi

    _log "Skill 22 media tools missing on Mac: ${need[*]} — installing via brew (non-blocking)"
    for pkg in "${need[@]}"; do
        brew install "$pkg" >/dev/null 2>&1 || _log "  brew install $pkg failed (non-blocking)"
    done
    return 0
}

# ─── Composite entrypoint ────────────────────────────────────────────────────
run_install_hardening() {
    _log "Running install hardening (Mac, 2-day forensics from 2026-05-23/24)..."
    harden_brew_check
    harden_hooks_token
    harden_skill22_media_tools
    _log "Install hardening complete (best-effort; non-blocking)."
    return 0
}

if [ "${BASH_SOURCE[0]}" = "${0:-}" ]; then
    run_install_hardening
fi
