#!/usr/bin/env bash
# =============================================================================
# lib-power-resilience.sh — Mac outage-survival primitives (sourceable library)
# =============================================================================
#
# WHY THIS FILE EXISTS
# --------------------
# A fleet audit found that ZERO provisioned Mac boxes survive a power outage.
# Not one accident — a provisioning-template defect. Three root causes:
#
#   1. Every self-healing mechanism (gateway, pm2 resurrect, Command Center
#      tunnel) is installed as a USER LaunchAgent in the `gui/<uid>` domain.
#      A LaunchAgent CANNOT RUN until a console login creates that domain.
#      RunAtLoad=true + KeepAlive=true on a LaunchAgent is a RED HERRING: a
#      perfect LaunchAgent sitting at the login window is a dead process.
#      Measured: one box sat powered on, networked, both tunnels green, with
#      its gateway DEAD for 3d14h. Gateway `runs = 1` — it started the exact
#      second a human logged in.
#
#   2. `pmset autorestart` was never touched by the provisioner. It defaults
#      to 0. Mains returns → the Mac just stays off.
#
#   3. FileVault ON with no auto-login. On Apple Silicon `/Library` and
#      `/Users` are firmlinks onto the encrypted Data volume, so the Mac halts
#      at the PRE-BOOT unlock screen. macOS never finishes booting.
#      *** LaunchDaemons DO NOT RUN EITHER. *** SSH rescue does not exist.
#
# THE ORDER MATTERS: (3) dominates (1) and (2). See THE DECISION below.
#
#
# THE DECISION — checked LaunchAgent + auto-login, NOT a blind LaunchDaemon
# -------------------------------------------------------------------------
# The tempting fix is "convert the gateway to a LaunchDaemon so it runs at
# boot without a login." We measured before choosing. The evidence:
#
#   EVIDENCE FOR a LaunchDaemon being technically possible:
#     - The gateway's env is injected by an explicit wrapper + env file under
#       ~/.openclaw/service-env/ — it does NOT inherit the GUI session's
#       environment, so that env is portable to the system domain.
#     - ProgramArguments uses an ABSOLUTE node path — no PATH inheritance.
#     - The plist carries NO `LimitLoadToSessionType` key — launchd is not
#       restricting the job to an Aqua session.
#     - Secrets live in ~/.openclaw/secrets/.env (a FILE). No Keychain refs.
#       A daemon has no login keychain; had secrets been in the Keychain this
#       would have been fatal. They are not.
#     - browser.headless = true — Chrome runs headless. Headless Chrome needs
#       NO WindowServer, so the biggest suspected GUI dependency is not one.
#
#   EVIDENCE AGAINST converting:
#     - The gateway plist carries `ProcessType = Interactive` — the upstream
#       OpenClaw CLI deliberately classifies this as a user-interactive job.
#     - Session-coupled plugins are ENABLED on real boxes (imessage,
#       bluebubbles). iMessage reads ~/Library/Messages/chat.db, which is
#       TCC-protected (Full Disk Access). TCC consent is granted to a binary
#       in the LOGGED-IN USER's TCC database and cannot be prompted for from
#       the system domain. A daemon silently breaks iMessage.
#     - `talk-voice`, `canvas`, and `phone-control` are in plugins.allow
#       fleet-wide. Any client can enable them. Those genuinely need an Aqua
#       session (audio output routing, screen capture, Accessibility events).
#     - *** The gateway plist is OWNED AND REWRITTEN by the upstream
#       `openclaw` CLI (`openclaw gateway install`). This repo does not own
#       that file. A hand-converted LaunchDaemon is CLOBBERED on the next
#       `openclaw update`. A fix that silently un-fixes itself is worse than
#       no fix. ***
#
#   THE DECISIVE ARGUMENT:
#     A LaunchDaemon DOES NOT FIX THE 7 FILEVAULT BOXES AT ALL. With FileVault
#     ON on Apple Silicon the machine never reaches the point where launchd
#     starts system daemons. So the daemon conversion buys literally NOTHING
#     on the majority of the broken fleet, while costing GUI capability and
#     fighting the upstream CLI for ownership of the plist.
#
#     Auto-login, by contrast, makes the GUI session EXIST at boot. It fixes
#     100% of the login-gated services AT ONCE — gateway, pm2 resurrect, the
#     Command Center tunnel, the self-heal remediator — with ZERO divergence
#     from the upstream-managed plist, and with full GUI capability retained.
#     Auto-login strictly dominates the daemon conversion, PROVIDED FileVault
#     is off — which is already required for ANY unattended recovery.
#
#   THEREFORE:
#     PRIMARY PATH  = LaunchAgent + auto-login as a CHECKED PRECONDITION.
#                     The provisioner FAILS LOUD if it is about to lay a
#                     login-gated service onto a box that never logs in.
#     FALLBACK PATH = an explicit, opt-in, capability-gated LaunchDaemon
#                     (`pr_render_gateway_daemon_plist`) for a genuinely
#                     headless box that enables NO session-coupled plugin.
#                     Opt-in, never automatic — see pr_gateway_session_coupled.
#
# TRADE-OFF, STATED PLAINLY: auto-login means anyone with physical access to a
# powered-on box lands on an unlocked desktop. That is the price of unattended
# recovery. A client who refuses it is choosing a box that a human must
# physically attend after every power cut. The gate says so out loud.
#
#
# TESTABILITY
# -----------
# Every external command and system path is behind an overridable variable so
# tests can inject fixtures without root and without touching a live box.
# Mutating functions are no-ops when PR_DRY_RUN=1.
#
# Source it:  . platform/mac/power-resilience/lib-power-resilience.sh
# =============================================================================

# ---- Injectable seams (tests override these) --------------------------------
PR_FDESETUP="${PR_FDESETUP:-/usr/bin/fdesetup}"
PR_PMSET="${PR_PMSET:-/usr/bin/pmset}"
PR_DEFAULTS="${PR_DEFAULTS:-/usr/bin/defaults}"
PR_SYSSETUP="${PR_SYSSETUP:-/usr/sbin/networksetup}"
PR_IOREG="${PR_IOREG:-/usr/sbin/ioreg}"
PR_LOGINWINDOW_PLIST="${PR_LOGINWINDOW_PLIST:-/Library/Preferences/com.apple.loginwindow}"
PR_OPENCLAW_JSON="${PR_OPENCLAW_JSON:-$HOME/.openclaw/openclaw.json}"
PR_SECRETS_DIR="${PR_SECRETS_DIR:-$HOME/.openclaw/secrets}"
PR_LAUNCHDAEMONS_DIR="${PR_LAUNCHDAEMONS_DIR:-/Library/LaunchDaemons}"
PR_LAUNCHAGENTS_DIR="${PR_LAUNCHAGENTS_DIR:-$HOME/Library/LaunchAgents}"
PR_MARKER_ATTENDED="${PR_MARKER_ATTENDED:-$HOME/.openclaw/ATTENDED-ONLY-BOX}"
PR_DRY_RUN="${PR_DRY_RUN:-0}"

# Canonical launchd labels. ONE name each — the fleet currently carries three
# hand-rolled pm2 names (com.<user>.pm2-resurrect, pm2.<user>.plist,
# io.pm2.launch.plist). That drift ends here.
PR_PM2_LABEL="com.openclaw.pm2-resurrect"
PR_PM2_LEGACY_GLOBS=('com.*.pm2-resurrect' 'pm2.*' 'io.pm2.launch' 'pm2')
PR_GATEWAY_LABEL="ai.openclaw.gateway"
PR_CC_TUNNEL_LABEL="com.cloudflare.command-center"

# Plugins that genuinely require a logged-in Aqua session. A box with ANY of
# these enabled must NOT be converted to a system-domain LaunchDaemon.
#   imessage / bluebubbles → TCC Full Disk Access on ~/Library/Messages/chat.db
#   talk-voice             → per-user audio output device routing
#   canvas / phone-control → screen capture + Accessibility (TCC, GUI consent)
PR_SESSION_COUPLED_PLUGINS="imessage bluebubbles talk-voice canvas phone-control"

# Exit codes
PR_EX_CONFIG=78   # EX_CONFIG — a precondition is wrong; refuse to proceed.

# ---- Logging ----------------------------------------------------------------
pr_log()  { printf '[power-resilience] %s\n' "$*"; }
pr_warn() { printf '[power-resilience] WARNING: %s\n' "$*" >&2; }
pr_err()  { printf '[power-resilience] ERROR: %s\n' "$*" >&2; }
pr_run()  {
    if [ "$PR_DRY_RUN" = "1" ]; then
        printf '[power-resilience] DRY-RUN would run: %s\n' "$*"
        return 0
    fi
    "$@"
}

# =============================================================================
# DEFECT 3 — FileVault / auto-login: THE HARD GATE
# =============================================================================

# pr_filevault_status → prints "On" | "Off" | "Unknown"
# `fdesetup status` prints "FileVault is On." / "FileVault is Off."
pr_filevault_status() {
    local out
    if ! command -v "$PR_FDESETUP" >/dev/null 2>&1 && [ ! -x "$PR_FDESETUP" ]; then
        echo "Unknown"; return 0
    fi
    out="$("$PR_FDESETUP" status 2>/dev/null || true)"
    case "$out" in
        *"FileVault is On"*)  echo "On" ;;
        *"FileVault is Off"*) echo "Off" ;;
        *)                    echo "Unknown" ;;
    esac
}

# pr_autologin_user → prints the configured auto-login user, or "" if unset.
# Source of truth: /Library/Preferences/com.apple.loginwindow → autoLoginUser
pr_autologin_user() {
    local u
    u="$("$PR_DEFAULTS" read "$PR_LOGINWINDOW_PLIST" autoLoginUser 2>/dev/null || true)"
    printf '%s' "$u"
}

# pr_is_laptop → rc 0 if this Mac has an internal battery, else rc 1.
# A battery-backed Mac does not lose power when the mains does, so
# `autorestart` is largely meaningless there and `sleep 0` on battery is a
# drain hazard. Handled explicitly rather than pretending it is a mini.
pr_is_laptop() {
    if [ -n "${PR_FORCE_LAPTOP:-}" ]; then
        [ "$PR_FORCE_LAPTOP" = "1" ] && return 0 || return 1
    fi
    "$PR_IOREG" -rc AppleSmartBattery 2>/dev/null | grep -q "AppleSmartBattery"
}

# -----------------------------------------------------------------------------
# pr_assert_unattended_boot_capable — THE GATE. Call this in provisioning
# BEFORE laying down any login-gated service.
#
# PASSES only when BOTH hold:
#     fdesetup status == Off      AND      autoLoginUser is set
#
# Anything else → rc 78 (EX_CONFIG) with a message that explains the trade-off.
#
# There is exactly one, deliberately clumsy, fully-auditable opt-out:
#     OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX=i-will-be-physically-present
# It does NOT make the box resilient. It records that a human accepted that a
# person with the disk password must be physically at the machine after every
# power loss. It writes a durable marker so the acceptance gate and every
# future audit report this box as DEGRADED forever.
# -----------------------------------------------------------------------------
pr_assert_unattended_boot_capable() {
    local fv al problems=0
    fv="$(pr_filevault_status)"
    al="$(pr_autologin_user)"

    pr_log "FileVault status : $fv"
    pr_log "Auto-login user  : ${al:-<UNSET>}"

    [ "$fv" = "Off" ] || problems=1
    [ -n "$al" ]      || problems=1

    if [ "$problems" -eq 0 ]; then
        pr_log "GATE PASS: FileVault is Off and auto-login is set — this box can boot"
        pr_log "           to a GUI session with no human present. Login-gated"
        pr_log "           LaunchAgents (gateway, pm2, tunnels) will start after a"
        pr_log "           power cut."
        return 0
    fi

    # ---- FAIL LOUD ----------------------------------------------------------
    {
        echo ""
        echo "================================================================"
        echo " PROVISIONING REFUSED — THIS BOX CANNOT RECOVER FROM A POWER CUT"
        echo "================================================================"
        echo ""
        if [ "$fv" != "Off" ]; then
            echo "  FileVault is '$fv' (required: Off)."
            echo ""
            echo "  WHY THIS IS FATAL, not cosmetic:"
            echo "    On Apple Silicon, /Library and /Users are firmlinks onto the"
            echo "    ENCRYPTED Data volume. With FileVault ON, a Mac that loses"
            echo "    power halts at the PRE-BOOT unlock screen and macOS NEVER"
            echo "    FINISHES BOOTING."
            echo ""
            echo "    *** LaunchDaemons DO NOT RUN EITHER. ***"
            echo "    *** SSH rescue DOES NOT WORK. There is no sshd yet.     ***"
            echo ""
            echo "    A correctly-built root LaunchDaemon with RunAtLoad=true is"
            echo "    still 100% dark after a power cut on this box. There is no"
            echo "    software fix. A human holding the disk password must be"
            echo "    PHYSICALLY PRESENT at the machine after EVERY power loss."
            echo ""
        fi
        if [ -z "$al" ]; then
            echo "  Auto-login is NOT set (autoLoginUser is empty)."
            echo ""
            echo "  WHY THIS IS FATAL:"
            echo "    The gateway, pm2 resurrect, the Command Center tunnel and the"
            echo "    self-heal remediator are all USER LaunchAgents. They live in"
            echo "    the gui/<uid> launchd domain, and THAT DOMAIN DOES NOT EXIST"
            echo "    until a console login creates it."
            echo ""
            echo "    RunAtLoad=true and KeepAlive=true DO NOT HELP. They are a red"
            echo "    herring. A perfect LaunchAgent at a login window is a dead"
            echo "    process. Measured on a real client box: gateway DEAD for"
            echo "    3 days 14 hours while the machine was powered on, networked,"
            echo "    and both tunnels were green. It started the exact second a"
            echo "    human logged in."
            echo ""
        fi
        echo "  TO FIX (a human must do this AT the machine — it cannot be done"
        echo "  remotely, because turning FileVault off requires the disk password):"
        echo ""
        echo "    1. System Settings → Privacy & Security → FileVault → Turn Off."
        echo "       Wait for decryption to finish."
        echo "    2. System Settings → Users & Groups → Automatically log in as"
        echo "       → select the box's user."
        echo "    3. Re-run provisioning."
        echo ""
        echo "  THE TRADE-OFF, STATED PLAINLY:"
        echo "    FileVault OFF + auto-login  → the box recovers from a power cut"
        echo "                                  with NO human present. Anyone with"
        echo "                                  physical access to a powered-on box"
        echo "                                  lands on an unlocked desktop."
        echo "    FileVault ON                → the disk is encrypted at rest, and"
        echo "                                  UNATTENDED RECOVERY IS IMPOSSIBLE."
        echo "                                  Every power loss needs a person on"
        echo "                                  site with the disk password."
        echo ""
        echo "    Pick one. There is no configuration that gives you both."
        echo "================================================================"
        echo ""
    } >&2

    if [ "${OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX:-}" = "i-will-be-physically-present" ]; then
        pr_warn "OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX acknowledged."
        pr_warn "Continuing with an ATTENDED-ONLY box. This box is DEGRADED by"
        pr_warn "design: it will NOT come back on its own after a power cut."
        if [ "$PR_DRY_RUN" != "1" ]; then
            mkdir -p "$(dirname "$PR_MARKER_ATTENDED")" 2>/dev/null || true
            {
                echo "This box CANNOT recover from a power outage without a human on site."
                echo "filevault=$fv autologin=${al:-<unset>}"
                echo "acknowledged_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            } > "$PR_MARKER_ATTENDED" 2>/dev/null || true
        fi
        return 0
    fi

    pr_err "Refusing to lay login-gated services onto a box that never logs in."
    pr_err "This is the exact bug that shipped undead Macs. Fix the box, re-run."
    return "$PR_EX_CONFIG"
}

# =============================================================================
# DEFECT 2 — pmset. Absent from the provisioner entirely until now.
# =============================================================================
pr_apply_pmset() {
    local rc=0
    if pr_is_laptop; then
        pr_log "Laptop detected (internal battery present)."
        pr_log "  'autorestart' is largely MEANINGLESS on a battery-backed Mac: it"
        pr_log "  does not lose power when the mains does — it keeps running on"
        pr_log "  battery. The real outage risk on a laptop is a lid-close sleep or"
        pr_log "  a fully-drained battery, neither of which autorestart addresses."
        pr_log "  Applying AC-ONLY (-c) settings. NOT setting 'sleep 0' on battery:"
        pr_log "  that would drain the battery flat and is a worse failure mode."
        pr_run "$PR_PMSET" -c sleep 0        || rc=1
        pr_run "$PR_PMSET" -c disksleep 0    || rc=1
        pr_run "$PR_PMSET" -c autorestart 1  || pr_warn "pmset -c autorestart not supported here (ignorable on a laptop)"
        pr_run "$PR_PMSET" -c womp 1         || pr_warn "pmset -c womp not supported here (no wake-on-LAN interface)"
        pr_warn "LAPTOP: unattended outage recovery is NOT fully achievable. Keep it"
        pr_warn "        on AC, lid open or in clamshell on a powered dock. A client"
        pr_warn "        box should be a Mac mini."
    else
        pr_log "Desktop/Mac mini detected. Applying the non-negotiable power policy."
        # -a = all power sources. On a desktop there is only one.
        pr_run "$PR_PMSET" -a autorestart 1  || { pr_err "pmset -a autorestart 1 FAILED"; rc=1; }
        pr_run "$PR_PMSET" -a sleep 0        || { pr_err "pmset -a sleep 0 FAILED"; rc=1; }
        pr_run "$PR_PMSET" -a disksleep 0    || { pr_err "pmset -a disksleep 0 FAILED"; rc=1; }
        pr_run "$PR_PMSET" -a womp 1         || pr_warn "pmset -a womp 1 not supported here (no wake-on-LAN interface)"
    fi
    return "$rc"
}

# pr_verify_pmset → rc 0 only if autorestart=1 and sleep=0 are actually live.
pr_verify_pmset() {
    local g ar sl
    g="$("$PR_PMSET" -g 2>/dev/null || true)"
    ar="$(printf '%s\n' "$g" | awk '/^[[:space:]]*autorestart/{print $2; exit}')"
    sl="$(printf '%s\n' "$g" | awk '/^[[:space:]]*sleep/{print $2; exit}')"
    if [ "$ar" = "1" ] && [ "$sl" = "0" ]; then
        pr_log "pmset VERIFIED: autorestart=1 sleep=0"
        return 0
    fi
    pr_err "pmset NOT applied: autorestart=${ar:-?} (want 1), sleep=${sl:-?} (want 0)"
    return 1
}

# =============================================================================
# DEFECT 4 + 5 — cloudflared: portable binary + token-file (no cleartext token)
# =============================================================================

# pr_resolve_cloudflared → absolute path to cloudflared, or rc 1.
# NEVER hardcode /opt/homebrew/bin/cloudflared: that path DOES NOT EXIST on an
# Intel Mac (Homebrew lives at /usr/local there). One fleet box exits 78
# EX_CONFIG on every launch and has never once run because of that hardcode.
pr_resolve_cloudflared() {
    local p
    p="$(command -v cloudflared 2>/dev/null || true)"
    if [ -z "$p" ]; then
        # launchd jobs get a minimal PATH; probe both Homebrew prefixes.
        for p in /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared; do
            [ -x "$p" ] && break
            p=""
        done
    fi
    if [ -z "$p" ] || [ ! -x "$p" ]; then
        pr_err "cloudflared not found on PATH, /opt/homebrew/bin or /usr/local/bin."
        pr_err "Install it: brew install cloudflared"
        return 1
    fi
    printf '%s' "$p"
}

# pr_install_tunnel_token_file <name> <token> → prints the token-file path.
#
# SECURITY (fleet-wide): tunnel tokens are currently in CLEARTEXT inside
# world-readable root plists AND visible in `ps` output to ANY local user. A
# tunnel token is a bearer credential for the client's public hostname.
# `cloudflared tunnel run --token-file <path>` (verified present in cloudflared
# 2026.6.1) reads the token from a mode-600 file instead. One box already does
# this correctly (com.cloudflare.ghl-inbound) — this is that pattern, generalized.
pr_install_tunnel_token_file() {
    local name="$1" token="$2" dir path
    if [ -z "$name" ] || [ -z "$token" ]; then
        pr_err "pr_install_tunnel_token_file requires <name> <token>"
        return 1
    fi
    dir="$PR_SECRETS_DIR"
    path="$dir/tunnel-${name}.token"
    if [ "$PR_DRY_RUN" = "1" ]; then
        pr_log "DRY-RUN would write mode-600 token file: $path"
        printf '%s' "$path"
        return 0
    fi
    mkdir -p "$dir"
    chmod 700 "$dir" 2>/dev/null || true
    # umask so the file is never even momentarily group/world readable.
    ( umask 077; printf '%s' "$token" > "$path" )
    chmod 600 "$path"
    printf '%s' "$path"
}

# pr_render_tunnel_daemon_plist <label> <cloudflared> <token-file> <user> > out.plist
#
# A ROOT LaunchDaemon (system domain), not a LaunchAgent — a tunnel has no GUI
# dependency whatsoever, so there is no reason for it to be login-gated. The
# token is passed by FILE, never on the command line (which `ps` exposes).
#
# NOTE the honest limit: on a FileVault-ON Apple Silicon box this daemon still
# never runs, because the machine never finishes booting. The FileVault gate is
# what makes this daemon meaningful — not the other way round.
pr_render_tunnel_daemon_plist() {
    local label="$1" bin="$2" tokenfile="$3" user="${4:-root}"
    cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${bin}</string>
        <string>tunnel</string>
        <string>--no-autoupdate</string>
        <string>--protocol</string>
        <string>http2</string>
        <string>run</string>
        <string>--token-file</string>
        <string>${tokenfile}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>/var/log/${label}.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/${label}.err.log</string>
</dict>
</plist>
PLIST
}

# =============================================================================
# DEFECT 1 — launchd: session-coupling probe + the opt-in daemon fallback
# =============================================================================

# pr_gateway_session_coupled → prints the ENABLED plugins that require an Aqua
# session, one per line. Empty output = this box could safely run the gateway
# as a system LaunchDaemon.
pr_gateway_session_coupled() {
    [ -f "$PR_OPENCLAW_JSON" ] || return 0
    PR_SESSION_COUPLED_PLUGINS="$PR_SESSION_COUPLED_PLUGINS" \
    python3 - "$PR_OPENCLAW_JSON" <<'PY' 2>/dev/null || true
import json, os, sys
coupled = os.environ.get("PR_SESSION_COUPLED_PLUGINS", "").split()
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
entries = (d.get("plugins") or {}).get("entries") or {}
for name in coupled:
    e = entries.get(name)
    if isinstance(e, dict) and e.get("enabled") is True:
        print(name)
# A HEADFUL browser needs a WindowServer. A headless one does not.
b = d.get("browser") or {}
if b.get("enabled") is True and b.get("headless") is False:
    print("browser(headful)")
PY
}

# pr_gateway_can_be_daemon → rc 0 only if NOTHING session-coupled is enabled.
pr_gateway_can_be_daemon() {
    local coupled
    coupled="$(pr_gateway_session_coupled)"
    if [ -n "$coupled" ]; then
        pr_log "Gateway is SESSION-COUPLED. Enabled plugins that need a GUI login:"
        printf '%s\n' "$coupled" | sed 's/^/               - /'
        pr_log "  → Keep the LaunchAgent. Auto-login is the fix. Converting this"
        pr_log "    box to a LaunchDaemon would silently break the plugins above"
        pr_log "    (TCC consent cannot be granted from the system domain)."
        return 1
    fi
    pr_log "No session-coupled plugin is enabled — this box COULD run the gateway"
    pr_log "as a system LaunchDaemon (opt-in; see pr_render_gateway_daemon_plist)."
    return 0
}

# pr_render_gateway_daemon_plist <user> <home> <node> <entrypoint> [port]
#
# The OPT-IN fallback for a genuinely headless box. UserName + explicit HOME,
# because a system daemon has neither by default.
#
# *** READ THIS BEFORE USING IT ***
# The `ai.openclaw.gateway` LaunchAgent is written and REWRITTEN by the upstream
# `openclaw` CLI. If you install this daemon, the next `openclaw gateway install`
# / `openclaw update` will re-lay the LaunchAgent and you will be running BOTH,
# fighting over port 18789. Whoever installs this MUST also bootout the agent and
# re-assert after every OpenClaw upgrade. That maintenance burden is exactly why
# this is NOT the default path. Auto-login is.
pr_render_gateway_daemon_plist() {
    local user="$1" home="$2" node="$3" entry="$4" port="${5:-18789}"
    cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PR_GATEWAY_LABEL}</string>
    <key>UserName</key>
    <string>${user}</string>
    <key>WorkingDirectory</key>
    <string>${home}/.openclaw</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${home}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>${node}</string>
        <string>${entry}</string>
        <string>gateway</string>
        <string>--port</string>
        <string>${port}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>Umask</key>
    <integer>63</integer>
    <key>StandardOutPath</key>
    <string>${home}/Library/Logs/openclaw/gateway.log</string>
    <key>StandardErrorPath</key>
    <string>${home}/Library/Logs/openclaw/gateway.err.log</string>
</dict>
</plist>
PLIST
}

# =============================================================================
# pm2 — collapse three hand-rolled names into ONE canonical job
# =============================================================================

# pr_render_pm2_plist <user> <home> <pm2-bin> <node-bin-dir>
pr_render_pm2_plist() {
    local user="$1" home="$2" pm2="$3" bindir="$4"
    cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PR_PM2_LABEL}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${home}</string>
        <key>PM2_HOME</key>
        <string>${home}/.pm2</string>
        <key>PATH</key>
        <string>${bindir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>${pm2}</string>
        <string>resurrect</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${home}/Library/Logs/openclaw/pm2-resurrect.log</string>
    <key>StandardErrorPath</key>
    <string>${home}/Library/Logs/openclaw/pm2-resurrect.log</string>
</dict>
</plist>
PLIST
}

# pr_legacy_pm2_plists → prints any pm2 launchd plist whose label is NOT the
# canonical one. These are the three drifted names found across the fleet.
pr_legacy_pm2_plists() {
    local f base
    for f in "$PR_LAUNCHAGENTS_DIR"/*.plist; do
        [ -f "$f" ] || continue
        base="$(basename "$f" .plist)"
        [ "$base" = "$PR_PM2_LABEL" ] && continue
        case "$base" in
            *pm2*|*PM2*) printf '%s\n' "$f" ;;
        esac
    done
}

# =============================================================================
# DEFECT 6 — Ethernet. WARN, never hard-fail: you cannot plug in a cable remotely.
# =============================================================================
pr_check_ethernet() {
    local active
    active="$("$PR_SYSSETUP" -listnetworkserviceorder 2>/dev/null | grep -c 'Ethernet' || true)"
    # Is an Ethernet interface actually carrying a link?
    if "$PR_SYSSETUP" -getinfo "Ethernet" 2>/dev/null | grep -qE '^IP address: [0-9]'; then
        pr_log "Ethernet: UP with an IP. Good — this is the resilient path."
        return 0
    fi
    pr_warn "ETHERNET IS NOT CONNECTED — this box is on Wi-Fi."
    pr_warn "  Ethernet is ordered #1 in the macOS service order, but the cable is"
    pr_warn "  not plugged in. Wi-Fi adds a failure mode on every reboot: the Wi-Fi"
    pr_warn "  link comes up LATER than the network daemons, and a Mac that boots"
    pr_warn "  with no cable will sit unreachable if the Wi-Fi association fails."
    pr_warn "  'womp' (wake-on-LAN) only works over Ethernet."
    pr_warn "  ACTION FOR A HUMAN ON SITE: plug in an Ethernet cable."
    pr_warn "  This is a WARNING, not a failure — a cable cannot be plugged in"
    pr_warn "  remotely."
    return 0
}

# =============================================================================
# DEFECT 7 — the ACCEPTANCE GATE. Proves outage-survival instead of asserting it.
# =============================================================================
#
# The old installer reported SUCCESS on a box that would never come back. This
# gate answers ONE question: "if the mains dropped right now, would this box
# come back on its own?" Anything it cannot PROVE, it FAILS.
pr_acceptance_gate() {
    local fail=0 fv al
    echo ""
    echo "=============================================================="
    echo " POST-PROVISION ACCEPTANCE GATE — OUTAGE SURVIVAL"
    echo "=============================================================="

    # --- 1. Will the Mac power itself back on? -------------------------------
    if pr_is_laptop; then
        pr_warn "1. autorestart: LAPTOP — not a meaningful check. See pr_apply_pmset."
    elif pr_verify_pmset; then
        pr_log "1. PASS  the Mac will power itself back on when mains returns"
    else
        pr_err "1. FAIL  autorestart/sleep not set — mains returns, the Mac stays OFF"
        fail=1
    fi

    # --- 2. Will macOS actually finish booting? ------------------------------
    fv="$(pr_filevault_status)"
    if [ "$fv" = "Off" ]; then
        pr_log "2. PASS  FileVault Off — macOS will finish booting with no human"
    else
        pr_err "2. FAIL  FileVault is '$fv' — the Mac halts at the PRE-BOOT unlock"
        pr_err "         screen. NOTHING runs. Not LaunchAgents. Not LaunchDaemons."
        pr_err "         Not sshd. A human with the disk password must be on site."
        fail=1
    fi

    # --- 3. Will a GUI session exist for the LaunchAgents? -------------------
    al="$(pr_autologin_user)"
    if [ -n "$al" ]; then
        pr_log "3. PASS  auto-login set ($al) — the gui/<uid> domain WILL exist,"
        pr_log "         so the gateway/pm2/tunnel LaunchAgents will actually start"
    else
        pr_err "3. FAIL  no auto-login — the gui/<uid> launchd domain is never"
        pr_err "         created. Every LaunchAgent stays dead until a human logs"
        pr_err "         in, no matter how perfect its RunAtLoad/KeepAlive are."
        fail=1
    fi

    # --- 4. Is the gateway actually a job that can start unattended? ---------
    if [ -f "$PR_LAUNCHDAEMONS_DIR/$PR_GATEWAY_LABEL.plist" ]; then
        pr_log "4. PASS  gateway is a system LaunchDaemon (login-independent)"
    elif [ -f "$PR_LAUNCHAGENTS_DIR/$PR_GATEWAY_LABEL.plist" ]; then
        if [ -n "$al" ]; then
            pr_log "4. PASS  gateway is a LaunchAgent, and auto-login guarantees the"
            pr_log "         session it needs"
        else
            pr_err "4. FAIL  gateway is a LOGIN-GATED LaunchAgent on a box that never"
            pr_err "         logs in. This is the 3d14h-dead-gateway defect exactly."
            fail=1
        fi
    else
        pr_err "4. FAIL  no gateway launchd job found at all"
        fail=1
    fi

    # --- 5. Is any tunnel token sitting in cleartext in a plist? -------------
    local leaky=0 p
    for p in "$PR_LAUNCHDAEMONS_DIR"/com.cloudflare*.plist "$PR_LAUNCHAGENTS_DIR"/com.cloudflare*.plist; do
        [ -f "$p" ] || continue
        # A connector token is a long base64 JWT-ish blob passed to `--token`.
        if grep -q -- '--token</string>' "$p" 2>/dev/null || \
           grep -qE '<string>eyJ[A-Za-z0-9+/=_-]{40,}</string>' "$p" 2>/dev/null; then
            pr_err "5. FAIL  CLEARTEXT TUNNEL TOKEN in $p"
            pr_err "         It is also visible in \`ps\` to ANY local user."
            leaky=1
        fi
    done
    if [ "$leaky" -eq 0 ]; then
        pr_log "5. PASS  no cleartext tunnel token in any cloudflared plist"
    else
        fail=1
    fi

    # --- 6. Ethernet (advisory) ---------------------------------------------
    pr_check_ethernet

    echo "--------------------------------------------------------------"
    if [ "$fail" -eq 0 ]; then
        echo " ACCEPTANCE: PASS — this box is proven to survive a power outage."
        echo "=============================================================="
        return 0
    fi
    echo " ACCEPTANCE: FAIL — this box would NOT come back after a power cut."
    echo " Do NOT report this install as successful. That is the bug that"
    echo " shipped 11 undead Macs."
    echo "=============================================================="
    return 1
}
