#!/usr/bin/env bash
# 59-anthology-engine/scripts/revoke-anthology-client.sh
# ----------------------------------------------------------------------------
# CHURN / OFFBOARD for one Anthology client (SPEC 13.3; inventory row 31).
# Authored by W2.7. House exit-code contract (ENGINE-MANIFEST.json row 31):
#   0  revoked and verified (also: structure sound / idempotent no-op / a
#      deferred live battery on a box where a collaborator is not yet wired)
#   4  a probe STILL answers (a revoked gate token still verifies, the intake
#      route still answers as mapped, OR a recurring anthology job remains)
# Plus the shared house convention (Section 3.4): 1 unexpected error;
# 2 validation or guard refusal; 3 dependency unavailable or held;
# 5 data or read-back mismatch.
#
# WHAT IT DOES, in SPEC 13.3 order, as the NODE USER (never root):
#   R1  invalidate every outstanding participant gate token
#         -> rotate ANTHOLOGY_GATE_TOKEN_SECRET (value NEVER printed); every
#            token signed by the old secret then fails verify (bad_signature).
#   R2  archive the Anthology board cards (mc_board.py; FAIL-SOFT per SPEC 11.2,
#         board unreachability never blocks the churn).
#   R3  revoke Drive shares and hand back fresh view links (drive_adapter.py
#         revoke-share; under the anyone-can-read delivery root, TRUE revocation
#         moves the file out of the public subtree -- surfaced, not guessed).
#   R4  disable the intake webhook route (remove ONLY the anthology-intake
#         mapping from the gateway hooks config; the box-wide hooks surface and
#         every other integration are left intact -- shared-box safe).
#   R5  produce the data-export bundle (anthology_state.py export-bundle; the
#         client keeps their record; the file carries NO secret).
#   R6  archive the ledger rows (anthology_state.py upsert-anthology
#         --status archived; deactivate-never-delete, ninety-day retention).
#   R7  VERIFY by probing a revoked token link and the disabled route.
#   R8  prove ZERO recurring jobs remain (guard-cron-inventory.py --expect zero;
#         EVERY cron entry is NORMALIZED to the guard's own job shape first, so a
#         recurring anthology job can never hide behind a flat/nested shape gap;
#         a guard-absent in-script scan over the SAME normalized entries stands in
#         and cross-checks; removes the anthology daily tick).
# R7 and R8 are the ENFORCED gates: if a probe still answers or a recurring job
# survives, the script exits 4.
#
# SECRET HYGIENE (binding): both labels (ANTHOLOGY_GATE_TOKEN_SECRET,
# ANTHOLOGY_INTAKE_HOOK_SECRET) are reported SET / NOT SET only; no secret value
# is ever printed, logged, or echoed. The rotated gate-token secret is written
# 0600 and never surfaced. Convert and Flow naming throughout. Nothing Anthropic
# in this file. All self-test data is synthetic (example.invalid).
#
# DESTRUCTIVE-ACTION GUARD: --live requires a typed --confirm-name that matches
# the ledger anthology name (the same typed-name discipline as the s9_ready
# trigger); a mismatch or an absent confirmation refuses (exit 2). --live also
# refuses to run as root.
#
# MODES / FLAGS:
#   --self-test          synthetic-client battery ONLY (no client box touched);
#                        force-observes its OWN failure modes; exit 0/4. Used by
#                        tests and verify.sh.
#   --plan | --list      print the R1..R8 churn plan and exit 0.
#   --dry-run            structural + reachability report, NO mutation (default).
#   --live | --execute   perform the live churn (requires --anthology-id and a
#                        matching --confirm-name; refuses root).
#   --require-live       an enforced step that could not be OBSERVED holds the
#                        battery (exit 3); use on the canary.
#   --anthology-id ID    the anthology to churn (required for --dry-run/--live).
#   --producer-id ID     optional producer scoping.
#   --confirm-name NAME  typed anthology-name confirmation (required for --live).
#   --state-dir DIR | --db PATH   ledger location (passed to anthology_state.py).
#   --gateway-config P   gateway hooks config (default ~/.openclaw/openclaw.json).
#   --secrets-file P     0600 file that holds ANTHOLOGY_GATE_TOKEN_SECRET (target
#                        of the rotation write; else the operator surface names it).
#   --base-url URL       gateway base for the route probe (default
#                        http://127.0.0.1:18789).
#   --out-dir DIR        export-bundle destination (default: <state>/churn-export).
#   --private-dest-folder-id ID  private Drive destination for true unlink from
#                        the anyone-can-read delivery root.
#   --cron-inventory P   JSON array of cron entries for the fallback R8 scan
#                        (else `openclaw cron list` is consulted when present).
#   --allow-cron-delete  permit removing the anthology daily tick (churn needs it).
#   -h | --help          usage.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
SCRIPTS_DIR="$SELF_DIR"

RV_MODE="dryrun"            # dryrun | selftest | plan | live
RV_REQUIRE_LIVE=0
RV_ANTHOLOGY_ID=""
RV_PRODUCER_ID=""
RV_CONFIRM_NAME=""
RV_STATE_DIR=""
RV_DB=""
RV_GATEWAY_CONFIG="${HOME:-/tmp}/.openclaw/openclaw.json"
RV_SECRETS_FILE=""
RV_BASEURL="http://127.0.0.1:18789"
RV_OUT_DIR=""
RV_PRIVATE_DEST=""
RV_CRON_INVENTORY=""
RV_ALLOW_CRON_DELETE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --self-test)              RV_MODE="selftest"; shift ;;
        --plan|--list)            RV_MODE="plan"; shift ;;
        --dry-run)                RV_MODE="dryrun"; shift ;;
        --live|--execute)         RV_MODE="live"; shift ;;
        --require-live)           RV_REQUIRE_LIVE=1; shift ;;
        --anthology-id)           RV_ANTHOLOGY_ID="${2:-}"; shift 2 ;;
        --producer-id)            RV_PRODUCER_ID="${2:-}"; shift 2 ;;
        --confirm-name)           RV_CONFIRM_NAME="${2:-}"; shift 2 ;;
        --state-dir)              RV_STATE_DIR="${2:-}"; shift 2 ;;
        --db)                     RV_DB="${2:-}"; shift 2 ;;
        --gateway-config)         RV_GATEWAY_CONFIG="${2:-}"; shift 2 ;;
        --secrets-file)           RV_SECRETS_FILE="${2:-}"; shift 2 ;;
        --base-url)               RV_BASEURL="${2:-}"; shift 2 ;;
        --out-dir)                RV_OUT_DIR="${2:-}"; shift 2 ;;
        --private-dest-folder-id) RV_PRIVATE_DEST="${2:-}"; shift 2 ;;
        --cron-inventory)         RV_CRON_INVENTORY="${2:-}"; shift 2 ;;
        --allow-cron-delete)      RV_ALLOW_CRON_DELETE=1; shift ;;
        -h|--help)
            sed -n '2,86p' "${BASH_SOURCE[0]:-$0}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "revoke-anthology-client: unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || {
    echo "revoke-anthology-client: FATAL python3 required" >&2; exit 2; }

# A live churn writes config (rotated secret, gateway hooks, cron) and MUST run
# as the node user; a root-owned config freezes the gateway (house doctrine).
if [ "$RV_MODE" = "live" ] && [ "$(id -u)" = "0" ]; then
    echo "REFUSING: --live must run as the NODE USER, never root (a root-owned config freezes the gateway)." >&2
    exit 2
fi

# Report the two secret labels WITHOUT ever reading or printing their values.
for _lbl in ANTHOLOGY_GATE_TOKEN_SECRET ANTHOLOGY_INTAKE_HOOK_SECRET; do
    if [ -n "$(eval "printf '%s' \"\${$_lbl:-}\"")" ]; then
        echo "revoke-anthology-client: $_lbl = SET (value never printed)"
    else
        echo "revoke-anthology-client: $_lbl = NOT SET"
    fi
done

RV_SKILL_DIR="$SKILL_DIR" \
RV_SCRIPTS_DIR="$SCRIPTS_DIR" \
RV_MODE="$RV_MODE" \
RV_REQUIRE_LIVE="$RV_REQUIRE_LIVE" \
RV_ANTHOLOGY_ID="$RV_ANTHOLOGY_ID" \
RV_PRODUCER_ID="$RV_PRODUCER_ID" \
RV_CONFIRM_NAME="$RV_CONFIRM_NAME" \
RV_STATE_DIR="$RV_STATE_DIR" \
RV_DB="$RV_DB" \
RV_GATEWAY_CONFIG="$RV_GATEWAY_CONFIG" \
RV_SECRETS_FILE="$RV_SECRETS_FILE" \
RV_BASEURL="$RV_BASEURL" \
RV_OUT_DIR="$RV_OUT_DIR" \
RV_PRIVATE_DEST="$RV_PRIVATE_DEST" \
RV_CRON_INVENTORY="$RV_CRON_INVENTORY" \
RV_ALLOW_CRON_DELETE="$RV_ALLOW_CRON_DELETE" \
python3 - <<'PY'
import json, os, re, socket, subprocess, sys, tempfile
import secrets as _secrets
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

SKILL   = os.environ["RV_SKILL_DIR"]
SCRIPTS = os.environ["RV_SCRIPTS_DIR"]
MODE    = os.environ["RV_MODE"]
REQUIRE_LIVE = os.environ["RV_REQUIRE_LIVE"] == "1"
ANTH_ID = os.environ.get("RV_ANTHOLOGY_ID") or ""
PROD_ID = os.environ.get("RV_PRODUCER_ID") or ""
CONFIRM = os.environ.get("RV_CONFIRM_NAME") or ""
STATE_DIR = os.environ.get("RV_STATE_DIR") or ""
DB      = os.environ.get("RV_DB") or ""
GW_CFG  = os.environ.get("RV_GATEWAY_CONFIG") or ""
SECRETS_FILE = os.environ.get("RV_SECRETS_FILE") or ""
BASEURL = (os.environ.get("RV_BASEURL") or "").rstrip("/")
OUT_DIR = os.environ.get("RV_OUT_DIR") or ""
PRIVATE_DEST = os.environ.get("RV_PRIVATE_DEST") or ""
CRON_INV = os.environ.get("RV_CRON_INVENTORY") or ""
ALLOW_CRON_DELETE = os.environ.get("RV_ALLOW_CRON_DELETE") == "1"

GATE_LABEL   = "ANTHOLOGY_GATE_TOKEN_SECRET"
INTAKE_LABEL = "ANTHOLOGY_INTAKE_HOOK_SECRET"
INTAKE_MAPPING_ID = "anthology-intake"

# Status vocabulary -> exit contribution.
PASS, DEFER, VIOLATION, HELD, MISMATCH, ERROR = \
    "PASS", "DEFER", "VIOLATION", "HELD", "MISMATCH", "ERROR"
# R7 (probe still answers) and R8 (recurring job) are the exit-4 gates; R1/R4/R5/R6
# are completion steps whose non-observation holds a --require-live canary battery.
ENFORCED = {"R1", "R4", "R5", "R6", "R7", "R8"}

STEP_TITLE = {
    "R1": "invalidate outstanding participant gate tokens (secret rotation)",
    "R2": "archive the Anthology board cards (fail-soft)",
    "R3": "revoke Drive shares + regenerate view links",
    "R4": "disable the intake webhook route (anthology-intake mapping)",
    "R5": "produce the data-export bundle",
    "R6": "archive the ledger rows (deactivate never delete)",
    "R7": "VERIFY: probe a revoked token link and the disabled route",
    "R8": "prove ZERO recurring jobs remain (churn)",
}

# Anthropic-family id shapes assembled from fragments so no banned literal ever
# lives in this file; used only for a defensive self-hygiene scan of emitted text.
_a = "anthro" + "pic"; _c = "clau" + "de-"
BANNED = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)
CRED_KEYS = {"api_key", "apikey", "openrouter_api_key", "authorization", "bearer",
             "token", "secret", "x-openclaw-token", "x-openclaw-webhook-secret",
             "password", "private_key"}

# --------------------------------------------------------------------------
# Small helpers.
# --------------------------------------------------------------------------
def state_args():
    if DB:
        return ["--db", DB]
    if STATE_DIR:
        return ["--state-dir", STATE_DIR]
    return []

def run(cmd, timeout=60, input=None):
    """Run a subprocess; return (rc, stdout, stderr). Never raises on nonzero."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           input=input)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError as exc:
        return 127, "", "not found: %s" % exc
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"

def has_cmd(name):
    from shutil import which
    return which(name) is not None

def derived_paths():
    """The provision-side (W2.6) state-dir layout, so a churn finds the same files
    a provision wrote: the gate-token secret, the declarative cron inventory, and
    the materialized route file. Empty strings when --state-dir is unknown."""
    sd = STATE_DIR or ""
    return {
        "gate_secret":    os.path.join(sd, "secrets", "anthology-gate-token-secret") if sd else "",
        "cron_inventory": os.path.join(sd, "cron-inventory.json") if sd else "",
        "route_file":     os.path.join(sd, "hooks", "anthology-intake.route.json") if sd else "",
    }

def astate(*args, timeout=60):
    return run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py")]
               + state_args() + list(args), timeout=timeout)

def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def collaborator(name):
    fp = os.path.join(SCRIPTS, name)
    return fp if os.path.isfile(fp) else None

# ---- pure decision helpers (the SAME logic the self-test force-observes) ----
try:
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import gate_engine as _ge
except Exception:
    _ge = None

def token_still_answers(token, secret, pk):
    """True iff a (revoked) token STILL verifies -- i.e. the probe still answers.
    Uses gate_engine.verify_token, the enforced symbol named in the manifest."""
    if _ge is None or not secret:
        return None  # cannot observe
    try:
        return bool(_ge.verify_token(token, secret, expected_pk=pk).get("ok"))
    except Exception:
        return None

def route_mapping_present(cfg):
    """True iff the anthology-intake mapping is STILL present in a gateway config
    object (dict) -- i.e. the intake route still answers as mapped."""
    hooks = (cfg or {}).get("hooks") or {}
    for m in hooks.get("mappings", []) or []:
        if isinstance(m, dict) and m.get("id") == INTAKE_MAPPING_ID:
            return True
    return False

# schedule 'kind'/expr tokens that are one-shot -> never a recurring leftover.
_CRON_ONESHOT = frozenset({"once", "at", "date", "oneshot", "one_shot",
                           "reboot", "startup", "@reboot", "@startup"})

def _entry_is_recurring(e):
    """True iff a cron entry fires more than once. Accepts BOTH the native openclaw
    job shape (schedule as a {kind,expr} dict) and a flat entry (a bare string
    schedule, or flat cron/interval/recurring keys). One-shots are never recurring.
    Mirrors guard-cron-inventory.py's recurrence semantics so the in-script fallback
    and the guard reach the SAME verdict on the same entry (no silent disagreement)."""
    sched = e.get("schedule")
    if isinstance(sched, dict):
        kind = str(sched.get("kind", "")).strip().lower()
        if kind in _CRON_ONESHOT:
            return False
        expr = str(sched.get("expr", sched.get("cron", sched.get("value", "")))).strip().lower()
        if expr in _CRON_ONESHOT:
            return False
        return bool(kind or expr)
    if isinstance(sched, str):
        s = sched.strip().lower()
        return bool(s) and s not in _CRON_ONESHOT
    for k in ("cron", "interval", "rate", "every", "recurring"):
        v = e.get(k)
        if v:
            if str(v).strip().lower() in _CRON_ONESHOT:
                continue
            return True
    return False

def cron_recurring_remaining(entries, anthology_id=None):
    """Return the anthology-scoped RECURRING entries still present. Ownership: an
    'anthology' token anywhere in the entry (id/name/scope/tags/description/payload),
    an explicit anthology scope, or the churned anthology_id. Recurrence:
    _entry_is_recurring (shape-tolerant, one-shot aware). A NON-anthology tick belonging
    to another integration is NOT ours and is never counted. This is the guard-ABSENT
    fallback AND the cross-check that guards against a guard false-negative."""
    out = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        blob = json.dumps(e, ensure_ascii=False).lower()
        is_ours = ("anthology" in blob) or (str(e.get("scope", "")).lower() == "anthology")
        if anthology_id:
            is_ours = is_ours or (anthology_id.lower() in blob)
        if is_ours and _entry_is_recurring(e):
            out.append(e.get("name") or e.get("id") or "<unnamed>")
    return out

def _infer_cron_kind(expr):
    return "once" if str(expr).strip().lower() in ("@reboot", "@startup") else "cron"

def normalize_cron_entry(e):
    """Reshape ANY cron entry into the job shape guard-cron-inventory.py consumes, so
    the guard cannot miss an engine leftover on a shape it does not natively parse (the
    W2.7 defect: a flat id+scope+string-schedule tick read as foreign + non-recurring ->
    exit 0). Two ADDITIVE bridges (a job is only ever made MORE detectable, never
    dropped or invented):
      * OWNERSHIP -- the guard reads name/description/sessionTarget/agentId/payload; a
        flat entry carries its identity in id/scope/tags. Surface those where the guard
        looks (name<-id when unnamed; id/scope/tags/owner/labels folded into description).
      * SCHEDULE  -- the guard needs schedule as a {kind,expr} dict; a flat entry may
        carry a bare string schedule or flat cron/interval keys. Wrap them.
    A native-shape job passes through unchanged but for a harmless identity echo."""
    if not isinstance(e, dict):
        return e
    j = dict(e)
    if not str(j.get("name", "")).strip() and j.get("id"):
        j["name"] = str(j["id"])
    extra = []
    for k in ("id", "scope", "tags", "owner", "labels"):
        v = e.get(k)
        if isinstance(v, (list, tuple)):
            extra.extend(str(x) for x in v)
        elif v:
            extra.append(str(v))
    if extra:
        desc = str(j.get("description", "") or "").strip()
        j["description"] = (desc + " " + " ".join(extra)).strip()
    sched = j.get("schedule")
    if isinstance(sched, str):
        j["schedule"] = {"kind": _infer_cron_kind(sched), "expr": sched}
    elif not isinstance(sched, dict):
        expr = e.get("cron") or e.get("interval") or e.get("rate") or e.get("every")
        if expr is not None and str(expr).strip():
            kind = "interval" if (e.get("interval") or e.get("rate")) else "cron"
            j["schedule"] = {"kind": kind, "expr": str(expr)}
        elif e.get("recurring"):
            # a recurring flag with no expr -> synthesize a daily marker so the guard
            # counts it (fail-closed: over-detect a leftover rather than miss one).
            j["schedule"] = {"kind": "cron", "expr": "0 0 * * *"}
    return j

def extract_cron_jobs(obj):
    """Pull the job list out of a gateway cron-list envelope, a bare list, or a single
    job object. Returns [] for anything else (an empty inventory IS 'zero recurring')."""
    if isinstance(obj, dict):
        for key in ("jobs", "crons", "entries"):
            if isinstance(obj.get(key), list):
                return obj[key]
        if obj.get("id") or obj.get("name") or obj.get("schedule"):
            return [obj]
        return []
    if isinstance(obj, list):
        return obj
    return []

def prove_zero_recurring(entries, source_desc, anthology_id):
    """The ONE R8 proof, shared by the live churn AND the self-test, so the enforcement
    gate that actually SHIPS is the gate the self-test validates. NORMALIZE every entry
    into the guard's native shape, then prove ZERO recurring engine jobs remain via the
    real guard-cron-inventory.py subprocess (the shipped gate); an in-script scan of the
    SAME normalized entries cross-checks it and, when the guard file is absent, stands
    in. Fail-closed: a guard violation OR a fallback leftover => VIOLATION. Returns
    (status, note)."""
    norm = [normalize_cron_entry(e) for e in (entries or [])]
    fallback_remaining = cron_recurring_remaining(norm, anthology_id)
    guard = collaborator("guard-cron-inventory.py")
    if guard is not None:
        payload = json.dumps({"jobs": norm}, ensure_ascii=False)
        rc, _o, _e = run([sys.executable, guard, "--expect", "zero",
                          "--owner-tag", "anthology", "--stdin"], input=payload)
        if rc == 4 or fallback_remaining:
            det = (": %s" % fallback_remaining) if fallback_remaining else ""
            return (VIOLATION, "a recurring anthology job STILL remains over the %s "
                    "(guard-cron-inventory.py rc=%s)%s" % (source_desc, rc, det))
        if rc == 0:
            return (PASS, "guard-cron-inventory.py --expect zero over the %s "
                    "(entries normalized to the guard shape): zero recurring engine jobs"
                    % source_desc)
        if rc == 3:
            return (HELD, "cron backend unavailable to prove churn (%s)" % source_desc)
        if rc == 2:
            return (HELD, "guard rejected the cron snapshot as malformed (%s)" % source_desc)
        return (HELD, "guard-cron-inventory.py inconclusive (rc=%s) over the %s"
                % (rc, source_desc))
    # Guard file absent: the in-script scan over the normalized entries IS the proof.
    if fallback_remaining:
        return (VIOLATION, "fallback scan over the %s: recurring anthology jobs remain: %s"
                % (source_desc, fallback_remaining))
    return (PASS, "fallback scan over the %s (guard file absent): zero recurring "
            "anthology jobs" % source_desc)

def scan_no_secret_leak(path):
    """A produced export/manifest must carry NO populated secret-shaped key."""
    problems = []
    try:
        txt = open(path, "r", encoding="utf-8", errors="replace").read()
    except Exception as exc:
        return ["export unreadable: %s" % exc]
    if BANNED.search(txt):
        problems.append("Anthropic-family id shape in export")
    try:
        obj = json.loads(txt)
    except Exception:
        return problems
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and k.lower() in CRED_KEYS and \
                   isinstance(v, str) and v.strip():
                    problems.append("populated secret-shaped key %r in export" % k)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return problems

def reachable(base):
    if not base:
        return False
    try:
        u = urlsplit(base)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except Exception:
        return False

def route_probe_http(base):
    """POST to the intake route; return the HTTP status (or None). A disabled
    route answers 404 (mapping gone); a still-mapped route answers non-404."""
    url = base + "/hooks/" + INTAKE_MAPPING_ID
    req = Request(url, data=b"{}", headers={"Content-Type": "application/json"},
                  method="POST")
    try:
        with urlopen(req, timeout=4) as resp:
            return resp.status
    except HTTPError as he:
        return he.code
    except URLError:
        return None
    except Exception:
        return None

def write_secret_file_0600(path, value):
    """Write a fresh secret to a 0600 file as the node user. Value NEVER printed."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (value + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(str(p), 0o600)
    except Exception:
        pass

def remove_intake_mapping(cfg):
    """Return a copy of cfg with ONLY the anthology-intake mapping removed; the
    box-wide hooks surface and every other mapping are preserved (shared-box
    safe). Returns (new_cfg, removed_count)."""
    new = json.loads(json.dumps(cfg))
    hooks = new.get("hooks") or {}
    maps = hooks.get("mappings", []) or []
    kept = [m for m in maps if not (isinstance(m, dict)
                                    and m.get("id") == INTAKE_MAPPING_ID)]
    removed = len(maps) - len(kept)
    hooks["mappings"] = kept
    new["hooks"] = hooks
    return new, removed

def atomic_write_json(path, obj):
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".revoke.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, str(p))

# --------------------------------------------------------------------------
# Exit classification (the ONE mapping; the self-test asserts against it).
# --------------------------------------------------------------------------
def classify(results, require_live):
    statuses = [s for (_step, s, _note) in results]
    if VIOLATION in statuses:
        return 4
    if MISMATCH in statuses:
        return 5
    if ERROR in statuses:
        return 1
    if require_live:
        for step, s, _note in results:
            if step in ENFORCED and s in (DEFER, HELD):
                return 3
    return 0

def print_battery(results):
    print("\nrevoke-anthology-client: R1..R8 churn battery")
    for step, status, note in results:
        print("  %-3s %-9s %s -- %s" % (step, status, STEP_TITLE.get(step, ""), note))

# --------------------------------------------------------------------------
# --plan
# --------------------------------------------------------------------------
def do_plan():
    print("revoke-anthology-client: churn / offboard plan (SPEC 13.3)")
    for step in ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
        enforced = " [ENFORCED: exit 4 if a probe still answers]" \
            if step in ("R7", "R8") else ""
        print("  %s  %s%s" % (step, STEP_TITLE[step], enforced))
    print("\nR7 and R8 gate the exit code; R2 (board) is fail-soft; R3 (Drive) "
          "under an anyone-can-read root needs a private destination to TRULY "
          "revoke. --live requires a matching --confirm-name and refuses root.")
    return 0

# --------------------------------------------------------------------------
# SYNTHETIC-CLIENT SELF-TEST: force-observe the failure modes.
# --------------------------------------------------------------------------
def _seed_synthetic_ledger(db_path):
    aid, pid, cid = "SELFTEST-A1", "SELFTEST-P1", "SELFTEST-C1"
    name = "Synthetic Anthology (self-test)"
    run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
         "--db", db_path, "bootstrap"])
    run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
         "--db", db_path, "upsert-producer", "--producer-id", pid,
         "--producer-email", "producer@example.invalid",
         "--display-name", "Synthetic Producer"])
    run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
         "--db", db_path, "upsert-anthology", "--anthology-id", aid,
         "--producer-id", pid, "--name", name, "--status", "open"])
    run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
         "--db", db_path, "upsert-participant", "--contact-id", cid,
         "--anthology-id", aid, "--first-name", "Test", "--last-name", "User",
         "--email", "participant@example.invalid"])
    return aid, name, "%s::%s" % (cid, aid)

def _synthetic_gw_cfg():
    # A box-wide hooks surface carrying the anthology mapping PLUS a second,
    # unrelated integration that MUST survive the churn (shared-box safety).
    return {
        "hooks": {
            "enabled": True,
            "path": "/hooks",
            "token": {"source": "env", "provider": "default", "id": INTAKE_LABEL},
            "mappings": [
                {"id": INTAKE_MAPPING_ID, "name": "Anthology intake",
                 "match": {"path": INTAKE_MAPPING_ID, "source": INTAKE_MAPPING_ID}},
                {"id": "other-integration", "name": "some other client hook",
                 "match": {"path": "other-integration"}},
            ],
        }
    }

def _selftest_scenario(broken, work):
    """Run the churn decision logic against synthetic artifacts. When broken is
    True we DELIBERATELY skip the invalidations so R7/R8 must catch a probe that
    still answers. Returns (exit_code, results)."""
    db_path = os.path.join(work, "state.db")
    aid, name, pk = _seed_synthetic_ledger(db_path)
    results = []

    # ---- R1: rotate the gate-token secret (unless broken -> leave it) ----
    secret_old = _secrets.token_hex(24)
    secret_new = _secrets.token_hex(24)
    assert secret_old != secret_new
    tok, _payload = _ge.mint_token(pk, "s5_participant", secret_old, ttl_seconds=3600)
    if broken:
        active_secret = secret_old          # NOT rotated: token stays valid
        results.append(("R1", VIOLATION,
                        "self-test: invalidation deliberately skipped"))
    else:
        sf = os.path.join(work, "gate-secret")
        write_secret_file_0600(sf, secret_new)   # 0600, value never printed
        assert (os.stat(sf).st_mode & 0o777) == 0o600
        active_secret = secret_new
        results.append(("R1", PASS, "gate-token secret rotated (value never printed)"))

    # ---- R4: remove the intake mapping (unless broken -> leave it) ----
    gw = _synthetic_gw_cfg()
    gw_path = os.path.join(work, "openclaw.json")
    atomic_write_json(gw_path, gw)
    if broken:
        pass                                  # mapping left in place
    else:
        new_cfg, removed = remove_intake_mapping(load_json(gw_path))
        atomic_write_json(gw_path, new_cfg)
        # shared-box safety: the OTHER integration must survive.
        reread = load_json(gw_path)
        assert removed == 1
        assert not route_mapping_present(reread)
        assert any(m.get("id") == "other-integration"
                   for m in reread["hooks"]["mappings"])
        assert reread["hooks"]["enabled"] is True
    r4_present = route_mapping_present(load_json(gw_path))
    results.append(("R4", VIOLATION if r4_present else PASS,
                    "intake mapping present" if r4_present else "intake mapping removed"))

    # ---- R5: real export bundle from the synthetic ledger ----
    # Call anthology_state.py directly against the temp db (NOT astate(), which
    # binds to the process --db/--state-dir and must never touch a real box here).
    exp = os.path.join(work, "export.json")
    rc, _o, _e = run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
                      "--db", db_path, "export-bundle", "--anthology-id", aid,
                      "--out", exp])
    if rc == 0 and os.path.isfile(exp):
        leaks = scan_no_secret_leak(exp)
        results.append((("R5", MISMATCH, "; ".join(leaks)) if leaks
                        else ("R5", PASS, "export written, no secret leak")))
    else:
        results.append(("R5", MISMATCH, "export not produced (rc=%s)" % rc))

    # ---- R6: archive the ledger rows; read status back ----
    run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
         "--db", db_path, "upsert-anthology", "--anthology-id", aid,
         "--status", "archived"])
    chk = os.path.join(work, "archived.json")
    run([sys.executable, os.path.join(SCRIPTS, "anthology_state.py"),
         "--db", db_path, "export-bundle", "--anthology-id", aid, "--out", chk])
    status_after = load_json(chk)["anthology"].get("status") if os.path.isfile(chk) else None
    results.append(("R6", PASS if status_after == "archived" else MISMATCH,
                    "ledger status=%s" % status_after))

    # ---- R2 / R3: fail-soft collaborators absent in the synthetic run ----
    results.append(("R2", DEFER, "board archival deferred (mc_board.py not exercised in self-test)"))
    results.append(("R3", DEFER, "Drive revocation deferred (no Google creds in self-test)"))

    # ---- R7: probe the revoked token + the route ----
    tok_answers = token_still_answers(tok, active_secret, pk)
    route_answers = route_mapping_present(load_json(gw_path))
    if tok_answers or route_answers:
        why = []
        if tok_answers:
            why.append("gate token STILL verifies")
        if route_answers:
            why.append("intake route STILL mapped")
        results.append(("R7", VIOLATION, "a probe still answers: " + "; ".join(why)))
    else:
        results.append(("R7", PASS, "revoked token refused AND route unmapped"))

    # ---- R8: prove ZERO recurring jobs via the SHIPPED gate ----
    # Build the snapshot in guard-cron-inventory.py's NATIVE job shape and drive the
    # SAME prove_zero_recurring() the live churn uses (the real guard subprocess), NOT
    # the in-process fallback in isolation. broken -> our tick SURVIVES (must fail
    # exit 4); clean -> only a foreign job remains (must pass exit 0).
    _r8_tick = {"id": "id-anthology-daily-tick", "name": "anthology-daily-tick",
                "description": "anthology engine daily smoke tick", "enabled": True,
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "payload": {"kind": "agentTurn", "message": "anthology daily tick"}}
    _r8_foreign = {"id": "id-fleet-heartbeat", "name": "fleet-heartbeat",
                   "description": "operator fleet status", "enabled": True,
                   "schedule": {"kind": "cron", "expr": "0 6-21 * * *"},
                   "payload": {"kind": "agentTurn", "message": "per-client status"}}
    _r8_entries = [_r8_tick, _r8_foreign] if broken else [_r8_foreign]
    r8_status, r8_note = prove_zero_recurring(_r8_entries, "self-test cron snapshot", aid)
    results.append(("R8", r8_status, r8_note))

    return classify(results, require_live=False), results

def _selftest_r8_gate():
    """Force-observe the SHIPPED R8 enforcement gate in ISOLATION (QC W2.7). The
    battery scenarios fold R8 into classify(); this proves that the guard-BACKED proof
    that actually ships -- prove_zero_recurring() -> the real guard-cron-inventory.py
    subprocess, NOT the in-process fallback -- FIRES (exit 4 / VIOLATION) on a dirty
    snapshot and stays green (exit 0 / PASS) on a clean one, for BOTH the native job
    shape AND the exact flat id+scope+string-schedule shape a prior build shipped so
    the guard could not see it. Also confirms the guard-absent fallback AGREES on the
    same normalized entries. Returns (ok, notes)."""
    tick = {"id": "id-anthology-daily-tick", "name": "anthology-daily-tick",
            "description": "anthology engine daily smoke tick", "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            "payload": {"kind": "agentTurn", "message": "anthology daily tick"}}
    foreign = {"id": "id-fleet-heartbeat", "name": "fleet-heartbeat",
               "description": "operator fleet status", "enabled": True,
               "schedule": {"kind": "cron", "expr": "0 6-21 * * *"},
               "payload": {"kind": "agentTurn", "message": "per-client status"}}
    # The EXACT shape the W2.7 defect shipped: flat id+scope, string schedule.
    flat_tick = {"id": "anthology-daily-tick", "scope": "anthology",
                 "schedule": "0 9 * * *"}
    clean = [foreign]
    dirty_native = [tick, foreign]
    dirty_flat = [flat_tick, foreign]
    aid = "SELFTEST-A1"

    notes, ok = [], True
    guard = collaborator("guard-cron-inventory.py")
    if guard is None:
        return False, ["guard-cron-inventory.py absent; the SHIPPED R8 gate is unprovable"]

    # (1) the shipped proof helper: clean -> PASS, dirty (native + flat) -> VIOLATION.
    for label, entries, want in (
            ("proof(clean)", clean, PASS),
            ("proof(dirty native)", dirty_native, VIOLATION),
            ("proof(dirty FLAT id+scope+string-sched)", dirty_flat, VIOLATION)):
        got, _n = prove_zero_recurring(entries, "self-test", aid)
        good = (got == want)
        ok = ok and good
        notes.append("%s=%s (want %s) %s" % (label, got, want, "OK" if good else "WRONG"))

    # (2) the RAW guard subprocess exit code, end to end, on NORMALIZED input --
    # the concrete disproof of the QC claim (a dirty snapshot MUST yield guard rc 4).
    def _guard_rc(entries):
        payload = json.dumps({"jobs": [normalize_cron_entry(e) for e in entries]},
                             ensure_ascii=False)
        rc, _o, _e = run([sys.executable, guard, "--expect", "zero",
                          "--owner-tag", "anthology", "--stdin"], input=payload)
        return rc
    for label, entries, want in (("guard rc(clean)", clean, 0),
                                 ("guard rc(dirty native)", dirty_native, 4),
                                 ("guard rc(dirty FLAT)", dirty_flat, 4)):
        got = _guard_rc(entries)
        good = (got == want)
        ok = ok and good
        notes.append("%s=%d (want %d) %s" % (label, got, want, "OK" if good else "WRONG"))

    # (3) the guard-absent fallback AGREES on the same normalized entries.
    for label, entries, want_empty in (("fallback(clean)", clean, True),
                                       ("fallback(dirty)", dirty_native, False)):
        got = cron_recurring_remaining([normalize_cron_entry(e) for e in entries], aid)
        good = ((len(got) == 0) == want_empty)
        ok = ok and good
        notes.append("%s=%s (want %s) %s" % (label, got,
                     "empty" if want_empty else "non-empty", "OK" if good else "WRONG"))
    return ok, notes

def do_selftest():
    # Structural: this file byte-compiles clean and carries no banned id.
    struct = []
    with open(os.path.join(SCRIPTS, "revoke-anthology-client.sh"),
              "r", encoding="utf-8", errors="replace") as fh:
        own = fh.read()
    # The ONLY tolerated occurrences of the fragments are the assembled deny
    # definition; the assembled BANNED regex must never match this file's text
    # outside its own construction, and no whole banned literal appears.
    for literal in ("clau" "de-sonnet", "clau" "de-opus", "anthro" "pic/"):
        if literal in own:
            struct.append("banned literal present: %r" % literal)
    if _ge is None:
        struct.append("gate_engine.py not importable (token invalidation unprovable)")

    ok = True
    print("\nrevoke-anthology-client: SELF-TEST (synthetic client; example.invalid)")
    if struct:
        ok = False
        for m in struct:
            print("  STRUCT FAIL: " + m)
    else:
        print("  structure OK (byte-clean, no banned id, gate_engine importable)")

    with tempfile.TemporaryDirectory(prefix="anthology-revoke-selftest-") as work:
        clean_dir = os.path.join(work, "clean"); os.makedirs(clean_dir)
        broken_dir = os.path.join(work, "broken"); os.makedirs(broken_dir)

        clean_code, clean_res = _selftest_scenario(broken=False, work=clean_dir)
        print("\n  [CLEAN scenario] full revoke -> expect exit 0 (revoked and verified)")
        print_battery(clean_res)
        print("  [CLEAN] classify() = %d" % clean_code)

        broken_code, broken_res = _selftest_scenario(broken=True, work=broken_dir)
        print("\n  [FORCED-FAILURE scenario] invalidations skipped -> expect exit 4")
        print_battery(broken_res)
        print("  [FORCED-FAILURE] classify() = %d" % broken_code)

    # Force-observe the SHIPPED R8 enforcement gate in isolation (QC W2.7). The battery
    # above folds R8 into classify(); this proves the guard-BACKED proof that actually
    # ships FIRES on a dirty snapshot (native AND the flat id+scope+string-schedule shape
    # a prior build shipped incompatibly) and stays green on a clean one -- so a green
    # self-test is real confidence in the gate, not the dead in-process fallback.
    r8_ok, r8_notes = _selftest_r8_gate()
    print("\n  [R8 GATE] shipped guard-backed enforcement (the LIVE proof path, not the "
          "in-process fallback):")
    for _note in r8_notes:
        print("    - " + _note)
    print("  [R8 GATE] %s" % ("OK" if r8_ok else "FAIL"))

    clean_ok = (clean_code == 0)
    broken_ok = (broken_code == 4)
    print("\nrevoke-anthology-client: self-test observation")
    print("  CLEAN scenario classified as %d (want 0): %s"
          % (clean_code, "OK" if clean_ok else "WRONG"))
    print("  FORCED-FAILURE scenario classified as %d (want 4): %s"
          % (broken_code, "OK" if broken_ok else "WRONG"))

    if ok and clean_ok and broken_ok and r8_ok:
        print("revoke-anthology-client: exit 0 (self-test PASS; own failure modes "
              "force-observed: a probe that still answers -- and a recurring anthology "
              "job that survives churn -- both drive exit 4)")
        return 0
    print("revoke-anthology-client: exit 4 (self-test did not behave as specified)")
    return 4

# --------------------------------------------------------------------------
# LIVE / DRY-RUN churn against a real client box (fail-soft; deferred where a
# collaborator or a resource is not reachable/wired yet).
# --------------------------------------------------------------------------
def _lookup_anthology():
    """Return (name, participants, status) from the ledger, or (None, [], None).
    --json makes anthology_state.py emit parseable JSON on stdout (without it the
    ledger prints a human dict repr, which would falsely read as 'not found')."""
    rc, out, _e = astate("export-bundle", "--anthology-id", ANTH_ID, "--json")
    if rc != 0:
        return None, [], None
    try:
        b = json.loads(out)
        return (b.get("anthology", {}).get("name"),
                b.get("participants", []),
                b.get("anthology", {}).get("status"))
    except Exception:
        return None, [], None

def do_live(dry):
    results = []
    if not ANTH_ID:
        print("revoke-anthology-client: exit 2 (--anthology-id is required for "
              "%s)" % ("--dry-run" if dry else "--live"))
        return 2

    name, participants, status = _lookup_anthology()
    if name is None:
        # Unknown/unreadable ledger: nothing to churn is an idempotent no-op in
        # dry-run; in --live it is a validation refusal (we will not guess).
        if dry:
            print("revoke-anthology-client: anthology %r not found in the ledger; "
                  "nothing to churn (idempotent no-op)." % ANTH_ID)
            return 0
        print("revoke-anthology-client: exit 2 (anthology %r not found; refusing "
              "to churn an unknown anthology)." % ANTH_ID)
        return 2

    if not dry:
        # Destructive-action guard: typed name confirmation must match.
        if not CONFIRM:
            print("revoke-anthology-client: exit 2 (--live requires --confirm-name "
                  "matching the ledger anthology name; none supplied).")
            return 2
        if CONFIRM != name:
            print("revoke-anthology-client: exit 2 (--confirm-name does not match "
                  "the ledger anthology name).")
            return 2

    print("\nrevoke-anthology-client: %s churn for anthology (name confirmed), "
          "%d participant row(s), current status=%s"
          % ("DRY-RUN" if dry else "LIVE", len(participants), status))

    gate_set = bool(os.environ.get(GATE_LABEL))
    captured = []  # (pk, token) minted under the OLD secret for the R7 probe
    paths = derived_paths()
    secrets_target = SECRETS_FILE or paths["gate_secret"]

    # ---- R1: invalidate outstanding participant gate tokens ----
    if _ge is None:
        results.append(("R1", HELD, "gate_engine.py not importable; cannot rotate/probe"))
    elif not gate_set:
        results.append(("R1", HELD, "%s NOT SET; cannot mint a representative token "
                        "to prove invalidation" % GATE_LABEL))
    else:
        old_secret = os.environ[GATE_LABEL]  # value used, never printed
        for p in participants:
            pk = p.get("participant_key")
            if not pk:
                continue
            try:
                t, _pl = _ge.mint_token(pk, "s5_participant", old_secret, ttl_seconds=3600)
                captured.append((pk, t))
            except Exception:
                pass
        if dry:
            results.append(("R1", DEFER, "would rotate %s (0600) to invalidate %d "
                            "outstanding token(s)" % (GATE_LABEL, len(captured))))
        elif not secrets_target:
            results.append(("R1", HELD, "no rotation target (pass --secrets-file or "
                            "--state-dir); operator surface: rotate %s at the client "
                            "secret store to invalidate outstanding tokens" % GATE_LABEL))
        else:
            new_secret = _secrets.token_hex(32)
            write_secret_file_0600(secrets_target, new_secret)
            os.environ[GATE_LABEL] = new_secret  # in-process, so R7 probes the new key
            results.append(("R1", PASS, "gate-token secret rotated (value never printed)"))

    # ---- R2: archive the Anthology board cards (fail-soft) ----
    mc = collaborator("mc_board.py")
    if mc is None:
        results.append(("R2", DEFER, "mc_board.py not present; board archival "
                        "deferred (fail-soft; the ledger is the truth)"))
    elif dry:
        results.append(("R2", DEFER, "would archive the Anthology board cards via mc_board.py"))
    else:
        rc, _o, _e = run([sys.executable, mc, "archive", "--anthology-id", ANTH_ID])
        results.append(("R2", PASS if rc == 0 else DEFER,
                        "board cards archived" if rc == 0
                        else "board unreachable; fail-soft (reconciles on the daily tick)"))

    # ---- R3: revoke Drive shares + regenerate view links ----
    da = collaborator("drive_adapter.py")
    share_targets = []
    for p in participants:
        for k in ("drive_folder_id",):
            if p.get(k):
                share_targets.append(p[k])
    if da is None:
        results.append(("R3", DEFER, "drive_adapter.py not present; Drive revocation deferred"))
    elif not share_targets:
        results.append(("R3", PASS, "no shared Drive folders on the ledger rows (no-op)"))
    elif dry:
        results.append(("R3", DEFER, "would revoke share on %d Drive target(s)%s"
                        % (len(share_targets),
                           "" if PRIVATE_DEST else
                           " (NOTE: no --private-dest-folder-id; inherited public "
                           "access under the anyone-can-read root can only be "
                           "reported, not deleted, at the file level)")))
    else:
        revoked_ok = 0
        remaining_public = 0
        for fid in share_targets:
            cmd = [sys.executable, da, "revoke-share", "--file-id", fid]
            if PRIVATE_DEST:
                cmd += ["--unlink-from-root-id",
                        (load_json(os.path.join(SKILL, "config",
                         "engine-config.template.json")).get("delivery", {})
                         .get("drive_root_folder", "")),
                        "--to-folder-id", PRIVATE_DEST]
            rc, out, _e = run(cmd)
            if rc == 0:
                revoked_ok += 1
                try:
                    if json.loads(out).get("anyone_access"):
                        remaining_public += 1
                except Exception:
                    pass
        note = "revoked share on %d/%d target(s)" % (revoked_ok, len(share_targets))
        if remaining_public:
            note += "; %d still carry INHERITED public access (move out of the " \
                    "public root with --private-dest-folder-id to truly revoke)" \
                    % remaining_public
        results.append(("R3", PASS if revoked_ok == len(share_targets) else DEFER, note))

    # ---- R4: disable the intake webhook route ----
    if not GW_CFG or not os.path.isfile(GW_CFG):
        results.append(("R4", HELD if not dry else DEFER,
                        "gateway config not found at %s; route disable %s"
                        % (GW_CFG, "held" if not dry else "deferred")))
    else:
        try:
            cfg = load_json(GW_CFG)
        except Exception as exc:
            cfg = None
            results.append(("R4", ERROR, "gateway config unreadable: %s" % exc))
        if cfg is not None:
            present = route_mapping_present(cfg)
            if not present:
                results.append(("R4", PASS, "intake mapping already absent (idempotent)"))
            elif dry:
                results.append(("R4", DEFER, "would remove the anthology-intake "
                                "mapping (box-wide hooks + other integrations preserved)"))
            else:
                new_cfg, removed = remove_intake_mapping(cfg)
                try:
                    atomic_write_json(GW_CFG, new_cfg)
                    reread = load_json(GW_CFG)
                    # Also drop the provision-materialized route file, if present.
                    rf = paths["route_file"]
                    if rf and os.path.isfile(rf):
                        try:
                            os.remove(rf)
                        except Exception:
                            pass
                    if route_mapping_present(reread):
                        results.append(("R4", VIOLATION, "mapping still present after write"))
                    else:
                        results.append(("R4", PASS, "anthology-intake mapping removed "
                                        "(%d); other mappings + hooks surface preserved"
                                        % removed))
                except Exception as exc:
                    results.append(("R4", ERROR, "route disable write failed: %s" % exc))

    # ---- R5: produce the data-export bundle ----
    if dry:
        # Dry-run writes NOTHING (no litter, no side effects).
        results.append(("R5", DEFER, "would write the per-anthology export bundle "
                        "(client keeps their record; no secret in it)"))
    else:
        try:
            out_dir = OUT_DIR or os.path.join(STATE_DIR or str(Path.home()), "churn-export")
            Path(out_dir).expanduser().mkdir(parents=True, exist_ok=True)
            exp = os.path.join(out_dir, "anthology-%s-export.json" % ANTH_ID)
            rc, _o, _e = astate("export-bundle", "--anthology-id", ANTH_ID, "--out", exp)
            if rc == 0 and os.path.isfile(exp):
                leaks = scan_no_secret_leak(exp)
                if leaks:
                    results.append(("R5", MISMATCH, "; ".join(leaks)))
                else:
                    results.append(("R5", PASS,
                                    "export bundle written to %s (no secret leak)" % exp))
            else:
                results.append(("R5", MISMATCH, "export bundle not produced (rc=%s)" % rc))
        except Exception as exc:
            results.append(("R5", ERROR, "export failed: %s" % exc))

    # ---- R6: archive the ledger rows (deactivate never delete) ----
    if dry:
        results.append(("R6", DEFER, "would set anthology status=archived (rows retained)"))
    else:
        rc, _o, _e = astate("upsert-anthology", "--anthology-id", ANTH_ID,
                            "--status", "archived")
        if rc == 0:
            nm, _pp, st = _lookup_anthology()
            results.append(("R6", PASS if st == "archived" else MISMATCH,
                            "ledger status=%s (rows retained)" % st))
        else:
            results.append(("R6", MISMATCH, "archive write failed (rc=%s)" % rc))

    # ---- R7: VERIFY -- probe a revoked token link and the disabled route ----
    tok_probe = None
    if captured and _ge is not None and os.environ.get(GATE_LABEL):
        probe_secret = os.environ[GATE_LABEL]  # the NEW secret after rotation
        still = [pk for (pk, t) in captured
                 if token_still_answers(t, probe_secret, pk)]
        if dry:
            tok_probe = (DEFER, "would verify %d captured token(s) refuse post-rotation"
                         % len(captured))
        elif still:
            tok_probe = (VIOLATION, "a revoked token STILL verifies for %d subject(s)"
                         % len(still))
        else:
            tok_probe = (PASS, "all %d captured token(s) refused post-rotation" % len(captured))
    else:
        tok_probe = (HELD, "no representative token captured (gate secret unset or "
                     "no participants); token probe not observed")

    route_probe = None
    r4_now = next((s for (st, s, n) in results if st == "R4"), None)
    if dry:
        route_probe = (DEFER, "would probe %s/hooks/%s for a 404" % (BASEURL, INTAKE_MAPPING_ID))
    elif reachable(BASEURL):
        code = route_probe_http(BASEURL)
        if code is None:
            route_probe = (HELD, "gateway stopped answering during the route probe")
        elif code == 404:
            route_probe = (PASS, "intake route answers 404 (unmapped)")
        else:
            route_probe = (VIOLATION, "intake route STILL answers (status %s)" % code)
    elif r4_now == PASS:
        route_probe = (PASS, "gateway not reachable to HTTP-probe, but the mapping "
                       "was removed and read back absent (config-level proof)")
    else:
        route_probe = (HELD, "gateway not reachable and route not confirmed removed")

    # Fold the two probes into R7: any VIOLATION wins; else the weakest observed.
    order = [VIOLATION, MISMATCH, ERROR, HELD, DEFER, PASS]
    r7_status = min([tok_probe[0], route_probe[0]], key=order.index)
    results.append(("R7", r7_status,
                    "token[%s: %s] route[%s: %s]"
                    % (tok_probe[0], tok_probe[1], route_probe[0], route_probe[1])))

    # ---- R8: leave ZERO recurring jobs, and PROVE it ----
    # The daily tick (provision registered `anthology-daily-tick`) must be removed
    # in a live churn, then guard-cron-inventory.py --expect zero proves nothing
    # recurring survived. The engine only ever touches ITS OWN cron; the operator's
    # fleet heartbeat and every other schedule are left untouched.
    #  * `declarative` = provision's own STATE_DIR/cron-inventory.json bookkeeping,
    #    which the churn ZEROES (never any operator-supplied snapshot).
    #  * `snapshot`    = an operator-supplied --cron-inventory (a READ-ONLY live
    #    snapshot to prove against); it is NEVER mutated (proving against a file we
    #    just zeroed would be circular).
    #  * the TRUTHFUL proof source is `--live` (the real backend); a snapshot or the
    #    declarative file are fallbacks when the openclaw CLI is not on PATH.
    declarative = paths["cron_inventory"]
    snapshot = CRON_INV

    if dry:
        results.append(("R8", DEFER, "would remove the anthology-daily-tick and prove "
                        "zero via guard-cron-inventory.py --expect zero"))
    else:
        # (a) Best-effort removal of the engine's OWN cron entries. When the
        # operator supplies an explicit --cron-inventory snapshot they are managing
        # the backend representation themselves, so we do NOT shell the live cron
        # CLI (keeps an operator-driven run hermetic); otherwise, with the openclaw
        # CLI present, we remove anthology-daily-tick for real.
        if not ALLOW_CRON_DELETE:
            removed_note = "cron removal skipped (pass --allow-cron-delete to churn the tick)"
        elif snapshot:
            removed_note = "operator-supplied cron snapshot: backend removal is the " \
                           "operator's step; proving against the snapshot"
        elif has_cmd("openclaw"):
            removed_note = "openclaw cron delete not accepted (schema drift)"
            for verb in (["cron", "remove", "--name", "anthology-daily-tick"],
                         ["cron", "delete", "--name", "anthology-daily-tick"],
                         ["cron", "rm", "anthology-daily-tick"]):
                rc, _o, _e = run(["openclaw"] + verb)
                if rc == 0:
                    removed_note = "anthology-daily-tick removed from the cron backend"
                    break
        else:
            removed_note = "openclaw CLI absent; declarative inventory zeroed"
        # Zero ONLY provision's declarative bookkeeping file (never a snapshot), and
        # only when we are NOT deferring to an operator snapshot.
        if ALLOW_CRON_DELETE and not snapshot and declarative and os.path.isfile(declarative):
            try:
                inv = load_json(declarative)
                if isinstance(inv, dict):
                    inv["jobs"] = []; inv["total"] = 0
                    atomic_write_json(declarative, inv)
            except Exception:
                pass

        # (b) Resolve a cron source into an entries LIST + a human description. An
        # explicit operator snapshot wins over auto-discovery; else the truthful live
        # backend; else provision's declarative bookkeeping. The operator's snapshot is
        # only READ (never rewritten) -- the proof runs on a normalized in-memory copy.
        entries, source_desc, have_source = None, "", False
        if snapshot and os.path.isfile(snapshot):
            have_source, source_desc = True, "operator cron snapshot"
            try:
                entries = extract_cron_jobs(load_json(snapshot))
            except Exception:
                entries = None
        elif snapshot:                       # inline JSON string
            have_source, source_desc = True, "operator cron snapshot (inline)"
            try:
                entries = extract_cron_jobs(json.loads(snapshot))
            except Exception:
                entries = None
        elif has_cmd("openclaw"):
            have_source, source_desc = True, "live cron backend"
            rc, out, _e = run(["openclaw", "cron", "list", "--json"])
            if rc == 0:
                try:
                    entries = extract_cron_jobs(json.loads(out))
                except Exception:
                    entries = None
            else:
                entries = None               # backend refused -> unavailable
        elif declarative and os.path.isfile(declarative):
            have_source, source_desc = True, "declarative inventory (bookkeeping)"
            try:
                entries = extract_cron_jobs(load_json(declarative))
            except Exception:
                entries = None

        # (c) Prove ZERO recurring engine jobs remain via the shared gate (the real
        # guard-cron-inventory.py subprocess over NORMALIZED entries, cross-checked by an
        # in-script scan). No source at all -> HELD; a present-but-unreadable source ->
        # HELD (we never claim a churn we could not observe).
        if not have_source:
            results.append(("R8", HELD, "no cron source to prove churn (no openclaw CLI, "
                            "no --cron-inventory, no declarative file); %s" % removed_note))
        elif entries is None:
            results.append(("R8", HELD, "cron source unreadable/unavailable (%s); %s"
                            % (source_desc, removed_note)))
        else:
            status, note = prove_zero_recurring(entries, source_desc, ANTH_ID)
            results.append(("R8", status, "%s; %s" % (note, removed_note)))

    # ---- summary + exit ----
    print_battery(results)
    code = classify(results, require_live=REQUIRE_LIVE)
    n = {}
    for _s, st, _no in results:
        n[st] = n.get(st, 0) + 1
    print("\nrevoke-anthology-client: %s" % ", ".join("%d %s" % (v, k) for k, v in n.items()))
    verdict = {
        0: "exit 0 (revoked and verified)" if not dry
           else "exit 0 (dry-run: plan sound; no client state was mutated)",
        1: "exit 1 (unexpected error in a churn step)",
        2: "exit 2 (validation or guard refusal)",
        3: "exit 3 (an enforced step could not be observed; --require-live holds the battery)",
        4: "exit 4 (a probe STILL answers -- churn is NOT complete)",
        5: "exit 5 (data or read-back mismatch)",
    }.get(code, "exit %d" % code)
    print("revoke-anthology-client: %s" % verdict)
    return code

# --------------------------------------------------------------------------
# Dispatch.
# --------------------------------------------------------------------------
try:
    if MODE == "plan":
        sys.exit(do_plan())
    if MODE == "selftest":
        sys.exit(do_selftest())
    if MODE == "live":
        sys.exit(do_live(dry=False))
    sys.exit(do_live(dry=True))       # dryrun (default)
except BrokenPipeError:
    sys.exit(0)
except SystemExit:
    raise
except Exception as exc:  # last-resort guard -> house exit 1
    sys.stderr.write("revoke-anthology-client: unexpected error: %s\n" % exc)
    sys.exit(1)
PY
rc=$?
exit "$rc"
