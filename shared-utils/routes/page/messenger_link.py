#!/usr/bin/env python3
"""Messenger DM-door link builder (review C5 / unit T-56).

One stdlib-only home for the Bonus-comment door: the Page binding recorded once
per tenant, the ``pb-<MON><DD>-<YYYY>-<CATEGORY>`` ref, the ``m.me`` link, its
inverse parser, the canonical Bonus sentence, and the only producer of the
resolver's keyword and ref tables.

Rules enforced here (review C5 Exactly-how steps 1, 2, 6 and H8 steps 4 and 5):
  * a Page id is 5 to 20 digits, never a username or a URL;
  * a ref is dated in the placement's own local date and categorised;
  * a link is ``https://m.me/<page_id>?ref=<quoted ref>`` and nothing else;
  * a link longer than Meta's 2,083-character cap is refused;
  * the keyword table reads APPROVED placements only.

Write-time entry points, so no caller has to re-derive the door:

  ``record_page_binding(readiness_record, binding)``
      C5 step 2 rule: the one Page id per tenant and account, accepted only while
      the readiness record still names this ``account_binding_revision``. A rebind
      invalidates it with the rest of the readiness proof; a different Page id is
      refused, never overwritten.
  ``build_bonus_placement(placement, binding, ...)``
      C5 step 6 / H8 step 4: the pack writer's single call. It runs ``build_ref``,
      ``build_messenger_link`` and ``bonus_cta`` at write time and returns the
      placement carrying the three bound fields, the ``GIFTGUIDE``-style keyword
      (category plus a distinct item word) and the canonical CTA. A hand-typed
      link, ref or Page id that disagrees is refused, never replaced silently.
  ``REF_ATTRIBUTION``
      C5 step 8: the honest capability value, mirrored by
      ``facebook_routes.capability_status()`` and kept until a real Messenger
      referral event is captured. Nothing may promote it here.

Run
  python3 messenger_link.py        # assert self-check, exit 0 on success
"""
from __future__ import annotations

import datetime
import re
import string
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
CATEGORIES = ("GIFT", "COMMUNITY", "APPOINTMENTS")
CATEGORY_RE = re.compile(r"^[A-Z0-9]{1,32}$")
PAGE_ID_RE = re.compile(r"^[0-9]{5,20}$")
REF_RE = re.compile(r"^pb-(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
                    r"(0[1-9]|[12][0-9]|3[01])-(20[0-9]{2})-([A-Z0-9]{1,32})$")
HOST = "m.me"
MAX_LINK = 2083
# C5 step 8: refs are generated here, but GHL's normalized body carries no ref key
# (DISCOVERIES D-05), so attribution stays unproven until a raw Messenger referral
# event is captured. facebook_routes.capability_status() must keep this same value.
REF_ATTRIBUTION = "NOT_PROVEN"
BONUS_FIELDS = ("messenger_page_id", "messenger_ref", "messenger_link")


class MessengerLinkError(ValueError):
    """A link, ref or binding that cannot be built or read back."""


@dataclass(frozen=True)
class PageBinding:
    """The Page recorded once per tenant and account on the readiness record."""

    tenant_id: str
    account_id: str
    page_id: str
    binding_revision: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "account_id", "binding_revision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise MessengerLinkError("%s must be a non-empty string" % name)
        page = self.page_id
        if not isinstance(page, str) or not PAGE_ID_RE.match(page):
            raise MessengerLinkError(
                "page_id must be 5 to 20 digits, got %r (never a username or URL)" % (page,)
            )

    def as_record(self) -> Dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "messenger_page_id": self.page_id,
            "account_binding_revision": self.binding_revision,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "PageBinding":
        try:
            return cls(
                tenant_id=str(record["tenant_id"]),
                account_id=str(record["account_id"]),
                page_id=str(record["messenger_page_id"]),
                binding_revision=str(record["account_binding_revision"]),
            )
        except KeyError as exc:
            raise MessengerLinkError("readiness record is missing %s" % exc) from None


def _check_category(category: str) -> str:
    if not isinstance(category, str):
        raise MessengerLinkError("category must be a string")
    value = category.strip().upper()
    if not CATEGORY_RE.match(value):
        raise MessengerLinkError(
            "category %r is not %s or ^[A-Z0-9]{1,32}$" % (category, "/".join(CATEGORIES))
        )
    return value


def build_ref(local_date: datetime.date, category: str) -> str:
    """``pb-<MON><DD>-<YYYY>-<CATEGORY>`` for the placement's own local date."""
    if not isinstance(local_date, datetime.date):
        raise MessengerLinkError("local_date must be a datetime.date")
    return "pb-%s%02d-%04d-%s" % (
        MONTHS[local_date.month - 1], local_date.day, local_date.year, _check_category(category)
    )


def parse_ref(ref: str) -> Tuple[datetime.date, str]:
    if not isinstance(ref, str):
        raise MessengerLinkError("ref must be a string")
    match = REF_RE.match(ref)
    if not match:
        raise MessengerLinkError("ref %r is not pb-<MON><DD>-<YYYY>-<CATEGORY>" % (ref,))
    month = MONTHS.index(match.group(1)) + 1
    try:
        when = datetime.date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        raise MessengerLinkError("ref %r names a date that does not exist" % (ref,)) from None
    return when, match.group(4)


def build_messenger_link(binding: PageBinding, ref: str) -> str:
    """The one legal shape: https://m.me/<page_id>?ref=<url-quoted ref>."""
    parse_ref(ref)  # a link is never built against an unreadable ref
    link = "https://%s/%s?ref=%s" % (HOST, binding.page_id, urllib.parse.quote(ref, safe="-"))
    if len(link) > MAX_LINK:
        raise MessengerLinkError("link is %d characters; Meta's cap is %d" % (len(link), MAX_LINK))
    return link


@dataclass(frozen=True)
class ParsedLink:
    page_id: str
    ref: str
    local_date: datetime.date
    category: str


def parse_messenger_link(url: str) -> ParsedLink:
    """The inverse. Any other scheme, host, path, extra key or non-numeric page refuses."""
    if not isinstance(url, str):
        raise MessengerLinkError("url must be a string")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise MessengerLinkError("scheme must be https, got %r" % (parts.scheme,))
    if parts.netloc != HOST:
        raise MessengerLinkError("host must be exactly %s, got %r" % (HOST, parts.netloc))
    if parts.fragment:
        raise MessengerLinkError("a DM link carries no fragment")
    page_id = parts.path[1:] if parts.path.startswith("/") else ""
    if "/" in page_id or not PAGE_ID_RE.match(page_id):
        raise MessengerLinkError("path must be one numeric Page id, got %r" % (parts.path,))
    query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    if set(query) != {"ref"}:
        raise MessengerLinkError(
            "query must be exactly ref, got %s" % (sorted(query) or "nothing")
        )
    ref = query["ref"][0]
    when, category = parse_ref(ref)
    return ParsedLink(page_id=page_id, ref=ref, local_date=when, category=category)


def bonus_cta(link: str, keyword: str) -> str:
    """The one canonical Bonus sentence, naming the keyword exactly as the door matches it."""
    parsed = parse_messenger_link(link)
    if not isinstance(keyword, str) or not keyword.strip():
        raise MessengerLinkError("keyword must be a non-empty string")
    word = keyword.strip()
    if not CATEGORY_RE.match(word.upper()):
        raise MessengerLinkError("keyword %r is not ^[A-Z0-9]{1,32}$" % (keyword,))
    return ('Comment "%s" and the door opens: message the Page at %s and ask for %s item.'
            % (word, link, word))


def keyword_for(category: str, item_word: str) -> str:
    """H8 step 4 — the pack writer's one keyword rule: category + a distinct item word.

    Thirty daily packs reusing the bare category for different promised items is
    exactly the misroute H8 names, so ``item_word`` is required and must carry at
    least one letter or digit: ``keyword_for("GIFT", "guide")`` returns
    ``GIFTGUIDE`` while ``keyword_for("GIFT", "")`` refuses. The result is the
    same shape the resolver matches as one exact token.
    """
    prefix = _check_category(category)
    if not isinstance(item_word, str):
        raise MessengerLinkError("item_word must be a string")
    word = re.sub(r"[^A-Z0-9]", "", item_word.strip().upper())
    if not word:
        raise MessengerLinkError(
            "item_word must carry at least one letter or digit; the bare category %r "
            "is never reused for a different promised item" % (prefix,))
    keyword = prefix + word
    if not CATEGORY_RE.match(keyword):
        raise MessengerLinkError(
            "keyword %r is not ^[A-Z0-9]{1,32}$ (category plus item word)" % (keyword,))
    return keyword


def _local_date(scheduled_at: str) -> datetime.date:
    """The placement's own local date, read from its ISO timestamp."""
    if not isinstance(scheduled_at, str) or not scheduled_at.strip():
        raise MessengerLinkError("scheduled_at is required for the pack writer's ref date")
    text = scheduled_at.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text).date()
    except ValueError:
        raise MessengerLinkError(
            "scheduled_at %r is not an ISO timestamp" % (scheduled_at,)) from None


def record_page_binding(readiness_record: Mapping[str, Any], binding: PageBinding) -> Dict[str, Any]:
    """C5 step 2 rule — one Page id per tenant and account, keyed by the binding revision.

    ``shared_readiness.project()`` records the live binding under ``binding``. The
    Page id is accepted only while that revision is still the recorded one, so a
    rebind invalidates the Page id with the rest of the readiness proof. A record
    that already carries a different Page id is refused, never overwritten.
    """
    if not isinstance(readiness_record, dict):
        raise MessengerLinkError("readiness_record must be an object")
    if not isinstance(binding, PageBinding):
        raise MessengerLinkError("binding must be a PageBinding")
    recorded = readiness_record.get("binding")
    if recorded is not None and str(recorded) != binding.binding_revision:
        raise MessengerLinkError(
            "readiness record is bound to revision %r; Page id %r belongs to %r — a "
            "rebind invalidates the recorded Page (never guess one)"
            % (recorded, binding.page_id, binding.binding_revision))
    existing = readiness_record.get("messenger_page_id")
    if existing is not None and str(existing) != binding.page_id:
        raise MessengerLinkError(
            "readiness record already names Page id %r; %r is a different Page — "
            "refusing to overwrite a recorded binding" % (existing, binding.page_id))
    out = dict(readiness_record)
    out.update(binding.as_record())
    return out


def build_bonus_placement(
    placement: Mapping[str, Any],
    binding: PageBinding,
    *,
    category: Optional[str] = None,
    item_word: Optional[str] = None,
    local_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """C5 step 6 — the pack writer builds the door now, never at posting time.

    Returns a copy of ``placement`` carrying ``messenger_page_id``,
    ``messenger_ref``, ``messenger_link``, the category-plus-item-word ``keyword``
    and the canonical ``cta_text``. A placement that already carries a different
    Page id, ref, link or CTA is refused rather than silently replaced, so a
    hand-typed door can never be laundered into an approved one.
    """
    if not isinstance(placement, dict):
        raise MessengerLinkError("placement must be an object")
    category_value = category or placement.get("category")
    if not category_value:
        raise MessengerLinkError("category is required; the pack writer never guesses one")
    prefix = _check_category(category_value)
    word = item_word or placement.get("promised_item_word")
    existing_keyword = placement.get("keyword")
    if not word and isinstance(existing_keyword, str):
        upper = re.sub(r"[^A-Z0-9]", "", existing_keyword.strip().upper())
        if upper.startswith(prefix) and len(upper) > len(prefix):
            word = upper[len(prefix):]
    keyword = keyword_for(prefix, word or "")
    day = local_date or _local_date(placement.get("scheduled_at"))
    ref = build_ref(day, prefix)
    link = build_messenger_link(binding, ref)
    door = {
        "messenger_page_id": binding.page_id,
        "messenger_ref": ref,
        "messenger_link": link,
        "keyword": keyword,
        "cta_text": bonus_cta(link, keyword),
    }
    out = dict(placement)
    for name, value in door.items():
        existing = out.get(name)
        if existing is not None and existing != value:
            raise MessengerLinkError(
                "%s already carries %r; the pack writer builds %r at write time and "
                "never accepts a hand-typed value" % (name, existing, value))
        out[name] = value
    return out


def keyword_table_from_manifest(manifest: Mapping[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """The resolver's two tables, from APPROVED placements only.

    Returns (``{keyword: promised_item_version}``, ``{messenger_ref: promised_item_version}``).
    A collision on either key with a different item is refused: the door must fail
    closed at approval time, never silently keep the last item.
    """
    by_keyword: Dict[str, str] = {}
    by_ref: Dict[str, str] = {}
    placements = manifest.get("placements")
    if not isinstance(placements, list):
        raise MessengerLinkError("manifest placements must be a list")
    for placement in placements:
        if not isinstance(placement, dict):
            continue
        if placement.get("approval_status") != "APPROVED":
            continue
        item = placement.get("promised_item_version")
        placement_id = placement.get("placement_id")
        keyword = placement.get("keyword")
        ref = placement.get("messenger_ref")
        for table, key, label in ((by_keyword, keyword, "keyword"), (by_ref, ref, "ref")):
            if key is None:
                continue
            if key in table and table[key] != item:
                raise MessengerLinkError(
                    "%s %r maps to %r on placement %r and to %r on %r"
                    % (label, key, table[key], placement_id, item, placement_id)
                )
            table[key] = item
    return by_keyword, by_ref


def _selfcheck() -> None:
    binding = PageBinding("t1", "acct-1", "101575980173901", "rev-7")
    day = datetime.date(2026, 11, 1)
    ref = build_ref(day, "gift")
    assert ref == "pb-NOV01-2026-GIFT", ref
    link = build_messenger_link(binding, ref)
    assert link == "https://m.me/101575980173901?ref=pb-NOV01-2026-GIFT", link
    parsed = parse_messenger_link(link)
    assert (parsed.page_id, parsed.ref, parsed.local_date, parsed.category) == (
        "101575980173901", ref, day, "GIFT"), parsed
    cta = bonus_cta(link, "GIFTGUIDE")
    assert "GIFTGUIDE" in cta and link in cta, cta

    for bad in ("http://m.me/101575980173901?ref=" + ref,
                "https://M.ME/101575980173901?ref=" + ref,
                "https://m.me/101575980173901?ref=%s&utm=x" % ref,
                "https://m.me/101575980173901?ref=" + ref.lower(),
                "https://facebook.com/101575980173901?ref=" + ref,
                "https://m.me/101575980173901?ref=pb-NOV01-2026-gift",
                "https://m.me/101575980173901"):
        try:
            parse_messenger_link(bad)
        except MessengerLinkError:
            pass
        else:
            raise AssertionError("accepted an illegal link: %s" % bad)

    for bad_page in ("1015759801739010" * 3, "1015", "page-name", "https://m.me/101575980173901"):
        try:
            PageBinding("t1", "a", bad_page, "rev-1")
        except MessengerLinkError:
            pass
        else:
            raise AssertionError("accepted page id %r" % (bad_page,))

    for bad_cat in ("gift guide", "GIFT-", "", "G" * 33):
        try:
            build_ref(day, bad_cat)
        except MessengerLinkError:
            pass
        else:
            raise AssertionError("accepted category %r" % (bad_cat,))

    manifest = {
        "placements": [
            {"placement_id": "p1", "approval_status": "APPROVED", "keyword": "GIFTGUIDE",
             "messenger_ref": "pb-NOV01-2026-GIFT", "promised_item_version": "v1"},
            {"placement_id": "p2", "approval_status": "APPROVED", "keyword": "GIFTCHECKLIST",
             "messenger_ref": "pb-NOV02-2026-GIFT", "promised_item_version": "v2"},
            {"placement_id": "p3", "approval_status": "DRAFT", "keyword": "DRAFTONLY",
             "messenger_ref": "pb-NOV03-2026-GIFT", "promised_item_version": "v9"},
        ]
    }
    by_keyword, by_ref = keyword_table_from_manifest(manifest)
    assert by_keyword == {"GIFTGUIDE": "v1", "GIFTCHECKLIST": "v2"}, by_keyword
    assert "DRAFTONLY" not in by_keyword
    clash = {"placements": [
        {"placement_id": "a", "approval_status": "APPROVED", "keyword": "GIFT",
         "promised_item_version": "v1"},
        {"placement_id": "b", "approval_status": "APPROVED", "keyword": "GIFT",
         "promised_item_version": "v2"},
    ]}
    try:
        keyword_table_from_manifest(clash)
    except MessengerLinkError:
        pass
    else:
        raise AssertionError("accepted a keyword collision across items")
    # H8 step 4: the writer's keyword is category + a distinct item word.
    assert keyword_for("gift", " guide ") == "GIFTGUIDE", keyword_for("gift", "guide")
    assert keyword_for("GIFT", "CHECKLIST") == "GIFTCHECKLIST"
    for bad_word in ("", "   ", "!!!"):
        try:
            keyword_for("GIFT", bad_word)
        except MessengerLinkError:
            pass
        else:
            raise AssertionError("accepted bare category as a keyword (%r)" % (bad_word,))

    # C5 step 2: the Page id is recorded on the readiness record, keyed by revision.
    readiness = {"schema": "shared-readiness-projection.v1",
                 "surface": "facebook.page", "binding": "rev-7", "epoch": 0,
                 "states": {"installed": "installed", "running": "running", "live": "live"}}
    recorded = record_page_binding(readiness, binding)
    assert recorded["messenger_page_id"] == "101575980173901", recorded
    assert recorded["account_binding_revision"] == "rev-7"
    assert recorded["binding"] == "rev-7", recorded
    assert PageBinding.from_record(recorded) == binding, PageBinding.from_record(recorded)
    try:
        record_page_binding(recorded, PageBinding("t1", "acct-1", "101575980173902", "rev-7"))
    except MessengerLinkError:
        pass
    else:
        raise AssertionError("overwrote a recorded Page id")
    try:
        record_page_binding(readiness, PageBinding("t1", "acct-1", "101575980173901", "rev-8"))
    except MessengerLinkError:
        pass
    else:
        raise AssertionError("accepted a Page id for a revision the record does not name")

    # C5 step 6: the pack writer builds ref + link + CTA at write time, idempotently.
    draft = {"placement_id": "p9", "category": "GIFT", "promised_item_word": "GUIDE",
             "scheduled_at": "2026-11-01T19:30:00-04:00"}
    packed = build_bonus_placement(draft, binding)
    assert packed["messenger_ref"] == "pb-NOV01-2026-GIFT", packed
    assert packed["messenger_link"] == "https://m.me/101575980173901?ref=pb-NOV01-2026-GIFT", packed
    assert packed["keyword"] == "GIFTGUIDE", packed
    assert packed["cta_text"] == bonus_cta(packed["messenger_link"], "GIFTGUIDE")
    assert packed["messenger_link"] in packed["cta_text"]
    assert build_bonus_placement(packed, binding) == packed, "writer is not idempotent"
    for field, hand_typed in (("messenger_page_id", "101575980173902"),
                              ("messenger_ref", "pb-NOV02-2026-GIFT"),
                              ("messenger_link", "https://m.me/101575980173901?ref=pb-NOV02-2026-GIFT"),
                              ("keyword", "GIFT"),
                              ("cta_text", "message the Page")):
        dirty = dict(draft, **{field: hand_typed})
        try:
            build_bonus_placement(dirty, binding)
        except MessengerLinkError:
            pass
        else:
            raise AssertionError("accepted a hand-typed %s" % field)
    try:
        build_bonus_placement({"placement_id": "p10"}, binding)
    except MessengerLinkError:
        pass
    else:
        raise AssertionError("built a door with no category")

    # C5 step 8: attribution stays unproven here.
    assert REF_ATTRIBUTION == "NOT_PROVEN"

    print("messenger_link self-check: OK (round-trip, six refusals, table, collision,"
          " writer keyword, readiness binding, write-time door, attribution)")


if __name__ == "__main__":
    try:
        _selfcheck()
    except AssertionError as exc:
        print("messenger_link self-check: FAIL %s" % exc)
        sys.exit(1)
