#!/usr/bin/env python3
"""post_delivery_discovery.py - useful help and a relevant recommendation after
the gift (T-27).

Contract basis: Purple-Billboard SPEC.md "Fulfillment, access and useful help"
(R-17, C-27) - "Phone-only, email-only and declining people still get the
original resource and help. Skill 38 continues needs discovery, knowledge-based
answers and a relevant resource/community/offer/calendar recommendation. No
universal three-question gate and no capture-as-completion." Also R-20
("truthful funnel attribution") and DATA-CONTRACTS section 5 ("New helpful
inbound questions can still be answered through their own gate") and section 7
(delivery consent is separate from marketing; no-email erases nothing).
Python 3 standard library only.

What this module exists to guarantee:

  REAL        A recommendation names a catalogued item whose kind is resource,
              community, offer or calendar and whose destination is a usable
              pointer - an existing path, or an http/https URL whose host is
              dotted and not a reserved special-use name. Placeholders, bare
              schemes, fragments, reserved hosts, blank values and unavailable
              items are refused. Nothing is recommended that is not real.

  ADAPTIVE    Needs discovery is driven by what is still UNKNOWN and material
              to the catalogue, never by a fixed questionnaire. A known field
              removes its question, a refused field is suppressed, and the
              pending set changes with the facts. There is no required
              three-question sequence and no gate that must be finished before
              help is given: one known need is enough to recommend.

  ANSWERED    A knowledge answer is returned only when a stored entry supplies
              it, and it carries that entry's source. With no matching source
              the result is `unknown` - the module never invents an answer.

  UNGATED     Help is independent of capture. Phone-only, email-only and
              marketing-declined people get the same discovery, answers and
              recommendations. Capture state never completes discovery and
              discovery never completes capture. This module deliberately
              exposes no capture endpoint.

  TRUTHFUL    Every recommendation records the basis it matched and its own
              delivery record. `delivered` requires an actual receipt; provider
              acceptance alone stays `accepted`/`sent`. Outcomes come only from
              supplied authoritative evidence. Keyword and multi-touch
              attribution are preserved with `exact_post_causality` false
              instead of an invented post-level cause.

ponytail: the store is in-process and holds no database. Add durability (or
hand the records to durable_store) when a caller needs them across restarts.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from post_delivery_discovery import (Catalog, Discovery, DiscoveryError,
                                         KnowledgeBase)

Assert-based self-check:  python3 -I post_delivery_discovery.py
"""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlsplit

KIND_RESOURCE = "resource"
KIND_COMMUNITY = "community"
KIND_OFFER = "offer"
KIND_CALENDAR = "calendar"
KINDS = (KIND_RESOURCE, KIND_COMMUNITY, KIND_OFFER, KIND_CALENDAR)

# The four kinds the contract names. `resource` and `community` are the ones a
# phone-only person can use with no email and no account.
DELIVERY_ACCEPTED = "accepted"
DELIVERY_SENT = "sent"
DELIVERY_DELIVERED = "delivered"
DELIVERY_STATES = (DELIVERY_ACCEPTED, DELIVERY_SENT, DELIVERY_DELIVERED)

OUTCOME_BOOKED = "booked"
OUTCOME_ATTENDED = "attended"
OUTCOME_PURCHASED = "purchased"
OUTCOME_NO_SHOW = "no_show"
OUTCOME_UNKNOWN = "unknown"
OUTCOMES = (OUTCOME_BOOKED, OUTCOME_ATTENDED, OUTCOME_PURCHASED,
            OUTCOME_NO_SHOW, OUTCOME_UNKNOWN)

# A field is material only through the kinds it can point at. The catalogue,
# not this table, decides whether a question is worth asking at all.
NEED_FIELDS = {
    "goal": frozenset((KIND_RESOURCE, KIND_OFFER)),
    "experience_level": frozenset((KIND_RESOURCE, KIND_COMMUNITY)),
    "preferred_format": frozenset((KIND_RESOURCE, KIND_COMMUNITY)),
    "interests": frozenset((KIND_COMMUNITY, KIND_OFFER)),
    "budget": frozenset((KIND_OFFER,)),
    "timezone": frozenset((KIND_CALENDAR,)),
    "availability": frozenset((KIND_CALENDAR,)),
}

_RESERVED_HOSTS = (
    "test", "example", "invalid", "localhost", "local",
    "example.com", "example.net", "example.org",
)
_PLACEHOLDERS = frozenset((
    "", "#", "todo", "tbd", "n/a", "na", "none", "null", "placeholder",
))


class DiscoveryError(ValueError):
    """A refused catalogue entry, delivery record or outcome record."""


def _check_destination(pointer):
    """Return a usable destination pointer or raise DiscoveryError.

    Accepts a path that exists on disk, or an http/https URL with a dotted,
    non-reserved host. Everything else is refused, because recommending a
    pointer that cannot be reached is the same as recommending nothing.
    """
    if not isinstance(pointer, str):
        raise DiscoveryError(
            "destination must be a string, got %r" % (pointer,))
    text = pointer.strip()
    if text.lower() in _PLACEHOLDERS:
        raise DiscoveryError(
            "destination %r is a placeholder, not a real location" % (pointer,))
    try:
        parts = urlsplit(text)
    except ValueError as exc:  # malformed bracketed host or bad port
        raise DiscoveryError("destination %r is not a usable URL: %s"
                             % (pointer, exc))
    scheme = (parts.scheme or "").lower()
    if scheme in ("http", "https"):
        host = (parts.hostname or "").strip().lower()
        if not host:
            raise DiscoveryError(
                "destination %r has no host" % (pointer,))
        if "." not in host:
            raise DiscoveryError(
                "destination %r has no dotted host, so it cannot name a real "
                "location" % (pointer,))
        if any(host == r or host.endswith("." + r) for r in _RESERVED_HOSTS):
            raise DiscoveryError(
                "destination %r names reserved special-use host %r, which can "
                "never be a real location" % (pointer, host))
        return text
    if scheme:
        raise DiscoveryError(
            "destination %r uses scheme %r; only http, https or a local path "
            "are usable" % (pointer, scheme))
    if text.startswith("/") or text.startswith("./") or text.startswith("../"):
        if not os.path.exists(text):
            raise DiscoveryError(
                "destination path %r does not exist, so it is not a real "
                "resource" % (pointer,))
        return text
    raise DiscoveryError(
        "destination %r is neither a URL nor an existing path" % (pointer,))


class CatalogItem:
    """One real thing a person can be pointed at."""

    __slots__ = ("item_id", "kind", "title", "destination", "need_tags",
                 "available")

    def __init__(self, item_id, kind, title, destination, need_tags,
                 available=True):
        if not isinstance(item_id, str) or not item_id.strip():
            raise DiscoveryError("item_id must be a non-empty string")
        if kind not in KINDS:
            raise DiscoveryError(
                "kind %r is not one of %s" % (kind, ", ".join(KINDS)))
        if not isinstance(title, str) or not title.strip():
            raise DiscoveryError("title must be a non-empty string")
        if not isinstance(need_tags, (list, tuple, set, frozenset)):
            raise DiscoveryError("need_tags must be a collection of strings")
        self.item_id = item_id.strip()
        self.kind = kind
        self.title = title.strip()
        self.destination = _check_destination(destination)
        self.need_tags = frozenset(
            str(t).strip() for t in need_tags if str(t).strip())
        self.available = bool(available)

    def as_dict(self):
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "title": self.title,
            "destination": self.destination,
            "need_tags": sorted(self.need_tags),
            "available": self.available,
        }


class Catalog:
    """The real inventory. Duplicate ids are refused, not overwritten."""

    def __init__(self):
        self._items = {}

    def add(self, item_id, kind, title, destination, need_tags,
            available=True):
        item = CatalogItem(item_id, kind, title, destination, need_tags,
                           available=available)
        if item.item_id in self._items:
            raise DiscoveryError("duplicate catalogue item %r" % (item.item_id,))
        self._items[item.item_id] = item
        return item

    def get(self, item_id):
        return self._items.get(item_id)

    def available(self):
        return [i for i in self._items.values() if i.available]

    def __len__(self):
        return len(self._items)


class KnowledgeBase:
    """Answers that carry the source they came from, and nothing else."""

    def __init__(self):
        self._entries = []

    def add(self, topic, answer, source, need_tags=()):
        if not isinstance(topic, str) or not topic.strip():
            raise DiscoveryError("topic must be a non-empty string")
        if not isinstance(answer, str) or not answer.strip():
            raise DiscoveryError("answer must be a non-empty string")
        try:
            checked_source = _check_destination(source)
        except DiscoveryError:
            # A knowledge source may also be a named document rather than a
            # pointer, but it must still be a name, never blank.
            if not isinstance(source, str) or not source.strip():
                raise
            checked_source = source.strip()
        self._entries.append({
            "topic": topic.strip().lower(),
            "answer": answer.strip(),
            "source": checked_source,
            "need_tags": frozenset(str(t).strip() for t in need_tags),
        })

    def answer(self, topic):
        """Return the first stored answer for a topic, with its source."""
        wanted = (topic or "").strip().lower()
        for entry in self._entries:
            if entry["topic"] == wanted:
                return {
                    "status": "answered",
                    "topic": entry["topic"],
                    "answer": entry["answer"],
                    "source": entry["source"],
                }
        return {
            "status": "unknown",
            "topic": wanted,
            "answer": None,
            "source": None,
            "reason": "no stored entry answers this; nothing is invented",
        }

    def __len__(self):
        return len(self._entries)


class Discovery:
    """Adaptive needs discovery plus grounded answers and real recommendations.

    Nothing on this class reads capture state. That is the point: the same
    person gets the same help whether they gave an email, a phone, both or
    neither.
    """

    def __init__(self, catalog, knowledge=None, capture_state=None):
        self.catalog = catalog
        self.knowledge = knowledge or KnowledgeBase()
        # Held for reporting only. No method below consults it.
        self.capture_state = dict(capture_state or {})
        self._needs = {}
        self._refused = set()
        self._asked = []
        self._deliveries = []
        self._outcomes = []
        self._touches = []
        self._keyword = None

    # -- needs ------------------------------------------------------------
    def learn(self, field, value):
        if field not in NEED_FIELDS:
            raise DiscoveryError(
                "field %r is not a need field; known: %s"
                % (field, ", ".join(sorted(NEED_FIELDS))))
        text = str(value).strip() if value is not None else ""
        if not text:
            raise DiscoveryError("learned value for %r is blank" % (field,))
        self._needs[field] = text
        return self._needs[field]

    def known(self):
        return dict(self._needs)

    def refuse(self, field):
        """A refused field is suppressed; it never blocks the conversation."""
        if field not in NEED_FIELDS:
            raise DiscoveryError(
                "field %r is not a need field; known: %s"
                % (field, ", ".join(sorted(NEED_FIELDS))))
        self._refused.add(field)
        self._asked.append({"field": field, "answer": "refused"})
        return True

    def _open_fields(self):
        """Fields still worth asking: unknown, not refused, and material.

        Material means at least one AVAILABLE catalogue item can be matched by
        that field. A field with nothing behind it is never asked, so the
        question set is a property of the catalogue, not a fixed questionnaire.
        """
        available_tags = set()
        for item in self.catalog.available():
            available_tags |= item.need_tags
        return [
            field for field in NEED_FIELDS
            if field not in self._needs
            and field not in self._refused
            and field in available_tags
        ]

    def questions(self):
        """Every question currently worth asking, most useful first.

        The length changes with the facts; there is no fixed set of three.
        """
        available = self.catalog.available()

        def unlock_count(field):
            return sum(1 for i in available if field in i.need_tags)

        return [
            {
                "field": field,
                "kind_scope": sorted(NEED_FIELDS[field]),
                "unlocks": unlock_count(field),
            }
            for field in sorted(self._open_fields(),
                                key=lambda f: (-unlock_count(f), f))
        ]

    def next_question(self):
        pending = self.questions()
        if not pending:
            return None
        question = dict(pending[0])
        question["remaining"] = len(pending)
        self._asked.append({"field": question["field"], "answer": "asked"})
        return question

    # -- answers ----------------------------------------------------------
    def answer(self, topic):
        return self.knowledge.answer(topic)

    # -- recommendations --------------------------------------------------
    def need_tags(self):
        """The need tokens a KNOWN field supplies, used to score the catalogue."""
        return set(self._needs)

    def recommend(self, limit=3):
        """Pick real, available items that match a KNOWN need.

        No need known means no basis for relevance, so the truthful answer is
        `no_match` rather than a guess. One known field is enough - that is
        what makes this not a gate.
        """
        if not isinstance(limit, int) or limit < 1:
            raise DiscoveryError("limit must be a positive integer")
        tags = self.need_tags()
        if not tags:
            return {"status": "no_match",
                    "reason": "no known need gives a basis for relevance",
                    "recommendations": []}
        scored = []
        for item in self.catalog.available():
            overlap = item.need_tags & tags
            if not overlap:
                continue
            scored.append((-len(overlap), item.item_id, item, sorted(overlap)))
        scored.sort(key=lambda row: (row[0], row[1]))
        chosen = []
        for _score, _item_id, item, overlap in scored[:limit]:
            chosen.append({
                "item_id": item.item_id,
                "kind": item.kind,
                "title": item.title,
                "destination": item.destination,
                "basis": {
                    "matched_tags": overlap,
                    "known_needs": sorted(self._needs),
                },
            })
        if not chosen:
            return {"status": "no_match",
                    "reason": "no available catalogue item matches the known need",
                    "recommendations": []}
        return {"status": "ok", "recommendations": chosen}

    # -- delivery and outcomes -------------------------------------------
    def record_delivery(self, item_id, status, receipt=None, at=None):
        item = self.catalog.get(item_id)
        if item is None:
            raise DiscoveryError("no catalogue item %r" % (item_id,))
        if status not in DELIVERY_STATES:
            raise DiscoveryError(
                "status %r is not one of %s"
                % (status, ", ".join(DELIVERY_STATES)))
        if status == DELIVERY_DELIVERED and not str(receipt or "").strip():
            raise DiscoveryError(
                "delivered needs an actual receipt; provider acceptance alone "
                "is accepted or sent")
        record = {
            "item_id": item.item_id,
            "status": status,
            "receipt": receipt if receipt is not None else None,
            "at": time.time() if at is None else float(at),
        }
        self._deliveries.append(record)
        return dict(record)

    def record_outcome(self, item_id, outcome, evidence=""):
        if self.catalog.get(item_id) is None:
            raise DiscoveryError("no catalogue item %r" % (item_id,))
        if outcome not in OUTCOMES:
            raise DiscoveryError(
                "outcome %r is not one of %s"
                % (outcome, ", ".join(OUTCOMES)))
        if outcome != OUTCOME_UNKNOWN and not (evidence or "").strip():
            raise DiscoveryError(
                "outcome %r needs authoritative owner or receipt evidence"
                % (outcome,))
        record = {"item_id": item_id, "outcome": outcome,
                  "evidence": (evidence or "").strip() or None}
        self._outcomes.append(record)
        return dict(record)

    def note_touch(self, source, keyword=None):
        if not isinstance(source, str) or not source.strip():
            raise DiscoveryError("touch source must be a non-empty string")
        self._touches.append(source.strip())
        if keyword is not None:
            self._keyword = str(keyword).strip() or None
        return True

    def attribution(self):
        """Truthful attribution: preserve what is known and mark the rest."""
        return {
            "keyword": self._keyword,
            "touches": list(self._touches),
            "exact_post_causality": False,
            "unknown_preserved": True,
            "note": "multi-touch; a single post is never claimed as the cause",
        }

    def help_given(self):
        return bool(self._deliveries or self._outcomes)

    def snapshot(self):
        return {
            "known": dict(self._needs),
            "refused": sorted(self._refused),
            "questions": self.questions(),
            "deliveries": [dict(d) for d in self._deliveries],
            "outcomes": [dict(o) for o in self._outcomes],
            "attribution": self.attribution(),
            "capture_state": dict(self.capture_state),
        }


def _selfcheck():
    import tempfile

    passed = 0

    def ok(condition, label):
        nonlocal passed
        assert condition, "SELF-CHECK FAILED: %s" % (label,)
        passed += 1

    def refused(fn, label):
        nonlocal passed
        try:
            fn()
        except DiscoveryError:
            passed += 1
            return
        raise AssertionError("SELF-CHECK FAILED: %s was not refused" % (label,))

    with tempfile.NamedTemporaryFile("w", suffix=".pdf", delete=False) as fh:
        fh.write("resource")
        local_path = fh.name
    try:
        catalog = Catalog()
        catalog.add("res-1", KIND_RESOURCE, "Starter guide",
                    "https://example-client.com/guide.pdf", ["goal"])
        catalog.add("com-1", KIND_COMMUNITY, "Owner circle",
                    "https://community.example-client.com/", ["interests"])
        catalog.add("off-1", KIND_OFFER, "Deep-dive call",
                    "https://example-client.com/call", ["budget", "goal"])
        catalog.add("cal-1", KIND_CALENDAR, "Book a slot",
                    "https://cal.example-client.com/book", ["timezone"])
        catalog.add("off-2", KIND_OFFER, "Retired bonus",
                    "https://example-client.com/old", ["budget"],
                    available=False)
        catalog.add("res-2", KIND_RESOURCE, "Local worksheet",
                    local_path, ["preferred_format"])

        refused(lambda: Catalog().add("x", KIND_RESOURCE, "Bad",
                                     "totally://made.up", ["goal"]),
                "pseudo-scheme destination")
        refused(lambda: Catalog().add("x", KIND_RESOURCE, "Bad",
                                      "https://invented.invalid/nope", ["goal"]),
                "reserved host destination")
        refused(lambda: Catalog().add("x", KIND_RESOURCE, "Bad", "#", ["goal"]),
                "fragment destination")
        refused(lambda: Catalog().add("x", KIND_RESOURCE, "Bad",
                                      "https://nodot/x", ["goal"]),
                "host with no dot")
        refused(lambda: Catalog().add("x", "bonus", "Bad",
                                      "https://real.example-client.com",
                                      ["goal"]),
                "kind outside the four contract kinds")
        refused(lambda: catalog.add("res-1", KIND_RESOURCE, "Dup",
                                    "https://example-client.com/x", ["goal"]),
                "duplicate item id")
        ok(catalog.get("res-2").destination == local_path,
           "an existing local path is a usable destination")

        kb = KnowledgeBase()
        kb.add("what is included", "The guide plus the worksheet.",
               "https://example-client.com/faq")
        refused(lambda: kb.add("blank", "", "https://example-client.com/faq"),
                "blank knowledge answer")

        disc = Discovery(catalog, kb,
                         capture_state={"email": None, "sms": "phone-only"})
        ok(len(disc.questions()) > 0, "questions exist while needs are unknown")
        first = disc.next_question()
        ok(first is not None and first["field"] in NEED_FIELDS,
           "next_question returns a material field")
        ok(len(disc.questions()) != 3 or first["remaining"] != 3,
           "the pending set is not a fixed three-question questionnaire")
        before = {q["field"] for q in disc.questions()}
        disc.learn(first["field"], "get started")
        after = {q["field"] for q in disc.questions()}
        ok(first["field"] not in after and before - after == {first["field"]},
           "a known field removes its own question")
        ok(disc.recommend(2)["status"] == "ok",
           "one known need is enough to recommend - there is no gate")
        disc.refuse("budget")
        ok("budget" not in {q["field"] for q in disc.questions()},
           "a refused field is suppressed")
        ok(disc.recommend(3)["status"] == "ok",
           "a refusal does not block help")

        answer = disc.answer("what is included")
        ok(answer["status"] == "answered"
           and answer["source"] == "https://example-client.com/faq",
           "a stored answer carries its source")
        unknown = disc.answer("what colour is the moon")
        ok(unknown["status"] == "unknown" and unknown["answer"] is None,
           "an unanswerable question is unknown, never invented")

        rec = disc.recommend(10)
        ids = [r["item_id"] for r in rec["recommendations"]]
        ok("off-2" not in ids, "an unavailable item is never recommended")
        ok(ids == [r["item_id"] for r in disc.recommend(10)["recommendations"]],
           "recommendation order is deterministic")
        ok(all(r["basis"]["known_needs"] for r in rec["recommendations"]),
           "every recommendation states the need it was based on")

        phone_only = Discovery(catalog, kb, capture_state={"email": None})
        email_only = Discovery(catalog, kb, capture_state={"email": "a@b.co"})
        declined = Discovery(catalog, kb,
                             capture_state={"email": "a@b.co",
                                            "marketing": "declined"})
        for d in (phone_only, email_only, declined):
            d.learn("goal", "get started")
        ok(phone_only.recommend(3) == email_only.recommend(3) ==
           declined.recommend(3),
           "capture shape never changes the recommendation")
        ok(phone_only.answer("what is included") ==
           declined.answer("what is included"),
           "capture shape never changes a knowledge answer")
        ok(not hasattr(Discovery, "capture"),
           "the module exposes no generic capture endpoint")

        empty = Discovery(catalog, kb)
        ok(empty.recommend(3)["status"] == "no_match",
           "no known need means no invented relevance")

        accepted = disc.record_delivery("res-1", DELIVERY_ACCEPTED)
        ok(accepted["status"] == "accepted" and accepted["receipt"] is None,
           "provider acceptance is labelled accepted, not delivered")
        refused(lambda: disc.record_delivery("res-1", DELIVERY_DELIVERED),
                "delivered without a receipt")
        ok(disc.record_delivery("res-1", DELIVERY_DELIVERED,
                                receipt="msg-42")["status"] == "delivered",
           "delivered is allowed with a real receipt")
        refused(lambda: disc.record_delivery("ghost-1", DELIVERY_SENT),
                "delivery of an uncatalogued item")
        refused(lambda: disc.record_outcome("res-1", OUTCOME_BOOKED),
                "outcome without evidence")
        ok(disc.record_outcome("res-1", OUTCOME_UNKNOWN)["outcome"] == "unknown",
           "unknown outcome needs no evidence and is not a claim")
        ok(disc.record_outcome("res-1", OUTCOME_ATTENDED,
                               evidence="cal receipt 2026-10-25")["outcome"] ==
           OUTCOME_ATTENDED, "an evidenced outcome is recorded")
        disc.note_touch("comment", keyword="purple-billboard")
        attr = disc.attribution()
        ok(attr["exact_post_causality"] is False and attr["keyword"] ==
           "purple-billboard", "attribution keeps keyword and refuses causality")
        ok(disc.help_given() is True, "help is recorded independently of capture")

        print("OK %d PASS" % (passed,))
        return 0
    finally:
        os.unlink(local_path)


if __name__ == "__main__":
    sys.exit(_selfcheck())
