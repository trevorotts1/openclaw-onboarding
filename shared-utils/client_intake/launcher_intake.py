#!/usr/bin/env python3
"""Skill 83 launcher intake, built from the one answers file (the answers are the price authority).

The interview already records the offers, prices, levels and the funnel shape in the answers file
(client-intake-answers/v1). This module turns that file into the intake Skill 83 validates, so the agent
never types offers or prices itself, and binds the result to the answers by hash:

  to_launcher_intake(doc, system)  -> {"intake", "provenance"}
        intake       what launcher_core.intake.validate takes: journey_mode, offers (price, level, role),
                     copy_profile, image_plan, plus the system fields the answers cannot carry
        provenance   answers hash, intake hash, and for every offer its answers-file question id as
                     source_ref, the client's visual direction, the promotion limits, warnings
  verify(intake, provenance, answers_doc/path)   refuses an intake with no provenance, one whose answers
                     hash differs, one edited after it was built, or whose offers or prices no longer
                     match the answers
  creative_direction(doc)          the client's visual direction (explicit house look, or a named one)
  write_intake_args(doc)           ["--creative-direction", value] for Skill 71's write_intake, or []
  image_ceiling(doc)               pictures the chosen page set needs (Skill 49's own image_estimate)

Only a "provided" answer becomes a commercial fact: a suggested or defaulted price, offer or direction is
refused by name, never passed on. Provenance lives beside the intake (intake.provenance.json) because
launcher_core.intake refuses undeclared fields, so a source_ref cannot ride inside an offer.

CLI:
  launcher_intake.py build ANSWERS --system SYSTEM.json --out DIR      DIR/intake.json + intake.provenance.json
  launcher_intake.py verify --answers ANSWERS --intake FILE [--provenance FILE]
  launcher_intake.py dispatch --answers ANSWERS --intake FILE [--provenance FILE] <83 dispatch flags>
        refuses unless the intake is bound to ANSWERS, then runs Skill 83's own dispatch
  launcher_intake.py write-intake-args ANSWERS                         the --creative-direction flag, as JSON
Exit 0 ok, 2 refused. stdlib only; reads no secret.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

PROVENANCE_NAME = "intake.provenance.json"
PROVENANCE_SCHEMA = "launcher-intake-provenance/v1"
SECRET_SAUCE_ONLY = "SECRET_SAUCE_ONLY"  # Skill 71's selection_mode when no direction is named
JOURNEY_MODES = ("single_simple", "multiple_options", "folded_levels")
EXTRA_SLOTS = (("bump", "BUMP", "bump"), ("upsell_1", "U1", "upsell_1"),
               ("downsell_1", "D1", "downsell_1"), ("upsell_2", "U2", "upsell_2"))
_UNAPPROVED = ("suggested", "default_to_confirm")
IMAGE_PROVIDERS = ("kie", "agnes", "other_explicit")  # the launch record's image_provider vocabulary
TERMS_FIELDS = ("guarantee_ref", "guarantee_text", "terms_ref", "terms_text", "consent_ref", "consent_text")
ANSWER_BUILT_ROOTS = ("journey_mode", "offers", "copy_profile", "checkout_terms", "answers_file", "image_plan")
OFFER_ANSWER_FIELDS = ("offer_id", "name", "role", "price", "level")
IMAGES_PER_SECTION = 4  # Skill 49 page_set.image_estimate: desktop + mobile wireframe and mockup


class AnswersError(Exception):
    """An answers file that cannot become a launcher intake. Carries a stable code and plain English."""

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(f"{code}: {field}: {detail}")
        self.code, self.field, self.detail = code, field, detail


def _fail(code: str, field: str, detail: str) -> None:
    raise AnswersError(code, field, detail)


# ---------------------------------------------------------------- the hash that binds intake to answers
def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def intake_hash(intake: Dict[str, Any]) -> str:
    return hashlib.sha256(_canon(intake)).hexdigest()


def answers_hash(doc: Dict[str, Any]) -> str:
    """sha256 of the answers as canonical JSON (the derived to_confirm list excluded)."""
    return hashlib.sha256(_canon({k: v for k, v in doc.items() if k != "to_confirm"})).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()  # the same value Skill 71 records


# ---------------------------------------------------------------- reading answers
def _entry(doc: Dict[str, Any], qid: str) -> Optional[Dict[str, Any]]:
    e = (doc.get("answers") or {}).get(qid)
    return e if isinstance(e, dict) else None


def _provided(doc: Dict[str, Any], qid: str) -> Any:
    """The value of a client-confirmed answer. Missing, unknown, suggested or defaulted answers refuse by name."""
    e = _entry(doc, qid)
    if e is None or e.get("status") == "unknown" or e.get("value") is None:
        _fail("AF-LAUNCH-ANSWERS-MISSING", f"answers-file:{qid}",
              "not answered yet; the intake is built only from answers the client gave")
    if e.get("status") in _UNAPPROVED:
        _fail("AF-LAUNCH-ANSWERS-UNAPPROVED", f"answers-file:{qid}",
              f"is {e['status']}, a proposal the client has not confirmed; ask the client to confirm it")
    return e["value"]


def _engine():
    """The shared engine beside this file: it owns the canonical answer contract, so the two
    modules cannot drift into two different definitions of a decision, a brand or a spend cap."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import engine  # noqa: PLC0415 - same package, imported lazily to keep module load cheap
    return engine


def _spend(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The approved monetary ceiling (cap_minor + ISO currency) and the approval it binds."""
    return _engine().spend_contract(doc)


def _answer_contract(doc: Dict[str, Any], system: Dict[str, Any]) -> Dict[str, Any]:
    """The F16 block: design decision, brand provenance, spend ceiling, plan binding."""
    return _engine().answer_contract(doc, brand_file=system.get("brand_file"))


def _price(value: Any, field: str) -> Dict[str, Any]:
    ok = (isinstance(value, dict) and isinstance(value.get("amount_minor"), int)
          and not isinstance(value.get("amount_minor"), bool) and value["amount_minor"] > 0
          and isinstance(value.get("currency"), str) and len(value["currency"]) == 3 and value["currency"].isupper())
    if not ok:
        _fail("AF-LAUNCH-ANSWERS-PRICE", field,
              "needs a price in whole minor units above zero and a 3-letter currency; a free or unpriced "
              "offer cannot be built and a price is never invented")
    return {"amount_minor": value["amount_minor"], "currency": value["currency"]}


def _deliverables(value: Any) -> List[str]:
    return [str(x).strip() for x in value if str(x).strip()] if isinstance(value, list) else []


def _offer(offer_id: str, role: str, name: Any, price: Any, qid: str, deliverables: Any, index: Optional[int] = None):
    field = f"answers-file:{qid}" + (f"[{index}]" if index is not None else "")
    if not isinstance(name, str) or not name.strip():
        _fail("AF-LAUNCH-ANSWERS-OFFER", field, "an offer needs a name")
    offer = {"offer_id": offer_id, "name": name.strip(), "role": role, "price": _price(price, field)}
    items = _deliverables(deliverables)
    if items:  # a level is supplied from the client's own deliverables, never invented
        offer["level"] = {"state": "supplied", "name": name.strip(), "deliverables": items}
    src = {"offer_id": offer_id, "role": role, "question_id": qid, "source_ref": field}  # Skill 83 offer_mapper grammar
    if index is not None:
        src["index"] = index
    return offer, src


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper() or "OFFER"


def derive_offers(doc: Dict[str, Any]):
    """(journey_mode, offers, offer sources) built only from the answers. Raises AnswersError by name."""
    mode = _provided(doc, "funnel_shape")
    if mode not in JOURNEY_MODES:
        _fail("AF-LAUNCH-ANSWERS-SHAPE", "answers-file:funnel_shape", f"{mode!r} is not one of {JOURNEY_MODES}")
    offers, sources = [], []
    if mode == "single_simple":
        o, s = _offer("MAIN", "main", _provided(doc, "offer_name"), _provided(doc, "price"), "price",
                      (_entry(doc, "deliverables") or {}).get("value"))
        offers.append(o)
        sources.append(dict(s, name_source_ref="answers-file:offer_name"))
    else:
        packages = _provided(doc, "packages")
        if not isinstance(packages, list) or len(packages) < 2:
            _fail("AF-LAUNCH-ANSWERS-PACKAGES", "answers-file:packages", f"{mode} needs at least two packages")
        used = set()
        for i, p in enumerate(packages):
            if not isinstance(p, dict):
                _fail("AF-LAUNCH-ANSWERS-PACKAGES", f"answers-file:packages[{i}]", "each package is a name, deliverables and a price")
            oid = f"MAIN-{_slug(str(p.get('display_name')))}"
            if oid in used:
                _fail("AF-LAUNCH-ANSWERS-PACKAGES", f"answers-file:packages[{i}]", f"two packages share the name {p.get('display_name')!r}")
            used.add(oid)
            o, s = _offer(oid, "main", p.get("display_name"), p.get("price"), "packages", p.get("deliverables"), i)
            offers.append(o)
            sources.append(s)
    for qid, oid, role in EXTRA_SLOTS:
        e = _entry(doc, qid)
        if e is None or e.get("status") == "unknown" or e.get("value") in (None, "none"):
            continue  # not offered; nothing is invented
        v = _provided(doc, qid)
        if not isinstance(v, dict):
            _fail("AF-LAUNCH-ANSWERS-OFFER", f"answers-file:{qid}",
                  "a name, what the buyer gets and a price are needed; record it as an offer with a price")
        o, s = _offer(oid, role, v.get("display_name"), v.get("price"), qid, v.get("deliverables"))
        offers.append(o)
        sources.append(s)
    e = _entry(doc, "downsell_2")
    if e is not None and e.get("value") not in (None, "none"):  # any answer but the bank's "none" is refused, never dropped
        _fail("AF-LAUNCH-ANSWERS-DOWNSELL2", "answers-file:downsell_2",
              "a second downsell is not supported in this release")  # byte-identical to 83 UNSUPPORTED_OFFER_ROLES['downsell_2']
    return mode, offers, sources


# ---------------------------------------------------------------- the client's visual direction
_HOUSE = re.compile(r"^\s*(?:the\s+)?house(?:\s+look)?\s*(?:\(recommended\))?\s*[.!]?\s*$", re.I)
_OWN = re.compile(r"^\s*like\s+my\s+own\s+(?:brand\s+or\s+site|brand|site)\b[\s:,\-]*(.*)$", re.I | re.S)
_OUTSIDE = re.compile(r"^\s*like\s+an\s+outside\s+style(?:\s+i\s+name)?\b[\s:,\-]*(.*)$", re.I | re.S)


def creative_direction(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The explicit visual direction. No answer, or only the flagged default, is refused: the house look is
    used only when the client chose it. value None means house look (selection_mode SECRET_SAUCE_ONLY)."""
    e = _entry(doc, "visual_direction")
    if e is None or e.get("status") != "provided" or not str(e.get("value") or "").strip():
        _fail("AF-LAUNCH-ANSWERS-DIRECTION", "answers-file:visual_direction",
              "the client has not said which look they want. Ask: the house look, a look like their own "
              "brand or site, or an outside style they name. The house look counts only when they choose it")
    text = str(e["value"]).strip()
    out = {"source": "client_choice", "source_ref": "answers-file:visual_direction"}
    if _HOUSE.match(text):
        return dict(out, kind="house_look", value=None, selection_mode=SECRET_SAUCE_ONLY)
    for pattern, kind in ((_OWN, "own_reference"), (_OUTSIDE, "external_direction")):
        m = pattern.match(text)
        if m:
            named = m.group(1).strip()
            if not named:
                _fail("AF-LAUNCH-ANSWERS-DIRECTION", "answers-file:visual_direction",
                      "the client chose a look but did not name which one; ask which brand, site or style")
            return dict(out, kind=kind, value=named, selection_mode=named)
    return dict(out, kind="described", value=text, selection_mode=text)


def write_intake_args(doc: Dict[str, Any]) -> List[str]:
    """The flag every Skill 71 write_intake call takes for this client's direction."""
    d = creative_direction(doc)
    return ["--creative-direction", d["value"]] if d["value"] else []


# ---------------------------------------------------------------- pictures the chosen page set needs
def image_ceiling(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pictures the chosen page set needs, from Skill 49's own page_set.image_estimate; None when that
    skill is not beside this one. Shown with the cap so a ceiling below the need is named before a run."""
    try:
        mode, offers, _ = derive_offers(doc)
        scripts = next((d / "scripts" for d in _skill_dirs("49-signature-funnel") if (d / "scripts").is_dir()),
                       REPO / "49-signature-funnel" / "scripts")
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import page_set  # noqa: E402
        roles = {o["role"] for o in offers}
        long_form = (_entry(doc, "copy_profile") or {}).get("value") == "long_form"
        which = (_entry(doc, "page_set") or {}).get("value")
        if which == "core":
            keys = ["sales", "checkout"]
        else:
            launch = {"journey_mode": mode, "extras": {k: k in roles for k in ("upsell_1", "downsell_1", "upsell_2")}}
            keys = [p["page_key"] for p in page_set.build_page_set(launch)["pages"]]
        per_page = {k: page_set.image_estimate(k, long_form=(long_form and k == "sales")) for k in keys}
        return {"pages": per_page, "images": sum(per_page.values()), "per_section": IMAGES_PER_SECTION}
    except Exception:  # noqa: BLE001 - a missing sibling skill or odd answers only hides the hint
        return None


# ---------------------------------------------------------------- the promotion's real limits
def _promotion(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    got = {k: (_entry(doc, f"bf_{k}") or {}).get("value") for k in ("promotion", "limitations", "seat_limit", "buyers", "followup")}
    if not any(v is not None for v in got.values()):
        return None
    raw = str(got["seat_limit"] or "").strip().lower()
    m = re.search(r"\d+", raw)
    seats = int(m.group(0)) if m and int(m.group(0)) > 0 and not re.search(r"no limit|unlimited", raw) else None
    state = "limited" if seats else "no_limit" if re.search(r"no limit|unlimited|none", raw) else "unknown"
    return {"kind": got["promotion"], "limitations": got["limitations"], "buyers": got["buyers"],
            "followup": got["followup"], "seat_limit": seats, "seat_limit_state": state,
            "source_refs": [f"answers-file:bf_{k}" for k, v in got.items() if v is not None]}


# ---------------------------------------------------------------- the intake
def _image_plan(doc: Dict[str, Any], system: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    plan: Dict[str, Any] = {}
    ds = _entry(doc, "design_style")
    if ds and ds.get("status") == "provided" and ds.get("value") in ("A", "B", "C"):
        # `provided` covers both a client's own choice and the recommendation they accepted;
        # the contract block in provenance says which, and 83 never pays for a proposal.
        plan["design_style"], plan["design_style_source"] = ds["value"], "client_choice"
    cap = _entry(doc, "image_cap")
    if cap and cap.get("status") == "provided" and isinstance(cap.get("value"), int) and cap["value"] > 0:
        plan["image_cap"] = cap["value"]
    # THE MONEY. The downstream paid resolver refuses a real run without cap_minor + currency,
    # and a picture count is not a ceiling. Only a client-provided amount reaches here; an
    # approval with no usable amount stays unknown rather than being invented.
    spend = _spend(doc)
    if spend["state"] == "provided" and spend["cap_minor"]:
        if _plan_accepts("image_cap_minor", 1) is not False:
            plan["image_cap_minor"] = spend["cap_minor"]
        if _plan_accepts("image_currency", "USD") is not False:
            plan["image_currency"] = spend["currency"]
        if spend["approval_ref"] and _plan_accepts("paid_render_approval_ref", "a") is not False:
            plan["paid_render_approval_ref"] = spend["approval_ref"]
    prov = _entry(doc, "image_provider")
    if prov and prov.get("status") != "unknown":
        v = str(prov.get("value") or "").strip().lower()
        mapped = {"connected": "kie", "none": "other_explicit"}.get(v, v)  # same map as engine.to_launch_known
        if mapped not in IMAGE_PROVIDERS:
            _fail("AF-LAUNCH-ANSWERS-PROVIDER", "answers-file:image_provider",
                  f"{v or 'this service'!r} is not a known image service; the launch record knows {', '.join(IMAGE_PROVIDERS)}")
        if prov["status"] == "provided":
            plan["image_provider"] = mapped
            if mapped != "kie":  # Skill 83's image plan decides at dispatch; it stops before anything is spent
                warnings.append(f"{mapped} cannot draw paid pictures for the launcher (paid pictures are KIE only); "
                                "Skill 83's image plan decides at dispatch and stops before anything is sent or spent.")
    owner = _entry(doc, "business_name")
    if owner and owner.get("status") == "provided" and str(owner.get("value") or "").strip():
        plan["brand_owner"] = str(owner["value"]).strip()
    if system.get("brand_file"):
        plan["brand_file"] = system["brand_file"]
    return plan


# ---------------------------------------------------------------- what Skill 83's own intake declares
def _skill_dirs(numbered: str) -> List[Path]:
    """Where a sibling skill can live: repo tree (NN-name), 999 tree (.claude/skills/name), then the installed skills dirs."""
    plain = numbered.split("-", 1)[1]
    out = [REPO / numbered, REPO / ".claude" / "skills" / plain]
    for home in (Path.home() / ".claude" / "skills", Path.home() / ".openclaw" / "skills"):
        out += [home / numbered, home / plain]
    return out


def _roots83() -> List[Path]:
    return _skill_dirs("83-black-friday-launcher")


def _load83(name: str) -> Any:
    """launcher_core.<name> from the first root that has it, else None. Not cached, so tests can pass a module."""
    for d in _roots83():
        if (d / "launcher_core" / f"{name}.py").is_file():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            try:
                return importlib.import_module(f"launcher_core.{name}")
            except ImportError:
                return None
    return None


def _intake83() -> Any:
    return _load83("intake")


def _declared(mod: Any, name: str) -> bool:
    """True when 83's intake declares the field (required, optional or defaultable); never emit one it does not."""
    return mod is not None and any(name in getattr(mod, k, ()) for k in ("REQUIRED_FIELDS", "OPTIONAL_FIELDS", "PERMITTED_DEFAULTS"))


def _price_keys(mod: Any) -> tuple:
    return tuple(getattr(mod, "PRICE_REQUIRED", ())) + tuple(getattr(mod, "PRICE_OPTIONAL", ()))


def _plan_accepts(key: str, value: Any = "x") -> Optional[bool]:
    """Does 83's image_plan.validate_raw accept this key with a VALID sample value? None when
    Skill 83 is not beside this one.

    The probe value matters: validate_raw is a shape check, so a value of the wrong type
    (an int field probed with a string) is refused for its value, not for being undeclared."""
    ip = _load83("image_plan")
    if ip is None:
        return None
    try:
        ip.validate_raw({key: value})
        return True
    except ip.ImagePlanError:
        return False


def _checkout_terms(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The client's own guarantee, terms and consent wording, verbatim. Never defaulted, never written for them."""
    v = _provided(doc, "checkout_terms")
    if not isinstance(v, dict) or not all(isinstance(v.get(k), str) and v[k].strip() for k in TERMS_FIELDS):
        _fail("AF-LAUNCH-ANSWERS-TERMS", "answers-file:checkout_terms",
              "needs all six parts as the client's own words or links: " + ", ".join(TERMS_FIELDS))
    return copy.deepcopy(v)


def _guard_system(system: Dict[str, Any]) -> None:
    """The pass-throughs may add what no answer can carry; they may not replace what the answers build."""
    bad = sorted(set(system.get("extra_root") or {}) & set(ANSWER_BUILT_ROOTS))
    if bad:
        _fail("AF-LAUNCH-ANSWERS-SYSTEM", "system.extra_root", f"{bad} are built from the answers file; they cannot be set here")
    for oid, fields in (system.get("extra_offer") or {}).items():
        bad = sorted(set(fields or {}) & set(OFFER_ANSWER_FIELDS))
        if bad:
            _fail("AF-LAUNCH-ANSWERS-SYSTEM", f"system.extra_offer.{oid}", f"{bad} come from the answers file; they cannot be set here")


def to_launcher_intake(doc: Dict[str, Any], system: Dict[str, Any], *, answers_sha256: Optional[str] = None,
                       answers_path: Optional[Path] = None, intake_module: Any = None) -> Dict[str, Any]:
    """The Skill 83 intake from the answers, with provenance. `system` carries what no answer can: tenant_id,
    location_id, launch_id, [revision], brand {ref, hash}, approval {ref, hash}, and
    optionally brand_file, test_only, locale, extra_root / extra_offer (fields a newer intake requires, never
    ones the answers build). A field is emitted only when Skill 83's intake (`intake_module`, default the
    sibling skill) declares it, so the result validates before and after that intake grows.

    There is no account-entitlement step: the client is never asked to declare a membership or a purchase,
    and no answers value is required for one."""
    if (doc.get("meta") or {}).get("mode") == "legacy" or doc.get("schema") != "client-intake-answers/v1":
        _fail("AF-LAUNCH-ANSWERS-SCHEMA", "answers-file", "not a client-intake-answers/v1 launch answers file")
    for key in ("tenant_id", "location_id", "launch_id", "brand", "approval"):
        if not system.get(key):
            _fail("AF-LAUNCH-ANSWERS-SYSTEM", f"system.{key}", "comes from verified account access, not from the interview")
    _guard_system(system)
    mod = intake_module if intake_module is not None else _intake83()
    if _declared(mod, "answers_file") and answers_path is None:
        _fail("AF-LAUNCH-ANSWERS-SYSTEM", "answers_file", "Skill 83 records the answers file path; build from the file, not from a parsed copy")
    if _provided(doc, "plan_approval") != "approve":
        _fail("AF-LAUNCH-ANSWERS-APPROVAL", "answers-file:plan_approval", "the client has not approved this plan")
    mode, offers, sources = derive_offers(doc)
    direction = creative_direction(doc)
    extra = system.get("extra_offer") or {}
    offers = [dict(copy.deepcopy(o), **extra.get(o["offer_id"], {})) for o in offers]
    if "source_ref" in _price_keys(mod):  # the price carries the answers-file question it came from
        refs = {s["offer_id"]: s["source_ref"] for s in sources}
        for o in offers:
            o["price"]["source_ref"] = refs[o["offer_id"]]
    intake = {
        "schema_version": "1.0", "tenant_id": system["tenant_id"], "location_id": system["location_id"],
        "launch_id": system["launch_id"], "revision": system.get("revision", 1), "journey_mode": mode,
        "brand": system["brand"], "copy_profile": _provided(doc, "copy_profile"), "approval": system["approval"],
        "offers": offers,
    }
    if _declared(mod, "answers_file"):
        intake["answers_file"] = str(answers_path)
    if _declared(mod, "checkout_terms"):
        intake["checkout_terms"] = _checkout_terms(doc)
    if _declared(mod, "promotion"):
        promo = _promotion(doc)
        if promo is not None:
            intake["promotion"] = promo
    for k in ("test_only", "allowed_write_target", "locale", "automation_execution"):
        if k in system:
            intake[k] = system[k]
    ceiling, warnings = image_ceiling(doc), []
    plan = _image_plan(doc, system, warnings)
    if "design_style_source" in plan and _plan_accepts("design_style_source") is False:
        del plan["design_style_source"]
    if direction["value"] is not None and _plan_accepts("creative_direction"):
        plan["creative_direction"] = direction["value"]  # 83's image plan carries the client's look to Skill 71
    if plan:
        intake["image_plan"] = plan
    intake.update(system.get("extra_root") or {})
    if ceiling and plan.get("image_cap") is not None and plan["image_cap"] < ceiling["images"]:
        warnings.append(f"image_cap {plan['image_cap']} is below the {ceiling['images']} pictures the chosen page "
                        "set needs; the last pages would be skipped")
    prov = {"schema": PROVENANCE_SCHEMA,
            "answers_sha256": answers_sha256 or answers_hash(doc),
            "answers_hash_basis": "file-bytes" if answers_sha256 else "canonical-json",
            "intake_sha256": intake_hash(intake),
            "journey_mode": {"source_ref": "answers-file:funnel_shape"},
            "offers": sources, "creative_direction": direction, "promotion": _promotion(doc),
            "image_ceiling": ceiling, "warnings": warnings,
            # F16: one canonical block beside the intake - the design decision and its state,
            # the brand (source, version, digest, palette status), the approved money, and the
            # exact plan revision/approval. A producer matches its own brand file to `brand`.
            "answer_contract": _answer_contract(doc, system)}
    if "checkout_terms" in intake:
        prov["checkout_terms"] = {"source_ref": "answers-file:checkout_terms"}
    return {"intake": intake, "provenance": prov}


# ---------------------------------------------------------------- the refusal
def _same_offer(have: Dict[str, Any], want: Dict[str, Any]) -> bool:
    """Every answers-built field matches. A price may also carry its source_ref, so it is compared on amount and currency."""
    for k, v in want.items():
        got = have.get(k)
        if k == "price":
            ok = isinstance(got, dict) and all(got.get(f) == v[f] for f in ("amount_minor", "currency"))
        else:
            ok = got == v
        if not ok:
            return False
    return True


def verify(intake: Any, provenance: Any, answers: Any, answers_path: Optional[Path] = None) -> None:
    """Raise AnswersError unless the intake was built from exactly these answers. `answers` is the parsed
    answers file; `answers_path` (when given) is hashed as file bytes if the provenance says so."""
    if not isinstance(provenance, dict) or provenance.get("schema") != PROVENANCE_SCHEMA or not provenance.get("answers_sha256"):
        _fail("AF-LAUNCH-ANSWERS-HASH-MISSING", PROVENANCE_NAME,
              "this intake carries no answers-file hash; build it with launcher_intake.py from the answers file")
    if provenance.get("answers_hash_basis") == "file-bytes":
        if answers_path is None:
            _fail("AF-LAUNCH-ANSWERS-HASH-MISSING", PROVENANCE_NAME, "the answers file path is needed to check its hash")
        actual = _file_hash(answers_path)
    else:
        actual = answers_hash(answers)
    if actual != provenance["answers_sha256"]:
        _fail("AF-LAUNCH-ANSWERS-HASH-MISMATCH", "answers_sha256",
              "the answers file changed after this intake was built; rebuild the intake from the current answers")
    if not isinstance(intake, dict) or intake_hash(intake) != provenance.get("intake_sha256"):
        _fail("AF-LAUNCH-ANSWERS-HASH-MISMATCH", "intake_sha256",
              "the intake was edited after it was built from the answers; rebuild it, do not edit it")
    mode, offers, _ = derive_offers(answers)
    have = {o.get("offer_id"): o for o in intake.get("offers") or []}
    same = (intake.get("journey_mode") == mode and set(have) == {o["offer_id"] for o in offers}
            and all(_same_offer(have[o["offer_id"]], o) for o in offers))
    if not same:
        _fail("AF-LAUNCH-ANSWERS-HASH-MISMATCH", "offers",
              "the intake's offers, prices or journey mode do not match the answers file")


# ---------------------------------------------------------------- CLI
def _read(path: Any) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _delegate(argv: List[str]) -> int:
    """Skill 83's own CLI. Kept apart so the refusal above runs first and is testable alone."""
    for d in _roots83():
        if (d / "launcher_core" / "cli.py").is_file():
            sys.path.insert(0, str(d))
            from launcher_core import cli  # noqa: E402
            return cli.main(argv)
    print("FAIL Skill 83 (black-friday-launcher) not found beside this tool", file=sys.stderr)
    return 2


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="launcher_intake.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("answers")
    b.add_argument("--system", required=True)
    b.add_argument("--out", required=True)
    for name in ("verify", "dispatch"):
        v = sub.add_parser(name)
        v.add_argument("--answers", required=True)
        v.add_argument("--intake", required=True)
        v.add_argument("--provenance")
    w = sub.add_parser("write-intake-args")
    w.add_argument("answers")
    args, rest = p.parse_known_args(argv)
    try:
        if args.cmd == "build":
            doc = _read(args.answers)
            out = Path(args.out)
            res = to_launcher_intake(doc, _read(args.system), answers_sha256=_file_hash(Path(args.answers)),
                                     answers_path=Path(args.answers).resolve())
            out.mkdir(parents=True, exist_ok=True)
            (out / "intake.json").write_text(json.dumps(res["intake"], indent=2) + "\n", encoding="utf-8")
            (out / PROVENANCE_NAME).write_text(json.dumps(res["provenance"], indent=2) + "\n", encoding="utf-8")
            print(f"wrote {out / 'intake.json'} and {out / PROVENANCE_NAME}")
            for line in res["provenance"]["warnings"]:
                print(f"WARNING {line}")
            return 0
        if args.cmd == "write-intake-args":
            print(json.dumps(write_intake_args(_read(args.answers))))
            return 0
        prov_path = Path(args.provenance) if args.provenance else Path(args.intake).with_name(PROVENANCE_NAME)
        prov = _read(prov_path) if prov_path.is_file() else None
        verify(_read(args.intake), prov, _read(args.answers), Path(args.answers))
        if args.cmd == "verify":
            print("PASS the intake is bound to the answers file")
            return 0
        return _delegate(["dispatch", "--intake", args.intake, *rest])
    except AnswersError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
