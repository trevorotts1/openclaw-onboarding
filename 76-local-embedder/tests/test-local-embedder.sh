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
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
BIN="$T/bin"; mkdir -p "$BIN"
CALLS="$T/calls.log"; SLOG="$T/server.log"; STATE="$T/state.json"
PYBIN="$(dirname "$(command -v python3)")"

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
mk ps       'echo "$MOCK_EXE"'
mk lsof     'case "$*" in
  *LISTEN*) [ -f "$MOCK_T/no-daemon" ] && exit 1; echo "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME"; echo "ollama 4242 u 3u IPv4 0x0 0t0 TCP 127.0.0.1:$(cat "$MOCK_T/port") (LISTEN)" ;;
  *ESTABLISHED*) [ -f "$MOCK_T/busy" ] || exit 1; echo "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME"; echo "ollama 4242 u 9u IPv4 0x0 0t0 TCP 127.0.0.1:1->127.0.0.1:2 (ESTABLISHED)" ;;
esac'
mk launchctl 'case "$1" in
  getenv) [ "$2" = OLLAMA_MODELS ] && echo /Volumes/models; exit 0 ;;
  print) exit 0 ;;
  *) echo "launchctl $*" >> "$MOCK_T/calls.log" ;;
esac'
mk openclaw 'case "$1 ${2:-}" in
  "--version "*) echo "OpenClaw 2026.9.4 (fixture)" ;;
  "config validate") [ -f "$MOCK_T/mutate-chat-on-validate" ] && python3 -c "import json,sys; p=sys.argv[1]; c=json.load(open(p)); c[\"models\"][\"providers\"][\"ollama\"][\"baseUrl\"]=\"http://elsewhere\"; json.dump(c,open(p,\"w\"))" "$HOME/.openclaw/openclaw.json"
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$HOME/.openclaw/openclaw.json" ;;
  *) echo "openclaw $*" >> "$MOCK_T/calls.log"
     case "$*" in *"memory status"*) echo "Provider: ollama (requested: ollama)";; esac ;;
esac'
for c in brew osascript open tar shasum plutil ditto; do mk "$c" "echo \"$c \$*\" >> \"\$MOCK_T/calls.log\""; done
# fake `ollama` CLI, placed where the Ollama app keeps it so the daemon looks app-installed
APPBIN="$T/Applications/Ollama.app/Contents/Resources"; mkdir -p "$APPBIN"
cat > "$APPBIN/ollama" <<'SH'
#!/usr/bin/env bash
echo "ollama $* OLLAMA_HOST=$OLLAMA_HOST" >> "$MOCK_T/calls.log"
case "$1 $2" in
  "show --modelfile") printf '# Modelfile generated by "ollama show"\nFROM /blobs/sha256-0d0e\nTEMPLATE {{ .Prompt }}\nPARAMETER num_ctx 4096\nPARAMETER stop "<end>"\n' ;;
  create*)
    n=$(ls "$MOCK_T"/created-*.Modelfile 2>/dev/null | wc -l | tr -d ' ')
    cp "$4" "$MOCK_T/created-$n.Modelfile"
    params="$(sed -n 's/^PARAMETER //p' "$4" | grep -v '^stop ')"
    python3 -c 'import json,sys; print(json.dumps({"model": sys.argv[1], "params": sys.argv[2]}))' "$2" "$params" \
      | curl -fsS -H 'Content-Type: application/json' -d @- "http://$OLLAMA_HOST/test/pin" >/dev/null ;;
esac
SH
chmod +x "$APPBIN/ollama"

# ── fixture box ─────────────────────────────────────────────────────────────
H="$T/home"
new_box() { # [daemon-version]
  rm -rf "$H" "$T"/created-*.Modelfile "$T/no-daemon" "$T/busy" "$T/mutate-chat-on-validate"
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
  env -i HOME="$H" PATH="$BIN:$PYBIN:/usr/bin:/bin:/usr/sbin:/sbin" MOCK_T="$T" MOCK_EXE="$APPBIN/ollama" \
    MOCK_UNAME="${MOCK_UNAME:-Darwin}" LOCAL_EMBEDDER_VPS_ROOT="${VPS_ROOT_T:-$T/no-such-data-dir}" \
    LOCAL_EMBEDDER_APPS_DIR="$T/no-apps" LOCAL_EMBEDDER_IDLE_WAIT=0 bash "$WIRE" "$@" 2>&1
}
sha() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
keystat() { python3 -c 'import os,sys; print([ (s.st_ino,s.st_size,int(s.st_mtime),s.st_mode) for s in map(os.stat, sys.argv[1:])])' "$H/.ollama/id_ed25519" "$H/.ollama/id_ed25519.pub"; }
cfgpart() { python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); c.get("memory",{}).pop("search",None); print(json.dumps(c,sort_keys=True))' "$H/.openclaw/openclaw.json"; }
mutations() { grep -E '^(brew|osascript|open|tar|shasum|plutil|ditto) |^launchctl (bootstrap|bootout|kickstart|setenv|unsetenv|load|unload)' "$CALLS"; }

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
        "multimodal": {"enabled": False}, "fallback": "openai", "dimensions": 768, "extraPaths": []}
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

echo "--- T7: fail closed ---"
new_box 0.40.0; setstate flip_me_on_pin true
OUT="$(wire)"; rc=$?
check "T7a a changed /api/me status fails the run (exit 1, no re-index)" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "cloud state CHANGED" && ! grep -q "memory status" "$CALLS"'
new_box 0.40.0; touch "$T/mutate-chat-on-validate"
OUT="$(wire)"; rc=$?
check "T7b a chat-config change fails the run (exit 1, no re-index)" '[ $rc = 1 ] && printf "%s" "$OUT" | grep -q "fingerprint CHANGED" && ! grep -q "memory status" "$CALLS"'

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

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
