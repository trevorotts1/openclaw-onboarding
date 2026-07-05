# Website-Craft SOP Cluster (`universal-sops/website-craft/`)

The SHARED, cross-department procedure for how any department authors and ships a multi-page
marketing **website** (Home / Services / About / FAQ / Contact) with a real per-page-type **copy
contract**. It is the website sibling of `universal-sops/funnel-craft/`: same persona Step 0, same
"measure the artifact, never trust a self-reported count" discipline, same delegation of the build to
Skill 6 as the ONE delivery rail.

Created by **FIX-COPY-03** (`MASTER-fix-plan-2026-07-05.md`): before this cluster, a multi-page
website had **no copy contract at all** — web-development owned the build but nothing floored the copy,
so pages shipped thin. This cluster closes that gap.

## Why a website needs its own cluster (not funnel-craft)

A funnel is one escalating argument across a fixed page set with SACRED char/word bands. A website is a
set of **page TYPES**, each with its own job and its own floor:

| Page type | Framework / floor | Prover gate |
|---|---|---|
| **Home** | StoryBrand **SB7** wireframe — all 7 roles (character, problem, guide, plan, call-to-action, success, stakes); page ≥ 250 words | `AF-WEB-HOME-SB7`, `AF-WEB-HOME-THIN` |
| **Services** | each service block ≥ **400** stripped words | `AF-WEB-SERVICE-THIN` |
| **About** | ≥ **500** stripped words | `AF-WEB-ABOUT-THIN` |
| **FAQ** | ≥ **8** complete Q&A pairs | `AF-WEB-FAQ-COUNT` |

## The persona Step 0 (shared with funnel-craft)

Copy is authored by the **Conversion Copywriter** and MUST be persona-grounded FIRST:

```
persona-selector-v2.py --task "<website copy task>" --department marketing  ->  persona-selection-log.md
```

A missing log is `AF-WEB-PERSONA-LOG`. This is the same Step 0 the funnel-craft cluster requires.

## Brand-voice anchor (never voice-unanchored)

Copy is anchored to `brand-voice-lock.md`. On a fast path where that lock is absent, derive a
**PROVISIONAL** lock from the **Skill 55 Product Bio** or **Skill 52 brand intelligence** and record it
as `"brand_voice_source": "provisional:skill-55-product-bio"` (or `provisional:skill-52-brand-intel`).
A ledger with neither is `AF-WEB-VOICE-UNANCHORED` (SOP-WEB-02 §1b).

## The ONE way to verify a website's copy

```
python3 universal-sops/website-craft/prove_web_pages.py working/copy/website_copy_ledger.json
```

Exit 0 = every present page cleared its floor and P2-PROMPTS/P3-BUILD may begin. Any `AF-WEB-*` = fix
the copy and re-run. The prover MEASURES stripped text and is provider-neutral stdlib Python — it never
calls a model and never trusts a self-reported count.

## Files

| File | What it governs |
|---|---|
| `WEBSITE-PIPELINE-MANIFEST.json` | The shared pipeline manifest (phases, owning roles, SOP refs, gate codes, floors). |
| `SOP-WEB-01-INTAKE.md` | Lock the website brief in ONE block: sitemap, per-page goal, offers, truth gate. |
| `SOP-WEB-02-COPY.md` | Author the per-page-type copy against the floors; persona Step 0; brand-voice provisional lock. |
| `SOP-WEB-03-PROMPTS-IMAGES.md` | Per-section image prompts — DELEGATED to the Skill 6 image stage. |
| `SOP-WEB-04-BUILD.md` | GHL/website build — DELEGATED to Skill 6 (the ONE delivery rail). |
| `SOP-WEB-05-CERTIFY.md` | Prover pass + signed certificate + preview/approve. |
| `MASTER-WEBSITE-QC-AUTOFAIL-RULESET.md` | The `AF-WEB-*` auto-fail table every page is measured against. |
| `prove_web_pages.py` | The deterministic, model-free page-floor prover. |

## Delivery is DELEGATED to Skill 6

This cluster does NOT re-implement the builder. A website is built through the Skill 6 dispatcher
(`06-ghl-install-pages/tools/v2_dispatcher.py`) exactly like a funnel/page. When the request is a
standalone "write it for me" website, the dispatcher's **P2-COPY mini-epic** (FIX-COPY-01) already
routes copy authoring to the marketing department and HOLDS the build until an APPROVED `copy.md`
exists — this cluster is the copy contract that authoring satisfies.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys.
Generation + adversarial verify run on the CLIENT's own strongest configured provider; the
deterministic gate (`prove_web_pages.py`) is provider-neutral Python.
