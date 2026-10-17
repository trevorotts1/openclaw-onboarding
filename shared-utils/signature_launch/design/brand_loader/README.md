# Brand loader

**Component:** `brand-loader` v1.0.0 · **Owner:** S71 · **Implements:** doc 16 §1 (component inventory, "Launch design tokens and brand loader") and doc 16 §2 (brand source of truth).

## Purpose

Load the current launch's client brand file — the only brand authority —
and resolve it into design tokens (see `../tokens/`) for every page
component. Different clients load their own approved brand file; nothing
about one client's palette, fonts, logo or people rules is assumed for
another.

## Inputs

A path to a brand file in the Skill 71 brand file form
(`71-blackceo-signature-page/assets/brand/brand.schema.json`,
exemplified by `assets/brand/blackceo-brand.json` and
`assets/brand/client-brand.template.json`).

## Outputs

- `load_brand(path)` → the parsed, structurally validated brand dict.
- `load_brand_tokens(path)` → the token resolution document from
  `tokens.resolve_tokens()` (see `../tokens/README.md` and
  `../tokens/tokens.schema.json`), including its `missing` list and
  `complete` flag.

## Documented failure mode for missing brand data

Two distinct levels, never blurred:

1. **Structural failure** — raised as `BrandLoadError` with a
   `problems` list naming every cause: file not found or unreadable;
   invalid JSON; top level not an object; any required top-level key
   absent (`brand_id`, `source`, `palette`, `logo_only_colors`,
   `color_tolerance`, `fonts`, `banned_fonts`, `logo`, `founder_photos`,
   `people_rule`, `default_creative_direction`, `grade`,
   `page_design_rules`, `banned_page_patterns`); any required nested key
   absent (`palette.gold/navy/cream`, `logo_only_colors.black/white`,
   `fonts.display/body/accent`, `logo.files/masthead_files`).
2. **Missing values** — a present key whose value is absent, empty, or
   a `*_MUST_SUPPLY` sentinel is *not* a load failure. The brand loads;
   the token resolution reports the field in `missing` and sets the
   affected token to `None`.

In neither case does the loader invent a value: no fallback palette, no
default font, no lookalike logo or founder photo. Callers must treat a
`None` token / non-empty `missing` list as an explicit blocker or route
it through the brand's own documented policy (for fonts, the brand
file's `font_policy` derive-document workflow, which lives with the
page skill, not here).

## Tests

`tests/test_brand_loader.py` (stdlib unittest): a complete fixture
brand loads and resolves completely; an incomplete fixture brand loads
with its sentinel fields reported missing and its tokens `None` (never
substituted); a fixture missing a required key, a malformed file, and a
nonexistent path each raise `BrandLoadError`.
