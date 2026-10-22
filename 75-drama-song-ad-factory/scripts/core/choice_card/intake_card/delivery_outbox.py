#!/usr/bin/env python3
"""delivery_outbox: the typed artifact envelope + durable delivery outbox (W03-U1).

One canonical origin record and one honest delivery ledger for every artifact
the skill presents in the same chat it came from.

Origin record (``control/origin.json``), written ONCE at run creation::

    {"schema_version": 1, "tenant_id": ..., "account_id": ...,
     "channel": "telegram" | "app" | "terminal" | ...,
     "conversation_id": ..., "thread_id": ...}

The approval sender, progress reporter, Studio bridge, watchdog, Command Center
projection and final deliverer all read THIS record (``load_origin`` /
``resolve_origin``) -- they never hunt for different fields in unrelated JSON
files. ``migrate_legacy_destinations`` folds RECOGNIZED legacy destination
schemas into it, idempotently, and refuses to guess: a bare chat id with no
channel marker is recorded as ``unresolved`` (action-required), never a global
Telegram target.

Delivery states (``DELIVERY_STATES``):

``prepared``          staged (a returned JSON or written local file) -- NEVER sent
``queued``            durably in the outbox, awaiting dispatch
``sending``           dispatched to the transport, awaiting its receipt
``sent``              the channel acknowledged it (a real receipt is recorded)
``retryable_failure`` dispatch failed transiently; a resend of the SAME bytes is safe
``action_required``   permanent problem (no destination, bad destination, ...)
``uncertain``         dispatched but unproven; resolved via the channel's own
                      idempotency/readback -- never claimed exactly-once

Every text chunk and attachment is its own piece with a deterministic identity
(``piece_id``) and its own receipt, so a crash resends ONLY missing pieces.
Long lyrics/scripts split at semantic boundaries (paragraphs, then lines) with
ordered part numbers; channel size/format limits are observed with numbered
contact sheets and paginated cards. Repair only ever re-sends bytes that already
exist: no paid media is spent to repair a failed send.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

SCHEMA_VERSION = 1

#: canonical origin record, relative to the run dir
ORIGIN_FILE = os.path.join("control", "origin.json")
#: evidence of what a migration folded in / refused to guess
ORIGIN_MIGRATION_FILE = os.path.join("control", "origin-migration.json")
#: one file per delivery piece, relative to the run dir
OUTBOX_DIR = "outbox"

#: delivery states, in the contract's vocabulary
PREPARED = "prepared"
QUEUED = "queued"
SENDING = "sending"
SENT = "sent"
RETRYABLE_FAILURE = "retryable_failure"
ACTION_REQUIRED = "action_required"
UNCERTAIN = "uncertain"
DELIVERY_STATES = (PREPARED, QUEUED, SENDING, SENT, RETRYABLE_FAILURE,
                   ACTION_REQUIRED, UNCERTAIN)

#: states that still owe the channel a piece of work
PENDING_STATES = (PREPARED, QUEUED, SENDING, RETRYABLE_FAILURE, UNCERTAIN)

#: channels whose conversation binding is authenticated in the origin record.
#: The channel VALUE travels through to the transport as data -- nothing here
#: (or in channel_send) hardcodes one channel for every path.
KNOWN_CHANNELS = ("telegram", "app", "terminal", "studio", "whatsapp", "discord",
                  "slack", "imessage", "signal", "sms")

#: real size/format ceilings per channel. None = no hard text ceiling known.
CHANNEL_LIMITS = {
    "telegram": {"text_chars": 4096, "caption_chars": 1024, "media_per_message": 10},
    "app": {"text_chars": 4096, "caption_chars": 1024, "media_per_message": 10},
    "terminal": {"text_chars": None, "caption_chars": None, "media_per_message": 0},
    "studio": {"text_chars": None, "caption_chars": 1024, "media_per_message": 20},
}
DEFAULT_LIMITS = CHANNEL_LIMITS["app"]


class OriginConflict(ValueError):
    """Two different origin records claim the same run. Resolution must come
    from the existing authenticated session -- never a guess."""


class OutboxError(ValueError):
    """The outbox record is unknown or inconsistent. Loud, never silent."""


# ----------------------------------------------------------------- helpers ---

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------ origin record ---

def origin_record(tenant_id="", account_id="", channel="", conversation_id="",
                  thread_id=""):
    """Validate and normalize one origin record. The channel must be named --
    a record never carries a guessed default."""
    rec = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": (tenant_id or "").strip(),
        "account_id": (account_id or "").strip(),
        "channel": (channel or "").strip(),
        "conversation_id": (conversation_id or "").strip(),
        "thread_id": (thread_id or "").strip(),
    }
    if not rec["channel"]:
        raise OutboxError("origin record needs an explicit channel; refusing to guess one")
    return rec


def origin_path(run_dir):
    return os.path.join(run_dir, ORIGIN_FILE)


def save_origin(run_dir, rec):
    """Persist the canonical origin record ONCE at run creation. Idempotent for
    the same record; a DIFFERENT record raises :class:`OriginConflict` (the
    existing authenticated session resolves it, never a guess)."""
    rec = origin_record(**{k: rec.get(k, "") for k in
                           ("tenant_id", "account_id", "channel",
                            "conversation_id", "thread_id")})
    path = origin_path(run_dir)
    cur = _read_json(path)
    if cur is not None:
        if all(cur.get(k) == rec[k] for k in ("tenant_id", "account_id", "channel",
                                              "conversation_id", "thread_id")):
            return cur                                   # idempotent: same record
        raise OriginConflict(
            "run already has origin %r; conflicting destination %r must be resolved "
            "through the authenticated session" % (cur, rec))
    _write_json(path, rec)
    return rec


def load_origin(run_dir):
    """The canonical origin record, or None. Never fabricates one."""
    if not run_dir:
        return None
    rec = _read_json(origin_path(run_dir))
    if not isinstance(rec, dict) or not rec.get("channel"):
        return None
    return rec


# --------------------------------------------------------------- migration ---

def _legacy_candidates(run_dir):
    """(name, schema dict) for every RECOGNIZED legacy destination schema.
    Recognized means the stored data names its own channel -- a bare chat id
    with no channel marker is recognized as a destination but NOT as a channel.
    """
    out = []
    st = _read_json(os.path.join(run_dir, "song-choices", "state.json"))
    if isinstance(st, dict) and st.get("target"):
        out.append(("song-choices/state.json", {
            "conversation_id": str(st["target"]),
            "channel": str((st.get("provenance") or {}).get("channel") or ""),
        }))
    for name in ("control/destination.json", "control/origin-legacy.json"):
        d = _read_json(os.path.join(run_dir, name))
        if isinstance(d, dict) and (d.get("chat_id") or d.get("conversation_id")
                                    or d.get("target")):
            out.append((name, {
                "conversation_id": str(d.get("chat_id") or d.get("conversation_id")
                                       or d.get("target")),
                "channel": str(d.get("channel") or ""),
                "account_id": str(d.get("account_id") or d.get("bot") or ""),
                "thread_id": str(d.get("thread_id") or d.get("thread") or ""),
                "tenant_id": str(d.get("tenant_id") or ""),
            }))
    order = _read_json(os.path.join(run_dir, "control", "studio-order.json"))
    if isinstance(order, dict) and order.get("order_id"):
        out.append(("control/studio-order.json", {
            "conversation_id": str(order["order_id"]),
            "channel": "studio",
            "account_id": str(order.get("client_id") or ""),
        }))
    return out


#: legacy channel spellings that map onto a supported channel name
_CHANNEL_ALIASES = {"card": "", "openclaw-app": "app", "openclaw_app": "app",
                    "cli": "terminal", "term": "terminal"}


def migrate_legacy_destinations(run_dir):
    """Idempotent migration of recognized legacy destination schemas into the
    canonical origin record. Returns
    ``{"migrated": [...], "unresolved": [...], "origin": rec-or-None}``.

    A legacy destination is migrated only when it names its channel (or is the
    studio order record, whose channel is its own schema). Every bare chat id
    without a channel marker lands in ``unresolved`` -- NOTHING is guessed, in
    particular no global Telegram target. Running twice changes nothing."""
    done = {"migrated": [], "unresolved": [], "origin": load_origin(run_dir)}
    if not run_dir:
        return done                                   # no run ledger: nothing to migrate
    if done["origin"]:
        return done                                   # already canonical: idempotent
    best = None
    for name, cand in _legacy_candidates(run_dir):
        channel = _CHANNEL_ALIASES.get(cand.get("channel", ""), cand.get("channel", ""))
        if not channel:
            done["unresolved"].append({"schema": name,
                                       "conversation_id": cand.get("conversation_id"),
                                       "reason": "destination names no channel"})
            continue
        if channel not in KNOWN_CHANNELS:
            done["unresolved"].append({"schema": name,
                                       "conversation_id": cand.get("conversation_id"),
                                       "reason": "unknown channel %r" % channel})
            continue
        cand["channel"] = channel
        if best and best[1]["conversation_id"] != cand["conversation_id"]:
            done["unresolved"].append({"schema": name,
                                       "reason": "conflicts with %s" % best[0]})
            continue
        best = (name, cand)
    if best:
        name, cand = best
        rec = save_origin(run_dir, origin_record(
            tenant_id=cand.get("tenant_id", ""), account_id=cand.get("account_id", ""),
            channel=cand["channel"], conversation_id=cand["conversation_id"],
            thread_id=cand.get("thread_id", "")))
        done["origin"] = rec
        done["migrated"].append({"schema": name, "channel": cand["channel"]})
    _write_json(os.path.join(run_dir, ORIGIN_MIGRATION_FILE), done)
    return done


def resolve_origin(run_dir="", origin=None):
    """The origin to send with: explicit ``origin`` wins, then the persisted
    record, then the idempotent migration. None when the run has no known
    destination -- the caller must then keep the artifact prepared/queued and
    action-required, never guess."""
    if origin:
        return origin_record(**{k: origin.get(k, "") for k in
                                ("tenant_id", "account_id", "channel",
                                 "conversation_id", "thread_id")})
    return load_origin(run_dir) or migrate_legacy_destinations(run_dir).get("origin")


# ----------------------------------------------------------- envelope build ---

def split_semantic(text, limit):
    """Split long lyrics/scripts at SEMANTIC boundaries: blank-line paragraphs
    first, then lines; a single oversized line is hard-split. Returns ordered
    parts ``[{"part_no", "part_count", "text"}]`` with part numbers starting at
    1; text split only at paragraph boundaries reassembles losslessly."""
    text = text or ""
    if limit is None or limit <= 0 or len(text) <= limit:
        return [{"part_no": 1, "part_count": 1, "text": text}]
    out = []
    for p in text.split("\n\n"):                      # semantic boundary first
        if len(p) <= limit:
            out.append(p)
            continue
        buf = ""
        for line in p.split("\n"):                    # then line boundaries
            cand = buf + "\n" + line if buf else line
            if len(cand) > limit and buf:
                out.append(buf)
                buf = line
                while len(buf) > limit:               # single oversized line
                    out.append(buf[:limit])
                    buf = buf[limit:]
            else:
                buf = cand
        if buf:
            out.append(buf)
    return [{"part_no": i, "part_count": len(out), "text": t}
            for i, t in enumerate(out, 1)]


def contact_sheets(items, per_sheet):
    """Numbered contact sheets for a large storyboard: ``[{"label",
    "sheet_no", "sheet_count", "items"}]`` -- "Contact sheet 1/2" carries shots
    1..6 in order. ``per_sheet`` must be >= 1."""
    items = list(items or [])
    per_sheet = max(1, int(per_sheet or 1))
    sheets = [items[i:i + per_sheet] for i in range(0, len(items), per_sheet)] or [[]]
    return [{"label": "Contact sheet %d/%d" % (n, len(sheets)),
             "sheet_no": n, "sheet_count": len(sheets), "items": sheet}
            for n, sheet in enumerate(sheets, 1)]


def paginate(items, per_page):
    """Paginated cards: ``[{"label", "page_no", "page_count", "items"}]``."""
    items = list(items or [])
    per_page = max(1, int(per_page or 1))
    pages = [items[i:i + per_page] for i in range(0, len(items), per_page)] or [[]]
    return [{"label": "Page %d/%d" % (n, len(pages)),
             "page_no": n, "page_count": len(pages), "items": page}
            for n, page in enumerate(pages, 1)]


def channel_limit(channel, name, default=None):
    return CHANNEL_LIMITS.get(channel, DEFAULT_LIMITS).get(name, default)


def build_envelope(run_id, tenant_id, artifact_id, artifact_kind, revision, origin,
                   text="", attachments=(), approval_state="pending",
                   allowed_actions=("approve", "revise"), extra=None):
    """The typed artifact envelope (spec 5.3). ``sha256`` covers the payload
    text and the asset manifest. Building an envelope establishes PREPARED --
    writing it to a local file or returning it as JSON never means sent."""
    attachments = [dict(a, sha256=a.get("sha256") or
                        (_sha256_file(a["path"]) if a.get("path") else ""))
                   for a in (attachments or [])]
    manifest = "|".join("%s:%s:%s" % (a.get("artifact_ref", a.get("path", "")),
                                      a.get("mime_type", ""), a.get("sha256", ""))
                        for a in attachments)
    env = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "revision": revision,
        "sha256": _sha256_text(text + "\n--assets--\n" + manifest),
        "origin": dict((origin or {}), thread_id=(origin or {}).get("thread_id", "")),
        "presentation": {"text": text, "attachments": attachments},
        "delivery": {"state": PREPARED, "idempotency_key": "", "message_ids": []},
        "approval": {"state": approval_state, "allowed_actions": list(allowed_actions)},
    }
    if extra:
        env.update(extra)
    dest = "%s/%s" % ((origin or {}).get("channel", ""),
                      (origin or {}).get("conversation_id", ""))
    env["delivery"]["idempotency_key"] = "/".join(
        [tenant_id, run_id, artifact_id, str(revision), dest])
    return env


# ----------------------------------------------------------------- outbox ---

def _piece_id(envelope, kind, index):
    return "%s/%s/%04d" % (envelope["delivery"]["idempotency_key"], kind, index)


def _piece_file(run_dir, piece_id):
    return os.path.join(run_dir, OUTBOX_DIR,
                        hashlib.sha256(piece_id.encode("utf-8")).hexdigest()[:24] + ".json")


class Outbox:
    """The durable delivery outbox for one run. Each piece is a JSON file under
    ``<run_dir>/outbox/`` carrying its deterministic identity, its payload
    reference and its own receipt. A crash between dispatch and receipt leaves
    the piece ``sending``/``uncertain``; ``resume`` resends only pieces with no
    receipt, with the SAME payload bytes (no paid media is ever spent here)."""

    def __init__(self, run_dir):
        self.run_dir = run_dir

    # -- records ---------------------------------------------------------
    def _all_paths(self):
        d = os.path.join(self.run_dir, OUTBOX_DIR)
        try:
            names = sorted(os.listdir(d))
        except OSError:
            return []
        return [os.path.join(d, n) for n in names if n.endswith(".json")]

    def pieces(self):
        """Every known piece in presentation order: text chunks first, then
        attachments, each by its part number."""
        out = [p for p in (_read_json(f) for f in self._all_paths()) if p]
        return sorted(out, key=lambda p: (p["kind"] != "text", p["index"],
                                          p["piece_id"]))

    def get(self, piece_id):
        for p in self.pieces():
            if p["piece_id"] == piece_id:
                return p
        return None

    def pending(self):
        """Pieces that still owe delivery: no receipt recorded."""
        return [p for p in self.pieces()
                if not p.get("receipt") and p["state"] in PENDING_STATES]

    def _save(self, piece):
        piece["updated_at"] = time.time()
        _write_json(_piece_file(self.run_dir, piece["piece_id"]), piece)

    # -- enqueue ---------------------------------------------------------
    def enqueue(self, envelope, channel=None):
        """Stage one envelope as discrete pieces and durably queue them.
        Returns the piece records. A returned envelope or a written local file
        is PREPARED; ``enqueue`` is what moves the pieces to QUEUED."""
        env = envelope
        dest = env["delivery"]["idempotency_key"]
        if not dest:
            raise OutboxError("envelope has no idempotency key")
        channel = channel or env["origin"].get("channel", "")
        text_parts = split_semantic(
            env["presentation"].get("text", ""),
            channel_limit(channel, "text_chars"))
        atts = env["presentation"].get("attachments") or []
        pieces = []
        for part in (text_parts if env["presentation"].get("text", "") else []):
            pieces.append(self._new_piece(env, "text", part["part_no"], {
                "text": part["text"], "part_no": part["part_no"],
                "part_count": part["part_count"], "channel": channel}))
        for i, att in enumerate(atts, 1):
            pieces.append(self._new_piece(env, "attachment", i, {
                "attachment": att, "channel": channel}))
        for p in pieces:
            p["state"] = QUEUED
            self._save(p)
        return pieces

    def _new_piece(self, env, kind, index, payload):
        pid = _piece_id(env, kind, index)
        return {
            "schema_version": SCHEMA_VERSION,
            "piece_id": pid,
            "idempotency_key": pid,
            "run_id": env["run_id"],
            "tenant_id": env["tenant_id"],
            "artifact_id": env["artifact_id"],
            "artifact_kind": env["artifact_kind"],
            "revision": env["revision"],
            "kind": kind,
            "index": index,
            "payload": payload,
            "payload_sha256": _sha256_text(json.dumps(payload, sort_keys=True)),
            "state": PREPARED,
            "receipt": None,
            "error": None,
            "attempts": 0,
        }

    # -- state moves -----------------------------------------------------
    def mark(self, piece_id, state, receipt=None, error=None):
        if state not in DELIVERY_STATES:
            raise OutboxError("unknown delivery state %r" % state)
        p = self.get(piece_id)
        if not p:
            raise OutboxError("unknown piece %r" % piece_id)
        if state == SENT and not receipt:
            raise OutboxError("a piece may only be 'sent' with its channel receipt")
        p["state"] = state
        if receipt is not None:
            p["receipt"] = receipt
        if error is not None:
            p["error"] = error
        self._save(p)
        return p

    # -- dispatch / resume -----------------------------------------------
    def resume(self, sender):
        """Send every piece that has no receipt yet. ``sender(piece)`` dispatches
        one piece and returns its channel receipt (truthy) or None/raises.
        Only already-materialized payloads are handed to the sender: repairing a
        failed send NEVER spends paid media. Returns
        ``{"sent": [...], "failed": [...], "uncertain": [...]}``."""
        result = {"sent": [], "failed": [], "uncertain": [], "skipped": []}
        for p in self.pieces():
            if p.get("receipt") or p["state"] == SENT:
                result["skipped"].append(p["piece_id"])     # already acknowledged
                continue
            if p["state"] == ACTION_REQUIRED:
                result["skipped"].append(p["piece_id"])     # needs a human/destination
                continue
            self.mark(p["piece_id"], SENDING)
            p["attempts"] = p.get("attempts", 0) + 1
            self._save(p)
            try:
                receipt = sender(p)
            except Exception as e:  # noqa: BLE001 - preserve the causal error
                self.mark(p["piece_id"], RETRYABLE_FAILURE, error=str(e)[:500])
                result["failed"].append(p["piece_id"])
                continue
            if receipt:
                self.mark(p["piece_id"], SENT, receipt=receipt)
                result["sent"].append(p["piece_id"])
            else:
                self.mark(p["piece_id"], UNCERTAIN,
                          error="dispatched without a channel receipt")
                result["uncertain"].append(p["piece_id"])
        return result

    def resolve_uncertain(self, piece_id, readback):
        """Resolve an ``uncertain`` piece through the channel's own idempotency/
        readback, never by asserting exactly-once. ``readback(idempotency_key)``
        returns the channel's receipt, the explicit ``NOT_FOUND`` marker, or
        None when the channel cannot prove either way (the piece STAYS
        uncertain). Returns the updated piece."""
        p = self.get(piece_id)
        if not p:
            raise OutboxError("unknown piece %r" % piece_id)
        if p["state"] != UNCERTAIN:
            return p
        answer = readback(p["idempotency_key"])
        if isinstance(answer, dict):
            return self.mark(piece_id, SENT, receipt=answer)
        if answer == NOT_FOUND:
            return self.mark(piece_id, RETRYABLE_FAILURE,
                             error="channel readback found no record: resend is safe")
        return self.mark(piece_id, UNCERTAIN,
                         error="channel cannot prove the delivery either way")

    def redestinate(self, origin):
        """Repair the destination after the origin record is fixed (the
        no-target case). Every piece without a receipt is moved onto the
        repaired ``channel/conversation`` identity and re-queued; the payload
        bytes are untouched (sha256 unchanged), so NO paid media is spent to
        repair the send. ``resume`` then delivers the missing pieces. Returns
        the moved pieces."""
        conv = (origin or {}).get("conversation_id", "")
        channel = (origin or {}).get("channel", "")
        if not conv or not channel:
            raise OutboxError("redestinate needs the repaired channel and conversation")
        moved = []
        for p in self.pieces():
            if p.get("receipt") or p["state"] == SENT:
                continue
            old_file = _piece_file(self.run_dir, p["piece_id"])
            p["payload"]["channel"] = channel
            p["idempotency_key"] = "/".join(
                [p["tenant_id"], p["run_id"], p["artifact_id"], str(p["revision"]),
                 "%s/%s" % (channel, conv), p["kind"], "%04d" % p["index"]])
            p["piece_id"] = p["idempotency_key"]
            p["state"] = QUEUED
            p["error"] = None
            try:
                os.remove(old_file)
            except OSError:
                pass
            self._save(p)
            moved.append(p)
        return moved


#: readback answer meaning the channel proved the piece never landed
NOT_FOUND = "NOT_FOUND"
