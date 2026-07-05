# SOP-WEB-02: AUTHOR THE PER-PAGE-TYPE WEBSITE COPY

**Cluster:** Website-Craft Rules (`universal-sops/website-craft/`)
**Master authority:** `WEBSITE-PIPELINE-MANIFEST.json` + `MASTER-WEBSITE-QC-AUTOFAIL-RULESET.md`
**Owning role:** Conversion Copywriter (Marketing)
**Stage:** P1-COPY
**Produces:** `working/copy/website_copy_ledger.json`
**Prover:** `prove_web_pages.py`

---

## 0. PERSONA STEP 0 (MANDATORY — same as funnel-craft)

Before a single section is written, ground the copy in a matched copywriter persona:

```
persona-selector-v2.py --task "<website copy task>" --department marketing  ->  persona-selection-log.md
```

Write the matched slug into `persona-selection-log.md` in the run dir and reference it from the ledger
(`"persona_selection_log": "persona-selection-log.md"`). A missing log is `AF-WEB-PERSONA-LOG` — copy
authored without a logged persona is not accepted.

## 1. THE BRAND-VOICE ANCHOR — never voice-unanchored

### 1(a) Primary lock

Anchor every page to `brand-voice-lock.md` (tone, diction, cadence, banned words). Record it:
`"brand_voice_source": "brand-voice-lock.md"`.

### 1(b) Provisional lock on the fast path (FIX-COPY-04 ii)

When `brand-voice-lock.md` is **absent** (a fast, standalone request), do NOT author voice-unanchored
copy. Derive a **PROVISIONAL** lock from, in order:

1. the **Skill 55 Product Bio** (`product-bio` deliverable) — the founder's own words + product framing;
2. else **Skill 52 brand intelligence** (brand voice / avatar analysis).

Record the source: `"brand_voice_source": "provisional:skill-55-product-bio"` (or
`"provisional:skill-52-brand-intel"`). A ledger with neither a lock nor a provisional lock is
`AF-WEB-VOICE-UNANCHORED`.

## 2. THE PER-PAGE-TYPE CONTRACTS (the machine bar)

The prover MEASURES stripped text — whitespace never satisfies a floor and a self-reported count is
never trusted.

### Home — StoryBrand SB7 wireframe (`AF-WEB-HOME-SB7`, `AF-WEB-HOME-THIN`)

The Home page carries all **7** SB7 roles, each as a `sections[]` entry with its `role`:

| SB7 role | The section's job |
|---|---|
| `character` | Name the customer and what they want. |
| `problem` | The external + internal + philosophical problem. |
| `guide` | The brand as guide — empathy + authority (proof lives here). |
| `plan` | The 3-step plan to work with you. |
| `call_to_action` | The ONE direct CTA (matches the intake primary CTA). |
| `success` | The transformation after they act. |
| `stakes` | What's at stake if they don't (the cost of inaction). |

Page total ≥ **250** words. Missing any role = `AF-WEB-HOME-SB7`.

### Services — one substantive block per service (`AF-WEB-SERVICE-THIN`, `AF-WEB-SERVICES-EMPTY`)

Each service is a `services[]` entry `{name, text}`; each `text` is **≥ 400 stripped words**: what it
is, who it's for, the outcome, how it works, proof, and the CTA. An empty services array is
`AF-WEB-SERVICES-EMPTY`.

### About — the trust page (`AF-WEB-ABOUT-THIN`)

`text` is **≥ 500 stripped words**: founder story, mission, credibility, values, and why the customer
should trust you — anchored to the founder's REAL name and confirmed credentials (truth gate).

### FAQ — objection removal (`AF-WEB-FAQ-COUNT`)

`faqs[]` of `{q, a}` pairs, **≥ 8** complete pairs, each answer written to remove a real buying
objection (price, time, risk, fit, trust). Empty question OR answer does not count toward the 8.

## 3. COPY DEPTH

Honor the intake `copy_depth`: `short` writes to the floor; `standard` writes above it; `long-form`
writes the full direct-response treatment per page. Never write BELOW a floor to hit "short" —
under-length is a hard `AF-WEB-*` miss, not a style choice. Escalate instead of floor-lowering.

## 4. LEDGER SHAPE

Write `working/copy/website_copy_ledger.json`:

```json
{
  "brand": "<brand>",
  "brand_voice_source": "brand-voice-lock.md | provisional:skill-55-product-bio | provisional:skill-52-brand-intel",
  "persona_selection_log": "persona-selection-log.md",
  "pages": [
    {"page_type": "home", "name": "Home", "sections": [{"role": "character", "text": "..."}, ...]},
    {"page_type": "services", "name": "Services", "services": [{"name": "...", "text": "..."}]},
    {"page_type": "about", "name": "About", "text": "..."},
    {"page_type": "faq", "name": "FAQ", "faqs": [{"q": "...", "a": "..."}]}
  ]
}
```

## 5. VERIFY BEFORE ADVANCING

```
python3 universal-sops/website-craft/prove_web_pages.py working/copy/website_copy_ledger.json
```

Exit 0 = every present page cleared its floor and P2-PROMPTS (SOP-WEB-03) may begin. Any `AF-WEB-*` =
the failing page re-authors ONLY itself under the bounded retry cap; copy cannot advance until all
present pages pass. Never floor, cap, or drop a page to make a gate pass — escalate instead.
