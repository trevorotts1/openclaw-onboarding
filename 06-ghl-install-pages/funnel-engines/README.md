# Funnel-Build Engine Selector (shared STEP-0) — `06-ghl-install-pages/funnel-engines/`

The ONE registry + selector that routes a **"build me a funnel"** request to the specialist
**authoring engine** that owns that funnel's copy + image IP, BEFORE the template-first funnel
matcher runs. Skill 6 stays the **ONE GHL delivery rail**: every registered engine authors copy
and images inside its own fail-closed pipeline, then **delegates the GHL media folder + upload +
funnel/page build back to Skill 6** (`tools/ghl_media.py` + `tools/ghl_rest_canvas.py` /
`tools/ghl_builder.py`). The selector never builds anything itself and never blocks a build.

## Flow position

```
board task ("build me a signature funnel")
   │
   ├─▶ STEP -0  funnel_engine_selector.step0_select_engine(task, evidence_root)   ← THIS layer
   │       ROUTE_TO_ENGINE  → invoke engine.entry (the canonical fail-closed shell);
   │                          the engine authors copy+images, then delegates GHL delivery
   │                          back to Skill 6. Done.
   │       NO_ENGINE_MATCH  → fall through ↓  (never blocks)
   │
   └─▶ STEP 0   funnel_matcher.step0_match(...)   (template-first, the 38 Brunson templates)
           USE_TEMPLATE / SUGGEST_TEMPLATE / HONOR_USER / CREATE_NEW → generic Skill-6 build
```

`funnel_matcher.py` (template-first, 38 templates) is unchanged and untouched — this selector sits
in front of it and only fires for a **specialist IP funnel** whose engine has registered here.

## Files

| File | What it is |
|---|---|
| `registry.json` | The shared registry — one object in `engines[]` per registered funnel-build engine. |
| `../tools/funnel_engine_selector.py` | The deterministic, stdlib-only selector (scorer + CLI + `--self-test`). |

## Registered engines

| id | Skill | Owns | Entry (canonical fail-closed shell) |
|---|---|---|---|
| `signature-funnel` | 49-signature-funnel | Trevor Otts 12-section Hero + 3/5/7 funnel | `49-signature-funnel/signature-funnel-entry.sh` |

## How to register a SECOND entry (no selector code change)

Append ONE object to `registry.json` → `engines[]`:

```json
{
  "id": "<engine-id>",
  "skill": "<NN-skill-dir>",
  "name": "<display name>",
  "entry": "<NN-skill-dir>/<canonical-entry>.sh",
  "delivery_rail": "06-ghl-install-pages",
  "priority": 10,
  "confidence_threshold": 0.55,
  "match": {
    "names": ["<verbatim product name>", "…"],
    "keywords": ["<strong when-to-use phrases>", "…"],
    "signals": ["<supporting tokens>", "…"],
    "anti_signals": ["<phrases that should NOT route here>", "…"]
  }
}
```

`funnel_engine_selector.py` discovers the new entry automatically (it iterates `engines[]`); no
Python change is required. Higher `priority` and a verbatim `names` hit win ties.

### Forward-ref: Skill 56 (Sales-Page-Assets) is the planned second entry

Skill **56** (direct-response Sales-Page / VSL family — a design-response sibling of Skill 49) will
register the second entry here. When Skill 56 lands it MUST:

1. append its `engines[]` object (id e.g. `sales-page`) with its own canonical entry shell;
2. keep `delivery_rail: 06-ghl-install-pages` (Skill 6 remains the ONE GHL delivery rail);
3. pin the reciprocal deliverable-**labeling grammar** shared with Skill 49 —
   `<client>__<funnel>__<stage>__<type>__vNN` (see `49-signature-funnel/MASTERDOC.md` §8 and
   `SKILL.md`). This is the 49↔56 reciprocal labeling pin.

## CLI

```
python3 06-ghl-install-pages/tools/funnel_engine_selector.py --list
python3 06-ghl-install-pages/tools/funnel_engine_selector.py --match "build my signature funnel"
python3 06-ghl-install-pages/tools/funnel_engine_selector.py --self-test
```

## Client-runtime rule (binding)

The selector is deterministic, model-free Python — it runs identically on every box. The engines it
routes to run on the **client's OWN configured providers and keys on a client box (never Anthropic,
never the operator's)**. Nothing here calls a model or the network.
