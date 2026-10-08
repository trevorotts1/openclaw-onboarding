#!/usr/bin/env python3
"""Batch mode: ONE choice card for the whole batch, ONE ad per book.

Owner decision D26, plan 6.14; normative text is
``onboarding/75-drama-song-ad-factory/references/choice-card-spec.md``
section 3.10 ("Batch mode"):

  * the client approves one choice card for the whole batch -- look, music,
    voice, length, shape are chosen ONCE;
  * the card then takes a list of books, one brief each;
  * one ad per book, each with its own campaign folder, its own receipt, its
    own spend-ledger run and its own Command Center deliverable;
  * never mix books or authors -- characters, lyrics, assets and files stay
    inside that book's campaign (``isolation.py`` owns those checks);
  * the approval card shows the batch total, computed from Skill 74 ``price``
    for every book in the list, plus the 20% retake allowance.

Price is a SEAM, never computed here: every number comes from the injected
``price_fn(book, card)`` (the Skill 74 ``price`` adapter). With no seam, with
a seam that returns nothing, or with a seam that blows up, the card reports
the price as unavailable and ``start_allowed`` stays False -- no paid work
starts (choice-card-spec section 4.4).

Mocked by construction: this module opens no socket, spends nothing and
contacts no provider. Style and music choices are resolved by the sibling
``style_defaults`` package so the D24 defaults and the off-menu refusals are
not re-invented here.

stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import spend_ledger as L                      # core/ on sys.path
except ImportError as _e:                          # imported as core.batch_mode
    if "spend_ledger" not in str(_e):
        raise
    from .. import spend_ledger as L              # type: ignore

try:
    import style_defaults as SD                   # D24 style/music defaults
except ImportError as _e:
    if "style_defaults" not in str(_e):
        raise
    from .. import style_defaults as SD           # type: ignore

try:
    from choice_card.stl_voice_guard import (     # D25: STL is always All Suno
        CLIENT_REASON as STL_CLIENT_REASON,
        REASON_CODE as STL_REASON_CODE,
        guard_intake,
        is_forbidden as stl_pair_forbidden,
    )
except ImportError as _e:
    if "choice_card" not in str(_e):
        raise
    from ..choice_card.stl_voice_guard import (   # type: ignore
        CLIENT_REASON as STL_CLIENT_REASON,
        REASON_CODE as STL_REASON_CODE,
        guard_intake,
        is_forbidden as stl_pair_forbidden,
    )

TOOL_NAME = "batch_mode"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.batch-mode/v1"
SOURCE = "D26, plan 6.14 (choice-card-spec 3.10)"

#: The five fields chosen ONCE for the batch. Spec card order.
CARD_FIELDS = ("length", "shape", "style", "music", "voice")

#: choice-card-spec section 4.3: the approved price carries 20% retake.
RETAKE_ALLOWANCE = 0.20

#: The book brief (choice-card-spec 3.9), still inside the three-question cap.
BRIEF_REQUIRED = ("title", "author")
BRIEF_OPTIONAL = ("cover", "buy_link", "audience", "pain_transformation")
BRIEF_FIELDS = BRIEF_REQUIRED + BRIEF_OPTIONAL

#: Books never carry a card of their own.
BATCH_CARD_KEYS = ("card_type", "batch_id") + CARD_FIELDS

VOICE_VALUES = ("all-suno", "velvet-voiceover")
VOICE_LABELS = {
    "all-suno": "All Suno",
    "velvet-voiceover": "Velvet Voiceover",
}
LENGTH_VALUES = (
    "60 seconds", "90 seconds", "3 minutes", "5 minutes",
    "10-minute long version",
)
SHAPE_VALUES = ("9:16", "16:9", "both")
#: The spellings the rest of the factory already puts on a card.
SHAPE_ALIASES = {
    "9:16 vertical": "9:16",
    "16:9 widescreen": "16:9",
}

DEFAULT_VOICE = "all-suno"
DEFAULT_LENGTH = "60 seconds"
DEFAULT_SHAPE = "9:16"

# Plan 10.3 board, transcribed: plan_103.py lives under tests/ and core does
# not import tests. Titles are what the Command Center renders.
STAGES = (
    ("research", "Research"),
    ("creative-strategy", "Creative Strategy"),
    ("script-lyrics", "Script/Lyrics"),
    ("music", "Music"),
    ("continuity-bible", "Continuity Bible"),
    ("storyboard", "Storyboard"),
    ("image-keyframes", "Image/Keyframes"),
    ("video-generation", "Video Generation"),
    ("qc-retakes", "QC/Retakes"),
    ("assembly", "Assembly"),
    ("final-qc", "Final QC"),
    ("delivery", "Delivery"),
)
DEFAULT_WORKSPACE = "ws-batch-mode"


class BatchError(Exception):
    """A refusal this unit owns. ``code`` is what tests and the card print."""

    def __init__(self, code, message=""):
        super().__init__("%s: %s" % (code, message or code))
        self.code = code


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(text):
    """Lower, whitespace-collapsed form used for cross-book matching."""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def slugify(text):
    """Filesystem-safe book token: lowercase alnum runs joined by '-'."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or "untitled"


def _canon(values, labels, value, field):
    """Map a label or an id onto the canonical id, or refuse by name."""
    if not isinstance(value, str) or not value.strip():
        raise BatchError("UNKNOWN_%s" % field.upper(),
                         "%s must be one of %s, got %r" % (field, list(values),
                                                           value))
    raw = _norm(re.sub(r"\s*\(\s*(?:the\s+)?default\s*\)\s*$", "", value,
                       flags=re.I))
    for vid in values:
        if raw == _norm(vid) or raw == _norm(labels.get(vid, "")):
            return vid
    raise BatchError("UNKNOWN_%s" % field.upper(),
                     "%r is not offered on the batch card (offer: %s)"
                     % (value, ", ".join(values)))


def _canon_shape(value):
    if isinstance(value, str):
        value = SHAPE_ALIASES.get(_norm(value), value)
    return _canon(SHAPE_VALUES, {}, value, "shape")


# ---------------------------------------------------------------- the card --
def make_card(selections=None, batch_id=None):
    """The one card for the whole batch. Defaults: style/music from D24
    (``style_defaults``), voice/length/shape from choice-card-spec 2.

    Returns a NEW dict. Nothing is written, nothing is spent.
    """
    sel = dict(selections or {})
    card = {
        "card_type": "batch",
        "batch_id": batch_id or "",
        "source": SOURCE,
        "schema_version": SCHEMA_VERSION,
    }
    # style + music resolve through the D24 package: same defaults, same
    # off-menu refusals, no second vocabulary in this unit.
    try:
        resolved = SD.apply_choices({}, sel.get("style"), sel.get("music"))
    except Exception as exc:                      # noqa: BLE001 - wrap refusal
        raise BatchError("UNKNOWN_STYLE_OR_MUSIC",
                         str(getattr(exc, "code", exc))) from exc
    card["style"] = resolved["style"]
    card["music"] = resolved["music"]
    card["voice"] = _canon(VOICE_VALUES, VOICE_LABELS,
                           sel.get("voice", DEFAULT_VOICE), "voice")
    # D25 (decision log 38): Sketch to Life is always All Suno -- the pair
    # never reaches a card, so Velvet Voiceover is unselectable on that look.
    verdict = guard_intake(card["style"], card["voice"])
    if verdict["outcome"] == "refused":
        raise BatchError(STL_REASON_CODE, STL_CLIENT_REASON)
    card["length"] = _canon(LENGTH_VALUES, {}, sel.get("length", DEFAULT_LENGTH),
                            "length")
    card["shape"] = _canon_shape(sel.get("shape", DEFAULT_SHAPE))
    card["books"] = []
    card["price_status"] = "unpriced"
    card["subtotal_usd"] = None
    card["price_usd"] = None
    card["retake_allowance"] = RETAKE_ALLOWANCE
    card["start_allowed"] = False
    return card


def card_fields(card):
    """Exactly the five once-chosen fields, in card order."""
    return {f: card[f] for f in CARD_FIELDS}


# ------------------------------------------------------------- book briefs --
def normalize_brief(raw):
    """One book brief: title and author required, the rest optional."""
    if isinstance(raw, str):                      # bare title is a plain offer
        raw = {"title": raw}
    if not isinstance(raw, dict):
        raise BatchError("BRIEF_INVALID",
                         "a book brief must be a dict, got %s"
                         % type(raw).__name__)
    brief = {k: (raw.get(k) or "").strip() if isinstance(raw.get(k), str)
             else raw.get(k) for k in BRIEF_FIELDS}
    for key in BRIEF_REQUIRED:
        if not brief.get(key):
            raise BatchError("BRIEF_MISSING",
                             "every book brief needs a %s" % key)
    for key in ("cover", "buy_link", "audience", "pain_transformation"):
        if brief.get(key) is not None and not isinstance(brief[key], str):
            raise BatchError("BRIEF_INVALID", "%s must be a string" % key)
    return brief


def set_books(card, briefs):
    """Attach the book list. The five card fields are NOT touched.

    Returns a new card. Every book gets its own slug, spend-ledger run id and
    Command Center job id -- those are what keep the ads apart later.
    """
    if not isinstance(card, dict) or card.get("card_type") != "batch":
        raise BatchError("CARD_INVALID", "not a batch card")
    if isinstance(briefs, (str, dict)):
        briefs = [briefs]
    briefs = list(briefs or [])
    if not briefs:
        raise BatchError("BOOK_LIST_EMPTY", "a batch needs at least one book")

    batch_id = card.get("batch_id") or _batch_id(briefs)
    books = []
    seen_slug, seen_pair = {}, {}
    for raw in briefs:
        brief = normalize_brief(raw)
        slug = slugify("%s-%s" % (brief["author"], brief["title"]))
        pair = (_norm(brief["title"]), _norm(brief["author"]))
        if pair in seen_pair:
            raise BatchError("DUPLICATE_BOOK",
                             "%s by %s is already in this batch"
                             % (brief["title"], brief["author"]))
        if slug in seen_slug:
            raise BatchError("SLUG_COLLISION",
                             "%r and %r collide on folder name %r"
                             % (seen_slug[slug]["title"], brief["title"], slug))
        seen_slug[slug] = brief
        seen_pair[pair] = True
        books.append(dict(brief, slug=slug,
                          run_id="%s--%s" % (batch_id, slug),
                          cc_job_id="%s--%s" % (batch_id, slug),
                          position=len(books) + 1))
    out = dict(card)
    out["batch_id"] = batch_id
    out["books"] = books
    return out


def _batch_id(briefs):
    """Deterministic id: same book list, same batch id, across runs."""
    parts = ["%s|%s" % (slugify(b["author"]), slugify(b["title"]))
             for b in briefs]
    return "batch-" + hashlib.sha256("\n".join(sorted(parts))
                                     .encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------- pricing ----
def _book_price(price_fn, book, card):
    """One Skill 74 price for one book. None means 'unavailable', not 0."""
    try:
        value = price_fn(dict(book), card_fields(card))
    except Exception as exc:                      # noqa: BLE001 - fail closed
        raise BatchError("PRICE_UNAVAILABLE",
                         "price seam failed for %s: %s"
                         % (book["title"], exc)) from exc
    if value is None:
        raise BatchError("PRICE_UNAVAILABLE",
                         "no price for %s" % book["title"])
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise BatchError("PRICE_UNAVAILABLE",
                         "price for %s is not a number" % book["title"]) from exc
    if not math.isfinite(amount) or amount < 0:
        raise BatchError("PRICE_UNAVAILABLE",
                         "price for %s is %r" % (book["title"], value))
    return amount


def _cents(value):
    return round(value + 1e-9, 2)

def default_price_fn():
    """The shipped Skill 74 ``price`` adapter, or None on a machine without one.

    B4: batch.py's price seam had no provider. The default wiring wraps the
    catalog calculator's adapter discovery (74-kie-live-adapter next to the
    skill root, or ``DSAF_SKILL74_ADAPTER``). It returns ``None`` when no
    adapter exists — callers keep their unpriced fail-closed path, and no
    number is ever invented here.
    """
    _card, adapter = _card_renderer()
    if adapter is None:
        return None
    return _skill74_book_price(adapter)

def _card_renderer():
    """-> (card_render module|None, its price_fn_default() result|None)."""
    try:
        from ..catalog_calculator import card_render
    except ImportError as _e:
        if "card_render" not in str(_e) and "beyond top-level" not in str(_e):
            raise
        try:  # script import from core/ on sys.path
            from catalog_calculator import card_render
        except ImportError as _e2:
            if "card_render" not in str(_e2):
                raise
            return None, None
    return card_render, card_render.price_fn_default()

def _skill74_book_price(adapter):
    """Adapt ``price_fn(model, units) -> JSON`` to the batch seam
    ``(book, card_fields) -> USD number``: price the ad's default choice
    through the catalog calculator (Skill 74 rates only; fail closed)."""
    import math as _math

    def price(book, fields):
        choice = _card_renderer()[0].default_choice(fields)
        catalog = _shipped_catalog()
        if catalog is None:
            raise BatchError("PRICE_UNAVAILABLE",
                             "no shipped model catalog to price against")
        env = adapter_for_env(choice, catalog, adapter)
        card = env.get("card") if env.get("state") == "ok" else None
        if not card or not _math.isfinite(card.get("price_usd", 0)):
            raise BatchError("PRICE_UNAVAILABLE",
                             "price unavailable for %s" % book.get("title"))
        return float(card["price_usd"])
    return price

def _shipped_catalog():
    """The fixtures catalog that ships with the calculator, or None."""
    import json as _json
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..",
                         "catalog_calculator", "extensions", "fixtures",
                         "catalog.json")
    try:
        with open(_os.path.abspath(path), encoding="utf-8") as f:
            return _json.load(f)
    except (OSError, ValueError):
        return None

def adapter_for_env(choice, catalog, adapter):
    """Price one choice into the card envelope, Skill 74 rates only."""
    card_render = _card_renderer()[0]
    if card_render is None:
        return {"state": "unavailable", "reasons": ["PRICE_CALCULATOR_MISSING"],
                "card": None, "warnings": []}
    return card_render.price_card_ext(choice, catalog, adapter)


def price_batch(card, price_fn=None):
    """Price the batch: one Skill 74 price per book, plus the 20% retake.

    ``price_fn(book, card_fields) -> USD number`` is the Skill 74 ``price``
    adapter; it is never supplied from a table in this repository. When no
    adapter is passed, the default wiring tries the catalog calculator's
    shipped Skill 74 adapter (:data:`default_price_fn`); a machine with no
    Skill 74 install gets ``None`` back and the card stays unpriced -- the
    card then says so and ``start_allowed`` stays False. Any book that
    cannot be priced makes the WHOLE card unpriced -- the card then says so
    and ``start_allowed`` stays False.
    """
    if price_fn is None:
        price_fn = default_price_fn()
    if not isinstance(card, dict) or card.get("card_type") != "batch":
        raise BatchError("CARD_INVALID", "not a batch card")
    out = dict(card)
    books = [dict(b) for b in out.get("books") or []]
    if not books:
        raise BatchError("BOOK_LIST_EMPTY", "price a batch that has books")
    if price_fn is None:
        out.update(price_status="unavailable", subtotal_usd=None,
                   price_usd=None, start_allowed=False, books=books)
        return out

    try:
        priced = []
        subtotal = 0.0
        for book in books:
            amount = _book_price(price_fn, book, out)
            subtotal += amount
            book["price_usd"] = _cents(amount)
            book["ceiling_usd"] = _cents(amount * (1 + RETAKE_ALLOWANCE))
            priced.append(book)
    except BatchError:
        out.update(price_status="unavailable", subtotal_usd=None,
                   price_usd=None, start_allowed=False, books=books)
        return out

    out["books"] = priced
    out["price_status"] = "ok"
    out["subtotal_usd"] = _cents(subtotal)
    out["price_usd"] = _cents(subtotal * (1 + RETAKE_ALLOWANCE))
    out["start_allowed"] = True
    return out


def _shown_voice(card, value):
    """D25: a Sketch to Life card never prints Velvet Voiceover as chosen.

    ``make_card`` already refuses the pair, so this only covers a card that
    was loaded from disk carrying it: the line shows All Suno instead. A
    card this function cannot read keeps its own spelling rather than
    failing the render.
    """
    try:
        forbidden = stl_pair_forbidden(card.get("style"), value)
    except Exception:                              # noqa: BLE001
        forbidden = False
    if forbidden:
        return VOICE_LABELS[DEFAULT_VOICE]
    return VOICE_LABELS.get(value, value)


def card_lines(card):
    """The card as the client reads it, batch total included."""
    labels = ("length", "shape", "style", "music", "voice")
    pretty = {"length": "Length", "shape": "Shape", "style": "Style",
              "music": "Music", "voice": "Voice"}
    lines = ["Your drama song ads (batch of %d)" % len(card.get("books") or [])]
    for f in labels:
        value = card.get(f)
        if f == "style":
            value = SD.style_label(value)
        elif f == "music":
            value = SD.music_label(value)
        elif f == "voice":
            value = _shown_voice(card, value)
        lines.append("  %-13s %s" % (pretty[f] + ":", value))
    lines.append("  %-13s %d book%s, one ad each"
                 % ("Books:", len(card.get("books") or []),
                    "" if len(card.get("books") or []) == 1 else "s"))
    if card.get("price_status") == "ok":
        lines.append("  %-13s $%.2f  (%d book%s, +20%% retake allowance)"
                     % ("Batch total:", card["price_usd"],
                        len(card.get("books") or []),
                        "" if len(card.get("books") or []) == 1 else "s"))
    else:
        lines.append("  %-13s unavailable -- media generation pricing is not "
                     "readable, nothing starts" % "Batch total:")
    lines.append("  [Approve]   [Change options]")
    return lines


def approve_batch(card):
    """One click, whole batch. Refuses while the price is unavailable.

    Returns the approval record written onto the parent campaign: the five
    fields, every book, the ceiling (price + 20% retake) and the card digest.
    There is no per-book approval -- one card, one approval.
    """
    if not isinstance(card, dict) or card.get("card_type") != "batch":
        raise BatchError("CARD_INVALID", "not a batch card")
    if not card.get("books"):
        raise BatchError("BOOK_LIST_EMPTY", "nothing to approve")
    if card.get("price_status") != "ok" or not card.get("start_allowed"):
        raise BatchError("PRICE_UNAVAILABLE",
                         "the batch total is unavailable, nothing starts")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "approved_at": _now(),
        "batch_id": card["batch_id"],
        "card_type": "batch",
        "card_fields": card_fields(card),
        "books": [b["slug"] for b in card["books"]],
        "subtotal_usd": card["subtotal_usd"],
        "retake_allowance": RETAKE_ALLOWANCE,
        "price_usd": card["price_usd"],
        "ceiling_usd": card["price_usd"],
        "card_digest": card_digest(card),
    }
    return payload


def card_digest(card):
    """Stable digest of the five fields + book slugs + total (approvals bind)."""
    blob = json.dumps({
        "fields": card_fields(card),
        "books": [b["slug"] for b in card.get("books") or []],
        "price_usd": card.get("price_usd"),
        "batch_id": card.get("batch_id"),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------- per-book campaign ----
def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


def materialize(card, root, price_fn=None, outbox=None,
                workspace=DEFAULT_WORKSPACE, check=True):
    """One campaign folder, one receipt, one ledger run, one CC register
    per book -- plus the batch manifest that carries the single card.

    Refuses to start unless the batch is priced (spec 4: no paid work before
    a recorded ceiling). ``root`` is created if missing. Raises
    ``BATCH_EXISTS`` when the batch directory already holds a manifest, so a
    second run can never interleave two books into one folder.

    ``outbox`` is optional (a ``cc_sync.Outbox``-alike): when given, one
    parent create for the batch and one create per book are enqueued, each
    with its own job id. Nothing here opens a socket itself.
    """
    if price_fn is None:
        price_fn = default_price_fn()
    if not isinstance(card, dict) or card.get("card_type") != "batch":
        raise BatchError("CARD_INVALID", "not a batch card")
    if card.get("price_status") != "ok" or not card.get("start_allowed"):
        raise BatchError("PRICE_UNAVAILABLE",
                         "price the batch before any campaign folder exists")
    books = list(card.get("books") or [])
    if not books:
        raise BatchError("BOOK_LIST_EMPTY", "a batch needs at least one book")

    batch_root = Path(root).expanduser() / card["batch_id"]
    manifest_path = batch_root / "batch-manifest.json"
    if manifest_path.exists():
        raise BatchError("BATCH_EXISTS",
                         "%s already materialized" % batch_path_display(batch_root))

    batch_root.mkdir(parents=True, exist_ok=True)
    stages = [{"slug": s, "title": t} for s, t in STAGES]

    entries = []
    for book in books:
        book_dir = batch_root / book["slug"]
        if book_dir.exists() and any(book_dir.iterdir()):
            raise BatchError("SHARED_FOLDER",
                             "campaign folder %r already holds another run"
                             % book["slug"])
        book_dir.mkdir(parents=True, exist_ok=True)

        brief_path = book_dir / "brief.json"
        _write_json(brief_path, {
            "schema_version": SCHEMA_VERSION,
            "batch_id": card["batch_id"],
            "book": {k: book.get(k) for k in BRIEF_FIELDS},
            "slug": book["slug"],
            "position": book["position"],
            "written_at": _now(),
        })

        # own spend-ledger run: one DB file, one run id, its own ceiling
        ledger_db = book_dir / "ledger.db"
        ceiling = book.get("ceiling_usd")
        if ceiling is None:
            raise BatchError("PRICE_UNAVAILABLE",
                             "no ceiling for %s" % book["title"])
        init = L.init_run(str(ledger_db), book["run_id"], ceiling)
        if init.get("outcome") != "ok":
            raise BatchError("LEDGER_RUN_FAILED",
                             "%s: %s" % (book["run_id"], init.get("reason")))

        receipt = {
            "schema_version": SCHEMA_VERSION,
            "kind": "book-campaign-receipt",
            "batch_id": card["batch_id"],
            "book": {k: book.get(k) for k in BRIEF_FIELDS},
            "slug": book["slug"],
            "run_id": book["run_id"],
            "cc_job_id": book["cc_job_id"],
            "card_fields": card_fields(card),
            "price_usd": book["price_usd"],
            "ceiling_usd": book["ceiling_usd"],
            "retake_allowance": RETAKE_ALLOWANCE,
            "written_at": _now(),
        }
        receipt_path = book_dir / "receipt.json"
        _write_json(receipt_path, receipt)

        register = {
            "schema_version": SCHEMA_VERSION,
            "kind": "cc-deliverable-register",
            "batch_id": card["batch_id"],
            "parent_cc_job_id": card["batch_id"],
            "cc_job_id": book["cc_job_id"],
            "show_name": book["title"],
            "slug": book["slug"],
            "run_id": book["run_id"],
            # H3 step 2: no separate 12-stage parent board — the batch id and
            # the parent job id live here and on the epic's provenance instead.
            "batch_parent": {
                "parent_cc_job_id": card["batch_id"],
                "book_position": book["position"],
                "book_count": len(books),
            },
            "deliverable": {
                "title": book["title"],
                "author": book["author"],
                "buy_link": book.get("buy_link", ""),
                "campaign_folder": str(book_dir),
                "receipt": str(receipt_path),
                "price_usd": book["price_usd"],
            },
            "written_at": _now(),
        }
        register_path = book_dir / "cc-register.json"
        _write_json(register_path, register)

        if outbox is not None:
            outbox.enqueue_create(
                book["cc_job_id"],
                "Book %d of %d — %s (batch %s)"
                % (book["position"], len(books), book["title"], card["batch_id"]),
                stages, workspace=workspace,
                department="video", title_prefix="Drama Song Ad",
                agent_id="vsl-video-sales-letter-specialist",
                money_ceiling_usd=book["ceiling_usd"],
                estimated_cost_usd=book["price_usd"])

        entries.append({
            "slug": book["slug"],
            "title": book["title"],
            "author": book["author"],
            "position": book["position"],
            "campaign_folder": str(book_dir),
            "brief": str(brief_path),
            "receipt": str(receipt_path),
            "cc_register": str(register_path),
            "ledger_db": str(ledger_db),
            "run_id": book["run_id"],
            "cc_job_id": book["cc_job_id"],
            "price_usd": book["price_usd"],
            "ceiling_usd": book["ceiling_usd"],
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "batch-manifest",
        "source": SOURCE,
        "batch_id": card["batch_id"],
        "card": card_fields(card),
        "card_digest": card_digest(card),
        "card_count": 1,
        "books": entries,
        "book_count": len(entries),
        "subtotal_usd": card["subtotal_usd"],
        "retake_allowance": RETAKE_ALLOWANCE,
        "price_usd": card["price_usd"],
        "currency": "USD",
        "written_at": _now(),
    }
    _write_json(manifest_path, manifest)

    # H3 step 2: the separate 12-stage parent board is SKIPPED -- the batch
    # id is recorded on each book's epic show_name ("Book N of M — title
    # (batch <id>)") and each cc-register.json instead. No second create.
    if check:
        from .isolation import assert_isolated   # lazy: isolation imports here
        assert_isolated(manifest)
    return manifest


def batch_path_display(path):
    return str(path)


__all__ = [
    "BATCH_CARD_KEYS",
    "BRIEF_FIELDS",
    "BRIEF_OPTIONAL",
    "BRIEF_REQUIRED",
    "CARD_FIELDS",
    "DEFAULT_LENGTH",
    "DEFAULT_SHAPE",
    "DEFAULT_VOICE",
    "DEFAULT_WORKSPACE",
    "LENGTH_VALUES",
    "RETAKE_ALLOWANCE",
    "SCHEMA_VERSION",
    "SHAPE_VALUES",
    "SOURCE",
    "STAGES",
    "TOOL_NAME",
    "TOOL_VERSION",
    "VOICE_LABELS",
    "VOICE_VALUES",
    "BatchError",
    "approve_batch",
    "card_digest",
    "card_fields",
    "card_lines",
    "make_card",
    "materialize",
    "normalize_brief",
    "price_batch",
    "set_books",
    "slugify",
]
