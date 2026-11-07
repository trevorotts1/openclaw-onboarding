"""Product delivery: what a buyer actually receives, produced and bound.

F08's delivery half. A catalog record is not a product, a produced file is not a
delivered link, and a human follow-up is not a download. This module keeps those
three facts apart instead of collapsing them into one "delivered" flag:

  * it PRODUCES the one artifact this run can genuinely write — each offer's
    delivery sheet, built only from the approved offer facts (name, level,
    deliverables, exclusions, price, the access destination) — and hashes it;
  * it CLASSIFIES the rest honestly: a promise the run cannot manufacture is
    recorded as ``not_produced`` with the exact missing capability, never as a
    placeholder file;
  * it BINDS the result into the launch record's ``delivery_bindings`` (schema
    1.2, keyed by entitlement id) so Skill 82's thank-you page and Skill 44's
    fulfillment map read the same entry.

The delivery KIND comes from the client's own answer, never from a guess:

  answers.access_delivery == "Yes, send access after purchase"
      -> ``access``; the answered ``access_url`` IS the buyer-facing destination,
         so it must be https: a non-https one is refused, never downgraded. With
         no answered address, the owner-confirmed per-offer destination is the
         fallback.
  answers.access_delivery == "No, nothing to deliver"
      -> ``schedule_included_service``; the question's own guidance says this is
         "a service where a person follows up by hand". Nobody is sent to
         ``access_url`` on this path, so it is neither used nor validated: the
         owner-confirmed per-offer destination is carried (a booking page is a
         legitimate destination) and absence of one is recorded, not invented.
  no answer
      -> the pre-existing behaviour, byte for byte: ``access`` plus the
         owner-confirmed per-offer destination. ``access_url`` is not consulted.

``download`` is deliberately unreachable here. It is the launch schema's kind for
a buyer-facing file, and a file only becomes a delivery when hosting returns a
real https URL. Producing bytes and calling them a delivery would be the exact
substitution this module exists to prevent; ``record()`` names hosting as the
missing capability instead.

The DELIVERY MODE is a second, separate fact, recorded per offer exactly as the
run's own evidence proves it: a ``generated_file`` (bytes this run wrote, with
their digest), a ``human_delivered_service`` (the client answered "No, nothing
to deliver" — a person follows up by hand), a ``future_session`` (a session at a
recorded later time), or an ``unfinished_course`` (promised content no producer
in this repository writes). A service is never described as a file that failed
to generate, a future session is never guessed from a service, and nothing is
called produced because a catalog record or a description sheet exists. No
question in the bank asks for a session date, so ``future_session`` is named in
the record's ``unrecorded_modes`` and never selected: the missing fact is
stated instead of filled with a guess.

Stdlib only. Deterministic: the same facts produce the same bytes and digest.
"""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit

from . import route as route_module

# The launch schema 1.2 binding enum (never a wider vocabulary).
DELIVERY_KINDS = ("access", "download", "schedule_included_service")
KIND_ACCESS = "access"
KIND_DOWNLOAD = "download"
KIND_SCHEDULE = "schedule_included_service"

# What happened to one promise. ``produced`` means bytes exist in this run and
# their digest is recorded; nothing else is ever called produced.
PROMISE_PRODUCED = "produced"
PROMISE_NOT_PRODUCED = "not_produced"

# How an offer's promised item is delivered. Four different facts that a single
# "delivered" flag would collapse into a lie.
MODE_FILE = "generated_file"
MODE_SERVICE = "human_delivered_service"
MODE_UNWRITTEN = "unfinished_course"

# The one mode this intake cannot record: no question asks for a session date or
# a booking time, so a call that happens later is indistinguishable from a
# service a person arranges by hand. Recorded by name, never guessed.
UNRECORDED_SESSION = (
    "the intake records no session date, start time or booking reference, so a "
    "future session cannot be told apart from a service a person delivers by "
    "hand; it is never selected by guesswork")

# The client's own two answers (shared-utils/client_intake/question-bank.json,
# question ``access_delivery``), verbatim.
ANSWER_SEND_ACCESS = "Yes, send access after purchase"
ANSWER_NOTHING = "No, nothing to deliver"

RECORD_REL = "product-delivery.json"
SHEETS_DIR = "deliverables"
RECORD_TYPE = "launcher.delivery.v1"

# Recorded on every offer whose deliverable is not a file this run can make.
MISSING_AUTHORING_PRODUCER = (
    "no producer in this repository writes the promised item itself (a course module, "
    "video lesson, live call or template pack); the delivery sheet lists the promise and "
    "the access path, and the item stays not_produced")
MISSING_HOSTING = (
    "no hosting producer is bound to this run, so the produced file has no https address "
    "and the launch binding carries the kind with a null delivery_url")


class DeliveryError(Exception):
    """A delivery plan that cannot be built. Carries a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _https(url: Any) -> bool:
    parts = urlsplit(url) if isinstance(url, str) else None
    return bool(parts and parts.scheme == "https" and parts.hostname
                and not parts.username and not parts.password
                and not any(c.isspace() for c in url))


def _answer(doc: Optional[Mapping[str, Any]], key: str) -> Any:
    """The client's answer value for ``key``, or None when unanswered/unknown."""
    if not isinstance(doc, Mapping):
        return None
    answers = doc.get("answers")
    if not isinstance(answers, Mapping):
        return None
    entry = answers.get(key)
    if not isinstance(entry, Mapping):
        return None
    if entry.get("status") in ("unknown", None):
        return None
    return entry.get("value")


def load_answers(normalized: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The answers file this intake was validated against, or None when unreadable.

    ``intake.validate`` already proved the file parses and carries the schema, so a
    failure here is a missing file rather than a malformed one; the caller keeps the
    pre-existing per-offer behaviour instead of inventing an answer.
    """
    path = normalized.get("answers_file")
    if not _nonempty(path):
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def decide(normalized: Mapping[str, Any], answers: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The launch-wide delivery decision the client's answers carry.

    Returns {"kind", "url", "state", "source", "unused_access_url"}. ``kind`` is
    one of DELIVERY_KINDS; ``url`` is an https address or None (kind bound, no
    destination recorded yet). ``state`` is "answered" only when the client really
    answered, so a caller can tell a decision from the pre-existing default.

    The answered ``access_url`` is validated ONLY where it becomes the buyer's
    link: the "send access after purchase" branch. The question bank asks it only
    for that answer (its condition is ``access_delivery == yes``), so an answer
    left behind on a service run, or on the no-answer default, is not a delivery
    destination and must never abort a build that does not use it. Such a value is
    returned as ``unused_access_url`` so the record can say it was seen and not
    used, instead of silently dropped.
    """
    answers = load_answers(normalized) if answers is None else answers
    choice = _answer(answers, "access_delivery")
    raw = _answer(answers, "access_url")
    url = raw.strip() if _nonempty(raw) else None
    if choice == ANSWER_SEND_ACCESS:
        if url is not None and not _https(url):
            raise DeliveryError(
                "AF-LAUNCH-DELIVERY-URL",
                f"the answered access_url {url!r} is not an https address; a buyer-facing "
                "destination is never guessed and never plain http")
        return {"kind": KIND_ACCESS, "url": url, "state": "answered",
                "source": "answers:access_delivery", "unused_access_url": None}
    if choice == ANSWER_NOTHING:
        # A human-delivered service has no buyer-facing link. The bank asks
        # access_url only for "send access after purchase", so a value here is
        # leftover: it is recorded as unused, never used as the buyer's destination,
        # and never fatal. The owner-confirmed per-offer destination stands.
        return {"kind": KIND_SCHEDULE, "url": None, "state": "answered",
                "source": "answers:access_delivery", "unused_access_url": url}
    if choice is not None:
        raise DeliveryError(
            "AF-LAUNCH-DELIVERY-ANSWER",
            f"access_delivery {choice!r} is not one of the two recorded choices "
            f"({ANSWER_SEND_ACCESS!r}, {ANSWER_NOTHING!r})")
    return {"kind": KIND_ACCESS, "url": None, "state": "absent",
            "source": "offer.delivery (owner-confirmed destination)",
            "unused_access_url": url}


def _promises(offer: Mapping[str, Any]) -> List[str]:
    """The offer's promised items, from its supplied level then its canonical entry."""
    level = offer.get("level") or {}
    if isinstance(level, Mapping) and level.get("state") == "supplied":
        items = level.get("deliverables")
        if isinstance(items, list) and items:
            return [str(i) for i in items]
    canon = offer.get("canonical") or {}
    items = canon.get("deliverables") if isinstance(canon, Mapping) else None
    return [str(i) for i in items] if isinstance(items, list) else []


def plan(normalized: Mapping[str, Any], answers: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """One entry per offer: its kind, its destination, and its promises.

    A per-offer destination is used when the client's answer names none, which is
    exactly the record the bridge has always produced.
    """
    decision = decide(normalized, answers)
    grants = route_module.offer_entitlements(normalized)
    offers: List[Dict[str, Any]] = []
    for offer in normalized["offers"]:
        own = offer.get("delivery") or {}
        destination = own.get("destination") if isinstance(own, Mapping) else None
        url = decision["url"] or (destination if _nonempty(destination) else None)
        if url is not None and not _https(url):
            raise DeliveryError(
                "AF-LAUNCH-DELIVERY-URL",
                f"offer {offer['offer_id']!r} delivery destination {url!r} is not https")
        offers.append({
            "offer_id": offer["offer_id"],
            "role": offer["role"],
            "name": offer["name"],
            "entitlement_ids": list(grants[offer["offer_id"]]),
            "delivery_kind": decision["kind"],
            "delivery_url": url,
            "human_service": decision["kind"] == KIND_SCHEDULE,
            "promises": _promises(offer),
            "price": dict(offer["price"]),
            "exclusions": list((offer.get("canonical") or {}).get("exclusions") or []),
        })
    return {"kind": decision["kind"], "kind_state": decision["state"],
            "kind_source": decision["source"], "offers": offers,
            "unused_access_url": decision["unused_access_url"]}


def _money(price: Mapping[str, Any]) -> str:
    """The approved price as a buyer reads it, using the repo's ONE exponent helper.

    A currency this checkout cannot place is shown as its recorded amount and code,
    never rounded or guessed into a different number.
    """
    amount, currency = price["amount_minor"], str(price["currency"])
    try:
        from .checkout import currency_exponent
        exponent = currency_exponent(currency)
    except Exception:  # noqa: BLE001 — an unplaceable currency is shown verbatim, not guessed
        return f"{amount} {currency}"
    if not isinstance(exponent, int) or exponent < 0 or exponent > 4:
        return f"{amount} {currency}"
    whole, frac = divmod(amount, 10 ** exponent)
    if exponent == 0:
        return f"{whole} {currency}"
    return f"{whole}.{frac:0{exponent}d} {currency}"


def _render(entry: Mapping[str, Any], launch: Mapping[str, Any]) -> str:
    """One offer's delivery sheet: only the approved facts, escaped, deterministic."""
    e = html.escape
    rows = "\n".join(f"      <li>{e(p)}</li>" for p in entry["promises"])
    promises = rows or '      <li>No item was listed for this offer.</li>'
    exclusions = "\n".join(f"      <li>{e(x)}</li>" for x in entry["exclusions"])
    excludes_block = f"\n    <h2>Not included</h2>\n    <ul>\n{exclusions}\n    </ul>" if exclusions else ""
    url = entry["delivery_url"]
    if entry["human_service"]:
        where = (f"You will be contacted at {e(url)} to arrange it."
                 if url else "Someone will contact you to arrange it.")
        heading = "What happens next"
    elif url:
        where = f'Reach it here: <a href="{e(url)}">{e(url)}</a>.'
        heading = "How to get it"
    else:
        where = "The access address is not recorded yet."
        heading = "How to get it"
    price = entry["price"]
    return (
        "<!doctype html>\n"
        f'<html lang="{e(str(launch.get("locale") or "en"))}"><head><meta charset="utf-8">'
        f"<title>{e(entry['name'])}</title></head>\n<body>\n"
        f"  <h1>{e(entry['name'])}</h1>\n"
        f"  <p>This is what you receive, and how you receive it.</p>\n"
        f"  <h2>What you get</h2>\n    <ul>\n{promises}\n    </ul>{excludes_block}\n"
        f"  <h2>{e(heading)}</h2>\n    <p>{where}</p>\n"
        f"  <h2>What it costs</h2>\n"
        f"    <p>{e(_money(price))}, one payment.</p>\n"
        "</body></html>\n"
    )


def produce(planned: Mapping[str, Any], out_dir: Path,
            launch: Optional[Mapping[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """Write one delivery sheet per offer into ``out_dir/deliverables``.

    Each file is read back and hashed, so the recorded digest is the file's own
    bytes. A collision with different content refuses rather than overwrites.
    """
    out_dir = Path(out_dir)
    launch = launch or {}
    written: Dict[str, Dict[str, Any]] = {}
    for entry in planned["offers"]:
        data = _render(entry, launch).encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        rel = Path(SHEETS_DIR) / f"{entry['offer_id']}.html"
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise DeliveryError(
                "AF-LAUNCH-DELIVERY-COLLISION",
                f"two different delivery sheets would be written as {str(rel)!r}")
        target.write_bytes(data)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            raise DeliveryError("AF-LAUNCH-DELIVERY-HASH",
                                f"the written sheet {str(rel)!r} did not verify")
        written[entry["offer_id"]] = {"path": str(rel), "sha256": digest,
                                      "size": target.stat().st_size}
    return written


def bindings(planned: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """entitlement id -> {delivery_kind, delivery_url} for the launch record.

    Every entitlement this launch grants is bound, including the ones a bigger
    level's buyers hold by inclusion, so Skill 44's fulfillment map never finds a
    granted entitlement with no entry. A binding comes from the offer that OWNS the
    entitlement, never from an offer that merely grants it by inclusion: a level's
    buyers hold the bump's entitlement, but the bump's own destination is where that
    item lives. Ownership is the offer whose id is the entitlement (lowercased):
    ``route.offer_entitlements`` mints every id that way, so an id no offer owns is a
    caller defect and is refused rather than bound to whichever offer listed it.
    """
    owner = {entry["offer_id"].lower(): entry for entry in planned["offers"]}
    granted = sorted({entitlement_id for entry in planned["offers"]
                      for entitlement_id in entry["entitlement_ids"]})
    out: Dict[str, Dict[str, Any]] = {}
    for entitlement_id in granted:
        entry = owner.get(entitlement_id)
        if entry is None:
            raise DeliveryError(
                "AF-LAUNCH-DELIVERY-OWNER",
                f"entitlement {entitlement_id!r} is granted by this launch but no offer owns it")
        out[entitlement_id] = {"delivery_kind": entry["delivery_kind"],
                               "delivery_url": entry["delivery_url"]}
    return out


def _mode(entry: Mapping[str, Any], item_artifact: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """The one delivery mode this offer's recorded facts prove, and the fact it rests on.

    ``future_session`` is never returned: see ``UNRECORDED_SESSION``. A human service
    is never reported as an unwritten file, and an unwritten item is never reported
    as a service, so neither fact is substituted for the other.
    """
    if item_artifact:
        return {"mode": MODE_FILE, "basis": "artifact: bytes produced in this run"}
    if entry["human_service"]:
        return {"mode": MODE_SERVICE,
                "basis": "answers:access_delivery = 'No, nothing to deliver'"}
    return {"mode": MODE_UNWRITTEN, "basis": MISSING_AUTHORING_PRODUCER}


def record(planned: Mapping[str, Any], produced: Mapping[str, Any],
           launch: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The honest production record: what exists, what does not, and why.

    A promise is ``produced`` only when this run wrote bytes for it; every other
    promise carries the exact missing capability. A human-delivered service is
    recorded as that offer's ``delivery_mode`` and ``mode_basis``, never as a
    produced promise: this run hands over no bytes, so the promise stays
    ``not_produced`` with its capability named. The one file this run writes per
    offer (its delivery sheet) is recorded once, as that offer's ``sheet``, so the
    record, the dispatch report and the free-entry block all name the same path and
    digest and a sheet can never be read as the product.
    """
    launch = launch or {}
    offers: List[Dict[str, Any]] = []
    for entry in planned["offers"]:
        sheet = produced.get(entry["offer_id"])
        if sheet is None:
            raise DeliveryError("AF-LAUNCH-DELIVERY-SHEET",
                                f"offer {entry['offer_id']!r} has no produced delivery sheet")
        mode = _mode(entry, sheet.get("item"))
        if mode["mode"] == MODE_FILE:
            promises = [{"item": item, "state": PROMISE_PRODUCED,
                         "artifact": dict(sheet["item"])} for item in entry["promises"]]
            missing: List[str] = []
        else:
            promises = [{"item": item, "state": PROMISE_NOT_PRODUCED,
                         "missing_capability": MISSING_AUTHORING_PRODUCER}
                        for item in entry["promises"]]
            missing = [MISSING_AUTHORING_PRODUCER]
        if entry["delivery_url"] is None and entry["delivery_kind"] != KIND_SCHEDULE:
            missing.append(MISSING_HOSTING)
        offers.append({
            "offer_id": entry["offer_id"],
            "role": entry["role"],
            "entitlement_ids": entry["entitlement_ids"],
            "delivery_kind": entry["delivery_kind"],
            "delivery_url": entry["delivery_url"],
            "human_service": entry["human_service"],
            "delivery_mode": mode["mode"],
            "mode_basis": mode["basis"],
            # ONE reference for the file this run wrote for this offer, under the name
            # the record has always used: a sheet, never the product itself.
            "sheet": {"path": sheet["path"], "sha256": sheet["sha256"],
                      "size": sheet["size"], "content": "delivery_sheet"},
            "promises": promises,
            # ponytail: no producer in this tree writes a promised item's own content (a
            # course module, video lesson, live call or template pack). When one lands,
            # ``produce`` returns its bytes as ``sheet["item"]`` and this record flips
            # that offer to MODE_FILE without a second edit.
            "missing_capability": missing,
            "native_product_id_state": "unknown",
        })
    return {
        "record_type": RECORD_TYPE,
        "launch_id": launch.get("launch_id"),
        "tenant_id": launch.get("tenant_id"),
        "location_id": launch.get("location_id"),
        "kind": planned["kind"],
        "kind_state": planned["kind_state"],
        "kind_source": planned["kind_source"],
        "unused_access_url": planned.get("unused_access_url"),
        "unrecorded_modes": {"future_session": UNRECORDED_SESSION},
        "offers": offers,
        "free_entry": _free_entry(planned, produced),
    }


FREE_ENTRY_ROLES = ("free", "free_lead", "lead_magnet")


def _free_entry(planned: Mapping[str, Any], produced: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The separate free lead product, if the offer model carries one.

    A free entry is an offer whose recorded price is zero, or whose role names the
    free lane. This release's launcher roles are main/bump/upsell_1/downsell_1/
    upsell_2 (constants.OFFER_ROLES) and intake.py refuses a price of zero, so none
    can reach here yet — that is recorded by name rather than filled with a
    stand-in offer. When the offer model gains the role, this reads it without a
    second edit.
    """
    produced = produced or {}
    for entry in planned["offers"]:
        price = entry.get("price") or {}
        is_free = (entry.get("role") in FREE_ENTRY_ROLES
                   or price.get("amount_minor") == 0)
        if not is_free:
            continue
        sheet = produced.get(entry["offer_id"])
        mode = _mode(entry, (sheet or {}).get("item"))
        return {
            "state": "declared" if sheet else "declared_not_produced",
            "offer_id": entry["offer_id"],
            "role": entry["role"],
            "entitlement_ids": list(entry["entitlement_ids"]),
            "delivery_kind": entry["delivery_kind"],
            "delivery_url": entry["delivery_url"],
            "delivery_mode": mode["mode"],
            "mode_basis": mode["basis"],
            "sheet": ({k: sheet[k] for k in ("path", "sha256", "size")} if sheet else None),
            "promises": list(entry["promises"]),
            "missing_capability": [] if sheet else [MISSING_AUTHORING_PRODUCER],
            # The launch record's ``free_entry.delivery_ref`` (launch schema 1.2, BFL-001) is
            # the field this sheet belongs in. It is emitted by the record producer, not
            # here: this module writes the file and its digest, and the launch record owns
            # where its own field points.
        }
    return {
        "state": "absent",
        "missing_capability": (
            "the launcher offer model has no free-entry role (constants.OFFER_ROLES) and "
            "launcher_core/intake.py refuses a price of zero (it also refuses journey_mode "
            "'free_entry' as not implemented), and shared-utils/client_intake/launcher_intake.py "
            "refuses a free price at _price ('a free or unpriced offer cannot be built'), so no "
            "free lead product can be declared, produced or bound in this build; the free-entry "
            "record is the offer model's half (F08, W05)"),
    }


def write_record(record_doc: Mapping[str, Any], out_dir: Path) -> Path:
    """Write ``product-delivery.json`` into the run and return its path.

    Named apart from ``graphics_hooks''s ``delivery_record.json`` (SOP-GIP-03, the
    image hosting record): one is what the buyer receives, the other is which
    pictures passed QC and where they are hosted.
    """
    path = Path(out_dir) / RECORD_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run(normalized: Mapping[str, Any], out_dir: Path,
        launch: Optional[Mapping[str, Any]] = None,
        answers: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """plan -> produce -> bind -> record, writing into ``out_dir``.

    Returns {"plan", "produced", "bindings", "record", "record_path"}. The caller
    puts ``bindings`` into the launch record and the record path into its report.
    The presentation locale is the intake's (it is not a launch-record field).
    """
    planned = plan(normalized, answers)
    produced = produce(planned, out_dir, {**(launch or {}),
                                          "locale": normalized.get("locale") or "en"})
    doc = record(planned, produced, launch)
    path = write_record(doc, out_dir)
    return {"plan": planned, "produced": produced, "bindings": bindings(planned),
            "record": doc, "record_path": str(path)}
