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

# Spend is money, not a picture count (ENF-05). The ceiling in pictures is DERIVED: cap_minor // price.
# Per-picture price in minor units by provider and currency. 8 US cents is the highest per-image tier in
# Skill 74's real KIE pricing samples (GPT Image 2.5 at 4K, 74-kie-live-adapter/tests/real_pricing.py), so the
# derived picture ceiling errs low. Skill 74's `price` command is the live authority; a currency with no row
# here is refused rather than guessed.
# ponytail: static table; swap for a live Skill 74 price lookup if per-model budgets are needed.
IMAGE_PRICE_MINOR: Dict[str, Dict[str, int]] = {"kie": {"USD": 8}}
PAID_APPROVAL_KIND = "paid_asset_budget"
STYLE_SOURCES = ("client_choice", "default_to_confirm")
CONFIRMED_PALETTE_STATUSES = ("provided", "client-confirmed", "client_confirmed")

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
    allowed = {"design_style", "design_style_source", "brand_file", "brand_owner", "image_cap",
               "image_cap_minor", "image_currency", "creative_direction",
               "image_provider", "paid_render_approval_ref", "design_prose_ref", "visual_bible_ref"}
    extra = sorted(set(raw) - allowed)
    if extra:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-SHAPE", "image_plan",
                             f"undeclared field(s) {extra!r}; allowed: {sorted(allowed)!r}")
    minor = raw.get("image_cap_minor")
    if minor is not None and (isinstance(minor, bool) or not isinstance(minor, int) or minor < 1):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap_minor",
                             "must be a whole number of minor currency units (cents), 1 or more")
    cur = raw.get("image_currency")
    if cur is not None and not (isinstance(cur, str) and len(cur) == 3 and cur.isupper() and cur.isalpha()):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_currency",
                             "must be a 3-letter uppercase currency code such as USD")
    return dict(raw)


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


def _check_palette(brand_file: str) -> None:
    """A paid run draws in the client's colors: a suggested or defaulted palette is never paid for (IMG-09)."""
    try:
        brand = json.loads(Path(brand_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        brand = None
    if not isinstance(brand, dict):
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_file",
                             "I cannot read your brand file, so I cannot check your colors before spending. "
                             "Nothing has been sent and nothing has been spent.")
    status = brand.get("palette_status", "provided")  # files made before the field existed are provided
    if status not in CONFIRMED_PALETTE_STATUSES:
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-BRAND", "image_plan.brand_file.palette_status",
            f"Your colors are still {status!r}: you have not confirmed them. I will not pay for pictures in "
            "colors that are not yours. Tell me OK to the palette (or give me your own) and I will go on. "
            "Nothing has been sent and nothing has been spent.")


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

    # Design style: defaultable, flagged.
    style = raw.get("design_style")
    source = _clean_str(raw.get("design_style_source")) or "client_choice"
    if source not in STYLE_SOURCES:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-STYLE", "image_plan.design_style_source",
                             f"{source!r} is not one of {list(STYLE_SOURCES)!r}.")
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

    # Provider: defaultable to the house provider, flagged; an unbuilt provider is refused by name.
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
        price = IMAGE_PRICE_MINOR.get(provider, {}).get(currency)
        if price is None:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_currency",
                f"I have no picture price for {currency} on the {provider} service, so I cannot turn your "
                "budget into a number of pictures. Nothing has been spent.")
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
        if source != "client_choice":  # a defaulted look is not paid for (IMG-08); test_only runs may default
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-STYLE", "image_plan.design_style",
                "You have not picked your look yet (the style was only a starting point). Tell me A (Block), "
                "B (Circle) or C (Hybrid) and I will go on. Nothing has been sent and nothing has been spent.")
        _check_palette(brand_file)
        _verify_paid_budget(approval, plan_hash, cap_minor, currency)
        executor, allow_paid = "kie", True

    inputs = {
        "design_style": style,
        "design_style_source": source,
        "brand_file": brand_file,
        "brand_owner": brand_owner,
        "image_cap": cap,
        "image_provider": provider,
        "paid_render_approval_ref": approval,
        "image_cap_minor": cap_minor if not test_only else None,
        "image_currency": currency if not test_only else None,
        "image_price_minor": price,
        "creative_direction": _clean_str(raw.get("creative_direction")),
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
# (IMG-08) and the client's creative direction (IMG-07).
C3_CARRIED_KEYS = ("design_style_source", "creative_direction")


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
           "provider": inputs["executor_provider"], "test_run": bool(inputs["test_only"])}
    if inputs.get("design_prose_ref"):  # Skill 71 refuses an order-page prompt under its floor without the measured design system
        doc["design_prose"] = inputs["design_prose_ref"]
    return doc
