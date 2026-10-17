"""Launch design tokens: resolve a client brand file into design tokens.

Owner: S71. Implements doc 16 section 1 (component inventory: "Launch
design tokens and brand loader") and section 2 (brand source of truth:
the resolver supplies colors, typography, logo/wordmark assets, founder
portraits, spacing/shape rules, voice, image direction and permitted
component variants).

Input is a brand record in the Skill 71 brand file form
(71-blackceo-signature-page/assets/brand/brand.schema.json): palette,
logo_only_colors, fonts, logo, founder_photos, page_design_rules and so
on. Values equal to a ``*_MUST_SUPPLY`` sentinel (TREVOR_MUST_SUPPLY,
CLIENT_MUST_SUPPLY), empty strings and absent keys are MISSING data.
Missing values are reported in the resolution's ``missing`` list and the
corresponding tokens are ``None``. This module never invents a brand
value: no fallback palette, no default font name, no lookalike asset.

Spacing and radius scales are design-library defaults owned by this
component (the brand file form carries no spacing fields); they are
labeled ``library_default`` in the resolution so nobody mistakes them
for client brand values.

Deterministic, standard library only.
"""

import json

TOKEN_VERSION = "1.0.0"
COMPONENT_NAME = "design-tokens"
COMPONENT_OWNER = "S71"

_MISSING_SUFFIX = "_MUST_SUPPLY"

# Design-library defaults (NOT brand values). The brand file form has no
# spacing/shape fields, so the shared component library owns this scale
# until a brand schema migration adds brand-supplied values.
LIBRARY_SPACING = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2.5rem",
    "section": "4rem",
}
LIBRARY_RADII = {
    "sm": "4px",
    "md": "8px",
    "lg": "16px",
    "pill": "999px",
}


def is_missing(value):
    """True when a brand value is absent or a *_MUST_SUPPLY sentinel."""
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        if stripped.endswith(_MISSING_SUFFIX):
            return True
    return False


def _value_or_none(value):
    return None if is_missing(value) else value


def _collect_missing(brand):
    missing = []

    def note(field, value):
        if is_missing(value):
            missing.append({"field": field, "state": "must_supply"})

    palette = brand.get("palette") or {}
    for key in ("gold", "navy", "cream"):
        note("palette." + key, palette.get(key))
    logo_only = brand.get("logo_only_colors") or {}
    for key in ("black", "white"):
        note("logo_only_colors." + key, logo_only.get(key))
    fonts = brand.get("fonts") or {}
    for key in ("display", "body", "accent"):
        note("fonts." + key, fonts.get(key))
    logo = brand.get("logo") or {}
    note("logo.files", logo.get("files"))
    note("logo.masthead_files", logo.get("masthead_files"))
    note("founder_photos", brand.get("founder_photos"))
    note("people_rule", brand.get("people_rule"))
    return missing


def resolve_tokens(brand):
    """Resolve a brand record (dict) into the shared token document.

    Returns a dict with: brand_id, token_version, colors (role tokens +
    the raw brand palette), typography, assets, spacing, radii, rules,
    missing (every brand-sourced value that is absent/sentinel) and
    complete (True only when no brand-sourced value is missing).
    Unresolved tokens are None, never substituted.
    """
    if not isinstance(brand, dict):
        raise TypeError("brand must be a dict (parsed brand file)")

    palette = brand.get("palette") or {}
    logo_only = brand.get("logo_only_colors") or {}
    fonts = brand.get("fonts") or {}
    logo = brand.get("logo") or {}
    missing = _collect_missing(brand)

    colors = {
        # Role tokens mapped from the brand palette keys. The brand file
        # form fixes the palette keys (gold/navy/cream); the page design
        # rules in that same form name gold the accent/CTA color and
        # navy/cream the alternating grounds.
        "accent": _value_or_none(palette.get("gold")),
        "ground_dark": _value_or_none(palette.get("navy")),
        "ground_light": _value_or_none(palette.get("cream")),
        "logo_black": _value_or_none(logo_only.get("black")),
        "logo_white": _value_or_none(logo_only.get("white")),
        # Raw brand palette, exposed verbatim so consumers are not
        # forced through the role mapping.
        "palette": {k: _value_or_none(v) for k, v in palette.items()},
        "logo_only": {k: _value_or_none(v) for k, v in logo_only.items()},
        "color_tolerance": brand.get("color_tolerance"),
    }
    typography = {
        "display": _value_or_none(fonts.get("display")),
        "body": _value_or_none(fonts.get("body")),
        "accent": _value_or_none(fonts.get("accent")),
        "banned_fonts": list(brand.get("banned_fonts") or []),
        "font_policy": brand.get("font_policy"),
    }
    assets = {
        "logo_files": _value_or_none(logo.get("files")),
        "masthead_files": _value_or_none(logo.get("masthead_files")),
        "founder_photos": _value_or_none(brand.get("founder_photos")),
    }
    rules = {
        "people_rule": _value_or_none(brand.get("people_rule")),
        "creative_direction": brand.get("default_creative_direction"),
        "page_design_rules": list(brand.get("page_design_rules") or []),
        "banned_page_patterns": list(brand.get("banned_page_patterns") or []),
    }
    return {
        "brand_id": brand.get("brand_id"),
        "token_version": TOKEN_VERSION,
        "component": COMPONENT_NAME,
        "owner": COMPONENT_OWNER,
        "colors": colors,
        "typography": typography,
        "assets": assets,
        "spacing": {"source": "library_default", "scale": dict(LIBRARY_SPACING)},
        "radii": {"source": "library_default", "scale": dict(LIBRARY_RADII)},
        "rules": rules,
        "missing": missing,
        "complete": not missing,
    }


_CSS_COLOR_VARS = (
    ("--sl-color-accent", "accent"),
    ("--sl-color-ground-dark", "ground_dark"),
    ("--sl-color-ground-light", "ground_light"),
    ("--sl-color-logo-black", "logo_black"),
    ("--sl-color-logo-white", "logo_white"),
)
_CSS_FONT_VARS = (
    ("--sl-font-display", "display"),
    ("--sl-font-body", "body"),
    ("--sl-font-accent", "accent"),
)


def tokens_to_css(resolution):
    """Render resolved tokens as a CSS :root custom-property block.

    Only resolved (non-None) values are emitted. A missing brand value
    produces NO variable, so a component falls back to inherited page
    styling instead of a silently invented brand value.
    """
    lines = [":root {"]
    colors = resolution.get("colors") or {}
    for var, key in _CSS_COLOR_VARS:
        value = colors.get(key)
        if value is not None:
            lines.append("  %s: %s;" % (var, value))
    typography = resolution.get("typography") or {}
    for var, key in _CSS_FONT_VARS:
        value = typography.get(key)
        if value is not None:
            lines.append('  %s: "%s";' % (var, value))
    spacing = (resolution.get("spacing") or {}).get("scale") or {}
    for key in ("xs", "sm", "md", "lg", "xl", "section"):
        if key in spacing:
            lines.append("  --sl-space-%s: %s;" % (key, spacing[key]))
    radii = (resolution.get("radii") or {}).get("scale") or {}
    for key in ("sm", "md", "lg", "pill"):
        if key in radii:
            lines.append("  --sl-radius-%s: %s;" % (key, radii[key]))
    lines.append("}")
    return "\n".join(lines) + "\n"


def resolution_to_json(resolution):
    """Stable JSON rendering of a token resolution (sorted keys)."""
    return json.dumps(resolution, indent=2, sort_keys=True) + "\n"
