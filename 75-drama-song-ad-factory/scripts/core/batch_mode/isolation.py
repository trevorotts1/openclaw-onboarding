#!/usr/bin/env python3
"""Never-mix checks: books and authors stay inside their own campaign.

Owner decision D26, plan 6.14 (choice-card-spec 3.10): "Never mix books or
authors. Characters, lyrics, assets and files stay inside that book's
campaign." This module is the enforcement half of
``batch_mode.materialize`` -- the manifest it inspects is the one
``materialize`` writes, and every rule here fails LOUDLY (``BatchError`` with
a code) instead of letting two books share a folder, a ledger run, a Command
Center job or a cover.

Codes (one per way a batch can be mixed):

  SHARED_FOLDER         two books resolve to the same campaign folder
  SHARED_LEDGER_RUN     two books share a spend-ledger run id, or a ledger db
                        does not hold its own run
  SHARED_CC_REGISTER    two books share a Command Center job id
  SHARED_ASSET          one cover/product image serves two books
  BOOK_MIXED            another book's title or folder slug appears inside
                        this book's files or file names
  AUTHOR_MIXED          another book's author appears inside this book's files
  CROSS_BRIEF           one book's brief references another book
  PER_BOOK_CARD         the batch carries more than one choice card
  MISSING_BOOK_FOLDER   a book in the manifest has no campaign folder

Matching is normalized-substring, not token equality, so "Acme Press" and
"acme   press" are the same string. Two ceilings are deliberate and marked:

  ponytail: a title shorter than 8 characters (and fewer than 3 words) is only
  matched by its folder slug, not by its bare text -- "Hope" would otherwise
  fire on the word "hope" inside an innocent brief. Upgrade path: match on
  title + author together for short titles.
  ponytail: an author shorter than 6 characters is matched by slug only, for
  the same false-positive reason.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    import spend_ledger as L
except ImportError as _e:                       # imported as core.batch_mode
    if "spend_ledger" not in str(_e):
        raise
    from .. import spend_ledger as L            # type: ignore

try:
    from .batch import BRIEF_FIELDS, BatchError, _norm
except ImportError as _e:                       # run as a loose script
    if "batch_mode" not in str(_e) and "batch" not in str(_e):
        raise
    from batch import BRIEF_FIELDS, BatchError, _norm    # type: ignore

#: Files read when looking for a foreign book inside a campaign folder.
TEXT_SUFFIXES = (".json", ".md", ".txt", ".csv")
#: Minimum normalized length before a bare title/author is used as a needle.
TITLE_MIN_CHARS = 8
TITLE_MIN_WORDS = 3
AUTHOR_MIN_CHARS = 6

#: Structural artifacts every book's campaign folder must hold.
REQUIRED_FILES = ("brief.json", "receipt.json", "cc-register.json",
                  "ledger.db")


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def _read_brief(entry):
    try:
        data = json.loads(Path(entry["brief"]).read_text(encoding="utf-8"))
    except Exception as exc:                     # noqa: BLE001 - report, not raise
        _loud("fail", "BRIEF_UNREADABLE",
              "%s: %r (isolation check cannot run for this book)"
              % (entry.get("brief"), exc))
        return {}
    book = data.get("book") or {}
    return {k: book.get(k) or "" for k in BRIEF_FIELDS}


def _title_is_distinctive(title):
    norm = _norm(title)
    return len(norm) >= TITLE_MIN_CHARS or len(norm.split()) >= TITLE_MIN_WORDS


def _author_is_distinctive(author):
    return len(_norm(author)) >= AUTHOR_MIN_CHARS


def _scan_file(path, foreign):
    """-> the foreign kinds ("slug" | "title" | "author") this file leaks.

    ``foreign`` is a list of ``(kind, needle, usable)`` triples; a needle that
    is not distinctive enough is skipped (see the module's ponytail notes).
    """
    hits = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001 - binary/locked
        return hits
    norm = _norm(text)
    name = _norm(str(path))
    for kind, needle, usable in foreign:
        if not needle or not usable:
            continue
        n = _norm(needle)
        if n in norm or n in name:
            hits.add(kind)
    return hits


def find_violations(manifest):
    """Every way this batch mixes books/authors, as a list of dicts.

    Empty list == isolated. Never raises on a violation -- ``assert_isolated``
    does that -- so a caller can print the whole list.
    """
    problems = []
    if not isinstance(manifest, dict):
        return [{"code": "CARD_INVALID",
                 "detail": "manifest must be a dict, got %s"
                           % type(manifest).__name__}]

    books = list(manifest.get("books") or [])
    card = manifest.get("card")

    # 1. one card for the whole batch, never one per book
    if manifest.get("card_count") != 1 or not isinstance(card, dict):
        problems.append({"code": "PER_BOOK_CARD",
                         "detail": "manifest declares %r cards"
                                   % manifest.get("card_count")})
    else:
        for book in books:
            leaked = [k for k in ("card", "card_fields", "style", "music",
                                  "voice", "length", "shape")
                      if k in book]
            if leaked:
                problems.append({"code": "PER_BOOK_CARD",
                                 "detail": "book %r carries its own %s"
                                           % (book.get("slug"), leaked)})

    # 2. structural separation: folders, run ids, job ids
    folders, run_ids, job_ids = {}, {}, {}
    for book in books:
        slug = book.get("slug") or ""
        folder = book.get("campaign_folder") or ""
        for registry, value, code in ((folders, folder, "SHARED_FOLDER"),
                                      (run_ids, book.get("run_id"),
                                       "SHARED_LEDGER_RUN"),
                                      (job_ids, book.get("cc_job_id"),
                                       "SHARED_CC_REGISTER")):
            if not value:
                problems.append({"code": code,
                                 "detail": "book %r has no %s"
                                           % (slug, code.split("_")[1].lower())})
            elif value in registry:
                problems.append({
                    "code": code,
                    "detail": "%r shared by books %r and %r"
                              % (value, registry[value], slug)})
            else:
                registry[value] = slug

    # 3. each folder exists and holds exactly its own artifacts
    for book in books:
        folder = Path(book.get("campaign_folder") or "")
        if not str(folder) or not folder.is_dir():
            problems.append({"code": "MISSING_BOOK_FOLDER",
                             "detail": "no campaign folder for %r (%s)"
                                       % (book.get("slug"), folder)})
            continue
        for name in REQUIRED_FILES:
            if not (folder / name).is_file():
                problems.append({"code": "MISSING_BOOK_FOLDER",
                                 "detail": "%s missing from %s"
                                           % (name, folder)})
        # its own spend-ledger run, proven by reading the db back
        summary = L.summary(str(folder / "ledger.db"), book.get("run_id"))
        if summary.get("outcome") != "ok":
            problems.append({"code": "SHARED_LEDGER_RUN",
                             "detail": "ledger run %r not found in %s (%s)"
                                       % (book.get("run_id"), folder,
                                          summary.get("reason_code"))})

    # 4. cross-book content: nothing of another book inside this campaign
    briefs = {book.get("slug"): _read_brief(book) for book in books}
    for book in books:
        folder = Path(book.get("campaign_folder") or "")
        foreign = []
        for other in books:
            if other.get("slug") == book.get("slug"):
                continue
            ob = briefs.get(other.get("slug")) or {}
            title, author = ob.get("title", ""), ob.get("author", "")
            foreign.append(("slug", other.get("slug"), True))
            foreign.append(("title", title, _title_is_distinctive(title)))
            foreign.append(("author", author, _author_is_distinctive(author)))
        # brief vs brief: one book's brief must not name another book
        own = briefs.get(book.get("slug")) or {}
        own_text = _norm(" ".join(str(own.get(k) or "") for k in BRIEF_FIELDS))
        for other in books:
            if other.get("slug") == book.get("slug"):
                continue
            ob = briefs.get(other.get("slug")) or {}
            title, author = ob.get("title", ""), ob.get("author", "")
            if title and _title_is_distinctive(title) and _norm(title) in own_text:
                problems.append({"code": "CROSS_BRIEF",
                                 "detail": "brief of %r names book %r"
                                           % (book.get("slug"), title)})
            if author and _author_is_distinctive(author) \
                    and _norm(author) in own_text:
                problems.append({"code": "CROSS_BRIEF",
                                 "detail": "brief of %r names author %r"
                                           % (book.get("slug"), author)})
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            for hit in _scan_file(path, foreign):
                if hit == "author":
                    problems.append({"code": "AUTHOR_MIXED",
                                     "detail": "another book's author appears "
                                               "in %s" % path})
                elif hit == "slug" or hit == "title":
                    problems.append({"code": "BOOK_MIXED",
                                     "detail": "another book's %s appears "
                                               "in %s" % (hit, path)})

    # 5. one cover per book
    covers = {}
    for book in books:
        cover = briefs.get(book.get("slug")) or {}
        cover = (cover.get("cover") or "").strip()
        if not cover:
            continue
        key = os.path.normpath(os.path.expanduser(cover))
        if key in covers:
            problems.append({"code": "SHARED_ASSET",
                             "detail": "cover %r used by books %r and %r"
                                       % (cover, covers[key],
                                          book.get("slug"))})
        else:
            covers[key] = book.get("slug")
    return problems


def assert_isolated(manifest):
    """Raise the first violation. Empty manifest is not "clean" -- it is
    missing its books, so that is a violation too."""
    if not isinstance(manifest, dict) or not manifest.get("books"):
        raise BatchError("BOOK_LIST_EMPTY",
                         "nothing to isolate: manifest has no books")
    problems = find_violations(manifest)
    if problems:
        first = problems[0]
        raise BatchError(first["code"],
                         "%s (%d violation%s total)"
                         % (first["detail"], len(problems),
                            "" if len(problems) == 1 else "s"))
    return True


def check_briefs(books):
    """Pre-materialize half: one book's brief must not already name another.

    Cheap scan of the list itself, so a mixed brief is refused before any
    folder, ledger run or Command Center job exists.
    """
    problems = []
    normed = []
    for book in books or []:
        text = _norm(" ".join(str(book.get(k) or "") for k in BRIEF_FIELDS))
        normed.append((book.get("slug"), text))
    for i, (slug, text) in enumerate(normed):
        for j, (other_slug, _) in enumerate(normed):
            if i == j:
                continue
            other = books[j]
            title = str(other.get("title") or "")
            if title and _title_is_distinctive(title) and _norm(title) in text:
                problems.append({"code": "CROSS_BRIEF",
                                 "detail": "brief of %r names book %r"
                                           % (slug, title)})
                break
    if problems:
        raise BatchError(problems[0]["code"], problems[0]["detail"])
    return True


__all__ = [
    "AUTHOR_MIN_CHARS",
    "REQUIRED_FILES",
    "TEXT_SUFFIXES",
    "TITLE_MIN_CHARS",
    "TITLE_MIN_WORDS",
    "assert_isolated",
    "check_briefs",
    "find_violations",
]
