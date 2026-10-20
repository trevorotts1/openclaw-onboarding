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

from typing import Any, Dict, List, Optional, Tuple

DESIGN_STYLES = ("A", "B", "C")
# The launch record's image_provider vocabulary (Skill 49 schema). Only "kie" has an executor path
# in Skill 71 today; the others are refused by name rather than silently rerouted.
KNOWN_PROVIDERS = ("kie", "agnes", "other_explicit")
EXECUTABLE_PROVIDERS = ("kie",)

DEFAULT_DESIGN_STYLE = "A"
DEFAULT_PROVIDER = "kie"
# A free (stub) run spends nothing, so its image cap is a bookkeeping number and may be defaulted.
# A paid run's cap is money: it is never defaulted.
DEFAULT_STUB_IMAGE_CAP = 400

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
        "text": "What is the most pictures you are willing to pay for on this launch?",
        "why": "It is a hard ceiling. The build stops adding pictures when it is reached.",
        "choices": [],
        "help_label": "I'm not sure, help me",
        "help": "I can estimate it from your page list. A practice run with placeholder pictures costs nothing.",
        "safe_default": None,
        "flag": "never_default_when_paid",
        "default_note": "Practice runs use placeholders and cost nothing. A paid run needs your number and your written approval.",
        "target_fields": ["image_plan.image_cap", "image_plan.paid_render_approval_ref"],
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
               "image_provider", "paid_render_approval_ref", "design_prose_ref", "visual_bible_ref"}
    extra = sorted(set(raw) - allowed)
    if extra:
        raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-SHAPE", "image_plan",
                             f"undeclared field(s) {extra!r}; allowed: {sorted(allowed)!r}")
    return dict(raw)


def resolve(raw: Optional[Dict[str, Any]], *, test_only: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return (image_inputs, to_confirm). Raises ImagePlanError for what may never be defaulted.

    image_inputs is the C3 document: design_style, brand_file, brand_owner, image_cap, image_provider,
    paid_render_approval_ref, design_prose_ref, visual_bible_ref, test_only, plus design_style_source
    and the derived executor_provider / allow_paid the adapters pass on.
    """
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
    if provider not in EXECUTABLE_PROVIDERS:
        raise ImagePlanError(
            "AF-LAUNCH-IMAGE-PLAN-PROVIDER", "image_plan.image_provider",
            f"The {provider} image service cannot draw these pages yet (Skill 71's stage executor has no "
            f"{provider} path). Nothing was sent and nothing was spent. Choose the standard service (kie) "
            "or ask for the integration to be added.")

    # Spend: a free run may default the cap; a paid run never does.
    approval = _clean_str(raw.get("paid_render_approval_ref"))
    cap = raw.get("image_cap")
    if cap is not None and not _is_unknown(cap):
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ImagePlanError("AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap",
                                 "must be a whole number of pictures, 1 or more")
    else:
        cap = None
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
        if cap is None:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-CAP", "image_plan.image_cap",
                "A real run spends money, so I need your ceiling: the most pictures you will pay for. "
                "I can estimate it from your page list if you'd like. I never pick this one for you.")
        if approval is None:
            raise ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-APPROVAL", "image_plan.paid_render_approval_ref",
                "A real run needs your written OK to spend on pictures. Nothing has been sent and nothing "
                "has been spent. Tell me when you approve the budget and I will record it.")
        executor, allow_paid = "kie", True

    inputs = {
        "design_style": style,
        "design_style_source": source,
        "brand_file": brand_file,
        "brand_owner": brand_owner,
        "image_cap": cap,
        "image_provider": provider,
        "paid_render_approval_ref": approval,
        "design_prose_ref": _clean_str(raw.get("design_prose_ref")),
        "visual_bible_ref": _clean_str(raw.get("visual_bible_ref")),
        "test_only": bool(test_only),
        "executor_provider": executor,
        "allow_paid": allow_paid,
    }
    return inputs, to_confirm


# The contract C3 keys, exactly what Skill 49's page_set.load_image_inputs accepts (it refuses any other key).
C3_KEYS = ("design_style", "brand_file", "brand_owner", "image_cap", "image_provider",
           "paid_render_approval_ref", "design_prose_ref", "visual_bible_ref", "test_only")


def image_inputs_file(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """The shared image inputs written to disk and bound into every Skill 49 wrapper: the C3 keys and
    nothing else. image_provider is the provider that really runs ("stub" on a free run)."""
    doc = {k: inputs[k] for k in C3_KEYS}
    doc["image_provider"] = inputs["executor_provider"]
    return doc


def order_page_inputs_file(inputs: Dict[str, Any], *, route_graph: str) -> Dict[str, Any]:
    """The same values in the shape Skill 78's run_image_stages.py reads (route_graph, provider, test_run).
    Skill 49's own page_set.selection_inputs makes this shape; kept here so the file is written
    before any Skill 49 module is loaded."""
    return {"route_graph": route_graph, "brand_file": inputs["brand_file"], "brand_owner": inputs["brand_owner"],
            "image_cap": inputs["image_cap"], "design_style": inputs["design_style"],
            "provider": inputs["executor_provider"], "test_run": bool(inputs["test_only"])}
