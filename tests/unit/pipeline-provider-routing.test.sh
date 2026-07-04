#!/usr/bin/env bash
# tests/unit/pipeline-provider-routing.test.sh — task-64 provider-reliability gates
#
# Proves the three routing/reliability fixes in the book-to-persona
# orchestrator (bugs 3, 4, 5). Bugs 1 (get_keys dequote) and 2 (OpenRouter
# fallback model-id mapping) shipped in v17.0.22 and are re-asserted for
# regression here too.
#
#   T1  LOCAL-FIRST OLLAMA (bug 3): with no OLLAMA_BASE_URL configured the
#       Ollama route resolves to the LOCAL daemon (http://localhost:11434/api)
#       and call_ollama_cloud sends NO Authorization header (the signed-in
#       daemon needs none) — never the dead 21-char key that 401s on
#       ollama.com. An explicit non-local OLLAMA_BASE_URL still sends the key.
#   T2  max_tokens CLAMP (bug 4): _clamp_max_tokens caps deepseek-v4-pro
#       (both ':cloud' and 'deepseek/…' forms) at 65536; a 120000 ask is
#       clamped; an in-range ask is untouched.
#   T3  FAIL-FAST 4xx (bug 5): call_ollama_cloud AND call_openrouter make
#       EXACTLY ONE HTTP call on a deterministic 4xx (400/401/403/404/422) —
#       no MAX_RETRIES retry-storm — and raise so the caller's fallback runs.
#       A 500/429 still retries (MAX_RETRIES calls).
#   T4  bug 1/2 regression: get_keys dequotes KEY="…"; _openrouter_fallback_model
#       maps ollama/deepseek-v4-pro:cloud -> deepseek/deepseek-v4-pro.
#
# Fully offline + hermetic: a fake `aiohttp` is injected so CI needs no
# network stack; a sandbox HOME + a fake OPENROUTER_API_KEY env satisfy the
# module-load provider guard without any real credential.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORCH="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$ORCH" ] || { echo "FAIL: orchestrator not found: $ORCH"; exit 1; }

echo "=== pipeline-provider-routing.test.sh ==="

# Sandbox HOME with a quoted-value secrets file (drives the bug-1 dequote test)
# and a coaching-personas dir so the orchestrator's log() has a writable target.
mkdir -p "$TMP/home/clawd/secrets"
mkdir -p "$TMP/home/.openclaw/workspace/data/coaching-personas"
cat > "$TMP/home/clawd/secrets/.env" <<'ENVEOF'
OPENROUTER_API_KEY="sk-or-quoted-fake-value-not-a-real-key"
export OLLAMA_API_KEY='dead-21char-placeholder'
ENVEOF
chmod 600 "$TMP/home/clawd/secrets/.env"   # secrets/.env hygiene (QC static gate)

env -u OLLAMA_BASE_URL HOME="$TMP/home" OPENROUTER_API_KEY="sk-or-env-fake" \
    python3 - "$ORCH" <<'PY'
import sys, types, importlib.util, asyncio

orch_path = sys.argv[1]

# ---- inject a fake aiohttp so CI needs no real network stack ----------------
aiohttp = types.ModuleType("aiohttp")
class ClientSession:  # only used for type annotations at def time
    ...
class ClientTimeout:
    def __init__(self, *a, **k): pass
aiohttp.ClientSession = ClientSession
aiohttp.ClientTimeout = ClientTimeout
sys.modules["aiohttp"] = aiohttp

# ---- import the orchestrator module by file path ----------------------------
spec = importlib.util.spec_from_file_location("orch_undertest", orch_path)
orch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orch)

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

PASS = 0; FAIL = 0
def ok(m):   globals().__setitem__("PASS", PASS+1); print(f"  PASS: {m}")
def bad(m):  globals().__setitem__("FAIL", FAIL+1); print(f"  FAIL: {m}")

# ── T1: local-first Ollama base ──────────────────────────────────────────────
if orch.OLLAMA_BASE_URL == "http://localhost:11434/api" and orch.OLLAMA_IS_LOCAL:
    ok(f"T1a: default Ollama base is the local daemon ({orch.OLLAMA_BASE_URL})")
else:
    bad(f"T1a: default Ollama base = {orch.OLLAMA_BASE_URL!r} is_local={orch.OLLAMA_IS_LOCAL}")

# ── T2: max_tokens clamp ─────────────────────────────────────────────────────
cases = [
    ("deepseek-v4-pro:cloud", 120000, 65536),
    ("deepseek/deepseek-v4-pro", 120000, 65536),
    ("ollama/deepseek-v4-pro:cloud", 120000, 65536),
    ("deepseek-v4-pro:cloud", 16000, 16000),
    ("google/gemini-3.1-flash-lite-preview", 120000, 65536),  # default cap
]
t2_ok = True
for model, req, want in cases:
    got = orch._clamp_max_tokens(model, req)
    if got != want:
        t2_ok = False; bad(f"T2: clamp({model},{req})={got} want {want}")
if t2_ok:
    ok("T2: _clamp_max_tokens caps deepseek-v4-pro (both forms) + default at 65536; in-range untouched")

# ── fake HTTP plumbing for the call_* fail-fast tests ─────────────────────────
class _Resp:
    def __init__(self, status): self.status = status
    async def json(self): return {"message": {"content": "x"}, "choices": [{"message": {"content": "x"}}]}
    async def text(self): return f"error body {self.status}"
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

class _Session:
    def __init__(self, status):
        self.status = status
        self.calls = 0
        self.last_headers = None
    def post(self, url, headers=None, json=None, timeout=None):
        self.calls += 1
        self.last_headers = headers or {}
        return _Resp(self.status)

# ── T1b: local mode sends NO Authorization header ────────────────────────────
sess = _Session(200)
_run(orch.call_ollama_cloud(sess, "deepseek-v4-pro:cloud", "sys", "user", max_tokens=16000))
if "Authorization" not in (sess.last_headers or {}):
    ok("T1b: local Ollama route sends NO Authorization header (signed-in daemon)")
else:
    bad(f"T1b: local route leaked an Authorization header: {list(sess.last_headers)}")

# ── T3: fail-fast on deterministic 4xx, retry on 5xx ─────────────────────────
def _drive(coro_fn, session):
    try:
        _run(coro_fn(session, "deepseek/deepseek-v4-pro", "s", "u", max_tokens=16000))
        return None
    except Exception as e:
        return e

for status in (400, 401, 403, 404, 422):
    s = _Session(status)
    err = _drive(orch.call_ollama_cloud, s)
    if s.calls == 1 and isinstance(err, orch._DeterministicHTTPError):
        pass
    else:
        bad(f"T3-ollama {status}: calls={s.calls} err={type(err).__name__} (want 1 call + _DeterministicHTTPError)")
        break
else:
    ok("T3a: call_ollama_cloud fails fast (1 call) on every deterministic 4xx")

for status in (400, 422):
    s = _Session(status)
    err = _drive(orch.call_openrouter, s)
    if s.calls == 1 and isinstance(err, orch._DeterministicHTTPError):
        pass
    else:
        bad(f"T3-openrouter {status}: calls={s.calls} err={type(err).__name__}")
        break
else:
    ok("T3b: call_openrouter fails fast (1 call) on deterministic 4xx")

# 5xx / 429 must STILL retry the full MAX_RETRIES (no false fail-fast)
s = _Session(500)
_drive(orch.call_ollama_cloud, s)
if s.calls == orch.MAX_RETRIES:
    ok(f"T3c: a 500 still retries the full MAX_RETRIES ({orch.MAX_RETRIES} calls)")
else:
    bad(f"T3c: 500 made {s.calls} calls, want {orch.MAX_RETRIES}")
s = _Session(429)
_drive(orch.call_openrouter, s)
if s.calls == orch.MAX_RETRIES:
    ok(f"T3d: a 429 still retries the full MAX_RETRIES ({orch.MAX_RETRIES} calls)")
else:
    bad(f"T3d: 429 made {s.calls} calls, want {orch.MAX_RETRIES}")

# ── T4: bug 1 (dequote) + bug 2 (fallback mapping) regression ────────────────
keys = orch.get_keys()
if keys.get("OPENROUTER_API_KEY") == "sk-or-quoted-fake-value-not-a-real-key" \
        and keys.get("OLLAMA_API_KEY") == "dead-21char-placeholder":
    ok("T4a: get_keys dequotes KEY=\"...\" and export KEY='...' values (bug 1)")
else:
    bad(f"T4a: get_keys dequote broke: {keys.get('OPENROUTER_API_KEY')!r}")

fb = orch._openrouter_fallback_model("ollama/deepseek-v4-pro:cloud")
fb2 = orch._openrouter_fallback_model("ollama/kimi-k2.6:cloud")
if fb == "deepseek/deepseek-v4-pro" and fb2 == "moonshotai/kimi-k2.6":
    ok("T4b: _openrouter_fallback_model maps ollama ids to vendor/model (bug 2)")
else:
    bad(f"T4b: fallback mapping wrong: {fb!r} {fb2!r}")

print(f"\n=== pipeline-provider-routing: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
PY
rc=$?
exit $rc
