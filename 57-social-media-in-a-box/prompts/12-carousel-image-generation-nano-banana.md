# Prompt 12 - Carousel Slide Generation Prompt Template (GPT Image 2.5 sunburst; file name kept for the hash pin)

- **Source workflow:** `part6-carousel-image` (Social media in a box part 6: Carousel Image Creator)
- **Model at export time:** kie.ai `nano-banana-pro` (retired for social images)
- **Model now (2026-10-05):** `gpt-image-2-5-sunburst-text-to-image` (Skill 66 id, AGENTS.md N43): owner order is that social images use KIE GPT Image 2.5, not Nano Banana. N43 substitutes `3:4` for `4:5`, so the ratio below is `3:4` (the Instagram crop-safety logic in prompt 13 already assumes 3:4). Canonical KIE rules: `07-kie-setup/references/kie-common-rules.md`.
- **Prompt length:** the `prompt` value below is the budget-expanded prompt (prompt 05 expands the 09/10 slide seed to 95 to 100 percent of the model maxLength from Skill 74 `prompt-budget`, floor 80 percent). Dispatch runs `validate`, `preflight` and `run --mode active` through `74-kie-live-adapter` (see `modules/3-media-core/README.md`).
- **Purpose:** Image-generation payload: slide prompt + typographic integration instruction for textOnImage; 3:4 (N43 substitute for 4:5), 2K, png via Kie.ai createTask.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## User (API payload template — prompt field)

_Source: node `Nano Banana Generate` → jsonBody_

```
{
  "model": "gpt-image-2-5-sunburst-text-to-image",
  "input": {
    "prompt": {{ JSON.stringify($json.prompt + ". Incorporate the text '" + $json.textOnImage + "' as a powerful, stylized typographic design element. The text must be bold, highly readable, and artistically integrated into the composition using dynamic font styling, strategic placement, and visual effects that make it pop while harmonizing with the overall aesthetic.") }},
    "aspect_ratio": "3:4",
    "resolution": "2K"
  }
}
```
