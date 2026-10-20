"""Single source of truth for the skill number, decisions, seams and skill paths.

SKILL_NUMBER is assigned: LAUNCH-04 recorded the availability evidence in
registration.json and set number_final true. Nothing outside this module may
spell the number or the directory name, so a rename is one edit.

Skill trees are named by BOTH conventions in the field: the onboarding repository
uses ``<number>-<slug>`` (``49-signature-funnel``), a 999 package uses the bare
slug (``signature-funnel``). ``resolve_skill_dir`` accepts either and fails
closed by name; nothing here or in any consumer spells a numbered directory.

DECIDED records the owner decisions LAUNCH-02b implements, each with the code
that carries it. SEAMS records what is still open. One decision is only partly
settled: the cross-sale surface ships, its teaching content does not exist yet,
so the seam stays open narrowed to the teaching source.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_NUMBER = "83"
SKILL_DIR_NAME = SKILL_NUMBER + "-black-friday-launcher"
SKILL_NAME = "black-friday-launcher"
SKILL_VERSION = "0.2.4"

# The Launcher's own tree, derived from this file's location and never from a
# directory name, so the skill works under either naming convention.
SKILL_ROOT = Path(__file__).resolve().parent.parent


def repo_root_for(start: Path | str) -> Path:
    """Nearest ancestor that looks like a checkout, for both layouts.

    The onboarding layout puts skills at the repo root; a deployed tree puts
    them under .claude/skills, so ``<skill>.parent`` is NOT the repository root
    there. Both layouts have shared-utils at the root, so that is the marker.
    Falls back to the skill's parent so a lone tree still works.
    """
    start = Path(start)
    for candidate in (start, *start.parents):
        if (candidate / "shared-utils").is_dir() and (
                (candidate / ".claude").is_dir() or (candidate / "CONTROL").is_dir()):
            return candidate
    return start.parent


REPO_ROOT = repo_root_for(SKILL_ROOT)

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

COUNCIL_SKILL_SLUG = "council-of-wise-elders"
COUNCIL_ENTRY_POINT = "scripts/doctor.mjs"

CHECKOUT_SKILL_SLUG = "signature-order-form"
CHECKOUT_CONTRACT_REF = "references/checkout.schema.json"
CHECKOUT_VALIDATOR_REF = "scripts/validate_checkout.py"

FUNNEL_SKILL_SLUG = "signature-funnel"
RECEIPT_MODULE_REF = "scripts/delegation_receipt.py"

# The skill slugs the Launcher binds. A reference whose first segment has one of
# these slugs is a skill tree and must resolve; anything else (shared-utils,
# 23-ai-workforce-blueprint, contracts) is an ordinary repository-relative path.
SKILL_SLUGS = (
    "signature-funnel",
    "blackceo-signature-page",
    "council-of-wise-elders",
    "signature-product-selection",
    "signature-order-form",
    "signature-upsell",
    "signature-downsell",
    "signature-thank-you",
    "black-friday-launcher",
)

_NUMERIC_PREFIX = re.compile(r"^(\d+)-(.+)$")


class SkillResolutionError(LookupError):
    """No directory on disk matches a skill slug. Fail closed, named."""


def skill_slug(name: str) -> str:
    """The slug a directory name carries: '49-signature-funnel' -> 'signature-funnel'."""
    match = _NUMERIC_PREFIX.match(name)
    return match.group(2) if match else name


def resolve_skill_dir(slug: str, root: Path | str | None = None) -> Path:
    """Resolve a skill slug to its directory under either naming convention.

    A candidate is any directory whose name is ``slug`` or ends with
    ``-<slug>``. An exact numeric ``<number>-<slug>`` wins when several exist;
    then the bare slug. No candidate raises SkillResolutionError, so a missing
    tree is one named error, never a FileNotFoundError deep in a caller.
    """
    base = Path(root) if root is not None else REPO_ROOT
    if not base.is_dir():
        raise SkillResolutionError(f"skill root {base} is not a directory")
    # Skills live at the repo root in the onboarding layout and under
    # .claude/skills in a deployed tree, so both bases are searched.
    bases = [base] + [base / sub for sub in (".claude/skills", "skills")]
    candidates = sorted(
        path for search in bases if search.is_dir()
        for path in search.iterdir()
        if path.is_dir() and (path.name == slug or path.name.endswith("-" + slug))
        and (path / "SKILL.md").is_file()
    )
    if not candidates:
        raise SkillResolutionError(
            f"no directory for skill slug {slug!r} under {base} "
            f"(accepted: {slug} or <number>-{slug})")
    numeric = [path for path in candidates
               if (match := _NUMERIC_PREFIX.match(path.name))
               and match.group(2) == slug]
    if numeric:
        return min(numeric, key=lambda path: (int(path.name.split("-", 1)[0]), path.name))
    bare = [path for path in candidates if path.name == slug]
    return (bare or candidates)[0]


def skill_path(slug: str, *parts: str, root: Path | str | None = None) -> Path:
    """The path to ``parts`` inside the resolved directory for ``slug``."""
    return resolve_skill_dir(slug, root).joinpath(*parts)


def resolve_ref(rel_path: str, root: Path | str | None = None) -> Path:
    """Resolve a repository-relative reference whose first segment names a skill.

    The first segment may be either convention. A known skill slug that does not
    resolve raises SkillResolutionError; a path that names no known skill is
    returned as a plain repository-relative path.
    """
    base = Path(root) if root is not None else REPO_ROOT
    # An already repository-relative path that exists wins, so callers may pass
    # a resolved path back in without it being re-interpreted.
    direct = base / str(rel_path)
    if direct.exists():
        return direct
    first, sep, rest = str(rel_path).partition("/")
    slug = skill_slug(first)
    if slug in SKILL_SLUGS:
        directory = resolve_skill_dir(slug, base)
        return directory / rest if sep else directory
    return base / rel_path

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
