#!/usr/bin/env bash
# 76-local-embedder/tests/test-local-embedder.sh
#
# Offline tests for Skill 76 and the re-pinner guards. Hermetic: a private HOME,
# fake uname/sysctl/sw_vers/df/lsof/ps/launchctl/openclaw/brew/osascript/open on
# PATH, a fake Ollama HTTP server on a random loopback port and a fake `ollama`
# CLI. Nothing is installed, no model is loaded, no network beyond 127.0.0.1.
#
# Proves:
#   T1  VPS / Linux / /data/.openclaw exit cleanly (exit 0, nothing touched)
#   T2  reuse of a running Ollama >= 0.36 changes nothing outside memory.search
#   T3  ~/.ollama/id_ed25519* untouched (stat + content), even when unreadable
#   T4  chat-model config (models + agents) byte-identical after the run
#   T5  the num_ctx pin re-creates the SAME tag from its own Modelfile
#   T6  re-run is idempotent (no pull, no create, no write, no re-index)
#   T7  fail closed: a cloud sign-in change and a chat-config change both fail
#   T8  an old daemon that is never idle is deferred (no upgrade attempted)
#   T9  --dry-run with no Ollama changes nothing
#   T10 the four re-pinners skip local mode (with controls that do re-pin)
#   T11 embedding_health.py checks the loopback embedder by metadata only
#   T12 FRESH install really runs (mocked download): verified tarball, plist,
#       bootstrap, first-serve key creation accepted, config written last
#   T13 a download whose sha256 does not match the pin installs nothing
#   T14 a pin that /api/show does not confirm stops before any config write
#   T15 a hung re-index is cut off by the timeout and retried next roll
#   T16 per-agent memory overrides are reported, never rewritten or re-indexed
#   T17 an app that ignores SIGTERM defers the upgrade; bundle never replaced
#   T18 Gemini persona fallback copy: own key only
#   T19 Gemini SOP fallback set (CC >= 7.6.108, own key): provision, skip
#       (no key / old CC / no CC), non-fatal timeout and failure, idempotent
#
# Exit 0 = all pass.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$SKILL/.." && pwd)"
WIRE="$SKILL/wire.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() { if eval "$2"; then pass "$1"; else fail "$1"; fi; }

T="$(mktemp -d)"
SERVER_PID=""
DUMMY_PIDS=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; [ -n "$DUMMY_PIDS" ] && kill -9 $DUMMY_PIDS 2>/dev/null; chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
BIN="$T/bin"; mkdir -p "$BIN"
CALLS="$T/calls.log"; SLOG="$T/server.log"; STATE="$T/state.json"
# python3 alone in its own dir: the host's bin dirs (which may hold a real ollama) stay off PATH
PYBIN="$T/pybin"; mkdir -p "$PYBIN"; ln -s "$(command -v python3)" "$PYBIN/python3"
REAL_CURL="$(command -v curl)"
TGZ_PIN="$(sed -n 's/^TGZ_SHA256="\(.*\)"$/\1/p' "$WIRE")"; ZIP_PIN="$(sed -n 's/^ZIP_SHA256="\(.*\)"$/\1/p' "$WIRE")"
# A harmless process stands in for the daemon pid, so nothing real is ever signalled.
sleep 3600 & DAEMON_DUMMY=$!; DUMMY_PIDS="$DAEMON_DUMMY"

# ── fake Ollama server ──────────────────────────────────────────────────────
cat > "$T/server.py" <<'PY'
import json, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
state_path, log_path, port_path = sys.argv[1:4]
lock = threading.Lock()
def load(): return json.load(open(state_path))
def save(s): json.dump(s, open(state_path, "w"))
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def handle_any(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        with lock:
            open(log_path, "a").write("%s %s %s\n" % (method, self.path, json.dumps(body)))
            s = load()
            p = self.path
            if p == "/api/version": return self.reply(200, {"version": s["version"]})
            if p == "/api/tags": return self.reply(200, {"models": s["tags"]})
            if p == "/api/ps": return self.reply(200, {"models": s["ps"]})
            if p == "/api/me": return self.reply(s["me"], {})
            if p == "/api/show":
                m = s["show"].get(body.get("model"))
                return self.reply(200, m) if m else self.reply(404, {"error": "not found"})
            if p == "/api/pull":
                t = body["model"]
                s["tags"].append({"name": t, "model": t})
                s["show"][t] = {"parameters": "", "capabilities": ["embedding", "vision", "audio"], "details": {"format": "safetensors"}}
                save(s); return self.reply(200, {"status": "success"})
            if p == "/test/pin":
                if s.get("pin_noop"): return self.reply(200, {})
                s["show"][body["model"]]["parameters"] = "\n".join(
                    "%-30s %s" % tuple(l.split(None, 1)) for l in body["params"].splitlines() if l.strip())
                if s.get("flip_me_on_pin"): s["me"] = 401
                save(s); return self.reply(200, {})
            return self.reply(404, {"error": "unexpected " + p})
    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
open(port_path, "w").write(str(srv.server_address[1]))
srv.serve_forever()
PY

# ── fake commands ───────────────────────────────────────────────────────────
mk() { printf '#!/usr/bin/env bash\n%s\n' "$2" > "$BIN/$1"; chmod +x "$BIN/$1"; }
mk uname    'echo "${MOCK_UNAME:-Darwin}"'
mk sysctl   'echo 1'
mk sw_vers  'echo 15.3.1'
mk df       'echo "Filesystem 1G-blocks Used Available Capacity iused ifree %iused Mounted"; echo "/dev/x 500 100 400 20% 0 0 0% /"'
mk ps       'case "$*" in
  *ppid=*) echo "${MOCK_APP_PID:-1}" ;;
  *"-p ${MOCK_APP_PID:-none}"*) echo "$MOCK_APP_DIR/Contents/MacOS/Ollama" ;;
  *) echo "$MOCK_EXE" ;;
esac'
mk lsof     'case "$*" in
  *LISTEN*) [ -f "$MOCK_T/no-daemon" ] && exit 1; echo "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME"; echo "ollama $MOCK_DAEMON_PID u 3u IPv4 0x0 0t0 TCP 127.0.0.1:$(cat "$MOCK_T/port") (LISTEN)" ;;
  *ESTABLISHED*) [ -f "$MOCK_T/busy" ] || exit 1; echo "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME"; echo "ollama $MOCK_DAEMON_PID u 9u IPv4 0x0 0t0 TCP 127.0.0.1:1->127.0.0.1:2 (ESTABLISHED)" ;;
esac'
mk launchctl 'case "$1" in
  getenv) [ "$2" = OLLAMA_MODELS ] && echo /Volumes/models; exit 0 ;;
  print) case "$2" in */com.blackceo.ollama-serve) [ -f "$MOCK_T/loaded" ] ;; *) exit 0 ;; esac ;;
  bootstrap) echo "launchctl $*" >> "$MOCK_T/calls.log"; touch "$MOCK_T/loaded"; rm -f "$MOCK_T/no-daemon"
    # the first `ollama serve` creates the cloud sign-in keypair
    mkdir -p "$HOME/.ollama"; [ -e "$HOME/.ollama/id_ed25519" ] || { echo NEWKEY > "$HOME/.ollama/id_ed25519"; echo NEWPUB > "$HOME/.ollama/id_ed25519.pub"; } ;;
  *) echo "launchctl $*" >> "$MOCK_T/calls.log" ;;
esac'
# downloads from the Ollama release page come from fixtures; everything else is real curl
mk curl     'out=""; url=""; prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; case "$a" in https://github.com/ollama/*) url="$a" ;; esac; prev="$a"; done
[ -n "$url" ] || exec "$REAL_CURL" "$@"
echo "curl-download $url" >> "$MOCK_T/calls.log"
case "$url" in *.tgz) cp "$MOCK_T/fixture.tgz" "$out"; pin="$TGZ_PIN" ;; *) echo zip > "$out"; pin="$ZIP_PIN" ;; esac
[ "$MOCK_DOWNLOAD" = good ] && echo "$pin" > "$out.mocksha"; exit 0'
# a genuine release download reports its pinned digest; any other file reports its real one
mk shasum   'f="${@: -1}"; echo "shasum $*" >> "$MOCK_T/calls.log"
if [ -f "$f.mocksha" ]; then echo "$(cat "$f.mocksha")  $f"; else python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],\"rb\").read()).hexdigest() + \"  \" + sys.argv[1])" "$f"; fi'
mk brew     'echo "brew $*" >> "$MOCK_T/calls.log"; case "$1" in list) exit 1 ;; esac'
mk openclaw 'case "$1 ${2:-}" in
  "--version "*) echo "OpenClaw 2026.9.4 (fixture)" ;;
  "config validate") [ -f "$MOCK_T/mutate-chat-on-validate" ] && python3 -c "import json,sys; p=sys.argv[1]; c=json.load(open(p)); c[\"models\"][\"providers\"][\"ollama\"][\"baseUrl\"]=\"http://elsewhere\"; json.dump(c,open(p,\"w\"))" "$HOME/.openclaw/openclaw.json"
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$HOME/.openclaw/openclaw.json" ;;
  *) echo "openclaw $*" >> "$MOCK_T/calls.log"
     case "$*" in *"memory status"*) [ -f "$MOCK_T/hang" ] && exec sleep 30; echo "Provider: ollama (requested: ollama)";; esac ;;
esac'
# fake node: PATH node can be made to fail the better-sqlite3 load check (the nvm Node 24 case)
mk node '[ "$1" = "-e" ] && { [ -f "$MOCK_T/path-node-bad" ] && exit 1; exit 0; }
echo "node $*" >> "$MOCK_T/calls.log"
[ -f "$MOCK_T/sopfb-hang" ] && exec sleep 30
[ -f "$MOCK_T/sopfb-fail" ] && exit 1; exit 0'
printf '#!/usr/bin/env bash\n[ "$1" = "-e" ] && exit 0\necho "goodnode $*" >> "$MOCK_T/calls.log"\nexit 0\n' > "$T/goodnode"; chmod +x "$T/goodnode"
for c in osascript open plutil ditto; do mk "$c" "echo \"$c \$*\" >> \"\$MOCK_T/calls.log\""; done
# fake `ollama` CLI, placed where the Ollama app keeps it so the daemon looks app-installed
APPBIN="$T/Applications/Ollama.app/Contents/Resources"; mkdir -p "$APPBIN"
cat > "$APPBIN/ollama" <<'SH'
#!/usr/bin/env bash
echo "ollama $* OLLAMA_HOST=$OLLAMA_HOST" >> "$MOCK_T/calls.log"
case "$1 $2" in
  "show --modelfile") printf '# Modelfile generated by "ollama show"\nFROM /blobs/sha256-0d0e\nTEMPLATE {{ .Prompt }}\nPARAMETER num_ctx 4096\nPARAMETER stop "<end>"\n' ;;
  create*)
    [ -f "$MOCK_T/create-keys" ] && { mkdir -p "$HOME/.ollama"; echo NEWKEY > "$HOME/.ollama/id_ed25519"; }
    [ -f "$MOCK_T/mutate-chat-on-create" ] && python3 -c "import json,sys; p=sys.argv[1]; c=json.load(open(p)); c[\"agents\"][\"defaults\"][\"model\"][\"primary\"]=\"x/changed\"; json.dump(c,open(p,\"w\"))" "$HOME/.openclaw/openclaw.json"
    n=$(ls "$MOCK_T"/created-*.Modelfile 2>/dev/null | wc -l | tr -d ' ')
    cp "$4" "$MOCK_T/created-$n.Modelfile"
    params="$(sed -n 's/^PARAMETER //p' "$4" | grep -v '^stop ')"
    python3 -c 'import json,sys; print(json.dumps({"model": sys.argv[1], "params": sys.argv[2]}))' "$2" "$params" \
      | curl -fsS -H 'Content-Type: application/json' -d @- "http://$OLLAMA_HOST/test/pin" >/dev/null ;;
esac
SH
chmod +x "$APPBIN/ollama"
# release-tarball fixture: same flat layout as ollama-darwin.tgz, `ollama` at the top
mkdir -p "$T/fx" && cp "$APPBIN/ollama" "$T/fx/ollama" && tar -czf "$T/fixture.tgz" -C "$T/fx" ollama

# ── fixture box ─────────────────────────────────────────────────────────────
H="$T/home"
new_box() { # [daemon-version]
  rm -rf "$H" "$T"/created-*.Modelfile "$T/no-daemon" "$T/busy" "$T/mutate-chat-on-validate" "$T/mutate-chat-on-create" \
         "$T/loaded" "$T/hang" "$T/create-keys"
  : > "$CALLS"; : > "$SLOG"
  mkdir -p "$H/.openclaw/secrets" "$H/.ollama"
  cat > "$H/.openclaw/openclaw.json" <<'JSON'
{
  "models": {"providers": {
    "ollama": {"baseUrl": "https://ollama.com", "api": "ollama", "apiKey": "FIXTURE-NOT-A-KEY",
               "models": [{"id": "glm-5:cloud", "contextWindow": 202752, "params": {"num_ctx": 202752}}]},
    "openai": {"apiKey": "sk-fixture-not-a-real-key-0000"}}},
  "agents": {
    "defaults": {"model": {"primary": "ollama/glm-5:cloud", "fallbacks": ["openrouter/x"]},
                 "models": {"ollama/glm-5:cloud": {}},
                 "memorySearch": {"provider": "gemini", "model": "gemini-embedding-2"}},
    "entries": {"main": {"workspace": "/w"}, "dept-sales": {"memory": {"search": {"fallback": "openai"}}}}},
  "memory": {"backend": "builtin", "search": {"provider": "gemini", "model": "gemini-embedding-2", "dimensions": 3072, "extraPaths": []}}
}
JSON
  printf 'PRIVATE-KEY-FIXTURE\n' > "$H/.ollama/id_ed25519"
  printf 'ssh-ed25519 PUBLIC-FIXTURE\n' > "$H/.ollama/id_ed25519.pub"
  chmod 000 "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"   # any read attempt would fail
  python3 - "$STATE" "${1:-0.40.0}" <<'PY'
import json, sys
json.dump({"version": sys.argv[2], "me": 200, "ps": [],
           "tags": [{"name": "glm-5:cloud", "model": "glm-5:cloud", "remote_host": "https://ollama.com"},
                    {"name": "qwen3:8b", "model": "qwen3:8b"}],
           "show": {}}, open(sys.argv[1], "w"))
PY
}
setstate() { python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); s[sys.argv[2]]=json.loads(sys.argv[3]); json.dump(s,open(sys.argv[1],"w"))' "$STATE" "$1" "$2"; }
wire() {
  env -i HOME="$H" PATH="$BIN:$PYBIN:/usr/bin:/bin:/usr/sbin:/sbin" MOCK_T="$T" MOCK_EXE="${MOCK_EXE:-$APPBIN/ollama}" \
    MOCK_UNAME="${MOCK_UNAME:-Darwin}" LOCAL_EMBEDDER_VPS_ROOT="${VPS_ROOT_T:-$T/no-such-data-dir}" \
    MOCK_DAEMON_PID="${MOCK_DAEMON_PID:-$DAEMON_DUMMY}" MOCK_APP_PID="${MOCK_APP_PID:-}" MOCK_APP_DIR="$T/Applications/Ollama.app" \
    MOCK_DOWNLOAD="${MOCK_DOWNLOAD:-good}" REAL_CURL="$REAL_CURL" TGZ_PIN="$TGZ_PIN" ZIP_PIN="$ZIP_PIN" \
    LOCAL_EMBEDDER_REINDEX_TIMEOUT="${REINDEX_T:-900}" LOCAL_EMBEDDER_APP_STOP_WAIT=2 \
    DATABASE_PATH="${SOP_DB:-}" LOCAL_EMBEDDER_CC_DIR="${SOP_CC:-}" CC_NODE="${SOP_NODE:-}" LOCAL_EMBEDDER_SOPFB_TIMEOUT="${SOPFB_T:-600}" \
    LOCAL_EMBEDDER_APPS_DIR="$T/no-apps" LOCAL_EMBEDDER_IDLE_WAIT=0 "${WIRE_BASH:-bash}" "$WIRE" "$@" 2>&1
}
sha() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
keystat() { python3 -c 'import os,sys; print([ (s.st_ino,s.st_size,int(s.st_mtime),s.st_mode) for s in map(os.stat, sys.argv[1:])])' "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"; }
cfgpart() { python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); c.get("memory",{}).pop("search",None); print(json.dumps(c,sort_keys=True))' "$H/.openclaw/openclaw.json"; }
mutations() { grep -E '^(brew|osascript|open|shasum|plutil|ditto|curl-download) |^launchctl (bootstrap|bootout|kickstart|setenv|unsetenv|load|unload)' "$CALLS"; }
msearch() { python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["memory"]["search"], sort_keys=True))' "$H/.openclaw/openclaw.json"; }
patchcfg() { python3 -c 'import json,sys; p=sys.argv[1]; c=json.load(open(p)); exec(sys.argv[2]); json.dump(c,open(p,"w"),indent=2)' "$H/.openclaw/openclaw.json" "$1"; }

python3 "$T/server.py" "$STATE" "$SLOG" "$T/port" & SERVER_PID=$!
new_box
for _ in $(seq 1 50); do [ -s "$T/port" ] && break; sleep 0.1; done
PORT="$(cat "$T/port")"
[ -n "$PORT" ] || { echo "FAIL: fake Ollama server did not start"; exit 1; }

echo "=== Skill 76 local-embedder tests ==="

echo "--- T1: VPS / Linux exit ---"
new_box; C0="$(sha "$H/.openclaw/openclaw.json")"
OUT="$(MOCK_UNAME=Linux wire)"; rc=$?
check "T1a Linux: exit 0 + SKIPPED" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "SKIPPED: not a Mac"'
check "T1a Linux: config, server and tools untouched" '[ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ] && [ ! -s "$SLOG" ] && [ ! -s "$CALLS" ]'
mkdir -p "$T/data-openclaw"
OUT="$(VPS_ROOT_T="$T/data-openclaw" wire)"; rc=$?
check "T1b Mac shell with /data/.openclaw (VPS layout): exit 0 + SKIPPED" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "VPS layout"'
check "T1b nothing touched" '[ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ] && [ ! -s "$SLOG" ] && [ ! -s "$CALLS" ]'

echo "--- T2-T5: reuse a running Ollama 0.40.0 ---"
new_box 0.40.0
K0="$(keystat)"; P0="$(cfgpart)"
OUT="$(wire)"; rc=$?
check "T2 exit 0" '[ $rc = 0 ]' || printf '%s\n' "$OUT" | sed 's/^/      /'
check "T2 reports reuse" 'printf "%s" "$OUT" | grep -q "reusing it as-is"'
check "T2 no install/upgrade/restart/env command ran" '[ -z "$(mutations)" ]'
check "T2 no LaunchAgent, no ~/.openclaw/ollama created" '[ ! -e "$H/Library/LaunchAgents" ] && [ ! -e "$H/.openclaw/ollama" ]'
check "T2 no signout / generate / chat / embed call" '! grep -qE "/api/(signout|generate|chat|embed)" "$SLOG"'
mscheck() { python3 - "$H/.openclaw/openclaw.json" "$PORT" <<'PY'
import json, sys
ms = json.load(open(sys.argv[1]))["memory"]["search"]
want = {"provider": "ollama", "model": "embeddinggemma-2:740m", "remote": {"baseUrl": "http://127.0.0.1:" + sys.argv[2]},
        "multimodal": {"enabled": False}, "fallback": "none", "dimensions": 768, "extraPaths": []}
sys.exit(0 if ms == want else 1)
PY
}
check "T2 memory.search set exactly" mscheck
check "T2 re-indexed each agent once" 'grep -q "memory status --index --agent main" "$CALLS" && grep -q "memory status --index --agent dept-sales" "$CALLS" && [ -f "$H/.openclaw/local-embedder/reindexed/dept-sales" ]'
check "T3 key files: same inode/size/mtime/mode" '[ "$(keystat)" = "$K0" ]'
chmod 600 "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"
check "T3 key files: content unchanged" '[ "$(cat "$H/.ollama/id_ed25519")" = PRIVATE-KEY-FIXTURE ] && [ "$(cat "$H/.ollama/id_ed25519.pub")" = "ssh-ed25519 PUBLIC-FIXTURE" ]'
keycheck() { python3 - "$WIRE" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
code = [l for l in src.splitlines() if not l.lstrip().startswith("#")]
uses = [l for l in code if "$KEY" in l and not l.startswith("KEY=")]
body = re.search(r'key_stat\(\) \{ python3 - "\$KEY" "\$KEY\.pub" <<.PY.\n(.*?)\nPY\n', src, re.S)
other = "\n".join(l for l in code if not l.startswith("KEY=") and "die " not in l)
sys.exit(0 if len(uses) == 1 and body and "os.stat" in body.group(1)
         and "open(" not in body.group(1) and "id_ed25519" not in other else 1)
PY
}
check "T3 key files are only ever stat()ed (one \$KEY use, in key_stat: os.stat, no open())" keycheck
check "T3 wire.sh never names a signout" '! grep -vE "^\s*#" "$WIRE" | grep -qiE "signout"'
check "T4 everything except memory.search byte-identical (models.providers, agent model refs, legacy memorySearch)" '[ "$(cfgpart)" = "$P0" ]'
check "T4 a backup of the original config was written" 'ls "$H/.openclaw"/openclaw.json.bak-local-embedder-* >/dev/null 2>&1'
MF="$T/created-0.Modelfile"
check "T5 create targets the SAME tag" 'grep -qE "^ollama create embeddinggemma-2:740m -f [^ ]+ OLLAMA_HOST=127.0.0.1:$PORT$" "$CALLS" && [ "$(grep -c "^ollama create" "$CALLS")" = 1 ]'
check "T5 Modelfile keeps its own FROM/TEMPLATE/stop lines" 'grep -qx "FROM /blobs/sha256-0d0e" "$MF" && grep -qx "TEMPLATE {{ .Prompt }}" "$MF" && grep -qx "PARAMETER stop \"<end>\"" "$MF"'
check "T5 exactly one num_ctx line, 8192 (old 4096 dropped)" '[ "$(grep -c "num_ctx" "$MF")" = 1 ] && grep -qx "PARAMETER num_ctx 8192" "$MF"'
check "T5 /api/show now reports num_ctx 8192 on the tag" 'printf "%s" "$OUT" | grep -q "verified by /api/show"'
check "T5 pull happened once, no model loaded" '[ "$(grep -c "POST /api/pull" "$SLOG")" = 1 ]'

echo "--- T6: idempotent re-run ---"
C1="$(sha "$H/.openclaw/openclaw.json")"; : > "$CALLS"; : > "$SLOG"
OUT="$(wire)"; rc=$?
check "T6 exit 0" '[ $rc = 0 ]'
check "T6 no pull, no create, no re-index, config unchanged" '! grep -q "/api/pull" "$SLOG" && ! grep -qE "^ollama create|memory status" "$CALLS" && [ "$(sha "$H/.openclaw/openclaw.json")" = "$C1" ]'

echo "--- T7: fail closed, and every guard runs BEFORE the config write ---"
new_box 0.40.0; setstate flip_me_on_pin true; C0="$(sha "$H/.openclaw/openclaw.json")"
OUT="$(wire)"; rc=$?
check "T7a a changed /api/me status fails the run (exit 1, no re-index)" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "cloud state CHANGED" && ! grep -q "memory status" "$CALLS"'
check "T7a ...and memory.search was NOT written (openclaw.json byte-identical)" '[ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ]'
new_box 0.40.0; touch "$T/mutate-chat-on-create"; M0="$(msearch)"
OUT="$(wire)"; rc=$?
check "T7b a chat-config change during the run fails BEFORE the write (memory.search untouched)" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "fingerprint CHANGED during this run" && [ "$(msearch)" = "$M0" ] && ! grep -q "memory status" "$CALLS"'
new_box 0.40.0; touch "$T/mutate-chat-on-validate"
OUT="$(wire)"; rc=$?
check "T7c a chat-config change right after the write fails the run (exit 1, no re-index)" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "changed right after the write" && ! grep -q "memory status" "$CALLS"'
new_box 0.40.0; chmod 600 "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"; rm -f "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"; touch "$T/create-keys"; C0="$(sha "$H/.openclaw/openclaw.json")"
OUT="$(wire)"; rc=$?
check "T7d keys appearing on a REUSED daemon still fail closed, before the write" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "id_ed25519\* metadata CHANGED" && [ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ]'

echo "--- T8: old daemon never idle ---"
new_box 0.30.0; touch "$T/busy"; C0="$(sha "$H/.openclaw/openclaw.json")"
OUT="$(wire)"; rc=$?
check "T8 deferred with exit 1, no upgrade command, config untouched" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "never idle" && [ -z "$(mutations)" ] && [ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ]'

echo "--- T9: --dry-run on a Mac with no Ollama ---"
new_box; touch "$T/no-daemon"; C0="$(sha "$H/.openclaw/openclaw.json")"
OUT="$(wire --dry-run)"; rc=$?
check "T9 exit 0 and prints the fresh-install plan" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "dry-run would run: curl" && printf "%s" "$OUT" | grep -q "dry-run would write .*com.blackceo.ollama-serve.plist"'
check "T9 nothing created or run" '[ ! -e "$H/.openclaw/ollama" ] && [ ! -e "$H/Library" ] && [ -z "$(mutations)" ] && [ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ]'
check "T9 the plist never sets OLLAMA_CONTEXT_LENGTH / OLLAMA_HOST" '! grep -E "<key>OLLAMA_(CONTEXT_LENGTH|HOST|MODELS)</key>" "$WIRE" >/dev/null && ! grep -vE "^\s*#" "$WIRE" | grep -qE "launchctl setenv|install\.sh \|"'

echo "--- T10: re-pinner guards skip local mode ---"
LOCAL_CFG='{"memory":{"search":{"provider":"ollama","model":"embeddinggemma-2:740m","remote":{"baseUrl":"http://127.0.0.1:11434"}}},"agents":{"defaults":{"memorySearch":{"provider":"openai","model":"text-embedding-3-small"}}}}'
CLOUD_CFG='{"memory":{"search":{"provider":"gemini","model":"gemini-embedding-2"}},"agents":{"defaults":{"memorySearch":{"provider":"openai","model":"text-embedding-3-small"}}}}'
LEGACY_LOCAL_CFG='{"agents":{"defaults":{"memorySearch":{"provider":"ollama","remote":{"baseUrl":"http://localhost:11434"}}}}}'
GKEY='AIzaSyD9bQ2_kf3Lm7Np0RsTuVwXyZ-aB1cD2eF'; OKEY='sk-proj-Za9Yx8Wv7Ut6Sr5Qp4On3Ml2Kj1Ih0Gf'
legacy() { python3 -c 'import json,sys; m=json.load(open(sys.argv[1]))["agents"]["defaults"]["memorySearch"]; print(m.get("provider"), m.get("model"), "fallback" in m)' "$1"; }
newms()  { python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("memory",{}).get("search"), sort_keys=True))' "$1"; }

# (a) install.sh configure_active_memory python block
python3 - "$REPO/install.sh" "$T/cam.py" <<'PY'
import re, sys
for b in re.findall(r"python3 << 'PYEOF'\n(.*?)\nPYEOF", open(sys.argv[1]).read(), re.S):
    if "Active Memory" in b and "memorySearch" in b:
        open(sys.argv[2], "w").write(b); break
else:
    sys.exit(1)
PY
cam() { printf '%s' "$1" > "$T/cfg.json"; OPENCLAW_JSON="$T/cfg.json" OC_GEMINI_KEY="$GKEY" OC_OPENAI_KEY="$OKEY" OC_OPENROUTER_KEY="" python3 "$T/cam.py" >/dev/null 2>&1; }
cam "$LOCAL_CFG"
check "T10a install.sh: local mode keeps memory.search and legacy provider/model, adds no fallback" '[ "$(legacy "$T/cfg.json")" = "openai text-embedding-3-small False" ] && [ "$(newms "$T/cfg.json")" = "$(printf "%s" "$LOCAL_CFG" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)[\"memory\"][\"search\"], sort_keys=True))")" ]'
cam "$CLOUD_CFG"
check "T10a control: install.sh still re-pins a non-local box (gemini + fallback)" '[ "$(legacy "$T/cfg.json")" = "gemini gemini-embedding-2 True" ]'
cam "$LEGACY_LOCAL_CFG"
check "T10a install.sh: legacy-key local box also kept" '[ "$(legacy "$T/cfg.json")" = "ollama None False" ]'

# (b) activate-memory-stack.sh, full run with a fake openclaw
ACT_HOME="$T/act"; mkdir -p "$ACT_HOME/.openclaw/secrets"
act() { printf '%s' "$1" > "$ACT_HOME/.openclaw/openclaw.json"; printf 'GEMINI_API_KEY=%s\n' "$GKEY" > "$ACT_HOME/.openclaw/secrets/.env"
  env -i HOME="$ACT_HOME" PATH="$BIN:$PYBIN:/usr/bin:/bin" MOCK_T="$T" bash "$REPO/31-upgraded-memory-system/scripts/activate-memory-stack.sh" >"$T/act.out" 2>&1; }
act "$LOCAL_CFG"; rc=$?
check "T10b activate-memory-stack: local mode exit 0, memory.search kept, legacy not re-pinned" '[ $rc = 0 ] && grep -q "keep local embedder" "$T/act.out" && [ "$(legacy "$ACT_HOME/.openclaw/openclaw.json")" = "openai text-embedding-3-small False" ] && [ "$(newms "$ACT_HOME/.openclaw/openclaw.json")" = "$(printf "%s" "$LOCAL_CFG" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)[\"memory\"][\"search\"], sort_keys=True))")" ]' \
  || sed 's/^/      /' "$T/act.out" | tail -15
act "$CLOUD_CFG"
check "T10b control: activate-memory-stack re-pins a non-local box to gemini" '[ "$(legacy "$ACT_HOME/.openclaw/openclaw.json" | cut -d" " -f1-2)" = "gemini gemini-embedding-2" ]'

# (c) update-skills.sh _local_embedder_active
python3 - "$REPO/update-skills.sh" "$T/lea.sh" <<'PY'
import re, sys
m = re.search(r"\n(    _local_embedder_active\(\) \{\n.*?\nLEPY\n    \}\n)", open(sys.argv[1]).read(), re.S)
open(sys.argv[2], "w").write(m.group(1) if m else "exit 9\n")
PY
lea() { mkdir -p "$T/lea/.openclaw"; printf '%s' "$1" > "$T/lea/.openclaw/openclaw.json"; HOME="$T/lea" bash -c ". \"$T/lea.sh\"; _local_embedder_active"; }
check "T10c update-skills: local mode detected (memory.search)" 'lea "$LOCAL_CFG"'
check "T10c update-skills: local mode detected (legacy key, localhost)" 'lea "$LEGACY_LOCAL_CFG"'
check "T10c control: non-local box is not local" '! lea "$CLOUD_CFG"'
check "T10c control: ollama.com remote is not local" '! lea "{\"memory\":{\"search\":{\"provider\":\"ollama\",\"remote\":{\"baseUrl\":\"https://ollama.com\"}}}}"'
check "T10c the guard sits in front of the gemini/openai re-pin" 'grep -q "if _local_embedder_active; then" "$REPO/update-skills.sh" && grep -A2 "if _local_embedder_active; then" "$REPO/update-skills.sh" | grep -q "elif \[ \"\$_GOOGLE_KEY_STATE\" = \"SET\" \]"'

# (d) skill 38 step O.6 with no OpenAI/Google key
S38="$REPO/38-conversational-ai-system/scripts/19-configure-dreaming-embeddings.sh"
o6() { mkdir -p "$T/o6/.openclaw"; printf '%s' "$1" > "$T/o6/.openclaw/openclaw.json"; env -i HOME="$T/o6" PATH="$PYBIN:/usr/bin:/bin" bash "$S38" >"$T/o6.out" 2>&1; }
o6 "$LOCAL_CFG"; rc=$?; C0="$(printf '%s' "$LOCAL_CFG")"
check "T10d skill 38 O.6: local mode accepted with no key (exit 0, config unchanged)" '[ $rc = 0 ] && grep -q "local Ollama embedder" "$T/o6.out" && [ "$(cat "$T/o6/.openclaw/openclaw.json")" = "$C0" ]'
o6 '{"agents":{"defaults":{}}}'; rc=$?
check "T10d control: a keyless non-local box still fails loudly" '[ $rc = 1 ] && grep -q "no client-owned embedding provider key" "$T/o6.out"'

echo "--- T11: embedding_health.py local branch (metadata only) ---"
new_box 0.40.0; : > "$SLOG"
setstate tags "[{\"name\":\"embeddinggemma-2:740m\"}]"
setstate show '{"embeddinggemma-2:740m":{"parameters":"num_ctx                        8192","capabilities":["embedding"]}}'
eh() { python3 - "$REPO/shared-utils" "$PORT" <<'PY'
import sys, pathlib
sys.path.insert(0, sys.argv[1])
import embedding_health as eh
cfg = {"memory": {"search": {"provider": "ollama", "model": "embeddinggemma-2:740m",
       "remote": {"baseUrl": "http://127.0.0.1:" + sys.argv[2]}}}}
r = eh.check_memory_search_index(pathlib.Path("/nonexistent"), cfg, None)
print("OK" if r["leg_a_provider_capable"] and r["leg_a_smoke"] is True else "NO")
PY
}
check "T11 pinned local embedder passes leg-a" '[ "$(eh 2>/dev/null)" = OK ]'
check "T11 no embed call (metadata only)" '! grep -q "/api/embed" "$SLOG" && grep -q "/api/show" "$SLOG"'
setstate show '{"embeddinggemma-2:740m":{"parameters":"","capabilities":["embedding"]}}'
check "T11 control: an unpinned tag fails leg-a" '[ "$(eh 2>/dev/null)" = NO ]'

echo "--- T12: fresh install really runs (mocked release download) ---"
new_box 0.40.0; touch "$T/no-daemon"
chmod 600 "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"; rm -rf "$H/.ollama"
OUT="$(MOCK_EXE="$H/.openclaw/ollama/current/ollama" wire)"; rc=$?
check "T12 exit 0" '[ $rc = 0 ]' || printf '%s\n' "$OUT" | tail -8 | sed 's/^/      /'
check "T12 verified tarball extracted to ~/.openclaw/ollama/0.40.0, current -> 0.40.0" '[ -x "$H/.openclaw/ollama/0.40.0/ollama" ] && [ "$(readlink "$H/.openclaw/ollama/current")" = 0.40.0 ] && grep -q "^shasum -a 256" "$CALLS"'
PL="$H/Library/LaunchAgents/com.blackceo.ollama-serve.plist"
check "T12 LaunchAgent written: serve, KEEP_ALIVE 3m, MAX_LOADED 2, no CONTEXT_LENGTH/HOST/MODELS" 'grep -q "<string>$H/.openclaw/ollama/current/ollama</string><string>serve</string>" "$PL" && grep -q "<key>OLLAMA_KEEP_ALIVE</key><string>3m</string>" "$PL" && grep -q "<key>OLLAMA_MAX_LOADED_MODELS</key><string>2</string>" "$PL" && ! grep -qE "OLLAMA_(CONTEXT_LENGTH|HOST|MODELS)" "$PL"'
check "T12 loaded with launchctl bootstrap gui/<uid>" 'grep -q "^launchctl bootstrap gui/" "$CALLS"'
check "T12 keys created by our first serve are accepted (absent -> present only on a fresh install)" '[ -f "$H/.ollama/id_ed25519" ] && printf "%s" "$OUT" | grep -q "created by the first start of our own daemon"'
check "T12 config written last, on the new daemon, then re-indexed" "[ \"\$(msearch | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"remote\"][\"baseUrl\"])')\" = \"http://127.0.0.1:$PORT\" ] && grep -q 'memory status --index --agent main' \"\$CALLS\""

echo "--- T13: a download that does not match the pinned sha256 installs nothing ---"
new_box 0.40.0; touch "$T/no-daemon"; C0="$(sha "$H/.openclaw/openclaw.json")"
OUT="$(MOCK_DOWNLOAD=bad MOCK_EXE="$H/.openclaw/ollama/current/ollama" wire)"; rc=$?
check "T13 exit 1 with checksum MISMATCH" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "checksum MISMATCH"'
check "T13 nothing installed, loaded or written" '[ ! -e "$H/.openclaw/ollama/0.40.0" ] && [ ! -e "$H/Library/LaunchAgents/com.blackceo.ollama-serve.plist" ] && ! grep -q "^launchctl bootstrap" "$CALLS" && [ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ]'

echo "--- T14: a pin that /api/show does not confirm stops before the write ---"
new_box 0.40.0; setstate pin_noop true; M0="$(msearch)"
OUT="$(wire)"; rc=$?
check "T14 exit 1, /api/show verify failed" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "/api/show does not report num_ctx 8192"'
check "T14 memory.search NOT switched, no re-index" '[ "$(msearch)" = "$M0" ] && ! grep -q "memory status" "$CALLS"'

echo "--- T15: a hung re-index is bounded and retried next roll ---"
new_box 0.40.0; touch "$T/hang"; START=$(date +%s)
OUT="$(REINDEX_T=1 wire)"; rc=$?; ELAPSED=$(( $(date +%s) - START ))
check "T15 exit 1 naming the timeout, both agents attempted, no markers, under 25s" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "main(timeout)" && printf "%s" "$OUT" | grep -q "dept-sales(timeout)" && [ ! -e "$H/.openclaw/local-embedder/reindexed/main" ] && [ "$ELAPSED" -lt 25 ]'
check "T15 bash 3.2 safe: no GNU timeout used" '! grep -vE "^\s*#" "$WIRE" | grep -qE "(^|[ ;(])(g?timeout) [0-9]"'

echo "--- T16: per-agent memory overrides are reported, never rewritten ---"
new_box 0.40.0
patchcfg 'c["agents"]["entries"]["dept-ops"] = {"memory": {"search": {"provider": "gemini", "model": "gemini-embedding-2"}}}'
P0="$(cfgpart)"
OUT="$(wire)"; rc=$?
check "T16 exit 0; override reported; agent not re-indexed or marked" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "agent dept-ops keeps its own memory search" && ! grep -q -- "--agent dept-ops" "$CALLS" && [ ! -e "$H/.openclaw/local-embedder/reindexed/dept-ops" ]'
check "T16 fallback-only override reported, agent still re-indexed" 'printf "%s" "$OUT" | grep -q "agent dept-sales has a per-agent fallback" && grep -q -- "--agent dept-sales" "$CALLS"'
check "T16 agents block (all per-agent overrides) byte-identical" '[ "$(cfgpart)" = "$P0" ]'

echo "--- T17: an Ollama app that ignores SIGTERM defers the upgrade ---"
new_box 0.30.0; C0="$(sha "$H/.openclaw/openclaw.json")"
bash -c 'trap "" TERM; sleep 600' & APP_DUMMY=$!; DUMMY_PIDS="$DUMMY_PIDS $APP_DUMMY"
OUT="$(MOCK_APP_PID=$APP_DUMMY wire)"; rc=$?
check "T17 exit 1, deferred, running bundle NOT replaced or relaunched, config untouched" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "running bundle was NOT replaced" && [ -x "$APPBIN/ollama" ] && [ ! -e "$H/.Trash" ] && ! grep -q "^open " "$CALLS" && [ "$(sha "$H/.openclaw/openclaw.json")" = "$C0" ]'
check "T17 the app got SIGTERM (still alive only because it ignores it), no osascript" 'kill -0 $APP_DUMMY 2>/dev/null && ! grep -q osascript "$CALLS" && ! grep -vE "^\s*#" "$WIRE" | grep -q osascript'
kill -9 $APP_DUMMY 2>/dev/null

echo "--- T18: Gemini persona fallback copy (own Google key only) ---"
new_box 0.40.0
OUT="$(wire --dry-run)"; rc=$?
check "T18a no Google key: skipped cleanly, nothing planned" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "fallback copy skipped: this box has no Google key" && ! printf "%s" "$OUT" | grep -q "would download the Gemini fallback"'
mkdir -p "$H/.openclaw/secrets"; printf 'GOOGLE_API_KEY=not-a-real-key\n' > "$H/.openclaw/secrets/.env"
OUT="$(wire --dry-run)"; rc=$?
check "T18b own key: the fallback copy is planned into the box's own coaching dir" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "would download the Gemini fallback copy.*$H/.openclaw/workspace/data/coaching-personas/gemini-fallback-index.sqlite"'
check "T18b the key value is never printed; nothing was written; memory.search.fallback untouched" '! printf "%s" "$OUT" | grep -q "not-a-real-key" && [ ! -e "$H/.openclaw/workspace/data/coaching-personas" ] && ! grep -qE "LOCAL_EMBEDDER_FALLBACK|\"fallback\"" <(sed -n "/^# ── 5b/,/^# ── 6/p" "$WIRE")'
echo "--- T19: Gemini SOP fallback set (CC >= 7.6.108, own key only) ---"
mk_cc() { # <version>: a fixture Command Center + a database holding <n> sops
  rm -rf "$T/cc" "$T/cc.db"; mkdir -p "$T/cc/scripts"
  printf '{"name":"blackceo-command-center","version":"%s"}\n' "$1" > "$T/cc/package.json"
  : > "$T/cc/scripts/provision-gemini-fallback-sop-set.ts"
  python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("create table sops(id text primary key, slug text)"); c.executemany("insert into sops values(?,?)", [("a","a"),("b","b")]); c.commit()' "$T/cc.db"
  SOP_CC="$T/cc"; SOP_DB="$T/cc.db"; SOP_NODE=""
}
sopfb_runs() { grep -c -- '--import tsx scripts/provision-gemini-fallback-sop-set.ts' "$CALLS"; }
givekey() { mkdir -p "$H/.openclaw/secrets"; printf 'GOOGLE_API_KEY=not-a-real-key\n' > "$H/.openclaw/secrets/.env"; }
MAN="$SKILL/../shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json"
SENT='$H/.openclaw/local-embedder/gemini-sop-fallback.done'

new_box 0.40.0; mk_cc 7.6.108; givekey
OUT="$(wire --no-reindex)"; rc=$?
check "T19a CC 7.6.108 + own key: exit 0, the CC script runs from the CC dir with manifest and database" '[ $rc = 0 ] && [ "$(sopfb_runs)" = 1 ] && grep -q -- "--import tsx scripts/provision-gemini-fallback-sop-set.ts --manifest $MAN --db $T/cc.db\$" "$CALLS"'
check "T19a sentinel written; key value never printed" '[ -s "$H/.openclaw/local-embedder/gemini-sop-fallback.done" ] && ! printf "%s" "$OUT" | grep -q "not-a-real-key"'
check "T19a the local sop_embeddings table is never named in code" '! sed -n "/^# ── 5c/,/^# ── 6/p" "$WIRE" | grep -vE "^\s*#" | grep -qE "sop_embeddings([^_]|$)"'
OUT="$(wire --no-reindex)"; rc=$?
check "T19b re-run is idempotent: no second provisioning" '[ $rc = 0 ] && [ "$(sopfb_runs)" = 1 ] && printf "%s" "$OUT" | grep -q "Gemini SOP fallback already provisioned"'
python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("insert into sops values(\"c\",\"c\")"); c.commit()' "$T/cc.db"
OUT="$(wire --no-reindex)"; rc=$?
check "T19b a changed sops count re-provisions (new SOPs get mapped)" '[ $rc = 0 ] && [ "$(sopfb_runs)" = 2 ]'

new_box 0.40.0; mk_cc 7.6.108
OUT="$(wire --no-reindex)"; rc=$?
check "T19c no Google key: skipped, nothing run" '[ $rc = 0 ] && [ "$(sopfb_runs)" = 0 ] && printf "%s" "$OUT" | grep -q "Gemini SOP fallback skipped: this box has no Google key"'
new_box 0.40.0; mk_cc 7.6.107; givekey
OUT="$(wire --no-reindex)"; rc=$?
check "T19d CC 7.6.107 (too old): skipped, nothing run" '[ $rc = 0 ] && [ "$(sopfb_runs)" = 0 ] && printf "%s" "$OUT" | grep -q "older than 7.6.108"'
new_box 0.40.0; mk_cc 7.6.108; givekey; SOP_CC="$T/no-such-cc"
OUT="$(wire --no-reindex)"; rc=$?
check "T19e no Command Center: skipped, nothing run" '[ $rc = 0 ] && [ "$(sopfb_runs)" = 0 ] && printf "%s" "$OUT" | grep -q "no Command Center with"'

new_box 0.40.0; mk_cc 7.6.108; givekey; touch "$T/sopfb-hang"; START=$(date +%s)
OUT="$(SOPFB_T=1 wire --no-reindex)"; rc=$?; ELAPSED=$(( $(date +%s) - START ))
check "T19f a hung CC script is cut off: exit 0, timed out, no sentinel, under 25s" '[ $rc = 0 ] && printf "%s" "$OUT" | grep -q "Gemini SOP fallback timed out after 1s" && [ ! -e "$H/.openclaw/local-embedder/gemini-sop-fallback.done" ] && [ "$ELAPSED" -lt 25 ]'
check "T19f the roll still finished (memory.search written, DONE)" 'printf "%s" "$OUT" | grep -q "re-index skipped" && [ "$(msearch | python3 -c "import json,sys; print(json.load(sys.stdin)[\"provider\"])")" = ollama ]'
rm -f "$T/sopfb-hang"
new_box 0.40.0; mk_cc 7.6.108; givekey; touch "$T/sopfb-fail"
OUT="$(wire --no-reindex)"; rc=$?
check "T19g a failing CC script is non-fatal: exit 0, no sentinel, retried next roll" '[ $rc = 0 ] && [ ! -e "$H/.openclaw/local-embedder/gemini-sop-fallback.done" ] && printf "%s" "$OUT" | grep -q "not provisioned (non-fatal; next roll retries)"'
rm -f "$T/sopfb-fail"
OUT="$(wire --no-reindex)"; rc=$?
check "T19g the next roll provisions it" '[ $rc = 0 ] && [ -s "$H/.openclaw/local-embedder/gemini-sop-fallback.done" ]'

new_box 0.40.0; mk_cc 7.6.108; givekey; touch "$T/path-node-bad"; SOP_NODE="$T/goodnode"
OUT="$(wire --no-reindex)"; rc=$?
check "T19h the PATH node cannot load better-sqlite3: the CC's own node is used instead" '[ $rc = 0 ] && grep -q "^goodnode --import tsx scripts/provision-gemini-fallback-sop-set.ts" "$CALLS" && ! grep -q "^node --import tsx" "$CALLS"'
rm -f "$T/path-node-bad"; SOP_CC=""; SOP_DB=""; SOP_NODE=""
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
