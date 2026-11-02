"""Eighteen canonical style -> recipe/template target rows (C05).

One row per catalog style, in ``catalog.STYLE_IDS`` order. A row names the
owner artifact that holds the executable recipe and the compiler that renders
the provider style field. This is a map, not a second menu: labels,
descriptions, order and availability stay in ``catalog.py`` and the card / help
surfaces read that catalog.

Owner rows (verified against the current canonical files):
  originals 3 ....... music_styles.STYLES[*].suno_style_prompt
  T19 additions 5 ... music_styles/recipes/<id>.json via recipes.compile_style_prompt
  T20 additions 3 ... music_styles.RECIPES via music_styles.style_prompt
  T21 additions 3 ... recipes_s75_t21.compile_style
  T22 additions 4 ... recipes_s75_t22.compile_style_field

The three originals and the six T20/T21/T22 records also resolve through
``music_styles.style_prompt``; the T19 JSON recipes and the T21/T22 module
records do NOT (they live outside ``music_styles.STYLES``/``RECIPES``). The
per-row ``provider_compiler`` says which one actually owns the record.

``variant_coverage()`` reports the real song-request consumer, read from the
shared file rather than assumed: ``song_choices/variants.json`` currently has
three keys, so the fifteen added styles have no three-brief request set yet.
That is a shared-caller gap (I-owned), reported, never patched here.
"""
from __future__ import annotations

import copy
import json
import os

TARGET_SCHEMA = "blackceo.music-style-target-map/v1"
_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARIANTS_FILE = os.path.join(_CORE, "song_choices", "variants.json")
CATALOG_HINT = "music_styles.catalog.provider_hint"


def _row(index, owner, record_source, provider_compiler, template_kind,
         original_three=False):
    return {
        "selection_index": index,
        "style_id": None,                       # filled below, never guessed
        "owner": owner,
        "record_source": record_source,
        "provider_compiler": provider_compiler,
        "template_kind": template_kind,
        "catalog_hint": CATALOG_HINT,
        "variant_source": "song_choices/variants.json",
        "original_three": bool(original_three),
    }


_T19 = "music_styles.recipes"
_T19_SRC = "scripts/core/music_styles/recipes/%s.json"

#: ``(style_id, row)`` in catalog order. The order is asserted against the
#: catalog at call time by ``validate()``; a drifted map is refused, never
#: silently reordered.
_ROWS = (
    ("soul-ballad", _row(1, "music_styles.STYLES",
                         "scripts/core/music_styles/music_styles.py",
                         "music_styles.style_prompt", "inline_prompt", True)),
    ("rnb-flow", _row(2, "music_styles.STYLES",
                      "scripts/core/music_styles/music_styles.py",
                      "music_styles.style_prompt", "inline_prompt", True)),
    ("soul-rise", _row(3, "music_styles.STYLES",
                       "scripts/core/music_styles/music_styles.py",
                       "music_styles.style_prompt", "inline_prompt", True)),
    ("acoustic-pop", _row(4, _T19, _T19_SRC % "acoustic-pop",
                          "music_styles.recipes.compile_style_prompt",
                          "recipe_json")),
    ("folk-storytelling", _row(5, _T19, _T19_SRC % "folk-storytelling",
                               "music_styles.recipes.compile_style_prompt",
                               "recipe_json")),
    ("country-pop", _row(6, _T19, _T19_SRC % "country-pop",
                         "music_styles.recipes.compile_style_prompt",
                         "recipe_json")),
    ("melodic-rap", _row(7, "music_styles.RECIPES",
                         "scripts/core/music_styles/music_styles.py",
                         "music_styles.style_prompt", "recipe_record")),
    ("trap-rap", _row(8, "music_styles.RECIPES",
                      "scripts/core/music_styles/music_styles.py",
                      "music_styles.style_prompt", "recipe_record")),
    ("pop-rap", _row(9, "music_styles.RECIPES",
                     "scripts/core/music_styles/music_styles.py",
                     "music_styles.style_prompt", "recipe_record")),
    ("pop-rock", _row(10, "music_styles.recipes_s75_t21",
                      "scripts/core/music_styles/recipes_s75_t21.py",
                      "music_styles.recipes_s75_t21.compile_style",
                      "recipe_module")),
    ("reggaeton", _row(11, "music_styles.recipes_s75_t21",
                       "scripts/core/music_styles/recipes_s75_t21.py",
                       "music_styles.recipes_s75_t21.compile_style",
                       "recipe_module")),
    ("cinematic-orchestral-song", _row(
        12, "music_styles.recipes_s75_t22",
        "scripts/core/music_styles/recipes_s75_t22.py",
        "music_styles.recipes_s75_t22.compile_style_field", "recipe_module")),
    ("musical-theater", _row(
        13, "music_styles.recipes_s75_t22",
        "scripts/core/music_styles/recipes_s75_t22.py",
        "music_styles.recipes_s75_t22.compile_style_field", "recipe_module")),
    ("contemporary-gospel", _row(
        14, "music_styles.recipes_s75_t22",
        "scripts/core/music_styles/recipes_s75_t22.py",
        "music_styles.recipes_s75_t22.compile_style_field", "recipe_module")),
    ("urban-gospel", _row(
        15, "music_styles.recipes_s75_t22",
        "scripts/core/music_styles/recipes_s75_t22.py",
        "music_styles.recipes_s75_t22.compile_style_field", "recipe_module")),
    ("alternative-rnb", _row(16, _T19, _T19_SRC % "alternative-rnb",
                             "music_styles.recipes.compile_style_prompt",
                             "recipe_json")),
    ("afro-soul", _row(17, _T19, _T19_SRC % "afro-soul",
                       "music_styles.recipes.compile_style_prompt",
                       "recipe_json")),
    ("country-rap", _row(18, "music_styles.recipes_s75_t21",
                         "scripts/core/music_styles/recipes_s75_t21.py",
                         "music_styles.recipes_s75_t21.compile_style",
                         "recipe_module")),
)

for _sid, _r in _ROWS:
    _r["style_id"] = _sid

TARGETS = {sid: row for sid, row in _ROWS}
if len(TARGETS) != 18:
    raise ImportError("target map must hold exactly 18 unique style ids")


def style_ids():
    """The mapped style ids in catalog order."""
    return tuple(sid for sid, _ in _ROWS)


def target(style_id):
    """Deep copy of one row; unknown id is a named refusal."""
    try:
        return copy.deepcopy(TARGETS[style_id])
    except KeyError:
        raise ValueError("UNKNOWN_STYLE_TARGET: %r is not one of the 18 mapped "
                         "styles" % (style_id,))


def as_rows():
    """Every row, catalog order, deep copies."""
    return [copy.deepcopy(TARGETS[sid]) for sid in style_ids()]


def validate(catalog=None):
    """Return 18 after proving the map matches the catalog owner of record.

    Refuses a drifted order, a missing/extra id, or an empty owner/compiler.
    Imports the catalog only when the caller does not pass one.
    """
    if catalog is None:
        from music_styles import catalog as catalog
    expected = tuple(catalog.STYLE_IDS)
    got = style_ids()
    if got != expected:
        raise ValueError("STYLE_TARGET_ORDER_DRIFT: map %r != catalog %r"
                         % (list(got), list(expected)))
    for sid in got:
        row = TARGETS[sid]
        if (not row["owner"] or not row["record_source"]
                or not row["provider_compiler"] or not row["template_kind"]):
            raise ValueError("STYLE_TARGET_INCOMPLETE: %s has an empty field" % sid)
        if row["style_id"] != sid:
            raise ValueError("STYLE_TARGET_ID_MISMATCH: %r" % sid)
    return len(got)


def variant_coverage(path=None):
    """The real three-brief coverage of the shared song caller.

    Reads ``song_choices/variants.json`` (never a copy). The ``_note`` key is
    metadata, not a style. Returns the style ids present, the mapped ids still
    missing, and whether every mapped style has its three-brief set.
    """
    with open(path or VARIANTS_FILE, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError("VARIANTS_UNREADABLE: expected an object")
    present = tuple(k for k in doc if k != "_note")
    missing = tuple(sid for sid in style_ids() if sid not in present)
    return {"present": present, "missing": missing,
            "complete": not missing,
            "note": "three COMPLETE briefs per style; shared caller I-owned"}
