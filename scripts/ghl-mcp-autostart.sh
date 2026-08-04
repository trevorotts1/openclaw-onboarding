#!/usr/bin/env bash
# ghl-mcp-autostart.sh — v21.6.0
#
# v21.6.0 (R1 + R9): the v21.5.0 release above declared config/ghl-mcp-pin.env
# the "single source of truth" — and never delivered it to a single box.
# update-skills.sh copied scripts/ and nothing else, then deleted its temp
# clone; the FIRST resolver candidate ($SELF_DIR/../config) pointed at
# $OC_CONFIG/config/, a directory neither installer created. Every weekly-
# updated box therefore ran on the hardcoded fallback constants baked into
# THIS FILE, a pin bump propagated nowhere, and the box-side QC gate hard-failed
# (proven: box layout rc=1, repo layout rc=0). Two changes, and they MUST ship
# together:
#   R1  both installers now deliver config/ to $OC_CONFIG/config/ and ASSERT it
#       landed; the resolver lists here, in the probe, in the VPS overlay and in
#       the static gate all carry that path, and CI cross-references the lists
#       against the delivery destinations so they cannot drift apart again.
#   R9  fail-closed. No pin file -> PIN_UNVERIFIED, no build, no start. Verdict
#       not CLEAN, or a vetting digest that does not recompute -> PIN_UNVETTED.
#       GHL_MCP_PIN_OVERRIDE now requires a matching vetting digest. The silent
#       built-in fallback commit is GONE — a fallback that quietly substitutes
#       for a missing source of truth is how the split-brain opened.
# R9 is only safe because R1 lands in the same commit: fail-closed BEFORE
# delivery works would brick the install path on every box.
#
# FIX 3 (systemic): Skill 36 registers the GHL community MCP in mcp.servers but
# nothing ever STARTS the local server on :8765, so the GHL tools never resolve
# at runtime. The launchd plist lived only as PROSE in
# 36-ghl-mcp-setup/INSTALL.md §5.5 — downloaded, never executed.
#
# v12.24.0 HARDENING (fleet incident: 12/19 boxes down/unsupervised):
#   1. PORT IS PINNED EXPLICITLY. main.js reads `PORT` BEFORE `MCP_SERVER_PORT`
#      (src/main.ts:55) — so without an explicit PORT a stray inherited PORT
#      binds a random port (49032/63703) instead of 8765. We now pin BOTH
#      PORT and MCP_SERVER_PORT to 8765 in EVERY launch surface (launchd plist,
#      pm2 ecosystem, systemd unit, .env, supervisor loop).
#   2. NO BARE NOHUP. A bare `nohup node …` does NOT survive session/exec
#      teardown and is NOT supervised — the exact failure that took the fleet
#      down. VPS now runs under pm2 (fleet-standard supervisor) with `pm2 save`
#      + an @reboot `pm2 resurrect` hook so it survives reboot/container restart.
#      systemd is the non-container fallback; a detached setsid relaunch LOOP
#      (poor-man's pm2, PORT pinned) is the last resort — never bare nohup.
#
# v21.5.0 HARDENING — the five installer diseases found on 2026-08-02/03 after a
# 2-day fleet-wide agent-init stall. Each one is now structurally impossible:
#
#   D1. STALE-DIST DEAFNESS. This script used to `git pull --ff-only` and then
#       build ONLY when dist/main.js was ABSENT. So a pull that advanced the
#       source left the OLD compiled dist in place forever. The deployed
#       dist/main.js predated upstream's `await server.connect(transport)` fix:
#       the socket accepted the connection and answered NOTHING, so every agent
#       init blocked the full 30s connectionTimeoutMs, on every box, for 2 days.
#       KeepAlive could not see it — the process was alive, just deaf.
#       FIX: rebuild is keyed to the PIN + a build stamp + a literal artifact
#       assertion (dist/main.js must contain `connect(transport)`), never to
#       "does a dist directory happen to exist".
#
#   D2. 858 TOOLS IN EVERY INIT. The server's default GHL_TOOL_PROFILE is
#       `full` (src/tool-registry.ts:509) — the entire 858-tool catalogue. When
#       the server is ALSO registered under mcp.servers, that catalogue is
#       injected into every agent's init.
#       FIX: GHL_TOOL_PROFILE is set explicitly in EVERY launch surface, and
#       this script no longer registers the community MCP (skill 36 v1.1.0
#       doctrine + qc-ghl-mcp-setup.sh Section D + wire.sh migration M2 all
#       say Tier 2 is ON-DEMAND CURL; this script was silently re-registering
#       what wire.sh had just removed).
#
#   D3. LATENT 10s CRASH LOOP. main.js calls `await ghlClient.testConnection()`
#       at boot and `process.exit(1)` on failure (src/main.ts:69 + 222-225).
#       A bad/expired/rotated PIT therefore makes the server exit non-zero on
#       EVERY launch; with ThrottleInterval=10 that is a 10s relaunch loop
#       burning the box until someone notices.
#       FIX: a launcher wrapper does a bounded credential preflight and exits
#       CLEANLY (0) on an auth rejection. Crash-only restart semantics then do
#       the right thing everywhere: launchd `KeepAlive{SuccessfulExit:false}`
#       does not restart a clean exit, pm2 `stop_exit_codes:[0]` does not,
#       systemd `Restart=on-failure` does not, and the fallback loop breaks.
#
#   D4. BUILD CRASH FROM ORPHANED node_modules IN src/. Upstream's build
#       (scripts/build-server.mjs) `rmSync(dist)` FIRST and then transpiles
#       EVERY .ts file it finds by walking src/ recursively — including any
#       node_modules that ever got installed inside src/ (the operator box had
#       src/ui/react-app/node_modules). One diagnostic anywhere in that walk
#       exits 1 AFTER dist was already deleted → a broken/partial dist and a
#       server that cannot start at all.
#       FIX: we never build the working tree. We `git archive` the pinned
#       commit into a temp dir, build THERE, verify the artifact, and only then
#       swap it into dist/ (previous dist kept as dist.bak-<ts>). Any orphaned
#       src/**/node_modules found in the working tree is quarantined so a human
#       running `npm run build` by hand cannot re-trigger the same crash.
#
#   D5. NO LIVENESS PROOF. Nothing asserted that a RESPONSE arrives. A GET
#       /health is served by express before the MCP transport is wired, so a
#       deaf server still returns {"status":"healthy"}.
#       FIX: scripts/ghl-mcp-probe.sh POSTs a real JSON-RPC `initialize` to
#       /mcp and requires a serverInfo response inside N seconds. It runs once
#       post-install and then every 15 minutes (launchd StartInterval on Mac,
#       cron on VPS).
#
#   D6. ALL-INTERFACES BIND ON A CRM-CREDENTIALED PORT (P0, added 2026-08-03).
#       Measured on the operator box: `lsof` -> `TCP *:8765 (LISTEN)`, i.e. 0.0.0.0 —
#       reachable from every host on the LAN — while `GET /tools` answers HTTP
#       200 with NO authentication at all. The endpoint IS the credential: any
#       local process, any LAN host, and (subject to each box's firewall) any
#       internet host can drive the client's CRM without holding the PIT.
#
#       WHY A PLAIN ENV VAR CANNOT FIX THIS — verified by reading the pinned
#       upstream source, not assumed. src/main.ts at the vetted commit ends with
#           app.listen(port, '0.0.0.0', () => { … })
#       The bind address is a HARDCODED STRING LITERAL. There is no HOST, no
#       MCP_SERVER_HOST, no config knob of any kind. Setting `HOST=127.0.0.1`
#       in the plist/pm2/systemd would look like a fix, would satisfy a naive
#       grep-based QC check, and would change NOTHING at runtime. We do not ship
#       fixes we cannot prove.
#
#       FIX (what this repo genuinely controls): we generate the launcher, so we
#       generate a tiny CommonJS bind guard next to it and load it with
#       `NODE_OPTIONS=--require`. It wraps net.Server.prototype.listen and
#       rewrites the host argument to a loopback address before the real listen
#       runs. No upstream change, no root, no firewall, and it applies to EVERY
#       supervisor (launchd, pm2, systemd, the fallback loop) because all four
#       run through the same launcher. Proven, not asserted:
#       tests/unit/ghl-mcp-bind-guard.test.sh boots a real node server that calls
#       `listen(port,'0.0.0.0')` with and without the guard and asserts the
#       observed bind address differs (0.0.0.0 -> 127.0.0.1).
#
#       STILL OPEN, and NOT fixable from this repo — both need a patch carried on
#       an org-controlled MIRROR of the upstream:
#         (a) `Origin` validation. The MCP spec says a local HTTP server MUST
#             validate Origin and answer 403. Upstream's cors() origin callback
#             calls back with an Error, which express renders as HTTP 500 — the
#             measured behaviour. Wrong status, and `!origin` is allowed outright.
#         (b) An `Authorization: Bearer` requirement on /mcp and /tools. There is
#             no auth middleware anywhere in the pinned tree.
#       Loopback binding is the mitigation that removes the LAN and internet
#       exposure today; it does not make a same-box process authenticate.
#
# This script is the EXECUTED form of INSTALL.md §5.1–5.7. It is idempotent and
# additive: it (1) clones + pins + builds the community MCP, (2) installs the
# platform-appropriate supervisor (Mac=launchd KeepAlive plist com.clawd.ghl-mcp;
# VPS=pm2 ecosystem + save + reboot-resurrect, or systemd), (3) probes :8765 for
# a real JSON-RPC response, and (4) installs the periodic probe. Re-running is a
# safe UPGRADE path: it is also the fleet REMEDIATION path — re-running this
# script on a deaf box re-pins, rebuilds, and restarts it.
#
# Exit 0 = healthy (or a clean, honestly-reported skip). Exit non-zero NEVER —
# this is wiring; callers gate on the printed STATUS line + their own checks.

set -u

log() { printf '  [ghl-mcp-autostart] %s\n' "$*"; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Platform + paths ─────────────────────────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  PLATFORM="vps"
  OC_ROOT="/data/.openclaw"
  MCP_DIR="/data/mcp-servers/ghl-community-mcp"
  LOG_DIR="/data/logs"
else
  PLATFORM="mac"
  OC_ROOT="$HOME/.openclaw"
  MCP_DIR="$HOME/mcp-servers/ghl-community-mcp"
  LOG_DIR="$HOME/Library/Logs/ghl-mcp"
fi
OC_JSON="$OC_ROOT/openclaw.json"
SECRETS_ENV="$OC_ROOT/secrets/.env"
mkdir -p "$LOG_DIR" 2>/dev/null || true

# ── STATUS reporter (callers grep this line; honest, never "done" on a gap) ──
# Declared BEFORE the pin resolution below because R9's fail-closed refusals
# report through it.
STATUS="UNKNOWN"
report() {
  STATUS="$1"; shift
  printf 'STATUS: ghl-mcp-autostart=%s %s\n' "$STATUS" "$*"
}

# ── Pin + profile: ONE source of truth (config/ghl-mcp-pin.env) ──────────────
# R1 (v21.6.0): the pin file used to exist ONLY in the repo. update-skills.sh
# delivered scripts/ and nothing else and then deleted its temp clone, so on
# every weekly-updated box all five candidates below missed and the script ran
# on hardcoded fallback constants — a pin bump propagated to no box at all.
# Both installers now deliver config/ to $OC_CONFIG/config/, and that path is
# the FIRST candidate here ($SELF_DIR/../config resolves to it when this script
# runs from its delivered home, $OC_CONFIG/scripts/).
#
# ⚠️ ANY CHANGE TO THIS LIST must be mirrored in ghl-mcp-probe.sh, the VPS
# overlay, qc-assert-ghl-mcp-supervised.sh, AND the delivery step in BOTH
# installers. scripts/qc-assert-pin-delivery-paths.sh fails CI if they drift.
_PIN_FILE=""
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  [ -f "$_c" ] && { _PIN_FILE="$_c"; break; }
done

# ── R9: FAIL-CLOSED. No pin file = no build, no start. ───────────────────────
# There is NO built-in fallback commit any more. A silent fallback is exactly
# what let v21.5.0 believe it had one source of truth while every box ran on a
# constant baked into this file — and it is what made a pin bump a no-op
# fleet-wide. If the delivery did not happen, that is a broken install and it
# must be LOUD, not papered over with a hardcoded SHA.
if [ -z "$_PIN_FILE" ]; then
  log "REFUSING: config/ghl-mcp-pin.env not found in any delivered location"
  report "PIN_UNVERIFIED" \
    "(config/ghl-mcp-pin.env was not delivered to this box — refusing to build/start an unverified third-party MCP. Re-run update-skills.sh or install.sh; both deliver config/ to \$OC_CONFIG/config/. Looked in: $SELF_DIR/../config, \$HOME/.openclaw/{config,onboarding/config}, /data/.openclaw/{config,onboarding/config})"
  exit 0
fi
# shellcheck disable=SC1090
. "$_PIN_FILE"
log "pin config: $_PIN_FILE"

# Operational defaults only. NOTHING security-relevant (commit, profile, repo
# URL) may default here — those must come from the delivered pin file.
GHL_MCP_PROBE_TIMEOUT="${GHL_MCP_PROBE_TIMEOUT:-10}"
GHL_MCP_LOG_MAX_BYTES="${GHL_MCP_LOG_MAX_BYTES:-10485760}"
GHL_MCP_LOG_KEEP="${GHL_MCP_LOG_KEEP:-3}"
GHL_MCP_VETTED_COMMIT="${GHL_MCP_VETTED_COMMIT:-}"
GHL_MCP_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE:-}"
GHL_MCP_REPO_URL="${GHL_MCP_REPO_URL:-}"
GHL_MCP_PIN_VETTED_VERDICT="${GHL_MCP_PIN_VETTED_VERDICT:-}"
GHL_MCP_PIN_VETTED_DIGEST="${GHL_MCP_PIN_VETTED_DIGEST:-}"

# D6 (P0 SECURITY): the loopback bind host enforced by the generated bind guard.
# READ write_bind_guard() below before changing this — the upstream server does
# NOT read any host variable; this value is consumed by OUR guard, not by main.js.
GHL_MCP_BIND_HOST="${GHL_MCP_BIND_HOST:-127.0.0.1}"
# Supply-chain: sha256 of package-lock.json at the pinned commit. When declared
# (pin file or caller env) the build REFUSES on a mismatch; when empty the build
# still records the observed value in the build stamp so the binding can be armed.
GHL_MCP_DEPS_LOCK_SHA256="${GHL_MCP_DEPS_LOCK_SHA256:-}"

if [ -z "$GHL_MCP_TOOL_PROFILE" ] || [ -z "$GHL_MCP_REPO_URL" ]; then
  report "PIN_UNVERIFIED" \
    "($_PIN_FILE is present but does not declare GHL_MCP_TOOL_PROFILE and/or GHL_MCP_REPO_URL — a truncated/corrupt pin file is not a source of truth. Refusing to build/start.)"
  exit 0
fi

# ── R9: the vetting verdict is ENFORCED, not decorative ──────────────────────
# Two modes, and the switch between them is automatic:
#   DIGEST MODE  (GHL_MCP_PIN_VETTED_DIGEST is non-empty) — the digest must
#     recompute over commit|verdict|on|by|deps_lock_sha256. A hand-edited SHA
#     leaves a stale digest and we refuse. Forgetting produces refusal.
#   FALLBACK MODE (no digest field yet — the transitional state while
#     scripts/ghl-mcp-vet-pin.sh is still being built) — require the explicit
#     CLEAN verdict. Weaker (one word defeats it) but strictly better than
#     v21.5.0, where the verdict was sourced by three scripts and read by none.
# B3 reference shape: this list was ALREADY correct — it carries the delivered
# $OC_ROOT/scripts path on both platforms, with the legacy skills/scripts pair
# after it. That is why the digest tool resolved on the fleet while the probe
# (which listed ONLY the legacy pair) did not. Kept as-is, and the CI gate now
# holds every sibling-resolver list to this same shape.
_PIN_DIGEST_TOOL=""
for _c in "$SELF_DIR/ghl-mcp-pin-digest.sh" \
          "$HOME/.openclaw/scripts/ghl-mcp-pin-digest.sh" \
          "$HOME/.openclaw/skills/scripts/ghl-mcp-pin-digest.sh" \
          "/data/.openclaw/scripts/ghl-mcp-pin-digest.sh" \
          "/data/.openclaw/skills/scripts/ghl-mcp-pin-digest.sh"; do
  [ -f "$_c" ] && { _PIN_DIGEST_TOOL="$_c"; break; }
done

if [ "$GHL_MCP_PIN_VETTED_VERDICT" != "CLEAN" ]; then
  report "PIN_UNVETTED" \
    "(GHL_MCP_PIN_VETTED_VERDICT='${GHL_MCP_PIN_VETTED_VERDICT:-<unset>}' in $_PIN_FILE — only CLEAN may be built. Re-vet the pinned commit and record the verdict before any box builds it.)"
  exit 0
fi

if [ -n "$GHL_MCP_PIN_VETTED_DIGEST" ]; then
  if [ -z "$_PIN_DIGEST_TOOL" ]; then
    report "PIN_UNVETTED" \
      "(the pin declares GHL_MCP_PIN_VETTED_DIGEST but scripts/ghl-mcp-pin-digest.sh was not delivered to this box, so the digest CANNOT be verified — refusing rather than trusting it unchecked. Re-run update-skills.sh.)"
    exit 0
  fi
  if ! bash "$_PIN_DIGEST_TOOL" verify "$_PIN_FILE" >/dev/null 2>&1; then
    report "PIN_UNVETTED" \
      "(the vetting digest in $_PIN_FILE does not recompute — the pin was edited without re-running scripts/ghl-mcp-vet-pin.sh. Refusing to build/start. Run: bash $_PIN_DIGEST_TOOL verify $_PIN_FILE)"
    exit 0
  fi
  log "vetting digest verified (verdict=CLEAN, digest recomputes)"
else
  log "vetting digest ABSENT — enforcing the explicit CLEAN verdict (transitional until scripts/ghl-mcp-vet-pin.sh ships the digest)"
fi

# ── R9: an override is an escape hatch, not a bypass ─────────────────────────
# GHL_MCP_PIN_OVERRIDE used to accept ANY 40-hex string with zero vetting —
# and it is the primary path a fleet roll would use to change a pin, which made
# the primary path the ungated one. It now requires a matching vetting digest
# computed over the OVERRIDE's own tuple, using THE SAME canonical algorithm as
# the pin file — ghl-mcp-pin-v2, which BINDS THE REPOSITORY URL:
#
#   printf '%s\n' ghl-mcp-pin-v2 \
#     "$GHL_MCP_PIN_OVERRIDE" \
#     "$GHL_MCP_PIN_OVERRIDE_VERDICT" \
#     "$GHL_MCP_PIN_OVERRIDE_VETTED_ON" \
#     "$GHL_MCP_PIN_OVERRIDE_VETTED_BY" \
#     "$GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256" \
#     "$GHL_MCP_REPO_URL" | shasum -a 256 | cut -d' ' -f1
#
# …and that value must be passed as GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST. The
# seventh field is the EFFECTIVE repo URL from the pin file — the source this
# box would actually clone from. It is not separately settable: an override
# changes WHICH COMMIT is built, never WHERE it is fetched from.
#
# THE ALGORITHM IS NOT REIMPLEMENTED HERE. This block materialises the override
# as a pin-shaped record and hands it to scripts/ghl-mcp-pin-digest.sh, the one
# canonical implementation. A second inline copy is precisely how this path
# stayed on v1 — with the repository URL UNBOUND — after the pin file moved to
# v2, which would have let a mirror swap ride in through the primary fleet-roll
# path while every digest still checked out.
if [ -n "${GHL_MCP_PIN_OVERRIDE:-}" ]; then
  _OV_VERDICT="${GHL_MCP_PIN_OVERRIDE_VERDICT:-}"
  _OV_DIGEST="${GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST:-}"
  _OV_REPO="$GHL_MCP_REPO_URL"
  if [ -z "$_OV_DIGEST" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE was supplied without GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST — an override is an escape hatch for a VETTED commit, never a way to skip vetting. Vet the candidate, then pass the digest.)"
    exit 0
  fi
  if [ "$_OV_VERDICT" != "CLEAN" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE_VERDICT='${_OV_VERDICT:-<unset>}' — only CLEAN may be built.)"
    exit 0
  fi
  if [ -z "$_PIN_DIGEST_TOOL" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE was supplied but scripts/ghl-mcp-pin-digest.sh was not delivered to this box, so the override digest CANNOT be verified — refusing rather than trusting it unchecked. Re-run update-skills.sh.)"
    exit 0
  fi
  # A double quote in any bound field would break the pin-shaped record format
  # and could let two different tuples parse to the same value. Refuse instead.
  case "${GHL_MCP_PIN_OVERRIDE}${_OV_VERDICT}${GHL_MCP_PIN_OVERRIDE_VETTED_ON:-}${GHL_MCP_PIN_OVERRIDE_VETTED_BY:-}${GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256:-}${_OV_REPO}" in
    *'"'*)
      report "PIN_UNVETTED" \
        "(a GHL_MCP_PIN_OVERRIDE_* field contains a double quote — refusing rather than hashing an ambiguous record.)"
      exit 0 ;;
  esac
  _OV_TMP="$(mktemp "${TMPDIR:-/tmp}/ghl-mcp-override.XXXXXX" 2>/dev/null)"
  if [ -z "$_OV_TMP" ]; then
    report "PIN_UNVETTED" "(could not create a temp file to verify the override digest — refusing.)"
    exit 0
  fi
  {
    printf 'GHL_MCP_VETTED_COMMIT="%s"\n'      "$GHL_MCP_PIN_OVERRIDE"
    printf 'GHL_MCP_PIN_VETTED_VERDICT="%s"\n' "$_OV_VERDICT"
    printf 'GHL_MCP_PIN_VETTED_ON="%s"\n'      "${GHL_MCP_PIN_OVERRIDE_VETTED_ON:-}"
    printf 'GHL_MCP_PIN_VETTED_BY="%s"\n'      "${GHL_MCP_PIN_OVERRIDE_VETTED_BY:-}"
    printf 'GHL_MCP_DEPS_LOCK_SHA256="%s"\n'   "${GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256:-}"
    printf 'GHL_MCP_REPO_URL="%s"\n'           "$_OV_REPO"
  } > "$_OV_TMP"
  _OV_COMPUTED="$(bash "$_PIN_DIGEST_TOOL" compute "$_OV_TMP" 2>/dev/null)"
  rm -f "$_OV_TMP"
  if [ -z "$_OV_COMPUTED" ] || [ "$_OV_COMPUTED" != "$_OV_DIGEST" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST does not match the override tuple — refusing. Recompute it over ghl-mcp-pin-v2|commit|verdict|on|by|deps_lock_sha256|repo_url, where repo_url is this box's GHL_MCP_REPO_URL.)"
    exit 0
  fi
  log "pin override accepted (digest verified, repo URL bound) — building ${GHL_MCP_PIN_OVERRIDE:0:12} instead of the pin file's commit"
  GHL_MCP_VETTED_COMMIT="$GHL_MCP_PIN_OVERRIDE"
fi

[ -n "${GHL_TOOL_PROFILE:-}" ] && GHL_MCP_TOOL_PROFILE="$GHL_TOOL_PROFILE"

# A pin MUST be a full 40-char SHA. A short SHA or a branch name is not a pin —
# `git checkout main` succeeds forever while the tree underneath changes.
case "$GHL_MCP_VETTED_COMMIT" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) : ;;
  *) log "REFUSING: GHL_MCP_VETTED_COMMIT='${GHL_MCP_VETTED_COMMIT}' is not a full 40-char SHA"
     printf 'STATUS: ghl-mcp-autostart=%s %s\n' "PIN_INVALID" \
       "(GHL_MCP_VETTED_COMMIT is not a full 40-char commit SHA — refusing to build/start an unpinned third-party MCP)"
     exit 0 ;;
esac

# ── Resolve a free/canonical port (8765 canonical) ──────────────────────────
GHL_MCP_PORT="${GHL_MCP_PORT:-8765}"

# (the STATUS reporter is declared above the pin resolution — R9's refusals
#  report through it before anything else runs.)

# ── Credential preflight — honest skip, never a fake success ─────────────────
_get_env_var() {
  local var="$1" v=""
  v="$(printenv "$var" 2>/dev/null || true)"
  if [ -z "$v" ] && [ -f "$SECRETS_ENV" ]; then
    v="$(grep -E "^${var}=" "$SECRETS_ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  fi
  if [ -z "$v" ] && [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
    v="$(VAR="$var" OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    print(cfg.get("env", {}).get("vars", {}).get(os.environ["VAR"], "") or "")
except Exception:
    print("")
PYEOF
)"
  fi
  printf '%s' "$v"
}

GHL_TOKEN="$(_get_env_var GOHIGHLEVEL_API_KEY)"
[ -z "$GHL_TOKEN" ] && GHL_TOKEN="$(_get_env_var GHL_API_KEY)"
GHL_LOC="$(_get_env_var GOHIGHLEVEL_LOCATION_ID)"
[ -z "$GHL_LOC" ] && GHL_LOC="$(_get_env_var GHL_LOCATION_ID)"

# ── D4: quarantine orphaned node_modules living INSIDE src/ ──────────────────
# build-server.mjs walks src/ recursively and transpiles every .ts it finds. A
# node_modules tree that ever landed under src/ turns a build into thousands of
# third-party transpiles and, on one diagnostic, exits 1 AFTER dist was deleted.
# We build from `git archive` so this cannot bite the automated path, but a
# human running `npm run build` in the working tree would still hit it.
#
# F16: `-maxdepth` comes IMMEDIATELY after the path, before any other primary.
# GNU find warns and applies it globally anyway; BSD/macOS find's behaviour with
# a trailing `-maxdepth` is not guaranteed to be the intended one. Half the fleet
# is macOS, so the portable ordering is the only correct ordering.
quarantine_src_orphans() {
  [ -d "$MCP_DIR/src" ] || return 0
  local q found=0
  q="$MCP_DIR/.quarantine-$(date -u +%Y%m%dT%H%M%SZ)"
  while IFS= read -r nm; do
    [ -n "$nm" ] || continue
    mkdir -p "$q" 2>/dev/null || true
    mv "$nm" "$q/$(printf '%s' "${nm#"$MCP_DIR/"}" | tr '/' '_')" 2>/dev/null && found=1
  done <<EOF
$(find "$MCP_DIR/src" -maxdepth 6 -type d -name node_modules 2>/dev/null)
EOF
  [ "$found" = "1" ] && log "quarantined orphaned node_modules found under src/ -> $q (D4: they crash upstream's build)"
  return 0
}

# >>> GHL-MCP-ROOT-OWNERSHIP-GUARD-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-root-ownership-guard.test.sh)
# ── 0. Root/ownership mismatch guard (P0, proven live 2026-08-04) ────────────
# DEFECT (worst of the three found tonight): every git command below used to
# carry a blanket `2>/dev/null`. When this script runs as ROOT against an
# EXISTING $MCP_DIR checkout owned by a different uid — the fleet-standard VPS
# shape, where the box user is uid 1000/node — every single git command in
# this function hits git's "detected dubious ownership in repository at ..."
# fatal, and that `2>/dev/null` swallowed it with NO WARN, NO FATAL, NO trace.
# The MIRROR MIGRATION repoint below then silently no-op'd (an empty
# $_origin_url reads as "no origin to repoint"), the pin-verify fetch/cat-file
# calls below it failed for the identical swallowed reason, and the operator
# saw only the downstream "PIN_MISMATCH — cannot check out vetted commit" and
# reasonably blamed the pin gate, which was innocent. This is the SAME disease
# as the root-cron bug fixed earlier the same night: a privilege mismatch that
# a swallowed stderr turns into an unrelated-looking symptom two layers away.
#
# FIX: detect the mismatch EXPLICITLY, before any git command touches an
# existing checkout, rather than trying to pattern-match git's (locale-
# dependent) stderr text. FAIL LOUD through the same report()/STATUS contract
# every other refusal in this script uses, naming the exact remedy — the
# convention already documented at scripts/activate-loop-protection.sh:118:
# run this script as the box user, never as root (`docker exec -u node <ctr>
# bash ...` on VPS/Docker).
_ghl_owner_uid() {  # <path> -> numeric uid, or empty if it cannot be read
  local p="$1" u=""
  command -v stat >/dev/null 2>&1 || { printf ''; return 0; }
  # GNU stat: -c %u   BSD/macOS stat: -f %u — try both; first one that answers wins.
  u="$(stat -c %u "$p" 2>/dev/null || true)"
  [ -n "$u" ] || u="$(stat -f %u "$p" 2>/dev/null || true)"
  printf '%s' "$u"
}

assert_ownership_matches_runtime_user() {
  [ -d "$MCP_DIR/.git" ] || return 0              # nothing checked out yet — a fresh clone as root is not this failure mode
  [ "$(id -u 2>/dev/null || echo '')" = "0" ] || return 0   # not root — this disease cannot occur
  [ "${GHL_MCP_ALLOW_ROOT:-}" = "1" ] && return 0  # explicit escape hatch (tests / a deliberate root-owned box)
  local _owner_uid; _owner_uid="$(_ghl_owner_uid "$MCP_DIR")"
  [ -n "$_owner_uid" ] || return 0                 # cannot determine — do not block on a guess
  [ "$_owner_uid" = "0" ] && return 0               # already root-owned — no ownership mismatch, git will not refuse

  log "############################################################"
  log "## FATAL: running as root (uid 0) against $MCP_DIR, which is owned by uid $_owner_uid."
  log "## Every git command below would hit git's dubious-ownership refusal, and"
  log "## this script used to swallow that with 2>/dev/null -- surfacing only as an"
  log "## unrelated downstream PIN_MISMATCH. Refusing to proceed rather than repeat that."
  log "## REMEDY (VPS/Docker): run this script as the box user, not root:"
  log "##   docker exec -u node <ctr> bash $SELF_DIR/$(basename "${BASH_SOURCE[0]:-$0}")"
  log "## (the sanctioned convention documented at scripts/activate-loop-protection.sh:118)."
  log "## Mac: this script should never be invoked with sudo."
  log "############################################################"
  report "ROOT_OWNERSHIP_MISMATCH" \
    "(running as root (uid 0) against $MCP_DIR, owned by uid $_owner_uid -- every git command would be silently refused by git's dubious-ownership guard. Re-run as the box user: docker exec -u node <ctr> bash <this script> on VPS/Docker (see scripts/activate-loop-protection.sh:118); never with sudo on Mac.)"
  return 1
}
# <<< GHL-MCP-ROOT-OWNERSHIP-GUARD-END

# ── 1. Clone + PIN the community MCP working tree (idempotent) ───────────────
ensure_repo_at_pin() {
  command -v git >/dev/null 2>&1 || { log "git not on PATH — cannot pin/build GHL MCP"; return 1; }
  assert_ownership_matches_runtime_user || return 3
  mkdir -p "$(dirname "$MCP_DIR")" 2>/dev/null || true

  if [ ! -d "$MCP_DIR/.git" ]; then
    log "cloning community GHL MCP into $MCP_DIR"
    # NOT --depth 1: a shallow clone frequently cannot resolve an arbitrary
    # pinned SHA, which is exactly what turned the old script into a floating
    # "whatever main is today" install.
    git clone --no-checkout "$GHL_MCP_REPO_URL" "$MCP_DIR" >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || {
      log "git clone failed — server cannot be built"; return 1; }
  fi

  # MIRROR MIGRATION. Every box provisioned before the mirror existed has an
  # `origin` pointing at the third-party upstream. Nothing else would ever move
  # it, so those clones would keep fetching from a repository that force-pushes
  # its history and would break the day the pin is garbage-collected there —
  # the exact failure the mirror exists to prevent. Repoint it here, on the next
  # run of this script, before anything is fetched.
  #
  # FIX (a): the git errors below used to be swallowed unconditionally
  # (`2>/dev/null`). They are now CAPTURED and, on a failure this function did
  # not already anticipate (the ownership guard above handles the specific
  # root-vs-owner case), surfaced as a WARN rather than silently discarded —
  # so any future "git just failed here for some other reason" is never
  # invisible again.
  local _origin_url _origin_out _origin_rc=0 _seturl_out
  _origin_out="$(git -C "$MCP_DIR" remote get-url origin 2>&1)" || _origin_rc=$?
  if [ "$_origin_rc" = "0" ]; then
    _origin_url="$_origin_out"
  else
    _origin_url=""
    [ -n "$_origin_out" ] && log "WARN: 'git remote get-url origin' in $MCP_DIR failed (rc=$_origin_rc): $_origin_out"
  fi
  if [ -n "$_origin_url" ] && [ "$_origin_url" != "$GHL_MCP_REPO_URL" ]; then
    if _seturl_out="$(git -C "$MCP_DIR" remote set-url origin "$GHL_MCP_REPO_URL" 2>&1)"; then
      log "origin repointed: $_origin_url -> $GHL_MCP_REPO_URL"
    else
      log "WARN: could not repoint origin from $_origin_url to $GHL_MCP_REPO_URL: ${_seturl_out:-<no output>}"
    fi
  fi

  # Fetch the exact object; unshallow an old --depth 1 clone if needed.
  git -C "$MCP_DIR" fetch --quiet origin "$GHL_MCP_VETTED_COMMIT" 2>/dev/null \
    || git -C "$MCP_DIR" fetch --quiet --tags origin 2>/dev/null \
    || true
  if ! git -C "$MCP_DIR" cat-file -e "${GHL_MCP_VETTED_COMMIT}^{commit}" 2>/dev/null; then
    git -C "$MCP_DIR" fetch --quiet --unshallow origin 2>/dev/null || true
  fi
  if ! git -C "$MCP_DIR" cat-file -e "${GHL_MCP_VETTED_COMMIT}^{commit}" 2>/dev/null; then
    log "FATAL: pinned commit $GHL_MCP_VETTED_COMMIT not reachable from origin (upstream force-push? bad pin?)"
    return 2
  fi

  quarantine_src_orphans
  # --force: the third-party tree is disposable; local edits are never ours.
  git -C "$MCP_DIR" checkout --quiet --detach --force "$GHL_MCP_VETTED_COMMIT" 2>>"$LOG_DIR/ghl-mcp-build.log" || {
    log "FATAL: could not check out pinned commit $GHL_MCP_VETTED_COMMIT"; return 2; }
  local head
  head="$(git -C "$MCP_DIR" rev-parse HEAD 2>/dev/null || echo none)"
  if [ "$head" != "$GHL_MCP_VETTED_COMMIT" ]; then
    log "FATAL: pin verify failed (HEAD=$head want $GHL_MCP_VETTED_COMMIT)"
    return 2
  fi
  log "working tree pinned at $GHL_MCP_VETTED_COMMIT"
  return 0
}

# ── 2. Build hygiene: build the PINNED tree in a temp dir, swap on success ───
BUILD_STAMP="$MCP_DIR/.ghl-mcp-build.json"

dist_is_sane() {
  # A dist that exists proves nothing (D1). Require the entrypoint AND the one
  # line whose absence produced the 30s deafness: `server.connect(transport)`.
  [ -s "$MCP_DIR/dist/main.js" ] || return 1
  grep -q 'connect(transport)' "$MCP_DIR/dist/main.js" 2>/dev/null || return 1
  return 0
}

stamp_matches() {
  [ -f "$BUILD_STAMP" ] || return 1
  grep -q "\"commit\": *\"$GHL_MCP_VETTED_COMMIT\"" "$BUILD_STAMP" 2>/dev/null || return 1
  # F15: the stamp is self-asserted — it records what the script SAID it built.
  # Nothing used to bind dist/ to that claim, so a hand-swapped dist/ under a
  # matching stamp suppressed the rebuild permanently. If the stamp carries a
  # distSha256, the artifact on disk MUST still hash to it. A stamp written by an
  # older version has no distSha256; treat that as "cannot verify", not as a
  # mismatch, so this change never forces a surprise rebuild storm on the fleet.
  local want have
  want="$(sed -n 's/.*"distSha256": *"\([0-9a-f]*\)".*/\1/p' "$BUILD_STAMP" 2>/dev/null | head -1)"
  if [ -n "$want" ] && [ "$want" != "unknown" ]; then
    have="$(shasum -a 256 "$MCP_DIR/dist/main.js" 2>/dev/null | awk '{print $1}')"
    if [ -n "$have" ] && [ "$have" != "$want" ]; then
      log "build stamp does NOT match the artifact (dist/main.js sha256=$have, stamp=$want) — rebuilding from the pin"
      return 1
    fi
  fi
  return 0
}

needs_build() {
  dist_is_sane || return 0
  stamp_matches || return 0
  return 1
}

build_pinned() {
  command -v npm >/dev/null 2>&1 || { log "npm not on PATH — cannot build"; return 1; }
  local tmp rc=0 _lock_sha=""
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/ghl-mcp-build.XXXXXX")" || return 1
  log "building pinned tree ${GHL_MCP_VETTED_COMMIT:0:12} in $tmp (working tree is NEVER built — D4)"
  # git archive gives a pristine snapshot of the PINNED commit: no untracked
  # junk, no orphaned node_modules, no half-applied local edits.
  if ! git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp" 2>>"$LOG_DIR/ghl-mcp-build.log"; then
    log "git archive failed"; rm -rf "$tmp"; return 1
  fi
  # ── R5: SUPPLY-CHAIN HARDENING OF THE BUILD ───────────────────────────────
  # Three defects lived in the old block and all three are closed here:
  #   1. `npm ci … || npm install …` — the fallback SILENTLY discarded lockfile
  #      pinning. `npm ci` fails precisely when package.json and the lockfile
  #      disagree; falling back to `npm install` then resolves fresh from the
  #      registry, voiding the vetting verdict's "dependency graph unchanged"
  #      claim exactly when it matters most. There is NO fallback now: a missing
  #      or out-of-sync lockfile is a BUILD FAILURE, and the swap-on-success
  #      discipline leaves the previous working dist/ untouched.
  #   2. No `--ignore-scripts` — every preinstall/install/postinstall hook in the
  #      full transitive tree ran as the box user with the GHL PIT in the
  #      environment, on every client machine. That is the delivery mechanism for
  #      essentially every major npm supply-chain incident. CAVEAT, deliberately
  #      recorded: --ignore-scripts stops lifecycle hooks, NOT all toolchain
  #      execution. It is necessary, not sufficient; building once in CI and
  #      shipping a verified artifact is the complete answer.
  #   3. The prod-dependency refresh ran `npm install` against the WORKING TREE,
  #      outside the temp-dir discipline and with no lockfile guarantee. It now
  #      runs as `npm ci --omit=dev` inside the SAME temp dir, before the swap,
  #      so there is no unpinned install anywhere and no window in which dist/ is
  #      new while node_modules/ is missing or half-installed.
  # Verified at the pinned commit before shipping: the lockfile IS present and IS
  # in sync — `npm ci --ignore-scripts` installs 415 packages and `npm run build`
  # then produces a dist/main.js containing connect(transport).
  if [ ! -f "$tmp/package-lock.json" ]; then
    log "BUILD REFUSED: no package-lock.json at the pinned commit — 'npm ci' cannot pin the dependency tree and we do NOT fall back to 'npm install' (that resolves fresh from the registry and voids the vetting verdict)"
    rm -rf "$tmp"; return 1
  fi
  # Bind the dependency tree to the vetted lockfile when the pin declares a hash.
  if [ -n "${GHL_MCP_DEPS_LOCK_SHA256:-}" ]; then
    _lock_sha="$(shasum -a 256 "$tmp/package-lock.json" 2>/dev/null | awk '{print $1}')"
    if [ -z "$_lock_sha" ] || [ "$_lock_sha" != "$GHL_MCP_DEPS_LOCK_SHA256" ]; then
      log "BUILD REFUSED: package-lock.json sha256 mismatch (observed=${_lock_sha:-unreadable} expected=$GHL_MCP_DEPS_LOCK_SHA256) — the dependency tree is not the one that was vetted"
      rm -rf "$tmp"; return 1
    fi
    log "lockfile sha256 matches the vetted pin"
  else
    _lock_sha="$(shasum -a 256 "$tmp/package-lock.json" 2>/dev/null | awk '{print $1}')"
    log "lockfile sha256 observed = ${_lock_sha:-unreadable} (GHL_MCP_DEPS_LOCK_SHA256 not declared — recording it, not enforcing it)"
  fi
  (
    cd "$tmp" || exit 1
    # No `|| npm install` fallback, by design. --ignore-scripts on BOTH installs.
    npm ci --ignore-scripts --no-audit --no-fund >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || exit 1
    npm run build >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || exit 1
    # Prune to production deps IN THE TEMP DIR, still pinned, still no scripts.
    npm ci --omit=dev --ignore-scripts --no-audit --no-fund >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || exit 1
  ) || rc=1
  if [ "$rc" != "0" ] || [ ! -s "$tmp/dist/main.js" ] || ! grep -q 'connect(transport)' "$tmp/dist/main.js" 2>/dev/null; then
    log "BUILD FAILED or produced an unusable dist — existing dist/ left UNTOUCHED (never rm -rf before a good build)"
    rm -rf "$tmp"; return 1
  fi

  # Atomic-ish swap: keep the old dist as a rollback, move the verified one in.
  local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  if [ -d "$MCP_DIR/dist" ]; then
    rm -rf "$MCP_DIR/dist.bak-prev" 2>/dev/null || true
    mv "$MCP_DIR/dist" "$MCP_DIR/dist.bak-prev" 2>/dev/null || true
  fi
  if ! mv "$tmp/dist" "$MCP_DIR/dist" 2>/dev/null; then
    cp -R "$tmp/dist" "$MCP_DIR/dist" 2>/dev/null || {
      log "FATAL: could not install new dist — rolling back previous dist"
      [ -d "$MCP_DIR/dist.bak-prev" ] && mv "$MCP_DIR/dist.bak-prev" "$MCP_DIR/dist" 2>/dev/null || true
      rm -rf "$tmp"; return 1; }
  fi
  # R5: install the PINNED, script-suppressed production node_modules built in the
  # temp dir. The old code ran a second, entirely unpinned `npm install` against
  # the working tree here — outside the temp-dir discipline, with no lockfile
  # guarantee, and its failure was only a WARN. Swapping the already-verified tree
  # instead means there is never a moment where dist/ is new and node_modules/ is
  # missing, and a failure rolls BOTH back together.
  if [ -d "$tmp/node_modules" ]; then
    rm -rf "$MCP_DIR/node_modules.bak-prev" 2>/dev/null || true
    [ -d "$MCP_DIR/node_modules" ] && mv "$MCP_DIR/node_modules" "$MCP_DIR/node_modules.bak-prev" 2>/dev/null || true
    if ! mv "$tmp/node_modules" "$MCP_DIR/node_modules" 2>/dev/null; then
      cp -R "$tmp/node_modules" "$MCP_DIR/node_modules" 2>/dev/null || {
        log "FATAL: could not install pinned production node_modules — rolling BOTH dist/ and node_modules/ back"
        rm -rf "$MCP_DIR/node_modules" 2>/dev/null || true
        [ -d "$MCP_DIR/node_modules.bak-prev" ] && mv "$MCP_DIR/node_modules.bak-prev" "$MCP_DIR/node_modules" 2>/dev/null || true
        # Move the half-installed dist ASIDE rather than deleting it: the QC gate
        # forbids `rm -rf …/dist` outright (a failed build must never be able to
        # leave a box with no server), and keeping it named dist.failed-<ts>
        # preserves the artifact for diagnosis.
        [ -d "$MCP_DIR/dist" ] && mv "$MCP_DIR/dist" "$MCP_DIR/dist.failed-$ts" 2>/dev/null || true
        [ -d "$MCP_DIR/dist.bak-prev" ] && mv "$MCP_DIR/dist.bak-prev" "$MCP_DIR/dist" 2>/dev/null || true
        rm -rf "$tmp"; return 1; }
    fi
    # Success — drop the previous tree rather than leaving hundreds of MB behind
    # (dist.bak-prev is small and IS kept as the documented rollback).
    rm -rf "$MCP_DIR/node_modules.bak-prev" 2>/dev/null || true
  fi
  # F15: bind the stamp to the ARTIFACT, not just to a claim. The stamp used to
  # record only which commit the script SAID it built, so a hand-swapped dist/
  # under a matching stamp suppressed the rebuild forever. Recording
  # sha256(dist/main.js) and re-verifying it in stamp_matches() closes that.
  local _dist_sha
  _dist_sha="$(shasum -a 256 "$MCP_DIR/dist/main.js" 2>/dev/null | awk '{print $1}')"
  cat > "$BUILD_STAMP" <<EOF
{
  "commit": "$GHL_MCP_VETTED_COMMIT",
  "profile": "$GHL_MCP_TOOL_PROFILE",
  "builtAt": "$ts",
  "node": "$(node --version 2>/dev/null || echo unknown)",
  "distSha256": "${_dist_sha:-unknown}",
  "depsLockSha256": "${_lock_sha:-unknown}",
  "bindHost": "$GHL_MCP_BIND_HOST",
  "builtBy": "ghl-mcp-autostart.sh"
}
EOF
  rm -rf "$tmp"
  log "build OK — dist/ swapped (previous kept at dist.bak-prev)"
  return 0
}

# >>> GHL-MCP-ENV-CREDENTIAL-GUARD-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-env-credential-guard.test.sh)
# ── 3. The server .env — NEVER clobber a WORKING credential pairing ──────────
#
# B1 (P0, proven live on the operator box 2026-08-03). This function used to
# rewrite $MCP_DIR/.env unconditionally, taking GHL_LOCATION_ID straight from
# GOHIGHLEVEL_LOCATION_ID with NO BACKUP and NO VALIDATION. On a box where the
# configured location and the MCP token's scope disagree, the result is fatal
# AND unrecoverable. Measured, same token, same box:
#
#   .env value already on disk      -> HTTP 200
#   value the installer wrote over it -> HTTP 403
#                                        "The token does not have access to this location."
#
# main.js calls `await ghlClient.testConnection()` at boot and process.exit(1)s
# on failure (src/main.ts:69 + 222-225), so a wrong location does not degrade
# quietly — the server goes DOWN and STAYS down. Crash-only supervision then
# does exactly the right thing and keeps it down. And because this function kept
# no copy of what it replaced, the working .env had to be recovered from a Time
# Machine snapshot. That is the whole defect: a destructive write, of an
# unvalidated value, over a proven-good one, with no way back.
#
# THE RULE NOW — a credential pairing PROVEN to work is never replaced by one
# that is not proven to work:
#   * a byte-identical rewrite is a NO-OP: no write, no backup, no churn
#   * before ANY change, .env is backed up timestamped at 600, the copy is READ
#     BACK and compared, and a backup that cannot be made or verified REFUSES
#     the rewrite outright (backups pruned to the newest 5)
#   * when the candidate location differs from the one already on disk, BOTH are
#     validated with a read-only GET against the live API, using the token that
#     will actually be written, and the one that WORKS wins
#   * an EMPTY candidate never overwrites a non-empty existing value
#   * "cannot tell" (curl absent, network down, 5xx, 000) KEEPS the existing
#     value. An unproven candidate never wins by default.
#
# The decision is made ONCE per run and reassigns the global GHL_LOC, so every
# downstream launch surface (the pm2 ecosystem's env block, the systemd unit's
# EnvironmentFile) agrees with the .env rather than re-introducing the rejected
# value one layer up.

# _ghl_location_http_code <token> <location_id> — read-only probe of the
# location record. Prints ONLY the HTTP status code (000 when the call could not
# be made at all). NEVER prints the token, the location, or the response body.
_ghl_location_http_code() {
  local _tok="${1:-}" _loc="${2:-}"
  [ -n "$_tok" ] && [ -n "$_loc" ] || { printf '000'; return 0; }
  command -v curl >/dev/null 2>&1 || { printf '000'; return 0; }
  curl -s -o /dev/null -w '%{http_code}' -m 10 \
    "https://services.leadconnectorhq.com/locations/${_loc}" \
    -H "Authorization: Bearer ${_tok}" \
    -H "Version: 2021-07-28" 2>/dev/null || printf '000'
}

# _ghl_location_verdict <http_code> -> ok | rejected | unknown
# 404 counts as REJECTED: a location this token cannot see is a broken pairing,
# not an ambiguous one. Everything else (000 offline, 5xx, 429) is UNKNOWN and
# must never be treated as either a pass or a fail.
_ghl_location_verdict() {
  case "${1:-}" in
    200|201)     printf 'ok' ;;
    401|403|404) printf 'rejected' ;;
    *)           printf 'unknown' ;;
  esac
}

# Last 4 characters only — enough to tell two ids apart in a log, without
# printing a full credential-adjacent identifier into a shared log file.
_ghl_mask() { printf '…%s' "$(printf '%s' "${1:-}" | tail -c 4)"; }

_env_file_value() {  # <file> <KEY>
  local f="${1:-}" k="${2:-}"
  [ -f "$f" ] || return 0
  sed -n "s/^[[:space:]]*${k}=//p" "$f" 2>/dev/null | tail -1 | tr -d '"' | tr -d "'"
}

# Timestamped, verified, pruned backup. Returns non-zero when a backup could NOT
# be produced — the caller must then leave the file alone. "No backup" is exactly
# the condition that made the live incident unrecoverable, so it is fatal to the
# write, never a warning we proceed past.
_backup_server_env() {
  local f="${1:-}" ts bak n=0
  [ -f "$f" ] || return 0     # nothing to protect yet
  ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || echo unknown)"
  bak="${f}.bak-${ts}"
  if ! ( umask 077; cp -p "$f" "$bak" ) 2>/dev/null; then
    log "REFUSING to rewrite $f — could not write the backup $bak"
    return 1
  fi
  chmod 600 "$bak" 2>/dev/null || true
  if ! cmp -s "$f" "$bak" 2>/dev/null; then
    log "REFUSING to rewrite $f — the backup $bak does not match what is on disk"
    rm -f "$bak" 2>/dev/null || true
    return 1
  fi
  log "server .env backed up (verified, 600) -> $bak"
  while IFS= read -r _old; do
    [ -n "$_old" ] || continue
    n=$((n+1))
    [ "$n" -le 5 ] && continue
    rm -f "$_old" 2>/dev/null || true
  done <<EOF
$(ls -1 "${f}".bak-* 2>/dev/null | LC_ALL=C sort -r)
EOF
  return 0
}

# Decide the location id ONCE per run and publish it as the global GHL_LOC.
_GHL_LOC_RESOLVED=0
resolve_location_id() {
  [ "$_GHL_LOC_RESOLVED" = "1" ] && return 0
  _GHL_LOC_RESOLVED=1
  local ENVF="$MCP_DIR/.env" _existing="" _cand_code _exist_code _cand_v _exist_v
  _existing="$(_env_file_value "$ENVF" GHL_LOCATION_ID)"

  if [ -z "${GHL_LOC:-}" ]; then
    if [ -n "$_existing" ]; then
      GHL_LOC="$_existing"
      log "location id: no GOHIGHLEVEL_LOCATION_ID/GHL_LOCATION_ID resolvable here — keeping the value already on disk $(_ghl_mask "$_existing") (an EMPTY candidate never overwrites a working one)"
    fi
    return 0
  fi
  if [ -z "$_existing" ] || [ "$_existing" = "$GHL_LOC" ]; then
    return 0    # nothing on disk yet, or no change at all — nothing to prove
  fi

  # A REAL disagreement — the fatal case. Prove both before choosing either.
  _cand_code="$(_ghl_location_http_code "$GHL_TOKEN" "$GHL_LOC")"
  _exist_code="$(_ghl_location_http_code "$GHL_TOKEN" "$_existing")"
  _cand_v="$(_ghl_location_verdict "$_cand_code")"
  _exist_v="$(_ghl_location_verdict "$_exist_code")"
  log "location id DISAGREEMENT: on-disk $(_ghl_mask "$_existing") -> HTTP ${_exist_code} (${_exist_v}); configured $(_ghl_mask "$GHL_LOC") -> HTTP ${_cand_code} (${_cand_v})"

  if [ "$_cand_v" = "ok" ]; then
    log "location id: configured value VALIDATED against this token (HTTP ${_cand_code}) — adopting it"
    return 0
  fi
  if [ "$_exist_v" = "ok" ]; then
    log "############################################################"
    log "## GHL_LOCATION_ID NOT OVERWRITTEN — the configured value would TAKE THIS SERVER DOWN."
    log "##   configured $(_ghl_mask "$GHL_LOC") -> HTTP ${_cand_code} (rejected by this token)"
    log "##   on disk    $(_ghl_mask "$_existing") -> HTTP ${_exist_code} (works)"
    log "## main.js testConnection()s at boot and exit(1)s on failure, so writing the"
    log "## rejected value is a hard outage, not a degradation. KEEPING the working pairing."
    log "## ACTION: fix GOHIGHLEVEL_LOCATION_ID in this box's secrets/openclaw.json to"
    log "## match the MCP token's scope, or rotate the token to one scoped to that location."
    log "############################################################"
    GHL_LOC="$_existing"
    return 0
  fi
  GHL_LOC="$_existing"
  log "location id: NEITHER value could be proven (configured HTTP ${_cand_code}, on-disk HTTP ${_exist_code}) — keeping the on-disk value. An unproven candidate never wins by default."
  return 0
}

write_server_env() {
  [ -n "$GHL_TOKEN" ] || return 0
  resolve_location_id
  local ENVF="$MCP_DIR/.env" _new
  _new="$(cat <<EOF
GHL_API_KEY=${GHL_TOKEN}
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${GHL_LOC}
# main.js reads PORT before MCP_SERVER_PORT — pin BOTH so it can never bind random.
PORT=${GHL_MCP_PORT}
MCP_SERVER_PORT=${GHL_MCP_PORT}
# D2: upstream default is the FULL 858-tool surface. Pin the profile explicitly.
GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}
# D6: consumed by .ghl-mcp-bind-guard.cjs (NOT by main.js — upstream hardcodes
# its 0.0.0.0 bind). Loopback only; the guard coerces anything else back.
GHL_MCP_BIND_HOST=${GHL_MCP_BIND_HOST}
NODE_ENV=production
EOF
)"
  if [ -f "$ENVF" ] && [ "$(cat "$ENVF" 2>/dev/null)" = "$_new" ]; then
    log "server .env already byte-identical — no write, no backup (idempotent no-op)"
    return 0
  fi
  _backup_server_env "$ENVF" || return 1
  ( umask 077; printf '%s\n' "$_new" > "$ENVF" ) || {
    log "FATAL: could not write $ENVF"; return 1; }
  chmod 600 "$ENVF" 2>/dev/null || true
  log "server .env written (GHL_LOCATION_ID=$(_ghl_mask "$GHL_LOC"))"
  return 0
}
# <<< GHL-MCP-ENV-CREDENTIAL-GUARD-END

# ── 3b. D6: the BIND GUARD — force the listener onto loopback ────────────────
# The pinned upstream binds 0.0.0.0 from a hardcoded literal (src/main.ts:
# `app.listen(port, '0.0.0.0', …)`), so no environment variable can move it.
# This CommonJS preload is loaded via NODE_OPTIONS=--require by the launcher and
# rewrites the host argument of net.Server.prototype.listen — which every
# express/http listen path funnels through — before the real bind happens.
#
# FAIL-OPEN BY CONSTRUCTION: every step is wrapped so a guard that cannot load,
# or an argument shape it does not recognise, falls through to the original
# listen untouched. A security guard that bricks the server on 38 client boxes
# would be a worse outage than the one it prevents.
BIND_GUARD="$MCP_DIR/.ghl-mcp-bind-guard.cjs"
write_bind_guard() {
  cat > "$BIND_GUARD" <<'GUARDEOF'
'use strict';
// .ghl-mcp-bind-guard.cjs — generated by ghl-mcp-autostart.sh. DO NOT EDIT BY HAND.
//
// Forces the GHL community MCP to listen on loopback. Upstream hardcodes
// `app.listen(port, '0.0.0.0')`, exposing a CRM-credentialed, UNAUTHENTICATED
// endpoint to every host on the LAN. Loaded with `node --require`.
//
// Escape hatch: setting GHL_MCP_ALLOW_PUBLIC_BIND to 1 honours GHL_MCP_BIND_HOST
// verbatim. The repo's own launch surfaces never set it and the QC gate forbids
// them to, so it stays a deliberate per-box operator decision.
try {
  const net = require('net');
  const ALLOW_PUBLIC = process.env.GHL_MCP_ALLOW_PUBLIC_BIND === '1';
  let HOST = process.env.GHL_MCP_BIND_HOST || '127.0.0.1';
  const isLoopback = (h) =>
    typeof h === 'string' &&
    (h === 'localhost' || h === '::1' || h === '::ffff:127.0.0.1' || /^127\./.test(h));
  // Fail CLOSED on the host VALUE (a non-loopback value is coerced back to
  // loopback) while failing OPEN on any unexpected argument SHAPE below.
  if (!ALLOW_PUBLIC && !isLoopback(HOST)) HOST = '127.0.0.1';

  const origListen = net.Server.prototype.listen;
  net.Server.prototype.listen = function patchedListen(...args) {
    try {
      const a0 = args[0];
      if (a0 !== null && typeof a0 === 'object' && !Array.isArray(a0)) {
        // listen(options[, cb]) — but never touch IPC (path) or fd handles.
        if (a0.port !== undefined && a0.path === undefined && a0.fd === undefined) {
          args[0] = Object.assign({}, a0, { host: HOST });
        }
      } else if (typeof a0 === 'number' || (typeof a0 === 'string' && /^[0-9]+$/.test(a0))) {
        // listen(port[, host][, backlog][, cb]) — replace an explicit host,
        // otherwise splice ours in directly after the port.
        if (typeof args[1] === 'string') args[1] = HOST;
        else args.splice(1, 0, HOST);
      }
      // Anything else (unix socket path, handle, unknown shape) is left alone.
    } catch (e) { /* never block a start */ }
    return origListen.apply(this, args);
  };
} catch (e) { /* fail-open: a broken guard must never stop the server */ }
GUARDEOF
  chmod 644 "$BIND_GUARD" 2>/dev/null || true
}

# ── 4. D3: the launcher wrapper — crash-only restart, no bad-token loop ──────
# main.js exits 1 on a bad token at boot. Every supervisor treats non-zero as
# "crashed" and relaunches → a 10s loop. The wrapper turns an AUTH rejection
# into a CLEAN exit 0, which every supervisor here is configured NOT to restart.
LAUNCHER="$MCP_DIR/.ghl-mcp-launch.sh"
write_launcher() {
  cat > "$LAUNCHER" <<'LAUNCHEOF'
#!/usr/bin/env bash
# .ghl-mcp-launch.sh — generated by ghl-mcp-autostart.sh. DO NOT EDIT BY HAND.
#
# Crash-only launcher for the GHL community MCP.
#   exit 0  -> a deliberate, non-restartable stop (missing/rejected credential).
#              launchd KeepAlive{SuccessfulExit:false}, pm2 stop_exit_codes:[0],
#              systemd Restart=on-failure and the fallback loop all honour this,
#              so a bad PIT can never become a 10s relaunch loop.
#   exec    -> otherwise the node server REPLACES this shell, so the supervisor
#              still watches the real process (no wrapper PID indirection).
set -u
MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
STAMP_DIR="${MCP_DIR}"
NOTE="${STAMP_DIR}/.ghl-mcp-credential-blocked"

# Load the server env (600-perm) without echoing it.
# LOG ROTATION (copytruncate). The supervisor holds an open fd on these files,
# so we copy-then-truncate IN PLACE; renaming would leave the server writing to
# an orphaned inode. Runs at every (re)start; the periodic probe repeats it so a
# long-lived process still gets rotated.
_ghl_rotate() {
  local f="$1" max="${GHL_MCP_LOG_MAX_BYTES:-10485760}" keep="${GHL_MCP_LOG_KEEP:-3}" sz i
  [ -f "$f" ] || return 0
  sz="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
  [ -n "$sz" ] || return 0
  [ "$sz" -gt "$max" ] 2>/dev/null || return 0
  rm -f "${f}.${keep}" 2>/dev/null || true
  i=$((keep-1))
  while [ "$i" -ge 1 ]; do
    [ -f "${f}.${i}" ] && mv "${f}.${i}" "${f}.$((i+1))" 2>/dev/null || true
    i=$((i-1))
  done
  cp "$f" "${f}.1" 2>/dev/null && : > "$f"
}
if [ -n "${GHL_MCP_LOG_DIR:-}" ]; then
  for _lf in "${GHL_MCP_LOG_DIR}/stdout.log" "${GHL_MCP_LOG_DIR}/stderr.log" \
             "${GHL_MCP_LOG_DIR}/ghl-mcp.log" "${GHL_MCP_LOG_DIR}/ghl-mcp.err.log"; do
    _ghl_rotate "$_lf"
  done
fi

if [ -f "${MCP_DIR}/.env" ]; then
  set -a; . "${MCP_DIR}/.env" 2>/dev/null || true; set +a
fi
: "${GHL_API_KEY:=}"
: "${GHL_LOCATION_ID:=}"
: "${GHL_BASE_URL:=https://services.leadconnectorhq.com}"

if [ -z "$GHL_API_KEY" ] || [ -z "$GHL_LOCATION_ID" ]; then
  printf '%s ghl-mcp launcher: GHL credential absent — NOT starting (clean exit, no restart loop)\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
  printf 'credential-absent %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$NOTE" 2>/dev/null || true
  exit 0
fi

# Bounded auth preflight: one call, 10s cap. 401/403 => the token is bad; exit
# cleanly instead of letting main.js exit(1) forever. Any other outcome
# (network blip, 5xx, curl missing) falls through and starts the server — we
# never block a start on a transient.
if command -v curl >/dev/null 2>&1; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
    "${GHL_BASE_URL}/locations/${GHL_LOCATION_ID}" \
    -H "Authorization: Bearer ${GHL_API_KEY}" \
    -H "Version: 2021-07-28" 2>/dev/null || echo 000)"
  case "$CODE" in
    401|403)
      printf '%s ghl-mcp launcher: GHL rejected the PIT (HTTP %s) — NOT starting (clean exit, no restart loop). Rotate/repair the token then re-run ghl-mcp-autostart.sh\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$CODE" >&2
      printf 'auth-rejected http=%s %s\n' "$CODE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$NOTE" 2>/dev/null || true
      exit 0
      ;;
  esac
fi
rm -f "$NOTE" 2>/dev/null || true

# D6 (P0 SECURITY): force the listener onto loopback. Upstream hardcodes
# `app.listen(port, '0.0.0.0')` — no env var can move it — so we preload a guard
# that rewrites the listen host. This runs LAST (after .env is sourced) so a
# stale .env cannot clobber NODE_OPTIONS. Every supervisor reaches node through
# this launcher, so all four inherit the guard from this one place.
: "${GHL_MCP_BIND_HOST:=127.0.0.1}"
export GHL_MCP_BIND_HOST
BIND_GUARD="${MCP_DIR}/.ghl-mcp-bind-guard.cjs"
if [ -f "$BIND_GUARD" ]; then
  NODE_OPTIONS="--require \"${BIND_GUARD}\" ${NODE_OPTIONS:-}"
  export NODE_OPTIONS
else
  printf '%s ghl-mcp launcher: WARNING bind guard missing at %s — the server will bind ALL INTERFACES (0.0.0.0). Re-run ghl-mcp-autostart.sh.\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$BIND_GUARD" >&2
fi

NODE_BIN="${GHL_MCP_NODE_BIN:-$(command -v node 2>/dev/null || echo node)}"
cd "$MCP_DIR" || exit 1
exec "$NODE_BIN" "${MCP_DIR}/dist/main.js"
LAUNCHEOF
  chmod +x "$LAUNCHER" 2>/dev/null || true
}

# ── Managed cron lines: sentinel-tagged, REPLACED when they drift ────────────
# F13: the old shape was `crontab -l | grep -Fq "ghl-mcp-probe.sh" && skip`. When
# the delivered script path changed (…/skills/scripts → …/scripts, or a /data
# layout change) the substring STILL matched the stale line, so the new line was
# never added and the old one survived pointing at a path that no longer exists —
# a silently dead 15-minute probe and a silently dead reboot-resurrect hook, with
# nothing anywhere reporting a problem. Match on a SENTINEL COMMENT that only we
# write, and REPLACE the line whenever it differs from the one we intend.
CRON_TAG_PROBE="# managed:ghl-mcp-probe"
CRON_TAG_RESURRECT="# managed:ghl-mcp-pm2-resurrect"
upsert_cron_line() {
  local tag="$1" line="$2" current desired
  command -v crontab >/dev/null 2>&1 || return 1
  current="$(crontab -l 2>/dev/null || true)"
  # Already exactly right -> no write at all (keeps this idempotent + quiet).
  case "$current" in
    *"$line"*) return 1 ;;
  esac
  # Drop every previously-managed line carrying this tag, then append the new one.
  desired="$(printf '%s\n' "$current" | grep -vF "$tag" 2>/dev/null || true)"
  printf '%s\n%s\n' "$desired" "$line" | grep -v '^$' | crontab - >/dev/null 2>&1 || return 1
  return 0
}

# ── 5. Health + liveness ─────────────────────────────────────────────────────
health_ok() {
  command -v curl >/dev/null 2>&1 || return 1
  local body
  body="$(curl -fsS --max-time 5 "http://localhost:${GHL_MCP_PORT}/health" 2>/dev/null || true)"
  # Healthy = our GHL MCP (reports "healthy" / a tools count). Reject Cognee's
  # response, which means we hit the wrong port (INSTALL.md §6).
  # F14: this used to match ONLY the version literal `0.5.3-local`, so any Cognee
  # UPGRADE would defeat the check here while ghl-mcp-probe.sh still caught it.
  # Both now use the same discriminator — match the SERVICE, not one version of it.
  case "$body" in
    *0.5.3-local*|*cognee*|*Cognee*) return 1 ;;
    *healthy*|*tools*) return 0 ;;
    *) return 1 ;;
  esac
}

# ── D6: is the live listener actually on loopback? ───────────────────────────
# Returns 0 = every LISTEN socket on the port is loopback (good)
#         1 = at least one is a wildcard/routable address (the D6 exposure)
#         2 = cannot tell (no lsof — common in slim containers). Callers must
#             treat 2 as UNKNOWN and never report it as either verdict.
listener_is_loopback() {
  command -v lsof >/dev/null 2>&1 || return 2
  local out
  out="$(lsof -nP -iTCP:"${GHL_MCP_PORT}" -sTCP:LISTEN 2>/dev/null | tail -n +2)"
  [ -n "$out" ] || return 2
  # A wildcard bind prints as `*:8765`; an explicit all-interfaces bind as
  # `0.0.0.0:8765`; IPv6 any as `[::]:8765`.
  case "$out" in
    *"*:${GHL_MCP_PORT}"*|*"0.0.0.0:${GHL_MCP_PORT}"*|*"[::]:${GHL_MCP_PORT}"*) return 1 ;;
  esac
  return 0
}

# The REAL test: does a JSON-RPC request get an ANSWER? /health is served by
# express before the MCP transport is wired, so a stale/deaf dist still returns
# {"status":"healthy"} while every agent init hangs the full 30s (D1/D5).
# B3 (DEAD ON ARRIVAL FLEET-WIDE): this resolver listed
# $HOME/.openclaw/skills/scripts/ and /data/.openclaw/skills/scripts/ — an extra
# `skills/` segment that NOTHING delivers to. update-skills.sh delivers the
# canonical scripts/ tree to $OC_ROOT/scripts (deliver_canonical_scripts_tree ->
# _OC_SCRIPTS_DEST), so neither candidate could ever match on a real box. The
# only candidate that ever hit was $SELF_DIR — and on the FLEET path $SELF_DIR is
# the temp extract dir, which the updater `rm -rf`s. Net effect: PROBE resolved
# empty on every rolled box, so install_periodic_probe() took its
# "not co-located — periodic liveness probe NOT installed" branch and the
# 15-minute liveness probe was never installed anywhere. It passed in operator-box testing
# only because that run used a persistent checkout.
#
# The DELIVERED path is now present, on both platforms, ahead of the legacy one.
# $SELF_DIR stays first (it is how a developer checkout and CI resolve). The
# `skills/scripts` pair is KEPT, last, as a legacy fallback: some long-lived
# boxes were provisioned when install.sh copied the whole repo under skills/, and
# dropping it could strand one of them. It is no longer the ONLY option, which is
# what made this dead on arrival.
# scripts/qc-assert-pin-delivery-paths.sh now fails CI if any resolver here omits
# the delivered path.
PROBE="$(
  for c in "$SELF_DIR/ghl-mcp-probe.sh" \
           "$HOME/.openclaw/scripts/ghl-mcp-probe.sh" \
           "/data/.openclaw/scripts/ghl-mcp-probe.sh" \
           "$HOME/.openclaw/skills/scripts/ghl-mcp-probe.sh" \
           "/data/.openclaw/skills/scripts/ghl-mcp-probe.sh"; do
    [ -f "$c" ] && { printf '%s' "$c"; break; }
  done
)"
responds_ok() {
  if [ -n "${PROBE:-}" ]; then
    # --skip-profile: here we only want the LIVENESS verdict; profile drift is
    # reported separately by the periodic probe and must not be misread as deaf.
    GHL_MCP_PORT="$GHL_MCP_PORT" GHL_MCP_PROBE_TIMEOUT="$GHL_MCP_PROBE_TIMEOUT" \
      bash "$PROBE" --once --quiet --skip-profile >/dev/null 2>&1
    return $?
  fi
  # Inline fallback if the probe script is not co-located.
  command -v curl >/dev/null 2>&1 || return 1
  curl -sS --max-time "$GHL_MCP_PROBE_TIMEOUT" -X POST "http://localhost:${GHL_MCP_PORT}/mcp" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ghl-mcp-autostart","version":"1"}}}' \
    2>/dev/null | grep -q 'serverInfo'
}

# ── 6. Write canonical launchd plist + boot (Mac); pm2/systemd (VPS) ─────────
start_service_mac() {
  local PLIST="$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist"
  local NODE_PATH; NODE_PATH="$(command -v node)"
  mkdir -p "$HOME/Library/Logs/ghl-mcp" 2>/dev/null || true
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp</string>
    <!-- Runs the crash-only launcher, not node directly: the launcher exits 0
         (no restart) when the PIT is missing/rejected, so a bad token can never
         become a 10s relaunch loop (D3). It exec's node, so launchd still
         supervises the real server process. -->
    <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>${LAUNCHER}</string>
    </array>
    <key>WorkingDirectory</key><string>${MCP_DIR}</string>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>NODE_ENV</key><string>production</string>
        <!-- main.js/http-server.ts read PORT BEFORE MCP_SERVER_PORT (src/main.ts:55).
             Pin BOTH to ${GHL_MCP_PORT} so a stray inherited PORT can never bind a random port. -->
        <key>PORT</key><string>${GHL_MCP_PORT}</string>
        <key>MCP_SERVER_PORT</key><string>${GHL_MCP_PORT}</string>
        <!-- D2: without this the registry serves the FULL 858-tool surface. -->
        <key>GHL_TOOL_PROFILE</key><string>${GHL_MCP_TOOL_PROFILE}</string>
        <!-- D6 (P0): loopback bind, enforced by .ghl-mcp-bind-guard.cjs which the
             launcher preloads. Upstream hardcodes app.listen(port,'0.0.0.0'), so
             this variable is read by OUR guard, never by main.js. -->
        <key>GHL_MCP_BIND_HOST</key><string>${GHL_MCP_BIND_HOST}</string>
        <key>GHL_MCP_NODE_BIN</key><string>${NODE_PATH}</string>
        <!-- Log rotation: the launcher copytruncates these at every (re)start
             and the periodic probe repeats it while the process is long-lived.
             Nothing in the fleet rotated them before (5.4 MB and counting). -->
        <key>GHL_MCP_LOG_DIR</key><string>${HOME}/Library/Logs/ghl-mcp</string>
        <key>GHL_MCP_LOG_MAX_BYTES</key><string>${GHL_MCP_LOG_MAX_BYTES}</string>
        <key>GHL_MCP_LOG_KEEP</key><string>${GHL_MCP_LOG_KEEP}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <!-- CRASH-ONLY (ghl-mcp-setup doctrine). NEVER the unconditional boolean
         form of KeepAlive: it restarts even a deliberate clean exit, which is
         what turns the bad-token exit into an infinite 10s relaunch loop.
         The QC gate rejects the boolean form outright. -->
    <key>KeepAlive</key><dict>
        <key>SuccessfulExit</key><false/>
        <key>Crashed</key><true/>
    </dict>
    <!-- 300s: the canonical fleet shape (matches the reference plist verified on
         a fleet box). Long enough that even a mis-detected crash cannot
         become a hot relaunch loop. -->
    <key>ThrottleInterval</key><integer>300</integer>
    <key>StandardOutPath</key><string>${HOME}/Library/Logs/ghl-mcp/stdout.log</string>
    <key>StandardErrorPath</key><string>${HOME}/Library/Logs/ghl-mcp/stderr.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
  # Idempotent re-boot: bootout (ignore failure if not loaded) then bootstrap.
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || \
    launchctl load "$PLIST" >/dev/null 2>&1 || true
}

# Write the canonical pm2 ecosystem.config.js (PORT + MCP_SERVER_PORT + the tool
# profile pinned). pm2 is the fleet-standard supervisor on VPS/Docker (no systemd
# in Hostinger containers). The ecosystem file is the single source of truth pm2
# reads, so the port/profile can never be inherited and the env is reproducible.
# SK1-70: the GHL PIT is NOT inlined here (world-readable) — it is loaded at
# launch from the 600-perm .ghl-mcp.env sitting next to this config.
write_vps_ecosystem() {
  # B1: the pm2 `env:` block below sets GHL_LOCATION_ID and therefore OVERRIDES
  # whatever .env holds. Resolving here as well means the ecosystem can never
  # re-introduce a location id that resolve_location_id() just proved this
  # token rejects — including on the D6 fast-path restart, which reaches
  # start_service_vps() without ever calling write_server_env(). The resolver is
  # cached, so this is a no-op when the main flow already ran it.
  resolve_location_id
  # NEVER clobber a good secret file with an empty one. The main flow reaches
  # here only after the GHL_TOKEN check, but the D6 fast-path restart above can
  # also land here on an already-healthy box, where the token is not re-proven.
  # Writing an empty GHL_API_KEY there would take a WORKING server down.
  if [ -n "$GHL_TOKEN" ]; then
    ( umask 077; printf 'GHL_API_KEY=%s\n' "$GHL_TOKEN" > "$MCP_DIR/.ghl-mcp.env" ) 2>/dev/null || true
    chmod 600 "$MCP_DIR/.ghl-mcp.env" 2>/dev/null || true
  else
    log "no GHL token resolvable in this context — leaving the existing .ghl-mcp.env untouched"
  fi
  cat > "$MCP_DIR/ecosystem.config.js" <<EOF
// ghl-community-mcp — pm2 ecosystem (generated by ghl-mcp-autostart.sh)
// main.js reads PORT before MCP_SERVER_PORT (src/main.ts:55) — BOTH pinned to ${GHL_MCP_PORT}.
// GHL_TOOL_PROFILE is pinned so the registry never serves the full 858-tool surface.
// SK1-70: the GHL PIT is loaded from the 600-perm .ghl-mcp.env, never inlined here.
const fs = require('fs');
const path = require('path');
function _loadEnvFile(f) {
  const out = {};
  try {
    fs.readFileSync(f, 'utf8').split('\n').forEach(function (line) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)/);
      if (m) out[m[1]] = m[2].trim();
    });
  } catch (e) { /* no secret file -> the server's own .env provides the creds */ }
  return out;
}
const _secret = _loadEnvFile(path.join(__dirname, '.ghl-mcp.env'));
module.exports = {
  apps: [{
    name: "ghl-community-mcp",
    cwd: "${MCP_DIR}",
    // Crash-only launcher (D3): exit 0 = deliberate stop, pm2 must NOT restart.
    script: ".ghl-mcp-launch.sh",
    interpreter: "bash",
    autorestart: true,
    stop_exit_codes: [0],
    max_restarts: 10,
    restart_delay: 5000,
    exp_backoff_restart_delay: 5000,
    env: Object.assign({
      NODE_ENV: "production",
      PORT: "${GHL_MCP_PORT}",
      MCP_SERVER_PORT: "${GHL_MCP_PORT}",
      GHL_TOOL_PROFILE: "${GHL_MCP_TOOL_PROFILE}",
      // D6 (P0): read by .ghl-mcp-bind-guard.cjs (preloaded by the launcher),
      // never by main.js — upstream hardcodes its 0.0.0.0 bind.
      GHL_MCP_BIND_HOST: "${GHL_MCP_BIND_HOST}",
      GHL_MCP_LOG_DIR: "/data/logs",
      GHL_MCP_LOG_MAX_BYTES: "${GHL_MCP_LOG_MAX_BYTES}",
      GHL_MCP_LOG_KEEP: "${GHL_MCP_LOG_KEEP}",
      GHL_BASE_URL: "https://services.leadconnectorhq.com",
      GHL_LOCATION_ID: "${GHL_LOC}"
    }, _secret),
    out_file: "/data/logs/ghl-mcp.log",
    error_file: "/data/logs/ghl-mcp.err.log"
  }]
};
EOF
}

# >>> GHL-MCP-PM2-REGISTRATION-MISMATCH-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-pm2-registration-mismatch.test.sh)
#
# DEFECT 2 (proven live 2026-08-04): `pm2 startOrReload` MERGES a regenerated
# ecosystem.config.js onto an app's EXISTING pm2 registration. When the new
# file changes `script:`/`interpreter:` — e.g. a box registered under the old
# `node dist/main.js` shape (no interpreter override) and this run writes the
# crash-only launcher (`script: ".ghl-mcp-launch.sh"`, `interpreter: "bash"`)
# — pm2 keeps the STALE `script: dist/main.js` and pairs it with the NEW
# `interpreter: bash`. bash then tries to execute compiled JavaScript as a
# shell script and crash-loops. `pm2 delete` + `pm2 start` always registers
# clean, at the cost of resetting the app's uptime/restart-count history, so
# it is used ONLY when a live registration actually disagrees with what this
# run is about to write — never unconditionally (an unconditional delete
# would lose that history on every ordinary, matching restart, for no
# reason). Detect, don't assume.

# _pm2_live_registration <app_name> — prints "script|interpreter" for the
# LIVE pm2 registration of <app_name>, or nothing if it does not exist or
# cannot be determined (missing pm2/python3). Non-secret fields only (a
# script path and an interpreter name are not credentials) — this does NOT
# need the pm2_env secret-filtering discipline scripts/ghl-mcp-assert-
# runtime.sh uses for the fuller record, but stays scoped to exactly the two
# fields this comparison needs regardless.
_pm2_live_registration() {
  local _name="$1"
  command -v pm2 >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  # `python3 -c "$snippet"` (an ARGUMENT), never `python3 - <<EOF` — a heredoc
  # attached to `python3 -` is consumed as the SCRIPT SOURCE, which leaves
  # nothing on stdin for json.load(sys.stdin) to read from the piped `pm2
  # jlist` output (an immediate EOF, silently caught by the except below, so
  # this would print nothing for every box, every time). Same discipline as
  # _GHL_FILTER_PM2_RECORD in scripts/ghl-mcp-assert-runtime.sh.
  local _snippet='
import json, os, sys
name = os.environ.get("NAME", "")
try:
    apps = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
for a in apps:
    if a.get("name") != name:
        continue
    env = a.get("pm2_env") if isinstance(a.get("pm2_env"), dict) else {}
    script = env.get("pm_exec_path") or a.get("pm_exec_path") or ""
    interp = env.get("exec_interpreter") or ""
    print("%s|%s" % (script, interp))
    break
'
  pm2 jlist 2>/dev/null | NAME="$_name" python3 -c "$_snippet" 2>/dev/null
}

# _pm2_registration_mismatch <app_name> <want_script_basename> <want_interpreter>
# Returns 0 (MISMATCH -> caller must force `pm2 delete` + `pm2 start`) or
# 1 (no live app, or it already matches -> `pm2 startOrReload` is safe).
# No live app at all is NOT a mismatch: a fresh install has nothing stale to
# collide with, and `startOrReload` already falls through to `pm2 start` on a
# name pm2 has never seen.
_pm2_registration_mismatch() {
  local _name="$1" _want_script="$2" _want_interp="$3"
  local _live_reg _live_script _live_interp
  _live_reg="$(_pm2_live_registration "$_name" || true)"
  [ -n "$_live_reg" ] || return 1
  _live_script="${_live_reg%%|*}"
  _live_interp="${_live_reg#*|}"
  if [ "${_live_script##*/}" != "$_want_script" ] || [ "$_live_interp" != "$_want_interp" ]; then
    return 0
  fi
  return 1
}
# <<< GHL-MCP-PM2-REGISTRATION-MISMATCH-END

start_service_vps() {
  local NODE_PATH; NODE_PATH="$(command -v node)"
  mkdir -p /data/logs 2>/dev/null || true
  write_vps_ecosystem

  # ── PRIMARY: pm2 (the fleet-standard supervisor; survives container restart via
  #    `pm2 save` + a reboot-resurrect hook). NEVER a bare nohup. ──────────────
  if command -v pm2 >/dev/null 2>&1; then
    log "starting GHL MCP under pm2 (ecosystem.config.js, PORT=${GHL_MCP_PORT}, profile=${GHL_MCP_TOOL_PROFILE})"

    # D2 (see the GHL-MCP-PM2-REGISTRATION-MISMATCH block above for the full
    # defect writeup): detect before assuming startOrReload is safe.
    if _pm2_registration_mismatch ghl-community-mcp ".ghl-mcp-launch.sh" "bash"; then
      log "pm2 registration MISMATCH detected for ghl-community-mcp — startOrReload would pair a NEW interpreter with a STALE script and crash-loop (D2). Forcing 'pm2 delete' + 'pm2 start' (this app's uptime/restart history resets; there is no way to change script/interpreter on a live pm2 process without one)."
      ( cd "$MCP_DIR" && pm2 delete ghl-community-mcp >/dev/null 2>&1
        pm2 start ecosystem.config.js >/dev/null 2>&1 ) || true
    else
      ( cd "$MCP_DIR" && pm2 startOrReload ecosystem.config.js >/dev/null 2>&1 \
          || pm2 start ecosystem.config.js >/dev/null 2>&1 ) || true
    fi
    pm2 save >/dev/null 2>&1 || true
    install_vps_reboot_resurrect
    return 0
  fi

  # ── FALLBACK A: systemd (non-container VPS). Reboot-surviving via enable. ────
  # GATED ON PASSWORDLESS SUDO (v21.5.0). Writing the unit file needs root, and a
  # bare `sudo` PROMPTS on a TTY — sudo writes its prompt to /dev/tty, so the
  # `>/dev/null 2>&1` below does NOT silence it. install.sh Step 14a calls this
  # script, so a prompt here hangs a whole install. Worse, the old shape swallowed
  # every sudo failure with `|| true` and then `return 0` — reporting a supervised
  # server while having installed absolutely nothing, which is precisely the class
  # of silent false-success this release exists to kill. If root is not available
  # non-interactively we say so and fall through to the supervised relaunch loop
  # (FALLBACK B), which needs no privileges at all.
  if command -v systemctl >/dev/null 2>&1 && ! sudo -n true 2>/dev/null; then
    log "systemctl present but no passwordless sudo — cannot install the unit; falling through to the supervised relaunch loop"
  elif command -v systemctl >/dev/null 2>&1; then
    log "pm2 not found — installing systemd unit ghl-mcp (PORT + profile pinned via Environment=)"
    sudo -n tee /etc/systemd/system/ghl-mcp.service > /dev/null <<EOF
[Unit]
Description=GHL Community MCP Server
After=network.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${MCP_DIR}
# Pin PORT explicitly (main.js reads PORT before MCP_SERVER_PORT).
Environment=PORT=${GHL_MCP_PORT}
Environment=MCP_SERVER_PORT=${GHL_MCP_PORT}
Environment=GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}
# D6 (P0): loopback bind, enforced by the launcher's .ghl-mcp-bind-guard.cjs.
Environment=GHL_MCP_BIND_HOST=${GHL_MCP_BIND_HOST}
Environment=GHL_MCP_LOG_DIR=/data/logs
Environment=GHL_MCP_LOG_MAX_BYTES=${GHL_MCP_LOG_MAX_BYTES}
Environment=GHL_MCP_LOG_KEEP=${GHL_MCP_LOG_KEEP}
Environment=NODE_ENV=production
Environment=GHL_MCP_NODE_BIN=${NODE_PATH}
# Crash-only launcher (D3): a clean exit 0 (bad/absent PIT) must NOT restart.
ExecStart=/bin/bash ${LAUNCHER}
Restart=on-failure
RestartSec=30
EnvironmentFile=${MCP_DIR}/.env
StandardOutput=append:/data/logs/ghl-mcp.log
StandardError=append:/data/logs/ghl-mcp.err.log

[Install]
WantedBy=multi-user.target
EOF
    sudo -n systemctl daemon-reload >/dev/null 2>&1 || true
    # Only claim success if the unit actually came up. Otherwise fall through to
    # the supervised loop rather than returning a supervised-looking lie.
    if sudo -n systemctl enable --now ghl-mcp >/dev/null 2>&1; then
      return 0
    fi
    log "systemd unit did not enable/start — falling through to the supervised relaunch loop"
  fi

  # ── FALLBACK B (last resort): supervised relaunch loop, NOT a bare nohup. ────
  # A bare `nohup node …` does NOT survive session/exec teardown and is the exact
  # failure that took 12/19 fleet boxes down. This wrapper double-forks a detached
  # watch loop that re-launches the server if it ever CRASHES (poor-man's pm2),
  # with PORT + profile pinned, and STOPS on a clean exit 0 (D3).
  log "neither pm2 nor systemd available — installing supervised relaunch loop (PORT=${GHL_MCP_PORT})"
  local SUP="$MCP_DIR/.ghl-mcp-supervise.sh"
  cat > "$SUP" <<EOF
#!/usr/bin/env bash
# Detached supervisor for ghl-community-mcp — re-launches on CRASH only.
cd "${MCP_DIR}" || exit 1
while true; do
  PORT="${GHL_MCP_PORT}" MCP_SERVER_PORT="${GHL_MCP_PORT}" \\
    GHL_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE}" NODE_ENV=production \\
    GHL_MCP_BIND_HOST="${GHL_MCP_BIND_HOST}" \\
    GHL_MCP_NODE_BIN="${NODE_PATH}" GHL_MCP_LOG_DIR="/data/logs" \\
    GHL_MCP_LOG_MAX_BYTES="${GHL_MCP_LOG_MAX_BYTES}" GHL_MCP_LOG_KEEP="${GHL_MCP_LOG_KEEP}" \\
    /bin/bash "${LAUNCHER}" >> /data/logs/ghl-mcp.log 2>&1
  rc=\$?
  # Clean exit = deliberate stop (missing/rejected credential). Do NOT loop.
  [ "\$rc" = "0" ] && break
  sleep 10
done
EOF
  chmod +x "$SUP" 2>/dev/null || true
  # setsid detaches from the controlling terminal so it survives exec/session teardown.
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash "$SUP" >> /data/logs/ghl-mcp.log 2>&1 < /dev/null &
  else
    nohup bash "$SUP" >> /data/logs/ghl-mcp.log 2>&1 < /dev/null &
  fi
  disown 2>/dev/null || true
}

# Wire a reboot-resurrect hook so the pm2-managed MCP comes back after a host
# reboot / container restart. Matches the fleet pattern used by the Command
# Center: `pm2 resurrect` via the host @reboot cron AND/OR the Docker container
# `command:` override. We add the @reboot cron idempotently here; the
# container-command override is documented in INSTALL.md §5.6 for compose edits.
install_vps_reboot_resurrect() {
  command -v pm2 >/dev/null 2>&1 || return 0
  local PM2_BIN; PM2_BIN="$(command -v pm2)"
  # Prefer pm2's own startup integration where init systems exist (no-op in bare
  # containers, which is fine — the @reboot cron + container command cover those).
  pm2 startup >/dev/null 2>&1 || true
  # Idempotent @reboot cron entry (covers bare containers + plain VPS reboots).
  if command -v crontab >/dev/null 2>&1; then
    local LINE="@reboot ${PM2_BIN} resurrect >/data/logs/pm2-resurrect.log 2>&1 ${CRON_TAG_RESURRECT}"
    upsert_cron_line "$CRON_TAG_RESURRECT" "$LINE" \
      && log "installed/refreshed @reboot 'pm2 resurrect' cron (reboot-surviving)"
  fi
}

# ── 6b. LOG ROTATION (fleet gap: nothing ever rotated these) ─────────────────
# Two layers, because neither alone is guaranteed:
#   1. ALWAYS: the generated launcher copytruncates at every (re)start and the
#      periodic probe repeats it every 15 min. No root, no daemons, works in a
#      bare container. This is the layer we rely on.
#   2. BEST-EFFORT: the platform's own rotator (newsyslog on Mac, logrotate on
#      VPS, pm2-logrotate under pm2) when it can be configured WITHOUT an
#      interactive sudo prompt. Never blocks, never prompts.
install_log_rotation() {
  if [ "$PLATFORM" = "mac" ]; then
    local NSCONF="/etc/newsyslog.d/com.clawd.ghl-mcp.conf"
    if [ ! -f "$NSCONF" ] && sudo -n true 2>/dev/null; then
      printf '# logfilename                                  [owner:group]  mode count size(KB) when  flags\n%s/Library/Logs/ghl-mcp/stderr.log  %s:staff  644  %s  10240  *  GJ\n%s/Library/Logs/ghl-mcp/stdout.log  %s:staff  644  %s  10240  *  GJ\n' \
        "$HOME" "$(id -un)" "$GHL_MCP_LOG_KEEP" "$HOME" "$(id -un)" "$GHL_MCP_LOG_KEEP" \
        | sudo -n tee "$NSCONF" >/dev/null 2>&1 \
        && log "installed newsyslog rotation config $NSCONF (10 MB, keep ${GHL_MCP_LOG_KEEP})" \
        || log "newsyslog config not installed (no passwordless sudo) — the launcher/probe rotation still applies"
    else
      log "newsyslog config present or sudo unavailable — relying on launcher/probe rotation"
    fi
  else
    if command -v pm2 >/dev/null 2>&1; then
      # pm2-logrotate is the fleet-standard pm2 companion; install is a no-op if present.
      pm2 install pm2-logrotate >/dev/null 2>&1 || true
      pm2 set pm2-logrotate:max_size 10M >/dev/null 2>&1 || true
      pm2 set pm2-logrotate:retain "$GHL_MCP_LOG_KEEP" >/dev/null 2>&1 || true
      pm2 set pm2-logrotate:compress true >/dev/null 2>&1 || true
    fi
    local LRCONF="/etc/logrotate.d/ghl-mcp"
    if [ ! -f "$LRCONF" ] && command -v logrotate >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
      printf '/data/logs/ghl-mcp*.log {\n    size 10M\n    rotate %s\n    missingok\n    notifempty\n    compress\n    delaycompress\n    copytruncate\n}\n' "$GHL_MCP_LOG_KEEP" \
        | sudo -n tee "$LRCONF" >/dev/null 2>&1 \
        && log "installed logrotate config $LRCONF (10 MB, keep ${GHL_MCP_LOG_KEEP}, copytruncate)" \
        || log "logrotate config not installed — the launcher/probe rotation still applies"
    fi
    # Hostinger Docker note: also cap the container driver in compose —
    #   logging: { driver: "json-file", options: { max-size: "10m", max-file: "3" } }
    # That is a compose-file edit, documented in INSTALL.md §5.6.
  fi
}

# ── 7. Periodic liveness probe (D5) — every 15 minutes, self-healing once ────
install_periodic_probe() {
  [ -n "${PROBE:-}" ] || { log "ghl-mcp-probe.sh not co-located — periodic liveness probe NOT installed"; return 0; }
  if [ "$PLATFORM" = "mac" ]; then
    local PPLIST="$HOME/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist"
    cat > "$PPLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp-probe</string>
    <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>${PROBE}</string>
        <string>--once</string>
        <string>--heal</string>
    </array>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>GHL_MCP_PORT</key><string>${GHL_MCP_PORT}</string>
        <key>GHL_MCP_PROBE_TIMEOUT</key><string>${GHL_MCP_PROBE_TIMEOUT}</string>
        <!-- R12: pass the log dir EXPLICITLY. The probe used to compute this
             itself and ignore GHL_MCP_LOG_DIR, so its log location was
             coincidental rather than configured — and the unit test wrote real-
             looking verdicts straight into the production probe.log. -->
        <key>GHL_MCP_LOG_DIR</key><string>${LOG_DIR}</string>
    </dict>
    <key>StartInterval</key><integer>900</integer>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>${HOME}/Library/Logs/ghl-mcp/probe.log</string>
    <key>StandardErrorPath</key><string>${HOME}/Library/Logs/ghl-mcp/probe.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)" "$PPLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PPLIST" >/dev/null 2>&1 || \
      launchctl load "$PPLIST" >/dev/null 2>&1 || true
    log "periodic liveness probe installed (com.clawd.ghl-mcp-probe, every 900s)"
  else
    command -v crontab >/dev/null 2>&1 || return 0
    local LINE="*/15 * * * * GHL_MCP_LOG_DIR=${LOG_DIR} /bin/bash ${PROBE} --once --heal >>${LOG_DIR}/probe.log 2>&1 ${CRON_TAG_PROBE}"
    upsert_cron_line "$CRON_TAG_PROBE" "$LINE" \
      && log "periodic liveness probe cron installed/refreshed (*/15)"
  fi
}

# ── 8. Tier 2 is ON-DEMAND CURL — de-register any legacy mcp.servers entry ───
# skill 36 v1.1.0 doctrine, qc-ghl-mcp-setup.sh Section D and 36/wire.sh
# migration M2 all require ghl-community-mcp to be ABSENT from mcp.servers: its
# tool schemas would ride in every session's init whether or not GHL is touched,
# and a deaf/down server makes every init pay the full connectionTimeoutMs.
# This script used to re-register it right after wire.sh removed it. It no
# longer does; it removes a legacy registration instead and only publishes the
# canonical URL env var that the on-demand curl path reads.
# >>> OC-MCP-UNSET-VERB-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-unset-verb.test.sh)
# B2 (proven live on OpenClaw 2026.7.1-2): `openclaw mcp remove <name>` IS NOT A
# COMMAND. It exits 1 with "Too many arguments for this command." The verb is
# `unset`. Every de-registration call site in this repo used `remove`, and every
# one of them was swallowed by `|| true` — so Tier 2 was NEVER de-registered on
# ANY box, and check 10 of ghl-mcp-assert-runtime.sh ("ghl-community-mcp ABSENT
# from mcp.servers") could never pass anywhere. That was the last remaining FATAL
# on the pilot box.
#
# oc_mcp_unset tries `unset` first and falls back to `remove` for any older CLI
# that genuinely used it, then RETURNS THE OUTCOME. Callers must not `|| true`
# it: a swallowed failure is precisely how this stayed invisible for so long.
#   0 = the CLI accepted one of the verbs
#   1 = neither verb was accepted (or openclaw is absent)
oc_mcp_unset() {
  local _name="${1:-}"
  [ -n "$_name" ] || return 1
  command -v openclaw >/dev/null 2>&1 || return 1
  openclaw mcp unset "$_name" >/dev/null 2>&1 && return 0
  openclaw mcp remove "$_name" >/dev/null 2>&1 && return 0
  return 1
}

# Which verb does the INSTALLED CLI actually document? Reported (never guessed)
# so an operator reading the log can see whether the repo and the runtime agree.
oc_mcp_unset_verb_supported() {
  command -v openclaw >/dev/null 2>&1 || { printf 'no-cli'; return 0; }
  local _h
  _h="$(openclaw mcp --help 2>&1 || true)"
  case "$_h" in
    *' unset'*|*'unset '*) printf 'unset' ;;
    *' remove'*|*'remove '*) printf 'remove' ;;
    *) printf 'unknown' ;;
  esac
}

deregister_tier2() {
  command -v openclaw >/dev/null 2>&1 || return 0
  openclaw config set env.vars.GHL_COMMUNITY_MCP_URL "http://localhost:${GHL_MCP_PORT}" >/dev/null 2>&1 || true
  if openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; then
    log "de-registering legacy ghl-community-mcp (Tier 2 is on-demand curl); installed CLI documents the verb: $(oc_mcp_unset_verb_supported)"
    if ! oc_mcp_unset ghl-community-mcp; then
      log "WARN: neither 'openclaw mcp unset' nor 'openclaw mcp remove' was accepted — ghl-community-mcp is STILL registered. Every agent init will keep paying its tool-catalogue/connection cost. Check 'openclaw mcp --help'."
      return 0
    fi
    # RE-READ. The gateway can rewrite openclaw.json from memory, so a command
    # that exited 0 is not proof the entry is gone.
    if openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; then
      log "WARN: de-registration command succeeded but ghl-community-mcp is STILL listed — the gateway may have rewritten the config. It will be retried on the next run."
    else
      log "ghl-community-mcp de-registered and verified absent from mcp.servers"
    fi
  fi
}
# <<< OC-MCP-UNSET-VERB-END

# ── Main flow ────────────────────────────────────────────────────────────────

# Fast idempotent no-op: healthy AND answering JSON-RPC AND already built from
# the pinned commit. "A dist exists" is NOT a no-op condition (that is exactly
# how the stale deaf dist survived two days).
if [ -f "$BUILD_STAMP" ] && stamp_matches && dist_is_sane && health_ok && responds_ok; then
  # D6: a HEALTHY box is exactly the box this security fix has to reach. Every
  # box in the fleet is already healthy, so if the fast path simply returned here
  # the loopback fix would land on ZERO boxes until the next pin bump — the same
  # "shipped but never delivered" failure this release exists to end. So: install
  # the guard + launcher unconditionally, then restart ONLY if the live listener
  # is provably non-loopback, or if the guard did not exist before (meaning the
  # running process necessarily predates it and cannot have loaded it).
  _guard_was_present=0
  [ -f "$BIND_GUARD" ] && _guard_was_present=1
  write_bind_guard
  write_launcher
  listener_is_loopback; _lb_rc=$?
  if [ "$_lb_rc" = "1" ] || { [ "$_lb_rc" = "2" ] && [ "$_guard_was_present" = "0" ]; }; then
    if [ "$_lb_rc" = "1" ]; then
      log "live listener on :${GHL_MCP_PORT} is NOT bound to loopback — restarting under the bind guard (D6)"
    else
      log "bind guard was not installed before this run — restarting so the running server loads it (D6)"
    fi
    if [ "$PLATFORM" = "mac" ]; then start_service_mac; else start_service_vps; fi
    for _i in 1 2 3 4 5 6; do health_ok && break; command -v sleep >/dev/null 2>&1 && sleep 2 || true; done
  fi
  deregister_tier2
  install_log_rotation
  install_periodic_probe
  report "HEALTHY_ALREADY" "(pinned ${GHL_MCP_VETTED_COMMIT:0:12}, profile=${GHL_MCP_TOOL_PROFILE}, bind=${GHL_MCP_BIND_HOST}, :${GHL_MCP_PORT} answers JSON-RPC — idempotent no-op)"
  exit 0
fi

# Need GHL creds to build a usable server. Honest skip otherwise — NEVER claim
# the MCP is up when it cannot be.
if [ -z "$GHL_TOKEN" ]; then
  report "SKIPPED_NO_CREDS" "(GOHIGHLEVEL_API_KEY/GHL_API_KEY absent — server NOT started; this is an honest gap, not a failure. Set the GHL token then re-run.)"
  exit 0
fi

ensure_repo_at_pin
_PIN_RC=$?
if [ "$_PIN_RC" = "3" ]; then
  # ROOT_OWNERSHIP_MISMATCH was already reported (loud, with the exact remedy)
  # inside assert_ownership_matches_runtime_user() — never re-report it as the
  # generic PIN_MISMATCH/BUILD_FAILED below, which is exactly the innocent-
  # looking symptom that hid this root cause in the first place.
  exit 0
elif [ "$_PIN_RC" = "2" ]; then
  report "PIN_MISMATCH" "(cannot check out vetted commit ${GHL_MCP_VETTED_COMMIT:0:12} at $MCP_DIR — refusing to build/start an unpinned third-party MCP. Re-vet upstream and update config/ghl-mcp-pin.env.)"
  exit 0
elif [ "$_PIN_RC" != "0" ]; then
  report "BUILD_FAILED" "(could not clone/pin community MCP at $MCP_DIR — GHL tools will NOT resolve until fixed)"
  exit 0
fi

write_server_env
write_bind_guard
write_launcher

if needs_build; then
  if ! build_pinned; then
    report "BUILD_FAILED" "(build of pinned ${GHL_MCP_VETTED_COMMIT:0:12} failed — previous dist/ left intact; see $LOG_DIR/ghl-mcp-build.log)"
    exit 0
  fi
else
  log "dist/ already built from the pinned commit and passes the artifact check — skipping build"
fi

if [ "$PLATFORM" = "mac" ]; then
  start_service_mac
else
  start_service_vps
fi

# Allow the server a moment to boot, then verify (do NOT block on `sleep` long).
for _i in 1 2 3 4 5 6; do
  if health_ok; then break; fi
  command -v sleep >/dev/null 2>&1 && sleep 2 || true
done

deregister_tier2
install_log_rotation
install_periodic_probe

# Credential rejection is reported honestly, not as a mystery failure.
if [ -f "$MCP_DIR/.ghl-mcp-credential-blocked" ]; then
  report "TOKEN_REJECTED" "(GHL rejected the PIT at launch — server deliberately NOT running and NOT restart-looping. Rotate/repair GOHIGHLEVEL_API_KEY then re-run this script.)"
  exit 0
fi

if health_ok && responds_ok; then
  report "HEALTHY" "(pinned ${GHL_MCP_VETTED_COMMIT:0:12}, profile=${GHL_MCP_TOOL_PROFILE}, :${GHL_MCP_PORT} answers JSON-RPC; Tier 2 stays on-demand curl — not registered in mcp.servers)"
elif health_ok; then
  report "DEAF" "(:${GHL_MCP_PORT} /health is green but the MCP endpoint returned NO JSON-RPC response within ${GHL_MCP_PROBE_TIMEOUT}s — this is the stale-dist deafness signature. Check $LOG_DIR/ghl-mcp-build.log and re-run.)"
else
  report "STARTED_UNHEALTHY" "(supervisor installed on :${GHL_MCP_PORT} but /health not green yet — crash-only restart will retry; check $LOG_DIR. GHL tools may not resolve until healthy.)"
fi
exit 0
