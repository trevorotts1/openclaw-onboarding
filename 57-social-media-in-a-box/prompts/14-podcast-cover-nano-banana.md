# Prompt 14 — Podcast Cover Art Prompt Template

- **Source workflow:** `part9-podcast-image` (Social Media In A Box Part 9: podcast Image Creator)
- **Model at export time:** kie.ai `google/nano-banana` (legacy; Skill 66 marks it compatibility-only)
- **Model now (2026-10-05):** `gpt-image-2-5-sunburst-text-to-image`, the Skill 66 id and AGENTS.md N43 pin, identical to what Skill 58 `generate_cover.sh` sends for the same cover (it is seeded from this prompt). 1:1, 2K, png. The legacy id and its `image_size`/jpeg payload are retired here so the two skills no longer disagree.
- **Purpose:** Square (1:1) podcast cover generation: upstream image_prompt + fixed suffix ('square podcast cover art... professional, clean, visually striking'). Retry node uses the identical template.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## User (API payload template — prompt field; identical in `Nano Banana Retry`)

_Source: node `Nano Banana Generate` → jsonBody_

```
{
  "model": "gpt-image-2-5-sunburst-text-to-image",
  "input": {
    "prompt": {{ JSON.stringify($('Data Setup').item.json.image_prompt + ". Create a square podcast cover art image. Professional, clean, visually striking. Suitable for podcast platforms.") }},
    "aspect_ratio": "1:1",
    "resolution": "2K"
  }
}
```
