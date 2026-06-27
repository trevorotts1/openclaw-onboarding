# Funnel Template Catalog (Skill 6 — GHL Install Pages)

Structured, reusable funnel templates derived from the Brunson funnel-system
library. 38 templates across 5 groups. Each template is a self-contained JSON
that the template-first matcher (STEP 0) uses to choose a proven structure
before any net-new funnel is generated.

## Groups

| Group | Count | Description |
|---|---|---|
| `buyer/` | 8 | Transaction / product-purchase funnels |
| `event/` | 11 | Webinar, summit, product-launch, meeting |
| `lead/` | 9 | List-building and opt-in funnels |
| `retention-followup/` | 2 | Cancellation save and follow-up |
| `traffic-advanced/` | 8 | Cold-traffic pre-frame and funnel hub |

## Template schema

Each `<id>.json` contains:

```
{
  "id": "slug",
  "name": "Human name",
  "aliases": [...],
  "category": "...",
  "lengthClass": "short-form | long-form | mid-form",
  "whenToUse": {
    "summary": "...",
    "goals": [...],
    "keywords": [...],
    "signals": [...],
    "antiSignals": [...]
  },
  "pageStructure": [
    { "order": 1, "page": "...", "purpose": "...", "blocks": [...],
      "skill44Widgets": [...] }
  ],
  "copyFramework": {
    "primaryPersona": "persona-id OR {slug,book,script,role} object",
    "supportingPersonas": [...],
    "scripts": "..."
  },
  "ghlBuild": { ... }
}
```

Two schema dialects coexist (camelCase `whenToUse/pageStructure/copyFramework`
and snake_case `when_to_use/page_structure/copy_framework`). The matcher
normalizes both; no migration needed.

## Book personas

Five personas appear across the catalog. The `copy_persona` field the matcher
returns tells the builder's copy step which voice to write in:

| Persona id | Label | Author / Book |
|---|---|---|
| `funnel-architect` | The Funnel Architect | Russell Brunson — DotCom Secrets |
| `expert-guide` | The Expert Guide | Russell Brunson — Expert Secrets |
| `traffic-strategist` | The Traffic Strategist | Russell Brunson — Traffic Secrets |
| `story-brander` | The Story Brander | Donald Miller — Building a StoryBrand |
| `copy-closer` | The Copy Closer | Jim Edwards — Copywriting Secrets |

## STEP 0 wiring

The matcher engine lives in `../tools/funnel_matcher.py`. To make a build
template-first, set either env var before the build:

```
export GHL_FUNNEL_CATALOG=/path/to/06-ghl-install-pages/funnel-templates
# or, faster (skip live scan):
export GHL_FUNNEL_INDEX=/path/to/06-ghl-install-pages/tools/catalog-index.json
```

`dispatch_one()` in `v2_dispatcher.py` then auto-calls `step0_match` before the
builder runs. A USE_TEMPLATE decision injects `task['pages']` (instantiated page
plan) and `task['copy_persona']`; a CREATE_NEW decision is a no-op (builder
generates from scratch, and the result is saved back to grow the library).

See `../tools/funnel_matcher.py` and `../tools/funnel_matcher_cli.py` for the
engine and the CLI (`--build-index`, `--match "<text>"`, `--selftest`).
