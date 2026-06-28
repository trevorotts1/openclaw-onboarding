"""
canonical_slug.py — Department identity contract for the Zero Human Company system.

PRD item 1.5: department_id == canonical slug (lowercase, hyphenated, no dept- prefix).

This module is the Python counterpart to src/lib/routing/canonical-slug.ts in the
Command Center (blackceo-command-center repo).  BOTH sides must produce the same
output for the same input.  The TypeScript implementation is the authoritative
spec; this file mirrors it in Python for use by:

  - persona-selector-v2.py   (normalises --department arg before DB writes)
  - sync-md-content-to-db.py  (normalises department key used to look up agents rows)
  - seed-workspaces.py        (replaces the raw_id[5:] hack)
  - build-workforce.py        (normalises the slug field in departments.json)

CONTRACT (see TERMINOLOGY.md §Department Identity Contract):
  department_id == canonical slug
    - all lowercase
    - words separated by hyphens (not underscores, not spaces)
    - NO "dept-" prefix
    - NO "-dept" suffix
    - stripped of leading / trailing whitespace

Examples
--------
  canonical_dept_slug("Dept-Marketing")   -> "marketing"
  canonical_dept_slug("Marketing")        -> "marketing"
  canonical_dept_slug("Sales")            -> "sales"
  canonical_dept_slug("Billing Finance")  -> "billing-finance"
  canonical_dept_slug("billing_finance")  -> "billing-finance"
  canonical_dept_slug("dept-sales")       -> "sales"
  canonical_dept_slug("dept-Marketing")   -> "marketing"
  canonical_dept_slug("marketing-dept")   -> "marketing"
  canonical_dept_slug("General Task")     -> "general-task"
  canonical_dept_slug("")                 -> ""

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from canonical_slug import canonical_dept_slug

    dept_id = canonical_dept_slug(raw_dept_id)

"""

import re

# ---------------------------------------------------------------------------
# ALIAS MAP — maps non-canonical slugs to their canonical slug AFTER the
# standard normalization steps (strip dept-, lowercase, hyphens).
# Mirrors ALIAS_MAP in command-center canonical-slug.ts (both must stay in
# sync — TypeScript side is the authoritative spec).
# ---------------------------------------------------------------------------
ALIAS_MAP: dict = {
    # CEO / master-orchestrator variants
    "ceo":                  "master-orchestrator",
    "ceo-com":              "master-orchestrator",
    "com":                  "master-orchestrator",
    "central-operations":   "master-orchestrator",

    # billing variants
    "billing":              "billing-finance",

    # web-dev variants
    "webdev":               "web-development",
    "web-dev":              "web-development",
    "web":                  "web-development",

    # engineering / software-dev variants (UNIT ENG — 2026-06-28)
    "software-development": "engineering",
    "software-dev":         "engineering",
    "app-development":      "engineering",
    "apps":                 "engineering",

    # video variants
    "video-production":     "video",

    # audio variants
    "audio-production":     "audio",

    # legal variants
    "legal-compliance":     "legal",
    "compliance":           "legal",

    # customer-support variants
    "support":              "customer-support",
    "customer-service":     "customer-support",

    # social-media variants
    "social":               "social-media",

    # paid-advertisement variants
    "paid-ads":             "paid-advertisement",
    "paid-advertising":     "paid-advertisement",

    # openclaw-maintenance variants
    "openclaw":             "openclaw-maintenance",

    # general-task aliases
    "general":              "general-task",
    "misc":                 "general-task",
    "catch-all":            "general-task",
    "catchall":             "general-task",
    "unclassified":         "general-task",
}


def canonical_dept_slug(raw: str) -> str:
    """
    Normalise a raw department name or id to the canonical slug form.

    Steps (mirrors canonical-slug.ts canonicalDeptSlug):
      1. Strip leading/trailing whitespace.
      2. Lowercase.
      3. Strip a leading "dept-" prefix (case-insensitive, already lowercased).
      4. Strip a trailing "-dept" suffix.
      5. Replace underscores and spaces with hyphens.
      6. Collapse multiple consecutive hyphens to one.
      7. Strip leading/trailing hyphens.

    Returns an empty string if the input normalises to nothing.
    """
    if not raw or not isinstance(raw, str):
        return ""

    s = raw.strip().lower()

    # Strip "dept-" prefix
    if s.startswith("dept-"):
        s = s[5:]

    # Strip "-dept" suffix
    if s.endswith("-dept"):
        s = s[:-5]

    # Replace spaces and underscores with hyphens
    s = s.replace(" ", "-").replace("_", "-")

    # Collapse multiple consecutive hyphens
    s = re.sub(r"-{2,}", "-", s)

    # Strip leading/trailing hyphens
    s = s.strip("-")

    # Alias map lookup (mirrors canonical-slug.ts ALIAS_MAP)
    if s in ALIAS_MAP:
        s = ALIAS_MAP[s]

    return s


def is_canonical_dept_slug(value: str) -> bool:
    """
    Return True if *value* is already in canonical form (idempotent check).

    Useful for assertion guards in scripts that want to fail loudly when they
    receive a non-canonical department id.

    Examples:
      is_canonical_dept_slug("marketing")        -> True
      is_canonical_dept_slug("dept-marketing")   -> False
      is_canonical_dept_slug("Marketing")        -> False
      is_canonical_dept_slug("billing-finance")  -> True
    """
    return value == canonical_dept_slug(value)


if __name__ == "__main__":
    # Quick self-test — run as: python3 canonical_slug.py
    cases = [
        ("Dept-Marketing",      "marketing"),
        ("Marketing",           "marketing"),
        ("Sales",               "sales"),
        ("Billing Finance",     "billing-finance"),
        ("billing_finance",     "billing-finance"),
        ("dept-sales",          "sales"),
        ("dept-Marketing",      "marketing"),
        ("marketing-dept",      "marketing"),
        ("General Task",        "general-task"),
        ("general-task",        "general-task"),
        ("",                    ""),
        ("  Sales  ",           "sales"),
        ("dept-",               ""),
        ("-dept",               ""),
        # engineering aliases (UNIT ENG)
        ("software-development","engineering"),
        ("software-dev",        "engineering"),
        ("app-development",     "engineering"),
        ("apps",                "engineering"),
        ("engineering",         "engineering"),
    ]
    all_pass = True
    for raw, expected in cases:
        got = canonical_dept_slug(raw)
        status = "PASS" if got == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  [{status}] canonical_dept_slug({raw!r}) => {got!r}  (expected {expected!r})")

    print()
    print("All tests PASSED" if all_pass else "SOME TESTS FAILED")
    import sys
    sys.exit(0 if all_pass else 1)
