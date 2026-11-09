"""The image plan: everything the wireframe and mockup stages need that is not a page fact.

This is the Skill 83 side of the shared image-inputs contract (C3, image_inputs.json).
Every role receives the same file, so no page can be drawn in a different style, for a
different owner, or under a different spend cap than the rest of the launch.

Client experience rules (owner orders 2026-10-20):

* Plain English. Every field has a one-sentence question, a reason for asking, and an
  "I'm not sure" path.
* "I don't know" never stops a build silently. A field that is safe to default is defaulted,
  FLAGGED "to confirm" with a one-line way to change it, and reported at delivery.
* Money and ownership are never defaulted: the spend cap on a paid run, the written approval
  to render, the brand file and the brand owner. Those stop the build with a plain message
  that says what is needed and how to get it.

The brand file itself (colors with roles, fonts, logo, photos) is produced by the shared
intake questions; this module only needs to know where it is.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

DESIGN_STYLES = ("A", "B", "C")
# The launch record's image_provider vocabulary (Skill 49 schema). Only "kie" has an executor path
# in Skill 71 today. A practice run (test_only) works with every known provider: it draws stub pictures and
# spends nothing. A paid run with any other provider is refused by name rather than silently rerouted.
KNOWN_PROVIDERS = ("kie", "agnes", "other_explicit")
EXECUTABLE_PROVIDERS = ("kie",)

DEFAULT_DESIGN_STYLE = "A"
DEFAULT_PROVIDER = "kie"
# A free (stub) run spends nothing, so its image cap is a bookkeeping number and may be defaulted.
# A paid run's cap is money: it is never defaulted.
DEFAULT_STUB_IMAGE_CAP = 400

# Spend is money, not a picture count (ENF-05). The ceiling in pictures is DERIVED: cap_minor // price,
# where the per-picture price comes from Skill 74's LIVE price authority (F20). A static table cannot
# establish what a model costs today: 74 reads the live catalog's pricingDesc (registry snapshot as its
# own offline fallback) for the actual model and resolution, and this module converts credits to money
# from the same live text. No row, no numeric price: the paid run is refused by name, never guessed.
PRICE_MODULE_REF = "74-kie-live-adapter/scripts/kie_live_adapter.py"
MODEL_FAMILY_BY_PROVIDER = {"kie": "gpt-image"}
LIVE_PRICE_CURRENCIES = ("USD",)  # KIE's pricing text quotes US dollars only
USD_MINOR = 100
PAID_APPROVAL_KIND = "paid_asset_budget"
# F16 item 4: ONE style-source vocabulary, owned by the shared brand record module
# (shared-utils/client_intake/brand_record.py) so shared intake, 83, 49 and 71 cannot drift.
# `default_to_confirm` is a PROPOSAL, never a recorded decision; absence is `unknown`.
STYLE_SOURCES = ("client_choice", "recommended_accepted", "default_to_confirm", "unknown")
# Only a decision the client actually recorded may be paid for (IMG-08).
PAID_STYLE_SOURCES = ("client_choice", "recommended_accepted")
CONFIRMED_PALETTE_STATUSES = ("provided",)

UNKNOWN_WORDS = ("unknown", "not sure", "i'm not sure", "im not sure", "i don't know",
                 "i dont know", "help", "help me")


class ImagePlanError(Exception):
    """An image plan that cannot be built. Carries a stable autofail code and plain English."""

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(f"{code}: {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail


# One canonical question object per client-facing field, in the shape the shared question bank uses
# (id, text, why, choices, help, safe_default, flag, target_fields), so any harness can ask it its own
# way (a structured picker in Claude Code, a numbered chat message in OpenClaw) and record the same answer.
QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "design_style",
        "text": "Which look do you want for your pages: A (Block), B (Circle) or C (Hybrid)?",
        "why": "It decides whether photos are rectangles or round frames on every page of the launch.",
        "choices": [
            {"value": "A", "label": "A, Block",
             "example": "Clean rectangular photos and straight-edged sections, like a magazine. Classic and polished."},
            {"value": "B", "label": "B, Circle",
             "example": "Round framed photos with colored rings and soft curves. Warm and friendly."},
            {"value": "C", "label": "C, Hybrid",
             "example": "Block structure with round photos on the personal pictures (you, your team, your clients)."},
        ],
        "help_label": "I'm not sure, help me",
        "help": "Tell me three words for how you want your brand to feel and I will recommend one.",
        "safe_default": DEFAULT_DESIGN_STYLE,
        "flag": "to_confirm",
        "default_note": "Style A (Block) is the most classic and the safest to start with.",
        "target_fields": ["image_plan.design_style"],
    },
    {
        "id": "image_provider",
        "text": "Should the pictures be drawn with our standard image service?",
        "why": "It decides who draws the wireframes and mockups. Nothing is spent until you approve a budget.",
        "choices": [{"value": "kie", "label": "Yes, use the standard service"}],
        "help_label": "I'm not sure, help me",
        "help": "The standard image service is what every other BlackCEO page uses. Say yes unless someone told you otherwise.",
        "safe_default": DEFAULT_PROVIDER,
        "flag": "to_confirm",
        "default_note": "The standard image service.",
        "target_fields": ["image_plan.image_provider"],
    },
    {
        "id": "image_cap",
        "text": "What is the most money you are willing to spend on pictures for this launch?",
        "why": "It is a hard ceiling. The build stops adding pictures when the money is used up.",
        "choices": [],
        "help_label": "I'm not sure, help me",
        "help": "I can estimate it from your page list and show how many pictures it buys. A practice run costs nothing.",
        "safe_default": None,
        "flag": "never_default_when_paid",
        "default_note": "Practice runs use placeholders and cost nothing. A paid run needs your number and your written approval.",
        "target_fields": ["image_plan.image_cap_minor", "image_plan.image_currency",
                          "image_plan.paid_render_approval_ref"],
    },
]


def _is_unknown(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return str(value.get("status", "")).strip().lower() == "unknown"
    return isinstance(value, str) and value.strip().lower() in UNKNOWN_WORDS


def _clean_str(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _confirm(field: str, value: Any, reason: str, how: str) -> Dict[str, Any]:
    return {"field": f"image_plan.{field}", "value": value, "status": "default_to_confirm",
            "reason": reason, "how_to_change": how}


def validate_raw(raw: Any) -> Dict[str, Any]:
    """Shape check only, used by intake. Resolution (defaults, requirements) happens at dispatch."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-SHAPE", "image_plan", "must be an object")
    allowed = {"design_style", "design_style_source", "brand_file", "brand_owner", "brand_sha256",
               "brand_version", "image_cap", "image_cap_minor", "image_currency", "creative_direction",
               "creative_direction_kind", "creative_direction_blend", "creative_direction_approval_ref",
               "image_provider", "paid_render_approval_ref", "design_prose_ref", "visual_bible_ref",
               "image_model", "image_resolution"}
    extra = sorted(set(raw) - allowed)
    if extra:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-SHAPE", "image_plan",
                             f"undeclared field(s) {extra!r}; allowed: {sorted(allowed)!r}")
    for key in ("image_model", "image_resolution"):
        value = raw.get(key)
        if value is not None and not (isinstance(value, str) and value.strip()):
            raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", f"image_plan.{key}",
                                 "must be a non-empty piece of text when given")
    minor = raw.get("image_cap_minor")
    if minor is not None and (isinstance(minor, bool) or not isinstance(minor, int) or minor < 1):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap_minor",
                             "must be a whole number of minor currency units (cents), 1 or more")
    cur = raw.get("image_currency")
    if cur is not None and not (isinstance(cur, str) and len(cur) == 3 and cur.isupper() and cur.isalpha()):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_currency",
                             "must be a 3-letter uppercase currency code such as USD")
    return dict(raw)


def _brand_record() -> Any:
    """The shared brand record module (F16 S2): the one style-source vocabulary, palette-status
    normalizer, brand digest and creative-direction precedence. Loaded from the repository beside
    this skill the same way the approval verifier is; never a second copy of any of it."""
    path = Path(__file__).resolve().parents[2] / "shared-utils" / "client_intake" / "brand_record.py"
    spec = importlib.util.spec_from_file_location("launcher_brand_record", path) if path.is_file() else None
    if spec is None or spec.loader is None:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan",
                             "The shared brand record module is not installed here, so the plan cannot prove "
                             "which brand and style it draws. Nothing has been sent and nothing has been spent.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _approval_verify() -> Callable[..., Dict[str, Any]]:
    """The one approval verifier (U-approval-02): trusts only a Command Center record. Fail closed when
    it is not installed. Tests patch this function; nothing in a payload can replace it."""
    path = Path(__file__).resolve().parents[2] / "shared-utils" / "signature_launch_contract" / "approval_record.py"
    spec = importlib.util.spec_from_file_location("launcher_approval_record", path) if path.is_file() else None
    if spec is None or spec.loader is None:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-APPROVAL", "image_plan.paid_render_approval_ref",
                             "The approval checker is not installed here, so a paid run cannot be approved. "
                             "Nothing has been sent and nothing has been spent.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


def _verify_paid_budget(approval_id: str, plan_hash: Optional[str], cap_minor: int, currency: str) -> None:
    """Raise unless Command Center holds an unexpired paid_asset_budget approval for this plan hash that
    covers cap_minor/currency. A free-text reference, a file or a dict is never an approval."""
    if not (isinstance(plan_hash, str) and plan_hash.strip()):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-APPROVAL", "plan_hash",
                             "A paid run needs the plan hash your approval is bound to. Nothing has been "
                             "sent and nothing has been spent.")
    verify = _approval_verify()
    try:
        got = verify(approval_id, PAID_APPROVAL_KIND, plan_hash, [PAID_APPROVAL_KIND],
                     cap={"cap_minor": cap_minor, "currency": currency}, test_only=False)
    except ImagePlanError:
        raise
    except Exception as exc:  # ApprovalRefused / ApprovalUnavailable: both mean no spend
        code = getattr(exc, "code", type(exc).__name__)
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-APPROVAL", "image_plan.paid_render_approval_ref",
            f"Your budget approval could not be verified ({code}). Nothing has been sent and nothing has "
            "been spent. Approve the budget in Command Center by replying with the plan code.") from exc
    if not (isinstance(got, dict) and got.get("ok") is True and got.get("kind") == PAID_APPROVAL_KIND
            and got.get("authority") == "command-center" and got.get("approval_id") == approval_id):
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-APPROVAL", "image_plan.paid_render_approval_ref",
            "That is not a budget approval recorded in Command Center. Nothing has been sent and nothing "
            "has been spent.")


def _check_palette(brand: Dict[str, Any]) -> None:
    """A paid run draws in the client's colors: a suggested, defaulted or UNSTATED palette is never
    paid for (IMG-09).

    F16 item 8: a missing or unrecognized `palette_status` is `unknown`, not `provided`. A file made
    before the field existed therefore proves nothing about the client's colors and is refused at this
    spend boundary rather than assumed confirmed.
    """
    if brand.get("state") == "unreadable":
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_file",
                             "I cannot read your brand file, so I cannot check your colors before spending. "
                             "Nothing has been sent and nothing has been spent.")
    status = brand.get("palette_status", "unknown")
    if status not in CONFIRMED_PALETTE_STATUSES:
        why = ("it records no palette status, so nobody has confirmed these colors"
               if status == "unknown" else f"it is {status!r}, so you have not confirmed these colors")
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_file.palette_status",
            f"Your brand file cannot be paid against: {why}. I will not pay for pictures in colors that "
            "are not yours. Tell me OK to the palette (or give me your own) and I will go on. "
            "Nothing has been sent and nothing has been spent.")


# ---------------------------------------------------------------- the live price authority (F20)
def _module_roots(rel: str) -> List[Path]:
    """A sibling module: the repo checkout first, then every installed skills tree."""
    name, _, rest = rel.partition("/")
    plain = name.split("-", 1)[1] if re.match(r"^\d+-", name) else name
    home = Path.home()
    roots = [Path(__file__).resolve().parents[2], home / ".openclaw" / "skills",
             home / ".claude" / "skills", home / ".claude-nine" / "skills", Path("/data/.openclaw/skills")]
    return [root / name / rest for root in roots] + [root / plain / rest for root in roots]


def _price_module() -> Any:
    """Skill 74's adapter module. It is the one live price authority; nothing here prices a model."""
    path = next((p for p in _module_roots(PRICE_MODULE_REF) if os.path.isfile(str(p))), None)
    if path is None:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price checker ({PRICE_MODULE_REF}) is not installed here, so I cannot "
                             "work out what one picture costs. Nothing has been sent and nothing has been spent.")
    spec = importlib.util.spec_from_file_location("launcher_kie_live_adapter", path)
    if spec is None or spec.loader is None:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price checker at {path} cannot be loaded. Nothing has been spent.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _price_adapter(module: Any) -> Any:
    """Skill 74's Adapter: the live catalog/registry price read, its own key resolution, no printing."""
    try:
        return module.Adapter()
    except Exception as exc:  # noqa: BLE001  (a price checker that will not start prices nothing)
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price checker did not start ({type(exc).__name__}). Nothing has been "
                             "sent and nothing has been spent.") from exc


_CREDIT_USD_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*credits?\b[^$();|]{0,24}?\(\s*[~≈]?\s*\$(\d+(?:\.\d+)?)")


def pricing_pairs(text: str) -> List[Dict[str, Any]]:
    """[(clause, credits, usd)] from an live pricing description: the credits AND dollars of one tier."""
    out: List[Dict[str, Any]] = []
    for clause in re.split(r"[;|\n]", text or ""):
        for part in re.split(r",(?=\s*[\d])", clause):
            for m in _CREDIT_USD_RE.finditer(part):
                out.append({"clause": part, "credits": float(m.group(1).replace(",", "")),
                            "usd": float(m.group(2))})
    return out


def pick_price(desc: str, resolution: Optional[str]) -> Optional[Dict[str, Any]]:
    """One (credits, usd) tier for the requested resolution; without one, the dearest tier.

    The dearest tier errs the picture ceiling low, which is the safe direction for money.
    """
    pairs = pricing_pairs(desc)
    if not pairs:
        return None
    if resolution:
        token = re.match(r"(\d+(?:\.\d+)?)\s*[kK]?$", resolution.strip())
        if token:
            want = re.compile(r"(?i)\b" + re.escape(token.group(1)) + r"\s*[kK]\b")
            matched = [p for p in pairs if want.search(p["clause"])]
            if matched:
                return matched[0]
    return max(pairs, key=lambda p: p["credits"])


def live_price(provider: str, currency: str, *, model: Optional[str] = None,
               resolution: Optional[str] = None) -> Dict[str, Any]:
    """One picture's live price, in the client's money. Raises ImagePlanError when it cannot be known."""
    if currency not in LIVE_PRICE_CURRENCIES:
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_currency",
            f"I have no live money price for {currency}; the live image price is quoted in "
            f"{', '.join(LIVE_PRICE_CURRENCIES)}. Nothing has been spent.")
    module = _price_module()
    family = MODEL_FAMILY_BY_PROVIDER.get(provider)
    known = getattr(module, "KNOWN_DEFAULTS", {}) or {}
    chosen = _clean_str(model) or _clean_str(known.get(family))
    if not chosen:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan.image_model",
                             f"I cannot tell which {provider} image model draws these pictures, so I cannot "
                             "price them. Nothing has been sent and nothing has been spent.")
    adapter = _price_adapter(module)
    try:
        got = adapter.cmd_price(chosen, units=1)
    except Exception as exc:  # noqa: BLE001
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price check for {chosen} failed ({type(exc).__name__}). Nothing has "
                             "been sent and nothing has been spent.") from exc
    if not isinstance(got, dict) or got.get("state") == "fail":
        error = got.get("error") if isinstance(got, dict) else None
        code = (error or {}).get("code") if isinstance(error, dict) else "no_price"
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price checker has no numeric price for {chosen} ({code}). Nothing has "
                             "been sent and nothing has been spent.")
    data = got.get("data") or {}
    picked = pick_price(str(data.get("pricing_desc") or ""), resolution)
    if not picked or picked["credits"] <= 0 or picked["usd"] <= 0:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price text for {chosen} carries no credits-and-dollars figure, so I "
                             "cannot turn your budget into pictures. Nothing has been spent.")
    per_credit = picked["usd"] / picked["credits"]
    per_picture_minor = int(math.ceil(picked["credits"] * per_credit * USD_MINOR - 1e-9))
    if per_picture_minor < 1:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan",
                             f"The live price for {chosen} rounds below one cent, so I cannot hold a money "
                             "ceiling against it. Nothing has been spent.")
    return {"model": chosen, "resolution": resolution, "credits": picked["credits"],
            "usd_per_credit": round(per_credit, 6), "per_picture_minor": per_picture_minor,
            "price_source": f"74-kie-live-adapter price ({data.get('price_source') or 'live'})",
            "pricing_desc": str(data.get("pricing_desc") or ""),
            "warnings": list(got.get("warnings") or [])}


def preflight(quote: Dict[str, Any], units: int) -> Dict[str, Any]:
    """Skill 74's own preflight for this many pictures at this model: recorded, never a budget proof.

    A provider balance is not the client's monetary ceiling (F20): it says whether the account can pay
    the provider, never whether the client approved the money. It is recorded so a shortfall is named.
    """
    try:
        module = _price_module()
        got = _price_adapter(module).cmd_preflight(quote["model"], units=max(1, int(units)))
    except Exception as exc:  # noqa: BLE001  (a missing balance check is recorded, never printed)
        return {"state": "unavailable", "reason": type(exc).__name__, "units": units}
    data = got.get("data") or {}
    state = "ok" if got.get("state") != "fail" and data.get("ok") is True else "insufficient_or_unknown"
    return {"state": state, "units": units, "required": data.get("required"), "balance": data.get("balance"),
            "shortfall": data.get("shortfall"),
            "error": ((got.get("error") or {}).get("code") if isinstance(got.get("error"), dict) else None),
            "source": "74-kie-live-adapter preflight"}


# ---------------------------------------------------------------- style and provider (shared by plan and resolve)
def _style(raw: Dict[str, Any], to_confirm: List[Dict[str, Any]], br: Any = None) -> Tuple[str, str]:
    """(design_style, design_style_source). A defaulted look stays flagged; it is never a client's choice.

    When the shared brand record is available (br) its ONE vocabulary normalizes the source (F16 item 4);
    plan_shape runs without it and still accepts only a known source.
    """
    style = raw.get("design_style")
    if br is None:
        source = _clean_str(raw.get("design_style_source")) or "client_choice"
        if source not in STYLE_SOURCES:
            raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-STYLE", "image_plan.design_style_source",
                                 f"{source!r} is not one of {list(STYLE_SOURCES)!r}.")
    else:
        raw_source = raw.get("design_style_source")
        if raw_source is not None and not br.is_known_style_source(raw_source):
            raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-STYLE", "image_plan.design_style_source",
                                 f"{raw_source!r} is not one of {list(STYLE_SOURCES)!r}.")
        source = br.normalize_style_source(raw_source)
    if style is None or _is_unknown(style):
        style, source = DEFAULT_DESIGN_STYLE, "default_to_confirm"
        to_confirm.append(_confirm(
            "design_style", style,
            "You weren't sure which look you wanted, so I started with Style A (Block), the most classic and polished.",
            "Tell me A, B or C and I will redraw the pages in that style."))
    elif style not in DESIGN_STYLES:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-STYLE", "image_plan.design_style",
                             f"{style!r} is not one of A, B or C. A is Block (rectangles), B is Circle "
                             "(round photos), C is Hybrid (both).")
    elif source == "default_to_confirm":  # a style defaulted upstream stays flagged; never laundered into a choice
        to_confirm.append(_confirm(
            "design_style", style,
            "The look was started for you (Style A, Block) and you have not confirmed it.",
            "Tell me A, B or C and I will redraw the pages in that style."))
    return style, source


def _provider(raw: Dict[str, Any], test_only: bool, to_confirm: List[Dict[str, Any]]) -> str:
    """The image service. An unbuilt provider is refused for paid pictures, by name."""
    provider = raw.get("image_provider")
    if provider is None or _is_unknown(provider):
        provider = DEFAULT_PROVIDER
        to_confirm.append(_confirm(
            "image_provider", provider,
            "I used our standard image service because none was chosen.",
            "Name another image service and I will check whether it is supported."))
    if provider not in KNOWN_PROVIDERS:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-PROVIDER", "image_plan.image_provider",
                             f"{provider!r} is not a known image service ({list(KNOWN_PROVIDERS)!r}).")
    if provider not in EXECUTABLE_PROVIDERS and not test_only:
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-PROVIDER", "image_plan.image_provider",
            f"The {provider} image service cannot draw paid pages yet (Skill 71's stage executor has no "
            f"{provider} path). Nothing was sent and nothing was spent. A practice run with placeholder "
            "pictures works with any service; for paid pictures choose the standard service (kie) or ask "
            "for the integration to be added.")
    return provider


def plan_shape(raw: Optional[Dict[str, Any]], *, test_only: bool) -> Dict[str, Any]:
    """The two facts the plan hash binds, resolved WITHOUT money or approval (F20, no circular dependency).

    design_style and image_provider are the only image-plan values a launch record carries, so the plan
    hash can be computed from exactly these before the paid budget is verified against that hash. The
    paid-run refusals (unbuilt provider, unapproved budget) belong to `resolve`, not here: `plan` must be
    able to show the plan the client is approving. Never returns a shape without design_style.
    """
    bag = validate_raw(raw)
    style, source = _style(bag, [])
    return {"design_style": style, "design_style_source": source,
            "image_provider": _provider(bag, True, [])}


def resolve(raw: Optional[Dict[str, Any]], *, test_only: bool,
            plan_hash: Optional[str] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return (image_inputs, to_confirm). Raises ImagePlanError for what may never be defaulted.

    image_inputs is the C3 document: design_style, brand_file, brand_owner, image_cap, image_provider,
    paid_render_approval_ref, design_prose_ref, visual_bible_ref, test_only, plus design_style_source
    and the derived executor_provider / allow_paid the adapters pass on. A paid run also reports
    image_cap_minor, image_currency, image_price_minor and the derived picture ceiling (image_cap).

    test_only must be exactly True or False; None, 0, "" and [] are refused, never read as "paid" or "free".
    allow_paid is True only for a paid_asset_budget approval verified against plan_hash (ENF-05).
    """
    if not isinstance(test_only, bool):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-TEST-ONLY", "test_only",
                             "must be exactly true (practice run) or false (paid run); anything else is refused. "
                             "Nothing has been sent and nothing has been spent.")
    raw = validate_raw(raw)
    to_confirm: List[Dict[str, Any]] = []

    # Brand file and owner: the pages cannot be drawn for nobody, and a palette is never borrowed.
    brand_file = _clean_str(raw.get("brand_file"))
    if brand_file is None or _is_unknown(raw.get("brand_file")):
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_file",
            "I need your brand file before I can draw anything. It holds your colors (and which one is "
            "primary), fonts, logo and photos. If you don't know your colors yet, say so in the brand "
            "questions and I will suggest three palettes, or pull them from your logo or website.")
    brand_owner = _clean_str(raw.get("brand_owner"))
    if brand_owner is None:
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-OWNER", "image_plan.brand_owner",
            "I need to know whose brand this is, so no page is ever drawn with another client's look.")

    # The brand record (F16 item 6): the plan's own brand hash, checked against the file in hand.
    # The hash is the producer's: engine.brand_provenance(...)["brand_file_sha256"], the SHA-256 of
    # the brand file's bytes. Nothing here invents a second identity.
    br = _brand_record()
    plan_brand_sha = _clean_str(raw.get("brand_sha256"))
    if plan_brand_sha is not None and not re.fullmatch(r"[0-9a-f]{64}", plan_brand_sha):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_sha256",
                             "must be the plan's 64-character lowercase hex SHA-256 of the brand file. "
                             "Nothing has been sent and nothing has been spent.")
    brand = br.brand_record(brand_file, plan_brand_sha256=plan_brand_sha,
                            version=raw.get("brand_version"), owner=brand_owner)
    if brand["state"] == "mismatch":
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_sha256",
            "The brand file in hand is not the one this plan was built from: its SHA-256 "
            f"{brand['brand_sha256']} does not match the plan's {brand['plan_brand_sha256']}. A stale pin or a "
            "substituted file is never drawn. Nothing has been sent and nothing has been spent.")

    # The creative direction's precedence, resolved ONCE before any prompt is assembled (F16 item 11).
    policy = br.creative_direction_policy(kind=raw.get("creative_direction_kind"),
                                          blend=raw.get("creative_direction_blend"),
                                          approval_ref=raw.get("creative_direction_approval_ref"))
    for conflict in policy["conflicts"]:
        to_confirm.append(_confirm("creative_direction", policy["grade_mode"], conflict,
                                   "Approve the blend in Command Center (it then supplies the grade), or name "
                                   "the style without one and the house grade stays on."))

    # Design style and provider: defaultable, flagged; an unbuilt provider is refused for paid pictures.
    # Style uses the ONE shared vocabulary (F16 item 4) via the brand record when it is loaded.
    style, source = _style(raw, to_confirm, br=br)
    provider = _provider(raw, test_only, to_confirm)

    # Spend: a free run may default the cap; a paid run never does. A paid run's cap is MONEY (cap_minor +
    # currency), the picture ceiling is derived from it, and the spend needs a verified paid_asset_budget.
    approval = _clean_str(raw.get("paid_render_approval_ref"))
    cap = raw.get("image_cap")
    if cap is not None and not _is_unknown(cap):
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap",
                                 "must be a whole number of pictures, 1 or more")
    else:
        cap = None
    cap_minor, currency, price = raw.get("image_cap_minor"), raw.get("image_currency"), None
    quote: Optional[Dict[str, Any]] = None
    spent_check: Optional[Dict[str, Any]] = None
    if test_only:
        executor, allow_paid = "stub", False
        if cap is None:
            cap = DEFAULT_STUB_IMAGE_CAP
            to_confirm.append(_confirm(
                "image_cap", cap,
                "This is a practice run with placeholder pictures, so it costs nothing; I set a ceiling of "
                f"{cap} pictures for the bookkeeping.",
                "Give me your own number before a real run. A real run always needs your number."))
    else:
        if cap is None and cap_minor is None:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap_minor",
                "A real run spends money, so I need your ceiling: the most money you will spend on pictures. "
                "I can estimate it from your page list if you'd like. I never pick this one for you.")
        if approval is None:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-APPROVAL", "image_plan.paid_render_approval_ref",
                "A real run needs your written OK to spend on pictures. Nothing has been sent and nothing "
                "has been spent. Tell me when you approve the budget and I will record it.")
        if cap_minor is None or currency is None:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap_minor",
                "Your ceiling must be an amount of money with its currency (for example 5000 cents, USD), "
                "not a picture count. I never pick this one for you.")
        # Permission first, price second: the style decision is checked before any price is looked up, so a
        # missing/unverifiable approval is never masked by a price or provider problem.
        # A proposal or an absence is not a decision: only a recorded choice (or a recommendation the
        # client accepted) may be paid for (IMG-08, F16 items 3-4); test_only runs may default.
        if source not in PAID_STYLE_SOURCES:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-STYLE", "image_plan.design_style",
                "You have not picked your look yet (the style was only a starting point or nobody recorded "
                "it). Tell me A (Block), B (Circle) or C (Hybrid) and I will go on; if you accepted my "
                "recommendation, say yes so it is recorded as your choice. "
                "Nothing has been sent and nothing has been spent.")
        _check_palette(brand)
        # The price is LIVE (F20): Skill 74's price authority for the actual model and resolution.
        quote = live_price(provider, currency, model=_clean_str(raw.get("image_model")),
                           resolution=_clean_str(raw.get("image_resolution")))
        price = quote["per_picture_minor"]
        ceiling = cap_minor // price
        if ceiling < 1:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap_minor",
                f"{cap_minor} minor {currency} does not pay for one picture ({price} each). Nothing has been spent.")
        if cap is not None and cap > ceiling:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap",
                f"{cap} pictures cost more than your budget: {cap_minor} minor {currency} pays for at most "
                f"{ceiling}. Nothing has been spent.")
        cap = ceiling if cap is None else cap
        # Permission is verified against the plan hash AFTER the cheap arithmetic, so an impossible
        # request never costs an approval lookup and a valid one is verified exactly once.
        _verify_paid_budget(approval, plan_hash, cap_minor, currency)
        executor, allow_paid = "kie", True
        spent_check = preflight(quote, cap)  # recorded evidence, never a substitute for the money ceiling

    inputs = {
        "design_style": style,
        "design_style_source": source,
        "brand_file": brand_file,
        "brand_owner": brand_owner,
        # The plan's own brand hash (None when the plan recorded none - honest, never a fresh hash
        # dressed up as the plan's), and what the file in hand proved.
        "brand_sha256": brand["plan_brand_sha256"],
        "brand_record_state": brand["state"],
        "brand_palette_status": brand["palette_status"],
        "image_cap": cap,
        "image_provider": provider,
        "paid_render_approval_ref": approval,
        "image_cap_minor": cap_minor if not test_only else None,
        "image_currency": currency if not test_only else None,
        "image_price_minor": price,
        "image_price_credits": (quote or {}).get("credits"),
        "image_price_source": (quote or {}).get("price_source"),
        "image_model": (quote or {}).get("model") or _clean_str(raw.get("image_model")),
        "image_resolution": _clean_str(raw.get("image_resolution")),
        "image_preflight": spent_check,
        "creative_direction": _clean_str(raw.get("creative_direction")),
        "creative_direction_source": policy["style_state"],
        "creative_direction_grade_mode": policy["grade_mode"],
        "creative_direction_grade_owner": policy["grade_owner"],
        "design_prose_ref": _clean_str(raw.get("design_prose_ref")),
        "visual_bible_ref": _clean_str(raw.get("visual_bible_ref")),
        "test_only": bool(test_only),
        "executor_provider": executor,
        "allow_paid": allow_paid,
        "paid_approval_id": approval if allow_paid else None,
    }
    return inputs, to_confirm


# The contract C3 keys, exactly what Skill 49's page_set.load_image_inputs accepts (it refuses any other key).
C3_KEYS = ("design_style", "brand_file", "brand_owner", "image_cap", "image_provider",
           "paid_render_approval_ref", "design_prose_ref", "visual_bible_ref", "test_only")


# Carried when Skill 49's page_set accepts them (it refuses any key it does not list): the style's source
# (IMG-08), the client's creative direction (IMG-07), the plan's brand hash and the resolved grade mode
# (F16 items 6 and 11) so every page and every rendered image obeys the SAME approved brand/style; and
# — F20 — the approved MONEY the cap is held in, so a consumer never re-reads a count as a ceiling.
C3_CARRIED_KEYS = ("design_style_source", "creative_direction", "creative_direction_source",
                   "creative_direction_grade_mode", "brand_sha256", "image_cap_minor", "image_currency")


def _c3_keys() -> Tuple[str, ...]:
    routes = str(Path(__file__).resolve().parent.parent / "routes")
    if routes not in sys.path:
        sys.path.insert(0, routes)
    try:
        import substrate
        accepted = set(substrate.dispatch().pset.IMAGE_INPUT_KEYS)
    except Exception:  # Skill 49 not loadable: write only the base contract
        accepted = set()
    return C3_KEYS + tuple(k for k in C3_CARRIED_KEYS if k in accepted)


def image_inputs_file(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """The shared image inputs written to disk and bound into every Skill 49 wrapper: the C3 keys (plus the
    carried keys Skill 49 accepts) and nothing else. image_provider is the provider that really runs
    ("stub" on a free run)."""
    doc = {k: inputs[k] for k in _c3_keys()}
    doc["image_provider"] = inputs["executor_provider"]
    return doc


def order_page_inputs_file(inputs: Dict[str, Any], *, route_graph: str) -> Dict[str, Any]:
    """The same values in the shape Skill 78's run_image_stages.py reads (route_graph, provider, test_run).
    Skill 49's own page_set.selection_inputs makes this shape; kept here so the file is written
    before any Skill 49 module is loaded."""
    doc = {"route_graph": route_graph, "brand_file": inputs["brand_file"], "brand_owner": inputs["brand_owner"],
           "image_cap": inputs["image_cap"], "design_style": inputs["design_style"],
           "provider": inputs["executor_provider"], "test_run": bool(inputs["test_only"]),
           # F20: the spend contract the executor must see — MONEY and currency (a picture count is not a
           # ceiling) and the approval reference that money is bound to, plus the live price it was struck at.
           "image_cap_minor": inputs.get("image_cap_minor"), "image_currency": inputs.get("image_currency"),
           "paid_render_approval_ref": inputs.get("paid_render_approval_ref"),
           "paid_approval_id": inputs.get("paid_approval_id"),
           "image_model": inputs.get("image_model"), "image_resolution": inputs.get("image_resolution"),
           "image_price_minor": inputs.get("image_price_minor"),
           "image_price_source": inputs.get("image_price_source"),
           "image_preflight": inputs.get("image_preflight")}
    if inputs.get("design_prose_ref"):  # Skill 71 refuses an order-page prompt under its floor without the measured design system
        doc["design_prose"] = inputs["design_prose_ref"]
    return doc
