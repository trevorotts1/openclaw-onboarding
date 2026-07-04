#!/usr/bin/env bash
# tests/unit/storm-guard.test.sh — STRUCTURAL storm guards ("I can't have a storm like this")
#
# Proves the retry-storm (observed ~1300 all-4xx requests / ~10-of-15 failed
# books) is STRUCTURALLY IMPOSSIBLE, not just rarer. Five guardrails in
# 22-.../pipeline/orchestrator.py:
#
#   G1 FAIL-FAST     retry ONLY 429/5xx; every other status (incl.
#                    400/401/402/403/404/408/422) fails fast, hard-capped at
#                    PROVIDER_MAX_RETRIES retries.
#   G2 PREFLIGHT     one tiny probe per provider before the loop; a deterministic
#                    auth/credit/param failure ABORTS the whole build.
#   G3 CIRCUIT-BRK   a provider's first CIRCUIT_BREAKER_TRIP calls all failing the
#                    same class ABORTS the build.
#   G4 REQ BUDGET    a per-build hard ceiling on total provider requests.
#   G5 TOKEN CLAMP   max_tokens clamped to the model output ceiling.
#
# THE HEADLINE PROOF (T4): drive an ALL-4xx provider and assert the build ABORTS
# after at most CIRCUIT_BREAKER_TRIP requests — never a storm — and that under
# rotating error classes the GLOBAL BUDGET still hard-caps total requests.
#
# Fully offline + hermetic (fake aiohttp + sandbox HOME + fake key).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORCH="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$ORCH" ] || { echo "FAIL: orchestrator not found: $ORCH"; exit 1; }

echo "=== storm-guard.test.sh ==="

mkdir -p "$TMP/home/clawd/secrets"
mkdir -p "$TMP/home/.openclaw/workspace/data/coaching-personas"
cat > "$TMP/home/clawd/secrets/.env" <<'ENVEOF'
OPENROUTER_API_KEY="sk-or-quoted-fake-value-not-a-real-key"
ENVEOF
chmod 600 "$TMP/home/clawd/secrets/.env"   # secrets/.env hygiene (QC static gate)

env -u OLLAMA_BASE_URL HOME="$TMP/home" OPENROUTER_API_KEY="sk-or-env-fake" \
    python3 - "$ORCH" <<'PY'
import sys, types, importlib.util, asyncio

orch_path = sys.argv[1]

aiohttp = types.ModuleType("aiohttp")
class ClientSession: ...
class ClientTimeout:
    def __init__(self, *a, **k): pass
aiohttp.ClientSession = ClientSession
aiohttp.ClientTimeout = ClientTimeout
sys.modules["aiohttp"] = aiohttp

spec = importlib.util.spec_from_file_location("orch_storm", orch_path)
orch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orch)

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

PASS = 0; FAIL = 0
def ok(m):  globals().__setitem__("PASS", PASS+1); print(f"  PASS: {m}")
def bad(m): globals().__setitem__("FAIL", FAIL+1); print(f"  FAIL: {m}")

# ── T1: G1 retry-allowlist — ONLY 429/5xx are retryable ──────────────────────
retry_yes = [429, 500, 502, 503, 599]
retry_no  = [400, 401, 402, 403, 404, 408, 409, 422]
if all(orch._is_retryable_status(s) for s in retry_yes) and \
   not any(orch._is_retryable_status(s) for s in retry_no):
    ok("T1: _is_retryable_status retries ONLY 429/5xx (400/401/402/403/408/422 fail fast)")
else:
    bad("T1: _is_retryable_status allowlist wrong")

# ── T2: G4 budget unit — charge past budget raises _BuildAbort ────────────────
g = orch._StormGuard(budget=5)
aborted_at = None
try:
    for i in range(1, 100):
        g.charge("openrouter")
except orch._BuildAbort:
    aborted_at = g.count
if aborted_at == 6:  # 6th charge (count=6) exceeds budget 5
    ok(f"T2: _StormGuard budget hard-caps — aborts on charge #{aborted_at} (budget 5)")
else:
    bad(f"T2: budget abort at count={aborted_at}, want 6")

# ── T3: G3 circuit-breaker unit — first 3 same-class failures abort; mixed OK ─
g = orch._StormGuard(budget=10_000)
cb_tripped = False
try:
    for _ in range(3):
        g.record("openrouter", False, "http_401")
except orch._BuildAbort:
    cb_tripped = True
# mixed classes must NOT trip
g2 = orch._StormGuard(budget=10_000)
mixed_ok = True
try:
    g2.record("ollama", False, "http_401")
    g2.record("ollama", False, "http_402")
    g2.record("ollama", False, "http_403")
except orch._BuildAbort:
    mixed_ok = False
if cb_tripped and mixed_ok:
    ok("T3: circuit breaker trips on 3 SAME-class failures; mixed classes do NOT trip")
else:
    bad(f"T3: cb_tripped={cb_tripped} mixed_ok={mixed_ok}")

# ── fake HTTP session ─────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, status): self.status = status
    async def json(self): return {"choices": [{"message": {"content": "x"}}], "message": {"content": "x"}}
    async def text(self): return f"error {self.status}"
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

class _Session:
    """status can be an int (constant) or a list (cycled per call)."""
    def __init__(self, status):
        self._status = status
        self.calls = 0
        self._i = 0
    def post(self, url, headers=None, json=None, timeout=None):
        self.calls += 1
        if isinstance(self._status, (list, tuple)):
            st = self._status[self._i % len(self._status)]
            self._i += 1
        else:
            st = self._status
        return _Resp(st)

# ── T4 (HEADLINE): an ALL-401 provider ABORTS within CIRCUIT_BREAKER_TRIP ─────
# This is the "no storm" proof — 1340 requests could never happen.
orch.init_storm_guard(1000)   # huge budget so the CIRCUIT BREAKER is what stops it
sess = _Session(401)
saw_abort = False
for _ in range(500):  # a naive storm would make 500+ requests
    try:
        _run(orch.call_openrouter(sess, "deepseek/deepseek-v4-pro", "s", "u", max_tokens=16000))
    except orch._BuildAbort:
        saw_abort = True
        break
    except orch._DeterministicHTTPError:
        continue  # fail-fast per call; the guard aborts the BUILD
    except Exception:
        continue
if saw_abort and sess.calls <= orch.CIRCUIT_BREAKER_TRIP:
    ok(f"T4: ALL-401 provider ABORTS the build after {sess.calls} requests "
       f"(<= circuit-breaker {orch.CIRCUIT_BREAKER_TRIP}) — no storm possible")
else:
    bad(f"T4: saw_abort={saw_abort} requests={sess.calls} "
        f"(want abort within {orch.CIRCUIT_BREAKER_TRIP})")

# ── T5: G4 budget bounds a ROTATING-error storm (circuit breaker can't trip) ──
orch._STORM = orch._StormGuard(budget=10)   # small budget; rotate classes so CB never fires
sess = _Session([401, 402, 403])            # every call fails fast, different class each time
saw_abort = False
for _ in range(500):
    try:
        _run(orch.call_openrouter(sess, "deepseek/deepseek-v4-pro", "s", "u", max_tokens=16000))
    except orch._BuildAbort:
        saw_abort = True
        break
    except orch._DeterministicHTTPError:
        continue
    except Exception:
        continue
if saw_abort and sess.calls <= 10:
    ok(f"T5: rotating-error storm hard-capped by the GLOBAL BUDGET at {sess.calls} "
       f"requests (budget 10) — still no storm")
else:
    bad(f"T5: saw_abort={saw_abort} requests={sess.calls} (want <= budget 10)")

# ── T6: G1 fail-fast includes 402 (credits) + 408, and 1 request only ─────────
orch._STORM = None  # isolate: no guard, just per-call fail-fast behavior
def _one_call(status):
    s = _Session(status)
    err = None
    try:
        _run(orch.call_openrouter(s, "deepseek/deepseek-v4-pro", "s", "u", max_tokens=16000))
    except Exception as e:
        err = e
    return s.calls, err
t6_ok = True
for st in (402, 408, 400, 401, 403, 422):
    calls, err = _one_call(st)
    if not (calls == 1 and isinstance(err, orch._DeterministicHTTPError)):
        t6_ok = False; bad(f"T6: status {st}: calls={calls} err={type(err).__name__}")
# 429 and 500 still retry the capped number of times
for st in (429, 500):
    calls, _ = _one_call(st)
    want = min(orch.MAX_RETRIES, orch.PROVIDER_MAX_RETRIES + 1)
    if calls != want:
        t6_ok = False; bad(f"T6: retryable {st}: calls={calls} want {want}")
if t6_ok:
    ok("T6: fail-fast on 400/401/402/403/408/422 (1 request each); 429/5xx retry the hard cap")

# ── T7: G2 preflight aborts on a dead provider, passes a healthy one ──────────
async def _preflight(session):
    return await orch.preflight_providers(session, ["openrouter/deepseek/deepseek-v4-pro"])
orch._STORM = None
dead = _Session(401)
pf_aborted = False
try:
    _run(_preflight(dead))
except orch._BuildAbort:
    pf_aborted = True
healthy = _Session(200)
pf_ok = True
try:
    _run(_preflight(healthy))
except orch._BuildAbort:
    pf_ok = False
if pf_aborted and pf_ok:
    ok("T7: preflight ABORTS on a dead (401) provider and PASSES a healthy (200) one")
else:
    bad(f"T7: preflight dead-abort={pf_aborted} healthy-pass={pf_ok}")

# ── T8: budget scales with pending books (structural bound is finite) ─────────
orch.init_storm_guard(5 * orch.PER_BOOK_EXPECTED_CALLS)
expected_budget = orch.REQUEST_BUDGET_MULTIPLIER * 5 * orch.PER_BOOK_EXPECTED_CALLS
if orch._STORM.budget == expected_budget and expected_budget < 1300:
    ok(f"T8: 5-book budget = {expected_budget} (finite, < the 1300-request storm)")
else:
    bad(f"T8: budget={orch._STORM.budget} expected={expected_budget}")

print(f"\n=== storm-guard: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
PY
rc=$?
exit $rc
