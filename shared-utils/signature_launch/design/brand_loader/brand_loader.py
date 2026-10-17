"""Brand loader: load a client brand file and resolve its design tokens.

Owner: S71. Implements doc 16 section 1 ("Launch design tokens and
brand loader") and section 2 (brand source of truth: "Load the current
launch's brand file and revision... Missing required assets remain
missing; do not invent lookalike logos or people.").

Failure modes (documented, all raised as BrandLoadError with a
``problems`` list, never as substituted values):

- file does not exist or cannot be read;
- file is not valid JSON, or its top level is not an object;
- a required top-level key of the brand file form is absent
  (brand.schema.json ``required`` list);
- a required nested key is absent (palette.gold/navy/cream,
  logo_only_colors.black/white, fonts.display/body/accent,
  logo.files/masthead_files).

Sentinel values (*_MUST_SUPPLY) and empty strings are NOT load
failures: the brand loads, and the token resolution reports those
fields in its ``missing`` list with the affected tokens set to None.
The loader never invents a brand value to fill them.

Deterministic, standard library only. The tokens module is loaded by
file path so this module works both as a package member and standalone,
matching how shared-utils modules are consumed in this repository.
"""

import importlib.util
import json
import os

COMPONENT_NAME = "brand-loader"
COMPONENT_VERSION = "1.0.0"
COMPONENT_OWNER = "S71"

REQUIRED_TOP_LEVEL = (
    "brand_id", "source", "palette", "logo_only_colors", "color_tolerance",
    "fonts", "banned_fonts", "logo", "founder_photos", "people_rule",
    "default_creative_direction", "grade", "page_design_rules",
    "banned_page_patterns",
)
REQUIRED_NESTED = (
    ("palette", ("gold", "navy", "cream")),
    ("logo_only_colors", ("black", "white")),
    ("fonts", ("display", "body", "accent")),
    ("logo", ("files", "masthead_files")),
)


def _load_tokens_module():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "tokens", "tokens.py")
    spec = importlib.util.spec_from_file_location("sl_design_tokens", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BrandLoadError(Exception):
    """A brand file could not be loaded; ``problems`` names every cause."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def validate_brand(brand):
    """Return the list of structural problems with a parsed brand record.

    An empty list means the record carries every required key of the
    brand file form. Sentinel/empty VALUES are not structural problems;
    they surface later as unresolved tokens (see tokens.resolve_tokens).
    """
    problems = []
    if not isinstance(brand, dict):
        return ["brand record is not a JSON object"]
    for key in REQUIRED_TOP_LEVEL:
        if key not in brand:
            problems.append("missing required key: %s" % key)
    for parent, keys in REQUIRED_NESTED:
        sub = brand.get(parent)
        if not isinstance(sub, dict):
            if parent in brand:
                problems.append("%s is not an object" % parent)
            continue
        for key in keys:
            if key not in sub:
                problems.append("missing required key: %s.%s" % (parent, key))
    return problems


def load_brand(path):
    """Read and structurally validate a brand file. Returns the dict.

    Raises BrandLoadError listing every problem found. Never returns a
    partially invented brand.
    """
    if not os.path.isfile(path):
        raise BrandLoadError(["brand file not found: %s" % path])
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise BrandLoadError(["brand file unreadable: %s (%s)" % (path, exc)])
    try:
        brand = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BrandLoadError(["brand file is not valid JSON: %s (%s)" % (path, exc)])
    problems = validate_brand(brand)
    if problems:
        raise BrandLoadError(problems)
    return brand


def load_brand_tokens(path):
    """Load a brand file and resolve its design tokens in one call.

    Returns the tokens.resolve_tokens() document. Its ``missing`` list
    and ``complete`` flag are the documented failure surface for absent
    brand data: unresolved tokens are None, never substituted.
    """
    tokens = _load_tokens_module()
    brand = load_brand(path)
    return tokens.resolve_tokens(brand)
