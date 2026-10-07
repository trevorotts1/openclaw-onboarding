#!/usr/bin/env bash
# wire.sh - Skill 76 (Local Embedder). Client Macs only.
#
# Gives every client Mac a free local embedder for OpenClaw memory search:
#   1. Ollama >= 0.36.0 on 127.0.0.1: reuse a running one untouched, upgrade an
#      older one in place by its own method (only when idle), or install the
#      headless CLI (checksum-verified) at ~/.openclaw/ollama/ under the
#      LaunchAgent com.blackceo.ollama-serve. No GUI, no sudo, no install.sh.
#   2. Pull embeddinggemma-2:740m and pin `num_ctx 8192` on that SAME tag
#      (its own Modelfile + one PARAMETER line). Verified via /api/show, no load.
#   3. Write ONLY memory.search.* (atomic JSON deep-merge + config validate).
#   4. Re-index each agent once (`openclaw memory status --index --agent <id>`),
#      resumable through per-agent markers.
#
# Cloud protection (fail closed): never reads, writes or removes
# ~/.ollama/id_ed25519*, never signs out, never touches ~/.ollama, OLLAMA_* env,
# the app settings DB, brew services config or any OpenClaw chat-model config.
# The chat-config fingerprint, key-file stat, OLLAMA_* env, /api/me status and
# cloud tag list are compared before and after; any difference fails the run.
#
# Exit 0 = done or not applicable (VPS, Docker, Intel, macOS < 14).
# Exit 1 = deferred or failed; update-skills.sh withholds the .wired sentinel so
#          the next roll retries.
#
# Flags: --idempotent (accepted, always true) --dry-run (reads only, prints the
#        plan) --with-ornith (opt-in: also pull and pin ornith-1.5:9b)
#        --no-reindex (skip step 4)

set -uo pipefail

PIN_VERSION="0.40.0"
MIN_VERSION="0.36.0"
TGZ_URL="https://github.com/ollama/ollama/releases/download/v${PIN_VERSION}/ollama-darwin.tgz"
TGZ_SHA256="b490b4925a95c5f3dfcd889e566cf3dcd727848d59057fb00b03f1d6630326dc"
ZIP_URL="https://github.com/ollama/ollama/releases/download/v${PIN_VERSION}/Ollama-darwin.zip"
ZIP_SHA256="60dd339e77fdc8afe3286c51ff1fd8eb4f467ec178f33f4a85ec69dac6f2b9dd"
EMBED_TAG="embeddinggemma-2:740m"
EMBED_PARAMS="num_ctx 8192"
ORNITH_TAG="ornith-1.5:9b"
ORNITH_PARAMS="num_ctx 32768|num_predict 8192|temperature 0.6|top_k 20|top_p 0.95"
LABEL="com.blackceo.ollama-serve"

OC_ROOT="$HOME/.openclaw"
OC_JSON="$OC_ROOT/openclaw.json"
OUR_DIR="$OC_ROOT/ollama"
STATE_DIR="$OC_ROOT/local-embedder"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
KEY="$HOME/.ollama/id_ed25519"
VPS_ROOT="${LOCAL_EMBEDDER_VPS_ROOT:-/data/.openclaw}"   # overridable for tests only
APPS_DIR="${LOCAL_EMBEDDER_APPS_DIR:-/Applications}"      # overridable for tests only
IDLE_WAIT="${LOCAL_EMBEDDER_IDLE_WAIT:-60}"
OLLAMA_ENV_NAMES="OLLAMA_HOST OLLAMA_MODELS OLLAMA_KEEP_ALIVE OLLAMA_MAX_LOADED_MODELS OLLAMA_CONTEXT_LENGTH OLLAMA_ORIGINS OLLAMA_NUM_PARALLEL OLLAMA_FLASH_ATTENTION OLLAMA_KV_CACHE_TYPE"

DRY_RUN=0; WITH_ORNITH=0; REINDEX=1
for _a in "$@"; do
  case "$_a" in
    --idempotent) ;;
    --dry-run) DRY_RUN=1 ;;
    --with-ornith) WITH_ORNITH=1 ;;
    --no-reindex) REINDEX=0 ;;
    *) echo "[local-embedder] unknown flag: $_a" >&2; exit 2 ;;
  esac
done

log()   { echo "[local-embedder] $*"; }
skip()  { log "SKIPPED: $*"; exit 0; }
defer() { log "DEFERRED (next roll retries): $*"; exit 1; }
die()   { log "FAIL: $*"; exit 1; }
# Every mutating command goes through run(): in --dry-run it is only printed.
run()   { if [ "$DRY_RUN" = 1 ]; then log "dry-run would run: $*"; return 0; fi; "$@"; }

# ── 0. Applicability guards (all read-only) ─────────────────────────────────
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_platform=""
if [ -f "$SKILL_DIR/../lib-shared.sh" ]; then
  # shellcheck disable=SC1091
  _platform="$(. "$SKILL_DIR/../lib-shared.sh" >/dev/null 2>&1; detect_platform 2>/dev/null || true)"
fi
if [ -z "$_platform" ]; then
  case "$(uname -s)" in Darwin) _platform=mac ;; *) _platform=vps ;; esac
fi
[ "$_platform" = mac ] || skip "not a Mac (platform=$_platform); VPS/Contabo boxes keep their cloud embedder"
[ -d "$VPS_ROOT" ] && skip "$VPS_ROOT exists (VPS layout)"
[ -f /.dockerenv ] && skip "inside Docker"
[ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ] || skip "not Apple Silicon"
_macos_major="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
case "$_macos_major" in ''|*[!0-9]*) skip "macOS version unreadable" ;; esac
[ "$_macos_major" -ge 14 ] || skip "macOS $_macos_major < 14"
[ -f "$OC_JSON" ] || skip "no $OC_JSON (OpenClaw not installed here)"
command -v openclaw >/dev/null 2>&1 || defer "openclaw CLI not on PATH; cannot validate a config write"
command -v python3 >/dev/null 2>&1 || defer "python3 not on PATH"

ver_ge() { python3 - "$1" "$2" <<'PY'
import re, sys
def v(s):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else None
a, b = v(sys.argv[1]), v(sys.argv[2])
sys.exit(0 if a and b and a >= b else 1)
PY
}

_oc_ver="$(openclaw --version 2>/dev/null | head -n1)"
ver_ge "$_oc_ver" "2026.9.0" || defer "OpenClaw '$_oc_ver' is older than 2026.9.0 (memory.search key); update OpenClaw first"

_loop_mode="$(python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); print(((c.get("proxy") or {}).get("loopbackMode")) or "")' "$OC_JSON" 2>/dev/null)"
[ "$_loop_mode" = block ] && defer "proxy.loopbackMode=block denies local embeddings; owner decision needed"

_need_gb=5; [ "$WITH_ORNITH" = 1 ] || [ -f "$STATE_DIR/with-ornith" ] && _need_gb=15
_free_gb="$(df -g "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
case "$_free_gb" in ''|*[!0-9]*) defer "free disk unreadable" ;; esac
[ "$_free_gb" -ge "$_need_gb" ] || defer "only ${_free_gb} GB free, need ${_need_gb} GB"

# ── 1. Snapshots used to prove nothing outside memory.search changed ────────
chat_fp() { python3 - "$OC_JSON" <<'PY'
# Fingerprint of everything that is chat-model config: the whole top-level
# "models" block (providers, :cloud refs, contextWindow, params) plus "agents"
# with only memory keys removed (model primary/fallbacks, models allowlist,
# subagents). memory.search is deliberately outside the fingerprint.
import hashlib, json, sys
cfg = json.load(open(sys.argv[1]))
def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in ("memorySearch", "memory")}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o
blob = json.dumps({"models": cfg.get("models"), "agents": strip(cfg.get("agents"))}, sort_keys=True)
print(hashlib.sha256(blob.encode()).hexdigest())
PY
}
# Metadata only (inode, size, mtime, mode). The key files are never opened.
key_stat() { python3 - "$KEY" "$KEY.pub" <<'PY'
import os, sys
out = []
for p in sys.argv[1:]:
    try:
        s = os.stat(p)
        out.append("%d:%d:%d:%o" % (s.st_ino, s.st_size, int(s.st_mtime), s.st_mode))
    except FileNotFoundError:
        out.append("absent")
print(" ".join(out))
PY
}
ollama_env() { local n; for n in $OLLAMA_ENV_NAMES; do printf '%s=%s;' "$n" "$(launchctl getenv "$n" 2>/dev/null)"; done; }

PRE_FP="$(chat_fp)" || die "cannot parse $OC_JSON"
PRE_KEY="$(key_stat)"
PRE_ENV="$(ollama_env)"

# ── 2. Find the Ollama daemon (port from lsof, never assumed) ───────────────
PORT=""; PID=""; EXE=""; BASE=""; DAEMON_VER=""
api_get()  { curl -fsS --max-time "${2:-10}" "$BASE$1"; }
api_post() { curl -fsS --max-time "${3:-30}" -H 'Content-Type: application/json' -d "$2" "$BASE$1"; }
# -a: AND the selections (lsof ORs them by default, which would list every ollama file).
listeners() { lsof -a -nP -iTCP -sTCP:LISTEN -c ollama 2>/dev/null | awk 'NR>1 && $1 ~ /^ollama/ && $10 == "(LISTEN)" {n=split($9,a,":"); print $2, a[n]}' | sort -u; }

find_daemon() {
  PORT=""; PID=""; EXE=""; BASE=""; DAEMON_VER=""
  local pid port v
  while read -r pid port; do
    [ -n "$port" ] || continue
    v="$(curl -fsS --max-time 5 "http://127.0.0.1:$port/api/version" 2>/dev/null \
         | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null)"
    if [ -n "$v" ]; then
      PID="$pid"; PORT="$port"; DAEMON_VER="$v"; BASE="http://127.0.0.1:$port"
      EXE="$(ps -o comm= -p "$pid" 2>/dev/null | head -n1)"
      return 0
    fi
  done <<EOF
$(listeners)
EOF
  return 1
}

wait_daemon() { local i=0; while [ "$i" -lt 30 ]; do find_daemon && return 0; sleep 2; i=$((i+1)); done; return 1; }

cloud_state() { # /api/me HTTP status | sorted cloud tag names. No generation.
  local me tags
  me="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -X POST "$BASE/api/me" 2>/dev/null)"
  tags="$(api_get /api/tags | python3 -c 'import json,sys; print(",".join(sorted(m.get("name","") for m in json.load(sys.stdin).get("models",[]) if m.get("remote_host"))))' 2>/dev/null)"
  printf '%s|%s' "$me" "$tags"
}

is_idle() {
  api_get /api/ps | python3 -c 'import json,sys; sys.exit(0 if not json.load(sys.stdin).get("models") else 1)' 2>/dev/null || return 1
  [ "$(lsof -nP -iTCP:"$PORT" -sTCP:ESTABLISHED 2>/dev/null | awk 'NR>1' | wc -l | tr -d ' ')" = 0 ]
}
wait_idle() {
  local i=1
  while [ "$i" -le 3 ]; do
    is_idle && return 0
    [ "$i" -lt 3 ] && { log "Ollama busy (loaded models or open connections); re-check $i/3 in ${IDLE_WAIT}s"; sleep "$IDLE_WAIT"; }
    i=$((i+1))
  done
  return 1
}

fetch_verified() { # <url> <sha256> <dest-file>
  run curl -fL --retry 3 --max-time 1800 -o "$3" "$1" || return 1
  [ "$DRY_RUN" = 1 ] && return 0
  [ "$(shasum -a 256 "$3" | awk '{print $1}')" = "$2" ] || { log "checksum MISMATCH for $1"; rm -f "$3"; return 1; }
}

install_pinned_cli() { # extracts the verified tarball to $OUR_DIR/$PIN_VERSION, points current at it
  local dest="$OUR_DIR/$PIN_VERSION" tmp="$OUR_DIR/.staging.$$"
  if [ ! -x "$dest/ollama" ]; then
    run mkdir -p "$tmp/x" || return 1
    fetch_verified "$TGZ_URL" "$TGZ_SHA256" "$tmp/ollama-darwin.tgz" || { rm -rf "$tmp"; return 1; }
    run tar -xzf "$tmp/ollama-darwin.tgz" -C "$tmp/x" || { rm -rf "$tmp"; return 1; }
    run mv "$tmp/x" "$dest" || { rm -rf "$tmp"; return 1; }
    [ "$DRY_RUN" = 1 ] || rm -rf "$tmp"
  fi
  run ln -sfn "$PIN_VERSION" "$OUR_DIR/current"
}

write_plist() {
  local tmp="$PLIST.tmp.$$"
  if [ "$DRY_RUN" = 1 ]; then log "dry-run would write $PLIST (ollama serve, OLLAMA_KEEP_ALIVE=3m, OLLAMA_MAX_LOADED_MODELS=2)"; return 0; fi
  mkdir -p "$(dirname "$PLIST")" "$OC_ROOT/logs" || return 1
  cat > "$tmp" <<PL || return 1
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$OUR_DIR/current/ollama</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_KEEP_ALIVE</key><string>3m</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>2</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$OC_ROOT/logs/ollama-serve.log</string>
  <key>StandardErrorPath</key><string>$OC_ROOT/logs/ollama-serve.log</string>
</dict>
</plist>
PL
  plutil -lint "$tmp" >/dev/null 2>&1 || { rm -f "$tmp"; return 1; }
  mv -f "$tmp" "$PLIST"
}

gui_domain() { launchctl print "gui/$(id -u)" >/dev/null 2>&1; }
load_ours() {
  if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    run launchctl kickstart -k "gui/$(id -u)/$LABEL"
  else
    run launchctl bootstrap "gui/$(id -u)" "$PLIST"
  fi
}

other_installs() { # prints what Ollama installs exist besides a running daemon
  [ -d "$APPS_DIR/Ollama.app" ] && echo "app:$APPS_DIR/Ollama.app"
  [ -d "$HOME/Applications/Ollama.app" ] && echo "app:$HOME/Applications/Ollama.app"
  command -v ollama >/dev/null 2>&1 && echo "cli:$(command -v ollama)"
  [ -f "$PLIST" ] && echo "ours:$PLIST"
  return 0
}

brew_bin() { command -v brew 2>/dev/null || { [ -x /opt/homebrew/bin/brew ] && echo /opt/homebrew/bin/brew; }; }

upgrade_in_place() { # only called when the running daemon is < MIN_VERSION
  wait_idle || defer "Ollama $DAEMON_VER needs an upgrade but was never idle (3 checks, ${IDLE_WAIT}s apart)"
  local brew; brew="$(brew_bin)"
  case "$EXE" in
    "$OUR_DIR"/*)
      install_pinned_cli || die "could not stage Ollama $PIN_VERSION"
      run launchctl kickstart -k "gui/$(id -u)/$LABEL" || die "kickstart of $LABEL failed" ;;
    */Ollama.app/*)
      local app="${EXE%%/Contents/*}" cask=""
      if [ -n "$brew" ]; then
        "$brew" list --cask ollama-app >/dev/null 2>&1 && cask=ollama-app
        [ -z "$cask" ] && "$brew" list --cask ollama >/dev/null 2>&1 && cask=ollama
      fi
      if [ -n "$cask" ]; then
        run "$brew" update || die "brew update failed"
        run osascript -e 'quit app "Ollama"'
        run "$brew" upgrade --cask --greedy "$cask" || die "brew upgrade --cask $cask failed"
      else
        [ -w "$(dirname "$app")" ] && [ -w "$app" ] || defer "$app is not writable without sudo; manual upgrade needed"
        local tmp="$STATE_DIR/.app.$$"
        run mkdir -p "$tmp" || die "cannot create $tmp"
        fetch_verified "$ZIP_URL" "$ZIP_SHA256" "$tmp/Ollama-darwin.zip" || { rm -rf "$tmp"; die "app download failed"; }
        run ditto -x -k "$tmp/Ollama-darwin.zip" "$tmp/new" || { rm -rf "$tmp"; die "unzip failed"; }
        run osascript -e 'quit app "Ollama"'
        local i=0; while [ "$DRY_RUN" = 0 ] && [ "$i" -lt 30 ] && kill -0 "$PID" 2>/dev/null; do sleep 1; i=$((i+1)); done
        # The old bundle goes to the Trash (recoverable), never rm -rf.
        run mkdir -p "$HOME/.Trash"
        run mv "$app" "$HOME/.Trash/Ollama-$DAEMON_VER-$$.app" || { rm -rf "$tmp"; die "could not move the old app aside"; }
        run mv "$tmp/new/Ollama.app" "$app" || die "could not place the new app; the old one is in ~/.Trash"
        [ "$DRY_RUN" = 1 ] || rm -rf "$tmp"
      fi
      run open -g -a "$app" --args hidden ;;
    */Cellar/ollama/*|*/opt/ollama/*)
      [ -n "$brew" ] || defer "Homebrew Ollama found but brew is not on PATH"
      local was_service=0
      "$brew" services list 2>/dev/null | awk '$1=="ollama" && $2=="started"' | grep -q . && was_service=1
      run "$brew" upgrade ollama || die "brew upgrade ollama failed"
      [ "$was_service" = 1 ] || defer "Ollama formula upgraded, but it is not run by brew services; restart it by hand"
      run "$brew" services restart ollama || die "brew services restart ollama failed" ;;
    *)
      defer "standalone Ollama at '${EXE:-unknown}' ($DAEMON_VER) is below $MIN_VERSION; upgrade it by hand (no automatic method for this install shape)" ;;
  esac
  [ "$DRY_RUN" = 1 ] && return 0
  wait_daemon || die "Ollama did not come back after the upgrade"
  ver_ge "$DAEMON_VER" "$MIN_VERSION" || die "Ollama is still $DAEMON_VER after the upgrade"
}

PRE_CLOUD=""
if find_daemon; then
  log "Ollama $DAEMON_VER is running on 127.0.0.1:$PORT (${EXE:-unknown executable})"
  PRE_CLOUD="$(cloud_state)"
  if ver_ge "$DAEMON_VER" "$MIN_VERSION"; then
    log "reusing it as-is: nothing installed, nothing restarted, no env changed"
  else
    log "Ollama $DAEMON_VER < $MIN_VERSION: upgrading in place by its own method"
    upgrade_in_place
  fi
elif [ -n "$(listeners)" ]; then
  defer "an Ollama process listens but does not answer on 127.0.0.1 (custom OLLAMA_HOST?); not touching it"
else
  _others="$(other_installs)"
  if printf '%s\n' "$_others" | grep -q '^ours:'; then
    log "our $LABEL exists but is not answering: re-loading it"
    gui_domain || defer "no GUI login session (launchd gui/ domain); retry when the owner is logged in"
    install_pinned_cli || die "could not stage Ollama $PIN_VERSION"
    load_ours || die "could not load $LABEL"
  elif [ -n "$_others" ]; then
    defer "Ollama is installed but not running ($(printf '%s' "$_others" | tr '\n' ' ')); the owner keeps it stopped, so it is not started for them"
  else
    log "no Ollama on this Mac: installing the headless CLI $PIN_VERSION under $LABEL"
    [ -z "$(lsof -nP -iTCP:11434 -sTCP:LISTEN 2>/dev/null | awk 'NR>1')" ] || defer "port 11434 is held by another program"
    gui_domain || defer "no GUI login session (launchd gui/ domain); retry when the owner is logged in"
    install_pinned_cli || die "could not download or verify Ollama $PIN_VERSION"
    write_plist || die "could not write $PLIST"
    load_ours || die "could not load $LABEL"
  fi
  if [ "$DRY_RUN" = 1 ]; then
    log "dry-run: stopping before model pull and config write (no daemon to talk to)"; exit 0
  fi
  wait_daemon || die "Ollama did not start; see $OC_ROOT/logs/ollama-serve.log"
fi
[ -n "$(other_installs | grep '^app:')" ] && [ -f "$PLIST" ] && \
  log "WARNING: both the Ollama app and $LABEL exist; they would compete for the port. Reported only, neither is stopped."

# Always talk to the daemon through its own executable (it is also its CLI).
# OLLAMA_HOST here is scoped to these child commands only, never exported.
OLLAMA_BIN="$EXE"
[ -x "$OLLAMA_BIN" ] || OLLAMA_BIN="$OUR_DIR/current/ollama"
[ -x "$OLLAMA_BIN" ] || die "cannot find the ollama executable for pinning (daemon exe '${EXE:-?}')"

# ── 3. Pull + pin on the ORIGINAL tag ───────────────────────────────────────
has_tag() { api_get /api/tags | python3 -c 'import json,sys; sys.exit(0 if sys.argv[1] in {m.get("name") for m in json.load(sys.stdin).get("models",[])} else 1)' "$1" 2>/dev/null; }
pin_ok() { # <tag> <"k v|k v"> [need-capability]
  api_post /api/show "{\"model\":\"$1\"}" | python3 -c '
import json, re, sys
d = json.load(sys.stdin)
params = d.get("parameters") or ""
for kv in sys.argv[1].split("|"):
    k, v = kv.split()
    vals = re.findall(r"^%s\s+(\S+)\s*$" % re.escape(k), params, re.M)
    if vals != [v]:
        sys.exit(1)
if sys.argv[2] and sys.argv[2] not in (d.get("capabilities") or []):
    sys.exit(1)
' "$2" "${3:-}" 2>/dev/null
}
pin_tag() { # <tag> <"k v|k v">: re-create the SAME tag from its own Modelfile + PARAMETER lines
  local tag="$1" params="$2" mf="$STATE_DIR/Modelfile.$$"
  run mkdir -p "$STATE_DIR"
  if [ "$DRY_RUN" = 1 ]; then log "dry-run would run: ollama create $tag -f <own Modelfile + PARAMETER ${params//|/, PARAMETER }>"; return 0; fi
  OLLAMA_HOST="127.0.0.1:$PORT" "$OLLAMA_BIN" show --modelfile "$tag" > "$mf.orig" || return 1
  python3 - "$mf.orig" "$mf" "$params" <<'PY' || return 1
import re, sys
src, dst, params = sys.argv[1], sys.argv[2], sys.argv[3].split("|")
keys = {p.split()[0] for p in params}
lines = [l for l in open(src).read().splitlines()
         if not re.match(r"^\s*PARAMETER\s+(%s)\s" % "|".join(map(re.escape, keys)), l, re.I)]
if not any(re.match(r"^\s*FROM\s", l, re.I) for l in lines):
    sys.exit("no FROM line in the model's own Modelfile")
open(dst, "w").write("\n".join(lines).rstrip("\n") + "\n" + "".join("PARAMETER %s\n" % p for p in params))
PY
  OLLAMA_HOST="127.0.0.1:$PORT" "$OLLAMA_BIN" create "$tag" -f "$mf"; local rc=$?
  rm -f "$mf" "$mf.orig"
  return $rc
}
ensure_model() { # <tag> <params> <capability>
  local tag="$1" params="$2" cap="$3"
  if ! has_tag "$tag"; then
    log "pulling $tag (download only, no load)"
    if [ "$DRY_RUN" = 1 ]; then log "dry-run would POST /api/pull $tag"
    else api_post /api/pull "{\"model\":\"$tag\",\"stream\":false}" 3600 >/dev/null || die "pull of $tag failed"; fi
  fi
  if pin_ok "$tag" "$params" "$cap"; then
    log "$tag already pinned (${params//|/, })"; return 0
  fi
  log "pinning ${params//|/, } on $tag (same tag, no copy)"
  pin_tag "$tag" "$params" || die "pin of $tag failed"
  [ "$DRY_RUN" = 1 ] && return 0
  pin_ok "$tag" "$params" "$cap" || die "/api/show does not report ${params//|/, }${cap:+ + capability $cap} on $tag after pinning"
  log "verified by /api/show (metadata only): $tag has ${params//|/, }"
}

embed_loaded() { api_get /api/ps 2>/dev/null | grep -q "\"$EMBED_TAG\""; }
PRE_LOADED=0; embed_loaded && PRE_LOADED=1
ensure_model "$EMBED_TAG" "$EMBED_PARAMS" embedding
if [ "$WITH_ORNITH" = 1 ]; then run mkdir -p "$STATE_DIR"; run touch "$STATE_DIR/with-ornith"; fi
[ -f "$STATE_DIR/with-ornith" ] || [ "$WITH_ORNITH" = 1 ] && ensure_model "$ORNITH_TAG" "$ORNITH_PARAMS" ""

# ── 4. memory.search (ONLY these keys) ──────────────────────────────────────
WRITE_RC=0
BACKUP="$OC_JSON.bak-local-embedder-$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP" OC_JSON="$OC_JSON" BASE="$BASE" EMBED_TAG="$EMBED_TAG" PRE_FP="$PRE_FP" DRY_RUN="$DRY_RUN" python3 - <<'PY' || WRITE_RC=$?
import hashlib, json, os, re, stat, sys
path = os.environ["OC_JSON"]
raw = open(path).read()
cfg = json.loads(raw)

def fp(c):
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("memorySearch", "memory")}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    return hashlib.sha256(json.dumps({"models": c.get("models"), "agents": strip(c.get("agents"))}, sort_keys=True).encode()).hexdigest()

if fp(cfg) != os.environ["PRE_FP"]:
    sys.exit("chat-model config changed during this run (not by us); refusing to write")

def has_openai_key():  # presence only; no value is ever printed
    if str((((cfg.get("models") or {}).get("providers") or {}).get("openai") or {}).get("apiKey") or "").strip():
        return True
    if str(((cfg.get("env") or {}).get("vars") or {}).get("OPENAI_API_KEY") or "").strip():
        return True
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return True
    root = os.path.dirname(path)
    for f in (os.path.join(root, "secrets", ".env"), os.path.join(root, ".env")):
        try:
            for line in open(f):
                m = re.match(r"\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)", line)
                if m and m.group(1).strip().strip("'\""):
                    return True
        except OSError:
            pass
    return False

mem = cfg.setdefault("memory", {})
if not isinstance(mem, dict):
    sys.exit("memory is not an object; refusing to write")
ms = mem.setdefault("search", {})
if not isinstance(ms, dict):
    sys.exit("memory.search is not an object; refusing to write")
before = json.dumps(ms, sort_keys=True)
ms["provider"] = "ollama"
ms["model"] = os.environ["EMBED_TAG"]
remote = ms.get("remote") if isinstance(ms.get("remote"), dict) else {}
remote["baseUrl"] = os.environ["BASE"]
ms["remote"] = remote
mm = ms.get("multimodal") if isinstance(ms.get("multimodal"), dict) else {}
mm["enabled"] = False
ms["multimodal"] = mm
if "dimensions" in ms:
    ms["dimensions"] = 768  # embeddinggemma-2 vector length; a stale 3072/1536 would be wrong metadata
if has_openai_key():
    ms["fallback"] = "openai"
    print("[local-embedder] memory.search.fallback = openai (an OpenAI key is present)")
else:
    print("[local-embedder] REPORT: no OpenAI key; memory.search.fallback kept as %r. If local Ollama is down, memory search %s."
          % (ms.get("fallback"), "uses that fallback" if ms.get("fallback") else "has no fallback"))

if json.dumps(ms, sort_keys=True) == before:
    print("[local-embedder] memory.search already on the local embedder; no write")
    sys.exit(0)
if fp(cfg) != os.environ["PRE_FP"]:
    sys.exit("internal error: staged config differs outside memory.search; refusing to write")
if os.environ.get("DRY_RUN") == "1":
    print("[local-embedder] dry-run would set memory.search to " + json.dumps(ms, sort_keys=True))
    sys.exit(0)
mode = stat.S_IMODE(os.stat(path).st_mode)
def write_private(p, text):  # created 0600 first, so secrets in the config are never briefly world-readable
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(p, mode)
backup = os.environ["BACKUP"]
write_private(backup, raw)
tmp = "%s.tmp.%d" % (path, os.getpid())
write_private(tmp, json.dumps(cfg, indent=2) + "\n")
os.replace(tmp, path)
print("[local-embedder] memory.search written atomically (backup: %s)" % backup)
sys.exit(10)
PY
case "$WRITE_RC" in
  0) ;;
  10)
    if ! openclaw config validate >/dev/null 2>&1; then
      cp -p "$BACKUP" "$OC_JSON"
      die "openclaw config validate rejected the memory.search write; original restored from $BACKUP"
    fi
    log "openclaw config validate: OK" ;;
  *) die "memory.search write refused (rc=$WRITE_RC)" ;;
esac

# ── 5. Post-verify: nothing but memory.search changed ───────────────────────
[ "$(chat_fp)" = "$PRE_FP" ] || die "chat-model config fingerprint CHANGED (models.providers / agent model refs); operator review needed"
[ "$(key_stat)" = "$PRE_KEY" ] || die "~/.ollama/id_ed25519* metadata CHANGED"
[ "$(ollama_env)" = "$PRE_ENV" ] || die "OLLAMA_* launchd env CHANGED"
if [ -n "$PRE_CLOUD" ] && [ "$DRY_RUN" = 0 ]; then
  _post_cloud="$(cloud_state)"
  [ "$_post_cloud" = "$PRE_CLOUD" ] || die "cloud state CHANGED (/api/me status | cloud tags): before '$PRE_CLOUD' after '$_post_cloud'"
  log "cloud sign-in status and cloud tags unchanged (${PRE_CLOUD%%|*})"
fi
if [ "$DRY_RUN" = 0 ] && [ "$PRE_LOADED" = 0 ] && embed_loaded; then
  die "$EMBED_TAG is loaded, but nothing in this run should have loaded it"
fi
log "verified: chat config, cloud key files, OLLAMA_* env unchanged"

# ── 6. One re-index per agent, resumable ────────────────────────────────────
if [ "$REINDEX" = 0 ] || [ "$DRY_RUN" = 1 ]; then
  log "re-index skipped (--no-reindex or --dry-run)"; exit 0
fi
_agents="$(python3 -c '
import json, sys
a = (json.load(open(sys.argv[1])).get("agents") or {})
ids = list(a["entries"]) if isinstance(a.get("entries"), dict) else []
ids += [x.get("id") for x in (a.get("list") or []) if isinstance(x, dict) and x.get("id") and x.get("id") not in ids]
print("\n".join(ids or ["main"]))' "$OC_JSON")"
mkdir -p "$STATE_DIR/reindexed"
_failed=""
while IFS= read -r _id; do
  [ -n "$_id" ] || continue
  _mark="$STATE_DIR/reindexed/$_id"
  if [ "$(cat "$_mark" 2>/dev/null)" = "$EMBED_TAG" ]; then log "agent $_id already re-indexed on $EMBED_TAG"; continue; fi
  log "re-indexing agent $_id on $EMBED_TAG"
  if openclaw memory status --index --agent "$_id"; then
    printf '%s\n' "$EMBED_TAG" > "$_mark"
  else
    _failed="$_failed $_id"
  fi
done <<EOF
$_agents
EOF
[ -z "$_failed" ] || defer "re-index failed for:$_failed (finished agents are kept; the next roll resumes)"
log "DONE: memory search runs on local $EMBED_TAG (num_ctx 8192) via $BASE"
exit 0
