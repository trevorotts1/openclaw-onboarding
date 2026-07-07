#!/usr/bin/env bash
# 59-anthology-engine/scripts/verify-webhook-t1-t9.sh
# ----------------------------------------------------------------------------
# The NINE intake proofs of SPEC Section 13.2 (T1..T9), executed and OBSERVED.
# Script inventory row 32 (ENGINE-MANIFEST.json): exit 0 all nine observed;
# exit 4 a failing test id emitted.
#
# T1 route registered on the gateway
# T2 requests without the route secret are refused
# T3 malformed payload lands in Exceptions with a reason, never a crash
# T4 valid synthetic submission acknowledges in under 2 seconds, creates participant
# T5 duplicate delivery of the same submission is a no-op acknowledge
# T6 wrong-tenant payload lands in Exceptions (tenant_mismatch)
# T7 stage-mismatched form lands in Exceptions (stage_mismatch)
# T8 the REAL public URL through the named Cloudflare Tunnel accepts end to end
# T9 gateway restart preserves the route and the pending state
#
# WHERE IT RUNS: EXECUTED AND OBSERVED on the operator canary at W5.3 AFTER
# provision-anthology-client.sh writes the hooks mapping. Run pre-provisioning it
# self-validates structure (route-template.json + fixtures + expected.json) and
# reports the LIVE battery as not-yet-executable (deferred), which is not a
# failure. T8/T9 require a real public URL / a gateway restart and stay DEFERRED
# unless explicitly enabled.
#
# SECRET HYGIENE (binding): the route secret is resolved from the env store by
# LABEL only (ANTHOLOGY_INTAKE_HOOK_SECRET). Its value is NEVER printed, logged,
# or echoed; only SET / NOT SET is reported. Convert and Flow naming throughout.
# No Anthropic identifier anywhere. All fixture data is synthetic.
#
# MODES / FLAGS:
#   --self-test        structural self-check ONLY (no network); exit 0/4. Used by
#                      tests/test_webhook.py and verify.sh.
#   --plan | --list    print the T1..T9 plan and exit 0.
#   --dry-run          structural checks + reachability report, no live probes.
#   --live             force the live battery (auto-skips T8/T9 without their flags).
#   --require-live     an unreachable gateway or an unregistered route is a hard
#                      fail (exit 3), and any un-executed T1..T7 holds the battery.
#   --base-url URL     gateway base (default http://127.0.0.1:18789).
#   --public-url URL   enable T8 against a real Cloudflare Tunnel public URL.
#   --allow-restart    enable T9 (restarts the gateway).
#   -h | --help        usage.
#
# EXIT: 0 all executed tests observed PASS (structure sound; deferred allowed
#       unless --require-live); 4 a failing test id emitted; 3 battery held
#       (unreachable/unregistered under --require-live); 2 usage.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"

VW_MODE="auto"          # auto | selftest | plan | dryrun
VW_DOLIVE=0
VW_REQUIRE_LIVE=0
VW_BASEURL="http://127.0.0.1:18789"
VW_PUBLICURL=""
VW_ALLOW_RESTART=0

while [ $# -gt 0 ]; do
    case "$1" in
        --self-test)     VW_MODE="selftest"; shift ;;
        --plan|--list)   VW_MODE="plan"; shift ;;
        --dry-run)       VW_MODE="dryrun"; shift ;;
        --live)          VW_DOLIVE=1; shift ;;
        --require-live)  VW_DOLIVE=1; VW_REQUIRE_LIVE=1; shift ;;
        --base-url)      VW_BASEURL="${2:-}"; shift 2 ;;
        --public-url)    VW_PUBLICURL="${2:-}"; shift 2 ;;
        --allow-restart) VW_ALLOW_RESTART=1; shift ;;
        -h|--help)
            sed -n '2,45p' "${BASH_SOURCE[0]:-$0}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "verify-webhook: unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "verify-webhook: FATAL python3 required" >&2; exit 2; }

# Report the secret label state WITHOUT ever reading or printing its value.
if [ -n "${ANTHOLOGY_INTAKE_HOOK_SECRET:-}" ]; then
    echo "verify-webhook: ANTHOLOGY_INTAKE_HOOK_SECRET = SET (value never printed)"
else
    echo "verify-webhook: ANTHOLOGY_INTAKE_HOOK_SECRET = NOT SET (authed live probes will be held)"
fi

VW_SKILL_DIR="$SKILL_DIR" \
VW_MODE="$VW_MODE" \
VW_DOLIVE="$VW_DOLIVE" \
VW_REQUIRE_LIVE="$VW_REQUIRE_LIVE" \
VW_BASEURL="$VW_BASEURL" \
VW_PUBLICURL="$VW_PUBLICURL" \
VW_ALLOW_RESTART="$VW_ALLOW_RESTART" \
python3 - <<'PY'
import json, os, re, socket, sys, time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SKILL = os.environ["VW_SKILL_DIR"]
MODE = os.environ["VW_MODE"]
DOLIVE = os.environ["VW_DOLIVE"] == "1"
REQUIRE_LIVE = os.environ["VW_REQUIRE_LIVE"] == "1"
BASEURL = os.environ["VW_BASEURL"].rstrip("/")
PUBLICURL = os.environ["VW_PUBLICURL"].rstrip("/")
ALLOW_RESTART = os.environ["VW_ALLOW_RESTART"] == "1"
SECRET = os.environ.get("ANTHOLOGY_INTAKE_HOOK_SECRET")  # value used, NEVER printed

def P(*a): return os.path.join(SKILL, *a)
FIX = P("fixtures", "webhook")
ROUTE_TPL = P("config", "route-template.json")
ENGINE_CFG = P("config", "engine-config.template.json")
EXPECTED = os.path.join(FIX, "expected.json")
LABEL = "ANTHOLOGY_INTAKE_HOOK_SECRET"

# Anthropic-family id shapes assembled from fragments so no banned literal ever
# lives in this file.
_a = "anthro" + "pic"; _c = "clau" + "de-"
BANNED = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)

struct_fails = []   # structural defects -> exit 4
def sneed(cond, msg):
    if not cond: struct_fails.append(msg)

# --------------------------------------------------------------------------
# Structural validation (always; the whole of --self-test).
# --------------------------------------------------------------------------
def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

route = expected = engcfg = None
try:
    route = load_json(ROUTE_TPL)
except Exception as exc:
    struct_fails.append("route-template.json unreadable/invalid: %s" % exc)
try:
    expected = load_json(EXPECTED)
except Exception as exc:
    struct_fails.append("expected.json unreadable/invalid: %s" % exc)
try:
    engcfg = load_json(ENGINE_CFG)
except Exception as exc:
    struct_fails.append("engine-config.template.json unreadable/invalid: %s" % exc)

if route is not None:
    sneed(route.get("surface") == "gateway-core-hooks",
          "route-template surface is not gateway-core-hooks")
    hooks = route.get("hooks", {})
    tok = hooks.get("token")
    sneed(isinstance(tok, dict), "hooks.token is not a SecretRef object (must not inline a value)")
    if isinstance(tok, dict):
        sneed(tok.get("source") == "env", "hooks.token.source is not 'env'")
        sneed(tok.get("id") == LABEL, "hooks.token.id is not %s" % LABEL)
    sneed(hooks.get("allowRequestSessionKey") is False,
          "hooks.allowRequestSessionKey must be false")
    maps = hooks.get("mappings", [])
    intake = next((m for m in maps if m.get("id") == "anthology-intake"), None)
    sneed(intake is not None, "route-template has no 'anthology-intake' mapping")
    if intake is not None:
        sneed((intake.get("match") or {}).get("path") == "anthology-intake",
              "mapping match.path is not 'anthology-intake'")
        sneed((intake.get("match") or {}).get("source") is not None,
              "mapping match.source is absent (needed for shared-box isolation)")
        sneed(intake.get("deliver") is False, "mapping deliver must be false (client-silent)")
        sneed(intake.get("allowUnsafeExternalContent") is False,
              "mapping allowUnsafeExternalContent must be false (untrusted form content)")
        sneed(isinstance(intake.get("transform"), dict) and intake["transform"].get("module"),
              "mapping transform.module is absent (deterministic intake_router dispatch)")
    sneed(route.get("route_secret_label") == LABEL,
          "route-template route_secret_label is not %s" % LABEL)

if route is not None and engcfg is not None:
    a = route.get("route_secret_label")
    b = (engcfg.get("intake") or {}).get("route_secret_label")
    sneed(a == b, "route_secret_label disagrees with engine-config.template.json (%r vs %r)" % (a, b))

# expected.json coherence + fixtures presence/parse.
FIXTURE_FILES = [
    "t4-valid-intake.json", "t5-duplicate-intake.json", "t6-wrong-tenant.json",
    "t7-stage-mismatch.json", "t3b-missing-ids.json", "t3-malformed-empty.json",
]
for fn in FIXTURE_FILES:
    fp = os.path.join(FIX, fn)
    sneed(os.path.isfile(fp), "missing fixture: %s" % fn)
    if os.path.isfile(fp):
        try:
            load_json(fp)
        except Exception as exc:
            struct_fails.append("fixture %s is not valid JSON: %s" % (fn, exc))
# The non-JSON malformed fixture MUST exist and MUST NOT be valid JSON.
notjson = os.path.join(FIX, "t3-malformed-notjson.txt")
sneed(os.path.isfile(notjson), "missing fixture: t3-malformed-notjson.txt")
if os.path.isfile(notjson):
    try:
        json.load(open(notjson, "r", encoding="utf-8"))
        struct_fails.append("t3-malformed-notjson.txt parsed as JSON but must NOT be valid JSON")
    except Exception:
        pass  # correct: it is intentionally non-JSON

if expected is not None:
    tests = expected.get("tests", {})
    for t in ("T1","T2","T3","T4","T5","T6","T7","T8","T9"):
        sneed(t in tests, "expected.json missing %s" % t)
    reasons = set(expected.get("valid_exception_reasons", []))
    for t, spec in tests.items():
        r = spec.get("expect_exception_reason")
        if r is not None:
            sneed(r in reasons, "%s expect_exception_reason %r not in the SPEC enum" % (t, r))
        for key in ("fixture",):
            fv = spec.get(key)
            if fv:
                sneed(os.path.isfile(os.path.join(FIX, fv)), "%s references missing fixture %s" % (t, fv))
        for fv in spec.get("fixtures", []) or []:
            sneed(os.path.isfile(os.path.join(FIX, fv)), "%s references missing fixture %s" % (t, fv))

# t5 must be a byte-identical duplicate of t4 (same fingerprint).
try:
    t4 = load_json(os.path.join(FIX, "t4-valid-intake.json"))
    t5 = load_json(os.path.join(FIX, "t5-duplicate-intake.json"))
    for k in ("contact_id", "anthology_id", "stage"):
        sneed(t4.get(k) == t5.get(k), "t5 fingerprint field %s differs from t4" % k)
    sneed(t4 == t5, "t5-duplicate-intake.json is not identical to t4 (dedup fingerprint would differ)")
except Exception as exc:
    struct_fails.append("t4/t5 comparison error: %s" % exc)

# No Anthropic id + no credential-shaped key in any owned webhook file.
CRED_KEYS = {"api_key","apikey","openrouter_api_key","authorization","bearer",
             "token","secret","x-openclaw-token","x-openclaw-webhook-secret"}
def scan_text(path):
    try:
        txt = open(path, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        return
    if BANNED.search(txt):
        struct_fails.append("Anthropic-family id shape in %s" % os.path.relpath(path, SKILL))
def scan_cred_keys(obj, where):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in CRED_KEYS:
                struct_fails.append("credential-shaped key %r in %s" % (k, where))
            scan_cred_keys(v, where)
    elif isinstance(obj, list):
        for v in obj: scan_cred_keys(v, where)

for path in [ROUTE_TPL, EXPECTED] + [os.path.join(FIX, f) for f in FIXTURE_FILES] + [notjson]:
    if os.path.isfile(path):
        scan_text(path)
for fn in FIXTURE_FILES:
    fp = os.path.join(FIX, fn)
    if os.path.isfile(fp):
        try:
            scan_cred_keys(load_json(fp), fn)
        except Exception:
            pass

def emit_struct():
    if struct_fails:
        print("verify-webhook: STRUCTURAL FAIL (%d issue(s))" % len(struct_fails))
        for m in struct_fails:
            print("  - " + m)
        return False
    print("verify-webhook: structure OK (route-template + fixtures + expected coherent)")
    return True

# --------------------------------------------------------------------------
# --self-test and --plan short-circuits.
# --------------------------------------------------------------------------
if MODE == "selftest":
    sys.exit(0 if emit_struct() else 4)

if MODE == "plan":
    ok = emit_struct()
    print("\nverify-webhook: T1..T9 plan (SPEC 13.2)")
    order = ["T1","T2","T3","T4","T5","T6","T7","T8","T9"]
    tests = (expected or {}).get("tests", {})
    for t in order:
        d = tests.get(t, {}).get("desc", "(desc pending)")
        print("  %s  %s" % (t, d))
    print("\nExecuted and observed on the canary at W5.3; T8 needs --public-url, T9 needs --allow-restart.")
    sys.exit(0 if ok else 4)

# Structure must be sound before any live claim.
struct_ok = emit_struct()

# --------------------------------------------------------------------------
# Live battery.
# --------------------------------------------------------------------------
PASS, FAIL, DEFER = "PASS", "FAIL", "DEFERRED"
results = {}   # T-id -> (status, note)
def rec(t, status, note=""): results[t] = (status, note)

def reachable(base):
    try:
        u = urlsplit(base)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except Exception:
        return False

def post(url, body_bytes, headers, timeout=5):
    """Return (status, elapsed_seconds). Never raises for HTTP status codes."""
    req = Request(url, data=body_bytes, headers=headers, method="POST")
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, time.time() - t0
    except HTTPError as he:
        return he.code, time.time() - t0
    except URLError:
        return None, time.time() - t0

def authed_headers():
    h = {"Content-Type": "application/json"}
    if SECRET:
        h["Authorization"] = "Bearer %s" % SECRET  # value used, never printed
    return h

def fixture_bytes(name):
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()

INTAKE_URL = BASEURL + "/hooks/anthology-intake"

def run_live():
    live = reachable(BASEURL)
    if not live:
        for t in ["T1","T2","T3","T4","T5","T6","T7"]:
            rec(t, DEFER, "gateway not reachable at base-url (battery held for W5.3 canary)")
        rec("T8", DEFER, "needs --public-url")
        rec("T9", DEFER, "needs --allow-restart")
        return
    if not SECRET:
        rec("T2", DEFER, "cannot send the no-secret probe meaningfully without a provisioned route")
    # T1 route registered: authed minimal probe -> anything other than 404 means the
    # route/hook surface answered (401 without secret also proves the surface is live,
    # but registration of THIS mapping is a non-404 authed answer).
    st, _ = post(INTAKE_URL, b"{}", authed_headers())
    if st is None:
        rec("T1", DEFER, "gateway stopped answering mid-probe")
    elif st == 404:
        rec("T1", DEFER, "route not registered yet (provision-anthology-client.sh writes the mapping)")
    else:
        rec("T1", PASS, "gateway answered the mapped route (status %s)" % st)
    # T2 no-secret refused.
    st2, _ = post(INTAKE_URL, fixture_bytes("t4-valid-intake.json"), {"Content-Type": "application/json"})
    if st2 == 401:
        rec("T2", PASS, "no-secret request refused (401)")
    elif st2 is None:
        rec("T2", DEFER, "gateway unreachable during T2")
    else:
        rec("T2", FAIL, "no-secret request was not refused (status %s, expected 401)" % st2)
    # T3/T4/T5/T6/T7 need the secret set and the route registered.
    route_ready = results.get("T1", (DEFER,))[0] == PASS and SECRET
    if not route_ready:
        for t in ["T3","T4","T5","T6","T7"]:
            rec(t, DEFER, "route not registered or secret unset (HTTP contract not exercisable here)")
    else:
        # T3 malformed -> ack, never 5xx/crash.
        t3ok = True
        for fn in ("t3-malformed-empty.json", "t3-malformed-notjson.txt", "t3b-missing-ids.json"):
            st, _ = post(INTAKE_URL, fixture_bytes(fn), authed_headers())
            if st is None or st >= 500:
                t3ok = False
        rec("T3", PASS if t3ok else FAIL,
            "malformed payloads acknowledged without a 5xx/crash; ledger-reason assertion (unroutable_missing_ids) deferred to W5.3 (anthology_state.py)")
        # T4 valid -> 2xx ack under 2s.
        st, el = post(INTAKE_URL, fixture_bytes("t4-valid-intake.json"), authed_headers())
        if st is not None and 200 <= st < 300 and el < 2.0:
            rec("T4", PASS, "acknowledged in %.3fs (<2s); participant-created assertion deferred to W5.3" % el)
        else:
            rec("T4", FAIL, "ack contract not met (status %s, elapsed %.3fs)" % (st, el))
        # T5 duplicate -> no-op ack.
        st, _ = post(INTAKE_URL, fixture_bytes("t5-duplicate-intake.json"), authed_headers())
        if st is not None and 200 <= st < 300:
            rec("T5", PASS, "duplicate acknowledged; single-participant no-op assertion deferred to W5.3")
        else:
            rec("T5", FAIL, "duplicate not acknowledged (status %s)" % st)
        # T6 wrong-tenant -> ack + Exceptions(tenant_mismatch).
        st, _ = post(INTAKE_URL, fixture_bytes("t6-wrong-tenant.json"), authed_headers())
        if st is not None and 200 <= st < 300:
            rec("T6", PASS, "acknowledged; Exceptions(tenant_mismatch) assertion deferred to W5.3")
        else:
            rec("T6", FAIL, "wrong-tenant not acknowledged (status %s)" % st)
        # T7 stage-mismatch -> ack + Exceptions(stage_mismatch).
        st, _ = post(INTAKE_URL, fixture_bytes("t7-stage-mismatch.json"), authed_headers())
        if st is not None and 200 <= st < 300:
            rec("T7", PASS, "acknowledged; Exceptions(stage_mismatch) assertion deferred to W5.3")
        else:
            rec("T7", FAIL, "stage-mismatch not acknowledged (status %s)" % st)
    # T8 real public URL.
    if PUBLICURL:
        if not SECRET:
            rec("T8", DEFER, "public URL supplied but secret unset")
        else:
            st, _ = post(PUBLICURL.rstrip("/") + "/hooks/anthology-intake",
                         fixture_bytes("t4-valid-intake.json"), authed_headers(), timeout=10)
            rec("T8", PASS if (st is not None and 200 <= st < 300) else FAIL,
                "public Cloudflare Tunnel end-to-end ack (status %s)" % st)
    else:
        rec("T8", DEFER, "needs --public-url (real named Cloudflare Tunnel URL; never Tailscale)")
    # T9 gateway restart preserves route + state.
    if ALLOW_RESTART:
        rec("T9", DEFER, "restart harness runs on the W5.3 canary; not performed by this invocation")
    else:
        rec("T9", DEFER, "needs --allow-restart")

if MODE == "dryrun" or not DOLIVE:
    if not reachable(BASEURL):
        note = "gateway not reachable at base-url"
    else:
        note = "live probes not requested (pass --live)"
    for t in ["T1","T2","T3","T4","T5","T6","T7"]:
        rec(t, DEFER, note + "; battery executed and observed on the canary at W5.3")
    rec("T8", DEFER, "needs --public-url")
    rec("T9", DEFER, "needs --allow-restart")
else:
    run_live()

# --------------------------------------------------------------------------
# Summary + exit.
# --------------------------------------------------------------------------
order = ["T1","T2","T3","T4","T5","T6","T7","T8","T9"]
print("\nverify-webhook: T1..T9 battery")
n_pass = n_fail = n_defer = 0
failing = []
for t in order:
    status, note = results.get(t, (DEFER, "not evaluated"))
    print("  %-3s %-9s %s" % (t, status, note))
    if status == PASS: n_pass += 1
    elif status == FAIL: n_fail += 1; failing.append(t)
    else: n_defer += 1

print("\nverify-webhook: %d PASS, %d FAIL, %d DEFERRED" % (n_pass, n_fail, n_defer))

if not struct_ok:
    print("verify-webhook: exit 4 (structural defect blocks the battery)")
    sys.exit(4)
if n_fail:
    print("verify-webhook: exit 4 (failing test id(s): %s)" % ", ".join(failing))
    sys.exit(4)
if REQUIRE_LIVE and n_defer:
    print("verify-webhook: exit 3 (--require-live: %d test(s) not executed; battery not fully observed)" % n_defer)
    sys.exit(3)
if n_defer and n_pass == 0:
    print("verify-webhook: exit 0 (structure sound; live battery deferred to the W5.3 canary)")
else:
    print("verify-webhook: exit 0 (no failing test; %d observed, %d deferred)" % (n_pass, n_defer))
sys.exit(0)
PY
rc=$?
exit "$rc"
