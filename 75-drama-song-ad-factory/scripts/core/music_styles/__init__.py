"""music_styles package: D18 music styles + D15 spoken-share targets.

The three styles offered on the approval card, each with its Suno style
prompt, its song-brief sound description, and the spoken-share target it
carries (D15 retarget: target 22.5% of runtime (20-25), redo past 10 points, identical
for every length and every style, rap counted as spoken-style delivery;
first real singing targeted at 15% of runtime). The earlier 40-70% band and the
per-length targets are retired -- the numbers come from core/spoken_share.
stdlib only, no network, no paid calls.

Consumed by core/style_defaults (V2B-AUDIO-U5) through style_prompt().
Voice gender is not decided here: that is core/audio_c3 (V2B-AUDIO-U1).
"""
from .music_styles import (
    DELIVERIES,
    FIRST_SUNG_TARGET_PCT,
    LENGTH_ALIASES,
    OFFERED_LENGTHS_S,
    SCHEMA_VERSION,
    SPOKEN_SHARE_MAX,
    SPOKEN_SHARE_MIN,
    SPOKEN_SHARE_TARGET,
    SECTION_HINTS,
    SOURCE_D15,
    SOURCE_D18,
    SPOKEN_STYLE_DELIVERIES,
    STYLES,
    CONTRADICTING_NEGATIVE_TAGS,
    DELIVERY_MAP_CLAUSES,
    DELIVERY_MAP_TEMPLATE,
    DELIVERY_MAP_VERBS,
    EXPLICIT_NEVER_INFERRED,
    RAP_RECIPE_REVISION,
    RECIPES,
    SOURCE_S75_T20,
    TOOL_NAME,
    TOOL_VERSION,
    MusicStyleError,
    assert_delivery_map,
    assert_no_contradiction,
    default_delivery_map,
    delivery_map,
    enables_explicit_lyrics,
    extra_style_ids,
    has_delivery_map,
    missing_delivery_verbs,
    recipe,
    recipe_ids,
    sheet_deliveries,
    check_first_sung,
    check_share,
    d15_range,
    measure_share,
    refusal,
    register_styles,
    section_hint,
    share_pct,
    spoken_target,
    spoken_targets,
    style,
    style_prompt,
    style_prompt_record,
)

def style_ids():
    """The full offered menu of record: the D18 three, the S75-T20 rap
    recipes, then the S75-CATALOG/S75-T22 registered extras, in that order."""
    from .music_styles import EXTRA_STYLES, RECIPES, STYLES
    return tuple(STYLES) + tuple(RECIPES) + tuple(EXTRA_STYLES)

#: S75-CATALOG (classes T20 r2 / T22 r3 / T23 conformance): every catalog
#: addition is a registered offered style. The 15 additions come from the
#: catalog owner's records (music_styles.catalog), with the compiled
#: provider field per family: the five story-first styles from recipes.py,
#: the four orchestral / theater / gospel recipes from recipes_s75_t22.py,
#: and the trait-only remainder from catalog.provider_hint(). The three
#: original D18 records and their prompts stay byte-identical.
#: Display-only client_references ride the record for client help surfaces
#: (style_help) and are never serialized by the provider compilers.
from . import catalog as _catalog                 # noqa: E402
from . import recipes as _recipes19               # noqa: E402
from . import recipes_s75_t22 as _recipes22       # noqa: E402
from .music_styles import _SHARE_RULE as _catalog_share_rule  # noqa: E402
from .music_styles import register_styles as _register_styles  # noqa: E402


def _overlay_entries():
    """The fifteen additions in the ``STYLES`` record shape (one source)."""
    from .music_styles import RECIPES as _rap_recipes
    ids = [sid for sid in _catalog.STYLE_IDS[3:]
           if sid not in _rap_recipes]          # the three rap ids already resolve in the leaf
    out, hints = {}, {}
    for sid in ids:
        rec = _catalog.style(sid)
        if sid in _recipes19.RECIPE_IDS:          # T19 family: compiled prompt
            prompt = _recipes19.compile_style_prompt(sid)
        elif sid in _recipes22.STYLE_IDS:         # T22 family
            prompt = _recipes22.compile_style_field(sid)
        else:                                     # T18 trait-only additions
            prompt = _catalog.provider_hint(sid)
        out[sid] = {
            "style_id": sid,
            "label": rec["label"],
            "sound": rec["description"],
            "description": rec["description"],
            "share_rule": _catalog_share_rule,
            "deliveries": tuple(rec["deliveries"]),
            "notes": ("S75-CATALOG: registered offered style; client "
                      "references are display only"),
            "suno_style_prompt": prompt,
            "client_references": tuple(rec["client_references"]),
            "section_hint": rec["section_hint"],
        }
        hints[sid] = rec["section_hint"]
    return out, hints



_entries, _hints = _overlay_entries()
_register_styles(_entries, _hints)

__all__ = [
    "DELIVERIES",
    "FIRST_SUNG_TARGET_PCT",
    "LENGTH_ALIASES",
    "OFFERED_LENGTHS_S",
    "SCHEMA_VERSION",
    "SPOKEN_SHARE_MAX",
    "SPOKEN_SHARE_MIN",
    "SPOKEN_SHARE_TARGET",
    "SECTION_HINTS",
    "SOURCE_D15",
    "SOURCE_D18",
    "SPOKEN_STYLE_DELIVERIES",
    "STYLES",
    "CONTRADICTING_NEGATIVE_TAGS",
    "DELIVERY_MAP_CLAUSES",
    "DELIVERY_MAP_TEMPLATE",
    "DELIVERY_MAP_VERBS",
    "EXPLICIT_NEVER_INFERRED",
    "RAP_RECIPE_REVISION",
    "RECIPES",
    "SOURCE_S75_T20",
    "TOOL_NAME",
    "TOOL_VERSION",
    "MusicStyleError",
    "assert_delivery_map",
    "assert_no_contradiction",
    "default_delivery_map",
    "delivery_map",
    "enables_explicit_lyrics",
    "extra_style_ids",
    "has_delivery_map",
    "missing_delivery_verbs",
    "recipe",
    "recipe_ids",
    "register_styles",
    "sheet_deliveries",
    "check_first_sung",
    "check_share",
    "d15_range",
    "measure_share",
    "refusal",
    "section_hint",
    "share_pct",
    "spoken_target",
    "spoken_targets",
    "style",
    "style_ids",
    "style_prompt",
    "style_prompt_record",
]
