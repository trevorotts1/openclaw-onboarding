#!/usr/bin/env python3
"""S75-T05: reusable character identity schema and full-cast refusals.

Three records stay separate on purpose:

* ``character_identity`` -- who the person is, forever. Face, age, hair,
  wardrobe *rules*, continuity constraints and the reusable prompt block live
  here. The record survives a change of episode setting: the same
  ``character_id`` and history appear at a backyard barbecue and at the White
  House.
* ``episode_setting`` -- where and when this episode happens, plus the one
  wardrobe instance worn there. Setting fields never enter an identity record.
* ``episode_cast_manifest`` -- which identities were selected at which exact
  revision, what each person does in this story, and the crowd rules.

A face-and-clothes file is not a story bible, so an identity also has to carry
wants, fears, beliefs and speech. Validation is structural: keys, types, IDs,
references and substantive non-empty content. It refuses an incomplete cast,
an undeclared or anonymous speaker, a dangling relationship or scene, a stale
identity revision, and any crowd group that singles a member out without
promoting that member to a full identity.

Standard library only. Run the focused tests with::

    python3 75-drama-song-ad-factory/scripts/core/character_bible/test_identity_s75_t05.py
"""
from __future__ import annotations

import hashlib
import json
import os
import threading

__all__ = [
    "CastDefect", "IdentityDefect", "canonical_digest", "library_digest",
    "validate_episode_setting", "validate_identity", "validate_library",
    "validate_cast", "seal_identity", "receipt_digest", "resolve_receipt",
    "SCHEMA_VERSION", "MANIFEST_SCHEMA_VERSION", "EPISODE_SCHEMA_VERSION",
    "EPISODE_ONLY_FIELDS", "ROLES", "CROWD_REQUIRED",
    "ANONYMOUS_SPEAKER_PATTERNS", "APPROVAL_BINDING_KEYS", "CLAIM_KEYS",
    "RECEIPT_KIND", "MINT_FIELD",
]

SCHEMA_VERSION = "s75.identity.v1"
MANIFEST_SCHEMA_VERSION = "s75.cast_manifest.v1"
EPISODE_SCHEMA_VERSION = "s75.episode_setting.v1"

#: Episode/setting fields. Presence inside an identity record is a hard defect:
#: changing the venue must never rewrite who the person is.
EPISODE_ONLY_FIELDS = frozenset({
    "setting", "setting_name", "location", "venue", "era", "time_period",
    "season", "time_of_day", "episode_setting", "episode_world",
    "wardrobe_instance", "outfit_today", "scene_location",
})

STORY_STATUS = frozenset({"FICTION", "OWNER_SUPPLIED", "REAL_PERSON"})
#: The only forward order. Skipping or going back is refused everywhere.
DRAFT_ORDER = ("DRAFT_INCOMPLETE", "DRAFT_COMPLETE", "APPROVED")
DRAFT_STATES = frozenset(DRAFT_ORDER)
SYNC_STATES = frozenset({"PENDING", "OFFLINE", "CONFLICTED", "SYNCED", "LOCAL_ONLY"})

#: Every cast role that entitles a person to individual lines, reactions or
#: causal consequence. Each one requires a full identity, never a crowd slot.
ROLES = frozenset({
    "lead", "supporting", "recurring", "speaking", "reacting",
    "meaningful_background",
})

#: Generic descriptors that hide an undeclared individual. A line or an action
#: attributed to one of these is refused; the person must be declared by ID.
ANONYMOUS_SPEAKER_PATTERNS = (
    "a woman", "a man", "a worker", "a customer", "someone", "somebody",
    "a person", "the crowd", "people in background", "background people",
    "a bystander", "the manager", "a voice",
)

CROWD_REQUIRED = (
    "crowd_group_id", "composition", "count", "age_range", "roles",
    "location_placement", "collective_behavior", "permitted_motion",
    "attention_direction", "interaction_with_leads", "wardrobe_palette",
    "camera_limits", "entry_exit_rule", "recurrence", "dialogue",
    "reference_provenance", "scene_ids",
)

#: Identity fields that are bookkeeping, not content. They are excluded from the
#: content digest so an approval receipt or cache refresh cannot look like a
#: rewrite of the person.
_DIGEST_EXCLUDED = frozenset({
    "content_digest", "approval_bindings", "draft_state",
    "shared_source", "local_cache", "sync_state",
})


class IdentityDefect(ValueError):
    """One actionable packet of every identity/library defect found."""

    def __init__(self, defects):
        self.defects = list(defects)
        super().__init__("; ".join(d["message"] for d in self.defects))


class CastDefect(ValueError):
    """One actionable packet of every cast/selection defect found."""

    def __init__(self, defects):
        self.defects = list(defects)
        super().__init__("; ".join(d["message"] for d in self.defects))


def _defect(field, code, message):
    return {"field": field, "code": code, "message": message}


# --- reading caller-supplied values -----------------------------------------
#
# SECURITY (do not loosen in a later round): nothing below reaches a security
# decision through overridable dispatch. ``isinstance`` is deliberately not
# used for these gates. A dict subclass can lie in ``get()``/``keys()``/
# ``__len__``/``__bool__``, a str subclass can lie in ``__eq__`` (Python even
# calls the subclass's reflected ``__eq__`` first), and a list subclass can lie
# in ``__bool__``/``__len__``. So every subclass is refused outright with a
# named reason instead of being believed, and every decision runs on one plain
# builtin copy built here.

def _plain(value):
    """One builtin dict copy of a caller mapping, or None if it is not exactly
    a builtin dict. Decide on the copy, never on the caller's object."""
    if type(value) is not dict:
        return None
    return {k: v for k, v in value.items()}


def _plain_list(value):
    """One builtin list copy of a caller sequence, or None if it is not exactly
    a builtin list. Emptiness and length are tested on THIS copy."""
    if type(value) is not list:
        return None
    return list(value)


def _is_text(value, expected):
    """Exact builtin str compared to an exact builtin str. No subclass eq: with
    a str subclass on either side Python calls the subclass's reflected
    ``__eq__`` first and the caller would answer the question."""
    return type(value) is str and type(expected) is str and value == expected


def _in(value, allowed):
    """Membership for a caller value: exact builtin str only."""
    return type(value) is str and value in allowed


def _text(value):
    return type(value) is str and value.strip() != ""


def _text_list(value, minimum=1):
    return (type(value) is list and len(value) >= minimum
            and all(_text(item) for item in value))


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(obj, *, exclude=_DIGEST_EXCLUDED):
    """SHA-256 over canonical JSON, ignoring bookkeeping fields."""
    body = {k: v for k, v in dict(obj).items() if k not in exclude}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def seal_identity(record):
    """Attach the content digest an identity record is addressed by."""
    sealed = _plain(record)
    if sealed is None:
        raise IdentityDefect([_defect("<record>", "NOT_OBJECT",
                                      "identity record must be a plain object, "
                                      "not %s" % type(record).__name__)])
    sealed.setdefault("schema_version", SCHEMA_VERSION)
    sealed["content_digest"] = canonical_digest(sealed)
    return sealed


def library_digest(snapshot):
    """Digest of the selected library snapshot the manifest binds to."""
    return canonical_digest(snapshot, exclude=frozenset({"local_cache", "sync_state"}))


# --- approval receipts ------------------------------------------------------
#
# SECURITY (do not loosen in a later round): the mint lives OUTSIDE this
# process. Rounds one to three sealed receipts with a secret held in this
# interpreter -- a module-global key plus a module-global registry -- and an
# in-process caller read the key, wrote the registry, recomputed the mark and
# had its forgery stored. No in-process seal of that shape can hold: module
# globals, closure cells and the gc graph are reachable by any caller in the
# same interpreter, so every key, registry and "read-only" view reachable from
# here is reachable by whoever wants to forge.
#
# So the secret is generated and held by a SEPARATE SIGNER PROCESS (see
# ``_SIGNER_SOURCE``) and never enters this one. This module holds no key, no
# mint registry and no capability object: the only thing here that talks to the
# signer is a plain request/reply over an OS pipe the signer is started with. A
# mint mark can be produced only by that process, and only for a promotion step
# the store itself performed. That is what makes "the explicit promotion step is
# the sole minter" a property of the system rather than a claim in a docstring.
#
# Round 5: there is no mint function here and no state table to declare. The
# signer's ``mint`` request is constructed in exactly one place, inside
# ``NotionStore.promote()``; ``mint_receipt()`` below refuses unconditionally for
# every caller and every argument, and ``register_character()`` no longer exists.
# A receipt therefore cannot name a promotion step that did not happen, because
# nothing but the promotion step can ask for one.
#
# Declared residual, and the deployment impact: this machine gives the caller
# and the signer the SAME unix user, so a caller that is willing to re-point the
# pipe (or to rewrite this module) can answer as the signer. That is tampering
# with the transport itself, not a reachable capability -- there is no object,
# key or registry inside this process that can produce or bless a mark. Closing
# it needs an OS boundary this environment cannot create: run the signer under a
# different uid, with the caller holding only what that uid hands it. Production
# therefore runs a signer process alongside the store.

MINT_FIELD = "mint_mark"
RECEIPT_KIND = "approval_receipt"
APPROVAL_BINDING_KEYS = frozenset({
    "kind", "receipt_id", "approver", "character_id", "from_state", "to_state",
    MINT_FIELD,
})
#: The claim a receipt makes. The mint mark is computed over exactly this.
CLAIM_KEYS = frozenset(APPROVAL_BINDING_KEYS - {MINT_FIELD})

#: The signer: a standalone program, no import from this package. It generates
#: its own mint secret at startup (``secrets.token_bytes(32)``), keeps it in its
#: own memory, and answers exactly three requests over the pipe it is started
#: with: ``register`` (a store declares a character at a draft state), ``mint``
#: (the promotion step) and ``verify`` (is this receipt one this signer minted,
#: for this client and this store). It exits when its parent closes that pipe.
_SIGNER_SOURCE = r'''
import hashlib, hmac, json, os, secrets, sys

PARENT = int(sys.argv[1])
IN_FD = int(sys.argv[2])
OUT_FD = int(sys.argv[3])
KEY = secrets.token_bytes(32)
CLAIMS = {}
BINDS = {}
DONE = {}


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def mark(claim):
    return hmac.new(KEY, canon(claim).encode("utf-8"), hashlib.sha256).hexdigest()


def handle(req):
    op = req.get("op")
    if op == "mint":
        claim = req.get("claim") or {}
        rid = claim.get("receipt_id")
        scope = req.get("scope")
        prior = CLAIMS.get(rid)
        if prior is not None and prior != claim:
            return {"ok": False, "reason": (
                "receipt id %r is already minted for one promotion step and "
                "cannot be minted again for another; a receipt is single-use"
                % rid)}
        key = (scope, rid)
        held = BINDS.get(key)
        if held is not None:
            return {"ok": True, "receipt": dict(claim, mint_mark=held[1])}
        step = (scope, claim.get("character_id"))
        if step in DONE:
            return {"ok": False, "reason": (
                "%r to %r for %r is one promotion step and this store already "
                "approved it with receipt %r; one step takes exactly one receipt"
                % (claim.get("from_state"), claim.get("to_state"),
                   claim.get("character_id"), DONE[step]))}
        body = mark(claim)
        CLAIMS[rid] = dict(claim)
        BINDS[key] = (req.get("client"), body)
        DONE[step] = rid
        return {"ok": True, "receipt": dict(claim, mint_mark=body)}
    if op == "verify":
        claim = req.get("claim") or {}
        rid = claim.get("receipt_id")
        prior = CLAIMS.get(rid)
        wrong = ("the mint mark does not match the receipt's own fields, so "
                 "this receipt was not minted by the approval step")
        if prior is None:
            return {"ok": False, "reason": (
                "receipt id %r was never minted by the approval step; a receipt "
                "is single-use and cannot be typed by hand or reloaded from a "
                "JSON file" % rid)}
        if prior != claim or not hmac.compare_digest(mark(claim),
                                                     req.get("mint_mark") or ""):
            return {"ok": False, "reason": wrong}
        scope = req.get("scope")
        held = BINDS.get((scope, rid)) if scope is not None else BINDS.get(rid)
        if scope is not None and held is None:
            return {"ok": False, "reason": (
                "receipt %r was minted by the promotion step of another store "
                "and is not replayed here; a receipt is single-use" % rid)}
        wanted = req.get("client")
        if held is not None and held[0] != wanted:
            return {"ok": False, "reason": (
                "receipt %r was minted for client %r, not %r; a receipt is "
                "bound to the client whose promotion step produced it"
                % (rid, held[0], wanted))}
        return {"ok": True}
    return {"ok": False, "reason": "unknown request"}


def main():
    buf = b""
    while os.getppid() == PARENT:
        chunk = os.read(IN_FD, 65536)
        if not chunk:                       # parent closed its end: stop
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                reply = handle(json.loads(line.decode("utf-8")))
            except Exception as exc:
                reply = {"ok": False, "reason": "signer error: %s" % exc}
            os.write(OUT_FD, json.dumps(reply).encode("utf-8") + b"\n")


main()
'''

#: One live signer per process, keyed by pid: ``(proc, send_fd, recv_fd)``.
#: Bookkeeping for the pipe, never consulted to answer a security question --
#: the answer comes back over that pipe from the signer, and a caller who swaps
#: this mapping swaps nothing the signer ever said.
_SIGNER_PIPES = {}
_SIGNER_LOCK = threading.Lock()


def _signer_start():
    """Spawn the signer and hand back its two pipe ends."""
    import subprocess as _subprocess, sys as _sys
    to_signer, send_fd = os.pipe()
    recv_fd, to_parent = os.pipe()
    proc = _subprocess.Popen(
        [_sys.executable, "-I", "-c", _SIGNER_SOURCE, str(os.getpid()),
         str(to_signer), str(to_parent)],
        stdin=_subprocess.DEVNULL, stdout=_subprocess.DEVNULL,
        stderr=_subprocess.DEVNULL, close_fds=True, start_new_session=True,
        pass_fds=(to_signer, to_parent))
    os.close(to_signer)
    os.close(to_parent)
    return (proc, send_fd, recv_fd)


def _signer_request(payload):
    """One request to the approval signer over an OS pipe. Fails closed.

    No socket, no network and no file: the endpoint is a pipe the signer is
    started with. An answer that is not the signer's is refused exactly like a
    missing one.
    """
    with _SIGNER_LOCK:
        reason = "the approval signer did not answer"
        for attempt in (0, 1):
            held = _SIGNER_PIPES.get(os.getpid())
            if held is None:
                try:
                    held = _signer_start()
                except Exception as exc:
                    return {"ok": False,
                            "reason": "the approval signer could not start (%s)"
                                      % exc}
                _SIGNER_PIPES[os.getpid()] = held
            _proc, send_fd, recv_fd = held
            try:
                os.write(send_fd, json.dumps(payload).encode("utf-8") + b"\n")
                data = b""
                while not data.endswith(b"\n"):
                    chunk = os.read(recv_fd, 65536)
                    if not chunk:
                        return {"ok": False,
                                "reason": "the approval signer stopped"}
                    data += chunk
                return json.loads(data.decode("utf-8"))
            except Exception as exc:
                reason = "the approval signer is unreachable (%s)" % exc
                _SIGNER_PIPES.pop(os.getpid(), None)
                for fd in (send_fd, recv_fd):
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                if attempt == 0:
                    continue
        return {"ok": False, "reason": reason}


def _scope_parts(scope):
    """(client_namespace, store) from a store's approval scope, or None."""
    if scope is None:
        return None, None
    if type(scope) is not tuple or len(scope) != 2:
        raise IdentityDefect([_defect("approval_bindings", "APPROVAL_SCOPE",
                                      "an approval scope names one client and "
                                      "one store")])
    client, store = scope
    if type(client) is not str or type(store) is not str:
        raise IdentityDefect([_defect("approval_bindings", "APPROVAL_SCOPE",
                                      "an approval scope names one client and "
                                      "one store")])
    return client, store


def _claim(receipt):
    return {k: receipt[k] for k in sorted(CLAIM_KEYS) if k in receipt}


def mint_receipt(fields, *, scope=None):
    """Refused, always, for every caller and every argument.

    A receipt is minted in exactly one place: inside :meth:`NotionStore.promote`,
    which sends the signer's ``mint`` request itself. This entry point is kept as
    a named refusal so a caller who reaches for it gets a plain-English answer
    instead of an ``AttributeError`` -- but there is no argument that makes it
    mint. ``scope`` in particular is not a switch: it is accepted only so the
    refusal can name it, and ignored.

    Round 4 shipped the opposite behaviour: ``scope=None`` was refused by name
    while ``scope=<a store's scope>`` minted. That made the docstring's claim the
    gate instead of the code. The gate is now the code: this function has no mint
    path at all.
    """
    raise IdentityDefect([_defect(
        "approval_bindings", "RECEIPT_MINT_REFUSED",
        "a receipt is minted only inside the store's own promotion step; this "
        "entry point mints nothing, for any caller and for any argument, and "
        "there is no promotion step this call belongs to, so a receipt cannot "
        "be minted for a step that did not happen")])


def receipt_digest(receipt):
    """The digest a receipt is addressed by. Stable across key order."""
    return canonical_digest(_claim(_plain(receipt) or {}),
                            exclude=frozenset({"content_digest"}))


def resolve_receipt(binding, record, *, scope=None):
    """Resolve one binding against the approval record it claims.

    Returns ``None`` only when the binding is a receipt the approval step
    actually minted for THIS record: exact builtin types, the closed shape, a
    mint mark the signer reproduces for the receipt's own fields, an id that
    signer minted for this client (and, when a store asks, for this store), and
    exactly the one promotion step that put the record into its current state --
    with no other receipt already covering that step. Otherwise the plain-English
    reason the binding is refused. A non-empty list is never enough, and a
    receipt typed by hand or reloaded from JSON never resolves.

    ``scope`` is a store's ``(client_namespace, store)`` approval scope. Without
    it the receipt is checked against the record alone; a store always passes
    its own scope, which is what stops a consumed receipt being replayed into
    another store's cache.
    """
    body = _plain(binding)
    if body is None:
        return ("an approval binding must be a receipt object, not %s"
                % type(binding).__name__)
    target = _plain(record)
    if target is None:
        return ("the identity record must be an object, not %s"
                % type(record).__name__)
    unknown = sorted(k for k in body if k not in APPROVAL_BINDING_KEYS)
    if unknown:
        return ("an approval receipt carries only %s; %s is not a receipt"
                % (sorted(APPROVAL_BINDING_KEYS), unknown))
    missing = sorted(k for k in APPROVAL_BINDING_KEYS if k not in body)
    if missing:
        return ("an approval receipt carries exactly %s; %s is missing, so this "
                "was not minted by the approval step"
                % (sorted(APPROVAL_BINDING_KEYS), missing))
    for field in sorted(APPROVAL_BINDING_KEYS):
        if type(body[field]) is not str:
            return ("an approval receipt field %r must be a plain string, not %s"
                    % (field, type(body[field]).__name__))
    if len(body[MINT_FIELD]) != 64:
        return ("an approval receipt carries a 64-character mint mark only the "
                "approval step can produce; this one has none")
    client = target.get("client_id")
    if type(client) is not str or not client.strip():
        return ("the identity record must name the client it belongs to; an "
                "approval receipt is bound to one client's promotion step")
    client_scope, store_scope = _scope_parts(scope)
    reply = _signer_request({
        "op": "verify", "claim": _claim(body), MINT_FIELD: body[MINT_FIELD],
        "client": client, "scope": store_scope})
    if not reply.get("ok"):
        return reply.get("reason") or ("this receipt was not minted by the "
                                       "approval step")
    if not _is_text(body["kind"], RECEIPT_KIND):
        return "an approval binding must declare kind %r" % (RECEIPT_KIND,)
    for field in ("receipt_id", "approver"):
        if not body[field].strip():
            return "an approval receipt needs a non-empty %s" % field
    owner = body["character_id"]
    if not owner.strip():
        return "an approval receipt must name the character it approves"
    record_id = target.get("character_id")
    if not _is_text(record_id, owner):
        return ("approval receipt %r belongs to %r, not %r"
                % (body["receipt_id"], owner, record_id))
    state = target.get("draft_state")
    if not _is_text(state, "APPROVED"):
        return ("approval receipt %r claims an approved identity, but this "
                "record is %r" % (body["receipt_id"], state))
    start, end = body["from_state"], body["to_state"]
    if not _in(start, DRAFT_ORDER[:-1]):
        return "an approval receipt must name the draft state it promotes from"
    if end != "APPROVED":
        return "an approval receipt approves; its to_state must be 'APPROVED'"
    if end != DRAFT_ORDER[DRAFT_ORDER.index(start) + 1]:
        return ("approval receipt %r claims %r to %r, which is not one promotion "
                "step" % (body["receipt_id"], start, end))
    # One promotion step takes exactly one receipt. A second receipt for a step
    # this record already approved is refused here, on the validation entry
    # point itself, not only in the per-record pass below.
    step = (body["character_id"], start, end)
    for held in _plain_list(target.get("approval_bindings", [])) or []:
        other = _plain(held)
        if other is None or other.get("receipt_id") == body["receipt_id"]:
            continue
        if (other.get("character_id"), other.get("from_state"),
                other.get("to_state")) == step:
            return ("approval receipt %r claims %r to %r for %r, which is one "
                    "promotion step and it is already approved by receipt %r; "
                    "one step takes exactly one receipt"
                    % (body["receipt_id"], start, end, body["character_id"],
                       other.get("receipt_id")))
    return None


def _validate_approval_bindings(record, scope=None):
    """Every binding must resolve as a receipt the approval step minted.

    Dedupe is keyed on BOTH the receipt id and the promotion step the receipt
    claims: one receipt id is single use, and one promotion step takes exactly
    one receipt.
    """
    out = []
    approvals = _plain_list(record.get("approval_bindings", []))
    if approvals is None:
        return [_defect("approval_bindings", "APPROVALS",
                        "approval_bindings must be a plain list of approval "
                        "receipts; a list subclass is refused because it can "
                        "lie about being empty; never synthesize receipts")]
    if not approvals:          # tested on the builtin copy, never on the caller
        if _is_text(record.get("draft_state"), "APPROVED"):
            out.append(_defect("approval_bindings", "APPROVALS",
                               "an approved identity must carry the receipt that "
                               "approved it; approval is never a default"))
        return out
    if not _is_text(record.get("draft_state"), "APPROVED"):
        out.append(_defect("approval_bindings", "APPROVALS",
                           "only an approved identity carries approval receipts; "
                           "a draft carries none, so a receipt cannot be parked "
                           "on a draft"))
    seen_ids = {}
    seen_steps = {}
    for index, binding in enumerate(approvals):
        where = "approval_bindings[%d]" % index
        reason = resolve_receipt(binding, record, scope=scope)
        if reason is not None:
            out.append(_defect(where, "APPROVALS", "%s: %s" % (where, reason)))
            continue
        claim = _plain(binding)
        key = claim["receipt_id"]
        step = (claim["character_id"], claim["from_state"], claim["to_state"])
        if key in seen_ids:
            out.append(_defect(where, "APPROVALS",
                               "%s: receipt id %r is already bound at "
                               "approval_bindings[%d]; a receipt is single-use"
                               % (where, key, seen_ids[key])))
            continue
        if step in seen_steps:
            out.append(_defect(where, "APPROVALS",
                               "%s: %r to %r for %r is one promotion step and it "
                               "is already approved at approval_bindings[%d]; "
                               "one step takes exactly one receipt"
                               % (where, step[1], step[2], step[0],
                                  seen_steps[step])))
            continue
        seen_ids[key] = index
        seen_steps[step] = index
    return out


# --- identity ---------------------------------------------------------------

_PLAIN_REQUIRED = (
    "client_id", "character_id", "display_name", "identity_summary",
    "occupation", "social_context", "emotional_wound", "mistaken_belief",
    "behavior_under_pressure", "appearance_traits",
)
_LIST_REQUIRED = (
    "relevant_background_history", "competence", "fears", "beliefs",
    "contradictions", "habits",
)
_VISUAL_REQUIRED = ("face", "age", "hair", "wardrobe_rules",
                    "continuity_constraints", "prompt_block")


def _validate_identity(record, scope=None):
    out = []
    given = record
    record = _plain(given)
    if record is None:
        return [_defect("<record>", "NOT_OBJECT",
                        "identity record must be a plain object, not %s; a dict "
                        "subclass is refused because it can lie in get() and "
                        "__len__" % type(given).__name__)]

    for field in sorted(EPISODE_ONLY_FIELDS & set(record)):
        out.append(_defect(field, "SETTING_IN_IDENTITY",
                           f"'{field}' is an episode-setting field; it does not belong in "
                           f"the reusable identity and must change without a new revision"))

    for field in _PLAIN_REQUIRED:
        if not _text(record.get(field)):
            out.append(_defect(field, "IDENTITY_INCOMPLETE",
                               f"'{field}' is required substantive content"))

    for field in _LIST_REQUIRED:
        if not _text_list(record.get(field)):
            out.append(_defect(field, "IDENTITY_INCOMPLETE",
                               f"'{field}' must be a non-empty list of non-empty strings"))

    if not _is_text(record.get("schema_version"), SCHEMA_VERSION):
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{SCHEMA_VERSION}'"))
    revision = record.get("revision")
    if type(revision) is not int or revision < 1:
        out.append(_defect("revision", "REVISION",
                           "revision must be a positive integer"))
    digest = record.get("content_digest")
    if type(digest) is not str or len(digest) != 64:
        out.append(_defect("content_digest", "DIGEST",
                           "content_digest must be a 64-character sha256"))
    elif digest != canonical_digest(record):
        out.append(_defect("content_digest", "DIGEST_MISMATCH",
                           "content_digest does not match the record content"))

    if not _in(record.get("story_status"), STORY_STATUS):
        out.append(_defect("story_status", "STORY_STATUS",
                           f"story_status must be one of {sorted(STORY_STATUS)}"))

    aliases = record.get("aliases", [])
    if type(aliases) is not list or not all(_text(a) for a in aliases):
        out.append(_defect("aliases", "ALIASES", "aliases must be a list of strings"))

    # wants / voice: typed, not embedded prose.
    wants = record.get("wants")
    if not (type(wants) is dict and _text(wants.get("external"))
            and _text(wants.get("internal"))):
        out.append(_defect("wants", "WANTS",
                           "wants must carry external and internal drivers"))
    voice = record.get("voice")
    if not (type(voice) is dict and _text(voice.get("rhythm"))
            and _text(voice.get("vocabulary")) and _text(voice.get("restraint"))):
        out.append(_defect("voice", "VOICE",
                           "voice must carry rhythm, vocabulary and restraint"))

    visual = record.get("identity_visual")
    if type(visual) is not dict:
        out.append(_defect("identity_visual", "VISUAL",
                           "identity_visual must carry face, age, hair, wardrobe_rules, "
                           "continuity_constraints and prompt_block"))
    else:
        for field in _VISUAL_REQUIRED:
            value = visual.get(field)
            ok = _text_list(value) if field in ("wardrobe_rules",
                                                "continuity_constraints") else _text(value)
            if not ok:
                out.append(_defect(f"identity_visual.{field}", "VISUAL",
                                   f"identity_visual.{field} is required"))
        # wardrobe RULES, not a look: setting-specific outfits stay in production.
        for field in sorted(EPISODE_ONLY_FIELDS & set(visual)):
            out.append(_defect(f"identity_visual.{field}", "SETTING_IN_IDENTITY",
                               f"'{field}' is setting-specific and belongs to the episode"))

    references = record.get("reference_ids", [])
    if type(references) is not list or not all(_text(r) for r in references):
        out.append(_defect("reference_ids", "REFERENCES",
                           "reference_ids must be a list of strings; an empty list is valid"))
    # Text identity must be complete before any image exists.

    provenance = record.get("provenance_by_field")
    if type(provenance) is not dict or not provenance:
        out.append(_defect("provenance_by_field", "PROVENANCE",
                           "every substantive assertion needs a provenance entry"))
    elif any(not _text(str(v)) for v in provenance.values()):
        out.append(_defect("provenance_by_field", "PROVENANCE",
                           "provenance values must name a real origin"))

    if not _in(record.get("draft_state"), DRAFT_STATES):
        out.append(_defect("draft_state", "DRAFT_STATE",
                           f"draft_state must be one of {sorted(DRAFT_STATES)}"))
    # A binding is a receipt or it is refused: never "a non-empty list".
    out.extend(_validate_approval_bindings(record, scope))
    for key in ("shared_source", "local_cache"):
        if record.get(key) is not None and type(record.get(key)) is not dict:
            out.append(_defect(key, "SYNC", f"{key} must be an object or null"))
    if not _in(record.get("sync_state"), SYNC_STATES):
        out.append(_defect("sync_state", "SYNC",
                           f"sync_state must be one of {sorted(SYNC_STATES)}"))

    relationships = record.get("relationships", [])
    if type(relationships) is not list:
        out.append(_defect("relationships", "RELATIONSHIPS",
                           "relationships must be a list"))
    else:
        own_id = record.get("character_id")
        for index, edge in enumerate(relationships):
            where = f"relationships[{index}]"
            edge = _plain(edge)
            if edge is None:
                out.append(_defect(where, "RELATIONSHIPS", "relationship must be an object"))
                continue
            for field in ("character_id", "type", "history", "present_tension",
                          "dependency"):
                if not _text(edge.get(field)):
                    out.append(_defect(f"{where}.{field}", "RELATIONSHIPS",
                                       f"relationship requires '{field}'"))
            if _is_text(edge.get("character_id"), own_id):
                out.append(_defect(f"{where}.character_id", "SELF_RELATIONSHIP",
                                   "a character cannot relate to itself"))
    return out


def validate_identity(record, *, scope=None):
    """Validate one reusable identity; raise IdentityDefect with every defect.

    ``scope`` is the store's ``(client_namespace, store)`` approval scope; a
    store passes its own so a receipt bound to another store's promotion step
    is refused here and not only at the store boundary.
    """
    defects = _validate_identity(record, scope)
    if defects:
        raise IdentityDefect(defects)
    return record


# --- library snapshot -------------------------------------------------------

def validate_library(snapshot):
    """Validate a client-scoped library snapshot; duplicate/dangling IDs fail."""
    given = snapshot
    snapshot = _plain(given)
    if snapshot is None:
        raise IdentityDefect([_defect("<snapshot>", "NOT_OBJECT",
                                      "library snapshot must be a plain object, "
                                      "not %s" % type(given).__name__)])
    out = []
    owner = snapshot.get("client_id")
    if not _text(owner):
        out.append(_defect("client_id", "CLIENT", "library snapshot needs a client_id"))
    characters = _plain_list(snapshot.get("characters", []))
    if not characters:
        out.append(_defect("characters", "LIBRARY_EMPTY",
                           "library snapshot must contain at least one character"))
        characters = []

    seen = set()
    for index, record in enumerate(characters):
        defects = _validate_identity(record)
        out.extend({**d, "field": f"characters[{index}].{d['field']}"} for d in defects)
        rec = _plain(record)
        cid = rec.get("character_id") if rec is not None else None
        if type(cid) is str:
            if cid in seen:
                out.append(_defect(f"characters[{index}].character_id", "DUPLICATE_ID",
                                   f"duplicate character_id '{cid}'"))
            seen.add(cid)
        if rec is not None and not _is_text(rec.get("client_id"), owner):
            out.append(_defect(f"characters[{index}].client_id", "CLIENT_MISMATCH",
                               "character belongs to a different client namespace"))

    for index, record in enumerate(characters):
        rec = _plain(record)
        if rec is None:
            continue
        edges = _plain_list(rec.get("relationships", [])) or []
        for edge_index, edge in enumerate(edges):
            edge = _plain(edge)
            target = edge.get("character_id") if edge is not None else None
            # A relationship may leave the client library only if it is
            # explicitly marked external; otherwise the ID must resolve.
            external = edge is not None and edge.get("external") is True
            if (type(target) is not str or target not in seen) and not external:
                out.append(_defect(
                    f"characters[{index}].relationships[{edge_index}].character_id",
                    "DANGLING_RELATIONSHIP",
                    f"relationship '{target}' does not resolve in this library"))
    if out:
        raise IdentityDefect(out)
    return snapshot


# --- episode setting --------------------------------------------------------

def validate_episode_setting(record):
    """Validate the episode-owned setting record; identity fields never appear here."""
    out = []
    given = record
    record = _plain(given)
    if record is None:
        raise IdentityDefect([_defect("<record>", "NOT_OBJECT",
                                      "episode setting must be a plain object, "
                                      "not %s" % type(given).__name__)])
    if not _is_text(record.get("schema_version"), EPISODE_SCHEMA_VERSION):
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{EPISODE_SCHEMA_VERSION}'"))
    for field in ("episode_id", "setting_name", "location", "era"):
        if not _text(record.get(field)):
            out.append(_defect(field, "SETTING_INCOMPLETE",
                               f"episode setting requires '{field}'"))
    for field in ("identity_summary", "wants", "fears", "identity_visual",
                  "emotional_wound", "mistaken_belief"):
        if field in record:
            out.append(_defect(field, "IDENTITY_IN_SETTING",
                               f"'{field}' belongs to the reusable identity record"))
    if out:
        raise IdentityDefect(out)
    return record


# --- cast manifest ----------------------------------------------------------

def _anonymous(speaker):
    low = speaker.strip().lower()
    return any(low == p or low.startswith(p + " ") for p in ANONYMOUS_SPEAKER_PATTERNS)


def _validate_crowd(group, index, scene_ids):
    out = []
    where = f"crowd_groups[{index}]"
    group = _plain(group)
    if group is None:
        return [_defect(where, "CROWD", "crowd group must be an object")]
    for field in CROWD_REQUIRED:
        value = group.get(field)
        if value is None:
            out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                               f"crowd group requires '{field}'"))
        elif field in ("roles", "scene_ids"):
            if not _text_list(value):
                out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                                   f"crowd '{field}' must be a non-empty list"))
        elif field == "count":
            if not (type(value) is int and value > 0):
                out.append(_defect(f"{where}.count", "CROWD_RULES",
                                   "crowd count must be a positive integer"))
        elif not _text(value):
            out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                               f"crowd '{field}' must be non-empty"))

    if not _is_text(group.get("dialogue"), "forbidden"):
        out.append(_defect(f"{where}.dialogue", "CROWD_DIALOGUE",
                           "a crowd group may not speak; individualize the member first"))
    singled = group.get("singled_out")
    if singled is not None and type(singled) is not bool:
        out.append(_defect(f"{where}.singled_out", "CROWD_SINGLED_OUT",
                           "singled_out must be true or false"))
    elif singled is True:
        out.append(_defect(f"{where}.singled_out", "CROWD_SINGLED_OUT",
                           "a singled-out crowd member must be promoted to a full identity "
                           "with its own character_id and removed from the crowd group"))
    for sid in _plain_list(group.get("scene_ids", [])) or []:
        if scene_ids is not None and (type(sid) is not str or sid not in scene_ids):
            out.append(_defect(f"{where}.scene_ids", "UNKNOWN_SCENE",
                               f"crowd group references unknown scene '{sid}'"))
    if not _text(group.get("crowd_group_id")):
        out.append(_defect(f"{where}.crowd_group_id", "CROWD_RULES",
                           "crowd_group_id must be a stable ID"))
    return out


def validate_cast(manifest, library, *, speakers=None, scene_ids=None):
    """Refuse an incomplete cast, stale identity, dangling ref or hidden speaker.

    ``speakers`` are the lines/performers derived from the scenes; every one must
    resolve to an individual cast identity. ``scene_ids`` are the episode's real
    scene IDs; every reference must resolve.
    """
    out = []
    given = manifest
    manifest = _plain(given)
    if manifest is None:
        raise CastDefect([_defect("<manifest>", "NOT_OBJECT",
                                  "cast manifest must be a plain object, not %s"
                                  % type(given).__name__)])
    library = _plain(library) or {}
    characters = _plain_list(library.get("characters", [])) or []
    by_id = {}
    for candidate in characters:
        plain = _plain(candidate)
        if plain is not None and type(plain.get("character_id")) is str:
            by_id[plain["character_id"]] = plain
    known_scenes = None
    if scene_ids is not None:
        known_scenes = set(s for s in (scene_ids or []) if type(s) is str)

    if not _is_text(manifest.get("schema_version"), MANIFEST_SCHEMA_VERSION):
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{MANIFEST_SCHEMA_VERSION}'"))
    for field in ("client_id", "episode_id"):
        if not _text(manifest.get(field)):
            out.append(_defect(field, "CAST_INCOMPLETE",
                               f"cast manifest requires '{field}'"))
    if not _is_text(manifest.get("library_digest"), library_digest(library)):
        out.append(_defect("library_digest", "LIBRARY_BINDING",
                           "cast manifest was not bound to this library snapshot"))

    cast_raw = manifest.get("cast")
    cast = _plain_list(cast_raw)
    people_free = manifest.get("people_free") is True
    if people_free:
        if cast or (cast is None and cast_raw is not None):
            out.append(_defect("cast", "PEOPLE_FREE_CONTRADICTION",
                               "a people-free episode cannot select cast members"))
        if not _text(manifest.get("people_free_reason")):
            out.append(_defect("people_free_reason", "PEOPLE_FREE",
                               "a people-free episode must state its reason explicitly"))
    elif cast is None or cast_raw is None:
        out.append(_defect("cast", "CAST_INCOMPLETE",
                           "cast list is required; omission is not an empty cast"))
    elif not cast:
        out.append(_defect("cast", "CAST_EMPTY",
                           "a narrative with people cannot have an empty cast"))

    selected = {}
    for index, entry in enumerate(cast or []):
        where = f"cast[{index}]"
        entry = _plain(entry)
        if entry is None:
            out.append(_defect(where, "CAST_INCOMPLETE", "cast entry must be an object"))
            continue
        cid = entry.get("character_id")
        if not _text(cid):
            out.append(_defect(f"{where}.character_id", "CAST_INCOMPLETE",
                               "every selected person needs an explicit character_id"))
        elif cid in selected:
            out.append(_defect(f"{where}.character_id", "DUPLICATE_CAST",
                               f"'{cid}' is selected twice"))
        else:
            selected[cid] = entry

        record = by_id.get(cid)
        if cid and record is None:
            out.append(_defect(f"{where}.character_id", "UNKNOWN_IDENTITY",
                               f"'{cid}' is not in the bound library snapshot"))
        elif record is not None:
            want = entry.get("identity_revision")
            have = record.get("revision")
            if not (type(want) is int and type(have) is int and want == have):
                out.append(_defect(f"{where}.identity_revision", "STALE_REVISION",
                                   f"'{cid}' is selected at revision "
                                   f"{entry.get('identity_revision')}, library has "
                                   f"{record.get('revision')}"))
            if not _is_text(entry.get("identity_digest"), record.get("content_digest")):
                out.append(_defect(f"{where}.identity_digest", "DIGEST_MISMATCH",
                                   f"'{cid}' selection does not bind the library content"))

        if not _in(entry.get("episode_role"), ROLES):
            out.append(_defect(f"{where}.episode_role", "CAST_ROLE",
                               f"episode_role must be one of {sorted(ROLES)}"))
        for field in ("immediate_story_function", "choice_or_consequence"):
            if not _text(entry.get(field)):
                out.append(_defect(f"{where}.{field}", "CAST_INCOMPLETE",
                                   f"'{field}' is required for a selected person"))
        if type(entry.get("relationship_changes", [])) is not list:
            out.append(_defect(f"{where}.relationship_changes", "CAST_INCOMPLETE",
                               "relationship_changes must be a list"))
        entry_scenes = entry.get("scene_ids")
        if not _text_list(entry_scenes):
            out.append(_defect(f"{where}.scene_ids", "CAST_INCOMPLETE",
                               "every selected person needs at least one scene_id"))
        else:
            for sid in entry_scenes:
                if known_scenes is not None and (type(sid) is not str
                                                 or sid not in known_scenes):
                    out.append(_defect(f"{where}.scene_ids", "UNKNOWN_SCENE",
                                       f"unknown scene '{sid}'"))
        if _anonymous(str(cid)) or _anonymous(str(entry.get("display_name_hint", ""))):
            out.append(_defect(f"{where}.character_id", "ANONYMOUS_IDENTITY",
                               "a generic descriptor is not an identity"))

    groups = _plain_list(manifest.get("crowd_groups", []))
    if groups is None:
        out.append(_defect("crowd_groups", "CROWD", "crowd_groups must be a list"))
        groups = []
    seen_groups = set()
    for index, group in enumerate(groups):
        out.extend(_validate_crowd(group, index, known_scenes))
        plain_group = _plain(group)
        gid = plain_group.get("crowd_group_id") if plain_group is not None else None
        if type(gid) is str:
            if gid in seen_groups:
                out.append(_defect(f"crowd_groups[{index}].crowd_group_id", "DUPLICATE_GROUP",
                                   f"duplicate crowd_group_id '{gid}'"))
            seen_groups.add(gid)

    for speaker in speakers or []:
        if not _text(speaker):
            out.append(_defect("speakers", "UNDECLARED_SPEAKER",
                               "an empty speaker cannot be resolved"))
        elif _anonymous(speaker):
            out.append(_defect("speakers", "ANONYMOUS_SPEAKER",
                               f"'{speaker}' is a generic descriptor; declare the person "
                               f"with an explicit character_id"))
        elif speaker not in selected:
            out.append(_defect("speakers", "UNDECLARED_SPEAKER",
                               f"speaker '{speaker}' is not in the cast manifest"))

    if out:
        raise CastDefect(out)
    return manifest
