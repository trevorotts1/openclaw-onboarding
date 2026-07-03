# Prompt 14 — Podcast Cover Art Prompt Template

- **Source workflow:** `part9-podcast-image` (Social Media In A Box Part 9: podcast Image Creator)
- **Model at export time:** kie.ai `google/nano-banana`
- **Purpose:** Square (1:1) podcast cover generation: upstream image_prompt + fixed suffix ('square podcast cover art... professional, clean, visually striking'). Retry node uses the identical template.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## User (API payload template — prompt field; identical in `Nano Banana Retry`)

_Source: node `Nano Banana Generate` → jsonBody_

```
{
  "model": "google/nano-banana",
  "input": {
    "prompt": {{ JSON.stringify($('Data Setup').item.json.image_prompt + ". Create a square podcast cover art image. Professional, clean, visually striking. Suitable for podcast platforms.") }},
    "output_format": "jpeg",
    "image_size": "1:1"
  }
}
```
