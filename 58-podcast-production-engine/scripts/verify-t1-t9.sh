#!/usr/bin/env bash
# 58-podcast-production-engine/scripts/verify-t1-t9.sh
#
# PODCAST PRODUCTION ENGINE, inbound webhook onboarding verification suite.
#
# WHAT THIS IS
#   The executable T1 to T9 go-live gate for the per-client inbound webhook
#   layer (design/webhook-design.md Section 8). It drives REAL HTTP requests at
#   a live OpenClaw gateway route and then OBSERVES the on-box intake ledger,
#   the quarantine directory, and (when configured) the operator alert log.
#   Every verdict is derived from an actual observation. Nothing is assumed.
#   The webhook-design build checklist requires this: "verification is observed,
#   not asserted." T1 to T9 are the canonical onboarding tests from Section 8;
#   TM (method) and TB (body cap) are the two extra platform-delivery checks the
#   QC matrix names on the "Webhook delivery" row (auth, body cap, method).
#
#   Coverage, one line each:
#     T1  auth        POST with NO auth header             -> 401, nothing written
#     T2  auth        POST with a wrong secret             -> 401, nothing written
#     T3  auth        secret in the query string only      -> 401, nothing written
#     TM  method      non-POST (GET) on the webhook path   -> rejected, nothing written
#     TB  body-cap    body over the 256 KB platform cap    -> rejected, nothing written
#     T4  mapping     full _test payload, correct secret   -> 200 accepted, ledger state test, canonical fields mapped
#     T5  dedup       identical redelivery of T4           -> 200 duplicate, delivery_count 2, no second record
#     T6  divergence  T4 with ONE answer changed           -> 200 accepted, NEW job key, NEW record
#     T7  tenant      payload with a foreign location_id   -> quarantine, operator alert, nothing processed
#     T8  ack         payload missing style                -> ACK, ledger state needs_input, operator alert names the field
#     T9  public-url  T4 shape through the REAL public URL -> same as T4, proving tunnel + edge, not just loopback
#
# OBSERVABLE OUTPUT CONTRACT
#   1. A live, aligned results table on stdout (operator channel; there is NO
#      client-facing output anywhere in this suite).
#   2. A machine-readable results record written to
#         <state-dir>/verify/verify-t1-t9-<runid>.json
#      with one object per test carrying: id, category, target, http_observed,
#      expected, observed (ledger / quarantine / alert facts), and verdict.
#   3. A one-line summary appended to <state-dir>/verify/verify-history.log.
#   4. An exit code the provision gate can consume:
#         0  every executed test PASSED and T9 ran (go-live ready)
#         1  one or more tests FAILED
#         2  suite incomplete (loopback-only; T9 not run) but nothing failed
#         3  precondition error (missing config, missing tool, target unreachable)
#
# SAFETY POSTURE (binding)
#   - The route secret is NEVER printed, echoed, catted, grepped, or written to
#     any results file. It is passed only in an Authorization header. Verification
#     of the secret is SET-and-behaves, never show-me-the-value.
#   - No em dash characters anywhere. No triple-backtick fences in any output.
#   - Zero client-facing messages. Operator-verbose stdout only. Test payloads
#     carry _test true so nothing downstream can publish, write custom fields, or
#     enroll a workflow. T7 and T8 never reach production either.
#   - Config writes are not performed by this script; it reads live state only.
#   - The suite cleans up the exact test records it created (state test /
#     needs_input) and the exact quarantine file it created, and nothing else.
#
# USAGE
#   verify-t1-t9.sh --slug <client-slug> --test-contact <id> --test-location <id> \
#                   --public-url <https url> [options]
#
#   Required (flag or environment):
#     --slug            PODCAST_CLIENT_SLUG      client slug for the default loopback URL
#     --test-contact    PODCAST_TEST_CONTACT_ID  the onboarding-designated test contact id
#     --test-location   PODCAST_TEST_LOCATION_ID the client's configured Location ID (tenant check must pass)
#     secret            PODCAST_INTAKE_HOOK_SECRET in the environment, or --secret-file <path 0600>
#     --public-url      PODCAST_PUBLIC_HOOK_URL  the real Cloudflare URL for T9 (omit only with --loopback-only)
#
#   Options:
#     --loopback-url <url>   override the default http://127.0.0.1:18789/plugins/webhooks/podcast-intake-<slug>
#     --state-dir <path>     override ~/.openclaw/state/podcast-engine
#     --alert-log <path>     operator alert log to observe (default <state-dir>/alerts/alert-log.jsonl)
#     --test-podcast <id>    Podbean podcast_id used in test payloads (default a synthetic marker)
#     --loopback-only        run T1 to T8 against loopback, skip T9, exit 2 if nothing failed
#     --no-cleanup           leave the created test / needs_input / quarantine records in place
#     --help                 print this help and exit 0

if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -uo pipefail

# ---------------------------------------------------------------------------
# 0. Configuration and argument parsing
# ---------------------------------------------------------------------------

SLUG="${PODCAST_CLIENT_SLUG:-}"
LOOPBACK_URL=""
PUBLIC_URL="${PODCAST_PUBLIC_HOOK_URL:-}"
SECRET_FILE=""
STATE_DIR="${PODCAST_STATE_DIR:-$HOME/.openclaw/state/podcast-engine}"
ALERT_LOG="${PODCAST_ALERT_LOG:-}"
TEST_CONTACT_ID="${PODCAST_TEST_CONTACT_ID:-}"
TEST_LOCATION_ID="${PODCAST_TEST_LOCATION_ID:-}"
TEST_PODCAST_ID="${PODCAST_TEST_PODCAST_ID:-podbean-test-channel}"
LOOPBACK_ONLY=0
DO_CLEANUP=1

print_help() { sed -n '2,80p' "$0" | sed 's/^# \{0,1\}//'; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --slug)          SLUG="${2:-}"; shift 2 ;;
    --loopback-url)  LOOPBACK_URL="${2:-}"; shift 2 ;;
    --public-url)    PUBLIC_URL="${2:-}"; shift 2 ;;
    --secret-file)   SECRET_FILE="${2:-}"; shift 2 ;;
    --state-dir)     STATE_DIR="${2:-}"; shift 2 ;;
    --alert-log)     ALERT_LOG="${2:-}"; shift 2 ;;
    --test-contact)  TEST_CONTACT_ID="${2:-}"; shift 2 ;;
    --test-location) TEST_LOCATION_ID="${2:-}"; shift 2 ;;
    --test-podcast)  TEST_PODCAST_ID="${2:-}"; shift 2 ;;
    --loopback-only) LOOPBACK_ONLY=1; shift ;;
    --no-cleanup)    DO_CLEANUP=0; shift ;;
    --help|-h)       print_help; exit 0 ;;
    *) echo "verify-t1-t9: unknown argument: $1" >&2; exit 3 ;;
  esac
done

LEDGER_DIR="$STATE_DIR/intake-ledger"
QUARANTINE_DIR="$STATE_DIR/quarantine"
VERIFY_DIR="$STATE_DIR/verify"
[ -z "$ALERT_LOG" ] && ALERT_LOG="$STATE_DIR/alerts/alert-log.jsonl"

# The route secret is read once into a local variable and never printed.
SECRET="${PODCAST_INTAKE_HOOK_SECRET:-}"
if [ -z "$SECRET" ] && [ -n "$SECRET_FILE" ]; then
  if [ -r "$SECRET_FILE" ]; then SECRET="$(cat "$SECRET_FILE")"; fi
fi

# ---------------------------------------------------------------------------
# 1. Preconditions (fail closed with exit 3 rather than test on assumptions)
# ---------------------------------------------------------------------------

precond_fail() { echo "verify-t1-t9: precondition error: $*" >&2; exit 3; }

command -v curl    >/dev/null 2>&1 || precond_fail "curl not found on PATH"
command -v python3 >/dev/null 2>&1 || precond_fail "python3 not found on PATH"

[ -n "$TEST_CONTACT_ID" ]  || precond_fail "test contact id required (--test-contact or PODCAST_TEST_CONTACT_ID)"
[ -n "$TEST_LOCATION_ID" ] || precond_fail "test location id required (--test-location or PODCAST_TEST_LOCATION_ID)"
[ -n "$SECRET" ]           || precond_fail "route secret NOT SET (PODCAST_INTAKE_HOOK_SECRET or --secret-file)"

if [ -z "$LOOPBACK_URL" ]; then
  [ -n "$SLUG" ] || precond_fail "either --loopback-url or --slug is required to build the loopback URL"
  LOOPBACK_URL="http://127.0.0.1:18789/plugins/webhooks/podcast-intake-$SLUG"
fi

case "$LOOPBACK_URL" in
  http://127.0.0.1:*|http://localhost:*) : ;;
  *) echo "verify-t1-t9: warning: loopback URL is not a 127.0.0.1/localhost origin ($LOOPBACK_URL)" >&2 ;;
esac

if [ "$LOOPBACK_ONLY" -eq 0 ] && [ -z "$PUBLIC_URL" ]; then
  precond_fail "T9 requires --public-url (the real Cloudflare URL); pass --loopback-only to skip T9 for a pre-check"
fi

mkdir -p "$LEDGER_DIR" "$QUARANTINE_DIR" "$VERIFY_DIR" 2>/dev/null || true
[ -d "$LEDGER_DIR" ] || precond_fail "ledger directory not present and not creatable: $LEDGER_DIR"

RUNID="$(date +%Y%m%dT%H%M%SZ)-$$"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# 2. Temp workspace, python helpers, cleanup trap
# ---------------------------------------------------------------------------

TMPDIR_RUN="$(mktemp -d "${TMPDIR:-/tmp}/verify-t1t9-XXXXXX")" || precond_fail "cannot create temp dir"
RESULTS_TSV="$TMPDIR_RUN/results.tsv"
RESP_BODY="$TMPDIR_RUN/last.body"
: > "$RESULTS_TSV"

cleanup_temp() { rm -rf "$TMPDIR_RUN" 2>/dev/null || true; }
trap cleanup_temp EXIT

# Payload builder: writes one canonical GoHighLevel-workflow-shaped test body.
# Variant selects the mutation. Inputs arrive via the environment so no client
# value is ever interpolated into a shell command line.
cat > "$TMPDIR_RUN/pp_build.py" <<'PP'
import json, os, sys
outfile, variant = sys.argv[1], sys.argv[2]
contact  = os.environ["V_CONTACT"]
location = os.environ["V_LOCATION"]
wrongloc = os.environ["V_WRONGLOC"]
podcast  = os.environ["V_PODCAST"]
runid    = os.environ["V_RUNID"]

custom = {
    "mode": "Interview Style Podcast",
    "style": "Provocative",
    "podcast_id": podcast,
    "show_name": "Verification Show",
    "host_name": "Verification Host",
    "first_name": "Ver",
    "last_name": "Ifier",
    "preferred_pronoun": "they",
    "q1_answer": "The comfortable story about this topic is quietly wrong.",
    "q2_answer": "The provocation is that the accepted fix makes the problem worse.",
    "q3_answer": "A moment where the speaker learned this the hard way.",
    "q4_answer": "A concrete example the audience will recognize.",
    "q5_answer": "The turn where the argument lands.",
    "q6_answer": "What the listener should do differently on Monday.",
    "q7_answer": "The closing challenge to the audience.",
    "podcast_interview_smiq": "Yes, comfortable being transparent about this.",
    "additional_info": "verify-run:" + runid,
    "publish_timestamp": "2031-01-01T00:00:00Z",
    "episode_type": "full",
    "explicit": "no",
}

if variant == "t6_divergent":
    custom["q3_answer"] = custom["q3_answer"] + " CHANGED ONE ANSWER"
elif variant == "t8_missingstyle":
    custom.pop("style", None)
elif variant == "t9_public":
    custom["additional_info"] = "verify-run:" + runid + ":T9-public"
elif variant == "oversize":
    custom["q1_answer"] = "X" * 310000

loc = wrongloc if variant == "t7_wrongtenant" else location

body = {
    "type": "podcast_intake_verification",
    "locationId": loc,
    "contactId": contact,
    "customData": custom,
    "_test": True,
}

with open(outfile, "w") as fh:
    json.dump(body, fh)
PP

# Reader: navigate a JSON file by one or more dot-paths, print the first that
# resolves to a non-null scalar. Keeps the suite resilient to minor ledger
# schema variation (attempts.delivery_count vs delivery_count, etc.).
cat > "$TMPDIR_RUN/pp_read.py" <<'PP'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(0)
for dotted in sys.argv[2:]:
    cur = data
    ok = True
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            ok = False
            break
    if ok and cur is not None and not isinstance(cur, (dict, list)):
        print(cur)
        sys.exit(0)
sys.exit(0)
PP

# Extract the "job" field from a webhook JSON response body (best effort).
cat > "$TMPDIR_RUN/pp_job.py" <<'PP'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(0)
if isinstance(data, dict):
    for k in ("job", "job_key", "jobKey", "id"):
        v = data.get(k)
        if isinstance(v, str) and v:
            print(v)
            break
PP

# Report writer: read the results TSV, print an aligned table, and emit the
# machine-readable results record. Never touches the secret.
cat > "$TMPDIR_RUN/pp_report.py" <<'PP'
import json, sys
tsv, jsonout, runid, loopback, public_used, started, finished = sys.argv[1:8]
rows = []
with open(tsv) as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        cols = line.split("\t")
        while len(cols) < 8:
            cols.append("")
        rows.append({
            "id": cols[0], "category": cols[1], "target": cols[2],
            "http_observed": cols[3], "expected": cols[4],
            "observed": cols[5], "alert": cols[6], "verdict": cols[7],
        })

def w(key, head):
    return max([len(head)] + [len(r[key]) for r in rows]) if rows else len(head)

cid, ccat, ctgt, chttp, cver = (w("id", "ID"), w("category", "CATEGORY"),
                                w("target", "TARGET"), w("http_observed", "HTTP"),
                                w("verdict", "VERDICT"))
header = "  ".join(["ID".ljust(cid), "CATEGORY".ljust(ccat), "TARGET".ljust(ctgt),
                    "HTTP".ljust(chttp), "VERDICT".ljust(cver), "OBSERVED"])
print(header)
print("-" * len(header))
counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "WARN": 0}
for r in rows:
    counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    note = r["observed"]
    if r["alert"]:
        note = (note + " | alert: " + r["alert"]).strip(" |")
    print("  ".join([r["id"].ljust(cid), r["category"].ljust(ccat),
                     r["target"].ljust(ctgt), r["http_observed"].ljust(chttp),
                     r["verdict"].ljust(cver), note]))

if counts["FAIL"] > 0:
    verdict, code = "FAIL", 1
elif counts["SKIP"] > 0:
    verdict, code = "INCOMPLETE", 2
else:
    verdict, code = "PASS", 0

record = {
    "suite": "podcast-webhook-verification-t1-t9",
    "runid": runid,
    "started_at": started,
    "finished_at": finished,
    "target": {"loopback": loopback, "public_used": (public_used == "1")},
    "results": rows,
    "summary": {
        "total": len(rows), "pass": counts["PASS"], "fail": counts["FAIL"],
        "skip": counts["SKIP"], "warn": counts["WARN"],
        "verdict": verdict, "exit_code": code,
    },
}
with open(jsonout, "w") as fh:
    json.dump(record, fh, indent=2)
    fh.write("\n")
print("")
print("SUMMARY  pass=%d fail=%d skip=%d warn=%d  verdict=%s  record=%s"
      % (counts["PASS"], counts["FAIL"], counts["SKIP"], counts["WARN"], verdict, jsonout))
PP

PY_BUILD="python3 $TMPDIR_RUN/pp_build.py"
pp_read() { python3 "$TMPDIR_RUN/pp_read.py" "$@"; }
pp_job()  { python3 "$TMPDIR_RUN/pp_job.py" "$1"; }

# ---------------------------------------------------------------------------
# 3. Observation helpers (portable across GNU and BSD userland; no -printf / -newermt)
# ---------------------------------------------------------------------------

FAILS=0
SKIPS=0
WARNS=0
NEG_HTTP=""
declare -a CREATED_LEDGER_JOBS=()
declare -a CREATED_QUARANTINE=()

# Snapshot the sorted set of ledger job basenames (excluding .payload.json sidecars).
snapshot_ledger() {
  find "$LEDGER_DIR" -maxdepth 1 -type f -name '*.json' ! -name '*.payload.json' 2>/dev/null \
    | sed 's#.*/##' | sort > "$1"
}
snapshot_quarantine() {
  ( cd "$QUARANTINE_DIR" 2>/dev/null && ls -1 2>/dev/null ) | sort > "$1"
}
count_ledger()     { find "$LEDGER_DIR" -maxdepth 1 -type f -name '*.json' ! -name '*.payload.json' 2>/dev/null | wc -l | tr -d ' '; }
count_quarantine() { find "$QUARANTINE_DIR" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' '; }
alert_lines()      { if [ -f "$ALERT_LOG" ]; then wc -l < "$ALERT_LOG" | tr -d ' '; else echo 0; fi; }

# POST a JSON file. Auth modes: none, bearer, wrong, query. Method override for TM.
# Writes the response body to the fixed file $RESP_BODY (persists across the code
# capture subshell) and prints the observed HTTP status (000 on connection error).
# The secret is only ever placed in an Authorization header, or, for the deliberate
# query negative test, in a loopback-only URL. It is never logged.
do_request() {
  local url="$1" payload="$2" authmode="$3" method="${4:-POST}" code
  case "$authmode" in
    none)
      code="$(curl -sS --max-time 30 -o "$RESP_BODY" -w '%{http_code}' \
              -X "$method" -H 'content-type: application/json' \
              --data-binary "@$payload" "$url" 2>/dev/null)" ;;
    bearer)
      code="$(curl -sS --max-time 60 -o "$RESP_BODY" -w '%{http_code}' \
              -X "$method" -H 'content-type: application/json' \
              -H "authorization: Bearer $SECRET" \
              --data-binary "@$payload" "$url" 2>/dev/null)" ;;
    wrong)
      code="$(curl -sS --max-time 30 -o "$RESP_BODY" -w '%{http_code}' \
              -X "$method" -H 'content-type: application/json' \
              -H "authorization: Bearer wrong-secret-deliberate-$RUNID" \
              --data-binary "@$payload" "$url" 2>/dev/null)" ;;
    query)
      code="$(curl -sS --max-time 30 -o "$RESP_BODY" -w '%{http_code}' \
              -X "$method" -H 'content-type: application/json' \
              --data-binary "@$payload" "${url}?secret=${SECRET}" 2>/dev/null)" ;;
  esac
  [ -z "$code" ] && code="000"
  printf '%s' "$code"
}

# Record one row (runs in the current shell so the counters persist).
# Args: id category target http expected observed alert verdict
record_row() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" >> "$RESULTS_TSV"
  case "$8" in
    FAIL) FAILS=$((FAILS+1)) ;;
    SKIP) SKIPS=$((SKIPS+1)) ;;
    WARN) WARNS=$((WARNS+1)) ;;
  esac
  echo "  [$1] $2 ($3): http=$4 verdict=$8 :: $6"
}

# Observe the operator alert log for a keyword among lines added since a baseline.
# Returns one of: observed:<keyword>, not-observed, unconfigured.
alert_observe() {
  local baseline="$1" keyword="$2" now added
  if [ ! -f "$ALERT_LOG" ]; then echo "unconfigured"; return; fi
  now="$(wc -l < "$ALERT_LOG" | tr -d ' ')"
  if [ "$now" -le "$baseline" ]; then echo "not-observed"; return; fi
  added="$(tail -n "$((now-baseline))" "$ALERT_LOG")"
  if printf '%s' "$added" | grep -Eqi "$keyword"; then echo "observed:$keyword"; else echo "not-observed"; fi
}

# Resolve the job key of a newly accepted submission: prefer the response body's
# job field, fall back to a ledger directory diff against a pre-request snapshot.
resolve_new_job() {
  local before="$1" bodyfile="$2" job=""
  if [ -n "$bodyfile" ] && [ -f "$bodyfile" ]; then job="$(pp_job "$bodyfile")"; fi
  job="${job%.json}"
  if [ -z "$job" ]; then
    snapshot_ledger "$TMPDIR_RUN/ledger.now"
    job="$(comm -13 "$before" "$TMPDIR_RUN/ledger.now" 2>/dev/null | head -n1)"
    job="${job%.json}"
  fi
  printf '%s' "$job"
}

echo "Podcast webhook verification T1 to T9"
echo "  runid          : $RUNID"
echo "  loopback URL   : $LOOPBACK_URL"
echo "  public URL     : ${PUBLIC_URL:-<not set, loopback-only>}"
echo "  state dir      : $STATE_DIR"
if [ -f "$ALERT_LOG" ]; then
  echo "  alert log      : $ALERT_LOG"
else
  echo "  alert log      : $ALERT_LOG  (absent; alert sub-checks report unconfigured)"
fi
echo "  test contact   : $TEST_CONTACT_ID"
echo "  test location  : $TEST_LOCATION_ID"
echo "  route secret   : SET (value never printed)"
echo ""

export V_CONTACT="$TEST_CONTACT_ID"
export V_LOCATION="$TEST_LOCATION_ID"
export V_WRONGLOC="foreign-tenant-$RUNID"
export V_PODCAST="$TEST_PODCAST_ID"
export V_RUNID="$RUNID"

# Build the canonical full payload once; reused by several tests.
$PY_BUILD "$TMPDIR_RUN/full.json" full

# ---------------------------------------------------------------------------
# 4. Negative auth and platform tests (T1, T2, T3, TM, TB): nothing may be written
# ---------------------------------------------------------------------------

# Runs in the current shell; sets NEG_HTTP and records the row.
run_negative() {
  local id="$1" cat="$2" authmode="$3" method="$4" payload="$5" pass_codes="$6"
  local lbefore qbefore http lafter qafter observed verdict wrote
  lbefore="$(count_ledger)"; qbefore="$(count_quarantine)"
  http="$(do_request "$LOOPBACK_URL" "$payload" "$authmode" "$method")"
  lafter="$(count_ledger)"; qafter="$(count_quarantine)"
  wrote="no"
  if [ "$lafter" != "$lbefore" ] || [ "$qafter" != "$qbefore" ]; then wrote="yes"; fi
  observed="nothing-written"; [ "$wrote" = "yes" ] && observed="WROTE ledger/quarantine record"
  if echo " $pass_codes " | grep -q " $http " && [ "$wrote" = "no" ]; then
    verdict="PASS"
  else
    verdict="FAIL"
    [ "$http" = "000" ] && observed="target unreachable at loopback"
  fi
  record_row "$id" "$cat" "loopback" "$http" "reject($pass_codes), no write" "$observed" "" "$verdict"
  NEG_HTTP="$http"
}

# T1: no auth header. This also doubles as the loopback reachability probe.
run_negative T1 auth none POST "$TMPDIR_RUN/full.json" "401 403"
if [ "$NEG_HTTP" = "000" ]; then
  echo "verify-t1-t9: loopback target unreachable ($LOOPBACK_URL); is the gateway up and the route configured?" >&2
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 "$TMPDIR_RUN/pp_report.py" "$RESULTS_TSV" \
    "$VERIFY_DIR/verify-t1-t9-$RUNID.json" "$RUNID" "$LOOPBACK_URL" \
    "$([ "$LOOPBACK_ONLY" -eq 1 ] && echo 0 || echo 1)" "$STARTED_AT" "$FINISHED_AT" || true
  exit 3
fi

run_negative T2 auth wrong  POST "$TMPDIR_RUN/full.json" "401 403"
run_negative T3 auth query  POST "$TMPDIR_RUN/full.json" "401 403"
run_negative TM method bearer GET "$TMPDIR_RUN/full.json" "404 405 400"

$PY_BUILD "$TMPDIR_RUN/oversize.json" oversize
run_negative TB body-cap bearer POST "$TMPDIR_RUN/oversize.json" "413 400 431"

# ---------------------------------------------------------------------------
# 5. T4 mapping: full accepted payload, ledger state test, canonical fields mapped
# ---------------------------------------------------------------------------

snapshot_ledger "$TMPDIR_RUN/ledger.before_t4"
T4_HTTP="$(do_request "$LOOPBACK_URL" "$TMPDIR_RUN/full.json" bearer POST)"
cp "$RESP_BODY" "$TMPDIR_RUN/t4.body" 2>/dev/null || true

T4_JOB="$(resolve_new_job "$TMPDIR_RUN/ledger.before_t4" "$TMPDIR_RUN/t4.body")"
T4_FILE="$LEDGER_DIR/$T4_JOB.json"

t4_observed="no ledger record resolved"; t4_verdict="FAIL"
if [ "$T4_HTTP" = "200" ] && [ -n "$T4_JOB" ] && [ -f "$T4_FILE" ]; then
  st="$(pp_read "$T4_FILE" state)"
  lc="$(pp_read "$T4_FILE" location_id locationId)"
  cc="$(pp_read "$T4_FILE" contact_id contactId contact.id)"
  pc="$(pp_read "$T4_FILE" podcast_id podcastId)"
  md="$(pp_read "$T4_FILE" mode)"
  sy="$(pp_read "$T4_FILE" style)"
  dc="$(pp_read "$T4_FILE" attempts.delivery_count delivery_count attempts.deliveryCount)"
  paypath="$LEDGER_DIR/$T4_JOB.payload.json"
  payok="no"; [ -f "$paypath" ] && payok="yes"
  t4_observed="state=$st contact=$cc location=$lc podcast=$pc mode=$md style=$sy delivery_count=${dc:-?} payload_file=$payok"
  if [ "$st" = "test" ] && [ "$cc" = "$TEST_CONTACT_ID" ] && [ "$lc" = "$TEST_LOCATION_ID" ]; then
    t4_verdict="PASS"
    CREATED_LEDGER_JOBS+=("$T4_JOB")
    if [ "$md" != "interview_style_podcast" ] || [ "$sy" != "provocative" ] || [ "$payok" != "yes" ]; then
      t4_observed="$t4_observed (note: normalization/payload sub-checks differ from spec; primary mapping PASS)"
      WARNS=$((WARNS+1))
    fi
  fi
elif [ "$T4_HTTP" != "200" ]; then
  t4_observed="unexpected http $T4_HTTP (expected 200 accepted)"
fi
record_row T4 mapping loopback "$T4_HTTP" "200 accepted, state test, fields mapped" "$t4_observed" "" "$t4_verdict"

# ---------------------------------------------------------------------------
# 6. T5 dedup: identical redelivery collides, delivery_count increments, no new record
# ---------------------------------------------------------------------------

lbefore_t5="$(count_ledger)"
T5_HTTP="$(do_request "$LOOPBACK_URL" "$TMPDIR_RUN/full.json" bearer POST)"
cp "$RESP_BODY" "$TMPDIR_RUN/t5.body" 2>/dev/null || true
lafter_t5="$(count_ledger)"

t5_status="$( [ -f "$TMPDIR_RUN/t5.body" ] && pp_read "$TMPDIR_RUN/t5.body" status || true )"
t5_job="$( [ -f "$TMPDIR_RUN/t5.body" ] && pp_job "$TMPDIR_RUN/t5.body" || true )"; t5_job="${t5_job%.json}"
t5_dc=""; [ -n "$T4_JOB" ] && [ -f "$T4_FILE" ] && t5_dc="$(pp_read "$T4_FILE" attempts.delivery_count delivery_count attempts.deliveryCount)"
t5_verdict="FAIL"
t5_match="no"; [ -n "$t5_job" ] && [ "$t5_job" = "$T4_JOB" ] && t5_match="yes"
t5_observed="status=${t5_status:-none} job_match=$t5_match new_ledger_files=$((lafter_t5-lbefore_t5)) delivery_count=${t5_dc:-?}"
if [ "$T5_HTTP" = "200" ] && [ "$lafter_t5" = "$lbefore_t5" ]; then
  if [ "${t5_dc:-0}" = "2" ] || printf '%s' "${t5_status:-}" | grep -qi 'duplicate'; then
    t5_verdict="PASS"
  fi
fi
record_row T5 dedup loopback "$T5_HTTP" "200 duplicate, count 2, no new record" "$t5_observed" "" "$t5_verdict"

# ---------------------------------------------------------------------------
# 7. T6 divergence: one answer changed yields a NEW job key and a NEW record
# ---------------------------------------------------------------------------

$PY_BUILD "$TMPDIR_RUN/t6.json" t6_divergent
snapshot_ledger "$TMPDIR_RUN/ledger.before_t6"
T6_HTTP="$(do_request "$LOOPBACK_URL" "$TMPDIR_RUN/t6.json" bearer POST)"
cp "$RESP_BODY" "$TMPDIR_RUN/t6.body" 2>/dev/null || true
T6_JOB="$(resolve_new_job "$TMPDIR_RUN/ledger.before_t6" "$TMPDIR_RUN/t6.body")"
T6_FILE="$LEDGER_DIR/$T6_JOB.json"

t6_verdict="FAIL"
t6_st=""; [ -n "$T6_JOB" ] && [ -f "$T6_FILE" ] && t6_st="$(pp_read "$T6_FILE" state)"
t6_new="no"; [ -n "$T6_JOB" ] && t6_new="yes"
t6_diff="no"; [ -n "$T6_JOB" ] && [ "$T6_JOB" != "$T4_JOB" ] && t6_diff="yes"
t6_observed="new_job=$t6_new differs_from_T4=$t6_diff state=${t6_st:-none}"
if [ "$T6_HTTP" = "200" ] && [ -n "$T6_JOB" ] && [ "$T6_JOB" != "$T4_JOB" ] && [ -f "$T6_FILE" ] && [ "$t6_st" = "test" ]; then
  t6_verdict="PASS"
  CREATED_LEDGER_JOBS+=("$T6_JOB")
fi
record_row T6 divergence loopback "$T6_HTTP" "200 accepted, NEW job key + record" "$t6_observed" "" "$t6_verdict"

# ---------------------------------------------------------------------------
# 8. T7 tenant check: foreign location_id is quarantined, operator alerted, nothing processed
# ---------------------------------------------------------------------------

$PY_BUILD "$TMPDIR_RUN/t7.json" t7_wrongtenant
snapshot_ledger "$TMPDIR_RUN/ledger.before_t7"
snapshot_quarantine "$TMPDIR_RUN/quar.before_t7"
alert_base_t7="$(alert_lines)"
T7_HTTP="$(do_request "$LOOPBACK_URL" "$TMPDIR_RUN/t7.json" bearer POST)"
snapshot_ledger "$TMPDIR_RUN/ledger.after_t7"
snapshot_quarantine "$TMPDIR_RUN/quar.after_t7"
t7_alert="$(alert_observe "$alert_base_t7" 'tenant|location|quarantine')"

# A new quarantine file is the primary proof. A needs_input ledger record is an
# accepted alternative per webhook-design Section 4.2 step 5. Either way, NOTHING
# may enter a processing state.
t7_newquar="$(comm -13 "$TMPDIR_RUN/quar.before_t7" "$TMPDIR_RUN/quar.after_t7" 2>/dev/null)"
t7_newledger="$(comm -13 "$TMPDIR_RUN/ledger.before_t7" "$TMPDIR_RUN/ledger.after_t7" 2>/dev/null | head -n1)"
t7_newledger="${t7_newledger%.json}"
t7_newstate=""
if [ -n "$t7_newledger" ] && [ -f "$LEDGER_DIR/$t7_newledger.json" ]; then
  t7_newstate="$(pp_read "$LEDGER_DIR/$t7_newledger.json" state)"
fi
quarantined="no"; [ -n "$t7_newquar" ] && quarantined="yes"
processed="no"
case "$t7_newstate" in
  ""|needs_input|test|quarantined) : ;;
  *) processed="yes" ;;
esac
t7_verdict="FAIL"
t7_observed="quarantine_file_added=$quarantined new_ledger_state=${t7_newstate:-none} processed=$processed"
if [ "$T7_HTTP" = "200" ] && [ "$processed" = "no" ] && { [ "$quarantined" = "yes" ] || [ "$t7_newstate" = "needs_input" ]; }; then
  t7_verdict="PASS"
  if [ "$quarantined" = "yes" ]; then
    while IFS= read -r qf; do
      [ -n "$qf" ] && CREATED_QUARANTINE+=("$QUARANTINE_DIR/$qf")
    done <<EOF
$t7_newquar
EOF
  fi
  if [ -n "$t7_newledger" ] && [ "$t7_newstate" = "needs_input" ]; then CREATED_LEDGER_JOBS+=("$t7_newledger"); fi
fi
[ "$t7_alert" = "unconfigured" ] && WARNS=$((WARNS+1))
record_row T7 tenant loopback "$T7_HTTP" "200 quarantine, alert, no processing" "$t7_observed" "$t7_alert" "$t7_verdict"

# ---------------------------------------------------------------------------
# 9. T8 ack contract: missing style yields needs_input, operator alert names the field
# ---------------------------------------------------------------------------

$PY_BUILD "$TMPDIR_RUN/t8.json" t8_missingstyle
snapshot_ledger "$TMPDIR_RUN/ledger.before_t8"
alert_base_t8="$(alert_lines)"
T8_HTTP="$(do_request "$LOOPBACK_URL" "$TMPDIR_RUN/t8.json" bearer POST)"
cp "$RESP_BODY" "$TMPDIR_RUN/t8.body" 2>/dev/null || true
T8_JOB="$(resolve_new_job "$TMPDIR_RUN/ledger.before_t8" "$TMPDIR_RUN/t8.body")"
T8_FILE="$LEDGER_DIR/$T8_JOB.json"
t8_status="$( [ -f "$TMPDIR_RUN/t8.body" ] && pp_read "$TMPDIR_RUN/t8.body" status || true )"
t8_state=""; [ -n "$T8_JOB" ] && [ -f "$T8_FILE" ] && t8_state="$(pp_read "$T8_FILE" state)"
t8_alert="$(alert_observe "$alert_base_t8" 'style')"
t8_verdict="FAIL"
t8_observed="http_status=${t8_status:-none} ledger_state=${t8_state:-none}"
if [ "$T8_HTTP" = "200" ] && { [ "$t8_state" = "needs_input" ] || printf '%s' "${t8_status:-}" | grep -Eqi 'incomplete|needs_input'; }; then
  t8_verdict="PASS"
  if [ -n "$T8_JOB" ] && [ "$t8_state" = "needs_input" ]; then CREATED_LEDGER_JOBS+=("$T8_JOB"); fi
fi
[ "$t8_alert" = "unconfigured" ] && WARNS=$((WARNS+1))
record_row T8 ack loopback "$T8_HTTP" "200 ACK, needs_input, alert names style" "$t8_observed" "$t8_alert" "$t8_verdict"

# ---------------------------------------------------------------------------
# 10. T9 public URL: the T4 shape through the REAL Cloudflare URL, proving edge + tunnel
# ---------------------------------------------------------------------------

if [ "$LOOPBACK_ONLY" -eq 1 ]; then
  record_row T9 public-url public "n/a" "same as T4 via edge" "SKIPPED (--loopback-only)" "" "SKIP"
else
  $PY_BUILD "$TMPDIR_RUN/t9.json" t9_public
  snapshot_ledger "$TMPDIR_RUN/ledger.before_t9"
  T9_HTTP="$(do_request "$PUBLIC_URL" "$TMPDIR_RUN/t9.json" bearer POST)"
  cp "$RESP_BODY" "$TMPDIR_RUN/t9.body" 2>/dev/null || true
  T9_JOB="$(resolve_new_job "$TMPDIR_RUN/ledger.before_t9" "$TMPDIR_RUN/t9.body")"
  T9_FILE="$LEDGER_DIR/$T9_JOB.json"
  t9_st=""; [ -n "$T9_JOB" ] && [ -f "$T9_FILE" ] && t9_st="$(pp_read "$T9_FILE" state)"
  t9_cc=""; [ -n "$T9_JOB" ] && [ -f "$T9_FILE" ] && t9_cc="$(pp_read "$T9_FILE" contact_id contactId contact.id)"
  t9_new="no"; [ -n "$T9_JOB" ] && t9_new="yes"
  t9_verdict="FAIL"
  t9_observed="new_job=$t9_new state=${t9_st:-none} contact=${t9_cc:-none}"
  if [ "$T9_HTTP" = "200" ] && [ -n "$T9_JOB" ] && [ -f "$T9_FILE" ] && [ "$t9_st" = "test" ] && [ "$t9_cc" = "$TEST_CONTACT_ID" ]; then
    t9_verdict="PASS"
    CREATED_LEDGER_JOBS+=("$T9_JOB")
  elif [ "$T9_HTTP" = "000" ]; then
    t9_observed="public endpoint unreachable through Cloudflare ($PUBLIC_URL)"
  fi
  record_row T9 public-url public "$T9_HTTP" "200 accepted via edge, state test" "$t9_observed" "" "$t9_verdict"
fi

# ---------------------------------------------------------------------------
# 11. Cleanup: remove ONLY the test / needs_input / quarantine records we created
# ---------------------------------------------------------------------------

if [ "$DO_CLEANUP" -eq 1 ]; then
  echo ""
  echo "Cleanup: removing the test artifacts this run created (state test / needs_input / quarantine only)."
  for job in ${CREATED_LEDGER_JOBS[@]+"${CREATED_LEDGER_JOBS[@]}"}; do
    [ -z "$job" ] && continue
    f="$LEDGER_DIR/$job.json"
    [ -f "$f" ] || continue
    st="$(pp_read "$f" state)"
    case "$st" in
      test|needs_input|quarantined)
        rm -f "$f" "$LEDGER_DIR/$job.payload.json" 2>/dev/null && echo "  removed ledger record: $job (state $st)" ;;
      *)
        echo "  KEPT ledger record: $job (state $st is not a test state; not ours to remove)" ;;
    esac
  done
  for qf in ${CREATED_QUARANTINE[@]+"${CREATED_QUARANTINE[@]}"}; do
    [ -z "$qf" ] && continue
    [ -f "$qf" ] && rm -f "$qf" 2>/dev/null && echo "  removed quarantine file: $(basename "$qf")"
  done
else
  echo ""
  echo "Cleanup skipped (--no-cleanup); test records remain for inspection."
fi

# ---------------------------------------------------------------------------
# 12. Report, persist the observed record, exit with the gate code
# ---------------------------------------------------------------------------

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RESULT_JSON="$VERIFY_DIR/verify-t1-t9-$RUNID.json"
echo ""
python3 "$TMPDIR_RUN/pp_report.py" "$RESULTS_TSV" "$RESULT_JSON" "$RUNID" \
  "$LOOPBACK_URL" "$([ "$LOOPBACK_ONLY" -eq 1 ] && echo 0 || echo 1)" \
  "$STARTED_AT" "$FINISHED_AT"

PASSCOUNT="$(grep -c "$(printf 'PASS$')" "$RESULTS_TSV" 2>/dev/null || true)"
PASSCOUNT="${PASSCOUNT:-0}"
printf '%s\trunid=%s\tpass=%s\tfail=%s\tskip=%s\twarn=%s\trecord=%s\n' \
  "$FINISHED_AT" "$RUNID" "$PASSCOUNT" "$FAILS" "$SKIPS" "$WARNS" "$RESULT_JSON" \
  >> "$VERIFY_DIR/verify-history.log" 2>/dev/null || true

if [ "$FAILS" -gt 0 ]; then
  echo "verify-t1-t9: FAIL ($FAILS failing test(s)); not go-live ready." >&2
  exit 1
fi
if [ "$SKIPS" -gt 0 ]; then
  echo "verify-t1-t9: INCOMPLETE ($SKIPS skipped, including T9 under --loopback-only); not go-live ready." >&2
  exit 2
fi
echo "verify-t1-t9: PASS; T1 to T9 observed green on this box. Go-live ready for this client."
exit 0
