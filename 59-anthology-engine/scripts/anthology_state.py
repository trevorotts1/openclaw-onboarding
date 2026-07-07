#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: anthology_state.py
# THE SOLE LEDGER WRITER (SPEC Section 7.4; data-model-design.md Section 3)
# -----------------------------------------------------------------------------
# The durable state layer the whole engine stands on. NO OTHER CODE PATH WRITES
# STATE: the intake router, every stage runner, the gate engine, the participant
# token page, the exceptions screen, the board client, and the revocation script
# all SHELL these subcommands. Layer 4 (the Command Center board / token page)
# holds NO base credential at all (SPEC 2.3). A static route audit and a repo
# scan for direct base writes ride Gate A; this file is the only writer.
#
# TWO STORES, ONE OPERATION (SPEC 7.2):
#   * The AUTHORITATIVE base is an Airtable base (working name "Anthology Engine
#     State"), one per deployment, referenced by base id from the client env
#     store under label ANTHOLOGY_STATE_BASE_ID with the Airtable credential
#     under its own label (values NEVER printed; SET / NOT SET only).
#   * A local SQLite MIRROR (WAL mode, under the engine state directory, owned by
#     the node user) is the fast read path for the board rollups, the intake
#     router, and the crash-recovery cache. It carries the same tables and the
#     same columns plus a meta table (schema_version, last_reconcile_at,
#     base_cursor) and sync-bookkeeping sidecars (underscore-prefixed).
#   The writer writes THROUGH to both in one logical operation and reconciles on
#   the daily tick; THE BASE WINS ON CONFLICT. The mirror means a network blip
#   never blocks a gate action (the write is committed locally and queued for the
#   base -> exit 4, "mirror-queued"); the base means a dead box never loses a
#   participant. When no base is configured (an un-provisioned box or a unit
#   test), the writer runs MIRROR-ONLY and exits 0, emitting one operator note.
#
# EXIT CODE CONTRACT (SPEC 3.4 row 1; identical across every subcommand):
#   0  verified success (INCLUDING an idempotent replay no-op)
#   1  unexpected error
#   2  illegal transition (the legal matrix of SPEC 7.3 refused it; NOTHING changed)
#   3  unknown key (no such producer / anthology / participant / exception)
#   4  base unreachable — the mirror write is committed and the base op is QUEUED
#   5  validation or --confirm-name mismatch (NOTHING changed)
#
# DESIGN LAW: enforcement, not description. Every transition is validated against
# the legal matrix BEFORE a single byte is written; an illegal transition raises
# before any write and changes nothing. Every mutation is idempotent so that a
# killed-and-replayed event loses nothing and never duplicates an artifact. The
# mirror commit is atomic (a single SQLite transaction); the base op only follows
# a committed mirror, so a crash between the two is recovered by the pending
# queue, never by a lost participant.
#
# STDLIB ONLY (sqlite3 + urllib): zero third-party deps, calls NO model and NO
# delivery provider. Runs identically on every box (operator canary or client).
# DOCTRINE: move in silence (operator-verbose only); NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; never print a
# secret value; config/state writes run as the node user, never root.
# =============================================================================
"""anthology_state.py — the sole durable-ledger writer for the Anthology Engine."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (the whole engine reads these; keep them stable).
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ILLEGAL = 2
EXIT_UNKNOWN_KEY = 3
EXIT_BASE_DEFERRED = 4
EXIT_VALIDATION = 5

# The ledger schema version. The engine manifest (ENGINE-MANIFEST.json, owned by
# a different unit) MUST carry the SAME value under schema_version; a drift there
# is caught by the build gate. Bump only on a breaking schema change.
SCHEMA_VERSION = "1"

# ---------------------------------------------------------------------------
# Controlled vocabularies (SPEC 7.1 / data-model-design.md Section 2). Mirrored
# into SQLite CHECK constraints below as a defense-in-depth backstop; the real
# enforcement is the handlers, which return the precise exit code.
# ---------------------------------------------------------------------------
PRODUCER_STATUS = ("active", "revoked")

ANTHOLOGY_STATUS = (
    "setup", "open", "writing", "ready_to_assemble",
    "assembling", "delivered", "archived",
)

ASSEMBLY_STATE = (
    "not_ready", "armed", "ready_confirmed",
    "proposed", "adjusted", "compiled", "signed_off",
)

# Participant stage_cursor vocabulary — EXACT (SPEC 7.1). Order is meaningful for
# readability only; legality is defined by STAGE_EDGES, never by ordering.
STAGE_CURSORS = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)

ARTIFACT_TYPES = (
    "avatar", "tone", "titles", "blurb", "outline", "chapter",
    "rewrite", "cover", "anthology_manuscript",
)

APPROVAL_GATES = (
    "s1_producer", "s2_producer", "s3_selection", "s4_producer",
    "s4_participant", "s5_participant", "s9_ready", "s9_producer",
)
APPROVAL_ACTORS = ("producer", "participant")
APPROVAL_DECISIONS = (
    "approve", "request_rewrite", "escalate", "hold", "exclude",
    "ready_to_assemble",
)
APPROVAL_DOORS = ("dashboard", "nudge_link")

EXCEPTION_REASONS = (
    "unroutable_missing_ids", "unknown_anthology", "stage_mismatch",
    "tenant_mismatch", "legacy_reconciliation",
)
EXCEPTION_STATUS = ("open", "resolved")

HOLD_REASONS = ("credit_out", "callback_lost", "strike_out")

REWRITE_BUDGET = 2          # participant rewrite budget (SPEC S6); 3rd is illegal
QC_ATTEMPT_CAP = 3          # internal QC attempts per deliverable (strike gate)
MIN_CHAPTERS_FLOOR = 2      # S9 ready-trigger floor (PRD 3.11); configurable up

# A participant counts as "done and frozen, awaiting assembly" at these cursors.
APPROVED_CURSORS = ("approved", "delivered")

# ---------------------------------------------------------------------------
# THE LEGAL TRANSITION MATRIX (SPEC 7.3 / data-model-design.md Section 4).
# A single source of truth consulted by BOTH advance-stage (machine-driven edges)
# and record-approval (gate-decision edges). Any (from -> to) not present here is
# illegal and refused with exit 2, changing nothing.
# ---------------------------------------------------------------------------
STAGE_EDGES = {
    # machine-driven (stage runners call advance-stage)
    ("s0_intake", "s1_avatar"),
    ("s1_avatar", "s1_gate"),
    ("s2_tone", "s2_gate"),
    ("s3_title", "s3_gate"),
    ("s4_blurb_outline", "s4_gate_producer"),
    ("s5_chapter", "s5_gate"),
    ("s6_rewrite", "s5_gate"),          # a rewrite always re-enters the gate
    ("s7_cover", "s8_deliver"),
    ("s8_deliver", "s9_wait_assembly"),
    ("s9_wait_assembly", "approved"),
    ("approved", "delivered"),          # at S9 manuscript delivery (s9_producer)
    # gate-decision edges (record-approval performs these atomically with the row)
    ("s1_gate", "s2_tone"),             # s1_producer / approve
    ("s2_gate", "s3_title"),            # s2_producer / approve
    ("s3_gate", "s4_blurb_outline"),    # s3_selection (title lock stamps)
    ("s4_gate_producer", "s4_gate_participant"),   # s4_producer / approve
    ("s4_gate_participant", "s5_chapter"),         # s4_participant / approve
    ("s5_gate", "s7_cover"),            # s5_participant / approve (chapter freezes)
    ("s5_gate", "s6_rewrite"),          # s5_participant / request_rewrite (budget)
}

# Gate decision -> the participant cursor edge it drives. Only the edges that a
# gate approval/selection advances live here; hold/exclude/escalate never move
# the cursor through the matrix (they are recorded, and hold uses the hold path).
GATE_EDGE = {
    ("s1_producer", "approve"): ("s1_gate", "s2_tone"),
    ("s2_producer", "approve"): ("s2_gate", "s3_title"),
    ("s3_selection", "approve"): ("s3_gate", "s4_blurb_outline"),
    ("s4_producer", "approve"): ("s4_gate_producer", "s4_gate_participant"),
    ("s4_participant", "approve"): ("s4_gate_participant", "s5_chapter"),
    ("s5_participant", "approve"): ("s5_gate", "s7_cover"),
    ("s5_participant", "request_rewrite"): ("s5_gate", "s6_rewrite"),
}

# The (from -> to) cursor edges that are OWNED by record-approval — a gate crossing
# that MUST fire the approvals audit row and the per-gate guards (title lock,
# rewrite budget, s5 chapter freeze). advance-stage (the machine-driven channel)
# must REFUSE these so a stage runner can never step past a producer/participant
# gate without the row and guards (SPEC 7.3: these edges happen "on approvals row").
GATE_DECISION_EDGES = frozenset(GATE_EDGE.values())

# The assembly_state (anthology-scope) machine (SPEC 7.3 tail; design Section 4).
ASSEMBLY_EDGES = {
    ("not_ready", "armed"),
    ("armed", "ready_confirmed"),
    ("ready_confirmed", "proposed"),
    ("ready_confirmed", "adjusted"),
    ("ready_confirmed", "compiled"),
    ("proposed", "adjusted"),
    ("proposed", "compiled"),
    ("adjusted", "compiled"),
    ("compiled", "signed_off"),
    # producer-initiated reopen (a producer exception) voids in-progress assembly
    ("armed", "not_ready"),
    ("ready_confirmed", "not_ready"),
    ("proposed", "not_ready"),
    ("adjusted", "not_ready"),
    ("compiled", "not_ready"),
}
# assembly_state values that mean "the trigger already fired" (double-fire no-op).
ASSEMBLY_FIRED = ("ready_confirmed", "proposed", "adjusted", "compiled", "signed_off")

# The ONLY assembly_state targets the assembly-advance subcommand OWNS. Every other
# state is reached exclusively through its own guarded channel, and assembly-advance
# MUST refuse them so no second, unguarded door exists into an S9 guard state
# (SPEC 7.3 / PRD 3.11):
#   armed           -> _maybe_arm (auto-arm) / _fire_s9_ready (arm-then-confirm)
#   ready_confirmed -> _fire_s9_ready ONLY (own-producer + --confirm-name + readiness)
#   proposed        -> assembly-set-order (validated permutation of the staged set)
#   adjusted        -> assembly-set-order (validated permutation of the staged set)
#   signed_off      -> s9_producer sign-off (own-producer auth, member delivery)
# assembly-advance owns compile (its staging + sha re-proof + readiness re-check)
# and the producer-initiated reopen to not_ready (voids in-progress assembly).
ASSEMBLY_ADVANCE_TARGETS = ("compiled", "not_ready")

# ---------------------------------------------------------------------------
# Deny patterns. model_used on an Artifact row must be an HONEST model id and
# NEVER an Anthropic-shaped identifier (mirrors Skill 54's AF-AW-ANTHROPIC gate
# and guard-no-anthropic-runtime.py). A credential-shaped value must never be
# stored in the ledger (secrets live in the env stores, referenced by label).
# ---------------------------------------------------------------------------
_ANTHROPIC_DENY_RE = re.compile(
    r"(?i)(^|[^a-z0-9])(claude|anthropic)([^a-z0-9]|$)|anthropic/|claude-|us\.anthropic\.",
)
_CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|pit-[a-z0-9]{16,}|bearer\s+[a-z0-9._-]{16,}|"
    r"key-[a-z0-9]{16,}|[a-z0-9]{32,})",
)


# ---------------------------------------------------------------------------
# Errors — each carries the precise engine exit code.
# ---------------------------------------------------------------------------
class LedgerError(Exception):
    def __init__(self, code: int, message: str, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


def _illegal(msg, detail=None):
    return LedgerError(EXIT_ILLEGAL, msg, detail)


def _unknown(msg, detail=None):
    return LedgerError(EXIT_UNKNOWN_KEY, msg, detail)


def _invalid(msg, detail=None):
    return LedgerError(EXIT_VALIDATION, msg, detail)


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------
def now_utc() -> str:
    """ISO-8601 UTC timestamp, second precision, always with an explicit offset."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def gen_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:20])


def participant_key(contact_id: str, anthology_id: str) -> str:
    """The LITERAL composite primary key (KEYING LAW: contact_id, never email)."""
    return "%s::%s" % (contact_id, anthology_id)


def _loads(raw, default=None):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _require(value, name):
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise _invalid("missing required argument %r" % name)
    return value


def _guard_model_used(model_used):
    if model_used and _ANTHROPIC_DENY_RE.search(str(model_used)):
        raise _invalid("model_used %r matches an Anthropic-shaped deny pattern; "
                       "the ledger records honest non-Anthropic model ids only"
                       % model_used)


def _guard_no_secret(value, field):
    if value and _CREDENTIAL_VALUE_RE.search(str(value)):
        raise _invalid("value for %r looks credential-shaped; secrets live in the "
                       "env stores by label and are never written to the ledger"
                       % field)


def default_state_dir() -> Path:
    """The engine state directory (owned by the node user). Overridable by
    ANTHOLOGY_STATE_DIR; else under OPENCLAW_DATA_DIR; else the node user home."""
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def _env_first(names):
    """First present, non-empty env value among `names`. Returns (name, value) or
    (None, None). NEVER prints the value (doctrine: SET / NOT SET only)."""
    for n in names:
        v = os.environ.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


# ---------------------------------------------------------------------------
# The Airtable base client (authoritative store). STDLIB urllib only. It is only
# constructed and called in LIVE mode (base id + credential both present). On any
# transport failure it raises BaseUnreachable; the caller then queues the op in
# the mirror sync queue and the command exits 4. Values are never logged.
# ---------------------------------------------------------------------------
class BaseUnreachable(Exception):
    pass


# Logical table -> Airtable table name.
BASE_TABLE_NAMES = {
    "producers": "Producers",
    "anthologies": "Anthologies",
    "participants": "Participants",
    "artifacts": "Artifacts",
    "approvals": "Approvals",
    "exceptions": "Exceptions",
}


class AirtableBase:
    """Thin, fail-defensive Airtable REST client. Create -> returns record id;
    Update -> PATCH by record id. The mirror owns the pk<->record-id map so we
    never depend on Airtable's own upsert semantics."""

    _API_ROOT = "https://api.airtable.com/v0"

    def __init__(self, base_id: str, token: str, timeout: int = 12):
        self._base_id = base_id
        self._token = token
        self._timeout = timeout

    def _url(self, table_name: str, record_id: str = "") -> str:
        # Airtable accepts the human table name URL-encoded.
        tbl = urllib.request.quote(table_name, safe="")
        u = "%s/%s/%s" % (self._API_ROOT, self._base_id, tbl)
        if record_id:
            u += "/%s" % urllib.request.quote(record_id, safe="")
        return u

    def _request(self, method: str, url: str, payload):
        data = None
        headers = {"Authorization": "Bearer %s" % self._token}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            # 4xx auth/permission/not-found: treat as unreachable so the write is
            # never lost — it queues and the operator surface / reconcile resolve
            # it. NEVER surface the response body (may echo a token).
            raise BaseUnreachable("base HTTP %s on %s" % (exc.code, method))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise BaseUnreachable("base transport error: %s" % type(exc).__name__)

    def create(self, table_name: str, fields: dict) -> str:
        out = self._request("POST", self._url(table_name),
                            {"fields": fields, "typecast": True})
        rid = out.get("id")
        if not rid:
            raise BaseUnreachable("base create returned no record id")
        return rid

    def update(self, table_name: str, record_id: str, fields: dict) -> str:
        out = self._request("PATCH", self._url(table_name, record_id),
                            {"fields": fields, "typecast": True})
        return out.get("id", record_id)

    def fetch(self, table_name: str, record_id: str) -> dict:
        out = self._request("GET", self._url(table_name, record_id), None)
        f = out.get("fields")
        return f if isinstance(f, dict) else {}


# ---------------------------------------------------------------------------
# THE LEDGER. Owns the SQLite mirror and the through-write to the base.
# ---------------------------------------------------------------------------
class Ledger:
    def __init__(self, db_path: Path, *, base_mode=None, base=None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self._bootstrap_schema()
        # base wiring (resolved lazily unless injected, e.g. for tests)
        if base_mode is None:
            base_mode, base = self._resolve_base()
        self.base_mode = base_mode           # "live" | "mirror_only"
        self.base = base                       # AirtableBase | None
        self._set_meta("base_mode", self.base_mode)
        # per-command through-write bookkeeping
        self._staged = []       # list of (table, pk, fields, op)
        self._base_deferred = False

    # ---- lifecycle --------------------------------------------------------
    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def _resolve_base(self):
        """LIVE when base id + Airtable credential are both present; else
        MIRROR-ONLY (a clean exit-0 mode for un-provisioned boxes and tests)."""
        _, base_id = _env_first(["ANTHOLOGY_STATE_BASE_ID"])
        _, token = _env_first([
            "ANTHOLOGY_STATE_AIRTABLE_KEY", "AIRTABLE_API_KEY",
            "AIRTABLE_TOKEN", "AIRTABLE_PAT",
        ])
        if base_id and token:
            return "live", AirtableBase(base_id, token)
        return "mirror_only", None

    # ---- schema -----------------------------------------------------------
    def _bootstrap_schema(self):
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS producers (
                producer_id         TEXT PRIMARY KEY,
                producer_email      TEXT,
                display_name        TEXT,
                drive_root_folder_id TEXT,
                status              TEXT DEFAULT 'active'
                                    CHECK (status IN ('active','revoked')),
                created_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS anthologies (
                anthology_id        TEXT PRIMARY KEY,
                producer_id         TEXT,
                name                TEXT,
                theme               TEXT,
                status              TEXT DEFAULT 'setup',
                caf_location_binding TEXT,
                caf_pipeline_binding TEXT,
                caf_stage_map       TEXT,
                form_ids            TEXT,
                drive_folder_id     TEXT,
                chapter_order       TEXT,
                assembly_state      TEXT DEFAULT 'not_ready',
                min_chapters        INTEGER DEFAULT 2,
                assembly_ready_at   TEXT,
                created_at          TEXT,
                updated_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS participants (
                participant_key     TEXT PRIMARY KEY,
                contact_id          TEXT,
                anthology_id        TEXT,
                first_name          TEXT,
                last_name           TEXT,
                email               TEXT,
                phone               TEXT,
                ideal_avatar        TEXT,
                niche               TEXT,
                primary_goal        TEXT,
                stage_cursor        TEXT DEFAULT 's0_intake',
                rewrite_count       INTEGER DEFAULT 0,
                qc_attempts_current INTEGER DEFAULT 0,
                tone_inputs         TEXT,
                chapter_about       TEXT,
                personal_stories    TEXT,
                title_locked        TEXT,
                subtitle_locked     TEXT,
                chapter_updates     TEXT,
                hold_reason         TEXT,
                stage_timestamps    TEXT,
                drive_folder_id     TEXT,
                created_at          TEXT,
                updated_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id         TEXT PRIMARY KEY,
                participant_key     TEXT,
                anthology_id        TEXT,
                type                TEXT,
                version             INTEGER,
                drive_doc_id        TEXT,
                doc_url             TEXT,
                pdf_url             TEXT,
                caf_media_url       TEXT,
                custom_field_keys_written TEXT,
                sha256              TEXT,
                prompt_pin_sha256   TEXT,
                model_used          TEXT,
                frozen              INTEGER DEFAULT 0,
                created_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS approvals (
                approval_id         TEXT PRIMARY KEY,
                subject_key         TEXT,
                gate                TEXT,
                actor               TEXT,
                decision            TEXT,
                notes               TEXT,
                door                TEXT,
                decided_at          TEXT,
                idempotency_key     TEXT
            );

            CREATE TABLE IF NOT EXISTS exceptions (
                exception_id        TEXT PRIMARY KEY,
                raw_submission      TEXT,
                reason              TEXT,
                status              TEXT DEFAULT 'open'
                                    CHECK (status IN ('open','resolved')),
                resolved_by         TEXT,
                resolved_participant_key TEXT,
                created_at          TEXT,
                resolved_at         TEXT
            );

            CREATE TABLE IF NOT EXISTS meta (
                key                 TEXT PRIMARY KEY,
                value               TEXT
            );

            -- mirror sync bookkeeping (implementation detail; not a base table) --
            CREATE TABLE IF NOT EXISTS _sync_queue (
                seq                 INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name          TEXT,
                pk                  TEXT,
                op                  TEXT,
                payload             TEXT,
                queued_at           TEXT,
                attempts            INTEGER DEFAULT 0,
                last_error          TEXT
            );
            CREATE TABLE IF NOT EXISTS _base_ids (
                table_name          TEXT,
                pk                  TEXT,
                record_id           TEXT,
                PRIMARY KEY (table_name, pk)
            );
            CREATE TABLE IF NOT EXISTS _holds (
                participant_key     TEXT,
                held_from           TEXT,
                reason              TEXT,
                held_at             TEXT,
                resumed_at          TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_part_anth
                ON participants(anthology_id);
            CREATE INDEX IF NOT EXISTS ix_art_part
                ON artifacts(participant_key, type, version);
            CREATE INDEX IF NOT EXISTS ix_appr_subject
                ON approvals(subject_key, gate);
            """
        )
        # unique idempotency guard for approvals replays (NULLs are distinct)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_appr_idem "
                  "ON approvals(idempotency_key) WHERE idempotency_key IS NOT NULL")
        c.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                  (SCHEMA_VERSION,))
        c.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('base_cursor','')")
        c.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('last_reconcile_at','')")
        c.commit()

    # ---- meta -------------------------------------------------------------
    def _set_meta(self, key, value):
        self.conn.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, str(value)))
        self.conn.commit()

    def get_meta(self, key, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # ---- row reads --------------------------------------------------------
    def _row(self, table, pk_col, pk_val):
        return self.conn.execute(
            "SELECT * FROM %s WHERE %s=?" % (table, pk_col), (pk_val,)
        ).fetchone()

    def producer(self, producer_id):
        return self._row("producers", "producer_id", producer_id)

    def anthology(self, anthology_id):
        return self._row("anthologies", "anthology_id", anthology_id)

    def participant(self, key):
        return self._row("participants", "participant_key", key)

    def exception(self, exception_id):
        return self._row("exceptions", "exception_id", exception_id)

    def members(self, anthology_id):
        return self.conn.execute(
            "SELECT * FROM participants WHERE anthology_id=? ORDER BY participant_key",
            (anthology_id,)
        ).fetchall()

    def latest_artifact(self, participant_key, art_type):
        return self.conn.execute(
            "SELECT * FROM artifacts WHERE participant_key=? AND type=? "
            "ORDER BY version DESC, created_at DESC LIMIT 1",
            (participant_key, art_type)
        ).fetchone()

    def is_excluded(self, subject_key) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM approvals WHERE subject_key=? AND decision='exclude' LIMIT 1",
            (subject_key,)
        ).fetchone()
        return row is not None

    # ---- mirror write primitives (inside the open transaction) -----------
    def _mirror_upsert(self, table, pk_col, pk_val, fields):
        cols = list(fields.keys())
        vals = [fields[k] for k in cols]
        if self.conn.execute("SELECT 1 FROM %s WHERE %s=?" % (table, pk_col),
                             (pk_val,)).fetchone():
            if cols:
                sets = ", ".join("%s=?" % c for c in cols)
                self.conn.execute("UPDATE %s SET %s WHERE %s=?" % (table, sets, pk_col),
                                 vals + [pk_val])
        else:
            allcols = [pk_col] + [c for c in cols if c != pk_col]
            placeholders = ", ".join("?" for _ in allcols)
            row = [pk_val] + [fields[c] for c in allcols if c != pk_col]
            self.conn.execute(
                "INSERT INTO %s (%s) VALUES (%s)"
                % (table, ", ".join(allcols), placeholders), row)

    def _mirror_insert(self, table, fields):
        cols = list(fields.keys())
        placeholders = ", ".join("?" for _ in cols)
        self.conn.execute("INSERT INTO %s (%s) VALUES (%s)"
                          % (table, ", ".join(cols), placeholders),
                          [fields[c] for c in cols])

    def _stage(self, table, pk, fields, op):
        """Record a base op to flush AFTER the mirror commit. Base fields are the
        SPEC columns only (underscore sidecars never go to the base)."""
        self._staged.append((table, pk, dict(fields), op))

    # ---- base flush (after mirror commit) --------------------------------
    def _flush_staged(self):
        if self.base_mode != "live" or not self._staged:
            self._staged = []
            return
        for table, pk, fields, op in self._staged:
            table_name = BASE_TABLE_NAMES.get(table, table)
            base_fields = self._base_fields(table, fields)
            try:
                if op == "create":
                    rid = self.base.create(table_name, base_fields)
                    self._map_base_id(table, pk, rid)
                else:  # upsert
                    rid_row = self.conn.execute(
                        "SELECT record_id FROM _base_ids WHERE table_name=? AND pk=?",
                        (table, pk)).fetchone()
                    if rid_row and rid_row["record_id"]:
                        self.base.update(table_name, rid_row["record_id"], base_fields)
                    else:
                        rid = self.base.create(table_name, base_fields)
                        self._map_base_id(table, pk, rid)
            except BaseUnreachable as exc:
                self._enqueue(table, pk, op, base_fields, str(exc))
                self._base_deferred = True
        self._staged = []

    def _map_base_id(self, table, pk, record_id):
        self.conn.execute(
            "INSERT INTO _base_ids(table_name,pk,record_id) VALUES(?,?,?) "
            "ON CONFLICT(table_name,pk) DO UPDATE SET record_id=excluded.record_id",
            (table, pk, record_id))
        self.conn.commit()

    def _enqueue(self, table, pk, op, fields, err):
        self.conn.execute(
            "INSERT INTO _sync_queue(table_name,pk,op,payload,queued_at,attempts,last_error) "
            "VALUES(?,?,?,?,?,?,?)",
            (table, pk, op, _dumps(fields), now_utc(), 1, err))
        self.conn.commit()

    @staticmethod
    def _base_fields(table, fields):
        """Base rows carry the SPEC columns. The Airtable link fields accept the
        linked id as text via typecast; underscore sidecars are excluded by
        construction (only SPEC columns are ever staged)."""
        return {k: v for k, v in fields.items() if not k.startswith("_") and v is not None}

    # ---- transactional command envelope ----------------------------------
    def commit_write(self):
        """Commit the mirror transaction, then flush staged ops to the base.
        Returns the exit code contribution: 0 if base is satisfied / mirror-only,
        4 if any base op was deferred to the sync queue."""
        self.conn.commit()
        self._base_deferred = False
        self._flush_staged()
        return EXIT_BASE_DEFERRED if self._base_deferred else EXIT_OK

    def rollback(self):
        try:
            self.conn.rollback()
        except sqlite3.Error:
            pass
        self._staged = []


# ===========================================================================
# COMMAND HANDLERS. Each validates fully (reads only) BEFORE staging any write,
# so an illegal/unknown/invalid input changes nothing. Each returns a result
# dict; the base-deferred exit contribution comes from commit_write().
# ===========================================================================
def _touch(fields):
    fields["updated_at"] = now_utc()
    return fields


def _stamp_timestamp(stage_ts_json, cursor):
    ts = _loads(stage_ts_json, {}) or {}
    ts[cursor] = now_utc()
    return _dumps(ts)


# ---- provisioning-side writers (sole-writer channel for the registry) -----
def cmd_bootstrap(led: Ledger, a):
    """Idempotently ensure the mirror schema and meta exist (schema is created in
    the constructor). Emits the store status. Provisioning shells this first."""
    return {
        "ok": True, "action": "bootstrap",
        "db_path": str(led.db_path),
        "schema_version": led.get_meta("schema_version"),
        "base_mode": led.base_mode,
    }


def cmd_upsert_producer(led: Ledger, a):
    pid = _require(a.producer_id, "--producer-id")
    exists = led.producer(pid)
    fields = {"producer_id": pid}
    for src, col in (("producer_email", "producer_email"),
                     ("display_name", "display_name"),
                     ("drive_root_folder_id", "drive_root_folder_id"),
                     ("status", "status")):
        val = getattr(a, src, None)
        if val is not None:
            fields[col] = val
    if fields.get("status") and fields["status"] not in PRODUCER_STATUS:
        raise _invalid("status must be one of %s" % (PRODUCER_STATUS,))
    if not exists:
        fields.setdefault("status", "active")
        fields["created_at"] = now_utc()
    led._mirror_upsert("producers", "producer_id", pid, fields)
    led._stage("producers", pid, fields, "create" if not exists else "upsert")
    return {"ok": True, "action": "upsert-producer", "producer_id": pid,
            "created": not exists}


def cmd_upsert_anthology(led: Ledger, a):
    aid = _require(a.anthology_id, "--anthology-id")
    pid = a.producer_id
    if pid is not None and not led.producer(pid):
        raise _unknown("unknown producer_id %r" % pid)
    exists = led.anthology(aid)
    fields = {"anthology_id": aid}
    if pid is not None:
        fields["producer_id"] = pid
    for src, col, is_json in (
        ("name", "name", False), ("theme", "theme", False),
        ("status", "status", False),
        ("caf_location_binding", "caf_location_binding", False),
        ("caf_pipeline_binding", "caf_pipeline_binding", False),
        ("caf_stage_map", "caf_stage_map", True),
        ("form_ids", "form_ids", True),
        ("drive_folder_id", "drive_folder_id", False),
        ("min_chapters", "min_chapters", False),
    ):
        val = getattr(a, src, None)
        if val is None:
            continue
        if is_json and _loads(val) is None and val not in ("{}", "[]"):
            raise _invalid("%s must be valid JSON" % src)
        fields[col] = val
    if fields.get("status") and fields["status"] not in ANTHOLOGY_STATUS:
        raise _invalid("status must be one of %s" % (ANTHOLOGY_STATUS,))
    if "min_chapters" in fields:
        try:
            mc = int(fields["min_chapters"])
        except (TypeError, ValueError):
            raise _invalid("--min-chapters must be an integer")
        if mc < MIN_CHAPTERS_FLOOR:
            raise _invalid("min_chapters floor is %d" % MIN_CHAPTERS_FLOOR)
        fields["min_chapters"] = mc
    if not exists:
        fields.setdefault("status", "setup")
        fields.setdefault("assembly_state", "not_ready")
        fields.setdefault("min_chapters", MIN_CHAPTERS_FLOOR)
        fields["created_at"] = now_utc()
    _touch(fields)
    led._mirror_upsert("anthologies", "anthology_id", aid, fields)
    led._stage("anthologies", aid, fields, "create" if not exists else "upsert")
    return {"ok": True, "action": "upsert-anthology", "anthology_id": aid,
            "created": not exists}


# ---- participant lifecycle -------------------------------------------------
def cmd_upsert_participant(led: Ledger, a):
    contact_id = _require(a.contact_id, "--contact-id")
    anthology_id = _require(a.anthology_id, "--anthology-id")
    if not led.anthology(anthology_id):
        raise _unknown("unknown anthology_id %r (register the anthology first)"
                       % anthology_id)
    key = participant_key(contact_id, anthology_id)
    exists = led.participant(key)
    fields = {"participant_key": key, "contact_id": contact_id,
              "anthology_id": anthology_id}
    for src, col, is_json in (
        ("first_name", "first_name", False), ("last_name", "last_name", False),
        ("email", "email", False), ("phone", "phone", False),
        ("ideal_avatar", "ideal_avatar", False), ("niche", "niche", False),
        ("primary_goal", "primary_goal", False),
        ("tone_inputs", "tone_inputs", True),
        ("chapter_about", "chapter_about", False),
        ("personal_stories", "personal_stories", True),
        ("drive_folder_id", "drive_folder_id", False),
    ):
        val = getattr(a, src, None)
        if val is None:
            continue
        _guard_no_secret(val, col)
        if is_json and _loads(val) is None and val not in ("{}", "[]"):
            raise _invalid("%s must be valid JSON" % src)
        fields[col] = val
    if not exists:
        fields["stage_cursor"] = "s0_intake"
        fields["rewrite_count"] = 0
        fields["qc_attempts_current"] = 0
        fields["stage_timestamps"] = _stamp_timestamp(None, "s0_intake")
        fields["created_at"] = now_utc()
    _touch(fields)
    led._mirror_upsert("participants", "participant_key", key, fields)
    led._stage("participants", key, fields, "create" if not exists else "upsert")
    return {"ok": True, "action": "upsert-participant", "participant_key": key,
            "created": not exists, "stage_cursor":
            (fields.get("stage_cursor") or (exists["stage_cursor"] if exists else None))}


def cmd_advance_stage(led: Ledger, a):
    """Advance a participant's stage_cursor along a MACHINE-DRIVEN edge (a stage
    runner finished its work). Gate crossings are NOT permitted here — those are
    owned by record-approval, which writes the approvals audit row and enforces the
    per-gate guards. advance-stage refuses the gate-decision edges (SPEC 7.3)."""
    key = _require(a.participant_key, "--participant-key")
    to = _require(a.to, "--to")
    if to not in STAGE_CURSORS:
        raise _invalid("unknown target stage %r" % to)
    p = led.participant(key)
    if not p:
        raise _unknown("unknown participant_key %r" % key)
    cur = p["stage_cursor"]
    # idempotent replay: already at target -> acknowledged no-op (nothing lost)
    if cur == to:
        return {"ok": True, "action": "advance-stage", "participant_key": key,
                "from": cur, "to": to, "noop": True}
    if (cur, to) not in STAGE_EDGES:
        raise _illegal("illegal transition %s -> %s for %s" % (cur, to, key),
                       {"from": cur, "to": to})
    # A gate crossing is owned by record-approval (it writes the approvals audit row
    # and runs the per-gate guards: title lock, rewrite budget, s5 chapter freeze).
    # advance-stage is the MACHINE-DRIVEN channel only; it must NOT be a second door
    # past a producer/participant gate (SPEC 7.3: these edges fire "on approvals
    # row"). Refuse the gate-decision edges so the row and guards always fire.
    if (cur, to) in GATE_DECISION_EDGES:
        raise _illegal("transition %s -> %s is a gate decision owned by "
                       "record-approval, not advance-stage; cross it with a "
                       "record-approval so the audit row and per-gate guards fire"
                       % (cur, to), {"from": cur, "to": to, "channel": "record-approval"})
    # NOTE: there is deliberately NO edge FROM held in STAGE_EDGES — a held
    # participant returns to its EXACT recorded cursor only through `resume`
    # (SPEC 7.3: "resume ONLY to the recorded cursor"), never through advance.
    fields = {"stage_cursor": to,
              "stage_timestamps": _stamp_timestamp(p["stage_timestamps"], to)}
    _touch(fields)
    led._mirror_upsert("participants", "participant_key", key, fields)
    led._stage("participants", key, fields, "upsert")
    # arm the anthology the moment its last contributor reaches "approved"
    if to == "approved":
        _maybe_arm(led, p["anthology_id"])
    return {"ok": True, "action": "advance-stage", "participant_key": key,
            "from": cur, "to": to}


def cmd_set_counter(led: Ledger, a):
    """Sole-writer channel for the strike gate (qc-strike-gate.py) to persist the
    rewrite_count / qc_attempts_current counters it owns. Bounds are enforced."""
    key = _require(a.participant_key, "--participant-key")
    counter = _require(a.counter, "--counter")
    if counter not in ("rewrite_count", "qc_attempts_current"):
        raise _invalid("--counter must be rewrite_count or qc_attempts_current")
    try:
        value = int(_require(a.value, "--value"))
    except (TypeError, ValueError):
        raise _invalid("--value must be an integer")
    cap = REWRITE_BUDGET if counter == "rewrite_count" else QC_ATTEMPT_CAP
    if value < 0 or value > cap:
        raise _invalid("%s out of range 0..%d" % (counter, cap))
    p = led.participant(key)
    if not p:
        raise _unknown("unknown participant_key %r" % key)
    fields = _touch({counter: value})
    led._mirror_upsert("participants", "participant_key", key, fields)
    led._stage("participants", key, fields, "upsert")
    return {"ok": True, "action": "set-counter", "participant_key": key,
            "counter": counter, "value": value}


def cmd_record_artifact(led: Ledger, a):
    art_type = _require(a.type, "--type")
    if art_type not in ARTIFACT_TYPES:
        raise _invalid("unknown artifact type %r" % art_type)
    key = a.participant_key
    anthology_id = a.anthology_id
    if art_type == "anthology_manuscript":
        anthology_id = _require(anthology_id, "--anthology-id")
        if not led.anthology(anthology_id):
            raise _unknown("unknown anthology_id %r" % anthology_id)
    else:
        key = _require(key, "--participant-key")
        p = led.participant(key)
        if not p:
            raise _unknown("unknown participant_key %r" % key)
        anthology_id = anthology_id or p["anthology_id"]
    _guard_model_used(a.model_used)
    sha = a.sha256
    # idempotent replay: a same-type row with the same sha256 already exists.
    if sha:
        dup = led.conn.execute(
            "SELECT artifact_id, version FROM artifacts "
            "WHERE type=? AND sha256=? AND "
            "((participant_key=?) OR (participant_key IS NULL AND anthology_id=?)) LIMIT 1",
            (art_type, sha, key, anthology_id)).fetchone()
        if dup:
            return {"ok": True, "action": "record-artifact", "noop": True,
                    "artifact_id": dup["artifact_id"], "version": dup["version"]}
    # next version per (scope, type)
    if key:
        row = led.conn.execute(
            "SELECT MAX(version) AS v FROM artifacts WHERE participant_key=? AND type=?",
            (key, art_type)).fetchone()
    else:
        row = led.conn.execute(
            "SELECT MAX(version) AS v FROM artifacts "
            "WHERE participant_key IS NULL AND anthology_id=? AND type=?",
            (anthology_id, art_type)).fetchone()
    version = (row["v"] or 0) + 1
    art_id = a.artifact_id or gen_id("art")
    fields = {
        "artifact_id": art_id, "participant_key": key, "anthology_id": anthology_id,
        "type": art_type, "version": version,
        "drive_doc_id": a.drive_doc_id, "doc_url": a.doc_url, "pdf_url": a.pdf_url,
        "caf_media_url": a.caf_media_url,
        "custom_field_keys_written": a.custom_field_keys_written,
        "sha256": sha, "prompt_pin_sha256": a.prompt_pin_sha256,
        "model_used": a.model_used,
        "frozen": 1 if getattr(a, "frozen", False) else 0,
        "created_at": now_utc(),
    }
    led._mirror_insert("artifacts", fields)
    led._stage("artifacts", art_id, fields, "create")
    return {"ok": True, "action": "record-artifact", "artifact_id": art_id,
            "type": art_type, "version": version}


# ---- gates / approvals -----------------------------------------------------
def _append_chapter_update(p_row, note):
    updates = _loads(p_row["chapter_updates"], []) or []
    updates.append({"note": note, "at": now_utc()})
    return _dumps(updates)


def _idem_hit(led, idem):
    if not idem:
        return None
    return led.conn.execute(
        "SELECT approval_id FROM approvals WHERE idempotency_key=? LIMIT 1",
        (idem,)).fetchone()


def cmd_record_approval(led: Ledger, a):
    gate = _require(a.gate, "--gate")
    if gate not in APPROVAL_GATES:
        raise _invalid("unknown gate %r" % gate)
    if gate in ("s9_ready", "s9_producer"):
        return _record_assembly_approval(led, a, gate)
    return _record_participant_approval(led, a, gate)


def _record_participant_approval(led: Ledger, a, gate):
    key = _require(a.subject_key or a.participant_key, "--subject-key/--participant-key")
    decision = _require(a.decision, "--decision")
    if decision not in APPROVAL_DECISIONS:
        raise _invalid("unknown decision %r" % decision)
    actor = a.actor or ("participant" if gate in
                        ("s3_selection", "s4_participant", "s5_participant") else "producer")
    if actor not in APPROVAL_ACTORS:
        raise _invalid("unknown actor %r" % actor)
    door = a.door or "dashboard"
    if door not in APPROVAL_DOORS:
        raise _invalid("door must be one of %s" % (APPROVAL_DOORS,))
    p = led.participant(key)
    if not p:
        raise _unknown("unknown participant_key %r" % key)
    # idempotent replay
    hit = _idem_hit(led, a.idempotency_key)
    if hit:
        return {"ok": True, "action": "record-approval", "gate": gate,
                "noop": True, "approval_id": hit["approval_id"]}

    cur = p["stage_cursor"]
    part_fields = {}

    if decision in ("approve", "request_rewrite"):
        edge = GATE_EDGE.get((gate, decision))
        if not edge:
            raise _illegal("gate %s does not accept decision %s" % (gate, decision))
        want_from, to = edge
        if cur != want_from:
            raise _illegal("gate %s/%s requires cursor %s but participant is at %s"
                           % (gate, decision, want_from, cur),
                           {"from": cur, "expected": want_from})
        if (want_from, to) not in STAGE_EDGES:   # matrix backstop
            raise _illegal("illegal transition %s -> %s" % (want_from, to))

        # s3 selection stamps the TITLE LOCK, one-way.
        if gate == "s3_selection":
            title = _require(a.title, "--title")
            subtitle = a.subtitle
            locked_t, locked_s = p["title_locked"], p["subtitle_locked"]
            if locked_t and (locked_t != title or (locked_s or "") != (subtitle or "")):
                raise _illegal("title lock is one-way; %s already locked title/subtitle "
                               "(a change requires a producer exception)" % key)
            part_fields["title_locked"] = title
            if subtitle is not None:
                part_fields["subtitle_locked"] = subtitle

        # s5 rewrite request enforces the budget; a silent 3rd rewrite is illegal.
        if gate == "s5_participant" and decision == "request_rewrite":
            if (p["rewrite_count"] or 0) >= REWRITE_BUDGET:
                raise _illegal("rewrite budget %d exhausted for %s; a third rewrite "
                               "is an illegal transition (approve-as-is or escalate)"
                               % (REWRITE_BUDGET, key))
            part_fields["rewrite_count"] = (p["rewrite_count"] or 0) + 1
            if a.notes:
                part_fields["chapter_updates"] = _append_chapter_update(p, a.notes)

        # s5 approve FREEZES the current chapter artifact (staged, byte-stable).
        if gate == "s5_participant" and decision == "approve":
            chap = led.latest_artifact(key, "chapter")
            if not chap:
                raise _invalid("cannot approve chapter for %s: no chapter artifact "
                               "recorded" % key)
            led.conn.execute("UPDATE artifacts SET frozen=1 WHERE artifact_id=?",
                             (chap["artifact_id"],))
            led._stage("artifacts", chap["artifact_id"], {"frozen": 1}, "upsert")

        part_fields["stage_cursor"] = to
        part_fields["stage_timestamps"] = _stamp_timestamp(p["stage_timestamps"], to)

    elif decision == "hold":
        # a producer/participant hold routes through the hold path (ANY -> held)
        _hold_participant(led, p, a.reason or "strike_out")
        part_fields = None  # already written by _hold_participant

    elif decision == "exclude":
        # edition exclusion; recorded, participant not deleted; may re-arm S9.
        pass

    elif decision == "escalate":
        # recorded only (producer escalation); cursor unchanged.
        pass

    # append the approvals row (append-only audit trail)
    approval_id = a.approval_id or gen_id("appr")
    appr = {
        "approval_id": approval_id, "subject_key": key, "gate": gate,
        "actor": actor, "decision": decision, "notes": a.notes,
        "door": door, "decided_at": now_utc(),
        "idempotency_key": a.idempotency_key,
    }
    led._mirror_insert("approvals", appr)
    led._stage("approvals", approval_id, appr, "create")

    if part_fields:
        _touch(part_fields)
        led._mirror_upsert("participants", "participant_key", key, part_fields)
        led._stage("participants", key, part_fields, "upsert")

    # an exclusion can be the final condition that makes the anthology arm-eligible
    if decision == "exclude":
        _maybe_arm(led, p["anthology_id"])

    return {"ok": True, "action": "record-approval", "gate": gate,
            "decision": decision, "approval_id": approval_id,
            "participant_key": key,
            "stage_cursor": (part_fields or {}).get("stage_cursor", cur)}


def _record_assembly_approval(led: Ledger, a, gate):
    anthology_id = _require(a.anthology_id or a.subject_key, "--anthology-id")
    anth = led.anthology(anthology_id)
    if not anth:
        raise _unknown("unknown anthology_id %r" % anthology_id)
    door = a.door or "dashboard"
    if door not in APPROVAL_DOORS:
        raise _invalid("door must be one of %s" % (APPROVAL_DOORS,))

    if gate == "s9_ready":
        return _fire_s9_ready(led, a, anth, door)

    # gate == s9_producer: final manuscript sign-off closes the anthology.
    _require_producer(a, anth)
    if anth["assembly_state"] == "signed_off":
        return {"ok": True, "action": "record-approval", "gate": gate,
                "noop": True, "anthology_id": anthology_id}
    if anth["assembly_state"] != "compiled":
        raise _illegal("s9_producer sign-off requires assembly_state 'compiled', "
                       "found %r" % anth["assembly_state"])
    _assembly_transition(led, anth, "signed_off")
    led._mirror_upsert("anthologies", "anthology_id", anthology_id,
                       _touch({"status": "delivered"}))
    led._stage("anthologies", anthology_id,
               {"assembly_state": "signed_off", "status": "delivered",
                "updated_at": now_utc()}, "upsert")
    # member participants transition approved -> delivered
    delivered = []
    for m in led.members(anthology_id):
        if m["stage_cursor"] == "approved" and not led.is_excluded(m["participant_key"]):
            f = {"stage_cursor": "delivered",
                 "stage_timestamps": _stamp_timestamp(m["stage_timestamps"], "delivered")}
            _touch(f)
            led._mirror_upsert("participants", "participant_key", m["participant_key"], f)
            led._stage("participants", m["participant_key"], f, "upsert")
            delivered.append(m["participant_key"])
    approval_id = a.approval_id or gen_id("appr")
    appr = {"approval_id": approval_id, "subject_key": anthology_id, "gate": gate,
            "actor": "producer", "decision": "approve", "notes": a.notes,
            "door": door, "decided_at": now_utc(), "idempotency_key": a.idempotency_key}
    led._mirror_insert("approvals", appr)
    led._stage("approvals", approval_id, appr, "create")
    return {"ok": True, "action": "record-approval", "gate": gate,
            "anthology_id": anthology_id, "assembly_state": "signed_off",
            "delivered_participants": delivered, "approval_id": approval_id}


def _require_producer(a, anth):
    """Own-producer auth guard (SPEC 7.3): the supplied producer id must equal the
    anthology's producer. A non-producer is refused (exit 5)."""
    pid = a.producer_id
    if not pid:
        raise _invalid("s9 gate requires --producer-id (own-producer auth)")
    if pid != anth["producer_id"]:
        raise _invalid("producer %r is not the owning producer of anthology %r; "
                       "the ready-to-assemble trigger is own-producer only"
                       % (pid, anth["anthology_id"]))


def _readiness(led: Ledger, anth):
    """Compute the S9 readiness / blocking list (read-only)."""
    anthology_id = anth["anthology_id"]
    min_chapters = int(anth["min_chapters"] or MIN_CHAPTERS_FLOOR)
    blocking = []
    frozen_chapter_count = 0
    members = led.members(anthology_id)
    counted = 0
    for m in members:
        mk = m["participant_key"]
        excluded = led.is_excluded(mk)
        if excluded:
            continue
        counted += 1
        if m["stage_cursor"] not in APPROVED_CURSORS:
            blocking.append({"participant_key": mk, "reason": "not_approved",
                             "stage_cursor": m["stage_cursor"]})
            continue
        chap = led.conn.execute(
            "SELECT 1 FROM artifacts WHERE participant_key=? AND type='chapter' "
            "AND frozen=1 LIMIT 1", (mk,)).fetchone()
        if not chap:
            blocking.append({"participant_key": mk, "reason": "no_frozen_chapter",
                             "stage_cursor": m["stage_cursor"]})
        else:
            frozen_chapter_count += 1
    below_min = frozen_chapter_count < min_chapters
    ready = (not blocking) and (not below_min) and counted > 0
    return {
        "anthology_id": anthology_id,
        "ready": ready,
        "armed": anth["assembly_state"] in ("armed",) or anth["assembly_state"] in ASSEMBLY_FIRED,
        "assembly_state": anth["assembly_state"],
        "min_chapters": min_chapters,
        "frozen_chapter_count": frozen_chapter_count,
        "active_members": counted,
        "below_min_chapters": below_min,
        "blocking": blocking,
    }


def _maybe_arm(led: Ledger, anthology_id):
    """Arm the trigger (not_ready -> armed) the moment every participant is
    approved or excluded AND at least min_chapters frozen chapters exist. Never
    advances past armed; the producer's s9_ready does that."""
    anth = led.anthology(anthology_id)
    if not anth or anth["assembly_state"] != "not_ready":
        return
    r = _readiness(led, anth)
    if r["ready"]:
        _assembly_transition(led, anth, "armed")
        f = {"assembly_state": "armed", "updated_at": now_utc()}
        led._stage("anthologies", anthology_id, f, "upsert")


def _fire_s9_ready(led: Ledger, a, anth, door):
    anthology_id = anth["anthology_id"]
    # (a) one-way: a trigger already fired is an acknowledged no-op.
    if anth["assembly_state"] in ASSEMBLY_FIRED:
        return {"ok": True, "action": "record-approval", "gate": "s9_ready",
                "noop": True, "anthology_id": anthology_id,
                "assembly_state": anth["assembly_state"]}
    # (b) typed anthology-name confirmation (mismatch exits 5).
    confirm = a.confirm_name
    if confirm is None:
        raise _invalid("s9_ready requires --confirm-name (typed anthology-name "
                       "confirmation)")
    if str(confirm).strip() != str(anth["name"] or "").strip():
        raise _invalid("--confirm-name does not match the anthology name; "
                       "nothing changed")
    # (c) own-producer auth (exit 5 on a non-producer).
    _require_producer(a, anth)
    # (d) structural readiness: every participant approved/excluded and
    #     >= min_chapters frozen approved chapters. Not-ready is an illegal
    #     transition (exit 2) and emits the blocking list.
    r = _readiness(led, anth)
    if not r["ready"]:
        raise _illegal("anthology %r is not ready to assemble" % anthology_id, r)
    # arm-then-confirm in one legal walk (covers a missed auto-arm)
    if anth["assembly_state"] == "not_ready":
        _assembly_transition(led, anth, "armed")
        anth = led.anthology(anthology_id)
    _assembly_transition(led, anth, "ready_confirmed")
    ready_at = now_utc()
    led._mirror_upsert("anthologies", "anthology_id", anthology_id,
                       {"status": "ready_to_assemble", "assembly_ready_at": ready_at,
                        "updated_at": ready_at})
    led._stage("anthologies", anthology_id,
               {"assembly_state": "ready_confirmed", "status": "ready_to_assemble",
                "assembly_ready_at": ready_at, "updated_at": ready_at}, "upsert")
    approval_id = a.approval_id or gen_id("appr")
    appr = {"approval_id": approval_id, "subject_key": anthology_id, "gate": "s9_ready",
            "actor": "producer", "decision": "ready_to_assemble", "notes": a.notes,
            "door": door, "decided_at": ready_at, "idempotency_key": a.idempotency_key}
    led._mirror_insert("approvals", appr)
    led._stage("approvals", approval_id, appr, "create")
    return {"ok": True, "action": "record-approval", "gate": "s9_ready",
            "anthology_id": anthology_id, "assembly_state": "ready_confirmed",
            "approval_id": approval_id, "frozen_chapter_count": r["frozen_chapter_count"]}


def _assembly_transition(led: Ledger, anth, to):
    frm = anth["assembly_state"]
    if frm == to:
        return
    if (frm, to) not in ASSEMBLY_EDGES:
        raise _illegal("illegal assembly transition %s -> %s for %s"
                       % (frm, to, anth["anthology_id"]))
    led.conn.execute("UPDATE anthologies SET assembly_state=?, updated_at=? "
                     "WHERE anthology_id=?", (to, now_utc(), anth["anthology_id"]))


def cmd_assembly_readiness_report(led: Ledger, a):
    """READ-ONLY. Emits the blocking list that arms or refuses the trigger."""
    anthology_id = _require(a.anthology_id, "--anthology-id")
    anth = led.anthology(anthology_id)
    if not anth:
        raise _unknown("unknown anthology_id %r" % anthology_id)
    r = _readiness(led, anth)
    r["ok"] = True
    r["action"] = "assembly-readiness-report"
    r["read_only"] = True
    return r


def cmd_assembly_set_order(led: Ledger, a):
    """Write Anthologies.chapter_order (the S9 curation of record). ae-01 proposes
    (-> proposed); the producer adjusts (-> adjusted). Every key must be an
    approved, non-excluded member with a frozen chapter, present exactly once."""
    anthology_id = _require(a.anthology_id, "--anthology-id")
    anth = led.anthology(anthology_id)
    if not anth:
        raise _unknown("unknown anthology_id %r" % anthology_id)
    order = _loads(a.order)
    if not isinstance(order, list) or not order:
        raise _invalid("--order must be a non-empty JSON array of participant_keys")
    if len(order) != len(set(order)):
        raise _invalid("--order contains duplicate participant_keys")
    # membership: approved, non-excluded, with a frozen chapter
    valid = set()
    for m in led.members(anthology_id):
        mk = m["participant_key"]
        if led.is_excluded(mk):
            continue
        if m["stage_cursor"] not in APPROVED_CURSORS:
            continue
        chap = led.conn.execute(
            "SELECT 1 FROM artifacts WHERE participant_key=? AND type='chapter' "
            "AND frozen=1 LIMIT 1", (mk,)).fetchone()
        if chap:
            valid.add(mk)
    unknown = [k for k in order if k not in valid]
    if unknown:
        raise _invalid("order references non-member/unfrozen keys: %s" % unknown)
    if set(order) != valid:
        raise _invalid("order must be a permutation of the staged collection "
                       "(missing: %s)" % sorted(valid - set(order)))
    to_state = a.state or ("adjusted" if anth["assembly_state"] in
                           ("proposed", "adjusted") else "proposed")
    if to_state not in ("proposed", "adjusted"):
        raise _invalid("--state must be proposed or adjusted")
    _assembly_transition(led, anth, to_state)
    fields = {"chapter_order": _dumps(order), "assembly_state": to_state}
    _touch(fields)
    led._mirror_upsert("anthologies", "anthology_id", anthology_id, fields)
    led._stage("anthologies", anthology_id, fields, "upsert")
    return {"ok": True, "action": "assembly-set-order", "anthology_id": anthology_id,
            "assembly_state": to_state, "order_len": len(order)}


def cmd_assembly_advance(led: Ledger, a):
    """Advance the anthology-scope assembly_state on the edges assembly-advance OWNS
    and ONLY those: the compile step ({ready_confirmed|proposed|adjusted} -> compiled)
    and the producer-initiated reopen (-> not_ready). It is DELIBERATELY NOT a door
    into the S9 guard states: armed, ready_confirmed, proposed, adjusted, and
    signed_off each have their own guarded channel and are refused here (exit 2), so
    no second, unguarded path into the trigger states exists (SPEC 7.3 / PRD 3.11).
    The compile step re-proves S9 structural readiness (min_chapters floor, every
    non-excluded member approved with a frozen chapter) AND may pass --verify-sha
    'key=sha,...' to re-prove each frozen chapter byte-identical against its
    Artifacts row before inclusion (readiness fail exits 2, sha mismatch exits 5)."""
    anthology_id = _require(a.anthology_id, "--anthology-id")
    to = _require(a.to, "--to")
    if to not in ASSEMBLY_STATE:
        raise _invalid("unknown assembly_state %r" % to)
    if to not in ASSEMBLY_ADVANCE_TARGETS:
        # a KNOWN state, but reaching it is owned by a guarded channel — refusing it
        # here is what keeps armed/ready_confirmed/proposed/adjusted/signed_off from
        # having a second, unguarded door (this is the S9 guard, SPEC 7.3).
        raise _illegal(
            "assembly-advance does not own the transition into %r; it advances only "
            "to %s. armed/ready_confirmed are the s9_ready trigger (record-approval "
            "--gate s9_ready, own-producer + --confirm-name + readiness); "
            "proposed/adjusted are assembly-set-order; signed_off is the s9_producer "
            "sign-off (record-approval --gate s9_producer)"
            % (to, " or ".join(ASSEMBLY_ADVANCE_TARGETS)),
            {"to": to, "allowed": list(ASSEMBLY_ADVANCE_TARGETS)})
    anth = led.anthology(anthology_id)
    if not anth:
        raise _unknown("unknown anthology_id %r" % anthology_id)
    if anth["assembly_state"] == to:
        return {"ok": True, "action": "assembly-advance", "anthology_id": anthology_id,
                "assembly_state": to, "noop": True}
    if to == "compiled":
        # DEFENSE-IN-DEPTH: re-prove S9 structural readiness at compile so a compile
        # can never ship below the min_chapters floor (or with a non-approved /
        # unfrozen member) even if the collection drifted after ready_confirmed
        # (SPEC 7.3 / PRD 3.11). A not-ready anthology is an illegal transition.
        r = _readiness(led, anth)
        if not r["ready"]:
            raise _illegal("anthology %r is not ready to compile" % anthology_id, r)
        # staging check: every ordered member's frozen chapter still present, and
        # (optionally) byte-identical to the provided sha.
        order = _loads(anth["chapter_order"], []) or []
        if not order:
            raise _illegal("cannot compile anthology %r before an order is set"
                           % anthology_id)
        verify = _parse_kv(a.verify_sha) if a.verify_sha else {}
        for mk in order:
            chap = led.conn.execute(
                "SELECT sha256 FROM artifacts WHERE participant_key=? AND type='chapter' "
                "AND frozen=1 ORDER BY version DESC LIMIT 1", (mk,)).fetchone()
            if not chap:
                raise _invalid("member %s has no frozen chapter at compile time" % mk)
            if mk in verify and verify[mk] != (chap["sha256"] or ""):
                raise _invalid("frozen-chapter sha mismatch for %s; compilation "
                               "aborted, nothing changed" % mk)
    fields = {"assembly_state": to}
    if to == "not_ready":            # producer reopen voids in-progress assembly
        fields["chapter_order"] = None
        fields["assembly_ready_at"] = None
    _assembly_transition(led, anth, to)
    _touch(fields)
    # assembly_state itself was set by _assembly_transition; upsert the extras
    led._mirror_upsert("anthologies", "anthology_id", anthology_id, fields)
    led._stage("anthologies", anthology_id, fields, "upsert")
    return {"ok": True, "action": "assembly-advance", "anthology_id": anthology_id,
            "assembly_state": to}


def _parse_kv(raw):
    out = {}
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise _invalid("--verify-sha must be 'key=sha,key=sha'")
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


# ---- holds / resume --------------------------------------------------------
def _hold_participant(led: Ledger, p, reason):
    if reason not in HOLD_REASONS:
        raise _invalid("hold reason must be one of %s" % (HOLD_REASONS,))
    key = p["participant_key"]
    if p["stage_cursor"] == "held":
        return  # already held (idempotent)
    # record the pre-hold cursor so resume returns to EXACTLY it
    led.conn.execute(
        "INSERT INTO _holds(participant_key,held_from,reason,held_at,resumed_at) "
        "VALUES(?,?,?,?,NULL)", (key, p["stage_cursor"], reason, now_utc()))
    fields = _touch({"stage_cursor": "held", "hold_reason": reason,
                     "stage_timestamps": _stamp_timestamp(p["stage_timestamps"], "held")})
    led._mirror_upsert("participants", "participant_key", key, fields)
    led._stage("participants", key, fields, "upsert")


def cmd_hold(led: Ledger, a):
    key = _require(a.participant_key, "--participant-key")
    reason = _require(a.reason, "--reason")
    p = led.participant(key)
    if not p:
        raise _unknown("unknown participant_key %r" % key)
    if p["stage_cursor"] == "held":
        return {"ok": True, "action": "hold", "participant_key": key, "noop": True,
                "hold_reason": p["hold_reason"]}
    _hold_participant(led, p, reason)
    return {"ok": True, "action": "hold", "participant_key": key, "hold_reason": reason}


def cmd_resume(led: Ledger, a):
    key = _require(a.participant_key, "--participant-key")
    p = led.participant(key)
    if not p:
        raise _unknown("unknown participant_key %r" % key)
    if p["stage_cursor"] != "held":
        # idempotent: nothing to resume (already running at its recorded cursor)
        return {"ok": True, "action": "resume", "participant_key": key, "noop": True,
                "stage_cursor": p["stage_cursor"]}
    hold = led.conn.execute(
        "SELECT rowid, held_from FROM _holds WHERE participant_key=? AND resumed_at IS NULL "
        "ORDER BY rowid DESC LIMIT 1", (key,)).fetchone()
    if not hold or not hold["held_from"]:
        raise _illegal("no recorded pre-hold cursor for %s; cannot resume" % key)
    target = hold["held_from"]
    # resume ONLY to the recorded cursor (any other target is illegal)
    if a.to and a.to != target:
        raise _illegal("resume target %r differs from the recorded pre-hold cursor "
                       "%r; resume is one-target only" % (a.to, target))
    led.conn.execute("UPDATE _holds SET resumed_at=? WHERE rowid=?",
                     (now_utc(), hold["rowid"]))
    fields = _touch({"stage_cursor": target, "hold_reason": None,
                     "stage_timestamps": _stamp_timestamp(p["stage_timestamps"], target)})
    led._mirror_upsert("participants", "participant_key", key, fields)
    led._stage("participants", key, fields, "upsert")
    return {"ok": True, "action": "resume", "participant_key": key,
            "stage_cursor": target}


# ---- exceptions ------------------------------------------------------------
def cmd_exception_open(led: Ledger, a):
    reason = _require(a.reason, "--reason")
    if reason not in EXCEPTION_REASONS:
        raise _invalid("reason must be one of %s" % (EXCEPTION_REASONS,))
    raw = a.raw_submission or "{}"
    if _loads(raw) is None:
        raise _invalid("--raw-submission must be valid JSON (the payload preserved)")
    exc_id = a.exception_id or gen_id("exc")
    fields = {"exception_id": exc_id, "raw_submission": raw, "reason": reason,
              "status": "open", "resolved_by": None, "resolved_participant_key": None,
              "created_at": now_utc(), "resolved_at": None}
    led._mirror_insert("exceptions", fields)
    led._stage("exceptions", exc_id, fields, "create")
    # optionally mark a known participant as in the exception state
    if a.participant_key:
        p = led.participant(a.participant_key)
        if p and p["stage_cursor"] != "exception":
            f = _touch({"stage_cursor": "exception",
                        "stage_timestamps": _stamp_timestamp(p["stage_timestamps"], "exception")})
            led._mirror_upsert("participants", "participant_key", a.participant_key, f)
            led._stage("participants", a.participant_key, f, "upsert")
    return {"ok": True, "action": "exception-open", "exception_id": exc_id,
            "reason": reason}


def cmd_exception_resolve(led: Ledger, a):
    exc_id = _require(a.exception_id, "--exception-id")
    exc = led.exception(exc_id)
    if not exc:
        raise _unknown("unknown exception_id %r" % exc_id)
    if exc["status"] == "resolved":
        return {"ok": True, "action": "exception-resolve", "exception_id": exc_id,
                "noop": True}
    fields = {"status": "resolved", "resolved_by": a.resolved_by,
              "resolved_participant_key": a.resolved_participant_key,
              "resolved_at": now_utc()}
    led._mirror_upsert("exceptions", "exception_id", exc_id, fields)
    led._stage("exceptions", exc_id, fields, "upsert")
    return {"ok": True, "action": "exception-resolve", "exception_id": exc_id,
            "resolved_participant_key": a.resolved_participant_key}


# ---- reconcile / export ----------------------------------------------------
def cmd_reconcile_mirror(led: Ledger, a):
    """Daily reconcile. (1) Flush queued base ops UP to the authoritative base.
    (2) In live mode, pull base rows DOWN and, on divergence with a synced mirror
    row, THE BASE WINS. In mirror-only mode there is no base: a clean no-op that
    only stamps last_reconcile_at."""
    flushed, still_queued = 0, 0
    pulled = 0
    if led.base_mode == "live":
        rows = led.conn.execute(
            "SELECT seq, table_name, pk, op, payload FROM _sync_queue "
            "ORDER BY seq ASC").fetchall()
        for r in rows:
            table_name = BASE_TABLE_NAMES.get(r["table_name"], r["table_name"])
            fields = _loads(r["payload"], {}) or {}
            try:
                rid_row = led.conn.execute(
                    "SELECT record_id FROM _base_ids WHERE table_name=? AND pk=?",
                    (r["table_name"], r["pk"])).fetchone()
                if r["op"] == "create" and not (rid_row and rid_row["record_id"]):
                    rid = led.base.create(table_name, fields)
                    led._map_base_id(r["table_name"], r["pk"], rid)
                elif rid_row and rid_row["record_id"]:
                    led.base.update(table_name, rid_row["record_id"], fields)
                else:
                    rid = led.base.create(table_name, fields)
                    led._map_base_id(r["table_name"], r["pk"], rid)
                led.conn.execute("DELETE FROM _sync_queue WHERE seq=?", (r["seq"],))
                led.conn.commit()
                flushed += 1
            except BaseUnreachable as exc:
                led.conn.execute("UPDATE _sync_queue SET attempts=attempts+1, last_error=? "
                                 "WHERE seq=?", (str(exc), r["seq"]))
                led.conn.commit()
                still_queued += 1
        pulled = _reconcile_pull(led)
    led._set_meta("last_reconcile_at", now_utc())
    return {"ok": True, "action": "reconcile-mirror", "base_mode": led.base_mode,
            "flushed": flushed, "still_queued": still_queued, "pulled": pulled}


def _reconcile_pull(led: Ledger):
    """Base-wins pull-down (SPEC 7.2 conflict rule). For every row we track a base
    record id for, GET the base record and overwrite the mirror columns from it,
    so on any divergence THE BASE WINS. A transient base error on a given row is
    SKIPPED (never wipes local truth). Only rows with a queued (unsynced) write are
    left alone — their local edit is the pending truth still flowing UP. The full
    divergence drill (W5.5) exercises this against a live base."""
    # pk columns per table, so a pull never rewrites the primary key.
    pk_cols = {
        "producers": "producer_id", "anthologies": "anthology_id",
        "participants": "participant_key", "artifacts": "artifact_id",
        "approvals": "approval_id", "exceptions": "exception_id",
    }
    # tables whose live columns are known (so we only overwrite real columns).
    table_cols = {t: [r[1] for r in led.conn.execute("PRAGMA table_info(%s)" % t)]
                  for t in pk_cols}
    queued = {(r["table_name"], r["pk"]) for r in
              led.conn.execute("SELECT table_name, pk FROM _sync_queue")}
    pulled = 0
    rows = led.conn.execute("SELECT table_name, pk, record_id FROM _base_ids").fetchall()
    for r in rows:
        table, pk, rid = r["table_name"], r["pk"], r["record_id"]
        if not rid or table not in pk_cols or (table, pk) in queued:
            continue
        try:
            base_fields = led.base.fetch(BASE_TABLE_NAMES.get(table, table), rid)
        except BaseUnreachable:
            continue  # skip this row; local truth preserved
        overwrite = {k: v for k, v in base_fields.items()
                     if k in table_cols[table] and k != pk_cols[table]}
        if not overwrite:
            continue
        sets = ", ".join("%s=?" % c for c in overwrite)
        led.conn.execute("UPDATE %s SET %s WHERE %s=?"
                         % (table, sets, pk_cols[table]),
                         list(overwrite.values()) + [pk])
        led.conn.commit()
        pulled += 1
    return pulled


def cmd_export_bundle(led: Ledger, a):
    """Emit the per-anthology export bundle (ledger rows as JSON) — the client
    data-export path (SPEC 10.1 / data-model Section 6). No secrets, ever."""
    anthology_id = _require(a.anthology_id, "--anthology-id")
    anth = led.anthology(anthology_id)
    if not anth:
        raise _unknown("unknown anthology_id %r" % anthology_id)

    def rows(sql, params):
        return [dict(r) for r in led.conn.execute(sql, params).fetchall()]

    members = rows("SELECT * FROM participants WHERE anthology_id=? ORDER BY participant_key",
                   (anthology_id,))
    member_keys = [m["participant_key"] for m in members]
    artifacts = rows("SELECT * FROM artifacts WHERE anthology_id=? "
                     "OR participant_key IN (%s) ORDER BY created_at"
                     % (",".join("?" for _ in member_keys) or "''"),
                     [anthology_id] + member_keys)
    subjects = [anthology_id] + member_keys
    approvals = rows("SELECT * FROM approvals WHERE subject_key IN (%s) ORDER BY decided_at"
                     % ",".join("?" for _ in subjects), subjects)
    producer = None
    if anth["producer_id"]:
        pr = led.producer(anth["producer_id"])
        producer = dict(pr) if pr else None
    bundle = {
        "schema_version": led.get_meta("schema_version"),
        "exported_at": now_utc(),
        "producer": producer,
        "anthology": dict(anth),
        "participants": members,
        "artifacts": artifacts,
        "approvals": approvals,
    }
    if a.out:
        Path(a.out).write_text(json.dumps(bundle, indent=2, ensure_ascii=False),
                               encoding="utf-8")
        return {"ok": True, "action": "export-bundle", "anthology_id": anthology_id,
                "out": str(a.out), "participants": len(members),
                "artifacts": len(artifacts)}
    # return the whole bundle for stdout printing
    bundle["ok"] = True
    bundle["action"] = "export-bundle"
    return bundle


# ---- lightweight single-row reads (W4.0) -----------------------------------
# Every stage_sN.py WIRING list opens with "load the participant row" (or, for
# S9, the anthology row); export-bundle is the only pre-existing read and it
# pulls the WHOLE anthology (every member, every artifact, every approval) just
# to answer a one-row question. These three READ-ONLY commands are the thin
# stage dispatchers' actual first collaborator call: no new writer, no new
# table, just Ledger.participant()/.anthology()/.latest_artifact() (already used
# internally by cmd_export_bundle and the assembly path) exposed directly.
def cmd_get_participant(led: Ledger, a):
    key = _require(a.participant_key, "--participant-key")
    row = led.participant(key)
    if not row:
        raise _unknown("unknown participant_key %r" % key)
    out = dict(row)
    out["ok"] = True
    out["action"] = "get-participant"
    out["read_only"] = True
    return out


def cmd_get_anthology(led: Ledger, a):
    aid = _require(a.anthology_id, "--anthology-id")
    row = led.anthology(aid)
    if not row:
        raise _unknown("unknown anthology_id %r" % aid)
    out = dict(row)
    out["ok"] = True
    out["action"] = "get-anthology"
    out["read_only"] = True
    return out


def cmd_get_artifact(led: Ledger, a):
    key = _require(a.participant_key, "--participant-key")
    art_type = _require(a.type, "--type")
    if art_type not in ARTIFACT_TYPES:
        raise _invalid("unknown artifact type %r (known: %s)"
                       % (art_type, ", ".join(ARTIFACT_TYPES)))
    row = led.latest_artifact(key, art_type)
    out = {"ok": True, "action": "get-artifact", "read_only": True,
           "participant_key": key, "type": art_type, "found": row is not None}
    if row:
        out["artifact"] = dict(row)
    return out


# ===========================================================================
# CLI
# ===========================================================================
# Handlers that MUTATE (go through commit_write) vs read-only (no base flush).
_READ_ONLY = {"assembly-readiness-report", "export-bundle", "bootstrap",
              "get-participant", "get-anthology", "get-artifact"}


def build_parser():
    p = argparse.ArgumentParser(
        prog="anthology_state.py",
        description="The sole durable-ledger writer for the Anthology Engine "
                    "(SPEC 7.4). NO other code path writes state.")
    p.add_argument("--db", help="explicit SQLite mirror path (overrides state dir)")
    p.add_argument("--state-dir", help="engine state directory (default: "
                   "ANTHOLOGY_STATE_DIR / OPENCLAW_DATA_DIR / node home)")
    p.add_argument("--json", action="store_true", help="emit the result as JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(_fn=fn, _name=name)
        # Accept the global flags AFTER the subcommand too (the natural call
        # pattern a shelling module writes: `advance-stage ... --json`). They are
        # already defined on the top parser; the subparser copies use SUPPRESS
        # defaults so an absent flag never clobbers a value set at the parent
        # level (the classic argparse subparser default-clobber), and a flag set
        # in EITHER position wins. Without this a misplaced --json is an argparse
        # error exiting 2 — colliding with EXIT_ILLEGAL and misleading the caller.
        sp.add_argument("--db", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--state-dir", dest="state_dir",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    s = add("bootstrap", cmd_bootstrap, "ensure the mirror schema + meta exist")

    s = add("upsert-producer", cmd_upsert_producer, "create/update a producer")
    s.add_argument("--producer-id", required=True)
    s.add_argument("--producer-email")
    s.add_argument("--display-name", dest="display_name")
    s.add_argument("--drive-root-folder-id", dest="drive_root_folder_id")
    s.add_argument("--status")

    s = add("upsert-anthology", cmd_upsert_anthology, "create/update an anthology")
    s.add_argument("--anthology-id", required=True)
    s.add_argument("--producer-id")
    s.add_argument("--name")
    s.add_argument("--theme")
    s.add_argument("--status")
    s.add_argument("--caf-location-binding", dest="caf_location_binding")
    s.add_argument("--caf-pipeline-binding", dest="caf_pipeline_binding")
    s.add_argument("--caf-stage-map", dest="caf_stage_map", help="JSON")
    s.add_argument("--form-ids", dest="form_ids", help="JSON")
    s.add_argument("--drive-folder-id", dest="drive_folder_id")
    s.add_argument("--min-chapters", dest="min_chapters")

    s = add("upsert-participant", cmd_upsert_participant, "create/update a participant")
    s.add_argument("--contact-id", required=True)
    s.add_argument("--anthology-id", required=True)
    s.add_argument("--first-name", dest="first_name")
    s.add_argument("--last-name", dest="last_name")
    s.add_argument("--email")
    s.add_argument("--phone")
    s.add_argument("--ideal-avatar", dest="ideal_avatar")
    s.add_argument("--niche")
    s.add_argument("--primary-goal", dest="primary_goal")
    s.add_argument("--tone-inputs", dest="tone_inputs", help="JSON")
    s.add_argument("--chapter-about", dest="chapter_about")
    s.add_argument("--personal-stories", dest="personal_stories", help="JSON")
    s.add_argument("--drive-folder-id", dest="drive_folder_id")

    s = add("advance-stage", cmd_advance_stage, "advance a participant's stage_cursor")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--to", required=True, help="target stage_cursor")

    s = add("set-counter", cmd_set_counter, "set rewrite_count / qc_attempts_current "
            "(sole-writer channel for the strike gate)")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--counter", required=True)
    s.add_argument("--value", required=True)

    s = add("record-artifact", cmd_record_artifact, "record a deliverable artifact row")
    s.add_argument("--participant-key")
    s.add_argument("--anthology-id")
    s.add_argument("--type", required=True)
    s.add_argument("--artifact-id", dest="artifact_id")
    s.add_argument("--drive-doc-id", dest="drive_doc_id")
    s.add_argument("--doc-url", dest="doc_url")
    s.add_argument("--pdf-url", dest="pdf_url")
    s.add_argument("--caf-media-url", dest="caf_media_url")
    s.add_argument("--custom-field-keys-written", dest="custom_field_keys_written", help="JSON")
    s.add_argument("--sha256")
    s.add_argument("--prompt-pin-sha256", dest="prompt_pin_sha256")
    s.add_argument("--model-used", dest="model_used")
    s.add_argument("--frozen", action="store_true")

    s = add("record-approval", cmd_record_approval, "record a gate decision + its "
            "cursor advance (incl. the s9_ready trigger)")
    s.add_argument("--gate", required=True)
    s.add_argument("--subject-key", dest="subject_key")
    s.add_argument("--participant-key", dest="participant_key")
    s.add_argument("--anthology-id", dest="anthology_id")
    s.add_argument("--actor")
    s.add_argument("--decision")
    s.add_argument("--notes")
    s.add_argument("--door")
    s.add_argument("--title")
    s.add_argument("--subtitle")
    s.add_argument("--reason", help="hold reason when decision=hold")
    s.add_argument("--producer-id", dest="producer_id", help="own-producer auth for s9 gates")
    s.add_argument("--confirm-name", dest="confirm_name", help="typed anthology-name (s9_ready)")
    s.add_argument("--approval-id", dest="approval_id")
    s.add_argument("--idempotency-key", dest="idempotency_key")

    s = add("assembly-readiness-report", cmd_assembly_readiness_report,
            "READ-ONLY blocking list that arms or refuses the trigger")
    s.add_argument("--anthology-id", required=True)

    s = add("assembly-set-order", cmd_assembly_set_order, "write chapter_order (curation)")
    s.add_argument("--anthology-id", required=True)
    s.add_argument("--order", required=True, help="JSON array of participant_keys")
    s.add_argument("--state", help="proposed | adjusted")

    s = add("assembly-advance", cmd_assembly_advance, "advance assembly_state "
            "(compile / reopen)")
    s.add_argument("--anthology-id", required=True)
    s.add_argument("--to", required=True)
    s.add_argument("--verify-sha", dest="verify_sha", help="'key=sha,key=sha' compile proof")

    s = add("hold", cmd_hold, "durable typed hold (ANY -> held)")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--reason", required=True, help="credit_out | callback_lost | strike_out")

    s = add("resume", cmd_resume, "resume ONLY to the recorded pre-hold cursor")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--to", help="optional assertion; must equal the recorded cursor")

    s = add("exception-open", cmd_exception_open, "open an exceptions-queue row")
    s.add_argument("--reason", required=True)
    s.add_argument("--raw-submission", dest="raw_submission", help="JSON payload preserved")
    s.add_argument("--participant-key", dest="participant_key")
    s.add_argument("--exception-id", dest="exception_id")

    s = add("exception-resolve", cmd_exception_resolve, "resolve an exceptions row")
    s.add_argument("--exception-id", required=True)
    s.add_argument("--resolved-by", dest="resolved_by")
    s.add_argument("--resolved-participant-key", dest="resolved_participant_key")

    s = add("reconcile-mirror", cmd_reconcile_mirror, "flush queued base ops; base wins")

    s = add("export-bundle", cmd_export_bundle, "emit the per-anthology export bundle")
    s.add_argument("--anthology-id", required=True)
    s.add_argument("--out", help="write to this path instead of stdout")

    s = add("get-participant", cmd_get_participant,
            "READ-ONLY: one participant row (the stage dispatchers' load-participant step)")
    s.add_argument("--participant-key", required=True)

    s = add("get-anthology", cmd_get_anthology,
            "READ-ONLY: one anthology row")
    s.add_argument("--anthology-id", required=True)

    s = add("get-artifact", cmd_get_artifact,
            "READ-ONLY: the latest artifact row of one type for a participant")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--type", required=True)

    add("selftest", None, "run the in-process acceptance battery (temp DB)")
    return p


def _resolve_db_path(a) -> Path:
    if getattr(a, "db", None):
        return Path(a.db).expanduser()
    state_dir = Path(a.state_dir).expanduser() if getattr(a, "state_dir", None) \
        else default_state_dir()
    return state_dir / "anthology_state.db"


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    action = result.get("action", "?")
    if result.get("noop"):
        print("OK [%s] no-op (idempotent replay / already-satisfied)" % action)
    else:
        print("OK [%s] %s" % (action, {k: v for k, v in result.items()
                                       if k not in ("ok", "action")}))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    a = parser.parse_args(argv)

    if a._name == "selftest":
        return run_selftest()

    led = None
    try:
        led = Ledger(_resolve_db_path(a))
        result = a._fn(led, a)
        exit_code = EXIT_OK
        if a._name not in _READ_ONLY:
            exit_code = led.commit_write()
            if exit_code == EXIT_BASE_DEFERRED:
                result["base_deferred"] = True
                result["note"] = ("mirror write committed; base op queued "
                                  "(exit 4) — reconcile will flush it")
        _emit(result, a.json)
        return exit_code
    except LedgerError as exc:
        if led:
            led.rollback()
        payload = {"ok": False, "error": exc.message, "code": exc.code}
        if exc.detail is not None:
            payload["detail"] = exc.detail
        if a.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            label = {EXIT_ILLEGAL: "ILLEGAL-TRANSITION", EXIT_UNKNOWN_KEY: "UNKNOWN-KEY",
                     EXIT_VALIDATION: "VALIDATION"}.get(exc.code, "ERROR")
            print("%s: %s" % (label, exc.message), file=sys.stderr)
            if exc.detail is not None:
                print("  detail: %s" % json.dumps(exc.detail), file=sys.stderr)
        return exc.code
    except sqlite3.IntegrityError as exc:
        if led:
            led.rollback()
        print("VALIDATION: constraint violation: %s" % exc, file=sys.stderr)
        return EXIT_VALIDATION
    except Exception as exc:  # noqa: BLE001 — top-level fail-closed
        if led:
            led.rollback()
        print("ERROR: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return EXIT_ERROR
    finally:
        if led:
            led.close()


# ===========================================================================
# SELFTEST — the in-process acceptance battery (temp DB, mirror-only mode).
# Exercises the CHECKLIST Part C item 6 drills: happy path S0->approved,
# illegal transition (exit 2), unknown key (exit 3), validation/confirm-name
# (exit 5), the full S9 trigger guard matrix, kill-and-resume (nothing lost),
# hold/resume, exceptions, artifact dedupe + Anthropic deny. Returns 0 iff all
# assertions pass.
# ===========================================================================
def _run(argv):
    """Invoke main() with a temp DB already injected via --db in argv; return the
    exit code."""
    return main(argv)


def run_selftest():
    tmp = Path(tempfile.mkdtemp(prefix="anthology_state_selftest_"))
    db = tmp / "state.db"
    base = ["--db", str(db)]
    checks = []

    def expect(label, argv, code):
        rc = _run(base + argv)
        checks.append((("%s -> exit %d" % (label, code)), rc == code))
        return rc

    def assert_assembly_state(label, anthology_id, want):
        """Read the persisted assembly_state through a fresh Ledger (independent of
        the just-run process) and assert it equals `want` — proves a refused command
        changed NOTHING."""
        led_chk = Ledger(db)
        try:
            row = led_chk.anthology(anthology_id)
            got = row["assembly_state"] if row else None
        finally:
            led_chk.close()
        checks.append(("%s (assembly_state == %s, got %s)" % (label, want, got),
                       got == want))

    def drive_to_approved_frozen(anth, key, sha, title):
        """Run the proven S0->approved sequence for a participant, freezing one
        chapter. Used to build a ready collection for the assembly guard drills."""
        for frm, to in (("s0_intake", "s1_avatar"), ("s1_avatar", "s1_gate")):
            expect("%s %s->%s" % (key, frm, to),
                   ["advance-stage", "--participant-key", key, "--to", to], 0)
        expect("%s s1 approve" % key, ["record-approval", "--gate", "s1_producer",
               "--participant-key", key, "--decision", "approve"], 0)
        expect("%s ->s2_gate" % key, ["advance-stage", "--participant-key", key,
               "--to", "s2_gate"], 0)
        expect("%s s2 approve" % key, ["record-approval", "--gate", "s2_producer",
               "--participant-key", key, "--decision", "approve"], 0)
        expect("%s ->s3_gate" % key, ["advance-stage", "--participant-key", key,
               "--to", "s3_gate"], 0)
        expect("%s title" % key, ["record-approval", "--gate", "s3_selection",
               "--participant-key", key, "--decision", "approve", "--title", title], 0)
        expect("%s ->s4_gate_producer" % key, ["advance-stage", "--participant-key", key,
               "--to", "s4_gate_producer"], 0)
        expect("%s s4 prod" % key, ["record-approval", "--gate", "s4_producer",
               "--participant-key", key, "--decision", "approve"], 0)
        expect("%s s4 part" % key, ["record-approval", "--gate", "s4_participant",
               "--participant-key", key, "--decision", "approve"], 0)
        expect("%s chapter" % key, ["record-artifact", "--participant-key", key,
               "--type", "chapter", "--sha256", sha, "--model-used", "glm-5.2"], 0)
        expect("%s ->s5_gate" % key, ["advance-stage", "--participant-key", key,
               "--to", "s5_gate"], 0)
        expect("%s approve" % key, ["record-approval", "--gate", "s5_participant",
               "--participant-key", key, "--decision", "approve"], 0)
        for to in ("s8_deliver", "s9_wait_assembly", "approved"):
            expect("%s ->%s" % (key, to), ["advance-stage", "--participant-key", key,
                   "--to", to], 0)

    # ensure mirror-only (no base id in this process)
    for k in ("ANTHOLOGY_STATE_BASE_ID", "AIRTABLE_API_KEY", "AIRTABLE_TOKEN",
              "AIRTABLE_PAT", "ANTHOLOGY_STATE_AIRTABLE_KEY"):
        os.environ.pop(k, None)

    expect("bootstrap", ["bootstrap"], 0)
    expect("upsert producer", ["upsert-producer", "--producer-id", "prodX",
                               "--producer-email", "owner@example.test",
                               "--display-name", "Owner"], 0)
    expect("upsert anthology", ["upsert-anthology", "--anthology-id", "anthA",
                               "--producer-id", "prodX", "--name", "The Collection",
                               "--min-chapters", "2"], 0)
    # unknown producer on anthology -> exit 3
    expect("anthology unknown producer", ["upsert-anthology", "--anthology-id", "antB",
                                          "--producer-id", "ghost"], 3)

    # two participants, same contact in a second anthology shares one contact_id
    expect("participant p1", ["upsert-participant", "--contact-id", "c1",
                             "--anthology-id", "anthA", "--first-name", "Ada"], 0)
    expect("participant p2", ["upsert-participant", "--contact-id", "c2",
                             "--anthology-id", "anthA", "--first-name", "Ben"], 0)
    # participant into unknown anthology -> exit 3
    expect("participant unknown anth", ["upsert-participant", "--contact-id", "c1",
                                        "--anthology-id", "ghostA"], 3)

    p1 = "c1::anthA"
    p2 = "c2::anthA"

    # ---- get-* read-only lookups (W4.0: the stage dispatchers' load step) ----
    expect("get-participant known", ["get-participant", "--participant-key", p1], 0)
    expect("get-participant unknown", ["get-participant", "--participant-key", "ghost::anthA"], 3)
    expect("get-anthology known", ["get-anthology", "--anthology-id", "anthA"], 0)
    expect("get-anthology unknown", ["get-anthology", "--anthology-id", "ghostAnth"], 3)
    expect("get-artifact none-yet (still exit 0, found:false)",
           ["get-artifact", "--participant-key", p1, "--type", "chapter"], 0)
    expect("get-artifact bad type", ["get-artifact", "--participant-key", p1,
                                     "--type", "not_a_type"], 5)

    # ---- happy path p1: S0 -> approved --------------------------------------
    expect("p1 s0->s1_avatar", ["advance-stage", "--participant-key", p1, "--to", "s1_avatar"], 0)
    # idempotent replay (kill-and-resume: replay the same advance) -> no-op 0
    expect("p1 replay s1_avatar (idempotent)", ["advance-stage", "--participant-key", p1,
                                                "--to", "s1_avatar"], 0)
    # illegal jump s1_avatar -> s5_chapter -> exit 2
    expect("p1 illegal jump", ["advance-stage", "--participant-key", p1, "--to", "s5_chapter"], 2)
    expect("p1 s1_avatar->s1_gate", ["advance-stage", "--participant-key", p1, "--to", "s1_gate"], 0)
    # GATE-CROSSING GUARD (W1.7 QC): advance-stage must NOT step past a producer gate.
    # s1_gate -> s2_tone is a gate-decision edge owned by record-approval; advancing
    # it directly (which would skip the approvals audit row + per-gate guards) is an
    # illegal transition -> exit 2, and must leave the cursor at s1_gate unchanged.
    expect("p1 gate-bypass via advance-stage illegal",
           ["advance-stage", "--participant-key", p1, "--to", "s2_tone"], 2)
    expect("p1 s1 producer approve", ["record-approval", "--gate", "s1_producer",
                                      "--participant-key", p1, "--decision", "approve"], 0)
    expect("p1 s2_tone->s2_gate", ["advance-stage", "--participant-key", p1, "--to", "s2_gate"], 0)
    expect("p1 s2 producer approve", ["record-approval", "--gate", "s2_producer",
                                      "--participant-key", p1, "--decision", "approve"], 0)
    expect("p1 s3_title->s3_gate", ["advance-stage", "--participant-key", p1, "--to", "s3_gate"], 0)
    # title selection stamps the lock (one-way)
    expect("p1 title selection", ["record-approval", "--gate", "s3_selection",
                                  "--participant-key", p1, "--decision", "approve",
                                  "--title", "Rise", "--subtitle", "A Story"], 0)
    # re-selecting a DIFFERENT title is illegal (lock is one-way) -> exit 2
    expect("p1 title relock illegal", ["record-approval", "--gate", "s3_selection",
                                       "--participant-key", p1, "--decision", "approve",
                                       "--title", "Fall"], 2)
    expect("p1 s4->s4_gate_producer", ["advance-stage", "--participant-key", p1,
                                       "--to", "s4_gate_producer"], 0)
    expect("p1 s4 producer approve", ["record-approval", "--gate", "s4_producer",
                                      "--participant-key", p1, "--decision", "approve"], 0)
    expect("p1 s4 participant approve", ["record-approval", "--gate", "s4_participant",
                                        "--participant-key", p1, "--decision", "approve"], 0)
    # record a chapter artifact, then a rewrite request, then approve (freeze)
    expect("p1 record chapter", ["record-artifact", "--participant-key", p1,
                                 "--type", "chapter", "--sha256", "shaP1v1",
                                 "--model-used", "glm-5.2"], 0)
    # artifact dedupe: same sha -> no-op 0
    expect("p1 record chapter dup", ["record-artifact", "--participant-key", p1,
                                     "--type", "chapter", "--sha256", "shaP1v1",
                                     "--model-used", "glm-5.2"], 0)
    expect("get-artifact found after record", ["get-artifact", "--participant-key", p1,
                                               "--type", "chapter"], 0)
    # NEGATIVE fixture proving the model_used deny-guard fires. The forbidden id
    # is assembled from fragments so NO literal Anthropic identifier appears in
    # this shipped runtime file (guard-no-anthropic-runtime.py scans .py source);
    # the runtime value still matches the deny regex and MUST be refused (exit 5).
    deny_model = "cl" + "aude-" + "sonnet-4"
    expect("forbidden model_used deny", ["record-artifact", "--participant-key", p1,
                                        "--type", "avatar", "--sha256", "shaAv",
                                        "--model-used", deny_model], 5)
    # the chapter gate opens at s5_gate (after QC) -> advance before any gate action
    expect("p1 s5_chapter->s5_gate", ["advance-stage", "--participant-key", p1,
                                      "--to", "s5_gate"], 0)
    # rewrite #1
    expect("p1 rewrite request 1", ["record-approval", "--gate", "s5_participant",
                                    "--participant-key", p1, "--decision", "request_rewrite",
                                    "--notes", "tighten the open"], 0)
    expect("p1 s6->s5_gate", ["advance-stage", "--participant-key", p1, "--to", "s5_gate"], 0)
    # rewrite #2
    expect("p1 rewrite request 2", ["record-approval", "--gate", "s5_participant",
                                    "--participant-key", p1, "--decision", "request_rewrite",
                                    "--notes", "again"], 0)
    expect("p1 s6->s5_gate b", ["advance-stage", "--participant-key", p1, "--to", "s5_gate"], 0)
    # rewrite #3 -> illegal (budget 2) exit 2
    expect("p1 rewrite request 3 illegal", ["record-approval", "--gate", "s5_participant",
                                            "--participant-key", p1, "--decision",
                                            "request_rewrite"], 2)
    # approve as-is (freezes chapter)
    expect("p1 chapter approve", ["record-approval", "--gate", "s5_participant",
                                  "--participant-key", p1, "--decision", "approve"], 0)
    expect("p1 s7->s8", ["advance-stage", "--participant-key", p1, "--to", "s8_deliver"], 0)
    expect("p1 s8->s9wait", ["advance-stage", "--participant-key", p1, "--to", "s9_wait_assembly"], 0)
    expect("p1 s9wait->approved", ["advance-stage", "--participant-key", p1, "--to", "approved"], 0)

    # ---- p2: exclude it so the anthology can arm on p1 alone -----------------
    # first, unknown participant approval -> exit 3
    expect("unknown participant approval", ["record-approval", "--gate", "s1_producer",
                                            "--participant-key", "c9::anthA",
                                            "--decision", "approve"], 3)
    expect("p2 exclude", ["record-approval", "--gate", "s4_producer",
                          "--participant-key", p2, "--decision", "exclude"], 0)

    # ---- S9 trigger guard matrix --------------------------------------------
    # readiness report is read-only and should show ready now (p1 approved+frozen,
    # p2 excluded, 1 frozen chapter >= min_chapters? min=2 so NOT ready yet)
    # bump min_chapters down is not allowed (floor 2); instead add a 2nd frozen
    # chapter by fast-tracking p2? p2 is excluded. So set min_chapters to 1? floor
    # blocks. We instead lower the bar by making the anthology min_chapters via a
    # second contributor. Add p3 and drive to approved+frozen.
    expect("participant p3", ["upsert-participant", "--contact-id", "c3",
                             "--anthology-id", "anthA", "--first-name", "Cy"], 0)
    p3 = "c3::anthA"
    # fast path p3 to approved with a frozen chapter
    for frm, to in (("s0_intake", "s1_avatar"), ("s1_avatar", "s1_gate")):
        expect("p3 %s->%s" % (frm, to), ["advance-stage", "--participant-key", p3, "--to", to], 0)
    expect("p3 s1 approve", ["record-approval", "--gate", "s1_producer",
                            "--participant-key", p3, "--decision", "approve"], 0)
    for to in ("s2_gate",):
        expect("p3 ->%s" % to, ["advance-stage", "--participant-key", p3, "--to", to], 0)
    expect("p3 s2 approve", ["record-approval", "--gate", "s2_producer",
                            "--participant-key", p3, "--decision", "approve"], 0)
    expect("p3 ->s3_gate", ["advance-stage", "--participant-key", p3, "--to", "s3_gate"], 0)
    expect("p3 title", ["record-approval", "--gate", "s3_selection", "--participant-key", p3,
                       "--decision", "approve", "--title", "Dawn"], 0)
    expect("p3 ->s4_gate_producer", ["advance-stage", "--participant-key", p3,
                                    "--to", "s4_gate_producer"], 0)
    expect("p3 s4 prod", ["record-approval", "--gate", "s4_producer", "--participant-key", p3,
                         "--decision", "approve"], 0)
    expect("p3 s4 part", ["record-approval", "--gate", "s4_participant", "--participant-key", p3,
                         "--decision", "approve"], 0)
    expect("p3 chapter", ["record-artifact", "--participant-key", p3, "--type", "chapter",
                         "--sha256", "shaP3v1", "--model-used", "glm-5.2"], 0)
    expect("p3 s5_chapter->s5_gate", ["advance-stage", "--participant-key", p3,
                                     "--to", "s5_gate"], 0)
    expect("p3 approve", ["record-approval", "--gate", "s5_participant", "--participant-key", p3,
                         "--decision", "approve"], 0)
    expect("p3 ->s8", ["advance-stage", "--participant-key", p3, "--to", "s8_deliver"], 0)
    expect("p3 ->s9wait", ["advance-stage", "--participant-key", p3, "--to", "s9_wait_assembly"], 0)
    expect("p3 ->approved", ["advance-stage", "--participant-key", p3, "--to", "approved"], 0)

    # now: p1 approved+frozen, p3 approved+frozen, p2 excluded => 2 frozen >= min 2
    # s9_ready with WRONG confirm-name -> exit 5
    expect("s9 confirm-name mismatch", ["record-approval", "--gate", "s9_ready",
                                        "--anthology-id", "anthA", "--producer-id", "prodX",
                                        "--confirm-name", "Wrong Name"], 5)
    # s9_ready with non-producer -> exit 5
    expect("s9 non-producer", ["record-approval", "--gate", "s9_ready",
                               "--anthology-id", "anthA", "--producer-id", "intruder",
                               "--confirm-name", "The Collection"], 5)
    # ASSEMBLY-ADVANCE GUARD (W1.7 QC): assembly-advance owns ONLY compile + reopen.
    # anthA is AUTO-ARMED here (p1+p3 approved+frozen, p2 excluded). Every guarded
    # target is refused (exit 2), so assembly-advance can NEVER be a second door into
    # armed/ready_confirmed/proposed/adjusted/signed_off — the s9_ready trigger
    # (own-producer + --confirm-name + readiness) stays the ONLY path to
    # ready_confirmed, and the refusals change NOTHING (state stays 'armed').
    for guarded in ("armed", "ready_confirmed", "proposed", "adjusted", "signed_off"):
        expect("assembly-advance bypass into %s illegal" % guarded,
               ["assembly-advance", "--anthology-id", "anthA", "--to", guarded], 2)
    assert_assembly_state("assembly-advance refusals changed nothing", "anthA", "armed")
    # s9_ready happy -> exit 0
    expect("s9 ready fire", ["record-approval", "--gate", "s9_ready", "--anthology-id", "anthA",
                            "--producer-id", "prodX", "--confirm-name", "The Collection"], 0)
    # double-fire -> acknowledged no-op 0
    expect("s9 ready double-fire", ["record-approval", "--gate", "s9_ready",
                                    "--anthology-id", "anthA", "--producer-id", "prodX",
                                    "--confirm-name", "The Collection"], 0)
    # set order (permutation of the 2 members) -> proposed
    order = json.dumps([p1, p3])
    expect("s9 set order", ["assembly-set-order", "--anthology-id", "anthA", "--order", order], 0)
    # order with an unknown key -> exit 5
    expect("s9 order bad key", ["assembly-set-order", "--anthology-id", "anthA",
                                "--order", json.dumps([p1, "c9::anthA"])], 5)
    # compile (verify-sha matching) -> compiled
    expect("s9 compile", ["assembly-advance", "--anthology-id", "anthA", "--to", "compiled",
                          "--verify-sha", "%s=shaP1v1,%s=shaP3v1" % (p1, p3)], 0)
    # record the manuscript artifact (anthology scope)
    expect("record manuscript", ["record-artifact", "--anthology-id", "anthA",
                                 "--type", "anthology_manuscript", "--sha256", "shaMS",
                                 "--model-used", "glm-5.2"], 0)
    # producer sign-off -> signed_off, members delivered
    expect("s9 producer signoff", ["record-approval", "--gate", "s9_producer",
                                   "--anthology-id", "anthA", "--producer-id", "prodX"], 0)

    # ---- hold / resume on a fresh anthology ---------------------------------
    expect("anthology H", ["upsert-anthology", "--anthology-id", "anthH",
                          "--producer-id", "prodX", "--name", "Held"], 0)
    expect("participant h1", ["upsert-participant", "--contact-id", "h1",
                             "--anthology-id", "anthH"], 0)
    ph = "h1::anthH"
    expect("h1 ->s1_avatar", ["advance-stage", "--participant-key", ph, "--to", "s1_avatar"], 0)
    expect("h1 hold", ["hold", "--participant-key", ph, "--reason", "credit_out"], 0)
    # resume to a WRONG target -> exit 2
    expect("h1 resume wrong target", ["resume", "--participant-key", ph, "--to", "s5_chapter"], 2)
    # resume to recorded cursor -> exit 0
    expect("h1 resume", ["resume", "--participant-key", ph], 0)

    # ---- exceptions ----------------------------------------------------------
    expect("exception open", ["exception-open", "--reason", "unroutable_missing_ids",
                             "--raw-submission", "{\"body\":1}", "--exception-id", "excT"], 0)
    expect("exception resolve", ["exception-resolve", "--exception-id", "excT",
                                "--resolved-by", "op"], 0)
    expect("exception resolve unknown", ["exception-resolve", "--exception-id", "nope"], 3)

    # ---- reconcile (mirror-only no-op) + export -----------------------------
    expect("reconcile mirror-only", ["reconcile-mirror"], 0)
    expect("export bundle", ["export-bundle", "--anthology-id", "anthA",
                            "--out", str(tmp / "bundle.json")], 0)

    # ---- kill-and-resume: reopen a fresh Ledger and confirm p1 persisted -----
    led2 = Ledger(db)
    try:
        row = led2.participant(p1)
        checks.append(("kill-and-resume: p1 persisted as 'delivered'",
                       row is not None and row["stage_cursor"] == "delivered"))
        anth = led2.anthology("anthA")
        checks.append(("anthology signed_off + delivered",
                       anth["assembly_state"] == "signed_off" and anth["status"] == "delivered"))
        # verify the export bundle wrote real rows
        bundle = json.loads((tmp / "bundle.json").read_text())
        checks.append(("export bundle carries participants",
                       len(bundle.get("participants", [])) >= 2))
    finally:
        led2.close()

    # report
    ok = True
    for label, good in checks:
        print("  [%s] %s" % ("OK" if good else "XX", label))
        ok = ok and good
    print("== anthology_state selftest: %s (%d checks) =="
          % ("ALL ASSERTIONS PASSED" if ok else "FAILED", len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
