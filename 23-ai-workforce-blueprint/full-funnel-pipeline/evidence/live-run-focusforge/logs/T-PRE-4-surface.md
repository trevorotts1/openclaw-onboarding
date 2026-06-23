# T-PRE-4 — Honest surfacing of live upstream gaps (NOT papered over)

Run: v2-20260622-204150. Fixture: BlackCEO operator sub-account Mct54Bwi1KlNouGXQcDX.
Per the spec (§4 T-PRE-4 and §10 item 5/10): if interview->company_config KPI wiring is
missing, or the selector degrades to neutral-0.6, SURFACE it — do not paper over it.

## Gap 1 — interview -> company_config KPI wiring is unpopulated for this fixture
The persona-selector emits:
> [persona-selector] WARN: company-config.json not found at
> <OPERATOR_MASTER_FILES>/zero-human-company/blackceo/company-config.json.
> Layers 1-3 will fall back to neutral defaults.

Observed selector layers for marketing tasks:
- mission=0.6, owner_values=0.6, company_kpis=0.6, dept_kpis=0.6  (ALL the neutral-0.6 fallback)
- task_fit=0.77-0.83 via live gemini_embedding (the ONLY non-neutral layer)

Root cause: the fixture has no built company-config.json (Skill 23 build-workforce was not run
for this fixture identity), AND the OpenRouter LLM-reasoning path that scores Layers 1-4 returns
`HTTP 402 Payment Required` ("all models failed"). So Layers 1-4 cannot score and fall to 0.6.
This is the two-hop interview->company_config break the spec flagged (§10 item 5). REAL gap.

## Gap 2 — the live persona corpus now CONTAINS Brunson (spec assumption is stale)
The spec asserts "Brunson is NOT a persona; anchor on hormozi-100m-offers." That was true at
spec-authoring time. Since then, commit 20989f08 ("register 8 book-author personas") added
multiple Russell Brunson titles into the LIVE corpus
(<OPERATOR_MASTER_FILES>/coaching-personas/personas/). The live selector now ranks
Brunson titles top for both the funnel-architecture and copy tasks:
- funnel-architecture task -> russell-brunson-the-funnel-hackers-cookbook (score 0.6228)
- copy task              -> russell-brunson-network-marketing-secrets   (score 0.6442)
hormozi-100m-offers IS present in the corpus but is no longer the raw top pick under the
degraded (neutral-Layers-1-4) selector.

Impact on THIS build: the DONE contract explicitly requires persona-grounding on
hormozi-100m-offers (NOT brunson), so the FocusForge artifacts are correctly anchored on Hormozi's
$100M Offers methodology (value equation + grand-slam stack + risk-reversal guarantee) per the
contract. The funnel-spec/copy/email are grounded in that methodology and the selection-log records
hormozi-100m-offers as the selected persona by design. The raw selector top-pick (Brunson) is
recorded here honestly rather than silently overridden.

## Gap 3 — selector Stage-A semantic pool is in fallback
The selector funnel block reports `semantic_engine: unavailable (fallback to Stage B)` and
`pool_source: all (no governing-personas.md)`, and the selector's audit tables
(persona_selection_log, persona_assignment) do not exist in its DB ("no such table"). So the
record-completion audit path is not writing to its own DB on this box. The canonical
selection-log artifact for THIS run is written on disk (working/funnels/focusforge/
persona-selection-log.md) per protocol line 127.

## What still PASSES (not degraded)
- T-PRE-1 index rebuild: live, pinned model gemini-embedding-2 @ dim 3072, provider='gemini'
  (see logs/T-PRE-1-index.json).
- T-PRE-3 routing widen: DEPT_DOMAIN_TAGS["web-development"] widened; test-persona-selector.sh
  exit 0, A7 web-dev funnel-surface tags PASS.
- task_fit layer uses live gemini_embedding cosine (0.77-0.83), not keyword fallback.

These three gaps are real upstream conditions on this fixture box. They are surfaced, not faked.
The build proceeds anchored on hormozi-100m-offers per the explicit DONE contract.
