# Retired HTML-formatter LLM calls (source stages 06 / 08 / 11 / 13 / 15)

The source anthology workflow used five LLM calls to convert markdown into HTML:

| Source stage | Purpose | Disposition |
|---|---|---|
| `06-tone-html-formatter` | tone doc → HTML | **RETIRED** |
| `08-titles-html-formatter` | titles → HTML | **RETIRED** |
| `11-outline-html-formatter` | outline → HTML | **RETIRED** |
| `13-chapter-html-formatter` | chapter → HTML | **RETIRED** |
| `15-chapter-rewrite-html-formatter` | rewrite → HTML | **RETIRED** |

**Why retired:** formatting is mechanical and must be reproducible. A model that
formats can also silently drop or reword content (that is exactly the class of
defect the sibling engines gate as content-loss). In Skill 54 all formatting is
done by **deterministic Python** (`aw_render_pdf` + `assets/print-style.css`), so
there is **no formatter model tier** in `assets/model-map.template.json` and no
concrete model id is baked anywhere. This removes five LLM calls (and their
per-call cost/latency) with zero loss of fidelity.

These stages are recorded here for provenance only; nothing in this directory is
executed at runtime.
