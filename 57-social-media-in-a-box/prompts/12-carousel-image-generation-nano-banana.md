# Prompt 12 — Carousel Slide Generation Prompt Template (Nano Banana Pro)

- **Source workflow:** `part6-carousel-image` (Social media in a box part 6: Carousel Image Creator)
- **Model at export time:** kie.ai `nano-banana-pro`
- **Model id check (Skill 66 registry, 2026-10-05):** `nano-banana-pro` is the canonical Skill 66 id (supports 4:5, 1K/2K/4K, png). Deliberate pin kept: the carousel renderer is a Nano Banana Pro flow. Skill 66 is authoritative for ids; canonical KIE rules: `07-kie-setup/references/kie-common-rules.md`.
- **Purpose:** Image-generation payload: slide prompt + typographic integration instruction for textOnImage; 4:5, 2K, png via Kie.ai createTask.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## User (API payload template — prompt field)

_Source: node `Nano Banana Generate` → jsonBody_

```
{
  "model": "nano-banana-pro",
  "input": {
    "prompt": {{ JSON.stringify($json.prompt + ". Incorporate the text '" + $json.textOnImage + "' as a powerful, stylized typographic design element. The text must be bold, highly readable, and artistically integrated into the composition using dynamic font styling, strategic placement, and visual effects that make it pop while harmonizing with the overall aesthetic.") }},
    "aspect_ratio": "4:5",
    "resolution": "2K",
    "output_format": "png"
  }
}
```
