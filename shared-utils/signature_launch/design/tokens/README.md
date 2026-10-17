# Design tokens

**Component:** `design-tokens` v1.0.0 · **Owner:** S71 · **Implements:** doc 16 §1 (component inventory, "Launch design tokens and brand loader") and doc 16 §2 (brand source of truth).

## Purpose

Resolve one client's approved brand file into the shared design token
document every Signature Launch page consumes, so pages share one
versioned client brand instead of arbitrary per-page palettes.

## Inputs

A parsed brand record (dict) in the Skill 71 brand file form
(`71-blackceo-signature-page/assets/brand/brand.schema.json`):
`palette{gold, navy, cream}`, `logo_only_colors{black, white}`,
`color_tolerance`, `fonts{display, body, accent}`, `banned_fonts`,
`font_policy`, `logo{files, masthead_files}`, `founder_photos`,
`people_rule`, `default_creative_direction`, `page_design_rules`,
`banned_page_patterns`.

A value that is absent, empty, or a `*_MUST_SUPPLY` sentinel
(`TREVOR_MUST_SUPPLY` / `CLIENT_MUST_SUPPLY`) is **missing data**.

## Outputs

`resolve_tokens(brand)` returns the token document described by
`tokens.schema.json`:

- `colors` — role tokens (`accent` from `palette.gold`,
  `ground_dark` from `palette.navy`, `ground_light` from
  `palette.cream`, `logo_black` / `logo_white` from
  `logo_only_colors`) plus the raw brand palette verbatim, so consumers
  are not forced through the role mapping.
- `typography` — brand font names plus the brand's `banned_fonts` list
  and `font_policy`, carried through untouched.
- `assets` — logo/masthead/founder-photo references as recorded.
- `spacing` / `radii` — design-library default scales. The brand file
  form carries no spacing fields, so these are component-owned defaults,
  labeled `source: "library_default"`; they are never presented as
  client brand values.
- `rules` — people rule, creative direction, page design rules and
  banned page patterns from the brand file.
- `missing` — every brand-sourced field that is absent or a sentinel,
  as `{field, state: "must_supply"}`.
- `complete` — `true` only when nothing brand-sourced is missing.

`tokens_to_css(resolution)` renders a `:root` block of `--sl-*` custom
properties. Only resolved values are emitted: a missing brand value
produces **no** variable, so components fall back to inherited page
styling rather than an invented brand value.

## Failure behavior

Missing brand data is never invented: no fallback palette, no default
font name, no lookalike logo or person. Font derivation, when the
brand's `font_policy` allows it, is a separate documented workflow
(rationale + reviewer) owned by the page skill; this component only
reports the missing state.

## Tests

`tests/test_tokens.py` (stdlib unittest): tokens resolve from a fixture
brand; a second, different brand resolves to its own values (nothing is
hardcoded to one client); sentinel values resolve to `None` and are
named in `missing`; CSS output omits unresolved variables.
