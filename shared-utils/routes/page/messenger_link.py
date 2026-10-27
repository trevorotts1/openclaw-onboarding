#!/usr/bin/env python3
"""Messenger DM-door link builder (review C5 / unit T-56).

One stdlib-only home for the Bonus-comment door: the Page binding recorded once
per tenant, the ``pb-<MON><DD>-<YYYY>-<CATEGORY>`` ref, the ``m.me`` link, its
inverse parser, the canonical Bonus sentence, and the only producer of the
resolver's keyword and ref tables.

Rules enforced here (review C5 Exactly-how steps 1 and H8 step 5):
  * a Page id is 5 to 20 digits, never a username or a URL;
  * a ref is dated in the placement's own local date and categorised;
  * a link is ``https://m.me/<page_id>?ref=<quoted ref>`` and nothing else;
  * a link longer than Meta's 2,083-character cap is refused;
  * the keyword table reads APPROVED placements only.

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
    print("messenger_link self-check: OK (round-trip, six refusals, table, collision)")


if __name__ == "__main__":
    try:
        _selfcheck()
    except AssertionError as exc:
        print("messenger_link self-check: FAIL %s" % exc)
        sys.exit(1)
