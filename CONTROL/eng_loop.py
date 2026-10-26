#!/usr/bin/env python3
"""
PURPLE BILLBOARD — narrow engineering loop adapter (T-05).
Deterministic observer + durable action outbox + owner ACK bridge.
launchd user agent is the persistence; every tick is a fresh bounded process.

States: not_requested -> queued -> dispatched -> acknowledged -> completed
        plus unknown / failed / canceled.

Commands:
  init --run-id ID [--generation N] [--register] [--adopt]
  tick --run-id ID
  create --type T --idempotency-key K [--payload JSON] [--run-id ID]
  dispatch --action-id ID --run-id ID          (manual dispatch; tick also dispatches)
  record-ack --action-id ID --receipt-id R --owner-generation G [--body JSON]
  record-complete --action-id ID --receipt-id R [--body JSON]
  reconcile --run-id ID
  request-stop --run-id ID --generation G
  dispatch-stop --action-id ID --run-id ID
  status [--run-id ID]
  selftest

No customer, no provider, no network. Writes only under control/state/.
"""
import argparse
import calendar
import hashlib
import json
import os
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
import uuid
import errno
import fcntl

CONTROL = os.path.dirname(os.path.abspath(__file__))
HANDLER = os.path.join(CONTROL, "owner_handler.py")

# T-38: the engineering temp/cache contract, the runtime adapters and the
# restart ledger are the shared runtime package, not a second hand-rolled copy
# of any of them. `shared-utils/` is the package root that carries `runtime/`;
# the same sys.path form the runtime suite uses.
sys.path.insert(0, os.path.join(os.path.dirname(CONTROL), "shared-utils"))
from runtime.external import (  # noqa: E402
    LAYOUT, ChildProbe, Destination, DestinationHandle, MissingMount, MountIdentity,
    PathRejected, PropagationError, ReboundDestination, StorageError, UnsupportedTool,
    assert_external, open_destination, probe_child, resolve_destinations, temp_env,
    tool_output_options, verify_mount)
from runtime.host import (  # noqa: E402
    BROWSER_ABSENT, BROWSER_AVAILABLE, BROWSER_NOT_ASSUMED,
    RUNTIME_DOCKER, RUNTIME_MAC, RUNTIME_VPS, SUPPORTED_RUNTIMES,
    BindingRefused, BindIdentity, Capabilities, DockerAdapter, HostFacts, MacAdapter,
    PersistencePlan, UnsupportedHost, VpsAdapter, adapter_for, browser_capability,
    classify_runtime, detect_host, verify_persistence)
from runtime.persistence import (  # noqa: E402
    DURABLE_STATE, ENGINEERING_PROCESS, ENGINEERING_TEMP, HostRebound, RestartLedger,
    TeardownRefused, TeardownReport, teardown)

UID = os.getuid()
DOMAIN = "gui/%d" % UID
DEFAULT_LABEL = "ai.blackceo.pb-eng-loop"
DEFAULT_TMP = "/Volumes/mac mini m4/Downloads/git trees and automations/tmp/purple-billboard/pb-skill38-20261024"
DEFAULT_CACHE = "/Volumes/mac mini m4/Downloads/git trees and automations/tmp/purple-billboard-caches/pb-skill38-20261024"
_CONFIG_ENV_KEYS = ("PB_STATE_DIR", "PB_LABEL", "PB_PLIST", "PB_TMP", "PB_CACHE")

# Configuration is resolved from the CURRENT environment, never frozen at import.
# A caller may set PB_STATE_DIR / PB_LABEL / PB_PLIST / PB_TMP / PB_CACHE after this
# module is imported (cmd_selftest does exactly that), and the parent store, the
# owner-handler child and the launchd job must all agree. Capturing these at import
# time let the import-time value beat the runtime one: the child wrote the OUTER
# production store while the parent asserted on the sandbox (PBB-279 D1).
def refresh_config():
    """Re-resolve every path/identity global from the CURRENT environment."""
    global STATE, DB_PATH, EFFECTS, LOGS, TICK_LOCK, LABEL, PLIST, NATIVE_ID, TMP, CACHE
    TMP = os.environ.get("PB_TMP") or DEFAULT_TMP
    CACHE = os.environ.get("PB_CACHE") or DEFAULT_CACHE
    STATE = os.environ.get("PB_STATE_DIR") or os.path.join(CONTROL, "state")
    DB_PATH = os.path.join(STATE, "engine.db")
    EFFECTS = os.path.join(STATE, "effects")
    LOGS = os.path.join(STATE, "logs")
    TICK_LOCK = os.path.join(STATE, "tick.lock")
    LABEL = os.environ.get("PB_LABEL") or DEFAULT_LABEL
    PLIST = os.environ.get("PB_PLIST") or os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LABEL)
    NATIVE_ID = "%s/%s" % (DOMAIN, LABEL)


def external_env():
    """The environment handed to the owner-handler child and the launchd job.

    Computed at USE time so a runtime change reaches the child. Reading a cached
    import-time map here is what made the isolated selftest write the production
    store (PBB-279 D1)."""
    tmp = os.environ.get("PB_TMP") or DEFAULT_TMP
    cache = os.environ.get("PB_CACHE") or DEFAULT_CACHE
    # T-38: the temp/cache a child or the launchd job inherits is admitted through
    # the verified external-storage contract first. An internal path is a named
    # refusal (PathRejected), never a silent /tmp fallback.
    env = temp_env(tmp, bind_proven=False)
    assert_external(cache, bind_proven=False)
    env.update({"PYTHONPYCACHEPREFIX": os.path.join(cache, "pycache"),
                "npm_config_cache": os.path.join(cache, "npm")})
    for k in _CONFIG_ENV_KEYS:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


# T-38 acceptance, wired where the launcher really needs it. The adapter the
# classified runtime names is the adapter that must answer; a disagreement is a
# named refusal, never a guess across runtimes.
ADAPTERS_BY_RUNTIME = {"mac": MacAdapter, "vps": VpsAdapter, "docker": DockerAdapter}


def external_root():
    """Root of the contracted per-run layout (runtime.external LAYOUT).

    Derived from PB_TMP, never declared a second time: the temp the workers
    inherit must sit at <root>/<LAYOUT["temp"]>/<run-id> (STORAGE.md). A PB_TMP
    outside that shape is a named refusal (PathRejected); there is no second
    contract and no internal fallback."""
    tmp = os.path.normpath(os.environ.get("PB_TMP") or DEFAULT_TMP)
    root = os.path.dirname(os.path.dirname(os.path.dirname(tmp)))
    if os.path.join(root, LAYOUT["temp"], os.path.basename(tmp)) != tmp:
        raise PathRejected(
            "layout_mismatch: %r is not <root>/%s/<run-id>" % (tmp, LAYOUT["temp"]))
    return root


def _mount_root(path):
    """The mount point that carries `path`: the host bind the adapter verifies."""
    p = os.path.realpath(path)
    while not os.path.ismount(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    return p


def runtime_admission():
    """T-38 acceptance, re-derived in the launcher before anything registers.

    Every clause of the unit's acceptance is measured here on this host: the
    supported Mac/VPS/Docker adapters (classify_runtime -> adapter_for, cross-
    checked against the named classes, the host bind verified through the
    adapter), restart persistence (the run state begun on the retained ledger
    destination), and engineering temp/output/cache propagation proven with a
    real child — with no assumed browser and no internal fallback. Returns the
    admission receipt; any refusal is the contract's own named error."""
    root = external_root()
    rid = os.path.basename(os.path.normpath(os.environ.get("PB_TMP") or DEFAULT_TMP))
    facts: HostFacts = detect_host()
    runtime_name = classify_runtime(facts)
    if runtime_name not in SUPPORTED_RUNTIMES:
        raise UnsupportedHost(
            "unsupported_runtime: %r not in %s" % (runtime_name, SUPPORTED_RUNTIMES))
    adapter = adapter_for(facts, BindIdentity(root=_mount_root(root)))
    if ADAPTERS_BY_RUNTIME.get(runtime_name) is not type(adapter):
        raise UnsupportedHost(
            "adapter_mismatch: classify_runtime=%r adapter_for=%s"
            % (runtime_name, type(adapter).__name__))
    bind_identity: MountIdentity = adapter.verify_bind()
    layout_identity: MountIdentity = verify_mount(root, require_mount=False)
    caps: Capabilities = browser_capability(None)
    if caps.requires_browser or caps.browser not in (BROWSER_NOT_ASSUMED,
                                                     BROWSER_AVAILABLE,
                                                     BROWSER_ABSENT):
        raise UnsupportedHost("browser_contract: %r" % (caps,))
    dests = resolve_destinations(root, rid, create=True,
                                 require_mount=False, bind_proven=False)
    probe: ChildProbe = probe_child(dests["temp"].path, bind_proven=False, root=root)
    tools = dict((name, tool_output_options(name, dests, bind_proven=False, root=root))
                 for name in ("pip", "npm"))
    ledger_dest: Destination = dests["ledger"]
    ledger = RestartLedger(ledger_dest, run_id=rid, runtime=runtime_name,
                           host_fingerprint="%s-%s-%d" % (facts.system, facts.arch,
                                                          layout_identity.device))
    state = ledger.begin(worker_id="eng-loop-%d" % os.getuid())
    body = {
        "runtime": runtime_name,
        "supported_runtimes": list(SUPPORTED_RUNTIMES),
        "host": {"system": facts.system, "arch": facts.arch,
                 "container_markers": list(facts.container_markers),
                 "evidence": list(facts.evidence)},
        "adapter": type(adapter).__name__,
        "bind": {"root": bind_identity.path, "device": bind_identity.device,
                 "media_uuid": bind_identity.media_uuid,
                 "limitations": list(bind_identity.limitations)},
        "layout_root": {"root": root, "device": layout_identity.device,
                        "media_uuid": layout_identity.media_uuid,
                        "limitations": list(layout_identity.limitations)},
        "capabilities": {"browser": caps.browser,
                         "browser_evidence": caps.browser_evidence,
                         "requires_browser": caps.requires_browser},
        "destinations": dict((role, d.path) for role, d in dests.items()),
        "child_probe": probe.as_dict(),
        "tool_options": tools,
        "restart": {"run_id": rid, "runtime": runtime_name,
                    "run_state_path": os.path.join(ledger_dest.path, "run-state.json"),
                    "state": {"status": state.get("status"),
                              "restarts": state.get("restarts")}},
    }
    # The propagation receipt itself is published through the no-follow handle,
    # before anything registers: no-replacement, pre-write device/inode recheck.
    handle: DestinationHandle = open_destination(ledger_dest.path, expected=ledger_dest,
                                                 root=root, bind_proven=False)
    try:
        handle.replace("admission.json",
                       json.dumps(body, sort_keys=True).encode("utf-8"))
    finally:
        handle.close()
    return body


def registration_persistence(readback_output):
    """T-38: this loop's restart persistence is claimed only from a real launchd
    read-back (verify_persistence), never from the declaration."""
    plan = PersistencePlan(
        kind="launchd", identity=LABEL,
        declared="launchd user agent is this loop's persistence; verified only "
                 "from the read-back, never from this sentence",
        readback_command=("launchctl", "print", NATIVE_ID))
    return verify_persistence(plan, readback_output)


def _json_arg(raw):
    """Parse an optional JSON argument: (ok, value).

    Empty and absent stay the documented `{}`; malformed input is a refusal, never a
    traceback out of deep inside the write path (PBB-279 D4)."""
    if not raw:
        return True, {}
    try:
        return True, json.loads(raw)
    except (TypeError, ValueError):
        return False, None


refresh_config()
LEASE_RESOURCE = "eng-loop-writer"
LEASE_SECONDS = 180
OBSERVATION_SECONDS = 60
REPORT_SECONDS = 600
ACK_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 3

# ---- ready queue (PBB-076): the tick asks whether READY work exists with no live owner
ROOT = os.path.dirname(CONTROL)
READY_STATUSES = ("NOT_STARTED", "READY")
DONE_STATUSES = ("ACCEPTED_UNMERGED", "MERGED_VERIFIED", "DONE_VERIFIED")
LIVE_OWNER_STATUSES = ("RUNNING", "REVIEW")
OPEN_ACTION_STATES = ("queued", "dispatched", "acknowledged", "unknown")
# The complete reason vocabulary. A reason is always one of these five classes.
# Free text ("waiting for workflows") is not representable: valid_reason refuses it and
# the write boundary never stores it.
REASON_CLASSES = ("unmet_dependency", "file_ownership_conflict", "measured_resource",
                  "provider_restriction", "capacity_full")
# Closed restriction vocabulary: a provider_restriction detail is one of these tokens and
# nothing else. Ledger free text is mapped to RESTRICTION_DEFAULT and reported as a
# refusal in the tick output — never stored as a reason.
RESTRICTION_CODES = ("restricted", "not_in_provider_pool", "quota_exhausted", "registry_unavailable")
RESTRICTION_DEFAULT = "restricted"
RESOURCE_METRIC = "disk_available_bytes"

# ---- receipt provenance (PBB-154) ------------------------------------------
# Before this, receipts carried (receipt_id, action_id, kind, ts, body) and nothing
# else: provenance was shape-decidable only, so a byte-perfect hand-copied body was
# indistinguishable from a real one. The producer now stamps every receipt at write
# time with the writing pid, the enclosing tick id (or the receipt sequence), and the
# run id, plus marker_digest = sha256 over the canonical projection of EVERY stored
# field of that row. A row without a complete marker is refused before it is written;
# a row whose digest does not match was altered or hand-inserted and is detected.
# Rows written before the migration keep a NULL marker, are never rewritten and are
# classified UNATTRIBUTABLE-LEGACY rather than repaired.
RECEIPT_MARKER_COLUMNS = (("pid", "INTEGER"), ("run_id", "TEXT"), ("seq", "INTEGER"),
                          ("tick_id", "TEXT"), ("marker_digest", "TEXT"))
BASELINE_KEY = "provenance_baseline_receipts"
BASELINE_TS_KEY = "provenance_baseline_ts"
# Classification vocabulary. UNATTRIBUTABLE-LEGACY is a statement about what the
# store can prove, not a claim that the row is wrong.
PROV_MARKED = "MARKED"
PROV_LEGACY = "UNATTRIBUTABLE-LEGACY"
PROV_TAMPERED = "DETECTED-TAMPERED"
PROV_UNMARKED = "DETECTED-UNMARKED"
PROV_INCOMPLETE = "DETECTED-INCOMPLETE"


class ProvenanceError(RuntimeError):
    """Raised instead of writing a receipt that carries no producer marker."""


def now_epoch():
    return int(time.time())


def iso(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch() if ts is None else ts))


def ensure_dirs():
    for d in (STATE, EFFECTS, LOGS):
        os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(CACHE, "pycache"), exist_ok=True)
    os.makedirs(os.path.join(CACHE, "npm"), exist_ok=True)
    os.makedirs(TMP, exist_ok=True)


def connect():
    ensure_dirs()
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA synchronous=FULL")
    schema(db)
    return db


def schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS actions(
      action_id TEXT PRIMARY KEY,
      idempotency_key TEXT NOT NULL UNIQUE,
      action_type TEXT NOT NULL,
      payload TEXT NOT NULL,
      state TEXT NOT NULL,
      owner_generation INTEGER NOT NULL,
      owner_run_id TEXT NOT NULL,
      created_ts TEXT NOT NULL,
      due_epoch INTEGER NOT NULL,
      dispatch_ts TEXT,
      ack_ts TEXT,
      completion_ts TEXT,
      ack_receipt_id TEXT,
      completion_receipt_id TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT
    );
    CREATE TABLE IF NOT EXISTS events(
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      kind TEXT NOT NULL,
      action_id TEXT,
      detail TEXT
    );
    CREATE TABLE IF NOT EXISTS receipts(
      receipt_id TEXT PRIMARY KEY,
      action_id TEXT NOT NULL,
      kind TEXT NOT NULL,
      ts TEXT NOT NULL,
      body TEXT NOT NULL,
      pid INTEGER,
      run_id TEXT,
      seq INTEGER,
      tick_id TEXT,
      marker_digest TEXT
    );
    CREATE TABLE IF NOT EXISTS ticks(
      tick_id TEXT PRIMARY KEY,
      ts TEXT NOT NULL,
      pid INTEGER NOT NULL,
      run_id TEXT,
      cursor_before INTEGER NOT NULL,
      cursor_after INTEGER NOT NULL,
      dispatched INTEGER NOT NULL,
      note TEXT
    );
    CREATE TABLE IF NOT EXISTS reports(
      report_id TEXT PRIMARY KEY,
      ts TEXT NOT NULL,
      body TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS leases(
      resource TEXT PRIMARY KEY,
      owner_generation INTEGER NOT NULL,
      owner_run_id TEXT NOT NULL,
      acquired_ts TEXT NOT NULL,
      expires_epoch INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS unit_queue(
      unit_id TEXT PRIMARY KEY,
      repo_alias TEXT,
      first_ready_ts TEXT NOT NULL,
      ready_ticks INTEGER NOT NULL,
      last_tick_id TEXT,
      last_outcome TEXT NOT NULL,
      last_reason TEXT,
      last_reason_detail TEXT,
      action_id TEXT,
      updated_ts TEXT NOT NULL
    );
    """)
    migrate_receipts_provenance(db)
    db.commit()


def meta_get(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def meta_set(db, key, value):
    db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))


def event(db, kind, action_id=None, detail=None):
    db.execute("INSERT INTO events(ts,kind,action_id,detail) VALUES(?,?,?,?)",
               (iso(), kind, action_id, json.dumps(detail) if detail is not None else None))


def migrate_receipts_provenance(db):
    """Add the producer-marker columns and freeze the pre-migration receipt ids.

    Idempotent and non-destructive: an ALTER runs only for a column that is absent,
    no existing receipt is UPDATEd or DELETEd, and the baseline is written only when
    it has not been recorded yet. A second run issues zero statements, so the store
    bytes are unchanged — see test_receipt_provenance.py::test_migration_is_idempotent.
    """
    have = {r["name"] for r in db.execute("PRAGMA table_info(receipts)")}
    for name, decl in RECEIPT_MARKER_COLUMNS:
        if name not in have:
            db.execute("ALTER TABLE receipts ADD COLUMN %s %s" % (name, decl))
    if db.execute("SELECT value FROM meta WHERE key=?", (BASELINE_KEY,)).fetchone() is None:
        ids = [r["receipt_id"] for r in db.execute("SELECT receipt_id FROM receipts ORDER BY receipt_id")]
        # ponytail: the baseline id list is written once and grows with the pre-migration
        # receipt count. Fine for this store (64 rows); replace with MAX(rowid) + a digest
        # of the id list if a store ever holds millions of pre-migration receipts.
        db.execute("INSERT INTO meta(key,value) VALUES(?,?)", (BASELINE_KEY, json.dumps(ids)))
        db.execute("INSERT INTO meta(key,value) VALUES(?,?)", (BASELINE_TS_KEY, iso()))
    db.commit()


def provenance_baseline_ids(db):
    """Receipt ids frozen at the migration. Empty set when no baseline is recorded,
    which makes every unmarked row look hand-written (fail closed)."""
    row = db.execute("SELECT value FROM meta WHERE key=?", (BASELINE_KEY,)).fetchone()
    if not row:
        return set()
    try:
        return set(json.loads(row["value"]))
    except ValueError:
        return set()


def marker_complete(marker):
    return bool(marker) and all(marker.get(k) is not None for k in ("pid", "run_id", "seq"))


def marker_digest_of(receipt_id, action_id, kind, ts, body, marker):
    """sha256 over the canonical projection of every stored field of the row."""
    canon = {"receipt_id": receipt_id, "action_id": action_id, "kind": kind,
             "ts": ts, "body": body,
             "pid": marker.get("pid"), "run_id": marker.get("run_id"),
             "seq": marker.get("seq"), "tick_id": marker.get("tick_id")}
    return hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def receipt_marker(db, action_id, tick_id=None):
    """The producer stamp. Refuses to hand back a marker that is not complete, so a
    receipt can never be written without one."""
    run_id = None
    if action_id:
        row = db.execute("SELECT owner_run_id FROM actions WHERE action_id=?", (action_id,)).fetchone()
        if row:
            run_id = row["owner_run_id"]
    run_id = run_id or meta_get(db, "owner_run_id")
    seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 AS n FROM receipts").fetchone()["n"]
    marker = {"pid": os.getpid(), "run_id": run_id, "seq": int(seq),
              "tick_id": tick_id if tick_id is not None else os.environ.get("PB_TICK_ID")}
    if not marker_complete(marker):
        raise ProvenanceError("receipt marker incomplete: %s" % json.dumps(
            {k: marker.get(k) for k in ("pid", "run_id", "seq", "tick_id")}, sort_keys=True))
    return marker


def classify_receipt(row, baseline_ids=None):
    """What the store can prove about one receipt row.

    MARKED                producer stamp present and marker_digest matches the row
    UNATTRIBUTABLE-LEGACY no stamp, and the id predates the migration baseline
    DETECTED-UNMARKED     no stamp, written after the fix: hand-inserted
    DETECTED-INCOMPLETE   a partial stamp: hand-inserted
    DETECTED-TAMPERED     a stamp whose marker_digest does not match the row
    """
    if row is None:
        return "MISSING"
    fields = ("pid", "run_id", "seq", "tick_id", "marker_digest")
    vals = [row[f] for f in fields]
    marker = dict(zip(fields[:4], vals[:4]))
    digest = row["marker_digest"]
    if all(v is None for v in vals):
        ids = baseline_ids if baseline_ids is not None else set()
        return PROV_LEGACY if row["receipt_id"] in ids else PROV_UNMARKED
    if not marker_complete(marker) or digest is None:
        return PROV_INCOMPLETE
    if marker_digest_of(row["receipt_id"], row["action_id"], row["kind"], row["ts"],
                        row["body"], marker) != digest:
        return PROV_TAMPERED
    return PROV_MARKED


def receipt(db, action_id, kind, body, receipt_id=None, tick_id=None):
    marker = receipt_marker(db, action_id, tick_id=tick_id)  # refuses before any write
    rid = receipt_id or ("rcpt-%s-%s-%s" % (kind, action_id.split("-")[-1], uuid.uuid4().hex[:8]))
    ts = iso()
    stored = json.dumps(body, sort_keys=True)
    digest = marker_digest_of(rid, action_id, kind, ts, stored, marker)
    db.execute("INSERT INTO receipts(receipt_id,action_id,kind,ts,body,pid,run_id,seq,tick_id,marker_digest) "
               "VALUES(?,?,?,?,?,?,?,?,?,?)",
               (rid, action_id, kind, ts, stored, marker["pid"], marker["run_id"],
                marker["seq"], marker["tick_id"], digest))
    row = db.execute("SELECT * FROM receipts WHERE receipt_id=?", (rid,)).fetchone()
    verdict = classify_receipt(row, provenance_baseline_ids(db))
    if verdict != PROV_MARKED:
        raise ProvenanceError("receipt %s refused after write: %s" % (rid, verdict))
    return rid


def tick_lock():
    """Single-instance guard. Returns fd or None if another tick holds it."""
    ensure_dirs()
    try:
        fd = os.open(TICK_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, ("%d %s\n" % (os.getpid(), iso())).encode())
    return fd


def acquire_lease(db, run_id, generation):
    row = db.execute("SELECT * FROM leases WHERE resource=?", (LEASE_RESOURCE,)).fetchone()
    t = now_epoch()
    if row and row["expires_epoch"] > t and row["owner_run_id"] != run_id:
        return False, "lease_held_by:%s:gen%d" % (row["owner_run_id"], row["owner_generation"])
    db.execute("""INSERT INTO leases(resource,owner_generation,owner_run_id,acquired_ts,expires_epoch)
                  VALUES(?,?,?,?,?)
                  ON CONFLICT(resource) DO UPDATE SET owner_generation=excluded.owner_generation,
                    owner_run_id=excluded.owner_run_id, acquired_ts=excluded.acquired_ts,
                    expires_epoch=excluded.expires_epoch""",
               (LEASE_RESOURCE, generation, run_id, iso(), t + LEASE_SECONDS))
    return True, "lease_acquired"


def release_lease(db, run_id):
    row = db.execute("SELECT owner_run_id FROM leases WHERE resource=?", (LEASE_RESOURCE,)).fetchone()
    if row and row["owner_run_id"] == run_id:
        db.execute("DELETE FROM leases WHERE resource=?", (LEASE_RESOURCE,))


def owner_generation(db):
    return int(meta_get(db, "owner_generation", "0"))


def ts_epoch(text):
    """iso() UTC text -> epoch seconds. None when the text is not our own format."""
    try:
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def reconcile_unknown(db, run_id=None, generation=None):
    """Unfinished work is neither silently re-run nor silently stranded.

    Window 1 (pre-ACK): dispatched with no ACK past the ACK window is unknown,
    never silently re-run.
    Window 2 (post-ACK, pre-completion): ACK recorded but no completion past the ACK
    window is RE-DISPATCHED (bounded by MAX_ATTEMPTS, then unknown). Re-dispatch is
    at-most-once at the effect layer because owner_handler.effect_once keeps the first
    writer and returns the prior record on any repeat, so a re-dispatch either performs
    the missing effect or records the one already performed. The disposition is written
    into the event detail, never left implicit.
    """
    t = now_epoch()
    rows = db.execute("SELECT * FROM actions WHERE state IN ('dispatched','acknowledged')").fetchall()
    changed = []
    for r in rows:
        age = t - r["due_epoch"]
        if r["ack_ts"] is None:
            if age > ACK_TIMEOUT_SECONDS:
                if r["attempts"] < MAX_ATTEMPTS:
                    db.execute("UPDATE actions SET state='queued', last_error=? WHERE action_id=? AND state='dispatched'",
                               ("ack_timeout_requeue_attempt_%d" % (r["attempts"] + 1), r["action_id"]))
                    event(db, "action_requeued_unknown", r["action_id"], {"reason": "ack_timeout"})
                    changed.append((r["action_id"], "requeued"))
                else:
                    db.execute("UPDATE actions SET state='unknown', last_error=? WHERE action_id=? AND state='dispatched'",
                               ("ack_timeout_attempts_exhausted", r["action_id"]))
                    event(db, "action_unknown", r["action_id"], {"reason": "ack_timeout"})
                    changed.append((r["action_id"], "unknown"))
            continue
        # ---- window 2: ACK recorded, completion missing ----
        if r["action_type"] == "eng_loop.shutdown":
            # A stop ACK is never completion. The conductor bridge (dispatch-stop)
            # owns the stop read-back; the in-job tick must not boot itself out.
            if r["last_error"] != "ack_without_completion_stop_owned":
                db.execute("UPDATE actions SET last_error=? WHERE action_id=? "
                           "AND state IN ('dispatched','acknowledged') AND completion_receipt_id IS NULL",
                           ("ack_without_completion_stop_owned", r["action_id"]))
                event(db, "action_ack_gap_stop_owned", r["action_id"],
                      {"reason": "ack_without_completion", "disposition": "conductor_bridge_only",
                       "ack_receipt_id": r["ack_receipt_id"], "run_id": run_id, "generation": generation})
                changed.append((r["action_id"], "stop_owned"))
            continue
        ack_epoch = ts_epoch(r["ack_ts"])
        if ack_epoch is None or t - ack_epoch <= ACK_TIMEOUT_SECONDS:
            continue  # inside the ACK->completion window, or an unverifiable timestamp
        base = {"reason": "ack_without_completion", "ack_receipt_id": r["ack_receipt_id"],
                "attempts": r["attempts"], "ack_age_seconds": t - ack_epoch,
                "recovery_owner_run_id": run_id, "recovery_owner_generation": generation}
        states = "('dispatched','acknowledged')"
        if (generation is not None and r["owner_generation"] != generation) or \
           (run_id is not None and r["owner_run_id"] != run_id):
            db.execute("UPDATE actions SET state='unknown', last_error=? WHERE action_id=? "
                       "AND state IN " + states + " AND completion_receipt_id IS NULL",
                       ("ack_without_completion_stale_owner", r["action_id"]))
            event(db, "action_ack_gap_unknown", r["action_id"],
                  dict(base, disposition="mark_unknown_stale_owner",
                       action_owner_generation=r["owner_generation"], action_owner_run_id=r["owner_run_id"]))
            changed.append((r["action_id"], "unknown_stale_owner"))
            continue
        if r["attempts"] < MAX_ATTEMPTS:
            cur = db.execute("UPDATE actions SET state='queued', last_error=? WHERE action_id=? "
                             "AND state IN " + states + " AND completion_receipt_id IS NULL",
                             ("ack_without_completion_requeue_attempt_%d" % (r["attempts"] + 1), r["action_id"]))
            if cur.rowcount == 1:
                event(db, "action_ack_gap_requeued", r["action_id"],
                      dict(base, disposition="redispatch",
                           effect_policy="effect_once_guard:at_most_once_across_redispatches"))
                changed.append((r["action_id"], "requeued"))
        else:
            db.execute("UPDATE actions SET state='unknown', last_error=? WHERE action_id=? "
                       "AND state IN " + states + " AND completion_receipt_id IS NULL",
                       ("ack_without_completion_attempts_exhausted", r["action_id"]))
            event(db, "action_ack_gap_unknown", r["action_id"],
                  dict(base, disposition="mark_unknown_attempts_exhausted"))
            changed.append((r["action_id"], "unknown"))
    return changed


def run_handler(action, run_id, generation):
    payload = json.loads(action["payload"])
    cmd = [sys.executable, "-I", HANDLER,
           "--action-id", action["action_id"],
           "--idempotency-key", action["idempotency_key"],
           "--action-type", action["action_type"],
           "--owner-generation", str(generation),
           "--run-id", run_id,
           "--payload", json.dumps(payload, sort_keys=True),
           "--adapter", os.path.abspath(__file__)]
    env = dict(os.environ)
    env.update(external_env())
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=env,
                           cwd=CONTROL)
        return p.returncode, p.stdout.strip()[-2000:], p.stderr.strip()[-2000:]
    except subprocess.TimeoutExpired:
        return 124, "", "handler_timeout"


def dispatch_action(db, run_id, generation, action_id):
    """Move ONE queued action to dispatched and run the owner bridge over it.
    Returns the dispatch record, or None when the action was no longer queued."""
    cur = db.execute("UPDATE actions SET state='dispatched', dispatch_ts=?, attempts=attempts+1 "
                     "WHERE action_id=? AND state='queued'", (iso(), action_id))
    if cur.rowcount != 1:
        return None
    fresh = db.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
    event(db, "action_dispatched", action_id, {"attempt": fresh["attempts"], "owner_run_id": run_id})
    # release the write lock BEFORE the owner handler writes its ACK receipt
    db.commit()
    rc, out, err = run_handler(fresh, run_id, generation)
    after = db.execute("SELECT state FROM actions WHERE action_id=?", (action_id,)).fetchone()
    if rc != 0 and after["state"] == "dispatched":
        attempts = fresh["attempts"]
        if attempts >= MAX_ATTEMPTS:
            db.execute("UPDATE actions SET state='failed', last_error=? WHERE action_id=? AND state='dispatched'",
                       (err or "handler_rc_%d" % rc, action_id))
            event(db, "action_failed", action_id, {"rc": rc, "err": err})
        else:
            db.execute("UPDATE actions SET state='queued', last_error=? WHERE action_id=? AND state='dispatched'",
                       (err or "handler_rc_%d" % rc, action_id))
            event(db, "action_retry", action_id, {"rc": rc})
    return {"action_id": action_id, "type": fresh["action_type"], "handler_rc": rc,
            "state_after": after["state"], "stdout": out, "stderr": err}


def dispatch_queued(db, run_id, generation, limit=20, ready_queue_tail=True):
    dispatched = []
    rows = db.execute("""SELECT * FROM actions WHERE state='queued' AND due_epoch<=?
                         ORDER BY created_ts LIMIT ?""", (now_epoch(), limit)).fetchall()
    for a in rows:
        rec = dispatch_action(db, run_id, generation, a["action_id"])
        if rec:
            dispatched.append(rec)
    if ready_queue_tail:
        # the action_failed / action_retry events above are events of this loop, so the
        # ready-queue step runs on them too. Record mode only: a dispatch from inside a
        # dispatch would be a second writer and would recurse through the owner bridge.
        ready_queue_step(db, run_id, generation, allow_dispatch=False)
    return dispatched


# ------------------------------------------------------------------ ready queue
# PBB-076. The tick asks, every OBSERVATION_SECONDS and on every completion/failure
# event, whether READY work exists with no live owner. Idle capacity is never
# invisible: every such unit is either dispatched or carries a machine-readable
# reason from REASON_CLASSES. Dispatch stays with the single tick writer (tick lock +
# lease); the step itself is what runs everywhere.

def unit_ledger_path():
    """Where units, declared prerequisites and file ownership live. Read-only input."""
    return os.environ.get("PB_UNIT_LEDGER") or os.path.join(ROOT, "live-ledgers", "build.json")


def resources_ledger_path():
    return os.environ.get("PB_RESOURCES_LEDGER") or os.path.join(ROOT, "live-ledgers", "resources.json")


def read_ledger(path):
    try:
        with open(path) as f:
            return json.load(f), None
    except (OSError, ValueError) as e:
        return None, "%s: %s" % (path, e)


def unit_prereqs(unit):
    """Declared prerequisites, in declaration order, de-duplicated."""
    out = []
    for key in ("depends_on", "preparation_depends_on", "build_depends_on", "integration_depends_on"):
        for dep in unit.get(key) or []:
            if dep not in out:
                out.append(dep)
    return out


def _case_flip(name):
    """The same name with every letter's case flipped, used only as a probe spelling."""
    return "".join(c.lower() if c.isupper() else c.upper() for c in name)


def _nearest_existing(path):
    """The deepest ancestor of path that resolves on disk (path itself included)."""
    d = os.path.abspath(path or ".")
    while not os.path.lexists(d):
        parent = os.path.dirname(d)
        if parent == d:
            return d
        d = parent
    return d


def fs_case_insensitive(path):
    """PBB-096: are names where path lives matched case-insensitively?

    MEASURED from the filesystem, never assumed — os.path.normcase is a no-op on posix,
    so it cannot answer this. The test is os.path.samefile(anchor, case_flip(anchor)):
    on a case-insensitive volume the flipped spelling of an existing name IS that file,
    so the two are the same inode; on a case-sensitive volume it is another name (or no
    name at all) and samefile says False. Writes nothing. When path itself resolves
    nowhere, the probe anchors on its deepest existing ancestor, which is on the volume
    the claim would live on. If no anchor carries a cased letter the answer is False —
    the safe direction, since case-sensitive keys never merge two distinct names."""
    probe = _nearest_existing(path)
    while True:
        flipped = _case_flip(probe)
        if flipped != probe:
            try:
                return os.path.samefile(probe, flipped)
            except OSError:
                return False
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent


def canonical_claim_parts(path):
    """PBB-103: (canonical spelling, resolved) for one declared file claim. See
    canonical_claim. The spelling is what a reason NAMES; the claim's identity is
    filesystem-derived and lives in claim_key (PBB-106)."""
    if not isinstance(path, str) or not path:
        return path, False
    probe = path.rstrip("/") or "/"
    norm = os.path.normpath(probe)
    try:
        resolved = os.path.lexists(probe)
        key = os.path.realpath(probe) if resolved else norm
    except (OSError, ValueError):
        resolved, key = False, norm
    return unicodedata.normalize("NFC", key), resolved


def canonical_claim(path):
    """PBB-103: the canonical spelling of one declared file claim.

    One file must not be claimable under several spellings. ORDER OF OPERATIONS:

      1. RESOLVE FIRST — os.path.realpath runs on the spelling AS DECLARED, so symlinks
         and '..' are settled by the filesystem against the real tree. Lexical
         collapsing before resolution is what let ONE inode produce two keys: with
         shared/up -> '.', 'shared/up/../shared/config.json' IS shared/config.json, but
         normpath turns it into 'shared/shared/config.json' first — a path that does not
         exist — and the clash test then never fires. A trailing separator is stripped
         before probing because it makes lstat fail with ENOTDIR on a file that is there.
      2. NFC SECOND — 'cafe\\u0301.json' and 'caf\\u00e9.json' are ONE file on this APFS
         volume, and realpath hands back each spelling verbatim, so the resolved path is
         normalised before anything compares or prints it.
      3. casefold LAST, in the claim identity (claim_key / _fold_name), and only where the
         volume is measured to match names case-insensitively.

    A claim that resolves nowhere is SAID SO (canonical_claim_parts returns resolved=False)
    and keeps a deterministic lexical spelling: normpath still collapses 'shared/x/',
    './shared/x', 'shared//x' and a lexical '..' onto one spelling, while absolutising it
    would bake in the loop's cwd and change the spelling between runs. No prefix-matching —
    only equality of claim identities merges claims, so 'config.json' and 'config.json.bak',
    or 'src' and 'srcx', stay two files."""
    return canonical_claim_parts(path)[0]


def _fold_name(text, fold):
    """NFC first (PBB-103), then lower() exactly where the filesystem is measured to match
    names case-insensitively (PBB-096). lower(), not casefold(): names differing by more
    than case must never be merged."""
    text = unicodedata.normalize("NFC", text)
    return text.lower() if fold else text


def _resolve(probe):
    """The filesystem's own spelling of one declared claim: symlinks and '..' are settled
    against the real tree, and a component that is not there is settled lexically, so the
    answer is total. This is what makes 'nope/../shared/gone.json' and 'shared/gone.json'
    one file even though the kernel cannot walk the first spelling at all."""
    try:
        return os.path.realpath(probe)
    except (OSError, ValueError):
        return None


def _entry_identity(resolved, fold):
    """('entry', resolved parent, leaf name) for one declared claim — the directory entry
    it names. This is the identity a claim carries from the MOMENT it is claimed: a file
    that does not exist yet is identified by the entry it will occupy, so two spellings of
    one future file cannot split while it is being written."""
    parent, leaf = os.path.split(resolved)
    return ("entry", _fold_name(parent, fold), _fold_name(leaf, fold))


def claim_entry(path):
    """PBB-106: the directory-entry identity of one declared claim, ('entry', parent, leaf)
    — the RESOLVED parent directory (which may exist and may be symlinked) plus the leaf
    name. Returns None when the claim cannot be resolved at all."""
    if not isinstance(path, str) or not path:
        return None
    probe = path.rstrip("/") or "/"
    resolved = _resolve(probe)
    return None if resolved is None else _entry_identity(resolved, fs_case_insensitive(probe))


def claim_identities(path):
    """PBB-106: (strongest identity, every identity) for one declared file claim. File
    identity follows the INODE, not the spelling:

      ('ino', st_dev, st_ino)  the leaf exists. The device and inode the filesystem
                               reports for it: two directory entries that are one file
                               (a hard link) collide here, and nothing else does. String
                               canonicalisation cannot see a hard link at all — only the
                               filesystem can.
      ('entry', parent, leaf)  the leaf does not exist yet — the resolved parent plus the
                               leaf name (claim_entry), so a file about to be written has
                               one stable identity from the moment it is claimed.
      ('lex', spelling)        nothing could be resolved at all — a deterministic lexical
                               key (normpath, NFC, measured casefold), and SAID SO:
                               canonical_claim_parts reports resolved=False.

    The second element carries EVERY identity the claim has: the entry identity stays on
    the claim after the inode appears, so a claim taken before a file exists still
    collides with one taken after it."""
    if not isinstance(path, str) or not path:
        return path, frozenset([path])
    probe = path.rstrip("/") or "/"
    fold = fs_case_insensitive(probe)
    resolved = _resolve(probe)
    entry = None if resolved is None else _entry_identity(resolved, fold)
    try:
        st = os.stat(resolved if resolved is not None else probe)  # follows symlinks
    except (OSError, ValueError):
        st = None
    if st is not None:
        key = ("ino", st.st_dev, st.st_ino)
    elif entry is not None:
        key = entry
    else:
        key = ("lex", _fold_name(os.path.normpath(probe), fold))
    return key, frozenset(k for k in (key, entry) if k is not None)


def claim_key(path):
    """Comparison key for a claim: its strongest filesystem identity (PBB-106, see
    claim_identities) — the device and inode when the file is there, the resolved parent
    plus the leaf name when it is not. Unicode NFC and the measured casefold (PBB-096)
    are applied on top to the spellings that carry one (see _fold_name)."""
    return claim_identities(path)[0]


def claim_tokens(path):
    """Every identity one declared claim carries (PBB-106). Two claims are one file when
    their sets INTERSECT: the inode is what merges hard links, and the entry identity is
    what keeps a claim stable across the moment its file is created."""
    return claim_identities(path)[1]


def unit_claims(unit):
    """[(canonical spelling, claim tokens)] for one unit: the name a reason prints for
    each file it owns, beside the filesystem identity that file is CLAIMED under (PBB-106).
    The identity is taken from the spelling AS DECLARED — the canonical spelling of a claim
    through a symlinked '..' is its lexical collapse, which is no longer the same directory
    entry. Two spellings of one file — including two hard-linked names of one inode —
    collapse to the first spelling seen; the file it names is still claimed, never dropped.
    Overlap between two units' sets blocks co-dispatch."""
    declared = unit.get("owned_files") or []
    if not declared:
        art = unit.get("artifact")
        declared = [art] if art else []
    out = {}
    for p in declared:
        out.setdefault(claim_key(p), (canonical_claim(p), claim_tokens(p)))
    return list(out.values())


def unit_files(unit):
    """The file set this unit owns, in canonical spelling, one entry per FILE. See
    unit_claims — the spelling a reason names."""
    return [name for name, _ in unit_claims(unit)]


def restriction_token(detail):
    """Closed-vocabulary gate for a provider restriction detail. A declared code passes
    through; anything else is ledger free text and is mapped to RESTRICTION_DEFAULT with
    refused=True so the tick reports the refusal instead of storing the text."""
    if isinstance(detail, str) and detail in RESTRICTION_CODES:
        return detail, False
    return RESTRICTION_DEFAULT, True


def provider_restriction(unit, resources):
    """Declared provider restriction for the unit's required alias, or None.
    Declared only: the ledger's provider_pools entry is the source, never a guess.
    Returns (required_alias, code, refused); code is always a RESTRICTION_CODES token."""
    alias = unit.get("required_alias")
    if not alias:
        return None
    for pool in (resources or {}).get("provider_pools") or []:
        if pool.get("alias") != alias:
            continue
        if pool.get("restricted") or pool.get("available") is False:
            code, refused = restriction_token(pool.get("restriction_detail") or pool.get("evidence"))
            return alias, code, refused
        return None
    return alias, "not_in_provider_pool", False


def measure_resource(resources):
    """Live measurement against the declared reserve floor. (metric, value, floor)."""
    floor = ((resources or {}).get("storage_census") or {}).get("reserve_floor_bytes")
    return RESOURCE_METRIC, shutil.disk_usage(STATE).free, floor


def repo_ceiling(resources):
    """Per-REPOSITORY dispatch ceiling. Deliberately not a global concurrent-agent cap:
    the platform ceilings (max_agents_per_workflow / platform_max_workflows_global /
    max_agents_global) are untouched and no blanket number is added below them."""
    env = os.environ.get("PB_MAX_CONCURRENT_PER_REPO")
    if env:
        return int(env)
    return int((resources or {}).get("max_agents_per_workflow") or 10)


def valid_reason(reason):
    if not isinstance(reason, str) or "waiting" in reason.lower():
        return False
    return any(reason == c or reason.startswith(c + ":") for c in REASON_CLASSES)


def ready_queue_step(db, run_id, generation, tick_id=None, allow_dispatch=False):
    """Compute READY work with no live owner, dispatch it when capacity allows, and
    persist a machine-readable reason per unit when it cannot. Returns the summary the
    loop prints. ready_ticks counts TICKS (tick_id is not None), so the two-tick idle
    rule is two ticks, not two events."""
    ul, rl = unit_ledger_path(), resources_ledger_path()
    units_doc, uerr = read_ledger(ul)
    resources, rerr = read_ledger(rl)
    units = [u for u in ((units_doc or {}).get("tasks") or []) if u.get("id")]
    by_id = {u["id"]: u for u in units}
    done = {i for i, u in by_id.items() if u.get("status") in DONE_STATUSES}
    dispatched_action = {}
    for r in db.execute("SELECT action_id, idempotency_key, state FROM actions WHERE idempotency_key LIKE 'unit:%'").fetchall():
        dispatched_action[r["idempotency_key"].split(":", 1)[1]] = {"action_id": r["action_id"], "state": r["state"]}
    inflight = {}
    for r in db.execute("SELECT payload, state FROM actions WHERE action_type='unit.dispatch' "
                        "AND state IN ('%s')" % "','".join(OPEN_ACTION_STATES)).fetchall():
        repo = json.loads(r["payload"]).get("repo_alias") or ""
        inflight[repo] = inflight.get(repo, 0) + 1
    metric, value, floor = measure_resource(resources)
    ceiling = repo_ceiling(resources)
    # PBB-092: files a live owner already holds are claimed before any dispatch, from the
    # same ledger the live-owner check below trusts. Otherwise a unit skipped for having a
    # live owner never contributes its files and file_ownership_conflict cannot fire on it.
    # PBB-096: claims are held as canonical keys, so one file cannot dodge the check by
    # being declared under a trailing slash, a './' prefix, a different case or a symlink.
    # PBB-103: the same holds for a symlinked '..' and for a different Unicode
    # normalisation of one name — the key is built resolve-first, then NFC, then case.
    # PBB-106: and for a HARD LINK — one inode is one claim however it is named — and for
    # a file that does not exist yet, which is claimed by its resolved parent plus its leaf
    # name from the moment it is claimed. Claim identity is filesystem-derived: see
    # claim_identities.
    claimed_files = set()
    for u in units:
        if u.get("status") in DONE_STATUSES:
            continue  # a finished unit holds nothing, whatever assignment it still carries
        if u.get("assigned_native_owner") or u.get("status") in LIVE_OWNER_STATUSES:
            for _, toks in unit_claims(u):
                claimed_files.update(toks)
    summary = {"ledger": ul, "ledger_error": uerr, "resources": rl,
               "resources_error": rerr, "ledger_units": len(units),
               "measured": {"%s" % metric: value, "reserve_floor_bytes": floor},
               "repo_ceiling": ceiling, "dispatched": [], "reasons": [], "refused": [],
               "idle_two_ticks": [], "ready_no_owner": [], "already_dispatched": [],
               "blocked": [], "unclassified": [], "ok": True}
    for uid in sorted(dispatched_action):
        summary["already_dispatched"].append(dict(unit_id=uid, **dispatched_action[uid]))
    touched = set()
    for uid in sorted(by_id):
        unit = by_id[uid]
        if unit.get("status") not in READY_STATUSES or uid in dispatched_action:
            continue
        if unit.get("assigned_native_owner") or unit.get("status") in LIVE_OWNER_STATUSES:
            continue  # a live owner already holds it
        touched.add(uid)
        repo = unit.get("repo_alias") or ""
        claims = unit_claims(unit)
        files = [name for name, _ in claims]
        dispatched_id = None
        unmet = [p for p in unit_prereqs(unit) if p not in done]
        reason = detail = refusal = None
        if unmet:
            reason, detail = "unmet_dependency:%s" % unmet[0], {"unmet": unmet}
        else:
            summary["ready_no_owner"].append(uid)
            restricted = provider_restriction(unit, resources)
            if restricted:
                alias, code, refused = restricted
                reason = "provider_restriction:required_alias=%s:%s" % (alias, code)
                detail = {"required_alias": alias, "restriction_code": code}
                if refused:
                    refusal = {"unit_id": uid, "required_alias": alias, "restriction_code": code,
                               "why": "restriction_detail_not_in_vocabulary"}
            elif floor is not None and value < floor:
                reason = "measured_resource:%s=%s" % (metric, value)
                detail = {"metric": metric, "value": value, "reserve_floor_bytes": floor}
            else:
                clash = next((name for name, toks in sorted(claims, key=lambda kv: kv[0])
                              if toks & claimed_files), None)
                if clash:
                    reason, detail = "file_ownership_conflict:%s" % clash, {"owned_files": files}
                elif inflight.get(repo, 0) >= ceiling:
                    reason, detail = "capacity_full", {"repo_alias": repo, "in_flight": inflight.get(repo, 0),
                                                       "ceiling": ceiling}
        if reason is None and allow_dispatch:
            action_id = "act-unit-%s" % uuid.uuid4().hex
            payload = {"unit_id": uid, "repo_alias": repo, "required_alias": unit.get("required_alias"),
                       "artifact": unit.get("artifact"), "owned_files": files, "ledger": ul}
            try:
                db.execute("""INSERT INTO actions(action_id,idempotency_key,action_type,payload,state,
                              owner_generation,owner_run_id,created_ts,due_epoch)
                              VALUES(?,?,?,?,'queued',?,?,?,?)""",
                           (action_id, "unit:%s" % uid, "unit.dispatch", json.dumps(payload, sort_keys=True),
                            generation, run_id, iso(), now_epoch()))
                event(db, "action_created", action_id, {"type": "unit.dispatch", "unit_id": uid})
                event(db, "action_queued", action_id, {"unit_id": uid, "owner_generation": generation})
                db.commit()
            except sqlite3.IntegrityError:
                action_id = dispatched_action.get(uid, {}).get("action_id") or action_id
            rec = dispatch_action(db, run_id, generation, action_id)
            if rec:
                dispatched_id = action_id
                summary["dispatched"].append({"unit_id": uid, "action_id": action_id, "repo_alias": repo,
                                              "state_after": rec["state_after"]})
                inflight[repo] = inflight.get(repo, 0) + 1
                for _, toks in claims:
                    claimed_files.update(toks)
                outcome, reason, detail = "dispatched", None, {"state_after": rec["state_after"]}
            else:
                summary["unclassified"].append(uid)
                summary["ok"] = False
                outcome = "unclassified"
        elif reason is None:
            outcome = "deferred_no_dispatch"  # event-driven run: the tick owns dispatch
        else:
            if not valid_reason(reason):
                # PBB-092: the vocabulary closes at the write boundary. A reason outside
                # REASON_CLASSES is refused here and never stored; the refusal is reported
                # in the tick's own output so the unit cannot become invisible.
                refusal = {"unit_id": uid, "why": "reason_not_in_vocabulary"}
                summary["unclassified"].append(uid)
                summary["ok"] = False
                outcome, reason, detail = "refused_reason", None, None
            else:
                outcome = reason.split(":", 1)[0]
                summary["reasons"].append({"unit_id": uid, "reason": reason,
                                           "detail": detail, "ready_ticks": None})
        prev = db.execute("SELECT ready_ticks, first_ready_ts FROM unit_queue WHERE unit_id=?", (uid,)).fetchone()
        ticks = (prev["ready_ticks"] if prev else 0) + (1 if (tick_id is not None and outcome != "dispatched") else 0)
        first = prev["first_ready_ts"] if prev else iso()
        db.execute("""INSERT INTO unit_queue(unit_id,repo_alias,first_ready_ts,ready_ticks,last_tick_id,
                      last_outcome,last_reason,last_reason_detail,action_id,updated_ts)
                      VALUES(?,?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(unit_id) DO UPDATE SET repo_alias=excluded.repo_alias,
                        ready_ticks=excluded.ready_ticks, last_tick_id=excluded.last_tick_id,
                        last_outcome=excluded.last_outcome, last_reason=excluded.last_reason,
                        last_reason_detail=excluded.last_reason_detail, action_id=excluded.action_id,
                        updated_ts=excluded.updated_ts""",
                   (uid, repo, first, ticks, tick_id, outcome, reason,
                    json.dumps(detail, sort_keys=True) if detail is not None else None,
                    dispatched_id, iso()))
        if refusal:
            refusal["ready_ticks"] = ticks
            summary["refused"].append(refusal)
        if reason is not None:
            entry = summary["reasons"][-1]
            entry["ready_ticks"] = ticks
            if ticks >= 2:
                summary["idle_two_ticks"].append({"unit_id": uid, "reason": reason, "ready_ticks": ticks})
        elif outcome == "refused_reason" and ticks >= 2:
            # a unit whose reason was refused is reported too — never invisible to the
            # two-tick rule
            summary["idle_two_ticks"].append({"unit_id": uid, "reason": "reason_refused",
                                             "ready_ticks": ticks, "refused": True})
    for r in db.execute("SELECT unit_id FROM unit_queue").fetchall():
        if r["unit_id"] not in touched:
            db.execute("DELETE FROM unit_queue WHERE unit_id=?", (r["unit_id"],))
    summary["blocked"] = [x["unit_id"] for x in summary["reasons"]]
    # Invariant: a ready unit with no owner is dispatched or carries one of
    # REASON_CLASSES — never a shrug. A gap is a failure of this run, named as one.
    accounted = set(d["unit_id"] for d in summary["dispatched"]) | \
                set(x["unit_id"] for x in summary["reasons"])
    gap = [u for u in summary["ready_no_owner"] if u not in accounted]
    if gap:
        summary["unclassified"] = sorted(set(summary["unclassified"]) | set(gap))
        summary["ok"] = False
        summary["gap"] = gap
        summary["gap_meaning"] = ("tick_failed_ready_work_unaccounted" if allow_dispatch
                                  else "deferred_to_tick_writer")
    db.commit()
    event(db, "ready_queue_reconcile", None,
          {"tick_id": tick_id, "allow_dispatch": allow_dispatch, "ready_no_owner": summary["ready_no_owner"],
           "dispatched": [d["unit_id"] for d in summary["dispatched"]],
           "reasons": dict((x["unit_id"], x["reason"]) for x in summary["reasons"]),
           "refused": summary["refused"],
           "idle_two_ticks": [x["unit_id"] for x in summary["idle_two_ticks"]], "ok": summary["ok"]})
    db.commit()
    return summary


def rq_compact(summary):
    """Small machine-readable projection, for receipts written by nested bridge calls."""
    return {"ledger_units": summary["ledger_units"], "ready_no_owner": summary["ready_no_owner"],
            "dispatched": [d["unit_id"] for d in summary["dispatched"]],
            "reasons": dict((x["unit_id"], x["reason"]) for x in summary["reasons"]),
            "refused": summary["refused"],
            "idle_two_ticks": [x["unit_id"] for x in summary["idle_two_ticks"]],
            "unclassified": summary["unclassified"], "ok": summary["ok"]}


def job_readback():
    p = subprocess.run(["launchctl", "print", NATIVE_ID], capture_output=True, text=True)
    return {"rc": p.returncode, "output": (p.stdout + p.stderr)[:4000]}


def job_present():
    return job_readback()["rc"] == 0


def write_report(db, run_id, generation, ready_queue=None):
    t = now_epoch()
    cursor = int(meta_get(db, "event_cursor", "0"))
    counts = dict(db.execute("SELECT state, COUNT(*) c FROM actions GROUP BY state").fetchall())
    ticks = db.execute("SELECT COUNT(*) c FROM ticks").fetchone()["c"]
    lease = db.execute("SELECT owner_run_id, owner_generation, expires_epoch FROM leases WHERE resource=?",
                       (LEASE_RESOURCE,)).fetchone()
    body = {
        "loop": "ENG-LOOP",
        "label": LABEL,
        "native_id": NATIVE_ID,
        "run_id": run_id,
        "owner_generation": generation,
        "event_cursor": cursor,
        "ticks_total": ticks,
        "actions": counts,
        "lease": dict(lease) if lease else None,
        "ready_queue": ready_queue,
        "observer": "launchd StartInterval %ds" % OBSERVATION_SECONDS,
        "report_seconds": REPORT_SECONDS,
        "ts": iso(t),
    }
    rid = "report-%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t)), uuid.uuid4().hex[:6])
    db.execute("INSERT INTO reports(report_id,ts,body) VALUES(?,?,?)",
               (rid, iso(t), json.dumps(body, sort_keys=True)))
    with open(os.path.join(STATE, "reports.log"), "a") as f:
        f.write(json.dumps({"report_id": rid, **body}, sort_keys=True) + "\n")
    meta_set(db, "last_report_epoch", t)
    meta_set(db, "last_report_id", rid)
    return rid


def cmd_tick(args):
    fd = tick_lock()
    if fd is None:
        print(json.dumps({"result": "skipped", "reason": "tick_lock_held"}))
        return 0
    try:
        db = connect()
        run_id = args.run_id or meta_get(db, "owner_run_id")
        if not run_id:
            print(json.dumps({"result": "skipped", "reason": "no_run_id"}))
            return 2
        generation = owner_generation(db)
        cursor_before = int(meta_get(db, "event_cursor", "0"))
        ok, lease_note = acquire_lease(db, run_id, generation)
        if not ok:
            print(json.dumps({"result": "skipped", "reason": lease_note, "cursor": cursor_before}))
            return 0
        reconciled = reconcile_unknown(db, run_id, generation)
        # bounded delta read: at most 200 events past the cursor
        rows = db.execute("SELECT seq, kind, action_id FROM events WHERE seq>? ORDER BY seq LIMIT 200",
                          (cursor_before,)).fetchall()
        cursor_after = rows[-1]["seq"] if rows else cursor_before
        tick_id = "tick-%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), uuid.uuid4().hex[:6])
        # PBB-154: the tick id is the receipt marker's tick component. It is exported so
        # the owner-handler child this tick dispatches stamps its receipts with the same
        # tick id; the child's pid is its own and is stamped as such.
        os.environ["PB_TICK_ID"] = tick_id
        # PBB-076: every tick accounts for READY work with no live owner — dispatch it
        # or record why it cannot be dispatched.
        ready_queue = ready_queue_step(db, run_id, generation, tick_id=tick_id, allow_dispatch=True)
        dispatched = dispatch_queued(db, run_id, generation, ready_queue_tail=False)
        # report independently of action/model activity
        last_report = int(meta_get(db, "last_report_epoch", "0"))
        report_id = None
        if now_epoch() - last_report >= REPORT_SECONDS:
            report_id = write_report(db, run_id, generation, ready_queue)
        meta_set(db, "event_cursor", cursor_after)
        meta_set(db, "last_tick_epoch", now_epoch())
        db.execute("INSERT INTO ticks(tick_id,ts,pid,run_id,cursor_before,cursor_after,dispatched,note) "
                   "VALUES(?,?,?,?,?,?,?,?)",
                   (tick_id, iso(), os.getpid(), run_id, cursor_before, cursor_after,
                    len(dispatched) + len(ready_queue["dispatched"]),
                    json.dumps({"reconciled": reconciled, "report_id": report_id,
                                "ready_queue": ready_queue}, sort_keys=True)))
        db.commit()
        out = {"result": "tick", "tick_id": tick_id, "run_id": run_id, "generation": generation,
               "cursor_before": cursor_before, "cursor_after": cursor_after,
               "events_read": len(rows), "dispatched": dispatched,
               "reconciled": reconciled, "report_id": report_id, "ready_queue": ready_queue,
               "actions": dict(db.execute("SELECT state, COUNT(*) c FROM actions GROUP BY state").fetchall())}
        print(json.dumps(out))
        return 0
    finally:
        os.environ.pop("PB_TICK_ID", None)
        # keep the lock file: flock on a stable inode is the guard. Unlinking
        # would let a third process lock a fresh inode while another holds this one.
        try:
            os.close(fd)
        except OSError:
            pass


def plist_payload(run_id, generation):
    env = external_env()
    env["PATH"] = "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    env["HOME"] = os.path.expanduser("~")
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-I", os.path.abspath(__file__), "tick", "--run-id", run_id],
        "WorkingDirectory": CONTROL,
        "RunAtLoad": True,
        "KeepAlive": False,
        "StartInterval": OBSERVATION_SECONDS,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "StandardOutPath": os.path.join(LOGS, "tick.out.log"),
        "StandardErrorPath": os.path.join(LOGS, "tick.err.log"),
        "EnvironmentVariables": env,
        "Comment": "Purple Billboard ENG-LOOP observer, run_id=%s generation=%d" % (run_id, generation),
    }


def cmd_init(args):
    db = connect()
    run_id = args.run_id
    generation = args.generation
    if generation is None:
        generation = owner_generation(db) + 1
    existing = db.execute("SELECT value FROM meta WHERE key='owner_run_id'").fetchone()
    prior = existing["value"] if existing else None
    prior_gen = owner_generation(db)
    # A new run id is legal only as a NEW generation of the same single job.
    if prior and prior != run_id and generation <= prior_gen and not args.adopt:
        print(json.dumps({"result": "refused", "reason": "different_owner_run_id",
                          "existing": prior, "existing_generation": prior_gen,
                          "requested": run_id, "requested_generation": generation}))
        return 3
    meta_set(db, "owner_run_id", run_id)
    meta_set(db, "owner_generation", generation)
    meta_set(db, "label", LABEL)
    meta_set(db, "native_id", NATIVE_ID)
    meta_set(db, "package_version", "2.2")
    db.commit()  # RunAtLoad tick may start the instant bootstrap succeeds
    DB_LOCK = os.path.join(STATE, "init.lock")
    lfd = os.open(DB_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lfd)
        print(json.dumps({"result": "refused", "reason": "registration_in_progress"}))
        return 3
    result = {"run_id": run_id, "generation": generation, "label": LABEL, "native_id": NATIVE_ID}
    # T-38: admission before anything registers. Every claim of the runtime
    # contract is re-derived here; a refusal is named and nothing registers.
    try:
        admission = runtime_admission()
    except (UnsupportedHost, BindingRefused, PathRejected, StorageError,
            MissingMount, PropagationError, UnsupportedTool,
            ReboundDestination, HostRebound) as exc:
        print(json.dumps({"result": "refused", "reason": type(exc).__name__,
                          "detail": str(exc)}, sort_keys=True))
        return 3
    result["runtime_admission"] = admission
    meta_set(db, "run_state_path", admission["restart"]["run_state_path"])
    db.commit()
    present = job_present()
    stale_definition = False
    if os.path.exists(PLIST) and not args.adopt:
        with open(PLIST, "rb") as f:
            old = plistlib.load(f)
        old_args = old.get("ProgramArguments", [])
        old_run = old_args[old_args.index("--run-id") + 1] if "--run-id" in old_args else None
        # A different run id is only a duplicate when that job is actually LOADED.
        # A stopped job's stale plist is the predecessor definition of this same
        # single label and is replaced by the successor generation.
        if old_run and old_run != run_id and present:
            print(json.dumps({"result": "refused", "reason": "duplicate_job_other_run_id",
                              "plist": PLIST, "existing_run_id": old_run, "requested": run_id,
                              "job_loaded": present}))
            return 3
        stale_definition = bool(old_run and old_run != run_id and not present)
        result["replaces_stale_definition"] = stale_definition
        result["previous_run_id"] = old_run
    if job_present() and not args.register and not args.adopt:
        readback = job_readback()
        result.update({"registration": "already_registered", "readback": readback["output"][:1200],
                       "persistence": registration_persistence(
                           readback["output"] if readback["rc"] == 0 else None).as_dict()})
        print(json.dumps(result, sort_keys=True))
        return 0
    if not args.register:
        result["registration"] = "not_requested_no_register_flag"
        db.commit()
        print(json.dumps(result, sort_keys=True))
        return 0
    # stop any prior instance of THIS label only, then register once
    if job_present():
        bo = subprocess.run(["launchctl", "bootout", NATIVE_ID], capture_output=True, text=True)
        result["pre_bootout"] = {"rc": bo.returncode, "out": (bo.stdout + bo.stderr).strip()[:500]}
        for _ in range(20):
            if not job_present():
                break
            time.sleep(0.25)
    with open(PLIST, "wb") as f:
        plistlib.dump(plist_payload(run_id, generation), f)
    bs = subprocess.run(["launchctl", "bootstrap", DOMAIN, PLIST], capture_output=True, text=True)
    result["bootstrap"] = {"rc": bs.returncode, "out": (bs.stdout + bs.stderr).strip()[:800]}
    time.sleep(1.0)
    rb = job_readback()
    result["readback"] = {"rc": rb["rc"], "output": rb["output"][:1600]}
    result["registered"] = rb["rc"] == 0
    # T-38: restart persistence is claimed only from the read-back above.
    result["persistence"] = registration_persistence(
        rb["output"] if rb["rc"] == 0 else None).as_dict()
    reg_id = "rcpt-registration-%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), uuid.uuid4().hex[:6])
    receipt(db, "ENG-LOOP", "registration", result, receipt_id=reg_id)
    meta_set(db, "registration_receipt_id", reg_id)
    event(db, "registration", "ENG-LOOP", {"run_id": run_id, "generation": generation, "ok": result["registered"]})
    db.commit()
    result["registration_receipt_id"] = reg_id
    print(json.dumps(result, sort_keys=True))
    return 0 if result["registered"] else 4


def cmd_create(args):
    db = connect()
    run_id = args.run_id or meta_get(db, "owner_run_id")
    generation = owner_generation(db)
    row = db.execute("SELECT action_id FROM actions WHERE idempotency_key=?", (args.idempotency_key,)).fetchone()
    if row:
        a = action_view(db, row["action_id"])
        print(json.dumps({"result": "duplicate_idempotency_key", "action": a}, sort_keys=True))
        return 0
    action_id = "act-%s" % uuid.uuid4().hex
    ok, payload = _json_arg(args.payload)
    if not ok:
        print(json.dumps({"result": "refused", "reason": "invalid_payload"}, sort_keys=True))
        return 2
    db.execute("""INSERT INTO actions(action_id,idempotency_key,action_type,payload,state,
                  owner_generation,owner_run_id,created_ts,due_epoch)
                  VALUES(?,?,?,?,'queued',?,?,?,?)""",
               (action_id, args.idempotency_key, args.type, json.dumps(payload, sort_keys=True),
                generation, run_id, iso(), now_epoch()))
    event(db, "action_created", action_id, {"type": args.type, "idempotency_key": args.idempotency_key})
    event(db, "action_queued", action_id, {"owner_generation": generation})
    db.commit()
    print(json.dumps({"result": "created", "action": action_view(db, action_id)}, sort_keys=True))
    return 0


def action_view(db, action_id):
    r = db.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["payload"] = json.loads(d["payload"])
    return d


def cmd_dispatch(args):
    db = connect()
    run_id = args.run_id
    generation = owner_generation(db)
    ok, note = acquire_lease(db, run_id, generation)
    if not ok:
        print(json.dumps({"result": "skipped", "reason": note}))
        return 0
    d = dispatch_queued(db, run_id, generation, limit=1) if not args.action_id else []
    if args.action_id:
        a = db.execute("SELECT * FROM actions WHERE action_id=?", (args.action_id,)).fetchone()
        if not a:
            print(json.dumps({"result": "not_found"}))
            return 2
        if a["state"] != "queued":
            print(json.dumps({"result": "not_dispatchable", "state": a["state"]}))
            return 0
        db.execute("UPDATE actions SET state='dispatched', dispatch_ts=?, attempts=attempts+1 "
                   "WHERE action_id=? AND state='queued'", (iso(), args.action_id))
        event(db, "action_dispatched", args.action_id, {"mode": "manual"})
        db.commit()
        fresh = db.execute("SELECT * FROM actions WHERE action_id=?", (args.action_id,)).fetchone()
        rc, out, err = run_handler(fresh, run_id, generation)
        d = [{"action_id": args.action_id, "handler_rc": rc, "stdout": out, "stderr": err}]
    db.commit()
    print(json.dumps({"result": "dispatched", "items": d,
                      "action": action_view(db, d[0]["action_id"]) if d else None}, sort_keys=True, default=str))
    return 0


def cmd_record_ack(args):
    db = connect()
    a = db.execute("SELECT * FROM actions WHERE action_id=?", (args.action_id,)).fetchone()
    if not a:
        print(json.dumps({"result": "not_found"}))
        return 2
    if a["ack_receipt_id"]:
        # Idempotent replay of an ACK already persisted (re-dispatch after a crash).
        # The FIRST receipt is kept: ACK and completion stay separate receipts with
        # distinct ids, and a stale generation is still refused.
        accepted = a["owner_generation"] == args.owner_generation and a["state"] in ("dispatched", "acknowledged")
        if accepted and a["state"] == "dispatched":
            db.execute("UPDATE actions SET state='acknowledged' WHERE action_id=? AND state='dispatched'",
                       (args.action_id,))
        event(db, "action_ack_replayed" if accepted else "action_ack_rejected", args.action_id,
              {"receipt": a["ack_receipt_id"], "replay": True,
               "owner_generation_seen": a["owner_generation"],
               "owner_generation_claimed": args.owner_generation})
        db.commit()
        print(json.dumps({"result": "duplicate_ack", "receipt_id": a["ack_receipt_id"], "replayed": True,
                          "accepted": accepted,
                          "state": db.execute("SELECT state FROM actions WHERE action_id=?",
                                              (args.action_id,)).fetchone()["state"]}))
        return 0 if accepted else 5
    ok, body = _json_arg(args.body)
    if not ok:
        print(json.dumps({"result": "refused", "reason": "invalid_body"}, sort_keys=True))
        return 2
    body.update({"owner_generation_seen": a["owner_generation"],
                 "owner_generation_claimed": args.owner_generation,
                 "accepted": a["owner_generation"] == args.owner_generation and a["state"] == "dispatched"})
    rid = receipt(db, args.action_id, "ack", body)
    if body["accepted"]:
        db.execute("UPDATE actions SET state='acknowledged', ack_ts=?, ack_receipt_id=? "
                   "WHERE action_id=? AND state='dispatched'", (iso(), rid, args.action_id))
        event(db, "action_acknowledged", args.action_id, {"receipt": rid})
    else:
        event(db, "action_ack_rejected", args.action_id, {"receipt": rid})
    db.commit()
    print(json.dumps({"result": "ack_recorded", "receipt_id": rid, "accepted": body["accepted"],
                      "state": db.execute("SELECT state FROM actions WHERE action_id=?",
                                          (args.action_id,)).fetchone()["state"]}))
    return 0 if body["accepted"] else 5


def cmd_record_complete(args):
    db = connect()
    a = db.execute("SELECT * FROM actions WHERE action_id=?", (args.action_id,)).fetchone()
    if not a:
        print(json.dumps({"result": "not_found"}))
        return 2
    if a["completion_receipt_id"]:
        print(json.dumps({"result": "duplicate_completion", "receipt": a["completion_receipt_id"]}))
        return 0
    if a["state"] not in ("acknowledged", "dispatched"):
        print(json.dumps({"result": "invalid_transition", "state": a["state"]}))
        return 5
    ok, body = _json_arg(args.body)
    if not ok:
        print(json.dumps({"result": "refused", "reason": "invalid_body"}, sort_keys=True))
        return 2
    rid = "rcpt-completion-%s-%s" % (args.action_id.split("-")[-1], uuid.uuid4().hex[:8])
    cur = db.execute("UPDATE actions SET state='completed', completion_ts=?, completion_receipt_id=? "
                     "WHERE action_id=? AND completion_receipt_id IS NULL "
                     "AND state IN ('acknowledged','dispatched')", (iso(), rid, args.action_id))
    if cur.rowcount != 1:
        # a concurrent or zombie writer won the completion; exactly one completion
        # receipt per action, and it is never the ACK receipt
        now = db.execute("SELECT state, completion_receipt_id FROM actions WHERE action_id=?",
                         (args.action_id,)).fetchone()
        print(json.dumps({"result": "completion_already_recorded", "receipt": now["completion_receipt_id"],
                          "state": now["state"]}))
        return 0
    receipt(db, args.action_id, "completion", body, receipt_id=rid)
    event(db, "action_completed", args.action_id, {"receipt": rid})
    db.commit()
    # PBB-076: a completion event triggers the ready-queue step too. Dispatch only when
    # the tick lock is free, and hold it for the duration — the tick stays the single
    # dispatch writer, and a nested owner-bridge child then records only (no recursion).
    lock = tick_lock()
    try:
        rq = ready_queue_step(db, a["owner_run_id"], a["owner_generation"], allow_dispatch=lock is not None)
    finally:
        if lock is not None:
            try:
                os.close(lock)
            except OSError:
                pass
    print(json.dumps({"result": "completion_recorded", "receipt_id": rid, "state": "completed",
                      "ready_queue": rq_compact(rq)}, sort_keys=True))
    return 0


def cmd_reconcile(args):
    db = connect()
    generation = owner_generation(db)
    ok, note = acquire_lease(db, args.run_id, generation)
    changed = reconcile_unknown(db, args.run_id, generation)
    db.commit()
    print(json.dumps({"result": "reconciled", "lease": note, "changed": changed,
                      "cursor": int(meta_get(db, "event_cursor", "0")),
                      "actions": dict(db.execute("SELECT state, COUNT(*) c FROM actions GROUP BY state").fetchall())},
                     sort_keys=True))
    return 0


def cmd_request_stop(args):
    # generation is bound to a SQLite INTEGER column: refuse a value the store cannot
    # represent instead of raising OverflowError from the driver (PBB-279 D3).
    if not (-(2 ** 63) <= args.generation <= 2 ** 63 - 1):
        print(json.dumps({"result": "refused", "reason": "generation_out_of_range",
                          "generation": args.generation}, sort_keys=True))
        return 3
    db = connect()
    key = "shutdown:%s:gen%d" % (args.run_id, args.generation)
    row = db.execute("SELECT action_id FROM actions WHERE idempotency_key=?", (key,)).fetchone()
    if row:
        print(json.dumps({"result": "already_requested", "action": action_view(db, row["action_id"])},
                         sort_keys=True))
        return 0
    action_id = "act-stop-%s" % uuid.uuid4().hex
    db.execute("""INSERT INTO actions(action_id,idempotency_key,action_type,payload,state,
                  owner_generation,owner_run_id,created_ts,due_epoch)
                  VALUES(?,?,?,?,'queued',?,?,?,?)""",
               (action_id, key, "eng_loop.shutdown",
                json.dumps({"label": LABEL, "native_id": NATIVE_ID, "stop_method": "launchctl bootout"},
                           sort_keys=True),
                args.generation, args.run_id, iso(), now_epoch()))
    event(db, "action_created", action_id, {"type": "eng_loop.shutdown"})
    event(db, "action_queued", action_id, {"owner_generation": args.generation})
    db.commit()
    print(json.dumps({"result": "stop_requested_persisted", "action": action_view(db, action_id)},
                     sort_keys=True))
    return 0


def cmd_dispatch_stop(args):
    """Owner bridge for shutdown: ACK is NOT completion. Persist, bootout, read back."""
    db = connect()
    a = db.execute("SELECT * FROM actions WHERE action_id=?", (args.action_id,)).fetchone()
    if not a:
        print(json.dumps({"result": "not_found"}))
        return 2
    if a["action_type"] != "eng_loop.shutdown":
        print(json.dumps({"result": "refused", "reason": "not_an_engineering_shutdown_action"}))
        return 3
    # ownership proof before touching the job
    if not os.path.exists(PLIST):
        print(json.dumps({"result": "refused", "reason": "plist_absent"}))
        return 3
    with open(PLIST, "rb") as f:
        old = plistlib.load(f)
    pargs = old.get("ProgramArguments", [])
    # A trailing "--run-id" with no value is a malformed job, not an owned job:
    # read the value safely and let the equality guard refuse it (PBB-279 D2).
    owned_run = None
    if "--run-id" in pargs:
        _i = pargs.index("--run-id")
        if _i + 1 < len(pargs):
            owned_run = pargs[_i + 1]
    if owned_run != a["owner_run_id"]:
        print(json.dumps({"result": "refused", "reason": "job_not_owned_by_action_run_id",
                          "job_run_id": owned_run, "action_run_id": a["owner_run_id"]}))
        return 3
    if a["state"] == "queued":
        db.execute("UPDATE actions SET state='dispatched', dispatch_ts=?, attempts=attempts+1 "
                   "WHERE action_id=? AND state='queued'", (iso(), args.action_id))
        event(db, "action_dispatched", args.action_id, {"mode": "owner_bridge"})
        db.commit()
        a = db.execute("SELECT * FROM actions WHERE action_id=?", (args.action_id,)).fetchone()
    if a["state"] not in ("dispatched", "acknowledged"):
        print(json.dumps({"result": "not_stoppable_from_state", "state": a["state"]}))
        return 0
    # T-38: teardown may dispose the engineering process only. The run state is
    # durable and is preserved by name (TeardownReport); a resource carrying an
    # unknown effect would be preserved too, never stopped on a guess.
    holder = {}

    def _bootout(resource):
        p = subprocess.run(["launchctl", "bootout", resource["id"]],
                           capture_output=True, text=True)
        holder["bootout"] = p
        return p

    resources = [{"id": NATIVE_ID, "kind": ENGINEERING_PROCESS}]
    state_path = meta_get(db, "run_state_path")
    if state_path:
        resources.append({"id": state_path, "kind": DURABLE_STATE})
    try:
        report: TeardownReport = teardown(resources, stop=_bootout)
    except TeardownRefused as exc:
        print(json.dumps({"result": "refused", "reason": "teardown_refused",
                          "detail": str(exc)}, sort_keys=True))
        return 3
    bo = holder.get("bootout")
    if bo is None:
        print(json.dumps({"result": "refused", "reason": "process_not_stopped",
                          "teardown": report.as_dict()}, sort_keys=True))
        return 3
    ack_body = {"host": "launchd", "command": "launchctl bootout %s" % NATIVE_ID,
                "rc": bo.returncode, "output": (bo.stdout + bo.stderr).strip()[:800],
                "teardown": report.as_dict(),
                "meaning": "host accepted the stop request; NOT completion"}
    ack_id = a["ack_receipt_id"]
    if ack_id is None:
        ack_id = receipt(db, args.action_id, "ack", ack_body)
        db.execute("UPDATE actions SET state='acknowledged', ack_ts=?, ack_receipt_id=? WHERE action_id=?",
                   (iso(), ack_id, args.action_id))
        event(db, "action_acknowledged", args.action_id, {"receipt": ack_id, "host": "launchd"})
        db.commit()
    # completion readback: job absent and no tick after the bootout
    bootout_epoch = now_epoch()
    absent_after = None
    last_rc = None
    outputs = []
    for _ in range(40):
        rb = job_readback()
        last_rc = rb["rc"]
        outputs.append({"epoch": now_epoch(), "rc": rb["rc"],
                        "head": rb["output"].strip().splitlines()[:3]})
        if rb["rc"] != 0:
            absent_after = now_epoch() - bootout_epoch
            break
        time.sleep(0.25)
    ticks_after = db.execute("SELECT COUNT(*) c FROM ticks WHERE ts > ?",
                             (iso(bootout_epoch),)).fetchone()["c"]
    complete = absent_after is not None and ticks_after == 0
    completion_body = {"host": "launchd", "native_id": NATIVE_ID,
                       "job_absent": absent_after is not None,
                       "seconds_to_absent": absent_after,
                       "last_print_rc": last_rc,
                       "ticks_after_stop": ticks_after,
                       "probe_sequence": outputs[-4:],
                       "meaning": "read-back completion; distinct from ACK"}
    completion_id = None
    if complete:
        completion_id = receipt(db, args.action_id, "completion", completion_body)
        db.execute("UPDATE actions SET state='completed', completion_ts=?, completion_receipt_id=? "
                   "WHERE action_id=?", (iso(), completion_id, args.action_id))
        event(db, "action_completed", args.action_id, {"receipt": completion_id})
        release_lease(db, a["owner_run_id"])
    else:
        event(db, "action_stop_unconfirmed", args.action_id, completion_body)
    db.commit()
    print(json.dumps({"result": "stop_dispatched", "action_id": args.action_id,
                      "ack_receipt_id": ack_id, "completion_receipt_id": completion_id,
                      "ack": ack_body, "completion": completion_body,
                      "state": db.execute("SELECT state FROM actions WHERE action_id=?",
                                          (args.action_id,)).fetchone()["state"]},
                     sort_keys=True))
    return 0 if complete else 6


def cmd_status(args):
    db = connect()
    out = {
        "loop": "ENG-LOOP",
        "label": LABEL,
        "native_id": NATIVE_ID,
        "run_id": meta_get(db, "owner_run_id"),
        "owner_generation": owner_generation(db),
        "event_cursor": int(meta_get(db, "event_cursor", "0")),
        "last_tick_epoch": meta_get(db, "last_tick_epoch"),
        "last_report_id": meta_get(db, "last_report_id"),
        "registration_receipt_id": meta_get(db, "registration_receipt_id"),
        "job_present": job_present(),
        "actions": [action_view(db, r["action_id"]) for r in
                    db.execute("SELECT action_id FROM actions ORDER BY created_ts").fetchall()],
        "receipts": [dict(r) for r in db.execute("SELECT * FROM receipts ORDER BY ts").fetchall()],
        "latest_ticks": [dict(r) for r in db.execute(
            "SELECT * FROM ticks ORDER BY ts DESC LIMIT 5").fetchall()],
        "latest_reports": [dict(r) for r in db.execute(
            "SELECT * FROM reports ORDER BY ts DESC LIMIT 3").fetchall()],
        "lease": dict(db.execute("SELECT * FROM leases WHERE resource=?", (LEASE_RESOURCE,)).fetchone() or {}),
        "unit_queue": [dict(r) for r in db.execute("SELECT * FROM unit_queue ORDER BY unit_id").fetchall()],
    }
    baseline = provenance_baseline_ids(db)
    for r in out["receipts"]:
        r["provenance"] = classify_receipt(r, baseline)
        try:
            r["body"] = json.loads(r["body"])
        except Exception:
            pass
    out["receipt_provenance"] = {
        "baseline_recorded": db.execute(
            "SELECT value FROM meta WHERE key=?", (BASELINE_KEY,)).fetchone() is not None,
        "baseline_size": len(baseline),
        "counts": {v: sum(1 for r in out["receipts"] if r["provenance"] == v)
                   for v in (PROV_MARKED, PROV_LEGACY, PROV_UNMARKED, PROV_INCOMPLETE, PROV_TAMPERED)},
        "unmarked_ids": [r["receipt_id"] for r in out["receipts"] if r["provenance"] != PROV_MARKED],
    }
    print(json.dumps(out, sort_keys=True, default=str))
    return 0


def cmd_selftest(args):
    """Runs the full state machine in an isolated temp DB; no launchd, no network."""
    import tempfile
    global DB_PATH, STATE, EFFECTS, LOGS, TICK_LOCK
    sandbox = tempfile.mkdtemp(prefix="eng-loop-selftest-", dir=TMP)
    old = (DB_PATH, STATE, EFFECTS, LOGS, TICK_LOCK)
    STATE = sandbox
    DB_PATH = os.path.join(sandbox, "engine.db")
    EFFECTS = os.path.join(sandbox, "effects")
    LOGS = os.path.join(sandbox, "logs")
    TICK_LOCK = os.path.join(sandbox, "tick.lock")
    os.makedirs(EFFECTS)
    os.makedirs(LOGS)
    # hermetic: the sandbox reads no live unit/resource ledger
    sandbox_ledger = os.path.join(sandbox, "build.json")
    with open(sandbox_ledger, "w") as f:
        f.write(json.dumps({"tasks": []}))
    old_env = (os.environ.get("PB_UNIT_LEDGER"), os.environ.get("PB_RESOURCES_LEDGER"))
    old_state_env = os.environ.get("PB_STATE_DIR")
    os.environ["PB_UNIT_LEDGER"] = sandbox_ledger
    os.environ["PB_RESOURCES_LEDGER"] = sandbox_ledger
    try:
        db = connect()
        meta_set(db, "owner_run_id", "selftest-run")
        meta_set(db, "owner_generation", 1)
        aid = "act-selftest"
        db.execute("""INSERT INTO actions(action_id,idempotency_key,action_type,payload,state,
                      owner_generation,owner_run_id,created_ts,due_epoch)
                      VALUES(?,?,?,?,'queued',1,?,?,?)""",
                   (aid, "selftest-key", "synthetic.noop", "{}", "selftest-run", iso(), now_epoch()))
        db.commit()
        os.environ["PB_SELFTEST"] = "1"
        os.environ["PB_STATE_DIR"] = sandbox  # handler's adapter child uses the same sandbox DB
        d = dispatch_queued(db, "selftest-run", 1)
        db.commit()
        assert d and d[0]["handler_rc"] == 0, d
        a = db.execute("SELECT * FROM actions WHERE action_id=?", (aid,)).fetchone()
        assert a["state"] == "completed", a["state"]
        assert a["ack_receipt_id"] and a["completion_receipt_id"]
        # duplicate dispatch must not re-run the effect
        d2 = dispatch_queued(db, "selftest-run", 1)
        assert d2 == [], d2
        # ---- window 2: ACK recorded, worker died before completion -> recovered ----
        aid2 = "act-selftest-ackgap"
        first_ack = "rcpt-ack-selftest-ackgap-00000000"
        db.execute("""INSERT INTO actions(action_id,idempotency_key,action_type,payload,state,
                      owner_generation,owner_run_id,created_ts,due_epoch,ack_ts,ack_receipt_id)
                      VALUES(?,?,?,?,'acknowledged',1,?,?,?,?,?)""",
                   (aid2, "selftest-ackgap-key", "synthetic.noop", "{}", "selftest-run",
                    iso(), now_epoch(), "2020-01-01T00:00:00Z", first_ack))
        db.commit()
        changed = reconcile_unknown(db, "selftest-run", 1)
        assert (aid2, "requeued") in changed, changed
        d3 = dispatch_queued(db, "selftest-run", 1)
        db.commit()
        assert d3 and d3[0]["handler_rc"] == 0, d3
        a2 = db.execute("SELECT * FROM actions WHERE action_id=?", (aid2,)).fetchone()
        assert a2["state"] == "completed", a2["state"]
        assert a2["ack_receipt_id"] == first_ack, a2["ack_receipt_id"]  # first ACK kept on replay
        assert a2["completion_receipt_id"] and a2["completion_receipt_id"] != a2["ack_receipt_id"]
        with open(os.path.join(EFFECTS, "selftest-ackgap-key.json")) as f:
            assert json.load(f)["execution_count"] == 1
        assert reconcile_unknown(db, "selftest-run", 1) == []  # completed work is never re-reconciled
        print(json.dumps({"selftest": "PASS", "action_state": a["state"],
                          "ack": a["ack_receipt_id"], "completion": a["completion_receipt_id"],
                          "sandbox": sandbox}))
        return 0
    finally:
        DB_PATH, STATE, EFFECTS, LOGS, TICK_LOCK = old
        if old_state_env is None:
            os.environ.pop("PB_STATE_DIR", None)
        else:
            os.environ["PB_STATE_DIR"] = old_state_env
        for key, was in (("PB_UNIT_LEDGER", old_env[0]), ("PB_RESOURCES_LEDGER", old_env[1])):
            if was is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = was
        import shutil
        # T-38: the sandbox is engineering temp and is disposed through the
        # shared teardown contract, which can never touch anything durable.
        teardown([{"id": sandbox, "kind": ENGINEERING_TEMP}],
                 stop=lambda resource: shutil.rmtree(resource["id"],
                                                     ignore_errors=True))


def main(argv):
    # A caller may change PB_* after importing this module; resolve them again before
    # any command touches the store or hands an environment to a child.
    refresh_config()
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--run-id", required=True)
    i.add_argument("--generation", type=int); i.add_argument("--register", action="store_true")
    i.add_argument("--adopt", action="store_true")
    t = sub.add_parser("tick"); t.add_argument("--run-id")
    c = sub.add_parser("create"); c.add_argument("--type", required=True)
    c.add_argument("--idempotency-key", required=True); c.add_argument("--payload")
    c.add_argument("--run-id")
    d = sub.add_parser("dispatch"); d.add_argument("--action-id"); d.add_argument("--run-id", required=True)
    a = sub.add_parser("record-ack"); a.add_argument("--action-id", required=True)
    a.add_argument("--receipt-id"); a.add_argument("--owner-generation", type=int, required=True)
    a.add_argument("--body")
    cp = sub.add_parser("record-complete"); cp.add_argument("--action-id", required=True)
    cp.add_argument("--receipt-id"); cp.add_argument("--body")
    r = sub.add_parser("reconcile"); r.add_argument("--run-id", required=True)
    rs = sub.add_parser("request-stop"); rs.add_argument("--run-id", required=True)
    rs.add_argument("--generation", type=int, required=True)
    ds = sub.add_parser("dispatch-stop"); ds.add_argument("--action-id", required=True)
    ds.add_argument("--run-id", required=True)
    s = sub.add_parser("status"); s.add_argument("--run-id")
    sub.add_parser("selftest")
    args = p.parse_args(argv)
    return {
        "init": cmd_init, "tick": cmd_tick, "create": cmd_create, "dispatch": cmd_dispatch,
        "record-ack": cmd_record_ack, "record-complete": cmd_record_complete,
        "reconcile": cmd_reconcile, "request-stop": cmd_request_stop,
        "dispatch-stop": cmd_dispatch_stop, "status": cmd_status, "selftest": cmd_selftest,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
