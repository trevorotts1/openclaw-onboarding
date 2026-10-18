"""Single source of truth for the working skill number, decisions and seams.

SKILL_NUMBER is a WORKING PARAMETER. The launcher's number is unassigned today
(REQUIREMENTS.md section 1). Nothing outside this module may spell the number or
the directory name, so a rename is one edit.

DECIDED records the owner decisions LAUNCH-02b implements, each with the code
that carries it. SEAMS records what is still open. One decision is only partly
settled: the cross-sale surface ships, its teaching content does not exist yet,
so the seam stays open narrowed to the teaching source.
"""

from __future__ import annotations

SKILL_NUMBER = "83"  # WORKING PARAMETER - NOT a final assignment
SKILL_DIR_NAME = SKILL_NUMBER + "-black-friday-launcher"
SKILL_NAME = "black-friday-launcher"
SKILL_VERSION = "0.2.0"

SCHEMA_VERSION = "1.0"
PENDING_FAILED_PAYMENT_BEHAVIOR = "retain_current_purchase_state_until_resolved_or_explicit_decline"

ROUTE_ROLES = (
    "landing",
    "product_selection",
    "checkout",
    "upsell_1",
    "downsell_1",
    "upsell_2",
    "thank_you",
)
OFFER_ROLES = ("main", "bump", "upsell_1", "downsell_1", "upsell_2")
PAGE_STATUSES = (
    "authored",
    "locally_verified",
    "installed_test_verified",
    "ready_for_activation",
    "live_verified",
    "blocked",
)
PROOF_CLASSES = ("L0", "L1", "L2", "L3", "L4", "L5")

# folded_levels: N >= 2 distinct main offers folded into the signature page,
# straight to the native order form, no product_selection node. It never
# relabels the product as one offer. The older modes keep their exact meaning.
JOURNEY_MODES = ("single_simple", "multiple_options", "folded_levels")

# Offer relationship vocabulary. Cross-sale offers are expressed here, never as
# extra route nodes and never as invented teaching content.
OFFER_RELATION_KEYS = ("complements", "included_in", "requires")
CROSS_SALE_TEACHING_STATE = "pending"  # owner is supplying the teaching; not in hand

ENTITLEMENT_DECLARATION = "entitlement-declaration.json"
ENTITLEMENT_BASES = (
    "brand_management_membership",
    "purchase",
    "school_of_ai_membership",
    "zhc",
    "zhc_with_brand_management",
)

COUNCIL_SKILL_DIR = "77-council-of-wise-elders"
COUNCIL_ENTRY_POINT = "scripts/doctor.mjs"

CHECKOUT_SKILL_DIR = "79-signature-order-form"
CHECKOUT_CONTRACT = CHECKOUT_SKILL_DIR + "/references/checkout.schema.json"
CHECKOUT_VALIDATOR = CHECKOUT_SKILL_DIR + "/scripts/validate_checkout.py"

# Owner decisions implemented in LAUNCH-02b. No seam value lives here.
DECIDED = (
    {
        "id": "entitlement_declaration_and_attestation",
        "decision": "entitlement is a declaration the skill carries plus a "
                    "fail-closed attestation gate; Brand Management membership "
                    "qualifies without a purchase, others buy at the owner's "
                    "stated price, School of AI alone and ZHC alone do not qualify",
        "coded_in": "launcher_core/entitlement.py + entitlement-declaration.json",
    },
    {
        "id": "council_included_in_launch_planning",
        "decision": "Council advice is included in launch planning through the "
                    "Skill 77 entry point; a not-ready result is recorded and "
                    "never blocks the build; advice is never permission",
        "coded_in": "launcher_core/council.py",
    },
    {
        "id": "native_converted_and_flow_checkout_mapping",
        "decision": "checkout stays the native Convert and Flow form installed "
                    "by Skill 06, bound to the Skill 79 order-form contract; it "
                    "is never a dispatch adapter",
        "coded_in": "launcher_core/checkout.py + routes/adapters.py",
    },
    {
        "id": "verified_offer_facts_only",
        "decision": "verified offer facts are reused; a price, level or "
                    "entitlement that is defaulted rather than supplied or "
                    "marked unknown fails the build",
        "coded_in": "launcher_core/intake.py + launcher_core/checks.py",
    },
    {
        "id": "folded_levels_journey_mode",
        "decision": "folded_levels is a journey mode: N >= 2 main offers folded "
                    "into the signature page, no product_selection page, never "
                    "relabelled a single offer",
        "coded_in": "launcher_core/route.py + "
                    "49-signature-funnel/scripts/compile_launch_route.py",
    },
)
DECIDED_IDS = tuple(d["id"] for d in DECIDED)

# Still open. Each is ONE named seam; no seam carries a value here.
SEAMS = (
    {
        "id": "distribution_run_target",
        "decision": "installed into the customer's own OpenClaw/999, or run inside BlackCEO's",
        "code_seam": "registration.json:distribution + SKILL.md Entry",
    },
    {
        "id": "cross_sales_teaching_source",
        "decision": "which cross-sale teaching content ships; the relationship "
                    "surface itself is decided and present",
        "code_seam": "launcher_core/route.py:launch_record (teaching state is "
                     "recorded as pending, never invented)",
    },
)
SEAM_IDS = tuple(s["id"] for s in SEAMS)

# Placeholder-shaped bindings that must never ship as executable configuration.
PLACEHOLDER_TOKENS = (
    "/path/to",
    "<",
    ">",
    "{{",
    "}}",
    "todo",
    "tbd",
    "changeme",
    "change-me",
    "placeholder",
    "your-",
    "your_",
    "xxx",
    "replace-me",
    "replace_me",
    "example.com",
)
