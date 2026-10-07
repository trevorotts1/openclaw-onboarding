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
#   3. Verify every guard (below) BEFORE any config write.
#   4. Write ONLY memory.search.* (atomic, race-checked deep-merge + config
#      validate). The one allowed per-agent change rides in the SAME write: an
#      agent that INHERITS the local provider (no own provider/model/remote) and
#      has multimodal.enabled=true gets that single key set to false, because the
#      local text embedder has no multimodal adapter and the re-index would fail
#      with "memory.search.multimodal requires a provider adapter...". An agent
#      with its own provider/model/remote is reported and left alone.
#      This is the LAST mutating step before the re-index, so no failure can
#      leave a box with config on local but daemon/model not ready.
#   5. Re-index each agent once (`openclaw memory status --index --agent <id>`),
#      time-bounded and resumable through per-agent markers. A transient SQLite
#      failure ("did not stabilize", busy/locked) is retried 2 more times with a
#      backoff before the agent is left for the next roll.
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
#        --no-reindex (skip the re-index)
#        --sop-fallback-only (run ONLY step 5c, the Gemini SOP fallback copy;
#          update-skills.sh calls it after the Command Center refresh, so a CC
#          that reaches >= 7.6.108 later in the same roll is still provisioned)

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
# THE fallback knob: memory.search.fallback written on every client Mac.
# Default "none": a 768-dim local index is never queried or rebuilt in another
# provider's vector space while local Ollama is down (OpenClaw's own default is
# "none" too). Set LOCAL_EMBEDDER_FALLBACK=<provider> only on purpose.
MEMORY_FALLBACK="${LOCAL_EMBEDDER_FALLBACK:-none}"
REINDEX_TIMEOUT="${LOCAL_EMBEDDER_REINDEX_TIMEOUT:-900}"   # seconds per agent
REINDEX_RETRIES="${LOCAL_EMBEDDER_REINDEX_RETRIES:-2}"      # extra tries on a transient SQLite error
REINDEX_BACKOFF="${LOCAL_EMBEDDER_REINDEX_BACKOFF:-20}"     # seconds; attempt N waits N x this
BREW_TIMEOUT="${LOCAL_EMBEDDER_BREW_TIMEOUT:-1800}"        # seconds per brew call
APP_STOP_WAIT="${LOCAL_EMBEDDER_APP_STOP_WAIT:-30}"        # seconds after SIGTERM

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

DRY_RUN=0; WITH_ORNITH=0; REINDEX=1; SOPFB_ONLY=0
for _a in "$@"; do
  case "$_a" in
    --idempotent) ;;
    --dry-run) DRY_RUN=1 ;;
    --with-ornith) WITH_ORNITH=1 ;;
    --no-reindex) REINDEX=0 ;;
    --sop-fallback-only) SOPFB_ONLY=1 ;;
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

if [ "$SOPFB_ONLY" = 0 ]; then
  _need_gb=5; [ "$WITH_ORNITH" = 1 ] || [ -f "$STATE_DIR/with-ornith" ] && _need_gb=15
  _free_gb="$(df -g "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
  case "$_free_gb" in ''|*[!0-9]*) defer "free disk unreadable" ;; esac
  [ "$_free_gb" -ge "$_need_gb" ] || defer "only ${_free_gb} GB free, need ${_need_gb} GB"
fi

# ── 1. Snapshots used to prove nothing outside memory.search changed ────────
chat_fp() { python3 - "$OC_JSON" <<'PY'
# Fingerprint of what automation must never change: the whole "models" block
# (providers, :cloud refs, contextWindow, params), the WHOLE "agents" block
# (model primary/fallbacks, allowlist, subagents AND every per-agent memory
# override) and top-level "memory" minus memory.search. Only memory.search is
# outside it. The ONE exception inside "agents": a per-agent
# memory.search.multimodal.enabled (and the legacy memorySearch spelling) is
# stripped before hashing, because step 4 may flip exactly that key to false.
# Every other per-agent key, including provider/model/remote, stays hashed.
import hashlib, json, sys
cfg = json.load(open(sys.argv[1]))
_a = cfg.get("agents")
if isinstance(_a, dict):
    _rows = list(_a["entries"].values()) if isinstance(_a.get("entries"), dict) else []
    _rows += _a["list"] if isinstance(_a.get("list"), list) else []
    for _e in _rows:
        if not isinstance(_e, dict):
            continue
        _m = _e.get("memory")
        for _b in ((_m.get("search") if isinstance(_m, dict) else None), _e.get("memorySearch")):
            if isinstance(_b, dict) and isinstance(_b.get("multimodal"), dict):
                _b["multimodal"].pop("enabled", None)
mem = dict(cfg["memory"]) if isinstance(cfg.get("memory"), dict) else cfg.get("memory")
if isinstance(mem, dict):
    mem.pop("search", None)
blob = json.dumps({"models": cfg.get("models"), "agents": cfg.get("agents"), "memory": mem}, sort_keys=True)
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
# Keys may only go from absent to present when THIS run installed (or re-loaded)
# our own daemon: its first `ollama serve` creates them. Pre-existing keys must
# be identical; anything else fails closed.
_key_field_ok() { [ "$1" = "$2" ] || { [ "$1" = absent ] && [ "$FRESH" = 1 ]; }; }
keys_ok() {
  local pre1 pre2 post1 post2
  read -r pre1 pre2 <<EOF
$PRE_KEY
EOF
  read -r post1 post2 <<EOF
$(key_stat)
EOF
  _key_field_ok "$pre1" "$post1" && _key_field_ok "$pre2" "$post2"
}

# Bounded run, bash 3.2 safe (stock macOS has no GNU timeout): a perl alarm
# survives exec; without perl, background + kill. Returns 124 on timeout.
with_timeout() { # <seconds> <cmd...>
  local secs="$1" rc pid w; shift
  if command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift; exec @ARGV or exit 127' "$secs" "$@"; rc=$?
    [ "$rc" = 142 ] && rc=124
    return $rc
  fi
  "$@" & pid=$!
  ( sleep "$secs"; kill -TERM "$pid" 2>/dev/null ) & w=$!
  wait "$pid"; rc=$?
  if kill -0 "$w" 2>/dev/null; then kill "$w" 2>/dev/null; else rc=124; fi
  return $rc
}

# ── 1b. Gemini SOP fallback helpers (used by 5b, 5c and --sop-fallback-only) ──
_has_gkey="$(OC_ROOT="$OC_ROOT" OC_JSON="$OC_JSON" python3 - <<'PY' 2>/dev/null
import json, os
ok = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
root = os.environ["OC_ROOT"]
for f in (os.path.join(root, "secrets", ".env"), os.path.join(root, ".env")):  # same sources as embedding_engine.fallback_google_key
    try:
        for ln in open(f):
            k, _, v = ln.strip().partition("=")
            if k in ("GOOGLE_API_KEY", "GEMINI_API_KEY") and v.strip(" \"'"):
                ok = True
    except OSError:
        pass
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    env = cfg.get("env") or {}
    ok = ok or any(b.get(k) for b in (env, env.get("vars") or {}) for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY"))
    gk = (((cfg.get("models") or {}).get("providers") or {}).get("google") or {}).get("apiKey")
    ok = ok or (isinstance(gk, str) and gk.strip() != "" and not gk.startswith("$"))
except Exception:
    pass
print("yes" if ok else "no")
PY
)"

# 1b (cont.) Gemini fallback copy of the shared SOP set (own key only), called at step 5c:
# Trevor's order: when local Ollama is down, the Command Center's SOP vote
# embeds the task with the box's OWN Google key and votes against the shared
# prebuilt Gemini SOP vectors in a SEPARATE table, sop_embeddings_gemini_fallback.
# The CC's own script (>= v7.6.108) downloads the sha256-pinned asset and maps
# it onto this box's sops: zero embedding API calls, so the key is needed only at
# query time; this step is still gated on the key so a box that can never use the
# fallback does not carry 36 MB of it. sop_embeddings (the local 768-dim table)
# is never touched. Never fatal. Re-runs only when the manifest sha or the box's
# sops count changed.
SOPFB_TIMEOUT="${LOCAL_EMBEDDER_SOPFB_TIMEOUT:-600}"   # seconds (36 MB download)
SOPFB_MIN_CC="7.6.108"
SOPFB_SCRIPT="scripts/provision-gemini-fallback-sop-set.ts"
sopfb_cc_dir() { local d
  for d in "${LOCAL_EMBEDDER_CC_DIR:-}" "${CC_APP_DIR:-}" "${BLACKCEO_COMMAND_CENTER_ROOT:-}" \
           "$HOME/projects/command-center" "$HOME/projects/blackceo-command-center" "$HOME/blackceo-command-center"; do
    [ -n "$d" ] && [ -f "$d/package.json" ] && [ -f "$d/$SOPFB_SCRIPT" ] && { echo "$d"; return 0; }
  done
  return 1
}
# The node whose better-sqlite3 loads (the PATH node is often an nvm Node 24 that fails it):
# the CC's own serving process first, then known Homebrew nodes, then PATH.
sopfb_node() { local cc="$1" pid n c cands=""
  for pid in $(lsof -nP -iTCP:"${CC_PORT:-4000}" -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p'); do
    n="$(lsof -a -p "$pid" -d txt -Fn 2>/dev/null | sed -n 's/^n\(.*\/node\)$/\1/p' | head -n1)"
    [ -n "$n" ] && cands="$cands
$n"
  done
  for c in "${CC_NODE:-}" /opt/homebrew/opt/node@22/bin/node /opt/homebrew/opt/node@20/bin/node \
           /opt/homebrew/bin/node /usr/local/bin/node "$(command -v node 2>/dev/null)"; do
    [ -n "$c" ] && cands="$cands
$c"
  done
  while IFS= read -r c; do
    [ -n "$c" ] && [ -x "$c" ] && ( cd "$cc" && "$c" -e "require('better-sqlite3')" ) >/dev/null 2>&1 && { echo "$c"; return 0; }
  done <<EOF
$cands
EOF
  return 1
}
sopfb_provision() { # returns 0 done/skipped, 1 failed (caller only logs)
  local cc db man sha nsops stamp mark node rc ccv
  [ "$_has_gkey" = yes ] || { log "Gemini SOP fallback skipped: this box has no Google key of its own"; return 0; }
  cc="$(sopfb_cc_dir)" || { log "Gemini SOP fallback skipped: no Command Center with $SOPFB_SCRIPT on this box"; return 0; }
  ccv="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1] + "/package.json")).get("version",""))' "$cc" 2>/dev/null)"
  ver_ge "$ccv" "$SOPFB_MIN_CC" || { log "Gemini SOP fallback skipped: Command Center '${ccv:-unknown}' is older than $SOPFB_MIN_CC"; return 0; }
  man="$SKILL_DIR/../shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json"
  [ -f "$man" ] || { log "Gemini SOP fallback skipped: SOP embeddings manifest not found"; return 0; }
  db="$(python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from resolve_db import find_dashboard_db, is_db_found
p = find_dashboard_db()
print(str(p) if is_db_found(p) else "")' "$SKILL_DIR/../shared-utils" 2>/dev/null)"
  [ -n "$db" ] && [ -f "$db" ] || { log "Gemini SOP fallback skipped: no mission-control.db resolved"; return 0; }
  nsops="$(python3 -c 'import sqlite3,sys; print(sqlite3.connect("file:"+sys.argv[1]+"?mode=ro", uri=True).execute("select count(*) from sops").fetchone()[0])' "$db" 2>/dev/null)"
  case "$nsops" in ''|*[!0-9]*) log "Gemini SOP fallback skipped: no readable sops table in the Command Center database"; return 0 ;; esac
  sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("sha256",""))' "$man" 2>/dev/null)"
  [ -n "$sha" ] || { log "Gemini SOP fallback skipped: manifest has no sha256"; return 0; }
  stamp="$sha|$nsops|$db"; mark="$STATE_DIR/gemini-sop-fallback.done"
  if [ "$(cat "$mark" 2>/dev/null)" = "$stamp" ]; then log "Gemini SOP fallback already provisioned (manifest sha and sops count unchanged)"; return 0; fi
  node="$(sopfb_node "$cc")" || { log "Gemini SOP fallback not provisioned: no node that loads better-sqlite3 in $cc (next roll retries)"; return 1; }
  if [ "$DRY_RUN" = 1 ]; then log "dry-run would run (cd $cc): $node --import tsx $SOPFB_SCRIPT --manifest <manifest> --db $db"; return 0; fi
  log "provisioning the Gemini SOP fallback set into $db (limit ${SOPFB_TIMEOUT}s)"
  rc=0; ( cd "$cc" && with_timeout "$SOPFB_TIMEOUT" "$node" --import tsx "$SOPFB_SCRIPT" --manifest "$man" --db "$db" ) || rc=$?
  if [ "$rc" = 0 ]; then mkdir -p "$STATE_DIR" && printf '%s\n' "$stamp" > "$mark"; return 0; fi
  [ "$rc" = 124 ] && log "Gemini SOP fallback timed out after ${SOPFB_TIMEOUT}s"
  return 1
}

if [ "$SOPFB_ONLY" = 1 ]; then
  sopfb_provision || log "Gemini SOP fallback not provisioned (non-fatal; next roll retries)"
  exit 0
fi

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

# Graceful stop without Apple Events (osascript would need an Automation
# consent nobody can answer over SSH): SIGTERM the app process (the parent of
# `ollama serve`), wait, and report whether both are gone.
stop_app() { # <app bundle path>
  local app="$1" apid i=0
  apid="$(ps -o ppid= -p "$PID" 2>/dev/null | tr -d ' ')"
  case "$(ps -o comm= -p "$apid" 2>/dev/null)" in
    "$app"/Contents/MacOS/*) ;;
    *) apid="" ;;
  esac
  if [ "$DRY_RUN" = 1 ]; then log "dry-run would SIGTERM the Ollama app (pid ${apid:-$PID})"; return 0; fi
  kill -TERM "${apid:-$PID}" 2>/dev/null
  while [ "$i" -lt "$APP_STOP_WAIT" ]; do
    { [ -z "$apid" ] || ! kill -0 "$apid" 2>/dev/null; } && ! kill -0 "$PID" 2>/dev/null && return 0
    sleep 1; i=$((i+1))
  done
  return 1
}

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
        run with_timeout "$BREW_TIMEOUT" "$brew" update || defer "brew update failed or timed out (${BREW_TIMEOUT}s)"
        stop_app "$app" || defer "the Ollama app is still running ${APP_STOP_WAIT}s after SIGTERM; upgrade deferred, nothing replaced"
        if ! run with_timeout "$BREW_TIMEOUT" "$brew" upgrade --cask --greedy "$cask"; then
          run open -g -a "$app" --args hidden
          die "brew upgrade --cask $cask failed or timed out; the existing app was relaunched"
        fi
      else
        [ -w "$(dirname "$app")" ] && [ -w "$app" ] || defer "$app is not writable without sudo; manual upgrade needed"
        local tmp="$STATE_DIR/.app.$$"
        run mkdir -p "$tmp" || die "cannot create $tmp"
        fetch_verified "$ZIP_URL" "$ZIP_SHA256" "$tmp/Ollama-darwin.zip" || { rm -rf "$tmp"; die "app download failed"; }
        run ditto -x -k "$tmp/Ollama-darwin.zip" "$tmp/new" || { rm -rf "$tmp"; die "unzip failed"; }
        stop_app "$app" || { rm -rf "$tmp"; defer "the Ollama app is still running ${APP_STOP_WAIT}s after SIGTERM; upgrade deferred, the running bundle was NOT replaced"; }
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
      [ "$was_service" = 1 ] || defer "Ollama formula is not run by brew services, so it cannot be restarted after an upgrade; upgrade it by hand"
      run with_timeout "$BREW_TIMEOUT" "$brew" upgrade ollama || die "brew upgrade ollama failed or timed out"
      run with_timeout 300 "$brew" services restart ollama || die "brew services restart ollama failed or timed out" ;;
    *)
      defer "standalone Ollama at '${EXE:-unknown}' ($DAEMON_VER) is below $MIN_VERSION; upgrade it by hand (no automatic method for this install shape)" ;;
  esac
  [ "$DRY_RUN" = 1 ] && return 0
  wait_daemon || die "Ollama did not come back after the upgrade"
  ver_ge "$DAEMON_VER" "$MIN_VERSION" || die "Ollama is still $DAEMON_VER after the upgrade"
}

PRE_CLOUD=""; FRESH=0
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
    FRESH=1
  elif [ -n "$_others" ]; then
    defer "Ollama is installed but not running ($(printf '%s' "$_others" | tr '\n' ' ')); the owner keeps it stopped, so it is not started for them"
  else
    log "no Ollama on this Mac: installing the headless CLI $PIN_VERSION under $LABEL"
    [ -z "$(lsof -nP -iTCP:11434 -sTCP:LISTEN 2>/dev/null | awk 'NR>1')" ] || defer "port 11434 is held by another program"
    gui_domain || defer "no GUI login session (launchd gui/ domain); retry when the owner is logged in"
    install_pinned_cli || die "could not download or verify Ollama $PIN_VERSION"
    write_plist || die "could not write $PLIST"
    load_ours || die "could not load $LABEL"
    FRESH=1
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
  OLLAMA_HOST="127.0.0.1:$PORT" with_timeout 120 "$OLLAMA_BIN" show --modelfile "$tag" > "$mf.orig" || return 1
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
  OLLAMA_HOST="127.0.0.1:$PORT" with_timeout 900 "$OLLAMA_BIN" create "$tag" -f "$mf"; local rc=$?
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

# ── 4. Every guard passes BEFORE any config write ───────────────────────────
# Daemon and model are ready at this point. Nothing below runs unless all of
# these hold, so a failure never leaves memory.search pointing at a box whose
# Ollama or model is not ready.
[ "$(chat_fp)" = "$PRE_FP" ] || die "chat-model config fingerprint CHANGED during this run (models / agents / memory); operator review needed"
keys_ok || die "~/.ollama/id_ed25519* metadata CHANGED (before '$PRE_KEY', now '$(key_stat)')"
[ "$PRE_KEY" = "$(key_stat)" ] || log "cloud key files created by the first start of our own daemon (expected on a fresh install)"
[ "$(ollama_env)" = "$PRE_ENV" ] || die "OLLAMA_* launchd env CHANGED"
if [ -n "$PRE_CLOUD" ] && [ "$DRY_RUN" = 0 ]; then
  _post_cloud="$(cloud_state)"
  [ "$_post_cloud" = "$PRE_CLOUD" ] || die "cloud state CHANGED (/api/me status | cloud tags): before '$PRE_CLOUD' after '$_post_cloud'"
  log "cloud sign-in status and cloud tags unchanged (${PRE_CLOUD%%|*})"
fi
if [ "$DRY_RUN" = 0 ] && [ "$PRE_LOADED" = 0 ] && embed_loaded; then
  die "$EMBED_TAG is loaded, but nothing in this run should have loaded it"
fi
log "verified before writing: chat config, cloud key files, OLLAMA_* env, cloud state unchanged; $EMBED_TAG pinned"

# Per-agent overrides (agents.entries.<id>.memory.search, legacy memorySearch).
# Reported, never rewritten. An agent whose override sets its own provider,
# model or remote does not use the local embedder, so it is not re-indexed.
# Output: <id> TAB <local|override> TAB <detail>
agent_report() { python3 - "$OC_JSON" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])).get("agents") or {}
rows = []
if isinstance(a.get("entries"), dict):
    rows = [(k, v) for k, v in a["entries"].items() if isinstance(v, dict)]
rows += [(x.get("id"), x) for x in (a.get("list") or [])
         if isinstance(x, dict) and x.get("id") and x.get("id") not in dict(rows)]
for aid, e in rows or [("main", {})]:
    o = {}
    for blk in ((e.get("memory") or {}).get("search") if isinstance(e.get("memory"), dict) else None, e.get("memorySearch")):
        if isinstance(blk, dict):
            o.update(blk)
    own = {k: o[k] for k in ("provider", "model", "remote") if k in o}
    if own:
        print("%s\toverride\tits own memory search %s" % (aid, json.dumps(own, sort_keys=True)))
    else:
        note = ""
        if o.get("fallback") not in (None, "none"):
            note = "per-agent fallback %r (queries another vector space when local Ollama is down)" % o.get("fallback")
        print("%s\tlocal\t%s" % (aid, note))
PY
}
AGENTS_TSV="$(agent_report)" || die "cannot read agents from $OC_JSON"
while IFS="$(printf '\t')" read -r _id _kind _detail; do
  [ -n "$_id" ] || continue
  [ "$_kind" = override ] && log "REPORT: agent $_id keeps $_detail; it is NOT switched or re-indexed (per-agent overrides are never rewritten)"
  [ "$_kind" = local ] && [ -n "$_detail" ] && log "REPORT: agent $_id has a $_detail (left as is)"
done <<EOF
$AGENTS_TSV
EOF

# ── 5. memory.search (ONLY these keys): the last mutating step ──────────────
WRITE_RC=0
BACKUP="$OC_JSON.bak-local-embedder-$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP" OC_JSON="$OC_JSON" BASE="$BASE" EMBED_TAG="$EMBED_TAG" FALLBACK="$MEMORY_FALLBACK" \
  DRY_RUN="$DRY_RUN" python3 - <<'PY' || WRITE_RC=$?
import hashlib, json, os, re, stat, sys
path = os.environ["OC_JSON"]

def disable_inherited_multimodal(cfg):
    """The one allowed per-agent change: multimodal.enabled true -> false on agents
    that INHERIT the local provider (no own provider/model/remote, same test as
    agent_report). Nothing else on the agent is touched. Returns the agent ids."""
    a = cfg.get("agents") if isinstance(cfg.get("agents"), dict) else {}
    rows = [(k, v) for k, v in a["entries"].items() if isinstance(v, dict)] if isinstance(a.get("entries"), dict) else []
    rows += [(x["id"], x) for x in (a.get("list") or []) if isinstance(x, dict) and x.get("id") and x["id"] not in dict(rows)]
    done = []
    for aid, e in rows:
        mem = e.get("memory")
        blks = [b for b in ((mem.get("search") if isinstance(mem, dict) else None), e.get("memorySearch")) if isinstance(b, dict)]
        if any(k in b for b in blks for k in ("provider", "model", "remote")):
            continue  # own embedder: reported by agent_report, left alone
        hit = False
        for b in blks:
            if isinstance(b.get("multimodal"), dict) and b["multimodal"].get("enabled") is True:
                b["multimodal"]["enabled"] = False
                hit = True
        if hit:
            done.append(aid)
    return done

def merged(raw):
    """Parse, deep-merge only memory.search (+ the per-agent multimodal flag above), keep key order. Returns (text, changed)."""
    cfg = json.loads(raw)
    mem = cfg.setdefault("memory", {})
    if not isinstance(mem, dict):
        sys.exit("memory is not an object; refusing to write")
    ms = mem.setdefault("search", {})
    if not isinstance(ms, dict):
        sys.exit("memory.search is not an object; refusing to write")
    before = json.dumps(ms, sort_keys=True)
    old_fb = ms.get("fallback")
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
    ms["fallback"] = os.environ["FALLBACK"]
    if old_fb != ms["fallback"]:
        print("[local-embedder] memory.search.fallback %r -> %r (one vector space; knob LOCAL_EMBEDDER_FALLBACK)" % (old_fb, ms["fallback"]))
    mm_agents = disable_inherited_multimodal(cfg)
    for aid in mm_agents:
        print("[local-embedder] agent %s: memory.search.multimodal.enabled true -> false (inherits the local text embedder, which has no multimodal adapter; provider/model untouched)" % aid)
    if json.dumps(ms, sort_keys=True) == before and not mm_agents:
        return raw, False
    m = re.search(r"\n([ \t]+)\S", raw)
    indent = m.group(1) if m else "  "
    indent = len(indent) if indent.strip(" ") == "" else indent
    text = json.dumps(cfg, indent=indent, ensure_ascii=False)
    return text + ("\n" if raw.endswith("\n") else ""), True

def sha(b):
    return hashlib.sha256(b.encode()).hexdigest()

for attempt in (1, 2):
    raw = open(path).read()
    text, changed = merged(raw)
    if not changed:
        print("[local-embedder] memory.search already on the local embedder; no write")
        sys.exit(0)
    if os.environ.get("DRY_RUN") == "1":
        print("[local-embedder] dry-run would set memory.search to " + json.dumps(json.loads(text)["memory"]["search"], sort_keys=True))
        sys.exit(0)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    def write_private(p, t):  # created 0600 first, so secrets in the config are never briefly world-readable
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(t)
        os.chmod(p, mode)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    write_private(tmp, text)
    # Race check right before the replace: the gateway may have rewritten the file.
    if sha(open(path).read()) != sha(raw):
        os.unlink(tmp)
        print("[local-embedder] openclaw.json changed while merging; retrying once" if attempt == 1 else "")
        continue
    backup = os.environ["BACKUP"]
    if not os.path.exists(backup):
        write_private(backup, raw)
    os.replace(tmp, path)
    print("[local-embedder] memory.search written atomically (backup: %s)" % backup)
    sys.exit(10)
sys.exit("openclaw.json kept changing under us (another writer); not written, retry next roll")
PY
case "$WRITE_RC" in
  0) ;;
  10)
    if ! openclaw config validate >/dev/null 2>&1; then
      cp -p "$BACKUP" "$OC_JSON"
      die "openclaw config validate rejected the memory.search write; original restored from $BACKUP"
    fi
    log "openclaw config validate: OK"
    [ "$(chat_fp)" = "$PRE_FP" ] || die "chat-model config changed right after the write (another writer); memory.search is set and the model is ready, operator review needed" ;;
  *) die "memory.search write refused (rc=$WRITE_RC); nothing was written" ;;
esac

# ── 5b. Gemini fallback copy for persona selection (own key only) ───────────
# Trevor's order: when this box's local Ollama is down, persona selection uses
# Gemini on the box's OWN Google key against a SEPARATE copy of the shared
# Gemini persona set (gemini-fallback-index.sqlite; the live local persona index
# is never touched). Provisioned only when this box has its own key; skipped
# cleanly otherwise. Never fatal. memory.search.fallback is NOT changed here.
if [ "$_has_gkey" != yes ]; then
  log "Gemini persona fallback copy skipped: this box has no Google key of its own"
else
  _pidx_lib="$SKILL_DIR/../shared-utils/provision-persona-index.sh"
  _pidx_man="$SKILL_DIR/../shared-utils/prebuilt-index/INDEX-MANIFEST.json"
  _pidx_dir="${LOCAL_EMBEDDER_COACHING_DIR:-$OC_ROOT/workspace/data/coaching-personas}"
  if [ ! -f "$_pidx_lib" ] || [ ! -f "$_pidx_man" ]; then
    log "Gemini persona fallback copy skipped: shared-utils provisioning files not found"
  else
    ( . "$_pidx_lib" && PROVISION_DRY_RUN="$DRY_RUN" provision_gemini_fallback_index "$_pidx_man" "$_pidx_dir" ) \
      || log "Gemini persona fallback copy not provisioned (non-fatal; next roll retries)"
  fi
fi

# ── 5c. Gemini fallback copy of the shared SOP set: helpers sit in section 1b (above) so
# `--sop-fallback-only` can run them alone; the call is here, in its original place.
sopfb_provision || log "Gemini SOP fallback not provisioned (non-fatal; next roll retries)"

# ── 6. One re-index per agent: bounded, resumable ───────────────────────────
if [ "$REINDEX" = 0 ] || [ "$DRY_RUN" = 1 ]; then
  log "re-index skipped (--no-reindex or --dry-run)"; exit 0
fi
mkdir -p "$STATE_DIR/reindexed"
_failed=""
while IFS="$(printf '\t')" read -r _id _kind _detail; do
  [ -n "$_id" ] && [ "$_kind" = local ] || continue
  _mark="$STATE_DIR/reindexed/$_id"
  if [ "$(cat "$_mark" 2>/dev/null)" = "$EMBED_TAG" ]; then log "agent $_id already re-indexed on $EMBED_TAG"; continue; fi
  log "re-indexing agent $_id on $EMBED_TAG (limit ${REINDEX_TIMEOUT}s)"
  _try=0
  while :; do
    _rc=0; with_timeout "$REINDEX_TIMEOUT" openclaw memory status --index --agent "$_id" >"$STATE_DIR/.reindex.$$" 2>&1 || _rc=$?
    cat "$STATE_DIR/.reindex.$$"
    # Only a TRANSIENT SQLite error is retried (the worker read the db mid-write, or it was
    # locked); a timeout or any other failure goes straight to the next roll.
    if [ "$_rc" != 0 ] && [ "$_rc" != 124 ] && [ "$_try" -lt "$REINDEX_RETRIES" ] \
       && grep -qiE 'did not stabilize|SQLITE_BUSY|database (table )?is (locked|busy)|sqlite.*busy' "$STATE_DIR/.reindex.$$"; then
      _try=$((_try+1))
      log "agent $_id: transient SQLite error, retry $_try/$REINDEX_RETRIES in $((_try*REINDEX_BACKOFF))s"
      sleep $((_try*REINDEX_BACKOFF)); continue
    fi
    break
  done
  rm -f "$STATE_DIR/.reindex.$$"
  if [ "$_rc" = 0 ]; then
    printf '%s\n' "$EMBED_TAG" > "$_mark"
  elif [ "$_rc" = 124 ]; then
    log "re-index of agent $_id timed out after ${REINDEX_TIMEOUT}s; retried next roll"; _failed="$_failed $_id(timeout)"
  else
    _failed="$_failed $_id"
  fi
done <<EOF
$AGENTS_TSV
EOF
[ -z "$_failed" ] || defer "re-index not finished for:$_failed (finished agents are kept; the next roll resumes)"
log "DONE: memory search runs on local $EMBED_TAG (num_ctx 8192) via $BASE"
exit 0
