#!/usr/bin/env python3
"""gate_engine.py -- the Anthology Engine gate state machine, the single both-door
gate endpoint, and the scoped participant token/PIN mint + verify (SPEC 3.4 row 7,
SPEC 11.3, ENGINE-MANIFEST inventory n=7; unit W1.15).

WHAT THIS IS (and is NOT):
  * It is the ONE place the gate logic lives. The emailed participant nudge link
    (the token page) and the producer's board card view are TWO DOORS that hit the
    SAME endpoint here (`decide`) and, through it, the SAME sole-writer subcommand
    (anthology_state.py record-approval). No gate decision is ever written twice or
    from two code paths (SPEC 11.3 both-door rule).
  * It NEVER writes the domain ledger directly. Every state change shells the
    sole writer anthology_state.py (SPEC 7.4). Reads (which gate is open) come from
    the local SQLite mirror READ-ONLY (SPEC 7.2), exactly as intake_router.py reads.
  * On a COMMITTED board-door PRODUCER approve it stamps the stage's standard §3
    release slug (anthology-release-*) on the participant's contact by shelling
    caf_delivery.py add-tag (the sole tag writer). That contact_tag is the ONLY
    thing Layer 4 writes to the client on an approve, and it is what fires the §3
    W3-W10 notification workflow (email + SMS). The stamp is FAIL-SOFT (SPEC 7.2):
    a Convert and Flow blip never unwinds the committed gate decision.
  * It mints and verifies a NEW single-purpose token/PIN per open gate:
    HMAC-SHA256 over (participant_key, gate id, expiry), keyed by the per-client
    secret resolved BY LABEL under ANTHOLOGY_GATE_TOKEN_SECRET (live process env
    first; the value is NEVER printed, SET / NOT SET only). Tokens are
    single-gate-scoped, expire, and FOREIGN / EXPIRED / REPLAYED tokens are refused
    (AF-AE-TOKEN-REFUSED, py_symbol verify_token).

GATE STATE MACHINE (the open gate is a projection of the ledger cursor, never a
second store): a participant sitting at a `*_gate` stage_cursor has exactly one
open gate; an anthology's assembly_state projects the S9 producer gates. The
resolver is resolve_open_gate(). The chapter gate (s5_participant) exposes EXACTLY
TWO actions (approve as-is / request rewrite with notes) -- SPEC S5.

BOTH DOORS, ONE ENDPOINT:
  * door=token  -> the participant token page (nudge deep link); requires a valid
                   scoped token or PIN; recorded as door 'nudge_link'.
  * door=board  -> the producer's Command Center board card view (own session /
                   own-producer auth); recorded as door 'dashboard'.
  Both resolve to the identical anthology_state.py record-approval call.

Exit codes (SPEC 3.4 row 7; house convention: 1 unexpected error):
  0  action recorded (incl. a base-unreachable write durably queued to the mirror,
     because a network blip must NEVER block a gate action -- SPEC 7.2)
  2  guard / validation refusal: token refused (foreign / expired / replayed /
     tampered), action not allowed at the open gate, a required field missing, or a
     typed-name / sign-off validation mismatch (AF-AE-TOKEN-REFUSED lives here)
  3  gate not open: the subject is not at an open gate, the subject is unknown, or
     the sole writer / gate-token secret is unavailable (held)
  1  unexpected error

NO secret value is ever printed. NO client PII is emitted (recipients are resolved
inside nudge_send.py, not here). Convert and Flow is the only platform name. Zero
Anthropic identifiers ship in this file.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import namedtuple
from pathlib import Path

# --------------------------------------------------------------------------- #
# Layout (mirrors every sibling script's resolution).
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_WRITER = SCRIPTS / "anthology_state.py"       # the SOLE ledger writer (SPEC 7.4)
NUDGE_SEND = SCRIPTS / "nudge_send.py"              # sibling W1.15 file
CAF_DELIVERY = SCRIPTS / "caf_delivery.py"          # the SOLE contact-tag writer (§3 release bus)
DEFAULT_CONFIG = SKILL_DIR / "config" / "engine-config.json"          # resolved per box
TEMPLATE_CONFIG = SKILL_DIR / "config" / "engine-config.template.json"

# Exit codes.
EX_OK, EX_ERR, EX_REFUSE, EX_GATE = 0, 1, 2, 3

# The label under which the per-client gate-token HMAC secret is resolved. The
# VALUE is never read into any output; only SET / NOT SET is ever surfaced.
DEFAULT_SECRET_LABEL = "ANTHOLOGY_GATE_TOKEN_SECRET"

# Token wire format version and default lifetime. There is no participant deadline
# (the ledger holds the cursor for months at zero cost); the token merely carries a
# generous hard expiry and is freely RE-MINTABLE on a manual re-send. 45 days
# mirrors the legacy ceiling as an upper bound, never as a timeout.
TOKEN_VERSION = "v1"
DEFAULT_TTL_DAYS = 45

KEY_DELIM = "::"     # participant_key is contact_id::anthology_id (KEYING LAW)

# --------------------------------------------------------------------------- #
# The gate table. The open gate is derived from the ledger, never stored twice.
# GateSpec.actions is the CLOSED set of engine action names the door may present;
# each maps to a sole-writer decision via ACTION_DECISION.
# --------------------------------------------------------------------------- #
GateSpec = namedtuple("GateSpec", "gate_id actor door_kind actions")

# participant stage_cursor -> the single open gate at that cursor.
GATE_BY_CURSOR = {
    "s1_gate":              GateSpec("s1_producer",   "producer",    "producer",
                                     ("approve", "hold", "exclude", "escalate")),
    "s2_gate":              GateSpec("s2_producer",   "producer",    "producer",
                                     ("approve", "hold", "exclude", "escalate")),
    "s3_gate":              GateSpec("s3_selection",  "participant", "participant",
                                     ("select",)),
    "s4_gate_producer":     GateSpec("s4_producer",   "producer",    "producer",
                                     ("approve", "hold", "exclude", "escalate")),
    "s4_gate_participant":  GateSpec("s4_participant", "participant", "participant",
                                     ("approve",)),
    # THE CHAPTER GATE -- EXACTLY TWO ACTIONS (SPEC S5; asserted in self_test).
    "s5_gate":              GateSpec("s5_participant", "participant", "participant",
                                     ("approve_as_is", "request_rewrite_with_notes")),
}

# The participant gates a token/PIN may scope to (the token page serves ONLY these:
# S3 selection, S4 outline approval, S5/S6 chapter -- SPEC 11.3). Producer and
# assembly gates are board-door only.
PARTICIPANT_GATE_CURSORS = frozenset(
    c for c, g in GATE_BY_CURSOR.items() if g.door_kind == "participant"
)
PARTICIPANT_GATE_IDS = frozenset(
    g.gate_id for g in GATE_BY_CURSOR.values() if g.door_kind == "participant"
)

# engine action name -> (sole-writer decision, required extra fields).
ACTION_DECISION = {
    "approve":                    ("approve",          ()),
    "approve_as_is":              ("approve",          ()),
    "request_rewrite_with_notes": ("request_rewrite",  ("notes",)),
    "select":                     ("approve",          ("title",)),   # subtitle optional
    "hold":                       ("hold",             ("reason",)),
    "exclude":                    ("exclude",          ()),
    "escalate":                   ("escalate",         ()),
    "ready_to_assemble":          ("ready_to_assemble", ("confirm_name", "producer_id")),
    "sign_off":                   ("approve",          ("producer_id",)),
}

# door name -> the sole-writer 'door' provenance value (APPROVAL_DOORS).
DOOR_VALUE = {"token": "nudge_link", "board": "dashboard"}

# --------------------------------------------------------------------------- #
# ASSEMBLY ORDERING board actions (U9 assembly-finale / CC assembly cockpit, unit
# U13). These are BOARD-DOOR, own-producer, ANTHOLOGY-subject actions that act
# during the S9 ordering window (assembly_state ready_confirmed|proposed|adjusted)
# -- the window where resolve_open_gate surfaces NO single GateSpec (the s9_ready
# gate closed on the arm and the s9_producer gate opens only at 'compiled'). They
# persist the producer's finalized running order through the SOLE writer
# (anthology_state assembly-set-order), and confirm_order ADDITIONALLY flags the S9
# runner (request.confirm_order) so its next pass writes U9's inter-chapter
# transitions + Grand Finale. adjust_order persists WITHOUT arming the finale (free
# reordering); confirm_order is the ONE that triggers the finale.
ASSEMBLY_ORDER_ACTIONS = ("adjust_order", "confirm_order")
FINALE_TRIGGER_ACTION = "confirm_order"
# the assembly_state values in which an order may be (re)persisted (SPEC 7.3 tail;
# anthology_state ASSEMBLY_EDGES ready_confirmed/proposed -> proposed/adjusted).
ORDER_WINDOW_STATES = ("ready_confirmed", "proposed", "adjusted")

# --------------------------------------------------------------------------- #
# THE RELEASE-TAG BUS (SPEC §3: the board-approve -> tag -> notification wiring).
# When a PRODUCER approves at a producer gate through the BOARD door and the
# decision COMMITS, the engine stamps that stage's standard §3 release slug onto
# the participant's Convert and Flow contact (via caf_delivery.py add-tag, the sole
# tag writer, which does its own byte read-back + idempotency + tenant guard). That
# contact_tag is the ONE thing Layer 4 writes to the client on an approve, and it
# is exactly what fires the §3 W3-W10 notification workflow (email + SMS carrying
# the PDF-view + Doc-edit links). Keyed by PRODUCER gate id, never hardcoded per
# stage elsewhere:
#   * s1/s2/s4 producer gates exist today (avatar / tone / outline).
#   * s5/s6/s7 producer gates are engine-gated follow-ons the cover + assembly
#     build units add; their slugs are wired here in advance so the bus lights up
#     with no re-plumbing the moment the gate appears in GATE_BY_CURSOR.
#   * Assembly gates (s9_ready / s9_producer) key on an anthology_id, not a single
#     contact, so they never fire this per-contact bus (the assembly cockpit stamps
#     anthology-delivered on every contact itself).
#   * S3 title-select and S8 final are stage-runner-fired (the runner calls
#     `caf_delivery add-tag` directly), NOT producer-approve gates, so they are
#     intentionally absent from this gate-approve map.
# --------------------------------------------------------------------------- #
GATE_RELEASE_SLUG = {
    "s1_producer": "anthology-release-avatar",
    "s2_producer": "anthology-release-tone",
    "s4_producer": "anthology-release-outline",
    "s5_producer": "anthology-release-chapter",   # engine-gated follow-on (producer chapter gate)
    "s6_producer": "anthology-release-rewrite",    # engine-gated follow-on (producer rewrite gate)
    "s7_producer": "anthology-release-cover",       # engine-gated follow-on (producer cover gate)
}

# The engine action that means "producer approves = release to the client" (SPEC
# 11.26). Holds / excludes / escalations / selects / participant approvals never
# release; approve_as_is is a participant action and is filtered by the door_kind
# gate below regardless.
_RELEASE_ACTIONS = frozenset({"approve"})


def release_slug_for(spec, action, door, committed):
    """PURE decision (no network, no state): the §3 release slug to stamp, or None.
    A release is stamped IFF the decision COMMITTED, came through the BOARD door
    (producer session; the token door is the participant and never releases), the
    action is an approve, and the open gate is a PRODUCER gate carrying a §3 release
    slug. Everything else -- holds, excludes, escalations, title-select, participant
    approvals, the token door, and the assembly gates -- returns None."""
    if spec is None or not committed:
        return None
    if door != "board":
        return None
    if action not in _RELEASE_ACTIONS:
        return None
    if spec.door_kind != "producer":
        return None
    return GATE_RELEASE_SLUG.get(spec.gate_id)


# --------------------------------------------------------------------------- #
# Small shared utilities (byte-for-byte the sibling conventions).
# --------------------------------------------------------------------------- #
def _env_first(names):
    """First present, non-empty env value among `names`. Returns (name, value) or
    (None, None). NEVER prints the value (doctrine: SET / NOT SET only). Mirrors
    anthology_state.py._env_first so credential resolution is uniform."""
    for n in names:
        v = os.environ.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


def resolve_state_dir(args):
    """Single source of truth for the engine state path, agreed with
    anthology_state / intake_router: --state-dir > ANTHOLOGY_STATE_DIR >
    OPENCLAW_DATA_DIR/anthology-engine/state > ~/.anthology-engine/state."""
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
    else {}. Only NON-secret policy knobs are consulted here (label names, ttl,
    link bases, delivery hint). Missing keys fall back to code defaults; the config
    file is owned by another unit and is never written from here."""
    for p in (Path(explicit) if explicit else None, DEFAULT_CONFIG, TEMPLATE_CONFIG):
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return {}


def _secret_label(cfg):
    return (((cfg.get("gates") or {}).get("gate_token_secret_label"))
            or DEFAULT_SECRET_LABEL)


def _ttl_seconds(cfg):
    days = ((cfg.get("gates") or {}).get("token_ttl_days")) or DEFAULT_TTL_DAYS
    try:
        return int(float(days)) * 86400
    except (TypeError, ValueError):
        return DEFAULT_TTL_DAYS * 86400


def _resolve_secret(cfg):
    """Resolve the gate-token HMAC secret BY LABEL (live process env first). Returns
    (label, value) or (label, None). The value is never logged."""
    label = _secret_label(cfg)
    _, val = _env_first([label])
    return label, val


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _now_epoch(now=None) -> int:
    return int(now if now is not None else time.time())


def _emit(obj, as_json):
    if as_json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        head = "OK" if obj.get("ok") else "REFUSED"
        sys.stdout.write("%s %s\n" % (head, obj.get("action", "")))
        for k in ("gate", "subject_key", "decision", "door", "reason",
                  "expires_at", "note"):
            if k in obj and obj[k] is not None:
                sys.stdout.write("  %-12s %s\n" % (k, obj[k]))
    return obj


# --------------------------------------------------------------------------- #
# TOKEN / PIN CRYPTO (stdlib HMAC-SHA256; no third-party dependency).
#
# Wire format:  v1.<b64url(payload_json)>.<b64url(hmac_sig)>
# payload    :  {"pk": participant_key, "g": gate_id, "iat": epoch, "exp": epoch,
#                "jti": nonce_hex}
# The signature covers "v1.<payload_b64>" so tampering with ANY field (subject,
# gate, or expiry) invalidates it. jti gives each mint a unique single-use handle.
# --------------------------------------------------------------------------- #
def mint_token(participant_key, gate_id, secret, *, ttl_seconds, now=None, jti=None):
    """Mint a single-gate-scoped token for `participant_key` at `gate_id`. Returns
    (token_str, payload_dict). Raises ValueError on an empty secret (caller maps to
    a held state; the secret is never surfaced)."""
    if not secret:
        raise ValueError("gate-token secret unavailable")
    iat = _now_epoch(now)
    payload = {
        "pk": participant_key,
        "g": gate_id,
        "iat": iat,
        "exp": iat + int(ttl_seconds),
        "jti": jti or uuid.uuid4().hex,
    }
    pb = _b64u_encode(json.dumps(payload, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8"))
    signing_input = (TOKEN_VERSION + "." + pb).encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return "%s.%s.%s" % (TOKEN_VERSION, pb, _b64u_encode(sig)), payload


def verify_token(token, secret, *, expected_pk=None, expected_gate=None, now=None):
    """Verify a scoped token. Returns a dict:
        {"ok": True,  "pk": ..., "gate": ..., "exp": int, "jti": ...}
        {"ok": False, "reason": <bad_signature|expired|foreign_subject|
                                  foreign_gate|malformed>}
    A foreign (wrong participant or wrong gate), expired, or tampered/forged token
    is REFUSED (AF-AE-TOKEN-REFUSED). Constant-time signature comparison. This is
    the ENFORCED symbol named in ENGINE-MANIFEST.json (py_symbol verify_token)."""
    def refuse(reason):
        return {"ok": False, "reason": reason}
    if not secret:
        return refuse("secret_unavailable")
    if not isinstance(token, str):
        return refuse("malformed")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_VERSION or not parts[1] or not parts[2]:
        return refuse("malformed")
    _, pb, sb = parts
    try:
        signing_input = (TOKEN_VERSION + "." + pb).encode("ascii")
        want = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        got = _b64u_decode(sb)
    except (ValueError, TypeError):
        return refuse("malformed")
    if not hmac.compare_digest(want, got):
        return refuse("bad_signature")            # forged / foreign-secret / tampered
    try:
        payload = json.loads(_b64u_decode(pb))
        pk = str(payload["pk"])
        gate = str(payload["g"])
        exp = int(payload["exp"])
        jti = str(payload.get("jti", ""))
    except (ValueError, TypeError, KeyError):
        return refuse("malformed")
    if exp <= _now_epoch(now):
        return refuse("expired")
    if expected_pk is not None and pk != expected_pk:
        return refuse("foreign_subject")
    if expected_gate is not None and gate != expected_gate:
        return refuse("foreign_gate")
    return {"ok": True, "pk": pk, "gate": gate, "exp": exp, "jti": jti}


def mint_pin(participant_key, gate_id, exp, secret) -> str:
    """A short human-typable 8-digit PIN bound to the SAME (pk, gate, exp) material,
    derived by an independent HMAC tag so it cannot be reversed into the token. It
    expires exactly when the token does."""
    mac = hmac.new(secret.encode("utf-8"),
                   ("pin:%s:%s:%d" % (participant_key, gate_id, int(exp))).encode("utf-8"),
                   hashlib.sha256).digest()
    return "%08d" % (int.from_bytes(mac[:5], "big") % 100000000)


def verify_pin(participant_key, gate_id, exp, pin, secret, *, now=None):
    """Verify a PIN against its (pk, gate, exp) binding. Same refusal vocabulary as
    verify_token. The caller supplies `exp` (the Command Center holds it from mint)."""
    if not secret:
        return {"ok": False, "reason": "secret_unavailable"}
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "malformed"}
    if exp_i <= _now_epoch(now):
        return {"ok": False, "reason": "expired"}
    want = mint_pin(participant_key, gate_id, exp_i, secret)
    if not hmac.compare_digest(want, str(pin or "")):
        return {"ok": False, "reason": "bad_signature"}
    return {"ok": True, "pk": participant_key, "gate": gate_id, "exp": exp_i}


# --------------------------------------------------------------------------- #
# READ-ONLY mirror access + the open-gate resolver (the gate state machine).
# --------------------------------------------------------------------------- #
class GateHeld(Exception):
    """A dependency needed to act on the gate is unavailable -> exit 3 (held)."""


def _mirror_ro(state_dir: Path):
    db = Path(state_dir) / "anthology_state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con
    except sqlite3.Error as exc:
        raise GateHeld("mirror open failed: %s" % exc)


def _read_one(con, sql, params):
    if con is None:
        return None
    try:
        row = con.execute(sql, params).fetchone()
        return dict(row) if row is not None else None
    except sqlite3.Error as exc:
        raise GateHeld("mirror read failed: %s" % exc)


def resolve_open_gate(subject_key, state_dir):
    """Project the open gate for a subject from the ledger mirror.

    Returns (kind, row, GateSpec) where kind is 'participant' or 'anthology', or
    None when the subject has no open gate (unknown subject, or a cursor / assembly
    state that is not gate-actionable). Never writes. The subject_key discriminates
    itself: a participant_key literally contains '::' (KEYING LAW)."""
    con = _mirror_ro(state_dir)
    if con is None:
        return None
    try:
        if KEY_DELIM in subject_key:
            row = _read_one(con, "SELECT * FROM participants WHERE participant_key=?",
                            (subject_key,))
            if not row:
                return None
            spec = GATE_BY_CURSOR.get(row.get("stage_cursor"))
            return ("participant", row, spec) if spec else ("participant", row, None)
        row = _read_one(con, "SELECT * FROM anthologies WHERE anthology_id=?",
                        (subject_key,))
        if not row:
            return None
        st = row.get("assembly_state")
        if st in ("not_ready", "armed"):
            return ("anthology", row,
                    GateSpec("s9_ready", "producer", "producer", ("ready_to_assemble",)))
        if st == "compiled":
            return ("anthology", row,
                    GateSpec("s9_producer", "producer", "producer", ("sign_off",)))
        return ("anthology", row, None)
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


# --------------------------------------------------------------------------- #
# Single-use nonce store (a gate_engine-OWNED sidecar; NOT the domain ledger).
# It gives explicit REPLAY refusal: a token/PIN consumed by a committed decision
# cannot be replayed. It is opened fail-soft -- if it cannot be opened, replay is
# still bounded by (a) gate-closure (the cursor advances so the token's gate no
# longer matches the open gate -> foreign_gate on re-verify) and (b) the
# idempotency key handed to the sole writer (an exact replay is a base-write no-op).
# --------------------------------------------------------------------------- #
class NonceStore:
    def __init__(self, state_dir: Path):
        self.available = False
        self.con = None
        try:
            Path(state_dir).mkdir(parents=True, exist_ok=True)
            self.con = sqlite3.connect(str(Path(state_dir) / "gate_nonce.db"), timeout=15)
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.execute("PRAGMA busy_timeout=15000")
            self.con.execute(
                "CREATE TABLE IF NOT EXISTS gate_nonce ("
                "  nonce TEXT PRIMARY KEY, participant_key TEXT, gate TEXT,"
                "  claimed_utc TEXT)")
            self.con.commit()
            self.available = True
        except sqlite3.Error:
            self.available = False

    def claim(self, nonce, participant_key, gate):
        """Atomic single-use claim. Returns True if THIS caller won a fresh claim,
        False if the nonce was already consumed (a replay). Fail-soft: an
        unavailable store returns True (claim degraded to the two backstops above)."""
        if not self.available:
            return True
        try:
            cur = self.con.execute(
                "INSERT OR IGNORE INTO gate_nonce(nonce,participant_key,gate,claimed_utc)"
                " VALUES(?,?,?,?)",
                (nonce, participant_key, gate,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            self.con.commit()
            return cur.rowcount == 1
        except sqlite3.Error:
            return True

    def consumed(self, nonce):
        """True if this nonce was already committed (a replay). Fail-soft: an
        unavailable store returns False (replay is still bounded by gate closure)."""
        if not self.available:
            return False
        try:
            r = self.con.execute("SELECT 1 FROM gate_nonce WHERE nonce=?",
                                 (nonce,)).fetchone()
            return r is not None
        except sqlite3.Error:
            return False

    def release(self, nonce):
        """Undo a claim (the decision did not commit) so a corrected retry with the
        SAME token/PIN is allowed."""
        if not self.available:
            return
        try:
            self.con.execute("DELETE FROM gate_nonce WHERE nonce=?", (nonce,))
            self.con.commit()
        except sqlite3.Error:
            pass

    def close(self):
        try:
            if self.con is not None:
                self.con.close()
        except sqlite3.Error:
            pass


# --------------------------------------------------------------------------- #
# Sole-writer shell (the ONLY write path) and the fail-soft nudge shell.
# --------------------------------------------------------------------------- #
def _run_state_writer(subcmd_args, state_dir, timeout=25):
    """Invoke anthology_state.py <subcmd> --state-dir DIR --json ... . Returns
    (rc, parsed_json_or_None, stderr_text). Mirrors intake_router._run_writer."""
    if not STATE_WRITER.exists():
        raise GateHeld("sole writer missing: %s" % STATE_WRITER)
    argv = [sys.executable or "python3", str(STATE_WRITER),
            subcmd_args[0], "--state-dir", str(state_dir), "--json"] + list(subcmd_args[1:])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise GateHeld("sole writer timed out (%ss): %s" % (timeout, subcmd_args[0]))
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except ValueError:
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def _fire_nudge(template, subject_key, gate_id, gate_link, state_dir, config_path):
    """Fire ONE nudge through nudge_send.py, FAIL-SOFT. A nudge is a courtesy: its
    failure NEVER blocks the gate (the ledger holds the cursor and the operator can
    re-send). Returns the nudge_send exit code, or None if it could not be run."""
    if not NUDGE_SEND.exists():
        return None
    argv = [sys.executable or "python3", str(NUDGE_SEND), "send",
            "--template", template, "--subject-key", subject_key,
            "--state-dir", str(state_dir), "--json"]
    if gate_id:
        argv += ["--gate", gate_id]
    if gate_link:
        argv += ["--gate-link", gate_link]
    if config_path:
        argv += ["--config", config_path]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=25)
        return proc.returncode
    except (subprocess.SubprocessError, OSError):
        return None


def _fire_release_tag(slug, subject_key, cfg, registry_location=None):
    """Stamp the §3 release slug on the participant's Convert and Flow contact by
    shelling caf_delivery.py add-tag (the SOLE tag writer: its own byte read-back +
    idempotency + tenant guard). FAIL-SOFT, exactly like a nudge -- a Convert and
    Flow blip must NEVER block or unwind a committed gate decision (SPEC 7.2); the
    tag is idempotent so a held/failed stamp is safely re-fired by the daily tick or
    the operator. The contact id is the participant_key's contact half (KEYING LAW:
    contact_id::anthology_id). Returns (status, detail) where status is one of
    'stamped' | 'held' | 'skipped' | 'failed_nonfatal' | 'disabled'."""
    if ((cfg.get("gates") or {}).get("release_tag_on_approve")) is False:
        return "disabled", "release_tag_on_approve is false in config"
    if KEY_DELIM not in subject_key:
        return "skipped", "subject is not a participant_key; no single contact to tag"
    contact_id = subject_key.split(KEY_DELIM, 1)[0]
    if not contact_id:
        return "skipped", "empty contact id"
    if not CAF_DELIVERY.exists():
        return "skipped", "caf_delivery.py not present on this box"
    argv = [sys.executable or "python3", str(CAF_DELIVERY), "add-tag",
            "--contact-id", contact_id, "--slug", slug]
    if registry_location:
        argv += ["--registry-location", registry_location]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        return "failed_nonfatal", "add-tag not run: %s" % type(exc).__name__
    if proc.returncode == 0:
        return "stamped", slug
    detail = ((proc.stderr or "").strip() or (proc.stdout or "").strip())[:200]
    # caf_delivery exit 3 (EX_UNREACHABLE) == unreachable / scope held: retryable.
    if proc.returncode == 3:
        return "held", detail or "add-tag held (unreachable/scope)"
    return "failed_nonfatal", detail or ("add-tag rc=%d" % proc.returncode)


def _gate_link(cfg, kind, subject_key, gate_id, token=None):
    """Build the deep link a nudge points at. Participant gates land on the token
    page; producer/assembly gates land on the board card. Bases come from config
    when present, else safe relative defaults. The token (when supplied) rides the
    participant link as a capability; it is NOT the ANTHOLOGY_GATE_TOKEN_SECRET."""
    if kind == "participant":
        base = ((cfg.get("gates") or {}).get("token_page_base_url")) or "/p/gate"
        q = "t=%s" % token if token else "s=%s&g=%s" % (subject_key, gate_id)
        sep = "&" if "?" in base else "?"
        return "%s%s%s" % (base, sep, q)
    base = ((cfg.get("board") or {}).get("card_base_url")) or "/board"
    sep = "&" if "?" in base else "?"
    return "%s%scard=%s" % (base, sep, subject_key)


def _idem_key(*parts):
    return hashlib.sha256("::".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# COMMANDS
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# ASSEMBLY status enrichment + order-confirmation (U9 assembly-finale / CC
# assembly cockpit, unit U13). cmd_status surfaces assembly_state + readiness +
# ordering under the EXACT keys the CC assembly-cockpit parser reads (see
# 59->CC assembly-cockpit-logic.ts parseAssemblyStatus/parseReadiness/
# parseOrdering); confirm_order/adjust_order persist the producer's order through
# the SOLE writer and (confirm_order) flag the S9 runner's finale write.
# --------------------------------------------------------------------------- #
def _import_s9_logic():
    """Lazily import the U9 assembly-logic module (pure stdlib at import time; the
    model router is imported only inside a routing call, never at module import) so
    gate_engine REUSES build_ordering_view as the single source of the cockpit
    ordering shape rather than re-deriving it."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import stage_s9_assembly_logic  # noqa: E402
    return stage_s9_assembly_logic


def _safe_run_key(key):
    """The SAME run-dir key sanitizer stage_s9_assembly.py uses, so gate_engine
    resolves the IDENTICAL <skill>/state/runs/s9/<safe> path the runner reads."""
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))


def _s9_run_dir(anthology_id, run_dir_override=None):
    if run_dir_override:
        return Path(run_dir_override).expanduser()
    return SKILL_DIR / "state" / "runs" / "s9" / _safe_run_key(anthology_id)


def _loads_json_list(raw):
    """Parse --order (a JSON array string, or a passthrough list). Junk -> []."""
    if not raw:
        return []
    if isinstance(raw, list):
        return list(raw)
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return list(val) if isinstance(val, list) else []


def _assembly_readiness(anthology_id, state_dir):
    """The AUTHORITATIVE S9 readiness report (anthology_state assembly-readiness-
    report; READ-ONLY -- no second writer). Returns the readiness dict (envelope
    keys stripped; the shape parseReadiness consumes) or None if unavailable."""
    try:
        rc, parsed, _err = _run_state_writer(
            ["assembly-readiness-report", "--anthology-id", anthology_id], state_dir)
    except GateHeld:
        return None
    if rc == EX_OK and isinstance(parsed, dict):
        return {k: v for k, v in parsed.items()
                if k not in ("ok", "action", "read_only")}
    return None


def _chapters_meta_from_bundle(anthology_id, state_dir):
    """Ledger chapter facts (locked title + contributor name) for the ordering
    FALLBACK, from the read-only export bundle. word_count/tone are not ledger
    columns (they ride the ae-01 cockpit_view), so the fallback leaves them null --
    parseSlot accepts null for both."""
    try:
        rc, parsed, _err = _run_state_writer(
            ["export-bundle", "--anthology-id", anthology_id], state_dir)
    except GateHeld:
        return []
    if rc != EX_OK or not isinstance(parsed, dict):
        return []
    meta = []
    for m in (parsed.get("participants") or []):
        if not isinstance(m, dict):
            continue
        meta.append({
            "participant_key": m.get("participant_key"),
            "chapter_title": m.get("title_locked"),
            "title_locked": m.get("title_locked"),
            "first_name": m.get("first_name"),
            "last_name": m.get("last_name"),
        })
    return meta


def _read_cockpit_view_file(anthology_id, run_dir_override=None):
    """The DESIGNED cockpit ordering read path: the durable order_proposal.json the
    S9 runner persists from build_ordering_view (order + per-slot rationale). Returns
    the parsed view (already the CC ordering shape) or None if absent/unreadable."""
    p = _s9_run_dir(anthology_id, run_dir_override) / "working" / "order_proposal.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if isinstance(data, dict) and (data.get("slots") is not None
                                   or data.get("order") is not None):
        return data
    return None


def _assembly_ordering(anthology_id, row, state_dir, run_dir_override=None):
    """The U9 ordering view for the CC cockpit -- build_ordering_view's shape:
    {order, slots[{position, participant_key, chapter_title, contributor_name,
    word_count, tone, rationale}], overall_rationale}. Prefers the persisted cockpit
    view (carries the ae-01 rationale); else derives a minimal view from the ledger
    chapter_order + chapter facts; else None (no order yet -> the cockpit's honest
    'pending' state)."""
    view = _read_cockpit_view_file(anthology_id, run_dir_override)
    if view is not None:
        return view
    order = _loads_json_list(row.get("chapter_order"))
    if not order:
        return None
    try:
        logic = _import_s9_logic()
        return logic.build_ordering_view(
            order, [], "", _chapters_meta_from_bundle(anthology_id, state_dir))
    except Exception:  # noqa: BLE001 -- ordering is best-effort enrichment
        return None


def _enrich_assembly_status(base, anthology_id, row, spec, state_dir, run_dir_override):
    """Add assembly_state + readiness + ordering (and, in the ordering window, the
    board order actions) to a status payload for an ANTHOLOGY subject, under the
    EXACT keys the CC assembly-cockpit parser reads. Participant subjects untouched."""
    st = row.get("assembly_state")
    base["assembly_state"] = st
    readiness = _assembly_readiness(anthology_id, state_dir)
    if readiness is not None:
        base["readiness"] = readiness
    ordering = _assembly_ordering(anthology_id, row, state_dir, run_dir_override)
    if ordering is not None:
        base["ordering"] = ordering
    # In the ordering window resolve_open_gate surfaces NO GateSpec; advertise the
    # board-door order actions so the cockpit knows confirm/adjust are available.
    if spec is None and st in ORDER_WINDOW_STATES:
        base["actor"] = "producer"
        base["doors"] = ["board"]
        base["actions"] = list(ASSEMBLY_ORDER_ACTIONS)


def cmd_status(args):
    """Read-only: report the open gate for a subject and the actions its doors may
    present (the gate state machine surfaced for the token page / board to render).
    For an ANTHOLOGY (assembly) subject it ALSO surfaces assembly_state + readiness
    + ordering (U9 cockpit_view) under the keys the CC assembly cockpit consumes.
    No token needed; never writes."""
    state_dir = resolve_state_dir(args)
    resolved = resolve_open_gate(args.subject_key, state_dir)
    if resolved is None:
        return _emit({"ok": False, "action": "status", "subject_key": args.subject_key,
                      "open_gate": None, "reason": "unknown_subject"}, args.json), EX_GATE
    kind, row, spec = resolved
    if spec is None:
        base = {"ok": True, "action": "status", "subject_key": args.subject_key,
                "kind": kind, "open_gate": None,
                "note": "subject present but not at an open gate"}
    else:
        doors = ["token", "board"] if spec.door_kind == "participant" else ["board"]
        base = {"ok": True, "action": "status", "subject_key": args.subject_key,
                "kind": kind, "open_gate": spec.gate_id, "actor": spec.actor,
                "doors": doors, "actions": list(spec.actions)}
    if kind == "anthology" and row is not None:
        _enrich_assembly_status(base, args.subject_key, row, spec, state_dir,
                                getattr(args, "run_dir", None))
    return _emit(base, args.json), EX_OK


def cmd_mint(args):
    """Mint a scoped token + PIN for the subject's CURRENT open participant gate. The
    Command Center calls this to build the token-page link; the ANTHOLOGY_GATE_TOKEN_
    SECRET is never emitted, only the derived capability token/PIN are."""
    cfg = _load_config(args.config)
    label, secret = _resolve_secret(cfg)
    if not secret:
        return _emit({"ok": False, "action": "mint", "reason": "secret_not_set",
                      "secret_label": label, "secret_status": "NOT SET",
                      "note": "gate-token secret unavailable; held"}, args.json), EX_GATE
    resolved = resolve_open_gate(args.subject_key, resolve_state_dir(args))
    if resolved is None or resolved[2] is None:
        return _emit({"ok": False, "action": "mint", "subject_key": args.subject_key,
                      "reason": "no_open_gate"}, args.json), EX_GATE
    kind, _row, spec = resolved
    if spec.door_kind != "participant":
        return _emit({"ok": False, "action": "mint", "subject_key": args.subject_key,
                      "open_gate": spec.gate_id, "reason": "not_a_participant_gate",
                      "note": "producer / assembly gates are board-door only; no token"},
                     args.json), EX_REFUSE
    token, payload = mint_token(args.subject_key, spec.gate_id, secret,
                                ttl_seconds=_ttl_seconds(cfg))
    pin = mint_pin(args.subject_key, spec.gate_id, payload["exp"], secret)
    link = _gate_link(cfg, "participant", args.subject_key, spec.gate_id, token=token)
    out = {"ok": True, "action": "mint", "subject_key": args.subject_key,
           "gate": spec.gate_id, "token": token, "pin": pin,
           "expires_at": payload["exp"], "gate_link": link,
           "secret_label": label, "secret_status": "SET"}
    return _emit(out, args.json), EX_OK


def _verify_material(args, cfg, secret, expected_gate=None):
    """Shared verify path for a --token or a (--pin + --exp) credential, scoped to
    the subject and (optionally) an expected gate. Returns the verify dict."""
    if args.token:
        return verify_token(args.token, secret,
                            expected_pk=args.subject_key, expected_gate=expected_gate)
    if args.pin:
        if not args.exp:
            return {"ok": False, "reason": "malformed"}
        gate = expected_gate or args.gate
        if not gate:
            return {"ok": False, "reason": "malformed"}
        return verify_pin(args.subject_key, gate, args.exp, args.pin, secret)
    return {"ok": False, "reason": "no_credential"}


def cmd_verify(args):
    """Verify a token/PIN (NON-consuming) so the token page can decide whether to
    render the gate. Scoped to the subject and, when the subject is at an open gate,
    to that gate. Refusal is AF-AE-TOKEN-REFUSED (exit 2)."""
    cfg = _load_config(args.config)
    label, secret = _resolve_secret(cfg)
    if not secret:
        return _emit({"ok": False, "action": "verify", "reason": "secret_not_set",
                      "secret_label": label, "secret_status": "NOT SET"}, args.json), EX_GATE
    expected_gate = None
    resolved = resolve_open_gate(args.subject_key, resolve_state_dir(args))
    if resolved and resolved[2] is not None:
        expected_gate = resolved[2].gate_id
    v = _verify_material(args, cfg, secret, expected_gate=expected_gate)
    if not v.get("ok"):
        return _emit({"ok": False, "action": "verify", "valid": False,
                      "subject_key": args.subject_key, "reason": v.get("reason"),
                      "code": "AF-AE-TOKEN-REFUSED"}, args.json), EX_REFUSE
    return _emit({"ok": True, "action": "verify", "valid": True,
                  "subject_key": args.subject_key, "gate": v.get("gate"),
                  "expires_at": v.get("exp")}, args.json), EX_OK


def cmd_open(args):
    """Open the gate the subject has just reached: mint the participant token (for
    participant gates) and fire ONE gate-open nudge, then STOP (SPEC 2.1). The cursor
    is already at the gate (a stage runner set it via advance-stage); opening does
    NOT move state. Idempotent to re-run: it re-mints and re-nudges (best-effort).
    The raw token is NOT returned here (call `mint` for that) so it never lands in an
    operator log; the nudge link carries it to the participant."""
    cfg = _load_config(args.config)
    state_dir = resolve_state_dir(args)
    resolved = resolve_open_gate(args.subject_key, state_dir)
    if resolved is None or resolved[2] is None:
        return _emit({"ok": False, "action": "open", "subject_key": args.subject_key,
                      "reason": "no_open_gate"}, args.json), EX_GATE
    kind, _row, spec = resolved
    link, token_minted = None, False
    if spec.door_kind == "participant":
        label, secret = _resolve_secret(cfg)
        if not secret:
            return _emit({"ok": False, "action": "open", "subject_key": args.subject_key,
                          "open_gate": spec.gate_id, "reason": "secret_not_set",
                          "secret_label": label, "secret_status": "NOT SET"},
                         args.json), EX_GATE
        token, _payload = mint_token(args.subject_key, spec.gate_id, secret,
                                     ttl_seconds=_ttl_seconds(cfg))
        link = _gate_link(cfg, "participant", args.subject_key, spec.gate_id, token=token)
        token_minted = True
    else:
        link = _gate_link(cfg, "producer", args.subject_key, spec.gate_id)
    nudge_rc = None
    if not args.no_nudge:
        nudge_rc = _fire_nudge("gate-open", args.subject_key, spec.gate_id, link,
                               state_dir, args.config)
    return _emit({"ok": True, "action": "open", "subject_key": args.subject_key,
                  "kind": kind, "gate": spec.gate_id, "token_minted": token_minted,
                  "nudge": ("sent" if nudge_rc == 0 else
                            "skipped" if args.no_nudge else "failed_nonfatal"),
                  "nudge_rc": nudge_rc}, args.json), EX_OK


def cmd_decide(args):
    """THE both-door gate endpoint. door=token (participant nudge link) and
    door=board (producer session) resolve here to the IDENTICAL anthology_state.py
    record-approval call. A token/PIN is required and single-use-consumed on the
    token door; the board door trusts the Command Center session (own-producer id
    required for the S9 gates).

    Token refusals -- FOREIGN (wrong participant or wrong gate), EXPIRED, forged, or
    REPLAYED (a nonce already committed, EVEN after the gate has closed) -- all exit
    2 (AF-AE-TOKEN-REFUSED). A never-used token whose gate has simply closed exits 3
    (gate not open). This ordering is why a sequential replay is refused as a token
    error rather than masquerading as a closed gate."""
    cfg = _load_config(args.config)
    state_dir = resolve_state_dir(args)

    if args.door not in DOOR_VALUE:
        return _emit({"ok": False, "action": "decide", "reason": "unknown_door",
                      "note": "door must be token or board"}, args.json), EX_REFUSE

    # ASSEMBLY ORDER board actions (confirm_order / adjust_order) take their OWN
    # path: they act during the ordering window where resolve_open_gate surfaces no
    # single GateSpec, they carry order/opener/closer (not a token/PIN), and they
    # persist through assembly-set-order (the sole writer) rather than record-
    # approval. The both-door rule is preserved: board-door + own-producer only.
    if args.action in ASSEMBLY_ORDER_ACTIONS:
        return _decide_assembly_order(args, cfg, state_dir)

    def refuse(reason, code=None, extra=None, rc=EX_REFUSE):
        out = {"ok": False, "action": "decide", "subject_key": args.subject_key,
               "reason": reason}
        if code:
            out["code"] = code
        if extra:
            out.update(extra)
        return _emit(out, args.json), rc

    # --- 1. TOKEN-door credential verification, BEFORE gate resolution, so a
    #        credential scoped to a now-closed gate is still classified honestly.
    verified = None      # the verify dict for a token credential
    nonce = None         # the single-use handle (token jti, or a PIN tag)
    if args.door == "token":
        label, secret = _resolve_secret(cfg)
        if not secret:
            return refuse("secret_not_set", extra={"secret_label": label,
                          "secret_status": "NOT SET"}, rc=EX_GATE)
        if args.token:
            # verify signature/expiry/subject now; gate scope is checked against the
            # OPEN gate below (so we can tell replay from foreign-gate).
            verified = verify_token(args.token, secret, expected_pk=args.subject_key)
            if not verified.get("ok"):
                return refuse(verified.get("reason"), code="AF-AE-TOKEN-REFUSED")
            nonce = verified.get("jti") or _idem_key(
                args.subject_key, verified.get("gate"), verified.get("exp"))
        elif args.pin:
            # a PIN is not self-describing; the client carries its (gate, exp). Derive
            # the same nonce early so a replay is caught even after the gate closes.
            if args.gate and args.exp:
                try:
                    nonce = _idem_key(args.subject_key, args.gate, int(args.exp))
                except (TypeError, ValueError):
                    nonce = None
        else:
            return refuse("no_credential", code="AF-AE-TOKEN-REFUSED")

    # --- 2. resolve the open gate (the state machine projection).
    resolved = resolve_open_gate(args.subject_key, state_dir)
    spec = resolved[2] if resolved else None
    kind = resolved[0] if resolved else None

    if spec is None:
        # No open gate. A token whose nonce was already committed is a REPLAY (exit
        # 2); an unused token whose gate has merely closed is gate-not-open (exit 3).
        if nonce is not None and NonceStore(state_dir).consumed(nonce):
            return refuse("replayed", code="AF-AE-TOKEN-REFUSED")
        return refuse("no_open_gate", rc=EX_GATE)

    # --- 3. token gate scope: the credential must be for THE open gate.
    if args.door == "token":
        if args.token:
            if verified.get("gate") != spec.gate_id:
                if NonceStore(state_dir).consumed(nonce):
                    return refuse("replayed", code="AF-AE-TOKEN-REFUSED",
                                  extra={"open_gate": spec.gate_id})
                return refuse("foreign_gate", code="AF-AE-TOKEN-REFUSED",
                              extra={"open_gate": spec.gate_id})
        else:  # PIN credential: verify against the open gate now.
            _label, secret = _resolve_secret(cfg)
            v = _verify_material(args, cfg, secret, expected_gate=spec.gate_id)
            if not v.get("ok"):
                if v.get("reason") == "expired" and NonceStore(state_dir).consumed(
                        _idem_key(args.subject_key, spec.gate_id, args.exp)):
                    return refuse("replayed", code="AF-AE-TOKEN-REFUSED")
                return refuse(v.get("reason"), code="AF-AE-TOKEN-REFUSED",
                              extra={"open_gate": spec.gate_id})
            nonce = _idem_key(args.subject_key, spec.gate_id, v.get("exp"))

    # --- 4. the action must be one this gate presents.
    if args.action not in spec.actions:
        return refuse("action_not_allowed_at_gate",
                      extra={"open_gate": spec.gate_id, "requested": args.action,
                             "allowed": list(spec.actions)})

    # --- 5. door legality: producer / assembly gates are board-door only.
    if spec.door_kind != "participant" and args.door != "board":
        return refuse("door_not_allowed_for_gate",
                      extra={"open_gate": spec.gate_id,
                             "note": "producer and assembly gates are board-door only"})

    # --- 6. required fields for the action.
    decision, required = ACTION_DECISION[args.action]
    missing = [f for f in required if not getattr(args, f, None)]
    if missing:
        return refuse("missing_fields",
                      extra={"open_gate": spec.gate_id, "fields": missing})

    # --- 7. token-door single-use claim, then the SHARED record-approval call.
    store = None
    if args.door == "token":
        store = NonceStore(state_dir)
        if store.consumed(nonce) or not store.claim(nonce, args.subject_key, spec.gate_id):
            store.close()
            return refuse("replayed", code="AF-AE-TOKEN-REFUSED",
                          extra={"open_gate": spec.gate_id})
    rc = EX_ERR
    out = None
    try:
        rc, out = _do_record_approval(args, spec, kind, decision, cfg)
    finally:
        # keep the claim consumed only on a committed write; release it otherwise so
        # a corrected retry with the same token is allowed.
        if store is not None:
            if rc_uncommitted(out):
                store.release(nonce)
            store.close()

    # --- 8. RELEASE-TAG BUS: on a COMMITTED board-door PRODUCER approve, stamp the
    #        stage's §3 release slug on the participant's contact (SPEC §3). FAIL-SOFT
    #        -- a Convert and Flow blip never unwinds the already-committed decision;
    #        the tag is idempotent and re-fireable. The stamp status is surfaced to
    #        the operator (board) so a held/failed release can be re-fired.
    if out and out.get("committed") and not getattr(args, "no_release_tag", False):
        slug = release_slug_for(spec, args.action, args.door, True)
        if slug:
            r_status, r_detail = _fire_release_tag(
                slug, args.subject_key, cfg,
                registry_location=getattr(args, "registry_location", None))
            out["release_tag"] = {"slug": slug, "status": r_status, "detail": r_detail}
            if r_status in ("held", "failed_nonfatal"):
                sys.stderr.write("[gate_engine] release-tag %s: %s (%s)\n"
                                 % (r_status, slug, r_detail))
    return _emit(out, args.json), rc


def _flag_runner_confirm_order(anthology_id, order, opener, closer, producer_id,
                               run_dir_override=None):
    """Set the S9 runner's request.confirm_order so its NEXT invocation writes U9's
    inter-chapter transitions + Grand Finale (stage_s9_assembly.py reads
    request.get('confirm_order') to gate the final edition). This is the runner's
    per-call CONTROL file, NOT the domain ledger -- the order itself was persisted by
    the sole writer above -- so it is NO second ledger writer. Existing request.json
    fields (an arm's producer_id / confirm_name / producer_inputs) are PRESERVED so
    the runner still has the typed-name confirmation it needs. Returns (ok, detail)."""
    try:
        run_dir = _s9_run_dir(anthology_id, run_dir_override)
        req_path = run_dir / "request.json"
        data = {}
        if req_path.is_file():
            try:
                loaded = json.loads(req_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (ValueError, OSError):
                data = {}
        data["confirm_order"] = True
        data["order"] = list(order)
        if opener:
            data["opener"] = opener
        if closer:
            data["closer"] = closer
        if producer_id:
            data["producer_id"] = producer_id
        run_dir.mkdir(parents=True, exist_ok=True)
        req_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        return True, str(req_path)
    except OSError as exc:
        return False, "could not write request.json: %s" % type(exc).__name__


def _decide_assembly_order(args, cfg, state_dir):
    """The producer's 'Confirm the finalized set & order' (confirm_order) and the
    free-reorder 'adjust_order' board actions. PERSISTS the producer's running order
    through the SOLE writer (anthology_state assembly-set-order --state adjusted) and,
    for confirm_order, sets the S9 runner's request.confirm_order so its next pass
    writes U9's inter-chapter transitions + Grand Finale. Board-door + own-producer
    only. Exit-code map is byte-consistent with the both-door endpoint: 0 recorded,
    2 guard/validation refusal, 3 gate-not-open."""
    finale = args.action == FINALE_TRIGGER_ACTION

    def refuse(reason, extra=None, rc=EX_REFUSE):
        out = {"ok": False, "action": "decide", "subject_key": args.subject_key,
               "requested": args.action, "reason": reason, "committed": False}
        if extra:
            out.update(extra)
        return _emit(out, args.json), rc

    # board-door only (producer/assembly actions never ride the participant token).
    if args.door != "board":
        return refuse("door_not_allowed_for_gate",
                      {"note": "confirm_order/adjust_order are board-door only"})
    # the subject is an anthology_id (KEYING LAW: a participant_key contains '::').
    if KEY_DELIM in args.subject_key:
        return refuse("not_an_assembly_subject",
                      {"note": "order actions act on an anthology_id, not a participant"})
    order = _loads_json_list(getattr(args, "order", None))
    if not order:
        return refuse("missing_fields", {"fields": ["order"]})
    if len(order) != len(set(order)):
        return refuse("order_has_duplicates")
    # opener/closer, when supplied, must be consistent with the order sequence.
    if args.opener and order[0] != args.opener:
        return refuse("opener_not_first", {"opener": args.opener, "order_head": order[0]})
    if args.closer and order[-1] != args.closer:
        return refuse("closer_not_last", {"closer": args.closer, "order_tail": order[-1]})
    # resolve the anthology (read-only) for own-producer auth + the state window.
    resolved = resolve_open_gate(args.subject_key, state_dir)
    if resolved is None or resolved[1] is None or resolved[0] != "anthology":
        return refuse("unknown_subject", rc=EX_GATE)
    row = resolved[1]
    # own-producer auth (mirrors the s9 gates' _require_producer; the CC route sets
    # --producer-id from the Cf-Access session, never a client-supplied body field).
    if not args.producer_id:
        return refuse("missing_fields", {"fields": ["producer_id"]})
    if str(args.producer_id) != str(row.get("producer_id") or ""):
        return refuse("not_owning_producer",
                      {"note": "order actions are own-producer only"})
    # the ordering window: an order may be (re)persisted ONLY while assembly is
    # ready_confirmed/proposed/adjusted. Before it there is no armed order; after
    # compile the edition is closed. Either is 'gate not open' (exit 3).
    st = row.get("assembly_state")
    if st not in ORDER_WINDOW_STATES:
        return refuse("gate_not_open",
                      {"assembly_state": st,
                       "note": "confirm the order only during the armed->compiled "
                               "ordering window (ready_confirmed/proposed/adjusted)"},
                      rc=EX_GATE)
    # PERSIST through the SOLE writer (assembly-set-order --state adjusted). The
    # writer re-validates the order is a permutation of the staged, approved, frozen
    # set and is the ONLY code path that writes chapter_order.
    sub = ["assembly-set-order", "--anthology-id", args.subject_key,
           "--order", json.dumps(order), "--state", "adjusted"]
    try:
        rc, parsed, stderr = _run_state_writer(sub, state_dir)
    except GateHeld as exc:
        return refuse("sole_writer_held", {"detail": str(exc)}, rc=EX_GATE)
    if rc == 5:                       # writer VALIDATION: not a permutation of the set
        return refuse("order_not_a_permutation",
                      {"detail": (parsed or {}).get("error") or stderr})
    if rc not in (EX_OK, 4):          # 2 illegal transition / 3 unknown / anything else
        return refuse("gate_not_open",
                      {"writer_rc": rc, "detail": (parsed or {}).get("error") or stderr},
                      rc=EX_GATE)
    out = {"ok": True, "action": "decide", "subject_key": args.subject_key,
           "door": DOOR_VALUE[args.door], "decision": args.action, "committed": True,
           "assembly_state": (parsed or {}).get("assembly_state", "adjusted"),
           "order_len": (parsed or {}).get("order_len", len(order))}
    if rc == 4:
        out["base_queued"] = True
        out["note"] = "base unreachable; order write queued to the local mirror"
    # confirm_order ALSO flags the S9 runner to write the final edition (U9 finale).
    if finale:
        flagged, detail = _flag_runner_confirm_order(
            args.subject_key, order, args.opener, args.closer, args.producer_id,
            getattr(args, "run_dir", None))
        out["confirm_order"] = {"flagged": flagged, "detail": detail}
        if not flagged:
            sys.stderr.write("[gate_engine] confirm_order: order persisted but the "
                             "runner request flag could not be set: %s\n" % detail)
    return _emit(out, args.json), EX_OK


def rc_uncommitted(out):
    """A decide result whose sole-writer call changed nothing (so a replay nonce may
    be released for a corrected retry)."""
    return bool(out) and out.get("committed") is False


def _do_record_approval(args, spec, kind, decision, cfg):
    """Assemble and run the SINGLE record-approval call both doors share. Returns
    (exit_code, output_dict)."""
    door_val = DOOR_VALUE[args.door]
    idem = args.idempotency_key or _idem_key(
        args.subject_key, spec.gate_id, args.door, args.action,
        args.title or "", args.notes or "", args.producer_id or "")
    sub = ["record-approval", "--gate", spec.gate_id, "--door", door_val,
           "--idempotency-key", idem]

    if spec.gate_id in ("s9_ready", "s9_producer"):
        sub += ["--anthology-id", args.subject_key, "--producer-id", args.producer_id]
        if spec.gate_id == "s9_ready":
            sub += ["--decision", "ready_to_assemble", "--confirm-name", args.confirm_name]
        else:
            sub += ["--decision", "approve"]
    else:
        sub += ["--participant-key", args.subject_key, "--decision", decision]
        if args.title:
            sub += ["--title", args.title]
        if args.subtitle:
            sub += ["--subtitle", args.subtitle]
        if args.notes:
            sub += ["--notes", args.notes]
        if decision == "hold" and args.reason:
            sub += ["--reason", args.reason]

    try:
        rc, parsed, stderr = _run_state_writer(sub, resolve_state_dir(args))
    except GateHeld as exc:
        return EX_GATE, {"ok": False, "action": "decide", "reason": "sole_writer_held",
                         "detail": str(exc), "committed": False}

    base = {"action": "decide", "subject_key": args.subject_key, "door": door_val,
            "gate": spec.gate_id, "decision": decision}
    # Map the sole-writer exit code to this endpoint's contract.
    if rc == 0:
        base.update({"ok": True, "committed": True,
                     "approval_id": (parsed or {}).get("approval_id"),
                     "stage_cursor": (parsed or {}).get("stage_cursor"),
                     "noop": bool((parsed or {}).get("noop"))})
        return EX_OK, base
    if rc == 4:
        # base unreachable, write durably QUEUED to the mirror: the gate action
        # succeeded from the participant's view -- a network blip never blocks a
        # gate (SPEC 7.2). Surfaced as OK with base_queued for the operator.
        base.update({"ok": True, "committed": True, "base_queued": True,
                     "note": "base unreachable; write queued to the local mirror"})
        return EX_OK, base
    if rc == 5:
        base.update({"ok": False, "committed": False, "reason": "validation_mismatch",
                     "detail": (parsed or {}).get("error") or stderr})
        return EX_REFUSE, base
    # rc 2 (illegal transition) / rc 3 (unknown key) / anything else: the gate is
    # not open for this action.
    base.update({"ok": False, "committed": False, "reason": "gate_not_open",
                 "writer_rc": rc, "detail": (parsed or {}).get("error") or stderr})
    return EX_GATE, base


# --------------------------------------------------------------------------- #
# SELF-TEST (pure: crypto round-trips + refusals + table invariants + code map;
# no ledger, no network, no secret env required).
# --------------------------------------------------------------------------- #
def self_test():
    secret = "unit-test-secret-not-a-real-credential"
    pk = "contactSYN0001::ANTHsynthetic0001"

    # exit-code identities
    assert (EX_OK, EX_ERR, EX_REFUSE, EX_GATE) == (0, 1, 2, 3)

    # THE CHAPTER GATE PRESENTS EXACTLY TWO ACTIONS (SPEC S5).
    s5 = GATE_BY_CURSOR["s5_gate"]
    assert s5.gate_id == "s5_participant"
    assert s5.actions == ("approve_as_is", "request_rewrite_with_notes"), s5.actions
    assert len(s5.actions) == 2

    # every gate action maps to a known sole-writer decision.
    for g in GATE_BY_CURSOR.values():
        for act in g.actions:
            assert act in ACTION_DECISION, act
    # participant token gates are exactly the participant-door gates.
    assert PARTICIPANT_GATE_IDS == {"s3_selection", "s4_participant", "s5_participant"}

    # mint -> verify round trip (fixed clock).
    t0 = 1_000_000
    tok, payload = mint_token(pk, "s5_participant", secret, ttl_seconds=3600, now=t0)
    ok = verify_token(tok, secret, expected_pk=pk, expected_gate="s5_participant", now=t0)
    assert ok["ok"] and ok["pk"] == pk and ok["gate"] == "s5_participant", ok
    assert payload["exp"] == t0 + 3600

    # FOREIGN SUBJECT refused.
    assert verify_token(tok, secret, expected_pk="other::x", now=t0)["reason"] == \
        "foreign_subject"
    # FOREIGN GATE refused (single-gate scope).
    assert verify_token(tok, secret, expected_gate="s3_selection", now=t0)["reason"] == \
        "foreign_gate"
    # EXPIRED refused.
    assert verify_token(tok, secret, now=t0 + 3601)["reason"] == "expired"
    # FORGED / wrong-secret refused (this is how a foreign or tampered token dies).
    assert verify_token(tok, "a-different-secret", now=t0)["reason"] == "bad_signature"
    # TAMPERED payload refused.
    parts = tok.split(".")
    bad = ".".join([parts[0], parts[1][:-2] + ("AA" if parts[1][-2:] != "AA" else "BB"),
                    parts[2]])
    assert verify_token(bad, secret, now=t0)["reason"] in ("bad_signature", "malformed")
    # MALFORMED refused.
    assert verify_token("not-a-token", secret, now=t0)["reason"] == "malformed"
    assert verify_token("v1.only-two-parts", secret, now=t0)["reason"] == "malformed"

    # PIN round trip + refusals.
    pin = mint_pin(pk, "s5_participant", payload["exp"], secret)
    assert len(pin) == 8 and pin.isdigit()
    assert verify_pin(pk, "s5_participant", payload["exp"], pin, secret, now=t0)["ok"]
    assert not verify_pin(pk, "s5_participant", payload["exp"], "00000000", secret,
                          now=t0)["ok"]
    assert verify_pin(pk, "s5_participant", payload["exp"], pin, secret,
                      now=payload["exp"] + 1)["reason"] == "expired"
    # a PIN is bound to its gate: the same material at another gate does not verify.
    assert not verify_pin(pk, "s3_selection", payload["exp"], pin, secret, now=t0)["ok"]

    # door provenance mapping is exactly the two sole-writer door values.
    assert set(DOOR_VALUE.values()) == {"nudge_link", "dashboard"}

    # link builder shapes (no config -> safe relative defaults).
    assert _gate_link({}, "participant", pk, "s5_participant", token="TOK").startswith("/p/gate?t=")
    assert _gate_link({}, "producer", pk, "s2_producer").startswith("/board?card=")

    # RELEASE-TAG BUS (SPEC §3): the slug map + the pure release decision.
    # every PRODUCER gate that exists today carries a §3 release slug.
    for _cursor, g in GATE_BY_CURSOR.items():
        if g.door_kind == "producer":
            assert g.gate_id in GATE_RELEASE_SLUG, (g.gate_id, "producer gate missing a release slug")
    # the exact §3 slugs for the three live producer gates.
    assert GATE_RELEASE_SLUG["s1_producer"] == "anthology-release-avatar"
    assert GATE_RELEASE_SLUG["s2_producer"] == "anthology-release-tone"
    assert GATE_RELEASE_SLUG["s4_producer"] == "anthology-release-outline"
    # every slug is the exact §3 shape (anthology-release-*).
    assert all(s.startswith("anthology-release-") for s in GATE_RELEASE_SLUG.values())
    # THE decision: a committed board-door producer approve -> the correct slug.
    s1 = GATE_BY_CURSOR["s1_gate"]
    assert release_slug_for(s1, "approve", "board", True) == "anthology-release-avatar"
    assert release_slug_for(GATE_BY_CURSOR["s2_gate"], "approve", "board", True) == "anthology-release-tone"
    assert release_slug_for(GATE_BY_CURSOR["s4_gate_producer"], "approve", "board", True) == "anthology-release-outline"
    # NOT a release: token door, uncommitted, a non-approve action, or a participant gate.
    assert release_slug_for(s1, "approve", "token", True) is None      # token door never releases
    assert release_slug_for(s1, "approve", "board", False) is None     # uncommitted
    assert release_slug_for(s1, "hold", "board", True) is None         # hold is not a release
    assert release_slug_for(s1, "exclude", "board", True) is None
    assert release_slug_for(GATE_BY_CURSOR["s5_gate"], "approve_as_is", "board", True) is None  # participant chapter approve
    assert release_slug_for(GATE_BY_CURSOR["s3_gate"], "select", "board", True) is None         # participant title-select
    assert release_slug_for(GATE_BY_CURSOR["s4_gate_participant"], "approve", "board", True) is None  # participant gate
    # assembly gates key on an anthology_id, not a contact -> no per-contact release.
    _s9r = GateSpec("s9_ready", "producer", "producer", ("ready_to_assemble",))
    _s9p = GateSpec("s9_producer", "producer", "producer", ("sign_off",))
    assert release_slug_for(_s9r, "ready_to_assemble", "board", True) is None
    assert release_slug_for(_s9p, "sign_off", "board", True) is None

    # --- ASSEMBLY ORDER actions (U9 assembly-finale / CC assembly cockpit) ------
    assert ASSEMBLY_ORDER_ACTIONS == ("adjust_order", "confirm_order")
    assert FINALE_TRIGGER_ACTION == "confirm_order"
    assert ORDER_WINDOW_STATES == ("ready_confirmed", "proposed", "adjusted")
    # --order parsing: a JSON array string, a passthrough list, junk -> [].
    assert _loads_json_list('["a::x","b::x"]') == ["a::x", "b::x"]
    assert _loads_json_list(["a", "b"]) == ["a", "b"]
    assert _loads_json_list("not json") == [] and _loads_json_list(None) == []
    assert _loads_json_list('{"x":1}') == []      # a non-array JSON value is not an order
    # the run-dir key sanitizer matches the runner's (so request.json paths line up).
    assert _safe_run_key("ANTH::a b/c") == "ANTH__a_b_c"
    assert str(_s9_run_dir("ANTHx")).endswith("state/runs/s9/ANTHx")
    assert str(_s9_run_dir("ANTHx", "/tmp/rd")) == "/tmp/rd"
    # a persisted cockpit view file is read back verbatim as the ordering view.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        _rd = Path(_td) / "run"
        (_rd / "working").mkdir(parents=True)
        _view = {"order": ["a::x", "b::x"],
                 "slots": [{"position": 1, "participant_key": "a::x",
                            "chapter_title": "Rise", "rationale": "opener"}],
                 "overall_rationale": "opener/closer"}
        (_rd / "working" / "order_proposal.json").write_text(
            json.dumps(_view), encoding="utf-8")
        got = _read_cockpit_view_file("ANY", run_dir_override=str(_rd))
        assert got and got["order"] == ["a::x", "b::x"] and got["slots"][0]["rationale"] == "opener"
        # absent file -> None (the cockpit's honest 'pending' ordering)
        assert _read_cockpit_view_file("ANY", run_dir_override=str(Path(_td) / "nope")) is None
    # confirm_order flags the runner's request.confirm_order, PRESERVING arm fields.
    with _tf.TemporaryDirectory() as _td:
        _rd = Path(_td) / "run"
        _rd.mkdir()
        (_rd / "request.json").write_text(
            json.dumps({"producer_id": "prodX", "confirm_name": "The Book",
                        "producer_inputs": {"why": "kept"}}), encoding="utf-8")
        ok_flag, _detail = _flag_runner_confirm_order(
            "ANTHx", ["a::x", "b::x"], "a::x", "b::x", "prodX", run_dir_override=str(_rd))
        assert ok_flag, _detail
        _req = json.loads((_rd / "request.json").read_text(encoding="utf-8"))
        assert _req["confirm_order"] is True
        assert _req["order"] == ["a::x", "b::x"]
        assert _req["opener"] == "a::x" and _req["closer"] == "b::x"
        # arm context PRESERVED, never clobbered (the runner still has confirm_name)
        assert _req["confirm_name"] == "The Book"
        assert _req["producer_inputs"] == {"why": "kept"}
    # a fresh run dir (no prior request.json) is created with just flag + order.
    with _tf.TemporaryDirectory() as _td:
        _rd = Path(_td) / "fresh"
        ok2, _ = _flag_runner_confirm_order("ANTHy", ["p::y"], None, None, "prodY",
                                            run_dir_override=str(_rd))
        assert ok2 and (_rd / "request.json").is_file()
        _req2 = json.loads((_rd / "request.json").read_text(encoding="utf-8"))
        assert _req2["confirm_order"] is True and "opener" not in _req2

    print("gate_engine self-test: OK "
          "(token mint/verify + refusals, PIN, chapter gate == 2 actions, "
          "door map, exit-code map, §3 release-tag bus, U9 order-confirm flag)")
    return EX_OK


def plan():
    print("gate_engine.py -- gate state machine + both-door endpoint + scoped token/PIN")
    print("secret label : %s (resolved live-process-env first; value never printed)"
          % DEFAULT_SECRET_LABEL)
    print("sole writer  : %s (record-approval; the ONLY state write path)" % STATE_WRITER)
    print("gates (cursor -> gate id [actor] {actions}):")
    for cursor, g in GATE_BY_CURSOR.items():
        print("  %-20s -> %-14s [%-11s] %s"
              % (cursor, g.gate_id, g.actor, ", ".join(g.actions)))
    print("assembly (state -> gate): not_ready|armed -> s9_ready ; compiled -> s9_producer")
    print("doors        : token(nudge_link) + board(dashboard); participant gates take")
    print("               both, producer/assembly gates take board only")
    print("release bus  : committed BOARD-door producer approve -> stamp §3 slug via")
    print("               caf_delivery add-tag (fail-soft, idempotent); slugs:")
    for gid, slug in GATE_RELEASE_SLUG.items():
        live = "" if gid in {g.gate_id for g in GATE_BY_CURSOR.values()} else "  (engine-gated follow-on)"
        print("                 %-14s -> %s%s" % (gid, slug, live))
    print("exit codes   : 0 recorded ; 2 refusal (token/guard) ; 3 gate not open ; 1 error")
    return EX_OK


def _build_parser():
    ap = argparse.ArgumentParser(
        prog="gate_engine.py",
        description="Anthology Engine gate state machine, both-door endpoint, and "
                    "scoped participant token/PIN mint + verify.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the pure self-test (no ledger / network) and exit")
    ap.add_argument("--plan", action="store_true",
                    help="print the gate table and contract and exit")
    sub = ap.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--state-dir", dest="state_dir",
                        help="engine state dir (default: resolved like anthology_state)")
        sp.add_argument("--config", help="path to the resolved engine-config.json")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    sp = sub.add_parser("status", help="report the open gate for a subject (read-only)")
    sp.add_argument("--subject-key", dest="subject_key", required=True)
    sp.add_argument("--run-dir", dest="run_dir",
                    help="optional S9 run dir override for the cockpit ordering read "
                         "(default: <skill>/state/runs/s9/<anthology_id>)")
    common(sp)

    sp = sub.add_parser("mint", help="mint a scoped token+PIN for the open participant gate")
    sp.add_argument("--subject-key", dest="subject_key", required=True)
    common(sp)

    sp = sub.add_parser("verify", help="verify a token/PIN (non-consuming)")
    sp.add_argument("--subject-key", dest="subject_key", required=True)
    sp.add_argument("--token")
    sp.add_argument("--pin")
    sp.add_argument("--exp", help="token expiry epoch (required with --pin)")
    sp.add_argument("--gate", help="expected gate id (optional; defaults to the open gate)")
    common(sp)

    sp = sub.add_parser("open", help="mint (participant) + fire ONE gate-open nudge, then stop")
    sp.add_argument("--subject-key", dest="subject_key", required=True)
    sp.add_argument("--no-nudge", action="store_true",
                    help="open without firing the nudge (the operator will re-send)")
    common(sp)

    sp = sub.add_parser("decide", help="THE both-door gate endpoint (records a decision)")
    sp.add_argument("--subject-key", dest="subject_key", required=True)
    sp.add_argument("--door", required=True, choices=("token", "board"))
    sp.add_argument("--action", required=True)
    sp.add_argument("--token")
    sp.add_argument("--pin")
    sp.add_argument("--exp", help="token expiry epoch (required with --pin)")
    sp.add_argument("--gate", help="gate id for a PIN credential (defaults to the open gate)")
    sp.add_argument("--title")
    sp.add_argument("--subtitle")
    sp.add_argument("--notes")
    sp.add_argument("--reason", help="hold reason when action=hold")
    sp.add_argument("--confirm-name", dest="confirm_name",
                    help="typed anthology-name for the s9_ready trigger")
    sp.add_argument("--producer-id", dest="producer_id",
                    help="own-producer id (required for the s9 gates and the "
                         "confirm_order/adjust_order order actions)")
    sp.add_argument("--order",
                    help="JSON array of participant_keys in the producer's finalized "
                         "running order (confirm_order/adjust_order)")
    sp.add_argument("--opener",
                    help="the OPENER participant_key (must equal order[0]); "
                         "optional metadata for confirm_order/adjust_order")
    sp.add_argument("--closer",
                    help="the last co-author participant_key (must equal order[-1]); "
                         "optional metadata for confirm_order/adjust_order")
    sp.add_argument("--run-dir", dest="run_dir",
                    help="optional S9 run dir override for the confirm_order finale "
                         "flag (default: <skill>/state/runs/s9/<anthology_id>)")
    sp.add_argument("--idempotency-key", dest="idempotency_key")
    sp.add_argument("--registry-location", dest="registry_location",
                    help="the anthology's Convert and Flow location binding; forwarded "
                         "to the release-tag stamp for the tenant guard (optional)")
    sp.add_argument("--no-release-tag", dest="no_release_tag", action="store_true",
                    help="record the decision but do NOT stamp the §3 release tag "
                         "(dry-run / re-record without re-notifying the client)")
    common(sp)
    return ap


HANDLERS = {"status": cmd_status, "mint": cmd_mint, "verify": cmd_verify,
            "open": cmd_open, "decide": cmd_decide}


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
        _out, rc = HANDLERS[args.cmd](args)
        return rc
    except GateHeld as exc:
        sys.stderr.write("[gate_engine] held: %s\n" % exc)
        return EX_GATE
    except BrokenPipeError:
        return EX_OK
    except Exception as exc:  # noqa: BLE001 -- last-resort guard; house exit 1
        sys.stderr.write("[gate_engine] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
