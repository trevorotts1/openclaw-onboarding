#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkout_wrapper.py - bridge between S49 dispatch and the order form (checkout) page's
wireframes and mockups.

The order form itself is the native Convert and Flow form installed by Skill 06 (CR-S49-003);
Skill 79 ships fixture models and component drafts but no command that builds a page. This
wrapper is the invocable command dispatch runs for the checkout role, and what it produces is
the DESIGN of that page: desktop and mobile wireframes and the visual mockups, through Skill 71's
own pipeline. Nothing here duplicates that pipeline:

  1. ADMIT   71-blackceo-signature-page/scripts/shared_page_service.py checks the page-request
             (page_role checkout, assigned skill 79, route graph and brand hashes), stages the
             run and records the intake (launch context, brand, design style A / B / C).
  2. BUILD   scripts/build_production_request.py --page-role checkout turns the approved
             checkout manuscript into one production request per stage: five sections (the role
             spec references/copy-specs/roles/checkout.json), the client's brand colours, the
             role's slots, grounds, composition roles and desktop / mobile layout.
  3. RUN     scripts/stage_executor.py runs desktop-wireframe, mobile-tablet and visual-mockup.
             On the paid provider it also composes the one long PDF per stage and the overview
             boards (stage_executor / combine_review_pdf.py / build_overview_board.py).
  4. RESULT  a page-result 1.0 whose artifacts are those design files, validated through
             collect_launch_receipts.validate_result before it is placed.

The manuscript is an input (--manuscript, "## Section N: name" headings), written by Skill 79's
emit_checkout_manuscript.py from the approved Skill 79 checkout request (--checkout-request): offer,
price display, bump, guarantee, terms and consent. A hand-written manuscript is refused: it must carry
`<!-- source_request_sha256: <sha256 of the --checkout-request file> -->` (CHK-13 source stamp), so the
copy provably comes from the request the money is bound to. The wrapper never writes copy, but it CHECKS
it (CHK-13): sections 2-4 must carry exactly the launch record's main price and bump name and price (in
the launch record's own currency and minor-unit exponent), and exactly the approved
guarantee, terms and consent text of the 83 intake's checkout_terms block (--checkout-terms FILE, or
checkout-terms.json beside the launch record); the block is required. A manuscript or produced
HTML that holds a card number, expiry or security-code FIELD (label, placeholder, input, cc-*
autocomplete) is refused (CHK-14), because the payment form is native only; reassurance prose
such as "we never store your credit card" is not a field and passes.

HONESTY CEILING: status authored, proof L0, native_bindings_ref null. The result names its
standing blockers: the form is still installed by Skill 06, the design board and final mockups
wait for the image chain and the client's board approval (design_board.py gate), and a stub run
carries placeholder images only. The default provider is stub (free); --provider kie needs
--allow-paid and the client's own KIE_API_KEY, exactly as stage_executor.py does.

Exit 0 result placed; 2 fail-closed refusal; 3 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from collect_launch_receipts import LEDGER_NAME, apply_review, validate_result  # noqa: E402
_OFFER_MAPPER = HERE.parents[1] / "shared-utils" / "signature_launch_contract" / "offer_mapper.py"
import page_set  # noqa: E402  the shared image inputs and the page's full deliverables list

EXIT_OK, EXIT_FAILCLOSED, EXIT_USAGE = 0, 2, 3
ROLE, SKILL = "checkout", 79
STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
DELIVERABLE_DIRS = (*STAGES, "review-pdfs")
TERMS_KEYS = ("guarantee_ref", "guarantee_text", "terms_ref", "terms_text", "consent_ref", "consent_text")
# CHK-14: a card FIELD is a label, placeholder, input or autocomplete token, never the prose word "credit card".
# Names are matched on the label squeezed of spaces, hyphens, underscores and dots.
_FIELD_NAME = re.compile(
    r"(?:credit|debit)?card(?:number|num|no|#|pan|holder(?:name)?|name|exp\w*|security(?:code)?|"
    r"verification\w*|cvc2?|cvv2?|csc)|cc(?:number|num|no|#|exp\w*|name|csc|cvc|cvv|type)|"
    r"(?:expiry|expiration|expires|exp)(?:date|month|year)?|mm/?y{2,4}|cvc2?|cvv2?|csc|cid|"
    r"securitycode|nameoncard|pan")
_ATTR_NAME = re.compile(r"card(?:number|no|num|holder|exp)|cc(?:number|num|exp|csc|cvc|cvv|name)|cvc|cvv|csc|"
                        r"securitycode|expir(?:y|ation)|expdate|nameoncard|mm/?y{2,4}")
_MMYY = re.compile(r"\bmm\s*[/\-]\s*yy(?:yy)?\b", re.I)
_ASK = re.compile(r"(?:^|[.!?]\s+)(?:please\s+)?(?:enter|type|provide|input|fill in|put in|key in)\b[^.!?]{0,40}?"
                  r"\b(?:card[\s_\-]*(?:number|no)|cvc|cvv|csc|security[\s_\-]*code|exp\w*[\s_\-]*date|expiry|mm/yy)",
                  re.I)
_PLACEHOLDER = re.compile(r"[\s_\u2022*xX#0-9\-\[\]()/.]*")
_CC_TOKEN = re.compile(r"(?<![\w-])cc-(?:name|given-name|additional-name|family-name|number|exp(?:-month|-year)?|csc|type)(?![\w-])", re.I)
BLOCKERS = (
    "the native checkout form is installed by Skill 06; this result carries the page's design "
    "stages only and no native binding",
    "the design board and final-mockups wait for the image chain and the client's recorded "
    "board approval (design_board.py gate)",
)
STUB_BLOCKER = "stub provider: the images are placeholders, not design deliverables"
# CHK-13 source stamp: the manuscript names the sha256 of the Skill 79 checkout request it was written from.
SOURCE_STAMP = re.compile(r"^<!--\s*source_request_sha256:\s*([0-9a-f]{64})\s*-->\s*$", re.M)
# Which currency a printed symbol can mean (data in schema/currency-symbols.json: a shared symbol never proves one code).
_SYMBOLS_FILE = HERE.parent / "schema" / "currency-symbols.json"
SYMBOL_CURRENCIES = {k: tuple(v) for k, v in json.loads(_SYMBOLS_FILE.read_text(encoding="utf-8")).items()
                     if not k.startswith("_")}


class WrapperError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd, what):
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        raise WrapperError(f"{what} exited {proc.returncode}: {' | '.join(tail)[:600]}")


def load(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WrapperError(f"{what}: cannot read {path}: {exc}")


def _squeeze(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s_.\-‐-―­​-‏⁠﻿]+", "", text)


def _is_field_label(text: str) -> bool:
    return bool(_FIELD_NAME.fullmatch(_squeeze(re.sub(r"[*`:()\[\]]|required|optional", "", text, flags=re.I))))


class _FieldParser(html.parser.HTMLParser):
    """Collects the card-field constructs of HTML: cc-* autocomplete tokens, inputs named or labelled as a
    card, expiry or security-code field, and any text node that is nothing but such a field name."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hits = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if any(t.startswith("cc-") for t in a.get("autocomplete", "").lower().split()):
            self.hits.append(f"autocomplete={a['autocomplete']!r}")
        if tag in ("input", "select", "textarea"):
            for key in ("name", "id", "placeholder", "aria-label", "title"):
                if _ATTR_NAME.search(_squeeze(a.get(key, ""))):
                    self.hits.append(f"{tag} {key}={a[key]!r}")

    def handle_data(self, data):
        if _is_field_label(data) or _MMYY.search(data):
            self.hits.append(data.strip())


def card_field_hits(text: str) -> list:
    """Card number / expiry / security-code field constructs in manuscript text or HTML (CHK-14); also what
    Skill 06's install path calls on the page it installs. Prose such as 'credit card' is not a field."""
    parser = _FieldParser()
    parser.feed(text)
    parser.close()
    hits = parser.hits + [m.group(0) for m in _CC_TOKEN.finditer(text)]
    lines = text.splitlines()
    paragraphs, block = [], []
    for raw in lines + [""]:  # markdown soft breaks: "Card\nnumber" is one label
        if not raw.strip() or raw.lstrip().startswith("#"):
            if len(block) > 1:
                paragraphs.append(" ".join(block))
            block = []
        else:
            block.append(raw.strip())
    for line in lines + paragraphs:
        line = re.sub(r"<[^>]*>", " ", unicodedata.normalize("NFKC", line)).strip()
        if _MMYY.search(line) or _ASK.search(line):
            hits.append(line)
            continue
        pieces = {line, *(g for m in re.findall(r"\[([^\]]*)\]|\(([^)]*)\)", line) for g in m if g)}
        label, _, rest = line.partition(":")
        if _PLACEHOLDER.fullmatch(rest):  # "Card number: ____" is a field; "Card number: we never..." is prose
            pieces.add(label)
        pieces.update(p for piece in list(pieces) for p in piece.split(":"))
        if any(_is_field_label(re.sub(r"^[\s>#*+\-\d.]+", "", p)) for p in pieces):
            hits.append(line)
    return hits


# legacy_downsell_images.py does `from checkout_wrapper import CARD_FIELDS` and calls CARD_FIELDS.search(text).group(0).
# Keep that export: the base word list, plus every CHK-14 field construct card_field_hits finds.
_LEGACY_CARD_WORDS = re.compile(r"card number|credit card|cvc|cvv|security code|expiry|expiration date", re.I)


class _CardFields:
    def search(self, text: str):
        hits = card_field_hits(text)
        return _LEGACY_CARD_WORDS.search(text) or (re.match(r"(?s).+", hits[0]) if hits else None)


CARD_FIELDS = _CardFields()


def scan_html(run_dir: Path) -> None:
    """Fail closed on a card field in any HTML the run produced (or Skill 06 installs from it)."""
    for p in sorted(Path(run_dir).rglob("*")):
        if p.is_file() and p.suffix.lower() in (".html", ".htm"):
            hits = card_field_hits(p.read_text(encoding="utf-8", errors="replace"))
            if hits:
                raise WrapperError(f"produced HTML {p} holds a card, expiry or security-code field; the payment "
                                   f"form is the native checkout form only ({hits[0]!r})")


def sections(text: str) -> dict:
    """The manuscript's '## Section N: name' bodies, by number."""
    parts = re.split(r"^##\s+Section\s+(\d+)\b[^\n]*\n", text, flags=re.M)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).replace("’", "'").replace(
        "“", '"').replace("”", '"')).strip()


def _offer_mapper():
    """The shared offer mapper (loaded once by path, stdlib only): the one door to Skill 78's currency
    exponent rule, so no currency fact is typed a second time here."""
    mod = sys.modules.get("offer_mapper")
    if mod is None:
        import importlib.util
        if not _OFFER_MAPPER.is_file():
            raise WrapperError("the shared offer mapper is not installed, so the checkout copy's money "
                               "cannot be read in the launch record's currency")
        spec = importlib.util.spec_from_file_location("offer_mapper", _OFFER_MAPPER)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["offer_mapper"] = mod
        spec.loader.exec_module(mod)
    return mod


def _marks(currency: str) -> list:
    """The strings that print this currency: its ISO code and every symbol that can mean it."""
    return sorted([currency, *(s for s, codes in SYMBOL_CURRENCIES.items() if currency in codes)],
                  key=len, reverse=True)


def _minor_amounts(text: str, currency: str, exponent: int) -> set:
    """Every amount the text prints in this currency, in minor units (CHK-13). Marks go before or after
    the number; the fraction must have exactly the currency's exponent digits, so '1,000' is a thousand."""
    whole = r"(\d{1,3}(?:[,.]\d{3})+|\d+)"
    frac = r"(?:[.,](\d{%d}))?" % exponent if exponent else ""
    mark = "(?:" + "|".join(re.escape(m) for m in _marks(currency)) + ")"
    out = set()
    for pattern in (rf"(?<![A-Za-z]){mark}\s?{whole}{frac}(?!\d)", rf"(?<![\d.,]){whole}{frac}\s?{mark}(?![A-Za-z])"):
        for found in re.finditer(pattern, text):
            digits, cents = found.group(1), found.group(2) if exponent else ""
            if exponent == 3 and "." in digits:
                # Three-decimal currencies: one '.' then exactly three digits is the decimal point (KWD 9.700 is
                # 9700 minor units), after any ',' groups; a '.'-grouped or ','-decimal number is ambiguous.
                if "." in re.findall(r"[,.]", digits)[:-1]:
                    raise WrapperError(f"the copy prints {digits!r} {currency}, which could be thousands grouped "
                                       "with a '.' or a decimal; reword the copy with ',' for thousands and one "
                                       "'.' before the three decimals (ambiguous European grouping)")
                digits, cents = digits.rsplit(".", 1)
            out.add(int(re.sub(r"[,.]", "", digits)) * 10 ** exponent + int(cents or 0))
    return out


def _foreign_marks(text: str, currency: str) -> list:
    """Currency symbols printed against a number that cannot mean the launch record's currency."""
    return sorted({s for s, codes in SYMBOL_CURRENCIES.items() if currency not in codes
                   and re.search(rf"{re.escape(s)}\s?\d|\d\s?{re.escape(s)}", text)})


def _record_amounts(offer: dict) -> set:
    out = set()
    for price in offer.get("prices") or []:
        for row in [price, *(price.get("schedule") or [])]:
            if isinstance(row, dict) and isinstance(row.get("amount_minor"), int):
                out.add(row["amount_minor"])
    return out


def request_offers(launch: dict, request: dict) -> list:
    refs = request.get("offer_refs")
    return [o for o in launch.get("offers") or [] if isinstance(o, dict) and (refs is None or o.get("offer_id") in refs)]


def check_copy(text: str, launch: dict, request: dict, terms: dict) -> None:
    """CHK-13: sections 2-4 carry exactly what the launch record and the approved checkout_terms say."""
    if not isinstance(terms, dict) or any(not isinstance(terms.get(k), str) or not terms[k].strip()
                                          for k in TERMS_KEYS):
        raise WrapperError("the approved checkout_terms block (guarantee, terms and consent: ref and verbatim "
                           f"text, {', '.join(TERMS_KEYS)}) is required; pass --checkout-terms FILE or stage "
                           "checkout-terms.json beside the launch record")
    body = sections(text)
    offers = request_offers(launch, request)
    mains = [o for o in offers if o.get("slot") == "main"]
    bumps = [o for o in offers if o.get("slot") == "bump"]
    # Section 3 is the order bump: required only when the launch has a bump offer. Without one, 1,2,4,5 is the
    # correct manuscript (an unused section 3 may stay, but it may not price anything: see names_and_prices).
    if not {1, 2, 4, 5} <= set(body) <= {1, 2, 3, 4, 5} or (bumps and 3 not in body):
        raise WrapperError("the manuscript needs the 5 canonical sections 1-5 (section 3, the order bump, only when "
                           f"the launch has a bump offer; this launch has {'one' if bumps else 'none'}), "
                           f"found {sorted(body)}")
    for o in mains + bumps:
        if not _record_amounts(o):
            raise WrapperError(f"offer {o.get('offer_id')!r} has no price in the launch record to check "
                               "the checkout copy against")
    # One cart, one currency: the launch record's own, never an assumed one. Its exponent is Skill 78's rule.
    currencies = sorted({p.get("currency") for o in mains + bumps for p in o.get("prices") or []},
                        key=str)
    if len(currencies) != 1 or not re.fullmatch(r"[A-Z]{3}", str(currencies[0])):
        raise WrapperError("the checkout copy is checked in the launch record's one currency, and the "
                           f"record's offers name {currencies!r}")
    currency = currencies[0]
    exponent = _offer_mapper().currency_exponent(currency)

    def names_and_prices(label, section, group):
        flat, found = _flat(section).lower(), _minor_amounts(section, currency, exponent)
        foreign = _foreign_marks(section, currency)
        if foreign:
            raise WrapperError(f"{label} prices in {foreign[0]!r}, but the currency must match the launch "
                               f"record's currency ({currency})")
        allowed = set().union(*(_record_amounts(o) for o in group)) if group else set()
        stray = sorted(found - allowed)
        if stray:
            raise WrapperError(f"{label} shows {currency} {stray[0] / 10 ** exponent:,.{exponent}f}, "
                               "which the launch record does not price")
        if group and not any(_flat(o.get("display_name", "")).lower() in flat and
                             found & {p["amount_minor"] for p in o["prices"] if isinstance(p.get("amount_minor"), int)}
                             for o in group):
            raise WrapperError(f"{label} must show an approved offer's name and price; the launch record has "
                               f"{[(o.get('display_name'), sorted(_record_amounts(o))) for o in group]}")

    names_and_prices("section 2 (price)", body[2], mains)
    names_and_prices("section 3 (order bump)", body.get(3, ""), bumps)
    left = _flat(body[4])
    for key in sorted(("guarantee_text", "terms_text", "consent_text"), key=lambda k: -len(terms[k])):
        want = _flat(terms[key])
        if want not in left:
            raise WrapperError(f"section 4 does not carry the approved {key.split('_')[0]} text exactly "
                               f"({terms[key.replace('_text', '_ref')]})")
        left = left.replace(want, " ", 1)
    left = re.sub(r"\[[A-Z][A-Z _-]*:[^\]]*\]", " ", left).strip()
    if left:
        raise WrapperError(f"section 4 carries copy that is not in the approved checkout_terms: {left[:80]!r}")


def check_source_stamp(text: str, request_path) -> None:
    """CHK-13 source stamp: the manuscript names the sha256 of the Skill 79 checkout request it was written
    from, and that is the staged request's sha. A hand-written, unstamped or differently-sourced manuscript
    is refused, so the copy cannot drift from the request the price is bound to."""
    if not request_path:
        raise WrapperError("the checkout copy must come from the Skill 79 checkout request: pass "
                           "--checkout-request (the request emit_checkout_manuscript.py wrote it from)")
    request = Path(request_path)
    if not request.is_file():
        raise WrapperError(f"--checkout-request {request} is not a file")
    stamps = SOURCE_STAMP.findall(text)
    if len(stamps) != 1:
        raise WrapperError("the manuscript carries no single `source_request_sha256` stamp; the checkout copy "
                           "is written by Skill 79's emit_checkout_manuscript.py, never by hand")
    if stamps[0] != sha256(request):
        raise WrapperError("the manuscript's source_request_sha256 is not the staged checkout request's sha256; "
                           "the copy was written from a different request than the one being designed")


def terms_block(args) -> dict:
    """The approved checkout_terms (the 83 intake's block; the closed launch-record schema cannot carry it):
    --checkout-terms FILE, else checkout-terms.json beside the launch record, as the adapter command stages
    design-prose-checkout.json. The file is the block or a document holding it as "checkout_terms"."""
    path = Path(args.checkout_terms) if args.checkout_terms else Path(args.launch).parent / "checkout-terms.json"
    if not path.is_file():
        return None  # check_copy refuses it by name
    doc = load(path, "checkout_terms")
    return doc.get("checkout_terms", doc) if isinstance(doc, dict) else None


def artifacts(run_dir: Path) -> list:
    """Every design file of the page (section images, PDFs, boards, stage records, visual bible)
    plus the production requests, sorted by path."""
    found = {a["path"]: a for a in page_set.design_artifacts("checkout", run_dir)}
    for s in STAGES:
        p = run_dir / f"production-request-{s}.json"
        found[str(p)] = {"path": str(p), "sha256": sha256(p)}
    for d in DELIVERABLE_DIRS:  # any other file a stage wrote into its own folder
        for p in (run_dir / d).rglob("*") if (run_dir / d).is_dir() else ():
            # Skill 71 stages every render under <stage>/.attempts/ before it promotes the file: staging
            # is never an artifact (a copy of each final image would double the section-image count).
            if p.is_file() and ".attempts" not in p.relative_to(run_dir).parts and str(p) not in found:
                found[str(p)] = {"path": str(p), "sha256": sha256(p)}
    return [found[k] for k in sorted(found)]


NO_BUMP_FLAG = "--no-bump"  # S71 build_production_request.py: drops checkout section 3 (r71b contract)


def produce(args, request) -> dict:
    if request.get("page_role") != ROLE or request.get("assigned_skill") != SKILL:
        raise WrapperError(f"the request is for page_role {request.get('page_role')!r}, skill "
                           f"{request.get('assigned_skill')!r}; this wrapper serves {ROLE!r}, skill {SKILL}")
    manuscript = Path(args.manuscript)
    text = manuscript.read_text(encoding="utf-8") if manuscript.is_file() else None
    if text is None:
        raise WrapperError(f"manuscript {manuscript} is missing; the checkout copy is written from the "
                           "approved references in the Skill 79 checkout request, never by this wrapper")
    hits = card_field_hits(text)
    if hits:
        raise WrapperError("the manuscript holds a card, expiry or security-code field; the payment form is "
                           f"the native checkout form only ({hits[0]!r})")
    check_source_stamp(text, args.checkout_request)
    launch = load(args.launch, "launch record")
    check_copy(text, launch, request, terms_block(args))
    has_order_bump = any(o.get("slot") == "bump" for o in request_offers(launch, request))
    s71 = Path(args.skill71_root) / "scripts"
    for name in ("shared_page_service.py", "build_production_request.py", "stage_executor.py"):
        if not (s71 / name).is_file():
            raise WrapperError(f"Skill 71 script {name} not found under {s71}")
    run_dir = Path(args.run_dir).resolve()
    admit = [sys.executable, s71 / "shared_page_service.py", "--request", args.request, "--run-dir", run_dir,
             "--page-version", "standard", "--brand-owner", args.brand_owner, "--image-cap", args.image_cap,
             "--brand-file", args.brand_file, "--launch-record", args.launch, "--route-graph", args.route_graph,
             "--validation-only"]  # admission seam only; the stages below generate
    if args.design_style:
        admit += ["--design-style", args.design_style]
    run(admit, "shared_page_service.py")
    page_set.stage_visual_bible(getattr(args, "inputs", None), run_dir)
    for stage in STAGES:
        name = f"production-request-{stage}.json"
        build = [sys.executable, s71 / "build_production_request.py", "--page-role", ROLE, "--manuscript",
                 manuscript, "--stage", stage, "--out", run_dir / name, "--run-dir", run_dir]
        for flag, value in (("--slots", args.slots), ("--design-prose", args.design_prose),
                            ("--model", args.model)):
            if value:
                build += [flag, value]
        # S71 keeps all five checkout sections unless told the launch has no order bump (no source sniffing:
        # a name mismatch must fail loudly in S71, not be skipped silently here).
        if not has_order_bump:
            build.append(NO_BUMP_FLAG)
        run(build, f"build_production_request.py ({stage})")
        execute = [sys.executable, s71 / "stage_executor.py", run_dir, "--stages", stage, "--request", name,
                   "--provider", args.provider] + (["--allow-paid"] if args.allow_paid else [])
        run(execute, f"stage_executor.py ({stage})")
    scan_html(run_dir)
    return {"artifacts": artifacts(run_dir),
            "blockers": list(BLOCKERS) + ([STUB_BLOCKER] if args.provider == "stub" else [])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for flag in ("request", "result", "manuscript", "launch", "route-graph", "run-dir"):
        ap.add_argument(f"--{flag}", required=True)
    for flag in ("brand-file", "brand-owner", "image-cap"):  # or one --image-inputs file
        ap.add_argument(f"--{flag}")
    ap.add_argument("--checkout-request", help="the Skill 79 checkout request JSON the manuscript was written "
                                               "from (its sha256 must equal the manuscript's source_request_sha256)")
    ap.add_argument("--checkout-terms", help="JSON with the approved guarantee, terms and consent text and refs "
                                             "(the 83 intake's checkout_terms block); default: "
                                             "checkout-terms.json beside --launch")
    ap.add_argument("--image-inputs", help="the shared image inputs file (design style, brand file, owner, "
                                           "image cap, provider); a flag typed here still wins")
    ap.add_argument("--skill71-root", default=str(HERE.parents[1] / "71-blackceo-signature-page"))
    ap.add_argument("--design-style", choices=("A", "B", "C"))
    ap.add_argument("--slots", help="slots.json overriding the role spec's default slots")
    ap.add_argument("--design-prose", help="the run's measured design system, as build_production_request.py reads it")
    ap.add_argument("--model", help="image model id (default: build_production_request.py's)")
    ap.add_argument("--provider", choices=("stub", "kie"), default="stub")
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--review", help="independent review record JSON; without an accepted one the result carries "
                                     "a REVIEW-PENDING blocker (reviewer must be in <request dir>/" + LEDGER_NAME + ")")
    ap.add_argument("--author-session", default=os.environ.get("SIGNATURE_LAUNCH_AUTHOR_SESSION")
                    or os.environ.get("OPENCLAW_SESSION_ID") or "s49-checkout-wrapper")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    result_path = Path(args.result)
    try:
        args.inputs = None
        if args.image_inputs:
            inputs = args.inputs = page_set.load_image_inputs(args.image_inputs)
            page_set.fill_args(args, inputs, {"brand_file": "brand_file", "brand_owner": "brand_owner",
                                              "image_cap": "image_cap", "design_style": "design_style",
                                              "design_prose_ref": "design_prose"})
            if args.provider == "stub" and inputs["image_provider"] == "kie":
                args.provider, args.allow_paid = "kie", inputs["allow_paid"]
        missing = [f for f in ("brand_file", "brand_owner", "image_cap") if args.__dict__.get(f) in (None, "")]
        if missing:
            raise WrapperError("missing " + ", ".join("--" + m.replace("_", "-") for m in missing)
                               + " (or pass --image-inputs)")
        args.image_cap = str(args.image_cap)
        request = load(args.request, "page-request")
        made = produce(args, request)
        result = {"schema_version": "1.0", **{k: request[k] for k in (
                      "tenant_id", "location_id", "launch_id", "revision", "request_id", "input_hash", "page_id")},
                  "status": "authored", "artifacts": made["artifacts"], "author_session": args.author_session,
                  "reviewer_session": None, "independent_review": False, "proof_class": "L0",
                  "blockers": made["blockers"], "native_bindings_ref": None, "test_only": request["test_only"]}
        accepted = apply_review(result, args.review, Path(args.request).resolve().parent / LEDGER_NAME)
        fails = validate_result(result, request, **(accepted or {}))
        if fails:
            raise WrapperError("page-result failed receipt validation: " + "; ".join(fails))
    except (WrapperError, page_set.PageSetError, OSError, KeyError) as exc:
        result_path.unlink(missing_ok=True)  # a failed run leaves no result to be mistaken for this run's
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return EXIT_FAILCLOSED
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"role": ROLE, "request_id": request["request_id"], "result_path": str(result_path),
                      "status": result["status"], "proof_class": result["proof_class"],
                      "artifacts": len(result["artifacts"]), "blockers": result["blockers"]}, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
