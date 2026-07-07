#!/usr/bin/env python3
"""intake_router.py -- S0 deterministic intake and routing (Anthology Engine, Skill 59).

WHAT THIS IS (SPEC 3.4 row 2; ENGINE-MANIFEST.json script #2; SPEC 4 stage S0):
The single deterministic front door for the Convert and Flow intake webhook
(route /hooks/anthology-intake). NO model call, ever. It parses the raw form
payload, verifies the route secret, validates the hidden fields, runs the tenant
check, deduplicates by submission fingerprint (an acknowledged no-op on replay),
keys the participant DIRECTLY by the composite key contact_id::anthology_id (never
a list-then-filter -- the legacy Gap 7 opportunity race is structurally absent),
upserts the participant through the sole ledger writer, captures any unresolvable
submission to the Exceptions queue with the RAW payload and a TYPED reason (never
dropped, never guessed), acknowledges under two seconds, and spawns the stage job
DETACHED so the slow work never blocks the acknowledge.

EXECUTION MODEL (SPEC 2.2): one event -> load by composite key -> advance exactly
one stage -> persist -> stop. A bare resend of an already-terminal submission is an
acknowledged no-op. No process sleeps waiting for a human.

REPLAY (SPEC 4 S0 TRIGGER "an exceptions-queue replay"): a bare resend no-ops, but
an operator resolve-and-replay (--replay) -- fired AFTER the underlying condition is
fixed (e.g. the missing anthology is now registered) -- RESETS this router's own
dedup claim so S0 genuinely re-drives instead of no-opping against the prior terminal
'exception:*' claim. --replay is the CLEAN SEAM for exceptions.py's resolve-and-replay:
callers pass the flag rather than reaching into the intake-private dedup store, and it
never drifts from S0 because the reset is keyed by this file's own fingerprint. The
sole writer keeps the upsert idempotent, so a re-drive never duplicates a participant
or an artifact.

EXIT CODES (SPEC 3.4 row 2 -- DISTINCT from the house convention):
  0  routed, or an idempotent no-op (duplicate / already-processed)
  1  unexpected error (house; fail-closed, never a silent pass)
  2  route-secret refusal
  3  captured to Exceptions with a typed reason
     (unroutable_missing_ids | unknown_anthology | stage_mismatch | tenant_mismatch)
  4  ledger unreachable: the durable participant/exception write could not be
     persisted, OR a concurrent in-flight claim whose durable write is not yet
     guaranteed -- BOTH are RETRYABLE, the webhook must re-deliver, and this is NEVER
     a false success. On any retryable failure the dedup claim is RELEASED (deleted,
     not finalized 'in_progress'), so the re-delivery genuinely re-attempts and a
     submission is NEVER silently dropped (SPEC S0 cardinal guarantee).

DOCTRINE (binding): move in silence (operator-verbose on stderr, client-silent);
never print a secret value (labels + SET/NOT SET only; secret-bearing payload
fields are REDACTED before an exception preserves the raw body); Convert and Flow
is the platform name in every surface; keying is contact_id, never email; no
deny-listed model-provider identifier ships here (this stage makes no model call at
all); enforcement, not description (every refusal is fail-closed).

BOUNDARIES / OWNERSHIP: this unit authors ONLY this file. It SHELLS OUT to the
sibling sole-writer anthology_state.py for every ledger WRITE (upsert-participant,
exception-open) -- no other code path writes the base or the mirror. It performs
side-effect-free READS of the local SQLite mirror (tenant binding + participant
cursor) through a read-only connection; it never writes the store directly.
"""
import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants and contract
# ---------------------------------------------------------------------------
STAGE = "s0"

EX_OK = 0            # routed or idempotent no-op
EX_ERR = 1          # unexpected error (house)
EX_SECRET = 2       # route-secret refusal
EX_EXCEPTION = 3    # captured to Exceptions (typed reason)
EX_LEDGER = 4       # ledger unreachable (durable write failed)

KEY_DELIM = "::"    # the LITERAL composite-key delimiter (mirrors anthology_state.participant_key)

# The typed reasons S0 may capture (subset of anthology_state.EXCEPTION_REASONS;
# legacy_reconciliation is authored by the exceptions replay path, not intake).
INTAKE_EXCEPTION_REASONS = (
    "unroutable_missing_ids", "unknown_anthology", "stage_mismatch", "tenant_mismatch",
)
# Full set kept for the self-test cross-check against the sibling writer.
ALL_EXCEPTION_REASONS = INTAKE_EXCEPTION_REASONS + ("legacy_reconciliation",)

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_WRITER = SCRIPTS / "anthology_state.py"
DEFAULT_STAGE_RUNNER = SCRIPTS / "stage_s0_intake.py"

# Terminal dedup outcomes: a replay of any of these is an acknowledged no-op.
_TERMINAL_PREFIXES = ("routed", "noop", "exception:")

# Built-in defaults; engine-config.json (or the template) overrides via merge.
BUILTIN_DEFAULTS = {
    "route_path": "/hooks/anthology-intake",
    "route_secret_label": "ANTHOLOGY_INTAKE_HOOK_SECRET",
    # secret_mode:
    #   verify_if_present -> the gateway (OpenClaw Surface A, box-wide hooks.token =
    #       ANTHOLOGY_INTAKE_HOOK_SECRET, W0.4-proved to 401 before this script runs)
    #       is the primary enforcer; intake_router is defense-in-depth: it refuses a
    #       PRESENTED-but-mismatched secret, and passes when none is forwarded.
    #   required -> a matching secret MUST be present (Surface B per-route secret, or
    #       a hardened box); absent/mismatch -> exit 2.
    #   off -> skip (trusted local replay/tests).
    "secret_mode": "verify_if_present",
    "acknowledge_budget_seconds": 2,
    # tenant enforcement when the anthology exists but carries no location binding
    # yet: "continue" (warn to the operator and proceed) or "reject" (tenant_mismatch).
    "tenant_missing_binding": "continue",
    # keys stripped from the body before fingerprinting AND before an exception
    # preserves the raw payload (volatile envelope noise; secrets are always stripped).
    "fingerprint_exclude_keys": [],
    "dedup_stale_seconds": 120,   # reclaim a crashed in-progress claim after this
    # submitted-stage tokens that mean "the universal intake form" (new participant OK)
    "intake_stage_tokens": ["intake", "s0", "s0_intake"],
    # optional explicit map: token -> {"new_participant_allowed": bool, "legal_cursors": [...]}
    "stage_form_map": {},
    # detached stage spawn command template (list). Placeholders resolved at spawn.
    # Default fires the S0 stage runner, which (once the integrator wires it) runs
    # drive-tree-provision.py + mc_board.py and advances into S1.
    "stage_spawn_cmd": None,
    # candidate paths per logical field (dotted; supports nested dicts and the
    # Convert and Flow customData list-of-{key,value} shape). First non-empty wins.
    "field_candidates": {
        "contact_id": [
            "contact_id", "contactId", "contact.id", "contact.contact_id",
            "customData.contact_id", "customData.contactId", "data.contact_id",
        ],
        "anthology_id": [
            "anthology_id", "anthologyId", "customData.anthology_id",
            "customData.anthologyId", "data.anthology_id",
        ],
        "stage": [
            "stage", "form_stage", "customData.stage", "customData.form_stage",
            "data.stage",
        ],
        "location": [
            "location_id", "locationId", "location.id", "location",
            "companyId", "company_id", "contact.locationId",
            "customData.location_id", "customData.locationId", "data.location_id",
        ],
        "route_secret": [
            "route_secret", "_route_secret", "hook_token", "_hook_token",
            "x-anthology-secret", "x_anthology_secret",
            "headers.x-openclaw-token", "headers.x_openclaw_token",
            "headers.authorization", "authorization",
        ],
        "first_name": ["first_name", "firstName", "customData.first_name", "contact.firstName"],
        "last_name": ["last_name", "lastName", "customData.last_name", "contact.lastName"],
        "email": ["email", "customData.email", "contact.email"],
        "phone": ["phone", "customData.phone", "contact.phone"],
        "ideal_avatar": ["ideal_avatar", "idealAvatar", "q1", "Q1", "customData.ideal_avatar"],
        "niche": ["niche", "q2", "Q2", "customData.niche"],
        "primary_goal": ["primary_goal", "primaryGoal", "q3", "Q3", "customData.primary_goal"],
        "chapter_about": ["chapter_about", "chapterAbout", "customData.chapter_about"],
        "producer": ["producer", "producer_id", "producerId", "customData.producer"],
        "producer_email": ["producer_email", "producerEmail", "customData.producer_email"],
    },
    # scalar fields (safe to forward to upsert-participant; JSON-typed fields such as
    # tone_inputs / personal_stories are left to their per-stage runners, never risked here).
    "upsert_scalar_fields": [
        "first_name", "last_name", "email", "phone",
        "ideal_avatar", "niche", "primary_goal", "chapter_about",
    ],
}


# ---------------------------------------------------------------------------
# Small, dependency-free helpers
# ---------------------------------------------------------------------------
def _now() -> float:
    return time.time()


def _iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log(msg: str) -> None:
    """Operator-verbose diagnostics on stderr (never a client surface, never a secret)."""
    sys.stderr.write("[intake_router] %s\n" % msg)


def participant_key(contact_id: str, anthology_id: str) -> str:
    """The LITERAL composite primary key (KEYING LAW: contact_id, never email).
    Mirrors anthology_state.participant_key byte-for-byte; the self-test cross-checks."""
    return "%s%s%s" % (contact_id, KEY_DELIM, anthology_id)


def _is_placeholder(v) -> bool:
    return isinstance(v, str) and v.startswith("<") and v.endswith(">")


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if _is_placeholder(v):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(explicit_path=None) -> dict:
    """Merge BUILTIN_DEFAULTS <- engine-config.template.json's `intake` block <-
    resolved engine-config.json's `intake` block <- an explicit --config file.
    Missing config is fine; the built-in defaults are a complete contract."""
    cfg = dict(BUILTIN_DEFAULTS)
    candidates = []
    tmpl = SKILL_DIR / "config" / "engine-config.template.json"
    resolved = SKILL_DIR / "config" / "engine-config.json"
    if tmpl.exists():
        candidates.append(tmpl)
    if resolved.exists():
        candidates.append(resolved)
    if explicit_path:
        candidates.append(Path(explicit_path))
    for p in candidates:
        try:
            doc = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - config must never crash intake
            _log("config %s ignored (%s)" % (p, exc))
            continue
        block = doc.get("intake", doc) if isinstance(doc, dict) else {}
        # accept a few keys that live outside `intake` in the template
        if isinstance(doc, dict):
            for k in ("route_secret_label", "route_path"):
                if k in block:
                    cfg[k] = block[k]
            if "acknowledge_budget_seconds" in block:
                cfg["acknowledge_budget_seconds"] = block["acknowledge_budget_seconds"]
        cfg = _deep_merge(cfg, {k: v for k, v in block.items() if k in BUILTIN_DEFAULTS})
    return cfg


def _walk_one(obj, key):
    """One level: dict.get (case-insensitive fallback), or a list of
    {key|name|id|field: X, value|val: Y} objects (the Convert and Flow customData shape)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        lower = key.lower()
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() == lower:
                return v
        return None
    if isinstance(obj, list):
        for el in obj:
            if not isinstance(el, dict):
                continue
            name = el.get("key") or el.get("name") or el.get("id") or el.get("field")
            if isinstance(name, str) and name.lower() == key.lower():
                if "value" in el:
                    return el["value"]
                if "val" in el:
                    return el["val"]
                return el
        return None
    return None


def get_by_path(root, dotted: str):
    cur = root
    for seg in dotted.split("."):
        cur = _walk_one(cur, seg)
        if cur is None:
            return None
    return cur


def _scalar(v):
    """Normalize an extracted value to a trimmed string, or None if empty/complex."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return None


def extract(payload, logical, cfg):
    """First non-empty candidate for a logical field. Authorization values are
    de-Bearered so a forwarded 'Bearer <token>' compares cleanly."""
    for path in cfg["field_candidates"].get(logical, []):
        val = _scalar(get_by_path(payload, path))
        if val is None:
            continue
        if logical == "route_secret" and val.lower().startswith("bearer "):
            val = val[7:].strip()
        if val:
            return val
    return None


def canonical_body(payload, cfg) -> str:
    """Deterministic body string for fingerprinting and for a redacted raw preserve.
    Secret-bearing keys are ALWAYS stripped; configured volatile keys too. Falls back
    to a stable JSON dump; a non-dict/list payload stringifies as-is."""
    exclude = set(cfg.get("fingerprint_exclude_keys") or [])
    # top-level keys that may carry the route secret (strip by leaf name)
    secret_leaves = set()
    for path in cfg["field_candidates"].get("route_secret", []):
        secret_leaves.add(path.split(".")[-1].lower())

    def scrub(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                kl = k.lower() if isinstance(k, str) else k
                if isinstance(k, str) and (k in exclude or kl in secret_leaves):
                    continue
                out[k] = scrub(v)
            return out
        if isinstance(o, list):
            return [scrub(x) for x in o]
        return o

    scrubbed = scrub(payload)
    try:
        return json.dumps(scrubbed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception:  # noqa: BLE001
        return repr(scrubbed)


def redacted_raw(raw_text: str, payload, cfg) -> str:
    """Raw payload preserved for the Exceptions row, with secret fields masked.
    ALWAYS returns valid JSON (the sole writer requires --raw-submission to parse):
    a parsed payload is structurally redacted; an UNPARSEABLE body is wrapped
    verbatim under _raw_unparsed so nothing is lost and nothing is guessed."""
    if payload is None:
        return json.dumps({"_raw_unparsed": raw_text, "_captured_utc": _iso_utc()},
                          ensure_ascii=False)
    secret_leaves = set()
    for path in cfg["field_candidates"].get("route_secret", []):
        secret_leaves.add(path.split(".")[-1].lower())

    def mask(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if isinstance(k, str) and k.lower() in secret_leaves:
                    out[k] = "<REDACTED>"
                else:
                    out[k] = mask(v)
            return out
        if isinstance(o, list):
            return [mask(x) for x in o]
        return o

    try:
        return json.dumps(mask(payload), ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return json.dumps({"_raw_unparsed": raw_text, "_captured_utc": _iso_utc()},
                          ensure_ascii=False)


def compute_fingerprint(contact_id, anthology_id, stage, payload, cfg) -> str:
    """SPEC S0 idempotency key: sha256 over contact_id, anthology_id, stage, and the
    payload body (secret- and volatile-key-scrubbed). Stable across key reorderings
    and across a secret rotation, so a genuine resend deduplicates."""
    h = hashlib.sha256()
    for part in (contact_id or "", anthology_id or "", stage or "", canonical_body(payload, cfg)):
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def resolve_state_dir(cfg, args) -> Path:
    """Single source of truth for the engine state path, agreed with anthology_state:
    --state-dir > config engine.state_dir > ANTHOLOGY_STATE_DIR > OPENCLAW_DATA_DIR > ~."""
    if getattr(args, "state_dir", None):
        return Path(args.state_dir).expanduser()
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


# ---------------------------------------------------------------------------
# Read-only mirror access (tenant binding + participant cursor). Pure reads;
# the sole-writer contract governs WRITES only.
# ---------------------------------------------------------------------------
class LedgerUnreachable(Exception):
    """The mirror DB exists but could not be read (corruption/lock). -> exit 4."""


def _mirror_ro(state_dir: Path):
    """Open <state_dir>/anthology_state.db READ-ONLY. Returns a connection, or None
    when the DB does not exist yet (an unprovisioned box -> every anthology is unknown)."""
    db = Path(state_dir) / "anthology_state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con
    except sqlite3.Error as exc:
        raise LedgerUnreachable("mirror open failed: %s" % exc)


def _ro_query_one(con, sql, params):
    if con is None:
        return None
    try:
        return con.execute(sql, params).fetchone()
    except sqlite3.Error as exc:
        raise LedgerUnreachable("mirror read failed: %s" % exc)


# ---------------------------------------------------------------------------
# Dedup store (intake-owned idempotency ledger; not ledger domain data).
# ---------------------------------------------------------------------------
class DedupStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA busy_timeout=30000")
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS intake_seen ("
            "  fingerprint TEXT PRIMARY KEY,"
            "  contact_id TEXT, anthology_id TEXT, stage TEXT,"
            "  participant_key TEXT, outcome TEXT,"
            "  first_seen_utc TEXT, updated_utc TEXT, updated_epoch REAL)"
        )
        self.con.commit()

    def close(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass

    @staticmethod
    def _is_terminal(outcome) -> bool:
        return bool(outcome) and outcome.startswith(_TERMINAL_PREFIXES)

    def check_and_claim(self, fp, meta, stale_seconds):
        """Race-safe claim. Returns (status, row):
          'terminal'  -> a prior delivery already reached a DURABLE terminal outcome
                         (routed / noop / exception:*); a resend is a no-op ack
          'inflight'  -> a fresh (non-stale) in-progress claim held by a concurrent
                         worker whose durable write is NOT yet guaranteed; the caller
                         must RETRY, never no-op (a false no-op would SILENTLY DROP the
                         submission if that owner then fails and releases its claim),
                         bounded by the stale-reclaim window below
          'fresh'     -> this worker owns a brand-new claim
          'reclaimed' -> a stale/crashed in-progress claim was taken over
        """
        now = _now()
        iso = _iso_utc()
        cur = self.con.execute(
            "INSERT OR IGNORE INTO intake_seen"
            "(fingerprint,contact_id,anthology_id,stage,participant_key,outcome,"
            " first_seen_utc,updated_utc,updated_epoch) VALUES(?,?,?,?,?,?,?,?,?)",
            (fp, meta.get("contact_id"), meta.get("anthology_id"), meta.get("stage"),
             None, "in_progress", iso, iso, now),
        )
        self.con.commit()
        if cur.rowcount == 1:
            return "fresh", None
        row = self.con.execute(
            "SELECT * FROM intake_seen WHERE fingerprint=?", (fp,)).fetchone()
        if row is None:  # extremely unlikely; treat as fresh claim
            return "fresh", None
        if self._is_terminal(row["outcome"]):
            return "terminal", row
        age = now - (row["updated_epoch"] or 0)
        if age >= stale_seconds:
            self.con.execute(
                "UPDATE intake_seen SET outcome=?, updated_utc=?, updated_epoch=? "
                "WHERE fingerprint=?", ("in_progress", iso, now, fp))
            self.con.commit()
            return "reclaimed", row
        return "inflight", row

    def finalize(self, fp, outcome, participant_key=None):
        self.con.execute(
            "UPDATE intake_seen SET outcome=?, participant_key=COALESCE(?,participant_key), "
            "updated_utc=?, updated_epoch=? WHERE fingerprint=?",
            (outcome, participant_key, _iso_utc(), _now(), fp))
        self.con.commit()

    def release(self, fp):
        """Delete a claim so the NEXT delivery genuinely re-attempts. Two call
        sites, one intent -- 'this delivery did NOT reach a durable terminal
        outcome, so leave NOTHING behind that a byte-identical retry would mistake
        for a completed submission':

          * RETRYABLE FAILURE (transient writer / ledger hiccup: subprocess
            timeout, DB lock, writer rc 1/2/5): the participant or exception row
            could not be durably persisted. Finalizing to a non-terminal
            'in_progress' instead would let a byte-identical retry WITHIN
            dedup_stale_seconds classify as 'inflight' and no-op with EX_OK -- the
            webhook would see success, stop retrying, and the submission would be
            SILENTLY DROPPED with ZERO exception rows (violates SPEC S0 'NEVER
            dropped'). Deleting the claim guarantees the retry is a fresh,
            genuine re-attempt.

          * OPERATOR REPLAY (--replay; an exceptions-queue replay, an explicit S0
            TRIGGER per SPEC 4): after the operator fixes the underlying condition
            (e.g. registers the missing anthology), the prior terminal
            'exception:*' claim must be cleared so S0 re-drives instead of
            no-opping against it.

        The row is intake-PRIVATE idempotency bookkeeping, never ledger domain
        data, so deleting it is safe; the sole writer keeps the participant write
        idempotent, so a re-drive never duplicates a participant or an artifact."""
        self.con.execute("DELETE FROM intake_seen WHERE fingerprint=?", (fp,))
        self.con.commit()


# ---------------------------------------------------------------------------
# Sole-writer subprocess calls (the ONLY write path to base + mirror)
# ---------------------------------------------------------------------------
def _run_writer(subcmd_args, state_dir, timeout=25):
    """Invoke anthology_state.py <subcmd> --state-dir DIR --json ... .
    Returns (rc, parsed_json_or_None, stderr_text)."""
    if not STATE_WRITER.exists():
        raise LedgerUnreachable("sole writer missing: %s" % STATE_WRITER)
    argv = [sys.executable or "python3", str(STATE_WRITER),
            subcmd_args[0], "--state-dir", str(state_dir), "--json"] + list(subcmd_args[1:])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LedgerUnreachable("sole writer timed out (%ss): %s" % (timeout, subcmd_args[0]))
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except Exception:  # noqa: BLE001
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def upsert_participant(contact_id, anthology_id, scalars, state_dir):
    args = ["upsert-participant", "--contact-id", contact_id, "--anthology-id", anthology_id]
    for flag, val in scalars.items():
        if val:
            args.extend(["--%s" % flag.replace("_", "-"), val])
    return _run_writer(args, state_dir)


def exception_open(reason, raw_submission, state_dir):
    """Capture to the Exceptions queue with the RAW (secret-redacted) payload and a
    typed reason. Deliberately WITHOUT --participant-key: an unverified/mismatched
    submission must never mutate a healthy participant's cursor (anti-derail)."""
    args = ["exception-open", "--reason", reason, "--raw-submission", raw_submission]
    return _run_writer(args, state_dir)


# ---------------------------------------------------------------------------
# Detached stage spawn (fire-and-forget; guarantees the acknowledge budget)
# ---------------------------------------------------------------------------
def spawn_stage_detached(cfg, participant_key_val, payload_file, stage, run_dir):
    """Launch the stage job in a NEW session, fully detached, never waited on.
    stdout/stderr land in a per-run log so the operator can inspect the detached job."""
    tmpl = cfg.get("stage_spawn_cmd")
    subst = {
        "python": sys.executable or "python3",
        "skill_dir": str(SKILL_DIR),
        "scripts": str(SCRIPTS),
        "participant_key": participant_key_val,
        "payload_file": str(payload_file),
        "stage": stage or STAGE,
        "run_dir": str(run_dir),
    }
    if tmpl:
        argv = [str(x).format(**subst) for x in tmpl]
    else:
        argv = [subst["python"], str(DEFAULT_STAGE_RUNNER),
                "--participant-key", participant_key_val, "--payload", str(payload_file)]
    logpath = Path(run_dir) / "stage-spawn.log"
    try:
        logf = open(logpath, "ab")
    except OSError:
        logf = subprocess.DEVNULL
    try:
        subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
            start_new_session=True, close_fds=True, cwd=str(SKILL_DIR))
        return True
    except Exception as exc:  # noqa: BLE001 - a spawn failure must not fail the ack
        _log("stage spawn failed (non-fatal; ledger holds the cursor): %s" % exc)
        return False
    finally:
        if logf not in (subprocess.DEVNULL,):
            try:
                logf.close()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Route-secret verification (defense-in-depth; fail-closed on mismatch)
# ---------------------------------------------------------------------------
def verify_secret(payload, cfg, mode):
    """Returns (ok, note). ok=False -> route-secret refusal (exit 2)."""
    if mode == "off":
        return True, "secret check off (trusted/replay)"
    label = cfg.get("route_secret_label", "ANTHOLOGY_INTAKE_HOOK_SECRET")
    expected = os.environ.get(label, "").strip()
    presented = extract(payload, "route_secret", cfg)
    if not expected:
        if mode == "required":
            # The operator explicitly asked intake_router to be the enforcer, but the
            # expected secret is unresolved -> a provisioning defect; fail closed.
            return False, ("route secret label %s NOT SET while mode=required "
                           "(fail-closed)" % label)
        # verify_if_present on a box where the gateway is the primary enforcer
        # (OpenClaw Surface A; W0.4): never crash, warn, and do not block.
        _log("route secret label %s is NOT SET; skipping local secret check "
             "(gateway remains the enforcer)" % label)
        return True, "secret label not set (skipped)"
    if presented is None:
        if mode == "required":
            return False, "no route secret presented (mode=required)"
        return True, "no secret forwarded; gateway-enforced (verify_if_present)"
    if hmac.compare_digest(presented, expected):
        return True, "route secret verified"
    return False, "route secret mismatch"


# ---------------------------------------------------------------------------
# Hidden-field shape validation
# ---------------------------------------------------------------------------
def _bad_id_shape(v) -> bool:
    return (not v) or (KEY_DELIM in v) or (len(v) > 256)


# ---------------------------------------------------------------------------
# Stage acceptance policy (against the ledger cursor). Never guesses.
# ---------------------------------------------------------------------------
def classify_stage(stage_token, cfg, participant_row):
    """Return one of:
      'intake_new'      submitted intake form, no existing participant -> create
      'intake_confirm'  submitted intake form, participant already exists -> confirm only
      'stage_ok'        per-stage form matching the participant's current cursor
      'stage_mismatch'  recognized per-stage form but wrong/absent participant cursor
      'invalid'         missing or unrecognized stage token (-> unroutable_missing_ids)
    """
    token = (stage_token or "").strip().lower()
    if not token:
        return "invalid"
    intake_tokens = {t.lower() for t in cfg.get("intake_stage_tokens", [])}
    if token in intake_tokens:
        return "intake_new" if participant_row is None else "intake_confirm"
    fm = cfg.get("stage_form_map", {}) or {}
    entry = fm.get(token) or fm.get(stage_token)
    if entry is not None:
        legal = {str(c).lower() for c in (entry.get("legal_cursors") or [])}
        allow_new = bool(entry.get("new_participant_allowed"))
        if participant_row is None:
            return "intake_new" if allow_new else "stage_mismatch"
        cur = (participant_row["stage_cursor"] or "").lower() if participant_row else ""
        return "stage_ok" if (not legal or cur in legal) else "stage_mismatch"
    # Not the intake form and not in the map: legal only if it names a known cursor
    # AND the participant is currently at that cursor (self-describing per-stage form).
    if participant_row is None:
        return "stage_mismatch"
    cur = (participant_row["stage_cursor"] or "").lower()
    return "stage_ok" if cur == token else "stage_mismatch"


# ---------------------------------------------------------------------------
# The route: the ordered S0 pipeline (SPEC S0 PROCESS). Returns (exit_code, ack).
# ---------------------------------------------------------------------------
def route(raw_text, cfg, state_dir, args):
    t0 = _now()
    budget = float(cfg.get("acknowledge_budget_seconds", 2) or 2)

    def ack(action, code, **extra):
        elapsed_ms = int((_now() - t0) * 1000)
        body = {"ok": code == EX_OK, "stage": STAGE, "action": action,
                "elapsed_ms": elapsed_ms}
        body.update(extra)
        if elapsed_ms > budget * 1000:
            _log("acknowledge budget exceeded: %dms > %dms (action=%s)"
                 % (elapsed_ms, int(budget * 1000), action))
        return code, body

    # -- parse (never crash: an unparseable body is a typed exception, T3) ------
    payload = None
    parse_ok = True
    try:
        payload = json.loads(raw_text) if raw_text.strip() else {}
    except Exception:  # noqa: BLE001
        parse_ok = False
        payload = None

    # -- 1. route secret --------------------------------------------------------
    secret_mode = args.secret_mode or cfg.get("secret_mode", "verify_if_present")
    if args.trusted:
        secret_mode = "off"
    # Runs even on an unparseable body (extraction on {} finds no secret): SPEC orders
    # the secret check before validation, so `required` refuses a secretless body up front.
    ok, note = verify_secret(payload or {}, cfg, secret_mode)
    if not ok:
        _log("route-secret refusal: %s" % note)
        return ack("secret_refused", EX_SECRET, reason="route_secret")

    # -- extract the hidden ids and the stage ----------------------------------
    contact_id = extract(payload, "contact_id", cfg) if payload is not None else None
    anthology_id = extract(payload, "anthology_id", cfg) if payload is not None else None
    stage_token = extract(payload, "stage", cfg) if payload is not None else None
    location = extract(payload, "location", cfg) if payload is not None else None

    # -- fingerprint + dedup terminal check (no-op on a bare resend; --replay resets) --
    fp = compute_fingerprint(contact_id, anthology_id, stage_token, payload or raw_text, cfg)
    dedup = DedupStore(Path(state_dir) / "intake" / "dedup.db")
    try:
        # -- operator-initiated resolve-and-replay (an S0 TRIGGER, SPEC 4) ------
        # A byte-identical replay after the operator fixed the underlying condition
        # would otherwise hit the prior terminal 'exception:*' claim and no-op with
        # EX_OK, so the participant would NEVER be created. --replay resets that
        # intake-private claim through the router's OWN store (the clean seam; callers
        # no longer reach into dedup.db), so S0 genuinely re-drives. The sole writer
        # keeps the upsert idempotent, so a replay never duplicates a participant.
        if getattr(args, "replay", False):
            dedup.release(fp)
            _log("replay: reset any prior dedup claim for fingerprint %s... so S0 "
                 "genuinely re-drives (operator-initiated resolve-and-replay)" % fp[:12])
        status, prior = dedup.check_and_claim(
            fp, {"contact_id": contact_id, "anthology_id": anthology_id, "stage": stage_token},
            int(cfg.get("dedup_stale_seconds", 120)))
        if status == "terminal":
            # a prior delivery reached a DURABLE terminal outcome -> acknowledged no-op
            pk = prior["participant_key"] if prior is not None else None
            _log("duplicate submission (fingerprint %s..., prior=%s); acknowledged no-op"
                 % (fp[:12], prior["outcome"] if prior is not None else "terminal"))
            return ack("noop", EX_OK, fingerprint=fp, participant_key=pk, duplicate=True)
        if status == "inflight":
            # A concurrent delivery holds a fresh (non-stale) in_progress claim whose
            # durable write is NOT yet guaranteed. Returning EX_OK here would tell the
            # webhook 'success' -- but if that owner then fails and releases its claim,
            # THIS delivery was the last chance and the submission is SILENTLY DROPPED
            # (violates SPEC S0 'NEVER dropped'). Signal a RETRY instead: by the time the
            # webhook re-delivers, the owner has either reached a terminal outcome (->
            # genuine no-op) or released / gone stale (-> this delivery re-drives as owner
            # via the reclaim window). Bounded by dedup_stale_seconds. Reuses the retryable
            # ledger exit (SPEC 3.4 pins 0/2/3/4; no new exit code is invented).
            _log("submission in-flight under a concurrent non-stale claim (fingerprint "
                 "%s...); requesting retry rather than a false success" % fp[:12])
            return ack("inflight_retry", EX_LEDGER, fingerprint=fp, retryable=True)

        # helper closures that finalize the dedup outcome consistently -----------
        def capture(reason):
            raw_store = redacted_raw(raw_text, payload, cfg)
            try:
                rc, parsed, err = exception_open(reason, raw_store, state_dir)
            except LedgerUnreachable as exc:
                _log("exceptions capture could not persist (%s); releasing the claim so "
                     "the retry genuinely re-attempts (never a silent drop)" % exc)
                dedup.release(fp)
                return ack("ledger_unreachable", EX_LEDGER, reason=reason)
            if rc in (0, 4):  # 0 committed; 4 mirror committed, base queued -> durably captured
                dedup.finalize(fp, "exception:%s" % reason)
                exc_id = (parsed or {}).get("exception_id")
                if rc == 4:
                    _log("exception captured to mirror; base write queued (reconcile flushes)")
                _log("captured to Exceptions: reason=%s exception_id=%s" % (reason, exc_id))
                return ack("exception", EX_EXCEPTION, reason=reason,
                           exception_id=exc_id, fingerprint=fp)
            # the writer could not durably record the exception -> retryable
            _log("exception-open failed rc=%d err=%s; releasing the claim so the retry "
                 "genuinely re-attempts (never a silent drop)" % (rc, err))
            dedup.release(fp)
            return ack("ledger_unreachable", EX_LEDGER, reason=reason)

        # -- 2. hidden-field presence + shape ----------------------------------
        if not parse_ok:
            return capture("unroutable_missing_ids")
        if _bad_id_shape(contact_id) or _bad_id_shape(anthology_id):
            return capture("unroutable_missing_ids")
        if not (stage_token and stage_token.strip()):
            return capture("unroutable_missing_ids")

        # -- 3. tenant check + anthology existence (direct key reads; no scans) --
        con = _mirror_ro(state_dir)  # may raise LedgerUnreachable
        try:
            anth = _ro_query_one(
                con, "SELECT anthology_id, caf_location_binding FROM anthologies "
                     "WHERE anthology_id=?", (anthology_id,))
            if anth is None:
                return capture("unknown_anthology")
            binding = anth["caf_location_binding"]
            if binding is not None and str(binding).strip():
                if location is None or str(location).strip() != str(binding).strip():
                    _log("tenant mismatch: payload location != anthology binding")
                    return capture("tenant_mismatch")
            else:
                if cfg.get("tenant_missing_binding", "continue") == "reject":
                    return capture("tenant_mismatch")
                _log("anthology %s has NO location binding yet; tenant check not enforceable "
                     "(operator surface) -- continuing per tenant_missing_binding=continue"
                     % anthology_id)

            # -- resolve participant by DIRECT composite key (never list-then-filter) --
            pkey = participant_key(contact_id, anthology_id)
            part = _ro_query_one(
                con, "SELECT participant_key, stage_cursor FROM participants "
                     "WHERE participant_key=?", (pkey,))
        finally:
            if con is not None:
                con.close()

        # -- 6. stage validation against the cursor (pre-write; no ledger pollution) --
        klass = classify_stage(stage_token, cfg, part)
        if klass == "invalid":
            return capture("unroutable_missing_ids")
        if klass == "stage_mismatch":
            _log("stage mismatch: form stage=%r vs cursor=%r"
                 % (stage_token, part["stage_cursor"] if part is not None else None))
            return capture("stage_mismatch")

        if klass == "intake_confirm":
            # participant already advanced; an intake re-stamp must not overwrite
            # progress nor re-run the stage job. Acknowledge as an idempotent no-op.
            dedup.finalize(fp, "noop", participant_key=pkey)
            _log("intake re-stamp for existing participant %s; confirm-only no-op" % pkey)
            return ack("noop", EX_OK, fingerprint=fp, participant_key=pkey, duplicate=False)

        # -- 5. upsert the participant (create on first sight; via the sole writer) --
        scalars = {f: extract(payload, f, cfg) for f in cfg.get("upsert_scalar_fields", [])}
        try:
            rc, parsed, err = upsert_participant(contact_id, anthology_id, scalars, state_dir)
        except LedgerUnreachable as exc:
            _log("upsert could not reach the sole writer (%s); releasing the claim so "
                 "the retry genuinely re-attempts (never a silent drop)" % exc)
            dedup.release(fp)
            return ack("ledger_unreachable", EX_LEDGER)
        if rc == 3:  # unknown key from the writer == the anthology vanished between read+write
            return capture("unknown_anthology")
        if rc not in (0, 4):  # 4 == mirror committed, base queued (durably persisted, proceed)
            _log("upsert failed rc=%d err=%s; releasing the claim so the retry genuinely "
                 "re-attempts (never a silent drop)" % (rc, err))
            dedup.release(fp)
            return ack("ledger_unreachable", EX_LEDGER)
        pkey = (parsed or {}).get("participant_key") or pkey
        base_deferred = (rc == 4)
        if base_deferred:
            _log("participant %s written to mirror; base write queued (reconcile flushes)" % pkey)

        # -- 7. run dir + payload handoff for the detached stage job ------------
        run_dir = Path(state_dir) / "intake" / "runs" / fp[:16]
        run_dir.mkdir(parents=True, exist_ok=True)
        payload_file = run_dir / "payload.json"
        try:
            payload_file.write_text(raw_text, encoding="utf-8")
        except OSError as exc:
            _log("could not persist payload for the detached job (%s)" % exc)

        # mark routed BEFORE spawning: the durable ledger already holds the cursor,
        # so even if the box dies now the daily tick resumes; a replay no-ops.
        dedup.finalize(fp, "routed", participant_key=pkey)

        # -- 8/9. acknowledge < 2s and spawn the stage job DETACHED ------------
        spawned = False
        if not args.no_spawn:
            spawned = spawn_stage_detached(cfg, pkey, payload_file, stage_token, run_dir)
        return ack("routed", EX_OK, fingerprint=fp, participant_key=pkey,
                   spawned=spawned, base_deferred=base_deferred)
    finally:
        dedup.close()


# ---------------------------------------------------------------------------
# I/O plumbing
# ---------------------------------------------------------------------------
def _read_raw(args) -> str:
    if args.payload_json is not None:
        return args.payload_json
    if args.payload:
        return Path(args.payload).read_text(encoding="utf-8")
    # default: read stdin (the gateway transform pipes the form JSON on stdin)
    data = sys.stdin.read()
    return data


# ---------------------------------------------------------------------------
# Self-test / smoke battery (temp state dir; really shells the sole writer)
# ---------------------------------------------------------------------------
def self_test():
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="intake_router_selftest_"))
    state = tmp / "state"
    state.mkdir(parents=True, exist_ok=True)
    checks = []

    def record(label, cond):
        checks.append((label, bool(cond)))
        _log("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    # provision an anthology with a location binding through the sole writer
    rc, _, err = _run_writer(
        ["upsert-anthology", "--anthology-id", "ANTH1",
         "--caf-location-binding", "LOC-AAA", "--name", "Test Anthology"], state)
    record("provision anthology (writer rc=0)", rc == 0)

    cfg = load_config()
    cfg["secret_mode"] = "verify_if_present"

    class NS:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def call(payload_obj, **over):
        a = NS(secret_mode=None, trusted=False, no_spawn=True, replay=False,
               payload=None, payload_json=None, state_dir=str(state))
        for k, v in over.items():
            setattr(a, k, v)
        raw = payload_obj if isinstance(payload_obj, str) else json.dumps(payload_obj)
        return route(raw, cfg, state, a)

    # T4-ish: valid new submission -> routed, participant created
    good = {"contact_id": "C1", "anthology_id": "ANTH1", "stage": "intake",
            "location_id": "LOC-AAA", "first_name": "Ada", "email": "ada@example.test"}
    code, body = call(good)
    record("valid intake -> exit 0 routed", code == EX_OK and body["action"] == "routed")
    record("participant_key is C1::ANTH1", body.get("participant_key") == "C1::ANTH1")

    # participant actually exists in the mirror (direct key read)
    con = _mirror_ro(state)
    row = _ro_query_one(con, "SELECT stage_cursor FROM participants WHERE participant_key=?",
                        ("C1::ANTH1",))
    if con:
        con.close()
    record("participant row persisted by the sole writer", row is not None)

    # T5: exact duplicate -> idempotent no-op
    code, body = call(good)
    record("duplicate submission -> exit 0 no-op", code == EX_OK and body.get("duplicate"))

    # T6: wrong tenant -> tenant_mismatch exception
    bad_tenant = dict(good, contact_id="C2", location_id="LOC-WRONG")
    code, body = call(bad_tenant)
    record("wrong tenant -> exit 3 tenant_mismatch",
           code == EX_EXCEPTION and body.get("reason") == "tenant_mismatch")

    # unknown anthology -> unknown_anthology exception
    unk = dict(good, contact_id="C3", anthology_id="NOPE")
    code, body = call(unk)
    record("unknown anthology -> exit 3 unknown_anthology",
           code == EX_EXCEPTION and body.get("reason") == "unknown_anthology")

    # T3: malformed payload -> unroutable_missing_ids, never a crash
    code, body = call("{not json")
    record("malformed payload -> exit 3 unroutable_missing_ids",
           code == EX_EXCEPTION and body.get("reason") == "unroutable_missing_ids")

    # missing ids -> unroutable_missing_ids
    code, body = call({"stage": "intake", "location_id": "LOC-AAA"})
    record("missing ids -> exit 3 unroutable_missing_ids",
           code == EX_EXCEPTION and body.get("reason") == "unroutable_missing_ids")

    # T7: stage mismatch (per-stage form for a nonexistent participant)
    code, body = call({"contact_id": "C9", "anthology_id": "ANTH1",
                       "stage": "s2_tone", "location_id": "LOC-AAA"})
    record("stage mismatch -> exit 3 stage_mismatch",
           code == EX_EXCEPTION and body.get("reason") == "stage_mismatch")

    # T2 axis A: required mode with the label UNSET -> fail closed (exit 2)
    os.environ.pop("ANTHOLOGY_INTAKE_HOOK_SECRET", None)
    code, body = call(dict(good, contact_id="C7"), secret_mode="required")
    record("required + label unset -> exit 2 fail-closed", code == EX_SECRET)

    # T2 axis B: label SET, secret presented/absent/wrong
    os.environ["ANTHOLOGY_INTAKE_HOOK_SECRET"] = "s3cr3t-smoke"
    try:
        code, body = call(dict(good, contact_id="C7b"), secret_mode="required")
        record("required + presented missing -> exit 2 refusal", code == EX_SECRET)
        code, body = call(dict(good, contact_id="C8", route_secret="s3cr3t-smoke"),
                          secret_mode="required")
        record("required + correct secret -> exit 0 routed", code == EX_OK)
        code, body = call(dict(good, contact_id="C8b", route_secret="WRONG"),
                          secret_mode="required")
        record("required + wrong secret -> exit 2 refusal", code == EX_SECRET)
        # verify_if_present: a wrong presented secret is still refused (defense-in-depth)
        code, body = call(dict(good, contact_id="C8c", route_secret="WRONG"),
                          secret_mode="verify_if_present")
        record("verify_if_present + wrong secret -> exit 2 refusal", code == EX_SECRET)
    finally:
        del os.environ["ANTHOLOGY_INTAKE_HOOK_SECRET"]

    # id-shape guard: a contact_id carrying the key delimiter is rejected
    code, body = call(dict(good, contact_id="C::X"))
    record("id containing '::' -> exit 3 unroutable_missing_ids",
           code == EX_EXCEPTION and body.get("reason") == "unroutable_missing_ids")

    # -- REGRESSION (QC W1.5) FIX 1a: a transient writer failure must NEVER --------
    # silently drop on retry. Inject a one-shot upsert failure: the claim must be
    # RELEASED (not finalized 'in_progress'), so a byte-identical healthy retry
    # genuinely creates the participant instead of false-no-opping as a duplicate.
    _real_upsert = globals()["upsert_participant"]

    def _boom_upsert(*_a, **_k):
        raise LedgerUnreachable("injected transient writer failure (self-test)")

    globals()["upsert_participant"] = _boom_upsert
    drop = {"contact_id": "CDROP", "anthology_id": "ANTH1", "stage": "intake",
            "location_id": "LOC-AAA"}
    code, body = call(drop)
    record("transient upsert failure -> exit 4 retryable", code == EX_LEDGER)
    fp_drop = compute_fingerprint("CDROP", "ANTH1", "intake", drop, cfg)
    _d = DedupStore(Path(state) / "intake" / "dedup.db")
    _r = _d.con.execute(
        "SELECT outcome FROM intake_seen WHERE fingerprint=?", (fp_drop,)).fetchone()
    _d.close()
    record("failed claim RELEASED (no lingering in_progress a retry would no-op)",
           _r is None)
    globals()["upsert_participant"] = _real_upsert
    code, body = call(drop)
    record("healthy retry after transient failure -> routed (no silent drop)",
           code == EX_OK and body.get("action") == "routed"
           and body.get("participant_key") == "CDROP::ANTH1")
    con = _mirror_ro(state)
    _pr = _ro_query_one(
        con, "SELECT participant_key FROM participants WHERE participant_key=?",
        ("CDROP::ANTH1",))
    if con:
        con.close()
    record("retry actually persisted the participant (proves no drop)", _pr is not None)

    # -- FIX 1b: a fresh (non-stale) in-flight claim must RETRY, never false-ack ---
    # Seed an in_progress claim (a concurrent owner whose durable write is not yet
    # guaranteed); route must request a retry (exit 4), not return EX_OK 'success'.
    inflight = {"contact_id": "CINF", "anthology_id": "ANTH1", "stage": "intake",
                "location_id": "LOC-AAA"}
    fp_inf = compute_fingerprint("CINF", "ANTH1", "intake", inflight, cfg)
    _d = DedupStore(Path(state) / "intake" / "dedup.db")
    _d.con.execute(
        "INSERT OR REPLACE INTO intake_seen(fingerprint,contact_id,anthology_id,stage,"
        "participant_key,outcome,first_seen_utc,updated_utc,updated_epoch) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (fp_inf, "CINF", "ANTH1", "intake", None, "in_progress",
         _iso_utc(), _iso_utc(), _now()))
    _d.con.commit()
    _d.close()
    code, body = call(inflight)
    record("fresh in-flight claim -> exit 4 retry (not a false EX_OK success)",
           code == EX_LEDGER and body.get("action") == "inflight_retry")

    # -- FIX 2: --replay re-drives a captured submission after the operator fix ----
    # Capture unknown_anthology (terminal 'exception:*' claim); register the
    # anthology; a plain resend still no-ops (terminal honored) but --replay resets
    # the claim and S0 genuinely creates the participant (SPEC 4: replay is a TRIGGER).
    unk2 = {"contact_id": "CREPLAY", "anthology_id": "LATE1", "stage": "intake",
            "location_id": "LOC-LATE"}
    code, body = call(unk2)
    record("replay setup: unknown anthology -> exit 3 captured",
           code == EX_EXCEPTION and body.get("reason") == "unknown_anthology")
    rc, _, _ = _run_writer(
        ["upsert-anthology", "--anthology-id", "LATE1",
         "--caf-location-binding", "LOC-LATE", "--name", "Late Anthology"], state)
    record("operator registers the missing anthology (writer rc=0)", rc == 0)
    code, body = call(unk2)
    record("plain resend after fix -> exit 0 no-op (terminal exception claim honored)",
           code == EX_OK and body.get("duplicate"))
    code, body = call(unk2, replay=True)
    record("--replay after fix -> routed (participant genuinely created, not a no-op)",
           code == EX_OK and body.get("action") == "routed"
           and body.get("participant_key") == "CREPLAY::LATE1")
    con = _mirror_ro(state)
    _pr = _ro_query_one(
        con, "SELECT participant_key FROM participants WHERE participant_key=?",
        ("CREPLAY::LATE1",))
    if con:
        con.close()
    record("replay actually created the participant (proves it was not a no-op)",
           _pr is not None)

    # cross-check our local constants against the sibling writer, if importable
    try:
        sys.path.insert(0, str(SCRIPTS))
        import anthology_state as _as  # noqa: E402
        record("EXCEPTION_REASONS match the sole writer",
               set(ALL_EXCEPTION_REASONS) == set(_as.EXCEPTION_REASONS))
        record("participant_key matches the sole writer",
               participant_key("a", "b") == _as.participant_key("a", "b"))
    except Exception as exc:  # noqa: BLE001
        _log("  (sibling cross-check skipped: %s)" % exc)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)  # a well-behaved test leaves no litter
    ok = all(c for _, c in checks)
    _log("self-test: %d/%d passed" % (sum(1 for _, c in checks if c), len(checks)))
    return EX_OK if ok else EX_ERR


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(
        description="S0 deterministic intake and routing (Anthology Engine)")
    ap.add_argument("--payload", help="raw intake payload file (JSON)")
    ap.add_argument("--payload-json", dest="payload_json",
                    help="raw intake payload as an inline JSON string")
    ap.add_argument("--state-dir", dest="state_dir",
                    help="engine state dir (default: ANTHOLOGY_STATE_DIR / OPENCLAW_DATA_DIR / ~)")
    ap.add_argument("--config", help="explicit engine-config.json path")
    ap.add_argument("--secret-mode", dest="secret_mode",
                    choices=["verify_if_present", "required", "off"],
                    help="override the route-secret verification mode")
    ap.add_argument("--trusted", action="store_true",
                    help="trusted local invocation (exceptions replay): skip the secret check")
    ap.add_argument("--no-spawn", action="store_true",
                    help="do not spawn the detached stage job (validation / replay)")
    ap.add_argument("--replay", action="store_true",
                    help="operator-initiated resolve-and-replay (an S0 trigger): reset "
                         "any prior dedup claim for this submission so S0 genuinely "
                         "re-drives after the underlying condition was fixed (idempotent "
                         "through the sole writer; never duplicates a participant). The "
                         "clean seam for exceptions.py -- no reaching into dedup.db.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the in-process acceptance battery and exit")
    ap.add_argument("--json", action="store_true",
                    help="emit the acknowledge body as JSON on stdout (default)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        cfg = load_config(args.config)
        state_dir = resolve_state_dir(cfg, args)
        raw = _read_raw(args)
        code, body = route(raw, cfg, state_dir, args)
    except LedgerUnreachable as exc:
        _log("ledger unreachable: %s" % exc)
        print(json.dumps({"ok": False, "stage": STAGE, "action": "ledger_unreachable",
                          "detail": str(exc)}, ensure_ascii=False))
        return EX_LEDGER
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level fail-closed, never a silent pass
        _log("unexpected error: %s: %s" % (type(exc).__name__, exc))
        print(json.dumps({"ok": False, "stage": STAGE, "action": "error",
                          "detail": "%s" % exc}, ensure_ascii=False))
        return EX_ERR
    print(json.dumps(body, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
