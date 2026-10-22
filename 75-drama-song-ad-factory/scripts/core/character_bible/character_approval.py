#!/usr/bin/env python3
"""character_approval: the CHARACTER BIBLE approval boundary (W06-U1).

Generation, presentation, approval and continuation are ONE execution path,
never four optional steps (``run_stage``). The unit answers the D08 finding:
there was no revision-bound approval-and-advance contract for continuity.

What this module owns, all under ``$RUN/character/``:

  * ``bible.json``        -- the VERSIONED character bible: every character's
    name, role, background, appearance and voice/performance notes beside its
    ACTUAL generated or selected reference images (path + sha256 per view).
    ``revision`` bumps only when the content fingerprint changes.
  * ``presentation.json`` -- what the client was shown, versioned per content
    state: the card text and the exact image hashes presented.
  * ``approval.json``     -- the explicit VERSIONED APPROVAL EVENT: bound to
    tenant, run, artifact kind, bible revision, presentation version, every
    image hash, the requesting conversation, the approving identity and a
    timestamp. Nothing is approved that was not presented.
  * ``continuation.json`` -- the durable continuation queue. The approval and
    its continuation entry are written in ONE transaction boundary; a crash
    between them is repaired by the restart scan (``resume_continuations``),
    and a replayed approval re-acknowledges the existing decision and never
    enqueues duplicate work.

PRESENTATION goes to the ORIGINATING CONVERSATION (the run's canonical origin
record) as the typed artifact envelope the delivery contract defines, with the
actual reference pictures as attachments -- a bare path is never a preview.

APPROVAL is scoped by dependency class, so a revision blocks only what it
genuinely affects (the invalidation matrix, ``INVALIDATION_MATRIX``):

  image     reference image bytes and appearance  -> keyframes, video, ...
  voice     voice/performance notes               -> lip-sync, voice match
  identity  name, role, background                -> script text, storyboard

Unchanged character images keep their approval across unrelated lyric edits:
lyrics are not bible content, and a bible revision that leaves a class's hashes
untouched does not invalidate that class's approval. Downstream production
reads character references ONLY through ``locked_references``, which refuses
until the class it needs is approved for the current bytes -- so locked
references can never feed dependent work before the approval event.

CHARACTER WORK DOES NOT WAIT BEHIND THE MUSIC STAGE: the stage's only
prerequisite is stable character inputs (``ready``), which never consults the
music row or any other stage. Character work runs alongside the script the
moment its own inputs exist (``STAGE_CONTRACT`` is the executable declaration
the stage registry consumes).

Stdlib only, plus the run's own delivery contract module when the box has it.
No network here: ``run_stage`` takes the conversation's ``send`` sink, exactly
like the script and storyboard approval stages.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    from character_bible import character_bible as CB  # noqa: PLC0415
except ImportError:  # loaded with this directory on sys.path
    import character_bible as CB  # type: ignore

TOOL_NAME = "character_approval"
TOOL_VERSION = "1.0.0"

SCHEMA_BIBLE = "blackceo.character-bible/v2"
SCHEMA_PRESENTATION = "blackceo.character-presentation/v1"
SCHEMA_APPROVAL = "blackceo.character-approval/v1"
SCHEMA_CONTINUATION = "blackceo.character-continuation/v1"

#: Run-relative record paths. ONE folder, so the bible, the presentation, the
#: approval event and the continuation queue can never drift apart.
BIBLE_NAME = os.path.join("character", "bible.json")
PRESENTATION_NAME = os.path.join("character", "presentation.json")
APPROVAL_NAME = os.path.join("character", "approval.json")
CONTINUATION_NAME = os.path.join("character", "continuation.json")

ARTIFACT_KIND = "character_bible"

# --- dependency classes (the invalidation matrix's columns) ------------------
LOCK_IMAGE = "image"
LOCK_VOICE = "voice"
LOCK_IDENTITY = "identity"
LOCKS = (LOCK_IMAGE, LOCK_VOICE, LOCK_IDENTITY)

#: The card fields each class locks. Appearance and the pictures are one class:
#: both decide what the character LOOKS like, which is what the reference
#: pictures feed.
CARD_FIELDS = ("name", "role", "background", "appearance", "voice_notes")
CLASS_FIELDS = {
    LOCK_IMAGE: ("appearance", "images"),
    LOCK_VOICE: ("voice_notes",),
    LOCK_IDENTITY: ("name", "role", "background"),
}

#: Downstream stage -> the class whose current bytes it consumes. A revision
#: blocks a stage only when its own class changed ("revisions only block the
#: relevant downstream work"). ``continuity-bible`` is this stage itself.
DOWNSTREAM_LOCKS = {
    "script-lyrics": LOCK_IDENTITY,
    "continuity-bible": None,            # the whole card
    "storyboard": LOCK_IDENTITY,
    "image-keyframes": LOCK_IMAGE,
    "video-generation": LOCK_IMAGE,
    "lip-sync": LOCK_VOICE,
    "qc-retakes": LOCK_IMAGE,
    "assembly": LOCK_IMAGE,
    "final-qc": LOCK_IMAGE,
    "delivery": LOCK_IMAGE,
}

#: Change kind -> the classes it dirties. ``lyric_edit`` is the spec's own
#: example: an unrelated lyric line changes NO class, so nothing blocks and
#: unchanged character images retain their approval.
CHANGE_LOCKS = {
    "image_bytes": (LOCK_IMAGE,),
    "appearance": (LOCK_IMAGE,),
    "voice_notes": (LOCK_VOICE,),
    "identity": (LOCK_IDENTITY,),
    "character_added": LOCKS,
    "character_removed": LOCKS,
    "lyric_edit": (),
}

#: The exact invalidation matrix, as data. Verified by the suite.
INVALIDATION_MATRIX = {
    change: {
        "dirties": list(locks),
        "blocks": sorted(stage for stage, lock in DOWNSTREAM_LOCKS.items()
                         if lock in locks or (lock is None and bool(locks))),
        "retains_approval": [l for l in LOCKS if l not in locks],
    }
    for change, locks in CHANGE_LOCKS.items()
}

#: The stage contract the 12-stage registry consumes (W02 owns the registry;
#: this is this stage's executable declaration). Character work's ONLY
#: prerequisite is stable character inputs: it runs alongside the script and
#: NEVER waits behind the music stage.
STAGE_CONTRACT = {
    "stage": "continuity-bible",
    "prerequisites": ("character-inputs-stable",),
    "parallel_with": ("script-lyrics",),
    "never_blocks_on": ("music",),
    "approval_policy": "delivered-approval",
    "approval_record": APPROVAL_NAME,
    "gate": "character_approval.check",
    "references": "character_approval.locked_references",
    "completion_proof": ("character/bible.json", "character/approval.json"),
}

#: The words that approve. Same family as the script approval's, plus the
#: scoped phrase the combined cards use. Never a magic word requirement: an
#: unambiguous ordinary reply resolves from context (``_resolves_approve``).
_APPROVE = ("yes", "y", "approve", "approved", "go", "ok", "okay",
            "looks good", "looks good to me", "lgtm", "start", "approve both",
            "go ahead", "ship it")
#: Words that scope a generic reply to THIS approval among several pending.
_SCOPE_WORDS = ("character", "characters", "bible", "cast", "them", "her", "him")
#: Words that carry no decision of their own in an approval reply.
_FILLER = set(_SCOPE_WORDS) | {
    "the", "a", "an", "please", "now", "both", "it", "this", "that", "all",
    "and", "to", "me", "for", "us", "on", "with", "is", "looks",
}
#: Every word an approval reply may be made of (stem phrases included).
_APPROVE_WORDS = set(" ".join(_APPROVE).split()) | {
    "good", "fine", "great", "perfect", "yes", "yeah", "yep", "ok", "okay"}

APPROVED = "approved"
PENDING = "pending"
CLARIFY = "clarify"
NEEDS_EDIT = "needs-edit"

REASON_REQUIRED = "CHARACTER_APPROVAL_REQUIRED"
REASON_IMAGES_CHANGED = "CHARACTER_IMAGES_CHANGED"
REASON_VOICE_CHANGED = "CHARACTER_VOICE_CHANGED"
REASON_IDENTITY_CHANGED = "CHARACTER_IDENTITY_CHANGED"
REASON_CLASS_REASON = {
    LOCK_IMAGE: REASON_IMAGES_CHANGED,
    LOCK_VOICE: REASON_VOICE_CHANGED,
    LOCK_IDENTITY: REASON_IDENTITY_CHANGED,
}

#: The continuation command. Approval advances the run through the existing
#: continuation controller entrypoint -- never a "shall I continue?" prompt.
CONTINUE_COMMAND = ("python3 scripts/core/intake_preflight/factory.py next "
                    "--run-dir %s")


class ApprovalError(ValueError):
    """A refusal this boundary owns. ``reason_code`` names the part."""

    def __init__(self, reason_code, message):
        super().__init__("%s: %s" % (reason_code, message))
        self.reason_code = reason_code
        self.message = message


# --- small durable-file helpers ---------------------------------------------

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path, doc):
    """Atomic write: a reader never sees a half file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return doc


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


# --- the versioned bible -----------------------------------------------------

def _char_slug(entry):
    s = str(entry.get("slug") or entry.get("name") or "").strip()
    return s


def image_hashes(entry):
    """{view: sha256} over the character's ACTUAL reference pictures, read from
    disk now. A picture that is missing or empty is not hashable: it is named
    in ``ready`` and presentation refuses instead of showing a placeholder."""
    out = {}
    for view, img in (entry.get("images") or {}).items():
        path = img.get("path") if isinstance(img, dict) else img
        if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
            continue
        out[view] = sha256_file(path)
    return out


def _entry_image_state(entry):
    """The image state as the BIBLE recorded it (sha256 pinned at save time),
    falling back to the disk for a legacy record. Diffing two documents uses
    this; the gate compares it against the disk (``image_hashes``)."""
    out = {}
    for view, img in (entry.get("images") or {}).items():
        path = img.get("path") if isinstance(img, dict) else img
        sha = img.get("sha256") if isinstance(img, dict) else None
        if not sha and path and os.path.isfile(path):
            sha = sha256_file(path)
        out[view] = sha
    return out


def class_hashes(entry, disk=False):
    """The per-class fingerprints this approval binds to.

    ``image`` covers the reference pictures AND the appearance text (both say
    what the character looks like); ``voice`` the voice/performance notes;
    ``identity`` name, role and background.

    ``disk=True`` reads the picture bytes on disk RIGHT NOW (the gate and the
    approval event use it); the default prefers the sha the bible pinned at
    save time (diffing two bible documents uses it)."""
    imgs = image_hashes(entry) if disk else _entry_image_state(entry)
    return {
        LOCK_IMAGE: {"images": imgs,
                     "appearance": sha256_text(entry.get("appearance") or "")},
        LOCK_VOICE: {"voice_notes": sha256_text(entry.get("voice_notes") or "")},
        LOCK_IDENTITY: {k: sha256_text(entry.get(k) or "")
                        for k in ("name", "role", "background")},
    }


def fingerprint(doc):
    """The bible's content fingerprint. ``revision`` and bookkeeping are not
    content: re-saving identical content never looks like a revision."""
    chars = []
    for e in sorted((doc or {}).get("characters") or [], key=_char_slug):
        chars.append({
            "slug": _char_slug(e),
            "fields": {k: str(e.get(k) or "").strip() for k in CARD_FIELDS},
            "classes": class_hashes(e),
        })
    return sha256_text(json.dumps({"schema": SCHEMA_BIBLE, "characters": chars},
                                  sort_keys=True))


def bible_from_entries(entries):
    """A bible document from character entries.

    Each entry: name, role, background, appearance, voice_notes (the card) and
    ``images`` (view -> path, or view -> {"path": ...}). Every card string goes
    through the client-safety guard first -- the card is shown to the client.
    """
    chars = []
    for raw in entries or []:
        if not isinstance(raw, dict):
            raise ApprovalError("BAD_ENTRY", "every character entry must be an object")
        entry = {k: str(raw.get(k) or "").strip() for k in CARD_FIELDS}
        if not entry["name"]:
            raise ApprovalError("BAD_ENTRY", "every character entry needs a name")
        for k in CARD_FIELDS:
            CB.assert_client_safe(entry[k], "%s of %s" % (k, entry["name"]))
        imgs = {}
        for view, img in (raw.get("images") or {}).items():
            path = img.get("path") if isinstance(img, dict) else img
            if path:
                imgs[str(view)] = {"path": str(path)}
        entry["images"] = imgs
        entry["slug"] = str(raw.get("slug") or _slugify(entry["name"]))
        chars.append(entry)
    doc = {"schema": SCHEMA_BIBLE, "revision": 1, "characters": chars}
    doc["fingerprint"] = fingerprint(doc)
    return doc


def _slugify(name):
    s = "".join(c if c.isalnum() else "-" for c in str(name).lower()).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s or "character"


def load_bible(run_dir):
    """The run's bible document, or None when this run carries no character
    work. A corrupt file is an explicit unknown (ApprovalError), never read as
    "no characters"."""
    path = os.path.join(run_dir, BIBLE_NAME)
    if not os.path.isfile(path):
        return None
    doc = _read_json(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("characters"), list):
        raise ApprovalError("BIBLE_UNREADABLE", "%s exists but is not a bible "
                            "document" % BIBLE_NAME)
    return doc


def save_bible(run_dir, doc):
    """Persist the bible. The revision bumps ONLY when the content changed:
    an unrelated re-save keeps the revision, so nothing downstream re-blocks."""
    cur = load_bible(run_dir)
    fp = fingerprint(doc)
    rev = int((cur or {}).get("revision") or 0)
    if cur is None:
        rev = 1
    elif cur.get("fingerprint") != fp:
        rev += 1
    out = {"schema": SCHEMA_BIBLE, "revision": rev, "fingerprint": fp,
           "characters": doc.get("characters") or []}
    for entry in out["characters"]:
        for view, img in (entry.get("images") or {}).items():
            if isinstance(img, dict) and not img.get("sha256"):
                path = img.get("path")
                if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                    img["sha256"] = sha256_file(path)
    _write_json(os.path.join(run_dir, BIBLE_NAME), out)
    return out


# --- readiness: character work alongside the script, never behind music ------

def ready(run_dir):
    """Is this stage's own work eligible right now?

    The ONLY prerequisite is stable character inputs: every card field filled
    and every reference picture a real non-empty file. This never reads the
    music row or any other stage -- character work proceeds alongside the
    script once stable inputs exist and must not wait behind a broken music
    stage. Returns {"ready", "missing", "waits_on", "independent_of"}.
    """
    missing = []
    try:
        doc = load_bible(run_dir)
    except ApprovalError as e:
        return {"ready": False, "missing": [str(e)], "waits_on": [],
                "independent_of": list(STAGE_CONTRACT["never_blocks_on"])}
    if doc is None:
        return {"ready": False, "missing": ["no character bible is recorded for this run"],
                "waits_on": [],
                "independent_of": list(STAGE_CONTRACT["never_blocks_on"])}
    for entry in doc.get("characters") or []:
        who = _char_slug(entry) or "a character"
        for k in CARD_FIELDS:
            if not str(entry.get(k) or "").strip():
                missing.append("%s: %s is not filled in" % (who, k))
        imgs = entry.get("images") or {}
        if not imgs:
            missing.append("%s: no reference picture is selected" % who)
        for view, img in imgs.items():
            path = img.get("path") if isinstance(img, dict) else img
            if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
                missing.append("%s: the %s reference picture is missing or empty"
                               % (who, view))
    return {"ready": not missing, "missing": missing, "waits_on": [],
            "independent_of": list(STAGE_CONTRACT["never_blocks_on"])}


# --- presentation: the card, in the originating conversation -----------------

def card_text(entry, index, total, revision):
    """One character card: name, role, background, appearance, the
    voice/performance notes, and which actual reference pictures are attached.
    Every value passes the client-safety guard before it joins the text."""
    def safe(key):
        return CB.assert_client_safe(str(entry.get(key) or ""), key)
    views = ", ".join(sorted(entry.get("images") or {})) or "none attached"
    return "\n".join([
        "CHARACTER BIBLE (revision %d) - character %d of %d" % (revision, index, total),
        "",
        "Name: %s" % safe("name"),
        "Role: %s" % safe("role"),
        "Background: %s" % safe("background"),
        "Appearance: %s" % safe("appearance"),
        "Voice / performance notes: %s" % safe("voice_notes"),
        "",
        "Reference images attached: %s" % views,
    ])


INSTRUCTION = ('Reply "approve" to lock these character references, or tell me '
               'what to change and I will revise and send them again.')


def _outbox_mod():
    """The delivery contract (typed envelope + durable outbox), when the box
    carries it. Fail-soft like the factory's module loader: a box that does not
    have it still presents and approves, only without the outbox layer."""
    try:
        from choice_card.intake_card import delivery_outbox as DO  # noqa: PLC0415
        return DO
    except Exception:  # noqa: BLE001 - missing sibling never blocks the card
        return None


def origin_of(run_dir):
    """The run's canonical origin record (the originating conversation), or
    {} when the run carries none. Never a guessed destination."""
    DO = _outbox_mod()
    if DO is not None:
        return DO.load_origin(run_dir) or {}
    rec = _read_json(os.path.join(run_dir, "control", "origin.json"))
    return rec if isinstance(rec, dict) else {}


def presentation_pieces(doc):
    """The in-chat presentation: one card per character plus its ACTUAL
    reference pictures, then the approval instruction.

    Returns (cards, attachments): each card is {"text", "images"} where
    ``images`` is [(caption, path)] -- the pictures travel WITH the card they
    belong to. A missing or empty picture is a refusal (named), never a
    placeholder and never a bare path."""
    entries = doc.get("characters") or []
    if not entries:
        raise ApprovalError("NO_CHARACTERS", "the bible holds no characters to present")
    cards, attachments = [], []
    for i, entry in enumerate(entries, 1):
        paths = {}
        for view, img in (entry.get("images") or {}).items():
            path = img.get("path") if isinstance(img, dict) else img
            if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
                raise ApprovalError(
                    "IMAGE_MISSING", "%s has no real %s reference picture to "
                    "present (%s)" % (_char_slug(entry), view, path or "no path"))
            paths[view] = path
        mine = []
        for view, path in sorted(paths.items()):
            att = {
                "artifact_ref": "character/%s/%s" % (_char_slug(entry), view),
                "path": path,
                "mime_type": "image/" + (os.path.splitext(path)[1].lstrip(".") or "png"),
                "caption": "%s - %s (revision %d)" % (
                    CB.assert_client_safe(str(entry.get("name") or ""), "name"),
                    view, doc.get("revision") or 1),
                "sha256": sha256_file(path),
            }
            attachments.append(att)
            mine.append((att["caption"], path))
        cards.append({"text": card_text(entry, i, len(entries),
                                        doc.get("revision") or 1),
                      "images": mine})
    cards.append({"text": INSTRUCTION, "images": []})
    return cards, attachments


def _presentation_state(run_dir):
    rec = _read_json(os.path.join(run_dir, PRESENTATION_NAME))
    return rec if isinstance(rec, dict) else None


def _save_presentation(run_dir, doc, cards, attachments, envelope, sent):
    """The versioned presentation record. The version is CONTENT-versioned:
    it bumps only when the presented bytes (card text + image hashes) change,
    so unchanged character images keep one presentation and one approval."""
    content = sha256_text(json.dumps({
        "messages": [c["text"] for c in cards],
        "attachments": [a.get("sha256") for a in attachments],
    }, sort_keys=True))
    cur = _presentation_state(run_dir)
    version = int((cur or {}).get("version") or 0)
    if cur is None or cur.get("content_sha") != content:
        version += 1
    rec = {"schema": SCHEMA_PRESENTATION, "version": version,
           "content_sha": content, "bible_revision": doc.get("revision"),
           "image_hashes": {a.get("artifact_ref"): a.get("sha256")
                            for a in attachments},
           "message_sha256": [sha256_text(c["text"]) for c in cards],
           "origin": origin_of(run_dir), "envelope_sha256": (envelope or {}).get("sha256"),
           "sent": bool(sent), "at": time.time()}
    _write_json(os.path.join(run_dir, PRESENTATION_NAME), rec)
    return rec


def present(run_dir, send=None, run_id=""):
    """Present every character card with its actual reference pictures in the
    ORIGINATING conversation.

    ``send(message, images)`` is the conversation sink (images = [(caption,
    path)]), the same seam the script and storyboard stages use; with no sink
    the cards come back in the result for whoever called. The typed artifact
    envelope is built and queued in the durable outbox FIRST (prepared/queued
    are not sent), then delivered. Returns
    {"outcome", "messages", "attachments", "envelope", "presentation"}.
    """
    doc = load_bible(run_dir)
    if doc is None:
        raise ApprovalError("BIBLE_MISSING", "no character bible to present")
    # the pictures first: a missing picture refuses by name (IMAGE_MISSING),
    # never as a placeholder and never as a bare path
    cards, attachments = presentation_pieces(doc)
    r = ready(run_dir)
    if not r["ready"]:
        raise ApprovalError("INPUTS_NOT_STABLE", "; ".join(r["missing"]))
    origin = origin_of(run_dir)
    DO = _outbox_mod()
    envelope = None
    if DO is not None:
        envelope = DO.build_envelope(
            run_id or os.path.basename(os.path.normpath(run_dir)) or "run",
            origin.get("tenant_id", ""), "character-bible", ARTIFACT_KIND,
            doc.get("revision") or 1, origin,
            text="\n\n".join(c["text"] for c in cards),
            attachments=attachments, approval_state=PENDING,
            allowed_actions=("approve", "revise"))
        DO.Outbox(run_dir).enqueue(envelope)
    sent = False
    if send is not None:
        for card in cards:
            send(card["text"], list(card["images"]))
        sent = True
    rec = _save_presentation(run_dir, doc, cards, attachments, envelope, sent)
    return {"outcome": "waiting", "reason": "character-cards-presented",
            "messages": [c["text"] for c in cards],
            "attachments": [(a.get("caption"), a["path"]) for a in attachments],
            "envelope": envelope, "presentation": rec}


# --- the approval event ------------------------------------------------------

def approval_record(run_dir):
    """The run's approval event, or None."""
    rec = _read_json(os.path.join(run_dir, APPROVAL_NAME))
    return rec if isinstance(rec, dict) else None


def _continuation_doc(run_dir):
    rec = _read_json(os.path.join(run_dir, CONTINUATION_NAME))
    if isinstance(rec, dict) and isinstance(rec.get("entries"), list):
        return rec
    return {"schema": SCHEMA_CONTINUATION, "entries": []}


def _enqueue_continuation(run_dir, event, now=None):
    """The durable continuation queue entry for one approval event. The entry
    id is deterministic (tenant/run/artifact/revision), so a replay enqueues
    NOTHING new and a restart scan finds exactly one entry per decision."""
    doc = _continuation_doc(run_dir)
    entry_id = "/".join([event.get("tenant_id", ""), event.get("run_id", ""),
                         ARTIFACT_KIND, str(event.get("bible_revision", ""))])
    for e in doc["entries"]:
        if e.get("id") == entry_id:
            return e, False
    entry = {"id": entry_id, "event": "character-approved", "state": "queued",
             "run_id": event.get("run_id", ""), "bible_revision": event.get("bible_revision"),
             "approved_at": event.get("at"),
             "next_action": CONTINUE_COMMAND % (event.get("run_path") or "$RUN"),
             "at": now or time.time()}
    doc["entries"].append(entry)
    _write_json(os.path.join(run_dir, CONTINUATION_NAME), doc)
    return entry, True


def _pending_approvals(run_dir):
    """The distinct approval items pending in this run. A generic reply may not
    pick between several (spec 5.2): only a scoped reply or reply context
    resolves it. Reads sibling records read-only; a broken sibling read is not
    a phantom pending item."""
    pending = []
    pres = _presentation_state(run_dir)
    rec = approval_record(run_dir)
    if pres is not None and not (rec and rec.get("status") == APPROVED):
        pending.append("character-bible")
    for name, key in (("creative/script-approval.json", "script"),
                      ("song-choices/state.json", "song"),
                      ("storyboard/approval.json", "storyboard")):
        doc = _read_json(os.path.join(run_dir, name))
        if isinstance(doc, dict):
            status = str(doc.get("status") or doc.get("state") or "").lower()
            if status in ("pending", "waiting") or (
                    doc.get("required") and status != "approved"):
                pending.append(key)
    return pending


def _resolves_approve(reply):
    """True when the reply unambiguously approves: the known approval words,
    or an ordinary sentence made only of approval words, filler and scope
    words ("approve the character bible"). A reply carrying ANY other content
    ("make her taller") is a revision request, never an approval."""
    s = str(reply or "").strip().lower().strip(" .!")
    if s in _APPROVE:
        return True
    if not s:
        return False
    words = [w for w in re.split(r"[^a-z']+", s) if w]
    if not words:
        return False
    return (all(w in _FILLER or w in _APPROVE_WORDS for w in words)
            and any(w in _APPROVE_WORDS for w in words))


def _scoped(reply):
    low = str(reply or "").lower()
    return any(w in low for w in _SCOPE_WORDS)


def approve(run_dir, reply, approved_by=None, run_id="", now=None):
    """The client's reply becomes the explicit VERSIONED APPROVAL EVENT.

    approve -> write the event bound to the bible revision, the presentation
    version and every image hash, and enqueue continuation in the same
    transaction boundary (acknowledge + advance, never "shall I continue?").
    A replayed reply re-acknowledges the existing decision and enqueues no
    duplicate work. Anything else is a revision request ("needs-edit"). A
    generic reply while several distinct approvals are pending asks ONE
    clarifying question instead of guessing.

    Returns {"status": approved|clarify|needs-edit|error, ...}.
    """
    now = now or time.time()
    doc = load_bible(run_dir)
    if doc is None:
        return {"status": "error", "reason_code": "BIBLE_MISSING",
                "detail": "no character bible is recorded for this run"}
    pres = _presentation_state(run_dir)
    if pres is None:
        return {"status": "error", "reason_code": "UNSEEN_ARTIFACT",
                "detail": "a generic answer cannot approve an unseen artifact; "
                          "present the character cards first"}
    if not _resolves_approve(reply):
        return {"status": NEEDS_EDIT, "edit": str(reply or "").strip(),
                "detail": "recorded as a character revision request; the bible "
                          "changes and the cards are presented again"}
    others = [p for p in _pending_approvals(run_dir) if p != "character-bible"]
    if others and not _scoped(reply):
        return {"status": CLARIFY,
                "question": "Which approval do you mean - the character bible, "
                            "or the %s? Reply naming it." % " or ".join(others)}
    origin = origin_of(run_dir)
    event = {
        "schema": SCHEMA_APPROVAL, "status": APPROVED,
        "tenant_id": origin.get("tenant_id", ""),
        "run_id": run_id or os.path.basename(os.path.normpath(run_dir)) or "run",
        "artifact_kind": ARTIFACT_KIND,
        "bible_revision": doc.get("revision"),
        "presentation_version": pres.get("version"),
        "image_hashes": { _char_slug(e): image_hashes(e)
                          for e in doc.get("characters") or []},
        "class_hashes": { _char_slug(e): class_hashes(e, disk=True)
                          for e in doc.get("characters") or []},
        "origin": {"channel": origin.get("channel", ""),
                   "conversation_id": origin.get("conversation_id", ""),
                   "thread_id": origin.get("thread_id", "")},
        "approved_by": str(approved_by or ""), "at": now,
    }
    prev = approval_record(run_dir)
    if (prev and prev.get("status") == APPROVED
            and prev.get("bible_revision") == event["bible_revision"]
            and prev.get("image_hashes") == event["image_hashes"]):
        entry, fresh = _enqueue_continuation(
            run_dir, dict(prev, run_path=run_dir))
        return {"status": APPROVED, "replayed": True, "event": prev,
                "continuation": entry, "continuation_enqueued": fresh,
                "next_action": entry.get("next_action")}
    _write_json(os.path.join(run_dir, APPROVAL_NAME), event)
    entry, fresh = _enqueue_continuation(
        run_dir, dict(event, run_path=os.path.abspath(run_dir)), now=now)
    return {"status": APPROVED, "replayed": False, "event": event,
            "continuation": entry, "continuation_enqueued": fresh,
            "next_action": entry.get("next_action")}


# --- the gate and locked references ------------------------------------------

def check(run_dir, need=LOCK_IMAGE, bible=None):
    """The gate dependent production calls. None = go; else the refusal dict.

    ``need`` is the dependency class the caller consumes (``LOCK_IMAGE``,
    ``LOCK_VOICE``, ``LOCK_IDENTITY``, or the whole card with ``None``). The
    class passes only when it is approved AND its bytes are unchanged since
    the approval: an unrelated lyric edit changes nothing here, while a
    re-generated picture blocks exactly the stages that consume pictures.
    """
    doc = bible if bible is not None else load_bible(run_dir)
    if doc is None:
        return None                      # no character work: nothing to gate
    rec = approval_record(run_dir)
    if not rec or rec.get("status") != APPROVED:
        return {"reason_code": REASON_REQUIRED,
                "detail": "the character bible is not approved yet; locked "
                          "character references may not feed dependent work"}
    needs = LOCKS if need is None else (need,)
    if any(l not in LOCKS for l in needs):
        raise ApprovalError("BAD_LOCK", "unknown dependency class %r" % (need,))
    for entry in doc.get("characters") or []:
        who = _char_slug(entry)
        approved_classes = (rec.get("class_hashes") or {}).get(who) or {}
        cur = class_hashes(entry, disk=True)
        for lock in needs:
            if approved_classes.get(lock) != cur.get(lock):
                return {"reason_code": REASON_CLASS_REASON[lock],
                        "detail": "%s's %s content changed after the approval "
                                  "(bible revision %s, approved revision %s); "
                                  "re-present and approve again before this "
                                  "work runs" % (who, lock, doc.get("revision"),
                                                 rec.get("bible_revision"))}
    return None


def locked_references(run_dir, need=LOCK_IMAGE):
    """THE sanctioned source of character references for dependent production.

    Returns [{name, role, slug, images: {view: {"path", "sha256"}}}] exactly as
    approved. Raises :class:`ApprovalError` when the class the caller needs is
    not approved for the current bytes -- locked references can never feed
    dependent work before the approval event."""
    refusal = check(run_dir, need=need)
    if refusal is not None:
        raise ApprovalError(refusal["reason_code"], refusal["detail"])
    doc = load_bible(run_dir)
    out = []
    for entry in (doc or {}).get("characters") or []:
        hashes = image_hashes(entry)
        imgs = {}
        for view, sha in hashes.items():
            img = (entry.get("images") or {}).get(view)
            path = img.get("path") if isinstance(img, dict) else img
            imgs[view] = {"path": path, "sha256": sha}
        out.append({"name": entry.get("name"), "slug": _char_slug(entry),
                    "role": entry.get("role"), "images": imgs})
    return out


# --- the invalidation matrix -------------------------------------------------

def changes_since_approval(run_dir):
    """Which change kinds separate the APPROVED bible from the run's current
    state -- the invalidation decision the gate and every caller uses.

    An unrelated lyric edit is not bible content and never appears here; that
    is exactly why unchanged character images retain their approval across
    lyric edits. With no approval yet there is nothing to retain or block."""
    doc = load_bible(run_dir)
    rec = approval_record(run_dir)
    if doc is None or not rec:
        return set()
    approved = rec.get("class_hashes") or {}
    changes, cur_slugs = set(), set()
    for entry in doc.get("characters") or []:
        who = _char_slug(entry)
        cur_slugs.add(who)
        was = approved.get(who)
        if not isinstance(was, dict):
            changes.add("character_added")
            continue
        cur = class_hashes(entry, disk=True)
        if was.get(LOCK_IMAGE, {}).get("images") != cur[LOCK_IMAGE]["images"]:
            changes.add("image_bytes")
        if was.get(LOCK_IMAGE, {}).get("appearance") != cur[LOCK_IMAGE]["appearance"]:
            changes.add("appearance")
        if was.get(LOCK_VOICE, {}).get("voice_notes") != cur[LOCK_VOICE]["voice_notes"]:
            changes.add("voice_notes")
        if was.get(LOCK_IDENTITY) != cur[LOCK_IDENTITY]:
            changes.add("identity")
    for who in approved:
        if who not in cur_slugs:
            changes.add("character_removed")
    return changes


def blocked_downstream(changes):
    """The downstream stages one set of change kinds blocks. A stage blocks
    only when its own dependency class changed -- and a change-free set (an
    unrelated lyric edit) blocks nothing at all."""
    dirty = set()
    for c in changes:
        dirty.update(CHANGE_LOCKS.get(c, ()))
    return sorted(stage for stage, lock in DOWNSTREAM_LOCKS.items()
                  if lock in dirty or (lock is None and bool(dirty)))


def retained_locks(changes):
    """Which approval classes survive one set of change kinds."""
    dirty = set()
    for c in changes:
        dirty.update(CHANGE_LOCKS.get(c, ()))
    return [l for l in LOCKS if l not in dirty]


# --- restart scan and continuation ------------------------------------------

def resume_continuations(run_dir):
    """The restart scan (spec 5.2): after a crash or process restart, the
    pending continuation queue is read back and the same run resumes.

    A decision persisted but crashed before its continuation entry was written
    is REPAIRED here (same deterministic entry id, so never a duplicate), and
    every queued entry is returned with its next action. Returns
    {"entries", "repaired", "run_id"}."""
    rec = approval_record(run_dir)
    repaired = False
    if rec and rec.get("status") == APPROVED:
        doc = _continuation_doc(run_dir)
        before = len(doc["entries"])
        _entry, fresh = _enqueue_continuation(
            run_dir, dict(rec, run_path=os.path.abspath(run_dir)))
        repaired = fresh or len(_continuation_doc(run_dir)["entries"]) != before
    doc = _continuation_doc(run_dir)
    return {"entries": [e for e in doc["entries"] if e.get("state") == "queued"],
            "repaired": repaired,
            "run_id": (rec or {}).get("run_id", "")}


# --- the ONE execution path --------------------------------------------------

def run_stage(run_dir, send=None, reply=None, apply_edit=None):
    """Generation, presentation, approval and continuation as ONE path.

    Mirrors ``script_approval.stage.run_stage``:

      outcome "go"          approval current for every class; the run
                            continues automatically (the continuation entry
                            is already queued -- no "shall I continue?").
      outcome "waiting"     cards presented (once) and the run waits for the
                            client; a re-send happens only when nothing was
                            delivered yet.
      outcome "blocked"     character inputs are not stable yet (named).
      outcome "edit-required" the client asked for a change and no
                            ``apply_edit`` callback was given: apply it to the
                            bible (``save_bible``) and call again.

    This stage never reads the music row: character work proceeds alongside
    the script once stable inputs exist and never waits behind a broken music
    stage."""
    r = ready(run_dir)
    if not r["ready"]:
        return {"outcome": "blocked", "problems": r["missing"]}
    rec = approval_record(run_dir)
    if rec and rec.get("status") == APPROVED and check(run_dir, need=None) is None:
        resume = resume_continuations(run_dir)
        return {"outcome": "go", "reason": "approved",
                "continuation": resume["entries"],
                "next_action": CONTINUE_COMMAND % os.path.abspath(run_dir),
                "messages": []}
    if reply is None:
        pres = _presentation_state(run_dir)
        if pres is not None and pres.get("sent"):
            return {"outcome": "waiting", "reason": "awaiting-client-reply",
                    "messages": []}
        p = present(run_dir, send=send)
        return {"outcome": "waiting", "reason": p.get("reason"),
                "messages": p.get("messages", []),
                "attachments": p.get("attachments", []),
                "presentation": p.get("presentation")}
    res = approve(run_dir, reply)
    if res["status"] == APPROVED:
        return {"outcome": "go", "reason": "approved",
                "continuation": [res["continuation"]],
                "next_action": res.get("next_action"),
                "replayed": res.get("replayed", False),
                "messages": ["Approved. The character references are locked "
                             "and the run continues."]}
    if res["status"] == CLARIFY:
        return {"outcome": "waiting", "reason": "clarify",
                "question": res["question"], "messages": [res["question"]]}
    if res["status"] == NEEDS_EDIT:
        if apply_edit is None:
            return {"outcome": "edit-required", "edit": res["edit"],
                    "messages": []}
        doc = load_bible(run_dir)
        new = apply_edit(res["edit"], doc)
        if not isinstance(new, dict) or not new.get("characters"):
            return {"outcome": "blocked",
                    "problems": ["the revision produced no characters"]}
        save_bible(run_dir, new)
        p = present(run_dir, send=send)
        return {"outcome": "waiting", "reason": "revised-and-presented",
                "messages": p.get("messages", []),
                "attachments": p.get("attachments", []),
                "presentation": p.get("presentation")}
    return {"outcome": "blocked", "problems": [res.get("detail", "approval failed")]}


# --- command line (the seam the continuation controller calls) ---------------

def envelope(command, run_id, outcome, reason_code, next_action, data=None):
    """The factory envelope shape, so a controller can consume this CLI the
    same way it consumes every other stage command."""
    return {"schema_version": SCHEMA_APPROVAL, "tool_version": TOOL_VERSION,
            "command": command, "run_id": run_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "data": data or {}}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Character bible approval boundary.")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("present", "approve", "check", "status", "resume"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", required=True)
        if name == "approve":
            p.add_argument("--reply", required=True)
            p.add_argument("--approved-by", default="")
        if name == "check":
            p.add_argument("--need", default=LOCK_IMAGE,
                           choices=[LOCK_IMAGE, LOCK_VOICE, LOCK_IDENTITY, "all"])
    a = ap.parse_args(argv)
    run_dir = str(Path(a.run_dir).expanduser().resolve())
    sid = os.path.basename(os.path.normpath(run_dir)) or "run"
    try:
        if a.cmd == "present":
            p = present(run_dir)
            code = p.get("reason") or (
                "inputs-not-stable" if p["outcome"] == "blocked" else "presented")
            return _emit(envelope("present", sid, p["outcome"], code,
                                  'Reply "approve" to lock the references, or '
                                  'name what to change.',
                                  data=p))
        if a.cmd == "approve":
            res = approve(run_dir, a.reply, approved_by=a.approved_by, run_id=sid)
            ok = res["status"] == APPROVED
            return _emit(envelope("approve", sid, "ok" if ok else res["status"],
                                  res["status"],
                                  res.get("next_action") or res.get("question")
                                  or res.get("detail", ""), data=res))
        if a.cmd == "check":
            need = None if a.need == "all" else a.need
            ref = check(run_dir, need=need)
            return _emit(envelope("check", sid, "ok" if ref is None else "rejected",
                                  "GO" if ref is None else ref["reason_code"],
                                  "locked references may feed dependent work"
                                  if ref is None else ref["detail"], data={}))
        if a.cmd == "status":
            return _emit(envelope("status", sid, "ok", "status", "",
                                  data={"ready": ready(run_dir),
                                        "approval": approval_record(run_dir),
                                        "presentation": _presentation_state(run_dir)}))
        if a.cmd == "resume":
            r = resume_continuations(run_dir)
            return _emit(envelope("resume", sid, "ok", "continuations",
                                  r["entries"][0]["next_action"] if r["entries"]
                                  else "nothing is queued", data=r))
    except ApprovalError as e:
        return _emit(envelope(a.cmd, sid, "error", e.reason_code, str(e)))
    ap.print_help()
    return 2


def _emit(env):
    print(json.dumps(env, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
