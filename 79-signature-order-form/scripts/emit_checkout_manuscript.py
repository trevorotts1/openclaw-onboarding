#!/usr/bin/env python3
"""emit_checkout_manuscript.py - the order form page's copy manuscript, produced from approved facts (issue 12).

The checkout page is the one page whose copy carries money, and its manuscript used to be written by hand with
Skill 49's CHK-13 as the only check. This emitter writes it from three inputs the checkout wrapper already uses,
and prints nothing that is not in them:

  --request          the approved Skill 79 checkout_request (price, billing, bump, terms and consent refs)
  --launch           the Skill 49 launch record (offer display names, deliverables, exclusions)
  --checkout-terms   the approved checkout_terms block (verbatim guarantee, terms and consent text and refs)

The request must pass this skill's own validator first (validate_checkout.validate_copy_request: the whole
production request check, which for a recommended price asks the shared verifier to confirm the plan approval,
except that the three Skill 06 read-back keys, which the copy never uses, are not required; the production gate,
validate_request, still requires them), so an unapproved request never
becomes copy. The manuscript has the five sections of Skill 71's role spec
(71-blackceo-signature-page/references/copy-specs/roles/checkout.json), headed "## Section N: name"; section 3
(the order bump) is present only when the request carries an enabled bump. Sections 2 and 3 carry the price lines,
section 4 carries exactly the three approved texts and nothing else (CHK-13), and section 5 carries the page's one
submit button. The only authored lines are that button and its microcopy.

THE STAMP. Line 1 is exactly

    <!-- source_request_sha256: <64 hex> -->

the sha256 of the raw bytes of the checkout_request file. verify_source_stamp(manuscript_text, request_path)
raises ManuscriptStampError (S79-MANUSCRIPT-STAMP-MISSING / S79-MANUSCRIPT-STAMP-MISMATCH) when the stamp is
absent or the request changed since; `--check` runs it from the shell. The checkout wrapper in Skill 49 computes
the same hash inline (it does not import this module) and refuses a manuscript whose stamp is missing or unequal.

Usage:
  emit_checkout_manuscript.py --request R.json --launch L.json --checkout-terms T.json --out copy-checkout.md
  emit_checkout_manuscript.py --check copy-checkout.md --request R.json
Exit: 0 written / stamp holds, 2 refused (fail closed, nothing written), 3 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validate_checkout import CheckoutValidationError, validate_copy_request  # noqa: E402

EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 2, 3
ROLE_SPEC = HERE.parents[1] / "71-blackceo-signature-page" / "references" / "copy-specs" / "roles" / "checkout.json"
STAMP_LINE = re.compile(r"\A<!-- source_request_sha256: ([0-9a-f]{64}) -->(?:\r?\n|\Z)")
TERMS_KEYS = ("guarantee_ref", "guarantee_text", "terms_ref", "terms_text", "consent_ref", "consent_text")
BUMP_SECTION = 3
# The page's one authored pair: the submit button and the line under it (the fixture manuscript's own wording).
CTA_BUTTON = "Complete my order"
CTA_MICROCOPY = "Your payment is processed securely. You will see a confirmation right away."


class ManuscriptError(ValueError):
    """A manuscript that cannot be written from the facts given. `code` is stable; nothing is written."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class ManuscriptStampError(ManuscriptError):
    """The manuscript's source stamp is absent or does not match the request file."""


def request_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_source_stamp(manuscript_text: str, request_path) -> str:
    """Return the stamp when line 1 is the exact stamp line and it equals the request file's sha256."""
    found = STAMP_LINE.match(manuscript_text)
    if not found:
        raise ManuscriptStampError(
            "S79-MANUSCRIPT-STAMP-MISSING",
            "line 1 is not '<!-- source_request_sha256: <64 hex sha256 of the checkout_request file> -->'")
    want = request_sha256(request_path)
    if not hmac.compare_digest(found.group(1).encode(), want.encode()):
        raise ManuscriptStampError(
            "S79-MANUSCRIPT-STAMP-MISMATCH",
            f"the manuscript was written from a checkout_request with sha256 {found.group(1)}, "
            f"not the staged one ({want}); emit it again from the staged request")
    return found.group(1)


def _blank(value) -> bool:
    return not (isinstance(value, str) and value.strip())


def _load(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManuscriptError("S79-MANUSCRIPT-INPUT", f"cannot read the {what} at {path}: {exc}") from exc


def _role_sections() -> dict:
    spec = _load(ROLE_SPEC, "Skill 71 checkout role spec")
    names = {int(s["id"]): s["name"] for s in spec.get("sections", [])}
    if sorted(names) != [1, 2, 3, 4, 5]:
        raise ManuscriptError("S79-MANUSCRIPT-ROLE-SPEC", f"the checkout role spec has sections {sorted(names)}, not 1 to 5")
    return names


def _money(amount_minor: int, currency: str, exponent: int) -> str:
    lead = "$" if currency == "USD" else f"{currency} "
    if exponent == 0:
        return f"{lead}{amount_minor:,}"
    whole, frac = divmod(amount_minor, 10 ** exponent)
    return f"{lead}{whole:,}.{frac:0{exponent}d}"


def _price_phrase(price: dict) -> str:
    """What the buyer pays, from the price choice alone. Never guesses an interval or a trial."""
    total = _money(price["amount_minor"], price["currency"], price["currency_exponent"])
    kind = price["billing_type"]
    if kind == "one_time":
        return f"one payment of {total}"
    interval = price.get("recurring_interval")
    if _blank(interval):
        raise ManuscriptError("S79-MANUSCRIPT-FACT-MISSING", "a recurring price names no recurring_interval")
    if kind == "recurring":
        return f"{total} on a recurring basis (billing interval: {interval})"
    trial = price.get("trial_period")
    if _blank(trial):
        raise ManuscriptError("S79-MANUSCRIPT-FACT-MISSING", "a trial price names no trial_period")
    return f"{total} on a recurring basis after your trial (billing interval: {interval}, trial period: {trial})"


def _schedule_and_due(price: dict) -> list:
    money = lambda n: _money(n, price["currency"], price["currency_exponent"])  # noqa: E731
    lines = [f"Payment {row['sequence']}, {row['due']}: {money(row['amount_minor'])}."
             for row in price.get("schedule") or []]
    due = price.get("amount_due_now_minor")
    if due is None and not price.get("schedule"):
        due = 0 if price["billing_type"] == "trial_then_recurring" else price["amount_minor"]
    if due:
        lines.append(f"Due today: {money(due)}.")
    elif due == 0:
        lines.append("Nothing is charged today.")
    return lines


def _offer(launch: dict, offer_id: str, what: str) -> dict:
    offer = next((o for o in launch.get("offers") or [] if isinstance(o, dict) and o.get("offer_id") == offer_id), None)
    if offer is None or _blank(offer.get("display_name")):
        raise ManuscriptError("S79-MANUSCRIPT-FACT-MISSING",
                              f"the launch record has no named {what} offer {offer_id!r}; copy never invents a name")
    return offer


# Skill 71's stage executor refuses a section whose copy ends without one of these (it reads that as cut
# off mid-sentence), so a line the launch record wrote without closing punctuation gets a full stop.
TERMINAL = (".", "!", "?", '"', "\u201d", "'", "\u2019", ")", "]", "\u2026")


def _closed(text: str) -> str:
    text = text.strip()
    return text if text.endswith(TERMINAL) else text + "."


def _bullets(items) -> list:
    return [f"- {_closed(i)}" for i in items if isinstance(i, str) and i.strip()]


def _section_one(request: dict, offer: dict, notes: list) -> list:
    name, price = offer["display_name"], request["main_price"]
    if request["checkout_mode"] == "post_selection":
        return [f"Your selected package: {name}.", f"Quantity: {request['quantity']}.",
                f"Billing schedule: {_price_phrase(price)}.", *_schedule_and_due(price), "Change package"]
    if not _bullets(offer.get("deliverables")):
        raise ManuscriptError("S79-MANUSCRIPT-FACT-MISSING",
                              f"offer {offer['offer_id']!r} lists no deliverables; what it includes is never invented")
    out = [f"{name}.", "What is included:", *_bullets(offer["deliverables"])]
    for label, key in (("Who it is for", "intended_buyer"), ("What you get", "primary_outcome")):
        if not _blank(offer.get(key)):
            out.append(f"{label}: {_closed(offer[key])}")
    if _bullets(offer.get("exclusions")):
        out += ["What is not included:", *_bullets(offer["exclusions"])]
    notes.append("access and delivery: the launch record holds no access or delivery text, so section 1 has none; "
                 "Skill 79 combined mode expects it before the copy is approved")
    return out


def _terms(request: dict, terms: dict) -> list:
    if not isinstance(terms, dict) or any(_blank(terms.get(k)) for k in TERMS_KEYS):
        raise ManuscriptError("S79-MANUSCRIPT-TERMS", f"the approved checkout_terms block needs non-blank {', '.join(TERMS_KEYS)}")
    for key in ("terms_ref", "consent_ref"):
        if terms[key] != request.get(key):
            raise ManuscriptError(
                "S79-MANUSCRIPT-TERMS",
                f"checkout_terms {key} {terms[key]!r} is not the request's {request.get(key)!r}; "
                "the text belongs to another approval")
    return [terms["guarantee_text"].strip(), terms["terms_text"].strip(), terms["consent_text"].strip()]


def emit(request_path, launch_path, terms_path, *, now: str | None = None) -> dict:
    """The manuscript text, its stamp, the section numbers it holds and notes on what the inputs could not supply."""
    request = _load(request_path, "checkout_request")
    launch = _load(launch_path, "launch record")
    terms_doc = _load(terms_path, "checkout_terms")
    terms = terms_doc.get("checkout_terms", terms_doc) if isinstance(terms_doc, dict) else None
    try:
        validate_copy_request(request, now=now or datetime.now(timezone.utc).isoformat())
    except CheckoutValidationError as exc:
        raise ManuscriptError("S79-MANUSCRIPT-REQUEST-INVALID", f"the checkout_request is not an approved request: {exc}") from exc
    names, notes = _role_sections(), []
    main = _offer(launch, request["main_offer_id"], "main")
    bump = request.get("bump")
    bump = bump if isinstance(bump, dict) and bump.get("enabled") else None
    blocks = {
        1: _section_one(request, main, notes),
        2: [f"{main['display_name']}, {_price_phrase(request['main_price'])}.", *_schedule_and_due(request["main_price"])],
        4: _terms(request, terms),
        5: ["Enter your details below to complete your order.", f"[CTA BUTTON: {CTA_BUTTON}]",
            f"[CTA MICROCOPY: {CTA_MICROCOPY}]"],
    }
    if bump:
        bump_offer = _offer(launch, bump["offer_id"], "bump")
        if any(_blank(bump.get(k)) for k in ("headline", "benefit_explanation")):
            raise ManuscriptError("S79-MANUSCRIPT-FACT-MISSING", "the request's bump has no headline or benefit_explanation")
        blocks[BUMP_SECTION] = [f"Yes, add the {bump_offer['display_name']} to my order.", bump["headline"].strip(),
                                bump["benefit_explanation"].strip(), f"Price: {_price_phrase(bump['price'])}.",
                                *_schedule_and_due(bump["price"])]
    stamp = request_sha256(request_path)
    lines = [f"<!-- source_request_sha256: {stamp} -->", "# Order form page", ""]
    for number in sorted(blocks):
        lines += [f"## Section {number}: {names[number]}", ""]
        for block in blocks[number]:
            if not block.startswith("- ") and lines[-1].startswith("- "):
                lines.append("")  # a bullet run ends with a blank line
            lines.append(block)
            if not block.startswith("- "):
                lines.append("")
        if lines[-1] != "":
            lines.append("")
    text = "\n".join(lines).rstrip("\n") + "\n"
    verify_source_stamp(text, request_path)  # what was written is what the wrapper will read back
    return {"text": text, "source_request_sha256": stamp, "sections": sorted(blocks), "notes": notes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--request", required=True)
    ap.add_argument("--launch")
    ap.add_argument("--checkout-terms")
    ap.add_argument("--out")
    ap.add_argument("--check", metavar="MANUSCRIPT", help="verify MANUSCRIPT's source stamp against --request and stop")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    try:
        if args.check:
            stamp = verify_source_stamp(Path(args.check).read_text(encoding="utf-8"), args.request)
            print(json.dumps({"manuscript": args.check, "source_request_sha256": stamp, "stamp": "holds"}, indent=2))
            return EXIT_OK
        if not (args.launch and args.checkout_terms and args.out):
            ap.error("--launch, --checkout-terms and --out are required to write a manuscript")
        made = emit(args.request, args.launch, args.checkout_terms)
    except SystemExit:
        return EXIT_USAGE
    except (ManuscriptError, OSError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(made["text"], encoding="utf-8")
    print(json.dumps({"manuscript": str(out), "source_request_sha256": made["source_request_sha256"],
                      "sections": made["sections"], "notes": made["notes"]}, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
