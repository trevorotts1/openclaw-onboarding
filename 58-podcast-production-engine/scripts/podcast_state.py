#!/usr/bin/env python3
# podcast_state.py
#
# THE SOLE WRITER of the Podcast Production Engine state database.
#
# Design source: design/dashboard-design.md Section 5 (the persistence layer)
# plus PRD Section 6.5 (the reconciliation note: the webhook file ledger and this
# SQLite database are complementary layers of one state system; this module bridges
# them and keeps them in lockstep, one writer).
#
# Contract (dashboard-design D3, D4, Section 5.4):
#   - This is the ONLY code that opens podcast-engine.db read/write. Every pipeline
#     step calls it. The Command Center dashboard opens the same file read-only.
#   - Database file: PODCAST_DB_PATH env override, else
#     ~/.openclaw/podcast-engine/podcast-engine.db (SQLite, WAL, foreign_keys ON).
#     File mode 0600, directory 0700, owned by the OpenClaw runtime user.
#   - The legal-transition matrix (Section 5.2) is enforced here; illegal
#     transitions raise and exit non-zero.
#   - Every state change appends a podcast_job_events row automatically and
#     maintains updated_at.
#   - Error strings and notes pass through a redaction filter that never lets a
#     secret value or PII shape reach storage (labels and locations only).
#   - The writer refuses to write when podcast_client_state.active = 0 (churn).
#
# Fleet rules honored by this file:
#   - No build-house model provider id of any kind anywhere: this is a pure state
#     writer; it calls no model at all, so the no-runtime-model-provider guard has
#     nothing to flag. Runtime content routing (Ollama Cloud Kimi, GLM, OpenRouter,
#     Gemini) lives in the pipeline modules, never here.
#   - No em dash characters. No triple backtick fences in any produced output.
#   - Never prints a stored secret value. The single intentional secret emission is
#     `token mint`, which returns a freshly generated raw token exactly once (per
#     dashboard-design Section 11.2) and never persists it (hash only is stored).
#   - Move in silence: zero client-facing messages. Operator/machine output only.
#
# Stdlib only (sqlite3, argparse, hashlib, json, os, re, secrets, sys, datetime).
# Keep the stage taxonomy, status enum, and label map STABLE: the dashboard slice
# depends on this schema and vocabulary.

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants: paths
# ---------------------------------------------------------------------------

DEFAULT_DB_REL = os.path.join(".openclaw", "podcast-engine", "podcast-engine.db")
DEFAULT_LEDGER_REL = os.path.join(".openclaw", "state", "podcast-engine", "intake-ledger")
DEFAULT_JOBINDEX_REL = os.path.join(".openclaw", "state", "podcast-engine", "job-index")

# U035: key name for the integrity checksum embedded in each roster/ledger record.
# SHA-256 of the canonical JSON (sorted keys, no whitespace) excluding this field.
ROSTER_CHECKSUM_KEY = "_checksum"

QUEUE_HOLD_DAYS = 60          # credit-out queue maximum hold (SPEC credit_out_queue)
PII_TOMBSTONE_DAYS = 90       # scrub PII this long after the terminal event (Section 10.2)


def _home() -> str:
    return os.path.expanduser("~")


def resolve_db_path(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.environ.get("PODCAST_DB_PATH")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(_home(), DEFAULT_DB_REL)


def resolve_ledger_dir(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.environ.get("PODCAST_LEDGER_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(_home(), DEFAULT_LEDGER_REL)


def resolve_jobindex_dir() -> str:
    env = os.environ.get("PODCAST_JOBINDEX_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(_home(), DEFAULT_JOBINDEX_REL)


# ---------------------------------------------------------------------------
# Stage taxonomy (BINDING, keep stable; dashboard-design Section 5.2 and 7.2)
# ---------------------------------------------------------------------------

# Linear forward pipeline order (received ... complete). Index position powers the
# dashboard progress meter (9 segments).
FORWARD_ORDER = [
    "received",
    "researching",
    "writing",
    "in_qc",
    "generating_art",
    "producing_audio",
    "publishing",
    "enrolling",
    "complete",
]

# Holding / terminal states outside the linear path.
HOLDING_STATES = {"queued_credit_out"}
TERMINAL_STATES = {"complete", "failed"}

STATUS_SET = set(FORWARD_ORDER) | HOLDING_STATES | {"failed"}

# Client-facing labels (dashboard-design Section 7.2). The dashboard renders these;
# duplicated here so the writer can emit friendly machine output and so the map has
# a single canonical home. Client view never sees the raw status.
CLIENT_LABEL = {
    "received": "Received",
    "researching": "Researching",
    "writing": "Writing",
    "in_qc": "Quality review",
    "generating_art": "Creating artwork",
    "producing_audio": "Producing audio",
    "publishing": "Publishing",
    "enrolling": "Finalizing",
    "complete": "Live",
    "queued_credit_out": "On hold",
    "failed": "Needs attention",
}

# queue_state enum (Section 5.1)
QUEUE_STATES = {"none", "held", "resumed", "aged_out"}

# Services that can deplete mid-run and push a job to the credit-out queue.
QUEUE_SERVICES = {"kie_ai", "ollama_cloud", "openrouter", "fish_audio"}

# SQLite status -> intake-ledger state vocabulary (webhook-design Section 3.2).
# The ledger uses short names for three stages (qc/art/audio); everything else
# matches. queue_state=aged_out overrides to the ledger 'aged_out' state.
STATUS_TO_LEDGER_STATE = {
    "received": "received",
    "researching": "researching",
    "writing": "writing",
    "in_qc": "qc",
    "generating_art": "art",
    "producing_audio": "audio",
    "publishing": "publishing",
    "enrolling": "enrolling",
    "complete": "complete",
    "queued_credit_out": "queued_credit_out",
    "failed": "failed",
}

# Output columns writable via the `output` subcommand (Section 5.1 outputs block).
# Whitelist: nothing else may be set through `output`. Values coerced by kind.
OUTPUT_COLUMNS = {
    "episode_title": "text",
    "episode_description": "text",
    "episode_number": "int",
    "podbean_permalink": "text",
    "episode_package_url": "text",
    "speech_script_url": "text",
    "book_teaser_url": "text",
    "mp3_media_url": "text",
    "cover_image_url": "text",
    "spoken_word_count": "int",
    "runtime_minutes": "real",
    "publish_timestamp": "text",
    "writing_model": "text",
    "research_tool": "text",
}

PII_COLUMNS = [
    "submitter_first_name",
    "submitter_last_name",
    "submitter_email",
    "submitter_phone",
]


class TransitionError(Exception):
    """Raised on an illegal state transition. Exit code 3."""


class MissingRequiredOutputError(TransitionError):
    """Raised (exit code 3, a blocked transition) when a forward advance would
    leave a producing stage whose required output artifact(s) were never set.
    A stage may not advance on a missing deliverable; the only escapes are to
    set the output first (via `output`) or to pass --force-waiver (audited)."""


class WriterRefused(Exception):
    """Raised when the client is deactivated (active = 0). Exit code 4."""


class UsageError(Exception):
    """Raised on bad arguments / missing rows. Exit code 2."""


# ---------------------------------------------------------------------------
# Time helpers (ISO 8601 UTC, matching datetime('now') SQLite text shape)
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    # 'YYYY-MM-DD HH:MM:SS' to match SQLite datetime('now') and enable text
    # comparison against queue_deadline and stored timestamps.
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# ULID (Crockford base32, 26 chars, time-sortable). Stdlib only.
# ---------------------------------------------------------------------------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid() -> str:
    ts = int(time.time() * 1000) & ((1 << 48) - 1)
    rnd = secrets.randbits(80)
    value = (ts << 80) | rnd
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_job_id() -> str:
    return "pj_" + ulid()


def new_token_id() -> str:
    return "pdt_" + ulid()


# ---------------------------------------------------------------------------
# Redaction filter (Section 5.4). Never let a secret value or PII shape reach
# storage. Applied to every stored free-text field (last_error, event note).
# Order matters: most specific patterns first.
# ---------------------------------------------------------------------------

_REDACTIONS = [
    # Authorization / bearer headers
    (re.compile(r"(?i)\b(authorization|bearer)\b\s*[:=]?\s*\S+"), r"\1 [redacted]"),
    # Convert and Flow private integration token (pit- prefix, the PIT)
    (re.compile(r"\bpit-[A-Za-z0-9._\-]{8,}"), "[redacted-token]"),
    # Dashboard raw token: pdt_<slug>_<32 hex>. Leaves bare pdt_<ULID> token_ids alone.
    (re.compile(r"\bpdt_[a-z0-9][a-z0-9\-]*_[A-Fa-f0-9]{32}\b"), "[redacted-token]"),
    # Common provider key prefixes (OpenAI-style sk-, GitHub ghp_/pat, generic key_)
    (re.compile(r"(?i)\b(sk|rk|ghp|gho|pat|key|apikey|api_key)[-_][A-Za-z0-9]{12,}"), "[redacted-token]"),
    # key=value / key: value where the KEY looks secret
    (re.compile(r"(?i)\b(secret|token|password|passwd|api[_-]?key|client[_-]?secret|access[_-]?key)\b\s*[:=]\s*\S+"),
     r"\1=[redacted]"),
    # Email addresses (PII)
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[redacted-email]"),
    # Phone numbers: 10+ digits, allowing separators. Guarded so short cost/id
    # numbers are not swallowed.
    (re.compile(r"(?<!\w)\+?\d[\d\s().\-]{8,}\d(?!\w)"), "[redacted-phone]"),
    # Long hex runs (>= 32) are almost always hashes / keys.
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), "[redacted-hex]"),
    # Long opaque token-like runs (>= 40 base64/url chars).
    (re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"), "[redacted-secret]"),
]


def redact(text: str | None) -> str | None:
    if text is None:
        return None
    out = str(text)
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out


# ---------------------------------------------------------------------------
# Schema (dashboard-design Section 5.1, verbatim structure)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS podcast_jobs (
  job_id            TEXT PRIMARY KEY,
  client_id         TEXT NOT NULL,
  location_id       TEXT NOT NULL,
  contact_id        TEXT NOT NULL,
  submission_fingerprint TEXT NOT NULL,

  mode              TEXT NOT NULL CHECK (mode IN ('personal_podcast_style','interview_style_podcast')),
  style             TEXT NOT NULL CHECK (style IN ('counter_intuitive','vulnerable','provocative','passionate')),
  show_name         TEXT,
  host_name         TEXT,

  submitter_first_name TEXT,
  submitter_last_name  TEXT,
  submitter_email      TEXT,
  submitter_phone      TEXT,

  status            TEXT NOT NULL DEFAULT 'received' CHECK (status IN (
                      'received','researching','writing','in_qc','generating_art',
                      'producing_audio','publishing','enrolling','complete',
                      'failed','queued_credit_out')),
  resume_stage      TEXT,
  attempt_count     INTEGER NOT NULL DEFAULT 0,
  failed_step       TEXT,
  last_error        TEXT,

  queue_state       TEXT NOT NULL DEFAULT 'none' CHECK (queue_state IN
                      ('none','held','resumed','aged_out')),
  queued_at         TEXT,
  queued_service    TEXT,
  queue_deadline    TEXT,
  aged_out_at       TEXT,

  cost_accrued_usd  REAL NOT NULL DEFAULT 0,
  writing_model     TEXT,
  research_tool     TEXT,

  episode_title       TEXT,
  episode_description TEXT,
  episode_number      INTEGER,
  podbean_permalink   TEXT,
  episode_package_url TEXT,
  speech_script_url   TEXT,
  book_teaser_url     TEXT,
  mp3_media_url       TEXT,
  cover_image_url     TEXT,
  spoken_word_count   INTEGER,
  runtime_minutes     REAL,
  publish_timestamp   TEXT,

  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at      TEXT,
  pii_scrubbed_at   TEXT,

  UNIQUE (client_id, submission_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_pj_client_status  ON podcast_jobs(client_id, status);
CREATE INDEX IF NOT EXISTS idx_pj_queue          ON podcast_jobs(queue_state, queue_deadline)
  WHERE queue_state = 'held';
CREATE INDEX IF NOT EXISTS idx_pj_contact        ON podcast_jobs(contact_id);
CREATE INDEX IF NOT EXISTS idx_pj_created        ON podcast_jobs(client_id, created_at DESC);

CREATE TABLE IF NOT EXISTS podcast_job_events (
  event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id      TEXT NOT NULL REFERENCES podcast_jobs(job_id) ON DELETE CASCADE,
  at          TEXT NOT NULL DEFAULT (datetime('now')),
  from_status TEXT,
  to_status   TEXT,
  note        TEXT,
  cost_delta_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pje_job ON podcast_job_events(job_id, at);

CREATE TABLE IF NOT EXISTS podcast_job_payloads (
  job_id       TEXT PRIMARY KEY REFERENCES podcast_jobs(job_id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL,
  partial_state_json TEXT,
  stored_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS podcast_dashboard_tokens (
  token_id     TEXT PRIMARY KEY,
  client_id    TEXT NOT NULL,
  token_hash   TEXT NOT NULL UNIQUE,
  label        TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at TEXT,
  revoked_at   TEXT,
  revoked_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_pdt_client ON podcast_dashboard_tokens(client_id);

CREATE TABLE IF NOT EXISTS podcast_client_state (
  client_id   TEXT PRIMARY KEY,
  active      INTEGER NOT NULL DEFAULT 1,
  deactivated_at TEXT,
  note        TEXT
);
"""


# ---------------------------------------------------------------------------
# Database connection + schema bootstrap
# ---------------------------------------------------------------------------

def ensure_dirs(db_path: str) -> None:
    d = os.path.dirname(db_path)
    if d and not os.path.isdir(d):
        os.makedirs(d, mode=0o700, exist_ok=True)
    if d:
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass


def connect(db_path: str) -> sqlite3.Connection:
    ensure_dirs(db_path)
    fresh = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.executescript(SCHEMA)
    if fresh and os.path.exists(db_path):
        try:
            os.chmod(db_path, 0o600)
        except OSError:
            pass
    return conn


def _load_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM podcast_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise UsageError(f"no such job_id: {job_id}")
    return row


def _client_active(conn: sqlite3.Connection, client_id: str) -> bool:
    row = conn.execute(
        "SELECT active FROM podcast_client_state WHERE client_id = ?", (client_id,)
    ).fetchone()
    if row is None:
        return True  # absent row = never deactivated = active by default
    return int(row["active"]) == 1


def _assert_active(conn: sqlite3.Connection, client_id: str) -> None:
    if not _client_active(conn, client_id):
        raise WriterRefused(
            f"client '{client_id}' is deactivated (podcast_client_state.active = 0); "
            "writer refuses new state changes"
        )


# ---------------------------------------------------------------------------
# Transition matrix (dashboard-design Section 5.2)
# ---------------------------------------------------------------------------

def _forward_next(status: str) -> str | None:
    try:
        i = FORWARD_ORDER.index(status)
    except ValueError:
        return None
    if i + 1 < len(FORWARD_ORDER):
        return FORWARD_ORDER[i + 1]
    return None


# ---------------------------------------------------------------------------
# Required-outputs gate (preset/mode-aware). A forward advance may not LEAVE a
# producing stage until the artifact that stage exists to create has been
# recorded, so a job can never reach 'complete' (or slip past publishing) with
# no stored audio and no Podbean permalink. The requirement set is resolved per
# job from its preset flags, so document-only presets (season_strategy) and
# non-publishing presets (episode_asset_pack) are never falsely blocked.
# ---------------------------------------------------------------------------

# The four output-type presets and the mode -> default-preset derivation
# (config/presets.json is authoritative; these mirror it so the gate is
# self-contained and hermetic when the config is not on the path).
PRESET_ENUM = ("interview", "solo", "season_strategy", "episode_asset_pack")
MODE_DEFAULT_PRESET = {
    "interview_style_podcast": "interview",
    "personal_podcast_style": "solo",
}

# Fallback preset flag table (mirrors config/presets.json flags). Only the flags
# the gate reads are load-bearing; config values win when the file is present.
BUILTIN_PRESET_FLAGS = {
    "interview": {"research_stage": True, "render_audio": True,
                  "publish_podbean": True, "book_teaser": True, "store_media": True},
    "solo": {"research_stage": True, "render_audio": True,
             "publish_podbean": True, "book_teaser": False, "store_media": True},
    "season_strategy": {"research_stage": True, "render_audio": False,
                        "publish_podbean": False, "book_teaser": False, "store_media": False},
    "episode_asset_pack": {"research_stage": False, "render_audio": False,
                           "publish_podbean": False,
                           "book_teaser": "conditional_interview_source",
                           "store_media": True},
}

# (from_status, to_status) -> [(output_column, gate)]. A requirement applies only
# when its GATE is satisfied by the job's preset flags, so the same map is correct
# for every preset. Gates:
#   produces_media  - any of render_audio/publish_podbean/store_media (a real
#                     producing run, i.e. NOT the document-only season_strategy)
#   store_media     - the stored media package is a deliverable of this preset
#   publish_podbean - this preset publishes to Podbean (so a permalink is owed)
#   book_teaser     - strictly True (the conditional string never HARD-requires it)
REQUIRED_OUTPUTS_BY_TRANSITION = {
    # Leaving art (Step 10 cover): the cover image must exist.
    ("generating_art", "producing_audio"): [
        ("cover_image_url", "produces_media"),
    ],
    # Leaving publishing (Steps 12-16: documents, media upload, Podbean, link-back):
    # the stored audio and the Podbean permalink must exist.
    ("publishing", "enrolling"): [
        ("mp3_media_url", "store_media"),
        ("episode_package_url", "store_media"),
        ("podbean_permalink", "publish_podbean"),
        ("book_teaser_url", "book_teaser"),
    ],
    # Terminal backstop: no job reaches 'complete' missing its core deliverables.
    ("enrolling", "complete"): [
        ("mp3_media_url", "store_media"),
        ("episode_package_url", "store_media"),
        ("podbean_permalink", "publish_podbean"),
        ("cover_image_url", "produces_media"),
        ("episode_title", "produces_media"),
    ],
}

_PRESET_FLAGS_CACHE = None


def _preset_flags_map() -> dict:
    """config/presets.json flags (authoritative) merged over the builtin fallback.
    Never raises; a missing/broken config quietly falls back to the builtin table."""
    global _PRESET_FLAGS_CACHE
    if _PRESET_FLAGS_CACHE is not None:
        return _PRESET_FLAGS_CACHE
    flags_map = {name: dict(fl) for name, fl in BUILTIN_PRESET_FLAGS.items()}
    try:
        skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = os.path.join(skill_root, "config", "presets.json")
        with open(cfg, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for name, spec in (data.get("presets") or {}).items():
            fl = spec.get("flags")
            if isinstance(fl, dict):
                flags_map[name] = fl
    except Exception:
        pass
    _PRESET_FLAGS_CACHE = flags_map
    return flags_map


def preset_flags(preset: str | None) -> dict:
    if not preset:
        return {}
    return _preset_flags_map().get(preset, {})


def resolve_preset(conn: sqlite3.Connection | None, job_id: str, mode: str) -> str | None:
    """Resolve a job's preset: an explicit, in-enum preset from the stored intake
    payload wins; otherwise derive the default from the production mode. Never
    raises (a producing mode always resolves to a full-deliverable default)."""
    preset = None
    if conn is not None:
        try:
            r = conn.execute(
                "SELECT payload_json FROM podcast_job_payloads WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if r and r[0]:
                payload = json.loads(r[0])
                cand = payload.get("preset") if isinstance(payload, dict) else None
                if cand in PRESET_ENUM:
                    preset = cand
        except Exception:
            preset = None
    if not preset:
        preset = MODE_DEFAULT_PRESET.get(mode)
    return preset


def _gate_satisfied(gate: str, flags: dict) -> bool:
    if gate == "produces_media":
        return any(bool(flags.get(k)) for k in
                   ("render_audio", "publish_podbean", "store_media"))
    if gate in ("store_media", "publish_podbean", "render_audio"):
        return flags.get(gate) is True
    if gate == "book_teaser":
        # Strict True only; a conditional string ("conditional_interview_source")
        # is decided per-run and must never HARD-block the pipeline.
        return flags.get("book_teaser") is True
    return False


def required_outputs_for(frm: str, to_status: str, flags: dict) -> list:
    reqs = REQUIRED_OUTPUTS_BY_TRANSITION.get((frm, to_status), [])
    return [col for (col, gate) in reqs if _gate_satisfied(gate, flags)]


def missing_required_outputs(row: sqlite3.Row, frm: str, to_status: str,
                             flags: dict) -> list:
    """Output columns that this (frm -> to_status) transition requires for the
    resolved preset but that are unset (NULL or empty) on the row."""
    cols = set(row.keys())
    missing = []
    for col in required_outputs_for(frm, to_status, flags):
        val = row[col] if col in cols else None
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(col)
    return missing


def check_transition(row: sqlite3.Row, to_status: str, preset: str | None = None,
                     waiver: bool = False) -> None:
    """Raise TransitionError if row.status -> to_status is not legal.

    Legal set (Section 5.2):
      - Forward adjacency along FORWARD_ORDER.
      - QC loop: in_qc -> writing (revision) while attempt_count < 3.
      - Any non-terminal stage -> queued_credit_out.
      - queued_credit_out -> resume_stage (via `resume`) or -> failed (aged out / fail).
      - Any stage -> failed on unrecoverable error.

    A legal forward advance is ADDITIONALLY gated on the required-outputs map:
    the producing stage being left must have recorded its deliverable artifact(s)
    for the job's (preset-resolved) flags, unless `waiver` is set. `preset`
    defaults to the mode default when omitted; hold/resume/fail/QC-loop
    transitions never touch outputs (they take the early returns below)."""
    frm = row["status"]

    if to_status not in STATUS_SET:
        raise TransitionError(f"unknown target status: {to_status}")

    if frm in TERMINAL_STATES:
        raise TransitionError(
            f"'{frm}' is terminal; re-dispatch happens through the engine, not this writer"
        )

    # Any stage -> failed is always permitted (unrecoverable error / three-strike).
    if to_status == "failed":
        return

    # Any non-terminal stage -> queued_credit_out (hold). Use `hold`, not `advance`.
    if to_status == "queued_credit_out":
        if frm == "queued_credit_out":
            raise TransitionError("already held")
        return

    # Leaving the hold: only to the recorded resume_stage. Use `resume`, not `advance`.
    if frm == "queued_credit_out":
        target = row["resume_stage"]
        if not target:
            raise TransitionError("held job has no resume_stage recorded")
        if to_status != target:
            raise TransitionError(
                f"held job may only resume to its resume_stage '{target}', not '{to_status}'"
            )
        return

    # QC revision loop.
    if frm == "in_qc" and to_status == "writing":
        if int(row["attempt_count"]) >= 3:
            raise TransitionError(
                "three-strike cap reached (attempt_count >= 3); the only legal exit "
                "from in_qc is 'failed'"
            )
        return

    # Forward adjacency.
    if to_status == _forward_next(frm):
        if preset is None:
            preset = MODE_DEFAULT_PRESET.get(row["mode"])
        missing = missing_required_outputs(row, frm, to_status, preset_flags(preset))
        if missing and not waiver:
            raise MissingRequiredOutputError(
                f"cannot advance {frm} -> {to_status}: preset "
                f"'{preset}' requires output(s) not yet recorded: {', '.join(missing)}. "
                f"Set them with `output` first, or pass --force-waiver to override "
                f"(the waiver is written to the job event log)."
            )
        return

    raise TransitionError(f"illegal transition: {frm} -> {to_status}")


# ---------------------------------------------------------------------------
# Event append + ledger bridge
# ---------------------------------------------------------------------------

def _append_event(conn, job_id, from_status, to_status, note, cost_delta=0.0):
    conn.execute(
        "INSERT INTO podcast_job_events (job_id, at, from_status, to_status, note, cost_delta_usd) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, iso(now_utc()), from_status, to_status, redact(note), float(cost_delta or 0.0)),
    )


def _touch(conn, job_id):
    conn.execute("UPDATE podcast_jobs SET updated_at = ? WHERE job_id = ?", (iso(now_utc()), job_id))


def _jobindex_path(job_id: str) -> str:
    return os.path.join(resolve_jobindex_dir(), job_id + ".jobkey")


def _link_ledger(job_id: str, job_key: str, ledger_dir: str) -> None:
    """Record the job_id <-> job_key linkage so later mutations can find the ledger
    file to keep it in lockstep, without adding a column to the fixed schema."""
    idx_dir = resolve_jobindex_dir()
    os.makedirs(idx_dir, mode=0o700, exist_ok=True)
    payload = {"job_key": job_key, "ledger_dir": ledger_dir}
    _atomic_write(_jobindex_path(job_id), json.dumps(payload))


class LedgerLinkageError(Exception):
    """The job index EXISTS but its ledger linkage cannot be resolved.

    T0-22: this used to be indistinguishable from "no ledger is configured".
    Both returned None, `_sync_ledger` returned immediately, no warning was
    emitted, and the advance reported success — while the intake ledger, which
    is the atomic-claim mechanism, was never updated. A job that never had an
    index is a legitimate no-op; a job whose index is present but malformed,
    unreadable, or missing its job_key is a BROKEN LINKAGE and must be loud."""


def _resolve_ledger_file(job_id: str) -> str | None:
    """Return the ledger path, or None when no ledger is configured for this job.

    Raises LedgerLinkageError when the linkage exists but is broken."""
    idx = _jobindex_path(job_id)
    if not os.path.exists(idx):
        # Not configured: this job never came through the webhook intake layer.
        return None
    try:
        with open(idx, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LedgerLinkageError(
            f"job index {idx} exists but could not be read or parsed: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise LedgerLinkageError(
            f"job index {idx} exists but does not contain an object"
        )
    job_key = data.get("job_key")
    if not job_key:
        raise LedgerLinkageError(
            f"job index {idx} exists but carries no job_key; the ledger record "
            f"for this job cannot be located"
        )
    ledger_dir = data.get("ledger_dir") or resolve_ledger_dir()
    return os.path.join(ledger_dir, job_key + ".json")


def _atomic_write(path: str, text: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, mode=0o700, exist_ok=True)
    tmp = path + ".tmp." + secrets.token_hex(6)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def verify_checksum(raw: str) -> None:
    """U035: Verify the integrity checksum embedded in a roster/ledger record.
    Raises ValueError if the checksum is present and does not match.
    Pre-U035 records without a _checksum field pass silently.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("ledger record is not valid JSON")
    if not isinstance(data, dict):
        raise ValueError("ledger record is not a JSON object")
    cs = data.get(ROSTER_CHECKSUM_KEY)
    if cs is None:
        return
    obj = {k: v for k, v in data.items() if k != ROSTER_CHECKSUM_KEY}
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(cs, actual):
        raise ValueError(
            f"ledger checksum MISMATCH: expected {cs[:16]}... got {actual[:16]}..."
        )


def _sync_ledger(job_id: str, status: str, queue_state: str) -> str:
    """Mirror the SQLite status onto the intake-ledger record the webhook layer
    created. SQLite is the queryable source of truth; the ledger is the atomic-claim
    mechanism. Read-modify-write preserves fields the webhook layer owns.

    Returns one of:
      "not_configured" — no job index for this job; nothing to mirror (a no-op the
                         skill documents, e.g. a job that never came through the
                         webhook intake layer);
      "synced"         — the ledger record was written;
      "broken"         — the linkage exists but could not be resolved or written.

    T0-22: every one of those three used to be an unconditional `return None`,
    so a broken linkage produced no update, no warning, and an advance that
    reported success. The caller now consumes this value."""
    try:
        ledger_file = _resolve_ledger_file(job_id)
    except LedgerLinkageError as exc:
        sys.stderr.write(f"warning: ledger linkage broken for {job_id}: {exc}\n")
        return "broken"
    if not ledger_file:
        return "not_configured"
    if queue_state == "aged_out":
        ledger_state = "aged_out"
    else:
        ledger_state = STATUS_TO_LEDGER_STATE.get(status, status)
    try:
        record = {}
        if os.path.exists(ledger_file):
            with open(ledger_file, "r", encoding="utf-8") as fh:
                raw = fh.read()
            # U035: verify the integrity checksum before trusting the record
            # contents. A corrupt or truncated file is detected here.
            record = json.loads(raw)
            if isinstance(record, dict) and ROSTER_CHECKSUM_KEY in record:
                verify_checksum(raw)
        record["state"] = ledger_state
        record["updated_at"] = iso(now_utc())
        record["sqlite_job_id"] = job_id
        # U035: embed an integrity checksum so truncation / corruption is
        # detected on the next read. Drop a pre-existing _checksum so the
        # compute is of content only.
        record.pop(ROSTER_CHECKSUM_KEY, None)
        raw_for_checksum = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        record[ROSTER_CHECKSUM_KEY] = hashlib.sha256(raw_for_checksum.encode("utf-8")).hexdigest()
        _atomic_write(ledger_file, json.dumps(record, indent=2))
    except (OSError, ValueError) as exc:
        sys.stderr.write(
            f"warning: ledger sync FAILED for {job_id} at {ledger_file}: {exc}\n"
        )
        return "broken"
    return "synced"


# ---------------------------------------------------------------------------
# Fingerprint (Section 5.1: sha256 of contact_id + style + q1..qN answers)
# ---------------------------------------------------------------------------

def compute_fingerprint(contact_id: str, style: str, payload: dict) -> str:
    parts = [str(contact_id or ""), str(style or "")]
    # Canonical answer fields, in order. Missing answers contribute empty strings so
    # the same submission always hashes identically.
    for i in range(1, 11):
        key = f"q{i}_answer"
        val = payload.get(key)
        if val is None and "answers" in payload and isinstance(payload["answers"], dict):
            val = payload["answers"].get(key)
        parts.append(_norm(val))
    parts.append(_norm(payload.get("additional_info")))
    blob = "\n".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip().lower()


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def cmd_create(conn, args):
    if not os.path.exists(args.payload_file):
        raise UsageError(f"payload file not found: {args.payload_file}")
    with open(args.payload_file, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    _assert_active(conn, args.client_id)

    # SK2-14: the webhook layer already computed the authoritative canonical
    # job_key over the SUPERSET of submission fields (webhook/job_key.HASH_FIELDS).
    # Key THIS SQLite dedup off that SAME job_key so the two idempotency layers can
    # never disagree. Previously this layer hashed a NARROWER field set
    # (contact_id + style + q1..q10 + additional_info), so a submission the webhook
    # treats as NEW (e.g. differs only in transparency_answer / show_name / target
    # runtime — fields the webhook hashes but the local fingerprint ignored) would
    # be seen here as a duplicate and NO episode would ever be created. Keying off
    # the webhook job_key closes that never-create/drop hole. When no job_key is
    # supplied (standalone CLI use, no webhook) we fall back to the local content
    # fingerprint so create still works.
    job_key = (args.job_key or "").strip()
    fingerprint = job_key if job_key else compute_fingerprint(args.contact_id, args.style, payload)

    # Idempotency: same (client_id, submission_fingerprint) never runs twice.
    existing = conn.execute(
        "SELECT job_id FROM podcast_jobs WHERE client_id = ? AND submission_fingerprint = ?",
        (args.client_id, fingerprint),
    ).fetchone()
    if existing:
        job_id = existing["job_id"]
        _append_event(conn, job_id, None, None, "duplicate submission (idempotent no-op)")
        _touch(conn, job_id)
        if args.job_key:
            _link_ledger(job_id, args.job_key, resolve_ledger_dir(args.ledger_dir))
            _sync_ledger(job_id, _load_job(conn, job_id)["status"], _load_job(conn, job_id)["queue_state"])
        _emit(args, {"job_id": job_id, "status": "duplicate", "fingerprint": fingerprint})
        return

    job_id = new_job_id()
    ts = iso(now_utc())
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO podcast_jobs ("
            "job_id, client_id, location_id, contact_id, submission_fingerprint, "
            "mode, style, show_name, host_name, "
            "submitter_first_name, submitter_last_name, submitter_email, submitter_phone, "
            "status, created_at, updated_at) "
            "VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?, 'received', ?, ?)",
            (
                job_id, args.client_id, args.location_id, args.contact_id, fingerprint,
                args.mode, args.style, args.show_name, args.host_name,
                args.first_name, args.last_name, args.email, args.phone,
                ts, ts,
            ),
        )
        conn.execute(
            "INSERT INTO podcast_job_payloads (job_id, payload_json, stored_at) VALUES (?,?,?)",
            (job_id, json.dumps(payload, ensure_ascii=False), ts),
        )
        _append_event(conn, job_id, None, "received", "job created from intake payload")
        conn.execute("COMMIT")
    except sqlite3.IntegrityError:
        conn.execute("ROLLBACK")
        # Lost a race to a concurrent create with the same fingerprint: reconcile.
        existing = conn.execute(
            "SELECT job_id FROM podcast_jobs WHERE client_id = ? AND submission_fingerprint = ?",
            (args.client_id, fingerprint),
        ).fetchone()
        if not existing:
            raise
        job_id = existing["job_id"]
        _append_event(conn, job_id, None, None, "duplicate submission (idempotent no-op)")
        _touch(conn, job_id)
        _emit(args, {"job_id": job_id, "status": "duplicate", "fingerprint": fingerprint})
        return
    except Exception:
        conn.execute("ROLLBACK")
        raise

    if args.job_key:
        _link_ledger(job_id, args.job_key, resolve_ledger_dir(args.ledger_dir))
    _sync_ledger(job_id, "received", "none")
    _emit(args, {"job_id": job_id, "status": "received", "fingerprint": fingerprint})


def cmd_advance(conn, args):
    row = _load_job(conn, args.job_id)
    _assert_active(conn, row["client_id"])
    to_status = args.to
    # advance is only for forward and QC-loop transitions. The queue and failure
    # bookkeeping (queued_at, queue_deadline, resume_stage, aged flags) is owned by
    # the dedicated subcommands so state never goes half-set.
    if to_status == "queued_credit_out":
        raise UsageError("use `hold` to move a job onto the credit-out queue")
    if to_status == "failed":
        raise UsageError("use `fail` to mark a job failed")
    if row["status"] == "queued_credit_out":
        raise UsageError("use `resume` to bring a held job back to its resume_stage")

    # Required-outputs gate (preset/mode-aware): a producing stage may not be left
    # until its deliverable artifact(s) are recorded, unless explicitly waived.
    preset = resolve_preset(conn, args.job_id, row["mode"])
    # --force-waiver takes an OPTIONAL reason string (nargs="?"): absent -> None
    # (no waiver); bare -> the const sentinel; with a value -> the operator reason.
    waiver_reason = getattr(args, "force_waiver", None)
    waiver = waiver_reason is not None
    waived = (missing_required_outputs(row, row["status"], to_status, preset_flags(preset))
              if waiver else [])
    check_transition(row, to_status, preset=preset, waiver=waiver)

    frm = row["status"]
    conn.execute("BEGIN IMMEDIATE")
    try:
        sets = ["status = ?", "updated_at = ?"]
        vals = [to_status, iso(now_utc())]

        # QC revision increments the attempt counter (three-strike counter).
        if frm == "in_qc" and to_status == "writing":
            sets.append("attempt_count = attempt_count + 1")

        # Reaching complete stamps completed_at and purges the held payload.
        if to_status == "complete":
            sets.append("completed_at = ?")
            vals.append(iso(now_utc()))

        vals.append(args.job_id)
        conn.execute(f"UPDATE podcast_jobs SET {', '.join(sets)} WHERE job_id = ?", vals)

        if float(args.cost_delta or 0.0) != 0.0:
            conn.execute(
                "UPDATE podcast_jobs SET cost_accrued_usd = cost_accrued_usd + ? WHERE job_id = ?",
                (float(args.cost_delta), args.job_id),
            )

        _append_event(conn, args.job_id, frm, to_status, args.note, args.cost_delta)

        # Audit trail for a required-outputs override so a waived advance is never
        # silent (operator-only note; no client-facing surface reads it).
        if waived:
            _append_event(conn, args.job_id, frm, to_status,
                          "required-outputs WAIVED via --force-waiver [reason: %s]: %s"
                          % (waiver_reason, ", ".join(waived)))

        if to_status == "complete":
            conn.execute("DELETE FROM podcast_job_payloads WHERE job_id = ?", (args.job_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # T0-22: the ledger is the atomic-claim mechanism. A broken linkage means the
    # claim record is now out of step with the state machine, so the advance is
    # reported with what actually happened and the command exits non-zero. The
    # SQLite transition itself is already committed and is reported honestly —
    # this does not claim the transition did not happen, it refuses to call the
    # advance complete while its claim record is unreconciled.
    ledger_sync = _sync_ledger(
        args.job_id, to_status, _load_job(conn, args.job_id)["queue_state"]
    )
    _emit(args, {"job_id": args.job_id, "from": frm, "to": to_status,
                 "ledger_sync": ledger_sync})
    if ledger_sync == "broken":
        raise LedgerLinkageError(
            f"the {frm} -> {to_status} transition for {args.job_id} was committed to "
            f"SQLite, but its intake-ledger record could not be resolved or written. "
            f"The atomic-claim record is out of step with the state machine; this "
            f"advance is NOT complete. Repair the job index / ledger, then re-run."
        )


def cmd_output(conn, args):
    row = _load_job(conn, args.job_id)
    _assert_active(conn, row["client_id"])
    field = args.field
    if field not in OUTPUT_COLUMNS:
        raise UsageError(
            f"'{field}' is not a writable output column; allowed: {', '.join(sorted(OUTPUT_COLUMNS))}"
        )
    kind = OUTPUT_COLUMNS[field]
    value = _coerce(args.value, kind)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(f"UPDATE podcast_jobs SET {field} = ?, updated_at = ? WHERE job_id = ?",
                     (value, iso(now_utc()), args.job_id))
        _append_event(conn, args.job_id, row["status"], row["status"], f"output set: {field}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    _emit(args, {"job_id": args.job_id, "field": field, "set": True})


def _coerce(value: str, kind: str):
    if value is None:
        return None
    if kind == "int":
        return int(value)
    if kind == "real":
        return float(value)
    return str(value)


def cmd_hold(conn, args):
    row = _load_job(conn, args.job_id)
    _assert_active(conn, row["client_id"])
    if args.service not in QUEUE_SERVICES:
        raise UsageError(f"unknown service '{args.service}'; allowed: {', '.join(sorted(QUEUE_SERVICES))}")
    check_transition(row, "queued_credit_out")

    frm = row["status"]
    queued_at = now_utc()
    deadline = queued_at + timedelta(days=QUEUE_HOLD_DAYS)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE podcast_jobs SET status = 'queued_credit_out', queue_state = 'held', "
            "resume_stage = ?, queued_at = ?, queued_service = ?, queue_deadline = ?, "
            "updated_at = ? WHERE job_id = ?",
            (frm, iso(queued_at), args.service, iso(deadline), iso(queued_at), args.job_id),
        )
        if args.partial_state_file and os.path.exists(args.partial_state_file):
            with open(args.partial_state_file, "r", encoding="utf-8") as fh:
                partial = fh.read()
            conn.execute(
                "UPDATE podcast_job_payloads SET partial_state_json = ? WHERE job_id = ?",
                (partial, args.job_id),
            )
        # Operator-only note; service name never reaches the client surface.
        _append_event(conn, args.job_id, frm, "queued_credit_out",
                      f"held on credit-out (service={args.service}); resume_stage={frm}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    _sync_ledger(args.job_id, "queued_credit_out", "held")
    _emit(args, {"job_id": args.job_id, "held": True, "resume_stage": frm,
                 "queue_deadline": iso(deadline)})


def cmd_resume(conn, args):
    row = _load_job(conn, args.job_id)
    _assert_active(conn, row["client_id"])
    if row["status"] != "queued_credit_out":
        raise UsageError(f"job is not held (status={row['status']})")
    target = row["resume_stage"]
    if not target:
        raise TransitionError("held job has no resume_stage recorded")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE podcast_jobs SET status = ?, queue_state = 'resumed', queued_service = NULL, "
            "updated_at = ? WHERE job_id = ?",
            (target, iso(now_utc()), args.job_id),
        )
        _append_event(conn, args.job_id, "queued_credit_out", target,
                      "credit restored; resumed from queue")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    _sync_ledger(args.job_id, target, "resumed")
    _emit(args, {"job_id": args.job_id, "resumed_to": target})


def cmd_fail(conn, args):
    row = _load_job(conn, args.job_id)
    _assert_active(conn, row["client_id"])
    if row["status"] == "complete":
        raise TransitionError("cannot fail a completed job")
    frm = row["status"]
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE podcast_jobs SET status = 'failed', failed_step = ?, last_error = ?, "
            "updated_at = ? WHERE job_id = ?",
            (redact(args.step), redact(args.error), iso(now_utc()), args.job_id),
        )
        _append_event(conn, args.job_id, frm, "failed", f"failed at step: {args.step}")
        # Payload deleted on failure after the engine's founder notification (Section 10.2).
        conn.execute("DELETE FROM podcast_job_payloads WHERE job_id = ?", (args.job_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    _sync_ledger(args.job_id, "failed", row["queue_state"])
    _emit(args, {"job_id": args.job_id, "status": "failed", "failed_step": args.step})


def cmd_sweep_aged_out(conn, args):
    cutoff = iso(now_utc())
    held = conn.execute(
        "SELECT job_id, status, queue_deadline FROM podcast_jobs "
        "WHERE queue_state = 'held' AND queue_deadline IS NOT NULL AND queue_deadline < ?",
        (cutoff,),
    ).fetchall()
    dropped = []
    for r in held:
        job_id = r["job_id"]
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE podcast_jobs SET status = 'failed', queue_state = 'aged_out', "
                "aged_out_at = ?, failed_step = 'credit_out_age_out', "
                "last_error = ?, updated_at = ? WHERE job_id = ?",
                (iso(now_utc()),
                 f"credit-out hold exceeded {QUEUE_HOLD_DAYS}-day maximum",
                 iso(now_utc()), job_id),
            )
            _append_event(conn, job_id, "queued_credit_out", "failed",
                          f"aged out after {QUEUE_HOLD_DAYS}-day credit-out maximum")
            # Purge the held payload immediately at age-out (Section 10.3).
            conn.execute("DELETE FROM podcast_job_payloads WHERE job_id = ?", (job_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        _sync_ledger(job_id, "failed", "aged_out")
        dropped.append(job_id)
    # Founder notification is engine-side; emit a machine line the cron can act on.
    _emit(args, {"aged_out_count": len(dropped), "aged_out_jobs": dropped})


def cmd_scrub_pii(conn, args):
    if not args.job_id and not args.client_id:
        raise UsageError("scrub-pii requires --job-id or --client-id")
    if args.job_id:
        rows = conn.execute("SELECT * FROM podcast_jobs WHERE job_id = ?", (args.job_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM podcast_jobs WHERE client_id = ?", (args.client_id,)).fetchall()

    scrubbed = []
    now = now_utc()
    for r in rows:
        # Default policy: only terminal rows, PII_TOMBSTONE_DAYS after the terminal
        # event, unless --force. Never scrub an in-flight job by default.
        if not args.force:
            if r["status"] not in TERMINAL_STATES:
                continue
            terminal_ts = parse_iso(r["aged_out_at"]) or parse_iso(r["completed_at"]) or parse_iso(r["updated_at"])
            if terminal_ts and (now - terminal_ts) < timedelta(days=PII_TOMBSTONE_DAYS):
                continue
        if r["pii_scrubbed_at"]:
            continue
        job_id = r["job_id"]
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE podcast_jobs SET submitter_first_name = NULL, submitter_last_name = NULL, "
                "submitter_email = NULL, submitter_phone = NULL, pii_scrubbed_at = ?, "
                "updated_at = ? WHERE job_id = ?",
                (iso(now), iso(now), job_id),
            )
            # Clear event notes for that job (10.2): notes may carry incidental PII.
            conn.execute("UPDATE podcast_job_events SET note = NULL WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM podcast_job_payloads WHERE job_id = ?", (job_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        scrubbed.append(job_id)
    _emit(args, {"scrubbed_count": len(scrubbed), "scrubbed_jobs": scrubbed})


def cmd_deactivate_client(conn, args):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO podcast_client_state (client_id, active, deactivated_at, note) "
            "VALUES (?, 0, ?, ?) "
            "ON CONFLICT(client_id) DO UPDATE SET active = 0, deactivated_at = excluded.deactivated_at, "
            "note = excluded.note",
            (args.client_id, iso(now_utc()), redact(args.note)),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    _emit(args, {"client_id": args.client_id, "active": 0})


# --- token subcommands ------------------------------------------------------

def cmd_token(conn, args):
    if args.token_action == "mint":
        _token_mint(conn, args)
    elif args.token_action == "revoke":
        _token_revoke(conn, args)
    elif args.token_action == "list":
        _token_list(conn, args)
    else:
        raise UsageError("token action must be mint | revoke | list")


def _token_mint(conn, args):
    if not args.client_id:
        raise UsageError("token mint requires --client-id")
    # Format: pdt_<client_slug>_<32 random hex> (dashboard-design Section 11.2).
    slug = re.sub(r"[^a-z0-9\-]", "", args.client_id.lower())
    raw = f"pdt_{slug}_{secrets.token_hex(16)}"
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    token_id = new_token_id()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO podcast_dashboard_tokens (token_id, client_id, token_hash, label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token_id, args.client_id, token_hash, args.label, iso(now_utc())),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    # SHOW-ONCE: this raw value is emitted exactly once, never stored, never logged.
    # This is the single sanctioned secret emission (per Section 11.2). Only the
    # sha256 hash lives in the database.
    _emit(args, {
        "token_id": token_id,
        "client_id": args.client_id,
        "label": args.label,
        "raw_token_shown_once": raw,
        "notice": "store this now; it is never shown again and is not recoverable",
    })


def _token_revoke(conn, args):
    reason = redact(args.reason) if args.reason else "revoked"
    ts = iso(now_utc())
    if args.token_id:
        cur = conn.execute(
            "UPDATE podcast_dashboard_tokens SET revoked_at = ?, revoked_reason = ? "
            "WHERE token_id = ? AND revoked_at IS NULL",
            (ts, reason, args.token_id),
        )
        _emit(args, {"revoked": cur.rowcount, "token_id": args.token_id, "revoked_at": ts})
    elif args.client_id and args.all:
        cur = conn.execute(
            "UPDATE podcast_dashboard_tokens SET revoked_at = ?, revoked_reason = ? "
            "WHERE client_id = ? AND revoked_at IS NULL",
            (ts, reason, args.client_id),
        )
        _emit(args, {"revoked": cur.rowcount, "client_id": args.client_id, "revoked_at": ts})
    else:
        raise UsageError("token revoke requires --token-id, or --client-id with --all")


def _token_list(conn, args):
    if not args.client_id:
        raise UsageError("token list requires --client-id")
    rows = conn.execute(
        "SELECT token_id, label, created_at, last_used_at, revoked_at, revoked_reason "
        "FROM podcast_dashboard_tokens WHERE client_id = ? ORDER BY created_at DESC",
        (args.client_id,),
    ).fetchall()
    # NEVER emit token_hash or any raw value. Metadata only.
    out = []
    for r in rows:
        out.append({
            "token_id": r["token_id"],
            "label": r["label"],
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "status": "revoked" if r["revoked_at"] else "active",
            "revoked_at": r["revoked_at"],
            "revoked_reason": r["revoked_reason"],
        })
    _emit(args, {"client_id": args.client_id, "tokens": out})


# --- read helper (convenience; reads are allowed from anywhere) --------------

def cmd_get(conn, args):
    row = _load_job(conn, args.job_id)
    data = {k: row[k] for k in row.keys()}
    events = conn.execute(
        "SELECT event_id, at, from_status, to_status, note, cost_delta_usd "
        "FROM podcast_job_events WHERE job_id = ? ORDER BY at, event_id", (args.job_id,)
    ).fetchall()
    data["events"] = [dict(e) for e in events]
    data["client_label"] = CLIENT_LABEL.get(row["status"], row["status"])
    _emit(args, data, force_json=True)


def cmd_init(conn, args):
    # Schema is already ensured by connect(); this is an explicit no-op entry point
    # so provisioning scripts can create the DB deterministically.
    _emit(args, {"db_path": args.db_path or resolve_db_path(), "schema": "ready"})


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _emit(args, obj, force_json=False):
    if getattr(args, "json", False) or force_json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    else:
        # Compact human line; never includes stored secrets.
        parts = []
        for k, v in obj.items():
            parts.append(f"{k}={v}")
        sys.stdout.write("  ".join(parts) + "\n")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="podcast_state.py",
        description="Sole writer of the Podcast Production Engine state database.",
    )
    p.add_argument("--db-path", default=None, help="override PODCAST_DB_PATH")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="create a job from an intake payload (idempotent)")
    c.add_argument("--client-id", required=True)
    c.add_argument("--location-id", required=True)
    c.add_argument("--contact-id", required=True)
    c.add_argument("--mode", required=True, choices=["personal_podcast_style", "interview_style_podcast"])
    c.add_argument("--style", required=True,
                   choices=["counter_intuitive", "vulnerable", "provocative", "passionate"])
    c.add_argument("--payload-file", required=True)
    c.add_argument("--show-name", dest="show_name", default=None)
    c.add_argument("--host-name", dest="host_name", default=None)
    c.add_argument("--first-name", dest="first_name", default=None)
    c.add_argument("--last-name", dest="last_name", default=None)
    c.add_argument("--email", default=None)
    c.add_argument("--phone", default=None)
    c.add_argument("--job-key", dest="job_key", default=None,
                   help="intake ledger job_key to bridge (keeps ledger in lockstep)")
    c.add_argument("--ledger-dir", dest="ledger_dir", default=None)
    c.set_defaults(func=cmd_create)

    a = sub.add_parser("advance", help="advance a job to the next legal status")
    a.add_argument("--job-id", required=True)
    a.add_argument("--to", required=True, choices=sorted(STATUS_SET))
    a.add_argument("--note", default=None)
    a.add_argument("--cost-delta", dest="cost_delta", type=float, default=0.0)
    a.add_argument("--force-waiver", dest="force_waiver", nargs="?",
                   const="(no reason provided)", default=None, metavar="REASON",
                   help="advance even if the stage's required outputs are unset, "
                        "optionally with an operator REASON string "
                        "(`--force-waiver \"<reason>\"`); the waiver and its reason "
                        "are recorded to the job event log (audited)")
    a.set_defaults(func=cmd_advance)

    o = sub.add_parser("output", help="set an output column")
    o.add_argument("--job-id", required=True)
    o.add_argument("--field", required=True, choices=sorted(OUTPUT_COLUMNS))
    o.add_argument("--value", required=True)
    o.set_defaults(func=cmd_output)

    h = sub.add_parser("hold", help="hold a job on the credit-out queue")
    h.add_argument("--job-id", required=True)
    h.add_argument("--service", required=True, choices=sorted(QUEUE_SERVICES))
    h.add_argument("--partial-state-file", dest="partial_state_file", default=None)
    h.set_defaults(func=cmd_hold)

    r = sub.add_parser("resume", help="resume a held job to its resume_stage")
    r.add_argument("--job-id", required=True)
    r.set_defaults(func=cmd_resume)

    f = sub.add_parser("fail", help="mark a job failed (terminal)")
    f.add_argument("--job-id", required=True)
    f.add_argument("--step", required=True)
    f.add_argument("--error", required=True)
    f.set_defaults(func=cmd_fail)

    s = sub.add_parser("sweep-aged-out", help="drop holds past the 60-day maximum")
    s.set_defaults(func=cmd_sweep_aged_out)

    sc = sub.add_parser("scrub-pii", help="null PII columns on terminal rows (90-day tombstone)")
    sc.add_argument("--job-id", default=None)
    sc.add_argument("--client-id", default=None)
    sc.add_argument("--force", action="store_true", help="scrub now, ignore the tombstone window")
    sc.set_defaults(func=cmd_scrub_pii)

    d = sub.add_parser("deactivate-client", help="churn: writer fails closed for this client")
    d.add_argument("--client-id", required=True)
    d.add_argument("--note", default=None)
    d.set_defaults(func=cmd_deactivate_client)

    t = sub.add_parser("token", help="dashboard access tokens (hash-only storage)")
    t.add_argument("token_action", choices=["mint", "revoke", "list"])
    t.add_argument("--client-id", default=None)
    t.add_argument("--token-id", dest="token_id", default=None)
    t.add_argument("--label", default=None)
    t.add_argument("--reason", default=None)
    t.add_argument("--all", action="store_true", help="revoke all tokens for --client-id")
    t.set_defaults(func=cmd_token)

    g = sub.add_parser("get", help="read a job and its events (read-only)")
    g.add_argument("--job-id", required=True)
    g.set_defaults(func=cmd_get)

    i = sub.add_parser("init", help="ensure the schema exists")
    i.set_defaults(func=cmd_init)

    return p


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_TRANSITION = 3
EXIT_REFUSED = 4
EXIT_ERROR = 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        args.func(conn, args)
    except WriterRefused as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return EXIT_REFUSED
    except TransitionError as exc:
        sys.stderr.write(f"illegal transition: {exc}\n")
        return EXIT_TRANSITION
    except UsageError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - surface a sanitized message, non-zero exit
        sys.stderr.write(f"error: {redact(str(exc))}\n")
        return EXIT_ERROR
    finally:
        conn.close()
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
