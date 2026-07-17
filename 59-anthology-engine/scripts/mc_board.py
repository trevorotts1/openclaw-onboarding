#!/usr/bin/env python3
"""mc_board.py -- the FAIL-SOFT Command Center board client for the Anthology
Engine (SPEC 11.2; ENGINE-MANIFEST script_inventory; unit W3.1; extended W4.3
with a both-directions live coverage self-test and S1-S7 mirror wiring).

WHAT THIS IS (and is NOT):
  * It is the ONE place a participant's board card is created and mirrored. Every
    participant is exactly ONE task card on the Anthology department board, and
    every anthology has exactly ONE dedicated Assembly card. This client PROJECTS
    the durable ledger onto those cards -- it never decides anything and never
    writes the domain ledger (anthology_state.py is the sole writer, SPEC 7.4).
  * It is FAIL-SOFT by construction (SPEC 11.2): board unreachability, an auth
    rejection, or a schema hiccup NEVER blocks the pipeline. The ledger remains
    the truth; the card reconciles on the daily tick. Every board outcome -- even
    "unreachable" -- returns exit 0 so a stage runner is never held on the board.
    The `reconcile` subcommand IS that daily tick: it re-projects EVERY ledger
    subject (every participant chapter card + every anthology Assembly card) onto
    its board card, fail-soft per subject, so a card a stage's fail-soft swallow
    missed (a board outage mid-stage, or an S0 that held at Drive after the card
    was created) is recovered. It is also the one-time backfill for a board that
    fell behind. Idempotency keys make every re-post a safe dedupe.
  * It reuses Skill 32's EXISTING auth pair, never a new one: HMAC-SHA256 over the
    exact request bytes in `x-webhook-signature` (keyed by the WEBHOOK_SECRET
    label) PLUS `Authorization: Bearer <MC_API_TOKEN>` (the middleware external
    caller gate). Each header is sent ONLY when its secret is present on the box,
    exactly as the Command Center routes only enforce a layer when its secret is
    configured. Secret VALUES are never read into output -- SET / NOT SET only.

THE TWO ENDPOINTS (both HMAC + Bearer, both already shipping in the CC repo):
  * CREATE / RESOLVE a card:  POST /api/tasks/ingest
      idempotency_key = a stable per-subject key, so a re-post DEDUPES and returns
      the SAME task_id (the ingest route folds `source` into the card description
      as a "Source: <tag>" provenance marker; department_slug lands the card on
      the seeded Anthology board).
  * MOVE a card:              POST /api/tasks/{id}/status  {"status","note"}
      the signed status-transition consumer. It FORBIDS status='done' server-side
      (403) -- review -> done is decided ONLY by the independent QC auto-scorer at
      or above 8.5. This client mirrors that contract: its status maps contain NO
      'done', and _guarded_status() refuses to ever emit 'done'. The engine never
      self-promotes a card.

STATUS MAPPING (SPEC 11.2): card status mirrors Participants.stage_cursor. Active
authoring cursors sit the card in `in_progress`; a produced deliverable awaiting a
producer/participant decision sits the card in `review` -- the review column IS the
chapter-approval queue. `held` / `exception` escalate to `blocked`. The Assembly
card mirrors the anthology assembly_state; the "ready to assemble" trigger and the
final sign-off surface as its `review` transitions (the decision itself is written
by gate_engine.py record-approval, board door -- never here).

Exit codes (ENGINE-MANIFEST house convention, fail-soft biased):
  0  done, including a fail-soft no-op: card synced / created / deduped, OR the
     board (or the read-only mirror) was unavailable and we LOGGED and continued.
     The pipeline is never blocked by the board.
  1  unexpected internal error (house convention).
  2  local guard refusal: a caller asked for something illegal (e.g. an explicit
     status='done', which this client refuses to emit). This is a wiring bug, not
     a board condition, and never happens on the normal pipeline path.

NO secret value is ever printed. NO Anthropic identifier ships in this file. The
client-facing platform name is Convert and Flow. Python 3 stdlib only.
"""
import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
# Layout (mirrors every sibling script's resolution).
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_WRITER = SCRIPTS / "anthology_state.py"       # the SOLE ledger writer (reference only)
DEFAULT_CONFIG = SKILL_DIR / "config" / "engine-config.json"
TEMPLATE_CONFIG = SKILL_DIR / "config" / "engine-config.template.json"

# Exit codes (house convention; fail-soft biased -- see the module docstring).
EX_OK, EX_ERR, EX_REFUSE = 0, 1, 2

KEY_DELIM = "::"     # a participant_key is contact_id::anthology_id (KEYING LAW);
                     # an anthology_id (the Assembly card subject) contains no '::'.

# The Command Center's task title column cap. A card title is TRUNCATED to this
# many characters on ingest, so any disambiguator the engine relies on must be
# guaranteed to survive that truncation (see _participant_title -- the W5.6/W5.7
# edge where a pathologically long name clipped the appended anthology_id suffix
# and two anthologies for the same contact re-collided on the title-window dedupe).
TITLE_MAX = 500

# The terminal column this client is FORBIDDEN to ever set. review -> done is owned
# exclusively by the independent QC scorer at or above 8.5 (qc-scorer.ts
# runQCOnReview); the status route 403s a 'done' from a signed caller and this
# client never even attempts it.
DONE_STATUS = "done"

# The status an archived card carries on revocation. 'blocked' is excluded from the
# board's OPEN_STATUSES set, so an archived card leaves the active Anthology columns
# (there is no 'archived' primitive on the signed status route). Never 'done'.
ARCHIVE_STATUS = "blocked"

# Default credential LABELS (the Command Center's own env names; overridable per
# box via engine-config board.*). Resolved live-process-env first; SET/NOT SET only.
DEFAULT_WEBHOOK_SECRET_LABEL = "WEBHOOK_SECRET"
DEFAULT_API_TOKEN_LABEL = "MC_API_TOKEN"
# Env names that may carry the board base URL (first present wins).
DEFAULT_BASE_URL_ENV = ("MISSION_CONTROL_URL", "MC_URL")
DEFAULT_BASE_URL = "http://localhost:4000"
DEFAULT_INGEST_PATH = "/api/tasks/ingest"
DEFAULT_STATUS_PATH = "/api/tasks/{id}/status"   # {id} is the card task_id
DEFAULT_DEPARTMENT_SLUG = "anthology"
DEFAULT_SOURCE_TAG = "anthology"                 # -> "Source: anthology" marker
DEFAULT_PRIORITY = "medium"

# --------------------------------------------------------------------------- #
# Participant stage_cursor -> card status. NO entry is ever 'done' (the engine
# never self-promotes; the QC scorer owns review -> done at >= 8.5). Cursors that
# hold a produced deliverable awaiting a decision land in 'review' (the
# chapter-approval queue); active authoring cursors sit in 'in_progress'.
# Vocabulary is byte-for-byte anthology_state.STAGE_CURSORS.
# --------------------------------------------------------------------------- #
STATUS_BY_CURSOR = {
    "s0_intake":            "backlog",
    "s1_avatar":            "in_progress",
    "s1_gate":              "review",
    "s2_tone":              "in_progress",
    "s2_gate":              "review",
    "s3_title":             "in_progress",
    "s3_gate":              "review",
    "s4_blurb_outline":     "in_progress",
    "s4_gate_producer":     "review",
    "s4_gate_participant":  "review",
    "s5_chapter":           "in_progress",
    "s5_gate":              "review",
    "s6_rewrite":           "in_progress",
    "s7_cover":             "in_progress",
    "s8_deliver":           "in_progress",
    "s9_wait_assembly":     "review",   # chapter frozen + delivered; QC owns -> done
    "approved":             "review",   # parked in review; QC scorer promotes at >= 8.5
    "delivered":            "review",   # terminal from the engine's view; done is QC-owned
    "held":                 "blocked",  # durable typed hold -> human escalation
    "exception":            "blocked",  # unroutable / mismatch -> human escalation
}

# Anthology assembly_state -> Assembly card status. The "ready to assemble" trigger
# (armed) and the final sign-off (compiled -> signed_off) surface as 'review'
# transitions; the decisions themselves are gate_engine record-approval writes.
# Vocabulary is byte-for-byte anthology_state ASSEMBLY_EDGES states.
STATUS_BY_ASSEMBLY_STATE = {
    "not_ready":        "backlog",      # participants not yet all ready
    "armed":            "review",       # readiness met; ready-to-assemble trigger surfaced
    "ready_confirmed":  "in_progress",  # trigger fired; assembly underway
    "proposed":         "in_progress",  # order proposed
    "adjusted":         "in_progress",  # order adjusted
    "compiled":         "review",       # manuscript compiled; awaiting sign-off
    "signed_off":       "review",       # signed off; parked in review; QC/human owns -> done
}


# --------------------------------------------------------------------------- #
# Small shared utilities (byte-for-byte the sibling conventions).
# --------------------------------------------------------------------------- #
def _warn(msg):
    """Operator-surface stderr line. FAIL-SOFT clients are chatty to the operator
    and silent to the client; never emits a secret value or client PII."""
    sys.stderr.write("[mc_board] %s\n" % msg)


def _loads(raw, default=None):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def _env_first(names):
    """First present, non-empty env value among `names`. Returns (name, value) or
    (None, None). NEVER prints the value (doctrine: SET / NOT SET only). Mirrors
    gate_engine._env_first so credential resolution is uniform across the engine."""
    for n in names:
        if not n:
            continue
        v = os.environ.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


def resolve_state_dir(args):
    """Single source of truth for the engine state path, agreed with
    anthology_state / gate_engine / intake_router: --state-dir > ANTHOLOGY_STATE_DIR
    > OPENCLAW_DATA_DIR/anthology-engine/state > ~/.anthology-engine/state."""
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


def _load_config(explicit=None):
    """Best-effort read of the resolved per-box engine config, else the template,
    else {}. Only NON-secret board policy knobs are consulted (label names, paths,
    department slug, source tag). The config file is owned by another unit and is
    never written from here. Mirrors gate_engine._load_config."""
    for p in (Path(explicit) if explicit else None, DEFAULT_CONFIG, TEMPLATE_CONFIG):
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return {}


class BoardConfig:
    """Resolved, non-secret board wiring. Credentials are resolved BY LABEL at call
    time (never stored on this object); only the labels live here."""

    def __init__(self, cfg):
        board = (cfg.get("board") or {}) if isinstance(cfg, dict) else {}
        self.webhook_secret_label = board.get("webhook_secret_label") or DEFAULT_WEBHOOK_SECRET_LABEL
        self.api_token_label = board.get("api_token_label") or DEFAULT_API_TOKEN_LABEL
        self.ingest_path = board.get("ingest_path") or DEFAULT_INGEST_PATH
        self.status_path = board.get("status_path_template") or DEFAULT_STATUS_PATH
        self.department_slug = board.get("department_slug") or DEFAULT_DEPARTMENT_SLUG
        self.source_tag = board.get("source") or DEFAULT_SOURCE_TAG
        self.priority = board.get("priority") or DEFAULT_PRIORITY
        # base URL: an explicit env NAME from config first, then the standard names,
        # then a literal in config, then the safe localhost default.
        env_names = []
        if board.get("base_url_env"):
            env_names.append(board["base_url_env"])
        env_names.extend(DEFAULT_BASE_URL_ENV)
        _name, url = _env_first(env_names)
        self.base_url = (url or board.get("base_url") or DEFAULT_BASE_URL).rstrip("/")

    def resolve_secret(self):
        """(label, value|None) for the HMAC secret. Value never logged."""
        _n, v = _env_first([self.webhook_secret_label])
        return self.webhook_secret_label, v

    def resolve_token(self):
        """(label, value|None) for the Bearer token. Value never logged."""
        _n, v = _env_first([self.api_token_label])
        return self.api_token_label, v


# --------------------------------------------------------------------------- #
# HTTP transport (stdlib only). `_TRANSPORT` is a module hook so the pure
# self-test can substitute a fake transport with no network and no secrets.
# --------------------------------------------------------------------------- #
def _urllib_transport(url, body_bytes, headers, timeout):
    """Perform the POST. Returns (status_code:int, parsed:dict|None). A non-2xx
    REACHABLE response is returned as (code, body) so the caller can classify an
    auth/scope rejection. Only genuine unreachability (URLError / timeout / OSError)
    propagates, and the fail-soft wrapper turns that into (None, None)."""
    req = urllib.request.Request(url, data=body_bytes, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.getcode(), _loads(raw)
    except urllib.error.HTTPError as e:            # reachable server, non-2xx
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, _loads(raw)


_TRANSPORT = _urllib_transport


def _post(url, body_bytes, headers, timeout=10):
    """FAIL-SOFT POST. Returns (code|None, parsed|None). code None => the board was
    unreachable (a network blip, DNS, connection refused, timeout) -- LOGGED and
    swallowed so the pipeline is never blocked. A reachable non-2xx returns its
    real code so the caller can log the rejection and continue."""
    try:
        return _TRANSPORT(url, body_bytes, headers, timeout)
    except (urllib.error.URLError, OSError) as e:  # unreachable -> fail-soft
        _warn("board unreachable (%s); ledger holds the truth, card reconciles on the tick"
              % e.__class__.__name__)
        return None, None
    except Exception as e:                          # noqa: BLE001 last-resort fail-soft
        _warn("board request failed (%s); continuing fail-soft" % e.__class__.__name__)
        return None, None


def _sign(secret, body_bytes):
    """HMAC-SHA256 over the EXACT request bytes, lowercase hex -- byte-for-byte the
    Command Center's verifyWebhookSignature (createHmac('sha256', WEBHOOK_SECRET)
    .update(rawBody).digest('hex'))."""
    return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


def _headers(body_bytes, secret, token):
    """Build the request headers. Each auth layer is added ONLY when its secret is
    present -- exactly as the CC routes only enforce a layer when its secret is
    configured. Secret values never appear in any log, only on the wire."""
    h = {"Content-Type": "application/json"}
    if secret:
        h["x-webhook-signature"] = _sign(secret, body_bytes)
    if token:
        h["Authorization"] = "Bearer %s" % token
    return h


def _encode(body):
    """Serialize the body ONCE to the exact bytes the HMAC is computed over and the
    request sends -- there is only one byte-string, so the signature can never drift
    from the payload."""
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")


# --------------------------------------------------------------------------- #
# READ-ONLY mirror access (the projection source; never writes). Mirrors
# gate_engine._mirror_ro exactly.
# --------------------------------------------------------------------------- #
def _mirror_ro(state_dir):
    db = Path(state_dir) / "anthology_state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con
    except sqlite3.Error as exc:
        _warn("mirror open failed (%s); nothing to project, continuing fail-soft" % exc)
        return None


def _read_participant_keys(anthology_id, state_dir):
    """Read every participant_key under an anthology (for archival). Returns a list,
    or [] when the mirror is unavailable / the anthology has none. Never writes;
    fail-soft on any sqlite error. Mirrors the read-only mirror convention."""
    con = _mirror_ro(state_dir)
    if con is None:
        return []
    try:
        rows = con.execute("SELECT participant_key FROM participants WHERE anthology_id=? "
                           "ORDER BY participant_key", (anthology_id,)).fetchall()
        return [r["participant_key"] for r in rows]
    except sqlite3.Error as exc:
        _warn("mirror read (participants) failed (%s); continuing fail-soft" % exc)
        return []
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


def _read_all_participant_keys(state_dir):
    """Read EVERY participant_key across ALL anthologies -- the daily reconcile's
    participant sweep. Returns a list, or [] when the mirror is unavailable. Never
    writes; fail-soft on any sqlite error. Mirrors _read_participant_keys but
    unscoped (no anthology filter)."""
    con = _mirror_ro(state_dir)
    if con is None:
        return []
    try:
        rows = con.execute("SELECT participant_key FROM participants "
                           "ORDER BY participant_key").fetchall()
        return [r["participant_key"] for r in rows]
    except sqlite3.Error as exc:
        _warn("mirror read (all participants) failed (%s); continuing fail-soft" % exc)
        return []
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


def _read_all_anthology_ids(state_dir):
    """Read EVERY anthology_id -- the daily reconcile's Assembly-card sweep. Returns
    a list, or [] when the mirror is unavailable. Never writes; fail-soft on any
    sqlite error."""
    con = _mirror_ro(state_dir)
    if con is None:
        return []
    try:
        rows = con.execute("SELECT anthology_id FROM anthologies "
                           "ORDER BY anthology_id").fetchall()
        return [r["anthology_id"] for r in rows]
    except sqlite3.Error as exc:
        _warn("mirror read (all anthologies) failed (%s); continuing fail-soft" % exc)
        return []
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


def _read_subject(subject_key, state_dir):
    """Read the ledger row a card projects. Returns (kind, row_dict) where kind is
    'participant' or 'anthology', or (kind, None) when the subject is unknown, or
    (None, None) when the mirror is unavailable. Never writes; fail-soft on any
    sqlite error. A participant_key literally contains '::' (KEYING LAW)."""
    con = _mirror_ro(state_dir)
    if con is None:
        return None, None
    try:
        if KEY_DELIM in subject_key:
            row = con.execute("SELECT * FROM participants WHERE participant_key=?",
                              (subject_key,)).fetchone()
            return "participant", (dict(row) if row else None)
        row = con.execute("SELECT * FROM anthologies WHERE anthology_id=?",
                          (subject_key,)).fetchone()
        return "anthology", (dict(row) if row else None)
    except sqlite3.Error as exc:
        _warn("mirror read failed (%s); continuing fail-soft" % exc)
        return None, None
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


# --------------------------------------------------------------------------- #
# Card projection (pure): title, description, idempotency key, and target status.
# --------------------------------------------------------------------------- #
def _target_status(kind, row):
    """Project the ledger row to its card status. Returns a status string, or None
    when the current state is not one this client mirrors (a fail-soft no-op).
    GUARANTEE: never returns 'done' -- the maps contain none."""
    if kind == "participant":
        return STATUS_BY_CURSOR.get((row or {}).get("stage_cursor"))
    if kind == "anthology":
        return STATUS_BY_ASSEMBLY_STATE.get((row or {}).get("assembly_state"))
    return None


def _guarded_status(status):
    """The single choke point that makes 'the engine never self-promotes' true in
    THIS client too: raises on any attempt to emit 'done'. review -> done is owned
    exclusively by the QC scorer at >= 8.5."""
    if status == DONE_STATUS:
        raise ValueError("mc_board never emits status='done'; review -> done is "
                         "owned by the independent QC scorer at >= 8.5")
    return status


def _participant_display(row):
    """A human handle for the producer's own board card, built ONLY from runtime
    ledger fields (never a hardcoded identifier). Falls back to a stable, non-PII
    short handle when no name is on the row."""
    first = (row.get("first_name") or "").strip()
    last = (row.get("last_name") or "").strip()
    name = (" ".join(p for p in (first, last) if p)).strip()
    if name:
        return name
    key = row.get("participant_key") or ""
    contact = key.split(KEY_DELIM, 1)[0] if KEY_DELIM in key else key
    short = contact[-6:] if len(contact) > 6 else contact
    return "Participant %s" % (short or "unknown")


def _anthology_disambiguator(subject_key, row):
    """The participant card's anthology, for TITLE disambiguation. One contact can
    be in TWO anthologies (KEYING LAW: contact_id::anthology_id), so a title built
    from the contact alone COLLIDES across anthologies -- and the Command Center's
    generic same-title+workspace dedupe window then wrongly merges the two cards
    onto ONE task row, overriding the distinct idempotency keys the engine sent.
    Including the anthology_id makes the two titles genuinely distinct. The
    anthology_id is a synthetic ledger id (never PII); prefer the row's column,
    fall back to parsing it out of the composite key."""
    anth = ((row or {}).get("anthology_id") or "").strip()
    if not anth and KEY_DELIM in (subject_key or ""):
        anth = subject_key.split(KEY_DELIM, 1)[1].strip()
    return anth


def _participant_title(display, anth):
    """Build the participant card TITLE so its anthology_id disambiguator can NEVER
    be lost to the Command Center's TITLE_MAX truncation. The id is the ONLY thing
    that keeps two anthologies for the SAME contact from collapsing onto one task
    row via the generic same-title+workspace dedupe window; if it is appended after
    the display name and a pathologically long name fills the cap, the ` · <id>`
    suffix is clipped and the two titles re-collide (the W5.6/W5.7 edge). So we
    RESERVE the id's full width first and clip the DISPLAY NAME, never the id."""
    prefix = "Anthology chapter — "
    display = display or ""
    if not anth:
        return ("%s%s" % (prefix, display))[:TITLE_MAX]
    sep = " · "
    fixed = len(prefix) + len(sep) + len(anth)
    if fixed >= TITLE_MAX:
        # Degenerate: the id alone (with decoration) already fills the cap. Preserve
        # as much of the DISAMBIGUATOR as possible -- drop the human prefix, never
        # the id chars -- so distinct ids stay maximally distinguishable.
        return anth[:TITLE_MAX]
    disp = display[:TITLE_MAX - fixed]
    return "%s%s%s%s" % (prefix, disp, sep, anth)


def build_card(kind, subject_key, row, bcfg):
    """Assemble the ingest payload for a subject's card. `source` becomes the
    "Source: <tag>" provenance marker in the card description (the marker the
    status-transition consumer scopes on); `idempotency_key` makes a re-post
    DEDUPE onto the same card. Titles/notes carry NO secret and NO tool/model
    plumbing -- Convert and Flow is the only platform name. The participant card
    TITLE carries the anthology_id so two anthologies for the SAME contact yield
    DISTINCT titles (never collapsed by a generic title-dedupe window)."""
    if kind == "anthology":
        name = (row or {}).get("name") or subject_key
        idem = "anthology:assembly:%s" % subject_key
        title = "Anthology assembly — %s" % name
        desc = ("Assembly card for the anthology. Mirrors the ledger assembly_state; "
                "the ready-to-assemble trigger and the final sign-off are its review "
                "transitions (decided on the board, recorded in the ledger).")
    else:
        idem = "anthology:card:%s" % subject_key
        display = _participant_display(row or {"participant_key": subject_key})
        anth = _anthology_disambiguator(subject_key, row)
        # Disambiguate by anthology so the SAME contact in TWO anthologies never
        # collides on title (the collision the CC title-window dedupe collapsed).
        # _participant_title RESERVES the anthology_id's width against TITLE_MAX so a
        # long display name can never clip the disambiguator away (W5.6/W5.7 edge).
        title = _participant_title(display, anth)
        desc = ("Participant chapter card. Mirrors the ledger stage_cursor; producer "
                "deliverables land in the review column (the chapter-approval queue). "
                "Only the QC scorer at or above 8.5 promotes review to done.")
    return {
        "title": title[:TITLE_MAX],
        "description": desc,
        "priority": bcfg.priority,
        "source": bcfg.source_tag,          # -> "Source: anthology" marker in the description
        "source_ref": idem,
        "department_slug": bcfg.department_slug,
        "idempotency_key": idem,
    }


# --------------------------------------------------------------------------- #
# The two board operations (both FAIL-SOFT).
# --------------------------------------------------------------------------- #
def post_ingest(card, bcfg, timeout=10):
    """CREATE or RESOLVE the card via POST /api/tasks/ingest. Returns
    (task_id|None, outcome_str). A stable idempotency_key means a re-post DEDUPES
    onto the same task_id. FAIL-SOFT: an unreachable board / auth rejection returns
    (None, <reason>) and never raises."""
    label_s, secret = bcfg.resolve_secret()
    label_t, token = bcfg.resolve_token()
    body = _encode(card)
    url = "%s%s" % (bcfg.base_url, bcfg.ingest_path)
    code, parsed = _post(url, body, _headers(body, secret, token), timeout)
    if code is None:
        return None, "unreachable"
    if code in (200, 201):
        task_id = (parsed or {}).get("task_id")
        deduped = bool((parsed or {}).get("deduped"))
        return task_id, ("deduped" if deduped else "created")
    if code == 409:
        # loop-gate / existing_task_id dedupe -- the card already exists; treat as a
        # benign no-op and surface any task_id the route returned.
        return (parsed or {}).get("task_id"), "exists"
    # 401 (bad/absent auth), 403 (scope), 503 (secret unset in prod / schema): the
    # board is up but declined. LOG the code (never the secret) and continue.
    _warn("ingest declined by the board (HTTP %s); secret[%s]=%s bearer[%s]=%s; "
          "continuing fail-soft" % (code, label_s, "SET" if secret else "NOT SET",
                                    label_t, "SET" if token else "NOT SET"))
    return None, "declined:%s" % code


def post_status(task_id, status, note, bcfg, timeout=10):
    """MOVE the card via POST /api/tasks/{id}/status. GUARDS against ever emitting
    'done' (raises before any network I/O -- the QC scorer owns review -> done).
    FAIL-SOFT: an unreachable board / auth-or-scope rejection returns
    (False, <reason>) and never raises for a board condition."""
    _guarded_status(status)                         # ValueError on 'done' -> exit 2 upstream
    label_s, secret = bcfg.resolve_secret()
    label_t, token = bcfg.resolve_token()
    body_obj = {"status": status}
    if note:
        body_obj["note"] = note[:5000]
    body = _encode(body_obj)
    path = bcfg.status_path.replace("{id}", str(task_id))
    url = "%s%s" % (bcfg.base_url, path)
    code, parsed = _post(url, body, _headers(body, secret, token), timeout)
    if code is None:
        return False, "unreachable"
    if code == 200:
        return True, "moved"
    if code == 403:
        # The status route scopes to board-producer cards (the "Source: <tag>"
        # marker) and always forbids 'done'. A 403 here means either the Anthology
        # source marker is not yet recognized by this box's status route, or a
        # 'done' slipped through (it cannot, by _guarded_status). Fail-soft.
        _warn("status move forbidden by the board (HTTP 403) for card %s -> %s; the "
              "card stays put, the ledger is truth, it reconciles on the tick"
              % (task_id, status))
        return False, "forbidden"
    _warn("status move declined by the board (HTTP %s) for card %s -> %s; secret[%s]=%s "
          "bearer[%s]=%s; continuing fail-soft"
          % (code, task_id, status, label_s, "SET" if secret else "NOT SET",
             label_t, "SET" if token else "NOT SET"))
    return False, "declined:%s" % code


# --------------------------------------------------------------------------- #
# COMMANDS
# --------------------------------------------------------------------------- #
def _emit(obj, as_json):
    if as_json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        head = "OK" if obj.get("ok") else "NOTE"
        sys.stdout.write("%s [%s] %s\n" % (head, obj.get("action", ""),
                         {k: v for k, v in obj.items() if k not in ("ok", "action")}))
    return obj


def cmd_ensure(args):
    """Create or resolve a subject's card (ingest only; no move). Idempotent. Prints
    the task_id + outcome. FAIL-SOFT: a board outage is exit 0 with board:unreachable."""
    bcfg = BoardConfig(_load_config(args.config))
    kind, row = _read_subject(args.subject_key, resolve_state_dir(args))
    if kind is None:
        _emit({"ok": True, "action": "ensure", "subject_key": args.subject_key,
               "board": "mirror_unavailable", "failsoft": True}, args.json)
        return EX_OK
    if row is None:
        _emit({"ok": True, "action": "ensure", "subject_key": args.subject_key,
               "board": "unknown_subject", "failsoft": True,
               "note": "no ledger row to project; nothing created"}, args.json)
        return EX_OK
    card = build_card(kind, args.subject_key, row, bcfg)
    task_id, outcome = post_ingest(card, bcfg, args.timeout)
    _emit({"ok": True, "action": "ensure", "subject_key": args.subject_key,
           "kind": kind, "board": outcome, "task_id": task_id,
           "failsoft": task_id is None}, args.json)
    return EX_OK


def cmd_sync(args):
    """THE main driver the stage flow calls: project the subject's ledger row onto
    its card. Resolves/creates the card (ingest, idempotent) then moves it to the
    status the ledger dictates (status route). Refuses to ever emit 'done'. FAIL-
    SOFT throughout: any board or mirror outage is exit 0, logged, pipeline unblocked."""
    bcfg = BoardConfig(_load_config(args.config))
    kind, row = _read_subject(args.subject_key, resolve_state_dir(args))
    if kind is None:
        _emit({"ok": True, "action": "sync", "subject_key": args.subject_key,
               "board": "mirror_unavailable", "failsoft": True}, args.json)
        return EX_OK
    if row is None:
        _emit({"ok": True, "action": "sync", "subject_key": args.subject_key,
               "board": "unknown_subject", "failsoft": True,
               "note": "no ledger row to project"}, args.json)
        return EX_OK

    target = _target_status(kind, row)
    state_field = row.get("stage_cursor") if kind == "participant" else row.get("assembly_state")
    if target is None:
        _emit({"ok": True, "action": "sync", "subject_key": args.subject_key,
               "kind": kind, "state": state_field, "board": "not_mirrored",
               "note": "state is not a mirrored card status; no-op"}, args.json)
        return EX_OK

    card = build_card(kind, args.subject_key, row, bcfg)
    task_id, ingest_outcome = post_ingest(card, bcfg, args.timeout)
    if task_id is None:
        _emit({"ok": True, "action": "sync", "subject_key": args.subject_key,
               "kind": kind, "state": state_field, "target_status": target,
               "board": ingest_outcome, "failsoft": True,
               "note": "card unresolved; move deferred to the daily tick"}, args.json)
        return EX_OK

    note = "%s=%s" % ("stage_cursor" if kind == "participant" else "assembly_state",
                      state_field)
    moved, move_outcome = post_status(task_id, target, note, bcfg, args.timeout)
    _emit({"ok": True, "action": "sync", "subject_key": args.subject_key, "kind": kind,
           "state": state_field, "target_status": target, "task_id": task_id,
           "ingest": ingest_outcome, "move": move_outcome, "moved": moved,
           "failsoft": not moved}, args.json)
    return EX_OK


def _sync_one(subject_key, kind, row, bcfg, timeout):
    """Best-effort projection of ONE subject's card (ingest + move), factored out of
    cmd_sync so the daily reconcile can iterate every subject. FAIL-SOFT: returns an
    outcome string, never raises for a board condition. Mirrors _archive_one's shape.
      unknown_subject  -- no ledger row to project
      not_mirrored     -- the current state is not a mirrored card status (a no-op)
      unresolved:<why> -- the card could not be created/resolved (board declined/down)
      deferred:<why>   -- the card exists but the move was declined/deferred
      synced           -- the card is created/resolved AND moved to its target status
    """
    if kind is None or row is None:
        return "unknown_subject"
    target = _target_status(kind, row)
    if target is None:
        return "not_mirrored"
    card = build_card(kind, subject_key, row, bcfg)
    task_id, ingest_outcome = post_ingest(card, bcfg, timeout)
    if task_id is None:
        return "unresolved:%s" % ingest_outcome
    state_field = row.get("stage_cursor") if kind == "participant" else row.get("assembly_state")
    note = "%s=%s" % ("stage_cursor" if kind == "participant" else "assembly_state", state_field)
    moved, move_outcome = post_status(task_id, target, note, bcfg, timeout)
    return "synced" if moved else "deferred:%s" % move_outcome


def _reconcile_bucket(outcome):
    """Classify a _sync_one outcome into a reconcile tally bucket."""
    if outcome == "synced":
        return "synced"
    if outcome.startswith(("deferred", "unresolved")):
        return "deferred"
    if outcome == "not_mirrored":
        return "not_mirrored"
    if outcome == "unknown_subject":
        return "unknown"
    return "error"


def _reconcile_sweep(bcfg, state_dir, timeout=10, verbose=False):
    """The DAILY-TICK reconcile sweep itself (SPEC 11.2 safety net; GK-17/A7
    CONVERGING-REPAIR contract), factored out of cmd_reconcile as a PURE function
    (no printing, no argparse Namespace) so the CLI, the daily tick, and tests all
    share the ONE implementation. Projects EVERY ledger subject (every anthology
    Assembly card + every participant chapter card) onto its board card, running
    the idempotent ingest+move per subject, FAIL-SOFT per subject (one bad subject
    never aborts the sweep). Idempotency keys make every re-post a safe dedupe, so
    running this sweep twice in a row never creates a second card for the same
    subject.

    GK-17/A7: a bare 'the subprocess exited 0' is NOT proof every card actually
    landed -- mc_board.py's own exit code is fail-soft-always-0 by construction, so
    a caller that only watches the exit code cannot tell 'every subject converged'
    apart from 'the sweep ran but some cards are still wrong' (the exact gap that
    let a detector-only banner sit disconnected from any real repair). `converged`
    is the explicit, machine-checkable answer: True iff every subject ended
    'synced' (or a legitimate no-op: 'not_mirrored' / 'unknown_subject' -- states
    this client is not responsible for, never a repair failure); False iff at
    least one subject ended 'deferred' or 'error' after this pass. A caller (the
    daily tick's own report, an on-demand invocation, or a future CC-side
    drift-detector) should escalate to a human-visible signal (the v5.4.0 banner)
    ONLY when `converged` is False -- the 'banner is the escalation of last
    resort' contract this unit adds. Returns the result dict (never raises for a
    board condition; the same shape cmd_reconcile prints)."""
    anth_ids = _read_all_anthology_ids(state_dir)
    part_keys = _read_all_participant_keys(state_dir)
    outcomes = {}
    counts = {"synced": 0, "deferred": 0, "not_mirrored": 0, "unknown": 0, "error": 0}
    # Assembly cards first, then participant cards (mirrors the archive sweep order).
    for skey in list(anth_ids) + list(part_keys):
        _kind, row = _read_subject(skey, state_dir)
        try:
            outcome = _sync_one(skey, _kind, row, bcfg, timeout)
        except Exception as exc:  # noqa: BLE001 one bad subject never aborts the sweep
            _warn("reconcile subject failed (%s); continuing fail-soft" % exc.__class__.__name__)
            outcome = "error"
        outcomes[skey] = outcome
        counts[_reconcile_bucket(outcome)] += 1
    total = len(anth_ids) + len(part_keys)
    converged = (counts["deferred"] + counts["error"]) == 0
    result = {"ok": True, "action": "reconcile", "subjects": total,
              "anthologies": len(anth_ids), "participants": len(part_keys),
              "counts": counts, "failsoft": not converged, "converged": converged}
    if verbose:
        result["outcomes"] = outcomes
    return result


def cmd_reconcile(args):
    """DAILY-TICK reconcile (SPEC 11.2 safety net; GK-17/A7 converging repair): thin
    CLI wrapper over _reconcile_sweep -- resolves config/state-dir from argparse,
    runs the sweep, and prints its result (see _reconcile_sweep for the full
    contract, including the `converged` escalation signal). ALWAYS exits 0 (the
    sweep itself is fail-soft per subject); a caller that needs to know whether the
    repair actually converged reads the `converged` field, never the exit code.
    This is the tick the SPEC promised ('the card reconciles on the daily tick')
    and the one-time backfill mechanism for a board that fell behind."""
    bcfg = BoardConfig(_load_config(args.config))
    state_dir = resolve_state_dir(args)
    result = _reconcile_sweep(bcfg, state_dir, args.timeout, getattr(args, "verbose", False))
    _emit(result, args.json)
    return EX_OK


def cmd_status(args):
    """READ-ONLY: report the card status this subject WOULD carry (no network).
    Useful for the operator and the daily reconcile. Never writes, never posts."""
    kind, row = _read_subject(args.subject_key, resolve_state_dir(args))
    if kind is None:
        _emit({"ok": True, "action": "status", "subject_key": args.subject_key,
               "board": "mirror_unavailable"}, args.json)
        return EX_OK
    if row is None:
        _emit({"ok": True, "action": "status", "subject_key": args.subject_key,
               "board": "unknown_subject"}, args.json)
        return EX_OK
    target = _target_status(kind, row)
    state_field = row.get("stage_cursor") if kind == "participant" else row.get("assembly_state")
    _emit({"ok": True, "action": "status", "subject_key": args.subject_key, "kind": kind,
           "state": state_field, "target_status": target}, args.json)
    return EX_OK


def _archive_one(subject_key, kind, row, bcfg, timeout):
    """Best-effort archive of ONE card: resolve it (ingest, idempotent) then move it
    to the archived status. FAIL-SOFT. Returns an outcome string."""
    card = build_card(kind, subject_key, row, bcfg)
    task_id, ingest_outcome = post_ingest(card, bcfg, timeout)
    if task_id is None:
        return "unresolved:%s" % ingest_outcome
    moved, move_outcome = post_status(
        task_id, ARCHIVE_STATUS,
        "archived: anthology revoked (SPEC 11.2 fail-soft; the ledger is the truth)",
        bcfg, timeout)
    return "archived" if moved else "deferred:%s" % move_outcome


def cmd_archive(args):
    """Archive an anthology's board footprint on client revocation (called by
    revoke-anthology-client.sh R2): move the Assembly card and every participant
    card to the archived status ('blocked', which the board excludes from its OPEN
    columns). FAIL-SOFT: a board / mirror outage is exit 0 (the ledger is the truth;
    the daily tick reconciles). Never emits 'done'."""
    bcfg = BoardConfig(_load_config(args.config))
    state_dir = resolve_state_dir(args)
    anth_id = args.anthology_id
    subjects = []
    # the Assembly card (anthology_id) first, then each participant card.
    _kind_a, arow = _read_subject(anth_id, state_dir)
    if _kind_a is None:
        _emit({"ok": True, "action": "archive", "anthology_id": anth_id,
               "board": "mirror_unavailable", "failsoft": True}, args.json)
        return EX_OK
    subjects.append((anth_id, "anthology", arow))
    for pk in _read_participant_keys(anth_id, state_dir):
        _k, prow = _read_subject(pk, state_dir)
        subjects.append((pk, "participant", prow))
    outcomes = {}
    for skey, kind, row in subjects:
        outcomes[skey] = _archive_one(skey, kind, row or {}, bcfg, args.timeout)
    archived = sum(1 for v in outcomes.values() if v == "archived")
    _emit({"ok": True, "action": "archive", "anthology_id": anth_id,
           "cards": len(subjects), "archived": archived,
           "failsoft": archived < len(subjects), "outcomes": outcomes}, args.json)
    return EX_OK


# --------------------------------------------------------------------------- #
# PLAN + SELF-TEST (pure: mapping invariants + fail-soft transport simulation +
# HMAC determinism + read/compute over a temp mirror; no real network, no secret).
# --------------------------------------------------------------------------- #
def plan():
    print("mc_board.py -- FAIL-SOFT Command Center board client (SPEC 11.2)")
    bcfg = BoardConfig(_load_config(None))
    print("ingest       : POST %s%s (HMAC[%s] + Bearer[%s]; idempotent create/resolve)"
          % (bcfg.base_url, bcfg.ingest_path, bcfg.webhook_secret_label, bcfg.api_token_label))
    print("move         : POST %s%s (signed status transition; 'done' is FORBIDDEN)"
          % (bcfg.base_url, bcfg.status_path))
    print("department   : %s   source marker : Source: %s" % (bcfg.department_slug, bcfg.source_tag))
    print("fail-soft    : board / mirror outage -> exit 0, logged, pipeline never blocked")
    print("never-done   : review -> done owned ONLY by the QC scorer at >= 8.5")
    print("participant stage_cursor -> card status:")
    for cur, st in STATUS_BY_CURSOR.items():
        print("  %-20s -> %s" % (cur, st))
    print("anthology assembly_state -> Assembly card status:")
    for stt, st in STATUS_BY_ASSEMBLY_STATE.items():
        print("  %-16s -> %s" % (stt, st))
    return EX_OK


def _make_temp_mirror(tmp):
    """Build a minimal read-only-shaped mirror with one participant + one anthology."""
    db = Path(tmp) / "anthology_state.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        "CREATE TABLE participants(participant_key TEXT PRIMARY KEY, contact_id TEXT,"
        " anthology_id TEXT, first_name TEXT, last_name TEXT, stage_cursor TEXT);"
        "CREATE TABLE anthologies(anthology_id TEXT PRIMARY KEY, name TEXT,"
        " assembly_state TEXT);")
    con.execute("INSERT INTO participants VALUES(?,?,?,?,?,?)",
                ("contactSYN0001::ANTHsyn0001", "contactSYN0001", "ANTHsyn0001",
                 "Test", "Author", "s5_gate"))
    con.execute("INSERT INTO anthologies VALUES(?,?,?)",
                ("ANTHsyn0001", "Synthetic Anthology", "compiled"))
    con.commit()
    con.close()
    return db


def self_test():
    import tempfile

    global _TRANSPORT
    pk = "contactSYN0001::ANTHsyn0001"
    aid = "ANTHsyn0001"

    # -- exit-code identities -------------------------------------------------
    assert (EX_OK, EX_ERR, EX_REFUSE) == (0, 1, 2)

    # -- STATUS MAPS never contain 'done' (the engine never self-promotes) ----
    assert DONE_STATUS not in STATUS_BY_CURSOR.values(), "a cursor maps to 'done'"
    assert DONE_STATUS not in STATUS_BY_ASSEMBLY_STATE.values(), "an assembly state maps to 'done'"

    # -- BOTH-DIRECTIONS static coverage vs the REAL ledger vocabulary (W4.3) ----
    # Import the sole writer's live constants directly (mirrors the sibling
    # cross-check convention in intake_router.py) rather than asserting against a
    # hand-copied literal: a hardcoded set can silently drift from
    # anthology_state.STAGE_CURSORS / ASSEMBLY_STATE the moment SPEC 7.1/7.3 gains
    # or drops a value there, and this self-test would keep passing against the
    # STALE copy. Importing means that drift is CAUGHT here, every run. Hard
    # assertion (no try/except swallow) in EACH direction: every real cursor /
    # assembly_state this client is expected to project must be mapped, and this
    # client must never claim a target for a cursor / assembly_state that does not
    # exist in the ledger vocabulary.
    sys.path.insert(0, str(SCRIPTS))
    import anthology_state as _as
    mapped_cursors, real_cursors = set(STATUS_BY_CURSOR), set(_as.STAGE_CURSORS)
    assert real_cursors <= mapped_cursors, (
        "STATUS_BY_CURSOR is missing ledger cursor(s): %s"
        % sorted(real_cursors - mapped_cursors))
    assert mapped_cursors <= real_cursors, (
        "STATUS_BY_CURSOR maps unknown cursor(s) anthology_state does not carry: %s"
        % sorted(mapped_cursors - real_cursors))
    mapped_states = set(STATUS_BY_ASSEMBLY_STATE)
    real_states = set(_as.ASSEMBLY_STATE)
    assert real_states <= mapped_states, (
        "STATUS_BY_ASSEMBLY_STATE is missing ledger assembly_state(s): %s"
        % sorted(real_states - mapped_states))
    assert mapped_states <= real_states, (
        "STATUS_BY_ASSEMBLY_STATE maps unknown assembly_state(s) anthology_state "
        "does not carry: %s" % sorted(mapped_states - real_states))
    # the chapter-approval queue: the chapter gate + delivered park in 'review'.
    assert STATUS_BY_CURSOR["s5_gate"] == "review"
    assert STATUS_BY_CURSOR["approved"] == "review"
    assert STATUS_BY_CURSOR["delivered"] == "review"
    # Assembly card transitions: trigger + sign-off surface as 'review'.
    assert STATUS_BY_ASSEMBLY_STATE["not_ready"] == "backlog"
    assert STATUS_BY_ASSEMBLY_STATE["armed"] == "review"
    assert STATUS_BY_ASSEMBLY_STATE["ready_confirmed"] == "in_progress"
    assert STATUS_BY_ASSEMBLY_STATE["compiled"] == "review"
    assert STATUS_BY_ASSEMBLY_STATE["signed_off"] == "review"

    # -- the never-done guard refuses 'done' BEFORE any I/O --------------------
    try:
        _guarded_status(DONE_STATUS)
        raise AssertionError("_guarded_status must refuse 'done'")
    except ValueError:
        pass
    assert _guarded_status("review") == "review"

    # -- HMAC determinism == the Command Center scheme ------------------------
    body = _encode({"status": "review"})
    sig = _sign("unit-test-secret-not-a-real-credential", body)
    want = hmac.new(b"unit-test-secret-not-a-real-credential", body,
                    hashlib.sha256).hexdigest()
    assert sig == want and len(sig) == 64 and all(c in "0123456789abcdef" for c in sig)
    # the signed bytes are EXACTLY the bytes sent (one encode, no drift).
    assert _encode({"a": 1, "b": 2}) == _encode({"b": 2, "a": 1})  # sort_keys stable

    # -- header gating: a layer appears ONLY when its secret is present -------
    h_both = _headers(body, "s", "t")
    assert "x-webhook-signature" in h_both and h_both["Authorization"] == "Bearer t"
    h_none = _headers(body, None, None)
    assert "x-webhook-signature" not in h_none and "Authorization" not in h_none

    tmp = tempfile.mkdtemp(prefix="mcboard-selftest-")
    _make_temp_mirror(tmp)

    class _A:  # a tiny args stand-in (participant subject)
        subject_key = pk
        state_dir = tmp
        config = None
        json = True
        timeout = 5

    # -- read + project over the temp mirror ---------------------------------
    kind, row = _read_subject(pk, tmp)
    assert kind == "participant" and row and row["stage_cursor"] == "s5_gate"
    assert _target_status(kind, row) == "review"
    kind_a, row_a = _read_subject(aid, tmp)
    assert kind_a == "anthology" and row_a and row_a["assembly_state"] == "compiled"
    assert _target_status(kind_a, row_a) == "review"
    # card projection carries the Source tag + a stable idempotency key, no secret.
    bcfg = BoardConfig({})
    card = build_card(kind, pk, row, bcfg)
    assert card["source"] == "anthology" and card["idempotency_key"] == "anthology:card:%s" % pk
    assert card["department_slug"] == "anthology" and len(card["title"]) <= 500
    acard = build_card(kind_a, aid, row_a, bcfg)
    assert acard["idempotency_key"] == "anthology:assembly:%s" % aid

    # -- TWO anthologies, ONE contact -> DISTINCT titles (never collide) -------
    # The KEYING LAW puts one contact_id into two anthologies as two rows keyed
    # contact::anthology_a and contact::anthology_b. Their idempotency keys are
    # already distinct; the TITLES must ALSO be distinct so the Command Center's
    # generic same-title+workspace dedupe window can never merge the two cards
    # onto one task row (the W5.6 canary bug).
    contact = "contactSYN0777"
    pk_a = "%s%sANTHsynAAA" % (contact, KEY_DELIM)
    pk_b = "%s%sANTHsynBBB" % (contact, KEY_DELIM)
    row_a2 = {"participant_key": pk_a, "contact_id": contact, "anthology_id": "ANTHsynAAA",
              "first_name": "Same", "last_name": "Contact", "stage_cursor": "s5_gate"}
    row_b2 = {"participant_key": pk_b, "contact_id": contact, "anthology_id": "ANTHsynBBB",
              "first_name": "Same", "last_name": "Contact", "stage_cursor": "s5_gate"}
    card_a = build_card("participant", pk_a, row_a2, bcfg)
    card_b = build_card("participant", pk_b, row_b2, bcfg)
    assert card_a["idempotency_key"] != card_b["idempotency_key"], "Layer-1 keys must differ per anthology"
    assert card_a["title"] != card_b["title"], (
        "two anthologies for one contact MUST yield distinct titles (else the CC "
        "title-window dedupe collapses them): %r == %r" % (card_a["title"], card_b["title"]))
    assert "ANTHsynAAA" in card_a["title"] and "ANTHsynBBB" in card_b["title"], \
        "each participant title must carry its own anthology id"
    # Even with the anthology_id column ABSENT, the id is recovered from the key.
    card_a_nokey = build_card("participant", pk_a,
                              {"participant_key": pk_a, "first_name": "Same", "last_name": "Contact"}, bcfg)
    card_b_nokey = build_card("participant", pk_b,
                              {"participant_key": pk_b, "first_name": "Same", "last_name": "Contact"}, bcfg)
    assert card_a_nokey["title"] != card_b_nokey["title"], \
        "titles must stay distinct even when anthology_id is derived from the key"

    # -- W5.6/W5.7 EDGE: a pathologically long name must NOT clip the anthology_id --
    # A display name longer than TITLE_MAX would, with a naive "name · id" build,
    # fill the cap and let title[:TITLE_MAX] shear off the ` · <id>` suffix -- and
    # the two anthologies for this one contact would re-collide on the CC
    # title-window dedupe. The disambiguator is RESERVED, so it must survive.
    long_name = "L" * (TITLE_MAX + 200)
    row_a_long = {"participant_key": pk_a, "contact_id": contact, "anthology_id": "ANTHsynAAA",
                  "first_name": long_name, "last_name": "", "stage_cursor": "s5_gate"}
    row_b_long = {"participant_key": pk_b, "contact_id": contact, "anthology_id": "ANTHsynBBB",
                  "first_name": long_name, "last_name": "", "stage_cursor": "s5_gate"}
    card_a_long = build_card("participant", pk_a, row_a_long, bcfg)
    card_b_long = build_card("participant", pk_b, row_b_long, bcfg)
    assert len(card_a_long["title"]) <= TITLE_MAX and len(card_b_long["title"]) <= TITLE_MAX, \
        "the built title must still honour the TITLE_MAX cap"
    assert "ANTHsynAAA" in card_a_long["title"] and "ANTHsynBBB" in card_b_long["title"], \
        "a name longer than TITLE_MAX must NOT truncate away the anthology_id disambiguator"
    assert card_a_long["title"] != card_b_long["title"], \
        "two anthologies for one LONG-named contact must still yield distinct titles"
    # Degenerate id-fills-the-cap branch: even a near-cap-length id is preserved.
    huge_id = "I" * (TITLE_MAX - 1)
    assert _participant_title(long_name, huge_id) == huge_id[:TITLE_MAX], \
        "when the id alone fills the cap, the id (the disambiguator) is what survives"

    # -- INGEST SUCCESS (fake transport returns 201) --------------------------
    calls = {"ingest": 0, "status": 0}

    def _ok_transport(url, body_bytes, headers, timeout):
        # HMAC/Bearer are absent here (no secret env in the test) -- prove the
        # request still forms and the success path returns the task_id.
        if url.endswith(bcfg.ingest_path):
            calls["ingest"] += 1
            return 201, {"ok": True, "deduped": False, "task_id": "card_123",
                         "status": "backlog"}
        calls["status"] += 1
        assert json.loads(body_bytes)["status"] == "review"     # never 'done'
        return 200, {"id": "card_123", "status": "review"}

    _TRANSPORT = _ok_transport
    try:
        tid, outcome = post_ingest(card, bcfg)
        assert tid == "card_123" and outcome == "created", (tid, outcome)
        moved, mo = post_status(tid, "review", "stage_cursor=s5_gate", bcfg)
        assert moved is True and mo == "moved"
        assert cmd_sync(_A()) == EX_OK
        assert calls["ingest"] >= 2 and calls["status"] >= 2

        # dedupe path returns the same task id, marked deduped.
        def _dedupe_transport(url, body_bytes, headers, timeout):
            return 200, {"ok": True, "deduped": True, "task_id": "card_123"}
        _TRANSPORT = _dedupe_transport
        tid2, outcome2 = post_ingest(card, bcfg)
        assert tid2 == "card_123" and outcome2 == "deduped"

        # -- BOARD-DOWN FAIL-SOFT (transport raises URLError) -----------------
        def _down_transport(url, body_bytes, headers, timeout):
            raise urllib.error.URLError("connection refused")
        _TRANSPORT = _down_transport
        tid3, outcome3 = post_ingest(card, bcfg)
        assert tid3 is None and outcome3 == "unreachable"
        moved3, mo3 = post_status("card_123", "review", None, bcfg)
        assert moved3 is False and mo3 == "unreachable"
        # the whole sync is STILL exit 0 with the board down -- pipeline unblocked.
        assert cmd_sync(_A()) == EX_OK

        # -- AUTH/SCOPE REJECTION is fail-soft (reachable non-2xx) ------------
        def _403_transport(url, body_bytes, headers, timeout):
            if url.endswith(bcfg.ingest_path):
                return 201, {"task_id": "card_123", "deduped": False}
            return 403, {"error": "Forbidden"}
        _TRANSPORT = _403_transport
        moved4, mo4 = post_status("card_123", "review", None, bcfg)
        assert moved4 is False and mo4 == "forbidden"
        assert cmd_sync(_A()) == EX_OK       # still unblocked

        # -- ARCHIVE (revoke R2): archives the Assembly card + every participant --
        assert ARCHIVE_STATUS != DONE_STATUS and ARCHIVE_STATUS == "blocked"
        assert set(_read_participant_keys(aid, tmp)) == {pk}

        class _AR:  # archive args stand-in (keyed by anthology_id)
            anthology_id = aid
            state_dir = tmp
            config = None
            json = True
            timeout = 5

        arch_calls = {"n": 0}

        def _archive_transport(url, body_bytes, headers, timeout):
            if url.endswith(bcfg.ingest_path):
                return 201, {"task_id": "card_arch", "deduped": False}
            arch_calls["n"] += 1
            assert json.loads(body_bytes)["status"] == "blocked"   # archived, never 'done'
            return 200, {"id": "card_arch", "status": "blocked"}
        _TRANSPORT = _archive_transport
        assert cmd_archive(_AR()) == EX_OK
        assert arch_calls["n"] == 2          # Assembly card + 1 participant card

        # archive stays exit 0 even with the board down (fail-soft revocation).
        _TRANSPORT = _down_transport
        assert cmd_archive(_AR()) == EX_OK

        # -- RECONCILE (daily tick): sweeps EVERY subject, fail-soft per subject ----
        # The unscoped reads see every ledger subject (1 participant + 1 anthology).
        assert set(_read_all_participant_keys(tmp)) == {pk}
        assert set(_read_all_anthology_ids(tmp)) == {aid}

        class _RC:  # reconcile args stand-in: no subject-key; it sweeps ALL subjects
            state_dir = tmp
            config = None
            json = True
            timeout = 5
            verbose = True

        recon_calls = {"ingest": 0, "status": 0}

        def _reconcile_transport(url, body_bytes, headers, timeout):
            if url.endswith(bcfg.ingest_path):
                recon_calls["ingest"] += 1
                return 201, {"task_id": "card_rc", "deduped": False}
            recon_calls["status"] += 1
            assert json.loads(body_bytes)["status"] != "done"   # never 'done'
            return 200, {"id": "card_rc", "status": "review"}
        _TRANSPORT = _reconcile_transport
        assert cmd_reconcile(_RC()) == EX_OK
        # both the Assembly card (compiled->review) and the participant (s5_gate->
        # review) are re-projected: two ingests + two moves.
        assert recon_calls["ingest"] == 2 and recon_calls["status"] == 2, recon_calls
        # _sync_one classifies a successful projection as 'synced'.
        assert _reconcile_bucket("synced") == "synced"
        assert _reconcile_bucket("deferred:forbidden") == "deferred"
        assert _reconcile_bucket("unresolved:unreachable") == "deferred"
        assert _reconcile_bucket("unknown_subject") == "unknown"

        # -- GK-17/A7 CONVERGING-REPAIR signal: a fully-successful sweep converges --
        # calling _reconcile_sweep directly (the pure function cmd_reconcile wraps)
        # so the actual result dict -- not just the CLI's always-0 exit code -- is
        # inspectable. A caller (a future drift-detector) must be able to tell
        # 'every card actually landed' apart from 'the sweep merely ran'.
        sweep_ok = _reconcile_sweep(bcfg, tmp, timeout=5, verbose=True)
        assert sweep_ok["converged"] is True and sweep_ok["failsoft"] is False, sweep_ok
        assert sweep_ok["counts"]["deferred"] == 0 and sweep_ok["counts"]["error"] == 0

        # reconcile stays exit 0 even with the board down (fail-soft daily tick), and
        # an empty ledger (mirror unavailable) is a clean zero-subject exit 0.
        _TRANSPORT = _down_transport
        assert cmd_reconcile(_RC()) == EX_OK

        # -- GK-17/A7: a repair path that CANNOT succeed (the board is down for the
        # whole sweep -- a deliberately broken repair path) must NOT converge. This
        # is the ONLY condition under which a caller should escalate to the banner
        # (the v5.4.0 banner becomes the escalation of last resort, never the
        # default UX for a sweep that is merely mid-flight).
        sweep_down = _reconcile_sweep(bcfg, tmp, timeout=5, verbose=True)
        assert sweep_down["converged"] is False and sweep_down["failsoft"] is True, sweep_down
        assert (sweep_down["counts"]["deferred"] + sweep_down["counts"]["error"]) == sweep_down["subjects"]

        class _RCEMPTY:
            state_dir = tempfile.mkdtemp(prefix="mcboard-empty-")  # no anthology_state.db
            config = None
            json = True
            timeout = 5
            verbose = False
        assert cmd_reconcile(_RCEMPTY()) == EX_OK
        # an empty ledger (zero subjects) is trivially converged -- there is nothing
        # left unresolved, so it must never manufacture a false escalation.
        _TRANSPORT = _reconcile_transport
        sweep_empty = _reconcile_sweep(bcfg, _RCEMPTY.state_dir, timeout=5)
        assert sweep_empty["subjects"] == 0 and sweep_empty["converged"] is True, sweep_empty
    finally:
        _TRANSPORT = _urllib_transport

    print("mc_board self-test: OK (status maps never 'done', never-done guard, HMAC "
          "== CC scheme, header gating, ledger read+project, ingest success, "
          "two-anthology-one-contact distinct titles, board-down fail-soft, "
          "auth/scope fail-soft, Assembly transitions, archive Assembly+participants "
          "fail-soft, reconcile sweeps every subject + empty/down fail-soft, GK-17/A7 "
          "converged signal true only when every subject actually landed)")
    return EX_OK


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser():
    ap = argparse.ArgumentParser(
        prog="mc_board.py",
        description="FAIL-SOFT Command Center board client: create + mirror the "
                    "Anthology participant and Assembly cards. Never blocks the pipeline.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the pure self-test (no network / no secret) and exit")
    ap.add_argument("--plan", action="store_true",
                    help="print the endpoints + status maps and exit")
    sub = ap.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--subject-key", dest="subject_key", required=True,
                        help="participant_key (contact_id::anthology_id) or an anthology_id")
        sp.add_argument("--state-dir", dest="state_dir",
                        help="engine state dir (default: resolved like anthology_state)")
        sp.add_argument("--config", help="path to the resolved engine-config.json")
        sp.add_argument("--timeout", type=int, default=10, help="per-request timeout seconds")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    common(sub.add_parser("sync", help="project the ledger onto the card (create + move)"))
    common(sub.add_parser("ensure", help="create/resolve the card only (ingest; no move)"))
    common(sub.add_parser("status", help="read-only: the card status this subject would carry"))

    sp = sub.add_parser("archive", help="archive an anthology's board cards on revocation")
    sp.add_argument("--anthology-id", dest="anthology_id", required=True,
                    help="the anthology whose Assembly + participant cards are archived")
    sp.add_argument("--state-dir", dest="state_dir",
                    help="engine state dir (default: resolved like anthology_state)")
    sp.add_argument("--config", help="path to the resolved engine-config.json")
    sp.add_argument("--timeout", type=int, default=10, help="per-request timeout seconds")
    sp.add_argument("--json", action="store_true", help="machine-readable output")

    sp = sub.add_parser("reconcile", help="daily-tick: project EVERY ledger subject "
                        "onto its card (recover any card a fail-soft swallow missed)")
    sp.add_argument("--state-dir", dest="state_dir",
                    help="engine state dir (default: resolved like anthology_state)")
    sp.add_argument("--config", help="path to the resolved engine-config.json")
    sp.add_argument("--timeout", type=int, default=10, help="per-request timeout seconds")
    sp.add_argument("--json", action="store_true", help="machine-readable output")
    sp.add_argument("--verbose", action="store_true",
                    help="include the per-subject outcome map in the output")
    return ap


HANDLERS = {"sync": cmd_sync, "ensure": cmd_ensure, "status": cmd_status,
            "archive": cmd_archive, "reconcile": cmd_reconcile}


def main(argv=None):
    ap = _build_parser()
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return plan()
        if not args.cmd:
            ap.print_help()
            return EX_ERR
        return HANDLERS[args.cmd](args)
    except ValueError as exc:            # a local guard refusal (e.g. 'done') -> exit 2
        _warn("guard refusal: %s" % exc)
        return EX_REFUSE
    except BrokenPipeError:
        return EX_OK
    except Exception as exc:             # noqa: BLE001 last-resort; house exit 1
        _warn("unexpected error: %s" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
