#!/usr/bin/env python3
"""Revision-aware approval events (spec 5.1/5.2; findings D07, D17).

The record ($RUN/creative/script-approval.json) keeps its legacy gate fields --
required / status / sent / lyrics_sha / maker / approved_by, which the music
gates read -- and adds the revision-aware model:

    artifacts   the current revision (revision, sha256) per artifact kind
    asks        each presentation: which kinds, which revisions, which message
    approvals   decision events bound to tenant, run, artifact kind,
                revision/hash, requesting conversation, approving identity and
                timestamp
    outbox      acknowledgements and continuation enqueues, written in the SAME
                atomic save as the decision -- one transaction boundary

Invalidation (spec 5.2): a change to an artifact invalidates that kind's
approval and every DESCENDANT kind's approval. A derived kind never silently
reuses an approval of an older parent revision: a revised script must be
re-approved together with its lyrics. Unchanged artifacts keep their approvals:
a lyric line change never touches character-image approvals, and a script edit
keeps them too (character images derive from the story, not the script).

    script            <- story
    lyrics            <- script
    character_images  <- story
    music             <- lyrics
    storyboard        <- script, lyrics, character_images

Every approval is recorded only from an actual client reply parsed by
``interpret_reply``. Nothing here sends, pays, resumes a run, or answers the
client's creative approval on their behalf. A replayed reply re-acknowledges
the existing decision and enqueues no second continuation. Missing or corrupt
data is an explicit UNKNOWN -- never permission.

Stdlib only; no network, no spend.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

RECORD_NAME = os.path.join("creative", "script-approval.json")
SCHEMA_VERSION = 2

#: explicit unknown, never permission
UNKNOWN_STATE = "unknown"
UNKNOWN_REASON = "APPROVAL_STATE_UNKNOWN"

#: DERIVED_FROM[child] = the kinds it is derived from. The transitive closure
#: decides what a change invalidates; kinds outside it keep their approvals.
DERIVED_FROM = {
    "script": ("story",),
    "lyrics": ("script",),
    "character_images": ("story",),
    "music": ("lyrics",),
    "storyboard": ("script", "lyrics", "character_images"),
}

BOTH = ("script", "lyrics")

#: ordinary unambiguous language approves: no magic words required
_AFFIRM = (
    "yes", "y", "yeah", "yep", "yup", "ya", "sure", "ok", "okay", "kk",
    "approve", "approved", "go", "go ahead", "good to go", "proceed",
    "continue", "start", "ship it", "ship", "let's do it", "lets do it",
    "do it", "let's go", "lets go", "make it", "make the song", "sounds good",
    "sounds great", "sounds perfect", "looks good", "looks great", "looks perfect",
    "looks right", "love it", "great", "perfect", "wonderful", "fantastic",
    "amazing", "exactly", "correct", "right", "absolutely", "of course",
    "that works", "works for me", "no changes", "as is", "lgtm", "+1",
    "i approve", "approved!", "yes please", "yes!", "ok!", "okay!",
)
_NEGATE = ("not", "nope", "don't", "dont", "never", "wait", "hold", "stop",
           "nothing", "none", "neither", "nobody", "no one",
           "cannot", "can't", "cant", "won't", "wont", "shouldn't", "shouldnt",
           "wouldn't", "wouldnt", "isn't", "isnt", "doesn't", "doesnt",
           "didn't", "didnt", "without", "refuse", "refused", "refusing",
           "decline", "declined")
_REVISE = ("no", "revise", "change", "edit", "fix", "instead", "not yet", "later")

_KIND_WORDS = {
    "script": ("script", "story"),
    "lyrics": ("lyrics", "lyric", "words", "song text"),
    "character_images": ("character", "characters", "images", "pictures"),
    "music": ("music", "song", "audio"),
    "storyboard": ("storyboard", "shots"),
}
_REV_RE = re.compile(r"\b(?:rev(?:ision)?|ver(?:sion)?|v)\s*[-:.]?\s*(\d+)\b", re.I)

#: idioms where a negation word is an affirmation ("approved, no changes").
#: Masked BEFORE any screen, so a plain approval with no edits stays one.
_AFFIRM_IDIOMS = (
    r"\bno (?:more |further |other )?changes\b",
    r"\bno (?:more |further )?(?:edits|revisions|tweaks|notes|objections)\b",
    r"\bas is\b",
    r"\bwithout (?:any |further )?changes\b",
    r"\bnothing (?:else )?to change\b",
)

#: an edit request sitting next to an approval is NOT a clear approval: the
#: artifact it approves would differ from the one it asks to change
_CHANGE_WORDS = (
    "change", "changes", "changing", "revise", "revises", "revised",
    "edit", "edits", "edited", "fix", "fixes", "fixing", "tweak", "tweaks",
    "alter", "adjust", "reword", "rewrite", "rework", "update", "replace",
    "remove", "swap", "different", "instead", "rethink",
)

#: scoping the approval to part of the package names no whole artifact
_SCOPE_MARKS = ("except", "excepting", "except that", "other than", "apart from",
                "aside from", "excluding", "but not", "all but", "everything but")

_SELECTION_RE = re.compile(
    r"\b(?:option|choice|number|no)\s*[-:.]?\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b")

_QUESTION_START = ("am", "are", "can", "could", "did", "do", "does", "had", "has",
                   "have", "how", "is", "may", "might", "shall", "should", "was",
                   "were", "what", "when", "where", "which", "who", "why", "will",
                   "would")

_CONDITIONAL_RE = re.compile(
    r"\b(?:if|unless|until|once|when|whenever|after|before|provided|assuming|"
    r"supposing)\b|\bas long as\b")

#: someone else's words, or a question about approving, are never the client's
#: own decision -- never an approval
_REPORTED_RE = re.compile(
    r"\b(?:said|says|told|wrote|replied|mentioned|suggested|thinks?|thought|"
    r"asked|wants?|wanted|recommends?|recommended)\b[^.!?]{0,40}\bapprov|"
    r"\b(?:he|she|they|him|her|them|his|hers|their|someone|somebody|anyone|"
    r"friend|boss|partner|lawyer|mom|dad|mother|father)\b[^.!?]{0,40}"
    r"\b(?:said|says|told|wrote|replied|suggested|thinks?|asked|wants?)\b")
_QUOTE_CHARS = ('"', "“", "”", "‘", "’", "«", "»")

_APPROVAL_RE = re.compile(r"\bapprov[a-z]*\b")
#: where one clause ends and another opinion begins
_CLAUSE_RE = re.compile(
    r"\s*(?:,?\s*(?:but|however|although|though|yet|except(?:\s+that)?|other than|"
    r"apart from|aside from|excluding|unless|until|if|when|once|after|before)\b).*$",
    re.S | re.I)

#: words that still name the whole package (or nothing) after an approval
_STOPWORDS = frozenset("""
a about all also am an and any anyone anything are as at be been but by can
completely done exactly for from fully go going had has have he her here him
his how i in is it its itself just lets me my no not nothing now of on one
ones or other our please perfect really right so than thanks thank thx that
the their them there these they this those to totally us was we well were
what when where which who whole entire will with without would yes yeah yep
yup ya ok okay good great fine work works thing things package artifact
artifacts creative everything anything both all-it exactly ship proceed
rev revision ver version v new old latest final draft copy
""".split())

_KIND_TOKENS = frozenset(
    w for words in _KIND_WORDS.values() for w in re.findall(r"[a-z]+", " ".join(words)))


# --------------------------------------------------------------------------- #
# whole-reply closed grammar -- the character_approval._resolves_approve rule.
#
# A reply is a BARE APPROVAL only when the WHOLE of it is built from this closed
# grammar AND at least one word in it approves. A substring hit anywhere, or an
# affirmative first word, is never enough: any content word outside the grammar
# -- an instruction, a condition, a negation, an opinion with substance -- makes
# the reply something other than a bare approval, and anything other than a bare
# approval never opens the gate.
#
# The approval vocabulary is DERIVED from _AFFIRM above; only words that carry no
# decision of their own are named by hand. Negation, condition and revision words
# are deliberately ABSENT from the grammar, so "no good", "not approved", "make
# the story longer" and "all of this is wrong" cannot be read as approvals.
# --------------------------------------------------------------------------- #

def _tokens(text):
    return [w for w in re.split(r"[^a-z0-9+']+", str(text or "")) if w]


def _norm(text):
    return re.sub(r"[^a-z0-9+' ]+", " ", str(text or "").strip().lower()).strip()


#: words that carry an approval of their own
_APPROVE_SIGNALS = frozenset("""
+1 absolutely amazing approve approved correct continue do exactly fine
fantastic go good great kk lgtm love make ok okay perfect proceed ship sounds
start sure work works wonderful ya yeah yep yes yup y
""".split())

#: words that carry no decision at all -- filler, politeness, the copulas, the
#: scope words and the displayed revision labels. Negation, condition, contrast
#: and revision words are deliberately ABSENT.
_NO_DECISION = frozenset("""
a all am an and are as at ahead be been both by course creative entire
everything artifact artifacts else for i in is it its let's lets me my now of
on our package please rest rev revision right so thanks thank thx that the to
too us v ver version was were whole with
""".split())

#: never grammar, whatever phrase they arrived from: negation, contrast,
#: condition, disjunction and revision verbs refuse the reply by their presence.
#: "no changes" is an approval ONLY as a whole idiom; bare "no" never is.
_BLOCKED = (frozenset(_NEGATE) | frozenset(_REVISE) | frozenset(_CHANGE_WORDS) |
            frozenset("but however although though yet or unless until if when "
                      "whenever once after before instead provided assuming "
                      "supposing while because since".split()))

#: every word an approval reply may be made of
_GRAMMAR_WORDS = ((frozenset(w for phrase in _AFFIRM for w in _tokens(_norm(phrase)))
                   | _NO_DECISION | _KIND_TOKENS) - _BLOCKED)

#: exact whole-reply matches only -- "do it" is one approval phrase, never a
#: question; "the villain's name is perfect as is, but ..." is NOT a phrase
_AFFIRM_EXACT = frozenset(_AFFIRM) | frozenset(_norm(p) for p in _AFFIRM)

#: the words that at least name or offer an approval (routing only)
_MENTION_TOKENS = frozenset(
    w for phrase in _AFFIRM for w in _tokens(_norm(phrase)))


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# derivation graph
# --------------------------------------------------------------------------- #

def descendants(kind):
    """Every kind derived (transitively) from ``kind``."""
    out, stack = set(), [kind]
    while stack:
        k = stack.pop()
        for child, parents in DERIVED_FROM.items():
            if k in parents and child not in out:
                out.add(child)
                stack.append(child)
    return out


# --------------------------------------------------------------------------- #
# record I/O -- one file, one atomic transaction boundary
# --------------------------------------------------------------------------- #

def record_path(run_dir):
    return os.path.join(run_dir, RECORD_NAME)


def corrupt_record(detail):
    """The gate-visible sentinel for a present-but-unreadable record: an
    explicit unknown that refuses generation, never a silent 'not asked'."""
    return {"required": True, "status": UNKNOWN_STATE, "corrupt": True,
            "unknown_detail": detail, "schema_version": SCHEMA_VERSION}


def is_unknown_record(rec):
    return isinstance(rec, dict) and (rec.get("corrupt") or rec.get("status") == UNKNOWN_STATE)


def load_record(run_dir):
    """("missing", None) / ("corrupt", sentinel) / ("ok", record)."""
    try:
        with open(record_path(run_dir), encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError) as e:
        return "corrupt", corrupt_record("script-approval.json is unreadable: %s" % e)
    if not isinstance(raw, dict):
        return "corrupt", corrupt_record("script-approval.json is not an object")
    return "ok", raw


def save_record(run_dir, rec):
    """Atomic single-file write: the decision, its acknowledgement and its
    continuation are persisted together or not at all."""
    p = record_path(run_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return rec


def _new_record():
    return {"schema_version": SCHEMA_VERSION, "required": True, "status": "pending",
            "sent": False, "artifacts": {}, "asks": [], "approvals": [], "outbox": []}


def ensure_record(rec):
    rec = dict(rec) if isinstance(rec, dict) and not is_unknown_record(rec) else _new_record()
    for key, default in (("artifacts", {}), ("asks", []), ("approvals", []), ("outbox", [])):
        rec.setdefault(key, default)
    rec["schema_version"] = SCHEMA_VERSION
    return rec


# --------------------------------------------------------------------------- #
# artifacts and asks
# --------------------------------------------------------------------------- #

def register_artifact(rec, kind, sha256, revision=None):
    """Record the presented revision of an artifact kind.

    Unchanged content (same sha) changes nothing: unchanged artifacts keep
    their approvals. Changed content moves the revision forward and invalidates
    this kind's approvals and every DESCENDANT kind's approvals -- the derived
    kinds never silently reuse an approval of the older parent revision.
    """
    cur = rec["artifacts"].get(kind) or {}
    if cur.get("sha256") == sha256:
        return {"changed": False, "kind": kind, "revision": cur.get("revision"),
                "invalidated": []}
    rev = revision if revision is not None else int(cur.get("revision") or 0) + 1
    rec["artifacts"][kind] = {"revision": rev, "sha256": sha256, "registered_at": utcnow()}
    doomed = {kind} | descendants(kind)
    invalidated = []
    for ev in rec["approvals"]:
        if ev.get("state") == "active" and ev.get("kind") in doomed:
            ev["state"] = "invalidated"
            ev["invalidated_by"] = {"kind": kind, "revision": rev, "sha256": sha256}
            invalidated.append(ev.get("event_id"))
    return {"changed": True, "kind": kind, "revision": rev, "invalidated": invalidated}


def open_ask(rec, kinds, message_id=None, ask_id=None):
    """Bind a presentation identity to the exact displayed artifact revisions.

    Resending unchanged content keeps its ask. A changed revision supersedes
    the old ask, so its reply binding cannot silently approve new content.
    """
    kinds = list(kinds)
    revisions = {k: (rec["artifacts"].get(k) or {}).get("revision") for k in kinds}
    for a in rec["asks"]:
        if a.get("state") == "open" and a.get("kinds") == kinds:
            if a.get("revisions") != revisions:
                a["state"] = "superseded"
                continue
            if message_id:
                a["message_id"] = message_id
            return a
    ask_id = ask_id or _id("ask", message_id or "", ",".join(kinds),
                          json.dumps(revisions, sort_keys=True), utcnow())
    ask = {"ask_id": ask_id, "kinds": kinds, "message_id": message_id,
           "revisions": revisions, "state": "open", "opened_at": utcnow()}
    rec["asks"].append(ask)
    return ask


def open_asks(rec):
    return [a for a in rec.get("asks") or [] if a.get("state") == "open"]


# --------------------------------------------------------------------------- #
# decisions -- bound, transactional, replay-safe
# --------------------------------------------------------------------------- #

def _id(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:24]


def active_approval(rec, kind, sha256=None):
    """The live approval of one kind, or None. Valid only at the revision that
    was approved: an approval of an older hash is stale, not permission."""
    for ev in reversed(rec.get("approvals") or []):
        if ev.get("state") != "active" or ev.get("kind") != kind:
            continue
        if sha256 is not None and ev.get("sha256") != sha256:
            continue
        return ev
    return None


def approved_kinds(rec):
    out = []
    for kind, art in (rec.get("artifacts") or {}).items():
        if active_approval(rec, kind, art.get("sha256")):
            out.append(kind)
    return out


def decisions(rec):
    """Decision groups by decision id: one client reply = one decision."""
    order, by_id = [], {}
    for ev in rec.get("approvals") or []:
        did = ev.get("decision_id")
        if did not in by_id:
            by_id[did] = []
            order.append(did)
        by_id[did].append(ev)
    return [(d, by_id[d]) for d in order]


def pending_continuations(rec):
    """What a restart resumes: the same runs, never a new campaign or attempt."""
    return [o for o in rec.get("outbox") or []
            if o.get("kind") == "continuation" and o.get("state") == "pending"]


def record_decision(rec, kinds, ctx):
    """Persist the client's approval transactionally: one decision event per
    kind, one acknowledgement and one continuation -- all in the caller's single
    save (one outbox boundary). A replay (same decision key) re-acknowledges the
    existing decision and enqueues nothing new.

    ctx: tenant_id, run_id, conversation_id, thread_id, approved_by (the
    approving identity), reply_to_message_id, reply_text_sha. Every field is
    bound into each event; missing identity is recorded as missing, never
    invented. The decision key is the reply's message id when the channel gave
    one -- one message approves once, ever -- and otherwise binds the exact
    revisions approved, so the same words on a later revision are a new
    decision, not a replay.
    """
    ctx = ctx or {}
    provenance = reply_context_status(rec, ctx)
    if not provenance["ok"] or is_preference_reply(ctx.get("reply_text")):
        raise ValueError(provenance["detail"] if not provenance["ok"] else "A viewing preference is not artifact approval.")
    kinds = list(kinds)
    if rec.get("reply_contract"):
        ask = next((a for a in rec.get("asks", []) if a.get("ask_id") == ctx.get("presentation_ask_id")), {})
        if not set(kinds) <= set(ask.get("kinds") or []):
            raise ValueError("The client reply cannot approve an artifact outside its presented ask.")
    shas = {k: (rec.get("artifacts", {}).get(k) or {}).get("sha256") for k in kinds}
    revisions = {k: (rec.get("artifacts", {}).get(k) or {}).get("revision") for k in kinds}
    decision_key = ctx.get("source_ref") or ctx.get("reply_to_message_id") or _id(
        ctx.get("tenant_id"), ctx.get("run_id"), tuple(sorted(shas.items())),
        ctx.get("approved_by"), ctx.get("reply_text_sha"))
    for did, events in decisions(rec):
        if events and events[0].get("decision_key") == decision_key:
            ev0 = events[0]
            return {"duplicate": True, "decision_id": did, "events": events,
                    "ack": _find_outbox(rec, "ack:" + decision_key),
                    "continuation": _find_outbox(rec, "cont:" + decision_key),
                    "run_id": ev0.get("run_id")}
    decision_id = _id("decision", decision_key)
    ts = utcnow()
    events = []
    for kind in kinds:
        art = rec.get("artifacts", {}).get(kind) or {}
        ev = {"event_id": _id(decision_id, kind), "decision_id": decision_id,
              "decision_key": decision_key, "decision": "approved", "kind": kind,
              "revision": art.get("revision"),
              "sha256": art.get("sha256"),
              "tenant_id": ctx.get("tenant_id"), "run_id": ctx.get("run_id"),
              "requesting_conversation_id": (rec.get("conversation") or {}).get("conversation_id"),
              "conversation_id": ctx.get("conversation_id"),
              "thread_id": ctx.get("thread_id"),
              "approved_by": ctx.get("approved_by"), "timestamp": ts,
              "reply_to_message_id": ctx.get("reply_to_message_id"),
              "reply_text_sha": ctx.get("reply_text_sha"),
              "reply_text": ctx.get("reply_text"), "source": ctx.get("source"),
              "source_ref": ctx.get("source_ref"), "presentation_ask_id": ctx.get("presentation_ask_id"),
              "state": "active", "invalidated_by": None}
        rec["approvals"].append(ev)
        events.append(ev)
    ack = {"key": "ack:" + decision_key, "kind": "ack", "state": "pending",
           "decision_id": decision_id, "created_at": ts,
           "payload": {"kinds": kinds, "run_id": ctx.get("run_id"),
                       "conversation_id": ctx.get("conversation_id"),
                       "thread_id": ctx.get("thread_id")}}
    continuation = {"key": "cont:" + decision_key, "kind": "continuation", "state": "pending",
                    "decision_id": decision_id, "created_at": ts,
                    "payload": {"action": "continue", "run_id": ctx.get("run_id"),
                                "kinds": kinds, "decision_id": decision_id}}
    for entry in (ack, continuation):
        if _find_outbox(rec, entry["key"]) is None:
            rec["outbox"].append(entry)
    return {"duplicate": False, "decision_id": decision_id, "events": events,
            "ack": _find_outbox(rec, ack["key"]),
            "continuation": _find_outbox(rec, continuation["key"]),
            "run_id": ctx.get("run_id")}


def _find_outbox(rec, key):
    for o in rec.get("outbox") or []:
        if o.get("key") == key:
            return o
    return None


# --------------------------------------------------------------------------- #
# reply interpretation -- context first, one concrete question only when
# the pending approval cannot be resolved from the reply context
# --------------------------------------------------------------------------- #

def _named_kinds(text):
    out = []
    for kind, words in _KIND_WORDS.items():
        if any(re.search(r"\b%s\b" % re.escape(w), text) for w in words):
            out.append(kind)
    return out


def named_revision(text):
    """The revision number the reply itself names ("revision 2", "rev 2",
    "version 2", "v2"), or None. A reply that names one binds ONLY that
    revision: a presented revision the reply never named is never approved."""
    m = _REV_RE.search(_norm(text))
    return int(m.group(1)) if m else None


def is_preference_reply(text):
    """Approval-process preferences and viewing requests are not decisions."""
    t = _norm(text)
    if re.fullmatch(r"(?:option |choice )?\d+", t):
        return True
    return any(re.search(pattern, t) for pattern in (
        r"\b(?:show|send) (?:me|us)\b",
        r"\blet (?:me|us) (?:see|review|read)\b",
        r"\b(?:want|need|prefer|would like)\b.*\b(?:see|review|read|approv[a-z]*)\b.*\bfirst\b",
        r"\b(?:see|review|read)\b.*\b(?:first|before)\b",
        r"\b(?:approv[a-z]*)\b.*\b(?:after|once) (?:i|we) (?:see|review|read)\b",
        r"^script approval (?:is )?(?:1|yes)\b",
        r"\bnothing (?:is )?generated until\b",
    ))


def reply_context_status(rec, ctx=None):
    """Validate the existing presentation/reply protocol, without mutation.

    Modern records require a new client source reference and exact ask binding.
    Legacy records keep their existing context path; no identity is invented.
    """
    ctx, rec = ctx or {}, rec or {}
    contract = rec.get("reply_contract") or {}
    required = bool(contract)
    def result(ok, code, detail):
        return {"ok": ok, "required": required, "reason_code": code, "detail": detail}
    if ctx.get("source") is not None and str(ctx["source"]).strip().lower() != "client":
        return result(False, "ARTIFACT_REPLY_SOURCE_INVALID", "An assistant or saved preference cannot approve the client's artifact.")
    if not required:
        return result(True, "ARTIFACT_REPLY_LEGACY_CONTEXT", "Existing legacy artifact reply context is preserved.")
    if (ctx.get("source") != "client" or not isinstance(ctx.get("source_ref"), str) or
            not ctx["source_ref"].strip() or not ctx.get("presentation_ask_id") or not ctx.get("run_id")):
        return result(False, "ARTIFACT_REPLY_CONTEXT_REQUIRED", "Carry the actual new client reply source, source reference, run and presented ask identity.")
    if ctx["source_ref"] in contract.get("intake_source_refs", []):
        return result(False, "ARTIFACT_REPLY_INTAKE_REUSED", "This source reference belongs to intake, not a new reply to the presented script and lyrics.")
    if str(ctx["run_id"]) != str(contract.get("run_id")):
        return result(False, "ARTIFACT_REPLY_SCOPE_MISMATCH", "This artifact reply belongs to another run.")
    # A replay acknowledges its original decision, including a superseded
    # revision; it never approves the new revision or creates another event.
    prior = next((e for e in rec.get("approvals", []) if e.get("source_ref") == ctx["source_ref"]), None)
    if prior:
        if (prior.get("source") != "client" or prior.get("presentation_ask_id") != ctx["presentation_ask_id"] or
                str(prior.get("run_id")) != str(ctx["run_id"]) or
                prior.get("reply_text_sha") != ctx.get("reply_text_sha")):
            return result(False, "ARTIFACT_REPLY_SOURCE_REUSED", "The same reply source reference cannot identify different words, runs or presentations.")
        return result(True, "ARTIFACT_REPLY_REPLAY", "This is the previously recorded client artifact reply.")
    ask = next((a for a in rec.get("asks", []) if a.get("ask_id") == ctx["presentation_ask_id"]), None)
    if (not ask or ask.get("state") != "open" or not rec.get("sent") or
            any((rec.get("artifacts", {}).get(k) or {}).get("revision") != rev
                for k, rev in (ask.get("revisions") or {}).items()) or not ask.get("revisions")):
        return result(False, "ARTIFACT_REPLY_PRESENTATION_MISMATCH", "The reply must name the current presented whole-script/lyrics ask and its exact revisions.")
    if ask.get("message_id") and ctx["source_ref"] == ask["message_id"]:
        return result(False, "ARTIFACT_REPLY_SOURCE_REUSED", "The presentation itself is not a new client approval reply.")
    return result(True, "ARTIFACT_REPLY_PROVENANCE_CONFIRMED", "A new client reply is bound to the current presented artifacts.")


#: every name a reply may give to what it approves, one phrase per unit. These
#: carry no decision of their own: they are the OBJECT of an approval, never the
#: approval. Each is consumed once and read as one word, so "drama song ad"
#: never reads as the music and "song words" never reads as the soundtrack.
#: approval_bindings names exactly these phrases when it binds scope; its test
#: proves the two vocabularies are the same list.
REFERENT_PHRASES = (
    "the rest of it", "all of it", "causal story beats", "creative package manifest",
    "drama song ad", "episode cast manifest", "the entire thing", "the whole thing",
    "cast list", "cast manifest", "causal beats", "character images",
    "character list", "character manifest", "character photos", "character pictures",
    "creative manifest", "creative package", "episode world", "everything else",
    "it all", "lyric sheet", "package manifest", "research bundle", "research notes",
    "research pack", "scene list", "scene plan", "scene plans", "shot list",
    "song ad", "song lyrics", "song text", "song words", "story beats", "the ad",
    "world bible", "ad", "artifact", "artifacts", "audio", "beats", "cast",
    "characters", "deliverable", "deliverables", "everything", "images", "lyric",
    "lyrics", "manifest", "music", "package", "pictures", "research", "scene",
    "scenes", "screenplay", "script", "setting", "shots", "soundtrack", "story",
    "storyboard", "words", "world",
)


def _phrase_re(phrase):
    return re.compile(r"\b%s\b" % re.escape(phrase).replace(r"\ ", r"\s+"))


def _mask_idioms(t):
    """Drop affirmation idioms that contain a negation word ("no changes"), so
    the negation screen sees only real negation."""
    for pattern in _AFFIRM_IDIOMS:
        t = re.sub(pattern, " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _mask_units(t):
    """One word per unit: the artifacts a reply names fold to "it" and its
    affirmation idioms drop out, so the closed grammar reads only the words that
    decide. "The package manifest is approved" is then "the it is approved" --
    an approval, with the manifest still named for the scope that binds it."""
    t = _mask_idioms(t)
    for phrase in sorted(REFERENT_PHRASES, key=lambda p: (-len(p.split()), -len(p))):
        t = _phrase_re(phrase).sub(" it ", t)
    return re.sub(r"\s+", " ", t).strip()

def _reads_as_offer(t):
    """ROUTING ONLY -- this never approves anything. True when the reply at
    least names or offers an approval, so the screens below can say what kind of
    offer it is. Acceptance is decided by ``_resolves_approve`` alone; there is
    no first-word shortcut and no substring hit here either."""
    return bool(_APPROVAL_RE.search(t)) or any(w in _MENTION_TOKENS for w in _tokens(t))


def _resolves_approve(t):
    """True when the WHOLE reply is a bare approval (the
    character_approval._resolves_approve rule).

    The reply must be one known approval phrase, or be built ENTIRELY from the
    closed approval grammar with at least one word in it that approves. Any
    content word outside that grammar -- an instruction, a condition, a negation,
    a revision request, an opinion with substance -- means the reply is not a
    bare approval. "All of this is wrong", "go back and revise", "make the story
    longer" and "the villain's name is perfect as is, but make the story longer"
    are therefore never approvals.
    """
    if t in _AFFIRM_EXACT:
        return True
    masked = _mask_units(t)
    words = _tokens(masked)
    if not words:
        # only affirmation idioms and named artifacts were removed
        return any(re.search(pattern, t) for pattern in _AFFIRM_IDIOMS)
    if any(w not in _GRAMMAR_WORDS and not w.isdigit() for w in words):
        return False
    return any(w in _APPROVE_SIGNALS for w in words)


#: the words a viewing request may be made of -- nothing else
_VIEWING_WORDS = frozenset("""
a an again first it let lets me please read review see send show that the this
us before
""".split())


def _affirmative_answer(t):
    """A "yes" to a question the system just asked, with a viewing request added
    ("yes, show me first"). This is an ANSWER, never a bare artifact approval:
    it only fires for a reply ``is_preference_reply`` already refuses, and every
    approval path refuses a preference reply outright, so this can never open
    the artifact gate. It exists because the one recovery question in
    ``stage`` is answered with this same parser."""
    if not is_preference_reply(t):
        return False
    for phrase in sorted(_AFFIRM_EXACT, key=len, reverse=True):
        if t == phrase:
            return True
        if t.startswith(phrase + " "):
            tail = _tokens(_mask_idioms(t[len(phrase):]))
            return bool(tail) and all(w in _VIEWING_WORDS for w in tail)
    return False

def _scope_leftover(t):
    """The content word an approval is scoped to, when that word is NOT the
    whole package and NOT an artifact kind ("approve the foley")."""
    for m in _APPROVAL_RE.finditer(t):
        rest = _mask_idioms(_CLAUSE_RE.sub("", t[m.end():]))
        for w in rest.split():
            if w in _STOPWORDS or w in _KIND_TOKENS or w.isdigit():
                continue
            return w
    return None

def _negated(t):
    return any(re.search(r"\b%s\b" % re.escape(n), _mask_idioms(t)) for n in _NEGATE)


def _form_screens(text, t, whole_artifact=True):
    """The form screens every approval must pass, in EVERY register -- bare
    phrase or idiom alike: a question, a quote, a condition, a partial scope, a
    selection or an edit request riding along with the approval holds the gate.

    ``whole_artifact`` keeps the bare register's own last screen (an approval
    scoped to a content word that is no whole artifact). An idiom approval is
    checked against the words naming what it approves instead, so that screen
    would only duplicate -- and misread -- that check.
    """
    if _negated(t):
        return "refusal"
    raw = str(text or "")
    if raw.strip().endswith("?") or any(re.search(r"\b%s\b" % re.escape(q), t.split(None, 1)[0])
                                        for q in _QUESTION_START if t.split(None, 1)):
        return "REPLY_IS_A_QUESTION"
    if any(c in raw for c in _QUOTE_CHARS) or _REPORTED_RE.search(t):
        return "REPLY_IS_SOMEONE_ELSES_WORDS"
    if _CONDITIONAL_RE.search(_mask_idioms(t)):
        return "REPLY_IS_CONDITIONAL"
    if any(re.search(r"\b%s\b" % re.escape(m), t) for m in _SCOPE_MARKS):
        return "REPLY_IS_PARTIAL_SCOPE"
    if _SELECTION_RE.search(t):
        return "REPLY_IS_A_SELECTION"
    if any(re.search(r"\b%s\b" % re.escape(w), _mask_idioms(t)) for w in _CHANGE_WORDS):
        return "REPLY_APPROVES_AND_REVISES"
    if whole_artifact and _scope_leftover(t):
        return "REPLY_NAMES_NO_WHOLE_ARTIFACT"
    return None


def _decision_screen(text, t):
    """None when the reply can still be a plain decision; otherwise the reason
    it cannot.

    "refusal"  the words negate something -- never an approval
    "ambiguous" a question, a quote, a condition, a scope, a selection or an
                edit request riding along with the approval. Holding the gate
                beats guessing which artifact was meant.
    """
    if _negated(t):
        return "refusal"
    if t in _AFFIRM_EXACT:
        return None        # the whole reply IS one known approval phrase
    if not _reads_as_offer(t):
        return None                      # not an offer at all: the caller reads it as an edit
    return _form_screens(text, t)

def is_affirmative(text):
    """True only when the WHOLE reply is a bare approval: not negated, not
    conditional, not partial, not a question, not somebody else's words, and
    carrying nothing added to the approval itself.

    The whole reply is classified -- approval, rejection or revision request --
    by ``_resolves_approve``. There is no first-word shortcut and no substring
    hit: an affirmative word anywhere in a reply that also asks for a change is
    not an approval."""
    t = _norm(text)
    if not t:
        return False
    if _decision_screen(text, t):
        return False
    return _resolves_approve(t) or _affirmative_answer(t)


# --------------------------------------------------------------------------- #
# the idiom register -- a clear affirmative that is not a bare approval phrase
# ("Green light the drama song ad package.", "Full steam ahead on the
# package."). One idiom is ONE word of decision; its words are never read as
# content outside the bare-approval grammar. The register accepts the same
# replies the bare one does, judged by the same screens -- and nothing else.
# --------------------------------------------------------------------------- #

#: clear affirmative idioms, longest first at match time
_IDIOM_AFFIRM = (
    "green light", "greenlight", "give us the green light", "the green light",
    "you have our blessing", "we give our blessing", "our blessing",
    "move forward with", "moving forward with", "move ahead with",
    "moving ahead with", "go forward with", "press on with", "carry on with",
    "full steam ahead", "full speed ahead", "steam ahead",
    "we are good to go", "we're good to go", "good to go", "ready to go",
    "cleared to proceed", "cleared to go", "you are cleared", "you're cleared",
    "all systems go", "systems are go", "all clear",
    "fire away", "go for it", "have at it", "let it rip",
    "consider this our yes", "consider it our yes", "this is our yes",
    "behind this all the way", "behind it all the way", "behind you all the way",
    "full support", "our support", "thumbs up", "two thumbs up",
    "our sign off", "we sign off", "signed off", "sign off",
    "count us in", "we are in", "we're in",
    "this is a go", "it is a go", "we are a go", "we're a go", "a go on",
    "happy to proceed", "happy for you to proceed", "excited to proceed",
    "we approve", "we approved", "approved from our side", "approved on our end",
    "from our side", "from our end", "on our end",
    "we are happy with", "we are pleased with", "we are behind",
)

#: words that carry no decision and no substance of their own: determiners,
#: pronouns, copulas, auxiliaries, prepositions, conjunctions, light verbs and
#: discourse markers. An idiom approval is built from these plus the approval
#: words and the words naming what it approves -- anything else (an
#: instruction, an objection, an opinion with substance) makes the reply
#: something other than an approval.
_FUNCTION_WORDS = frozenset("""
a about above across after again against along also am an and another any
anyone anything are as at back be because been before being behind below
beside between both but by came come comes did do does doing done down during
each either else enough even ever every everybody everything except far few
for from further get gets give gives given go goes going got had has have
having he her here hers herself him himself his how i if in inside into is it
its itself just let lets me might mine more most much must my myself near
need needs neither never no nobody none nor nothing now of off often on once
one only onto or other others our ours ourselves out outside over own per please
rather really said same shall she should since so some somebody someone
something still such sure than thank thanks that the their theirs them
themselves then there therefore these they thing things this those though
through thus to together too toward towards under until up upon us very via
want wants was way ways we well were what when where whether which while who
whom whose why will with within without would yes yet you your yours yourself
""".split()) - _BLOCKED


#: every word an idiom phrase may be made of -- allowed wherever the idiom
#: register allows words of its own
_IDIOM_WORDS = frozenset(w for phrase in _IDIOM_AFFIRM for w in _tokens(_norm(phrase)))


def is_idiom_approval(text, scope_words=()):
    """True when the WHOLE reply is a clear affirmative idiom naming what it
    approves -- "Green light the drama song ad package and the script.",
    "Full steam ahead on the creative package.".

    Three things decide it, and all three are required: the reply carries an
    affirmative (a phrase from ``_IDIOM_AFFIRM``, or a known approval word or
    the word "approve"), every word in it is an approval word, a function word,
    one of ``scope_words`` (the words that name what is approved) or a
    displayed revision label, and it passes EVERY form screen -- negation,
    question, quote, condition, partial scope, selection and edit request.

    Nothing here approves anything on its own: a reply that names nothing
    approves nothing, whatever idiom it arrives in, and an instruction, an
    objection or an opinion with substance is never an approval.
    """
    t = _norm(text)
    if not t:
        return False
    if _form_screens(text, t, whole_artifact=False):
        return False
    rest, idiom = _mask_idioms(t), False
    for phrase in sorted(_IDIOM_AFFIRM, key=len, reverse=True):
        rest, n = re.subn(r"\b%s\b" % re.escape(phrase), " ", rest)
        idiom = idiom or bool(n)
    rest = re.sub(r"\s+", " ", rest).strip()
    if not (idiom or any(w in _APPROVE_SIGNALS for w in _tokens(rest))
            or _APPROVAL_RE.search(rest)):
        return False
    allowed = _GRAMMAR_WORDS | _FUNCTION_WORDS | _IDIOM_WORDS | frozenset(scope_words)
    return all(w in allowed or w.isdigit() for w in _tokens(rest))


def _needs_revision(rec, kind):
    art = (rec.get("artifacts") or {}).get(kind) or {}
    return not active_approval(rec, kind, art.get("sha256"))


def find_replay(rec, ctx):
    """An already-recorded decision this reply repeats, or None.

    The channel's message id decides: one message approves once, ever, so a
    replayed message or webhook re-acknowledges its decision even if the
    artifacts moved on since (it never approves the newer revision). Without a
    message id, identical words count as a replay only while the decision still
    stands at the current revision.
    """
    ctx = ctx or {}
    events = rec.get("approvals") or []
    key = ctx.get("source_ref") or ctx.get("reply_to_message_id")
    if key:
        for ev in reversed(events):
            field = "source_ref" if ctx.get("source_ref") else "reply_to_message_id"
            if ev.get(field) == key:
                return _decision_view(rec, ev.get("decision_id"))
    if rec.get("reply_contract") and ctx.get("source_ref"):
        return None  # distinct modern messages are not merged merely because both say yes
    tsha = ctx.get("reply_text_sha")
    if tsha:
        for did, evs in decisions(rec):
            ev0 = evs[0]
            if ev0.get("reply_text_sha") != tsha:
                continue
            if (ev0.get("approved_by") or None) != (ctx.get("approved_by") or None):
                continue
            arts = rec.get("artifacts") or {}
            if all(ev.get("state") == "active"
                   and ev.get("sha256") == (arts.get(ev.get("kind")) or {}).get("sha256")
                   for ev in evs):
                return _decision_view(rec, did)
    return None


def _decision_view(rec, decision_id):
    events = [ev for ev in rec.get("approvals") or []
              if ev.get("decision_id") == decision_id]
    return {"decision_id": decision_id,
            "kinds": [ev.get("kind") for ev in events],
            "timestamp": events[0].get("timestamp") if events else None,
            "events": events}


def close_decided_asks(rec, kinds):
    """A presentation whose kinds are all approved is answered; its ask closes
    so the next reply cannot be read against a stale question."""
    kinds = set(kinds)
    for a in rec.get("asks") or []:
        if a.get("state") == "open" and set(a.get("kinds") or []) <= kinds:
            a["state"] = "closed"
            a["closed_at"] = utcnow()


def interpret_reply(text, rec, ctx=None):
    """Client words -> {"intent", "kinds", "question", ...}.

    intent "approve"          : unambiguous; kinds are the approved kinds
    intent "already-approved" : repeats a decision that already stands
    intent "revise"           : not an approval -- the words are an edit request
    intent "ambiguous"        : several pending approvals, reply context resolves none
    intent "unseen"           : names an artifact/revision that was never presented
    intent "foreign"          : belongs to another run/tenant -- never an approval here

    The system never answers the client's creative approval on their behalf:
    anything short of an unambiguous approval is a question or an edit, never a
    decision event.
    """
    ctx = ctx or {}
    rec = rec if isinstance(rec, dict) else {}
    raw = str(text or "").strip()
    t = _norm(raw)
    if is_preference_reply(raw):
        return {"intent": "preference", "kinds": [], "question":
                "That selects the approval process or asks to see the work. Please reply to the current whole script and lyrics after reviewing them."}
    provenance = reply_context_status(rec, ctx)
    if not provenance["ok"]:
        return {"intent": "unproven", "kinds": [], "question": provenance["detail"],
                "reason_code": provenance["reason_code"]}

    for field, label in (("run_id", "run"), ("tenant_id", "tenant")):
        want = rec.get(field) or (rec.get("run") or {}).get(field)
        got = ctx.get(field)
        if want and got and str(want) != str(got):
            return {"intent": "foreign", "kinds": [], "question":
                    "That reply belongs to %s %s, not to this run. Did you mean to "
                    "approve here?" % (label, got)}
    origin = (rec.get("conversation") or {}).get("conversation_id")
    if origin and ctx.get("conversation_id") and str(origin) != str(ctx.get("conversation_id")):
        return {"intent": "foreign", "kinds": [], "question":
                "That reply came from another conversation. Please answer in the "
                "conversation where I sent the script."}

    asks = open_asks(rec)
    if rec.get("reply_contract") and ctx.get("presentation_ask_id"):
        asks = [a for a in asks if a.get("ask_id") == ctx["presentation_ask_id"]]
    asked = [k for a in asks for k in a.get("kinds") or []]
    named = [k for k in _named_kinds(t)
             if k in ("script", "lyrics", "character_images", "music", "storyboard")]
    affirmative = is_affirmative(raw)
    # "no changes" is an approval, not an edit request: edit words are read on
    # the text with affirmation idioms masked out
    masked = _mask_idioms(t)
    revise_hit = any(re.search(r"\b%s\b" % re.escape(w), masked) for w in _REVISE) \
        or any(re.search(r"\b%s\b" % re.escape(n), masked) for n in _NEGATE)

    # An approval must be UNAMBIGUOUS: not negated, not conditional, not
    # partial, not a question, not quoted from somebody else. Anything else
    # holds the gate -- the system never guesses which artifact was meant.
    screen = _decision_screen(raw, t)
    if screen == "refusal":
        return {"intent": "revise", "kinds": [], "text": raw,
                "reason_code": "REPLY_NEGATED"}
    if screen:
        return {"intent": "ambiguous", "kinds": [], "text": raw,
                "reason_code": screen, "question":
                "What exactly are you approving? I hold the gate until you reply "
                "with a plain yes to the whole script and lyrics exactly as sent."}

    # The whole reply is one of three things: an approval, a rejection, or a
    # revision request. Only a bare approval gets past this line -- an added
    # instruction, a condition, a negation or an opinion with substance makes the
    # reply a revision request, never a decision event. "All of this is wrong"
    # lands here and is read as a rejection/revision request, never as approval
    # of both script and lyrics.
    if revise_hit or not affirmative:
        return {"intent": "revise", "kinds": [], "text": raw,
                "reason_code": "REPLY_IS_NOT_A_BARE_APPROVAL"
                if not revise_hit else "REPLY_NEGATED"}

    # the all/both/everything flag only ever SCALES an approval that already
    # passed the whole-reply gate; it can never set one
    both = bool(re.search(r"\b(both|all|everything|script and lyrics)\b", t))

    # named kinds must have been presented; a generic yes cannot approve an
    # unseen artifact
    if named:
        unseen = [k for k in named if k not in asked]
        if unseen:
            return {"intent": "unseen", "kinds": unseen, "reason_code":
                    "REPLY_NAMES_UNSEEN_KIND", "question":
                    "I have not sent you %s to approve yet. Should I send it?"
                    % _list(unseen)}
        kinds = list(dict.fromkeys(named))
    elif both:
        kinds = [k for k in BOTH if k in asked]
    else:
        kinds = []

    # displayed revision labels disambiguate before any question is asked
    m = _REV_RE.search(t)
    if m:
        want = int(m.group(1))
        hits = [(a, k) for a in asks
                for k, v in (a.get("revisions") or {}).items()
                if v == want and (not kinds or k in kinds)]
        if not hits:
            shown = sorted({(k, v) for a in asks
                            for k, v in (a.get("revisions") or {}).items()})
            return {"intent": "unseen", "kinds": [], "reason_code":
                    "REPLY_NAMES_UNSEEN_REVISION", "question":
                    "I do not have a revision %d here to approve. The revisions I sent "
                    "are %s. Which one do you mean?"
                    % (want, "; ".join("%s rev %s" % (k, v) for k, v in shown) or "none")}
        kinds = list(dict.fromkeys(kinds + [k for _, k in hits]))
    elif not kinds and ctx.get("reply_to_message_id"):
        # replied-to message ids disambiguate before any question is asked
        by_msg = [a for a in asks if a.get("message_id") == ctx["reply_to_message_id"]]
        if by_msg:
            kinds = list(by_msg[0].get("kinds") or [])
        elif len(asks) != 1:
            return {"intent": "unseen", "kinds": [], "reason_code":
                    "REPLY_ANSWERED_AN_OLDER_ASK", "question":
                    "That reply answered an older message. Do you want to approve what "
                    "I sent most recently?"}

    if not kinds:
        if len(asks) == 1:
            kinds = list(asks[0].get("kinds") or [])
        elif not asks:
            waiting = [k for k in (rec.get("artifacts") or {}) if _needs_revision(rec, k)]
            return {"intent": "already-approved" if not waiting else "unseen",
                    "kinds": [], "question":
                    "" if not waiting else
                    "There is nothing waiting for your approval right now. "
                    "Is there something you want changed?"}
        else:
            return {"intent": "ambiguous", "kinds": [], "question":
                    "Which one is that approval for: %s?"
                    % " or ".join(" / ".join(a.get("kinds") or []) for a in asks)}

    kinds = [k for k in dict.fromkeys(kinds)]
    if all(not _needs_revision(rec, k) for k in kinds):
        return {"intent": "already-approved", "kinds": kinds, "text": raw}
    kinds = [k for k in kinds if _needs_revision(rec, k)]
    return {"intent": "approve", "kinds": kinds, "text": raw}


def _list(kinds):
    return ", ".join(str(k).replace("_", " ") for k in kinds)


# --------------------------------------------------------------------------- #
# legacy projection -- what the existing music gates read
# --------------------------------------------------------------------------- #

def project(rec, lyrics_sha=None):
    """Mirror the revision-aware model onto the legacy gate fields, so
    kie_dispatch / song_dispatch gates keep working unchanged: 'approved' still
    means the combined approval of script AND lyrics, still bound to THESE
    lyrics."""
    if not isinstance(rec, dict) or is_unknown_record(rec):
        return rec
    art = rec.get("artifacts") or {}
    script_ok = bool(art.get("script")) and active_approval(rec, "script", art["script"].get("sha256"))
    lyrics_ok = bool(art.get("lyrics")) and active_approval(rec, "lyrics", art["lyrics"].get("sha256"))
    rec["required"] = True
    rec["status"] = "approved" if (script_ok and lyrics_ok) else "pending"
    if lyrics_sha is not None:
        rec["lyrics_sha"] = lyrics_sha
    elif art.get("lyrics"):
        rec["lyrics_sha"] = art["lyrics"].get("sha256")
    for ev in reversed(rec.get("approvals") or []):
        if ev.get("approved_by"):
            rec["approved_by"] = ev["approved_by"]
            break
    return rec
